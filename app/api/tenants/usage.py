"""
Tenant Usage Routes — Usage Metrics
===================================

Endpoint:
    GET /tenants/{id}/usage → GetTenantUsageUseCase
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from typing import Optional

from app.business.use_cases.get_usage import (
    GetTenantUsageUseCase,
    GetTenantUsageRequest,
)
from infrastructure.persistence.tenant_repository import (
    OrganizationRepository,
    OrganizationNotFoundError,
)
from app.dependencies.providers import (
    get_organization_repository,
    get_get_usage_use_case,
)

router = APIRouter(prefix="/tenants/{tenant_id}/usage", tags=["Tenant Usage"])


@router.get("")
async def get_tenant_usage(
    tenant_id: UUID,
    period: str = "current",
    use_case: GetTenantUsageUseCase = Depends(get_get_usage_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get usage metrics for a tenant."""
    
    # Look up org to get org_id
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    
    # Map to DTO
    request_dto = GetTenantUsageRequest(
        org_id=org.org_id,
        period=period,
    )
    
    response = use_case.execute(request_dto)
    
    if not response.success:
        raise HTTPException(status_code=400, detail=response.errors)
    
    return {
        "org_id": response.org_id,
        "period": response.period,
        "metrics": [
            {
                "metric_name": m.metric_name,
                "value": m.value,
                "limit": m.limit,
                "unit": m.unit,
            }
            for m in response.metrics
        ],
    }
