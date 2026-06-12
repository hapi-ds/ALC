"""Pydantic v2 schemas for search results export endpoint.

Defines request schema for generating CSV or PDF exports of search
results with optional PRISMA flow diagram inclusion.

References:
    - Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class ExportFormat(StrEnum):
    """Output format for search results export."""

    CSV = "csv"
    PDF = "pdf"


# ─── Request Schema ──────────────────────────────────────────────────────────


class ExportRequest(BaseModel):
    """Request body for POST /api/literature-search/export.

    Generates an export of search results in the specified format.
    At least one of search_execution_id or saved_search_id must be provided.

    Attributes:
        search_execution_id: ID of a past search execution to export (optional).
        saved_search_id: ID of a saved search to re-execute and export (optional).
        format: Output format (csv or pdf).
        include_prisma_flow: Whether to include PRISMA flow diagram (PDF only).
    """

    search_execution_id: int | None = None
    saved_search_id: int | None = None
    format: ExportFormat = Field(default=ExportFormat.CSV)
    include_prisma_flow: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_at_least_one_reference(self) -> ExportRequest:
        """Validate that at least one search reference is provided.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If neither search_execution_id nor saved_search_id is set.
        """
        if self.search_execution_id is None and self.saved_search_id is None:
            msg = (
                "At least one of search_execution_id or saved_search_id "
                "must be provided"
            )
            raise ValueError(msg)
        return self
