# Database Migrations

Production-grade database migration system for the Tenancy Service using Alembic.

## Quick Start

```bash
# Create a new migration
alembic revision -m "add tenant status column"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# Show current version
alembic current
```

## Migration Best Practices

### Zero-Downtime Migrations

For production deployments with zero downtime, follow the **expand-contract pattern**:

1. **Expand Phase** (backwards compatible):
   - Add new columns as nullable
   - Create new tables
   - Add new indexes CONCURRENTLY
   - Dual-write to old and new columns

2. **Migrate Phase** (deploy new code):
   - Deploy application code that reads from new schema
   - Backfill data if needed
   - Monitor for errors

3. **Contract Phase** (remove old schema):
   - Stop writing to old columns
   - Remove old columns/tables
   - Drop unused indexes

### Example: Adding a Required Column

**Migration 1 - Expand (safe to deploy):**
```python
def upgrade():
    # Add column as nullable first
    op.add_column('tenants', sa.Column('plan_tier', sa.String(50), nullable=True))
    
def downgrade():
    op.drop_column('tenants', 'plan_tier')
```

**Migration 2 - Backfill (run after deploy):**
```python
def upgrade():
    # Set default value for existing rows
    op.execute("UPDATE tenants SET plan_tier = 'standard' WHERE plan_tier IS NULL")
    
def downgrade():
    pass  # No rollback needed for data changes
```

**Migration 3 - Contract (make NOT NULL):**
```python
def upgrade():
    # Now safe to make it required
    op.alter_column('tenants', 'plan_tier', nullable=False)
    
def downgrade():
    op.alter_column('tenants', 'plan_tier', nullable=True)
```

### PostgreSQL-Specific Optimizations

#### Concurrent Indexes
```python
def upgrade():
    # Create index without locking table
    op.create_index(
        'ix_tenants_status',
        'tenants',
        ['status'],
        postgresql_concurrently=True
    )

# Must be outside transaction - add to migration:
# revision_environment = True in migration file
```

#### Adding Foreign Keys Safely
```python
def upgrade():
    # Step 1: Add FK as NOT VALID (no full table scan)
    op.execute("""
        ALTER TABLE tenants 
        ADD CONSTRAINT fk_tenant_region 
        FOREIGN KEY (region_id) REFERENCES regions(id) 
        NOT VALID
    """)
    
    # Step 2: Validate separately (allows concurrent operations)
    op.execute("""
        ALTER TABLE tenants 
        VALIDATE CONSTRAINT fk_tenant_region
    """)
```

### Migration Naming Conventions

Use descriptive names that indicate the change type and risk level:

```bash
# Schema changes
alembic revision -m "schema: add tenant subscription table - low risk"

# Data migrations
alembic revision -m "data: backfill tenant plan tiers - medium risk"

# Breaking changes
alembic revision -m "breaking: remove deprecated status column - high risk"
```

### Testing Migrations

#### Local Testing
```bash
# Apply migration
alembic upgrade head

# Test application functionality
pytest tests/integration/

# Test rollback
alembic downgrade -1

# Verify application still works with old schema
pytest tests/integration/

# Re-apply
alembic upgrade head
```

#### Production-Like Testing
```bash
# Restore production snapshot to staging
pg_restore -d staging_db production_dump.sql

# Time the migration
time alembic upgrade head

# Check for locks
SELECT * FROM pg_locks WHERE NOT granted;

# Verify data integrity
SELECT COUNT(*) FROM tenants WHERE plan_tier IS NULL;
```

### Pre-Deployment Checklist

Before applying migrations to production:

- [ ] Tested on production-size dataset (staging)
- [ ] Migration completes in under 30 seconds (or uses online operations)
- [ ] Rollback tested and verified
- [ ] No exclusive locks on large tables
- [ ] Application can handle partial migration state
- [ ] Database backup verified and recent
- [ ] Monitoring alerts configured for new columns/tables
- [ ] Team notified of deployment window
- [ ] Rollback plan documented and ready

### Emergency Rollback

If a migration causes issues in production:

```bash
# Quick rollback (if caught immediately)
alembic downgrade -1

# Manual rollback (if automatic fails)
psql -d tenancy_db -f rollback_script.sql

# Verify application health
curl http://api/health

# Check error logs
kubectl logs -f deployment/tenancy-service --tail=100
```

### Monitoring Migrations

Key metrics to monitor during and after migrations:

- **Lock Duration**: `SELECT * FROM pg_stat_activity WHERE wait_event_type = 'Lock'`
- **Query Performance**: Check slow query logs for regressions
- **Error Rates**: Monitor application error rates for new issues
- **Database Size**: Track disk usage after schema changes

## Common Patterns

### Adding an Enum Column
```python
from sqlalchemy.dialects.postgresql import ENUM

def upgrade():
    # Create enum type
    status_enum = ENUM('active', 'suspended', 'terminated', name='tenant_status')
    status_enum.create(op.get_bind())
    
    # Add column
    op.add_column('tenants', sa.Column('status', status_enum, nullable=True))

def downgrade():
    op.drop_column('tenants', 'status')
    op.execute('DROP TYPE tenant_status')
```

### Large Data Migration with Batching
```python
def upgrade():
    connection = op.get_bind()
    
    # Process in batches to avoid long transactions
    batch_size = 1000
    offset = 0
    
    while True:
        result = connection.execute(f"""
            UPDATE tenants 
            SET normalized_name = LOWER(name)
            WHERE id IN (
                SELECT id FROM tenants 
                WHERE normalized_name IS NULL 
                LIMIT {batch_size}
            )
        """)
        
        if result.rowcount == 0:
            break
            
        offset += batch_size
```

### Renaming a Column (Zero-Downtime)
```python
# Migration 1: Add new column
def upgrade():
    op.add_column('tenants', sa.Column('company_name', sa.String(255)))
    # Trigger to keep columns in sync
    op.execute("""
        CREATE TRIGGER sync_tenant_name
        BEFORE INSERT OR UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION sync_names()
    """)

# Migration 2: Backfill data
def upgrade():
    op.execute("UPDATE tenants SET company_name = name")

# Migration 3: Remove old column
def upgrade():
    op.execute("DROP TRIGGER sync_tenant_name ON tenants")
    op.drop_column('tenants', 'name')
```

## Troubleshooting

### Migration Stuck
```sql
-- Check for blocking queries
SELECT pid, query, state, wait_event 
FROM pg_stat_activity 
WHERE state != 'idle';

-- Kill blocking query (last resort)
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = <blocking_pid>;
```

### Alembic Out of Sync
```bash
# Stamp current version without running migrations
alembic stamp head

# Resolve conflicts manually
alembic history
alembic stamp <correct_revision>
```

### Testing Failed Migration Recovery
```bash
# Start transaction
BEGIN;

# Run upgrade
alembic upgrade head;

# If something wrong, rollback
ROLLBACK;

# Otherwise commit
COMMIT;
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [PostgreSQL Concurrent Operations](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY)
- [Expand-Contract Pattern](https://martinfowler.com/bliki/ParallelChange.html)
