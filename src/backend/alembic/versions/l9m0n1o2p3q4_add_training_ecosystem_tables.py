"""add training ecosystem tables

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-09-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "l9m0n1o2p3q4"
down_revision: Union[str, Sequence[str], None] = "k8l9m0n1o2p3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add training_schedules, skill_gaps, training_materials, generated_questions, virtual_audit_sessions, dynamic_feedback_cache tables."""
    # --- training_schedules ---
    op.create_table(
        "training_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "schedule_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("compliance_percentage", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_recalculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_training_schedules"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_training_schedules_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_training_schedules_company_id_companies",
        ),
        sa.UniqueConstraint(
            "user_id", "company_id", name="uq_training_schedule_user_company"
        ),
        sa.CheckConstraint(
            "completed_items <= total_items",
            name="ck_schedule_completed_lte_total",
        ),
    )
    op.create_index(
        "ix_training_schedule_user_company",
        "training_schedules",
        ["user_id", "company_id"],
    )

    # --- skill_gaps ---
    op.create_table(
        "skill_gaps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("gap_type", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("days_overdue", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("blocks_access", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "identified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_skill_gaps"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_skill_gaps_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_skill_gaps_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_skill_gaps_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_skill_gaps_document_version_id_document_versions",
        ),
        sa.UniqueConstraint(
            "user_id",
            "document_id",
            "document_version_id",
            "gap_type",
            name="uq_skill_gap_user_doc_version_type",
        ),
    )
    op.create_index(
        "ix_skill_gap_user_company",
        "skill_gaps",
        ["user_id", "company_id"],
    )
    op.create_index(
        "ix_skill_gap_document",
        "skill_gaps",
        ["document_id", "document_version_id"],
    )

    # --- training_materials ---
    op.create_table(
        "training_materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("material_type", sa.String(length=50), nullable=False),
        sa.Column(
            "content_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "learning_objectives",
            postgresql.JSON(),
            nullable=False,
        ),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column("generated_by_agent_id", sa.String(length=255), nullable=True),
        sa.Column("inference_duration_ms", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_training_materials"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_training_materials_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_training_materials_document_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_training_materials_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_training_materials_reviewed_by_users",
        ),
        sa.UniqueConstraint(
            "document_id",
            "document_version_id",
            "material_type",
            name="uq_training_material_doc_version_type",
        ),
    )
    op.create_index(
        "ix_training_material_doc_version",
        "training_materials",
        ["document_id", "document_version_id"],
    )
    op.create_index(
        "ix_training_material_status",
        "training_materials",
        ["status"],
    )

    # --- generated_questions ---
    op.create_table(
        "generated_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("distractors", postgresql.JSON(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("difficulty_level", sa.String(length=20), nullable=False),
        sa.Column("bloom_taxonomy_level", sa.String(length=50), nullable=False),
        sa.Column("sop_section_ref", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_generated_questions"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_generated_questions_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_generated_questions_document_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_generated_questions_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name="fk_generated_questions_reviewed_by_users",
        ),
    )
    op.create_index(
        "ix_generated_question_doc_version",
        "generated_questions",
        ["document_id", "document_version_id"],
    )
    op.create_index(
        "ix_generated_question_status",
        "generated_questions",
        ["status"],
    )

    # --- virtual_audit_sessions ---
    op.create_table(
        "virtual_audit_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("turns_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_turns", sa.Integer(), nullable=False),
        sa.Column(
            "session_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "summary_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_virtual_audit_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_virtual_audit_sessions_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_virtual_audit_sessions_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_virtual_audit_sessions_document_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_virtual_audit_sessions_company_id_companies",
        ),
        sa.CheckConstraint(
            "turns_completed <= total_turns",
            name="ck_session_turns_lte_total",
        ),
    )
    op.create_index(
        "ix_virtual_audit_user_company",
        "virtual_audit_sessions",
        ["user_id", "company_id"],
    )
    op.create_index(
        "ix_virtual_audit_user_doc",
        "virtual_audit_sessions",
        ["user_id", "document_id"],
    )
    op.create_index(
        "ix_virtual_audit_status",
        "virtual_audit_sessions",
        ["status"],
    )

    # --- dynamic_feedback_cache ---
    op.create_table(
        "dynamic_feedback_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("paragraph_text", sa.Text(), nullable=False),
        sa.Column("section_reference", sa.String(length=500), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dynamic_feedback_cache"),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["generated_questions.id"],
            name="fk_dynamic_feedback_cache_question_id_generated_questions",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_dynamic_feedback_cache_document_version_id_document_versions",
        ),
        sa.UniqueConstraint(
            "question_id",
            "document_version_id",
            name="uq_feedback_cache_question_version",
        ),
    )
    op.create_index(
        "ix_feedback_cache_question",
        "dynamic_feedback_cache",
        ["question_id"],
    )
    op.create_index(
        "ix_feedback_cache_doc_version",
        "dynamic_feedback_cache",
        ["document_version_id"],
    )

    # --- active_question_sets ---
    op.create_table(
        "active_question_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.String(length=255), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_active_question_sets"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_active_question_sets_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_active_question_sets_document_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_active_question_sets_company_id_companies",
        ),
    )
    op.create_index(
        "ix_active_question_set_content_id",
        "active_question_sets",
        ["content_id"],
    )
    op.create_index(
        "ix_active_question_set_doc_version",
        "active_question_sets",
        ["document_id", "document_version_id"],
    )


def downgrade() -> None:
    """Drop all training ecosystem tables in reverse dependency order."""
    op.drop_table("active_question_sets")
    op.drop_table("dynamic_feedback_cache")
    op.drop_table("virtual_audit_sessions")
    op.drop_table("generated_questions")
    op.drop_table("training_materials")
    op.drop_table("skill_gaps")
    op.drop_table("training_schedules")
