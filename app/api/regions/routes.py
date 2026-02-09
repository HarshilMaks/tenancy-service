"""Regional settings endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Optional

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

router = APIRouter(prefix="/api/v1/regions", tags=["Regions"])

AVAILABLE_REGIONS = {
    "us-east-1": {"name": "US East", "timezone": "America/New_York"},
    "us-west-2": {"name": "US West", "timezone": "America/Los_Angeles"},
    "eu-west-1": {"name": "EU West", "timezone": "Europe/London"},
    "eu-central-1": {"name": "EU Central", "timezone": "Europe/Berlin"},
    "ap-south-1": {"name": "Asia Pacific South", "timezone": "Asia/Kolkata"},
    "ap-southeast-1": {"name": "Asia Pacific Southeast", "timezone": "Asia/Singapore"},
    "ap-northeast-1": {"name": "Asia Northeast", "timezone": "Asia/Tokyo"},
}


class RegionalSettings(BaseModel):
    org_id: str
    region: str
    timezone: str
    data_residency: str


@router.get("/{org_id}", response_model=RegionalSettings)
async def get_regional_settings(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get regional settings."""
    try:
        org = repo.get_by_org_id(org_id)
        
        region = org.region.value if hasattr(org.region, 'value') else str(org.region)
        region_code = region.lower().replace("_", "-")
        
        region_info = AVAILABLE_REGIONS.get(region_code, {})
        timezone = region_info.get("timezone", "UTC")
        
        return {
            "org_id": org.org_id,
            "region": region_code,
            "timezone": timezone,
            "data_residency": region_code.split("-")[0].upper(),
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.patch("/{org_id}", response_model=RegionalSettings)
async def update_regional_settings(
    org_id: str,
    settings: RegionalSettings,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Update regional settings."""
    if settings.region not in AVAILABLE_REGIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid region: {settings.region}"
        )
    
    try:
        org = repo.get_by_org_id(org_id)
        
        # Update region in metadata
        if not org.metadata:
            org.metadata = {}
        
        org.metadata["region_settings"] = {
            "region": settings.region,
            "timezone": settings.timezone,
            "data_residency": settings.data_residency,
        }
        
        repo.save(org)
        
        return settings
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.get("", response_model=Dict)
async def list_available_regions():
    """List available regions."""
    regions = [
        {
            "code": code,
            "name": info["name"],
            "timezone": info["timezone"]
        }
        for code, info in AVAILABLE_REGIONS.items()
    ]
    
    return {"regions": regions}
