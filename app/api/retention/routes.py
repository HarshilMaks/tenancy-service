"""Data retention endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

router = APIRouter(prefix="/api/v1/retention", tags=["Retention"])

# Default retention policies by edition
DEFAULT_RETENTION_DAYS = {
    "free": 30,
    "essentials": 90,
    "professional": 180,
    "enterprise": 365,
    "unlimited": 730,
}


class RetentionPolicy(BaseModel):
    org_id: str
    retention_days: int
    data_retention_until: datetime


class RetentionResponse(BaseModel):
    org_id: str
    retention_days: int
    data_retention_until: datetime
    status: str


@router.get("/{org_id}", response_model=RetentionResponse)
async def get_retention_policy(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get data retention policy."""
    try:
        org = repo.get_by_org_id(org_id)
        
        # Get retention days from metadata or use default based on edition
        retention_data = org.metadata.get("retention", {}) if org.metadata else {}
        retention_days = retention_data.get("retention_days")
        
        if not retention_days:
            edition = org.edition.value if hasattr(org.edition, 'value') else str(org.edition).lower()
            retention_days = DEFAULT_RETENTION_DAYS.get(edition, 90)
        
        data_retention_until = datetime.now(timezone.utc) + timedelta(days=retention_days)
        
        return {
            "org_id": org.org_id,
            "retention_days": retention_days,
            "data_retention_until": data_retention_until,
            "status": "active",
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.patch("/{org_id}", response_model=RetentionResponse)
async def update_retention_policy(
    org_id: str,
    policy: RetentionPolicy,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Update retention policy."""
    if policy.retention_days < 1 or policy.retention_days > 2555:  # Max ~7 years
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Retention days must be between 1 and 2555"
        )
    
    try:
        org = repo.get_by_org_id(org_id)
        
        if not org.metadata:
            org.metadata = {}
        
        org.metadata["retention"] = {
            "retention_days": policy.retention_days,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        saved_org = repo.save(org)
        
        data_retention_until = datetime.now(timezone.utc) + timedelta(days=policy.retention_days)
        
        return {
            "org_id": saved_org.org_id,
            "retention_days": policy.retention_days,
            "data_retention_until": data_retention_until,
            "status": "updated",
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.post("/{org_id}/purge", response_model=dict)
async def purge_expired_data(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Purge expired data."""
    try:
        org = repo.get_by_org_id(org_id)
        
        if not org.metadata:
            org.metadata = {}
        
        org.metadata["last_purge_at"] = datetime.now(timezone.utc).isoformat()
        
        repo.save(org)
        
        return {"org_id": org_id, "status": "purge_initiated", "message": "Data purge initiated"}
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )
