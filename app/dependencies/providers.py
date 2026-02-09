"""
Dependency Providers - FastAPI Dependency Injection Factories
=============================================================

This module is the GLUE between the API layer and the business logic layer.

HOW IT WORKS:
    FastAPI's Depends() system calls these factory functions before each request.
    Each function builds the objects that route handlers need:
    
    1. get_db_session() → yields a SQLAlchemy Session (auto-commits/rollbacks)
    2. get_organization_repository(session) → wraps session in Repository pattern
    3. get_*_use_case(session) → builds a use case with its dependencies
    
    The route handler then calls use_case.execute(request_dto) and maps the result.

WHY THIS EXISTS:
    Route handlers shouldn't know HOW to build repositories or use cases.
    They just declare what they need via Depends(), and FastAPI provides it.
    This keeps route handlers thin and testable.

EXAMPLE:
    @router.post("/tenants")
    async def create_tenant(
        tenant: TenantCreate,
        use_case: CreateOrganizationUseCase = Depends(get_create_tenant_use_case),
    ):
        # use_case is already built with repo + publisher injected
        response = use_case.execute(...)
"""

from typing import List

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

# Infrastructure — these are the "adapters" that connect to external systems
from infrastructure.database import get_db_session
from infrastructure.persistence.tenant_repository import OrganizationRepository
from infrastructure.messaging import get_event_publisher

# Domain model — needed for the org-to-response mapper
from domain.models import Organization

# Use cases — the business logic orchestrators
from app.business.use_cases.create_tenant import CreateOrganizationUseCase
from app.business.use_cases.suspend_tenant import SuspendOrganizationUseCase
from app.business.use_cases.enforce_policy import EnforcePolicyUseCase
from app.business.use_cases.get_tenants import GetTenantsListUseCase
from app.business.use_cases.update_tenant import UpdateTenantUseCase
from app.business.use_cases.activate_tenant import ActivateOrganizationUseCase
from app.business.use_cases.resume_tenant import ResumeOrganizationUseCase
from app.business.use_cases.terminate_tenant import TerminateOrganizationUseCase
from app.business.use_cases.delete_tenant import DeleteOrganizationUseCase
from app.business.use_cases.get_events import GetTenantEventsUseCase
from app.business.use_cases.get_usage import GetTenantUsageUseCase

# API schema — for the response mapper
from app.schemas.v1.requests_responses import TenantResponse


# =============================================================================
# REPOSITORY FACTORY
# =============================================================================

def get_organization_repository(
    session: Session = Depends(get_db_session),
) -> OrganizationRepository:
    """
    Build an OrganizationRepository from a DB session.
    
    The session is created by get_db_session (a generator that yields
    a Session and auto-commits on success / rollbacks on error).
    
    The repository wraps the session and provides domain-friendly
    methods like save(), get_by_id(), list(), etc.
    """
    return OrganizationRepository(session)


# =============================================================================
# USE CASE FACTORIES
# =============================================================================

def get_create_tenant_use_case(
    session: Session = Depends(get_db_session),
) -> CreateOrganizationUseCase:
    """
    Build CreateOrganizationUseCase with repository + event publisher.
    
    This use case needs:
    - OrganizationRepository: to save the new tenant to the database
    - EventPublisher: to publish domain events (e.g., OrganizationCreatedEvent)
    """
    repo = OrganizationRepository(session)
    publisher = get_event_publisher()
    return CreateOrganizationUseCase(repository=repo, event_publisher=publisher)


def get_suspend_tenant_use_case(
    session: Session = Depends(get_db_session),
) -> SuspendOrganizationUseCase:
    """
    Build SuspendOrganizationUseCase with repository + event publisher.
    
    This use case needs:
    - OrganizationRepository: to load the org, update its status, and save
    - EventPublisher: to publish OrganizationSuspendedEvent
    """
    repo = OrganizationRepository(session)
    publisher = get_event_publisher()
    return SuspendOrganizationUseCase(repository=repo, event_publisher=publisher)


def get_enforce_policy_use_case(
    session: Session = Depends(get_db_session),
) -> EnforcePolicyUseCase:
    """
    Build EnforcePolicyUseCase with repository.
    
    This use case only needs the repository (to load the org and check
    its edition/status). No events are published for policy checks.
    """
    repo = OrganizationRepository(session)
    return EnforcePolicyUseCase(repository=repo)


def get_get_tenants_use_case(
    session: Session = Depends(get_db_session),
) -> GetTenantsListUseCase:
    """Build GetTenantsListUseCase with repository."""
    repo = OrganizationRepository(session)
    return GetTenantsListUseCase(repository=repo)


def get_update_tenant_use_case(
    session: Session = Depends(get_db_session),
) -> UpdateTenantUseCase:
    """Build UpdateTenantUseCase with repository."""
    repo = OrganizationRepository(session)
    return UpdateTenantUseCase(repository=repo)


def get_activate_tenant_use_case(
    session: Session = Depends(get_db_session),
) -> ActivateOrganizationUseCase:
    """
    Build ActivateOrganizationUseCase with repository + event publisher.
    
    This use case needs:
    - OrganizationRepository: to load the org, update its status, and save
    - EventPublisher: to publish OrganizationActivatedEvent
    """
    repo = OrganizationRepository(session)
    publisher = get_event_publisher()
    return ActivateOrganizationUseCase(repository=repo, event_publisher=publisher)


