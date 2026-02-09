"""
Organization Invariants - Business Rule Validation

This module enforces business rules (invariants) that must ALWAYS be true.
These are the rules that protect data integrity at the domain level.

Invariants vs Policies:
- Invariants: MUST be true at all times (data integrity)
- Policies: Business rules that CAN be configured/changed

Examples:
- Invariant: "Organization name cannot be empty" → Always true
- Policy: "Organization can have max 10 users" → Depends on edition
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Set, Tuple
import re
import unicodedata

from app.db.models.domain_models import (
    Organization,
    OrganizationStatus,
    SuspensionInfo,
    Edition,
    BillingStatus,
    OrganizationType,
    Region,
    Address,
)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class InvariantViolation(Exception):
    """Base exception for invariant violations."""
    
    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        self.message = message
        super().__init__(message)


class NameInvariantViolation(InvariantViolation):
    """Raised when organization name violates invariants."""
    pass


class IdentityInvariantViolation(InvariantViolation):
    """Raised when identity fields violate invariants."""
    pass


class StatusInvariantViolation(InvariantViolation):
    """Raised when status-related fields violate invariants."""
    pass


class BillingInvariantViolation(InvariantViolation):
    """Raised when billing-related fields violate invariants."""
    pass


class SuspensionInvariantViolation(InvariantViolation):
    """Raised when suspension-related fields violate invariants."""
    pass


class DateInvariantViolation(InvariantViolation):
    """Raised when date-related fields violate invariants."""
    pass


# ============================================================================
# NAME INVARIANTS
# ============================================================================

# Naming rules (similar to Salesforce org naming)
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 255
MAX_NORMALIZED_NAME_LENGTH = 100

# Characters not allowed in organization names
FORBIDDEN_NAME_CHARS = set('<>{}[]|\\^~`@#$%&*+=;:?!')

# Reserved names (case-insensitive)
RESERVED_NAMES = {
    'admin', 'administrator', 'root', 'system', 'null', 'undefined',
    'support', 'help', 'billing', 'sales', 'api', 'www', 'mail',
    'test', 'demo', 'trial', 'sandbox', 'staging', 'production',
}


def validate_organization_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate organization name.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name or not name.strip():
        return False, "Organization name cannot be empty"
    
    name = name.strip()
    
    # Length checks
    if len(name) < MIN_NAME_LENGTH:
        return False, f"Organization name must be at least {MIN_NAME_LENGTH} characters"
    
    if len(name) > MAX_NAME_LENGTH:
        return False, f"Organization name cannot exceed {MAX_NAME_LENGTH} characters"
    
    # Check for forbidden characters
    forbidden_found = FORBIDDEN_NAME_CHARS.intersection(set(name))
    if forbidden_found:
        return False, f"Organization name contains forbidden characters: {forbidden_found}"
    
    # Check for reserved names
    if name.lower() in RESERVED_NAMES:
        return False, f"'{name}' is a reserved name and cannot be used"
    
    # Check for control characters
    if any(unicodedata.category(c) == 'Cc' for c in name):
        return False, "Organization name cannot contain control characters"
    
    # Must start with alphanumeric
    if not name[0].isalnum():
        return False, "Organization name must start with a letter or number"
    
    return True, None


def normalize_organization_name(name: str) -> str:
    """
    Create a normalized, URL-safe version of the organization name.
    
    Used for:
    - Subdomains (acme-corp.supportplatform.com)
    - API identifiers
    - Unique lookups
    """
    # Lowercase
    normalized = name.lower()
    
    # Replace spaces and underscores with hyphens
    normalized = re.sub(r'[\s_]+', '-', normalized)
    
    # Remove non-alphanumeric characters except hyphens
    normalized = re.sub(r'[^a-z0-9-]', '', normalized)
    
    # Collapse multiple hyphens
    normalized = re.sub(r'-+', '-', normalized)
    
    # Remove leading/trailing hyphens
    normalized = normalized.strip('-')
    
    # Truncate to max length
    if len(normalized) > MAX_NORMALIZED_NAME_LENGTH:
        normalized = normalized[:MAX_NORMALIZED_NAME_LENGTH].rstrip('-')
    
    return normalized


def require_valid_name(name: str) -> None:
    """
    Require organization name to be valid.
    
    Raises:
        NameInvariantViolation: If name is invalid
    """
    is_valid, error = validate_organization_name(name)
    if not is_valid:
        raise NameInvariantViolation(error, field="name")


# ============================================================================
# IDENTITY INVARIANTS
# ============================================================================

ORG_ID_PATTERN = re.compile(r'^ORG-[A-Z0-9]{8}$')
EXTERNAL_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_org_id(org_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate organization ID format.
    
    Format: ORG-XXXXXXXX (8 alphanumeric characters)
    """
    if not org_id:
        return False, "Organization ID cannot be empty"
    
    if not ORG_ID_PATTERN.match(org_id):
        return False, "Organization ID must match format ORG-XXXXXXXX"
    
    return True, None


