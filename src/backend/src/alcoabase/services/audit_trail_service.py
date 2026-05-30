"""Audit trail service for aggregating audit events across all version tables.

This module provides the AuditTrailService class that queries, filters,
paginates, and searches audit events across all versioned record types
in AlcoaBase. It supports both explicit version models (DocumentVersion,
TemplateVersion, WorkflowVersion) and SQLAlchemy-Continuum auto-generated
version tables (for Report, SignatureRecord, TrainingTask, TrainingRecord).

References:
    - Design doc: Components > AuditTrailService
    - Requirements 1.1–1.7: Centralized audit event aggregation
    - Requirements 2.1–2.3: Paginated retrieval
    - Requirements 3.1–3.5: Filtering
    - Requirements 4.1–4.3: Multi-tenant scoping
    - Requirements 5.1–5.3: Full-text search
    - Requirements 6.1–6.5: Event detail view
"""

import base64
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import Select, String as SAString, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.document import DocumentVersion
from alcoabase.models.report import Report
from alcoabase.models.signature import SignatureRecord
from alcoabase.models.template_version import TemplateVersion
from alcoabase.models.training import TrainingRecord, TrainingTask
from alcoabase.models.user import User
from alcoabase.models.workflow import WorkflowVersion
from alcoabase.schemas.audit_trail import (
    AuditEvent,
    AuditEventDetail,
    AuditTrailFilters,
    AuditTrailPage,
    FieldChange,
)

logger = logging.getLogger(__name__)


# Operation type mapping: Continuum uses integers, we use strings
OPERATION_TYPE_MAP = {0: "INSERT", 1: "UPDATE", 2: "DELETE"}
OPERATION_TYPE_REVERSE = {"INSERT": 0, "UPDATE": 1, "DELETE": 2}

# Fields to exclude from change tracking (internal/system fields)
EXCLUDED_FIELDS = frozenset({
    "id",
    "transaction_id",
    "operation_type",
    "end_transaction_id",
    "is_csv_validation_record",
    "is_demo_data",
})


class _VersionTableConfig:
    """Configuration for a single audited version table.

    Attributes:
        record_type: String identifier for the record type.
        model_cls: The SQLAlchemy model class for the version table.
        is_explicit: Whether this is an explicit version model (True)
            or a Continuum-managed base model (False).
        timestamp_col: Name of the timestamp column.
        user_col: Name of the user ID column.
        change_reason_col: Name of the change reason column (or None).
        company_id_col: Name of the company_id column (or None for
            models that need a JOIN to get company_id).
        record_id_col: Name of the column that identifies the parent record.
    """

    def __init__(
        self,
        record_type: str,
        model_cls: type,
        is_explicit: bool,
        timestamp_col: str,
        user_col: str,
        change_reason_col: str | None = None,
        company_id_col: str | None = None,
        record_id_col: str = "id",
    ) -> None:
        self.record_type = record_type
        self.model_cls = model_cls
        self.is_explicit = is_explicit
        self.timestamp_col = timestamp_col
        self.user_col = user_col
        self.change_reason_col = change_reason_col
        self.company_id_col = company_id_col
        self.record_id_col = record_id_col


# Configuration for each audited record type.
# Explicit version models have their own timestamp/user/change_reason columns.
# Continuum-managed models use the transaction table for metadata.
AUDITED_RECORD_TYPES: dict[str, _VersionTableConfig] = {
    "documents": _VersionTableConfig(
        record_type="documents",
        model_cls=DocumentVersion,
        is_explicit=True,
        timestamp_col="uploaded_at",
        user_col="uploaded_by",
        change_reason_col="change_reason",
        company_id_col=None,  # Need JOIN to documents table
        record_id_col="document_id",
    ),
    "templates": _VersionTableConfig(
        record_type="templates",
        model_cls=TemplateVersion,
        is_explicit=True,
        timestamp_col="created_at",
        user_col="created_by",
        change_reason_col="change_reason",
        company_id_col=None,  # Need JOIN to templates table
        record_id_col="template_id",
    ),
    "reports": _VersionTableConfig(
        record_type="reports",
        model_cls=Report,
        is_explicit=False,
        timestamp_col="uploaded_at",
        user_col="uploaded_by",
        change_reason_col=None,
        company_id_col="company_id",
        record_id_col="id",
    ),
    "workflows": _VersionTableConfig(
        record_type="workflows",
        model_cls=WorkflowVersion,
        is_explicit=True,
        timestamp_col="created_at",
        user_col="created_by",
        change_reason_col="change_reason",
        company_id_col="company_id",
        record_id_col="workflow_id",
    ),
    "signatures": _VersionTableConfig(
        record_type="signatures",
        model_cls=SignatureRecord,
        is_explicit=False,
        timestamp_col="signed_at",
        user_col="signer_user_id",
        change_reason_col="reason",
        company_id_col="company_id",
        record_id_col="id",
    ),
    "training_tasks": _VersionTableConfig(
        record_type="training_tasks",
        model_cls=TrainingTask,
        is_explicit=False,
        timestamp_col="created_at",
        user_col="assigned_user_id",
        change_reason_col=None,
        company_id_col="company_id",
        record_id_col="id",
    ),
    "training_records": _VersionTableConfig(
        record_type="training_records",
        model_cls=TrainingRecord,
        is_explicit=False,
        timestamp_col="completed_at",
        user_col="user_id",
        change_reason_col=None,
        company_id_col="company_id",
        record_id_col="id",
    ),
}


