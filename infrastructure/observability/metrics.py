"""
Metrics Module - Prometheus-Compatible Application Metrics
==========================================================

Production-grade metrics collection for monitoring and alerting.
Compatible with Prometheus, Datadog, CloudWatch, and other systems.

Metric Types:
    - Counter: Monotonically increasing values (requests, errors)
    - Gauge: Point-in-time values (active connections, queue size)
    - Histogram: Distribution of values (latencies, sizes)
    - Summary: Similar to histogram with pre-calculated quantiles

Naming Convention (Prometheus style):
    {namespace}_{subsystem}_{name}_{unit}
    
    Example: tenancy_service_organization_create_duration_seconds

Labels/Tags:
    - status: success, failure, error
    - edition: free, essentials, professional, enterprise, unlimited
    - region: us-east-1, eu-west-1, etc.
    - operation: create, read, update, delete

Author: Platform Engineering Team
"""

from __future__ import annotations

import functools
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from .logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Metric Types
# =============================================================================

class MetricType(Enum):
    """Supported metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """Container for a metric value with labels."""
    value: float
    labels: Dict[str, str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MetricDefinition:
    """Definition of a metric."""
    name: str
    type: MetricType
    description: str
    labels: List[str] = field(default_factory=list)
    buckets: Optional[List[float]] = None  # For histograms


# =============================================================================
# Base Metric Classes
# =============================================================================

class BaseMetric:
    """Base class for all metrics."""
    
    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.labels = labels or []
        self._lock = threading.Lock()
        self._values: Dict[tuple, float] = defaultdict(float)
    
    def _label_key(self, labels: Optional[Dict[str, str]] = None) -> tuple:
        """Create a hashable key from labels."""
        if not labels:
            return ()
        return tuple(sorted(labels.items()))
    
    def _validate_labels(self, labels: Optional[Dict[str, str]]) -> None:
        """Validate that provided labels match definition."""
        if labels is None:
            labels = {}
        
        provided = set(labels.keys())
        expected = set(self.labels)
        
        if provided != expected:
            missing = expected - provided
            extra = provided - expected
            
            if missing:
                logger.warning(
                    f"Missing labels for metric {self.name}",
                    missing_labels=list(missing),
                )
            if extra:
                logger.warning(
                    f"Unexpected labels for metric {self.name}",
                    extra_labels=list(extra),
                )


class Counter(BaseMetric):
    """
    Counter metric - monotonically increasing value.
    
    Use for:
        - Request counts
        - Error counts
        - Events processed
        - Operations completed
    
    Usage:
        >>> requests_total = Counter(
        ...     "http_requests_total",
        ...     "Total HTTP requests",
        ...     labels=["method", "status"]
        ... )
        >>> requests_total.inc(labels={"method": "POST", "status": "200"})
        >>> requests_total.inc(5, labels={"method": "GET", "status": "200"})
    """
    
    def inc(
        self,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment counter by value (must be positive)."""
        if value < 0:
            raise ValueError("Counter can only be incremented")
        
        self._validate_labels(labels)
        key = self._label_key(labels)
        
        with self._lock:
            self._values[key] += value
        
        # Log metric for debugging
        logger.debug(
            f"Counter incremented: {self.name}",
            metric_name=self.name,
            metric_value=value,
            metric_labels=labels,
        )
    
    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value."""
        key = self._label_key(labels)
        with self._lock:
            return self._values[key]


class Gauge(BaseMetric):
    """
    Gauge metric - point-in-time value that can go up or down.
    
    Use for:
        - Current connections
        - Queue size
        - Temperature
        - Memory usage
    
    Usage:
        >>> active_connections = Gauge(
        ...     "active_connections",
        ...     "Number of active connections",
        ...     labels=["pool"]
        ... )
        >>> active_connections.set(42, labels={"pool": "primary"})
        >>> active_connections.inc(labels={"pool": "primary"})
        >>> active_connections.dec(labels={"pool": "primary"})
    """
    
    def set(
        self,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set gauge to specific value."""
        self._validate_labels(labels)
        key = self._label_key(labels)
        
        with self._lock:
            self._values[key] = value
        
        logger.debug(
            f"Gauge set: {self.name}={value}",
            metric_name=self.name,
            metric_value=value,
            metric_labels=labels,
        )
    
    def inc(
        self,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment gauge by value."""
        key = self._label_key(labels)
        
        with self._lock:
            self._values[key] += value
    
    def dec(
        self,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Decrement gauge by value."""
        key = self._label_key(labels)
        
        with self._lock:
            self._values[key] -= value
    
    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current gauge value."""
        key = self._label_key(labels)
        with self._lock:
            return self._values[key]


class Histogram(BaseMetric):
    """
    Histogram metric - distribution of values in buckets.
    
    Use for:
        - Request latencies
        - Response sizes
        - Batch sizes
    
    Default buckets optimized for HTTP latencies (seconds):
        [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
    
    Usage:
        >>> request_duration = Histogram(
        ...     "http_request_duration_seconds",
        ...     "HTTP request latency",
        ...     labels=["method", "endpoint"]
        ... )
        >>> request_duration.observe(0.245, labels={"method": "GET", "endpoint": "/api/v1/orgs"})
    """
    
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    
    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None,
    ):
        super().__init__(name, description, labels)
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        self._sums: Dict[tuple, float] = defaultdict(float)
        self._counts: Dict[tuple, int] = defaultdict(int)
        self._bucket_values: Dict[tuple, Dict[float, int]] = defaultdict(
            lambda: defaultdict(int)
        )
    
    def observe(
        self,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Observe a value, incrementing appropriate buckets."""
        self._validate_labels(labels)
        key = self._label_key(labels)
        
        with self._lock:
            self._sums[key] += value
            self._counts[key] += 1
            
            # Increment all buckets >= value
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_values[key][bucket] += 1
        
        logger.debug(
            f"Histogram observed: {self.name}={value}",
            metric_name=self.name,
            metric_value=value,
            metric_labels=labels,
        )
    
    def get_sum(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get sum of all observed values."""
        key = self._label_key(labels)
        with self._lock:
            return self._sums[key]
    
    def get_count(self, labels: Optional[Dict[str, str]] = None) -> int:
        """Get count of observations."""
        key = self._label_key(labels)
        with self._lock:
            return self._counts[key]
    
    def get_buckets(
        self,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[float, int]:
        """Get bucket values."""
        key = self._label_key(labels)
        with self._lock:
            return dict(self._bucket_values[key])


# =============================================================================
# FastAPI Middleware for Metrics
# =============================================================================

class MetricsMiddleware:
    """FastAPI middleware for collecting request metrics."""
    
    def __init__(self, app):
        self.app = app
        self.collector = get_metrics()
    
    async def __call__(self, scope, receive, send):
        """Process request and collect metrics."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        start_time = time.time()
        method = scope["method"]
        path = scope["path"]
        
        # Wrap send to capture response
        status_code = 500  # Default to error
        
        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = 500
            raise
        finally:
            # Record metrics
            duration = time.time() - start_time
            track_request_duration(
                method=method,
                endpoint=path,
                duration_seconds=duration,
                status=str(status_code),
            )


# =============================================================================
# Metrics Registry
# =============================================================================

class MetricsCollector:
    """
    Central registry for all application metrics.
    
    Provides:
        - Metric registration and lookup
        - Prometheus exposition format export
        - JSON format export for custom systems
        - Pre-defined metrics for common patterns
    
    Usage:
        >>> metrics = MetricsCollector("tenancy_service")
        >>> 
        >>> # Register metrics
        >>> metrics.register_counter("organizations_created", "Total orgs created")
        >>> 
        >>> # Use metrics
        >>> metrics.counter("organizations_created").inc()
        >>> 
        >>> # Export
        >>> print(metrics.export_prometheus())
    """
    
    def __init__(self, namespace: str = "tenancy_service"):
        self.namespace = namespace
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()
        
        # Register default metrics
        self._register_default_metrics()
    
    def _full_name(self, name: str) -> str:
        """Create full metric name with namespace."""
        return f"{self.namespace}_{name}"
    
    def _register_default_metrics(self) -> None:
        """Register common default metrics."""
        
        # HTTP metrics
        self.register_counter(
            "http_requests_total",
            "Total HTTP requests",
            labels=["method", "endpoint", "status"],
        )
        self.register_histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            labels=["method", "endpoint"],
        )
        
        # Database metrics
        self.register_counter(
            "database_queries_total",
            "Total database queries",
            labels=["operation", "table", "status"],
        )
        self.register_histogram(
            "database_query_duration_seconds",
            "Database query latency in seconds",
            labels=["operation", "table"],
        )
        
        # Event metrics
        self.register_counter(
            "events_published_total",
            "Total events published",
            labels=["event_type", "status"],
        )
        self.register_histogram(
            "event_publish_duration_seconds",
            "Event publishing latency in seconds",
            labels=["event_type"],
        )
        
        # Business metrics
        self.register_counter(
            "organizations_created_total",
            "Total organizations created",
            labels=["edition", "region", "trial"],
        )
        # Count of organizations successfully activated (by previous status)
        self.register_counter(
            "organizations_activated_total",
            "Total organizations activated",
            labels=["previous_status"],
        )
        self.register_counter(
            "organizations_suspended_total",
            "Total organizations suspended",
            labels=["reason", "previous_status"],
        )
        self.register_counter(
            "organizations_terminated_total",
            "Total organizations terminated",
            labels=["reason"],
        )
        self.register_counter(
            "organizations_resumed_total",
            "Total organizations resumed",
            labels=["previous_status"],
        )
        self.register_counter(
            "organizations_deleted_total",
            "Total organizations deleted",
            labels=[],
        )
        # Policy metrics
        self.register_counter(
            "policy_decisions_total",
            "Total policy decisions made",
            labels=["decision", "policy_type"],
        )
        self.register_gauge(
            "organizations_active_count",
            "Current active organizations",
            labels=["edition"],
        )
        self.register_gauge(
            "organizations_trial_count",
            "Current trial organizations",
            labels=["edition"],
        )
    
    # =========================================================================
    # Registration Methods
    # =========================================================================
    
    def register_counter(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
    ) -> Counter:
        """Register a counter metric."""
        full_name = self._full_name(name)
        
        with self._lock:
            if full_name not in self._counters:
                self._counters[full_name] = Counter(
                    full_name, description, labels
                )
                logger.debug(
                    f"Registered counter: {full_name}",
                    metric_name=full_name,
                    metric_type="counter",
                )
        
        return self._counters[full_name]
    
    def register_gauge(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
    ) -> Gauge:
        """Register a gauge metric."""
        full_name = self._full_name(name)
        
        with self._lock:
            if full_name not in self._gauges:
                self._gauges[full_name] = Gauge(
                    full_name, description, labels
                )
                logger.debug(
                    f"Registered gauge: {full_name}",
                    metric_name=full_name,
                    metric_type="gauge",
                )
        
        return self._gauges[full_name]
    
    def register_histogram(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None,
    ) -> Histogram:
        """Register a histogram metric."""
        full_name = self._full_name(name)
        
        with self._lock:
            if full_name not in self._histograms:
                self._histograms[full_name] = Histogram(
                    full_name, description, labels, buckets
                )
                logger.debug(
                    f"Registered histogram: {full_name}",
                    metric_name=full_name,
                    metric_type="histogram",
                )
        
        return self._histograms[full_name]
    
    # =========================================================================
    # Accessor Methods
    # =========================================================================
    
    def counter(self, name: str, description: Optional[str] = None, labels: Optional[List[str]] = None) -> Counter:
        """Get or register counter by name. If description and labels are provided, auto-register the counter."""
        full_name = self._full_name(name)
        with self._lock:
            if full_name not in self._counters:
                if description is None:
                    raise KeyError(f"Counter not registered: {name}")
                # Auto-register the counter with provided metadata
                self.register_counter(name, description, labels)
        return self._counters[full_name]
    
    def gauge(self, name: str) -> Gauge:
        """Get gauge by name."""
        full_name = self._full_name(name)
        if full_name not in self._gauges:
            raise KeyError(f"Gauge not registered: {name}")
        return self._gauges[full_name]
    
    def histogram(self, name: str) -> Histogram:
        """Get histogram by name."""
        full_name = self._full_name(name)
        if full_name not in self._histograms:
            raise KeyError(f"Histogram not registered: {name}")
        return self._histograms[full_name]
    
    # =========================================================================
    # Export Methods
    # =========================================================================
    
    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus exposition format.
        
        Returns text compatible with Prometheus scraping endpoint.
        """
        lines = []
        
        # Counters
        for name, counter in self._counters.items():
            lines.append(f"# HELP {name} {counter.description}")
            lines.append(f"# TYPE {name} counter")
            
            with counter._lock:
                for labels_key, value in counter._values.items():
                    labels_str = self._format_labels(labels_key)
                    lines.append(f"{name}{labels_str} {value}")
        
        # Gauges
        for name, gauge in self._gauges.items():
            lines.append(f"# HELP {name} {gauge.description}")
            lines.append(f"# TYPE {name} gauge")
            
            with gauge._lock:
                for labels_key, value in gauge._values.items():
                    labels_str = self._format_labels(labels_key)
                    lines.append(f"{name}{labels_str} {value}")
        
        # Histograms
        for name, histogram in self._histograms.items():
            lines.append(f"# HELP {name} {histogram.description}")
            lines.append(f"# TYPE {name} histogram")
            
            with histogram._lock:
                for labels_key in set(histogram._counts.keys()):
                    labels_str = self._format_labels(labels_key)
                    
                    # Bucket values
                    for bucket, count in histogram._bucket_values[labels_key].items():
                        bucket_labels = f'{labels_str[:-1]},le="{bucket}"}}' if labels_str else f'{{le="{bucket}"}}'
                        lines.append(f"{name}_bucket{bucket_labels} {count}")
                    
                    # +Inf bucket
                    inf_count = histogram._counts[labels_key]
                    inf_labels = f'{labels_str[:-1]},le="+Inf"}}' if labels_str else '{le="+Inf"}'
                    lines.append(f"{name}_bucket{inf_labels} {inf_count}")
                    
                    # Sum and count
                    lines.append(f"{name}_sum{labels_str} {histogram._sums[labels_key]}")
                    lines.append(f"{name}_count{labels_str} {histogram._counts[labels_key]}")
        
        return "\n".join(lines)
    
    def export_json(self) -> Dict[str, Any]:
        """Export metrics as JSON dictionary."""
        return {
            "namespace": self.namespace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "counters": {
                name: {
                    "description": c.description,
                    "values": {
                        str(k): v for k, v in c._values.items()
                    }
                }
                for name, c in self._counters.items()
            },
            "gauges": {
                name: {
                    "description": g.description,
                    "values": {
                        str(k): v for k, v in g._values.items()
                    }
                }
                for name, g in self._gauges.items()
            },
            "histograms": {
                name: {
                    "description": h.description,
                    "buckets": h.buckets,
                    "sums": {str(k): v for k, v in h._sums.items()},
                    "counts": {str(k): v for k, v in h._counts.items()},
                }
                for name, h in self._histograms.items()
            },
        }
    
    def _format_labels(self, labels_key: tuple) -> str:
        """Format labels tuple as Prometheus label string."""
        if not labels_key:
            return ""
        
        parts = [f'{k}="{v}"' for k, v in labels_key]
        return "{" + ",".join(parts) + "}"


# =============================================================================
# Global Metrics Instance
# =============================================================================

_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get global metrics collector instance."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


# =============================================================================
# Convenience Functions
# =============================================================================

def track_request_duration(
    method: str,
    endpoint: str,
    duration_seconds: float,
    status: str,
) -> None:
    """Track HTTP request duration and count."""
    metrics = get_metrics()
    
    metrics.counter("http_requests_total").inc(labels={
        "method": method,
        "endpoint": endpoint,
        "status": status,
    })
    
    metrics.histogram("http_request_duration_seconds").observe(
        duration_seconds,
        labels={"method": method, "endpoint": endpoint},
    )


def track_database_operation(
    operation: str,
    table: str,
    duration_seconds: float,
    success: bool = True,
) -> None:
    """Track database operation duration and count."""
    metrics = get_metrics()
    
    metrics.counter("database_queries_total").inc(labels={
        "operation": operation,
        "table": table,
        "status": "success" if success else "error",
    })
    
    metrics.histogram("database_query_duration_seconds").observe(
        duration_seconds,
        labels={"operation": operation, "table": table},
    )


def track_event_published(
    event_type: str,
    duration_seconds: float,
    success: bool = True,
) -> None:
    """Track event publishing."""
    metrics = get_metrics()
    
    metrics.counter("events_published_total").inc(labels={
        "event_type": event_type,
        "status": "success" if success else "error",
    })
    
    metrics.histogram("event_publish_duration_seconds").observe(
        duration_seconds,
        labels={"event_type": event_type},
    )


def track_organization_created(
    edition: str,
    region: str,
    is_trial: bool,
) -> None:
    """Track organization creation."""
    metrics = get_metrics()
    
    metrics.counter("organizations_created_total").inc(labels={
        "edition": edition,
        "region": region,
        "trial": str(is_trial).lower(),
    })


# =============================================================================
# Decorators
# =============================================================================

F = TypeVar("F", bound=Callable[..., Any])


def timed(
    metric_name: str,
    labels: Optional[Dict[str, str]] = None,
) -> Callable[[F], F]:
    """
    Decorator to time function execution.
    
    Usage:
        >>> @timed("organization_create_duration_seconds")
        ... def create_organization(name: str) -> Organization:
        ...     pass
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                get_metrics().histogram(metric_name).observe(
                    duration,
                    labels=labels,
                )
        return wrapper  # type: ignore
    return decorator


def counted(
    metric_name: str,
    labels: Optional[Dict[str, str]] = None,
) -> Callable[[F], F]:
    """
    Decorator to count function calls.
    
    Usage:
        >>> @counted("organization_lookups_total")
        ... def get_organization(org_id: str) -> Organization:
        ...     pass
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            get_metrics().counter(metric_name).inc(labels=labels)
            return func(*args, **kwargs)
        return wrapper  # type: ignore
    return decorator


__all__ = [
    # Metric types
    "Counter",
    "Gauge",
    "Histogram",
    "MetricType",
    
    # Registry
    "MetricsCollector",
    "get_metrics",
    
    # Middleware
    "MetricsMiddleware",
    
    # Convenience functions
    "track_request_duration",
    "track_database_operation",
    "track_event_published",
    "track_organization_created",
    
    # Decorators
    "timed",
    "counted",
]
