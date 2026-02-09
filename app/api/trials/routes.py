"""Trial management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

router = APIRouter(prefix="/api/v1/trials", tags=["Trials"])


class TrialResponse(BaseModel):
    org_id: str
    trial_started_at: datetime
    trial_ends_at: datetime
    days_remaining: int
    is_active: bool


class TrialExtendRequest(BaseModel):
    org_id: str
    days: int = 7


@router.get("/{org_id}", response_model=TrialResponse)
async def get_trial(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get trial information for organization."""
    try:
        org = repo.get_by_org_id(org_id)
        
        trial_started_at = org.trial_started_at or datetime.now(timezone.utc)
        trial_ends_at = org.trial_ends_at or (datetime.now(timezone.utc) + timedelta(days=14))
        
        days_remaining = max(0, (trial_ends_at - datetime.now(timezone.utc)).days)
        is_active = trial_ends_at > datetime.now(timezone.utc)
        
        return {
            "org_id": org.org_id,
            "trial_started_at": trial_started_at,
            "trial_ends_at": trial_ends_at,
            "days_remaining": days_remaining,
            "is_active": is_active,
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.post("/{org_id}/extend", response_model=TrialResponse)
async def extend_trial(
    org_id: str,
    request: TrialExtendRequest,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Extend trial period."""
    try:
        org = repo.get_by_org_id(org_id)
        
        # Extend trial end date
        current_trial_end = org.trial_ends_at or datetime.now(timezone.utc)
        org.trial_ends_at = current_trial_end + timedelta(days=request.days)
        
        saved_org = repo.save(org)
        
        trial_started_at = saved_org.trial_started_at or datetime.now(timezone.utc)
        trial_ends_at = saved_org.trial_ends_at
        
        days_remaining = max(0, (trial_ends_at - datetime.now(timezone.utc)).days)
        
        return {
            "org_id": saved_org.org_id,
            "trial_started_at": trial_started_at,
            "trial_ends_at": trial_ends_at,
            "days_remaining": days_remaining,
            "is_active": True,
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.post("/{org_id}/convert", response_model=dict)
async def convert_trial_to_paid(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Convert trial to paid subscription."""
    try:
        org = repo.get_by_org_id(org_id)
        
        # Update status from trial to active
        org.status = "active"
        org.trial_ended_at = datetime.now(timezone.utc)
        
        repo.save(org)
        
        return {"org_id": org_id, "status": "converted", "message": "Trial converted to paid"}
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )
