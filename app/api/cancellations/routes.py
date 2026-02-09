"""Cancellation workflow endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import logging

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cancellations", tags=["Cancellations"])


class CancellationRequest(BaseModel):
    org_id: str
    reason: str
    feedback: Optional[str] = None


class CancellationResponse(BaseModel):
    org_id: str
    status: str
    cancellation_date: datetime
    effective_date: datetime


@router.post("", response_model=CancellationResponse)
async def request_cancellation(
    request: CancellationRequest,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Request organization cancellation."""
    try:
        org = repo.get_by_org_id(request.org_id)
        
        logger.info("Cancellation requested", extra={"org_id": request.org_id})
        
        org.status = "pending_cancellation"
        org.cancellation_reason = request.reason
        org.cancellation_feedback = request.feedback
        org.cancellation_requested_at = datetime.now(timezone.utc)
        
        saved_org = repo.save(org)
        
        return {
            "org_id": saved_org.org_id,
            "status": "pending_cancellation",
            "cancellation_date": datetime.now(timezone.utc),
            "effective_date": datetime.now(timezone.utc),
        }
    except OrganizationNotFoundError:
        logger.warning("Organization not found", extra={"org_id": request.org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )


@router.get("/{org_id}", response_model=CancellationResponse)
async def get_cancellation_status(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get cancellation status."""
    try:
        org = repo.get_by_org_id(org_id)
        
        logger.info("Cancellation status retrieved", extra={"org_id": org_id})
        
        return {
            "org_id": org.org_id,
            "status": org.status,
            "cancellation_date": org.cancellation_requested_at or datetime.now(timezone.utc),
            "effective_date": org.updated_at,
        }
    except OrganizationNotFoundError:
        logger.warning("Organization not found", extra={"org_id": org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )


@router.post("/{org_id}/confirm", response_model=dict)
async def confirm_cancellation(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Confirm cancellation."""
    try:
        org = repo.get_by_org_id(org_id)
        
        logger.info("Cancellation confirmed", extra={"org_id": org_id})
        
        org.status = "terminated"
        org.terminated_at = datetime.now(timezone.utc)
        
        repo.save(org)
        
        return {"org_id": org_id, "status": "cancelled", "message": "Cancellation confirmed"}
    except OrganizationNotFoundError:
        logger.warning("Organization not found", extra={"org_id": org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )


@router.post("/{org_id}/revert", response_model=dict)
async def revert_cancellation(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Revert pending cancellation."""
    try:
        org = repo.get_by_org_id(org_id)
        
        logger.info("Cancellation reverted", extra={"org_id": org_id})
        
        org.status = "active"
        org.cancellation_reason = None
        org.cancellation_feedback = None
        org.cancellation_requested_at = None
        
        repo.save(org)
        
        return {"org_id": org_id, "status": "active", "message": "Cancellation reverted"}
    except OrganizationNotFoundError:
        logger.warning("Organization not found", extra={"org_id": org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )
