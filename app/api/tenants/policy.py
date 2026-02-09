"""
Tenant Policy Routes — Policy Evaluation Endpoint
===================================================

Evaluates whether a tenant is allowed to perform a specific action
based on their edition, status, quotas, and compliance rules.

Endpoint:
    POST /tenants/{id}/policy/evaluate → wired to EnforcePolicyUseCase
"""

from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from app.schemas.v1.requests_responses import (
    PolicyEvaluationRequest,
    PolicyEvaluationResponse,
)

from app.business.use_cases.enforce_policy import (
    EnforcePolicyUseCase,
    EnforcePolicyRequest,
    PolicyContext,
)

from infrastructure.persistence.tenant_repository import (
    OrganizationRepository,
    OrganizationNotFoundError,
)

from app.dependencies.providers import (
    get_organization_repository,
    get_enforce_policy_use_case,
    map_error_to_http,
)

router = APIRouter(prefix="/tenants/{tenant_id}/policy", tags=["Tenant Policy"])


@router.post("/evaluate", response_model=PolicyEvaluationResponse)
async def evaluate_policy(
    tenant_id: UUID,
    request: PolicyEvaluationRequest,
    use_case: EnforcePolicyUseCase = Depends(get_enforce_policy_use_case),
    repo: OrganizationRepository = Depends(get_organization_repository),
):
    """Evaluate a policy for a tenant."""

    # Look up org to get org_id
    try:
        org = repo.get_by_id(tenant_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")

    # Map API schema → domain DTO
    # The API has flat fields (action, resource, context dict)
    # The domain DTO nests resource inside PolicyContext
    request_dto = EnforcePolicyRequest(
        org_id=org.org_id,
        action=request.action,
        context=PolicyContext(
            requested_resource=request.resource,
            attributes=request.context or {},
        ),
    )

    response = use_case.execute(request_dto)

    # Check for hard errors (not just policy denials)
    if response.error_code:
        raise map_error_to_http(response.error_code, [response.error_message or "Policy evaluation failed"])

    # Map domain response → API schema
    # violations are PolicyViolation objects — extract their messages
    return PolicyEvaluationResponse(
        allow=response.allowed,
        reason=response.warnings[0] if response.warnings else None,
        violations=[v.message for v in response.violations],
    )
