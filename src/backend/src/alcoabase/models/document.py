"""Document and DocumentVersion models for document management.

This module defines the core document models that support versioned
document storage with full audit trail via SQLAlchemy-Continuum.

References:
    - Document-UUID format: YYYY-NNNNN (year prefix + zero-padded sequence)
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class Document(Base, AuditMixin):
    """Core document model with UUID-based identification and tagging.

    Documents are the primary managed entities in AlcoaBase. Each document
    receives a unique Document-UUID upon creation and can have multiple
    versions, tags, and workflow states.

    Attributes:
        id: Primary key.
        document_uuid: Unique identifier in YYYY-NNNNN format.
        title: Document title (max 500 chars).
        folder_path: Logical folder path for organization.
        document_type: Classification type (SOP, Report, Template, etc.).
        current_status: Current workflow state (Draft, Review, Approved, etc.).
        is_csv_validation_record: Flag to exclude from standard searches
            and audit trail versioning.
        created_by: Foreign key to the creating user.
        created_at: Server-side UTC timestamp of creation.
        tags: One-to-many relationship to DocumentTag.
        versions: One-to-many relationship to DocumentVersion.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_uuid: Mapped[str] = mapped_column(
        String(12), unique=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    folder_path: Mapped[str] = mapped_column(String(1000))
    document_type: Mapped[str] = mapped_column(String(100))
    current_status: Mapped[str] = mapped_column(String(50))
    is_csv_validation_record: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    source_ingestion_record_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("literature_ingestion_records.id"), nullable=True, index=True
    )
    is_demo_data: Mapped[bool] = mapped_column(default=False)

    tags: Mapped[list["DocumentTag"]] = relationship(back_populates="document")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document"
    )


class DocumentTag(Base):
    """Tag model for document classification and virtual folder filtering.

    Tags enable flexible document categorization and are used by virtual
    folders to dynamically aggregate documents.

    Attributes:
        id: Primary key.
        document_id: Foreign key to the parent document.
        tag: Tag string value (e.g., "SOP", "Lab-A", "Report").
        document: Back-reference to the parent Document.
    """

    __tablename__ = "document_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    tag: Mapped[str] = mapped_column(String(100), index=True)

    document: Mapped["Document"] = relationship(back_populates="tags")


class DocumentVersion(Base, AuditMixin):
    """Versioned document storage model.

    Each version represents a specific revision of a document, stored
    in MinIO with a SHA-512 hash for integrity verification.

    Attributes:
        id: Primary key.
        document_id: Foreign key to the parent document.
        major_version: Major version number (content changes requiring re-training).
        minor_version: Minor version number (editorial corrections).
        storage_key: MinIO object key for the stored file.
        file_hash: SHA-512 hash of the file content for integrity verification.
        uploaded_by: Foreign key to the uploading user.
        uploaded_at: Server-side UTC timestamp of upload.
        change_reason: User-provided reason for the version change.
        content_type: MIME type of the stored file (nullable for legacy rows).
        document: Back-reference to the parent Document.
    """

    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    major_version: Mapped[int] = mapped_column(default=1)
    minor_version: Mapped[int] = mapped_column(default=0)
    storage_key: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(128))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(200), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="versions")
