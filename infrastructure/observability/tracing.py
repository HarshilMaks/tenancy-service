"""
Distributed Tracing Module - OpenTelemetry Integration
=======================================================

Production-grade distributed tracing for request flow visualization
and performance analysis across microservices.

Integrations:
    - OpenTelemetry (OTLP) - Standard
    - Jaeger - Open source tracing
    - Zipkin - Alternative backend
    - Datadog APM - Commercial
    - AWS X-Ray - AWS native

Concepts:
    - Trace: End-to-end request journey
    - Span: Individual operation within trace
    - Context: Propagated trace information
    - Baggage: Custom key-value pairs carried across services

Author: Platform Engineering Team
"""

from __future__ import annotations

import contextvars
import functools
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, List, Optional, TypeVar
from uuid import uuid4

from .logging import get_logger, get_correlation_id, set_correlation_id

logger = get_logger(__name__)


# =============================================================================
# Span Data Structures
# =============================================================================

@dataclass
class SpanContext:
    """
    Trace context for propagation across services.
    
    W3C Trace Context compatible format for interoperability.
    """
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    trace_flags: int = 1  # 1 = sampled
    trace_state: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def generate(cls, parent: Optional["SpanContext"] = None) -> "SpanContext":
        """Generate new span context, optionally as child of parent."""
        return cls(
            trace_id=parent.trace_id if parent else uuid4().hex,
            span_id=uuid4().hex[:16],
            parent_span_id=parent.span_id if parent else None,
        )
    
    def to_traceparent(self) -> str:
        """Convert to W3C traceparent header format."""
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags:02x}"
    
    @classmethod
    def from_traceparent(cls, header: str) -> Optional["SpanContext"]:
        """Parse W3C traceparent header."""
        try:
            parts = header.split("-")
            if len(parts) != 4:
                return None
            return cls(
                trace_id=parts[1],
                span_id=parts[2],
                trace_flags=int(parts[3], 16),
            )
        except Exception:
            return None


@dataclass
class SpanEvent:
    """Event that occurred during a span."""
    name: str
    timestamp: datetime
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpanLink:
    """Link to another span (for async operations)."""
    context: SpanContext
    attributes: Dict[str, Any] = field(default_factory=dict)


