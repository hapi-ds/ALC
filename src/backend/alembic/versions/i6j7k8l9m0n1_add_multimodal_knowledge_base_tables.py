"""add_multimodal_knowledge_base_tables

Revision ID: i6j7k8l9m0n1
Revises: h5i6j7k8l9m0
Create Date: 2026-07-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "i6j7k8l9m0n1"
down_revision: Union[str, Sequence[str], None] = "h5i6j7k8l9m0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create multimodal knowledge base tables.

    Creates:
    - video_metadata: Video-specific metadata for Training Video documents
    - video_step_sequences: Extracted steps from video frame analysis
    - video_sop_links: Association between videos and SOPs
    - discrepancy_reports: Generated alignment reports
    - processing_jobs: Async job tracking for video operations
    """
    # --- Create video_metadata table ---
    op.create_table(
        "video_metadata",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("resolution_width", sa.Integer(), nullable=True),
        sa.Column("resolution_height", sa.Integer(), nullable=True),
        sa.Column("frame_count", sa.Integer(), nullable=True),
        sa.Column("codec", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_video_metadata_document_id_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_metadata")),
        sa.UniqueConstraint(
            "document_id", name=op.f("uq_video_metadata_document_id")
        ),
    )

    # --- Create video_step_sequences table ---
    op.create_table(
        "video_step_sequences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("start_timestamp", sa.Float(), nullable=False),
        sa.Column("end_timestamp", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("frame_indices", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("audio_transcript", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_video_step_sequences_document_id_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_step_sequences")),
    )
    op.create_index(
        op.f("ix_video_step_sequences_document_id"),
        "video_step_sequences",
        ["document_id"],
        unique=False,
    )

    # --- Create video_sop_links table ---
    op.create_table(
        "video_sop_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_document_id", sa.Integer(), nullable=False),
        sa.Column("sop_document_id", sa.Integer(), nullable=False),
        sa.Column("sop_version", sa.String(length=20), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("linked_by", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_document_id"],
            ["documents.id"],
            name=op.f("fk_video_sop_links_video_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["sop_document_id"],
            ["documents.id"],
            name=op.f("fk_video_sop_links_sop_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["linked_by"],
            ["users.id"],
            name=op.f("fk_video_sop_links_linked_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_video_sop_links_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video_sop_links")),
        sa.UniqueConstraint(
            "video_document_id",
            "sop_document_id",
            name="uq_video_sop_link",
        ),
    )
    op.create_index(
        op.f("ix_video_sop_links_video_document_id"),
        "video_sop_links",
        ["video_document_id"],
        unique=False,
    )

    # --- Create discrepancy_reports table ---
    op.create_table(
        "discrepancy_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_document_id", sa.Integer(), nullable=False),
        sa.Column("sop_document_id", sa.Integer(), nullable=False),
        sa.Column("alignment_score", sa.Float(), nullable=False),
        sa.Column("total_video_steps", sa.Integer(), nullable=False),
        sa.Column("total_sop_steps", sa.Integer(), nullable=False),
        sa.Column("matched_steps", sa.Text(), nullable=False),
        sa.Column("missing_steps", sa.Text(), nullable=False),
        sa.Column("extra_steps", sa.Text(), nullable=False),
        sa.Column("order_mismatches", sa.Text(), nullable=False),
        sa.Column(
            "requires_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("generated_by", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_document_id"],
            ["documents.id"],
            name=op.f("fk_discrepancy_reports_video_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["sop_document_id"],
            ["documents.id"],
            name=op.f("fk_discrepancy_reports_sop_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["generated_by"],
            ["users.id"],
            name=op.f("fk_discrepancy_reports_generated_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_discrepancy_reports_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discrepancy_reports")),
    )
    op.create_index(
        op.f("ix_discrepancy_reports_video_document_id"),
        "discrepancy_reports",
        ["video_document_id"],
        unique=False,
    )

    # --- Create processing_jobs table ---
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "progress_percent",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "estimated_duration_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("result_reference", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_processing_jobs_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_processing_jobs_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processing_jobs")),
        sa.UniqueConstraint("job_id", name=op.f("uq_processing_jobs_job_id")),
    )
    op.create_index(
        op.f("ix_processing_jobs_job_id"),
        "processing_jobs",
        ["job_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_processing_jobs_document_id"),
        "processing_jobs",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all multimodal knowledge base tables."""
    # --- Drop processing_jobs table ---
    op.drop_index(
        op.f("ix_processing_jobs_document_id"),
        table_name="processing_jobs",
    )
    op.drop_index(
        op.f("ix_processing_jobs_job_id"),
        table_name="processing_jobs",
    )
    op.drop_table("processing_jobs")

    # --- Drop discrepancy_reports table ---
    op.drop_index(
        op.f("ix_discrepancy_reports_video_document_id"),
        table_name="discrepancy_reports",
    )
    op.drop_table("discrepancy_reports")

    # --- Drop video_sop_links table ---
    op.drop_index(
        op.f("ix_video_sop_links_video_document_id"),
        table_name="video_sop_links",
    )
    op.drop_table("video_sop_links")

    # --- Drop video_step_sequences table ---
    op.drop_index(
        op.f("ix_video_step_sequences_document_id"),
        table_name="video_step_sequences",
    )
    op.drop_table("video_step_sequences")

    # --- Drop video_metadata table ---
    op.drop_table("video_metadata")