def get_resume_tenant_use_case(
    session: Session = Depends(get_db_session),
) -> ResumeOrganizationUseCase:
    """
    Build ResumeOrganizationUseCase with repository + event publisher.
    
    This use case needs:
    - OrganizationRepository: to load the org, update its status, and save
    - EventPublisher: to publish OrganizationResumedEvent
    """
    repo = OrganizationRepository(session)
    publisher = get_event_publisher()
    return ResumeOrganizationUseCase(repository=repo, event_publisher=publisher)


def get_terminate_tenant_use_case(
    session: Session = Depends(get_db_session),
) -> TerminateOrganizationUseCase:
    """
    Build TerminateOrganizationUseCase with repository + event publisher.
    
    This use case needs:
    - OrganizationRepository: to load the org, update its status, and save
    - EventPublisher: to publish OrganizationTerminatedEvent
    """
    repo = OrganizationRepository(session)
    publisher = get_event_publisher()
    return TerminateOrganizationUseCase(repository=repo, event_publisher=publisher)


def get_delete_tenant_use_case(
    session: Session = Depends(get_db_session),
) -> DeleteOrganizationUseCase:
    """
    Build DeleteOrganizationUseCase with repository + event publisher.
    
    This use case needs:
    - OrganizationRepository: to load the org and hard delete it
    - EventPublisher: to publish OrganizationDeletedEvent
    """
    repo = OrganizationRepository(session)
    publisher = get_event_publisher()
    return DeleteOrganizationUseCase(repository=repo, event_publisher=publisher)


# =============================================================================
# ERROR MAPPING
# =============================================================================

# Maps use case error code strings → HTTP status codes
# This is how domain errors become meaningful HTTP responses
ERROR_CODE_TO_HTTP = {
    # 404 — Resource not found
    "NOT_FOUND": 404,
    "ORG_NOT_FOUND": 404,
    "ORGANIZATION_NOT_FOUND": 404,

    # 400 — Client sent bad data or invalid operation
    "VALIDATION_FAILED": 400,
    "INVALID_EDITION": 400,
    "INVALID_REGION": 400,
    "INVALID_ORG_TYPE": 400,
    "INVALID_STATE": 400,
    "INVALID_ACTION": 400,
    "CANNOT_SUSPEND": 400,

    # 409 — Conflict with current state
    "NAME_ALREADY_EXISTS": 409,
    "ALREADY_SUSPENDED": 409,
    "INVALID_STATE_TRANSITION": 409,
    "RETENTION_PERIOD_NOT_EXPIRED": 409,

    # 500 — Server-side failure
    "PERSISTENCE_FAILED": 500,
    "PERSISTENCE_ERROR": 500,
    "INTERNAL_ERROR": 500,
    "EVENT_PUBLISH_FAILED": 500,
    "EVALUATION_FAILED": 500,
}


def map_error_to_http(error_code, errors: List[str]) -> HTTPException:
    """
    Convert a use case error into an HTTPException.
    
    Use cases return error codes as enums (e.g., CreateOrganizationError.VALIDATION_FAILED).
    This function extracts the string value and maps it to an HTTP status code.
    
    Args:
        error_code: The error enum from the use case response (has .value attribute)
        errors: List of human-readable error messages
        
    Returns:
        HTTPException ready to be raised in the route handler
    """
    code_str = error_code.value if hasattr(error_code, "value") else str(error_code)
    status_code = ERROR_CODE_TO_HTTP.get(code_str, 500)
    return HTTPException(status_code=status_code, detail=errors)


# =============================================================================
# RESPONSE MAPPER
# =============================================================================

def map_org_to_response(org: Organization) -> TenantResponse:
    """
    Map a domain Organization object to a TenantResponse API schema.
    
    This is the bridge between the domain layer and the API layer.
    Domain objects use enums (OrganizationStatus.ACTIVE), but the API
    returns plain strings ("active"). This function handles that conversion.
    
    Used by: create_tenant, get_tenant, update_tenant, list_tenants
    
    Args:
        org: Domain Organization object from use case or repository
        
    Returns:
        TenantResponse Pydantic model ready for JSON serialization
    """
    return TenantResponse(
        id=org.id,
        org_id=org.org_id,
        name=org.name,
        status=org.status.value if hasattr(org.status, "value") else str(org.status),
        edition=org.edition.value if hasattr(org.edition, "value") else str(org.edition),
        region=org.region.value if hasattr(org.region, "value") else str(org.region),
        org_type=org.org_type.value if hasattr(org.org_type, "value") else str(org.org_type),
        is_trial=org.is_trial() if callable(getattr(org, "is_trial", None)) else False,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


def get_get_events_use_case(
    session: Session = Depends(get_db_session),
) -> GetTenantEventsUseCase:
    """Build GetTenantEventsUseCase with repository."""
    repo = OrganizationRepository(session)
    return GetTenantEventsUseCase(repository=repo)


def get_get_usage_use_case(
    session: Session = Depends(get_db_session),
) -> GetTenantUsageUseCase:
    """Build GetTenantUsageUseCase with repository."""
    repo = OrganizationRepository(session)
    return GetTenantUsageUseCase(repository=repo)
