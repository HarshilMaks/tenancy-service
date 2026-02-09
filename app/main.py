"""
Tenancy Service - Production-Grade FastAPI Application
======================================================

Main application entry point for the tenancy microservice.
This service handles organization (tenant) management for the platform.

Features:
    - Organization CRUD operations
    - Subscription and billing management
    - Policy enforcement
    - Trial management
    - Comprehensive observability
    - Health checks for Kubernetes

Architecture:
    - Clean Architecture / Hexagonal Architecture
    - Domain-Driven Design
    - CQRS pattern for complex queries
    - Event-driven architecture
    - Repository pattern for data access

Author: Platform Engineering Team
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import time

# Infrastructure imports
from infrastructure.config import get_settings
from infrastructure.database import DatabaseManager, get_db_session
from infrastructure.observability import (
    StructuredLogger,
    TracingMiddleware,
    MetricsMiddleware,
    get_health_checker,
    HealthStatus,
)

# Middleware imports
from app.middleware import RateLimitMiddleware

# API routes
from app.api.health import router as health_router
from app.api.tenants import router as tenants_router
from app.api.organizations import router as organizations_router
from app.api.users import router as user_context_router
from app.api.context import router as context_router

# Setup
settings = get_settings()
logger = StructuredLogger(__name__)


# =============================================================================
# APPLICATION LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown operations including:
    - Database connection initialization
    - Observability setup
    - Background task startup
    - Graceful shutdown
    """
    logger.info("Starting tenancy service", version="1.0.0")
    
    # Startup
    try:
        # Initialize database
        db_manager = DatabaseManager(settings.database)
        # Trigger initialization by accessing the engine property
        _ = db_manager.engine
        logger.info("Database initialized successfully")
        
        # Get health checker (already initialized)
        health_checker = get_health_checker()
        logger.info("Health checks initialized")
        
        # Initialize metrics collection
        logger.info("Observability initialized")
        
        logger.info("Tenancy service started successfully")
        
        yield
        
    except Exception as e:
        logger.exception("Failed to start tenancy service", error=str(e))
        raise
    
    # Shutdown
    logger.info("Shutting down tenancy service")
    try:
        # Cleanup database connections
        if 'db_manager' in locals() and db_manager:
            if hasattr(db_manager, 'close'):
                result = db_manager.close()
                if result is not None:
                    await result
            logger.info("Database connections closed")
        
        # Stop background tasks
        logger.info("Background tasks stopped")
        
        logger.info("Tenancy service shutdown complete")
        
    except Exception as e:
        logger.exception("Error during shutdown", error=str(e))


# =============================================================================
# APPLICATION SETUP
# =============================================================================

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Tenancy Service",
        description="Multi-tenant organization management service",
        version="1.0.0",
        docs_url="/docs" if settings.service.debug else None,
        redoc_url="/redoc" if settings.service.debug else None,
        openapi_url="/openapi.json" if settings.service.debug else None,
        lifespan=lifespan,
    )
    
    # ==========================================================================
    # MIDDLEWARE (Order matters!)
    # ==========================================================================
    
    # Rate limiting (first - protects against DoS)
    if settings.service.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_window=settings.service.rate_limit_requests,
            window_seconds=settings.service.rate_limit_window,
        )
    
    # Security middleware
    if settings.service.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.service.allowed_hosts,
        )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.service.cors_origins_list,
        allow_credentials=settings.service.cors_allow_credentials,
        allow_methods=settings.service.cors_allow_methods_list,
        allow_headers=settings.service.cors_allow_headers_list,
        max_age=settings.service.cors_max_age,
    )
    
    # Observability middleware
    app.add_middleware(TracingMiddleware)
    app.add_middleware(MetricsMiddleware)
    
    # Custom middleware for request correlation
    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next):
        """Add correlation ID to all requests."""
        start_time = time.perf_counter()
        
        # Get or generate correlation ID
        correlation_id = (
            request.headers.get("x-correlation-id") or
            f"req-{int(time.time() * 1000000) % 1000000:06d}"
        )
        
        # Add to request state
        request.state.correlation_id = correlation_id
        
        # Process request
        response = await call_next(request)
        
        # Add timing and correlation headers to response
        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["x-correlation-id"] = correlation_id
        response.headers["x-response-time"] = f"{duration_ms:.2f}ms"
        
        return response
    
    # ==========================================================================
    # EXCEPTION HANDLERS
    # ==========================================================================
    
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle value errors as bad requests."""
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')
        
        logger.warning(
            "Value error in request",
            path=request.url.path,
            error=str(exc),
            correlation_id=correlation_id,
        )
        
        # Show error message in development, hide in production
        message = str(exc) if settings.service.debug else "Invalid request"
        
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid request",
                "message": message,
                "correlation_id": correlation_id,
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        correlation_id = getattr(request.state, 'correlation_id', 'unknown')
        
        logger.exception(
            "Unexpected error in request",
            path=request.url.path,
            error=str(exc),
            correlation_id=correlation_id,
        )
        
        # Show error details in development, hide in production
        if settings.service.debug:
            message = str(exc)
            error_type = type(exc).__name__
        else:
            message = "An unexpected error occurred"
            error_type = "Internal Server Error"
        
        return JSONResponse(
            status_code=500,
            content={
                "error": error_type,
                "message": message,
                "correlation_id": correlation_id,
            }
        )
    
    # ==========================================================================
    # ROUTES
    # ==========================================================================
    
    # Health & Monitoring
    app.include_router(health_router, prefix="/api/v1")
    
    # Tenants (includes lifecycle, settings, policy, events)
    app.include_router(tenants_router, prefix="/api/v1")
    
    # Organizations (includes members)
    app.include_router(organizations_router, prefix="/api/v1")
    
    # Users (context management)
    app.include_router(user_context_router, prefix="/api/v1")
    
    # Context Resolution
    app.include_router(context_router, prefix="/api/v1")
    
    # Trial Management
    from app.api.trials.routes import router as trials_router
    app.include_router(trials_router)
    
    # Cancellation Workflow
    from app.api.cancellations.routes import router as cancellations_router
    app.include_router(cancellations_router)
    
    # Feature Gating
    from app.api.features.routes import router as features_router
    app.include_router(features_router)
    
    # Compliance
    from app.api.compliance.routes import router as compliance_router
    app.include_router(compliance_router)
    
    # Regional Settings
    from app.api.regions.routes import router as regions_router
    app.include_router(regions_router)
    
    # Onboarding
    from app.api.onboarding.routes import router as onboarding_router
    app.include_router(onboarding_router)
    
    # Migrations
    from app.api.migrations.routes import router as migrations_router
    app.include_router(migrations_router)
    
    # Data Retention
    from app.api.retention.routes import router as retention_router
    app.include_router(retention_router)
    
    # Root endpoint
    @app.get("/", tags=["Info"])
    async def root():
        """
        Service information endpoint.
        
        Returns basic service information and available endpoints.
        """
        return {
            "service": "tenancy",
            "version": "1.0.0",
            "description": "Multi-tenant organization management service",
            "endpoints": {
                "docs": "/docs",
                "health": "/health",
                "metrics": "/metrics",
                "api": "/api/v1",
            }
        }
    
    logger.info(
        "FastAPI application configured",
        debug=settings.service.debug,
        cors_origins=settings.service.cors_origins,
    )
    
    return app


# Create application instance
app = create_app()


# =============================================================================
# DEVELOPMENT SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting development server")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.service.debug,
        log_level="info" if settings.service.debug else "warning",
        access_log=settings.service.debug,
    )