class AuditTrailService:
    """Service for aggregating, filtering, and paginating audit events.

    Queries each version table individually, merges results in-memory,
    and applies cursor-based pagination. Supports graceful degradation
    when individual version table queries fail.
    """

    async def list_events(
        self,
        session: AsyncSession,
        company_id: int,
        filters: AuditTrailFilters,
        search_query: str | None = None,
        cursor: str | None = None,
        page_size: int = 50,
        cross_company: bool = False,
    ) -> AuditTrailPage:
        """Aggregate and return paginated audit events.

        Queries each version table individually with applied filters,
        merges results in-memory sorted by timestamp descending, and
        applies cursor-based pagination.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.
            filters: Filter criteria to apply.
            search_query: Optional substring search query.
            cursor: Opaque cursor for pagination (None for first page).
            page_size: Number of events per page (clamped to [1, 200]).
            cross_company: If True, skip company scoping (system_admin only).

        Returns:
            AuditTrailPage with events, next_cursor, total_count, and warnings.
        """
        # Clamp page_size to valid range
        page_size = max(1, min(200, page_size))

        # Determine which record types to query
        record_types_to_query = self._get_record_types_to_query(filters)

        all_events: list[AuditEvent] = []
        warnings: list[str] = []
        total_count = 0

        # Query each version table with graceful degradation
        for record_type, config in record_types_to_query.items():
            try:
                events = await self._query_version_table(
                    session=session,
                    config=config,
                    company_id=company_id,
                    filters=filters,
                    search_query=search_query,
                    cross_company=cross_company,
                )
                all_events.extend(events)
            except Exception:
                logger.exception(
                    "Failed to query version table for record_type=%s",
                    record_type,
                )
                warnings.append(
                    f"Failed to retrieve events for record type: {record_type}"
                )

        # Sort all events by timestamp descending (most recent first)
        all_events.sort(key=lambda e: e.timestamp, reverse=True)

        # Calculate total count before pagination
        total_count = len(all_events)

        # Apply cursor-based pagination
        if cursor:
            cursor_data = self._decode_cursor(cursor)
            if cursor_data:
                all_events = self._apply_cursor(all_events, cursor_data)

        # Take page_size + 1 to determine if there's a next page
        has_next = len(all_events) > page_size
        page_events = all_events[:page_size]

        # Generate next cursor
        next_cursor: str | None = None
        if has_next and page_events:
            last_event = page_events[-1]
            next_cursor = self._encode_cursor(last_event)

        return AuditTrailPage(
            events=page_events,
            next_cursor=next_cursor,
            total_count=total_count,
            warnings=warnings if warnings else None,
        )

    async def get_event_detail(
        self,
        session: AsyncSession,
        company_id: int,
        record_type: str,
        record_id: int,
        transaction_id: int,
    ) -> AuditEventDetail | None:
        """Return full version snapshot for a specific event.

        Queries the specific version table for the exact version entry
        and computes field-level changes by comparing with the previous
        version.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.
            record_type: The type of record.
            record_id: The record's primary key.
            transaction_id: The version entry's ID (used as transaction_id).

        Returns:
            AuditEventDetail with field changes, or None if not found.
        """
        if record_type not in AUDITED_RECORD_TYPES:
            return None

        config = AUDITED_RECORD_TYPES[record_type]
        model_cls = config.model_cls

        # Query the specific version entry
        stmt = select(model_cls).where(model_cls.id == transaction_id)
        result = await session.execute(stmt)
        version = result.scalar_one_or_none()

        if version is None:
            return None

        # Verify company scoping for explicit models
        if config.company_id_col:
            version_company = getattr(version, config.company_id_col, None)
            if version_company != company_id:
                return None

        # Get all versions for this record to determine operation type and changes
        record_id_col = getattr(model_cls, config.record_id_col)
        record_id_value = getattr(version, config.record_id_col)
        timestamp_col = getattr(model_cls, config.timestamp_col)

        all_versions_stmt = (
            select(model_cls)
            .where(record_id_col == record_id_value)
            .order_by(timestamp_col.asc())
        )
        all_versions_result = await session.execute(all_versions_stmt)
        all_versions = list(all_versions_result.scalars().all())

        # Determine operation type and compute field changes
        version_index = None
        for i, v in enumerate(all_versions):
            if v.id == transaction_id:
                version_index = i
                break

        if version_index is None:
            return None

        # Determine operation type based on position
        if version_index == 0:
            operation_type = "INSERT"
        else:
            operation_type = "UPDATE"

        # Compute field changes
        field_changes = self._compute_field_changes(
            version=version,
            previous_version=all_versions[version_index - 1] if version_index > 0 else None,
            operation_type=operation_type,
            model_cls=model_cls,
        )

        # Resolve user display name
        user_id = getattr(version, config.user_col)
        user_display_name = await self._resolve_user_display_name(
            session, user_id
        )

        # Get timestamp and change reason
        timestamp = getattr(version, config.timestamp_col)
        change_reason = (
            getattr(version, config.change_reason_col, None)
            if config.change_reason_col
            else None
        )

        return AuditEventDetail(
            transaction_id=version.id,
            timestamp=timestamp,
            user_id=user_id,
            user_display_name=user_display_name,
            record_type=record_type,
            record_id=record_id_value,
            operation_type=operation_type,
            change_reason=change_reason,
            field_changes=field_changes,
            company_id=company_id,
        )

    async def get_total_count(
        self,
        session: AsyncSession,
        company_id: int,
        filters: AuditTrailFilters,
        search_query: str | None = None,
    ) -> int:
        """Return total count of matching events across all version tables.

        Executes COUNT queries against each version table with the same
        filters and sums results.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.
            filters: Filter criteria to apply.
            search_query: Optional substring search query.

        Returns:
            Total count of matching events.
        """
        record_types_to_query = self._get_record_types_to_query(filters)
        total = 0

        for record_type, config in record_types_to_query.items():
            try:
                count = await self._count_version_table(
                    session=session,
                    config=config,
                    company_id=company_id,
                    filters=filters,
                    search_query=search_query,
                )
                total += count
            except Exception:
                logger.exception(
                    "Failed to count version table for record_type=%s",
                    record_type,
                )

        return total

    # -----------------------------------------------------------------------
    # Private helper methods
    # -----------------------------------------------------------------------

    def _get_record_types_to_query(
        self, filters: AuditTrailFilters
    ) -> dict[str, _VersionTableConfig]:
        """Determine which record types to query based on filters.

        Args:
            filters: Filter criteria (may restrict to a single record_type).

        Returns:
            Dict of record_type -> config for tables to query.
        """
        if filters.record_type:
            if filters.record_type in AUDITED_RECORD_TYPES:
                return {
                    filters.record_type: AUDITED_RECORD_TYPES[filters.record_type]
                }
            return {}
        return dict(AUDITED_RECORD_TYPES)

    async def _query_version_table(
        self,
        session: AsyncSession,
        config: _VersionTableConfig,
        company_id: int,
        filters: AuditTrailFilters,
        search_query: str | None,
        cross_company: bool = False,
    ) -> list[AuditEvent]:
        """Query a single version table and return audit events.

        Args:
            session: Active async database session.
            config: Configuration for the version table.
            company_id: Company ID for tenant scoping.
            filters: Filter criteria.
            search_query: Optional search query.
            cross_company: If True, skip company scoping.

        Returns:
            List of AuditEvent objects from this table.
        """
        model_cls = config.model_cls
        stmt = select(model_cls)

        # Apply company scoping
        if not cross_company:
            stmt = self._apply_company_filter(stmt, config, company_id)

        # Apply user_id filter
        if filters.user_id is not None:
            user_col = getattr(model_cls, config.user_col)
            stmt = stmt.where(user_col == filters.user_id)

        # Apply date range filter
        timestamp_col = getattr(model_cls, config.timestamp_col)
        if filters.date_start is not None:
            stmt = stmt.where(timestamp_col >= filters.date_start)
        if filters.date_end is not None:
            stmt = stmt.where(timestamp_col <= filters.date_end)

        # Apply search query (ILIKE substring match)
        if search_query:
            stmt = self._apply_search_filter(
                stmt, config, search_query
            )

        # Order by timestamp descending
        stmt = stmt.order_by(timestamp_col.desc())

        result = await session.execute(stmt)
        rows = result.scalars().all()

        # Convert to AuditEvent objects
        events: list[AuditEvent] = []
        # Batch resolve user display names
        user_ids = {getattr(row, config.user_col) for row in rows}
        user_names = await self._batch_resolve_user_names(session, user_ids)

        for row in rows:
            event = self._row_to_audit_event(row, config, user_names, company_id)
            if event:
                events.append(event)

        return events

    async def _count_version_table(
        self,
        session: AsyncSession,
        config: _VersionTableConfig,
        company_id: int,
        filters: AuditTrailFilters,
        search_query: str | None,
    ) -> int:
        """Execute a COUNT query against a single version table.

        Args:
            session: Active async database session.
            config: Configuration for the version table.
            company_id: Company ID for tenant scoping.
            filters: Filter criteria.
            search_query: Optional search query.

        Returns:
            Count of matching rows.
        """
        model_cls = config.model_cls
        stmt = select(func.count()).select_from(model_cls)

        # Apply company scoping
        stmt = self._apply_company_filter(stmt, config, company_id)

        # Apply user_id filter
        if filters.user_id is not None:
            user_col = getattr(model_cls, config.user_col)
            stmt = stmt.where(user_col == filters.user_id)

        # Apply date range filter
        timestamp_col = getattr(model_cls, config.timestamp_col)
        if filters.date_start is not None:
            stmt = stmt.where(timestamp_col >= filters.date_start)
        if filters.date_end is not None:
            stmt = stmt.where(timestamp_col <= filters.date_end)

        # Apply search query
        if search_query:
            stmt = self._apply_search_filter(stmt, config, search_query)

        result = await session.execute(stmt)
        return result.scalar_one()

    def _apply_company_filter(
        self,
        stmt: Select,
        config: _VersionTableConfig,
        company_id: int,
    ) -> Select:
        """Apply company_id scoping to a query.

        For models with a direct company_id column, filter directly.
        For models without (DocumentVersion, TemplateVersion), we
        filter by the parent table's company_id via a subquery approach
        or skip if the model doesn't support it directly.

        Args:
            stmt: The current SQLAlchemy select statement.
            config: Version table configuration.
            company_id: Company ID to filter by.

        Returns:
            Modified select statement with company filter applied.
        """
        model_cls = config.model_cls

        if config.company_id_col:
            col = getattr(model_cls, config.company_id_col)
            return stmt.where(col == company_id)

        # For DocumentVersion: filter via document_id -> documents.company_id
        if config.record_type == "documents":
            from alcoabase.models.document import Document

            stmt = stmt.join(
                Document, model_cls.document_id == Document.id
            ).where(Document.company_id == company_id)
        # For TemplateVersion: filter via template_id -> templates.company_id
        elif config.record_type == "templates":
            from alcoabase.models.template import Template

            stmt = stmt.join(
                Template, model_cls.template_id == Template.id
            ).where(Template.company_id == company_id)

        return stmt

    def _apply_search_filter(
        self,
        stmt: Select,
        config: _VersionTableConfig,
        search_query: str,
    ) -> Select:
        """Apply ILIKE substring search against searchable fields.

        Searches against change_reason, record_type (as literal),
        and cast record_id to string.

        Args:
            stmt: The current SQLAlchemy select statement.
            config: Version table configuration.
            search_query: The search substring.

        Returns:
            Modified select statement with search filter applied.
        """
        model_cls = config.model_cls
        pattern = f"%{search_query}%"
        conditions = []

        # Search in change_reason if available
        if config.change_reason_col:
            reason_col = getattr(model_cls, config.change_reason_col, None)
            if reason_col is not None:
                conditions.append(reason_col.ilike(pattern))

        # Search in record_id cast to string
        record_id_col = getattr(model_cls, config.record_id_col)
        conditions.append(
            cast(record_id_col, SAString).ilike(pattern)
        )

        # Search against the record_type literal
        # (matches if search_query is a substring of the record_type name)
        if search_query.lower() in config.record_type.lower():
            # This record type matches the search, don't filter it out
            return stmt

        if conditions:
            stmt = stmt.where(or_(*conditions))

        return stmt

    def _row_to_audit_event(
        self,
        row: Any,
        config: _VersionTableConfig,
        user_names: dict[int, str | None],
        company_id: int,
    ) -> AuditEvent | None:
        """Convert a version table row to an AuditEvent.

        Args:
            row: SQLAlchemy model instance from the version table.
            config: Version table configuration.
            user_names: Pre-resolved mapping of user_id -> display_name.
            company_id: Company ID for the event.

        Returns:
            AuditEvent instance, or None if conversion fails.
        """
        try:
            user_id = getattr(row, config.user_col)
            timestamp = getattr(row, config.timestamp_col)
            record_id = getattr(row, config.record_id_col)
            change_reason = (
                getattr(row, config.change_reason_col, None)
                if config.change_reason_col
                else None
            )

            # Determine operation type for explicit version models
            # For explicit models, first version is INSERT, rest are UPDATE
            operation_type = "UPDATE"
            if config.is_explicit:
                # Check if this is the first version (version_number == 1)
                version_number = getattr(row, "version_number", None)
                if version_number == 1:
                    operation_type = "INSERT"
            else:
                # For Continuum-managed models, check operation_type attribute
                op_type = getattr(row, "operation_type", None)
                if op_type is not None:
                    operation_type = OPERATION_TYPE_MAP.get(op_type, "UPDATE")

            # Get changed fields by inspecting the model columns
            changed_fields = self._get_changed_fields(row, config)
            total_changed_fields = len(changed_fields)
            truncated_fields = changed_fields[:10]

            # Get company_id from the row if available
            event_company_id = company_id
            if config.company_id_col:
                event_company_id = getattr(row, config.company_id_col, company_id)

            return AuditEvent(
                transaction_id=row.id,
                timestamp=timestamp,
                user_id=user_id,
                user_display_name=user_names.get(user_id),
                record_type=config.record_type,
                record_id=record_id,
                operation_type=operation_type,
                change_reason=change_reason,
                changed_fields=truncated_fields,
                total_changed_fields=total_changed_fields,
                company_id=event_company_id,
            )
        except Exception:
            logger.exception(
                "Failed to convert row to AuditEvent for record_type=%s",
                config.record_type,
            )
            return None

    def _get_changed_fields(self, row: Any, config: _VersionTableConfig) -> list[str]:
        """Get list of field names that have non-null values in a version row.

        For explicit version models, returns all data columns (excluding
        system fields). This represents the fields captured in this version.

        Args:
            row: SQLAlchemy model instance.
            config: Version table configuration.

        Returns:
            List of field names with values set.
        """
        mapper = row.__class__.__mapper__
        fields = []
        for column in mapper.columns:
            key = column.key
            if key in EXCLUDED_FIELDS:
                continue
            # Skip internal columns
            if key in (
                config.timestamp_col,
                config.user_col,
                config.record_id_col,
                "version_number",
            ):
                continue
            if config.change_reason_col and key == config.change_reason_col:
                continue
            if config.company_id_col and key == config.company_id_col:
                continue
            value = getattr(row, key, None)
            if value is not None:
                fields.append(key)
        return fields

    def _compute_field_changes(
        self,
        version: Any,
        previous_version: Any | None,
        operation_type: str,
        model_cls: type,
    ) -> list[FieldChange]:
        """Compute field-level changes between two versions.

        Args:
            version: Current version row.
            previous_version: Previous version row (None for INSERT).
            operation_type: "INSERT", "UPDATE", or "DELETE".
            model_cls: The model class for column introspection.

        Returns:
            List of FieldChange objects.
        """
        mapper = model_cls.__mapper__
        changes: list[FieldChange] = []

        data_columns = [
            col for col in mapper.columns
            if col.key not in EXCLUDED_FIELDS
        ]

        if operation_type == "INSERT":
            # All fields with old_value=None
            for col in data_columns:
                value = getattr(version, col.key, None)
                if value is not None:
                    changes.append(FieldChange(
                        field_name=col.key,
                        old_value=None,
                        new_value=self._serialize_value(value),
                    ))
        elif operation_type == "DELETE":
            # All fields with new_value=None
            for col in data_columns:
                value = getattr(version, col.key, None)
                if value is not None:
                    changes.append(FieldChange(
                        field_name=col.key,
                        old_value=self._serialize_value(value),
                        new_value=None,
                    ))
        elif operation_type == "UPDATE" and previous_version is not None:
            # Compare fields between versions
            for col in data_columns:
                old_val = getattr(previous_version, col.key, None)
                new_val = getattr(version, col.key, None)
                if old_val != new_val:
                    changes.append(FieldChange(
                        field_name=col.key,
                        old_value=self._serialize_value(old_val),
                        new_value=self._serialize_value(new_val),
                    ))

        return changes

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """Serialize a value for JSON-safe output.

        Converts datetime objects to ISO format strings and leaves
        other types as-is.

        Args:
            value: The value to serialize.

        Returns:
            JSON-serializable value.
        """
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    async def _resolve_user_display_name(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> str | None:
        """Resolve a user_id to their display name.

        Args:
            session: Active async database session.
            user_id: The user's ID.

        Returns:
            The user's full_name, or None if user not found.
        """
        stmt = select(User.full_name).where(User.id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _batch_resolve_user_names(
        self,
        session: AsyncSession,
        user_ids: set[int],
    ) -> dict[int, str | None]:
        """Batch resolve user IDs to display names.

        Args:
            session: Active async database session.
            user_ids: Set of user IDs to resolve.

        Returns:
            Dict mapping user_id -> full_name (None if not found).
        """
        if not user_ids:
            return {}

        stmt = select(User.id, User.full_name).where(User.id.in_(user_ids))
        result = await session.execute(stmt)
        rows = result.all()

        name_map: dict[int, str | None] = {uid: None for uid in user_ids}
        for row in rows:
            name_map[row[0]] = row[1]

        return name_map

    # -----------------------------------------------------------------------
    # Cursor encoding/decoding
    # -----------------------------------------------------------------------

    @staticmethod
    def _encode_cursor(event: AuditEvent) -> str:
        """Encode an AuditEvent into an opaque cursor string.

        The cursor is a base64-encoded JSON object containing the
        composite key: (timestamp, transaction_id, record_type).

        Args:
            event: The last event on the current page.

        Returns:
            Base64-encoded cursor string.
        """
        cursor_data = {
            "ts": event.timestamp.isoformat(),
            "tid": event.transaction_id,
            "rt": event.record_type,
        }
        json_bytes = json.dumps(cursor_data).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).decode("ascii")

    @staticmethod
    def _decode_cursor(cursor: str) -> dict[str, Any] | None:
        """Decode an opaque cursor string into its components.

        Args:
            cursor: Base64-encoded cursor string.

        Returns:
            Dict with 'ts' (datetime), 'tid' (int), 'rt' (str),
            or None if decoding fails.
        """
        try:
            json_bytes = base64.urlsafe_b64decode(cursor.encode("ascii"))
            data = json.loads(json_bytes)
            data["ts"] = datetime.fromisoformat(data["ts"])
            return data
        except (ValueError, KeyError, json.JSONDecodeError):
            return None

    @staticmethod
    def _apply_cursor(
        events: list[AuditEvent],
        cursor_data: dict[str, Any],
    ) -> list[AuditEvent]:
        """Filter events to those after the cursor position.

        Events are already sorted by timestamp descending. The cursor
        marks the last event seen, so we skip all events up to and
        including the cursor position.

        Args:
            events: Sorted list of all events.
            cursor_data: Decoded cursor with 'ts', 'tid', 'rt'.

        Returns:
            Events after the cursor position.
        """
        cursor_ts = cursor_data["ts"]
        cursor_tid = cursor_data["tid"]
        cursor_rt = cursor_data["rt"]

        # Find the position after the cursor
        for i, event in enumerate(events):
            if (
                event.timestamp == cursor_ts
                and event.transaction_id == cursor_tid
                and event.record_type == cursor_rt
            ):
                return events[i + 1:]
            # Since events are sorted desc, if we pass the cursor timestamp
            # without finding an exact match, start from here
            if event.timestamp < cursor_ts:
                return events[i:]

        # Cursor not found or all events are before cursor
        return []
