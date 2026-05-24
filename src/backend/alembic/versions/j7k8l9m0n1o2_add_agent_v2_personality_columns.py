"""add_agent_v2_personality_columns

Revision ID: j7k8l9m0n1o2
Revises: i6j7k8l9m0n1
Create Date: 2026-08-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "j7k8l9m0n1o2"
down_revision: Union[str, Sequence[str], None] = "i6j7k8l9m0n1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add v2.0 personality framework columns to agent_definitions table."""
    op.add_column(
        "agent_definitions",
        sa.Column("archetype", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "agent_definitions",
        sa.Column(
            "personality_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_definitions",
        sa.Column(
            "contextual_tuning",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_definitions",
        sa.Column(
            "evaluation_rubric",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_definitions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_agent_definitions_archetype",
        "agent_definitions",
        ["archetype"],
    )


def downgrade() -> None:
    """Remove v2.0 personality framework columns from agent_definitions table."""
    op.drop_index("ix_agent_definitions_archetype", table_name="agent_definitions")
    op.drop_column("agent_definitions", "updated_at")
    op.drop_column("agent_definitions", "evaluation_rubric")
    op.drop_column("agent_definitions", "contextual_tuning")
    op.drop_column("agent_definitions", "personality_profile")
    op.drop_column("agent_definitions", "archetype")
