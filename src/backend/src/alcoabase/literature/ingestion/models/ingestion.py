"""SQLAlchemy models for the Ingestion Pipeline (Phase 9.2).

Defines:
- IngestionRecord: Tracks lifecycle of each ingested literature item.
- IngestionConfiguration: Per-company ingestion settings.
- IngestionAuditLog: Append-only audit records (no Continuum versioning).

All models follow existing project patterns:
- Inherit from Base (alcoabase.database)
- Use AuditMixin for versioned models (SQLAlchemy-Continuum)
- Use mapped_column with type annotations (SQLAlchemy 2.0 style)
- Include proper indexes and constraints

References:
    - Requirements 1.1, 1.2, 1.6, 2.1, 2.3, 2.6, 4.5, 8.1, 9.4, 10.1, 10.2
    - Design: .kiro/specs/Step_9-2_automated-ingestion-pipeline/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class IngestionRecord(Base, AuditMixin):
    """Tracks the lifecycle of a single ingested literature item.

    Each record represents one paper/article progressing through the
    dual-stage ingestion pipeline: metadata capture → full-text retrieval
    → sanitization → indexing. State transitions are enforced by the
    ingestion state machine service.

    Attributes:
        id: Primary key.
        company_id: FK to companies table (tenant isolation).
        batch_id: UUID grouping records submitted together.
        state: Current lifecycle state (metadata_only, abstract_indexed, etc.).
        failed_from_state: State from which failure occurred (for retry logic).
        error_type: Classification of the failure (e.g., doi_not_found).
        error_message: Human-readable error description.
        retry_count: Number of retry attempts for this record.
        title: Paper title.
        authors: JSONB array of author objects.
        doi: Digital Object Identifier (nullable).
        publication_date: Date of publication.
        journal_or_venue: Journal or conference name.
        publication_type: Type of publication (article, conference_paper, etc.).
        external_id: Source-specific identifier.
        source_id: Name of the source adapter that found this result.
        url: URL to the paper on the source platform.
        abstract: Paper abstract text (nullable).
        storage_path: MinIO object path for the original downloaded file.
        file_size_bytes: Size of the downloaded file.
        content_type: MIME type of the downloaded file.
        sha256_checksum: SHA-256 hash of the downloaded file.
        download_url: URL from which the file was downloaded.
        download_timestamp: When the file was downloaded.
        sanitized_storage_path: MinIO path for the sanitized content JSON.
        word_count: Word count from sanitization.
        document_record_id: FK-like reference to document created by Dual-UUID layer.
        retention_expiry_date: When the original file should be purged.
        original_file_purged: Whether the original file has been deleted.
        purge_timestamp: When the original file was purged.
        state_history: JSONB array of state transition records.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_ingestion_records"
    __table_args__ = (
        # Partial unique index: only enforce uniqueness when doi IS NOT NULL
        Index(
            "uq_lit_ingestion_company_doi",
            "company_id",
            "doi",
            unique=True,
            postgresql_where="doi IS NOT NULL",
        ),
        UniqueConstraint(
            "company_id",
            "source_id",
            "external_id",
            name="uq_lit_ingestion_company_source_extid",
        ),
        Index(
            "ix_lit_ingestion_company_state",
            "company_id",
            "state",
        ),
        Index(
            "ix_lit_ingestion_batch",
            "batch_id",
        ),
        Index(
            "ix_lit_ingestion_retention",
            "company_id",
            "retention_expiry_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )

    # Batch tracking
    batch_id: Mapped[str] = mapped_column(String(36))

    # State machine
    state: Mapped[str] = mapped_column(String(30), default="metadata_only")
    failed_from_state: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata fields (from LiteratureSearchResult)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list] = mapped_column(JSONB, default=list)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    journal_or_venue: Mapped[str] = mapped_column(String(500))
    publication_type: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File storage fields
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    sha256_checksum: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Sanitized content reference
    sanitized_storage_path: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Dual-UUID reference
    document_record_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # Retention fields
    retention_expiry_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    original_file_purged: Mapped[bool] = mapped_column(Boolean, default=False)
    purge_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # State history (JSONB array of transition records)
    state_history: Mapped[list] = mapped_column(JSONB, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()


class IngestionConfiguration(Base, AuditMixin):
    """Per-company configuration for the ingestion pipeline.

    Controls full-text retrieval behavior, storage quotas, retention
    policies, and Dual-UUID integration settings. One record per company.

    Attributes:
        id: Primary key.
        company_id: FK to companies table (unique per company).
        full_text_retrieval_enabled: Whether to attempt full-text downloads.
        storage_quota_mb: Maximum storage in MB for this company.
        retention_days: Days to retain original files (0 = indefinite).
        unpaywall_email: Contact email for Unpaywall API (required when enabled).
        dual_uuid_integration_enabled: Whether to pipe through Dual-UUID layer.
        max_concurrent_downloads: Max parallel downloads for this company.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_ingestion_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True
    )
    full_text_retrieval_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True
    )
    storage_quota_mb: Mapped[int] = mapped_column(Integer, default=10240)
    retention_days: Mapped[int] = mapped_column(Integer, default=365)
    unpaywall_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    dual_uuid_integration_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    max_concurrent_downloads: Mapped[int] = mapped_column(Integer, default=5)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()


class IngestionAuditLog(Base):
    """Append-only audit log for ingestion pipeline operations.

    NOT versioned via SQLAlchemy-Continuum — these are immutable audit
    records. Each record captures a single pipeline event (state
    transition, download, sanitization, error, etc.) for regulatory
    traceability.

    Attributes:
        id: Primary key.
        company_id: FK to companies table (tenant isolation).
        ingestion_record_id: Reference to the IngestionRecord (nullable for
            system-level events).
        event_type: Classification of the audit event.
        details: JSONB dict with event-specific metadata.
        user_id: User who triggered the event (nullable for system events).
        created_at: Event timestamp.
    """

    __tablename__ = "literature_ingestion_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    ingestion_record_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_lit_ingestion_audit_company_timestamp",
            "company_id",
            "created_at",
        ),
    )
