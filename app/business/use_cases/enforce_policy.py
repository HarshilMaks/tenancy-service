"""
Enforce Policy Use Case - Production-Grade Implementation
=========================================================

Enterprise-ready policy enforcement for multi-tenant operations.
Implements the Policy Decision Point (PDP) pattern for authorization.

Features:
    - Edition-based feature gating
    - Usage quota enforcement
    - Regional compliance checks
    - Rate limiting integration
    - Status-based access control
    - Comprehensive audit logging

Policy Types:
    - FEATURE_ACCESS: Can tenant use this feature?
    - USAGE_QUOTA: Has tenant exceeded limits?
    - RATE_LIMIT: Is tenant within rate bounds?
    - REGIONAL_COMPLIANCE: Is action compliant with region?
    - DATA_RESIDENCY: Is data location valid?
    - TIME_BASED: Is action within allowed timeframe?

Decision Flow:
    1. Load organization context
    2. Check organization status
    3. Evaluate edition permissions
    4. Check usage quotas
    5. Apply regional policies
    6. Return aggregated decision

Author: Platform Engineering Team
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Set, runtime_checkable
from uuid import uuid4

# Infrastructure imports
from infrastructure.observability.logging import (
    get_logger,
    AuditLogger,
    LogContext,
)
from infrastructure.observability.metrics import get_metrics
from infrastructure.observability.tracing import (
    trace_operation,
    create_span,
    SpanKind,
)

# Domain imports
from domain.models import (
    Organization,
    OrganizationStatus,
    Edition,
    Region,
)
from app.business.domain.entities.policies import (
    get_edition_limits,
    get_edition_features,
    EditionLimits,
    is_feature_enabled,
)

# Setup logging
logger = get_logger(__name__)
audit = AuditLogger("tenancy_service")
metrics = get_metrics()


# =============================================================================
# PORTS
# =============================================================================

@runtime_checkable
class OrganizationRepository(Protocol):
    """Port for organization persistence."""
    
    def get_by_org_id(self, org_id: str) -> Optional[Organization]:
        """Get organization by external ID."""
        ...


@runtime_checkable
class UsageTracker(Protocol):
    """Port for tracking usage metrics."""
    
    def get_current_usage(
        self,
        org_id: str,
        metric: str,
        period: str,
    ) -> int:
        """Get current usage for a metric."""
        ...


@runtime_checkable
class RateLimiter(Protocol):
    """Port for rate limiting."""
    
    def check_rate_limit(
        self,
        org_id: str,
        action: str,
        limit: int,
        window_seconds: int,
    ) -> bool:
        """Check if action is within rate limit."""
        ...


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class PolicyType(Enum):
    """Type of policy being evaluated."""
    
    FEATURE_ACCESS = "feature_access"
    USAGE_QUOTA = "usage_quota"
    RATE_LIMIT = "rate_limit"
    REGIONAL_COMPLIANCE = "regional_compliance"
    DATA_RESIDENCY = "data_residency"
    TIME_BASED = "time_based"
    STATUS_CHECK = "status_check"


class PolicyDecision(Enum):
    """Result of policy evaluation."""
    
    ALLOW = "allow"
    DENY = "deny"
    WARN = "warn"  # Allow but with warning


class PolicyError(Enum):
    """Error codes for policy enforcement."""
    
    ORG_NOT_FOUND = "ORG_NOT_FOUND"
    INVALID_ACTION = "INVALID_ACTION"
    EVALUATION_FAILED = "EVALUATION_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Status restrictions - which statuses can perform actions
STATUS_RESTRICTIONS: Dict[OrganizationStatus, Set[str]] = {
    OrganizationStatus.PROVISIONING: {"read", "configure"},
    OrganizationStatus.ACTIVE: {"*"},  # All actions
    OrganizationStatus.TRIAL: {"*"},   # All actions (may have limits)
    OrganizationStatus.SUSPENDED: {"read_only", "billing", "reactivate"},
    OrganizationStatus.PENDING_TERMINATION: {"read_only", "export", "cancel_termination"},
    OrganizationStatus.TERMINATED: set(),  # No actions
}

# Actions that require specific editions
EDITION_REQUIRED_ACTIONS: Dict[str, Set[Edition]] = {
    "create_workflow": {Edition.PROFESSIONAL, Edition.ENTERPRISE, Edition.UNLIMITED},
    "custom_reports": {Edition.PROFESSIONAL, Edition.ENTERPRISE, Edition.UNLIMITED},
    "api_access": {Edition.ESSENTIALS, Edition.PROFESSIONAL, Edition.ENTERPRISE, Edition.UNLIMITED},
    "sandbox_create": {Edition.ENTERPRISE, Edition.UNLIMITED},
    "sso_configure": {Edition.ENTERPRISE, Edition.UNLIMITED},
    "audit_logs": {Edition.ENTERPRISE, Edition.UNLIMITED},
    "unlimited_storage": {Edition.UNLIMITED},
}

# Regional compliance requirements
GDPR_REGIONS: Set[Region] = {Region.EU_WEST_1, Region.EU_CENTRAL_1}
CCPA_REGIONS: Set[Region] = {Region.US_WEST_1, Region.US_EAST_1}


# =============================================================================
# REQUEST/RESPONSE DTOs
# =============================================================================

@dataclass
class PolicyContext:
    """
    Context for policy evaluation.
    
    Contains all information needed to make a policy decision
    without additional lookups.
    """
    
    # Current usage (for quota checks)
    current_users: int = 0
    current_storage_gb: float = 0.0
    current_api_calls_today: int = 0
    current_tickets_month: int = 0
    
    # Request context
    requested_resource: Optional[str] = None
    resource_size_bytes: Optional[int] = None
    target_region: Optional[str] = None
    
    # Actor information
    actor_id: Optional[str] = None
    actor_roles: List[str] = field(default_factory=list)
    
    # Time context
    request_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Custom attributes
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyViolation:
    """Details of a policy violation."""
    
    policy_type: PolicyType
    rule: str
    message: str
    current_value: Optional[Any] = None
    limit_value: Optional[Any] = None
    severity: str = "error"  # error, warning


@dataclass
class EnforcePolicyRequest:
    """
    Request DTO for policy enforcement.
    
    Attributes:
        org_id: Organization performing the action
        action: Action being attempted
        context: Additional context for evaluation
        skip_quota_check: Skip usage quota validation
        skip_rate_limit: Skip rate limiting check
        actor_id: User/system requesting the action
    """
    
    # Required
    org_id: str
    action: str
    
    # Context
    context: Optional[PolicyContext] = None
    
    # Options
    skip_quota_check: bool = False
    skip_rate_limit: bool = False
    
    # Actor
    actor_id: Optional[str] = None
    
    # Tracking
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        """Normalize fields but preserve original org_id as tests expect exact inputs."""
        if self.org_id is None:
            self.org_id = ""
        else:
            self.org_id = str(self.org_id)
        self.action = self.action.strip().lower() if self.action else ""
        if self.context is None:
            self.context = PolicyContext()


@dataclass
class EnforcePolicyResponse:
    """Response DTO for policy enforcement."""
    
    # Decision
    allowed: bool
    decision: PolicyDecision
    
    # Details
    violations: List[PolicyViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Organization context (for client use)
    org_status: Optional[str] = None
    edition: Optional[str] = None
    
    # Limits info (for client feedback)
    limits: Optional[Dict[str, Any]] = None
    current_usage: Optional[Dict[str, Any]] = None
    
    # Error info
    error_code: Optional[PolicyError] = None
    error_message: Optional[str] = None
    
    # Timing
    duration_ms: Optional[float] = None
    request_id: Optional[str] = None
    
    @classmethod
    def allow(
        cls,
        org_status: str,
        edition: str,
        warnings: Optional[List[str]] = None,
        limits: Optional[Dict[str, Any]] = None,
        current_usage: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> "EnforcePolicyResponse":
        """Create allow response."""
        return cls(
            allowed=True,
            decision=PolicyDecision.ALLOW,
            warnings=warnings or [],
            org_status=org_status,
            edition=edition,
            limits=limits,
            current_usage=current_usage,
            duration_ms=duration_ms,
            request_id=request_id,
        )
    
    @classmethod
    def deny(
        cls,
        violations: List[PolicyViolation],
        org_status: Optional[str] = None,
        edition: Optional[str] = None,
        limits: Optional[Dict[str, Any]] = None,
        current_usage: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> "EnforcePolicyResponse":
        """Create deny response."""
        return cls(
            allowed=False,
            decision=PolicyDecision.DENY,
            violations=violations,
            org_status=org_status,
            edition=edition,
            limits=limits,
            current_usage=current_usage,
            duration_ms=duration_ms,
            request_id=request_id,
        )
    
    @classmethod
    def error(
        cls,
        error_code: PolicyError,
        error_message: str,
        duration_ms: Optional[float] = None,
        request_id: Optional[str] = None,
    ) -> "EnforcePolicyResponse":
        """Create error response."""
        return cls(
            allowed=False,
            decision=PolicyDecision.DENY,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
            request_id=request_id,
        )


# =============================================================================
# USE CASE IMPLEMENTATION
# =============================================================================

class EnforcePolicyUseCase:
    """
    Use case for enforcing policies on tenant actions.
    
    Implements the Policy Decision Point (PDP) pattern for
    evaluating whether an organization can perform an action.
    
    Evaluation Order:
        1. Status check (is org in valid state?)
        2. Feature access (does edition include feature?)
        3. Usage quotas (are limits respected?)
        4. Rate limits (is request rate acceptable?)
        5. Regional compliance (is action compliant?)
    
    Thread Safety:
        Stateless and thread-safe.
    """
    
    _decision_counter = None
    _evaluation_histogram = None
    
    def __init__(
        self,
        repository: OrganizationRepository,
        usage_tracker: Optional[UsageTracker] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Initialize use case with dependencies.
        
        Args:
            repository: Organization persistence port
            usage_tracker: Optional usage tracking port
            rate_limiter: Optional rate limiting port
        """
        self._repository = repository
        self._usage_tracker = usage_tracker
        self._rate_limiter = rate_limiter
        
        # Initialize metrics
        logger.debug(
            "EnforcePolicyUseCase initialized",
            has_usage_tracker=usage_tracker is not None,
            has_rate_limiter=rate_limiter is not None,
        )
    
    @trace_operation("enforce_policy", kind=SpanKind.INTERNAL)
    def execute(
        self,
        request: EnforcePolicyRequest,
    ) -> EnforcePolicyResponse:
        """
        Execute the policy enforcement use case.
        
        Args:
            request: Policy enforcement parameters
            
        Returns:
            Response with decision and details
        """
        start_time = time.perf_counter()
        request_id = request.request_id or f"req-{uuid4().hex[:12]}"
        
        with LogContext(
            correlation_id=request.correlation_id,
            request_id=request_id,
        ):
            logger.debug(
                "Starting policy evaluation",
                org_id=request.org_id,
                action=request.action,
                actor_id=request.actor_id,
            )
            
            try:
                # Step 1: Load organization
                with create_span("load_organization") as span:
                    organization = self._repository.get_by_org_id(request.org_id)
                    
                    if organization is None:
                        logger.warning(
                            "Organization not found for policy check",
                            org_id=request.org_id,
                        )
                        return EnforcePolicyResponse.error(
                            error_code=PolicyError.ORG_NOT_FOUND,
                            error_message=f"Organization not found: {request.org_id}",
                            duration_ms=self._elapsed_ms(start_time),
                            request_id=request_id,
                        )
                    
                    span.set_attribute("org_status", organization.status.value)
                    span.set_attribute("edition", organization.edition.value)
                    span.set_attribute("region", organization.region.value)
                    
                    logger.debug(
                        "Organization loaded for policy check",
                        org_id=request.org_id,
                        status=organization.status.value,
                        edition=organization.edition.value,
                    )
                
                # Get edition limits for response
                limits = get_edition_limits(organization.edition)
                
                # Collect all violations
                violations: List[PolicyViolation] = []
                warnings: List[str] = []
                
                # Step 2: Check organization status
                with create_span("check_status") as span:
                    status_violations = self._check_status(
                        organization, request.action
                    )
                    violations.extend(status_violations)
                    span.set_attribute("violations", len(status_violations))
                    
                    if status_violations:
                        logger.info(
                            "Status check failed",
                            org_id=request.org_id,
                            status=organization.status.value,
                            action=request.action,
                        )
                
                # Step 3: Check feature access (edition-based)
                with create_span("check_feature_access") as span:
                    feature_violations = self._check_feature_access(
                        organization, request.action
                    )
                    violations.extend(feature_violations)
                    span.set_attribute("violations", len(feature_violations))
                    
                    if feature_violations:
                        logger.info(
                            "Feature access denied",
                            org_id=request.org_id,
                            edition=organization.edition.value,
                            action=request.action,
                        )
                
                # Step 4: Check usage quotas
                if not request.skip_quota_check:
                    with create_span("check_usage_quotas") as span:
                        quota_violations, quota_warnings = self._check_usage_quotas(
                            organization, request.action, request.context, limits
                        )
                        violations.extend(quota_violations)
                        warnings.extend(quota_warnings)
                        span.set_attribute("violations", len(quota_violations))
                        span.set_attribute("warnings", len(quota_warnings))
                
                # Step 5: Check rate limits
                if not request.skip_rate_limit and self._rate_limiter:
                    with create_span("check_rate_limit") as span:
                        rate_violations = self._check_rate_limit(
                            organization, request.action
                        )
                        violations.extend(rate_violations)
                        span.set_attribute("violations", len(rate_violations))
                
                # Step 6: Check regional compliance
                with create_span("check_regional_compliance") as span:
                    compliance_violations = self._check_regional_compliance(
                        organization, request.action, request.context
                    )
                    violations.extend(compliance_violations)
                    span.set_attribute("violations", len(compliance_violations))
                
                # Determine final decision
                decision = PolicyDecision.ALLOW if not violations else PolicyDecision.DENY
                
                # Build current usage info
                current_usage = {
                    "users": request.context.current_users if request.context else 0,
                    "storage_gb": request.context.current_storage_gb if request.context else 0,
                    "api_calls_today": request.context.current_api_calls_today if request.context else 0,
                }
                
                # Build limits info
                limits_dict = {
                    "max_users": limits.max_users if limits else None,
                    "max_storage_gb": limits.max_storage_gb if limits else None,
                    "api_calls_per_day": limits.api_calls_per_day if limits else None,
                } if limits else None
                
                # Record metrics
                duration_ms = self._elapsed_ms(start_time)
                self._record_metrics(
                    organization, request.action, decision, duration_ms
                )
                
                # Log decision
                logger.info(
                    "Policy decision rendered",
                    org_id=request.org_id,
                    action=request.action,
                    decision=decision.value,
                    violations_count=len(violations),
                    warnings_count=len(warnings),
                    duration_ms=round(duration_ms, 2),
                )
                
                # Return response
                if violations:
                    return EnforcePolicyResponse.deny(
                        violations=violations,
                        org_status=organization.status.value,
                        edition=organization.edition.value,
                        limits=limits_dict,
                        current_usage=current_usage,
                        duration_ms=duration_ms,
                        request_id=request_id,
                    )
                
                return EnforcePolicyResponse.allow(
                    org_status=organization.status.value,
                    edition=organization.edition.value,
                    warnings=warnings,
                    limits=limits_dict,
                    current_usage=current_usage,
                    duration_ms=duration_ms,
                    request_id=request_id,
                )
                
            except Exception as e:
                logger.exception(
                    "Unexpected error during policy evaluation",
                    org_id=request.org_id,
                    action=request.action,
                    error=str(e),
                )
                
                return EnforcePolicyResponse.error(
                    error_code=PolicyError.INTERNAL_ERROR,
                    error_message=f"Internal error: {str(e)}",
                    duration_ms=self._elapsed_ms(start_time),
                    request_id=request_id,
                )
    
    def _check_status(
        self,
        organization: Organization,
        action: str,
    ) -> List[PolicyViolation]:
        """Check if action is allowed in current status."""
        violations = []
        
        allowed_actions = STATUS_RESTRICTIONS.get(
            organization.status, set()
        )
        
        # "*" means all actions allowed
        if "*" in allowed_actions:
            return violations
        
        # Check if action matches any allowed action
        action_allowed = (
            action in allowed_actions or
            any(action.startswith(a.replace("*", "")) for a in allowed_actions if a.endswith("*"))
        )
        
        if not action_allowed:
            violations.append(PolicyViolation(
                policy_type=PolicyType.STATUS_CHECK,
                rule="status_restriction",
                message=(
                    f"Action '{action}' is not allowed when organization "
                    f"is in '{organization.status.value}' status"
                ),
                current_value=organization.status.value,
                limit_value=list(allowed_actions) if allowed_actions else "none",
            ))
            
            logger.debug(
                "Status restriction violated",
                action=action,
                status=organization.status.value,
                allowed=list(allowed_actions),
            )
        
        return violations
    
    def _check_feature_access(
        self,
        organization: Organization,
        action: str,
    ) -> List[PolicyViolation]:
        """Check if edition allows the action."""
        violations = []
        
        required_editions = EDITION_REQUIRED_ACTIONS.get(action)
        
        if required_editions and organization.edition not in required_editions:
            violations.append(PolicyViolation(
                policy_type=PolicyType.FEATURE_ACCESS,
                rule="edition_restriction",
                message=(
                    f"Action '{action}' requires edition: "
                    f"{', '.join(e.value for e in required_editions)}. "
                    f"Current edition: {organization.edition.value}"
                ),
                current_value=organization.edition.value,
                limit_value=[e.value for e in required_editions],
            ))
            
            logger.debug(
                "Edition restriction violated",
                action=action,
                current_edition=organization.edition.value,
                required_editions=[e.value for e in required_editions],
            )
        
        # Check using domain policy function
        if not is_feature_enabled(organization.edition, action):
            # Only add if not already violated
            if not violations:
                violations.append(PolicyViolation(
                    policy_type=PolicyType.FEATURE_ACCESS,
                    rule="feature_disabled",
                    message=f"Feature '{action}' is not enabled for {organization.edition.value} edition",
                    current_value=organization.edition.value,
                ))
        
        return violations
    
    def _check_usage_quotas(
        self,
        organization: Organization,
        action: str,
        context: PolicyContext,
        limits: Optional[EditionLimits],
    ) -> tuple[List[PolicyViolation], List[str]]:
        """Check if action would exceed usage quotas."""
        violations = []
        warnings = []
        
        if not limits:
            return violations, warnings
        
        # Check user limit
        if limits.max_users and context.current_users >= limits.max_users:
            if action in ["add_user", "invite_user", "create_user"]:
                violations.append(PolicyViolation(
                    policy_type=PolicyType.USAGE_QUOTA,
                    rule="max_users",
                    message=f"User limit reached: {context.current_users}/{limits.max_users}",
                    current_value=context.current_users,
                    limit_value=limits.max_users,
                ))
        elif limits.max_users and context.current_users >= limits.max_users * 0.9:
            warnings.append(
                f"Approaching user limit: {context.current_users}/{limits.max_users}"
            )
        
        # Check storage limit
        if limits.max_storage_gb and context.current_storage_gb >= limits.max_storage_gb:
            if action in ["upload", "create_attachment", "store_file"]:
                violations.append(PolicyViolation(
                    policy_type=PolicyType.USAGE_QUOTA,
                    rule="max_storage",
                    message=f"Storage limit reached: {context.current_storage_gb:.1f}/{limits.max_storage_gb} GB",
                    current_value=context.current_storage_gb,
                    limit_value=limits.max_storage_gb,
                ))
        elif limits.max_storage_gb and context.current_storage_gb >= limits.max_storage_gb * 0.9:
            warnings.append(
                f"Approaching storage limit: {context.current_storage_gb:.1f}/{limits.max_storage_gb} GB"
            )
        
        # Check API call limit
        if limits.api_calls_per_day and context.current_api_calls_today >= limits.api_calls_per_day:
            if action.startswith("api_"):
                violations.append(PolicyViolation(
                    policy_type=PolicyType.USAGE_QUOTA,
                    rule="api_calls_per_day",
                    message=f"Daily API limit reached: {context.current_api_calls_today}/{limits.api_calls_per_day}",
                    current_value=context.current_api_calls_today,
                    limit_value=limits.api_calls_per_day,
                ))
        elif limits.api_calls_per_day and context.current_api_calls_today >= limits.api_calls_per_day * 0.9:
            warnings.append(
                f"Approaching API limit: {context.current_api_calls_today}/{limits.api_calls_per_day}"
            )
        
        return violations, warnings
    
    def _check_rate_limit(
        self,
        organization: Organization,
        action: str,
    ) -> List[PolicyViolation]:
        """Check if action is within rate limits."""
        violations = []
        
        if not self._rate_limiter:
            return violations
        
        # Define rate limits per action
        rate_limits = {
            "api_call": (1000, 60),    # 1000 per minute
            "bulk_export": (10, 3600),  # 10 per hour
            "login": (100, 60),         # 100 per minute
        }
        
        limit_config = rate_limits.get(action)
        if limit_config:
            limit, window = limit_config
            allowed = self._rate_limiter.check_rate_limit(
                org_id=organization.org_id,
                action=action,
                limit=limit,
                window_seconds=window,
            )
            
            if not allowed:
                violations.append(PolicyViolation(
                    policy_type=PolicyType.RATE_LIMIT,
                    rule=f"rate_limit_{action}",
                    message=f"Rate limit exceeded for '{action}': {limit} per {window}s",
                    limit_value=f"{limit}/{window}s",
                ))
                
                logger.info(
                    "Rate limit exceeded",
                    org_id=organization.org_id,
                    action=action,
                    limit=limit,
                    window_seconds=window,
                )
        
        return violations
    
    def _check_regional_compliance(
        self,
        organization: Organization,
        action: str,
        context: PolicyContext,
    ) -> List[PolicyViolation]:
        """Check regional compliance requirements."""
        violations = []
        
        # GDPR compliance for EU regions
        if organization.region in GDPR_REGIONS:
            if action in ["export_data", "transfer_data"] and context.target_region:
                try:
                    target = Region(context.target_region.lower().replace("_", "-"))
                    if target not in GDPR_REGIONS:
                        violations.append(PolicyViolation(
                            policy_type=PolicyType.REGIONAL_COMPLIANCE,
                            rule="gdpr_data_residency",
                            message=(
                                f"Cannot transfer data from EU region to {target.value}. "
                                "GDPR data residency requirements apply."
                            ),
                            current_value=organization.region.value,
                            limit_value=[r.value for r in GDPR_REGIONS],
                            severity="error",
                        ))
                        
                        logger.warning(
                            "GDPR data residency violation",
                            org_id=organization.org_id,
                            source_region=organization.region.value,
                            target_region=context.target_region,
                        )
                except ValueError:
                    pass
        
        # CCPA compliance for US regions
        if organization.region in CCPA_REGIONS:
            if action == "sell_data":
                violations.append(PolicyViolation(
                    policy_type=PolicyType.REGIONAL_COMPLIANCE,
                    rule="ccpa_do_not_sell",
                    message="Data sale prohibited under CCPA without explicit consent",
                    severity="error",
                ))
        
        return violations
    
    def _elapsed_ms(self, start_time: float) -> float:
        """Calculate elapsed time in milliseconds."""
        return (time.perf_counter() - start_time) * 1000
    
    def _record_metrics(
        self,
        organization: Organization,
        action: str,
        decision: PolicyDecision,
        duration_ms: float,
    ) -> None:
        """Record metrics for policy decision."""
        if self._decision_counter:
            self._decision_counter.inc(
                labels={
                    "action": action,
                    "decision": decision.value,
                    "edition": organization.edition.value,
                }
            )
        
        if self._evaluation_histogram:
            self._evaluation_histogram.observe(
                duration_ms / 1000,  # Convert to seconds
                labels={"action": action}
            )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def enforce_policy(
    org_id: str,
    action: str,
    repository: OrganizationRepository,
    context: Optional[PolicyContext] = None,
    **kwargs,
) -> EnforcePolicyResponse:
    """
    Convenience function for policy enforcement.
    
    Args:
        org_id: Organization to check
        action: Action being attempted
        repository: Persistence port
        context: Optional policy context
        **kwargs: Additional request parameters
        
    Returns:
        EnforcePolicyResponse with decision
        
    Example:
        >>> response = enforce_policy(
        ...     org_id="ORG-ABC12345",
        ...     action="create_workflow",
        ...     repository=repo,
        ...     context=PolicyContext(current_users=50),
        ... )
        >>> if response.allowed:
        ...     print("Action permitted")
        >>> else:
        ...     print(f"Denied: {response.violations}")
    """
    request = EnforcePolicyRequest(
        org_id=org_id,
        action=action,
        context=context,
        **kwargs,
    )
    
    use_case = EnforcePolicyUseCase(repository=repository)
    
    return use_case.execute(request)


def check_feature_allowed(
    org_id: str,
    feature: str,
    repository: OrganizationRepository,
) -> bool:
    """
    Quick check if a feature is allowed.
    
    Simplified helper for common feature checks.
    
    Args:
        org_id: Organization ID
        feature: Feature name to check
        repository: Persistence port
        
    Returns:
        True if feature is allowed, False otherwise
    """
    response = enforce_policy(
        org_id=org_id,
        action=feature,
        repository=repository,
        skip_quota_check=True,
        skip_rate_limit=True,
    )
    
    return response.allowed


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Ports
    "OrganizationRepository",
    "UsageTracker",
    "RateLimiter",
    
    # Enums
    "PolicyType",
    "PolicyDecision",
    "PolicyError",
    
    # DTOs
    "PolicyContext",
    "PolicyViolation",
    "EnforcePolicyRequest",
    "EnforcePolicyResponse",
    
    # Use case
    "EnforcePolicyUseCase",
    
    # Convenience
    "enforce_policy",
    "check_feature_allowed",
    
    # Constants
    "STATUS_RESTRICTIONS",
    "EDITION_REQUIRED_ACTIONS",
    "GDPR_REGIONS",
    "CCPA_REGIONS",
]
