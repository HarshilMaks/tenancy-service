"""Organizations API - Complete organization management"""
from fastapi import APIRouter
from .routes import router as routes_router
from .members import router as members_router

# Combine all organization routers
router = APIRouter()
router.include_router(routes_router)
router.include_router(members_router)

__all__ = ["router"]
