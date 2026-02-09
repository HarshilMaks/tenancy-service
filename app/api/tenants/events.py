"""
Tenant Events Routes — Event Audit Trail
=========================================

Endpoint:
    GET /tenants/{id}/events → GetTenantEventsUseCase
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional

from app.schemas.v1.requests_responses import EventListResponse
from app.business.use_cases.get_events import (
    GetTenantEventsUseCase,
    GetTenantEventsRequest,
)
from infrastructure.persistence.tenant_repository import (
    OrganizationRepository,
    OrganizationNotFoundError,
)
from app.dependencies.providers import (
    get_organization_repository,
    get_get_events_use_case,
)

router = APIRouter(prefix="/tenants/{tenant_id}/events", tags=["Tenant Events"])


@router.get("", response_model=EventListResponse)
async def get_tenant_events(
    tenant_id: UUID,
    skip: int = 0,
    limit: int = 20,
    event_type: Optional[str] = None,
    use_case: GetTenantEventsUseCase = Depends(get_get_events_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get events for a tenant."""
    
    # Look up org to get org_id
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    
    # Map to DTO
    request_dto = GetTenantEventsRequest(
        org_id=org.org_id,
        skip=skip,
        limit=limit,
        event_type=event_type,
    )
    
    response = use_case.execute(request_dto)
    
    if not response.success:
        raise HTTPException(status_code=400, detail=response.errors)
    
    return EventListResponse(
        items=response.items,
        total=response.total,
        offset=response.skip,
        limit=response.limit,
    )
