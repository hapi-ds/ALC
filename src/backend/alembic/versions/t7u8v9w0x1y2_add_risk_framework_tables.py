"""add risk framework tables

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x1
Create Date: 2027-01-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "t7u8v9w0x1y2"
down_revision: Union[str, Sequence[str], None] = "s6t7u8v9w0x1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all AI Risk & Compliance Framework tables.

    Tables created:
        - ai_task_types: Registry of AI-powered task types with risk classifications
        - company_risk_profiles: Per-tenant risk profile configuration
        - risk_tier_overrides: Company-specific tier overrides within a profile
        - risk_assessment_records: Immutable records of tier assignment changes
        - hitl_checkpoints: Human-in-the-loop review checkpoints
        - ai_operation_logs: Immutable operation audit logs
        - control_enforcement_logs: Immutable control enforcement records

    Note: Enum values (risk_tier, audit_depth, gate_result, checkpoint_status)
    are stored as String columns rather than native PostgreSQL enum types,
    matching the model definitions in risk_framework.py.
    """

    # --- ai_task_types ---
    op.create_table(
        "ai_task_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("task_type_id", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("module_reference", sa.String(length=100), nullable=False),
        sa.Column("default_risk_tier", sa.String(length=10), nullable=False),
        sa.Column(
            "risk_factors",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "is_system_defined", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_ai_task_types"),
        sa.UniqueConstraint("task_type_id", name="uq_ai_task_types_task_type_id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_ai_task_types_company_id_companies",
        ),
    )
    op.create_index(
        "ix_ai_task_types_company_id",
        "ai_task_types",
        ["company_id"],
    )
    op.create_index(
        "ix_ai_task_types_task_type_id",
        "ai_task_types",
        ["task_type_id"],
    )

    # --- company_risk_profiles ---
    op.create_table(
        "company_risk_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("profile_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "regulatory_frameworks",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_company_risk_profiles"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_company_risk_profiles_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_company_risk_profiles_created_by_users",
        ),
    )
    op.create_index(
        "ix_company_risk_profiles_company_id",
        "company_risk_profiles",
        ["company_id"],
    )
    # Partial unique index: at most one active profile per company
    op.create_index(
        "ix_company_risk_profiles_active_company",
        "company_risk_profiles",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    # --- risk_tier_overrides ---
    op.create_table(
        "risk_tier_overrides",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("task_type_id", sa.String(length=100), nullable=False),
        sa.Column("assigned_tier", sa.String(length=10), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("regulatory_reference", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approval_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_tier_overrides"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["company_risk_profiles.id"],
            name="fk_risk_tier_overrides_profile_id_company_risk_profiles",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_risk_tier_overrides_approved_by_users",
        ),
    )
    op.create_index(
        "ix_risk_tier_overrides_profile_id",
        "risk_tier_overrides",
        ["profile_id"],
    )
    op.create_index(
        "ix_risk_tier_overrides_task_type_id",
        "risk_tier_overrides",
        ["task_type_id"],
    )

    # --- risk_assessment_records ---
    op.create_table(
        "risk_assessment_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("task_type_id", sa.String(length=100), nullable=False),
        sa.Column("previous_tier", sa.String(length=10), nullable=True),
        sa.Column("new_tier", sa.String(length=10), nullable=False),
        sa.Column("assessor_user_id", sa.Integer(), nullable=False),
        sa.Column("assessment_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "regulatory_references",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_assessment_records"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_risk_assessment_records_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["assessor_user_id"],
            ["users.id"],
            name="fk_risk_assessment_records_assessor_user_id_users",
        ),
    )
    op.create_index(
        "ix_risk_assessment_records_company_id",
        "risk_assessment_records",
        ["company_id"],
    )
    op.create_index(
        "ix_risk_assessment_records_task_type_id",
        "risk_assessment_records",
        ["task_type_id"],
    )
    op.create_index(
        "ix_risk_assessment_records_created_at",
        "risk_assessment_records",
        ["created_at"],
    )

    # --- hitl_checkpoints ---
    op.create_table(
        "hitl_checkpoints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.String(length=200), nullable=False),
        sa.Column("task_type_id", sa.String(length=100), nullable=False),
        sa.Column("ai_output_reference", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("assigned_reviewer_role", sa.String(length=50), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewer_comments", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_sections",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_hitl_checkpoints"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_hitl_checkpoints_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name="fk_hitl_checkpoints_reviewer_user_id_users",
        ),
    )
    op.create_index(
        "ix_hitl_checkpoints_company_id",
        "hitl_checkpoints",
        ["company_id"],
    )
    op.create_index(
        "ix_hitl_checkpoints_task_type_id",
        "hitl_checkpoints",
        ["task_type_id"],
    )
    op.create_index(
        "ix_hitl_checkpoints_status",
        "hitl_checkpoints",
        ["status"],
    )
    op.create_index(
        "ix_hitl_checkpoints_created_at",
        "hitl_checkpoints",
        ["created_at"],
    )
    op.create_index(
        "ix_hitl_checkpoints_expires_at",
        "hitl_checkpoints",
        ["expires_at"],
    )

    # --- ai_operation_logs ---
    op.create_table(
        "ai_operation_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("task_type_id", sa.String(length=100), nullable=False),
        sa.Column("risk_tier", sa.String(length=10), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("audit_depth", sa.String(length=10), nullable=False),
        sa.Column(
            "input_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "output_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("inference_duration_ms", sa.Integer(), nullable=True),
        sa.Column("token_count_input", sa.Integer(), nullable=True),
        sa.Column("token_count_output", sa.Integer(), nullable=True),
        sa.Column("gate_result", sa.String(length=10), nullable=False),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column(
            "source_document_ids",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_operation_logs"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_ai_operation_logs_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_operation_logs_user_id_users",
        ),
    )
    op.create_index(
        "ix_ai_operation_logs_company_id",
        "ai_operation_logs",
        ["company_id"],
    )
    op.create_index(
        "ix_ai_operation_logs_task_type_id",
        "ai_operation_logs",
        ["task_type_id"],
    )
    op.create_index(
        "ix_ai_operation_logs_created_at",
        "ai_operation_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_ai_operation_logs_user_id",
        "ai_operation_logs",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_operation_logs_risk_tier",
        "ai_operation_logs",
        ["risk_tier"],
    )

    # --- control_enforcement_logs ---
    op.create_table(
        "control_enforcement_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "operation_log_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("task_type_id", sa.String(length=100), nullable=False),
        sa.Column("risk_tier", sa.String(length=10), nullable=False),
        sa.Column(
            "controls_enforced",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "controls_satisfied",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("overall_result", sa.String(length=10), nullable=False),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("enforcement_duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_control_enforcement_logs"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_control_enforcement_logs_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["operation_log_id"],
            ["ai_operation_logs.id"],
            name="fk_control_enforcement_logs_operation_log_id_ai_operation_logs",
        ),
    )
    op.create_index(
        "ix_control_enforcement_logs_company_id",
        "control_enforcement_logs",
        ["company_id"],
    )
    op.create_index(
        "ix_control_enforcement_logs_operation_log_id",
        "control_enforcement_logs",
        ["operation_log_id"],
    )
    op.create_index(
        "ix_control_enforcement_logs_task_type_id",
        "control_enforcement_logs",
        ["task_type_id"],
    )
    op.create_index(
        "ix_control_enforcement_logs_created_at",
        "control_enforcement_logs",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop all risk framework tables in reverse dependency order."""
    op.drop_table("control_enforcement_logs")
    op.drop_table("ai_operation_logs")
    op.drop_table("hitl_checkpoints")
    op.drop_table("risk_assessment_records")
    op.drop_table("risk_tier_overrides")
    op.drop_table("company_risk_profiles")
    op.drop_table("ai_task_types")
