"""add ingestion pipeline tables

Revision ID: v9w0x1y2z3a4
Revises: u8v9w0x1y2z3
Create Date: 2027-02-15 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "v9w0x1y2z3a4"
down_revision: Union[str, Sequence[str], None] = "u8v9w0x1y2z3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ingestion pipeline tables.

    Tables created:
        - literature_ingestion_records: Tracks lifecycle of ingested literature items
        - literature_ingestion_configurations: Per-company ingestion settings
        - literature_ingestion_audit_log: Append-only audit log for ingestion events
    """

    # --- literature_ingestion_records ---
    op.create_table(
        "literature_ingestion_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column(
            "state",
            sa.String(length=30),
            nullable=False,
            server_default="metadata_only",
        ),
        sa.Column("failed_from_state", sa.String(length=30), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        # Metadata fields (from LiteratureSearchResult)
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "authors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("publication_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("journal_or_venue", sa.String(length=500), nullable=False),
        sa.Column("publication_type", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        # File storage fields
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("download_timestamp", sa.DateTime(timezone=True), nullable=True),
        # Sanitized content reference
        sa.Column("sanitized_storage_path", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        # Dual-UUID reference
        sa.Column("document_record_id", sa.Integer(), nullable=True),
        # Retention fields
        sa.Column("retention_expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "original_file_purged",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("purge_timestamp", sa.DateTime(timezone=True), nullable=True),
        # State history (JSONB array of transition records)
        sa.Column(
            "state_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        # Timestamps
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
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_ingestion_records_company_id_companies",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_id",
            "external_id",
            name="uq_lit_ingestion_company_source_extid",
        ),
    )

    # Index on company_id (for FK lookups)
    op.create_index(
        "ix_literature_ingestion_records_company_id",
        "literature_ingestion_records",
        ["company_id"],
    )

    # Partial unique index: enforce DOI uniqueness per company only when doi IS NOT NULL
    op.execute(
        "CREATE UNIQUE INDEX uq_lit_ingestion_company_doi "
        "ON literature_ingestion_records (company_id, doi) "
        "WHERE doi IS NOT NULL"
    )

    # Composite index on (company_id, state) for filtering by state per company
    op.create_index(
        "ix_lit_ingestion_company_state",
        "literature_ingestion_records",
        ["company_id", "state"],
    )

    # Index on batch_id for batch status lookups
    op.create_index(
        "ix_lit_ingestion_batch",
        "literature_ingestion_records",
        ["batch_id"],
    )

    # Index on (company_id, retention_expiry_date) for retention cleanup queries
    op.create_index(
        "ix_lit_ingestion_retention",
        "literature_ingestion_records",
        ["company_id", "retention_expiry_date"],
    )

    # --- literature_ingestion_configurations ---
    op.create_table(
        "literature_ingestion_configurations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "full_text_retrieval_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "storage_quota_mb",
            sa.Integer(),
            nullable=False,
            server_default="10240",
        ),
        sa.Column(
            "retention_days",
            sa.Integer(),
            nullable=False,
            server_default="365",
        ),
        sa.Column("unpaywall_email", sa.String(length=255), nullable=True),
        sa.Column(
            "dual_uuid_integration_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "max_concurrent_downloads",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        # Timestamps
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
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_ingestion_config_company_id_companies",
        ),
        sa.UniqueConstraint("company_id", name="uq_lit_ingestion_config_company_id"),
    )

    # Index on company_id (unique constraint also creates an index,
    # but explicit for clarity and FK lookup)
    op.create_index(
        "ix_literature_ingestion_configurations_company_id",
        "literature_ingestion_configurations",
        ["company_id"],
    )

    # --- literature_ingestion_audit_log ---
    op.create_table(
        "literature_ingestion_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("ingestion_record_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_ingestion_audit_company_id_companies",
        ),
    )

    # Index on company_id for FK lookups
    op.create_index(
        "ix_literature_ingestion_audit_log_company_id",
        "literature_ingestion_audit_log",
        ["company_id"],
    )

    # Index on ingestion_record_id for record-specific queries
    op.create_index(
        "ix_literature_ingestion_audit_log_record_id",
        "literature_ingestion_audit_log",
        ["ingestion_record_id"],
    )

    # Composite index on (company_id, created_at) for time-based queries per company
    op.create_index(
        "ix_lit_ingestion_audit_company_timestamp",
        "literature_ingestion_audit_log",
        ["company_id", "created_at"],
    )


def downgrade() -> None:
    """Drop all ingestion pipeline tables in reverse creation order."""
    op.drop_table("literature_ingestion_audit_log")
    op.drop_table("literature_ingestion_configurations")
    # Drop the partial unique index explicitly before dropping the table
    op.execute("DROP INDEX IF EXISTS uq_lit_ingestion_company_doi")
    op.drop_table("literature_ingestion_records")
