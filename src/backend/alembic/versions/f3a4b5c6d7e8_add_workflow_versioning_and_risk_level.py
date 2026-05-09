"""add_workflow_versioning_and_risk_level

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-05-25 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add workflow versioning and risk level support.

    Changes:
    1. Add risk_level column to workflow_definitions (with CHECK constraint)
    2. Add auto_assignment_config column to workflow_definitions
    3. Add current_version column to workflow_definitions
    4. Create workflow_versions table with unique constraint
    5. Backfill: create version 1 record for each existing WorkflowDefinition
    """
    # --- Add new columns to workflow_definitions ---

    op.add_column(
        "workflow_definitions",
        sa.Column(
            "risk_level",
            sa.String(length=20),
            nullable=False,
            server_default="low",
        ),
    )
    op.create_check_constraint(
        "risk_level",
        "workflow_definitions",
        "risk_level IN ('low', 'medium', 'high', 'critical')",
    )

    op.add_column(
        "workflow_definitions",
        sa.Column(
            "auto_assignment_config",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.add_column(
        "workflow_definitions",
        sa.Column(
            "current_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    # --- Create workflow_versions table ---

    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("bpmn_xml", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("document_tag", sa.String(length=100), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column(
            "signature_required_transitions",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "training_trigger_transitions",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "auto_assignment_config",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("change_reason", sa.String(length=500), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflow_definitions.id"],
            name=op.f("fk_workflow_versions_workflow_id_workflow_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_workflow_versions_created_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_workflow_versions_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_versions")),
        sa.UniqueConstraint(
            "workflow_id",
            "version_number",
            name="uq_workflow_version",
        ),
    )
    op.create_index(
        op.f("ix_workflow_versions_workflow_id"),
        "workflow_versions",
        ["workflow_id"],
        unique=False,
    )

    # --- Backfill: create version 1 record for each existing WorkflowDefinition ---

    op.execute(
        """
        INSERT INTO workflow_versions (
            workflow_id,
            version_number,
            bpmn_xml,
            name,
            document_tag,
            risk_level,
            signature_required_transitions,
            training_trigger_transitions,
            auto_assignment_config,
            created_by,
            change_reason,
            company_id
        )
        SELECT
            id,
            1,
            bpmn_xml,
            name,
            document_tag,
            COALESCE(risk_level, 'low'),
            signature_required_transitions,
            training_trigger_transitions,
            auto_assignment_config,
            created_by,
            'Initial version (migration backfill)',
            company_id
        FROM workflow_definitions
        """
    )


def downgrade() -> None:
    """Remove workflow versioning and risk level support."""
    # --- Drop workflow_versions table ---
    op.drop_index(
        op.f("ix_workflow_versions_workflow_id"),
        table_name="workflow_versions",
    )
    op.drop_table("workflow_versions")

    # --- Remove new columns from workflow_definitions ---
    op.drop_column("workflow_definitions", "current_version")
    op.drop_column("workflow_definitions", "auto_assignment_config")
    op.drop_constraint(
        "risk_level",
        "workflow_definitions",
        type_="check",
    )
    op.drop_column("workflow_definitions", "risk_level")
