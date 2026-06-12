"""Add Phase 9.6 literature search and citation tables.

Creates:
- literature_saved_searches (persisted search query configurations)
- literature_citation_collections (named document groupings)
- literature_citation_collection_documents (collection↔document junction)
- literature_search_execution_logs (immutable audit records)

Modifies:
- documents: adds source_ingestion_record_id FK, full_text_status column,
  and partial unique index on (company_id, source_ingestion_record_id)

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2025-01-15 00:00:00.000000

References:
    - Requirements 2.2, 3.5, 4.2, 5.1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "z3a4b5c6d7e8"
down_revision: str = "y2z3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 9.6 tables and modify documents table."""

    # --- literature_saved_searches ---
    op.create_table(
        "literature_saved_searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("filters", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "search_mode", sa.String(20), nullable=False, server_default="hybrid"
        ),
        sa.Column(
            "include_internal", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for literature_saved_searches
    op.create_index(
        "ix_lit_saved_search_user_id",
        "literature_saved_searches",
        ["user_id"],
    )
    op.create_index(
        "ix_lit_saved_search_company_id",
        "literature_saved_searches",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_saved_search_company_user_status",
        "literature_saved_searches",
        ["company_id", "user_id", "status"],
    )
    op.create_index(
        "ix_lit_saved_search_company_user_last_exec",
        "literature_saved_searches",
        ["company_id", "user_id", "last_executed_at"],
        postgresql_ops={"last_executed_at": "DESC"},
    )

    # --- literature_citation_collections ---
    op.create_table(
        "literature_citation_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for literature_citation_collections
    op.create_index(
        "ix_lit_citation_coll_company_id",
        "literature_citation_collections",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_citation_coll_created_by",
        "literature_citation_collections",
        ["created_by"],
    )
    op.create_index(
        "ix_lit_citation_coll_company_status",
        "literature_citation_collections",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_lit_citation_coll_company_purpose_status",
        "literature_citation_collections",
        ["company_id", "purpose", "status"],
    )

    # --- literature_citation_collection_documents ---
    op.create_table(
        "literature_citation_collection_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("literature_citation_collections.id"),
            nullable=False,
        ),
        sa.Column(
            "document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "added_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
    )

    # Indexes for literature_citation_collection_documents
    op.create_index(
        "ix_lit_citation_coll_doc_collection_id",
        "literature_citation_collection_documents",
        ["collection_id"],
    )
    op.create_index(
        "ix_lit_citation_coll_doc_document_id",
        "literature_citation_collection_documents",
        ["document_id"],
    )
    op.create_index(
        "ix_lit_citation_coll_doc_collection_position",
        "literature_citation_collection_documents",
        ["collection_id", "position"],
    )
    op.create_index(
        "uq_lit_citation_coll_doc_collection_document",
        "literature_citation_collection_documents",
        ["collection_id", "document_id"],
        unique=True,
    )

    # --- literature_search_execution_logs ---
    op.create_table(
        "literature_search_execution_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("filters", JSONB(), nullable=False, server_default="{}"),
        sa.Column("search_mode", sa.String(20), nullable=False),
        sa.Column("include_internal", sa.Boolean(), nullable=False),
        sa.Column("total_results", sa.Integer(), nullable=False),
        sa.Column("sources_queried", JSONB(), nullable=False),
        sa.Column("execution_duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "saved_search_id",
            sa.Integer(),
            sa.ForeignKey("literature_saved_searches.id"),
            nullable=True,
        ),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for literature_search_execution_logs
    op.create_index(
        "ix_lit_search_exec_user_id",
        "literature_search_execution_logs",
        ["user_id"],
    )
    op.create_index(
        "ix_lit_search_exec_company_id",
        "literature_search_execution_logs",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_search_exec_company_user_executed",
        "literature_search_execution_logs",
        ["company_id", "user_id", "executed_at"],
        postgresql_ops={"executed_at": "DESC"},
    )
    op.create_index(
        "ix_lit_search_exec_saved_search",
        "literature_search_execution_logs",
        ["saved_search_id"],
    )

    # --- Modify documents table ---
    op.add_column(
        "documents",
        sa.Column(
            "source_ingestion_record_id",
            sa.Integer(),
            sa.ForeignKey(
                "literature_ingestion_records.id",
                name="fk_documents_source_ingestion_record_id",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "full_text_status",
            sa.String(20),
            nullable=True,
        ),
    )

    # Partial unique index on documents for source ingestion record deduplication
    op.create_index(
        "uq_documents_company_source_ingestion",
        "documents",
        ["company_id", "source_ingestion_record_id"],
        unique=True,
        postgresql_where=text("source_ingestion_record_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop Phase 9.6 tables and revert documents modifications."""

    # --- Revert documents table modifications ---
    op.drop_index(
        "uq_documents_company_source_ingestion",
        table_name="documents",
    )
    op.drop_column("documents", "full_text_status")
    op.drop_column("documents", "source_ingestion_record_id")

    # --- Drop literature_search_execution_logs ---
    op.drop_index(
        "ix_lit_search_exec_saved_search",
        table_name="literature_search_execution_logs",
    )
    op.drop_index(
        "ix_lit_search_exec_company_user_executed",
        table_name="literature_search_execution_logs",
    )
    op.drop_index(
        "ix_lit_search_exec_company_id",
        table_name="literature_search_execution_logs",
    )
    op.drop_index(
        "ix_lit_search_exec_user_id",
        table_name="literature_search_execution_logs",
    )
    op.drop_table("literature_search_execution_logs")

    # --- Drop literature_citation_collection_documents ---
    op.drop_index(
        "uq_lit_citation_coll_doc_collection_document",
        table_name="literature_citation_collection_documents",
    )
    op.drop_index(
        "ix_lit_citation_coll_doc_collection_position",
        table_name="literature_citation_collection_documents",
    )
    op.drop_index(
        "ix_lit_citation_coll_doc_document_id",
        table_name="literature_citation_collection_documents",
    )
    op.drop_index(
        "ix_lit_citation_coll_doc_collection_id",
        table_name="literature_citation_collection_documents",
    )
    op.drop_table("literature_citation_collection_documents")

    # --- Drop literature_citation_collections ---
    op.drop_index(
        "ix_lit_citation_coll_company_purpose_status",
        table_name="literature_citation_collections",
    )
    op.drop_index(
        "ix_lit_citation_coll_company_status",
        table_name="literature_citation_collections",
    )
    op.drop_index(
        "ix_lit_citation_coll_created_by",
        table_name="literature_citation_collections",
    )
    op.drop_index(
        "ix_lit_citation_coll_company_id",
        table_name="literature_citation_collections",
    )
    op.drop_table("literature_citation_collections")

    # --- Drop literature_saved_searches ---
    op.drop_index(
        "ix_lit_saved_search_company_user_last_exec",
        table_name="literature_saved_searches",
    )
    op.drop_index(
        "ix_lit_saved_search_company_user_status",
        table_name="literature_saved_searches",
    )
    op.drop_index(
        "ix_lit_saved_search_company_id",
        table_name="literature_saved_searches",
    )
    op.drop_index(
        "ix_lit_saved_search_user_id",
        table_name="literature_saved_searches",
    )
    op.drop_table("literature_saved_searches")
