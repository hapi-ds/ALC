"""add phase 9.4 literature review tables

Revision ID: e94f1a2b3c4d
Revises: w0x1y2z3a4b5
Create Date: 2027-03-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e94f1a2b3c4d"
down_revision: Union[str, Sequence[str], None] = "w0x1y2z3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 9.4 Literature Review & Synthesis tables.

    Tables created (in dependency order):
        - literature_screening_protocols
        - literature_screening_configurations
        - literature_slr_reviews
        - literature_screening_runs
        - literature_screening_decisions
        - literature_contradiction_alerts
        - literature_novelty_flags
    """

    # --- literature_screening_protocols ---
    op.create_table(
        "literature_screening_protocols",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="'draft'",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        # PICO framework fields
        sa.Column("pico_population", sa.String(length=2000), nullable=True),
        sa.Column("pico_intervention", sa.String(length=2000), nullable=True),
        sa.Column("pico_comparison", sa.String(length=2000), nullable=True),
        sa.Column("pico_outcome", sa.String(length=2000), nullable=True),
        # Custom criteria (JSONB)
        sa.Column(
            "inclusion_criteria", postgresql.JSONB(), nullable=True
        ),
        sa.Column(
            "exclusion_criteria", postgresql.JSONB(), nullable=True
        ),
        # Filtering fields
        sa.Column(
            "publication_date_from", sa.String(length=10), nullable=True
        ),
        sa.Column(
            "publication_date_to", sa.String(length=10), nullable=True
        ),
        sa.Column(
            "allowed_publication_types",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
        sa.Column(
            "allowed_languages",
            postgresql.ARRAY(sa.String()),
            nullable=True,
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
            name="fk_lit_screening_protocols_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_lit_screening_protocols_created_by",
        ),
    )

    op.create_index(
        "ix_literature_screening_protocols_company_id",
        "literature_screening_protocols",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_screening_protocols_company_status",
        "literature_screening_protocols",
        ["company_id", "status"],
    )

    # --- literature_screening_configurations ---
    op.create_table(
        "literature_screening_configurations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "auto_screen_on_index",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "default_batch_size",
            sa.Integer(),
            nullable=False,
            server_default="20",
        ),
        sa.Column(
            "confidence_threshold_for_auto_include",
            sa.Float(),
            nullable=False,
            server_default="0.8",
        ),
        sa.Column(
            "max_concurrent_screening_tasks",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "contradiction_detection_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
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
            name="fk_lit_screening_config_company_id",
        ),
        sa.UniqueConstraint(
            "company_id", name="uq_screening_config_company"
        ),
    )

    op.create_index(
        "ix_literature_screening_configurations_company_id",
        "literature_screening_configurations",
        ["company_id"],
    )

    # --- literature_slr_reviews ---
    op.create_table(
        "literature_slr_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="'protocol_defined'",
        ),
        sa.Column("record_filter", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("completed_by", sa.Integer(), nullable=True),
        sa.Column(
            "records_identified",
            sa.Integer(),
            nullable=False,
            server_default="0",
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_slr_reviews_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["literature_screening_protocols.id"],
            name="fk_lit_slr_reviews_protocol_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_lit_slr_reviews_created_by",
        ),
    )

    op.create_index(
        "ix_literature_slr_reviews_company_id",
        "literature_slr_reviews",
        ["company_id"],
    )
    op.create_index(
        "ix_literature_slr_reviews_protocol_id",
        "literature_slr_reviews",
        ["protocol_id"],
    )
    op.create_index(
        "ix_lit_slr_reviews_company_status",
        "literature_slr_reviews",
        ["company_id", "status"],
    )

    # --- literature_screening_runs ---
    op.create_table(
        "literature_screening_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        # Status and progress tracking
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="'queued'",
        ),
        sa.Column(
            "total_records",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "screened_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "include_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "exclude_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "uncertain_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "failed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # Batch configuration
        sa.Column(
            "batch_size",
            sa.Integer(),
            nullable=False,
            server_default="20",
        ),
        sa.Column(
            "total_batches",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_batch",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        # Timestamps and tracking
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_duration_ms", sa.Integer(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["literature_slr_reviews.id"],
            name="fk_lit_screening_runs_review_id",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["literature_screening_protocols.id"],
            name="fk_lit_screening_runs_protocol_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_screening_runs_company_id",
        ),
    )

    op.create_index(
        "ix_literature_screening_runs_review_id",
        "literature_screening_runs",
        ["review_id"],
    )
    op.create_index(
        "ix_literature_screening_runs_company_id",
        "literature_screening_runs",
        ["company_id"],
    )
    op.create_index(
        "ix_literature_screening_runs_celery_task_id",
        "literature_screening_runs",
        ["celery_task_id"],
    )
    op.create_index(
        "ix_lit_screening_runs_company_status",
        "literature_screening_runs",
        ["company_id", "status"],
    )

    # --- literature_screening_decisions ---
    op.create_table(
        "literature_screening_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("screening_run_id", sa.Integer(), nullable=False),
        sa.Column("ingestion_record_id", sa.Integer(), nullable=False),
        sa.Column("protocol_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        # AI screening result
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "matched_inclusion_criteria",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "matched_exclusion_criteria",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column("screening_duration_ms", sa.Integer(), nullable=False),
        # Human override fields
        sa.Column("human_verdict", sa.String(length=20), nullable=True),
        sa.Column("human_rationale", sa.Text(), nullable=True),
        sa.Column("human_reviewer_id", sa.Integer(), nullable=True),
        sa.Column(
            "human_override_at", sa.DateTime(timezone=True), nullable=True
        ),
        # Timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["screening_run_id"],
            ["literature_screening_runs.id"],
            name="fk_lit_screening_decisions_run_id",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_record_id"],
            ["literature_ingestion_records.id"],
            name="fk_lit_screening_decisions_ingestion_record_id",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_id"],
            ["literature_screening_protocols.id"],
            name="fk_lit_screening_decisions_protocol_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_screening_decisions_company_id",
        ),
    )

    op.create_index(
        "ix_literature_screening_decisions_screening_run_id",
        "literature_screening_decisions",
        ["screening_run_id"],
    )
    op.create_index(
        "ix_literature_screening_decisions_ingestion_record_id",
        "literature_screening_decisions",
        ["ingestion_record_id"],
    )
    op.create_index(
        "ix_literature_screening_decisions_protocol_id",
        "literature_screening_decisions",
        ["protocol_id"],
    )
    op.create_index(
        "ix_literature_screening_decisions_company_id",
        "literature_screening_decisions",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_screening_decisions_run_record",
        "literature_screening_decisions",
        ["screening_run_id", "ingestion_record_id"],
    )
    op.create_index(
        "ix_lit_screening_decisions_company_verdict",
        "literature_screening_decisions",
        ["company_id", "verdict"],
    )

    # --- literature_contradiction_alerts ---
    op.create_table(
        "literature_contradiction_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ingestion_record_id", sa.Integer(), nullable=False),
        sa.Column(
            "internal_document_id", sa.String(length=36), nullable=False
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        # Contradiction details
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column(
            "contradiction_description", sa.Text(), nullable=False
        ),
        sa.Column("evidence_from_literature", sa.Text(), nullable=False),
        sa.Column(
            "recommended_action", sa.String(length=1000), nullable=False
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "affected_internal_sections",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
        # Status lifecycle
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="'new'",
        ),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column(
            "acknowledged_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("change_request_id", sa.Integer(), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("dismissed_by", sa.Integer(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        # Impact analysis linkage
        sa.Column("impact_report_id", sa.String(length=36), nullable=True),
        # Timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["ingestion_record_id"],
            ["literature_ingestion_records.id"],
            name="fk_lit_contradiction_alerts_ingestion_record_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_contradiction_alerts_company_id",
        ),
    )

    op.create_index(
        "ix_literature_contradiction_alerts_ingestion_record_id",
        "literature_contradiction_alerts",
        ["ingestion_record_id"],
    )
    op.create_index(
        "ix_literature_contradiction_alerts_internal_document_id",
        "literature_contradiction_alerts",
        ["internal_document_id"],
    )
    op.create_index(
        "ix_literature_contradiction_alerts_company_id",
        "literature_contradiction_alerts",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_contradiction_alerts_company_severity_status",
        "literature_contradiction_alerts",
        ["company_id", "severity", "status"],
    )
    op.create_index(
        "ix_lit_contradiction_alerts_company_created",
        "literature_contradiction_alerts",
        ["company_id", "created_at"],
    )

    # --- literature_novelty_flags ---
    op.create_table(
        "literature_novelty_flags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ingestion_record_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        # Novelty details
        sa.Column("novelty_description", sa.Text(), nullable=False),
        sa.Column(
            "suggested_document_types",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column(
            "high_priority",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        # Status lifecycle
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="'new'",
        ),
        sa.Column("linked_document_id", sa.String(length=36), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column(
            "acknowledged_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("integrated_by", sa.Integer(), nullable=True),
        sa.Column("integrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_by", sa.Integer(), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        # Grouping
        sa.Column("group_id", sa.String(length=36), nullable=True),
        # Timestamp
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["ingestion_record_id"],
            ["literature_ingestion_records.id"],
            name="fk_lit_novelty_flags_ingestion_record_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_novelty_flags_company_id",
        ),
    )

    op.create_index(
        "ix_literature_novelty_flags_ingestion_record_id",
        "literature_novelty_flags",
        ["ingestion_record_id"],
    )
    op.create_index(
        "ix_literature_novelty_flags_company_id",
        "literature_novelty_flags",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_novelty_flags_company_status",
        "literature_novelty_flags",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_lit_novelty_flags_company_relevance",
        "literature_novelty_flags",
        ["company_id", "relevance_score"],
    )


def downgrade() -> None:
    """Drop Phase 9.4 tables in reverse dependency order."""
    op.drop_table("literature_novelty_flags")
    op.drop_table("literature_contradiction_alerts")
    op.drop_table("literature_screening_decisions")
    op.drop_table("literature_screening_runs")
    op.drop_table("literature_slr_reviews")
    op.drop_table("literature_screening_configurations")
    op.drop_table("literature_screening_protocols")
