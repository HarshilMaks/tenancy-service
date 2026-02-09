"""Application Services - Shared service utilities

Contains shared services used across use cases such as:
  - Logging services
  - Caching services  
  - Notification services
"""
Each use case implements a single business operation.

Use Cases:
    - CreateOrganizationUseCase: Provisions new organizations
    - SuspendOrganizationUseCase: Suspends organizations
    - EnforcePolicyUseCase: Policy decision point

Architecture:
    - Use cases are stateless and thread-safe
    - Dependencies injected via constructor (ports pattern)
    - Request/Response DTOs for input/output
    - Domain objects for business logic
    - Events published for side effects

Example:
    >>> from services import (
    ...     CreateOrganizationUseCase,
    ...     CreateOrganizationRequest,
    ... )
    >>> 
    >>> use_case = CreateOrganizationUseCase(repo, publisher)
    >>> response = use_case.execute(
    ...     CreateOrganizationRequest(
    ...         name="Acme Corp",
    ...         edition="professional",
    ...         region="us-east-1",
    ...     )
    ... )

Author: Platform Engineering Team
"""

# Create organization
from services.create_tenant import (
    # Ports
    OrganizationRepository as CreateOrgRepository,
    EventPublisher as CreateOrgEventPublisher,
    IdGenerator,
    DefaultIdGenerator,
    
    # DTOs
    CreateOrganizationRequest,
    CreateOrganizationResponse,
    CreateOrganizationError,
    
    # Use case
    CreateOrganizationUseCase,
    
    # Convenience
    create_organization,
)

# Suspend organization
from services.suspend_tenant import (
    # Enums
    SuspensionReason,
    SuspensionError,
    
    # DTOs
    SuspendOrganizationRequest,
    SuspendOrganizationResponse,
    
    # Use case
    SuspendOrganizationUseCase,
    
    # Convenience
    suspend_organization,
    
    # Constants
    DEFAULT_GRACE_PERIODS,
)

# Enforce policy
from services.enforce_policy import (
    # Enums
    PolicyType,
    PolicyDecision,
    PolicyError,
    
    # DTOs
    PolicyContext,
    PolicyViolation,
    EnforcePolicyRequest,
    EnforcePolicyResponse,
    
    # Use case
    EnforcePolicyUseCase,
    
    # Convenience
    enforce_policy,
    check_feature_allowed,
    
    # Constants
    STATUS_RESTRICTIONS,
    EDITION_REQUIRED_ACTIONS,
    GDPR_REGIONS,
    CCPA_REGIONS,
)

# Get tenants list
from services.get_tenants import (
    # DTOs
    GetTenantsListRequest,
    GetTenantsListResponse,
    TenantListItem,
    
    # Use case
    GetTenantsListUseCase,
)

# Update tenant
from services.update_tenant import (
    # DTOs
    UpdateTenantRequest,
    UpdateTenantResponse,
    
    # Use case
    UpdateTenantUseCase,
)

# Re-export ports with unified names
OrganizationRepository = CreateOrgRepository
EventPublisher = CreateOrgEventPublisher

__all__ = [
    # === Create Organization ===
    "CreateOrganizationUseCase",
    "CreateOrganizationRequest",
    "CreateOrganizationResponse",
    "CreateOrganizationError",
    "create_organization",
    "IdGenerator",
    "DefaultIdGenerator",
    
    # === Suspend Organization ===
    "SuspendOrganizationUseCase",
    "SuspendOrganizationRequest",
    "SuspendOrganizationResponse",
    "SuspensionReason",
    "SuspensionError",
    "suspend_organization",
    "DEFAULT_GRACE_PERIODS",
    
    # === Enforce Policy ===
    "EnforcePolicyUseCase",
    "EnforcePolicyRequest",
    "EnforcePolicyResponse",
    "PolicyContext",
    "PolicyViolation",
    "PolicyType",
    "PolicyDecision",
    "PolicyError",
    "enforce_policy",
    "check_feature_allowed",
    "STATUS_RESTRICTIONS",
    "EDITION_REQUIRED_ACTIONS",
    "GDPR_REGIONS",
    "CCPA_REGIONS",
    
    # Get tenants list
    "GetTenantsListRequest",
    "GetTenantsListResponse",
    "TenantListItem",
    "GetTenantsListUseCase",
    
    # Update tenant
    "UpdateTenantRequest",
    "UpdateTenantResponse",
    "UpdateTenantUseCase",
    
    # === Shared Ports ===
    "OrganizationRepository",
    "EventPublisher",
]
