"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Migration Type: ${message.split(':')[0] if ':' in message else 'schema'}
Risk Level: ${message.split(':')[1].strip() if ':' in message and len(message.split(':')) > 1 else 'medium'}

Safety Checklist:
- [ ] Backwards compatible (old code can run with new schema)
- [ ] Forwards compatible (new code can run with old schema during rollout)
- [ ] Tested on production-size dataset
- [ ] Rollback plan documented
- [ ] Monitoring alerts updated
- [ ] Zero-downtime deployment strategy confirmed

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """
    Apply forward migration.
    
    Best Practices:
    1. Add columns as nullable first, then backfill, then set NOT NULL
    2. Create indexes CONCURRENTLY (PostgreSQL)
    3. Add foreign keys as NOT VALID first, then validate separately
    4. Use batch operations for large data changes
    5. Add new tables/columns before removing old ones (expand-contract pattern)
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """
    Revert migration.
    
    Considerations:
    1. Data loss: Document what data will be lost on rollback
    2. Dependencies: Ensure dependent services can handle rollback
    3. Timing: Some rollbacks may require manual data migration
    4. Testing: Rollback should be tested as thoroughly as upgrade
    """
    ${downgrades if downgrades else "pass"}
