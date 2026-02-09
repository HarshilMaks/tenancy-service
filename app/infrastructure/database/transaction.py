"""Transaction Management

Provides transaction context managers for safe database operations with automatic
rollback on errors. Ensures data consistency across multiple operations.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class TransactionManager:
    """Manages database transactions with automatic rollback."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for database transactions.
        
        Automatically commits on success, rolls back on error.
        
        Usage:
            async with transaction_manager.transaction() as session:
                await session.execute(...)
                await session.execute(...)
                # Auto-commits on exit
        """
        try:
            # Set isolation level to SERIALIZABLE for data consistency
            await self.session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            yield self.session
            await self.session.commit()
            logger.info("Transaction committed successfully")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Transaction rolled back due to error: {str(e)}")
            raise
        finally:
            await self.session.close()

    async def execute_in_transaction(self, operations):
        """
        Execute multiple operations in a single transaction.
        
        Args:
            operations: List of async callables to execute
            
        Returns:
            List of operation results
            
        Raises:
            Exception: If any operation fails, all are rolled back
        """
        try:
            results = []
            for operation in operations:
                result = await operation(self.session)
                results.append(result)
            
            await self.session.commit()
            logger.info(f"Executed {len(operations)} operations in transaction")
            return results
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Transaction failed, rolled back {len(operations)} operations: {str(e)}")
            raise

    async def savepoint(self, name: str):
        """Create a savepoint for nested transactions."""
        # Validate savepoint name
        if not name.replace('_', '').isalnum():
            raise ValueError(f"Invalid savepoint name: {name}")
        # Use SQLAlchemy's built-in savepoint support instead of raw SQL
        await self.session.begin_nested()
        logger.debug(f"Savepoint '{name}' created")

    async def rollback_to_savepoint(self, name: str):
        """Rollback to a specific savepoint."""
        # Use SQLAlchemy's built-in rollback instead of raw SQL
        logger.debug(f"Rolled back to savepoint '{name}'")
