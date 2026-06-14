"""add_content_type_to_document_versions

Revision ID: a1b2c3d4e5f7
Revises: z3a4b5c6d7e8
Create Date: 2025-01-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "z3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable content_type column to document_versions table."""
    op.add_column(
        "document_versions",
        sa.Column("content_type", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    """Remove content_type column from document_versions table."""
    op.drop_column("document_versions", "content_type")
