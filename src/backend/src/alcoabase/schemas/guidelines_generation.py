"""Pydantic schemas for AI regulatory guidelines generation reports and errors.

Provides validated response schemas for the GuidelinesGeneratorService,
including per-document report entries, the complete generation report,
and the error response.

References:
    - Design doc: GuidelinesGenerationReport Schema, Error Handling
    - Requirements 5.4, 6.5
"""

from pydantic import BaseModel


class DocumentReportEntry(BaseModel):
    """Report entry for a single generated guideline document.

    Attributes:
        document_id: ID of the created/versioned Document record.
        document_uuid: Document UUID in YYYY-NNNNN format.
        title: Title of the guideline document.
        sector: Sector identifier (cross-sector, pharma_gmp,
            medtech_iso13485, or ivd_ivdr).
        version_number: Major version number of the document.
        tags_applied: List of tags applied to the document.
        workflow_state: Current workflow state after generation.
        is_new_document: True if a new document was created, False if versioned.
        policy_section_count: Number of policy sections in this document.
    """

    document_id: int
    document_uuid: str
    title: str
    sector: str
    version_number: int
    tags_applied: list[str]
    workflow_state: str
    is_new_document: bool
    policy_section_count: int


class GuidelinesGenerationReport(BaseModel):
    """Complete report of AI guidelines generation and upload.

    Attributes:
        documents_created: List of report entries for each generated document.
        total_documents: Total number of guideline documents generated.
        total_policy_sections: Sum of policy sections across all documents.
        risk_tiers_referenced: List of risk tier levels used in generation.
        regulatory_frameworks_covered: List of framework identifiers referenced.
        total_duration_ms: Total execution time in milliseconds.
    """

    documents_created: list[DocumentReportEntry]
    total_documents: int
    total_policy_sections: int
    risk_tiers_referenced: list[str]
    regulatory_frameworks_covered: list[str]
    total_duration_ms: int


class GuidelinesGenerationError(BaseModel):
    """Error response when guidelines generation fails.

    Attributes:
        error: Human-readable error message.
        failed_operation: Operation that failed (prerequisite_check,
            risk_data_load, content_generation, document_upload,
            tag_application, or workflow_assignment).
        document_title: Title of the document that caused the failure,
            if applicable.
        detail: Additional context about the failure.
    """

    error: str
    failed_operation: str
    document_title: str | None = None
    detail: str | None = None
