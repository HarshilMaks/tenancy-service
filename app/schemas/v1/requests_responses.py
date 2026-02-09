"""
API Schemas - Pydantic Models for Request/Response Validation
==============================================================

Centralized schemas for all API endpoints, organized by resource.
Aligned with docs/ENDPOINTS.md and domain DTOs in use case layer.
"""

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any


# =============================================================================
# TENANTS - Core Schemas
# =============================================================================

class TenantCreate(BaseModel):
    """Request schema for creating a tenant (POST /tenants)"""
    name: str = Field(
        ..., min_length=1, max_length=255,
        description="Tenant display name",
        examples=["Acme Corporation"],
    )
    edition: str = Field(
        ...,
        description="Subscription tier (free, essentials, professional, enterprise, unlimited)",
        examples=["professional"],
    )
    region: str = Field(
        ...,
        description="Primary data region",
        examples=["us-east-1"],
    )
    org_type: str = Field(
        default="production",
        description="Organization type (production, sandbox, developer)",
        examples=["production"],
    )
    created_by_email: Optional[str] = Field(
        None,
        description="Email of the user creating the tenant",
    )
    billing_email: Optional[str] = Field(
        None,
        description="Billing contact email",
    )
    start_trial: bool = Field(
        default=True,
        description="Whether to start a trial period",
    )
    trial_days: int = Field(
        default=14, ge=1, le=365,
        description="Trial duration in days",
    )


class TenantUpdate(BaseModel):
    """Request schema for updating a tenant (PATCH /tenants/{id})"""
    name: Optional[str] = Field(
        None, min_length=1, max_length=255,
        description="Tenant display name",
    )
    edition: Optional[str] = Field(
        None,
        description="Subscription tier",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom metadata key-value pairs",
    )


class TenantResponse(BaseModel):
    """Response schema for tenant details"""
    id: UUID = Field(..., description="Internal UUID")
    org_id: str = Field(..., description="External organization ID (ORG-XXXXXXXX)")
    name: str = Field(..., description="Tenant display name")
    status: str = Field(..., description="Current lifecycle status")
    edition: str = Field(..., description="Subscription tier")
    region: str = Field(..., description="Primary data region")
    org_type: str = Field(..., description="Organization type")
    is_trial: bool = Field(..., description="Whether tenant is in trial period")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class TenantListResponse(BaseModel):
    """Paginated list response for tenants (GET /tenants)"""
    items: List[TenantResponse] = Field(..., description="List of tenants")
    total: int = Field(..., description="Total number of matching tenants")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum items per page")


class DeleteResponse(BaseModel):
    """Response schema for tenant deletion (DELETE /tenants/{id})"""
    success: bool = Field(..., description="Whether deletion succeeded")
    message: str = Field(..., description="Result message")


# =============================================================================
# TENANTS - Lifecycle Schemas
# =============================================================================

class ActivateRequest(BaseModel):
    """Request schema for activating a tenant (POST /tenants/{id}/activate)"""
    pass


class SuspendRequest(BaseModel):
    """Request schema for suspending a tenant (POST /tenants/{id}/suspend)"""
    reason: str = Field(
        ..., max_length=500,
        description="Reason for suspension",
        examples=["payment_failure", "policy_violation"],
    )
    suspension_period: Optional[int] = Field(
        None, ge=1,
        description="Suspension period in days",
    )
    notify_admins: bool = Field(
        default=True,
        description="Whether to notify organization admins",
    )


class ResumeRequest(BaseModel):
    """Request schema for resuming a tenant (POST /tenants/{id}/resume)"""
    pass


class TerminateRequest(BaseModel):
    """Request schema for terminating a tenant (POST /tenants/{id}/terminate)"""
    reason: str = Field(
        ..., max_length=500,
        description="Reason for termination",
    )
    data_retention_days: Optional[int] = Field(
        None, ge=0,
        description="Days to retain data after termination",
    )


class ActivateResponse(BaseModel):
    """Response schema for tenant activation"""
    org_id: str = Field(..., description="External organization ID")
    status: str = Field(..., description="New status after activation")
    activated_at: datetime = Field(..., description="Activation timestamp")


