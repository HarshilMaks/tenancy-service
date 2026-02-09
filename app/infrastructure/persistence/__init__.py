"""Persistence Module

Implements repository pattern for database access. Provides data access abstraction
layer separating business logic from database implementation details.

Example:
    >>> from app.infrastructure.persistence import TenantRepository
    >>> repo = TenantRepository(db)
    >>> tenant = await repo.get_by_id(tenant_id)
"""
