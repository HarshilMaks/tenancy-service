"""
Infrastructure Persistence Layer - Organization Repository
==========================================================

SQLAlchemy-based implementation of the OrganizationRepository protocol.
Handles all database operations for Organization aggregates.

This follows the Repository pattern from DDD, providing a clean interface
between the domain layer and the persistence mechanism.

Enterprise Features:
    - Full CRUD operations for Organizations
    - Soft delete with retention period support
    - Optimistic locking via version field
    - Audit trail preservation
    - Query filtering and pagination
    - Transaction management
    - Domain ↔ ORM model mapping

Salesforce Alignment:
    - Organization model maps to Salesforce Organization object
    - Edition stored as enumeration
    - Status tracks full lifecycle
    - Region support for data residency

Author: Platform Engineering Team
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID
from functools import lru_cache
import hashlib

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
    func,
    or_,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship

# Domain imports
from domain.models import (
    Organization,
    OrganizationStatus,
    Edition,
    BillingStatus,
    SubscriptionType,
    OrganizationId,
    BillingInfo,
    RegionalSettings,
    Region,
)
from app.business.domain.entities.lifecycle import OrganizationLifecycle

# =============================================================================
# SQLAlchemy Base
# =============================================================================

Base = declarative_base()


# =============================================================================
# ORM Models - Database Tables
# =============================================================================

class OrganizationModel(Base):
    """
    SQLAlchemy ORM model for organizations table.
    
    Maps to the domain Organization aggregate root.
    
    Table Design:
        - Primary key: UUID for global uniqueness
        - Unique constraints: org_id, normalized_name
        - Indexes: status, edition, created_at for common queries
        - JSONB: billing_info, regional_settings for flexibility
        - Soft delete: terminated_at with retention period
    
    Salesforce Mapping:
        - org_id → Organization ID (ORG-XXXXXXXX format)
        - edition → Salesforce Edition (Enterprise, Professional, etc.)
        - status → Organization Status in lifecycle
    """
    
    __tablename__ = "tenants"
    
    # ==========================================================================
    # Primary Identification
    # ==========================================================================
    
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        comment="Internal UUID, never exposed externally"
    )
    
    external_id = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="External identifier (ORG-XXXXXXXX format)"
    )
    
    # ==========================================================================
    # Organization Identity
    # ==========================================================================
    
    name = Column(
        String(255),
        nullable=False,
        comment="Display name of the organization"
    )
    
    normalized_name = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Lowercase name for uniqueness checks"
    )
    
    # ==========================================================================
    # Lifecycle State
    # ==========================================================================
    
    status = Column(
        SQLEnum(OrganizationStatus, name="tenant_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OrganizationStatus.PROVISIONING,
        index=True,
        comment="Current lifecycle status"
    )
    
    plan_tier = Column(
        SQLEnum(Edition, name="edition", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=Edition.FREE,
        index=True,
        comment="Subscription edition/tier"
    )
    
    region = Column(
        String(50),
        nullable=True,
        comment="Geographic region"
    )
    
    # ==========================================================================
    # Trial Management
    # ==========================================================================
    # Trial Management - COMMENTED OUT (not in current DB schema)
    # ==========================================================================
    
    # is_trial = Column(
    #     Boolean,
    #     nullable=False,
    #     default=False,
    #     comment="Whether organization is in trial period"
    # )
    
    # trial_started_at = Column(
    #     DateTime(timezone=True),
    #     nullable=True,
    #     comment="When trial period began"
    # )
    
    # trial_ends_at = Column(
    #     DateTime(timezone=True),
    #     nullable=True,
    #     index=True,
    #     comment="When trial period expires"
    # )
    
    # trial_converted_at = Column(
    #     DateTime(timezone=True),
    #     nullable=True,
    #     comment="When trial converted to paid"
    # )
    
    # ==========================================================================
    # Billing Information (JSONB) - NOT IN CURRENT DB SCHEMA
    # ==========================================================================
    
    # billing_info = Column(
    #     JSONB,
    #     nullable=True,
    #     comment="Billing configuration as JSON"
    # )
    
    # ==========================================================================
    # Regional Settings (JSONB) - NOT IN CURRENT DB SCHEMA
    # ==========================================================================
    
    # regional_settings = Column(
    #     JSONB,
    #     nullable=True,
    #     comment="Regional configuration as JSON"
    # )
    
    # ==========================================================================
    # Lifecycle Timestamps
    # ==========================================================================
    
    # activated_at = Column(
    #     DateTime(timezone=True),
    #     nullable=True,
    #     comment="When organization was activated"
    # )
    
    suspended_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When organization was suspended"
    )
    
    suspended_reason = Column(
        String(255),
        nullable=True,
        comment="Reason for suspension"
    )
    
    # terminated_at = Column(
    #     DateTime(timezone=True),
    #     nullable=True,
    #     index=True,
    #     comment="When organization was terminated (soft delete)"
    # )
    
    # ==========================================================================
    # Usage & Limits - NOT IN CURRENT DB SCHEMA
    # ==========================================================================
    
    # current_users = Column(
    #     Integer,
    #     nullable=False,
    #     default=0,
    #     comment="Current active user count"
    # )
    
    # current_storage_bytes = Column(
    #     Numeric(20, 0),
    #     nullable=False,
    #     default=0,
    #     comment="Current storage usage in bytes"
    # )
    
    # current_api_calls_today = Column(
    #     Integer,
    #     nullable=False,
    #     default=0,
    #     comment="API calls made today"
    # )
    
    # ==========================================================================
    # Audit Fields
    # ==========================================================================
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="Record creation timestamp"
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="Last update timestamp"
    )
    
    version = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Optimistic locking version"
    )
    
    # ==========================================================================
    # Additional JSONB Fields
    # ==========================================================================
    
    compliance_requirements = Column(
        JSONB,
        nullable=True,
        comment="Compliance requirements as JSON"
    )
    
    plan_limits = Column(
        JSONB,
        nullable=True,
        comment="Plan limits as JSON"
    )
    
    # ==========================================================================
    # Metadata
    # ==========================================================================
    
    metadata_json = Column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional metadata as JSON"
    )
    
    # ==========================================================================
    # Table Configuration
    # ==========================================================================
    
    __table_args__ = (
        # Composite indexes for common queries
        Index(
            "ix_tenants_status_edition",
            "status",
            "plan_tier"
        ),
        Index(
            "ix_tenants_created_at_status",
            "created_at",
            "status"
        ),
        # Index(
        #     "ix_tenants_trial_ends_at",
        #     "trial_ends_at",
        #     postgresql_where=(Column("is_trial") == True)
        # ),
        # Partial index for active organizations
        Index(
            "ix_tenants_active",
            "status",
            postgresql_where=(Column("terminated_at").is_(None))
        ),
        {
            "comment": "Multi-tenant organization registry",
            "schema": None,  # Use default schema
        },
    )
    
    def __repr__(self) -> str:
        return (
            f"<OrganizationModel("
            f"id={self.id}, "
            f"org_id='{self.org_id}', "
            f"name='{self.name}', "
            f"status={self.status.name if self.status else 'None'}"
            f")>"
        )


class OrganizationEventModel(Base):
    """
    SQLAlchemy ORM model for organization domain events.
    
    Stores domain events for event sourcing and audit trail.
    Events are immutable once created.
    
    Design:
        - One-to-many relationship with organizations
        - Events are append-only (never updated or deleted)
        - JSONB payload for flexible event data
        - Indexed by organization and timestamp for queries
    """
    
    __tablename__ = "tenant_events"
    
    id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        comment="Event UUID"
    )
    
    organization_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Organization this event belongs to"
    )
    
    event_type = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Event type name"
    )
    
    event_version = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Event schema version"
    )
    
    payload = Column(
        JSONB,
        nullable=False,
        comment="Event data as JSON"
    )
    
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="When the event occurred"
    )
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When the event was recorded"
    )
    
    __table_args__ = (
        Index(
            "ix_organization_events_org_occurred",
            "organization_id",
            "occurred_at"
        ),
        {
            "comment": "Organization domain events for audit and event sourcing",
        },
    )


# =============================================================================
# Exceptions
# =============================================================================

class OrganizationNotFoundError(Exception):
    """Raised when an organization cannot be found."""
    
    def __init__(self, identifier: str | UUID):
        self.identifier = identifier
        super().__init__(f"Organization not found: {identifier}")


class OrganizationAlreadyExistsError(Exception):
    """Raised when trying to create an organization that already exists."""
    
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Organization already exists with name: {name}")


class OptimisticLockError(Exception):
    """Raised when optimistic locking detects a concurrent modification."""
    
    def __init__(self, org_id: str, expected_version: int, actual_version: int):
        self.org_id = org_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Optimistic lock failed for organization {org_id}: "
            f"expected version {expected_version}, found {actual_version}"
        )


# =============================================================================
# Query Filters
# =============================================================================

class OrganizationFilter:
    """
    Filter criteria for organization queries.
    
    Supports filtering by:
        - Status (single or multiple)
        - Edition (single or multiple)
        - Trial status
        - Date ranges
        - Search text
        - Active/terminated state
    
    Example:
        >>> filter = OrganizationFilter(
        ...     statuses=[OrganizationStatus.ACTIVE],
        ...     editions=[Edition.ENTERPRISE, Edition.UNLIMITED],
        ...     is_trial=False,
        ...     search_text="Acme"
        ... )
    """
    
    def __init__(
        self,
        statuses: Optional[List[OrganizationStatus]] = None,
        editions: Optional[List[Edition]] = None,
        is_trial: Optional[bool] = None,
        is_active: Optional[bool] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        search_text: Optional[str] = None,
        exclude_terminated: bool = True,
    ):
        self.statuses = statuses
        self.editions = editions
        self.is_trial = is_trial
        self.is_active = is_active
        self.created_after = created_after
        self.created_before = created_before
        self.search_text = search_text
        self.exclude_terminated = exclude_terminated


class PaginationParams:
    """
    Pagination parameters for list queries.
    
    Attributes:
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
        sort_by: Field to sort by
        sort_desc: Sort descending if True
    """
    
    MAX_PAGE_SIZE = 100
    DEFAULT_PAGE_SIZE = 20
    
    def __init__(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ):
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), self.MAX_PAGE_SIZE)
        self.sort_by = sort_by
        self.sort_desc = sort_desc
    
    @property
    def offset(self) -> int:
        """Calculate offset for SQL query."""
        return (self.page - 1) * self.page_size
    
    @property
    def limit(self) -> int:
        """Get limit for SQL query."""
        return self.page_size


class PaginatedResult:
    """
    Paginated query result.
    
    Attributes:
        items: List of items for current page
        total: Total number of items matching filter
        page: Current page number
        page_size: Items per page
        total_pages: Total number of pages
    """
    
    def __init__(
        self,
        items: List[Organization],
        total: int,
        page: int,
        page_size: int,
    ):
        self.items = items
        self.total = total
        self.page = page
        self.page_size = page_size
        self.total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages
    
    @property
    def has_previous(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1


# =============================================================================
# Repository Implementation
# =============================================================================

class OrganizationRepository:
    """
    SQLAlchemy-based repository for Organization aggregates.
    
    Implements the repository pattern, providing a clean interface
    for domain operations while hiding persistence details.
    
    Features:
        - CRUD operations with domain model mapping
        - Optimistic locking for concurrency
        - Soft delete support
        - Complex query filtering
        - Pagination support
        - Event persistence
    
    Usage:
        >>> with session_factory() as session:
        ...     repo = OrganizationRepository(session)
        ...     org = repo.get_by_id(org_uuid)
        ...     org.activate()
        ...     repo.save(org)
    
    Thread Safety:
        Repository instances are NOT thread-safe.
        Create a new instance per request/transaction.
    """
    
    def __init__(self, session: Session):
        """
        Initialize repository with database session.
        
        Args:
            session: SQLAlchemy session for database operations
        """
        self._session = session
        self._exists_cache: Dict[str, bool] = {}  # Cache for exists checks
        self._query_cache: Dict[str, Any] = {}  # Query result cache
        self._cache_ttl = 300  # 5 minutes TTL
    
    # =========================================================================
    # Create Operations
    # =========================================================================
    
    def save(self, organization: Organization) -> Organization:
        """
        Persist an organization (create or update).
        
        For new organizations, creates the record.
        For existing organizations, updates with optimistic locking.
        
        Args:
            organization: Domain organization to persist
            
        Returns:
            Updated organization with new version
            
        Raises:
            OrganizationAlreadyExistsError: If normalized name already exists
            OptimisticLockError: If concurrent modification detected
        """
        # Check if this is a new organization
        existing = self._session.query(OrganizationModel).filter_by(
            id=organization.id
        ).first()
        
        if existing is None:
            # New organization - check name uniqueness
            name_exists = self._session.query(OrganizationModel).filter_by(
                normalized_name=organization.normalized_name
            ).first()
            
            if name_exists:
                raise OrganizationAlreadyExistsError(organization.name)
            
            # Create new record
            model = self._to_model(organization)
            self._session.add(model)
            self._session.flush()
            
            return organization
        
        else:
            # Existing organization - check version for optimistic locking
            if existing.version != organization.version:
                raise OptimisticLockError(
                    organization.org_id,
                    organization.version,
                    existing.version
                )
            
            # Check name uniqueness if changed
            if existing.normalized_name != organization.normalized_name:
                name_exists = self._session.query(OrganizationModel).filter(
                    OrganizationModel.normalized_name == organization.normalized_name,
                    OrganizationModel.id != organization.id
                ).first()
                
                if name_exists:
                    raise OrganizationAlreadyExistsError(organization.name)
            
            # Update existing record
            self._update_model(existing, organization)
            existing.version += 1
            existing.updated_at = datetime.now(timezone.utc)
            self._session.flush()
            
            # Return updated domain object with new version
            return self._to_domain(existing)
    
    # =========================================================================
    # Read Operations
    # =========================================================================
    
    def get_by_id(self, organization_id: UUID) -> Organization:
        """
        Get organization by internal UUID.
        
        Args:
            organization_id: Internal UUID
            
        Returns:
            Domain organization
            
        Raises:
            OrganizationNotFoundError: If not found
        """
        model = self._session.query(OrganizationModel).filter_by(
            id=organization_id
        ).first()
        
        if model is None:
            raise OrganizationNotFoundError(organization_id)
        
        return self._to_domain(model)
    
    def get_by_org_id(self, org_id: str) -> Organization:
        """
        Get organization by external org_id (ORG-XXXXXXXX).
        
        Args:
            org_id: External organization ID
            
        Returns:
            Domain organization
            
        Raises:
            OrganizationNotFoundError: If not found
        """
        model = self._session.query(OrganizationModel).filter_by(
            external_id=org_id
        ).first()
        
        if model is None:
            raise OrganizationNotFoundError(org_id)
        
        return self._to_domain(model)
    
    def get_by_normalized_name(self, normalized_name: str) -> Optional[Organization]:
        """
        Get organization by normalized name.
        
        Args:
            normalized_name: Lowercase organization name
            
        Returns:
            Domain organization or None if not found
        """
        model = self._session.query(OrganizationModel).filter_by(
            normalized_name=normalized_name.lower()
        ).first()
        
        return self._to_domain(model) if model else None
    
    def find_by_id(self, organization_id: UUID) -> Optional[Organization]:
        """
        Find organization by ID, returning None if not found.
        
        Args:
            organization_id: Internal UUID
            
        Returns:
            Domain organization or None
        """
        model = self._session.query(OrganizationModel).filter_by(
            id=organization_id
        ).first()
        
        return self._to_domain(model) if model else None
    
    def exists_by_normalized_name(self, normalized_name: str) -> bool:
        """
        Check if organization exists with given normalized name.
        Uses optimized exists() query and caching.
        
        Args:
            normalized_name: Lowercase organization name
            
        Returns:
            True if exists, False otherwise
        """
        cache_key = f"name:{normalized_name.lower()}"
        
        # Check cache first
        if cache_key in self._exists_cache:
            return self._exists_cache[cache_key]
        
        # Use optimized exists() query
        from sqlalchemy import exists, select
        
        stmt = select(exists().where(OrganizationModel.normalized_name == normalized_name.lower()))
        result = self._session.execute(stmt).scalar()
        
        # Cache result
        self._exists_cache[cache_key] = result
        return result
    
    def exists_by_org_id(self, org_id: str) -> bool:
        """
        Check if organization exists with given org_id.
        Uses optimized exists() query and caching.
        
        Args:
            org_id: External organization ID
            
        Returns:
            True if exists, False otherwise
        """
        cache_key = f"org_id:{org_id}"
        
        # Check cache first
        if cache_key in self._exists_cache:
            return self._exists_cache[cache_key]
        
        # Use optimized exists() query
        from sqlalchemy import exists, select
        
        stmt = select(exists().where(OrganizationModel.external_id == org_id))
        result = self._session.execute(stmt).scalar()
        
        # Cache result
        self._exists_cache[cache_key] = result
        return result
    
    # =========================================================================
    # List Operations
    # =========================================================================
    
    def list(
        self,
        filter: Optional[OrganizationFilter] = None,
        pagination: Optional[PaginationParams] = None,
    ) -> PaginatedResult:
        """
        List organizations with filtering and pagination.
        
        Args:
            filter: Filter criteria
            pagination: Pagination parameters
            
        Returns:
            Paginated list of organizations
        """
        filter = filter or OrganizationFilter()
        pagination = pagination or PaginationParams()
        
        # Build base query with optimizations
        query = self._session.query(OrganizationModel)
        
        # Apply filters
        query = self._apply_filters(query, filter)
        
        # Use count() with optimization - only count if needed
        total = query.count()
        
        # Apply sorting
        query = self._apply_sorting(query, filter)
        
        # Apply pagination
        query = query.offset(pagination.offset).limit(pagination.limit)
        
        # Execute query with all() for better performance
        models = query.all()
        
        # Convert to domain objects
        organizations = [self._to_domain(m) for m in models]
        
        return PaginatedResult(
            items=organizations,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    
    def list_by_status(
        self,
        status: OrganizationStatus,
        limit: int = 100,
    ) -> List[Organization]:
        """
        List organizations by status.
        
        Args:
            status: Organization status to filter by
            limit: Maximum number of results
            
        Returns:
            List of organizations
        """
        models = self._session.query(OrganizationModel).filter_by(
            status=status
        ).limit(limit).all()
        
        return [self._to_domain(m) for m in models]
    
    def list_expiring_trials(
        self,
        before: datetime,
        limit: int = 100,
    ) -> List[Organization]:
        """
        List trial organizations expiring before given date.
        
        Args:
            before: Expiration cutoff date
            limit: Maximum number of results
            
        Returns:
            List of trial organizations
        """
        models = self._session.query(OrganizationModel).filter(
            OrganizationModel.is_trial == True,
            OrganizationModel.trial_ends_at < before,
            OrganizationModel.status == OrganizationStatus.ACTIVE,
        ).limit(limit).all()
        
        return [self._to_domain(m) for m in models]
    
    def list_terminated_for_purge(
        self,
        before: datetime,
        limit: int = 100,
    ) -> List[Organization]:
        """
        List terminated organizations eligible for permanent deletion.
        
        Organizations terminated before the given date have exceeded
        the retention period and can be permanently purged.
        
        Args:
            before: Termination date cutoff
            limit: Maximum number of results
            
        Returns:
            List of organizations to purge
        """
        models = self._session.query(OrganizationModel).filter(
            OrganizationModel.status == OrganizationStatus.TERMINATED,
            OrganizationModel.terminated_at < before,
        ).limit(limit).all()
        
        return [self._to_domain(m) for m in models]
    
    # =========================================================================
    # Update Operations
    # =========================================================================
    
    def update(
        self,
        organization_id: UUID,
        updates: Dict[str, Any],
    ) -> Organization:
        """
        Update specific fields of an organization.
        
        Supports partial updates. Only provided fields are updated.
        Automatically updates updated_at timestamp.
        
        Args:
            organization_id: Internal UUID
            updates: Dictionary of fields to update
                    Valid keys: name, metadata
            
        Returns:
            Updated domain organization
            
        Raises:
            OrganizationNotFoundError: If not found
        """
        model = self._session.query(OrganizationModel).filter_by(
            id=organization_id
        ).first()
        
        if model is None:
            raise OrganizationNotFoundError(organization_id)
        
        # Update allowed fields
        allowed_fields = {'name', 'metadata'}
        
        for field, value in updates.items():
            if field not in allowed_fields:
                continue
                
            if field == 'name' and value:
                model.name = value
                model.normalized_name = value.lower()
            elif field == 'metadata' and value:
                model.metadata = value
        
        model.updated_at = datetime.now(timezone.utc)
        model.version += 1
        self._session.flush()
        
        return self._to_domain(model)
    
    # =========================================================================
    # Delete Operations
    # =========================================================================
    
    def delete(self, organization_id: UUID) -> None:
        """
        Permanently delete an organization.
        
        WARNING: This is a hard delete. Use only for purging
        organizations that have exceeded retention period.
        
        Args:
            organization_id: Internal UUID
            
        Raises:
            OrganizationNotFoundError: If not found
        """
        model = self._session.query(OrganizationModel).filter_by(
            id=organization_id
        ).first()
        
        if model is None:
            raise OrganizationNotFoundError(organization_id)
        
        self._session.delete(model)
        self._session.flush()
    
    # =========================================================================
    # Event Operations
    # =========================================================================
    
    def save_event(
        self,
        organization_id: UUID,
        event_type: str,
        payload: Dict[str, Any],
        occurred_at: datetime,
        event_id: Optional[UUID] = None,
    ) -> None:
        """
        Save a domain event for an organization.
        
        Args:
            organization_id: Organization UUID
            event_type: Type name of the event
            payload: Event data as dictionary
            occurred_at: When the event occurred
            event_id: Optional event UUID (generated if not provided)
        """
        from uuid import uuid4
        
        event = OrganizationEventModel(
            id=event_id or uuid4(),
            organization_id=organization_id,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at,
        )
        
        self._session.add(event)
        self._session.flush()
    
    def get_events(
        self,
        organization_id: UUID,
        after: Optional[datetime] = None,
        event_types: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get domain events for an organization.
        
        Args:
            organization_id: Organization UUID
            after: Only return events after this timestamp
            event_types: Filter by event types
            limit: Maximum number of events
            
        Returns:
            List of event dictionaries
        """
        query = self._session.query(OrganizationEventModel).filter_by(
            organization_id=organization_id
        )
        
        if after:
            query = query.filter(OrganizationEventModel.occurred_at > after)
        
        if event_types:
            query = query.filter(OrganizationEventModel.event_type.in_(event_types))
        
        query = query.order_by(OrganizationEventModel.occurred_at.asc())
        query = query.limit(limit)
        
        events = query.all()
        
        return [
            {
                "id": str(e.id),
                "organization_id": str(e.organization_id),
                "event_type": e.event_type,
                "event_version": e.event_version,
                "payload": e.payload,
                "occurred_at": e.occurred_at.isoformat(),
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def count_by_status(self) -> Dict[OrganizationStatus, int]:
        """
        Get organization counts grouped by status.
        
        Returns:
            Dictionary of status → count
        """
        results = self._session.query(
            OrganizationModel.status,
            func.count(OrganizationModel.id)
        ).group_by(OrganizationModel.status).all()
        
        return {status: count for status, count in results}
    
    def count_by_edition(self) -> Dict[Edition, int]:
        """
        Get organization counts grouped by edition.
        
        Returns:
            Dictionary of edition → count
        """
        results = self._session.query(
            OrganizationModel.plan_tier,
            func.count(OrganizationModel.id)
        ).group_by(OrganizationModel.plan_tier).all()
        
        return {edition: count for edition, count in results}
    
    def count_active_trials(self) -> int:
        """
        Count active trial organizations.
        
        Returns:
            Number of active trials
        """
        # Note: is_trial column not in DB schema, returning 0
        return 0
    
    # =========================================================================
    # Private: Filter Application
    # =========================================================================
    
    def _apply_filters(
        self,
        query,
        filter: OrganizationFilter,
    ):
        """Apply filter criteria to query."""
        
        # Status filter
        if filter.statuses:
            query = query.filter(OrganizationModel.status.in_(filter.statuses))
        
        # Edition filter
        if filter.editions:
            query = query.filter(OrganizationModel.plan_tier.in_(filter.editions))
        
        # Trial filter
        if filter.is_trial is not None:
            # Skip: is_trial not in DB schema
            pass
        
        # Active filter (not terminated)
        if filter.is_active is True:
            query = query.filter(OrganizationModel.terminated_at.is_(None))
            query = query.filter(
                OrganizationModel.status.in_([
                    OrganizationStatus.ACTIVE,
                    OrganizationStatus.PROVISIONING,
                ])
            )
        elif filter.is_active is False:
            query = query.filter(OrganizationModel.terminated_at.isnot(None))
        
        # Date range filters
        if filter.created_after:
            query = query.filter(OrganizationModel.created_at >= filter.created_after)
        
        if filter.created_before:
            query = query.filter(OrganizationModel.created_at <= filter.created_before)
        
        # Search text (name contains)
        if filter.search_text:
            search_pattern = f"%{filter.search_text.lower()}%"
            query = query.filter(
                or_(
                    OrganizationModel.normalized_name.ilike(search_pattern),
                    OrganizationModel.external_id.ilike(search_pattern),  # Map org_id to external_id
                )
            )
        
        # Exclude terminated
        if filter.exclude_terminated:
            query = query.filter(
                OrganizationModel.status != OrganizationStatus.TERMINATED
            )
        
        return query
    
    def _apply_sorting(
        self,
        query,
        pagination: PaginationParams,
    ):
        """Apply sorting to query."""
        
        sort_columns = {
            "created_at": OrganizationModel.created_at,
            "updated_at": OrganizationModel.updated_at,
            "name": OrganizationModel.name,
            "org_id": OrganizationModel.external_id,  # Map org_id to external_id
            "status": OrganizationModel.status,
            "edition": OrganizationModel.plan_tier,  # Map edition to plan_tier
        }
        
        column = sort_columns.get(pagination.sort_by, OrganizationModel.created_at)
        
        if pagination.sort_desc:
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())
        
        return query
    
    # =========================================================================
    # Private: Domain ↔ Model Mapping
    # =========================================================================
    
    def _to_model(self, organization: Organization) -> OrganizationModel:
        """
        Convert domain Organization to ORM model.
        
        Args:
            organization: Domain organization
            
        Returns:
            SQLAlchemy ORM model
        """
        # Handle suspension_info from domain model
        suspended_at = None
        suspended_reason = None
        if organization.suspension_info:
            suspended_at = organization.suspension_info.suspended_at
            suspended_reason = organization.suspension_info.description
        
        return OrganizationModel(
            id=organization.id,
            external_id=organization.org_id,  # Map org_id to external_id
            name=organization.name,
            normalized_name=organization.normalized_name,
            status=organization.status,
            plan_tier=organization.edition,  # Map edition to plan_tier
            region=organization.region.value if hasattr(organization.region, 'value') else str(organization.region),
            suspended_at=suspended_at,
            suspended_reason=suspended_reason,
            created_at=organization.created_at,
            updated_at=organization.updated_at,
            version=organization.version,
            metadata_json=organization.metadata,
        )
    
    def _update_model(
        self,
        model: OrganizationModel,
        organization: Organization,
    ) -> None:
        """
        Update ORM model from domain organization.
        
        Args:
            model: Existing ORM model
            organization: Domain organization with updated data
        """
        model.name = organization.name
        model.normalized_name = organization.normalized_name
        model.status = organization.status
        model.plan_tier = organization.edition  # Map edition to plan_tier
        # Skip trial and other fields that don't exist in DB
        # suspension_info is in domain, but we store suspended_at in DB
        if organization.suspension_info:
            model.suspended_at = organization.suspension_info.suspended_at
            model.suspended_reason = organization.suspension_info.description
        model.metadata_json = organization.metadata
    
    def _to_domain(self, model: OrganizationModel) -> Organization:
        """
        Convert ORM model to domain Organization.
        
        Args:
            model: SQLAlchemy ORM model
            
        Returns:
            Domain organization aggregate
        """
        return Organization(
            id=model.id,
            org_id=model.external_id,
            name=model.name,
            normalized_name=model.normalized_name,
            status=model.status,
            edition=model.plan_tier,
            region=Region(model.region) if model.region else Region.US_EAST_1,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
            metadata=model.metadata_json or {},
            # All other fields use defaults
        )
    
    def _billing_to_dict(
        self,
        billing_info: Optional[BillingInfo],
    ) -> Optional[Dict[str, Any]]:
        """Convert BillingInfo to dictionary for JSONB storage."""
        if billing_info is None:
            return None
        
        return {
            "billing_email": billing_info.billing_email,
            "billing_status": billing_info.billing_status.value if billing_info.billing_status else None,
            "subscription_type": billing_info.subscription_type.value if billing_info.subscription_type else None,
            "payment_method_id": billing_info.payment_method_id,
            "stripe_customer_id": billing_info.stripe_customer_id,
            "billing_cycle_day": billing_info.billing_cycle_day,
            "currency": billing_info.currency,
            "monthly_amount": str(billing_info.monthly_amount) if billing_info.monthly_amount else None,
            "annual_amount": str(billing_info.annual_amount) if billing_info.annual_amount else None,
            "next_billing_date": (
                billing_info.next_billing_date.isoformat() 
                if billing_info.next_billing_date else None
            ),
            "last_payment_date": (
                billing_info.last_payment_date.isoformat() 
                if billing_info.last_payment_date else None
            ),
            "last_payment_amount": str(billing_info.last_payment_amount) if billing_info.last_payment_amount else None,
            "failed_payment_count": billing_info.failed_payment_count,
        }
    
    def _dict_to_billing(
        self,
        data: Optional[Dict[str, Any]],
    ) -> Optional[BillingInfo]:
        """Convert dictionary from JSONB to BillingInfo."""
        if data is None:
            return None
        
        return BillingInfo(
            billing_email=data.get("billing_email"),
            billing_status=BillingStatus(data["billing_status"]) if data.get("billing_status") else None,
            subscription_type=SubscriptionType(data["subscription_type"]) if data.get("subscription_type") else None,
            payment_method_id=data.get("payment_method_id"),
            stripe_customer_id=data.get("stripe_customer_id"),
            billing_cycle_day=data.get("billing_cycle_day"),
            currency=data.get("currency", "USD"),
            monthly_amount=Decimal(data["monthly_amount"]) if data.get("monthly_amount") else None,
            annual_amount=Decimal(data["annual_amount"]) if data.get("annual_amount") else None,
            next_billing_date=(
                datetime.fromisoformat(data["next_billing_date"]) 
                if data.get("next_billing_date") else None
            ),
            last_payment_date=(
                datetime.fromisoformat(data["last_payment_date"]) 
                if data.get("last_payment_date") else None
            ),
            last_payment_amount=Decimal(data["last_payment_amount"]) if data.get("last_payment_amount") else None,
            failed_payment_count=data.get("failed_payment_count", 0),
        )
    
    def _regional_to_dict(
        self,
        regional: Optional[RegionalSettings],
    ) -> Optional[Dict[str, Any]]:
        """Convert RegionalSettings to dictionary for JSONB storage."""
        if regional is None:
            return None
        
        return {
            "primary_region": regional.primary_region,
            "data_residency_region": regional.data_residency_region,
            "backup_region": regional.backup_region,
            "timezone": regional.timezone,
            "locale": regional.locale,
            "date_format": regional.date_format,
            "currency_code": regional.currency_code,
        }
    
    def _dict_to_regional(
        self,
        data: Optional[Dict[str, Any]],
    ) -> Optional[RegionalSettings]:
        """Convert dictionary from JSONB to RegionalSettings."""
        if data is None:
            return None
        
        return RegionalSettings(
            primary_region=data.get("primary_region", "us-east-1"),
            data_residency_region=data.get("data_residency_region"),
            backup_region=data.get("backup_region"),
            timezone=data.get("timezone", "UTC"),
            locale=data.get("locale", "en-US"),
            date_format=data.get("date_format", "YYYY-MM-DD"),
            currency_code=data.get("currency_code", "USD"),
        )


# =============================================================================
# Unit of Work Pattern
# =============================================================================

class UnitOfWork:
    """
    Unit of Work pattern implementation.
    
    Manages transaction boundaries and repository access.
    Ensures all operations within a unit succeed or fail together.
    
    Usage:
        >>> async with UnitOfWork(session_factory) as uow:
        ...     org = uow.organizations.get_by_id(org_id)
        ...     org.activate()
        ...     uow.organizations.save(org)
        ...     await uow.commit()
    
    Features:
        - Transaction management
        - Repository access
        - Automatic rollback on exception
        - Event collection for publishing
    """
    
    def __init__(self, session_factory):
        """
        Initialize Unit of Work.
        
        Args:
            session_factory: Callable that creates SQLAlchemy sessions
        """
        self._session_factory = session_factory
        self._session: Optional[Session] = None
        self._organizations: Optional[OrganizationRepository] = None
        self._events: List[Dict[str, Any]] = []
    
    @property
    def organizations(self) -> OrganizationRepository:
        """Get organization repository."""
        if self._organizations is None:
            raise RuntimeError("UnitOfWork not entered. Use 'with' statement.")
        return self._organizations
    
    @property
    def collected_events(self) -> List[Dict[str, Any]]:
        """Get events collected during this unit of work."""
        return self._events.copy()
    
    def collect_event(self, event: Dict[str, Any]) -> None:
        """
        Collect an event for publishing after commit.
        
        Args:
            event: Event dictionary to collect
        """
        self._events.append(event)
    
    def __enter__(self) -> "UnitOfWork":
        """Enter context manager, create session."""
        self._session = self._session_factory()
        self._organizations = OrganizationRepository(self._session)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager, handle transaction."""
        if exc_type is not None:
            self.rollback()
        self._session.close()
        self._session = None
        self._organizations = None
    
    def commit(self) -> None:
        """Commit the transaction."""
        if self._session:
            self._session.commit()
    
    def rollback(self) -> None:
        """Rollback the transaction."""
        if self._session:
            self._session.rollback()
            self._events.clear()
    
    def flush(self) -> None:
        """Flush pending changes without committing."""
        if self._session:
            self._session.flush()


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # ORM Models
    "Base",
    "OrganizationModel",
    "OrganizationEventModel",
    
    # Exceptions
    "OrganizationNotFoundError",
    "OrganizationAlreadyExistsError",
    "OptimisticLockError",
    
    # Query Helpers
    "OrganizationFilter",
    "PaginationParams",
    "PaginatedResult",
    
    # Repository
    "OrganizationRepository",
    
    # Unit of Work
    "UnitOfWork",
]
