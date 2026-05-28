"""Anomaly alert model for audit trail anomaly detection.

This module defines the AnomalyAlert model that stores detected anomalies
from periodic audit trail scanning. Anomalies include backdated signatures,
workflow bypasses, bulk approvals, off-hours mutations, and rapid version churn.

References:
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
    - 21 CFR Part 11: FDA regulation for electronic records and signatures
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class AnomalyAlert(Base):
    """Record of a detected anomaly in the audit trail.

    Each alert represents a suspicious pattern identified during periodic
    scanning of the audit trail. Alerts are deduplicated by a unique
    constraint on (anomaly_type, affected_document_id, affected_user_id,
    detected_at date) to prevent duplicate alerts for the same event.

    Attributes:
        id: Primary key.
        company_id: Foreign key to the owning company (multi-tenancy).
        anomaly_type: Classification of the anomaly (e.g., "backdated_signature",
            "workflow_bypass", "bulk_approval", "off_hours_mutation",
            "rapid_version_churn").
        severity: Severity level (Critical, Major, Minor).
        description: Human-readable description of the detected anomaly.
        affected_document_id: Foreign key to the affected document (nullable).
        affected_user_id: Foreign key to the affected user (nullable).
        detected_at: Timestamp when the anomaly was detected.
        is_resolved: Whether the anomaly has been reviewed and resolved.
        resolved_at: Timestamp when the anomaly was resolved (nullable).
        resolution_note: Explanation of how the anomaly was resolved (nullable).
        created_at: Server-side UTC timestamp of record creation.
    """

    __tablename__ = "anomaly_alerts"
    __table_args__ = (
        UniqueConstraint(
            "anomaly_type",
            "affected_document_id",
            "affected_user_id",
            "detected_at",
            name="uq_anomaly_alerts_deduplication",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    anomaly_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(50), index=True)
    description: Mapped[str] = mapped_column(Text)
    affected_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    affected_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_resolved: Mapped[bool] = mapped_column(default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