class SuspendResponse(BaseModel):
    """Response schema for tenant suspension"""
    org_id: str = Field(..., description="External organization ID")
    status: str = Field(..., description="New status after suspension")
    suspended_at: datetime = Field(..., description="Suspension timestamp")
    suspended_reason: str = Field(..., description="Reason for suspension")


class ResumeResponse(BaseModel):
    """Response schema for tenant resumption"""
    org_id: str = Field(..., description="External organization ID")
    status: str = Field(..., description="New status after resumption")
    resumed_at: datetime = Field(..., description="Resumption timestamp")


class TerminateResponse(BaseModel):
    """Response schema for tenant termination"""
    org_id: str = Field(..., description="External organization ID")
    status: str = Field(..., description="New status after termination")
    terminated_at: datetime = Field(..., description="Termination timestamp")


# =============================================================================
# TENANTS - Settings Schemas
# =============================================================================

class TenantSettingsUpdate(BaseModel):
    """Request schema for updating tenant settings (PATCH /tenants/{id}/settings)"""
    primary_region: Optional[str] = Field(
        None,
        description="Primary data region",
    )
    allowed_regions: Optional[List[str]] = Field(
        None,
        description="List of allowed data regions",
    )
    compliance_flags: Optional[Dict[str, bool]] = Field(
        None,
        description="Compliance flags (e.g., gdpr, hipaa)",
    )
    custom_domain: Optional[str] = Field(
        None,
        description="Custom domain for the tenant",
    )


class TenantSettingsResponse(BaseModel):
    """Response schema for tenant settings (GET/PATCH /tenants/{id}/settings)"""
    primary_region: str = Field(..., description="Primary data region")
    allowed_regions: List[str] = Field(..., description="List of allowed data regions")
    compliance_flags: Dict[str, bool] = Field(..., description="Compliance flags")
    data_isolation_mode: str = Field(..., description="Data isolation mode (logical, physical)")
    custom_domain: Optional[str] = Field(None, description="Custom domain")
    updated_at: Optional[datetime] = Field(None, description="Last settings update timestamp")


# =============================================================================
# TENANTS - Region & Residency Schemas
# =============================================================================

class RegionResponse(BaseModel):
    """Response schema for tenant region info (GET /tenants/{id}/region)"""
    primary_region: str = Field(..., description="Primary data region")
    allowed_regions: List[str] = Field(..., description="Allowed data regions")
    data_residency_requirement: str = Field(..., description="Data residency requirement (e.g., US_ONLY)")
    compliance_zones: List[str] = Field(..., description="Compliance zones (e.g., FedRAMP, SOC2)")


class RegionValidateRequest(BaseModel):
    """Request schema for region validation (POST /tenants/{id}/region/validate)"""
    region: str = Field(
        ...,
        description="Region to validate",
        examples=["eu-west-1"],
    )


class RegionValidateResponse(BaseModel):
    """Response schema for region validation"""
    valid: bool = Field(..., description="Whether the region is allowed")
    reason: Optional[str] = Field(None, description="Explanation of the validation result")


# =============================================================================
# TENANTS - Policy Schemas
# =============================================================================

class PolicyEvaluationRequest(BaseModel):
    """Request schema for policy evaluation (POST /tenants/{id}/policy/evaluate)"""
    action: str = Field(
        ...,
        description="Action to evaluate",
        examples=["read:data", "create_workflow"],
    )
    resource: str = Field(
        ...,
        description="Resource being accessed",
        examples=["dataset:xyz"],
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional context for policy evaluation (user_id, ip, etc.)",
    )


class PolicyEvaluationResponse(BaseModel):
    """Response schema for policy evaluation"""
    allow: bool = Field(..., description="Whether the action is allowed")
    reason: Optional[str] = Field(None, description="Explanation of the decision")
    violations: List[str] = Field(
        default_factory=list,
        description="List of policy violations if denied",
    )


# =============================================================================
# TENANTS - Usage Schemas
# =============================================================================

