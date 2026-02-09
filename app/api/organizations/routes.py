"""
Organizations Routes

Endpoints:
    POST   /orgs
    GET    /orgs/{org_id}
    PATCH  /orgs/{org_id}
    DELETE /orgs/{org_id}
"""

from fastapi import APIRouter, status
from uuid import UUID

from app.schemas.v1.requests_responses import OrgCreate, OrgUpdate, OrgResponse

router = APIRouter(prefix="/orgs", tags=["Organizations"])


@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_org(org: OrgCreate):
    """Create a new organization"""
    pass


@router.get("/{org_id}", response_model=OrgResponse)
async def get_org(org_id: UUID):
    """Get a specific organization"""
    pass


@router.patch("/{org_id}", response_model=OrgResponse)
async def update_org(org_id: UUID, org: OrgUpdate):
    """Update a specific organization"""
    pass


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(org_id: UUID):
    """Delete a specific organization"""
    pass
