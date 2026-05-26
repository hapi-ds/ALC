"""add traceability tables

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
Create Date: 2026-10-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p3q4r5s6t7u8"
down_revision: Union[str, Sequence[str], None] = "o2p3q4r5s6t7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add traceability_matrices, coverage_snapshots, traceability_alerts, stale_link_markers tables."""
    # --- traceability_matrices (no FK to other new tables, created first) ---
    op.create_table(
        "traceability_matrices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("matrix_id", sa.String(length=36), nullable=False),
        sa.Column("matrix_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source_document_uuids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "target_document_uuids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "source_document_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "target_document_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "traceability_links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "orphan_requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "orphan_test_cases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "coverage_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("parent_matrix_id", sa.String(length=36), nullable=True),
        sa.Column("generation_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation_duration_ms", sa.Integer(), nullable=False),
        sa.Column("agent_archetype_used", sa.String(length=100), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column("total_token_count", sa.Integer(), nullable=False),
        sa.Column("requesting_user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_traceability_matrices"),
        sa.ForeignKeyConstraint(
            ["requesting_user_id"],
            ["users.id"],
            name="fk_traceability_matrices_requesting_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_traceability_matrices_company_id_companies",
        ),
        sa.UniqueConstraint("matrix_id", name="uq_traceability_matrices_matrix_id"),
    )
    op.create_index(
        "ix_traceability_matrices_matrix_id",
        "traceability_matrices",
        ["matrix_id"],
    )
    op.create_index(
        "ix_traceability_matrix_company_timestamp",
        "traceability_matrices",
        ["company_id", "generation_timestamp"],
    )
    op.create_index(
        "ix_traceability_matrix_company_deleted",
        "traceability_matrices",
        ["company_id", "deleted_at"],
    )

    # --- coverage_snapshots (references traceability_matrices.matrix_id logically) ---
    op.create_table(
        "coverage_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("matrix_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_uuid", sa.String(length=12), nullable=False),
        sa.Column("coverage_percentage", sa.Float(), nullable=False),
        sa.Column("orphan_requirements_count", sa.Integer(), nullable=False),
        sa.Column("orphan_test_cases_count", sa.Integer(), nullable=False),
        sa.Column("compliance_readiness_score", sa.Float(), nullable=False),
        sa.Column("total_requirements", sa.Integer(), nullable=False),
        sa.Column("covered_requirements", sa.Integer(), nullable=False),
        sa.Column("total_test_cases", sa.Integer(), nullable=False),
        sa.Column("linked_test_cases", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_coverage_snapshots"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_coverage_snapshots_company_id_companies",
        ),
    )
    op.create_index(
        "ix_coverage_snapshots_matrix_id",
        "coverage_snapshots",
        ["matrix_id"],
    )
    op.create_index(
        "ix_coverage_snapshots_source_document_uuid",
        "coverage_snapshots",
        ["source_document_uuid"],
    )
    op.create_index(
        "ix_coverage_snapshot_company_doc_date",
        "coverage_snapshots",
        ["company_id", "source_document_uuid", "snapshot_date"],
    )

    # --- traceability_alerts (references users, companies) ---
    op.create_table(
        "traceability_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.String(length=36), nullable=False),
        sa.Column("triggering_report_id", sa.String(length=36), nullable=False),
        sa.Column(
            "affected_matrix_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("affected_link_count", sa.Integer(), nullable=False),
        sa.Column("alert_severity", sa.String(length=20), nullable=False),
        sa.Column(
            "is_resolved", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolution_action", sa.String(length=50), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_traceability_alerts"),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name="fk_traceability_alerts_resolved_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_traceability_alerts_company_id_companies",
        ),
        sa.UniqueConstraint("alert_id", name="uq_traceability_alerts_alert_id"),
        sa.UniqueConstraint(
            "triggering_report_id",
            "company_id",
            name="uq_traceability_alert_report_company",
        ),
    )
    op.create_index(
        "ix_traceability_alerts_alert_id",
        "traceability_alerts",
        ["alert_id"],
    )
    op.create_index(
        "ix_traceability_alerts_triggering_report_id",
        "traceability_alerts",
        ["triggering_report_id"],
    )
    op.create_index(
        "ix_traceability_alert_company_resolved",
        "traceability_alerts",
        ["company_id", "is_resolved"],
    )

    # --- stale_link_markers (references companies, created last) ---
    op.create_table(
        "stale_link_markers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("matrix_id", sa.String(length=36), nullable=False),
        sa.Column("requirement_id", sa.String(length=100), nullable=False),
        sa.Column("stale_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stale_reason", sa.Text(), nullable=False),
        sa.Column("triggering_report_id", sa.String(length=36), nullable=False),
        sa.Column(
            "is_cleared", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stale_link_markers"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_stale_link_markers_company_id_companies",
        ),
        sa.UniqueConstraint(
            "matrix_id",
            "requirement_id",
            "triggering_report_id",
            name="uq_stale_link_marker_matrix_req_report",
        ),
    )
    op.create_index(
        "ix_stale_link_markers_matrix_id",
        "stale_link_markers",
        ["matrix_id"],
    )
    op.create_index(
        "ix_stale_link_marker_matrix_cleared",
        "stale_link_markers",
        ["matrix_id", "is_cleared"],
    )


def downgrade() -> None:
    """Drop traceability tables in reverse dependency order."""
    op.drop_table("stale_link_markers")
    op.drop_table("traceability_alerts")
    op.drop_table("coverage_snapshots")
    op.drop_table("traceability_matrices")
