"""Pydantic request/response schemas for AI document generation endpoints.

Provides validated schemas for template registration, template-based document
generation, generation job status tracking, provenance retrieval, cross-reference
viewing, and generated document review operations.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 1.1, 1.13, 2.1, 2.13, 6.2, 6.10
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Request Schemas ---


class TemplateRegisterRequest(BaseModel):
    """Request schema for registering a .docx file as a Master Template.

    Attributes:
        document_id: ID of the source document in the system.
        document_version_id: ID of the specific document version to use as template.
        template_name: Human-readable name for the template (1-500 chars).
        document_type_target: Target document type (e.g., "URS", "MVP", "SOP").
    """

    document_id: int
    document_version_id: int
    template_name: str = Field(min_length=1, max_length=500)
    document_type_target: str = Field(min_length=1, max_length=100)


class GenerateFromTemplateRequest(BaseModel):
    """Request schema for starting a template-based document generation job.

    Attributes:
        template_id: ID of the registered template to use.
        title: Title for the generated document (1-500 chars).
        generation_instructions: Instructions guiding content generation (1-10000 chars).
        reference_document_ids: Optional list of document IDs to use as primary sources.
        output_folder_path: Target folder path for the generated document (1-1000 chars).
    """

    template_id: int
    title: str = Field(min_length=1, max_length=500)
    generation_instructions: str = Field(min_length=1, max_length=10000)
    reference_document_ids: list[int] | None = Field(default=None, max_length=20)
    output_folder_path: str = Field(min_length=1, max_length=1000)


class DocumentReviewRequest(BaseModel):
    """Request schema for approving or rejecting an AI-generated document.

    Attributes:
        action: Review action — either "approve" or "reject".
        reviewer_comments: Optional reviewer comments (max 2000 chars).
    """

    action: Literal["approve", "reject"]
    reviewer_comments: str | None = Field(default=None, max_length=2000)


# --- Response Schemas ---


class JobAcceptedResponse(BaseModel):
    """Response returned when an async job is accepted (HTTP 202).

    Attributes:
        job_id: UUID of the created job for status polling.
        status: Initial job status (always "pending").
    """

    job_id: str
    status: str = "pending"


class TemplateResponse(BaseModel):
    """Response schema for a registered template.

    Attributes:
        id: Template primary key.
        document_id: Source document ID.
        document_version_id: Source document version ID.
        template_name: Human-readable template name.
        document_type_target: Target document type.
        status: Template status ("pending", "active", "archived").
        registered_by: ID of the user who registered the template.
        registered_at: Registration timestamp.
        template_analysis: Full structural analysis (included on detail endpoint).
    """

    id: int
    document_id: int
    document_version_id: int
    template_name: str
    document_type_target: str
    status: str
    registered_by: int
    registered_at: datetime
    template_analysis: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    """Paginated list of registered templates.

    Attributes:
        items: List of template responses.
        total: Total number of matching templates.
    """

    items: list[TemplateResponse]
    total: int


class GenerationJobStatusResponse(BaseModel):
    """Response schema for generation job status polling.

    Attributes:
        job_id: UUID of the generation job.
        status: Current status ("processing", "completed", "failed").
        progress_percent: Completion percentage (0-100).
        current_section: Name of section currently being generated.
        sections_completed: Number of sections successfully generated.
        sections_total: Total number of sections in the template.
        estimated_time_remaining_seconds: Estimated seconds until completion.
        error_message: Error details if job failed.
        result_document_id: Generated document ID (populated on completion).
        result_document_uuid: Generated document UUID (populated on completion).
        result_storage_key: MinIO storage key (populated on completion).
        file_size_bytes: Generated file size (populated on completion).
        generation_duration_ms: Total generation time (populated on completion).
    """

    job_id: str
    status: str
    progress_percent: int
    current_section: str | None
    sections_completed: int
    sections_total: int
    estimated_time_remaining_seconds: int | None
    error_message: str | None
    result_document_id: int | None = None
    result_document_uuid: str | None = None
    result_storage_key: str | None = None
    file_size_bytes: int | None = None
    generation_duration_ms: int | None = None

    model_config = {"from_attributes": True}


class ProvenanceResponse(BaseModel):
    """Response schema for generation provenance (audit trail).

    Attributes:
        generation_id: UUID uniquely identifying this generation event.
        template_id: ID of the template used.
        template_document_uuid: UUID of the template source document.
        source_document_uuids: UUIDs of all KB documents used as sources.
        reference_document_ids: Explicitly provided reference document IDs.
        agent_archetype: Agent archetype used for generation.
        generation_parameters: Generation config (temperature, max_tokens, etc.).
        requesting_user_id: ID of the user who requested generation.
        total_inference_duration_ms: Total LLM call time in milliseconds.
        total_token_count: Sum of input and output tokens.
        section_provenance: Per-section provenance details.
        unverified_references: References not found in cross-reference map.
        generation_timestamp: When generation was executed.
        previous_generation_id: UUID of previous generation (for regeneration tracing).
    """

    generation_id: str
    template_id: int
    template_document_uuid: str
    source_document_uuids: list[str]
    reference_document_ids: list[int]
    agent_archetype: str
    generation_parameters: dict[str, Any]
    requesting_user_id: int
    total_inference_duration_ms: int
    total_token_count: int
    section_provenance: list[dict[str, Any]]
    unverified_references: list[dict[str, Any]]
    generation_timestamp: datetime
    previous_generation_id: str | None = None

    model_config = {"from_attributes": True}


class CrossReferenceResponse(BaseModel):
    """Response schema for a single cross-reference entry.

    Attributes:
        source_document_id: ID of the referenced source document.
        source_document_title: Title of the referenced source document.
        reference_type: Type of reference ("requirement", "section", "test_case").
        reference_identifier: The extracted identifier (e.g., "REQ-00123").
        reference_text: First 150 chars of the referenced content.
        location_in_output: Location in the generated document.
    """

    source_document_id: int
    source_document_title: str
    reference_type: str
    reference_identifier: str
    reference_text: str | None
    location_in_output: dict[str, Any]

    model_config = {"from_attributes": True}


class CrossReferenceListResponse(BaseModel):
    """Paginated list of cross-reference entries.

    Attributes:
        items: List of cross-reference responses.
        total: Total number of cross-references.
    """

    items: list[CrossReferenceResponse]
    total: int


class DocumentReviewResponse(BaseModel):
    """Response schema for a document review action.

    Attributes:
        document_id: ID of the reviewed document.
        current_status: Updated workflow status.
        content_status: Updated content review status.
    """

    document_id: int
    current_status: str
    content_status: str


class GeneratedDocumentResponse(BaseModel):
    """Response schema for an AI-generated document in listing views.

    Attributes:
        id: Document primary key.
        document_uuid: Unique document identifier.
        title: Document title.
        document_type: Document classification type.
        current_status: Current workflow status.
        content_status: Content review status.
        template_name: Name of the template used for generation.
        generated_at: Timestamp when the document was generated.
        generation_duration_ms: Total generation time in milliseconds.
    """

    id: int
    document_uuid: str
    title: str
    document_type: str
    current_status: str
    content_status: str
    template_name: str
    generated_at: datetime
    generation_duration_ms: int | None

    model_config = {"from_attributes": True}


class GeneratedDocumentListResponse(BaseModel):
    """Paginated list of AI-generated documents.

    Attributes:
        items: List of generated document responses.
        total: Total number of matching generated documents.
    """

    items: list[GeneratedDocumentResponse]
    total: int
