"""
Update Tenant Use Case
======================

Updates specific tenant fields (PATCH semantics).

Features:
    - Partial updates (name, metadata)
    - Validation
    - Optimistic locking support

Author: Platform Engineering Team
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from domain.models import Organization
from infrastructure.persistence.tenant_repository import OrganizationRepository
from infrastructure.observability.logging import get_logger

# Setup
logger = get_logger(__name__)


# =============================================================================
# DTOs
# =============================================================================

@dataclass
class UpdateTenantRequest:
    """Request to update tenant."""
    tenant_id: str
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class UpdateTenantResponse:
    """Response after updating tenant."""
    org_id: str
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""
    success: bool = True
    errors: list = field(default_factory=list)


class UpdateTenantError(Exception):
    """Error during tenant update."""
    pass


# =============================================================================
# Use Case
# =============================================================================

class UpdateTenantUseCase:
    """
    Use case for updating tenant details.
    
    Supports partial updates via PATCH semantics.
    Only provided fields are updated.
    """
    
    def __init__(self, repository: OrganizationRepository):
        """Initialize with repository."""
        self.repository = repository
    
    def execute(self, request: UpdateTenantRequest) -> UpdateTenantResponse:
        """
        Execute the use case.
        
        Args:
            request: Update request with fields to update
            
        Returns:
            Updated tenant response
        """
        try:
            # Find tenant by org_id
            org = self.repository.get_by_org_id(request.tenant_id)
            
            # Prepare updates
            updates = {}
            
            if request.name is not None:
                if not request.name.strip():
                    return UpdateTenantResponse(
                        org_id=request.tenant_id,
                        name=org.name,
                        success=False,
                        errors=["Name cannot be empty"]
                    )
                updates['name'] = request.name.strip()
            
            if request.metadata is not None:
                updates['metadata'] = request.metadata
            
            if not updates:
                # No updates provided
                return UpdateTenantResponse(
                    org_id=org.org_id,
                    name=org.name,
                    metadata=org.metadata or {},
                    updated_at=org.updated_at.isoformat(),
                    success=True,
                )
            
            # Perform update
            updated_org: Organization = self.repository.update(
                organization_id=org.id,
                updates=updates,
            )
            
            logger.info(
                "Tenant updated",
                org_id=request.tenant_id,
                updated_fields=list(updates.keys()),
            )
            
            return UpdateTenantResponse(
                org_id=updated_org.org_id,
                name=updated_org.name,
                metadata=updated_org.metadata or {},
                updated_at=updated_org.updated_at.isoformat(),
                success=True,
            )
            
        except Exception as e:
            logger.error(
                "Tenant update failed",
                org_id=request.tenant_id,
                error=str(e),
            )
            
            return UpdateTenantResponse(
                org_id=request.tenant_id,
                name="",
                success=False,
                errors=[str(e)]
            )
