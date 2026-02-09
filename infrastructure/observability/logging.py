"""
Structured Logging Module - Production-Grade Enterprise Logging
================================================================

This module provides enterprise-grade structured logging with:
- JSON-formatted logs for log aggregation (ELK, Datadog, Splunk)
- Correlation ID propagation for distributed tracing
- Request context injection (tenant_id, user_id, request_id)
- PII masking for compliance (GDPR, SOC2, HIPAA)
- Audit logging for security events
- Performance logging with timing
- Log level filtering by environment

Log Levels:
    DEBUG   - Detailed debugging, only in dev
    INFO    - Normal operation events
    WARNING - Unusual but handled conditions  
    ERROR   - Failures requiring attention
    CRITICAL - System-wide failures

Output Format (JSON):
    {
        "timestamp": "2026-02-02T10:30:45.123Z",
        "level": "INFO",
        "logger": "tenancy_service.services.create_tenant",
        "message": "Organization created successfully",
        "correlation_id": "req-abc123",
        "tenant_id": "ORG-12345678",
        "user_id": "usr-xyz789",
        "duration_ms": 45.2,
        "extra": {...}
    }

Author: Platform Engineering Team
"""

from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
from uuid import uuid4


# =============================================================================
# Context Variables for Request Tracking
# =============================================================================

_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)
_tenant_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "tenant_id", default=None
)
_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "user_id", default=None
)
_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
_operation_name: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "operation_name", default=None
)


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context."""
    _correlation_id.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get correlation ID from current context."""
    return _correlation_id.get()


def set_tenant_context(tenant_id: str, user_id: Optional[str] = None) -> None:
    """Set tenant context for current request."""
    _tenant_id.set(tenant_id)
    if user_id:
        _user_id.set(user_id)


def get_tenant_id() -> Optional[str]:
    """Get tenant ID from current context."""
    return _tenant_id.get()


def get_user_id() -> Optional[str]:
    """Get user ID from current context."""
    return _user_id.get()


def set_request_id(request_id: str) -> None:
    """Set request ID for current context."""
    _request_id.set(request_id)


def get_request_id() -> Optional[str]:
    """Get request ID from current context."""
    return _request_id.get()


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return f"corr-{uuid4().hex[:16]}"


def generate_request_id() -> str:
    """Generate a new request ID."""
    return f"req-{uuid4().hex[:12]}"


# =============================================================================
# PII Masking for Compliance
# =============================================================================

