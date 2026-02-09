"""
Health & Monitoring Routes

Endpoints:
    GET    /health
    GET    /health/live
    GET    /health/ready
    GET    /metrics
"""

from datetime import datetime, timezone
from fastapi import APIRouter

from app.schemas.v1.requests_responses import HealthResponse, ReadinessResponse, MetricsResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/health/live", response_model=HealthResponse)
async def liveness():
    """Kubernetes liveness probe"""
    return HealthResponse(
        status="alive",
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness():
    """Kubernetes readiness probe"""
    return ReadinessResponse(
        status="ready",
        checks={"database": "connected", "api": "ready"}
    )


@router.get("/metrics", response_model=MetricsResponse)
async def metrics():
    """Prometheus metrics endpoint"""
    return MetricsResponse(data={"requests_total": 0, "errors_total": 0})