def validate_external_id(external_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate external ID format.
    
    External IDs are provided by integrations (CRM, billing systems, etc.)
    """
    if not external_id:
        return True, None  # External ID is optional
    
    if len(external_id) > 255:
        return False, "External ID cannot exceed 255 characters"
    
    if not EXTERNAL_ID_PATTERN.match(external_id):
        return False, "External ID can only contain letters, numbers, underscores, and hyphens"
    
    return True, None


def require_valid_org_id(org_id: str) -> None:
    """Require valid organization ID."""
    is_valid, error = validate_org_id(org_id)
    if not is_valid:
        raise IdentityInvariantViolation(error, field="org_id")


# ============================================================================
# STATUS INVARIANTS
# ============================================================================

def validate_status_consistency(org: Organization) -> List[str]:
    """
    Validate that organization status is consistent with other fields.
    
    Returns list of inconsistencies found.
    """
    issues = []
    
    # SUSPENDED must have suspension_info
    if org.status == OrganizationStatus.SUSPENDED:
        if org.suspension_info is None:
            issues.append("SUSPENDED organization must have suspension_info")
    
    # Non-SUSPENDED should not have suspension_info
    if org.status != OrganizationStatus.SUSPENDED and org.suspension_info is not None:
        issues.append(
            f"Organization in {org.status.value} status should not have suspension_info"
        )
    
    # TRIAL must have trial_ends_at
    if org.status == OrganizationStatus.TRIAL:
        if org.trial_ends_at is None:
            issues.append("TRIAL organization must have trial_ends_at")
    
    # TERMINATED must have terminated_at and termination_reason
    if org.status == OrganizationStatus.TERMINATED:
        if org.terminated_at is None:
            issues.append("TERMINATED organization must have terminated_at")
        if not org.termination_reason:
            issues.append("TERMINATED organization must have termination_reason")
    
    # PROVISIONING should not have subscription dates
    if org.status == OrganizationStatus.PROVISIONING:
        if org.subscription_started_at is not None:
            issues.append("PROVISIONING organization should not have subscription_started_at")
    
    # PENDING_CANCELLATION must have subscription_ends_at
    if org.status == OrganizationStatus.PENDING_CANCELLATION:
        if org.subscription_ends_at is None:
            issues.append("PENDING_CANCELLATION organization should have subscription_ends_at")
    
    return issues


def require_status_consistency(org: Organization) -> None:
    """
    Require organization status to be consistent.
    
    Raises:
        StatusInvariantViolation: If status is inconsistent
    """
    issues = validate_status_consistency(org)
    if issues:
        raise StatusInvariantViolation(
            f"Status inconsistencies: {'; '.join(issues)}",
            field="status"
        )


# ============================================================================
# BILLING INVARIANTS
# ============================================================================

def validate_billing_consistency(org: Organization) -> List[str]:
    """
    Validate billing-related field consistency.
    
    Returns list of inconsistencies found.
    """
    issues = []
    
    # ACTIVE billing should have subscription dates
    if org.billing_status == BillingStatus.ACTIVE:
        if org.subscription_started_at is None:
            issues.append("ACTIVE billing status should have subscription_started_at")
    
    # PAST_DUE should have some indication
    if org.billing_status == BillingStatus.PAST_DUE:
        if not org.payment_method_on_file:
            issues.append("PAST_DUE billing should have payment_method_on_file to retry")
    
    # CANCELED billing should not be ACTIVE status
    if org.billing_status == BillingStatus.CANCELED:
        if org.status == OrganizationStatus.ACTIVE:
            issues.append(
                "Organization with CANCELED billing should not be ACTIVE "
                "(should be PENDING_CANCELLATION or TERMINATED)"
            )
    
    # FREE edition should have FREE billing
    if org.edition == Edition.FREE:
        if org.billing_status not in {BillingStatus.FREE, BillingStatus.TRIALING}:
            issues.append(
                f"FREE edition should have FREE or TRIALING billing status, "
                f"not {org.billing_status.value}"
            )
    
    return issues


def require_billing_consistency(org: Organization) -> None:
    """
    Require billing fields to be consistent.
    
    Raises:
        BillingInvariantViolation: If billing is inconsistent
    """
    issues = validate_billing_consistency(org)
    if issues:
        raise BillingInvariantViolation(
            f"Billing inconsistencies: {'; '.join(issues)}",
            field="billing"
        )


# ============================================================================
# DATE INVARIANTS
# ============================================================================

def validate_date_consistency(org: Organization) -> List[str]:
    """
    Validate date field consistency.
    
    Returns list of inconsistencies found.
    """
    issues = []
    now = datetime.now(timezone.utc)
    
    # created_at should not be in the future
    if org.created_at > now + timedelta(minutes=5):  # Small buffer for clock skew
        issues.append("created_at cannot be in the future")
    
    # updated_at should be >= created_at
    if org.updated_at < org.created_at:
        issues.append("updated_at cannot be before created_at")
    
    # subscription_started_at should be after created_at
    if org.subscription_started_at is not None:
        if org.subscription_started_at < org.created_at:
            issues.append("subscription_started_at cannot be before created_at")
    
    # subscription_ends_at should be after subscription_started_at
    if org.subscription_started_at and org.subscription_ends_at:
        if org.subscription_ends_at < org.subscription_started_at:
            issues.append("subscription_ends_at cannot be before subscription_started_at")
    
    # trial_ends_at should be after created_at
    if org.trial_ends_at is not None:
        if org.trial_ends_at < org.created_at:
            issues.append("trial_ends_at cannot be before created_at")
    
    # terminated_at should be after created_at
    if org.terminated_at is not None:
        if org.terminated_at < org.created_at:
            issues.append("terminated_at cannot be before created_at")
    
    # contract dates
    if org.contract_start_date and org.contract_end_date:
        if org.contract_end_date < org.contract_start_date:
            issues.append("contract_end_date cannot be before contract_start_date")
    
    # data_retention_until should be after terminated_at
    if org.terminated_at and org.data_retention_until:
        if org.data_retention_until < org.terminated_at:
            issues.append("data_retention_until cannot be before terminated_at")
    
    return issues


def require_date_consistency(org: Organization) -> None:
    """
    Require date fields to be consistent.
    
    Raises:
        DateInvariantViolation: If dates are inconsistent
    """
    issues = validate_date_consistency(org)
    if issues:
        raise DateInvariantViolation(
            f"Date inconsistencies: {'; '.join(issues)}",
            field="dates"
        )


# ============================================================================
# SUSPENSION INVARIANTS
# ============================================================================

def validate_suspension_info(suspension: SuspensionInfo) -> List[str]:
    """
    Validate suspension information.
    
    Returns list of issues found.
    """
    issues = []
    
    # Must have suspended_at
    if suspension.suspended_at is None:
        issues.append("Suspension must have suspended_at timestamp")
    
    # Must have a reason
    if suspension.reason is None:
        issues.append("Suspension must have a reason")
    
    # Must have severity
    if suspension.severity is None:
        issues.append("Suspension must have a severity level")
    
    # auto_resume_at must be after suspended_at
    if suspension.auto_resume_at and suspension.suspended_at:
        if suspension.auto_resume_at <= suspension.suspended_at:
            issues.append("auto_resume_at must be after suspended_at")
    
    # Description should not be empty
    if not suspension.description or not suspension.description.strip():
        issues.append("Suspension should have a description")
    
    return issues


def require_valid_suspension(suspension: SuspensionInfo) -> None:
    """
    Require suspension info to be valid.
    
    Raises:
        SuspensionInvariantViolation: If suspension is invalid
    """
    issues = validate_suspension_info(suspension)
    if issues:
        raise SuspensionInvariantViolation(
            f"Suspension issues: {'; '.join(issues)}",
            field="suspension_info"
        )


# ============================================================================
# SANDBOX INVARIANTS
# ============================================================================

def validate_sandbox_invariants(org: Organization) -> List[str]:
    """
    Validate sandbox-specific invariants.
    
    Returns list of issues found.
    """
    issues = []
    
    if org.org_type == OrganizationType.SANDBOX:
        # Sandbox must have parent_org_id
        if not org.parent_org_id:
            issues.append("Sandbox organization must have parent_org_id")
        
        # Sandbox should not be billed
        if org.billing_status not in {BillingStatus.FREE, BillingStatus.NOT_APPLICABLE}:
            issues.append("Sandbox organization should not have billing")
        
        # Sandbox edition should match or be lower than parent
        # (This would require loading parent - noted for application layer)
    
    if org.org_type == OrganizationType.PRODUCTION:
        # Production should not have parent_org_id
        if org.parent_org_id:
            issues.append("Production organization should not have parent_org_id")
    
    return issues


# ============================================================================
# COMPREHENSIVE VALIDATION
# ============================================================================

@dataclass
class ValidationResult:
    """Result of comprehensive validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]


