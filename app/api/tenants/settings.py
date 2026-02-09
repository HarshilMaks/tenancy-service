"""
Tenant Settings Routes — Not Implemented Yet
=============================================

These endpoints will manage tenant configuration (region, compliance, domain).
Currently returns 501 until the settings use cases are built.

Endpoints:
    GET    /tenants/{id}/settings → 501
    PATCH  /tenants/{id}/settings → 501
"""

from fastapi import APIRouter, HTTPException
from uuid import UUID

from app.schemas.v1.requests_responses import TenantSettingsUpdate, TenantSettingsResponse

router = APIRouter(prefix="/tenants/{tenant_id}/settings", tags=["Tenant Settings"])


@router.get("", response_model=TenantSettingsResponse)
async def get_tenant_settings(tenant_id: UUID):
    """Get tenant settings (not implemented)."""
    raise HTTPException(status_code=501, detail="Get tenant settings not implemented")


@router.patch("", response_model=TenantSettingsResponse)
async def update_tenant_settings(tenant_id: UUID, settings: TenantSettingsUpdate):
    """Update tenant settings (not implemented)."""
    raise HTTPException(status_code=501, detail="Update tenant settings not implemented")
