"""Monitoring & Alerting

Provides basic monitoring for system health, performance metrics, and error tracking.
Includes alerting for critical issues with TTL caching.
"""

import logging
import time
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)

# Sensitive keywords that should not be recorded as metrics
SENSITIVE_KEYWORDS = ['password', 'secret', 'key', 'token', 'api_key', 'credential', 'auth']
MAX_METRIC_NAME_LENGTH = 100
VALID_METRIC_PATTERN = r'^[a-z0-9_]+$'
CACHE_TTL_SECONDS = 30  # Time to live for cached data


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class CachedValue:
    """Cached value with TTL."""
    value: Any
    timestamp: datetime
    ttl_seconds: int = CACHE_TTL_SECONDS
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds() > self.ttl_seconds


class CacheManager:
    """Simple TTL-based cache manager."""
    
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.cache: Dict[str, CachedValue] = {}
        self.ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self.cache:
            return None
        
        cached = self.cache[key]
        if cached.is_expired():
            del self.cache[key]
            return None
        
        return cached.value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache with TTL."""
        self.cache[key] = CachedValue(value=value, timestamp=datetime.now(timezone.utc), ttl_seconds=self.ttl_seconds)
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        expired_keys = [k for k, v in self.cache.items() if v.is_expired()]
        for key in expired_keys:
            del self.cache[key]
        return len(expired_keys)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class Metric:
    """Single metric data point."""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class Alert:
    """Alert notification."""
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    current_value: Optional[float] = None

    def to_dict(self):
        return {
            'severity': self.severity.value,
            'title': self.title,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'metric_name': self.metric_name,
            'threshold': self.threshold,
            'current_value': self.current_value
        }


class MetricsCollector:
    """Collects and stores metrics with TTL caching."""

    def __init__(self, retention_hours: int = 24):
        self.metrics: Dict[str, List[Metric]] = {}
        self.retention_hours = retention_hours
        self.alerts: List[Alert] = []
        self.cache = CacheManager(ttl_seconds=CACHE_TTL_SECONDS)

    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """
        Record a metric value.
        
        Args:
            name: Metric name (e.g., 'db_query_time', 'error_count')
            value: Metric value
            tags: Optional tags for grouping
            
        Raises:
            ValueError: If metric name is invalid or contains sensitive keywords
        """
        # Validate metric name length
        if len(name) > MAX_METRIC_NAME_LENGTH:
            raise ValueError(
                f"Metric name too long: {len(name)} > {MAX_METRIC_NAME_LENGTH}"
            )
        
        # Validate metric name format
        if not re.match(VALID_METRIC_PATTERN, name):
            raise ValueError(
                f"Invalid metric name: {name}. "
                f"Must match pattern: {VALID_METRIC_PATTERN}"
            )
        
        # Reject sensitive metrics
        if any(keyword in name.lower() for keyword in SENSITIVE_KEYWORDS):
            raise ValueError(f"Cannot record sensitive metric: {name}")
        
        # Validate value is numeric
        if not isinstance(value, (int, float)):
            raise ValueError(f"Metric value must be numeric, got {type(value)}")
        
        if name not in self.metrics:
            self.metrics[name] = []
        
        metric = Metric(
            name=name,
            value=value,
            timestamp=datetime.now(timezone.utc),
            tags=tags or {}
        )
        
        self.metrics[name].append(metric)
        logger.debug(f"Recorded metric: {name}={value}")

    def get_metric_stats(self, name: str) -> Dict:
        """
        Get statistics for a metric (cached for 30 seconds).
        
        Args:
            name: Metric name
            
        Returns:
            Dict with min, max, avg, count
        """
        # Check cache first
        cache_key = f"stats_{name}"
        cached_stats = self.cache.get(cache_key)
        if cached_stats is not None:
            return cached_stats
        
        if name not in self.metrics or not self.metrics[name]:
            return {}
        
        values = [m.value for m in self.metrics[name]]
        
        stats = {
            'name': name,
            'count': len(values),
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values),
            'latest': values[-1]
        }
        
        # Cache the stats for 30 seconds
        self.cache.set(cache_key, stats)
        return stats

    def cleanup_old_metrics(self):
        """Remove metrics older than retention period and expired cache entries."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
        
        for name in self.metrics:
            self.metrics[name] = [
                m for m in self.metrics[name]
                if m.timestamp > cutoff
            ]
        
        # Cleanup expired cache entries
        expired_count = self.cache.cleanup_expired()
        if expired_count > 0:
            logger.debug(f"Cleaned up {expired_count} expired cache entries")

    def create_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        metric_name: Optional[str] = None,
        threshold: Optional[float] = None,
        current_value: Optional[float] = None
    ) -> Alert:
        """
        Create an alert.
        
        Args:
            severity: Alert severity level
            title: Alert title
            message: Alert message
            metric_name: Associated metric name
            threshold: Threshold that was exceeded
            current_value: Current metric value
            
        Returns:
            Created alert
        """
        alert = Alert(
            severity=severity,
            title=title,
            message=message,
            timestamp=datetime.now(timezone.utc),
            metric_name=metric_name,
            threshold=threshold,
            current_value=current_value
        )
        
        self.alerts.append(alert)
        logger.warning(f"Alert created: {severity.value} - {title}")
        
        return alert


