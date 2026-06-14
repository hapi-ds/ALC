"""Document access log model for audit trail of document downloads and previews.

This module defines the DocumentAccessLog model that records every download
and content preview access to documents. This table is append-only — no
updates or deletes are permitted, enforcing immutability at the service layer
per ALCOA+ and 21 CFR Part 11 requirements.

References:
    - Requirement 6.4: Log all download and content access events to the audit trail
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class DocumentAccessLog(Base):
    """Immutable log of document access events (downloads and content previews).

    Records every download and inline content preview action performed
    against documents. This enables auditing of who accessed which
    document content, when, and how.

    This table is append-only. No update or delete operations are
    permitted, enforced at the service layer per ALCOA+ compliance.

    Attributes:
        id: Primary key.
        user_id: ID of the user who accessed the document.
        document_uuid: UUID of the accessed document.
        major_version: Major version number of the accessed document version.
        minor_version: Minor version number of the accessed document version.
        action: Type of access — "download" or "content_preview".
        timestamp: Server-side UTC timestamp of the access event.
    """

    __tablename__ = "document_access_log"
    __table_args__ = (
        Index(
            "ix_document_access_log_user_id_timestamp",
            "user_id",
            "timestamp",
        ),
        Index(
            "ix_document_access_log_document_uuid",
            "document_uuid",
        ),
        Index(
            "ix_document_access_log_timestamp",
            "timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    document_uuid: Mapped[str] = mapped_column(String(12))
    major_version: Mapped[int] = mapped_column(Integer)
    minor_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))  # "download" | "content_preview"
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
