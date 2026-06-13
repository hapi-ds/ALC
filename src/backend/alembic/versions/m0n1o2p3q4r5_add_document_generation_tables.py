"""add document generation tables

Revision ID: m0n1o2p3q4r5
Revises: l9m0n1o2p3q4
Create Date: 2026-09-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "m0n1o2p3q4r5"
down_revision: Union[str, Sequence[str], None] = "l9m0n1o2p3q4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add document_templates, generation_provenance, cross_reference_entries, generation_job_metadata tables."""
    # --- document_templates ---
    op.create_table(
        "document_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("template_name", sa.String(length=500), nullable=False),
        sa.Column("document_type_target", sa.String(length=100), nullable=False),
        sa.Column(
            "template_analysis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("registered_by", sa.Integer(), nullable=False),
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
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_document_templates"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_templates_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_document_templates_document_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_document_templates_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["registered_by"],
            ["users.id"],
            name="fk_document_templates_registered_by_users",
        ),
        sa.UniqueConstraint(
            "document_version_id",
            "company_id",
            name="uq_document_template_version_company",
        ),
    )
    op.create_index(
        "ix_document_template_company",
        "document_templates",
        ["company_id"],
    )
    op.create_index(
        "ix_document_template_type",
        "document_templates",
        ["document_type_target"],
    )

    # --- generation_provenance (immutable - no AuditMixin) ---
    op.create_table(
        "generation_provenance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("document_version_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("requesting_user_id", sa.Integer(), nullable=False),
        sa.Column("agent_archetype", sa.String(length=100), nullable=False),
        sa.Column(
            "generation_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "source_document_uuids",
            postgresql.JSON(),
            nullable=False,
        ),
        sa.Column(
            "reference_document_ids",
            postgresql.JSON(),
            nullable=False,
        ),
        sa.Column(
            "section_provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("total_inference_duration_ms", sa.Integer(), nullable=False),
        sa.Column("total_token_count", sa.Integer(), nullable=False),
        sa.Column(
            "unverified_references",
            postgresql.JSON(),
            nullable=False,
        ),
        sa.Column("previous_generation_id", sa.String(length=36), nullable=True),
        sa.Column("generation_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generation_provenance"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_generation_provenance_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_generation_provenance_document_version_id_document_versions",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["document_templates.id"],
            name="fk_generation_provenance_template_id_document_templates",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_generation_provenance_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["requesting_user_id"],
            ["users.id"],
            name="fk_generation_provenance_requesting_user_id_users",
        ),
        sa.UniqueConstraint("generation_id", name="uq_generation_provenance_generation_id"),
    )
    op.create_index(
        "ix_generation_provenance_company",
        "generation_provenance",
        ["company_id"],
    )
    op.create_index(
        "ix_generation_provenance_document",
        "generation_provenance",
        ["document_id"],
    )
    op.create_index(
        "ix_generation_provenance_generation_id",
        "generation_provenance",
        ["generation_id"],
        unique=True,
    )

    # --- cross_reference_entries (immutable - no AuditMixin) ---
    op.create_table(
        "cross_reference_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("generation_provenance_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=False),
        sa.Column("reference_identifier", sa.String(length=200), nullable=False),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column(
            "location_in_output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cross_reference_entries"),
        sa.ForeignKeyConstraint(
            ["generation_provenance_id"],
            ["generation_provenance.id"],
            name="fk_cross_ref_entries_gen_provenance_id",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name="fk_cross_reference_entries_source_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_cross_reference_entries_company_id_companies",
        ),
    )
    op.create_index(
        "ix_cross_ref_provenance_type",
        "cross_reference_entries",
        ["generation_provenance_id", "reference_type"],
    )
    op.create_index(
        "ix_cross_ref_company",
        "cross_reference_entries",
        ["company_id"],
    )

    # --- generation_job_metadata ---
    op.create_table(
        "generation_job_metadata",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("requesting_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("generation_instructions", sa.Text(), nullable=False),
        sa.Column(
            "reference_document_ids",
            postgresql.JSON(),
            nullable=False,
        ),
        sa.Column("output_folder_path", sa.String(length=1000), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="processing"
        ),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_section", sa.String(length=500), nullable=True),
        sa.Column("sections_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sections_total", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_document_id", sa.Integer(), nullable=True),
        sa.Column("result_storage_key", sa.String(length=500), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("generation_duration_ms", sa.Integer(), nullable=True),
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
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_generation_job_metadata"),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["document_templates.id"],
            name="fk_generation_job_metadata_template_id_document_templates",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_generation_job_metadata_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["requesting_user_id"],
            ["users.id"],
            name="fk_generation_job_metadata_requesting_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["result_document_id"],
            ["documents.id"],
            name="fk_generation_job_metadata_result_document_id_documents",
        ),
        sa.UniqueConstraint("job_id", name="uq_generation_job_metadata_job_id"),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_gen_job_progress_range",
        ),
        sa.CheckConstraint(
            "sections_completed <= sections_total",
            name="ck_gen_job_sections_lte_total",
        ),
    )
    op.create_index(
        "ix_gen_job_company",
        "generation_job_metadata",
        ["company_id"],
    )
    op.create_index(
        "ix_gen_job_job_id",
        "generation_job_metadata",
        ["job_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop document generation tables in reverse dependency order."""
    op.drop_table("generation_job_metadata")
    op.drop_table("cross_reference_entries")
    op.drop_table("generation_provenance")
    op.drop_table("document_templates")
