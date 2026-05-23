"""Pydantic request/response schemas for video alignment endpoints.

Provides validated schemas for SOP linking, async job tracking,
discrepancy reporting, and visual indexing results.

References:
    - Design doc Section 6: Video Alignment Router
    - Requirements 10.3, 10.5, 10.6, 10.7
"""

from datetime import datetime

from pydantic import BaseModel, Field


# --- Video Alignment Request Schemas ---


class LinkSOPRequest(BaseModel):
    """Request to link an SOP document to a video.

    Attributes:
        sop_document_uuid: UUID of the SOP document to link.
        sop_version: Specific version to link, defaults to latest if None.
    """

    sop_document_uuid: str = Field(..., description="UUID of the SOP document")
    sop_version: str | None = Field(
        None, description="Specific version, defaults to latest"
    )


# --- Video Alignment Response Schemas ---


class SOPLinkResponse(BaseModel):
    """Response after successfully linking an SOP.

    Attributes:
        video_document_uuid: UUID of the video document.
        sop_document_uuid: UUID of the linked SOP document.
        sop_version: Version of the SOP that was linked.
        linked_at: Timestamp when the link was created.
    """

    video_document_uuid: str
    sop_document_uuid: str
    sop_version: str
    linked_at: datetime


class JobStatusResponse(BaseModel):
    """Response for async job creation (HTTP 202).

    Returned when a long-running operation is accepted for processing.

    Attributes:
        job_id: Unique identifier for the processing job.
        status: Current job status, defaults to "processing".
        estimated_duration_seconds: Estimated time to completion in seconds.
    """

    job_id: str
    status: str = "processing"
    estimated_duration_seconds: int


class JobStatusDetailResponse(BaseModel):
    """Detailed job status for polling.

    Provides full status information for tracking async operations.

    Attributes:
        job_id: Unique identifier for the processing job.
        status: Current status (processing, completed, failed).
        started_at: Timestamp when the job started.
        completed_at: Timestamp when the job completed, if finished.
        progress_percent: Current progress percentage (0-100).
        result_reference: Reference to the result resource, if completed.
        error_message: Error description, if failed.
    """

    job_id: str
    status: str  # processing, completed, failed
    started_at: datetime
    completed_at: datetime | None = None
    progress_percent: int = 0
    result_reference: str | None = None
    error_message: str | None = None


class MatchedStepResponse(BaseModel):
    """A matched step in the discrepancy report.

    Represents a video step that was successfully matched to an SOP step.

    Attributes:
        video_step_description: Description of the video step.
        sop_step_text: Text of the matched SOP step.
        similarity_score: Cosine similarity score between the steps.
        video_timestamp_start: Start timestamp in the video (seconds).
        video_timestamp_end: End timestamp in the video (seconds).
    """

    video_step_description: str
    sop_step_text: str
    similarity_score: float
    video_timestamp_start: float
    video_timestamp_end: float


class DiscrepancyStepResponse(BaseModel):
    """A missing or extra step in the discrepancy report.

    Represents a step present in one source but not the other.

    Attributes:
        step_description: Description of the discrepant step.
        source: Origin of the step ("video" or "sop").
        severity: Severity rating (critical, major, minor).
        recommendation: Suggested corrective action.
    """

    step_description: str
    source: str  # "video" or "sop"
    severity: str  # critical, major, minor
    recommendation: str


class OrderMismatchResponse(BaseModel):
    """An order mismatch in the discrepancy report.

    Represents steps that matched but appear in different sequence positions.

    Attributes:
        video_step_description: Description of the video step.
        sop_step_text: Text of the matched SOP step.
        video_position: Position index in the video step sequence.
        sop_position: Position index in the SOP step list.
        severity: Severity rating for the ordering discrepancy.
    """

    video_step_description: str
    sop_step_text: str
    video_position: int
    sop_position: int
    severity: str


class DiscrepancyReportResponse(BaseModel):
    """Full discrepancy report response.

    Contains the complete alignment analysis between a video and linked SOP.

    Attributes:
        alignment_score: Overall alignment score (0.0 to 1.0).
        matched_steps: Steps successfully matched between video and SOP.
        missing_steps: Steps in video but not found in SOP.
        extra_steps: Steps in SOP but not observed in video.
        order_mismatches: Steps matched but in different order.
        total_video_steps: Total number of steps extracted from video.
        total_sop_steps: Total number of steps extracted from SOP.
        generated_at: Timestamp when the report was generated.
        requires_review: Whether the report requires manual review.
    """

    alignment_score: float = Field(..., ge=0.0, le=1.0)
    matched_steps: list[MatchedStepResponse]
    missing_steps: list[DiscrepancyStepResponse]
    extra_steps: list[DiscrepancyStepResponse]
    order_mismatches: list[OrderMismatchResponse]
    total_video_steps: int
    total_sop_steps: int
    generated_at: datetime
    requires_review: bool


# --- Visual Content Indexing Schemas ---


class IndexingResult(BaseModel):
    """Result of document indexing with visual content.

    Extends the standard indexing result with visual processing fields.

    Attributes:
        document_uuid: UUID of the indexed document.
        version: Document version that was indexed.
        text_chunks_count: Number of text chunks created.
        visual_chunks_count: Number of visual chunks created.
        visual_indexing_status: Status of visual indexing
            (not_applicable, pending, completed, partial).
        visual_pages_detected: Number of pages detected as visual content.
        visual_pages_processed: Number of visual pages successfully processed.
        indexing_duration_ms: Total indexing duration in milliseconds.
    """

    document_uuid: str
    version: str
    text_chunks_count: int
    visual_chunks_count: int
    visual_indexing_status: str  # not_applicable, pending, completed, partial
    visual_pages_detected: int
    visual_pages_processed: int
    indexing_duration_ms: int


# --- Extended Source Citation ---


class VisualSourceCitationResponse(BaseModel):
    """Source citation with visual content metadata.

    Extends the standard citation with visual-specific fields for
    rendering visual content indicators in the frontend.

    Attributes:
        document_uuid: UUID of the source document.
        title: Document title.
        version: Document version.
        page_or_section: Page number or section reference.
        content_type: Type of content ("text" or "visual").
        visual_type: Classification of visual content, if applicable.
    """

    document_uuid: str
    title: str
    version: str
    page_or_section: str
    content_type: str = "text"  # "text" or "visual"
    visual_type: str | None = None  # flowchart, diagram, chart, mixed
