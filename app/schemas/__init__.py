"""API Schemas - Request and Response Models

Organized by version:
  - v1: API v1 request/response schemas
"""

from .v1.requests_responses import (
    # Health
    HealthResponse,
    ReadinessResponse,
    MetricsResponse,
    # Tenants
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    # Lifecycle (actual names used by endpoints)
    ActivateRequest,
    ActivateResponse,
    SuspendRequest,
    SuspendResponse,
    ResumeRequest,
    ResumeResponse,
    TerminateRequest,
    TerminateResponse,
    # Settings
    TenantSettingsUpdate,
    TenantSettingsResponse,
    # Policy
    PolicyEvaluationRequest,
    PolicyEvaluationResponse,
    # Events
    EventDetail,
    # Organizations
    OrgCreate,
    OrgUpdate,
    OrgResponse,
    # Members
    MemberCreate,
    MemberResponse,
    # Users
    UserOrgResponse,
    SelectOrgResponse,
    # Context
    ContextResolveRequest,
    ContextResolveResponse,
)

__all__ = [
    # Health
    "HealthResponse",
    "ReadinessResponse",
    "MetricsResponse",
    # Tenants
    "TenantCreate",
    "TenantUpdate",
    "TenantResponse",
    # Lifecycle
    "ActivateRequest",
    "ActivateResponse",
    "SuspendRequest",
    "SuspendResponse",
    "ResumeRequest",
    "ResumeResponse",
    "TerminateRequest",
    "TerminateResponse",
    # Settings
    "TenantSettingsUpdate",
    "TenantSettingsResponse",
    # Policy
    "PolicyEvaluationRequest",
    "PolicyEvaluationResponse",
    # Events
    "EventDetail",
    # Organizations
    "OrgCreate",
    "OrgUpdate",
    "OrgResponse",
    # Members
    "MemberCreate",
    "MemberResponse",
    # Users
    "UserOrgResponse",
    "SelectOrgResponse",
    # Context
    "ContextResolveRequest",
    "ContextResolveResponse",
]
