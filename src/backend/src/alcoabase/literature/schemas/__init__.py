"""Pydantic schemas for the literature search engine.

Contains request/response schemas for search queries, results,
source configuration, search profiles, and admin endpoints.
"""

from alcoabase.literature.schemas.search import (
    AdapterCapabilities,
    AdapterRegistryEntry,
    AsyncTaskResponse,
    AsyncTaskStatus,
    DatePrecision,
    LiteratureSearchResult,
    PartialResultInfo,
    PublicationType,
    SearchQuery,
    SearchResponse,
    TaskStatus,
)

__all__ = [
    "AdapterCapabilities",
    "AdapterRegistryEntry",
    "AsyncTaskResponse",
    "AsyncTaskStatus",
    "DatePrecision",
    "LiteratureSearchResult",
    "PartialResultInfo",
    "PublicationType",
    "SearchQuery",
    "SearchResponse",
    "TaskStatus",
]
