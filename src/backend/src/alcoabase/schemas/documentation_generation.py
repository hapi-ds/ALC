"""Pydantic schemas for documentation suite generation reports and errors.

Provides validated response schemas for the DocumentationGeneratorService,
including per-document report entries, cross-reference summaries, the
complete generation report, and the error response.

References:
    - Design doc: DocumentationGenerationReport Schema, Error Handling
    - Requirements 4.4, 4.5
"""

from pydantic import BaseModel


class DocumentReportEntry(BaseModel):
    """Report entry for a single generated guide document.

    Attributes:
        document_id: ID of the created/versioned Document record.
        document_uuid: Document UUID in YYYY-NNNNN format.
        title: Title of the guide document.
        guide_type: Guide identifier ("user_guide" or "admin_guide").
        version_number: Major version number of the document.
        tags_applied: List of tags applied to the document.
        workflow_state: Current workflow state after generation.
        is_new_document: True if a new document was created, False if versioned.
        section_count: Number of level-2 sections in this document.
        procedure_count: Number of Procedure_Blocks in this document.
        screenshot_placeholder_count: Number of screenshot placeholders in this document.
    """

    document_id: int
    document_uuid: str
    title: str
    guide_type: str
    version_number: int
    tags_applied: list[str]
    workflow_state: str
    is_new_document: bool
    section_count: int
    procedure_count: int
    screenshot_placeholder_count: int


class CrossReferenceSummary(BaseModel):
    """Summary of cross-references included in generated guides.

    Attributes:
        urs_references: Whether URS cross-references were included.
        ai_guidelines_references: Whether AI Guidelines cross-references were included.
    """

    urs_references: bool
    ai_guidelines_references: bool


class DocumentationGenerationReport(BaseModel):
    """Complete report of documentation suite generation and upload.

    Attributes:
        documents_created: List of report entries for each generated guide.
        total_documents: Total number of guide documents generated (always 2).
        total_sections: Sum of sections across both guides.
        total_procedures: Sum of Procedure_Blocks across both guides.
        cross_references_included: Summary of which cross-references were included.
        total_duration_ms: Total execution time in milliseconds.
    """

    documents_created: list[DocumentReportEntry]
    total_documents: int
    total_sections: int
    total_procedures: int
    cross_references_included: CrossReferenceSummary
    total_duration_ms: int


class DocumentationGenerationError(BaseModel):
    """Error response when documentation generation fails.

    Attributes:
        error: Human-readable error message.
        failed_operation: Operation that failed (prerequisite_check,
            cross_reference_load, content_generation, document_upload,
            tag_application, or workflow_assignment).
        document_title: Title of the document that caused the failure,
            if applicable.
        detail: Additional context about the failure.
    """

    error: str
    failed_operation: str
    document_title: str | None = None
    detail: str | None = None
