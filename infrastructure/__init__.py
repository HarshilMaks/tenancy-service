"""
Infrastructure Layer - External Integrations & Adapters
========================================================

This layer implements the ports defined in the services layer,
connecting domain logic to external systems:

- persistence/ - Database repositories (PostgreSQL/SQLAlchemy)
- billing/ - Payment processing (Stripe integration)
- region/ - Multi-region management
- messaging/ - Event publishing (RabbitMQ/Kafka)
- observability/ - Logging, metrics, tracing

Clean Architecture Principle:
    Domain ← Services ← Infrastructure
    
    Infrastructure DEPENDS ON services/domain,
    NOT the other way around.

Author: Platform Engineering Team
"""

from .observability import (
    get_logger,
    LogContext,
    trace_operation,
    MetricsCollector,
    HealthChecker,
)

__all__ = [
    # Observability
    "get_logger",
    "LogContext",
    "trace_operation",
    "MetricsCollector",
    "HealthChecker",
]
