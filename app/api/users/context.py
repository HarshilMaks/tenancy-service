"""
User Organization Context Routes

Endpoints:
    GET    /users/{user_id}/orgs
    POST   /users/{user_id}/orgs/{org_id}/select
"""

from fastapi import APIRouter
from uuid import UUID
from typing import List

from app.schemas.v1.requests_responses import UserOrgResponse, SelectOrgResponse

router = APIRouter(prefix="/users/{user_id}", tags=["User Context"])


@router.get("/orgs", response_model=List[UserOrgResponse])
async def get_user_orgs(user_id: UUID):
    """Get all organizations for a user"""
    pass


@router.post("/orgs/{org_id}/select", response_model=SelectOrgResponse)
async def select_user_org(user_id: UUID, org_id: UUID):
    """Set the user's current organization context"""
    pass
