"""Pydantic v2 schemas for per-company embedding configuration endpoints.

Provides request/response schemas for:
- GET /api/literature/index/config (read current configuration)
- PUT /api/literature/index/config (update configuration)

Includes Field validators for numeric ranges defined in Requirement 9.1:
- chunk_size_tokens: 128–2048
- chunk_overlap_tokens: 0–256
- max_chunks_per_document: 1–5000

References:
    - Requirements: 9.1, 9.7, 9.8, 9.9, 10.6
    - Design doc: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ─── Configuration Response ───────────────────────────────────────────────────


class EmbeddingConfigurationSchema(BaseModel):
    """Response schema for the current embedding configuration.

    Represents the per-company embedding settings stored in the
    EmbeddingConfiguration model. Returned by GET /api/literature/index/config.

    Attributes:
        id: Configuration record primary key.
        company_id: Company this configuration belongs to.
        chunk_size_tokens: Maximum tokens per chunk (128–2048, default 512).
        chunk_overlap_tokens: Overlap tokens between chunks (0–256, default 50).
        auto_embed_on_ingest: Automatically embed on ingestion (default True).
        embed_abstract_only: Only embed abstract text (default False).
        max_chunks_per_document: Maximum chunks per document (1–5000, default 500).
        created_at: When this configuration was created.
        updated_at: When this configuration was last modified.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    chunk_size_tokens: int = Field(
        ge=128,
        le=2048,
        description="Maximum tokens per chunk (128–2048).",
    )
    chunk_overlap_tokens: int = Field(
        ge=0,
        le=256,
        description="Overlap tokens between consecutive chunks (0–256).",
    )
    auto_embed_on_ingest: bool = Field(
        description="Whether to automatically generate embeddings on ingestion.",
    )
    embed_abstract_only: bool = Field(
        description="Whether to embed only the abstract (skip body sections).",
    )
    max_chunks_per_document: int = Field(
        ge=1,
        le=5000,
        description="Maximum chunks to index per document (1–5000).",
    )
    created_at: datetime
    updated_at: datetime


# ─── Configuration Update ─────────────────────────────────────────────────────


class EmbeddingConfigurationUpdateSchema(BaseModel):
    """Request schema for updating embedding configuration.

    All fields are optional; only provided fields are updated.
    Field validators enforce the allowed ranges per Requirement 9.9:
    - chunk_size_tokens: 128–2048
    - chunk_overlap_tokens: 0–256
    - max_chunks_per_document: 1–5000

    Attributes:
        chunk_size_tokens: Maximum tokens per chunk (128–2048).
        chunk_overlap_tokens: Overlap tokens between chunks (0–256).
        auto_embed_on_ingest: Automatically embed on ingestion.
        embed_abstract_only: Only embed abstract text.
        max_chunks_per_document: Maximum chunks per document (1–5000).
    """

    chunk_size_tokens: int | None = Field(
        default=None,
        ge=128,
        le=2048,
        description="Maximum tokens per chunk (128–2048).",
    )
    chunk_overlap_tokens: int | None = Field(
        default=None,
        ge=0,
        le=256,
        description="Overlap tokens between consecutive chunks (0–256).",
    )
    auto_embed_on_ingest: bool | None = Field(
        default=None,
        description="Whether to automatically generate embeddings on ingestion.",
    )
    embed_abstract_only: bool | None = Field(
        default=None,
        description="Whether to embed only the abstract (skip body sections).",
    )
    max_chunks_per_document: int | None = Field(
        default=None,
        ge=1,
        le=5000,
        description="Maximum chunks to index per document (1–5000).",
    )

    @model_validator(mode="after")
    def _validate_overlap_less_than_chunk_size(self) -> EmbeddingConfigurationUpdateSchema:
        """Validate that overlap does not exceed chunk size when both are provided.

        Raises:
            ValueError: If chunk_overlap_tokens >= chunk_size_tokens.
        """
        if (
            self.chunk_size_tokens is not None
            and self.chunk_overlap_tokens is not None
            and self.chunk_overlap_tokens >= self.chunk_size_tokens
        ):
            msg = "chunk_overlap_tokens must be less than chunk_size_tokens"
            raise ValueError(msg)
        return self
