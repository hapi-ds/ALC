"""Pydantic v2 schemas for saved search CRUD endpoints.

Defines request/response schemas for creating, listing, executing,
and deleting saved search configurations.

References:
    - Requirements: 3.1, 3.2, 3.5
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alcoabase.literature.search.schemas.query import SearchFilters, SearchMode


# ─── Request Schemas ─────────────────────────────────────────────────────────


class CreateSavedSearchRequest(BaseModel):
    """Request body for POST /api/literature-search/saved-searches.

    Persists a search configuration for later re-execution, including
    the complete filter set and search mode settings.

    Attributes:
        name: User-provided name for the saved search (1–200 characters).
        description: Optional description of the search purpose (max 1000 chars).
        query_text: The search query string (1–1000 characters, non-whitespace).
        filters: Faceted filter constraints to persist.
        search_mode: Retrieval strategy to use on re-execution.
        include_internal: Whether to include internal documents on re-execution.
    """

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    query_text: str = Field(..., min_length=1, max_length=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    search_mode: SearchMode = Field(default=SearchMode.HYBRID)
    include_internal: bool = Field(default=False)

    @field_validator("query_text")
    @classmethod
    def query_text_not_whitespace(cls, v: str) -> str:
        """Validate that query_text is not empty or whitespace-only.

        Args:
            v: The query text value to validate.

        Returns:
            The stripped query text.

        Raises:
            ValueError: If query_text contains only whitespace characters.
        """
        if not v.strip():
            msg = "Search query must not be empty or whitespace-only"
            raise ValueError(msg)
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_not_whitespace(cls, v: str) -> str:
        """Validate that name is not empty or whitespace-only.

        Args:
            v: The name value to validate.

        Returns:
            The stripped name.

        Raises:
            ValueError: If name contains only whitespace characters.
        """
        if not v.strip():
            msg = "Saved search name must not be empty or whitespace-only"
            raise ValueError(msg)
        return v.strip()


# ─── Response Schemas ─────────────────────────────────────────────────────────


class SavedSearchResponse(BaseModel):
    """Response schema for a saved search record.

    Returned from creation, listing, and detail endpoints with the
    full saved search configuration and execution metadata.

    Attributes:
        id: Primary key of the saved search.
        name: User-provided name.
        description: Optional description.
        query_text: Stored search query string.
        filters: Stored faceted filter constraints.
        search_mode: Stored retrieval strategy.
        include_internal: Stored internal document inclusion flag.
        user_id: ID of the user who created the saved search.
        company_id: ID of the owning company.
        last_executed_at: Timestamp of last execution (null if never executed).
        last_result_count: Result count from last execution (null if never executed).
        status: Current status ("active" or "archived").
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    name: str
    description: str | None = None
    query_text: str
    filters: SearchFilters
    search_mode: SearchMode
    include_internal: bool
    user_id: int
    company_id: int
    last_executed_at: datetime | None = None
    last_result_count: int | None = None
    status: str = "active"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedSavedSearchResponse(BaseModel):
    """Paginated list of saved searches.

    Returned from GET /api/literature-search/saved-searches with pagination
    metadata.

    Attributes:
        items: List of saved search records for the current page.
        page: Current page number (1-indexed).
        page_size: Number of results per page.
        total_count: Total number of matching saved searches.
    """

    items: list[SavedSearchResponse]
    page: int
    page_size: int
    total_count: int