class SpanKind:
    """Span kind indicators."""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus:
    """Span status codes."""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class Span:
    """
    Represents a single operation within a trace.
    
    A span captures:
        - Operation name
        - Start/end time
        - Attributes (key-value pairs)
        - Events (timestamped annotations)
        - Links (references to other spans)
        - Status (ok, error)
    
    Usage:
        >>> span = Span("create_organization")
        >>> span.set_attribute("org_id", "ORG-12345678")
        >>> span.add_event("validation_complete")
        >>> span.end()
    """
    
    name: str
    context: SpanContext = field(default_factory=lambda: SpanContext.generate())
    kind: str = SpanKind.INTERNAL
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[SpanEvent] = field(default_factory=list)
    links: List[SpanLink] = field(default_factory=list)
    status: str = SpanStatus.UNSET
    status_message: Optional[str] = None
    
    # Internal tracking
    _start_perf: float = field(default_factory=time.perf_counter)
    
    def set_attribute(self, key: str, value: Any) -> "Span":
        """Set span attribute."""
        self.attributes[key] = value
        return self
    
    def set_attributes(self, attributes: Dict[str, Any]) -> "Span":
        """Set multiple attributes."""
        self.attributes.update(attributes)
        return self
    
    def add_event(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> "Span":
        """Add event to span."""
        self.events.append(SpanEvent(
            name=name,
            timestamp=datetime.now(timezone.utc),
            attributes=attributes or {},
        ))
        return self
    
    def add_link(
        self,
        context: SpanContext,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> "Span":
        """Add link to another span."""
        self.links.append(SpanLink(
            context=context,
            attributes=attributes or {},
        ))
        return self
    
    def set_status(self, status: str, message: Optional[str] = None) -> "Span":
        """Set span status."""
        self.status = status
        self.status_message = message
        return self
    
    def record_exception(self, exception: Exception) -> "Span":
        """Record exception in span."""
        self.set_status(SpanStatus.ERROR, str(exception))
        self.add_event(
            "exception",
            {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
            },
        )
        return self
    
    def end(self, end_time: Optional[datetime] = None) -> "Span":
        """End the span."""
        self.end_time = end_time or datetime.now(timezone.utc)
        
        # Calculate duration
        duration_ms = (time.perf_counter() - self._start_perf) * 1000
        self.attributes["duration_ms"] = duration_ms
        
        # Log span completion
        logger.debug(
            f"Span ended: {self.name} ({duration_ms:.2f}ms)",
            span_name=self.name,
            trace_id=self.context.trace_id,
            span_id=self.context.span_id,
            duration_ms=duration_ms,
            status=self.status,
        )
        
        # Export span (would go to tracing backend)
        _tracer.export_span(self)
        
        return self
    
    @property
    def duration_ms(self) -> Optional[float]:
        """Get span duration in milliseconds."""
        return self.attributes.get("duration_ms")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary for export."""
        return {
            "name": self.name,
            "trace_id": self.context.trace_id,
            "span_id": self.context.span_id,
            "parent_span_id": self.context.parent_span_id,
            "kind": self.kind,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": [
                {
                    "name": e.name,
                    "timestamp": e.timestamp.isoformat(),
                    "attributes": e.attributes,
                }
                for e in self.events
            ],
            "status": {
                "code": self.status,
                "message": self.status_message,
            },
        }


# =============================================================================
# Context Management
# =============================================================================

_current_span: contextvars.ContextVar[Optional[Span]] = contextvars.ContextVar(
    "current_span", default=None
)


def get_current_span() -> Optional[Span]:
    """Get the current active span."""
    return _current_span.get()


def set_current_span(span: Optional[Span]) -> contextvars.Token:
    """Set the current active span."""
    return _current_span.set(span)


# =============================================================================
# Tracer
# =============================================================================

class Tracer:
    """
    Creates and manages spans for distributed tracing.
    
    In production, this would integrate with OpenTelemetry SDK.
    This implementation provides the interface and local functionality.
    
    Usage:
        >>> tracer = Tracer("tenancy_service")
        >>> with tracer.start_span("create_organization") as span:
        ...     span.set_attribute("org_name", "Acme Corp")
        ...     do_work()
    """
    
    def __init__(
        self,
        service_name: str,
        enabled: bool = True,
        sample_rate: float = 1.0,
    ):
        self.service_name = service_name
        self.enabled = enabled
        self.sample_rate = sample_rate
        self._spans: List[Dict[str, Any]] = []
        self._exporters: List[Callable[[Span], None]] = []
    
    def start_span(
        self,
        name: str,
        kind: str = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[List[SpanLink]] = None,
    ) -> "SpanContextManager":
        """
        Start a new span.
        
        Returns a context manager that automatically ends the span.
        
        Args:
            name: Operation name
            kind: Span kind (internal, server, client, producer, consumer)
            attributes: Initial attributes
            links: Links to other spans
        """
        # Get parent context
        parent_span = get_current_span()
        parent_context = parent_span.context if parent_span else None
        
        # Create span context
        context = SpanContext.generate(parent_context)
        
        # Sync with correlation ID
        if parent_context is None:
            set_correlation_id(context.trace_id[:16])
        
        # Create span
        span = Span(
            name=name,
            context=context,
            kind=kind,
            attributes={
                "service.name": self.service_name,
                **(attributes or {}),
            },
            links=links or [],
        )
        
        return SpanContextManager(span)
    
    def export_span(self, span: Span) -> None:
        """Export completed span to backends."""
        if not self.enabled:
            return
        
        span_data = span.to_dict()
        self._spans.append(span_data)
        
        # Call registered exporters
        for exporter in self._exporters:
            try:
                exporter(span)
            except Exception as e:
                logger.warning(f"Span export failed: {e}")
    
    def add_exporter(self, exporter: Callable[[Span], None]) -> None:
        """Add span exporter."""
        self._exporters.append(exporter)
    
    def get_spans(self) -> List[Dict[str, Any]]:
        """Get exported spans (for testing)."""
        return self._spans.copy()
    
    def clear_spans(self) -> None:
        """Clear exported spans (for testing)."""
        self._spans.clear()


class SpanContextManager:
    """Context manager for span lifecycle."""
    
    def __init__(self, span: Span):
        self.span = span
        self._token: Optional[contextvars.Token] = None
    
    def __enter__(self) -> Span:
        self._token = set_current_span(self.span)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.span.record_exception(exc_val)
        elif self.span.status == SpanStatus.UNSET:
            self.span.set_status(SpanStatus.OK)
        
        self.span.end()
        
        if self._token:
            _current_span.reset(self._token)
        
        return False


# =============================================================================
# Global Tracer
# =============================================================================

_tracer: Optional[Tracer] = None


def get_tracer(service_name: str = "tenancy_service") -> Tracer:
    """Get or create global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = Tracer(service_name)
    return _tracer


def configure_tracing(
    service_name: str = "tenancy_service",
    enabled: bool = True,
    sample_rate: float = 1.0,
) -> Tracer:
    """Configure global tracer."""
    global _tracer
    _tracer = Tracer(service_name, enabled, sample_rate)
    return _tracer


# =============================================================================
# Convenience Functions
# =============================================================================

@contextmanager
def create_span(
    name: str,
    kind: str = SpanKind.INTERNAL,
    **attributes: Any,
) -> Generator[Span, None, None]:
    """
    Create a span using context manager.
    
    Usage:
        >>> with create_span("database_query", table="organizations") as span:
        ...     result = db.query(...)
        ...     span.set_attribute("row_count", len(result))
    """
    with get_tracer().start_span(name, kind, attributes) as span:
        yield span


def add_span_attributes(**attributes: Any) -> None:
    """Add attributes to current span."""
    span = get_current_span()
    if span:
        span.set_attributes(attributes)


def add_span_event(name: str, **attributes: Any) -> None:
    """Add event to current span."""
    span = get_current_span()
    if span:
        span.add_event(name, attributes)


def record_span_exception(exception: Exception) -> None:
    """Record exception in current span."""
    span = get_current_span()
    if span:
        span.record_exception(exception)


# =============================================================================
# Decorators
# =============================================================================

F = TypeVar("F", bound=Callable[..., Any])


def trace_operation(
    name: Optional[str] = None,
    kind: str = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, str]] = None,
) -> Callable[[F], F]:
    """
    Decorator to trace function execution.
    
    Usage:
        >>> @trace_operation("create_organization")
        ... def create_org(name: str) -> Organization:
        ...     return Organization(name=name)
    """
    def decorator(func: F) -> F:
        span_name = name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with create_span(span_name, kind, **(attributes or {})) as span:
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    raise
        
        return wrapper  # type: ignore
    
    return decorator


