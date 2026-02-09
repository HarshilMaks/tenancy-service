"""
Context Resolution Routes

Endpoints:
    POST   /context/resolve
"""

from fastapi import APIRouter
from uuid import UUID

from app.schemas.v1.requests_responses import ContextResolveRequest, ContextResolveResponse

router = APIRouter(prefix="/context", tags=["Context Resolution"])


@router.post("/resolve", response_model=ContextResolveResponse)
async def resolve_context(request: ContextResolveRequest):
    """Resolve the context for a user request"""
    pass
