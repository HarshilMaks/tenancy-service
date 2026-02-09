"""Domain Events - Events emitted by domain logic

Implements event-driven architecture for tenant lifecycle and policy events.
Events are published and can be consumed by subscribers.

Events enable:
    - Loose coupling between services
    - Async processing of side effects
    - Audit trails and analytics
    - Event sourcing (future)

Event Categories:
    - Lifecycle: Created, Activated, Suspended, Terminated
    - Trial: Started, Extended, Converted, Expired
    - Edition: Upgraded, Downgraded
    - Billing: Payment received, Failed, Status changed
    - Security: Suspension, Access change

Author: Platform Engineering Team
"""

from .tenant_events import (
    # Base
    DomainEvent,
    
    # Lifecycle events
    OrganizationCreatedEvent,
    OrganizationActivatedEvent,
    OrganizationSuspendedEvent,
    OrganizationResumedEvent,
    OrganizationTerminatedEvent,
    OrganizationDeletedEvent,
    OrganizationRestoredEvent,
    
    # Trial events
    TrialStartedEvent,
    TrialConvertedEvent,
    
    # Edition events
    EditionUpgradedEvent,
    EditionDowngradedEvent,
    
    # Billing events
    BillingStatusChangedEvent,
    
    # Region events
    RegionMigrationStartedEvent,
    RegionMigrationCompletedEvent,
    
    # Registry
    EVENT_TYPES,
    deserialize_event,
)

__all__ = [
    # Base
    "DomainEvent",
    
    # Lifecycle events
    "OrganizationCreatedEvent",
    "OrganizationActivatedEvent",
    "OrganizationSuspendedEvent",
    "OrganizationResumedEvent",
    "OrganizationTerminatedEvent",
    "OrganizationDeletedEvent",
    "OrganizationRestoredEvent",
    
    # Trial events
    "TrialStartedEvent",
    "TrialConvertedEvent",
    
    # Edition events
    "EditionUpgradedEvent",
    "EditionDowngradedEvent",
    
    # Billing events
    "BillingStatusChangedEvent",
    
    # Region events
    "RegionMigrationStartedEvent",
    "RegionMigrationCompletedEvent",
    
    # Registry
    "EVENT_TYPES",
    "deserialize_event",
]