def validate_organization(org: Organization) -> ValidationResult:
    """
    Perform comprehensive validation of an organization.
    
    Returns ValidationResult with all errors and warnings.
    """
    errors = []
    warnings = []
    
    # Name validation
    name_valid, name_error = validate_organization_name(org.name)
    if not name_valid:
        errors.append(f"Name: {name_error}")
    
    # ID validation
    id_valid, id_error = validate_org_id(org.org_id)
    if not id_valid:
        errors.append(f"ID: {id_error}")
    
    # Status consistency
    status_issues = validate_status_consistency(org)
    errors.extend([f"Status: {issue}" for issue in status_issues])
    
    # Billing consistency
    billing_issues = validate_billing_consistency(org)
    errors.extend([f"Billing: {issue}" for issue in billing_issues])
    
    # Date consistency
    date_issues = validate_date_consistency(org)
    errors.extend([f"Date: {issue}" for issue in date_issues])
    
    # Suspension validation (if suspended)
    if org.suspension_info:
        suspension_issues = validate_suspension_info(org.suspension_info)
        errors.extend([f"Suspension: {issue}" for issue in suspension_issues])
    
    # Sandbox validation
    sandbox_issues = validate_sandbox_invariants(org)
    errors.extend([f"Sandbox: {issue}" for issue in sandbox_issues])
    
    # Warnings (non-blocking issues)
    
    # Trial about to expire
    if org.status == OrganizationStatus.TRIAL and org.trial_ends_at:
        days_left = (org.trial_ends_at - datetime.now(timezone.utc)).days
        if days_left <= 3:
            warnings.append(f"Trial expires in {days_left} days")
    
    # Subscription about to end
    if org.subscription_ends_at:
        days_left = (org.subscription_ends_at - datetime.now(timezone.utc)).days
        if 0 < days_left <= 7:
            warnings.append(f"Subscription ends in {days_left} days")
    
    # No payment method
    if org.edition != Edition.FREE and not org.payment_method_on_file:
        warnings.append("No payment method on file for paid edition")
    
    # High usage (would need actual usage data)
    # warnings.append("Approaching API rate limit")
    
    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def require_valid_organization(org: Organization) -> None:
    """
    Require organization to pass all validations.
    
    Raises:
        InvariantViolation: If any validation fails
    """
    result = validate_organization(org)
    if not result.is_valid:
        raise InvariantViolation(
            f"Organization validation failed: {'; '.join(result.errors)}"
        )


