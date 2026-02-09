"""Tenants API - Complete tenant management"""
from fastapi import APIRouter
from .routes import router as routes_router
from .lifecycle import router as lifecycle_router
from .settings import router as settings_router
from .policy import router as policy_router
from .events import router as events_router
from .usage import router as usage_router

# Combine all tenant routers
router = APIRouter()
router.include_router(routes_router)
router.include_router(lifecycle_router)
router.include_router(settings_router)
router.include_router(policy_router)
router.include_router(events_router)
router.include_router(usage_router)

__all__ = ["router"]
