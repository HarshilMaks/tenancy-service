"""
Domain Models - Salesforce-style Organization (Tenant) System

This module defines the core domain entities for a multi-tenant platform
modeled after Salesforce's organization system. Pure Python with NO
framework dependencies - can be tested and modified independently.

Key Concepts (Salesforce terminology):
- Organization (Org) = Tenant = A customer company instance
- Edition = Plan Tier = What features/limits they have
- Sandbox vs Production = Environment type
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

# Type aliases
OrganizationId = UUID


# ============================================================================
# ENUMS - Allowed values (Salesforce-style)
# ============================================================================

class OrganizationStatus(Enum):
    """
    Organization lifecycle states.
    
    Modeled after Salesforce org states with additional states for
    modern SaaS requirements.
    """
    PROVISIONING = "provisioning"      # Initial setup in progress
    TRIAL = "trial"                     # Free trial period
    ACTIVE = "active"                   # Paid, normal operation
    SUSPENDED = "suspended"             # Temporarily disabled
    PENDING_CANCELLATION = "pending_cancellation"  # Will terminate at period end
    PENDING_TERMINATION = "pending_termination"    # Immediate termination scheduled
    MIGRATING = "migrating"             # Data migration in progress
    TERMINATED = "terminated"           # Soft-deleted, can restore within retention


class SuspensionSeverity(Enum):
    """
    Suspension severity levels - determines what access remains.
    """
    SOFT = "soft"          # Read-only access, can self-resolve
    HARD = "hard"          # No access, must contact support
    SECURITY = "security"  # Security incident, requires verification


class SuspensionReason(Enum):
    """
    Predefined suspension reasons for consistency.
    """
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_OVERDUE = "payment_overdue"
    TERMS_VIOLATION = "terms_violation"
    SECURITY_THREAT = "security_threat"
    ABUSE_DETECTED = "abuse_detected"
    LEGAL_REQUEST = "legal_request"
    ADMIN_ACTION = "admin_action"
    TRIAL_EXPIRED = "trial_expired"


class Edition(Enum):
    """
    Salesforce-style Editions (Plan Tiers).
    
    Modeled after Salesforce Sales Cloud editions:
    - Free: Limited free tier for small teams
    - Essentials: Small business basics
    - Professional: Complete CRM for any size team
    - Enterprise: Deeply customizable CRM
    - Unlimited: Unlimited CRM power and support
    """
    FREE = "free"                   # Free forever, limited features
    ESSENTIALS = "essentials"       # $25/user/month equivalent
    PROFESSIONAL = "professional"   # $75/user/month equivalent
    ENTERPRISE = "enterprise"       # $150/user/month equivalent
    UNLIMITED = "unlimited"         # $300/user/month equivalent


class SubscriptionType(Enum):
    """
    Types of subscription billing models.
    """
    MONTHLY = "monthly"             # Monthly billing cycle
    ANNUAL = "annual"               # Annual billing cycle
    USAGE_BASED = "usage_based"     # Pay-per-use model
    PERPETUAL = "perpetual"         # One-time license
    CUSTOM = "custom"               # Enterprise custom terms


class BillingStatus(Enum):
    """
    Billing account status.
    """
    ACTIVE = "active"           # Payments current
    PAST_DUE = "past_due"       # Payment overdue
    CANCELLED = "cancelled"     # Subscription cancelled
    PAUSED = "paused"           # Temporarily paused
    TRIAL = "trial"             # In trial period


class BillingFrequency(Enum):
    """
    Billing cycle frequency.
    """
    MONTHLY = "monthly"
    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    CUSTOM = "custom"


class OrganizationType(Enum):
    """
    Salesforce-style organization types.
    """
    PRODUCTION = "production"       # Live customer data
    SANDBOX = "sandbox"             # Testing/development copy
    DEVELOPER = "developer"         # Developer edition
    TRIAL = "trial"                 # Trial organization
    SCRATCH = "scratch"             # Temporary dev org


class ComplianceStandard(Enum):
    """
    Supported compliance standards for production systems.
    """
    GDPR = "gdpr"           # EU General Data Protection Regulation
    SOC2 = "soc2"           # Service Organization Control 2
    HIPAA = "hipaa"         # Health Insurance Portability (US Healthcare)
    ISO27001 = "iso27001"   # Information Security Management
    PCI_DSS = "pci_dss"     # Payment Card Industry Data Security
    CCPA = "ccpa"           # California Consumer Privacy Act
    FedRAMP = "fedramp"     # US Federal Risk Authorization


class Region(Enum):
    """
    Available deployment regions with data residency.
    """
    # North America
    US_EAST_1 = "us-east-1"         # Virginia
    US_WEST_1 = "us-west-1"         # N. California
    US_WEST_2 = "us-west-2"         # Oregon
    CA_CENTRAL_1 = "ca-central-1"   # Canada
    
    # Europe
    EU_WEST_1 = "eu-west-1"         # Ireland
    EU_CENTRAL_1 = "eu-central-1"   # Frankfurt
    EU_WEST_2 = "eu-west-2"         # London
    
    # Asia Pacific
    AP_SOUTHEAST_1 = "ap-southeast-1"  # Singapore
    AP_NORTHEAST_1 = "ap-northeast-1"  # Tokyo
    AP_SOUTH_1 = "ap-south-1"          # Mumbai
    
    # Australia
    AP_SOUTHEAST_2 = "ap-southeast-2"  # Sydney


class OnboardingStep(Enum):
    """
    Onboarding progress tracking steps.
    """
    ACCOUNT_CREATED = "account_created"
    EMAIL_VERIFIED = "email_verified"
    PROFILE_COMPLETED = "profile_completed"
    FIRST_USER_INVITED = "first_user_invited"
    FIRST_RECORD_CREATED = "first_record_created"
    INTEGRATION_CONNECTED = "integration_connected"
    ONBOARDING_COMPLETED = "onboarding_completed"


# ============================================================================
# VALUE OBJECTS - Immutable sub-objects
# ============================================================================

@dataclass(frozen=True)
class PolicyDecision:
    """
    Result of policy evaluation.
    
    Returned by policy checks to indicate whether an action is allowed.
    """
    allowed: bool
    reason: Optional[str] = None
    error_code: Optional[str] = None
    throttle_after: Optional[int] = None  # Soft limit warning
    retry_after_seconds: Optional[int] = None
    upgrade_required: bool = False
    
    @classmethod
    def allow(cls) -> "PolicyDecision":
        return cls(allowed=True)
    
    @classmethod
    def deny(cls, reason: str, error_code: str = "DENIED") -> "PolicyDecision":
        return cls(allowed=False, reason=reason, error_code=error_code)
    
    @classmethod
    def upgrade_needed(cls, reason: str, current_limit: int) -> "PolicyDecision":
        return cls(
            allowed=False, 
            reason=reason, 
            error_code="LIMIT_EXCEEDED",
            upgrade_required=True,
            throttle_after=current_limit
        )


@dataclass(frozen=True)
class BillingInfo:
    """
    Organization billing information.
    
    Stores billing details including subscription type, status, and payment info.
    """
    subscription_type: Optional[SubscriptionType] = None
    billing_status: Optional[BillingStatus] = None
    billing_frequency: Optional[BillingFrequency] = None
    next_billing_date: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    subscription_started_at: Optional[datetime] = None
    payment_method_id: Optional[str] = None
    billing_contact_email: Optional[str] = None
    tax_id: Optional[str] = None
    
    def is_trial_active(self) -> bool:
        """Check if trial period is still active."""
        if not self.trial_ends_at:
            return False
        return datetime.now(timezone.utc) < self.trial_ends_at
    
    def is_billing_overdue(self) -> bool:
        """Check if billing is overdue."""
        return self.billing_status == BillingStatus.PAST_DUE
    
    def days_until_trial_expires(self) -> Optional[int]:
        """Get days until trial expires."""
        if not self.trial_ends_at:
            return None
        delta = self.trial_ends_at - datetime.now(timezone.utc)
        return max(0, delta.days)


@dataclass(frozen=True)
class Address:
    """
    Organization billing/physical address.
    """
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "US"


@dataclass(frozen=True)
class RegionalSettings:
    """
    Regional configuration and data residency settings.
    """
    primary_region: Region
    data_residency_requirements: List[str] = field(default_factory=list)
    compliance_standards: List[ComplianceStandard] = field(default_factory=list)
    timezone: str = "UTC"
    locale: str = "en-US"
    currency: str = "USD"
    
    def is_gdpr_required(self) -> bool:
        """Check if GDPR compliance is required."""
        return ComplianceStandard.GDPR in self.compliance_standards
    
    def is_ccpa_required(self) -> bool:
        """Check if CCPA compliance is required."""
        return ComplianceStandard.CCPA in self.compliance_standards


@dataclass(frozen=True)
class SuspensionInfo:
    """
    Details about an organization's suspension.
    """
    reason: SuspensionReason
    severity: SuspensionSeverity
    description: str
    suspended_at: datetime
    suspended_by: Optional[str] = None  # Admin user ID or "SYSTEM"
    auto_resume_at: Optional[datetime] = None  # For soft suspensions
    ticket_id: Optional[str] = None  # Support ticket reference


# ============================================================================
# AGGREGATE ROOT - Organization (Tenant)
# ============================================================================

@dataclass
class Organization:
    """
    Organization Aggregate Root - Salesforce-style Tenant.
    
    This is the central domain concept representing a customer's instance:
    - Called "Organization" or "Org" (Salesforce terminology)
    - Each customer company = one Organization
    - All data is isolated by org_id
    
    Key responsibilities:
    - Define WHO owns the data (isolation boundary)
    - Define WHAT they can do (edition limits, features)
    - Define WHERE they operate (region, compliance)
    - Define WHEN they can use platform (status, subscription dates)
    """
    
    # ========================================================================
    # IDENTITY - Salesforce Org ID style
    # ========================================================================
    
    id: UUID  # Internal UUID
    org_id: str  # Salesforce-style: "00D5g00000Bq8QUEAZ" format
    name: str  # Display name: "Acme Corporation"
    normalized_name: str  # Lowercase for uniqueness checks
    
    # External references
    external_id: Optional[str] = None  # CRM/ERP reference
    instance_url: Optional[str] = None  # https://acme.myplatform.com
    
    # Organization type
    org_type: OrganizationType = OrganizationType.PRODUCTION
    parent_org_id: Optional[str] = None  # For sandbox orgs, points to production
    
    # ========================================================================
    # LIFECYCLE - Current state
    # ========================================================================
    
    status: OrganizationStatus = OrganizationStatus.PROVISIONING
    
    # Suspension details (only populated when status=SUSPENDED)
    suspension_info: Optional[SuspensionInfo] = None
    
    # Termination (soft delete)
    terminated_at: Optional[datetime] = None
    termination_reason: Optional[str] = None
    data_retention_until: Optional[datetime] = None  # When data will be purged
    
    # ========================================================================
    # SUBSCRIPTION & EDITION
    # ========================================================================
    
    edition: Edition = Edition.FREE
    
    # Plan limits (overrides default edition limits for custom deals)
    custom_limits: Dict[str, Any] = field(default_factory=dict)
    
    # Feature flags (per-org feature toggles)
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    
    # API limits
    api_requests_per_day: Optional[int] = None  # None = use edition default
    api_requests_per_second: Optional[int] = None
    
    # ========================================================================
    # BILLING
    # ========================================================================
    
    billing_status: BillingStatus = BillingStatus.TRIAL
    billing_frequency: BillingFrequency = BillingFrequency.MONTHLY
    billing_account_id: Optional[str] = None  # Stripe/Chargebee customer ID
    
    # Subscription dates
    trial_started_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    subscription_started_at: Optional[datetime] = None
    subscription_ends_at: Optional[datetime] = None  # Contract end date
    
    # Payment
    payment_method_on_file: bool = False
    last_payment_at: Optional[datetime] = None
    next_billing_at: Optional[datetime] = None
    
    # Revenue tracking
    monthly_recurring_revenue: Optional[float] = None  # MRR in cents
    annual_contract_value: Optional[float] = None  # ACV for enterprise
    
    # ========================================================================
    # CONTRACT DETAILS
    # ========================================================================
    
    contract_start_date: Optional[datetime] = None
    contract_end_date: Optional[datetime] = None
    auto_renew: bool = True
    contract_term_months: int = 12
    
    # Seats/Users
    licensed_users: int = 1  # Paid seats
    max_users: Optional[int] = None  # Hard limit (None = unlimited for edition)
    
    # ========================================================================
    # REGIONAL & COMPLIANCE
    # ========================================================================
    
    region: Region = Region.US_EAST_1
    compliance_requirements: List[ComplianceStandard] = field(default_factory=list)
    
    # Data residency
    data_residency_locked: bool = False  # If true, cannot migrate regions
    secondary_region: Optional[Region] = None  # For DR/backup
    
    # ========================================================================
    # ONBOARDING
    # ========================================================================
    
    onboarding_completed: bool = False
    onboarding_step: OnboardingStep = OnboardingStep.ACCOUNT_CREATED
    onboarding_completed_at: Optional[datetime] = None
    
    # Activation
    first_login_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None  # When they started really using
    
    # ========================================================================
    # USAGE TRACKING
    # ========================================================================
    
    last_active_at: Optional[datetime] = None
    total_logins: int = 0
    total_api_calls: int = 0
    storage_used_bytes: int = 0
    
    # Record counts (cached for quick checks)
    record_count: Dict[str, int] = field(default_factory=dict)
    # Example: {"contacts": 1500, "tickets": 3200, "users": 25}
    
    # ========================================================================
    # CONTACT & ADDRESS
    # ========================================================================
    
    billing_email: Optional[str] = None
    technical_contact_email: Optional[str] = None
    billing_address: Optional[Address] = None
    
    # Account management
    account_manager_id: Optional[str] = None  # Internal sales rep
    success_manager_id: Optional[str] = None  # CSM
    
    # ========================================================================
    # METADATA
    # ========================================================================
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Flexible storage for:
    # - industry, company_size, employee_count
    # - signup_source, referral_code
    # - custom_notes, tags
    
    # ========================================================================
    # AUDITING
    # ========================================================================
    
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = None  # User ID who created
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: Optional[str] = None  # Last user who modified
    
    # Optimistic locking
    version: int = 1
    
    # ========================================================================
    # BUSINESS LOGIC METHODS
    # ========================================================================
    
    # --- Status Checks ---
    
    def is_active(self) -> bool:
        """Check if org is in active operational state."""
        return self.status == OrganizationStatus.ACTIVE
    
    def is_trial(self) -> bool:
        """Check if org is in trial period."""
        return self.status == OrganizationStatus.TRIAL
    
    def is_suspended(self) -> bool:
        """Check if org is currently suspended."""
        return self.status == OrganizationStatus.SUSPENDED
    
    def is_terminated(self) -> bool:
        """Check if org is terminated (soft deleted)."""
        return self.status == OrganizationStatus.TERMINATED
    
    def is_pending_cancellation(self) -> bool:
        """Check if org is pending cancellation."""
        return self.status == OrganizationStatus.PENDING_CANCELLATION
    
    def is_migrating(self) -> bool:
        """Check if org is currently migrating."""
        return self.status == OrganizationStatus.MIGRATING
    
    def can_perform_operations(self) -> bool:
        """Check if org can perform platform operations."""
        return self.status in [
            OrganizationStatus.ACTIVE,
            OrganizationStatus.TRIAL,
            OrganizationStatus.PENDING_CANCELLATION
        ]
    
    def can_read_data(self) -> bool:
        """Check if org can read their data (even if suspended)."""
        # Soft suspension allows read access
        if self.is_suspended() and self.suspension_info:
            return self.suspension_info.severity == SuspensionSeverity.SOFT
        return self.can_perform_operations()
    
    def is_in_grace_period(self) -> bool:
        """Check if terminated org is still in data retention period."""
        if not self.is_terminated() or not self.data_retention_until:
            return False
        return datetime.now(timezone.utc) < self.data_retention_until
    
    # --- Trial Checks ---
    
    def trial_days_remaining(self) -> Optional[int]:
        """Get number of days remaining in trial."""
        if not self.trial_ends_at:
            return None
        delta = self.trial_ends_at - datetime.now(timezone.utc)
        return max(0, delta.days)
    
    def is_trial_expired(self) -> bool:
        """Check if trial has expired."""
        if not self.trial_ends_at:
            return False
        return datetime.now(timezone.utc) > self.trial_ends_at
    
    # --- Plan & Limits ---
    
    def get_limit(self, limit_key: str) -> Optional[int]:
        """
        Get a specific limit value.
        
        Checks custom_limits first, then falls back to edition defaults.
        """
        if limit_key in self.custom_limits:
            return self.custom_limits[limit_key]
        return None  # Edition defaults handled by PlanPolicy
    
    def has_feature(self, feature_name: str) -> bool:
        """Check if org has access to a feature."""
        # Check per-org feature flags first
        if feature_name in self.feature_flags:
            return self.feature_flags[feature_name]
        return False  # Edition defaults handled by PlanPolicy
    
    def exceeds_limit(self, limit_key: str, current_value: int, limit: int) -> bool:
        """Check if current usage exceeds limit."""
        return current_value >= limit
    
    def exceeds_user_limit(self) -> bool:
        """Check if org has exceeded user license limit."""
        if self.max_users is None:
            return False
        current_users = self.record_count.get("users", 0)
        return current_users >= self.max_users
    
    # --- Billing ---
    
    def is_payment_overdue(self) -> bool:
        """Check if payment is overdue."""
        return self.billing_status == BillingStatus.PAST_DUE
    
    def has_valid_payment_method(self) -> bool:
        """Check if org has a valid payment method."""
        return self.payment_method_on_file
    
    def needs_payment_method(self) -> bool:
        """Check if org needs to add payment method (trial ending)."""
        if self.edition == Edition.FREE:
            return False
        if self.is_trial() and self.trial_days_remaining() and self.trial_days_remaining() <= 7:
            return not self.payment_method_on_file
        return False
    
    # --- Compliance ---
    
    def requires_compliance(self, standard: ComplianceStandard) -> bool:
        """Check if org is subject to a compliance standard."""
        return standard in self.compliance_requirements
    
    def is_gdpr_applicable(self) -> bool:
        """Check if GDPR applies (EU region or explicit requirement)."""
        eu_regions = [Region.EU_WEST_1, Region.EU_CENTRAL_1, Region.EU_WEST_2]
        return self.region in eu_regions or ComplianceStandard.GDPR in self.compliance_requirements
    
    # --- Onboarding ---
    
    def complete_onboarding_step(self, step: OnboardingStep) -> None:
        """Mark an onboarding step as complete."""
        self.onboarding_step = step
        if step == OnboardingStep.ONBOARDING_COMPLETED:
            self.onboarding_completed = True
            self.onboarding_completed_at = datetime.now(timezone.utc)
        self._mark_updated()
    
    # ========================================================================
    # STATE CHANGE METHODS
    # ========================================================================
    
    def activate(self) -> None:
        """Activate org from provisioning or trial state."""
        self.status = OrganizationStatus.ACTIVE
        self.activated_at = datetime.now(timezone.utc)
        self._mark_updated()
    
    def start_trial(self, trial_days: int = 14) -> None:
        """Start trial period."""
        self.status = OrganizationStatus.TRIAL
        self.trial_started_at = datetime.now(timezone.utc)
        self.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=trial_days)
        self.billing_status = BillingStatus.TRIAL
        self._mark_updated()
    
    def suspend(self, info: SuspensionInfo) -> None:
        """Suspend the organization."""
        self.status = OrganizationStatus.SUSPENDED
        self.suspension_info = info
        self._mark_updated()
    
    def resume(self) -> None:
        """Resume a suspended organization."""
        self.status = OrganizationStatus.ACTIVE
        self.suspension_info = None
        self._mark_updated()
    
    def start_cancellation(self) -> None:
        """Mark org as pending cancellation."""
        self.status = OrganizationStatus.PENDING_CANCELLATION
        self._mark_updated()
    
    def start_migration(self) -> None:
        """Mark org as migrating."""
        self.status = OrganizationStatus.MIGRATING
        self._mark_updated()
    
    def complete_migration(self, new_region: Region) -> None:
        """Complete migration to new region."""
        self.region = new_region
        self.status = OrganizationStatus.ACTIVE
        self._mark_updated()
    
    def terminate(self, reason: str, retention_days: int = 90) -> None:
        """Soft delete the organization."""
        self.status = OrganizationStatus.TERMINATED
        self.terminated_at = datetime.now(timezone.utc)
        self.termination_reason = reason
        self.data_retention_until = datetime.now(timezone.utc) + timedelta(days=retention_days)
        self._mark_updated()
    
    def restore(self) -> None:
        """Restore a terminated org within retention period."""
        if not self.is_in_grace_period():
            raise ValueError("Cannot restore org outside retention period")
        self.status = OrganizationStatus.ACTIVE
        self.terminated_at = None
        self.termination_reason = None
        self.data_retention_until = None
        self._mark_updated()
    
    def change_edition(self, new_edition: Edition, new_limits: Optional[Dict] = None) -> None:
        """Change org's edition (upgrade/downgrade)."""
        self.edition = new_edition
        if new_limits:
            self.custom_limits = new_limits
        self._mark_updated()
    
    def update_billing(
        self,
        status: Optional[BillingStatus] = None,
        payment_method: Optional[bool] = None,
        next_billing: Optional[datetime] = None
    ) -> None:
        """Update billing information."""
        if status:
            self.billing_status = status
        if payment_method is not None:
            self.payment_method_on_file = payment_method
        if next_billing:
            self.next_billing_at = next_billing
        self._mark_updated()
    
    def record_activity(self) -> None:
        """Record that org was active (called on any operation)."""
        self.last_active_at = datetime.now(timezone.utc)
    
    def increment_usage(self, metric: str, amount: int = 1) -> None:
        """Increment a usage counter."""
        if metric == "api_calls":
            self.total_api_calls += amount
        elif metric == "logins":
            self.total_logins += amount
        else:
            self.record_count[metric] = self.record_count.get(metric, 0) + amount
    
    def _mark_updated(self) -> None:
        """Internal: Update timestamp and version."""
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
    
    # ========================================================================
    # UTILITIES
    # ========================================================================
    
    def __repr__(self) -> str:
        return (
            f"Organization(org_id='{self.org_id}', name='{self.name}', "
            f"status={self.status.value}, edition={self.edition.value})"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "org_id": self.org_id,
            "name": self.name,
            "status": self.status.value,
            "edition": self.edition.value,
            "region": self.region.value,
            "created_at": self.created_at.isoformat(),
        }
