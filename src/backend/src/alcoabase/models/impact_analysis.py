"""Impact analysis models for AI-Driven Change Impact Analysis.

This module defines the database models for Phase 5.5 — AI-Driven Change
Impact Analysis, including:
- DependencyEdge: Directed edges in the document dependency graph (mutable, versioned)
- ImpactReport: Immutable impact analysis report records (append-only)
- GapAnalysisResult: Immutable gap analysis result records (append-only)
- ImpactNotification: Notifications for document owners (mutable, versioned)

ImpactReport and GapAnalysisResult are intentionally immutable (no AuditMixin,
no UPDATE/DELETE) to satisfy GxP audit trail requirements. DependencyEdge and
ImpactNotification use AuditMixin for versioned audit trails via
SQLAlchemy-Continuum.

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class DependencyEdge(Base, AuditMixin):
    """Directed edge in the document dependency graph.

    Represents a dependency relationship between two documents within
    a company scope. Mutable (edges can be updated/pruned during
    incremental builds). AuditMixin enables Continuum versioning.

    Attributes:
        id: Primary key.
        source_document_uuid: UUID of the source document (12-char string).
        target_document_uuid: UUID of the target document (12-char string).
        dependency_type: Type of dependency relationship. Constrained to:
            "validates", "references", "implements", "trains_on", "derived_from".
        confidence_score: Confidence of the detected relationship (0.0 to 1.0).
        detected_references: JSONB array of reference identifiers linking
            the documents (max 500 entries).
        last_verified_at: Timestamp when this edge was last verified.
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of creation.
        updated_at: Timestamp of last update.
    """

    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_document_uuid",
            "target_document_uuid",
            "dependency_type",
            "company_id",
            name="uq_dependency_edge_source_target_type_company",
        ),
        Index(
            "ix_dependency_edge_company_source",
            "company_id",
            "source_document_uuid",
        ),
        Index(
            "ix_dependency_edge_company_target",
            "company_id",
            "target_document_uuid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    target_document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    dependency_type: Mapped[str] = mapped_column(String(50))
    confidence_score: Mapped[float] = mapped_column(Float)
    detected_references: Mapped[dict] = mapped_column(JSONB, default=list)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )


class ImpactReport(Base):
    """Immutable impact analysis report record.

    Append-only. Uses before_update and before_delete event listeners
    to prevent mutation (same pattern as GenerationProvenance).

    Attributes:
        id: Primary key.
        report_id: UUID string uniquely identifying this report.
        triggering_document_uuid: UUID of the document that triggered analysis.
        triggering_version_id: Foreign key to the specific document version.
        change_delta_summary: JSONB containing the ChangeDelta structure.
        affected_items: JSONB array of AffectedItem structures.
        gap_findings: JSONB array of GapFinding structures.
        status: Report status. Constrained to:
            "completed", "partial_success", "failed".
        analysis_timestamp: Timestamp when analysis was executed.
        analysis_duration_ms: Total analysis time in milliseconds.
        agent_archetype_used: Name of the agent archetype used.
        model_used: Name of the AI model used for inference.
        total_token_count: Sum of input and output tokens.
        requesting_user_id: Foreign key to the user who requested analysis
            (nullable if triggered automatically).
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of record creation.
    """

    __tablename__ = "impact_reports"
    __table_args__ = (
        Index(
            "ix_impact_report_company_trigger",
            "company_id",
            "triggering_document_uuid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    triggering_document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    triggering_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id")
    )
    change_delta_summary: Mapped[dict] = mapped_column(JSONB)
    affected_items: Mapped[list] = mapped_column(JSONB, default=list)
    gap_findings: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20))
    analysis_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    analysis_duration_ms: Mapped[int] = mapped_column(Integer)
    agent_archetype_used: Mapped[str] = mapped_column(String(100))
    model_used: Mapped[str] = mapped_column(String(100))
    total_token_count: Mapped[int] = mapped_column(Integer)
    requesting_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GapAnalysisResult(Base):
    """Immutable gap analysis result record.

    Append-only. Uses before_update and before_delete event listeners
    to prevent mutation (same pattern as GenerationProvenance).

    Attributes:
        id: Primary key.
        job_id: Job identifier for tracking (indexed).
        source_document_uuid: UUID of the source document.
        target_document_uuid: UUID of the target document.
        gap_findings: JSONB array of GapFinding structures.
        total_gaps_detected: Total number of gaps found before limiting.
        gaps_retained: Number of gaps retained after severity-based limiting.
        status: Result status. Constrained to:
            "completed", "partial_success", "failed".
        analysis_duration_ms: Total analysis time in milliseconds.
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of record creation.
    """

    __tablename__ = "gap_analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(String(100), index=True)
    source_document_uuid: Mapped[str] = mapped_column(String(12))
    target_document_uuid: Mapped[str] = mapped_column(String(12))
    gap_findings: Mapped[list] = mapped_column(JSONB, default=list)
    total_gaps_detected: Mapped[int] = mapped_column(Integer)
    gaps_retained: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    analysis_duration_ms: Mapped[int] = mapped_column(Integer)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ImpactNotification(Base, AuditMixin):
    """Notification for document owners about impact findings.

    Mutable (can be acknowledged). AuditMixin enables Continuum versioning.

    Attributes:
        id: Primary key.
        report_id: UUID string of the associated impact report.
        affected_document_uuid: UUID of the affected document.
        notification_type: Type of notification. Constrained to: "change_impact".
        impact_severity: Severity of the impact. Constrained to:
            "critical", "major", "minor", "unknown".
        change_summary: Human-readable summary of the change (max 2000 chars).
        target_user_id: Foreign key to the user who should be notified.
        is_acknowledged: Whether the notification has been acknowledged.
        acknowledged_at: Timestamp when acknowledged (nullable).
        acknowledged_by: Foreign key to the user who acknowledged (nullable).
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of creation.
    """

    __tablename__ = "impact_notifications"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "affected_document_uuid",
            "target_user_id",
            name="uq_impact_notification_report_doc_user",
        ),
        Index(
            "ix_impact_notification_user_ack",
            "target_user_id",
            "is_acknowledged",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[str] = mapped_column(String(36), index=True)
    affected_document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    notification_type: Mapped[str] = mapped_column(String(50))
    impact_severity: Mapped[str] = mapped_column(String(20))
    change_summary: Mapped[str] = mapped_column(Text)
    target_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
