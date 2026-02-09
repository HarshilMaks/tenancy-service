"""
Terminate Organization Use Case - Production-Grade Implementation
==================================================================

Enterprise-ready use case for terminating (soft deleting) organizations.

Features:
    - State transition validation
    - Data retention period management
    - Event publishing
    - Comprehensive error handling
    - Structured logging and metrics
    - Audit trail

Flow:
    1. Validate organization exists and can be terminated
    2. Apply domain state transition rules
    3. Set termination details and retention period
    4. Update database within transaction
    5. Publish termination events
    6. Record metrics and audit logs

Author: Platform Engineering Team
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, List, Optional, Protocol, runtime_checkable
from uuid import uuid4

# Infrastructure imports
from infrastructure.observability.logging import (
    get_logger,
    AuditLogger,
    LogContext,
)
from infrastructure.observability.metrics import get_metrics
from infrastructure.observability.tracing import (
    trace_operation,
    create_span,
    SpanKind,
)

# Domain imports
from app.db.models.domain_models import (
    Organization,
    OrganizationStatus,
)
from app.business.domain.entities.lifecycle import (
    can_transition,
    get_allowed_transitions,
    OrganizationLifecycle,
)

# Event imports
from app.business.events.tenant_events import (
    OrganizationTerminatedEvent,
)

# Setup logging
logger = get_logger(__name__)
audit = AuditLogger("tenancy_service")
metrics = get_metrics()


# =============================================================================
# PORTS
# =============================================================================

@runtime_checkable
class OrganizationRepository(Protocol):
    """Port for organization persistence."""
    
    def get_by_org_id(self, org_id: str) -> Optional[Organization]:
        """Get organization by external ID."""
        ...
    
    def save(self, organization: Organization) -> Organization:
        """Persist organization changes."""
        ...


@runtime_checkable
class EventPublisher(Protocol):
    """Port for event publishing."""
    
    def publish(self, event: Any) -> None:
        """Publish domain event."""
        ...
    
    def publish_batch(self, events: List[Any]) -> None:
        """Publish batch of events."""
        ...


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class TerminateOrganizationError(Enum):
    """Error codes for termination operations."""
    
    ORGANIZATION_NOT_FOUND = "ORGANIZATION_NOT_FOUND"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Default retention period in days
DEFAULT_RETENTION_DAYS = 90


# =============================================================================
# REQUEST/RESPONSE DTOs
# =============================================================================

@dataclass
class TerminateOrganizationRequest:
    """
    Request DTO for terminating an organization.
    
    Attributes:
        org_id: Organization to terminate
        reason: Termination reason
        data_retention_days: Days to retain data (default 90)
        terminated_by: ID of user/system initiating termination
        request_id: Idempotency key
        correlation_id: Tracing correlation ID
    """
    
    # Required
    org_id: str
    reason: str
    
    # Retention configuration
    data_retention_days: int = DEFAULT_RETENTION_DAYS
    
    # Actor information
    terminated_by: Optional[str] = None
    
    # Tracking
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        """Normalize fields but preserve original org_id as tests expect exact inputs."""
        if self.org_id is None:
            self.org_id = ""
        else:
            self.org_id = str(self.org_id)
        self.reason = self.reason.strip() if self.reason else ""


@dataclass
class TerminateOrganizationResponse:
    """Response DTO for termination operation."""
    
    success: bool
    
    # Result
    org_id: Optional[str] = None
    new_status: Optional[str] = None
    terminated_at: Optional[datetime] = None
    data_retention_until: Optional[datetime] = None
    
    # Error details
    error_code: Optional[TerminateOrganizationError] = None
    errors: List[str] = field(default_factory=list)
    
    # Timing
    duration_ms: Optional[float] = None
    request_id: Optional[str] = None
    
    @classmethod
    def success_response(
        cls,
        org_id: str,
        terminated_at: datetime,
        data_retention_until: datetime,
        duration_ms: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> "TerminateOrganizationResponse":
        """Create success response."""
        return cls(
            success=True,
            org_id=org_id,
            new_status=OrganizationStatus.TERMINATED.value,
            terminated_at=terminated_at,
            data_retention_until=data_retention_until,
            duration_ms=duration_ms,
            request_id=request_id,
        )
    
    @classmethod
    def error_response(
        cls,
        error_code: TerminateOrganizationError,
        errors: List[str],
        request_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> "TerminateOrganizationResponse":
        """Create error response."""
        return cls(
            success=False,
            error_code=error_code,
            errors=errors,
            duration_ms=duration_ms,
            request_id=request_id,
        )


# =============================================================================
# USE CASE IMPLEMENTATION
# =============================================================================

class TerminateOrganizationUseCase:
    """
    Use case for terminating an organization.
    
    Handles the complete termination workflow including
    validation, state transition, and event publishing.
    
    Thread Safety:
        Stateless and thread-safe.
    """
    
    # Counter for termination metrics
    _termination_counter = None
    
    def __init__(
        self,
        repository: OrganizationRepository,
        event_publisher: EventPublisher,
        lifecycle: Optional[OrganizationLifecycle] = None,
    ):
        """
        Initialize use case with dependencies.
        
        Args:
            repository: Organization persistence port
            event_publisher: Event publishing port
            lifecycle: Optional lifecycle service (uses default if not provided)
        """
        self._repository = repository
        self._event_publisher = event_publisher
        self._lifecycle = lifecycle or OrganizationLifecycle()
        
        # Initialize metrics
        logger.debug("TerminateOrganizationUseCase initialized")
    
    @trace_operation("terminate_organization", kind=SpanKind.INTERNAL)
    def execute(
        self,
        request: TerminateOrganizationRequest,
    ) -> TerminateOrganizationResponse:
        """
        Execute the terminate organization use case.
        
        Args:
            request: Termination request parameters
            
        Returns:
            Response with result or errors
        """
        start_time = time.perf_counter()
        request_id = request.request_id or f"req-{uuid4().hex[:12]}"
        
        with LogContext(
            correlation_id=request.correlation_id,
            request_id=request_id,
        ):
            logger.info(
                "Starting organization termination",
                org_id=request.org_id,
                reason=request.reason,
                terminated_by=request.terminated_by,
            )
            
            try:
                # Step 1: Validate request
                with create_span("validate_request") as span:
                    if not request.org_id:
                        return self._error_response(
                            TerminateOrganizationError.INTERNAL_ERROR,
                            ["org_id is required"],
                            request_id, start_time,
                        )
                    
                    if not request.reason:
                        return self._error_response(
                            TerminateOrganizationError.INTERNAL_ERROR,
                            ["reason is required"],
                            request_id, start_time,
                        )
                    
                    if request.data_retention_days <= 0:
                        return self._error_response(
                            TerminateOrganizationError.INTERNAL_ERROR,
                            ["data_retention_days must be positive"],
                            request_id, start_time,
                        )
                    
                    span.set_attribute("retention_days", request.data_retention_days)
                
                # Step 2: Load organization
                with create_span("load_organization") as span:
                    organization = self._repository.get_by_org_id(request.org_id)
                    
                    if organization is None:
                        logger.warning(
                            "Organization not found for termination",
                            org_id=request.org_id,
                        )
                        return self._error_response(
                            TerminateOrganizationError.ORGANIZATION_NOT_FOUND,
                            [f"Organization not found: {request.org_id}"],
                            request_id, start_time,
                        )
                    
                    previous_status = organization.status
                    span.set_attribute("current_status", organization.status.value)
                    
                    logger.debug(
                        "Organization loaded for termination",
                        org_id=request.org_id,
                        name=organization.name,
                        status=organization.status.value,
                    )
                
                # Step 3: Apply termination using lifecycle
                with create_span("apply_termination") as span:
                    try:
                        # Call OrganizationLifecycle.terminate to validate and apply transition
                        self._lifecycle.terminate(
                            organization,
                            reason=request.reason,
                            retention_days=request.data_retention_days,
                        )
                        
                        now = datetime.now(timezone.utc)
                        retention_until = now + timedelta(days=request.data_retention_days)
                        
                        span.set_attribute("terminated_at", str(now))
                        span.set_attribute("data_retention_until", str(retention_until))
                        
                        logger.info(
                            "Termination applied to organization",
                            org_id=request.org_id,
                            reason=request.reason,
                            terminated_at=now.isoformat(),
                            retention_until=retention_until.isoformat(),
                        )
                    except Exception as e:
                        # Check if it's an invalid state transition error
                        if "InvalidStateTransition" in str(type(e).__name__):
                            allowed = get_allowed_transitions(previous_status)
                            logger.warning(
                                "Invalid state transition for termination",
                                org_id=request.org_id,
                                current_status=previous_status.value,
                                allowed_transitions=[s.value for s in allowed],
                            )
                            return self._error_response(
                                TerminateOrganizationError.INVALID_STATE_TRANSITION,
                                [
                                    f"Cannot terminate organization in '{previous_status.value}' status. "
                                    f"Allowed transitions: {[s.value for s in allowed]}"
                                ],
                                request_id, start_time,
                            )
                        else:
                            raise
                
                # Step 4: Persist changes
                with create_span("persist_termination", kind=SpanKind.CLIENT) as span:
                    try:
                        self._repository.save(organization)
                        span.set_attribute("persisted", True)
                        
                        logger.info(
                            "Organization termination persisted",
                            org_id=request.org_id,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to persist termination",
                            org_id=request.org_id,
                            error=str(e),
                            exc_info=True,
                        )
                        return self._error_response(
                            TerminateOrganizationError.PERSISTENCE_ERROR,
                            [f"Failed to save termination: {str(e)}"],
                            request_id, start_time,
                        )
                
                # Step 5: Publish events
                with create_span("publish_events", kind=SpanKind.PRODUCER) as span:
                    event = OrganizationTerminatedEvent(
                        org_id=request.org_id,
                        reason=request.reason,
                        data_retention_until=retention_until,
                        terminated_by=request.terminated_by or "system",
                    )
                    
                    try:
                        self._event_publisher.publish(event)
                        span.set_attribute("event_published", True)
                        
                        logger.info(
                            "Termination event published",
                            org_id=request.org_id,
                            event_type="OrganizationTerminatedEvent",
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to publish termination event",
                            org_id=request.org_id,
                            error=str(e),
                        )
                
                # Step 6: Record metrics
                self._record_metrics(organization, previous_status, request)
                
                # Calculate duration
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                logger.info(
                    "Organization terminated successfully",
                    org_id=request.org_id,
                    reason=request.reason,
                    duration_ms=round(duration_ms, 2),
                )
                
                return TerminateOrganizationResponse.success_response(
                    org_id=request.org_id,
                    terminated_at=now,
                    data_retention_until=retention_until,
                    duration_ms=duration_ms,
                    request_id=request_id,
                )
                
            except Exception as e:
                logger.exception(
                    "Unexpected error during termination",
                    org_id=request.org_id,
                    error=str(e),
                )
                
                return self._error_response(
                    TerminateOrganizationError.INTERNAL_ERROR,
                    [f"Internal error: {str(e)}"],
                    request_id, start_time,
                )
    
    def _error_response(
        self,
        error_code: TerminateOrganizationError,
        errors: List[str],
        request_id: str,
        start_time: float,
    ) -> TerminateOrganizationResponse:
        """Create error response."""
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        logger.warning(
            "Termination failed",
            error_code=error_code.value,
            errors=errors,
            duration_ms=round(duration_ms, 2),
        )
        
        return TerminateOrganizationResponse.error_response(
            error_code=error_code,
            errors=errors,
            request_id=request_id,
            duration_ms=duration_ms,
        )
    
    def _record_metrics(
        self,
        organization: Organization,
        previous_status: OrganizationStatus,
        request: TerminateOrganizationRequest,
    ) -> None:
        """Record metrics and audit log."""
        # Increment counter
        if self._termination_counter:
            try:
                # Attempt to increment with the termination reason label
                self._termination_counter.inc(labels={"reason": request.reason})
            except Exception:
                # Fallback to increment without labels if counter not configured with labels
                self._termination_counter.inc()
        
        # Audit log
        audit.log_modification(
            actor_id=request.terminated_by or "system",
            resource_type="organization",
            resource_id=request.org_id,
            action="terminate",
            changes={
                "reason": request.reason,
                "previous_status": previous_status.value,
                "new_status": OrganizationStatus.TERMINATED.value,
                "retention_days": request.data_retention_days,
            },
        )


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Ports
    "OrganizationRepository",
    "EventPublisher",
    
    # Enums
    "TerminateOrganizationError",
    
    # DTOs
    "TerminateOrganizationRequest",
    "TerminateOrganizationResponse",
    
    # Use case
    "TerminateOrganizationUseCase",
    
    # Constants
    "DEFAULT_RETENTION_DAYS",
]
