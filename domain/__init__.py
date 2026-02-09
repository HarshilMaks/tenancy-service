"""
Domain Layer Bridge - Re-exports from app.db.models.domain_models

This module provides a clean import path for domain models used throughout
the application. It bridges the root-level domain package to the actual
implementation in app.db.models.domain_models.

Usage:
    from domain import Organization, OrganizationStatus, Edition
    from domain.models import Organization, OrganizationStatus
"""

from app.db.models.domain_models import (
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
