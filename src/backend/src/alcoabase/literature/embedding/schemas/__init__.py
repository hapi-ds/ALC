"""Pydantic v2 schemas for embedding search, indexing, and configuration.

This package provides request/response schemas for:
- Hybrid search (BM25 + kNN) and unified search endpoints
- Re-indexing operations and progress tracking
- Per-company embedding configuration management

References:
    - Requirements: 6.5, 6.6, 10.1, 10.2, 10.4, 10.5, 10.6
    - Design doc: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
"""

from alcoabase.literature.embedding.schemas.configuration import (
    EmbeddingConfigurationSchema,
    EmbeddingConfigurationUpdateSchema,
)
from alcoabase.literature.embedding.schemas.indexing import (
    IndexStatusSchema,
    ReindexProgressSchema,
    ReindexRequestSchema,
)
from alcoabase.literature.embedding.schemas.search import (
    HybridSearchRequestSchema,
    HybridSearchResponseSchema,
    HybridSearchResultSchema,
)

__all__ = [
    "EmbeddingConfigurationSchema",
    "EmbeddingConfigurationUpdateSchema",
    "HybridSearchRequestSchema",
    "HybridSearchResponseSchema",
    "HybridSearchResultSchema",
    "IndexStatusSchema",
    "ReindexProgressSchema",
    "ReindexRequestSchema",
]
