"""add multi-agent review tables

Revision ID: k8l9m0n1o2p3
Revises: j7k8l9m0n1o2
Create Date: 2026-08-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "k8l9m0n1o2p3"
down_revision: Union[str, Sequence[str], None] = "j7k8l9m0n1o2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add review_sessions, agent_reviews, master_review_summaries, action_items, audit_profiles, anomaly_alerts tables."""
    # --- audit_profiles (created first since review_sessions references it) ---
    op.create_table(
        "audit_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "regulatory_frameworks",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "assigned_agent_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("quorum", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "severity_thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_profiles"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_audit_profiles_company_id_companies",
        ),
    )
    op.create_index(
        "ix_audit_profiles_company_id",
        "audit_profiles",
        ["company_id"],
    )

    # --- review_sessions ---
    op.create_table(
        "review_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("audit_profile_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="Pending",
        ),
        sa.Column("submitted_by", sa.Integer(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compliance_score", sa.Float(), nullable=True),
        sa.Column("summary_failed", sa.Boolean(), nullable=False, server_default="false"),
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
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_sessions"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_review_sessions_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_review_sessions_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_review_sessions_document_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["audit_profile_id"],
            ["audit_profiles.id"],
            name="fk_review_sessions_audit_profile_id_audit_profiles",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
            name="fk_review_sessions_submitted_by_users",
        ),
    )
    op.create_index(
        "ix_review_sessions_company_id",
        "review_sessions",
        ["company_id"],
    )
    op.create_index(
        "ix_review_sessions_document_id",
        "review_sessions",
        ["document_id"],
    )
    op.create_index(
        "ix_review_sessions_status",
        "review_sessions",
        ["status"],
    )

    # --- agent_reviews ---
    op.create_table(
        "agent_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("agent_definition_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="Pending",
        ),
        sa.Column(
            "report_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_reason", sa.String(length=500), nullable=True),
        sa.Column("inference_duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_reviews"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["review_sessions.id"],
            name="fk_agent_reviews_session_id_review_sessions",
        ),
        sa.ForeignKeyConstraint(
            ["agent_definition_id"],
            ["agent_definitions.id"],
            name="fk_agent_reviews_agent_definition_id_agent_definitions",
        ),
    )
    op.create_index(
        "ix_agent_reviews_session_id",
        "agent_reviews",
        ["session_id"],
    )

    # --- master_review_summaries ---
    op.create_table(
        "master_review_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column(
            "summary_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("compliance_score", sa.Float(), nullable=False),
        sa.Column("risk_assessment", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_master_review_summaries"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["review_sessions.id"],
            name="fk_master_review_summaries_session_id_review_sessions",
        ),
        sa.UniqueConstraint(
            "session_id",
            name="uq_master_review_summaries_session_id",
        ),
    )

    # --- action_items ---
    op.create_table(
        "action_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("finding_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="Open",
        ),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
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
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_action_items"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["review_sessions.id"],
            name="fk_action_items_session_id_review_sessions",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"],
            ["users.id"],
            name="fk_action_items_assigned_to_users",
        ),
    )
    op.create_index(
        "ix_action_items_session_id",
        "action_items",
        ["session_id"],
    )

    # --- anomaly_alerts ---
    op.create_table(
        "anomaly_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("anomaly_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_document_id", sa.Integer(), nullable=True),
        sa.Column("affected_user_id", sa.Integer(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_anomaly_alerts"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_anomaly_alerts_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["affected_document_id"],
            ["documents.id"],
            name="fk_anomaly_alerts_affected_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["affected_user_id"],
            ["users.id"],
            name="fk_anomaly_alerts_affected_user_id_users",
        ),
        sa.UniqueConstraint(
            "anomaly_type",
            "affected_document_id",
            "affected_user_id",
            "detected_at",
            name="uq_anomaly_alerts_deduplication",
        ),
    )
    op.create_index(
        "ix_anomaly_alerts_company_id",
        "anomaly_alerts",
        ["company_id"],
    )
    op.create_index(
        "ix_anomaly_alerts_anomaly_type",
        "anomaly_alerts",
        ["anomaly_type"],
    )
    op.create_index(
        "ix_anomaly_alerts_severity",
        "anomaly_alerts",
        ["severity"],
    )


def downgrade() -> None:
    """Drop all multi-agent review tables in reverse dependency order."""
    op.drop_table("anomaly_alerts")
    op.drop_table("action_items")
    op.drop_table("master_review_summaries")
    op.drop_table("agent_reviews")
    op.drop_table("review_sessions")
    op.drop_table("audit_profiles")
