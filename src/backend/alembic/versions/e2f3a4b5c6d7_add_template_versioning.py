"""add_template_versioning

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-05-20 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add template versioning tables and enhanced field columns.

    Creates:
    - template_versions table with constraints:
      - UNIQUE (template_id, version_number)
      - CHECK (version_number > 0)
      - Partial unique index on (template_id, is_active) WHERE is_active = TRUE
    - template_version_fields table with:
      - UNIQUE (version_id, field_uuid)
    - New columns on template_fields for rich field configuration
    """
    # --- Create template_versions table ---
    op.create_table(
        "template_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("document_uuid", sa.String(length=12), nullable=False),
        sa.Column(
            "json_schema",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ReadOnly",
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
            name=op.f("fk_template_versions_template_id_templates"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_template_versions_created_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_versions")),
        sa.UniqueConstraint(
            "template_id",
            "version_number",
            name="uq_template_versions_template_version",
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name=op.f("ck_template_versions_version_positive"),
        ),
    )
    op.create_index(
        op.f("ix_template_versions_template_id"),
        "template_versions",
        ["template_id"],
        unique=False,
    )
    # Partial unique index: only one active version per template
    op.create_index(
        "ix_template_versions_active",
        "template_versions",
        ["template_id", "is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    # --- Create template_version_fields table ---
    op.create_table(
        "template_version_fields",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("field_uuid", sa.String(length=40), nullable=False),
        sa.Column("field_type", sa.String(length=20), nullable=False),
        sa.Column("field_label", sa.String(length=200), nullable=False),
        sa.Column("field_order", sa.Integer(), nullable=False),
        sa.Column(
            "element_type",
            sa.String(length=20),
            nullable=False,
            server_default="field",
        ),
        sa.Column("content_type", sa.String(length=20), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column(
            "config",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("help_text", sa.String(length=500), nullable=True),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["template_versions.id"],
            name=op.f("fk_template_version_fields_version_id_template_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_version_fields")),
        sa.UniqueConstraint(
            "version_id",
            "field_uuid",
            name="uq_template_version_fields_uuid",
        ),
    )
    op.create_index(
        op.f("ix_template_version_fields_version_id"),
        "template_version_fields",
        ["version_id"],
        unique=False,
    )

    # --- Add new columns to template_fields for rich field configuration ---
    op.add_column(
        "template_fields",
        sa.Column(
            "element_type",
            sa.String(length=20),
            nullable=False,
            server_default="field",
        ),
    )
    op.add_column(
        "template_fields",
        sa.Column("content_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "template_fields",
        sa.Column("text_content", sa.Text(), nullable=True),
    )
    op.add_column(
        "template_fields",
        sa.Column(
            "config",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "template_fields",
        sa.Column(
            "required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "template_fields",
        sa.Column("help_text", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "template_fields",
        sa.Column("default_value", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove template versioning tables and enhanced field columns."""
    # --- Remove new columns from template_fields ---
    op.drop_column("template_fields", "default_value")
    op.drop_column("template_fields", "help_text")
    op.drop_column("template_fields", "required")
    op.drop_column("template_fields", "config")
    op.drop_column("template_fields", "text_content")
    op.drop_column("template_fields", "content_type")
    op.drop_column("template_fields", "element_type")

    # --- Drop template_version_fields table ---
    op.drop_index(
        op.f("ix_template_version_fields_version_id"),
        table_name="template_version_fields",
    )
    op.drop_table("template_version_fields")

    # --- Drop template_versions table ---
    op.drop_index(
        "ix_template_versions_active",
        table_name="template_versions",
    )
    op.drop_index(
        op.f("ix_template_versions_template_id"),
        table_name="template_versions",
    )
    op.drop_table("template_versions")
