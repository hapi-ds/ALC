"""Document generation models for AI Template-Based Document Generator.

This module defines the database models for the Template-Based AI Document
Generator (Phase 5.4), including:
- DocumentTemplate: Registered .docx templates with structural analysis
- GenerationProvenance: Immutable audit records for generated documents
- CrossReferenceEntry: Immutable cross-reference records for generated documents
- GenerationJobMetadata: Async generation job tracking with progress

GenerationProvenance and CrossReferenceEntry are intentionally immutable
(no AuditMixin, no UPDATE/DELETE) to satisfy GxP audit trail requirements.
DocumentTemplate and GenerationJobMetadata use AuditMixin for versioned
audit trails via SQLAlchemy-Continuum.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class DocumentTemplate(Base, AuditMixin):
    """Registered .docx template with structural analysis for document generation.

    A DocumentTemplate represents an existing .docx file that has been
    designated as a "Master Template" for guiding the structure of AI-generated
    documents. The template_analysis field stores the extracted structural
    layout (section hierarchy, numbering, styles, placeholders).

    Attributes:
        id: Primary key.
        document_id: Foreign key to the source document.
        document_version_id: Foreign key to the specific version used as template.
        company_id: Foreign key to the owning company (tenant isolation).
        template_name: Human-readable name for the template (max 500 chars).
        document_type_target: Target document type (e.g., "URS", "MVP", "SOP").
        template_analysis: JSONB containing the full TemplateAnalysis structure.
        status: Template status ("active" or "archived").
        registered_by: Foreign key to the user who registered the template.
        registered_at: Timestamp when the template was registered.
        created_at: Server-side UTC timestamp of creation.
        updated_at: Timestamp of last update.
    """

    __tablename__ = "document_templates"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "company_id",
            name="uq_document_template_version_company",
        ),
        Index("ix_document_template_company", "company_id"),
        Index("ix_document_template_type", "document_type_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    template_name: Mapped[str] = mapped_column(String(500), nullable=False)
    document_type_target: Mapped[str] = mapped_column(String(100), nullable=False)
    template_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    registered_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class GenerationProvenance(Base):
    """Immutable provenance record for AI-generated documents.

    Captures the complete audit trail of a document generation event:
    which template was used, which knowledge base sources were retrieved,
    which agent archetype was used, generation parameters, and per-section
    provenance details. This record is append-only — no UPDATE or DELETE
    operations are permitted.

    Attributes:
        id: Primary key.
        generation_id: UUID string uniquely identifying this generation event.
        document_id: Foreign key to the generated document (set after creation).
        document_version_id: Foreign key to the generated document version.
        template_id: Foreign key to the template used for generation.
        company_id: Foreign key to the owning company (tenant isolation).
        requesting_user_id: Foreign key to the user who requested generation.
        agent_archetype: Name of the agent archetype used (e.g., "technical_writer").
        generation_parameters: JSONB containing generation config (temperature, etc.).
        source_document_uuids: JSON list of document UUIDs used as KB sources.
        reference_document_ids: JSON list of explicitly provided reference doc IDs.
        section_provenance: JSONB list of per-section provenance details.
        total_inference_duration_ms: Total time spent on LLM calls in milliseconds.
        total_token_count: Sum of input and output tokens across all sections.
        unverified_references: JSON list of references not found in cross-ref map.
        previous_generation_id: UUID of previous generation (for regeneration tracing).
        generation_timestamp: Timestamp when generation was executed.
        created_at: Server-side UTC timestamp of record creation.
        cross_references: Relationship to associated CrossReferenceEntry records.
    """

    __tablename__ = "generation_provenance"
    __table_args__ = (
        Index("ix_generation_provenance_company", "company_id"),
        Index("ix_generation_provenance_document", "document_id"),
        Index(
            "ix_generation_provenance_generation_id",
            "generation_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id"), nullable=True
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("document_templates.id"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    requesting_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    agent_archetype: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_document_uuids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    reference_document_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    section_provenance: Mapped[list] = mapped_column(JSONB, nullable=False)
    total_inference_duration_ms: Mapped[int] = mapped_column(nullable=False)
    total_token_count: Mapped[int] = mapped_column(nullable=False)
    unverified_references: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    previous_generation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("generation_provenance.generation_id"),
        nullable=True,
    )
    generation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    cross_references: Mapped[list["CrossReferenceEntry"]] = relationship(
        back_populates="provenance", cascade="save-update, merge"
    )


class CrossReferenceEntry(Base):
    """Immutable cross-reference record linking generated content to source documents.

    Stores individual cross-references extracted from reference documents
    and their locations in the generated output. This record is append-only —
    no UPDATE or DELETE operations are permitted.

    Attributes:
        id: Primary key.
        generation_provenance_id: Foreign key to the parent provenance record.
        source_document_id: Foreign key to the referenced source document.
        reference_type: Type of reference ("requirement", "section", "test_case").
        reference_identifier: The extracted identifier (e.g., "REQ-00123").
        reference_text: First 150 chars of the referenced content (nullable).
        location_in_output: JSONB with section_number and paragraph_index.
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of record creation.
        provenance: Back-reference to the parent GenerationProvenance.
    """

    __tablename__ = "cross_reference_entries"
    __table_args__ = (
        Index(
            "ix_cross_ref_provenance_type",
            "generation_provenance_id",
            "reference_type",
        ),
        Index("ix_cross_ref_company", "company_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    generation_provenance_id: Mapped[int] = mapped_column(
        ForeignKey("generation_provenance.id"), nullable=False
    )
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_in_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    provenance: Mapped["GenerationProvenance"] = relationship(
        back_populates="cross_references"
    )


class GenerationJobMetadata(Base, AuditMixin):
    """Tracks async document generation job progress and results.

    Provides job state management for template-based document generation
    tasks, including progress tracking, section completion counts, and
    final result references.

    Attributes:
        id: Primary key.
        job_id: UUID string (unique, indexed) for external reference.
        template_id: Foreign key to the template being used.
        company_id: Foreign key to the owning company (tenant isolation).
        requesting_user_id: Foreign key to the user who requested generation.
        title: Title for the document being generated.
        generation_instructions: User-provided instructions for content generation.
        reference_document_ids: JSON list of reference document IDs.
        output_folder_path: Target folder path for the generated document.
        status: Job status ("processing", "completed", "failed").
        progress_percent: Completion percentage (0-100).
        current_section: Name of the section currently being generated.
        sections_completed: Number of sections successfully generated.
        sections_total: Total number of sections in the template.
        error_message: Error details if job failed.
        result_document_id: Foreign key to the generated document (on completion).
        result_storage_key: MinIO storage key for the generated .docx file.
        file_size_bytes: Size of the generated file in bytes.
        generation_duration_ms: Total generation time in milliseconds.
        started_at: Timestamp when the job started.
        completed_at: Timestamp when the job completed or failed.
        created_at: Server-side UTC timestamp of creation.
        updated_at: Timestamp of last update.
    """

    __tablename__ = "generation_job_metadata"
    __table_args__ = (
        Index("ix_gen_job_company", "company_id"),
        Index("ix_gen_job_job_id", "job_id", unique=True),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_gen_job_progress_range",
        ),
        CheckConstraint(
            "sections_completed <= sections_total",
            name="ck_gen_job_sections_lte_total",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("document_templates.id"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    requesting_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    generation_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    reference_document_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    output_folder_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="processing"
    )
    progress_percent: Mapped[int] = mapped_column(nullable=False, default=0)
    current_section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sections_completed: Mapped[int] = mapped_column(nullable=False, default=0)
    sections_total: Mapped[int] = mapped_column(nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    result_storage_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    generation_duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    content_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending_review"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
