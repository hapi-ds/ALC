"""Pydantic schemas for URS generation reports and errors.

Provides validated response schemas for the URSGeneratorService,
including the complete generation report and error response.

References:
    - Design doc: URSGenerationReport Schema, Error Handling
    - Requirements 6.4, 7.5
"""

from pydantic import BaseModel


class URSGenerationReport(BaseModel):
    """Complete report of URS generation and upload.

    Attributes:
        document_id: ID of the created/versioned Document record.
        document_uuid: Document UUID in YYYY-NNNNN format.
        document_title: Title of the URS document.
        version_number: Major version number of the document.
        tags_applied: List of tags applied to the document.
        workflow_state: Current workflow state after generation.
        requirement_count: Total number of distinct requirements generated.
        module_count: Number of requirement modules in the URS.
        is_new_document: True if a new document was created, False if versioned.
        total_duration_ms: Total execution time in milliseconds.
    """

    document_id: int
    document_uuid: str
    document_title: str
    version_number: int
    tags_applied: list[str]
    workflow_state: str
    requirement_count: int
    module_count: int
    is_new_document: bool
    total_duration_ms: int


class URSGenerationError(BaseModel):
    """Error response when URS generation fails.

    Attributes:
        error: Human-readable error message.
        failed_step: Step name that failed (content_generation,
            document_upload, tag_application, or workflow_assignment).
        detail: Additional context about the failure.
    """

    error: str
    failed_step: str
    detail: str | None = None
