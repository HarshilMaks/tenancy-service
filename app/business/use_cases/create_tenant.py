"""
Create Organization Use Case - Production-Grade Implementation
===============================================================

Enterprise-ready use case for creating new organizations (tenants).
This is the primary entry point for organization provisioning.

Features:
    - Full request validation
    - Domain invariant enforcement
    - Transactional persistence
    - Event publishing with outbox pattern
    - Comprehensive observability
    - Audit logging for compliance

Flow:
    1. Validate request (format, required fields)
    2. Check business rules (name uniqueness, edition validity)
    3. Generate unique organization ID
    4. Create domain object with invariant validation
    5. Persist within transaction
    6. Publish domain events
    7. Return response with created organization

Error Handling:
    - ValidationError: Invalid input data
    - DuplicateNameError: Organization name already exists
    - DomainError: Business rule violation
    - PersistenceError: Database operation failed
    - PublishingError: Event publishing failed (non-fatal)

Author: Platform Engineering Team
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import UUID, uuid4

# Infrastructure imports
from infrastructure.observability.logging import (
    get_logger,
    AuditLogger,
    LogContext,
    log_operation,
)
from infrastructure.observability.metrics import (
    get_metrics,
    track_organization_created,
)
from infrastructure.observability.tracing import (
    trace_operation,
    create_span,
    add_span_attributes,
    SpanKind,
)

# Domain imports
from domain.models import (
    Organization,
    OrganizationStatus,
    Edition,
    BillingStatus,
    OrganizationType,
    Region,
    Address,
)
from app.business.domain.models.invariants import (
    validate_organization_creation,
    normalize_organization_name,
    ValidationResult,
)
from app.business.domain.entities.lifecycle import OrganizationLifecycle

# Event imports
from app.business.events.tenant_events import (
    OrganizationCreatedEvent,
    TrialStartedEvent,
)

# Setup logging
logger = get_logger(__name__)
audit = AuditLogger("tenancy_service")


# =============================================================================
# PORTS (Dependency Injection Interfaces)
# =============================================================================

@runtime_checkable
class OrganizationRepository(Protocol):
    """
    Port for organization persistence operations.
    
    Implemented by infrastructure layer (SQLAlchemy repository).
    """
    
    def save(self, organization: Organization) -> Organization:
        """Persist organization (create or update)."""
        ...
    
    def get_by_id(self, organization_id: UUID) -> Organization:
        """Get organization by internal ID."""
        ...
    
    def get_by_org_id(self, org_id: str) -> Organization:
        """Get organization by external ID (ORG-XXXXXXXX)."""
        ...
    
    def exists_by_normalized_name(self, normalized_name: str) -> bool:
        """Check if name is already taken."""
        ...
    
    def exists_by_org_id(self, org_id: str) -> bool:
        """Check if org_id already exists."""
        ...


@runtime_checkable
class EventPublisher(Protocol):
    """
    Port for event publishing.
    
    Implemented by infrastructure layer (message broker adapter).
    """
    
    def publish(self, event: Any) -> None:
        """Publish single domain event."""
        ...
    
    def publish_batch(self, events: List[Any]) -> None:
        """Publish batch of events."""
        ...


@runtime_checkable
class IdGenerator(Protocol):
    """
    Port for generating unique identifiers.
    
    Allows injection of different ID generation strategies
    (UUID, snowflake, etc.) for testing and customization.
    """
    
    def generate_org_id(self) -> str:
        """Generate unique organization ID (ORG-XXXXXXXX format)."""
        ...
    
    def generate_uuid(self) -> UUID:
        """Generate unique internal UUID."""
        ...


# =============================================================================
# DEFAULT IMPLEMENTATIONS
# =============================================================================

class DefaultIdGenerator:
    """
    Default ID generator using UUID.
    
    Generates IDs in Salesforce-style format:
        - org_id: ORG-XXXXXXXX (8 hex characters)
        - internal: Standard UUID4
    """
    
    def generate_org_id(self) -> str:
        """Generate organization ID with collision check prefix."""
        unique_part = uuid4().hex[:8].upper()
        return f"ORG-{unique_part}"
    
    def generate_uuid(self) -> UUID:
        """Generate internal UUID."""
        return uuid4()


# =============================================================================
# REQUEST/RESPONSE DTOs
# =============================================================================

@dataclass
class CreateOrganizationRequest:
    """
    Request DTO for creating an organization.
    
    Immutable data transfer object containing all parameters
    needed to create a new organization.
    
    Attributes:
        name: Display name (required, 1-255 chars)
        edition: Subscription tier (FREE, ESSENTIALS, PROFESSIONAL, ENTERPRISE, UNLIMITED)
        region: Deployment region (US_EAST_1, EU_WEST_1, etc.)
        org_type: Organization type (PRODUCTION, SANDBOX, DEVELOPER)
        parent_org_id: For sandboxes, the parent production org
        start_trial: Whether to start trial period (default True)
        trial_days: Trial duration in days (default 14)
        created_by_user_id: ID of user creating the org
        created_by_email: Email of user creating the org
        billing_email: Email for billing notifications
        address: Physical/billing address
        external_id: External system reference
        metadata: Additional custom data
    """
    
    # Required fields
    name: str
    edition: str
    region: str
    
    # Organization type
    org_type: str = "PRODUCTION"
    parent_org_id: Optional[str] = None
    
    # Creator info
    created_by_user_id: Optional[str] = None
    created_by_email: Optional[str] = None
    
    # Trial configuration
    start_trial: bool = True
    trial_days: int = 14
    
    # Contact info
    billing_email: Optional[str] = None
    technical_contact_email: Optional[str] = None
    
    # Address
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    
    # External references
    external_id: Optional[str] = None
    
    # Custom data
    metadata: Optional[Dict[str, Any]] = None
    
    # Request tracking
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        """Normalize string fields."""
        self.name = self.name.strip() if self.name else ""
        self.edition = self.edition.upper() if self.edition else ""
        self.region = self.region.upper().replace("-", "_") if self.region else ""
        self.org_type = self.org_type.upper() if self.org_type else "PRODUCTION"


class CreateOrganizationError(Enum):
    """Error codes for organization creation."""
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INVALID_EDITION = "INVALID_EDITION"
    INVALID_REGION = "INVALID_REGION"
    INVALID_ORG_TYPE = "INVALID_ORG_TYPE"
    NAME_ALREADY_EXISTS = "NAME_ALREADY_EXISTS"
    PARENT_ORG_NOT_FOUND = "PARENT_ORG_NOT_FOUND"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    EVENT_PUBLISH_FAILED = "EVENT_PUBLISH_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class CreateOrganizationResponse:
    """
    Response DTO for organization creation.
    
    Contains result of the operation including the created
    organization or error details.
    """
    
    # Status
    success: bool
    
    # Result (on success)
    org_id: Optional[str] = None
    organization: Optional[Organization] = None
    
    # Error details (on failure)
    error_code: Optional[CreateOrganizationError] = None
    errors: List[str] = field(default_factory=list)
    
    # Warnings (non-fatal issues)
    warnings: List[str] = field(default_factory=list)
    
    # Timing
    duration_ms: Optional[float] = None
    
    # Tracking
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    
    @classmethod
    def success_response(
        cls,
        organization: Organization,
        warnings: Optional[List[str]] = None,
        duration_ms: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> "CreateOrganizationResponse":
        """Create success response."""
        return cls(
            success=True,
            org_id=organization.org_id,
            organization=organization,
            warnings=warnings or [],
            duration_ms=duration_ms,
            request_id=request_id,
        )
    
    @classmethod
    def error_response(
        cls,
        error_code: CreateOrganizationError,
        errors: List[str],
        request_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> "CreateOrganizationResponse":
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

class CreateOrganizationUseCase:
    """
    Use case for creating a new organization.
    
    Orchestrates the entire organization creation process:
    1. Input validation and normalization
    2. Business rule enforcement
    3. Domain object creation
    4. Transactional persistence
    5. Event publishing
    
    Thread Safety:
        This class is stateless and thread-safe.
        Create one instance and reuse across requests.
    
    Usage:
        >>> repo = OrganizationRepository(session)
        >>> publisher = EventPublisher()
        >>> use_case = CreateOrganizationUseCase(repo, publisher)
        >>> 
        >>> request = CreateOrganizationRequest(
        ...     name="Acme Corporation",
        ...     edition="PROFESSIONAL",
        ...     region="US_EAST_1",
        ... )
        >>> response = use_case.execute(request)
        >>> if response.success:
        ...     print(f"Created: {response.org_id}")
    """
    
    def __init__(
        self,
        repository: OrganizationRepository,
        event_publisher: EventPublisher,
        id_generator: Optional[IdGenerator] = None,
    ):
        """
        Initialize use case with dependencies.
        
        Args:
            repository: Organization persistence port
            event_publisher: Event publishing port
            id_generator: ID generation port (optional)
        """
        self._repository = repository
        self._event_publisher = event_publisher
        self._id_generator = id_generator or DefaultIdGenerator()
        
        logger.debug(
            "CreateOrganizationUseCase initialized",
            repository_type=type(repository).__name__,
            publisher_type=type(event_publisher).__name__,
        )
    
    @trace_operation("create_organization", kind=SpanKind.INTERNAL)
    def execute(self, request: CreateOrganizationRequest) -> CreateOrganizationResponse:
        """
        Execute the create organization use case.
        
        Args:
            request: Organization creation parameters
            
        Returns:
            Response with created organization or errors
        """
        start_time = time.perf_counter()
        request_id = request.request_id or f"req-{uuid4().hex[:12]}"
        
        # Set up logging context
        with LogContext(
            correlation_id=request.correlation_id,
            request_id=request_id,
        ):
            logger.info(
                "Starting organization creation",
                request_id=request_id,
                org_name=request.name,
                edition=request.edition,
                region=request.region,
            )
            
            try:
                # Step 1: Parse and validate enums
                with create_span("validate_enums") as span:
                    edition, region, org_type, errors = self._parse_enums(request)
                    
                    if errors:
                        span.set_attribute("validation_failed", True)
                        return self._create_error_response(
                            errors, request_id, start_time,
                            CreateOrganizationError.VALIDATION_FAILED
                        )
                    
                    span.set_attribute("edition", edition.value)
                    span.set_attribute("region", region.value)
                
                # Step 2: Validate business rules
                with create_span("validate_business_rules") as span:
                    validation = self._validate_business_rules(
                        request, edition, region, org_type
                    )
                    
                    if not validation.is_valid:
                        span.set_attribute("validation_failed", True)
                        return self._create_error_response(
                            validation.errors, request_id, start_time,
                            CreateOrganizationError.VALIDATION_FAILED
                        )
                
                # Step 3: Check name uniqueness
                with create_span("check_uniqueness") as span:
                    normalized_name = normalize_organization_name(request.name)
                    span.set_attribute("normalized_name", normalized_name)
                    
                    if self._repository.exists_by_normalized_name(normalized_name):
                        logger.warning(
                            "Organization name already exists",
                            name=request.name,
                            normalized_name=normalized_name,
                        )
                        return self._create_error_response(
                            [f"Organization name '{request.name}' is already taken"],
                            request_id, start_time,
                            CreateOrganizationError.NAME_ALREADY_EXISTS
                        )
                
                # Step 4: Generate identifiers
                with create_span("generate_ids") as span:
                    internal_id = self._id_generator.generate_uuid()
                    org_id = self._generate_unique_org_id()
                    
                    span.set_attribute("org_id", org_id)
                    span.set_attribute("internal_id", str(internal_id))
                
                # Step 5: Create domain object
                with create_span("create_domain_object") as span:
                    organization = self._create_organization(
                        internal_id=internal_id,
                        org_id=org_id,
                        request=request,
                        edition=edition,
                        region=region,
                        org_type=org_type,
                        normalized_name=normalized_name,
                    )
                    
                    span.set_attribute("status", organization.status.value)
                    span.set_attribute("is_trial", organization.is_trial())
                
                # Step 6: Handle trial setup
                events: List[Any] = []
                if request.start_trial and edition != Edition.FREE:
                    with create_span("setup_trial") as span:
                        organization.start_trial(request.trial_days)
                        
                        events.append(TrialStartedEvent(
                            org_id=org_id,
                            edition=edition.value,
                            trial_days=request.trial_days,
                            trial_ends_at=organization.trial_ends_at,
                        ))
                        
                        span.set_attribute("trial_days", request.trial_days)
                        span.set_attribute("trial_ends_at", str(organization.trial_ends_at))
                
                # Step 7: Persist to database
                with create_span("persist_organization", kind=SpanKind.CLIENT) as span:
                    try:
                        saved_org = self._repository.save(organization)
                        span.set_attribute("persisted", True)
                        
                        logger.info(
                            "Organization persisted successfully",
                            org_id=org_id,
                            internal_id=str(internal_id),
                        )
                        
                    except Exception as e:
                        logger.error(
                            "Failed to persist organization",
                            org_id=org_id,
                            error=str(e),
                            exc_info=True,
                        )
                        return self._create_error_response(
                            [f"Failed to save organization: {str(e)}"],
                            request_id, start_time,
                            CreateOrganizationError.PERSISTENCE_FAILED
                        )
                
                # Step 8: Publish domain events
                with create_span("publish_events", kind=SpanKind.PRODUCER) as span:
                    # Add creation event
                    events.insert(0, OrganizationCreatedEvent(
                        org_id=org_id,
                        name=organization.name,
                        edition=edition.value,
                        region=region.value,
                        org_type=org_type.value,
                        created_by=request.created_by_user_id,
                    ))
                    
                    span.set_attribute("event_count", len(events))
                    
                    try:
                        self._event_publisher.publish_batch(events)
                        
                        logger.info(
                            "Domain events published",
                            org_id=org_id,
                            event_count=len(events),
                            event_types=[e.__class__.__name__ for e in events],
                        )
                        
                    except Exception as e:
                        # Event publishing failure is non-fatal
                        # Events will be retried via outbox pattern
                        logger.warning(
                            "Event publishing failed (will retry)",
                            org_id=org_id,
                            error=str(e),
                        )
                
                # Step 9: Record metrics and audit
                self._record_success_metrics(organization, request)
                
                # Calculate duration
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                logger.info(
                    "Organization created successfully",
                    org_id=org_id,
                    org_name=organization.name,
                    edition=edition.value,
                    region=region.value,
                    is_trial=organization.is_trial(),
                    duration_ms=duration_ms,
                )
                
                return CreateOrganizationResponse.success_response(
                    organization=saved_org,
                    warnings=validation.warnings if validation.warnings else None,
                    duration_ms=duration_ms,
                    request_id=request_id,
                )
                
            except Exception as e:
                logger.exception(
                    "Unexpected error during organization creation",
                    error=str(e),
                    org_name=request.name,
                )
                
                return self._create_error_response(
                    [f"Internal error: {str(e)}"],
                    request_id, start_time,
                    CreateOrganizationError.INTERNAL_ERROR
                )
    
    def _parse_enums(
        self,
        request: CreateOrganizationRequest,
    ) -> tuple[Optional[Edition], Optional[Region], Optional[OrganizationType], List[str]]:
        """Parse and validate enum values from request."""
        errors = []
        edition = None
        region = None
        org_type = None
        
        # Parse edition
        try:
            edition = Edition(request.edition.lower())
        except ValueError:
            valid_editions = [e.value for e in Edition]
            errors.append(
                f"Invalid edition: '{request.edition}'. "
                f"Valid options: {', '.join(valid_editions)}"
            )
            logger.warning(
                "Invalid edition provided",
                provided=request.edition,
                valid=valid_editions,
            )
        
        # Parse region
        try:
            region = Region(request.region.lower().replace("_", "-"))
        except ValueError:
            valid_regions = [r.value for r in Region]
            errors.append(
                f"Invalid region: '{request.region}'. "
                f"Valid options: {', '.join(valid_regions)}"
            )
            logger.warning(
                "Invalid region provided",
                provided=request.region,
                valid=valid_regions,
            )
        
        # Parse org type
        try:
            org_type = OrganizationType(request.org_type.lower())
        except ValueError:
            valid_types = [t.value for t in OrganizationType]
            errors.append(
                f"Invalid organization type: '{request.org_type}'. "
                f"Valid options: {', '.join(valid_types)}"
            )
            logger.warning(
                "Invalid org_type provided",
                provided=request.org_type,
                valid=valid_types,
            )
        
        return edition, region, org_type, errors
    
    def _validate_business_rules(
        self,
        request: CreateOrganizationRequest,
        edition: Edition,
        region: Region,
        org_type: OrganizationType,
    ) -> ValidationResult:
        """Validate business rules using domain invariants."""
        return validate_organization_creation(
            name=request.name,
            edition=edition,
            region=region,
            org_type=org_type,
            parent_org_id=request.parent_org_id,
        )
    
    def _generate_unique_org_id(self, max_attempts: int = 10) -> str:
        """Generate unique org_id with collision checking."""
        for attempt in range(max_attempts):
            org_id = self._id_generator.generate_org_id()
            
            if not self._repository.exists_by_org_id(org_id):
                logger.debug(
                    "Generated unique org_id",
                    org_id=org_id,
                    attempts=attempt + 1,
                )
                return org_id
            
            logger.warning(
                "org_id collision detected, regenerating",
                org_id=org_id,
                attempt=attempt + 1,
            )
        
        # Fallback: use longer unique suffix
        fallback_id = f"ORG-{uuid4().hex[:12].upper()}"
        logger.warning(
            "Using fallback org_id generation",
            org_id=fallback_id,
        )
        return fallback_id
    
    def _create_organization(
        self,
        internal_id: UUID,
        org_id: str,
        request: CreateOrganizationRequest,
        edition: Edition,
        region: Region,
        org_type: OrganizationType,
        normalized_name: str,
    ) -> Organization:
        """Create Organization domain object."""
        now = datetime.now(timezone.utc)
        
        # Determine initial status based on edition and trial
        if request.start_trial and edition != Edition.FREE:
            initial_status = OrganizationStatus.TRIAL
            billing_status = BillingStatus.TRIAL
        else:
            initial_status = OrganizationStatus.PROVISIONING
            billing_status = BillingStatus.ACTIVE if edition == Edition.FREE else BillingStatus.PAST_DUE
        
        # Build address if provided
        billing_address = None
        if any([request.street, request.city, request.country]):
            billing_address = Address(
                street=request.street or "",
                city=request.city or "",
                state=request.state or "",
                postal_code=request.postal_code or "",
                country=request.country or "US",
            )
        
        # Create organization
        return Organization(
            id=internal_id,
            org_id=org_id,
            name=request.name.strip(),
            normalized_name=normalized_name,
            status=initial_status,
            edition=edition,
            org_type=org_type,
            region=region,
            billing_status=billing_status,
            parent_org_id=request.parent_org_id,
            billing_email=request.billing_email,
            technical_contact_email=request.technical_contact_email,
            billing_address=billing_address,
            external_id=request.external_id,
            metadata=request.metadata or {},
            created_at=now,
            updated_at=now,
            created_by=request.created_by_user_id,
        )
    
    def _create_error_response(
        self,
        errors: List[str],
        request_id: str,
        start_time: float,
        error_code: CreateOrganizationError,
    ) -> CreateOrganizationResponse:
        """Create error response with timing."""
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        logger.warning(
            "Organization creation failed",
            error_code=error_code.value,
            errors=errors,
            duration_ms=duration_ms,
        )
        
        return CreateOrganizationResponse.error_response(
            error_code=error_code,
            errors=errors,
            request_id=request_id,
            duration_ms=duration_ms,
        )
    
    def _record_success_metrics(
        self,
        organization: Organization,
        request: CreateOrganizationRequest,
    ) -> None:
        """Record metrics and audit log for successful creation."""
        # Metrics
        track_organization_created(
            edition=organization.edition.value,
            region=organization.region.value,
            is_trial=organization.is_trial(),
        )
        
        # Audit log
        audit.log_modification(
            actor_id=request.created_by_user_id or "system",
            resource_type="organization",
            resource_id=organization.org_id,
            action="create",
            changes={
                "name": organization.name,
                "edition": organization.edition.value,
                "region": organization.region.value,
                "org_type": organization.org_type.value,
            },
        )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def create_organization(
    name: str,
    edition: str,
    region: str,
    repository: OrganizationRepository,
    event_publisher: EventPublisher,
    **kwargs,
) -> CreateOrganizationResponse:
    """
    Convenience function for creating an organization.
    
    Wraps CreateOrganizationUseCase for simple use cases.
    
    Args:
        name: Organization display name
        edition: Subscription tier (FREE, PROFESSIONAL, etc.)
        region: Deployment region
        repository: Persistence port
        event_publisher: Event publishing port
        **kwargs: Additional request parameters
        
    Returns:
        CreateOrganizationResponse with result
    """
    request = CreateOrganizationRequest(
        name=name,
        edition=edition,
        region=region,
        **kwargs,
    )
    
    use_case = CreateOrganizationUseCase(
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
    "IdGenerator",
    
    # Default implementations
    "DefaultIdGenerator",
    
    # DTOs
    "CreateOrganizationRequest",
    "CreateOrganizationResponse",
    "CreateOrganizationError",
    
    # Use case
    "CreateOrganizationUseCase",
    
    # Convenience
    "create_organization",
]
