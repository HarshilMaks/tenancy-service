"""
Tenant Lifecycle Routes — State Transition Endpoints
=====================================================

These endpoints change a tenant's lifecycle state.

Endpoints:
    POST /tenants/{id}/activate  → ActivateOrganizationUseCase
    POST /tenants/{id}/suspend   → SuspendOrganizationUseCase
    POST /tenants/{id}/resume    → ResumeOrganizationUseCase
    POST /tenants/{id}/terminate → TerminateOrganizationUseCase
    DELETE /tenants/{id}         → DeleteOrganizationUseCase
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from app.schemas.v1.requests_responses import (
    ActivateRequest,
    ActivateResponse,
    SuspendRequest,
    SuspendResponse,
    ResumeRequest,
    ResumeResponse,
    TerminateRequest,
    TerminateResponse,
)

from app.business.use_cases.suspend_tenant import (
    SuspendOrganizationUseCase,
    SuspendOrganizationRequest,
)

from app.business.use_cases.activate_tenant import (
    ActivateOrganizationUseCase,
    ActivateOrganizationRequest,
    ActivateOrganizationError,
)

from app.business.use_cases.resume_tenant import (
    ResumeOrganizationUseCase,
    ResumeOrganizationRequest,
    ResumeOrganizationError,
)

from app.business.use_cases.terminate_tenant import (
    TerminateOrganizationUseCase,
    TerminateOrganizationRequest,
    TerminateOrganizationError,
)

from app.business.use_cases.delete_tenant import (
    DeleteOrganizationUseCase,
    DeleteOrganizationRequest,
    DeleteOrganizationError,
)

from infrastructure.persistence.tenant_repository import (
    OrganizationRepository,
    OrganizationNotFoundError,
)

from app.dependencies.providers import (
    get_organization_repository,
    get_suspend_tenant_use_case,
    get_activate_tenant_use_case,
    get_resume_tenant_use_case,
    get_terminate_tenant_use_case,
    get_delete_tenant_use_case,
    map_error_to_http,
)

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["Tenant Lifecycle"])


@router.post("/activate", response_model=ActivateResponse)
async def activate_tenant(
    tenant_id: UUID,
    action: ActivateRequest,
    use_case: ActivateOrganizationUseCase = Depends(get_activate_tenant_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Activate a tenant."""
    
    # Look up the org to get the org_id string (e.g., "ORG-ABC12345")
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    
    # Map API schema → domain DTO
    request_dto = ActivateOrganizationRequest(
        org_id=org.org_id,
        activated_by=action.activated_by if hasattr(action, 'activated_by') else None,
    )
    
    response = use_case.execute(request_dto)
    
    if not response.success:
        raise map_error_to_http(response.error_code, response.errors)
    
    return ActivateResponse(
        org_id=response.org_id,
        status=response.new_status,
        activated_at=response.activated_at,
    )


@router.post("/suspend", response_model=SuspendResponse)
async def suspend_tenant(
    tenant_id: UUID,
    action: SuspendRequest,
    use_case: SuspendOrganizationUseCase = Depends(get_suspend_tenant_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Suspend a tenant."""

    # Look up the org to get the org_id string (e.g., "ORG-ABC12345")
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

    # Map API schema → domain DTO
    # Note: suspension_period (days) maps to grace_period_days in the domain
    request_dto = SuspendOrganizationRequest(
        org_id=org.org_id,
        reason=action.reason,
        notify_admins=action.notify_admins,
        grace_period_days=action.suspension_period,
    )

    response = use_case.execute(request_dto)

    if not response.success:
        raise map_error_to_http(response.error_code, response.errors)

    return SuspendResponse(
        org_id=response.org_id,
        status=response.new_status,
        suspended_at=response.suspended_at,
        suspended_reason=action.reason,
    )


@router.post("/resume", response_model=ResumeResponse)
async def resume_tenant(
    tenant_id: UUID,
    action: ResumeRequest,
    use_case: ResumeOrganizationUseCase = Depends(get_resume_tenant_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Resume a suspended tenant."""
    
    # Look up the org to get the org_id string (e.g., "ORG-ABC12345")
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    
    # Map API schema → domain DTO
    request_dto = ResumeOrganizationRequest(
        org_id=org.org_id,
        resumed_by=action.resumed_by if hasattr(action, 'resumed_by') else None,
    )
    
    response = use_case.execute(request_dto)
    
    if not response.success:
        raise map_error_to_http(response.error_code, response.errors)
    
    return ResumeResponse(
        org_id=response.org_id,
        status=response.new_status,
        resumed_at=response.resumed_at,
    )


@router.post("/terminate", response_model=TerminateResponse)
async def terminate_tenant(
    tenant_id: UUID,
    action: TerminateRequest,
    use_case: TerminateOrganizationUseCase = Depends(get_terminate_tenant_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Terminate a tenant."""
    
    # Look up the org to get the org_id string (e.g., "ORG-ABC12345")
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    
    # Map API schema → domain DTO
    request_dto = TerminateOrganizationRequest(
        org_id=org.org_id,
        reason=action.reason if hasattr(action, 'reason') else "Customer requested",
        data_retention_days=action.data_retention_days if hasattr(action, 'data_retention_days') else 90,
        terminated_by=action.terminated_by if hasattr(action, 'terminated_by') else None,
    )
    
    response = use_case.execute(request_dto)
    
    if not response.success:
        raise map_error_to_http(response.error_code, response.errors)
    
    return TerminateResponse(
        org_id=response.org_id,
        status=response.new_status,
        terminated_at=response.terminated_at,
        data_retention_until=response.data_retention_until,
    )


@router.delete("", status_code=200)
async def delete_tenant(
    tenant_id: UUID,
    use_case: DeleteOrganizationUseCase = Depends(get_delete_tenant_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Hard delete a terminated tenant (after retention period expires)."""
    
    # Look up the org to get the org_id string (e.g., "ORG-ABC12345")
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    
    # Map API schema → domain DTO
    request_dto = DeleteOrganizationRequest(
        org_id=org.org_id,
        deleted_by=None,
    )
    
    response = use_case.execute(request_dto)
    
    if not response.success:
        raise map_error_to_http(response.error_code, response.errors)
    
    return {
        "org_id": response.org_id,
        "message": response.message,
    }
