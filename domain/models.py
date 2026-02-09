"""
Domain Models Bridge - Re-exports from app.db.models.domain_models

This module provides the domain.models import path used throughout the codebase.

Usage:
    from domain.models import Organization, OrganizationStatus, Edition
"""

from app.db.models.domain_models import (
    # Type aliases
    OrganizationId,
    # Enums
    OrganizationStatus,
    SuspensionSeverity,
    SuspensionReason,
    Edition,
    SubscriptionType,
    BillingStatus,
    BillingFrequency,
    OrganizationType,
    ComplianceStandard,
    Region,
    OnboardingStep,
    PolicyDecision,
    # Data classes
    BillingInfo,
    Address,
    RegionalSettings,
    SuspensionInfo,
    # Main model
    Organization,
)

__all__ = [
    # Type aliases
    "OrganizationId",
    # Enums
    "OrganizationStatus",
    "SuspensionSeverity",
    "SuspensionReason",
    "Edition",
    "SubscriptionType",
    "BillingStatus",
    "BillingFrequency",
    "OrganizationType",
    "ComplianceStandard",
    "Region",
    "OnboardingStep",
    "PolicyDecision",
    # Data classes
    "BillingInfo",
    "Address",
    "RegionalSettings",
    "SuspensionInfo",
    # Main model
    "Organization",
]
