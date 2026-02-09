# Quick Start: Production Features

Get started with the 4 production-ready features in 5 minutes.

## 1. Transaction Handling

**Use this for:** Multi-step operations that must all succeed or all fail

```python
from app.infrastructure.database.transaction import TransactionManager

transaction_manager = TransactionManager(session)

async with transaction_manager.transaction() as session:
    await create_tenant(session, data)
    await initialize_billing(session, tenant_id)
    await send_email(session, email)
    # All succeed or all fail
```

---

## 2. Concurrency Control

**Use this for:** Preventing race conditions when multiple processes update same data

### Option A: Optimistic Locking (Recommended)

```python
from app.infrastructure.database.concurrency import ConcurrencyControl, OptimisticLockError

try:
    updated = await ConcurrencyControl.update_with_optimistic_lock(
        session,
        tenant_id="123",
        current_version=5,  # Must match database
        update_data={'status': 'SUSPENDED'}
    )
except OptimisticLockError:
    # Another process updated it - retry with fresh data
    pass
```

### Option B: Pessimistic Locking (For critical operations)

```python
updated = await ConcurrencyControl.update_with_pessimistic_lock(
    session,
    tenant_id="123",
    update_data={'status': 'SUSPENDED'}
)
```

---

## 3. Backup Management

**Use this for:** Creating backups and recovering from disasters

```python
from app.infrastructure.database.backup import BackupManager

backup_manager = BackupManager(
    database_url="postgresql+asyncpg://user:pass@host/db",
    backup_dir="./backups"
)

# Create backup
backup_path = await backup_manager.create_backup()

# Verify it's valid
is_valid = await backup_manager.verify_backup(backup_path)

# List all backups
backups = await backup_manager.list_backups()

# Restore from backup
await backup_manager.restore_backup(backup_path)

# Clean up old backups (keep last 30 days)
await backup_manager.cleanup_old_backups(retention_days=30)
```

---

## 4. Monitoring & Alerting

**Use this for:** Tracking system health and detecting issues

```python
from app.infrastructure.observability.monitoring import (
    MetricsCollector, HealthMonitor, PerformanceMonitor, AlertSeverity
)

# Create collectors
metrics = MetricsCollector(retention_hours=24)
health_monitor = HealthMonitor(metrics)
perf_monitor = PerformanceMonitor(metrics)

# Record metrics
metrics.record_metric('db_query_time_ms', 150)
metrics.record_metric('api_response_time_ms', 250)

# Create alerts
metrics.create_alert(
    AlertSeverity.CRITICAL,
    "Database connection failed",
    "Cannot connect to PostgreSQL"
)

# Register health checks
async def check_database():
    try:
        # Try to query database
        return True
    except:
        return False

health_monitor.register_check('database', check_database)

# Get system health
health = await health_monitor.get_system_health()
print(health)
# {'healthy': True, 'checks': {'database': True}, 'timestamp': '...'}

# Get performance report
report = perf_monitor.get_performance_report()
```

---

## Complete Example: Update Tenant

```python
import time
from app.infrastructure.database.transaction import TransactionManager
from app.infrastructure.database.concurrency import ConcurrencyControl, OptimisticLockError
from app.infrastructure.observability.monitoring import MetricsCollector, AlertSeverity

async def update_tenant_complete(
    session,
    metrics,
    tenant_id: str,
    current_version: int,
    updates: dict
):
    """Update tenant with all safety features."""
    start_time = time.time()
    transaction_manager = TransactionManager(session)
    
    try:
        # Execute in transaction
        async with transaction_manager.transaction() as session:
            # Update with optimistic lock
            updated_tenant = await ConcurrencyControl.update_with_optimistic_lock(
                session,
                tenant_id,
                current_version,
                updates
            )
            
            # Record success
            duration = time.time() - start_time
            metrics.record_metric('tenant_update_time_ms', duration * 1000)
            metrics.record_metric('tenant_update_success', 1)
            
            return updated_tenant
            
    except OptimisticLockError as e:
        # Conflict detected
        metrics.record_metric('tenant_update_conflict', 1)
        raise
        
    except Exception as e:
        # Error occurred
        metrics.record_metric('tenant_update_failure', 1)
        metrics.create_alert(
            AlertSeverity.CRITICAL,
            f"Tenant update failed: {tenant_id}",
            str(e)
        )
        raise
```

---

## Integration Checklist

- [ ] Import transaction manager in use cases
- [ ] Wrap multi-step operations in transactions
- [ ] Add version column to tenants table (for optimistic locking)
- [ ] Use ConcurrencyControl for updates
- [ ] Create BackupManager instance
- [ ] Set up daily backup schedule
- [ ] Create MetricsCollector instance
- [ ] Add metrics to use cases
- [ ] Register health checks
- [ ] Test each feature

---

## Files Reference

| File | Purpose |
|------|---------|
| `app/infrastructure/database/transaction.py` | Transaction handling |
| `app/infrastructure/database/concurrency.py` | Concurrency control |
| `app/infrastructure/database/backup.py` | Backup management |
| `app/infrastructure/observability/monitoring.py` | Monitoring & alerting |
| `app/infrastructure/examples.py` | Complete working examples |
| `docs/IMPLEMENTATION_GUIDE.md` | Detailed setup guide |
| `PRODUCTION_FEATURES.md` | Feature overview |

---

## Need More Details?

- **Setup Guide:** See `docs/IMPLEMENTATION_GUIDE.md`
- **Working Examples:** See `app/infrastructure/examples.py`
- **API Reference:** Check docstrings in each module

---

## Key Points

✅ **Transactions** - Use for multi-step operations  
✅ **Concurrency** - Use optimistic locking for most updates  
✅ **Backups** - Create daily, keep 30 days  
✅ **Monitoring** - Record metrics, create alerts  

That's it! You're ready to go.
