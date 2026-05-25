"""add impact analysis tables

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
Create Date: 2026-09-20 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "o2p3q4r5s6t7"
down_revision: Union[str, Sequence[str], None] = "n1o2p3q4r5s6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add dependency_edges, impact_reports, gap_analysis_results, impact_notifications tables."""
    # --- dependency_edges (no FK to other new tables, created first) ---
    op.create_table(
        "dependency_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_document_uuid", sa.String(length=12), nullable=False),
        sa.Column("target_document_uuid", sa.String(length=12), nullable=False),
        sa.Column("dependency_type", sa.String(length=50), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column(
            "detected_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_dependency_edges"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_dependency_edges_company_id_companies",
        ),
        sa.UniqueConstraint(
            "source_document_uuid",
            "target_document_uuid",
            "dependency_type",
            "company_id",
            name="uq_dependency_edge_source_target_type_company",
        ),
    )
    op.create_index(
        "ix_dependency_edges_source_document_uuid",
        "dependency_edges",
        ["source_document_uuid"],
    )
    op.create_index(
        "ix_dependency_edges_target_document_uuid",
        "dependency_edges",
        ["target_document_uuid"],
    )
    op.create_index(
        "ix_dependency_edge_company_source",
        "dependency_edges",
        ["company_id", "source_document_uuid"],
    )
    op.create_index(
        "ix_dependency_edge_company_target",
        "dependency_edges",
        ["company_id", "target_document_uuid"],
    )

    # --- impact_reports ---
    op.create_table(
        "impact_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("triggering_document_uuid", sa.String(length=12), nullable=False),
        sa.Column("triggering_version_id", sa.Integer(), nullable=False),
        sa.Column(
            "change_delta_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "affected_items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "gap_findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("analysis_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_duration_ms", sa.Integer(), nullable=False),
        sa.Column("agent_archetype_used", sa.String(length=100), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column("total_token_count", sa.Integer(), nullable=False),
        sa.Column("requesting_user_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_impact_reports"),
        sa.ForeignKeyConstraint(
            ["triggering_version_id"],
            ["document_versions.id"],
            name="fk_impact_reports_triggering_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["requesting_user_id"],
            ["users.id"],
            name="fk_impact_reports_requesting_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_impact_reports_company_id_companies",
        ),
        sa.UniqueConstraint("report_id", name="uq_impact_reports_report_id"),
    )
    op.create_index(
        "ix_impact_reports_report_id",
        "impact_reports",
        ["report_id"],
    )
    op.create_index(
        "ix_impact_reports_triggering_document_uuid",
        "impact_reports",
        ["triggering_document_uuid"],
    )
    op.create_index(
        "ix_impact_report_company_trigger",
        "impact_reports",
        ["company_id", "triggering_document_uuid"],
    )

    # --- gap_analysis_results ---
    op.create_table(
        "gap_analysis_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("source_document_uuid", sa.String(length=12), nullable=False),
        sa.Column("target_document_uuid", sa.String(length=12), nullable=False),
        sa.Column(
            "gap_findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("total_gaps_detected", sa.Integer(), nullable=False),
        sa.Column("gaps_retained", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("analysis_duration_ms", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_gap_analysis_results"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_gap_analysis_results_company_id_companies",
        ),
    )
    op.create_index(
        "ix_gap_analysis_results_job_id",
        "gap_analysis_results",
        ["job_id"],
    )

    # --- impact_notifications (references users, created last) ---
    op.create_table(
        "impact_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("affected_document_uuid", sa.String(length=12), nullable=False),
        sa.Column("notification_type", sa.String(length=50), nullable=False),
        sa.Column("impact_severity", sa.String(length=20), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=False),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_impact_notifications"),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name="fk_impact_notifications_target_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["users.id"],
            name="fk_impact_notifications_acknowledged_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_impact_notifications_company_id_companies",
        ),
        sa.UniqueConstraint(
            "report_id",
            "affected_document_uuid",
            "target_user_id",
            name="uq_impact_notification_report_doc_user",
        ),
    )
    op.create_index(
        "ix_impact_notifications_report_id",
        "impact_notifications",
        ["report_id"],
    )
    op.create_index(
        "ix_impact_notifications_affected_document_uuid",
        "impact_notifications",
        ["affected_document_uuid"],
    )
    op.create_index(
        "ix_impact_notifications_target_user_id",
        "impact_notifications",
        ["target_user_id"],
    )
    op.create_index(
        "ix_impact_notification_user_ack",
        "impact_notifications",
        ["target_user_id", "is_acknowledged"],
    )


def downgrade() -> None:
    """Drop impact analysis tables in reverse dependency order."""
    op.drop_table("impact_notifications")
    op.drop_table("gap_analysis_results")
    op.drop_table("impact_reports")
    op.drop_table("dependency_edges")
