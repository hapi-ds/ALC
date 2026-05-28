"""Review pipeline models for multi-agent auditing.

This module defines the database models for the review pipeline orchestration
system. It includes models for review sessions, individual agent reviews,
master review summaries, and action items.

References:
    - Multi-Agent Auditing spec: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/
    - SQLAlchemy-Continuum: https://sqlalchemy-continuum.readthedocs.io/
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class ReviewSession(Base, AuditMixin):
    """Review session tracking a multi-agent document review pipeline execution.

    A review session is created when a document is submitted for multi-agent
    review. It tracks the overall status of the pipeline, from initial
    submission through individual agent reviews to the final master summary.

    Status lifecycle: Pending → InProgress → Completed → Approved/Rejected
                                           → Failed

    Attributes:
        id: Primary key.
        company_id: Foreign key to the owning company (tenant isolation).
        document_id: Foreign key to the document being reviewed.
        document_version_id: Foreign key to the specific document version.
        audit_profile_id: Foreign key to the audit profile used (nullable).
        status: Current pipeline status (Pending/InProgress/Completed/Failed/Approved/Rejected).
        submitted_by: Foreign key to the user who submitted the review.
        submitted_at: Timestamp when the review was submitted.
        completed_at: Timestamp when the review completed (nullable).
        compliance_score: Overall compliance score 0.0–100.0 (nullable).
        summary_failed: Whether the master summary generation failed.
        created_at: Server-side UTC timestamp of creation.
        updated_at: Server-side timestamp updated on every modification.
    """

    __tablename__ = "review_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id")
    )
    audit_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_profiles.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="Pending", index=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    compliance_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    summary_failed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent_reviews: Mapped[list["AgentReview"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    master_summary: Mapped["MasterReviewSummary | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    action_items: Mapped[list["ActionItem"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AgentReview(Base):
    """Individual agent review record within a review session.

    Each agent review represents one auditor agent's independent analysis
    of the document. The report_data stores the full structured ReviewReport
    as JSONB for flexible querying.

    Attributes:
        id: Primary key.
        session_id: Foreign key to the parent ReviewSession.
        agent_definition_id: Foreign key to the agent that performed the review.
        status: Review status (Pending/InProgress/Completed/Failed).
        report_data: Full ReviewReport stored as JSONB (nullable until completed).
        error_reason: Reason for failure if status is Failed (nullable).
        inference_duration_ms: Wall-clock inference time in milliseconds (nullable).
        started_at: Timestamp when the agent review started (nullable).
        completed_at: Timestamp when the agent review completed (nullable).
        created_at: Server-side UTC timestamp of creation.
    """

    __tablename__ = "agent_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("review_sessions.id"), index=True
    )
    agent_definition_id: Mapped[int] = mapped_column(
        ForeignKey("agent_definitions.id")
    )
    status: Mapped[str] = mapped_column(String(50), default="Pending")
    report_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    error_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    inference_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    session: Mapped["ReviewSession"] = relationship(
        back_populates="agent_reviews"
    )


class MasterReviewSummary(Base):
    """Master auditor summary synthesizing all individual agent reviews.

    The master summary is produced by the supervisory Master Auditor agent
    after all individual reviews complete (or quorum is met). It contains
    consensus findings, contradictions, prioritized action items, and an
    overall compliance score.

    Attributes:
        id: Primary key.
        session_id: Foreign key to the parent ReviewSession (unique constraint).
        summary_data: Full MasterReviewSummary stored as JSONB.
        compliance_score: Computed compliance score 0.0–100.0.
        risk_assessment: Risk band classification (Critical/High/Medium/Low).
        created_at: Server-side UTC timestamp of creation.
    """

    __tablename__ = "master_review_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("review_sessions.id"), unique=True
    )
    summary_data: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    compliance_score: Mapped[float] = mapped_column(Float)
    risk_assessment: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    session: Mapped["ReviewSession"] = relationship(
        back_populates="master_summary"
    )


class ActionItem(Base, AuditMixin):
    """Action item generated from review findings.

    Action items track remediation work identified during the review process.
    They can be assigned to users and tracked through resolution.

    Status lifecycle: Open → InProgress → Resolved/Dismissed
                      InProgress → Open (reopen)

    Attributes:
        id: Primary key.
        session_id: Foreign key to the parent ReviewSession.
        finding_id: Identifier linking to the specific finding in the report.
        title: Short description of the action item (max 500 chars).
        description: Detailed description of what needs to be done.
        severity: Finding severity (Critical/Major/Minor/Informational).
        status: Current status (Open/InProgress/Resolved/Dismissed).
        assigned_to: Foreign key to the assigned user (nullable).
        resolved_at: Timestamp when the item was resolved (nullable).
        resolution_note: Notes on how the item was resolved (nullable).
        created_at: Server-side UTC timestamp of creation.
        updated_at: Server-side timestamp updated on every modification.
    """

    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("review_sessions.id"), index=True
    )
    finding_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="Open")
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    session: Mapped["ReviewSession"] = relationship(
        back_populates="action_items"
    )
