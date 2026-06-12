"""SQLAlchemy model for Saved Searches (Phase 9.6).

Defines:
- SavedSearch: Persisted search query configuration enabling reproducible
  search methodology documentation for systematic literature reviews.

All models follow existing project patterns:
- Inherit from Base (alcoabase.database)
- Use AuditMixin for versioned models (SQLAlchemy-Continuum)
- Use mapped_column with type annotations (SQLAlchemy 2.0 style)
- Include proper indexes and constraints

References:
    - Requirements 2.2, 3.5
    - Design: .kiro/specs/Step_9-6_literature-search-citation-ui/design.md
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class SavedSearch(Base, AuditMixin):
    """Persisted search query configuration for re-execution and audit evidence.

    Enables users to save search queries (including all filter parameters)
    for later re-execution, providing regulatory evidence of search methodology
    for systematic literature reviews and clinical evaluations.

    Attributes:
        id: Primary key.
        name: User-provided name for the saved search (max 200 chars).
        description: Optional description of the search purpose.
        query_text: The search query text.
        filters: JSONB object containing all applied filter parameters.
        search_mode: Search mode used (hybrid, keyword, semantic).
        include_internal: Whether to include internal documents in results.
        user_id: FK to users table (owner of the saved search).
        company_id: FK to companies table (tenant isolation).
        last_executed_at: Timestamp of last execution (nullable).
        last_result_count: Result count from last execution (nullable).
        status: Active or archived status.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_saved_searches"
    __versioned__ = {}

    __table_args__ = (
        Index(
            "ix_lit_saved_search_company_user_status",
            "company_id",
            "user_id",
            "status",
        ),
        Index(
            "ix_lit_saved_search_company_user_last_exec",
            "company_id",
            "user_id",
            "last_executed_at",
            postgresql_ops={"last_executed_at": "DESC"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_text: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    search_mode: Mapped[str] = mapped_column(String(20), default="hybrid")
    include_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_result_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
