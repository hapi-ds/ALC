"""Traceability models for AI-Powered Traceability & Gap Discovery.

This module defines the database models for Phase 5.6 — AI-Powered
Traceability & Gap Discovery, including:
- TraceabilityMatrix: Immutable traceability matrix records (append-only,
  soft-delete via deleted_at is the only permitted mutation)
- CoverageSnapshot: Immutable coverage snapshot records (fully append-only)
- TraceabilityAlert: Mutable alert records (versioned via AuditMixin)
- StaleLinkMarker: Mutable stale link markers (versioned via AuditMixin)

TraceabilityMatrix and CoverageSnapshot are intentionally immutable to satisfy
GxP audit trail requirements. TraceabilityMatrix permits only soft-delete
(setting deleted_at). CoverageSnapshot permits no mutations at all.
TraceabilityAlert and StaleLinkMarker use AuditMixin for versioned audit
trails via SQLAlchemy-Continuum.

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
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


class TraceabilityMatrix(Base):
    """Immutable traceability matrix record.

    Append-only with soft-delete support. Uses before_update event listener
    that permits UPDATE only on the deleted_at column and raises
    ImmutableRecordError on any other column mutation. before_delete raises
    ImmutableRecordError unconditionally.

    Attributes:
        id: Primary key.
        matrix_id: UUID string uniquely identifying this matrix.
        matrix_name: Human-readable name for the matrix (max 200 chars).
        description: Optional description (max 1000 chars).
        source_document_uuids: JSONB array of source document UUID strings.
        target_document_uuids: JSONB array of target document UUID strings.
        source_document_versions: JSONB array of {document_uuid, version_id}.
        target_document_versions: JSONB array of {document_uuid, version_id}.
        traceability_links: JSONB array of TraceabilityLink structures.
        orphan_requirements: JSONB array of OrphanRequirement structures.
        orphan_test_cases: JSONB array of OrphanTestCase structures.
        coverage_metrics: JSONB CoverageMetric structure.
        status: Matrix status. Constrained to:
            "completed", "partial_success", "failed".
        parent_matrix_id: UUID referencing previous matrix for same doc set.
        generation_timestamp: Timestamp when generation was executed.
        generation_duration_ms: Total generation time in milliseconds.
        agent_archetype_used: Name of the agent archetype used.
        model_used: Name of the AI model used for inference.
        total_token_count: Sum of input and output tokens.
        requesting_user_id: Foreign key to the user who requested generation.
        company_id: Foreign key to the owning company (tenant isolation).
        deleted_at: Soft-delete timestamp (only permitted mutation).
        created_at: Server-side UTC timestamp of record creation.
    """

    __tablename__ = "traceability_matrices"
    __table_args__ = (
        Index(
            "ix_traceability_matrix_company_timestamp",
            "company_id",
            "generation_timestamp",
        ),
        Index(
            "ix_traceability_matrix_company_deleted",
            "company_id",
            "deleted_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    matrix_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_uuids: Mapped[list] = mapped_column(JSONB)
    target_document_uuids: Mapped[list] = mapped_column(JSONB)
    source_document_versions: Mapped[list] = mapped_column(JSONB)
    target_document_versions: Mapped[list] = mapped_column(JSONB)
    traceability_links: Mapped[list] = mapped_column(JSONB, default=list)
    orphan_requirements: Mapped[list] = mapped_column(JSONB, default=list)
    orphan_test_cases: Mapped[list] = mapped_column(JSONB, default=list)
    coverage_metrics: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    parent_matrix_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    generation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )
    generation_duration_ms: Mapped[int] = mapped_column(Integer)
    agent_archetype_used: Mapped[str] = mapped_column(String(100))
    model_used: Mapped[str] = mapped_column(String(100))
    total_token_count: Mapped[int] = mapped_column(Integer)
    requesting_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CoverageSnapshot(Base):
    """Immutable coverage snapshot for trend analysis.

    Fully append-only. Uses before_update and before_delete event listeners
    to raise ImmutableRecordError on any attempted mutation.

    Attributes:
        id: Primary key.
        matrix_id: UUID string referencing TraceabilityMatrix.matrix_id.
        source_document_uuid: UUID of the source document (12-char string).
        coverage_percentage: Coverage percentage (0.0 to 100.0).
        orphan_requirements_count: Number of orphan requirements.
        orphan_test_cases_count: Number of orphan test cases.
        compliance_readiness_score: Compliance score (0.0 to 100.0).
        total_requirements: Total requirements extracted.
        covered_requirements: Requirements with at least one link >= 0.5.
        total_test_cases: Total test cases extracted.
        linked_test_cases: Test cases with at least one link.
        snapshot_date: Timestamp of the snapshot.
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of record creation.
    """

    __tablename__ = "coverage_snapshots"
    __table_args__ = (
        Index(
            "ix_coverage_snapshot_company_doc_date",
            "company_id",
            "source_document_uuid",
            "snapshot_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_id: Mapped[str] = mapped_column(String(36), index=True)
    source_document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    coverage_percentage: Mapped[float] = mapped_column(Float)
    orphan_requirements_count: Mapped[int] = mapped_column(Integer)
    orphan_test_cases_count: Mapped[int] = mapped_column(Integer)
    compliance_readiness_score: Mapped[float] = mapped_column(Float)
    total_requirements: Mapped[int] = mapped_column(Integer)
    covered_requirements: Mapped[int] = mapped_column(Integer)
    total_test_cases: Mapped[int] = mapped_column(Integer)
    linked_test_cases: Mapped[int] = mapped_column(Integer)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TraceabilityAlert(Base, AuditMixin):
    """Alert created when an impact report affects a traceability matrix source.

    Mutable (can be resolved). AuditMixin enables Continuum versioning.

    Attributes:
        id: Primary key.
        alert_id: UUID string uniquely identifying this alert.
        triggering_report_id: UUID string referencing ImpactReport.report_id.
        affected_matrix_ids: JSONB array of matrix_id UUIDs.
        affected_link_count: Number of traceability links affected.
        alert_severity: Severity level. Constrained to:
            "critical", "major", "minor".
        is_resolved: Whether the alert has been resolved.
        resolved_at: Timestamp when resolved (nullable).
        resolved_by: Foreign key to the user who resolved (nullable).
        resolution_action: Action taken to resolve. Constrained to:
            "matrix_regenerated", "links_verified", "no_action_needed".
        resolution_note: Free-text resolution note (max 500 chars).
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of creation.
    """

    __tablename__ = "traceability_alerts"
    __table_args__ = (
        UniqueConstraint(
            "triggering_report_id",
            "company_id",
            name="uq_traceability_alert_report_company",
        ),
        Index(
            "ix_traceability_alert_company_resolved",
            "company_id",
            "is_resolved",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    triggering_report_id: Mapped[str] = mapped_column(String(36), index=True)
    affected_matrix_ids: Mapped[list] = mapped_column(JSONB)
    affected_link_count: Mapped[int] = mapped_column(Integer)
    alert_severity: Mapped[str] = mapped_column(String(20))
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    resolution_action: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StaleLinkMarker(Base, AuditMixin):
    """Tracks stale traceability links when requirements change.

    Mutable (can be cleared on alert resolution). AuditMixin enables
    Continuum versioning.

    Attributes:
        id: Primary key.
        matrix_id: UUID string referencing TraceabilityMatrix.matrix_id.
        requirement_id: Extracted requirement identifier (e.g., "REQ-001").
        stale_since: Timestamp when the link became stale.
        stale_reason: Explanation of why the link is stale (max 500 chars).
        triggering_report_id: UUID string referencing ImpactReport.report_id.
        is_cleared: Whether the stale marker has been cleared.
        cleared_at: Timestamp when cleared (nullable).
        company_id: Foreign key to the owning company (tenant isolation).
        created_at: Server-side UTC timestamp of creation.
    """

    __tablename__ = "stale_link_markers"
    __table_args__ = (
        UniqueConstraint(
            "matrix_id",
            "requirement_id",
            "triggering_report_id",
            name="uq_stale_link_marker_matrix_req_report",
        ),
        Index(
            "ix_stale_link_marker_matrix_cleared",
            "matrix_id",
            "is_cleared",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    matrix_id: Mapped[str] = mapped_column(String(36), index=True)
    requirement_id: Mapped[str] = mapped_column(String(100))
    stale_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stale_reason: Mapped[str] = mapped_column(Text)
    triggering_report_id: Mapped[str] = mapped_column(String(36))
    is_cleared: Mapped[bool] = mapped_column(Boolean, default=False)
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
