"""
Infrastructure Persistence Layer
================================

Data access layer for the tenancy service.
Contains repository implementations and database models.

Components:
    - tenant_repository: Organization/Tenant persistence
    - database models: SQLAlchemy ORM definitions
    - migrations: Alembic database migrations

Usage:
    from infrastructure.persistence import SqlAlchemyOrganizationRepository
    
    # In dependency injection
    def get_org_repository(session = Depends(get_db_session)):
        return SqlAlchemyOrganizationRepository(session)

Author: Platform Engineering Team
"""

# Main repository
from infrastructure.persistence.tenant_repository import (
    # Repository implementation
    OrganizationRepository,
    
    # SQLAlchemy models (for migrations and direct DB access)
    OrganizationModel,
    OrganizationEventModel,
    
    # Database base
    Base,
)

__all__ = [
    # Repository
    "OrganizationRepository",
    
    # Models  
    "OrganizationModel",
    "OrganizationEventModel",
    
    # Base
    "Base",
]