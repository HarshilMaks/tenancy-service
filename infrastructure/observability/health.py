"""
Health Check Module - Production Readiness & Liveness Probes
=============================================================

Enterprise health check framework for Kubernetes readiness/liveness
probes and service discovery.

Health Check Types:
    - Liveness: Is the service running? (restart if false)
    - Readiness: Can the service handle traffic? (remove from LB if false)
    - Startup: Has the service finished starting? (for slow starters)

Components Monitored:
    - Database connectivity
    - Message broker connectivity
    - External API dependencies
    - Memory/CPU thresholds
    - Custom application checks

Output Formats:
    - JSON (default)
    - Kubernetes probe format
    - Prometheus metrics

Author: Platform Engineering Team
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from .logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Health Status
# =============================================================================

class HealthStatus(Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Working but impaired
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """
    Health status for a single component.
    
    Attributes:
        name: Component identifier
        status: Health status
        message: Optional status message
        latency_ms: Time to complete check
        details: Additional diagnostic info
        last_checked: When check was performed
    """
    name: str
    status: HealthStatus
    message: Optional[str] = None
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    last_checked: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY
    
    @property
    def is_degraded(self) -> bool:
        return self.status == HealthStatus.DEGRADED
    
    @property
    def is_unhealthy(self) -> bool:
        return self.status == HealthStatus.UNHEALTHY
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "details": self.details,
            "last_checked": self.last_checked.isoformat(),
        }


@dataclass
class HealthReport:
    """
    Aggregate health report for the service.
    
    Contains status of all checked components and overall service health.
    """
    status: HealthStatus
    service_name: str
    version: str
    uptime_seconds: float
    components: List[ComponentHealth]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY
    
    @property
    def unhealthy_components(self) -> List[ComponentHealth]:
        return [c for c in self.components if c.is_unhealthy]
    
    @property
    def degraded_components(self) -> List[ComponentHealth]:
        return [c for c in self.components if c.is_degraded]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "service": self.service_name,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "timestamp": self.timestamp.isoformat(),
            "components": [c.to_dict() for c in self.components],
            "summary": {
                "total": len(self.components),
                "healthy": sum(1 for c in self.components if c.is_healthy),
                "degraded": sum(1 for c in self.components if c.is_degraded),
                "unhealthy": sum(1 for c in self.components if c.is_unhealthy),
            },
        }


# =============================================================================
# Health Check Types
# =============================================================================

# Type for health check functions
HealthCheckFunc = Callable[[], ComponentHealth]
AsyncHealthCheckFunc = Callable[[], "asyncio.coroutine"]


@dataclass
class HealthCheckConfig:
    """Configuration for a health check."""
    name: str
    check_func: Union[HealthCheckFunc, AsyncHealthCheckFunc]
    timeout_seconds: float = 5.0
    critical: bool = True  # If true, unhealthy = service unhealthy
    interval_seconds: float = 30.0
    enabled: bool = True


# =============================================================================
# Built-in Health Checks
# =============================================================================

def check_database(
    get_session_func: Callable,
    timeout: float = 5.0,
) -> HealthCheckFunc:
    """
    Create database connectivity health check.
    
    Args:
        get_session_func: Function that returns DB session
        timeout: Query timeout in seconds
        
    Returns:
        Health check function
    """
    def check() -> ComponentHealth:
        start = time.perf_counter()
        
        try:
            session = get_session_func()
            # Simple connectivity test
            result = session.execute("SELECT 1")
            result.close()
            session.close()
            
            latency = (time.perf_counter() - start) * 1000
            
            # Warn if slow
            status = HealthStatus.HEALTHY
            message = None
            if latency > 1000:  # > 1 second
                status = HealthStatus.DEGRADED
                message = f"Slow response: {latency:.0f}ms"
            
            return ComponentHealth(
                name="database",
                status=status,
                message=message,
                latency_ms=latency,
                details={"type": "postgresql"},
            )
            
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            logger.error(f"Database health check failed: {e}", exc_info=True)
            
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency,
                details={"error_type": type(e).__name__},
            )
    
    return check


def check_redis(
    redis_client,
    timeout: float = 2.0,
) -> HealthCheckFunc:
    """Create Redis connectivity health check."""
    def check() -> ComponentHealth:
        start = time.perf_counter()
        
        try:
            redis_client.ping()
            latency = (time.perf_counter() - start) * 1000
            
            # Get additional info
            info = redis_client.info("server")
            
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                details={
                    "version": info.get("redis_version"),
                    "connected_clients": info.get("connected_clients"),
                },
            )
            
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            logger.error(f"Redis health check failed: {e}", exc_info=True)
            
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency,
            )
    
    return check


def check_external_api(
    name: str,
    url: str,
    expected_status: int = 200,
    timeout: float = 5.0,
) -> HealthCheckFunc:
    """Create external API health check."""
    def check() -> ComponentHealth:
        import httpx
        
        start = time.perf_counter()
        
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url)
            
            latency = (time.perf_counter() - start) * 1000
            
            if response.status_code == expected_status:
                return ComponentHealth(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency,
                    details={"url": url, "status_code": response.status_code},
                )
            else:
                return ComponentHealth(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message=f"Unexpected status: {response.status_code}",
                    latency_ms=latency,
                    details={"url": url, "status_code": response.status_code},
                )
                
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=latency,
                details={"url": url},
            )
    
    return check


def check_memory(
    threshold_percent: float = 90.0,
) -> HealthCheckFunc:
    """Create memory usage health check."""
    def check() -> ComponentHealth:
        try:
            import psutil
            
            memory = psutil.virtual_memory()
            used_percent = memory.percent
            
            status = HealthStatus.HEALTHY
            message = None
            
            if used_percent > threshold_percent:
                status = HealthStatus.UNHEALTHY
                message = f"Memory usage critical: {used_percent:.1f}%"
            elif used_percent > threshold_percent - 10:
                status = HealthStatus.DEGRADED
                message = f"Memory usage high: {used_percent:.1f}%"
            
            return ComponentHealth(
                name="memory",
                status=status,
                message=message,
                details={
                    "used_percent": used_percent,
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                },
            )
            
        except ImportError:
            return ComponentHealth(
                name="memory",
                status=HealthStatus.HEALTHY,
                message="psutil not installed, check skipped",
            )
        except Exception as e:
            return ComponentHealth(
                name="memory",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {e}",
            )
    
    return check


def check_disk(
    path: str = "/",
    threshold_percent: float = 90.0,
) -> HealthCheckFunc:
    """Create disk usage health check."""
    def check() -> ComponentHealth:
        try:
            import psutil
            
            disk = psutil.disk_usage(path)
            used_percent = disk.percent
            
            status = HealthStatus.HEALTHY
            message = None
            
            if used_percent > threshold_percent:
                status = HealthStatus.UNHEALTHY
                message = f"Disk usage critical: {used_percent:.1f}%"
            elif used_percent > threshold_percent - 10:
                status = HealthStatus.DEGRADED
                message = f"Disk usage high: {used_percent:.1f}%"
            
            return ComponentHealth(
                name="disk",
                status=status,
                message=message,
                details={
                    "path": path,
                    "used_percent": used_percent,
                    "total_gb": disk.total / (1024**3),
                    "free_gb": disk.free / (1024**3),
                },
            )
            
        except ImportError:
            return ComponentHealth(
                name="disk",
                status=HealthStatus.HEALTHY,
                message="psutil not installed, check skipped",
            )
        except Exception as e:
            return ComponentHealth(
                name="disk",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {e}",
            )
    
    return check


# =============================================================================
# Health Checker
# =============================================================================

class HealthChecker:
    """
    Central health check coordinator.
    
    Manages registration and execution of health checks,
    provides aggregated health status.
    
    Usage:
        >>> checker = HealthChecker("tenancy_service", "1.0.0")
        >>> checker.register("database", check_database(get_session))
        >>> checker.register("redis", check_redis(redis_client))
        >>> 
        >>> # Get health report
        >>> report = checker.check_health()
        >>> print(report.status)  # HealthStatus.HEALTHY
    """
    
    def __init__(
        self,
        service_name: str,
        version: str,
        start_time: Optional[datetime] = None,
    ):
        self.service_name = service_name
        self.version = version
        self.start_time = start_time or datetime.now(timezone.utc)
        
        self._checks: Dict[str, HealthCheckConfig] = {}
        self._last_results: Dict[str, ComponentHealth] = {}
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        logger.info(
            f"Health checker initialized for {service_name} v{version}",
            service=service_name,
            version=version,
        )
    
    @property
    def uptime_seconds(self) -> float:
        """Get service uptime in seconds."""
        delta = datetime.now(timezone.utc) - self.start_time
        return delta.total_seconds()
    
    def register(
        self,
        name: str,
        check_func: Union[HealthCheckFunc, AsyncHealthCheckFunc],
        timeout_seconds: float = 5.0,
        critical: bool = True,
        enabled: bool = True,
    ) -> None:
        """
        Register a health check.
        
        Args:
            name: Check identifier
            check_func: Function that performs the check
            timeout_seconds: Check timeout
            critical: If true, failure = service unhealthy
            enabled: Whether check is active
        """
        self._checks[name] = HealthCheckConfig(
            name=name,
            check_func=check_func,
            timeout_seconds=timeout_seconds,
            critical=critical,
            enabled=enabled,
        )
        
        logger.debug(
            f"Registered health check: {name}",
            check_name=name,
            critical=critical,
            timeout=timeout_seconds,
        )
    
    def unregister(self, name: str) -> None:
        """Remove a health check."""
        if name in self._checks:
            del self._checks[name]
            logger.debug(f"Unregistered health check: {name}")
    
    def check_health(
        self,
        include_non_critical: bool = True,
    ) -> HealthReport:
        """
        Run all health checks and return aggregate report.
        
        Args:
            include_non_critical: Include non-critical checks
            
        Returns:
            HealthReport with all component statuses
        """
        start = time.perf_counter()
        components: List[ComponentHealth] = []
        
        # Run checks
        for name, config in self._checks.items():
            if not config.enabled:
                continue
            if not include_non_critical and not config.critical:
                continue
            
            try:
                # Run with timeout
                check_start = time.perf_counter()
                result = self._run_check(config)
                
                components.append(result)
                self._last_results[name] = result
                
            except Exception as e:
                logger.error(f"Health check '{name}' failed: {e}", exc_info=True)
                
                result = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check error: {e}",
                )
                components.append(result)
                self._last_results[name] = result
        
        # Determine overall status
        overall_status = self._calculate_overall_status(components)
        
        # Create report
        report = HealthReport(
            status=overall_status,
            service_name=self.service_name,
            version=self.version,
            uptime_seconds=self.uptime_seconds,
            components=components,
        )
        
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"Health check completed: {overall_status.value} ({duration_ms:.1f}ms)",
            status=overall_status.value,
            duration_ms=duration_ms,
            healthy_count=sum(1 for c in components if c.is_healthy),
            unhealthy_count=sum(1 for c in components if c.is_unhealthy),
        )
        
        return report
    
    def check_liveness(self) -> ComponentHealth:
        """
        Quick liveness check (is the process alive?).
        
        For Kubernetes liveness probe.
        """
        return ComponentHealth(
            name="liveness",
            status=HealthStatus.HEALTHY,
            message="Service is alive",
            details={"uptime_seconds": self.uptime_seconds},
        )
    
    def check_readiness(self) -> HealthReport:
        """
        Full readiness check (can we handle traffic?).
        
        For Kubernetes readiness probe.
        """
        return self.check_health(include_non_critical=False)
    
    def check_startup(self) -> ComponentHealth:
        """
        Startup check (has initialization completed?).
        
        For Kubernetes startup probe.
        """
        # Check if minimum uptime has passed
        if self.uptime_seconds < 5:
            return ComponentHealth(
                name="startup",
                status=HealthStatus.UNHEALTHY,
                message="Service still starting",
                details={"uptime_seconds": self.uptime_seconds},
            )
        
        # Check critical components
        critical_healthy = all(
            self._last_results.get(name, ComponentHealth(name, HealthStatus.UNHEALTHY)).is_healthy
            for name, config in self._checks.items()
            if config.critical and config.enabled
        )
        
        if critical_healthy:
            return ComponentHealth(
                name="startup",
                status=HealthStatus.HEALTHY,
                message="Service started successfully",
                details={"uptime_seconds": self.uptime_seconds},
            )
        else:
            return ComponentHealth(
                name="startup",
                status=HealthStatus.UNHEALTHY,
                message="Critical components not ready",
                details={"uptime_seconds": self.uptime_seconds},
            )
    
    def _run_check(self, config: HealthCheckConfig) -> ComponentHealth:
        """Run a single health check with timeout."""
        import concurrent.futures
        
        future = self._executor.submit(config.check_func)
        
        try:
            return future.result(timeout=config.timeout_seconds)
        except concurrent.futures.TimeoutError:
            return ComponentHealth(
                name=config.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check timed out after {config.timeout_seconds}s",
            )
    
    def _calculate_overall_status(
        self,
        components: List[ComponentHealth],
    ) -> HealthStatus:
        """Calculate overall health from component statuses."""
        
        # Get critical components
        critical_names = {
            name for name, config in self._checks.items()
            if config.critical
        }
        
        critical_components = [
            c for c in components if c.name in critical_names
        ]
        
        # If any critical component is unhealthy, service is unhealthy
        if any(c.is_unhealthy for c in critical_components):
            return HealthStatus.UNHEALTHY
        
        # If any component is degraded, service is degraded
        if any(c.is_degraded for c in components):
            return HealthStatus.DEGRADED
        
        # All healthy
        return HealthStatus.HEALTHY
    
    def get_prometheus_metrics(self) -> str:
        """Export health metrics in Prometheus format."""
        lines = [
            "# HELP health_check_status Health check status (1=healthy, 0.5=degraded, 0=unhealthy)",
            "# TYPE health_check_status gauge",
        ]
        
        status_values = {
            HealthStatus.HEALTHY: 1,
            HealthStatus.DEGRADED: 0.5,
            HealthStatus.UNHEALTHY: 0,
        }
        
        for name, result in self._last_results.items():
            value = status_values.get(result.status, 0)
            lines.append(f'health_check_status{{component="{name}"}} {value}')
        
        lines.extend([
            "# HELP health_check_latency_seconds Health check latency",
            "# TYPE health_check_latency_seconds gauge",
        ])
        
        for name, result in self._last_results.items():
            if result.latency_ms:
                latency_seconds = result.latency_ms / 1000
                lines.append(f'health_check_latency_seconds{{component="{name}"}} {latency_seconds}')
        
        return "\n".join(lines)


# =============================================================================
# Global Health Checker
# =============================================================================

_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker("tenancy_service", "1.0.0")
    return _health_checker


def register_health_check(
    name: str,
    check_func: HealthCheckFunc,
    **kwargs,
) -> None:
    """Register health check with global checker."""
    get_health_checker().register(name, check_func, **kwargs)


def check_health() -> HealthReport:
    """Run health checks using global checker."""
    return get_health_checker().check_health()


__all__ = [
    # Status types
    "HealthStatus",
    "ComponentHealth",
    "HealthReport",
    "HealthCheckConfig",
    
    # Health checker
    "HealthChecker",
    "get_health_checker",
    "register_health_check",
    "check_health",
    
    # Built-in checks
    "check_database",
    "check_redis",
    "check_external_api",
    "check_memory",
    "check_disk",
]