class HealthMonitor:
    """Monitors system health with TTL caching."""

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.checks: Dict[str, callable] = {}
        self.cache = CacheManager(ttl_seconds=CACHE_TTL_SECONDS)

    def register_check(self, name: str, check_fn: callable):
        """
        Register a health check function.
        
        Args:
            name: Check name
            check_fn: Async function that returns True if healthy
        """
        self.checks[name] = check_fn
        logger.info(f"Registered health check: {name}")

    async def run_health_checks(self) -> Dict[str, bool]:
        """
        Run all registered health checks.
        
        Returns:
            Dict of check_name -> is_healthy
        """
        results = {}
        
        for name, check_fn in self.checks.items():
            try:
                start = time.time()
                is_healthy = await check_fn()
                duration = time.time() - start
                
                results[name] = is_healthy
                self.metrics.record_metric(
                    f"health_check_{name}",
                    1.0 if is_healthy else 0.0
                )
                
                status = "✓" if is_healthy else "✗"
                logger.info(f"Health check {status} {name} ({duration:.2f}s)")
                
            except Exception as e:
                results[name] = False
                logger.error(f"Health check failed: {name} - {str(e)}")
                self.metrics.create_alert(
                    AlertSeverity.CRITICAL,
                    f"Health check failed: {name}",
                    str(e)
                )
        
        return results

    async def get_system_health(self) -> Dict:
        """
        Get overall system health status (cached for 30 seconds).
        
        Returns:
            Health status dict
        """
        # Check cache first
        cache_key = "system_health"
        cached_health = self.cache.get(cache_key)
        if cached_health is not None:
            return cached_health
        
        checks = await self.run_health_checks()
        all_healthy = all(checks.values())
        
        health = {
            'healthy': all_healthy,
            'checks': checks,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Cache the health status for 30 seconds
        self.cache.set(cache_key, health)
        return health


class PerformanceMonitor:
    """Monitors performance metrics with TTL caching."""

    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.cache = CacheManager(ttl_seconds=CACHE_TTL_SECONDS)
        self.thresholds = {
            'db_query_time_ms': 1000,  # 1 second
            'api_response_time_ms': 5000,  # 5 seconds
            'error_rate_percent': 5,  # 5% errors
        }

    def check_thresholds(self):
        """Check if any metrics exceed thresholds."""
        for metric_name, threshold in self.thresholds.items():
            stats = self.metrics.get_metric_stats(metric_name)
            
            if not stats:
                continue
            
            if stats['latest'] > threshold:
                self.metrics.create_alert(
                    AlertSeverity.WARNING,
                    f"Performance threshold exceeded: {metric_name}",
                    f"{metric_name} is {stats['latest']:.2f}, threshold is {threshold}",
                    metric_name=metric_name,
                    threshold=threshold,
                    current_value=stats['latest']
                )

    def get_performance_report(self) -> Dict:
        """
        Get performance report (cached for 30 seconds).
        
        Returns:
            Performance metrics summary
        """
        # Check cache first
        cache_key = "performance_report"
        cached_report = self.cache.get(cache_key)
        if cached_report is not None:
            return cached_report
        
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metrics': {}
        }
        
        for metric_name in self.thresholds.keys():
            stats = self.metrics.get_metric_stats(metric_name)
            if stats:
                report['metrics'][metric_name] = stats
        
        # Cache the report for 30 seconds
        self.cache.set(cache_key, report)
        return report