class UsageMetrics(BaseModel):
    """Usage metrics for a tenant"""
    api_calls: int = Field(..., description="Number of API calls in the period")
    storage_gb: float = Field(..., description="Storage used in GB")
    active_users: int = Field(..., description="Number of active users")
    data_processed_gb: float = Field(..., description="Data processed in GB")


class UsageLimits(BaseModel):
    """Usage limits for a tenant based on edition"""
    api_calls_limit: int = Field(..., description="Maximum API calls allowed")
    storage_limit_gb: float = Field(..., description="Maximum storage in GB")
    users_limit: int = Field(..., description="Maximum number of users")


class UsagePercentage(BaseModel):
    """Usage as percentage of limits"""
    api_calls: float = Field(..., description="API calls usage percentage")
    storage: float = Field(..., description="Storage usage percentage")
    users: float = Field(..., description="Users usage percentage")


class UsageResponse(BaseModel):
    """Response schema for tenant usage (GET /tenants/{id}/usage)"""
    tenant_id: str = Field(..., description="External organization ID")
    period: str = Field(..., description="Usage period (e.g., 2026-02)")
    metrics: UsageMetrics = Field(..., description="Current usage metrics")
    limits: UsageLimits = Field(..., description="Edition-based limits")
    usage_percentage: UsagePercentage = Field(..., description="Usage as percentage of limits")


# =============================================================================
# TENANTS - Events Schemas
# =============================================================================

class EventDetail(BaseModel):
    """Schema for a single tenant event"""
    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Event type (e.g., organization.created)")
    timestamp: datetime = Field(..., description="When the event occurred")
    actor_id: Optional[str] = Field(None, description="ID of the user/system that triggered the event")
    details: Optional[Dict[str, Any]] = Field(None, description="Event payload details")


class EventListResponse(BaseModel):
    """Paginated list response for tenant events (GET /tenants/{id}/events)"""
    items: List[EventDetail] = Field(..., description="List of events")
    total: int = Field(..., description="Total number of matching events")
    limit: int = Field(..., description="Maximum items per page")
    offset: int = Field(..., description="Number of items skipped")


# =============================================================================
# ORGANIZATIONS - Schemas (kept as-is, out of scope)
# =============================================================================

class OrgCreate(BaseModel):
    """Request schema for creating an organization"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class OrgUpdate(BaseModel):
    """Request schema for updating an organization"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class OrgResponse(BaseModel):
    """Response schema for organization details"""
    id: UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime


# Organization Members Schemas
class MemberCreate(BaseModel):
    """Request schema for adding organization member"""
    user_id: UUID
    role: str = Field(default="member", description="Member role")


class MemberResponse(BaseModel):
    """Response schema for organization member"""
    user_id: UUID
    role: str
    joined_at: datetime


# =============================================================================
# USERS - Schemas (kept as-is, out of scope)
# =============================================================================

class UserOrgResponse(BaseModel):
    """Response schema for user's organization"""
    org_id: UUID
    org_name: str
    role: str
    joined_at: datetime


class SelectOrgResponse(BaseModel):
    """Response schema for organization selection"""
    user_id: UUID
    selected_org_id: UUID
    timestamp: datetime


# =============================================================================
# CONTEXT - Schemas (kept as-is, out of scope)
# =============================================================================

class ContextResolveRequest(BaseModel):
    """Request schema for context resolution"""
    user_id: UUID
    org_id: Optional[UUID] = None
    resource_id: Optional[UUID] = None
    metadata: Optional[Dict[str, Any]] = None


class ContextResolveResponse(BaseModel):
    """Response schema for context resolution"""
    user_id: UUID
    org_id: UUID
    tenant_id: UUID
    permissions: List[str]
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# HEALTH - Schemas (kept as-is, out of scope)
# =============================================================================

class HealthResponse(BaseModel):
    """Response schema for health check"""
    status: str
    timestamp: str


class ReadinessResponse(BaseModel):
    """Response schema for readiness check"""
    status: str
    checks: Dict[str, str]


class MetricsResponse(BaseModel):
    """Response schema for metrics"""
    data: Dict[str, Any]
