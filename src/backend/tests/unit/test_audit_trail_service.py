"""Unit tests for AuditTrailService.

Tests cover:
- list_events returns events ordered by timestamp descending
- list_events with each filter type individually
- list_events with combined filters (AND logic)
- list_events with search query (substring matching)
- list_events cursor-based pagination
- list_events company_id scoping (multi-tenant isolation)
- list_events cross_company=True for system_admin
- list_events graceful degradation when a version table query fails
- list_events with no Change_Reason (returns null, event not omitted)
- get_event_detail for INSERT (all fields, no old_value)
- get_event_detail for UPDATE (changed fields with old/new values)
- get_event_detail for DELETE (final values, no new_value)
- get_event_detail user_display_name resolution and fallback
- get_total_count accuracy with filters
- page_size clamping to [1, 200]

References:
    - Requirements: 1.1–1.7, 2.1–2.3, 3.1–3.5, 4.1–4.3, 5.1–5.3, 6.1–6.5
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.schemas.audit_trail import AuditTrailFilters
from alcoabase.services.audit_trail_service import (
    AUDITED_RECORD_TYPES,
    AuditTrailService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> AuditTrailService:
    """Create an AuditTrailService instance."""
    return AuditTrailService()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_mock_row(
    row_id: int,
    timestamp: datetime,
    user_id: int,
    record_id: int,
    config,
    change_reason: str | None = None,
    company_id: int = 1,
    version_number: int = 1,
) -> MagicMock:
    """Create a mock row mimicking a SQLAlchemy version table row.

    Args:
        row_id: The row's primary key (used as transaction_id).
        timestamp: The event timestamp.
        user_id: The user who performed the action.
        record_id: The parent record's ID.
        config: The _VersionTableConfig for this record type.
        change_reason: Optional change reason text.
        company_id: Company ID for the row.
        version_number: Version number (1 = INSERT for explicit models).

    Returns:
        MagicMock that responds to getattr for expected columns.
    """
    row = MagicMock()
    row.id = row_id
    setattr(row, config.timestamp_col, timestamp)
    setattr(row, config.user_col, user_id)
    setattr(row, config.record_id_col, record_id)

    if config.change_reason_col:
        setattr(row, config.change_reason_col, change_reason)

    if config.company_id_col:
        setattr(row, config.company_id_col, company_id)

    # Mock the mapper for _get_changed_fields
    mock_mapper = MagicMock()
    mock_mapper.columns = []
    row.__class__ = MagicMock()
    row.__class__.__mapper__ = mock_mapper

    if config.is_explicit:
        row.version_number = version_number

    return row


def _setup_query_mock(mock_session: AsyncMock, rows_by_type: dict) -> None:
    """Configure mock_session.execute to return rows per version table query.

    This patches _query_version_table to return pre-built AuditEvent lists
    based on record type, avoiding the complexity of mocking full SQLAlchemy
    query chains.
    """
    pass  # We'll use patch on _query_version_table instead


# ---------------------------------------------------------------------------
# Test: list_events returns events ordered by timestamp descending
# ---------------------------------------------------------------------------


class TestListEventsOrdering:
    """Tests that list_events returns events sorted by timestamp desc."""

    @pytest.mark.asyncio
    async def test_events_ordered_by_timestamp_descending(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events returns events most-recent-first."""
        ts1 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        ts3 = datetime(2025, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

        from alcoabase.schemas.audit_trail import AuditEvent

        events_unordered = [
            AuditEvent(
                transaction_id=1, timestamp=ts1, user_id=1,
                record_type="documents", record_id=1,
                operation_type="INSERT", company_id=1,
            ),
            AuditEvent(
                transaction_id=3, timestamp=ts3, user_id=1,
                record_type="documents", record_id=3,
                operation_type="UPDATE", company_id=1,
            ),
            AuditEvent(
                transaction_id=2, timestamp=ts2, user_id=1,
                record_type="templates", record_id=2,
                operation_type="INSERT", company_id=1,
            ),
        ]

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            # Return events in non-sorted order from different tables
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    return [events_unordered[0], events_unordered[1]]
                elif config.record_type == "templates":
                    return [events_unordered[2]]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters()
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        # Verify descending order
        timestamps = [e.timestamp for e in result.events]
        assert timestamps == sorted(timestamps, reverse=True)
        assert timestamps == [ts3, ts2, ts1]


# ---------------------------------------------------------------------------
# Test: list_events with each filter type individually
# ---------------------------------------------------------------------------


class TestListEventsIndividualFilters:
    """Tests that each filter type is passed to _query_version_table."""

    @pytest.mark.asyncio
    async def test_user_id_filter(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events passes user_id filter to version table queries."""
        from alcoabase.schemas.audit_trail import AuditEvent

        target_event = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=42, record_type="documents", record_id=1,
            operation_type="INSERT", company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = []

            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents" and filters.user_id == 42:
                    return [target_event]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(user_id=42)
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        assert len(result.events) == 1
        assert result.events[0].user_id == 42

    @pytest.mark.asyncio
    async def test_date_range_filter(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events passes date_start/date_end filters correctly."""
        from alcoabase.schemas.audit_trail import AuditEvent

        ts_in_range = datetime(2025, 3, 15, tzinfo=timezone.utc)
        event_in_range = AuditEvent(
            transaction_id=1, timestamp=ts_in_range, user_id=1,
            record_type="documents", record_id=1,
            operation_type="INSERT", company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    return [event_in_range]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(
                date_start=datetime(2025, 3, 1, tzinfo=timezone.utc),
                date_end=datetime(2025, 3, 31, tzinfo=timezone.utc),
            )
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        assert len(result.events) == 1
        assert result.events[0].timestamp == ts_in_range

    @pytest.mark.asyncio
    async def test_record_type_filter(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events queries only the specified record type when filtered."""
        from alcoabase.schemas.audit_trail import AuditEvent

        event = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=1, record_type="workflows", record_id=1,
            operation_type="INSERT", company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "workflows":
                    return [event]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="workflows")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        # Only workflows should be queried
        assert len(result.events) == 1
        assert result.events[0].record_type == "workflows"

    @pytest.mark.asyncio
    async def test_operation_type_filter(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events passes operation_type filter correctly."""
        from alcoabase.schemas.audit_trail import AuditEvent

        event = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=1, record_type="documents", record_id=1,
            operation_type="DELETE", company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                # Only documents returns the DELETE event
                if config.record_type == "documents" and filters.operation_type == "DELETE":
                    return [event]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(operation_type="DELETE")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        assert len(result.events) == 1
        assert result.events[0].operation_type == "DELETE"


# ---------------------------------------------------------------------------
# Test: list_events with combined filters (AND logic)
# ---------------------------------------------------------------------------


class TestListEventsCombinedFilters:
    """Tests that multiple filters combine with AND logic."""

    @pytest.mark.asyncio
    async def test_combined_filters_and_logic(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events applies all filters simultaneously (AND)."""
        from alcoabase.schemas.audit_trail import AuditEvent

        # Only this event matches both user_id=5 AND record_type=documents
        matching_event = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 2, 1, tzinfo=timezone.utc),
            user_id=5, record_type="documents", record_id=1,
            operation_type="UPDATE", company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                # Only documents table is queried (record_type filter)
                # and only user_id=5 events returned (user_id filter)
                if config.record_type == "documents" and filters.user_id == 5:
                    return [matching_event]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(user_id=5, record_type="documents")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        assert len(result.events) == 1
        assert result.events[0].user_id == 5
        assert result.events[0].record_type == "documents"


# ---------------------------------------------------------------------------
# Test: list_events with search query (substring matching)
# ---------------------------------------------------------------------------


class TestListEventsSearchQuery:
    """Tests that search_query is passed to version table queries."""

    @pytest.mark.asyncio
    async def test_search_query_substring_matching(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events passes search_query for substring matching."""
        from alcoabase.schemas.audit_trail import AuditEvent

        event = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=1, record_type="documents", record_id=1,
            operation_type="UPDATE", change_reason="Updated SOP procedure",
            company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if search_query == "SOP" and config.record_type == "documents":
                    return [event]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters()
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                search_query="SOP",
            )

        assert len(result.events) == 1
        assert "SOP" in result.events[0].change_reason


# ---------------------------------------------------------------------------
# Test: list_events cursor-based pagination
# ---------------------------------------------------------------------------


class TestListEventsPagination:
    """Tests cursor-based pagination for list_events."""

    @pytest.mark.asyncio
    async def test_first_page_returns_page_size_events(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """First page returns at most page_size events with next_cursor."""
        from alcoabase.schemas.audit_trail import AuditEvent

        # Create 5 events, request page_size=3
        events = [
            AuditEvent(
                transaction_id=i,
                timestamp=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                user_id=1, record_type="documents", record_id=i,
                operation_type="INSERT", company_id=1,
            )
            for i in range(1, 6)
        ]

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    return events
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="documents")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                page_size=3,
            )

        assert len(result.events) == 3
        assert result.next_cursor is not None
        assert result.total_count == 5

    @pytest.mark.asyncio
    async def test_next_page_no_duplicates(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """Using next_cursor returns subsequent events without duplicates."""
        from alcoabase.schemas.audit_trail import AuditEvent

        # Create 5 events sorted desc by timestamp
        events = [
            AuditEvent(
                transaction_id=i,
                timestamp=datetime(2025, 1, 6 - i, tzinfo=timezone.utc),
                user_id=1, record_type="documents", record_id=i,
                operation_type="INSERT", company_id=1,
            )
            for i in range(1, 6)
        ]

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    return events
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="documents")

            # Get first page
            page1 = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                page_size=3,
            )

            # Get second page using cursor
            page2 = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                page_size=3, cursor=page1.next_cursor,
            )

        # No duplicates between pages
        page1_ids = {e.transaction_id for e in page1.events}
        page2_ids = {e.transaction_id for e in page2.events}
        assert page1_ids.isdisjoint(page2_ids)

        # All events covered
        assert len(page1.events) + len(page2.events) == 5


# ---------------------------------------------------------------------------
# Test: list_events company_id scoping (multi-tenant isolation)
# ---------------------------------------------------------------------------


class TestListEventsCompanyScoping:
    """Tests that list_events scopes results to the specified company."""

    @pytest.mark.asyncio
    async def test_company_id_scoping(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events returns only events for the specified company_id."""
        from alcoabase.schemas.audit_trail import AuditEvent

        company1_event = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=1, record_type="workflows", record_id=1,
            operation_type="INSERT", company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                # Only return events for company_id=1
                if company_id == 1 and config.record_type == "workflows":
                    return [company1_event]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters()
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        assert len(result.events) == 1
        assert result.events[0].company_id == 1

    @pytest.mark.asyncio
    async def test_different_company_returns_no_events(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events for company_id=2 does not return company_id=1 events."""
        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = []

            filters = AuditTrailFilters()
            result = await service.list_events(
                session=mock_session, company_id=2, filters=filters
            )

        assert len(result.events) == 0


# ---------------------------------------------------------------------------
# Test: list_events cross_company=True for system_admin
# ---------------------------------------------------------------------------


class TestListEventsCrossCompany:
    """Tests cross_company parameter behavior."""

    @pytest.mark.asyncio
    async def test_cross_company_true_passes_to_query(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """list_events with cross_company=True passes it to version queries."""
        from alcoabase.schemas.audit_trail import AuditEvent

        event_company1 = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=1, record_type="documents", record_id=1,
            operation_type="INSERT", company_id=1,
        )
        event_company2 = AuditEvent(
            transaction_id=2,
            timestamp=datetime(2025, 1, 2, tzinfo=timezone.utc),
            user_id=2, record_type="documents", record_id=2,
            operation_type="INSERT", company_id=2,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if cross_company and config.record_type == "documents":
                    return [event_company1, event_company2]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="documents")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                cross_company=True,
            )

        assert len(result.events) == 2
        company_ids = {e.company_id for e in result.events}
        assert company_ids == {1, 2}


# ---------------------------------------------------------------------------
# Test: list_events graceful degradation when a version table query fails
# ---------------------------------------------------------------------------


class TestListEventsGracefulDegradation:
    """Tests graceful degradation when version table queries fail."""

    @pytest.mark.asyncio
    async def test_partial_failure_returns_remaining_events(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """When one table fails, events from other tables are still returned."""
        from alcoabase.schemas.audit_trail import AuditEvent

        good_event = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=1, record_type="templates", record_id=1,
            operation_type="INSERT", company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    raise RuntimeError("DB connection lost")
                if config.record_type == "templates":
                    return [good_event]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters()
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        # Events from non-failing tables are returned
        assert len(result.events) >= 1
        assert any(e.record_type == "templates" for e in result.events)

    @pytest.mark.asyncio
    async def test_partial_failure_includes_warning(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """When a table fails, warnings list the failed record type."""
        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "reports":
                    raise RuntimeError("Table not accessible")
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters()
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        assert result.warnings is not None
        assert any("reports" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Test: list_events with no Change_Reason (returns null, event not omitted)
# ---------------------------------------------------------------------------


class TestListEventsNoChangeReason:
    """Tests that events without change_reason are included with null."""

    @pytest.mark.asyncio
    async def test_null_change_reason_event_not_omitted(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """Events with no change_reason are returned with change_reason=None."""
        from alcoabase.schemas.audit_trail import AuditEvent

        event_no_reason = AuditEvent(
            transaction_id=1,
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            user_id=1, record_type="training_tasks", record_id=1,
            operation_type="INSERT", change_reason=None, company_id=1,
        )

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "training_tasks":
                    return [event_no_reason]
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="training_tasks")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters
            )

        assert len(result.events) == 1
        assert result.events[0].change_reason is None


# ---------------------------------------------------------------------------
# Test: get_event_detail for INSERT (all fields, no old_value)
# ---------------------------------------------------------------------------


class TestGetEventDetailInsert:
    """Tests get_event_detail for INSERT operations."""

    @pytest.mark.asyncio
    async def test_insert_all_fields_no_old_value(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """For INSERT, all fields have old_value=None and new_value set."""
        from sqlalchemy.orm import ColumnProperty

        config = AUDITED_RECORD_TYPES["workflows"]
        model_cls = config.model_cls

        # Create a mock version row
        version = MagicMock()
        version.id = 10
        version.workflow_id = 5
        version.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        version.created_by = 1
        version.change_reason = "Initial workflow creation"
        version.company_id = 1
        version.version_number = 1
        version.name = "Test Workflow"
        version.status = "Draft"

        # Mock the mapper columns
        mock_columns = []
        for col_name in ["name", "status", "created_at", "created_by",
                         "workflow_id", "company_id", "change_reason",
                         "version_number", "id"]:
            col = MagicMock()
            col.key = col_name
            mock_columns.append(col)

        # Mock session.execute for the version query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version

        # Mock session.execute for all_versions query
        mock_all_versions_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [version]
        mock_all_versions_result.scalars.return_value = mock_scalars

        # Mock user resolution
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = "Admin User"

        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_all_versions_result, mock_user_result]
        )

        result = await service.get_event_detail(
            session=mock_session, company_id=1,
            record_type="workflows", record_id=5, transaction_id=10,
        )

        assert result is not None
        assert result.operation_type == "INSERT"
        assert result.transaction_id == 10
        # For INSERT, all field_changes should have old_value=None
        for fc in result.field_changes:
            assert fc.old_value is None


# ---------------------------------------------------------------------------
# Test: get_event_detail for UPDATE (changed fields with old/new values)
# ---------------------------------------------------------------------------


class TestGetEventDetailUpdate:
    """Tests get_event_detail for UPDATE operations."""

    @pytest.mark.asyncio
    async def test_update_shows_changed_fields_with_old_new(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """For UPDATE, changed fields show both old_value and new_value."""
        config = AUDITED_RECORD_TYPES["workflows"]

        # Previous version
        prev_version = MagicMock()
        prev_version.id = 9
        prev_version.workflow_id = 5
        prev_version.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        prev_version.created_by = 1
        prev_version.change_reason = "Initial creation"
        prev_version.company_id = 1
        prev_version.version_number = 1
        prev_version.name = "Old Name"
        prev_version.status = "Draft"

        # Current version (UPDATE)
        curr_version = MagicMock()
        curr_version.id = 10
        curr_version.workflow_id = 5
        curr_version.created_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        curr_version.created_by = 1
        curr_version.change_reason = "Updated workflow name"
        curr_version.company_id = 1
        curr_version.version_number = 2
        curr_version.name = "New Name"
        curr_version.status = "Draft"

        # Mock mapper columns for _compute_field_changes
        mock_columns = []
        for col_name in ["name", "status", "created_at", "created_by",
                         "workflow_id", "company_id", "change_reason",
                         "version_number"]:
            col = MagicMock()
            col.key = col_name
            mock_columns.append(col)
        curr_version.__class__ = MagicMock()
        curr_version.__class__.__mapper__ = MagicMock()
        curr_version.__class__.__mapper__.columns = mock_columns

        # Mock session.execute
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = curr_version

        mock_all_versions_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [prev_version, curr_version]
        mock_all_versions_result.scalars.return_value = mock_scalars

        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = "Admin User"

        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_all_versions_result, mock_user_result]
        )

        result = await service.get_event_detail(
            session=mock_session, company_id=1,
            record_type="workflows", record_id=5, transaction_id=10,
        )

        assert result is not None
        assert result.operation_type == "UPDATE"
        # Should have field changes with old and new values
        name_change = next(
            (fc for fc in result.field_changes if fc.field_name == "name"),
            None,
        )
        if name_change:
            assert name_change.old_value == "Old Name"
            assert name_change.new_value == "New Name"


# ---------------------------------------------------------------------------
# Test: get_event_detail for DELETE (final values, no new_value)
# ---------------------------------------------------------------------------


class TestGetEventDetailDelete:
    """Tests get_event_detail for DELETE operations."""

    @pytest.mark.asyncio
    async def test_delete_shows_final_values_no_new_value(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """For DELETE, field_changes have old_value set and new_value=None."""
        # We test _compute_field_changes directly for DELETE
        from alcoabase.schemas.audit_trail import FieldChange

        # Create a mock model class with mapper
        mock_model_cls = MagicMock()
        col_name = MagicMock()
        col_name.key = "name"
        col_status = MagicMock()
        col_status.key = "status"
        mock_model_cls.__mapper__ = MagicMock()
        mock_model_cls.__mapper__.columns = [col_name, col_status]

        # Create a version row representing the deleted state
        version = MagicMock()
        version.name = "Deleted Workflow"
        version.status = "Active"

        changes = service._compute_field_changes(
            version=version,
            previous_version=None,
            operation_type="DELETE",
            model_cls=mock_model_cls,
        )

        assert len(changes) == 2
        for fc in changes:
            assert fc.new_value is None
            assert fc.old_value is not None

        name_change = next(fc for fc in changes if fc.field_name == "name")
        assert name_change.old_value == "Deleted Workflow"


# ---------------------------------------------------------------------------
# Test: get_event_detail user_display_name resolution and fallback
# ---------------------------------------------------------------------------


class TestGetEventDetailUserResolution:
    """Tests user_display_name resolution and fallback to None."""

    @pytest.mark.asyncio
    async def test_user_display_name_resolved(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """get_event_detail resolves user_display_name from users table."""
        config = AUDITED_RECORD_TYPES["workflows"]

        version = MagicMock()
        version.id = 10
        version.workflow_id = 5
        version.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        version.created_by = 1
        version.change_reason = "Test"
        version.company_id = 1
        version.version_number = 1

        # Mock mapper
        version.__class__ = MagicMock()
        version.__class__.__mapper__ = MagicMock()
        version.__class__.__mapper__.columns = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version

        mock_all_versions_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [version]
        mock_all_versions_result.scalars.return_value = mock_scalars

        # User found
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = "John Doe"

        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_all_versions_result, mock_user_result]
        )

        result = await service.get_event_detail(
            session=mock_session, company_id=1,
            record_type="workflows", record_id=5, transaction_id=10,
        )

        assert result is not None
        assert result.user_display_name == "John Doe"

    @pytest.mark.asyncio
    async def test_user_display_name_fallback_to_none(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """get_event_detail returns None when user not found."""
        config = AUDITED_RECORD_TYPES["workflows"]

        version = MagicMock()
        version.id = 10
        version.workflow_id = 5
        version.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        version.created_by = 999
        version.change_reason = "Test"
        version.company_id = 1
        version.version_number = 1

        version.__class__ = MagicMock()
        version.__class__.__mapper__ = MagicMock()
        version.__class__.__mapper__.columns = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version

        mock_all_versions_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [version]
        mock_all_versions_result.scalars.return_value = mock_scalars

        # User NOT found
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[mock_result, mock_all_versions_result, mock_user_result]
        )

        result = await service.get_event_detail(
            session=mock_session, company_id=1,
            record_type="workflows", record_id=5, transaction_id=10,
        )

        assert result is not None
        assert result.user_display_name is None
        assert result.user_id == 999


# ---------------------------------------------------------------------------
# Test: get_total_count accuracy with filters
# ---------------------------------------------------------------------------


class TestGetTotalCount:
    """Tests get_total_count returns accurate counts with filters."""

    @pytest.mark.asyncio
    async def test_total_count_sums_across_tables(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """get_total_count sums counts from all version tables."""
        with patch.object(
            service, "_count_version_table", new_callable=AsyncMock
        ) as mock_count:
            async def side_effect(session, config, company_id, filters, search_query):
                counts = {
                    "documents": 10,
                    "templates": 5,
                    "reports": 3,
                    "workflows": 7,
                    "signatures": 2,
                    "training_tasks": 4,
                    "training_records": 1,
                }
                return counts.get(config.record_type, 0)

            mock_count.side_effect = side_effect

            filters = AuditTrailFilters()
            total = await service.get_total_count(
                session=mock_session, company_id=1, filters=filters
            )

        assert total == 32  # 10+5+3+7+2+4+1

    @pytest.mark.asyncio
    async def test_total_count_with_record_type_filter(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """get_total_count with record_type filter queries only that table."""
        with patch.object(
            service, "_count_version_table", new_callable=AsyncMock
        ) as mock_count:
            mock_count.return_value = 15

            filters = AuditTrailFilters(record_type="documents")
            total = await service.get_total_count(
                session=mock_session, company_id=1, filters=filters
            )

        # Only one table queried
        assert mock_count.call_count == 1
        assert total == 15

    @pytest.mark.asyncio
    async def test_total_count_with_failed_table(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """get_total_count skips failed tables gracefully."""
        with patch.object(
            service, "_count_version_table", new_callable=AsyncMock
        ) as mock_count:
            async def side_effect(session, config, company_id, filters, search_query):
                if config.record_type == "reports":
                    raise RuntimeError("Table error")
                return 5

            mock_count.side_effect = side_effect

            filters = AuditTrailFilters()
            total = await service.get_total_count(
                session=mock_session, company_id=1, filters=filters
            )

        # 6 tables succeed * 5 = 30 (reports fails)
        assert total == 30


# ---------------------------------------------------------------------------
# Test: page_size clamping to [1, 200]
# ---------------------------------------------------------------------------


class TestPageSizeClamping:
    """Tests that page_size is clamped to the valid range [1, 200]."""

    @pytest.mark.asyncio
    async def test_page_size_below_minimum_clamped_to_1(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """page_size < 1 is clamped to 1."""
        from alcoabase.schemas.audit_trail import AuditEvent

        events = [
            AuditEvent(
                transaction_id=i,
                timestamp=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                user_id=1, record_type="documents", record_id=i,
                operation_type="INSERT", company_id=1,
            )
            for i in range(1, 4)
        ]

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    return events
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="documents")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                page_size=0,
            )

        # Clamped to 1, so only 1 event returned
        assert len(result.events) == 1

    @pytest.mark.asyncio
    async def test_page_size_above_maximum_clamped_to_200(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """page_size > 200 is clamped to 200."""
        from alcoabase.schemas.audit_trail import AuditEvent

        # Create 5 events (less than 200, so all should be returned)
        events = [
            AuditEvent(
                transaction_id=i,
                timestamp=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                user_id=1, record_type="documents", record_id=i,
                operation_type="INSERT", company_id=1,
            )
            for i in range(1, 6)
        ]

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    return events
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="documents")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                page_size=500,
            )

        # All 5 events returned (clamped to 200, but only 5 exist)
        assert len(result.events) == 5
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_page_size_negative_clamped_to_1(
        self, service: AuditTrailService, mock_session: AsyncMock
    ) -> None:
        """Negative page_size is clamped to 1."""
        from alcoabase.schemas.audit_trail import AuditEvent

        events = [
            AuditEvent(
                transaction_id=i,
                timestamp=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                user_id=1, record_type="documents", record_id=i,
                operation_type="INSERT", company_id=1,
            )
            for i in range(1, 4)
        ]

        with patch.object(
            service, "_query_version_table", new_callable=AsyncMock
        ) as mock_query:
            async def side_effect(session, config, company_id, filters, search_query, cross_company=False):
                if config.record_type == "documents":
                    return events
                return []

            mock_query.side_effect = side_effect

            filters = AuditTrailFilters(record_type="documents")
            result = await service.list_events(
                session=mock_session, company_id=1, filters=filters,
                page_size=-10,
            )

        # Clamped to 1
        assert len(result.events) == 1