class PIIMasker:
    """
    Masks Personally Identifiable Information (PII) in log messages.
    
    Required for GDPR, SOC2, HIPAA compliance - ensures sensitive
    data is never written to logs.
    
    Masked fields:
        - Email addresses
        - Phone numbers
        - Credit card numbers
        - Social security numbers
        - IP addresses (optionally)
        - Custom patterns
    """
    
    # Patterns for PII detection
    PATTERNS = {
        "email": (
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            "***EMAIL***"
        ),
        "phone": (
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "***PHONE***"
        ),
        "ssn": (
            r'\b\d{3}-\d{2}-\d{4}\b',
            "***SSN***"
        ),
        "credit_card": (
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            "***CC***"
        ),
        "api_key": (
            r'\b(sk_live_|sk_test_|pk_live_|pk_test_)[a-zA-Z0-9]{24,}\b',
            "***API_KEY***"
        ),
        "bearer_token": (
            r'Bearer\s+[a-zA-Z0-9._-]+',
            "Bearer ***TOKEN***"
        ),
    }
    
    # Fields to always mask in structured logs
    SENSITIVE_FIELDS = {
        "password", "secret", "token", "api_key", "apikey",
        "auth", "authorization", "credential", "credit_card",
        "card_number", "cvv", "ssn", "social_security",
        "access_token", "refresh_token", "private_key",
    }
    
    def __init__(self, mask_emails: bool = True, mask_ips: bool = False):
        self.mask_emails = mask_emails
        self.mask_ips = mask_ips
        self._compiled_patterns = {
            name: (re.compile(pattern, re.IGNORECASE), replacement)
            for name, (pattern, replacement) in self.PATTERNS.items()
        }
        if mask_ips:
            self._compiled_patterns["ip_address"] = (
                re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'),
                "***IP***"
            )
    
    def mask_string(self, value: str) -> str:
        """Mask PII in a string value."""
        if not value or not isinstance(value, str):
            return value
        
        result = value
        for name, (pattern, replacement) in self._compiled_patterns.items():
            if name == "email" and not self.mask_emails:
                continue
            result = pattern.sub(replacement, result)
        
        return result
    
    def mask_dict(self, data: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
        """Recursively mask PII in dictionary values."""
        if depth > 10:  # Prevent infinite recursion
            return data
        
        masked = {}
        for key, value in data.items():
            key_lower = key.lower()
            
            # Check if field name indicates sensitive data
            is_sensitive = any(
                sensitive in key_lower
                for sensitive in self.SENSITIVE_FIELDS
            )
            
            if is_sensitive:
                masked[key] = "***REDACTED***"
            elif isinstance(value, str):
                masked[key] = self.mask_string(value)
            elif isinstance(value, dict):
                masked[key] = self.mask_dict(value, depth + 1)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_dict(item, depth + 1) if isinstance(item, dict)
                    else self.mask_string(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                masked[key] = value
        
        return masked


# Global PII masker instance
_pii_masker = PIIMasker()


# =============================================================================
# JSON Log Formatter
# =============================================================================

class StructuredJsonFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.
    
    Outputs logs in JSON format suitable for log aggregation systems
    like ELK Stack, Datadog, Splunk, CloudWatch.
    
    Features:
        - Consistent JSON structure
        - Correlation ID injection
        - Context variables (tenant, user, request)
        - Exception formatting with stack traces
        - PII masking
        - Timestamp in ISO format with timezone
    """
    
    def __init__(
        self,
        service_name: str = "tenancy_service",
        environment: str = "development",
        mask_pii: bool = True,
    ):
        super().__init__()
        self.service_name = service_name
        self.environment = environment
        self.mask_pii = mask_pii
        self.hostname = os.environ.get("HOSTNAME", "unknown")
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        
        # Base log structure
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._format_message(record),
            "service": self.service_name,
            "environment": self.environment,
            "hostname": self.hostname,
        }
        
        # Add context variables
        correlation_id = get_correlation_id()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id
        
        tenant_id = get_tenant_id()
        if tenant_id:
            log_entry["tenant_id"] = tenant_id
        
        user_id = get_user_id()
        if user_id:
            log_entry["user_id"] = user_id
        
        request_id = get_request_id()
        if request_id:
            log_entry["request_id"] = request_id
        
        # Add source location
        log_entry["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }
        
        # Add extra fields from record
        extra = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "asctime",
            }:
                extra[key] = value
        
        if extra:
            if self.mask_pii:
                extra = _pii_masker.mask_dict(extra)
            log_entry["extra"] = extra
        
        # Add exception info
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self._format_traceback(record.exc_info),
            }
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)
    
    def _format_message(self, record: logging.LogRecord) -> str:
        """Format the log message, masking PII if enabled."""
        message = record.getMessage()
        if self.mask_pii:
            message = _pii_masker.mask_string(message)
        return message
    
    def _format_traceback(self, exc_info) -> Optional[List[str]]:
        """Format exception traceback as list of strings."""
        if exc_info and exc_info[2]:
            return traceback.format_exception(*exc_info)
        return None


# =============================================================================
# Console Formatter (for development)
# =============================================================================

class ColoredConsoleFormatter(logging.Formatter):
    """
    Colored console formatter for development.
    
    Provides human-readable colored output when running locally.
    """
    
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        
        # Format timestamp
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Get context
        correlation_id = get_correlation_id()
        tenant_id = get_tenant_id()
        
        context_parts = []
        if correlation_id:
            context_parts.append(f"corr={correlation_id[:12]}")
        if tenant_id:
            context_parts.append(f"tenant={tenant_id}")
        
        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        
        # Format message
        message = record.getMessage()
        
        # Build output
        output = (
            f"{self.BOLD}{timestamp}{self.RESET} "
            f"{color}{record.levelname:8}{self.RESET} "
            f"{record.name}:{record.lineno}{context_str} - {message}"
        )
        
        # Add exception
        if record.exc_info:
            output += "\n" + "".join(traceback.format_exception(*record.exc_info))
        
        return output


# =============================================================================
# Logger Factory
# =============================================================================

_loggers: Dict[str, "StructuredLogger"] = {}
_log_level: int = logging.INFO
_use_json: bool = True
_initialized: bool = False


def configure_logging(
    level: Union[int, str] = logging.INFO,
    use_json: bool = True,
    service_name: str = "tenancy_service",
    environment: str = "development",
) -> None:
    """
    Configure logging for the application.
    
    Call once at application startup.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_json: Use JSON format (True for production, False for dev)
        service_name: Service identifier for logs
        environment: Environment name (development, staging, production)
    """
    global _log_level, _use_json, _initialized
    
    if isinstance(level, str):
        level = getattr(logging, level.upper())
    
    _log_level = level
    _use_json = use_json
    _initialized = True
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add appropriate handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    if use_json:
        handler.setFormatter(StructuredJsonFormatter(
            service_name=service_name,
            environment=environment,
        ))
    else:
        handler.setFormatter(ColoredConsoleFormatter())
    
    root_logger.addHandler(handler)
    
    # Quiet down noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class StructuredLogger:
    """
    Enhanced logger with structured logging support.
    
    Provides additional methods for common logging patterns:
    - Operation logging with timing
    - Event logging
    - Audit logging
    - Error logging with context
    
    Usage:
        >>> logger = get_logger(__name__)
        >>> logger.info("User logged in", user_id="usr-123", ip="192.168.1.1")
        >>> with logger.operation("create_organization"):
        ...     # do work
        ...     pass
    """
    
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
        self._name = name
    
    @property
    def name(self) -> str:
        return self._name
    
    def _log(
        self,
        level: int,
        message: str,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """Internal logging method with extra fields."""
        # Reserved LogRecord attributes that cannot be overwritten
        RESERVED_ATTRS = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
            'message', 'asctime'
        }
        
        # Handle potential exc_info conflicts
        extra_kwargs = kwargs.copy()
        if 'exc_info' in extra_kwargs:
            # If exc_info is in kwargs, use that value instead
            exc_info = extra_kwargs.pop('exc_info')
        
        # Filter out reserved attributes to prevent LogRecord errors
        filtered_kwargs = {
            k if k not in RESERVED_ATTRS else f"log_{k}": v
            for k, v in extra_kwargs.items()
        }
        
        self._logger.log(level, message, exc_info=exc_info, extra=filtered_kwargs)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, message, exc_info=exc_info, **kwargs)
    
    def critical(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, exc_info=exc_info, **kwargs)
    
    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        self._log(logging.ERROR, message, exc_info=True, **kwargs)
    
    def event(
        self,
        event_type: str,
        message: str,
        **kwargs: Any,
    ) -> None:
        """
        Log a domain event.
        
        Args:
            event_type: Type of event (e.g., "OrganizationCreated")
            message: Human-readable description
            **kwargs: Event-specific data
        """
        self._log(
            logging.INFO,
            message,
            event_type=event_type,
            event_category="domain_event",
            **kwargs,
        )
    
    def audit(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        actor_id: Optional[str] = None,
        result: str = "success",
        **kwargs: Any,
    ) -> None:
        """
        Log an audit event for compliance.
        
        Args:
            action: Action performed (create, read, update, delete)
            resource_type: Type of resource (organization, user, etc.)
            resource_id: ID of the affected resource
            actor_id: ID of user/system performing action
            result: Outcome (success, failure, denied)
            **kwargs: Additional audit data
        """
        self._log(
            logging.INFO,
            f"AUDIT: {action} {resource_type} {resource_id} - {result}",
            audit_action=action,
            audit_resource_type=resource_type,
            audit_resource_id=resource_id,
            audit_actor_id=actor_id or get_user_id() or "system",
            audit_result=result,
            audit_category="audit_log",
            **kwargs,
        )
    
    def metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "count",
        **tags: Any,
    ) -> None:
        """
        Log a metric for monitoring.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement
            **tags: Metric tags/dimensions
        """
        self._log(
            logging.INFO,
            f"METRIC: {metric_name}={value}{unit}",
            metric_name=metric_name,
            metric_value=value,
            metric_unit=unit,
            metric_tags=tags,
            metric_category="metric",
        )
    
    def operation_start(
        self,
        operation: str,
        **kwargs: Any,
    ) -> float:
        """
        Log start of an operation and return start time.
        
        Args:
            operation: Operation name
            **kwargs: Operation context
            
        Returns:
            Start timestamp for duration calculation
        """
        self._log(
            logging.DEBUG,
            f"Starting operation: {operation}",
            operation=operation,
            operation_phase="start",
            **kwargs,
        )
        return time.perf_counter()
    
    def operation_end(
        self,
        operation: str,
        start_time: float,
        success: bool = True,
        **kwargs: Any,
    ) -> float:
        """
        Log end of an operation with duration.
        
        Args:
            operation: Operation name
            start_time: Start timestamp from operation_start
            success: Whether operation succeeded
            **kwargs: Operation result context
            
        Returns:
            Duration in milliseconds
        """
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        level = logging.INFO if success else logging.ERROR
        status = "completed" if success else "failed"
        
        self._log(
            level,
            f"Operation {status}: {operation} ({duration_ms:.2f}ms)",
            operation=operation,
            operation_phase="end",
            operation_success=success,
            duration_ms=duration_ms,
            **kwargs,
        )
        
        return duration_ms
    
    def operation(self, name: str, **context: Any) -> "OperationContext":
        """
        Context manager for operation logging.
        
        Usage:
            >>> with logger.operation("create_org", org_name="Acme"):
            ...     do_work()
        """
        return OperationContext(self, name, context)


class OperationContext:
    """Context manager for operation timing and logging."""
    
    def __init__(
        self,
        logger: StructuredLogger,
        operation: str,
        context: Dict[str, Any],
    ):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time: float = 0
        self.success = True
        self.error: Optional[Exception] = None
    
    def __enter__(self) -> "OperationContext":
        self.start_time = self.logger.operation_start(
            self.operation,
            **self.context,
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.success = False
            self.error = exc_val
            self.context["error_type"] = exc_type.__name__
            self.context["error_message"] = str(exc_val)
        
        self.logger.operation_end(
            self.operation,
            self.start_time,
            success=self.success,
            **self.context,
        )
        
        return False  # Don't suppress exceptions
    
    def mark_failed(self, reason: str) -> None:
        """Mark operation as failed without exception."""
        self.success = False
        self.context["failure_reason"] = reason


class LogContext:
    """
    Context manager for setting logging context.
    
    Automatically sets and clears context variables for
    correlation ID, tenant ID, etc.
    
    Usage:
        >>> with LogContext(correlation_id="abc", tenant_id="ORG-123"):
        ...     logger.info("This log has context")
    """
    
    def __init__(
        self,
        correlation_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        self.correlation_id = correlation_id or generate_correlation_id()
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.request_id = request_id or generate_request_id()
        
        self._tokens: List[contextvars.Token] = []
    
    def __enter__(self) -> "LogContext":
        self._tokens.append(_correlation_id.set(self.correlation_id))
        self._tokens.append(_request_id.set(self.request_id))
        
        if self.tenant_id:
            self._tokens.append(_tenant_id.set(self.tenant_id))
        if self.user_id:
            self._tokens.append(_user_id.set(self.user_id))
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        for token in reversed(self._tokens):
            try:
                token.var.reset(token)
            except ValueError:
                pass  # Token already reset
        return False


def get_logger(name: str) -> StructuredLogger:
    """
    Get or create a structured logger.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        StructuredLogger instance
        
    Usage:
        >>> logger = get_logger(__name__)
        >>> logger.info("Hello", key="value")
    """
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]


# =============================================================================
# Decorators
# =============================================================================

F = TypeVar("F", bound=Callable[..., Any])


def log_operation(
    operation: Optional[str] = None,
    log_args: bool = True,
    log_result: bool = False,
) -> Callable[[F], F]:
    """
    Decorator for logging function execution.
    
    Args:
        operation: Operation name (defaults to function name)
        log_args: Whether to log function arguments
        log_result: Whether to log function result
        
    Usage:
        >>> @log_operation("create_organization")
        ... def create_org(name: str) -> Organization:
        ...     return Organization(name=name)
    """
    def decorator(func: F) -> F:
        op_name = operation or func.__name__
        logger = get_logger(func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            context = {}
            
            if log_args:
                # Safely capture arguments
                context["args_count"] = len(args)
                context["kwargs_keys"] = list(kwargs.keys())
            
            with logger.operation(op_name, **context) as op:
                try:
                    result = func(*args, **kwargs)
                    
                    if log_result and result is not None:
                        op.context["has_result"] = True
                        if hasattr(result, "__class__"):
                            op.context["result_type"] = result.__class__.__name__
                    
                    return result
                    
                except Exception as e:
                    op.context["exception_type"] = type(e).__name__
                    raise
        
        return wrapper  # type: ignore
    
    return decorator


# =============================================================================
# Audit Logger (Specialized for Compliance)
# =============================================================================

class AuditLogger:
    """
    Specialized logger for audit trails.
    
    Required for SOC2, GDPR, HIPAA compliance. Records all
    security-relevant events with immutable structure.
    
    Audit events are:
    - Written to dedicated audit log stream
    - Never deleted or modified
    - Include full actor and context information
    - Timestamped with server time
    
    Usage:
        >>> audit = AuditLogger("tenancy_service")
        >>> audit.log_access("user-123", "organization", "ORG-456", "read")
    """
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self._logger = get_logger(f"audit.{service_name}")
    
    def log_access(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        result: str = "success",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Log resource access event."""
        self._logger.audit(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            result=result,
            ip_address=ip_address,
            user_agent=user_agent,
            audit_type="access",
            **extra,
        )
    
    def log_modification(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        changes: Optional[Dict[str, Any]] = None,
        result: str = "success",
        **extra: Any,
    ) -> None:
        """Log resource modification event."""
        self._logger.audit(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            result=result,
            changes=changes,
            audit_type="modification",
            **extra,
        )
    
    def log_authentication(
        self,
        actor_id: Optional[str],
        action: str,
        result: str,
        method: str = "password",
        ip_address: Optional[str] = None,
        failure_reason: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Log authentication event."""
        self._logger.audit(
            action=action,
            resource_type="session",
            resource_id=actor_id or "unknown",
            actor_id=actor_id or "anonymous",
            result=result,
            auth_method=method,
            ip_address=ip_address,
            failure_reason=failure_reason,
            audit_type="authentication",
            **extra,
        )
    
    def log_authorization(
        self,
        actor_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        result: str,
        required_permission: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Log authorization decision event."""
        self._logger.audit(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            result=result,
            required_permission=required_permission,
            audit_type="authorization",
            **extra,
        )
    
    def log_data_export(
        self,
        actor_id: str,
        resource_type: str,
        record_count: int,
        format: str,
        destination: str,
        **extra: Any,
    ) -> None:
        """Log data export event (GDPR compliance)."""
        self._logger.audit(
            action="export",
            resource_type=resource_type,
            resource_id=f"export-{record_count}-records",
            actor_id=actor_id,
            result="success",
            record_count=record_count,
            export_format=format,
            destination=destination,
            audit_type="data_export",
            **extra,
        )


# =============================================================================
# Module Initialization
# =============================================================================

# Auto-configure based on environment
_env = os.environ.get("ENVIRONMENT", "development").lower()
_log_level_env = os.environ.get("LOG_LEVEL", "INFO").upper()

if not _initialized:
    configure_logging(
        level=_log_level_env,
        use_json=_env in ("production", "staging"),
        environment=_env,
    )


__all__ = [
    # Core
    "get_logger",
    "StructuredLogger",
    "configure_logging",
    
    # Context
    "LogContext",
    "set_correlation_id",
    "get_correlation_id",
    "set_tenant_context",
    "get_tenant_id",
    "get_user_id",
    "generate_correlation_id",
    "generate_request_id",
    
    # Decorators
    "log_operation",
    
    # Audit
    "AuditLogger",
    
    # PII
    "PIIMasker",
]