# =============================================================================
# Middleware
# =============================================================================

class TracingMiddleware:
    """
    ASGI middleware for request tracing.
    
    Extracts trace context from incoming requests and creates
    root spans for each request.
    
    Usage:
        >>> app = FastAPI()
        >>> app.add_middleware(TracingMiddleware)
    """
    
    def __init__(self, app, service_name: str = "tenancy_service"):
        self.app = app
        self.tracer = get_tracer(service_name)
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Extract headers
        headers = dict(scope.get("headers", []))
        
        # Parse traceparent header
        traceparent = headers.get(b"traceparent", b"").decode()
        parent_context = SpanContext.from_traceparent(traceparent) if traceparent else None
        
        # Create root span
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        
        with self.tracer.start_span(
            f"{method} {path}",
            kind=SpanKind.SERVER,
            attributes={
                "http.method": method,
                "http.path": path,
                "http.host": headers.get(b"host", b"").decode(),
            },
        ) as span:
            # Inject parent if present
            if parent_context:
                span.context.trace_id = parent_context.trace_id
            
            # Track response status
            status_code = 500
            
            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    span.set_attribute("http.status_code", status_code)
                await send(message)
            
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as e:
                span.record_exception(e)
                raise
            finally:
                # Set final status
                if status_code >= 400:
                    span.set_status(SpanStatus.ERROR, f"HTTP {status_code}")


__all__ = [
    # Span types
    "Span",
    "SpanContext",
    "SpanKind",
    "SpanStatus",
    "SpanEvent",
    "SpanLink",
    
    # Tracer
    "Tracer",
    "get_tracer",
    "configure_tracing",
    
    # Context
    "get_current_span",
    "set_current_span",
    
    # Convenience
    "create_span",
    "add_span_attributes",
    "add_span_event",
    "record_span_exception",
    
    # Decorators
    "trace_operation",
    
    # Middleware
    "TracingMiddleware",
]
