"""Concurrency Control

Implements optimistic and pessimistic locking strategies to prevent race conditions
and data corruption from concurrent updates.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from app.db.models.domain_models import Tenant
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class OptimisticLockError(Exception):
    """Raised when optimistic lock check fails."""
    pass


class ConcurrencyControl:
    """Handles concurrent access to shared resources."""

    @staticmethod
    async def update_with_optimistic_lock(
        session: AsyncSession,
        tenant_id: str,
        current_version: int,
        update_data: dict
    ) -> Tenant:
        """
        Update tenant with optimistic locking using version numbers.
        
        Only updates if version matches. Prevents lost updates.
        
        Args:
            session: Database session
            tenant_id: Tenant ID to update
            current_version: Expected current version
            update_data: Fields to update
            
        Returns:
            Updated tenant
            
        Raises:
            OptimisticLockError: If version mismatch (concurrent update detected)
        """
        # Add version increment to update
        update_data['version'] = current_version + 1
        update_data['updated_at'] = datetime.now(timezone.utc)
        
        stmt = (
            update(Tenant)
            .where(
                and_(
                    Tenant.id == tenant_id,
                    Tenant.version == current_version  # ← Version check
                )
            )
            .values(**update_data)
            .returning(Tenant)
        )
        
        result = await session.execute(stmt)
        updated = result.scalar_one_or_none()
        
        if not updated:
            logger.warning(
                f"Optimistic lock failed for tenant {tenant_id}. "
                f"Expected version {current_version}, but version changed."
            )
            raise OptimisticLockError(
                f"Tenant was modified by another process. "
                f"Please refresh and try again."
            )
        
        logger.info(f"Optimistic lock update successful for tenant {tenant_id}")
        return updated

    @staticmethod
    async def get_with_pessimistic_lock(
        session: AsyncSession,
        tenant_id: str
    ) -> Tenant:
        """
        Retrieve tenant with pessimistic lock (row-level lock).
        
        Locks the row so other processes must wait.
        
        Args:
            session: Database session
            tenant_id: Tenant ID to lock
            
        Returns:
            Locked tenant
        """
        stmt = (
            select(Tenant)
            .where(Tenant.id == tenant_id)
            .with_for_update(timeout=30)  # 30 second timeout to prevent DoS
        )
        
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        if tenant:
            logger.info(f"Pessimistic lock acquired for tenant {tenant_id}")
        
        return tenant

    @staticmethod
    async def update_with_pessimistic_lock(
        session: AsyncSession,
        tenant_id: str,
        update_data: dict
    ) -> Tenant:
        """
        Update tenant with pessimistic locking.
        
        Acquires lock, updates, then releases lock.
        
        Args:
            session: Database session
            tenant_id: Tenant ID to update
            update_data: Fields to update
            
        Returns:
            Updated tenant
        """
        # Get with lock
        tenant = await ConcurrencyControl.get_with_pessimistic_lock(
            session, tenant_id
        )
        
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        
        # Update
        update_data['updated_at'] = datetime.now(timezone.utc)
        stmt = (
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(**update_data)
            .returning(Tenant)
        )
        
        result = await session.execute(stmt)
        updated = result.scalar_one()
        
        logger.info(f"Pessimistic lock update successful for tenant {tenant_id}")
        return updated

    @staticmethod
    async def check_version_conflict(
        session: AsyncSession,
        tenant_id: str,
        expected_version: int
    ) -> bool:
        """
        Check if version has changed (detect concurrent modification).
        
        Args:
            session: Database session
            tenant_id: Tenant ID
            expected_version: Expected version number
            
        Returns:
            True if version matches, False if changed
        """
        stmt = select(Tenant.version).where(Tenant.id == tenant_id)
        result = await session.execute(stmt)
        current_version = result.scalar_one_or_none()
        
        if current_version is None:
            return False
        
        return current_version == expected_version
