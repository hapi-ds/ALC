"""Video alignment models for multimodal knowledge base.

This module defines SQLAlchemy ORM models for the Video-to-SOP alignment
feature, including video metadata, extracted step sequences, SOP link
associations, discrepancy reports, and async processing job tracking.

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md
    - Requirements: 4.3, 5.4, 6.6, 8.1, 9.5, 10.6
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class VideoMetadata(Base):
    """Video-specific metadata stored alongside the Document record.

    Stores technical metadata extracted via ffprobe when a training video
    is uploaded. Fields are nullable to handle cases where ffprobe fails.

    Attributes:
        id: Primary key.
        document_id: Foreign key to documents.id (unique, one metadata per document).
        duration_seconds: Video duration in seconds.
        resolution_width: Video width in pixels.
        resolution_height: Video height in pixels.
        frame_count: Total number of frames in the video.
        codec: Video codec identifier (e.g., "h264").
        created_at: Server-side UTC timestamp of record creation.
    """

    __tablename__ = "video_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), unique=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    resolution_width: Mapped[int | None] = mapped_column(nullable=True)
    resolution_height: Mapped[int | None] = mapped_column(nullable=True)
    frame_count: Mapped[int | None] = mapped_column(nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VideoStepSequence(Base):
    """A single step in the extracted Step_Sequence for a video.

    Represents one procedural step identified from video frame analysis,
    with timestamp range, description, and optional audio transcript.

    Attributes:
        id: Primary key.
        document_id: Foreign key to documents.id (indexed for lookups).
        step_index: Zero-based index of this step in the sequence.
        start_timestamp: Start time in seconds within the video.
        end_timestamp: End time in seconds within the video.
        description: Textual description of the observed action.
        frame_indices: JSON array of frame indices belonging to this step.
        confidence: Confidence score (0.0-1.0), default 1.0.
        audio_transcript: Optional merged audio transcript for this step.
        created_at: Server-side UTC timestamp of record creation.
    """

    __tablename__ = "video_step_sequences"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    step_index: Mapped[int] = mapped_column()
    start_timestamp: Mapped[float] = mapped_column()
    end_timestamp: Mapped[float] = mapped_column()
    description: Mapped[str] = mapped_column(Text)
    frame_indices: Mapped[str] = mapped_column(Text)  # JSON array
    confidence: Mapped[float] = mapped_column(default=1.0)
    audio_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VideoSOPLink(Base):
    """Links a Video_Document to an SOP document for alignment.

    Tracks which SOP documents are associated with a video for
    step comparison. Maximum 10 SOPs per video enforced at service level.

    Attributes:
        id: Primary key.
        video_document_id: Foreign key to documents.id (the video).
        sop_document_id: Foreign key to documents.id (the SOP).
        sop_version: Version string of the SOP at time of linking.
        linked_at: Server-side UTC timestamp of link creation.
        linked_by: Foreign key to users.id who created the link.
        company_id: Foreign key to companies.id for tenant scoping.
    """

    __tablename__ = "video_sop_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    sop_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    sop_version: Mapped[str] = mapped_column(String(20))
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    linked_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    __table_args__ = (
        UniqueConstraint(
            "video_document_id", "sop_document_id", name="uq_video_sop_link"
        ),
    )


class DiscrepancyReport(Base):
    """Stored discrepancy report from video-to-SOP alignment.

    Contains the full alignment analysis results including matched,
    missing, extra steps and order mismatches with severity ratings.

    Attributes:
        id: Primary key.
        video_document_id: Foreign key to documents.id (the video).
        sop_document_id: Foreign key to documents.id (the SOP).
        alignment_score: Overall alignment score (0.0-1.0).
        total_video_steps: Number of steps extracted from video.
        total_sop_steps: Number of steps extracted from SOP.
        matched_steps: JSON array of matched step pairs.
        missing_steps: JSON array of steps in video but not SOP.
        extra_steps: JSON array of steps in SOP but not video.
        order_mismatches: JSON array of steps matched but in wrong order.
        requires_review: Flag set when alignment_score < 0.5.
        generated_at: Server-side UTC timestamp of report generation.
        generated_by: Foreign key to users.id who triggered alignment.
        company_id: Foreign key to companies.id for tenant scoping.
    """

    __tablename__ = "discrepancy_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    sop_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    alignment_score: Mapped[float] = mapped_column()
    total_video_steps: Mapped[int] = mapped_column()
    total_sop_steps: Mapped[int] = mapped_column()
    matched_steps: Mapped[str] = mapped_column(Text)  # JSON
    missing_steps: Mapped[str] = mapped_column(Text)  # JSON
    extra_steps: Mapped[str] = mapped_column(Text)  # JSON
    order_mismatches: Mapped[str] = mapped_column(Text)  # JSON
    requires_review: Mapped[bool] = mapped_column(default=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    generated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))


class ProcessingJob(Base):
    """Tracks async processing jobs for video operations.

    Provides job state management for long-running operations like
    frame extraction, frame analysis, audio transcription, and alignment.

    Attributes:
        id: Primary key.
        job_id: UUID string (unique, indexed) for external reference.
        document_id: Foreign key to documents.id being processed.
        operation: Operation type (extract_frames, analyze_frames, etc.).
        status: Current status (processing, completed, failed).
        progress_percent: Completion percentage (0-100).
        estimated_duration_seconds: Estimated total duration in seconds.
        result_reference: Optional reference to result data location.
        error_message: Error details if job failed.
        started_at: Server-side UTC timestamp of job start.
        completed_at: Timestamp when job completed or failed.
        company_id: Foreign key to companies.id for tenant scoping.
    """

    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    operation: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    progress_percent: Mapped[int] = mapped_column(default=0)
    estimated_duration_seconds: Mapped[int] = mapped_column(default=0)
    result_reference: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
