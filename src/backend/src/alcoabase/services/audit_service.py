"""Audit service for querying version history of GxP-relevant records.

This module provides the AuditService class that enables querying the
SQLAlchemy-Continuum version tables for any audited model. It supports
retrieving chronological version history for documents, templates, reports,
workflows, signatures, training tasks, and training records.

The service relies on SQLAlchemy-Continuum's automatic version table
creation for all models inheriting AuditMixin. Each version entry records:
    - transaction_id: Links all changes in a single request
    - operation_type: INSERT (0), UPDATE (1), DELETE (2)
    - All column snapshots at the time of the change

References:
    - SQLAlchemy-Continuum: https://sqlalchemy-continuum.readthedocs.io/
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.report import Report
from alcoabase.models.signature import SignatureRecord
from alcoabase.models.template import Template
from alcoabase.models.training import TrainingRecord, TrainingTask
from alcoabase.models.workflow import WorkflowDefinition


# Mapping of record type strings to their corresponding SQLAlchemy models.
# These models all inherit AuditMixin and have Continuum version tables.
RECORD_TYPE_MODEL_MAP: dict[str, type] = {
    "documents": Document,
    "templates": Template,
    "reports": Report,
    "workflows": WorkflowDefinition,
    "signatures": SignatureRecord,
    "training_tasks": TrainingTask,
    "training_records": TrainingRecord,
}


class AuditService:
    """Service for querying audit trail version history.

    Provides methods to retrieve the complete version history of any
    GxP-relevant record, returning entries in chronological order with
    monotonically increasing version numbers.

    The service uses SQLAlchemy-Continuum's version classes, which are
    automatically created for all models with __versioned__ = {}.
    """

    def get_supported_record_types(self) -> list[str]:
        """Return the list of supported record type identifiers.

        Returns:
            List of string identifiers that can be used with
            get_version_history().
        """
        return list(RECORD_TYPE_MODEL_MAP.keys())

    async def get_version_history(
        self,
        session: AsyncSession,
        record_type: str,
        record_id: int,
    ) -> list[dict[str, Any]]:
        """Retrieve the complete version history for a specific record.

        Queries the SQLAlchemy-Continuum version table for the given
        record type and returns all version entries in chronological
        order (ascending transaction_id).

        Args:
            session: Active async database session.
            record_type: The type of record (e.g., "documents", "templates").
                Must be one of the keys in RECORD_TYPE_MODEL_MAP.
            record_id: The primary key ID of the record to query.

        Returns:
            List of version entry dictionaries, each containing:
                - transaction_id: The Continuum transaction identifier
                - operation_type: 0=INSERT, 1=UPDATE, 2=DELETE
                - All column values at the time of the change

        Raises:
            ValueError: If record_type is not a supported type.
        """
        if record_type not in RECORD_TYPE_MODEL_MAP:
            raise ValueError(
                f"Unsupported record type: '{record_type}'. "
                f"Supported types: {list(RECORD_TYPE_MODEL_MAP.keys())}"
            )

        model_cls = RECORD_TYPE_MODEL_MAP[record_type]

        # Get the Continuum version class for this model
        try:
            version_cls = model_cls.__versioned_cls__  # type: ignore[attr-defined]
        except AttributeError:
            # Fallback: construct version table name and query directly
            # This handles cases where Continuum hasn't fully initialized
            # (e.g., in test environments without full DB setup)
            return await self._query_version_table_raw(
                session, model_cls, record_id
            )

        # Query version entries ordered by transaction_id (chronological)
        stmt = (
            select(version_cls)
            .where(version_cls.id == record_id)
            .order_by(version_cls.transaction_id.asc())
        )

        result = await session.execute(stmt)
        versions = result.scalars().all()

        return [self._version_to_dict(v) for v in versions]

    async def _query_version_table_raw(
        self,
        session: AsyncSession,
        model_cls: type,
        record_id: int,
    ) -> list[dict[str, Any]]:
        """Fallback query using raw table name when version class unavailable.

        Args:
            session: Active async database session.
            model_cls: The SQLAlchemy model class.
            record_id: The primary key ID of the record.

        Returns:
            List of version entry dictionaries.
        """
        from sqlalchemy import text

        table_name = model_cls.__tablename__  # type: ignore[attr-defined]
        version_table = f"{table_name}_version"

        query = text(
            f"SELECT * FROM {version_table} "  # noqa: S608
            f"WHERE id = :record_id "
            f"ORDER BY transaction_id ASC"
        )

        result = await session.execute(query, {"record_id": record_id})
        rows = result.mappings().all()

        return [dict(row) for row in rows]

    def _version_to_dict(self, version: Any) -> dict[str, Any]:
        """Convert a Continuum version object to a dictionary.

        Args:
            version: A SQLAlchemy-Continuum version instance.

        Returns:
            Dictionary with all column values from the version entry.
        """
        result: dict[str, Any] = {}
        # Get all column names from the version class mapper
        mapper = version.__class__.__mapper__  # type: ignore[attr-defined]
        for column in mapper.columns:
            key = column.key
            value = getattr(version, key, None)
            result[key] = value
        return result

    async def get_record_exists(
        self,
        session: AsyncSession,
        record_type: str,
        record_id: int,
    ) -> bool:
        """Check if a record exists in the base table.

        Args:
            session: Active async database session.
            record_type: The type of record.
            record_id: The primary key ID of the record.

        Returns:
            True if the record exists, False otherwise.

        Raises:
            ValueError: If record_type is not a supported type.
        """
        if record_type not in RECORD_TYPE_MODEL_MAP:
            raise ValueError(
                f"Unsupported record type: '{record_type}'. "
                f"Supported types: {list(RECORD_TYPE_MODEL_MAP.keys())}"
            )

        model_cls = RECORD_TYPE_MODEL_MAP[record_type]
        stmt = select(model_cls).where(model_cls.id == record_id)  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None
