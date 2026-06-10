"""add literature embedding tables

Revision ID: w0x1y2z3a4b5
Revises: v9w0x1y2z3a4
Create Date: 2027-03-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "w0x1y2z3a4b5"
down_revision: Union[str, Sequence[str], None] = "v9w0x1y2z3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create literature embedding configuration and reindex job tables.

    Tables created:
        - literature_embedding_configurations: Per-company embedding settings
        - literature_reindex_jobs: Batch re-indexing job progress tracking
    """

    # --- literature_embedding_configurations ---
    op.create_table(
        "literature_embedding_configurations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "chunk_size_tokens",
            sa.Integer(),
            nullable=False,
            server_default="512",
        ),
        sa.Column(
            "chunk_overlap_tokens",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
        sa.Column(
            "auto_embed_on_ingest",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "embed_abstract_only",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "max_chunks_per_document",
            sa.Integer(),
            nullable=False,
            server_default="500",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_embedding_config_company_id_companies",
        ),
        sa.UniqueConstraint(
            "company_id", name="uq_lit_embedding_config_company_id"
        ),
    )

    # Index on company_id for FK lookups (unique constraint also creates one,
    # but explicit for clarity)
    op.create_index(
        "ix_literature_embedding_configurations_company_id",
        "literature_embedding_configurations",
        ["company_id"],
    )

    # --- literature_reindex_jobs ---
    op.create_table(
        "literature_reindex_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "total_records", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_batches", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "current_batch", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "records_processed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "records_failed", sa.Integer(), nullable=False, server_default="0"
        ),
        # Timestamps
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Cancellation fields
        sa.Column("cancelled_by", sa.Integer(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_reindex_jobs_company_id_companies",
        ),
        sa.UniqueConstraint("task_id", name="uq_lit_reindex_jobs_task_id"),
    )

    # Index on task_id for progress lookups by UUID
    op.create_index(
        "ix_literature_reindex_jobs_task_id",
        "literature_reindex_jobs",
        ["task_id"],
    )

    # Index on company_id for FK lookups and filtering jobs by company
    op.create_index(
        "ix_literature_reindex_jobs_company_id",
        "literature_reindex_jobs",
        ["company_id"],
    )


def downgrade() -> None:
    """Drop literature embedding tables in reverse creation order."""
    op.drop_table("literature_reindex_jobs")
    op.drop_table("literature_embedding_configurations")
