"""SQLAlchemy models for Citation Collections (Phase 9.6).

Defines:
- CitationCollection: Named grouping of internalized documents for
  regulatory submissions.
- CitationCollectionDocument: Junction table linking collections to
  documents with ordering.

All models follow existing project patterns:
- Inherit from Base (alcoabase.database)
- Use AuditMixin for versioned models (SQLAlchemy-Continuum)
- Use mapped_column with type annotations (SQLAlchemy 2.0 style)
- Include proper indexes and constraints

References:
    - Requirements 5.1, 5.2, 5.3
    - Design: .kiro/specs/Step_9-6_literature-search-citation-ui/design.md
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class CitationCollection(Base, AuditMixin):
    """Named grouping of internalized documents for regulatory submissions.

    Citation collections organize internalized papers for specific
    regulatory purposes (e.g., clinical evaluation, post-market
    surveillance report, systematic literature review).

    Attributes:
        id: Primary key.
        name: Collection name (max 300 chars).
        description: Optional description of the collection purpose.
        purpose: Regulatory purpose classification.
        company_id: FK to companies table (tenant isolation).
        created_by: FK to users table (creator of the collection).
        status: Active or archived status.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
        documents: Relationship to CitationCollectionDocument junction records.
    """

    __tablename__ = "literature_citation_collections"
    __versioned__ = {}

    __table_args__ = (
        Index(
            "ix_lit_citation_coll_company_status",
            "company_id",
            "status",
        ),
        Index(
            "ix_lit_citation_coll_company_purpose_status",
            "company_id",
            "purpose",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(String(50))
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    documents: Mapped[list["CitationCollectionDocument"]] = relationship(
        back_populates="collection",
        order_by="CitationCollectionDocument.position",
    )


class CitationCollectionDocument(Base):
    """Junction model linking citation collections to documents with ordering.

    Each record represents a document's membership in a citation collection
    at a specific position. The UNIQUE constraint on (collection_id, document_id)
    prevents duplicate entries.

    Attributes:
        id: Primary key.
        collection_id: FK to the citation collection.
        document_id: FK to the internalized document.
        position: Ordering position within the collection.
        added_at: Timestamp when the document was added.
        added_by: FK to the user who added the document.
        collection: Relationship back to CitationCollection.
    """

    __tablename__ = "literature_citation_collection_documents"

    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "document_id",
            name="uq_lit_citation_coll_doc_collection_document",
        ),
        Index(
            "ix_lit_citation_coll_doc_collection_position",
            "collection_id",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("literature_citation_collections.id"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    added_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Relationships
    collection: Mapped["CitationCollection"] = relationship(
        back_populates="documents"
    )
