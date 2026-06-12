"""Add vigilance_execution_id FK to literature_ingestion_records.

Links ingestion records to vigilance search executions so the ingestion
pipeline can dispatch signal detection tasks when vigilance-linked
records reach the indexed state.

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2025-01-01 00:00:00.000000

References:
    - Requirements 5.1, 5.7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "y2z3a4b5c6d7"
down_revision: str = "x1y2z3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add vigilance_execution_id column and index."""
    op.add_column(
        "literature_ingestion_records",
        sa.Column(
            "vigilance_execution_id",
            sa.Integer(),
            sa.ForeignKey(
                "vigilance_search_executions.id",
                name="fk_ingestion_records_vigilance_execution_id",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_lit_ingestion_vigilance_execution",
        "literature_ingestion_records",
        ["vigilance_execution_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove vigilance_execution_id column and index."""
    op.drop_index(
        "ix_lit_ingestion_vigilance_execution",
        table_name="literature_ingestion_records",
    )
    op.drop_column("literature_ingestion_records", "vigilance_execution_id")
