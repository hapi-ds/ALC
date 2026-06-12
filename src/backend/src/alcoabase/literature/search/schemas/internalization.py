"""Pydantic v2 schemas for the one-click internalization endpoint.

Defines request/response schemas for converting IngestionRecords into
managed Document entities with optional traceability links and citation
collection assignment.

References:
    - Requirements: 4.1, 4.2, 4.4, 4.5
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class TraceabilityTargetType(StrEnum):
    """Target entity type for traceability link creation."""

    REQUIREMENT = "requirement"
    TEST_CASE = "test_case"


# ─── Nested Schemas ──────────────────────────────────────────────────────────


class TraceabilityLinkInput(BaseModel):
    """A single traceability link to create during internalization.

    Links the internalized document to a specific requirement or test case
    in the Traceability Matrix.

    Attributes:
        target_type: Type of the target entity (requirement or test_case).
        target_id: ID of the target requirement or test case.
    """

    target_type: TraceabilityTargetType
    target_id: int


# ─── Request Schema ──────────────────────────────────────────────────────────


class InternalizationRequest(BaseModel):
    """Request body for POST /api/literature-search/internalize.

    Converts an IngestionRecord into a managed internal Document entity,
    optionally creating traceability links and adding to a citation collection.

    Attributes:
        ingestion_record_id: ID of the IngestionRecord to internalize.
        document_name: Override name for the created Document (defaults to paper title).
        document_type: Document type classification (default "literature").
        tags: Optional tags for the created Document (max 20).
        citation_collection_id: Optional collection to add the document to.
        traceability_links: Optional traceability links to create (max 20).
    """

    ingestion_record_id: int
    document_name: str | None = None
    document_type: str = Field(default="literature")
    tags: list[str] = Field(default_factory=list, max_length=20)
    citation_collection_id: int | None = None
    traceability_links: list[TraceabilityLinkInput] = Field(
        default_factory=list, max_length=20
    )

    @field_validator("tags")
    @classmethod
    def validate_tags_count(cls, v: list[str]) -> list[str]:
        """Validate that no more than 20 tags are provided.

        Args:
            v: The tags list to validate.

        Returns:
            The validated tags list.

        Raises:
            ValueError: If more than 20 tags are provided.
        """
        if len(v) > 20:
            msg = "Maximum 20 tags allowed"
            raise ValueError(msg)
        return v

    @field_validator("traceability_links")
    @classmethod
    def validate_traceability_links_count(
        cls, v: list[TraceabilityLinkInput],
    ) -> list[TraceabilityLinkInput]:
        """Validate that no more than 20 traceability links are provided.

        Args:
            v: The traceability links list to validate.

        Returns:
            The validated traceability links list.

        Raises:
            ValueError: If more than 20 links are provided.
        """
        if len(v) > 20:
            msg = "Maximum 20 traceability links allowed"
            raise ValueError(msg)
        return v


# ─── Response Schema ─────────────────────────────────────────────────────────


class InternalizedDocumentResponse(BaseModel):
    """Response for a successfully internalized document.

    Returned from POST /api/literature-search/internalize (HTTP 201) with
    the newly created Document entity details.

    Attributes:
        id: Primary key of the created Document.
        document_name: Name of the created Document.
        document_type: Type classification of the Document.
        source_ingestion_record_id: FK back to the originating IngestionRecord.
        full_text_status: Status of the full-text file copy ("available" or "unavailable").
        current_status: Initial BPMN workflow state (always "Draft").
        tags: Tags applied to the Document.
        traceability_link_ids: IDs of created traceability links (empty if none).
        citation_collection_id: Collection the document was added to (null if none).
        created_at: Document creation timestamp.
    """

    id: int
    document_name: str
    document_type: str
    source_ingestion_record_id: int
    full_text_status: str = "available"
    current_status: str = "Draft"
    tags: list[str] = Field(default_factory=list)
    traceability_link_ids: list[int] = Field(default_factory=list)
    citation_collection_id: int | None = None
    created_at: datetime
