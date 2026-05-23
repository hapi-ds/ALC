"""add_quiz_attempts_table

Revision ID: h5i6j7k8l9m0
Revises: g4h5i6j7k8l9
Create Date: 2026-07-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "h5i6j7k8l9m0"
down_revision: Union[str, Sequence[str], None] = "g4h5i6j7k8l9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create quiz_attempts table and quiz_attempts_version table.

    Creates:
    - quiz_attempts table with all columns, foreign keys, and indexes
    - quiz_attempts_version table for SQLAlchemy-Continuum audit trail
    """
    # --- Create quiz_attempts table ---
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.String(length=255), nullable=False),
        sa.Column("sop_document_uuid", sa.String(length=36), nullable=False),
        sa.Column("sop_version", sa.String(length=20), nullable=False),
        sa.Column(
            "answers",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_quiz_attempts_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_quiz_attempts_company_id_companies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_attempts")),
    )

    # Individual column indexes
    op.create_index(
        op.f("ix_quiz_attempts_user_id"),
        "quiz_attempts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quiz_attempts_content_id"),
        "quiz_attempts",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quiz_attempts_sop_document_uuid"),
        "quiz_attempts",
        ["sop_document_uuid"],
        unique=False,
    )

    # Composite index for fast pass checks (user_id, content_id, passed)
    op.create_index(
        "ix_quiz_attempts_user_content_passed",
        "quiz_attempts",
        ["user_id", "content_id", "passed"],
        unique=False,
    )

    # --- Create quiz_attempts_version table (SQLAlchemy-Continuum) ---
    # This table stores audit trail snapshots for ALCOA+ compliance.
    # Columns include all model fields (nullable for partial updates),
    # Continuum transaction tracking, and PropertyModTrackerPlugin columns.
    op.create_table(
        "quiz_attempts_version",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("content_id", sa.String(length=255), nullable=True),
        sa.Column("sop_document_uuid", sa.String(length=36), nullable=True),
        sa.Column("sop_version", sa.String(length=20), nullable=True),
        sa.Column(
            "answers",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("transaction_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("end_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("operation_type", sa.SmallInteger(), nullable=False),
        # PropertyModTrackerPlugin columns (track which fields were modified)
        sa.Column("user_id_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("content_id_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sop_document_uuid_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sop_version_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("answers_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("score_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("total_questions_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("passed_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attempted_at_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("company_id_mod", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint(
            "id", "transaction_id", name=op.f("pk_quiz_attempts_version")
        ),
    )
    op.create_index(
        op.f("ix_quiz_attempts_version_transaction_id"),
        "quiz_attempts_version",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quiz_attempts_version_end_transaction_id"),
        "quiz_attempts_version",
        ["end_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quiz_attempts_version_operation_type"),
        "quiz_attempts_version",
        ["operation_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop quiz_attempts_version and quiz_attempts tables."""
    # --- Drop quiz_attempts_version table ---
    op.drop_index(
        op.f("ix_quiz_attempts_version_operation_type"),
        table_name="quiz_attempts_version",
    )
    op.drop_index(
        op.f("ix_quiz_attempts_version_end_transaction_id"),
        table_name="quiz_attempts_version",
    )
    op.drop_index(
        op.f("ix_quiz_attempts_version_transaction_id"),
        table_name="quiz_attempts_version",
    )
    op.drop_table("quiz_attempts_version")

    # --- Drop quiz_attempts table ---
    op.drop_index(
        "ix_quiz_attempts_user_content_passed",
        table_name="quiz_attempts",
    )
    op.drop_index(
        op.f("ix_quiz_attempts_sop_document_uuid"),
        table_name="quiz_attempts",
    )
    op.drop_index(
        op.f("ix_quiz_attempts_content_id"),
        table_name="quiz_attempts",
    )
    op.drop_index(
        op.f("ix_quiz_attempts_user_id"),
        table_name="quiz_attempts",
    )
    op.drop_table("quiz_attempts")
