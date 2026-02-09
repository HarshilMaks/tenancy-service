"""
Organization Policies - Edition Limits and Feature Definitions

This module defines what each Salesforce-style Edition can do.
Modeled after Salesforce's pricing tiers with modern SaaS features.

Edition Hierarchy (like Salesforce):
┌──────────────────────────────────────────────────────────────────────────────┐
│  UNLIMITED    │ Everything + Premier Support + Unlimited Storage            │
├──────────────────────────────────────────────────────────────────────────────┤
│  ENTERPRISE   │ Full customization + Advanced Analytics + API Priority       │
├──────────────────────────────────────────────────────────────────────────────┤
│  PROFESSIONAL │ Full CRM + Reports + API Access + Integrations              │
├──────────────────────────────────────────────────────────────────────────────┤
│  ESSENTIALS   │ Basic CRM + Limited Users + Email Support                   │
├──────────────────────────────────────────────────────────────────────────────┤
│  FREE         │ Trial/Freemium - Very Limited                               │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from enum import Enum

from domain.models import Edition, Organization, OrganizationStatus


# ============================================================================
# FEATURE FLAGS
# ============================================================================

class Feature(str, Enum):
    """
    Available platform features.
    
    Features are tied to Editions and can be overridden per-organization.
    """
    # Core Features
    TICKET_MANAGEMENT = "ticket_management"
    KNOWLEDGE_BASE = "knowledge_base"
    CUSTOMER_PORTAL = "customer_portal"
    LIVE_CHAT = "live_chat"
    EMAIL_INTEGRATION = "email_integration"
    
    # Advanced Features
    CUSTOM_FIELDS = "custom_fields"
    CUSTOM_WORKFLOWS = "custom_workflows"
    AUTOMATION_RULES = "automation_rules"
    SLA_MANAGEMENT = "sla_management"
    ESCALATION_RULES = "escalation_rules"
    
    # Analytics
    BASIC_REPORTS = "basic_reports"
    ADVANCED_ANALYTICS = "advanced_analytics"
    CUSTOM_DASHBOARDS = "custom_dashboards"
    FORECASTING = "forecasting"
    AI_INSIGHTS = "ai_insights"
    
    # Integration
    REST_API = "rest_api"
    WEBHOOKS = "webhooks"
    SSO = "sso"
    LDAP_INTEGRATION = "ldap_integration"
    THIRD_PARTY_APPS = "third_party_apps"
    
    # Communication
    MULTI_CHANNEL = "multi_channel"
    SOCIAL_MEDIA = "social_media"
    VOICE_SUPPORT = "voice_support"
    VIDEO_SUPPORT = "video_support"
    
    # Security & Compliance
    AUDIT_LOGS = "audit_logs"
    IP_WHITELIST = "ip_whitelist"
    DATA_ENCRYPTION = "data_encryption"
    FIELD_LEVEL_SECURITY = "field_level_security"
    DATA_RETENTION_POLICIES = "data_retention_policies"
    
    # Enterprise Features
    SANDBOX_ENVIRONMENTS = "sandbox_environments"
    MULTI_ORG = "multi_org"
    UNLIMITED_STORAGE = "unlimited_storage"
    PRIORITY_SUPPORT = "priority_support"
    DEDICATED_SUCCESS_MANAGER = "dedicated_success_manager"


# ============================================================================
# EDITION LIMITS
# ============================================================================

@dataclass(frozen=True)
class EditionLimits:
    """
    Defines the hard limits for each Edition.
    
    All limits are enforced at the application layer.
    """
    # User Limits
    max_users: int
    max_admin_users: int
    max_read_only_users: int  # "Light" users in Salesforce terms
    
    # Data Limits
    max_storage_gb: int
    max_file_storage_gb: int
    max_api_calls_per_day: int
    max_api_calls_per_minute: int
    
    # Feature Limits
    max_custom_fields: int
    max_custom_objects: int
    max_workflows: int
    max_automation_rules: int
    max_reports: int
    max_dashboards: int
    
    # Ticket Limits
    max_tickets_per_month: int  # 0 = unlimited
    max_sla_policies: int
    max_escalation_rules: int
    
    # Integration Limits
    max_webhooks: int
    max_api_keys: int
    max_connected_apps: int
    
    # Environment Limits
    max_sandboxes: int
    
    # Support
    support_tier: str  # "community", "email", "phone", "premier"
    support_response_hours: int  # Target SLA for support


# Pre-defined Edition Limits (Salesforce-style)
EDITION_LIMITS: Dict[Edition, EditionLimits] = {
    # ========================================================================
    # FREE - Trial/Freemium Tier
    # ========================================================================
    Edition.FREE: EditionLimits(
        max_users=2,
        max_admin_users=1,
        max_read_only_users=0,
        max_storage_gb=1,
        max_file_storage_gb=1,
        max_api_calls_per_day=1_000,
        max_api_calls_per_minute=10,
        max_custom_fields=5,
        max_custom_objects=0,
        max_workflows=2,
        max_automation_rules=2,
        max_reports=5,
        max_dashboards=1,
        max_tickets_per_month=100,
        max_sla_policies=1,
        max_escalation_rules=1,
        max_webhooks=1,
        max_api_keys=1,
        max_connected_apps=0,
        max_sandboxes=0,
        support_tier="community",
        support_response_hours=72,
    ),
    
    # ========================================================================
    # ESSENTIALS - Small Business
    # ========================================================================
    Edition.ESSENTIALS: EditionLimits(
        max_users=10,
        max_admin_users=2,
        max_read_only_users=5,
        max_storage_gb=10,
        max_file_storage_gb=10,
        max_api_calls_per_day=10_000,
        max_api_calls_per_minute=60,
        max_custom_fields=25,
        max_custom_objects=5,
        max_workflows=10,
        max_automation_rules=10,
        max_reports=25,
        max_dashboards=5,
        max_tickets_per_month=1_000,
        max_sla_policies=3,
        max_escalation_rules=5,
        max_webhooks=5,
        max_api_keys=3,
        max_connected_apps=3,
        max_sandboxes=0,
        support_tier="email",
        support_response_hours=48,
    ),
    
    # ========================================================================
    # PROFESSIONAL - Growing Business
    # ========================================================================
    Edition.PROFESSIONAL: EditionLimits(
        max_users=50,
        max_admin_users=5,
        max_read_only_users=25,
        max_storage_gb=50,
        max_file_storage_gb=50,
        max_api_calls_per_day=100_000,
        max_api_calls_per_minute=200,
        max_custom_fields=100,
        max_custom_objects=25,
        max_workflows=50,
        max_automation_rules=50,
        max_reports=100,
        max_dashboards=25,
        max_tickets_per_month=10_000,
        max_sla_policies=10,
        max_escalation_rules=25,
        max_webhooks=25,
        max_api_keys=10,
        max_connected_apps=10,
        max_sandboxes=1,
        support_tier="email",
        support_response_hours=24,
    ),
    
    # ========================================================================
    # ENTERPRISE - Large Organizations
    # ========================================================================
    Edition.ENTERPRISE: EditionLimits(
        max_users=500,
        max_admin_users=25,
        max_read_only_users=250,
        max_storage_gb=500,
        max_file_storage_gb=500,
        max_api_calls_per_day=1_000_000,
        max_api_calls_per_minute=1_000,
        max_custom_fields=500,
        max_custom_objects=100,
        max_workflows=200,
        max_automation_rules=200,
        max_reports=500,
        max_dashboards=100,
        max_tickets_per_month=0,  # Unlimited
        max_sla_policies=50,
        max_escalation_rules=100,
        max_webhooks=100,
        max_api_keys=50,
        max_connected_apps=50,
        max_sandboxes=5,
        support_tier="phone",
        support_response_hours=8,
    ),
    
    # ========================================================================
    # UNLIMITED - Enterprise Plus
    # ========================================================================
    Edition.UNLIMITED: EditionLimits(
        max_users=0,  # 0 = Unlimited
        max_admin_users=0,
        max_read_only_users=0,
        max_storage_gb=0,  # Unlimited
        max_file_storage_gb=0,
        max_api_calls_per_day=0,  # Unlimited
        max_api_calls_per_minute=0,
        max_custom_fields=0,
        max_custom_objects=0,
        max_workflows=0,
        max_automation_rules=0,
        max_reports=0,
        max_dashboards=0,
        max_tickets_per_month=0,
        max_sla_policies=0,
        max_escalation_rules=0,
        max_webhooks=0,
        max_api_keys=0,
        max_connected_apps=0,
        max_sandboxes=0,  # Unlimited
        support_tier="premier",
        support_response_hours=1,
    ),
}


# ============================================================================
# EDITION FEATURES
# ============================================================================

# Features available per Edition
EDITION_FEATURES: Dict[Edition, Set[Feature]] = {
    Edition.FREE: {
        Feature.TICKET_MANAGEMENT,
        Feature.BASIC_REPORTS,
        Feature.EMAIL_INTEGRATION,
    },
    
    Edition.ESSENTIALS: {
        Feature.TICKET_MANAGEMENT,
        Feature.KNOWLEDGE_BASE,
        Feature.CUSTOMER_PORTAL,
        Feature.EMAIL_INTEGRATION,
        Feature.BASIC_REPORTS,
        Feature.CUSTOM_FIELDS,
        Feature.REST_API,
        Feature.SLA_MANAGEMENT,
    },
    
    Edition.PROFESSIONAL: {
        Feature.TICKET_MANAGEMENT,
        Feature.KNOWLEDGE_BASE,
        Feature.CUSTOMER_PORTAL,
        Feature.LIVE_CHAT,
        Feature.EMAIL_INTEGRATION,
        Feature.CUSTOM_FIELDS,
        Feature.CUSTOM_WORKFLOWS,
        Feature.AUTOMATION_RULES,
        Feature.SLA_MANAGEMENT,
        Feature.ESCALATION_RULES,
        Feature.BASIC_REPORTS,
        Feature.ADVANCED_ANALYTICS,
        Feature.CUSTOM_DASHBOARDS,
        Feature.REST_API,
        Feature.WEBHOOKS,
        Feature.SSO,
        Feature.THIRD_PARTY_APPS,
        Feature.MULTI_CHANNEL,
        Feature.AUDIT_LOGS,
    },
    
    Edition.ENTERPRISE: {
        # All Professional features plus:
        Feature.TICKET_MANAGEMENT,
        Feature.KNOWLEDGE_BASE,
        Feature.CUSTOMER_PORTAL,
        Feature.LIVE_CHAT,
        Feature.EMAIL_INTEGRATION,
        Feature.CUSTOM_FIELDS,
        Feature.CUSTOM_WORKFLOWS,
        Feature.AUTOMATION_RULES,
        Feature.SLA_MANAGEMENT,
        Feature.ESCALATION_RULES,
        Feature.BASIC_REPORTS,
        Feature.ADVANCED_ANALYTICS,
        Feature.CUSTOM_DASHBOARDS,
        Feature.FORECASTING,
        Feature.AI_INSIGHTS,
        Feature.REST_API,
        Feature.WEBHOOKS,
        Feature.SSO,
        Feature.LDAP_INTEGRATION,
        Feature.THIRD_PARTY_APPS,
        Feature.MULTI_CHANNEL,
        Feature.SOCIAL_MEDIA,
        Feature.VOICE_SUPPORT,
        Feature.AUDIT_LOGS,
        Feature.IP_WHITELIST,
        Feature.DATA_ENCRYPTION,
        Feature.FIELD_LEVEL_SECURITY,
        Feature.SANDBOX_ENVIRONMENTS,
    },
    
    Edition.UNLIMITED: {
        # All features
        Feature.TICKET_MANAGEMENT,
        Feature.KNOWLEDGE_BASE,
        Feature.CUSTOMER_PORTAL,
        Feature.LIVE_CHAT,
        Feature.EMAIL_INTEGRATION,
        Feature.CUSTOM_FIELDS,
        Feature.CUSTOM_WORKFLOWS,
        Feature.AUTOMATION_RULES,
        Feature.SLA_MANAGEMENT,
        Feature.ESCALATION_RULES,
        Feature.BASIC_REPORTS,
        Feature.ADVANCED_ANALYTICS,
        Feature.CUSTOM_DASHBOARDS,
        Feature.FORECASTING,
        Feature.AI_INSIGHTS,
        Feature.REST_API,
        Feature.WEBHOOKS,
        Feature.SSO,
        Feature.LDAP_INTEGRATION,
        Feature.THIRD_PARTY_APPS,
        Feature.MULTI_CHANNEL,
        Feature.SOCIAL_MEDIA,
        Feature.VOICE_SUPPORT,
        Feature.VIDEO_SUPPORT,
        Feature.AUDIT_LOGS,
        Feature.IP_WHITELIST,
        Feature.DATA_ENCRYPTION,
        Feature.FIELD_LEVEL_SECURITY,
        Feature.DATA_RETENTION_POLICIES,
        Feature.SANDBOX_ENVIRONMENTS,
        Feature.MULTI_ORG,
        Feature.UNLIMITED_STORAGE,
        Feature.PRIORITY_SUPPORT,
        Feature.DEDICATED_SUCCESS_MANAGER,
    },
}


# ============================================================================
# EDITION PRICING (for reference - actual billing is in billing service)
# ============================================================================

@dataclass(frozen=True)
class EditionPricing:
    """Edition pricing information."""
    monthly_price_per_user: float
    annual_price_per_user: float  # Usually discounted
    min_users: int
    setup_fee: float


EDITION_PRICING: Dict[Edition, EditionPricing] = {
    Edition.FREE: EditionPricing(
        monthly_price_per_user=0.0,
        annual_price_per_user=0.0,
        min_users=1,
        setup_fee=0.0,
    ),
    Edition.ESSENTIALS: EditionPricing(
        monthly_price_per_user=25.0,
        annual_price_per_user=20.0,  # 20% annual discount
        min_users=1,
        setup_fee=0.0,
    ),
    Edition.PROFESSIONAL: EditionPricing(
        monthly_price_per_user=75.0,
        annual_price_per_user=60.0,
        min_users=5,
        setup_fee=0.0,
    ),
    Edition.ENTERPRISE: EditionPricing(
        monthly_price_per_user=150.0,
        annual_price_per_user=120.0,
        min_users=10,
        setup_fee=500.0,
    ),
    Edition.UNLIMITED: EditionPricing(
        monthly_price_per_user=300.0,
        annual_price_per_user=250.0,
        min_users=25,
        setup_fee=1000.0,
    ),
}


# ============================================================================
# POLICY CHECKER
# ============================================================================

class PolicyViolation(Exception):
    """Raised when a policy check fails."""
    
    def __init__(self, feature: str, limit: str, current: Any, allowed: Any):
        self.feature = feature
        self.limit = limit
        self.current = current
        self.allowed = allowed
        super().__init__(
            f"Policy violation: {feature} - {limit}. "
            f"Current: {current}, Allowed: {allowed}"
        )


class OrganizationPolicy:
    """
    Enforces policies and limits for an Organization.
    
    This is the main interface for checking what an org can do.
    """
    
    def __init__(self, org: Organization):
        self.org = org
        self._limits = EDITION_LIMITS.get(org.edition, EDITION_LIMITS[Edition.FREE])
        self._features = EDITION_FEATURES.get(org.edition, EDITION_FEATURES[Edition.FREE])
    
    # ========================================================================
    # FEATURE CHECKS
    # ========================================================================
    
    def has_feature(self, feature: Feature) -> bool:
        """
        Check if organization has access to a feature.
        
        Features can be:
        1. Included in Edition
        2. Overridden in feature_flags
        3. Added as add-on (in metadata)
        """
        # Check feature flags override first
        if self.org.feature_flags:
            override = self.org.feature_flags.get(feature.value)
            if override is not None:
                return override
        
        # Check Edition features
        return feature in self._features
    
    def get_available_features(self) -> Set[Feature]:
        """Get all features available to this organization."""
        available = set(self._features)
        
        # Add feature flag overrides
        if self.org.feature_flags:
            for feature_name, enabled in self.org.feature_flags.items():
                try:
                    feature = Feature(feature_name)
                    if enabled:
                        available.add(feature)
                    else:
                        available.discard(feature)
                except ValueError:
                    pass  # Unknown feature flag
        
        return available
    
    def require_feature(self, feature: Feature) -> None:
        """
        Require a feature, raising exception if not available.
        
        Raises:
            PolicyViolation: If feature not available
        """
        if not self.has_feature(feature):
            raise PolicyViolation(
                feature=feature.value,
                limit="feature_access",
                current=False,
                allowed=True
            )
    
    # ========================================================================
    # LIMIT CHECKS
    # ========================================================================
    
    def get_limit(self, limit_name: str) -> int:
        """Get a specific limit value. 0 = unlimited."""
        return getattr(self._limits, limit_name, 0)
    
    def check_limit(self, limit_name: str, current_value: int) -> bool:
        """
        Check if a value is within the limit.
        
        Returns True if within limit, False if exceeded.
        0 = unlimited (always returns True)
        """
        limit = self.get_limit(limit_name)
        if limit == 0:  # Unlimited
            return True
        return current_value < limit
    
    def require_limit(self, limit_name: str, current_value: int) -> None:
        """
        Require value to be within limit, raising exception if exceeded.
        
        Raises:
            PolicyViolation: If limit exceeded
        """
        limit = self.get_limit(limit_name)
        if limit > 0 and current_value >= limit:
            raise PolicyViolation(
                feature=limit_name,
                limit="max_limit",
                current=current_value,
                allowed=limit
            )
    
    def can_add_users(self, additional_users: int, current_users: int) -> bool:
        """Check if organization can add more users."""
        limit = self._limits.max_users
        if limit == 0:
            return True
        return (current_users + additional_users) <= limit
    
    def can_make_api_call(self, calls_today: int, calls_this_minute: int) -> bool:
        """Check if organization can make an API call."""
        daily_limit = self._limits.max_api_calls_per_day
        minute_limit = self._limits.max_api_calls_per_minute
        
        # Check daily limit (0 = unlimited)
        if daily_limit > 0 and calls_today >= daily_limit:
            return False
        
        # Check per-minute limit (0 = unlimited)
        if minute_limit > 0 and calls_this_minute >= minute_limit:
            return False
        
        return True
    
    def can_create_sandbox(self, current_sandboxes: int) -> bool:
        """Check if organization can create a sandbox."""
        if not self.has_feature(Feature.SANDBOX_ENVIRONMENTS):
            return False
        
        limit = self._limits.max_sandboxes
        if limit == 0:
            return True
        return current_sandboxes < limit
    
    # ========================================================================
    # STATUS CHECKS
    # ========================================================================
    
    def is_operational(self) -> bool:
        """Check if organization can perform normal operations."""
        return self.org.status in {
            OrganizationStatus.ACTIVE,
            OrganizationStatus.TRIAL,
        }
    
    def is_read_only(self) -> bool:
        """Check if organization is in read-only mode."""
        # Per requirements: suspended = full lockout, no read-only
        return False
    
    def can_access(self) -> bool:
        """Check if organization can be accessed at all."""
        return self.org.status in {
            OrganizationStatus.ACTIVE,
            OrganizationStatus.TRIAL,
            OrganizationStatus.PENDING_CANCELLATION,  # Access until end
        }
    
    # ========================================================================
    # UPGRADE PATHS
    # ========================================================================
    
    def can_upgrade_to(self, target_edition: Edition) -> bool:
        """Check if organization can upgrade to target edition."""
        # Define upgrade paths
        upgrade_order = [
            Edition.FREE,
            Edition.ESSENTIALS,
            Edition.PROFESSIONAL,
            Edition.ENTERPRISE,
            Edition.UNLIMITED,
        ]
        
        current_idx = upgrade_order.index(self.org.edition)
        target_idx = upgrade_order.index(target_edition)
        
        # Can only upgrade (not downgrade through this method)
        return target_idx > current_idx
    
    def get_upgrade_options(self) -> List[Edition]:
        """Get available upgrade options for this organization."""
        upgrade_order = [
            Edition.FREE,
            Edition.ESSENTIALS,
            Edition.PROFESSIONAL,
            Edition.ENTERPRISE,
            Edition.UNLIMITED,
        ]
        
        current_idx = upgrade_order.index(self.org.edition)
        return upgrade_order[current_idx + 1:]
    
    def get_features_gained_on_upgrade(self, target_edition: Edition) -> Set[Feature]:
        """Get features that would be gained by upgrading to target edition."""
        current_features = EDITION_FEATURES.get(self.org.edition, set())
        target_features = EDITION_FEATURES.get(target_edition, set())
        return target_features - current_features
    
    # ========================================================================
    # TRIAL POLICIES
    # ========================================================================
    
    def get_trial_duration_days(self) -> int:
        """Get trial duration for this edition."""
        # All editions get 14-day trial, Enterprise gets 30
        if self.org.edition in {Edition.ENTERPRISE, Edition.UNLIMITED}:
            return 30
        return 14
    
    def is_trial_extension_allowed(self) -> bool:
        """Check if trial can be extended."""
        # Allow one extension
        return self.org.metadata.get("trial_extended", False) is False
    
    def get_trial_features(self) -> Set[Feature]:
        """
        Get features available during trial.
        
        During trial, organizations get Professional features
        regardless of which edition they're trialing.
        """
        return EDITION_FEATURES[Edition.PROFESSIONAL]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_edition_limits(edition: Edition) -> EditionLimits:
    """Get limits for an edition."""
    return EDITION_LIMITS.get(edition, EDITION_LIMITS[Edition.FREE])


def get_edition_features(edition: Edition) -> Set[Feature]:
    """Get features for an edition."""
    return EDITION_FEATURES.get(edition, EDITION_FEATURES[Edition.FREE])


def get_edition_pricing(edition: Edition) -> EditionPricing:
    """Get pricing for an edition."""
    return EDITION_PRICING.get(edition, EDITION_PRICING[Edition.FREE])


def is_feature_enabled(edition: Edition, feature_or_action: str) -> bool:
    """
    Check if a feature/action is enabled for the edition.
    
    Args:
        edition: The organization's edition
        feature_or_action: Feature name or action name to check
        
    Returns:
        True if feature is enabled for this edition
    """
    enabled_features = get_edition_features(edition)
    
    # Direct feature lookup
    try:
        feature = Feature(feature_or_action)
        return feature in enabled_features
    except ValueError:
        pass
    
    # Action-to-feature mapping for common use cases
    action_mappings = {
        "create_workflow": Feature.CUSTOM_WORKFLOWS,
        "custom_reports": Feature.ADVANCED_ANALYTICS,
        "api_access": Feature.REST_API,
        "sandbox_create": Feature.SANDBOX_ENVIRONMENTS,
        "sso_configure": Feature.SSO,
        "audit_logs": Feature.AUDIT_LOGS,
        "unlimited_storage": Feature.UNLIMITED_STORAGE,
    }
    
    mapped_feature = action_mappings.get(feature_or_action)
    if mapped_feature:
        return mapped_feature in enabled_features
    
    # If no mapping found, assume it's not enabled
    return False


def compare_editions(edition_a: Edition, edition_b: Edition) -> Dict[str, Any]:
    """
    Compare two editions.
    
    Returns dict with 'limits_diff' and 'features_diff'.
    """
    limits_a = EDITION_LIMITS[edition_a]
    limits_b = EDITION_LIMITS[edition_b]
    features_a = EDITION_FEATURES[edition_a]
    features_b = EDITION_FEATURES[edition_b]
    
    # Compare limits
    limits_diff = {}
    for field_name in limits_a.__dataclass_fields__:
        val_a = getattr(limits_a, field_name)
        val_b = getattr(limits_b, field_name)
        if val_a != val_b:
            limits_diff[field_name] = {"edition_a": val_a, "edition_b": val_b}
    
    return {
        "limits_diff": limits_diff,
        "features_only_in_a": features_a - features_b,
        "features_only_in_b": features_b - features_a,
        "common_features": features_a & features_b,
    }
