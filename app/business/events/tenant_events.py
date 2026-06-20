"""
Tenant Domain Events - Event-Driven Architecture

Domain events represent something significant that happened in the domain.
They are used to:
1. Decouple services (event-driven communication)
2. Trigger side effects (send emails, update analytics)
3. Build audit logs
4. Enable event sourcing (future)

Event Flow:
    Domain Layer → Event Publisher → Message Broker → Event Handlers
         ↓                                               ↓
    (raises event)                              (billing, email, analytics)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
import json


# ============================================================================
# BASE EVENT
# ============================================================================

@dataclass
class DomainEvent:
    """Base class for all domain events."""
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def event_type(self) -> str:
        return self.__class__.__name__
    
    @property
    def aggregate_type(self) -> str:
        return "Organization"
    
    @property
    def aggregate_id(self) -> str:
        raise NotImplementedError
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "metadata": self.metadata,
            "payload": self._payload(),
        }
    
    def _payload(self) -> Dict[str, Any]:
        return {}
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


# ============================================================================
# ORGANIZATION LIFECYCLE EVENTS
# ============================================================================

@dataclass
class OrganizationCreatedEvent(DomainEvent):
    """Raised when a new organization is created."""
    org_id: str = ""
    name: str = ""
    edition: str = ""
    region: str = ""
    org_type: str = "PRODUCTION"
    created_by: Optional[str] = None
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, "name": self.name, "edition": self.edition,
            "region": self.region, "org_type": self.org_type, "created_by": self.created_by,
        }


@dataclass
class OrganizationActivatedEvent(DomainEvent):
    """Raised when an organization becomes active."""
    org_id: str = ""
    edition: str = ""
    activated_from: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {"org_id": self.org_id, "edition": self.edition, "activated_from": self.activated_from}


@dataclass
class OrganizationSuspendedEvent(DomainEvent):
    """Raised when an organization is suspended."""
    org_id: str = ""
    reason: str = ""
    severity: str = ""
    description: str = ""
    suspended_by: str = ""
    auto_resume_at: Optional[datetime] = None
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, "reason": self.reason, "severity": self.severity,
            "description": self.description, "suspended_by": self.suspended_by,
            "auto_resume_at": self.auto_resume_at.isoformat() if self.auto_resume_at else None,
        }


@dataclass
class SuspensionWarningEvent(DomainEvent):
    """Raised when an organization receives a suspension warning."""
    org_id: str = ""
    warning_type: str = ""
    severity: str = ""
    description: str = ""
    issued_by: str = ""
    grace_period_ends_at: Optional[datetime] = None
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, "warning_type": self.warning_type, "severity": self.severity,
            "description": self.description, "issued_by": self.issued_by,
            "grace_period_ends_at": self.grace_period_ends_at.isoformat() if self.grace_period_ends_at else None,
        }


@dataclass
class OrganizationResumedEvent(DomainEvent):
    """Raised when a suspended organization is resumed."""
    org_id: str = ""
    previous_reason: str = ""
    resumed_by: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {"org_id": self.org_id, "previous_reason": self.previous_reason, "resumed_by": self.resumed_by}


@dataclass
class OrganizationTerminatedEvent(DomainEvent):
    """Raised when an organization is terminated (soft deleted)."""
    org_id: str = ""
    reason: str = ""
    data_retention_until: Optional[datetime] = None
    terminated_by: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, "reason": self.reason, "terminated_by": self.terminated_by,
            "data_retention_until": self.data_retention_until.isoformat() if self.data_retention_until else None,
        }


@dataclass
class OrganizationRestoredEvent(DomainEvent):
    """Raised when a terminated organization is restored."""
    org_id: str = ""
    restored_by: str = ""
    days_since_termination: int = 0
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, 
            "restored_by": self.restored_by, 
            "days_since_termination": self.days_since_termination
        }


@dataclass
class OrganizationDeletedEvent(DomainEvent):
    """Raised when an organization is permanently deleted."""
    org_id: str = ""
    deleted_at: Optional[datetime] = None
    deleted_by: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "deleted_by": self.deleted_by,
        }


# ============================================================================
# TRIAL EVENTS
# ============================================================================

@dataclass
class TrialStartedEvent(DomainEvent):
    """Raised when an organization starts a trial."""
    org_id: str = ""
    edition: str = ""
    trial_days: int = 14
    trial_ends_at: Optional[datetime] = None
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, "edition": self.edition, "trial_days": self.trial_days,
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
        }


@dataclass
class TrialConvertedEvent(DomainEvent):
    """Raised when a trial converts to a paid subscription."""
    org_id: str = ""
    edition: str = ""
    trial_duration_days: int = 0
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {"org_id": self.org_id, "edition": self.edition, "trial_duration_days": self.trial_duration_days}


# ============================================================================
# EDITION EVENTS
# ============================================================================

@dataclass
class EditionUpgradedEvent(DomainEvent):
    """Raised when an organization upgrades their edition."""
    org_id: str = ""
    previous_edition: str = ""
    new_edition: str = ""
    upgraded_by: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, "previous_edition": self.previous_edition,
            "new_edition": self.new_edition, "upgraded_by": self.upgraded_by,
        }


@dataclass
class EditionDowngradedEvent(DomainEvent):
    """Raised when an organization downgrades their edition."""
    org_id: str = ""
    previous_edition: str = ""
    new_edition: str = ""
    effective_at: Optional[datetime] = None
    downgraded_by: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id, "previous_edition": self.previous_edition, "new_edition": self.new_edition,
            "effective_at": self.effective_at.isoformat() if self.effective_at else None, 
            "downgraded_by": self.downgraded_by,
        }


# ============================================================================
# BILLING EVENTS
# ============================================================================

@dataclass
class BillingStatusChangedEvent(DomainEvent):
    """Raised when billing status changes."""
    org_id: str = ""
    previous_status: str = ""
    new_status: str = ""
    reason: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {"org_id": self.org_id, "previous_status": self.previous_status, "new_status": self.new_status, "reason": self.reason}


# ============================================================================
# REGION EVENTS
# ============================================================================

@dataclass
class RegionMigrationStartedEvent(DomainEvent):
    """Raised when region migration starts."""
    org_id: str = ""
    source_region: str = ""
    target_region: str = ""
    initiated_by: str = ""
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {"org_id": self.org_id, "source_region": self.source_region, "target_region": self.target_region, "initiated_by": self.initiated_by}


@dataclass
class RegionMigrationCompletedEvent(DomainEvent):
    """Raised when region migration completes successfully."""
    org_id: str = ""
    source_region: str = ""
    new_region: str = ""
    duration_seconds: int = 0
    
    @property
    def aggregate_id(self) -> str:
        return self.org_id
    
    def _payload(self) -> Dict[str, Any]:
        return {"org_id": self.org_id, "source_region": self.source_region, "new_region": self.new_region, "duration_seconds": self.duration_seconds}


# ============================================================================
# EVENT REGISTRY
# ============================================================================

EVENT_TYPES: Dict[str, type] = {
    "OrganizationCreatedEvent": OrganizationCreatedEvent,
    "OrganizationActivatedEvent": OrganizationActivatedEvent,
    "OrganizationSuspendedEvent": OrganizationSuspendedEvent,
    "SuspensionWarningEvent": SuspensionWarningEvent,
    "OrganizationResumedEvent": OrganizationResumedEvent,
    "OrganizationTerminatedEvent": OrganizationTerminatedEvent,
    "OrganizationRestoredEvent": OrganizationRestoredEvent,
    "OrganizationDeletedEvent": OrganizationDeletedEvent,
    "TrialStartedEvent": TrialStartedEvent,
    "TrialConvertedEvent": TrialConvertedEvent,
    "EditionUpgradedEvent": EditionUpgradedEvent,
    "EditionDowngradedEvent": EditionDowngradedEvent,
    "BillingStatusChangedEvent": BillingStatusChangedEvent,
    "RegionMigrationStartedEvent": RegionMigrationStartedEvent,
    "RegionMigrationCompletedEvent": RegionMigrationCompletedEvent,
}


def deserialize_event(data: Dict[str, Any]) -> DomainEvent:
    """Deserialize event from dictionary."""
    event_type = data.get("event_type")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type: {event_type}")
    
    event_class = EVENT_TYPES[event_type]
    payload = data.get("payload", {})
    
    return event_class(
        event_id=data.get("event_id", str(uuid4())),
        timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
        version=data.get("version", 1),
        metadata=data.get("metadata", {}),
        **payload
    )
