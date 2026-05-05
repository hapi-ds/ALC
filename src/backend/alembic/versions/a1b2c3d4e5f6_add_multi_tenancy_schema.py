"""add multi-tenancy schema

Revision ID: a1b2c3d4e5f6
Revises: 3602b506bc61
Create Date: 2026-05-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3602b506bc61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Strategy: two-phase approach
    1. Create new tables (companies, company_memberships, company_agent_activations)
    2. Insert default company for backfill
    3. Add nullable company_id columns to existing tables
    4. Backfill existing records with default company ID
    5. Alter company_id to NOT NULL (except agent_definitions)
    6. Add composite indexes
    7. Add foreign key constraints
    """
    # --- Phase 1: Create new tables ---

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("regulatory_framework", sa.String(length=50), nullable=False),
        sa.Column(
            "audit_config",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_index(
        op.f("ix_companies_slug"), "companies", ["slug"], unique=True
    )

    op.create_table(
        "company_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_company_memberships_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_memberships_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_memberships")),
        sa.UniqueConstraint(
            "user_id", "company_id", name="uq_company_memberships_user_company"
        ),
    )
    op.create_index(
        op.f("ix_company_memberships_user_id"),
        "company_memberships",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_memberships_company_id"),
        "company_memberships",
        ["company_id"],
        unique=False,
    )

    op.create_table(
        "company_agent_activations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("agent_definition_id", sa.Integer(), nullable=False),
        sa.Column(
            "config_overrides",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_agent_activations_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_definition_id"],
            ["agent_definitions.id"],
            name=op.f(
                "fk_company_agent_activations_agent_definition_id_agent_definitions"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_company_agent_activations")
        ),
        sa.UniqueConstraint(
            "company_id",
            "agent_definition_id",
            name="uq_company_agent_activations_company_agent",
        ),
    )
    op.create_index(
        op.f("ix_company_agent_activations_company_id"),
        "company_agent_activations",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_agent_activations_agent_definition_id"),
        "company_agent_activations",
        ["agent_definition_id"],
        unique=False,
    )

    # --- Phase 2: Insert default company for backfill ---

    op.execute(
        "INSERT INTO companies (slug, display_name, regulatory_framework, audit_config, is_active) "
        "VALUES ('default', 'Default Company', 'ISO_13485', '{}', true)"
    )

    # --- Phase 3: Add nullable company_id columns to existing tables ---

    # Tables that will become NOT NULL after backfill
    tables_non_null = [
        "documents",
        "templates",
        "workflow_definitions",
        "training_records",
        "training_tasks",
        "virtual_folders",
        "reports",
        "signature_records",
    ]

    for table in tables_non_null:
        op.add_column(
            table,
            sa.Column("company_id", sa.Integer(), nullable=True),
        )

    # agent_definitions: company_id remains nullable (NULL = global)
    op.add_column(
        "agent_definitions",
        sa.Column("company_id", sa.Integer(), nullable=True),
    )

    # --- Phase 4: Backfill existing records with default company ID ---

    op.execute(
        "UPDATE documents SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )
    op.execute(
        "UPDATE templates SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )
    op.execute(
        "UPDATE workflow_definitions SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )
    op.execute(
        "UPDATE training_records SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )
    op.execute(
        "UPDATE training_tasks SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )
    op.execute(
        "UPDATE virtual_folders SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )
    op.execute(
        "UPDATE reports SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )
    op.execute(
        "UPDATE signature_records SET company_id = (SELECT id FROM companies WHERE slug = 'default') "
        "WHERE company_id IS NULL"
    )

    # --- Phase 5: Alter company_id to NOT NULL (except agent_definitions) ---

    for table in tables_non_null:
        op.alter_column(
            table,
            "company_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    # --- Phase 6: Add foreign key constraints ---

    for table in tables_non_null:
        op.create_foreign_key(
            op.f(f"fk_{table}_company_id_companies"),
            table,
            "companies",
            ["company_id"],
            ["id"],
        )

    # agent_definitions FK (nullable)
    op.create_foreign_key(
        op.f("fk_agent_definitions_company_id_companies"),
        "agent_definitions",
        "companies",
        ["company_id"],
        ["id"],
    )

    # --- Phase 7: Add composite indexes ---

    op.create_index(
        "ix_documents_company_id_document_uuid",
        "documents",
        ["company_id", "document_uuid"],
        unique=False,
    )
    op.create_index(
        "ix_documents_company_id_created_at",
        "documents",
        ["company_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_templates_company_id_document_uuid",
        "templates",
        ["company_id", "document_uuid"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_definitions_company_id_document_tag",
        "workflow_definitions",
        ["company_id", "document_tag"],
        unique=False,
    )
    op.create_index(
        "ix_training_tasks_company_id_assigned_user_id",
        "training_tasks",
        ["company_id", "assigned_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # --- Remove composite indexes ---

    op.drop_index(
        "ix_training_tasks_company_id_assigned_user_id",
        table_name="training_tasks",
    )
    op.drop_index(
        "ix_workflow_definitions_company_id_document_tag",
        table_name="workflow_definitions",
    )
    op.drop_index(
        "ix_templates_company_id_document_uuid",
        table_name="templates",
    )
    op.drop_index(
        "ix_documents_company_id_created_at",
        table_name="documents",
    )
    op.drop_index(
        "ix_documents_company_id_document_uuid",
        table_name="documents",
    )

    # --- Remove foreign key constraints ---

    op.drop_constraint(
        op.f("fk_agent_definitions_company_id_companies"),
        "agent_definitions",
        type_="foreignkey",
    )

    tables_non_null = [
        "documents",
        "templates",
        "workflow_definitions",
        "training_records",
        "training_tasks",
        "virtual_folders",
        "reports",
        "signature_records",
    ]

    for table in tables_non_null:
        op.drop_constraint(
            op.f(f"fk_{table}_company_id_companies"),
            table,
            type_="foreignkey",
        )

    # --- Remove company_id columns ---

    op.drop_column("agent_definitions", "company_id")

    for table in tables_non_null:
        op.drop_column(table, "company_id")

    # --- Remove default company data ---

    op.execute("DELETE FROM companies WHERE slug = 'default'")

    # --- Drop new tables ---

    op.drop_index(
        op.f("ix_company_agent_activations_agent_definition_id"),
        table_name="company_agent_activations",
    )
    op.drop_index(
        op.f("ix_company_agent_activations_company_id"),
        table_name="company_agent_activations",
    )
    op.drop_table("company_agent_activations")

    op.drop_index(
        op.f("ix_company_memberships_company_id"),
        table_name="company_memberships",
    )
    op.drop_index(
        op.f("ix_company_memberships_user_id"),
        table_name="company_memberships",
    )
    op.drop_table("company_memberships")

    op.drop_index(op.f("ix_companies_slug"), table_name="companies")
    op.drop_table("companies")
