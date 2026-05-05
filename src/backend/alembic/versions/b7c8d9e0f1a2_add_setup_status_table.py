"""add_setup_status_table

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-01 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create setup_status table for first-run wizard state tracking.

    Validates: Requirements 1.4
    """
    op.create_table(
        "setup_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("admin_created", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("company_created", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ai_mode_configured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("demo_data_seeded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("root_admin_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("ai_hardware_mode", sa.String(length=10), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["root_admin_id"],
            ["users.id"],
            name=op.f("fk_setup_status_root_admin_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_setup_status_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_setup_status")),
    )


def downgrade() -> None:
    """Drop setup_status table."""
    op.drop_table("setup_status")
