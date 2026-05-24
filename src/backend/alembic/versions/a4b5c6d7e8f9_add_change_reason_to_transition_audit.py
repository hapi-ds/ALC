"""add_change_reason_to_transition_audit

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add change_reason column to workflow_transition_audits.

    Adds a nullable String(500) column to store the audit reason for each
    state transition. Existing records will have NULL for this column.
    Skips if the table does not exist (may have been removed in a later migration).
    """
    from alembic import context
    bind = context.get_bind()
    inspector = sa.inspect(bind)
    if "workflow_transition_audits" in inspector.get_table_names():
        op.add_column(
            "workflow_transition_audits",
            sa.Column("change_reason", sa.String(500), nullable=True),
        )


def downgrade() -> None:
    """Remove change_reason column from workflow_transition_audits."""
    from alembic import context
    bind = context.get_bind()
    inspector = sa.inspect(bind)
    if "workflow_transition_audits" in inspector.get_table_names():
        op.drop_column("workflow_transition_audits", "change_reason")