# ============================================================================
# CREATION INVARIANTS
# ============================================================================

def validate_organization_creation(
    name: str,
    edition: Edition,
    region: Region,
    org_type: OrganizationType = OrganizationType.PRODUCTION,
    parent_org_id: Optional[str] = None,
) -> ValidationResult:
    """
    Validate parameters for creating a new organization.
    
    Called BEFORE creating the organization object.
    """
    errors = []
    warnings = []
    
    # Name validation
    name_valid, name_error = validate_organization_name(name)
    if not name_valid:
        errors.append(f"Name: {name_error}")
    
    # Sandbox requires parent
    if org_type == OrganizationType.SANDBOX and not parent_org_id:
        errors.append("Sandbox organization requires parent_org_id")
    
    # Production should not have parent
    if org_type == OrganizationType.PRODUCTION and parent_org_id:
        errors.append("Production organization should not have parent_org_id")
    
    # FREE edition warning
    if edition == Edition.FREE:
        warnings.append("FREE edition has limited features")
    
    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_valid_org_name(name: str) -> bool:
    """Quick check if name is valid."""
    valid, _ = validate_organization_name(name)
    return valid


def is_valid_org_id(org_id: str) -> bool:
    """Quick check if org_id is valid."""
    valid, _ = validate_org_id(org_id)
    return valid


def get_name_suggestions(invalid_name: str) -> List[str]:
    """
    Get suggestions for fixing an invalid organization name.
    
    Returns list of suggested valid names.
    """
    suggestions = []
    
    # Clean up the name
    cleaned = invalid_name.strip()
    
    # Remove forbidden characters
    for char in FORBIDDEN_NAME_CHARS:
        cleaned = cleaned.replace(char, '')
    
    # Ensure starts with alphanumeric
    if cleaned and not cleaned[0].isalnum():
        cleaned = 'X' + cleaned
    
    if cleaned and is_valid_org_name(cleaned):
        suggestions.append(cleaned)
    
    # Suggest normalized version
    normalized = normalize_organization_name(invalid_name)
    if normalized and is_valid_org_name(normalized):
        suggestions.append(normalized)
    
    return list(set(suggestions))  # Remove duplicates
