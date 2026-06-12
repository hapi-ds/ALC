"""SQLAlchemy model for Search Execution Logs (Phase 9.6).

Defines:
- SearchExecutionLog: Immutable, append-only audit record capturing every
  search execution with full parameter capture for regulatory evidence.

This model is NOT versioned via SQLAlchemy-Continuum — it is an immutable
audit record. Immutability is enforced at the application layer via event
listeners registered in alcoabase.models.immutability at app startup.

All models follow existing project patterns:
- Inherit from Base (alcoabase.database)
- Use mapped_column with type annotations (SQLAlchemy 2.0 style)
- Include proper indexes and constraints

References:
    - Requirements 2.2
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


class SearchExecutionLog(Base):
    """Immutable audit record for literature search executions.

    Each record captures a single search execution with full parameter
    capture for regulatory evidence (FDA/EMA audit compliance). Records
    are append-only — UPDATE and DELETE operations are prevented by
    application-layer event listeners (see alcoabase.models.immutability).

    NOTE: Immutability listeners for this model should be registered
    in register_immutability_listeners() at application startup.

    Attributes:
        id: Primary key.
        user_id: FK to users table (who executed the search).
        company_id: FK to companies table (tenant isolation).
        query_text: The search query text that was executed.
        filters: JSONB object containing all applied filter parameters.
        search_mode: Search mode used (hybrid, keyword, semantic).
        include_internal: Whether internal documents were included.
        total_results: Total number of results returned.
        sources_queried: JSONB array of source adapter names searched.
        execution_duration_ms: Time taken to execute the search in milliseconds.
        saved_search_id: Optional FK to the saved search that triggered this
            execution (nullable for ad-hoc searches).
        executed_at: Timestamp of execution.
    """

    __tablename__ = "literature_search_execution_logs"

    __table_args__ = (
        Index(
            "ix_lit_search_exec_company_user_executed",
            "company_id",
            "user_id",
            "executed_at",
            postgresql_ops={"executed_at": "DESC"},
        ),
        Index(
            "ix_lit_search_exec_saved_search",
            "saved_search_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    query_text: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    search_mode: Mapped[str] = mapped_column(String(20))
    include_internal: Mapped[bool] = mapped_column(Boolean)
    total_results: Mapped[int] = mapped_column(Integer)
    sources_queried: Mapped[list] = mapped_column(JSONB)
    execution_duration_ms: Mapped[int] = mapped_column(Integer)
    saved_search_id: Mapped[int | None] = mapped_column(
        ForeignKey("literature_saved_searches.id"), nullable=True
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
