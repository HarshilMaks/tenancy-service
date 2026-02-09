"""
Organization Members Routes

Endpoints:
    POST   /orgs/{org_id}/members
    GET    /orgs/{org_id}/members
    DELETE /orgs/{org_id}/members/{user_id}
"""

from fastapi import APIRouter, status
from uuid import UUID
from typing import List

from app.schemas.v1.requests_responses import MemberCreate, MemberResponse

router = APIRouter(prefix="/orgs/{org_id}/members", tags=["Org Members"])


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_org_member(org_id: UUID, member: MemberCreate):
    """Add a member to an organization"""
    pass


@router.get("", response_model=List[MemberResponse])
async def list_org_members(org_id: UUID, skip: int = 0, limit: int = 10):
    """List all members of an organization"""
    pass


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_org_member(org_id: UUID, user_id: UUID):
    """Remove a member from an organization"""
    pass
