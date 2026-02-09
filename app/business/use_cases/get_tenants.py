"""
Get Tenants List Use Case
=========================

Retrieves a paginated list of tenants with optional filtering.

Features:
    - Pagination support (skip/limit)
    - Status filtering
    - Edition filtering
    - Sorting
    - Search by name

Author: Platform Engineering Team
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from domain.models import OrganizationStatus, Edition, Region
from infrastructure.persistence.tenant_repository import (
    OrganizationRepository,
    OrganizationFilter,
    PaginationParams,
    PaginatedResult,
)


# =============================================================================
# DTOs
# =============================================================================

@dataclass
class TenantListItem:
    """A single tenant in list response."""
    id: str
    org_id: str
    name: str
    status: str
    edition: str
    region: str
    created_at: str
    is_trial: bool


@dataclass
class GetTenantsListRequest:
    """Request to list tenants."""
    skip: int = 0
    limit: int = 20
    status: Optional[str] = None
    edition: Optional[str] = None
    search: Optional[str] = None
    sort_by: str = "created_at"
    sort_desc: bool = True


@dataclass
class GetTenantsListResponse:
    """Response with paginated tenant list."""
    items: List[TenantListItem] = field(default_factory=list)
    total: int = 0
    skip: int = 0
    limit: int = 20
    success: bool = True
    errors: List[str] = field(default_factory=list)


# =============================================================================
# Use Case
# =============================================================================

class GetTenantsListUseCase:
    """
    Use case for listing tenants.
    
    Retrieves a paginated list of tenants with filtering and sorting.
    """
    
    def __init__(self, repository: OrganizationRepository):
        """Initialize with repository."""
        self.repository = repository
    
    def execute(self, request: GetTenantsListRequest) -> GetTenantsListResponse:
        """
        Execute the use case.
        
        Args:
            request: List request with filters and pagination
            
        Returns:
            Paginated list of tenants
        """
        try:
            # Build filters
            statuses = None
            if request.status:
                try:
                    statuses = [OrganizationStatus[request.status.upper()]]
                except KeyError:
                    return GetTenantsListResponse(
                        success=False,
                        errors=[f"Invalid status: {request.status}"]
                    )
            
            editions = None
            if request.edition:
                try:
                    editions = [Edition[request.edition.upper()]]
                except KeyError:
                    return GetTenantsListResponse(
                        success=False,
                        errors=[f"Invalid edition: {request.edition}"]
                    )
            
            filter_obj = OrganizationFilter(
                statuses=statuses,
                editions=editions,
                search_text=request.search,
            )
            
            # Calculate pagination (convert skip/limit to page/page_size)
            page_size = min(request.limit, 100)
            page = (request.skip // page_size) + 1 if page_size > 0 else 1
            
            pagination = PaginationParams(
                page=page,
                page_size=page_size,
                sort_by=request.sort_by,
                sort_desc=request.sort_desc,
            )
            
            # Execute query
            result: PaginatedResult = self.repository.list(
                filter=filter_obj,
                pagination=pagination,
            )
            
            # Convert to response
            items = [
                TenantListItem(
                    id=str(org.id),
                    org_id=org.org_id,
                    name=org.name,
                    status=org.status.value,
                    edition=org.edition.value,
                    region=org.region.value if hasattr(org.region, 'value') else str(org.region),
                    created_at=org.created_at.isoformat(),
                    is_trial=org.is_trial(),
                )
                for org in result.items
            ]
            
            return GetTenantsListResponse(
                items=items,
                total=result.total,
                skip=request.skip,
                limit=request.limit,
                success=True,
            )
            
        except Exception as e:
            return GetTenantsListResponse(
                success=False,
                errors=[str(e)]
            )
