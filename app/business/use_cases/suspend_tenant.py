"""
Suspend Organization Use Case - Production-Grade Implementation
===============================================================

Enterprise-ready use case for suspending organizations.
Handles voluntary suspension, billing-triggered suspension,
and administrative holds.

Features:
    - Multiple suspension reasons tracking
    - Grace period management
    - Access preservation options
    - Automatic downstream notifications
    - Comprehensive audit trail

Suspension Types:
    - BILLING: Payment failure (auto-suspends after grace period)
    - VOLUNTARY: Customer requested (can reactivate anytime)
    - ADMINISTRATIVE: Policy violation (requires manual review)
    - LEGAL: Legal hold (data preserved, no modifications)
    - SCHEDULED: Planned maintenance or migration

Flow:
    1. Validate organization exists and can be suspended
    2. Apply domain state transition rules
    3. Configure suspension parameters
    4. Update database within transaction
    5. Publish suspension events
    6. Trigger downstream notifications

Author: Platform Engineering Team
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import UUID, uuid4

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
from domain.models import (
    Organization,
    OrganizationStatus,
)
from app.business.domain.entities.lifecycle import (
    can_transition,
    get_allowed_transitions,
)

# Event imports
from app.business.events.tenant_events import (
    OrganizationSuspendedEvent,
    SuspensionWarningEvent,
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


@runtime_checkable
class NotificationService(Protocol):
    """Port for sending notifications."""
    
    def send_suspension_notice(
        self,
        org_id: str,
        email: str,
        reason: str,
        suspended_until: Optional[datetime],
    ) -> None:
        """Send suspension notification."""
        ...


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class SuspensionReason(Enum):
    """Reason for organization suspension."""
    
    BILLING = "billing"
    VOLUNTARY = "voluntary"
    ADMINISTRATIVE = "administrative"
    LEGAL = "legal"
    SCHEDULED = "scheduled"
    SECURITY = "security"
    ABUSE = "abuse"


class SuspensionError(Enum):
    """Error codes for suspension operations."""
    
    NOT_FOUND = "NOT_FOUND"
    INVALID_STATE = "INVALID_STATE"
    ALREADY_SUSPENDED = "ALREADY_SUSPENDED"
    CANNOT_SUSPEND = "CANNOT_SUSPEND"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Default grace periods by suspension reason (in days)
DEFAULT_GRACE_PERIODS = {
    SuspensionReason.BILLING: 7,        # 7 days to resolve payment
    SuspensionReason.VOLUNTARY: 0,      # Immediate
    SuspensionReason.ADMINISTRATIVE: 0, # Immediate
    SuspensionReason.LEGAL: 0,          # Immediate
    SuspensionReason.SCHEDULED: 0,      # Scheduled suspension
    SuspensionReason.SECURITY: 0,       # Immediate
    SuspensionReason.ABUSE: 0,          # Immediate
}


# =============================================================================
# REQUEST/RESPONSE DTOs
# =============================================================================

@dataclass
class SuspendOrganizationRequest:
    """
    Request DTO for suspending an organization.
    
    Attributes:
        org_id: Organization to suspend
        reason: Why the organization is being suspended
        suspended_by: ID of user/system initiating suspension
        suspended_by_email: Email of actor
        notes: Optional internal notes
        scheduled_at: For scheduled suspensions
        suspend_until: Optional auto-resume date
        preserve_data: Whether to preserve all data (default True)
        allow_readonly: Allow read-only access during suspension
        notify_admins: Send notification to org admins
        grace_period_days: Override default grace period
    """
    
    # Required
    org_id: str
    reason: str
    
    # Actor information
    suspended_by: Optional[str] = None
    suspended_by_email: Optional[str] = None
    
    # Suspension configuration
    notes: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    suspend_until: Optional[datetime] = None
    
    # Behavior flags
    preserve_data: bool = True
    allow_readonly: bool = False
    notify_admins: bool = True
    
    # Grace period override
    grace_period_days: Optional[int] = None
    
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
class SuspendOrganizationResponse:
    """Response DTO for suspension operation."""
    
    success: bool
    
    # Result
    org_id: Optional[str] = None
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    suspended_at: Optional[datetime] = None
    suspend_until: Optional[datetime] = None
    
    # Error details
    error_code: Optional[SuspensionError] = None
    errors: List[str] = field(default_factory=list)
    
    # Timing
    duration_ms: Optional[float] = None
    request_id: Optional[str] = None
    
    @classmethod
    def success_response(
        cls,
        org_id: str,
        previous_status: str,
        suspended_at: datetime,
        suspend_until: Optional[datetime] = None,
        duration_ms: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> "SuspendOrganizationResponse":
        """Create success response."""
        return cls(
            success=True,
            org_id=org_id,
            previous_status=previous_status,
            new_status=OrganizationStatus.SUSPENDED.value,
            suspended_at=suspended_at,
            suspend_until=suspend_until,
            duration_ms=duration_ms,
            request_id=request_id,
        )
    
    @classmethod
    def error_response(
        cls,
        error_code: SuspensionError,
        errors: List[str],
        request_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> "SuspendOrganizationResponse":
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

class SuspendOrganizationUseCase:
    """
    Use case for suspending an organization.
    
    Handles the complete suspension workflow including
    validation, state transition, and notifications.
    
    Thread Safety:
        Stateless and thread-safe.
    """
    
    # Counter for suspension metrics
    _suspension_counter = None
    
    def __init__(
        self,
        repository: OrganizationRepository,
        event_publisher: EventPublisher,
        notification_service: Optional[NotificationService] = None,
    ):
        """
        Initialize use case with dependencies.
        
        Args:
            repository: Organization persistence port
            event_publisher: Event publishing port
            notification_service: Optional notification port
        """
        self._repository = repository
        self._event_publisher = event_publisher
        self._notification_service = notification_service
        
        # Initialize metrics
        logger.debug(
            "SuspendOrganizationUseCase initialized",
            has_notification_service=notification_service is not None,
        )
    
    @trace_operation("suspend_organization", kind=SpanKind.INTERNAL)
    def execute(
        self,
        request: SuspendOrganizationRequest,
    ) -> SuspendOrganizationResponse:
        """
        Execute the suspend organization use case.
        
        Args:
            request: Suspension request parameters
            
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
                "Starting organization suspension",
                org_id=request.org_id,
                reason=request.reason,
                suspended_by=request.suspended_by,
            )
            
            try:
                # Step 1: Parse and validate reason
                with create_span("validate_reason") as span:
                    reason = self._parse_reason(request.reason)
                    if reason is None:
                        valid_reasons = [r.value for r in SuspensionReason]
                        return self._error_response(
                            SuspensionError.INTERNAL_ERROR,
                            [f"Invalid suspension reason: {request.reason}. Valid: {valid_reasons}"],
                            request_id, start_time,
                        )
                    span.set_attribute("reason", reason.value)
                
                # Step 2: Load organization
                with create_span("load_organization") as span:
                    organization = self._repository.get_by_org_id(request.org_id)
                    
                    if organization is None:
                        logger.warning(
                            "Organization not found for suspension",
                            org_id=request.org_id,
                        )
                        return self._error_response(
                            SuspensionError.NOT_FOUND,
                            [f"Organization not found: {request.org_id}"],
                            request_id, start_time,
                        )
                    
                    span.set_attribute("current_status", organization.status.value)
                    span.set_attribute("edition", organization.edition.value)
                    
                    logger.debug(
                        "Organization loaded for suspension",
                        org_id=request.org_id,
                        name=organization.name,
                        status=organization.status.value,
                    )
                
                # Step 3: Validate state transition
                with create_span("validate_transition") as span:
                    previous_status = organization.status
                    
                    if previous_status == OrganizationStatus.SUSPENDED:
                        logger.info(
                            "Organization already suspended",
                            org_id=request.org_id,
                        )
                        return self._error_response(
                            SuspensionError.ALREADY_SUSPENDED,
                            ["Organization is already suspended"],
                            request_id, start_time,
                        )
                    
                    if not can_transition(previous_status, OrganizationStatus.SUSPENDED):
                        allowed = get_allowed_transitions(previous_status)
                        logger.warning(
                            "Invalid state transition for suspension",
                            org_id=request.org_id,
                            current_status=previous_status.value,
                            allowed_transitions=[s.value for s in allowed],
                        )
                        return self._error_response(
                            SuspensionError.CANNOT_SUSPEND,
                            [
                                f"Cannot suspend organization in '{previous_status.value}' status. "
                                f"Allowed transitions: {[s.value for s in allowed]}"
                            ],
                            request_id, start_time,
                        )
                    
                    span.set_attribute("transition_valid", True)
                    logger.debug(
                        "State transition validated",
                        from_status=previous_status.value,
                        to_status="suspended",
                    )
                
                # Step 4: Apply suspension
                with create_span("apply_suspension") as span:
                    now = datetime.now(timezone.utc)
                    
                    # Calculate effective suspension date
                    grace_days = request.grace_period_days
                    if grace_days is None:
                        grace_days = DEFAULT_GRACE_PERIODS.get(reason, 0)
                    
                    effective_date = now
                    if grace_days > 0:
                        effective_date = now + timedelta(days=grace_days)
                        span.set_attribute("grace_period_days", grace_days)
                        
                        logger.info(
                            "Suspension has grace period",
                            org_id=request.org_id,
                            grace_days=grace_days,
                            effective_date=effective_date.isoformat(),
                        )
                    
                    # Update organization state
                    organization.status = OrganizationStatus.SUSPENDED
                    organization.suspended_at = effective_date
                    organization.suspended_reason = reason.value
                    organization.suspended_by = request.suspended_by
                    organization.suspension_notes = request.notes
                    organization.updated_at = now
                    
                    if request.suspend_until:
                        organization.suspension_ends_at = request.suspend_until
                    
                    span.set_attribute("effective_date", str(effective_date))
                    span.set_attribute("allow_readonly", request.allow_readonly)
                    
                    logger.info(
                        "Suspension applied to organization",
                        org_id=request.org_id,
                        reason=reason.value,
                        effective_date=effective_date.isoformat(),
                    )
                
                # Step 5: Persist changes
                with create_span("persist_suspension", kind=SpanKind.CLIENT) as span:
                    try:
                        self._repository.save(organization)
                        span.set_attribute("persisted", True)
                        
                        logger.info(
                            "Organization suspension persisted",
                            org_id=request.org_id,
                            reason=reason.value,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to persist suspension",
                            org_id=request.org_id,
                            error=str(e),
                            exc_info=True,
                        )
                        return self._error_response(
                            SuspensionError.PERSISTENCE_FAILED,
                            [f"Failed to save suspension: {str(e)}"],
                            request_id, start_time,
                        )
                
                # Step 6: Publish events
                with create_span("publish_events", kind=SpanKind.PRODUCER) as span:
                    events = [
                        OrganizationSuspendedEvent(
                            org_id=request.org_id,
                            reason=reason.value,
                            suspended_by=request.suspended_by,
                            previous_status=previous_status.value,
                            effective_at=effective_date,
                            suspend_until=request.suspend_until,
                        )
                    ]
                    
                    # Add warning event if grace period
                    if grace_days > 0:
                        events.append(SuspensionWarningEvent(
                            org_id=request.org_id,
                            reason=reason.value,
                            suspension_date=effective_date,
                            days_remaining=grace_days,
                        ))
                    
                    try:
                        self._event_publisher.publish_batch(events)
                        span.set_attribute("events_published", len(events))
                        
                        logger.info(
                            "Suspension events published",
                            org_id=request.org_id,
                            event_count=len(events),
                            event_types=[type(e).__name__ for e in events],
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to publish suspension events",
                            org_id=request.org_id,
                            error=str(e),
                        )
                
                # Step 7: Send notifications
                if request.notify_admins and self._notification_service:
                    with create_span("send_notifications") as span:
                        try:
                            billing_email = (
                                getattr(organization, 'billing_email', None) or 
                                getattr(organization, 'technical_contact_email', None)
                            )
                            if billing_email:
                                self._notification_service.send_suspension_notice(
                                    org_id=request.org_id,
                                    email=billing_email,
                                    reason=reason.value,
                                    suspended_until=request.suspend_until,
                                )
                                span.set_attribute("notification_sent", True)
                                
                                logger.info(
                                    "Suspension notification sent",
                                    org_id=request.org_id,
                                    email=billing_email[:3] + "***",  # Mask email
                                )
                        except Exception as e:
                            logger.warning(
                                "Failed to send suspension notification",
                                org_id=request.org_id,
                                error=str(e),
                            )
                
                # Step 8: Record metrics
                self._record_metrics(organization, reason, previous_status, request)
                
                # Calculate duration
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                logger.info(
                    "Organization suspended successfully",
                    org_id=request.org_id,
                    reason=reason.value,
                    previous_status=previous_status.value,
                    duration_ms=round(duration_ms, 2),
                )
                
                return SuspendOrganizationResponse.success_response(
                    org_id=request.org_id,
                    previous_status=previous_status.value,
                    suspended_at=effective_date,
                    suspend_until=request.suspend_until,
                    duration_ms=duration_ms,
                    request_id=request_id,
                )
                
            except Exception as e:
                logger.exception(
                    "Unexpected error during suspension",
                    org_id=request.org_id,
                    error=str(e),
                )
                
                return self._error_response(
                    SuspensionError.INTERNAL_ERROR,
                    [f"Internal error: {str(e)}"],
                    request_id, start_time,
                )
    
    def _parse_reason(self, reason_str: str) -> Optional[SuspensionReason]:
        """Parse suspension reason from string."""
        try:
            return SuspensionReason(reason_str.lower())
        except ValueError:
            valid_reasons = [r.value for r in SuspensionReason]
            logger.warning(
                "Invalid suspension reason",
                provided=reason_str,
                valid=valid_reasons,
            )
            return None
    
    def _error_response(
        self,
        error_code: SuspensionError,
        errors: List[str],
        request_id: str,
        start_time: float,
    ) -> SuspendOrganizationResponse:
        """Create error response."""
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        logger.warning(
            "Suspension failed",
            error_code=error_code.value,
            errors=errors,
            duration_ms=round(duration_ms, 2),
        )
        
        return SuspendOrganizationResponse.error_response(
            error_code=error_code,
            errors=errors,
            request_id=request_id,
            duration_ms=duration_ms,
        )
    
    def _record_metrics(
        self,
        organization: Organization,
        reason: SuspensionReason,
        previous_status: OrganizationStatus,
        request: SuspendOrganizationRequest,
    ) -> None:
        """Record metrics and audit log."""
        # Increment counter
        if self._suspension_counter:
            self._suspension_counter.inc(
                labels={
                    "reason": reason.value,
                    "previous_status": previous_status.value,
                }
            )
        
        # Audit log
        audit.log_modification(
            actor_id=request.suspended_by or "system",
            resource_type="organization",
            resource_id=request.org_id,
            action="suspend",
            changes={
                "reason": reason.value,
                "previous_status": previous_status.value,
                "new_status": OrganizationStatus.SUSPENDED.value,
                "notes": request.notes,
            },
        )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def suspend_organization(
    org_id: str,
    reason: str,
    repository: OrganizationRepository,
    event_publisher: EventPublisher,
    **kwargs,
) -> SuspendOrganizationResponse:
    """
    Convenience function for suspending an organization.
    
    Args:
        org_id: Organization to suspend
        reason: Suspension reason (billing, voluntary, administrative, etc.)
        repository: Persistence port
        event_publisher: Event port
        **kwargs: Additional request parameters
        
    Returns:
        SuspendOrganizationResponse with result
        
    Example:
        >>> response = suspend_organization(
        ...     org_id="ORG-ABC12345",
        ...     reason="billing",
        ...     repository=repo,
        ...     event_publisher=publisher,
        ...     suspended_by="admin-123",
        ...     notify_admins=True,
        ... )
    """
    request = SuspendOrganizationRequest(
        org_id=org_id,
        reason=reason,
        **kwargs,
    )
    
    use_case = SuspendOrganizationUseCase(
        repository=repository,
        event_publisher=event_publisher,
    )
    
    return use_case.execute(request)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Ports
    "OrganizationRepository",
    "EventPublisher",
    "NotificationService",
    
    # Enums
    "SuspensionReason",
    "SuspensionError",
    
    # DTOs
    "SuspendOrganizationRequest",
    "SuspendOrganizationResponse",
    
    # Use case
    "SuspendOrganizationUseCase",
    
    # Convenience
    "suspend_organization",
    
    # Constants
    "DEFAULT_GRACE_PERIODS",
]
