"""Pydantic v2 schemas for citation collection management endpoints.

Defines request/response schemas for creating, updating, listing, and
managing citation collections and their document memberships.

References:
    - Requirements: 5.1, 5.2, 5.3, 5.4, 5.6
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class CollectionPurpose(StrEnum):
    """Purpose classification for citation collections."""

    CLINICAL_EVALUATION = "clinical_evaluation"
    POST_MARKET_SURVEILLANCE = "post_market_surveillance"
    SYSTEMATIC_LITERATURE_REVIEW = "systematic_literature_review"
    RISK_ASSESSMENT = "risk_assessment"
    OTHER = "other"


# ─── Request Schemas ─────────────────────────────────────────────────────────


class CreateCitationCollectionRequest(BaseModel):
    """Request body for POST /api/literature-search/citation-collections.

    Creates a new citation collection for organizing internalized literature
    documents by regulatory purpose.

    Attributes:
        name: Collection name (1–300 characters).
        description: Optional description of the collection (max 2000 chars).
        purpose: Regulatory purpose classification for the collection.
    """

    name: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    purpose: CollectionPurpose

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
            msg = "Collection name must not be empty or whitespace-only"
            raise ValueError(msg)
        return v.strip()


class UpdateCitationCollectionRequest(BaseModel):
    """Request body for PUT /api/literature-search/citation-collections/{id}.

    Updates an existing citation collection's metadata fields. All fields
    are optional; only provided fields are updated.

    Attributes:
        name: Updated collection name (1–300 characters, optional).
        description: Updated description (max 2000 chars, optional).
        purpose: Updated purpose classification (optional).
    """

    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    purpose: CollectionPurpose | None = None

    @field_validator("name")
    @classmethod
    def name_not_whitespace(cls, v: str | None) -> str | None:
        """Validate that name (if provided) is not whitespace-only.

        Args:
            v: The name value to validate.

        Returns:
            The stripped name or None.

        Raises:
            ValueError: If name contains only whitespace characters.
        """
        if v is not None and not v.strip():
            msg = "Collection name must not be empty or whitespace-only"
            raise ValueError(msg)
        return v.strip() if v is not None else None


class AddDocumentsRequest(BaseModel):
    """Request body for POST /api/literature-search/citation-collections/{id}/documents.

    Adds internalized documents to an existing citation collection.

    Attributes:
        document_ids: List of Document IDs to add (1–50 entries).
    """

    document_ids: list[int] = Field(..., min_length=1, max_length=50)

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids_count(cls, v: list[int]) -> list[int]:
        """Validate that 1–50 document IDs are provided.

        Args:
            v: The document IDs list to validate.

        Returns:
            The validated document IDs list.

        Raises:
            ValueError: If the list is empty or exceeds 50 entries.
        """
        if len(v) > 50:
            msg = "Maximum 50 document IDs per request"
            raise ValueError(msg)
        if len(v) < 1:
            msg = "At least 1 document ID is required"
            raise ValueError(msg)
        return v


# ─── Response Schemas ─────────────────────────────────────────────────────────


class CitationCollectionDocumentRef(BaseModel):
    """Reference to a document within a citation collection.

    Contains metadata needed for display in the collection detail view.

    Attributes:
        document_id: Primary key of the Document.
        title: Document title.
        authors: List of author names.
        publication_year: Year of publication (may be null).
        doi: Digital Object Identifier (may be null).
        position: Order position within the collection.
        added_at: Timestamp when the document was added to the collection.
    """

    document_id: int
    title: str
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    doi: str | None = None
    position: int
    added_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CitationCollectionResponse(BaseModel):
    """Response schema for a citation collection (list view).

    Returned from creation, update, and list endpoints with collection
    metadata and document count summary.

    Attributes:
        id: Primary key of the citation collection.
        name: Collection name.
        description: Optional description.
        purpose: Regulatory purpose classification.
        status: Current status ("active" or "archived").
        document_count: Number of documents in the collection.
        created_by: ID of the user who created the collection.
        company_id: ID of the owning company.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    name: str
    description: str | None = None
    purpose: CollectionPurpose
    status: str = "active"
    document_count: int = 0
    created_by: int
    company_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CitationCollectionDetailResponse(BaseModel):
    """Detailed response for a citation collection including document list.

    Returned from GET /api/literature-search/citation-collections/{id}
    with the full ordered list of document references.

    Attributes:
        id: Primary key of the citation collection.
        name: Collection name.
        description: Optional description.
        purpose: Regulatory purpose classification.
        status: Current status ("active" or "archived").
        document_count: Number of documents in the collection.
        documents: Ordered list of document references with metadata.
        created_by: ID of the user who created the collection.
        company_id: ID of the owning company.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    name: str
    description: str | None = None
    purpose: CollectionPurpose
    status: str = "active"
    document_count: int = 0
    documents: list[CitationCollectionDocumentRef] = Field(default_factory=list)
    created_by: int
    company_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedCitationCollectionResponse(BaseModel):
    """Paginated list of citation collections.

    Returned from GET /api/literature-search/citation-collections with
    pagination metadata.

    Attributes:
        items: List of citation collection records for the current page.
        page: Current page number (1-indexed).
        page_size: Number of results per page.
        total_count: Total number of matching collections.
    """

    items: list[CitationCollectionResponse]
    page: int
    page_size: int
    total_count: int
