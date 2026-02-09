"""Domain Layer - Business Domain Models and Entities

Pure business logic with no framework dependencies.
Contains invariants, entities, and domain rules organized as:

  models/     - Domain invariants and rules
  entities/   - Domain entities (lifecycle, policies)
  enums/      - Enumerations (status, edition, etc)

Terminology (Salesforce-style):
- Organization: A customer company (what other platforms call "Tenant")
- Edition: The subscription tier (FREE, ESSENTIALS, PROFESSIONAL, ENTERPRISE, UNLIMITED)
- User: A person working for an Organization (managed by user_service)

Modules:
- models: Core domain entities (Organization aggregate root)
- lifecycle: State machine for organization status transitions
- policies: Edition limits and feature definitions
- invariants: Business rule validation

Usage:
    from domain import Organization, OrganizationLifecycle, OrganizationPolicy
    
    # Create organization
    org = Organization.create("Acme Corp", Edition.PROFESSIONAL, Region.US_EAST)
    
    # Manage lifecycle
    lifecycle = OrganizationLifecycle()
    lifecycle.activate(org)
    
    # Check policies
    policy = OrganizationPolicy(org)
    if policy.has_feature(Feature.LIVE_CHAT):
        # Enable live chat
        pass
"""

# Core Models - imported from app.db.models.domain_models
# (Note: Models are defined in app.db.models.domain_models, not in this package)
# This is a temporary workaround to avoid circular imports

# Lifecycle (State Machine) - imported from app.business.entities.lifecycle
# (Note: Lifecycle is defined in app.business.entities.lifecycle)

# Policies (Edition Limits & Features) - imported from app.business.entities.policies
# (Note: Policies are defined in app.business.entities.policies)

# Invariants (Business Rule Validation) - imported from app.business.domain.invariants
# (Note: Invariants are defined in app.business.domain.invariants)

__all__ = []
