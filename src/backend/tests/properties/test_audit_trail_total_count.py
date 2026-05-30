"""Property-based tests for Audit Trail Total Count Accuracy.

Tests Property 7 from the Step_6-3_audit-trail-viewer design document,
validating that the total_count returned in AuditTrailPage equals the
number of events satisfying all applied filter and search criteria.

**Validates: Requirements 2.3**

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md (Property 7)
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.schemas.audit_trail import AuditEvent, AuditTrailFilters
from alcoabase.services.audit_trail_service import (
    AUDITED_RECORD_TYPES,
    AuditTrailService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

ALL_RECORD_TYPES = list(AUDITED_RECORD_TYPES.keys())
VALID_OPERATION_TYPES = ["INSERT", "UPDATE", "DELETE"]


@st.composite
def st_audit_event(
    draw: st.DrawFn,
    company_id: int = 1,
) -> AuditEvent:
    """Generate a valid AuditEvent with randomized fields.

    Args:
        draw: Hypothesis draw function.
        company_id: Company ID to assign to the event.

    Returns:
        A valid AuditEvent instance.
    """
    transaction_id = draw(st.integers(min_value=1, max_value=100_000))
    timestamp = draw(
        st.datetimes(
            min_value=datetime(2022, 1, 1),
            max_value=datetime(2025, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    user_id = draw(st.integers(min_value=1, max_value=100))
    user_display_name = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(whitelist_categories=("L", "Zs")),
            ).filter(lambda s: s.strip()),
        )
    )
    record_type = draw(st.sampled_from(ALL_RECORD_TYPES))
    record_id = draw(st.integers(min_value=1, max_value=10_000))
    operation_type = draw(st.sampled_from(VALID_OPERATION_TYPES))
    change_reason = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=1,
                max_size=100,
                alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            ).filter(lambda s: s.strip()),
        )
    )
    num_fields = draw(st.integers(min_value=0, max_value=20))
    changed_fields = [f"field_{i}" for i in range(min(num_fields, 10))]

    return AuditEvent(
        transaction_id=transaction_id,
        timestamp=timestamp,
        user_id=user_id,
        user_display_name=user_display_name,
        record_type=record_type,
        record_id=record_id,
        operation_type=operation_type,
        change_reason=change_reason,
        changed_fields=changed_fields,
        total_changed_fields=num_fields,
        company_id=company_id,
    )


@st.composite
def st_dataset(draw: st.DrawFn) -> list[AuditEvent]:
    """Generate a dataset of audit events (5 to 50 events).

    Returns:
        A list of AuditEvent instances all belonging to company_id=1.
    """
    num_events = draw(st.integers(min_value=5, max_value=50))
    events = draw(
        st.lists(
            st_audit_event(company_id=1),
            min_size=num_events,
            max_size=num_events,
        )
    )
    return events


@st.composite
def st_filters(draw: st.DrawFn, dataset: list[AuditEvent]) -> AuditTrailFilters:
    """Generate filter criteria that may or may not match events in the dataset.

    Picks filter values from the dataset to ensure some events match,
    but also allows None (no filter) for each field.

    Args:
        draw: Hypothesis draw function.
        dataset: The dataset to potentially pick filter values from.

    Returns:
        An AuditTrailFilters instance.
    """
    # Decide which filters to apply (each has a chance of being None)
    user_id = None
    if draw(st.booleans()):
        # Pick a user_id from the dataset so at least some events match
        user_id = draw(st.sampled_from([e.user_id for e in dataset]))

    date_start = None
    date_end = None
    if draw(st.booleans()):
        # Pick a date range that covers some events
        timestamps = [e.timestamp for e in dataset]
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        # Strip tzinfo for hypothesis datetimes strategy (requires naive min/max)
        min_naive = min_ts.replace(tzinfo=None) - timedelta(days=30)
        max_naive = max_ts.replace(tzinfo=None)
        # Clamp to valid datetime range
        if min_naive < datetime(2020, 1, 1):
            min_naive = datetime(2020, 1, 1)
        # Generate a start within the range
        date_start = draw(
            st.datetimes(
                min_value=min_naive,
                max_value=max_naive,
                timezones=st.just(timezone.utc),
            )
        )
        # Generate end after start
        end_min_naive = date_start.replace(tzinfo=None)
        end_max_naive = max_ts.replace(tzinfo=None) + timedelta(days=30)
        if end_max_naive > datetime(2026, 12, 31):
            end_max_naive = datetime(2026, 12, 31)
        date_end = draw(
            st.datetimes(
                min_value=end_min_naive,
                max_value=end_max_naive,
                timezones=st.just(timezone.utc),
            )
        )

    record_type = None
    if draw(st.booleans()):
        record_type = draw(st.sampled_from([e.record_type for e in dataset]))

    operation_type = None
    if draw(st.booleans()):
        operation_type = draw(st.sampled_from([e.operation_type for e in dataset]))

    return AuditTrailFilters(
        user_id=user_id,
        date_start=date_start,
        date_end=date_end,
        record_type=record_type,
        operation_type=operation_type,
    )


@st.composite
def st_search_query(draw: st.DrawFn, dataset: list[AuditEvent]) -> str | None:
    """Generate a search query that may match events in the dataset.

    Either returns None (no search) or a substring from one of the
    searchable fields in the dataset.

    Args:
        draw: Hypothesis draw function.
        dataset: The dataset to pick search terms from.

    Returns:
        A search query string or None.
    """
    if draw(st.booleans()):
        return None

    # Pick a searchable field value from the dataset
    searchable_values: list[str] = []
    for event in dataset:
        if event.change_reason:
            searchable_values.append(event.change_reason)
        searchable_values.append(event.record_type)
        if event.user_display_name:
            searchable_values.append(event.user_display_name)
        searchable_values.append(str(event.record_id))

    if not searchable_values:
        return None

    source = draw(st.sampled_from(searchable_values))
    # Take a substring of length 1 to len(source)
    if len(source) <= 1:
        return source.lower()
    start = draw(st.integers(min_value=0, max_value=len(source) - 1))
    end = draw(st.integers(min_value=start + 1, max_value=len(source)))
    return source[start:end].lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_matches_filters(
    event: AuditEvent,
    filters: AuditTrailFilters,
) -> bool:
    """Check if an event satisfies all filter criteria.

    Args:
        event: The audit event to check.
        filters: The filter criteria to apply.

    Returns:
        True if the event satisfies all filters.
    """
    if filters.user_id is not None and event.user_id != filters.user_id:
        return False
    if filters.date_start is not None and event.timestamp < filters.date_start:
        return False
    if filters.date_end is not None and event.timestamp > filters.date_end:
        return False
    if filters.record_type is not None and event.record_type != filters.record_type:
        return False
    if filters.operation_type is not None and event.operation_type != filters.operation_type:
        return False
    return True


def _event_matches_search(event: AuditEvent, search_query: str) -> bool:
    """Check if an event matches a search query (case-insensitive substring).

    The search matches against: change_reason, record_type,
    user_display_name, and record_id as string.

    Args:
        event: The audit event to check.
        search_query: The search query (lowercase).

    Returns:
        True if the event matches the search query.
    """
    query = search_query.lower()
    searchable_fields = [
        event.record_type,
        str(event.record_id),
    ]
    if event.change_reason:
        searchable_fields.append(event.change_reason)
    if event.user_display_name:
        searchable_fields.append(event.user_display_name)

    return any(query in field.lower() for field in searchable_fields)


def _count_matching_events(
    dataset: list[AuditEvent],
    filters: AuditTrailFilters,
    search_query: str | None,
) -> int:
    """Count events in the dataset that satisfy all filters and search.

    Args:
        dataset: The full dataset of events.
        filters: Filter criteria to apply.
        search_query: Optional search query.

    Returns:
        Number of events satisfying all criteria.
    """
    count = 0
    for event in dataset:
        if not _event_matches_filters(event, filters):
            continue
        if search_query and not _event_matches_search(event, search_query):
            continue
        count += 1
    return count


def _filter_dataset(
    dataset: list[AuditEvent],
    filters: AuditTrailFilters,
    search_query: str | None,
) -> list[AuditEvent]:
    """Filter the dataset according to filters and search query.

    Args:
        dataset: The full dataset of events.
        filters: Filter criteria to apply.
        search_query: Optional search query.

    Returns:
        List of events satisfying all criteria.
    """
    result = []
    for event in dataset:
        if not _event_matches_filters(event, filters):
            continue
        if search_query and not _event_matches_search(event, search_query):
            continue
        result.append(event)
    return result


# ---------------------------------------------------------------------------
# Property 7: Total count accuracy
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 7: Total count accuracy
@settings(max_examples=100, deadline=None)
@given(data=st.data())
@pytest.mark.asyncio
async def test_total_count_equals_matching_events(
    data: st.DataObject,
) -> None:
    """For any combination of filters and search query, the total_count
    returned SHALL equal the number of events that satisfy all applied
    criteria.

    This test generates a dataset of audit events, applies random
    combinations of filters and search queries, and verifies that
    total_count in the AuditTrailPage response matches the actual
    count of events satisfying all criteria.

    **Validates: Requirements 2.3**
    """
    # Generate dataset
    dataset = data.draw(st_dataset())

    # Generate filters based on the dataset
    filters = data.draw(st_filters(dataset))

    # Generate search query based on the dataset
    search_query = data.draw(st_search_query(dataset))

    # Calculate expected count using our reference implementation
    expected_count = _count_matching_events(dataset, filters, search_query)

    # Mock _query_version_table to return the filtered dataset
    # The service applies filters internally via _query_version_table,
    # so we simulate it returning only events matching the filters/search
    # for the appropriate record types.
    service = AuditTrailService()

    async def mock_query_version_table(
        session, config, company_id, filters=None, search_query=None, cross_company=False
    ):
        """Return events from the dataset that match the given config's record_type
        and satisfy the filters and search query."""
        matching = []
        applied_filters = filters if filters else AuditTrailFilters()
        for event in dataset:
            if event.record_type != config.record_type:
                continue
            if not _event_matches_filters(event, applied_filters):
                continue
            if search_query and not _event_matches_search(event, search_query):
                continue
            matching.append(event)
        return matching

    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        result = await service.list_events(
            session=session,
            company_id=1,
            filters=filters,
            search_query=search_query,
            cursor=None,
            page_size=200,  # Large page to avoid pagination cutting results
        )

    # Property: total_count equals the number of events satisfying all criteria
    assert result.total_count == expected_count, (
        f"total_count mismatch: got {result.total_count}, "
        f"expected {expected_count}. "
        f"Filters: user_id={filters.user_id}, "
        f"date_start={filters.date_start}, date_end={filters.date_end}, "
        f"record_type={filters.record_type}, "
        f"operation_type={filters.operation_type}, "
        f"search_query={search_query!r}"
    )


# Feature: Step_6-3_audit-trail-viewer, Property 7: Total count accuracy
@settings(max_examples=100, deadline=None)
@given(data=st.data())
@pytest.mark.asyncio
async def test_total_count_matches_actual_events_returned_without_pagination(
    data: st.DataObject,
) -> None:
    """For any combination of filters and search query, when page_size is
    large enough to hold all results, total_count SHALL equal the number
    of events actually returned in the page.

    This verifies consistency between total_count and the events list
    when pagination does not truncate results.

    **Validates: Requirements 2.3**
    """
    # Generate dataset
    dataset = data.draw(st_dataset())

    # Generate filters based on the dataset
    filters = data.draw(st_filters(dataset))

    # Generate search query based on the dataset
    search_query = data.draw(st_search_query(dataset))

    service = AuditTrailService()

    async def mock_query_version_table(
        session, config, company_id, filters=None, search_query=None, cross_company=False
    ):
        """Return events from the dataset matching the config's record_type
        and satisfying filters and search."""
        matching = []
        applied_filters = filters if filters else AuditTrailFilters()
        for event in dataset:
            if event.record_type != config.record_type:
                continue
            if not _event_matches_filters(event, applied_filters):
                continue
            if search_query and not _event_matches_search(event, search_query):
                continue
            matching.append(event)
        return matching

    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        result = await service.list_events(
            session=session,
            company_id=1,
            filters=filters,
            search_query=search_query,
            cursor=None,
            page_size=200,  # Max page size to avoid pagination
        )

    # Property: total_count equals len(events) when no pagination truncation
    assert result.total_count == len(result.events), (
        f"total_count ({result.total_count}) should equal len(events) "
        f"({len(result.events)}) when page_size is large enough to hold "
        f"all results. Filters: user_id={filters.user_id}, "
        f"record_type={filters.record_type}, "
        f"operation_type={filters.operation_type}, "
        f"search_query={search_query!r}"
    )
