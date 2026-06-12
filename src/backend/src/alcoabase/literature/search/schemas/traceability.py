"""Pydantic v2 schemas for literature traceability link endpoints.

Defines request/response schemas for creating, listing, and deleting
traceability links between internalized literature documents and
requirements or test cases.

References:
    - Requirements: 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alcoabase.literature.search.schemas.internalization import (
    TraceabilityTargetType,
)


# ─── Nested Schemas ──────────────────────────────────────────────────────────


class TraceabilityLinkEntry(BaseModel):
    """A single traceability link specification within a creation request.

    Defines the target entity and optional rationale for linking
    an internalized document to a requirement or test case.

    Attributes:
        target_type: Type of the target entity (requirement or test_case).
        target_id: ID of the target requirement or test case.
        rationale: Optional justification for the link (max 1000 chars).
    """

    target_type: TraceabilityTargetType
    target_id: int
    rationale: str | None = Field(default=None, max_length=1000)


# ─── Request Schema ──────────────────────────────────────────────────────────


class CreateTraceabilityLinksRequest(BaseModel):
    """Request body for POST /api/literature-search/traceability-links.

    Creates one or more traceability links between an internalized document
    and requirements or test cases in the Traceability Matrix.

    Attributes:
        document_id: ID of the internalized Document to link from.
        links: Array of link specifications (1–20 entries).
    """

    document_id: int
    links: list[TraceabilityLinkEntry] = Field(..., min_length=1, max_length=20)

    @field_validator("links")
    @classmethod
    def validate_links_count(
        cls, v: list[TraceabilityLinkEntry],
    ) -> list[TraceabilityLinkEntry]:
        """Validate that 1–20 traceability links are provided.

        Args:
            v: The links list to validate.

        Returns:
            The validated links list.

        Raises:
            ValueError: If the list exceeds 20 entries.
        """
        if len(v) > 20:
            msg = "Maximum 20 traceability links per request"
            raise ValueError(msg)
        return v


# ─── Response Schemas ─────────────────────────────────────────────────────────


class TraceabilityLinkResponse(BaseModel):
    """Response schema for a single traceability link.

    Returned after creation or from listing endpoints with full link
    metadata including rationale and timestamps.

    Attributes:
        id: Primary key of the traceability link.
        document_id: ID of the source internalized Document.
        target_type: Type of the target entity.
        target_id: ID of the target requirement or test case.
        rationale: Optional justification for the link.
        link_method: Detection method used ("literature_evidence").
        link_confidence: Confidence score (always 1.0 for manual links).
        created_by: ID of the user who created the link.
        company_id: ID of the owning company.
        created_at: Link creation timestamp.
    """

    id: int
    document_id: int
    target_type: TraceabilityTargetType
    target_id: int
    rationale: str | None = None
    link_method: str = "literature_evidence"
    link_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_by: int
    company_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedTraceabilityLinksResponse(BaseModel):
    """Paginated list of traceability links.

    Returned from GET /api/literature-search/traceability-links with
    pagination metadata.

    Attributes:
        items: List of traceability link records for the current page.
        page: Current page number (1-indexed).
        page_size: Number of results per page.
        total_count: Total number of matching traceability links.
    """

    items: list[TraceabilityLinkResponse]
    page: int
    page_size: int
    total_count: int
