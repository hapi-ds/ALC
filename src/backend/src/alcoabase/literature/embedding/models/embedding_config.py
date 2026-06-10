"""EmbeddingConfiguration SQLAlchemy model for per-company embedding settings.

Stores configurable parameters for embedding generation per company,
including chunk size, overlap, auto-embed behavior, and max chunks.
Versioned via SQLAlchemy-Continuum for full audit trail.

References:
    - Requirement 9.1: Per-company embedding configuration
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class EmbeddingConfiguration(Base, AuditMixin):
    """Per-company embedding generation configuration.

    Each company has at most one EmbeddingConfiguration record (enforced
    by unique constraint on company_id). Controls how text is chunked,
    whether embedding happens automatically on ingestion, and limits
    on chunks per document.

    Attributes:
        id: Primary key.
        company_id: FK to companies table (unique — one config per company).
        chunk_size_tokens: Maximum tokens per chunk (128–2048, default 512).
        chunk_overlap_tokens: Token overlap between chunks (0–256, default 50).
        auto_embed_on_ingest: Auto-generate embeddings on ingestion (default True).
        embed_abstract_only: Only embed abstracts, skip body (default False).
        max_chunks_per_document: Max chunks indexed per document (1–5000, default 500).
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_embedding_configurations"
    __versioned__: dict = {}

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True
    )
    chunk_size_tokens: Mapped[int] = mapped_column(
        Integer, default=512
    )
    chunk_overlap_tokens: Mapped[int] = mapped_column(
        Integer, default=50
    )
    auto_embed_on_ingest: Mapped[bool] = mapped_column(default=True)
    embed_abstract_only: Mapped[bool] = mapped_column(default=False)
    max_chunks_per_document: Mapped[int] = mapped_column(
        Integer, default=500
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()
