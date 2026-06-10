"""SQLAlchemy models for the ingestion pipeline.

This sub-package defines the ORM models for ingestion records,
per-company ingestion configuration, and append-only audit logs.
"""

from alcoabase.literature.ingestion.models.ingestion import (
    IngestionAuditLog,
    IngestionConfiguration,
    IngestionRecord,
)

__all__ = [
    "IngestionAuditLog",
    "IngestionConfiguration",
    "IngestionRecord",
]
