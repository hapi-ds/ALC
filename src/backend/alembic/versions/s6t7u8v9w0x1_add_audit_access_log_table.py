"""add_audit_access_log_table

Revision ID: s6t7u8v9w0x1
Revises: r5s6t7u8v9w0
Create Date: 2026-12-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "s6t7u8v9w0x1"
down_revision: Union[str, Sequence[str], None] = "r5s6t7u8v9w0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_access_log table for meta-auditing of audit trail access.

    This table records every view and export action performed against the
    audit trail. It is append-only (immutable) per ALCOA+ and 21 CFR Part 11.

    Columns:
        id: Primary key
        user_id: FK to users.id — who accessed the audit trail
        company_id: FK to companies.id — tenant context of the access
        action: "view" or "export"
        filters_applied: JSON of active filter parameters (nullable)
        event_count: Number of events exported (nullable, only for exports)
        timestamp: Server-side UTC timestamp of the access event

    Indexes:
        - ix_audit_access_log_user_id: single-column index on user_id
        - ix_audit_access_log_company_id: single-column index on company_id
        - ix_audit_access_log_timestamp: single-column index on timestamp
        - ix_audit_access_log_user_id_timestamp: composite index on (user_id, timestamp)
    """
    op.create_table(
        "audit_access_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column(
            "filters_applied",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("event_count", sa.Integer(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_audit_access_log_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_audit_access_log_company_id_companies",
        ),
    )
    op.create_index(
        "ix_audit_access_log_user_id",
        "audit_access_log",
        ["user_id"],
    )
    op.create_index(
        "ix_audit_access_log_company_id",
        "audit_access_log",
        ["company_id"],
    )
    op.create_index(
        "ix_audit_access_log_timestamp",
        "audit_access_log",
        ["timestamp"],
    )
    op.create_index(
        "ix_audit_access_log_user_id_timestamp",
        "audit_access_log",
        ["user_id", "timestamp"],
    )


def downgrade() -> None:
    """Drop audit_access_log table and all associated indexes."""
    op.drop_index(
        "ix_audit_access_log_user_id_timestamp",
        table_name="audit_access_log",
    )
    op.drop_index(
        "ix_audit_access_log_timestamp",
        table_name="audit_access_log",
    )
    op.drop_index(
        "ix_audit_access_log_company_id",
        table_name="audit_access_log",
    )
    op.drop_index(
        "ix_audit_access_log_user_id",
        table_name="audit_access_log",
    )
    op.drop_table("audit_access_log")
