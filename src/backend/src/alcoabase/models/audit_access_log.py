"""Audit access log model for meta-auditing of audit trail access.

This module defines the AuditAccessLog model that records every access
to the audit trail viewer (views and exports). This table is itself an
immutable audit log — no updates or deletes are permitted.

The table is NOT versioned by SQLAlchemy-Continuum because it is itself
an append-only audit record. Immutability is enforced at the API layer.

References:
    - Requirement 11.1: Log access events with user identity, timestamp, and filters
    - Requirement 11.2: Log export events with user identity, timestamp, filters, and event count
    - Requirement 11.3: Dedicated audit_access_log table with same immutability rules
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class AuditAccessLog(Base):
    """Immutable log of audit trail access events.

    Records every view and export action performed against the audit
    trail. This enables meta-auditing: knowing who reviewed the audit
    data and when.

    This table is append-only. No update or delete operations are
    permitted, enforced at the API layer per ALCOA+ and 21 CFR Part 11.

    Attributes:
        id: Primary key.
        user_id: Foreign key to the user who accessed the audit trail.
        company_id: Foreign key to the company context of the access.
        action: Type of access — "view" for list/detail requests,
            "export" for PDF export requests.
        filters_applied: JSON object of active filter parameters at the
            time of access. None if no filters were applied.
        event_count: Number of events exported (populated only for
            export actions, None for view actions).
        timestamp: Server-side UTC timestamp of the access event.
    """

    __tablename__ = "audit_access_log"
    __table_args__ = (
        Index(
            "ix_audit_access_log_user_id_timestamp",
            "user_id",
            "timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(10))  # "view" | "export"
    filters_applied: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    event_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
