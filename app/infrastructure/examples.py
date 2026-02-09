"""Integration Examples

Shows how to use transaction handling, concurrency control, backups, and monitoring
in your use cases and repositories.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.transaction import TransactionManager
from app.infrastructure.database.concurrency import ConcurrencyControl, OptimisticLockError
from app.infrastructure.database.backup import BackupManager
from app.infrastructure.observability.monitoring import (
    MetricsCollector, HealthMonitor, PerformanceMonitor, AlertSeverity
)
import logging
import time

logger = logging.getLogger(__name__)


# ============================================================================
# EXAMPLE 1: Using Transactions in Use Cases
# ============================================================================

class CreateTenantWithTransactionExample:
    """Example: Create tenant with transaction handling."""

    def __init__(self, session: AsyncSession, metrics: MetricsCollector):
        self.session = session
        self.transaction_manager = TransactionManager(session)
        self.metrics = metrics

    async def execute(self, tenant_data: dict):
        """
        Create tenant with all-or-nothing transaction.
        
        If any step fails, everything rolls back.
        """
        start_time = time.time()
        
        try:
            async with self.transaction_manager.transaction() as session:
                # Step 1: Create tenant
                tenant = await self._create_tenant(session, tenant_data)
                
                # Step 2: Initialize billing (could fail)
                await self._initialize_billing(session, tenant.id)
                
                # Step 3: Send welcome email (could fail)
                await self._send_welcome_email(tenant.email)
                
                # If we reach here, all succeeded and transaction commits
                self.metrics.record_metric('tenant_creation_success', 1)
                return tenant
                
        except Exception as e:
            # Transaction automatically rolled back
            self.metrics.record_metric('tenant_creation_failure', 1)
            logger.error(f"Tenant creation failed and rolled back: {str(e)}")
            raise
        finally:
            duration = time.time() - start_time
            self.metrics.record_metric('tenant_creation_time_ms', duration * 1000)

    async def _create_tenant(self, session, data):
        """Create tenant in database."""
        # Implementation
        pass

    async def _initialize_billing(self, session, tenant_id):
        """Initialize billing account."""
        # Implementation
        pass

    async def _send_welcome_email(self, email):
        """Send welcome email."""
        # Implementation
        pass


# ============================================================================
# EXAMPLE 2: Using Optimistic Locking for Concurrent Updates
# ============================================================================

class UpdateTenantWithOptimisticLockExample:
    """Example: Update tenant with optimistic locking."""

    def __init__(self, session: AsyncSession, metrics: MetricsCollector):
        self.session = session
        self.metrics = metrics

    async def execute(self, tenant_id: str, current_version: int, updates: dict):
        """
        Update tenant with optimistic locking.
        
        Fails if another process updated the tenant first.
        """
        try:
            updated_tenant = await ConcurrencyControl.update_with_optimistic_lock(
                self.session,
                tenant_id,
                current_version,
                updates
            )
            
            self.metrics.record_metric('optimistic_lock_success', 1)
            return updated_tenant
            
        except OptimisticLockError as e:
            # Another process updated the tenant
            self.metrics.record_metric('optimistic_lock_conflict', 1)
            logger.warning(f"Optimistic lock conflict: {str(e)}")
            raise


# ============================================================================
# EXAMPLE 3: Using Pessimistic Locking for Critical Updates
# ============================================================================

class SuspendTenantWithPessimisticLockExample:
    """Example: Suspend tenant with pessimistic locking."""

    def __init__(self, session: AsyncSession, metrics: MetricsCollector):
        self.session = session
        self.metrics = metrics

    async def execute(self, tenant_id: str):
        """
        Suspend tenant with pessimistic locking.
        
        Locks the row so other processes must wait.
        """
        try:
            updated_tenant = await ConcurrencyControl.update_with_pessimistic_lock(
                self.session,
                tenant_id,
                {'status': 'SUSPENDED'}
            )
            
            self.metrics.record_metric('tenant_suspension_success', 1)
            return updated_tenant
            
        except Exception as e:
            self.metrics.record_metric('tenant_suspension_failure', 1)
            logger.error(f"Tenant suspension failed: {str(e)}")
            raise


# ============================================================================
# EXAMPLE 4: Using Backups
# ============================================================================

class BackupExample:
    """Example: Create and manage backups."""

    def __init__(self, database_url: str):
        self.backup_manager = BackupManager(database_url)

    async def daily_backup(self):
        """Create daily backup."""
        try:
            backup_path = await self.backup_manager.create_backup()
            logger.info(f"Daily backup created: {backup_path}")
            
            # Verify backup
            is_valid = await self.backup_manager.verify_backup(backup_path)
            if not is_valid:
                logger.error("Backup verification failed!")
                
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")

    async def cleanup_old_backups(self):
        """Clean up backups older than 30 days."""
        try:
            deleted = await self.backup_manager.cleanup_old_backups(retention_days=30)
            logger.info(f"Cleaned up {deleted} old backups")
        except Exception as e:
            logger.error(f"Backup cleanup failed: {str(e)}")

    async def list_available_backups(self):
        """List all available backups."""
        backups = await self.backup_manager.list_backups()
        for backup in backups:
            logger.info(f"Backup: {backup['name']} ({backup['size_bytes']} bytes)")


# ============================================================================
# EXAMPLE 5: Using Monitoring & Alerting
# ============================================================================

class MonitoringExample:
    """Example: Set up monitoring and health checks."""

    def __init__(self, database_url: str):
        self.metrics = MetricsCollector(retention_hours=24)
        self.health_monitor = HealthMonitor(self.metrics)
        self.performance_monitor = PerformanceMonitor(self.metrics)

    async def setup_health_checks(self):
        """Register health checks."""
        
        async def check_database():
            """Check if database is accessible."""
            try:
                # Try to query database
                # Implementation
                return True
            except:
                return False

        async def check_disk_space():
            """Check if disk space is available."""
            try:
                # Check disk space
                # Implementation
                return True
            except:
                return False

        self.health_monitor.register_check('database', check_database)
        self.health_monitor.register_check('disk_space', check_disk_space)

    async def monitor_operation(self, operation_name: str, operation_fn):
        """
        Monitor an operation and record metrics.
        
        Usage:
            result = await monitor_operation('create_tenant', create_tenant_fn)
        """
        start_time = time.time()
        
        try:
            result = await operation_fn()
            duration = time.time() - start_time
            
            self.metrics.record_metric(f'{operation_name}_time_ms', duration * 1000)
            self.metrics.record_metric(f'{operation_name}_success', 1)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_metric(f'{operation_name}_time_ms', duration * 1000)
            self.metrics.record_metric(f'{operation_name}_failure', 1)
            
            # Create alert for failures
            self.metrics.create_alert(
                AlertSeverity.WARNING,
                f"Operation failed: {operation_name}",
                str(e)
            )
            raise

    async def get_system_status(self):
        """Get overall system status."""
        health = await self.health_monitor.get_system_health()
        performance = self.performance_monitor.get_performance_report()
        
        return {
            'health': health,
            'performance': performance,
            'alerts': [a.to_dict() for a in self.metrics.alerts[-10:]]  # Last 10 alerts
        }


# ============================================================================
# EXAMPLE 6: Complete Use Case with All Features
# ============================================================================

class CompleteUpdateTenantExample:
    """Example: Update tenant with transactions, locking, monitoring."""

    def __init__(
        self,
        session: AsyncSession,
        metrics: MetricsCollector,
        database_url: str
    ):
        self.session = session
        self.transaction_manager = TransactionManager(session)
        self.metrics = metrics
        self.backup_manager = BackupManager(database_url)

    async def execute(
        self,
        tenant_id: str,
        current_version: int,
        updates: dict
    ):
        """
        Complete update with all safety features:
        1. Transaction handling
        2. Optimistic locking
        3. Monitoring
        4. Backup before critical changes
        """
        start_time = time.time()
        
        try:
            # Create backup before critical update
            if 'status' in updates:  # Status change is critical
                await self.backup_manager.create_backup(
                    f"before_status_change_{tenant_id}"
                )
            
            # Execute in transaction
            async with self.transaction_manager.transaction() as session:
                # Update with optimistic lock
                updated_tenant = await ConcurrencyControl.update_with_optimistic_lock(
                    session,
                    tenant_id,
                    current_version,
                    updates
                )
                
                # Record metrics
                duration = time.time() - start_time
                self.metrics.record_metric('tenant_update_time_ms', duration * 1000)
                self.metrics.record_metric('tenant_update_success', 1)
                
                return updated_tenant
                
        except OptimisticLockError as e:
            self.metrics.record_metric('tenant_update_conflict', 1)
            logger.warning(f"Update conflict: {str(e)}")
            raise
            
        except Exception as e:
            self.metrics.record_metric('tenant_update_failure', 1)
            self.metrics.create_alert(
                AlertSeverity.CRITICAL,
                f"Tenant update failed: {tenant_id}",
                str(e)
            )
            logger.error(f"Tenant update failed: {str(e)}")
            raise
