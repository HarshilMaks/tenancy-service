"""Get Tenant Usage Use Case"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from infrastructure.persistence.tenant_repository import OrganizationRepository


@dataclass
class UsageMetric:
    """A single usage metric."""
    metric_name: str
    value: float
    limit: Optional[float] = None
    unit: str = ""


@dataclass
class GetTenantUsageRequest:
    """Request to get tenant usage."""
    org_id: str
    period: str = "current"  # current, monthly, yearly


@dataclass
class GetTenantUsageResponse:
    """Response with tenant usage metrics."""
    org_id: str
    period: str
    metrics: List[UsageMetric] = field(default_factory=list)
    success: bool = True
    errors: List[str] = field(default_factory=list)


class GetTenantUsageUseCase:
    """Use case for retrieving tenant usage metrics."""
    
    def __init__(self, repository: OrganizationRepository):
        """Initialize with repository."""
        self.repository = repository
    
    def execute(self, request: GetTenantUsageRequest) -> GetTenantUsageResponse:
        """Execute the use case."""
        try:
            # For now, return empty metrics - usage tracking not yet implemented
            return GetTenantUsageResponse(
                org_id=request.org_id,
                period=request.period,
                metrics=[],
                success=True,
            )
        except Exception as e:
            return GetTenantUsageResponse(
                org_id=request.org_id,
                period=request.period,
                success=False,
                errors=[str(e)]
            )
