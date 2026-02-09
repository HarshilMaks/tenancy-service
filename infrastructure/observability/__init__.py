"""
Observability Module - Production-Grade Logging, Metrics & Tracing
===================================================================

Enterprise observability infrastructure providing:
- Structured JSON logging with correlation IDs
- Prometheus-compatible metrics
- OpenTelemetry tracing integration
- Health check framework
- Audit logging for compliance

Standards:
    - OpenTelemetry for distributed tracing
    - Prometheus for metrics
    - ELK/Datadog compatible structured logs
    - SOC2/GDPR compliant audit trails

Author: Platform Engineering Team
"""

from .logging import (
    get_logger,
    LogContext,
    StructuredLogger,
    AuditLogger,
    set_correlation_id,
    get_correlation_id,
    log_operation,
)

from .metrics import (
    MetricsCollector,
    Counter,
    Histogram,
    Gauge,
    MetricsMiddleware,
    get_metrics,
    track_request_duration,
    track_database_operation,
    track_event_published,
)

from .tracing import (
    trace_operation,
    create_span,
    get_current_span,
    add_span_attributes,
    TracingMiddleware,
)

from .health import (
    HealthChecker,
    HealthStatus,
    ComponentHealth,
    register_health_check,
    get_health_checker,
)

__all__ = [
    # Logging
    "get_logger",
    "LogContext",
    "StructuredLogger",
    "AuditLogger",
    "set_correlation_id",
    "get_correlation_id",
    "log_operation",
    
    # Metrics
    "MetricsCollector",
    "Counter",
    "Histogram",
    "Gauge",
    "MetricsMiddleware",
    "get_metrics",
    "track_request_duration",
    "track_database_operation",
    "track_event_published",
    
    # Tracing
    "trace_operation",
    "create_span",
    "get_current_span",
    "add_span_attributes",
    "TracingMiddleware",
    
    # Health
    "HealthChecker",
    "HealthStatus",
    "ComponentHealth",
    "register_health_check",
    "get_health_checker",
]
