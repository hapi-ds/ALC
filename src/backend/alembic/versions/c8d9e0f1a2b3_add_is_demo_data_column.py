"""add_is_demo_data_column

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_demo_data column to documents, templates, virtual_folders, workflow_definitions."""
    op.add_column(
        "documents",
        sa.Column("is_demo_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "templates",
        sa.Column("is_demo_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "virtual_folders",
        sa.Column("is_demo_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "workflow_definitions",
        sa.Column("is_demo_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    """Remove is_demo_data column from all tables."""
    op.drop_column("workflow_definitions", "is_demo_data")
    op.drop_column("virtual_folders", "is_demo_data")
    op.drop_column("templates", "is_demo_data")
    op.drop_column("documents", "is_demo_data")
