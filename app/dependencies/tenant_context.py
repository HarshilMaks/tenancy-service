"""
Tenant Context Dependencies - Request-Scoped Tenant Information
==============================================================

FastAPI dependencies for injecting tenant context into request handlers.
Provides access to organization information, user permissions, and 
request-scoped settings.

This module handles:
    - Extracting tenant ID from headers/tokens
    - Loading organization context
    - Caching within request scope
    - Multi-tenancy isolation

Author: Platform Engineering Team
"""

from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from uuid import UUID

from infrastructure.observability import get_logger
from infrastructure.persistence.tenant_repository import OrganizationRepository
from app.api.tenancy_routes import get_organization_repository

logger = get_logger(__name__)


class TenantContext:
    """Container for tenant-specific request context."""
    
    def __init__(
        self,
        organization_id: UUID,
        organization_name: str,
        edition: str,
        status: str,
        region: str,
    ):
        self.organization_id = organization_id
        self.organization_name = organization_name
        self.edition = edition
        self.status = status
        self.region = region


async def get_tenant_context(
    x_organization_id: Optional[str] = Header(None),
    repository: OrganizationRepository = Depends(get_organization_repository),
) -> TenantContext:
    """
    Extract and validate tenant context from request.
    
    Args:
        x_organization_id: Organization ID from header
        repository: Organization repository
        
    Returns:
        TenantContext with organization information
        
    Raises:
        HTTPException: If organization not found or invalid
    """
    if not x_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Organization-Id header"
        )
    
    try:
        org_id = UUID(x_organization_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID format"
        )
    
    # Load organization
    organization = await repository.get_by_id(org_id)
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found"
        )
    
    return TenantContext(
        organization_id=organization.id,
        organization_name=organization.name,
        edition=organization.edition.value,
        status=organization.status.value,
        region=organization.region,
    )


def get_optional_tenant_context(
    x_organization_id: Optional[str] = Header(None),
    repository: OrganizationRepository = Depends(get_organization_repository),
) -> Optional[TenantContext]:
    """
    Extract tenant context if present, None otherwise.
    
    For endpoints that work with or without tenant context.
    """
    if not x_organization_id:
        return None
    
    try:
        return get_tenant_context(x_organization_id, repository)
    except HTTPException:
        return None