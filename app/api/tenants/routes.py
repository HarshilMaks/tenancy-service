"""
Tenants Routes — Core CRUD Endpoints
=====================================

These are the main tenant endpoints. Each one:
1. Declares its dependencies via Depends() — FastAPI injects them automatically
2. Maps the API schema (Pydantic model) → domain DTO (dataclass)
3. Calls the use case's execute() method
4. Maps the domain response → API schema (Pydantic model)
5. Returns the response or raises HTTPException on error

Endpoints:
    POST   /tenants          → create_tenant (wired to CreateOrganizationUseCase)
    GET    /tenants           → list_tenants  (wired to GetTenantsListUseCase)
    GET    /tenants/{id}      → get_tenant    (wired to OrganizationRepository directly)
    PATCH  /tenants/{id}      → update_tenant (wired to UpdateTenantUseCase)
    DELETE /tenants/{id}      → delete_tenant (501 Not Implemented)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

from app.schemas.v1.requests_responses import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantListResponse,
    DeleteResponse,
)

# Use case imports — needed for type hints in Depends()
from app.business.use_cases.create_tenant import (
    CreateOrganizationUseCase,
    CreateOrganizationRequest,
)
from app.business.use_cases.get_tenants import (
    GetTenantsListUseCase,
    GetTenantsListRequest,
)
from app.business.use_cases.update_tenant import (
    UpdateTenantUseCase,
    UpdateTenantRequest,
)

# Infrastructure imports
from infrastructure.persistence.tenant_repository import (
    OrganizationRepository,
    OrganizationNotFoundError,
)

# Dependency providers — the factory functions that build our dependencies
from app.dependencies.providers import (
    get_organization_repository,
    get_create_tenant_use_case,
    get_get_tenants_use_case,
    get_update_tenant_use_case,
    map_error_to_http,
    map_org_to_response,
)

router = APIRouter(prefix="/tenants", tags=["Tenants"])


# =============================================================================
# POST /tenants — Create a new tenant
# =============================================================================

@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant: TenantCreate,
    # FastAPI sees Depends() and calls get_create_tenant_use_case() BEFORE
    # this function runs. The result (a fully built use case) is passed in.
    use_case: CreateOrganizationUseCase = Depends(get_create_tenant_use_case),
):
    """Create a new tenant organization."""

    # Step 1: Map API schema → domain DTO
    # The API schema (TenantCreate) is what the HTTP client sends.
    # The domain DTO (CreateOrganizationRequest) is what the use case expects.
    request_dto = CreateOrganizationRequest(
        name=tenant.name,
        edition=tenant.edition,
        region=tenant.region,
        org_type=tenant.org_type,
        created_by_email=tenant.created_by_email,
        billing_email=tenant.billing_email,
        start_trial=tenant.start_trial,
        trial_days=tenant.trial_days,
    )

    # Step 2: Execute the use case
    # This does: validate → create domain object → save to DB → publish events
    response = use_case.execute(request_dto)

    # Step 3: Check for errors
    if not response.success:
        raise map_error_to_http(response.error_code, response.errors)

    # Step 4: Map domain response → API schema
    return map_org_to_response(response.organization)


# =============================================================================
# GET /tenants — List tenants with pagination
# =============================================================================

@router.get("", response_model=TenantListResponse)
async def list_tenants(
    skip: int = 0,
    limit: int = 10,
    use_case: GetTenantsListUseCase = Depends(get_get_tenants_use_case),
):
    """List all tenants with pagination."""

    # Map query params → domain DTO
    request_dto = GetTenantsListRequest(skip=skip, limit=limit)

    response = use_case.execute(request_dto)

    if not response.success:
        raise HTTPException(status_code=400, detail=response.errors)

    # The list use case returns TenantListItem objects (simplified).
    # We map them to TenantResponse — some fields may not be available
    # from the list response, so we use what we have.
    items = [
        TenantResponse(
            id=item.id,
            org_id=item.org_id,
            name=item.name,
            status=item.status,
            edition=item.edition,
            region=item.region,
            org_type="production",  # list items don't include org_type
            is_trial=item.is_trial,
            created_at=item.created_at,
            updated_at=item.created_at,  # list items don't include updated_at
        )
        for item in response.items
    ]

    return TenantListResponse(
        items=items,
        total=response.total,
        skip=skip,
        limit=limit,
    )


# =============================================================================
# GET /tenants/{tenant_id} — Get a single tenant
# =============================================================================

@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    # No use case needed — we go directly to the repository for simple reads
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Get a specific tenant by ID."""
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

    return map_org_to_response(org)


# =============================================================================
# PATCH /tenants/{tenant_id} — Update a tenant
# =============================================================================

@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    tenant: TenantUpdate,
    use_case: UpdateTenantUseCase = Depends(get_update_tenant_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Update a specific tenant (partial update)."""

    # The UpdateTenantUseCase expects an org_id (string like "ORG-ABC12345"),
    # but the route receives a UUID. So we look up the org first.
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

    request_dto = UpdateTenantRequest(
        tenant_id=org.org_id,
        name=tenant.name,
        metadata=tenant.metadata,
    )

    response = use_case.execute(request_dto)

    if not response.success:
        raise HTTPException(status_code=400, detail=response.errors)

    # Re-fetch the full org to get all fields for TenantResponse
    updated_org = repo.get_by_id(tenant_id)
    return map_org_to_response(updated_org)


# =============================================================================
# DELETE /tenants/{tenant_id} — Not implemented yet
# =============================================================================

@router.delete("/{tenant_id}", response_model=DeleteResponse)
async def delete_tenant(tenant_id: UUID):
    """Delete a specific tenant (not implemented)."""
    raise HTTPException(status_code=501, detail="Delete tenant not implemented")
