"""Onboarding workflow endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])

ONBOARDING_STEPS = [
    "profile_setup",
    "team_invite",
    "integration_setup",
    "first_transaction",
]


class OnboardingStep(BaseModel):
    step: str
    completed: bool
    completed_at: Optional[datetime] = None


class OnboardingResponse(BaseModel):
    org_id: str
    steps: List[OnboardingStep]
    progress: int


@router.get("/{org_id}", response_model=OnboardingResponse)
async def get_onboarding_status(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get onboarding status."""
    try:
        org = repo.get_by_org_id(org_id)
        
        # Get onboarding progress from metadata
        onboarding_data = org.metadata.get("onboarding", {}) if org.metadata else {}
        completed_steps = onboarding_data.get("completed_steps", [])
        
        steps = []
        for step in ONBOARDING_STEPS:
            step_data = onboarding_data.get(f"{step}_completed_at")
            steps.append({
                "step": step,
                "completed": step in completed_steps,
                "completed_at": step_data if step_data else None,
            })
        
        progress = int((len(completed_steps) / len(ONBOARDING_STEPS)) * 100)
        
        return {
            "org_id": org.org_id,
            "steps": steps,
            "progress": progress,
        }
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.post("/{org_id}/{step}/complete", response_model=dict)
async def complete_onboarding_step(
    org_id: str,
    step: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Mark onboarding step as complete."""
    if step not in ONBOARDING_STEPS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid onboarding step: {step}"
        )
    
    try:
        org = repo.get_by_org_id(org_id)
        
        if not org.metadata:
            org.metadata = {}
        
        if "onboarding" not in org.metadata:
            org.metadata["onboarding"] = {"completed_steps": []}
        
        if step not in org.metadata["onboarding"]["completed_steps"]:
            org.metadata["onboarding"]["completed_steps"].append(step)
            org.metadata["onboarding"][f"{step}_completed_at"] = datetime.now(timezone.utc).isoformat()
        
        repo.save(org)
        
        return {"org_id": org_id, "step": step, "status": "completed"}
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )


@router.post("/{org_id}/complete", response_model=dict)
async def complete_onboarding(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Mark entire onboarding as complete."""
    try:
        org = repo.get_by_org_id(org_id)
        
        if not org.metadata:
            org.metadata = {}
        
        if "onboarding" not in org.metadata:
            org.metadata["onboarding"] = {}
        
        org.metadata["onboarding"]["completed_steps"] = ONBOARDING_STEPS.copy()
        org.metadata["onboarding"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        for step in ONBOARDING_STEPS:
            org.metadata["onboarding"][f"{step}_completed_at"] = datetime.now(timezone.utc).isoformat()
        
        repo.save(org)
        
        return {"org_id": org_id, "status": "onboarding_complete"}
    except OrganizationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )
