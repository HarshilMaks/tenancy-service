"""Initial tenant schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-02-01 00:00:00.000000

Migration Type: schema
Risk Level: low (initial setup)

Safety Checklist:
- [x] Backwards compatible (N/A - initial setup)
- [x] Forwards compatible (N/A - initial setup)
- [x] Tested on production-size dataset
- [x] Rollback plan documented
- [x] Monitoring alerts updated
- [x] Zero-downtime deployment strategy confirmed

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create initial tenant schema.
    
    Tables:
    - tenants: Core tenant aggregate with lifecycle, plan, and region
    - tenant_events: Event sourcing for audit trail and event-driven integration
    """
    
    # Create tenant status enum (let SQLAlchemy handle creation)
    tenant_status_enum = sa.Enum('provisioning', 'active', 'suspended', 'terminated', name='tenant_status', create_type=True)
    plan_tier_enum = sa.Enum('starter', 'professional', 'enterprise', 'custom', name='plan_tier', create_type=True)
    
    # Create tenants table (aggregate root)
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('normalized_name', sa.String(255), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=True, comment='External system reference (e.g., CRM ID)'),
        sa.Column('status', tenant_status_enum, nullable=False),
        sa.Column('plan_tier', plan_tier_enum, nullable=False),
        sa.Column('region', sa.String(50), nullable=False, comment='Primary region for data residency'),
        sa.Column('compliance_requirements', postgresql.JSONB, nullable=True, comment='GDPR, HIPAA, SOC2, etc.'),
        sa.Column('plan_limits', postgresql.JSONB, nullable=True, comment='Usage limits, feature flags, SLA'),
        sa.Column('metadata', postgresql.JSONB, nullable=True, comment='Custom tenant metadata'),
        sa.Column('suspended_reason', sa.String(500), nullable=True),
        sa.Column('suspended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1', comment='Optimistic locking version'),
        
        # Constraints
        sa.CheckConstraint(
            "status != 'suspended' OR (suspended_reason IS NOT NULL AND suspended_at IS NOT NULL)",
            name='check_suspended_requires_reason'
        ),
        sa.CheckConstraint(
            "status = 'suspended' OR (suspended_reason IS NULL AND suspended_at IS NULL)",
            name='check_unsuspended_no_reason'
        ),
    )
    
    # Create indexes for fast lookups
    op.create_index('ix_tenants_normalized_name', 'tenants', ['normalized_name'], unique=True)
    op.create_index('ix_tenants_external_id', 'tenants', ['external_id'], unique=True, postgresql_where=sa.text('external_id IS NOT NULL'))
    op.create_index('ix_tenants_status', 'tenants', ['status'])
    op.create_index('ix_tenants_region', 'tenants', ['region'])
    op.create_index('ix_tenants_plan_tier', 'tenants', ['plan_tier'])
    op.create_index('ix_tenants_created_at', 'tenants', ['created_at'])
    
    # Create tenant events table (event sourcing)
    op.create_table(
        'tenant_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('event_version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('metadata', postgresql.JSONB, nullable=True, comment='User, correlation ID, etc.'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('sequence_number', sa.BigInteger, nullable=False, comment='Global ordering of events'),
        
        # Foreign key to tenant
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for event queries
    op.create_index('ix_tenant_events_tenant_id', 'tenant_events', ['tenant_id'])
    op.create_index('ix_tenant_events_event_type', 'tenant_events', ['event_type'])
    op.create_index('ix_tenant_events_created_at', 'tenant_events', ['created_at'])
    op.create_index('ix_tenant_events_sequence', 'tenant_events', ['sequence_number'], unique=True)
    
    # Create sequence for event ordering
    op.execute('CREATE SEQUENCE tenant_event_sequence START 1')
    
    # Create updated_at trigger for tenants table
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER update_tenants_updated_at
        BEFORE UPDATE ON tenants
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)
    
    # Create function to auto-populate sequence_number
    op.execute("""
        CREATE OR REPLACE FUNCTION set_event_sequence_number()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.sequence_number = nextval('tenant_event_sequence');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER set_tenant_event_sequence
        BEFORE INSERT ON tenant_events
        FOR EACH ROW
        EXECUTE FUNCTION set_event_sequence_number();
    """)


def downgrade() -> None:
    """
    Drop initial tenant schema.
    
    WARNING: This will destroy all tenant data.
    Only use in non-production environments or with confirmed backup.
    """
    # Drop triggers
    op.execute('DROP TRIGGER IF EXISTS set_tenant_event_sequence ON tenant_events')
    op.execute('DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants')
    
    # Drop functions
    op.execute('DROP FUNCTION IF EXISTS set_event_sequence_number()')
    op.execute('DROP FUNCTION IF EXISTS update_updated_at_column()')
    
    # Drop sequence
    op.execute('DROP SEQUENCE IF EXISTS tenant_event_sequence')
    
    # Drop tables
    op.drop_table('tenant_events')
    op.drop_table('tenants')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS plan_tier')
    op.execute('DROP TYPE IF EXISTS tenant_status')
