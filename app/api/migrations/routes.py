"""Migration workflow endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import logging

from infrastructure.persistence.tenant_repository import OrganizationRepository, OrganizationNotFoundError
from app.dependencies.providers import get_organization_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/migrations", tags=["Migrations"])


class MigrationRequest(BaseModel):
    org_id: str
    target_region: str
    target_edition: Optional[str] = None


class MigrationResponse(BaseModel):
    org_id: str
    status: str
    started_at: datetime
    estimated_completion: datetime


@router.post("", response_model=MigrationResponse)
async def start_migration(
    request: MigrationRequest,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Start organization migration."""
    try:
        org = repo.get_by_org_id(request.org_id)
        
        # Log without exposing sensitive data
        logger.info(f"Migration started for organization", extra={"org_id": request.org_id})
        
        # Update organization status to migrating
        org.status = "migrating"
        org.migration_target_region = request.target_region
        if request.target_edition:
            org.migration_target_edition = request.target_edition
        
        saved_org = repo.save(org)
        
        return {
            "org_id": saved_org.org_id,
            "status": "migrating",
            "started_at": datetime.now(timezone.utc),
            "estimated_completion": datetime.now(timezone.utc),
        }
    except OrganizationNotFoundError:
        logger.warning(f"Organization not found for migration", extra={"org_id": request.org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )


@router.get("/{org_id}", response_model=MigrationResponse)
async def get_migration_status(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get migration status."""
    try:
        org = repo.get_by_org_id(org_id)
        
        logger.info("Migration status retrieved", extra={"org_id": org_id})
        
        return {
            "org_id": org.org_id,
            "status": org.status,
            "started_at": org.created_at,
            "estimated_completion": org.updated_at,
        }
    except OrganizationNotFoundError:
        logger.warning("Organization not found", extra={"org_id": org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )


@router.post("/{org_id}/complete", response_model=dict)
async def complete_migration(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Complete migration."""
    try:
        org = repo.get_by_org_id(org_id)
        
        logger.info("Migration completed", extra={"org_id": org_id})
        
        org.status = "active"
        org.migration_target_region = None
        org.migration_target_edition = None
        
        repo.save(org)
        
        return {"org_id": org_id, "status": "migration_complete"}
    except OrganizationNotFoundError:
        logger.warning("Organization not found", extra={"org_id": org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )


@router.post("/{org_id}/rollback", response_model=dict)
async def rollback_migration(
    org_id: str,
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Rollback migration."""
    try:
        org = repo.get_by_org_id(org_id)
        
        logger.info("Migration rolled back", extra={"org_id": org_id})
        
        org.status = "active"
        org.migration_target_region = None
        org.migration_target_edition = None
        
        repo.save(org)
        
        return {"org_id": org_id, "status": "migration_rolled_back"}
    except OrganizationNotFoundError:
        logger.warning("Organization not found", extra={"org_id": org_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization not found"
        )
