"""Property-based tests for Audit Trail Filter AND-combination with search.

Tests Property 9 from the audit-trail-viewer design document, validating
that when multiple filters and a search query are applied simultaneously,
the result set equals the intersection of applying each filter and search
individually.

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md (Property 9)
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.schemas.audit_trail import AuditEvent, AuditTrailFilters, AuditTrailPage
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
    user_ids: list[int] | None = None,
) -> AuditEvent:
    """Generate a random AuditEvent with realistic field values.

    Args:
        draw: Hypothesis draw function.
        company_id: Fixed company_id for all events.
        user_ids: Pool of user IDs to draw from (for filter testing).

    Returns:
        A valid AuditEvent instance.
    """
    uid_pool = user_ids or list(range(1, 11))
    user_id = draw(st.sampled_from(uid_pool))

    timestamp = draw(
        st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2025, 6, 30),
            timezones=st.just(timezone.utc),
        )
    )

    record_type = draw(st.sampled_from(ALL_RECORD_TYPES))
    operation_type = draw(st.sampled_from(VALID_OPERATION_TYPES))

    # Generate change_reason with searchable content
    change_reason = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=1,
                max_size=100,
                alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
            ),
        )
    )

    # Generate user_display_name (searchable field)
    user_display_name = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(whitelist_categories=("L", "Zs")),
            ),
        )
    )

    record_id = draw(st.integers(min_value=1, max_value=10000))
    transaction_id = draw(st.integers(min_value=1, max_value=100000))

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
def st_filter_combination(draw: st.DrawFn, events: list[AuditEvent]) -> dict:
    """Generate a combination of filters and search query based on existing events.

    Draws filter values from the actual event data to ensure non-trivial
    intersections. Each filter is independently optional.

    Args:
        draw: Hypothesis draw function.
        events: The dataset of events to derive filter values from.

    Returns:
        A dict with keys: user_id, date_start, date_end, record_type,
        operation_type, search_query. Values are None if filter not applied.
    """
    result: dict = {
        "user_id": None,
        "date_start": None,
        "date_end": None,
        "record_type": None,
        "operation_type": None,
        "search_query": None,
    }

    # Ensure at least 2 filters are applied (to test AND-combination)
    filters_to_apply = draw(
        st.lists(
            st.sampled_from(
                ["user_id", "date_range", "record_type", "operation_type", "search"]
            ),
            min_size=2,
            max_size=5,
            unique=True,
        )
    )

    if "user_id" in filters_to_apply and events:
        # Pick a user_id that exists in the dataset
        result["user_id"] = draw(
            st.sampled_from([e.user_id for e in events])
        )

    if "date_range" in filters_to_apply and events:
        # Pick a date range that covers some events
        timestamps = sorted(e.timestamp for e in events)
        # Pick two indices to form a range
        idx1 = draw(st.integers(min_value=0, max_value=len(timestamps) - 1))
        idx2 = draw(st.integers(min_value=0, max_value=len(timestamps) - 1))
        start_idx, end_idx = min(idx1, idx2), max(idx1, idx2)
        result["date_start"] = timestamps[start_idx]
        result["date_end"] = timestamps[end_idx]

    if "record_type" in filters_to_apply and events:
        result["record_type"] = draw(
            st.sampled_from([e.record_type for e in events])
        )

    if "operation_type" in filters_to_apply and events:
        result["operation_type"] = draw(
            st.sampled_from([e.operation_type for e in events])
        )

    if "search" in filters_to_apply and events:
        # Pick a search term from existing event data (substring of a field)
        searchable_events = [
            e for e in events
            if e.change_reason or e.user_display_name
        ]
        if searchable_events:
            source_event = draw(st.sampled_from(searchable_events))
            # Choose which field to derive search from
            search_sources = []
            if source_event.change_reason:
                search_sources.append(source_event.change_reason)
            if source_event.user_display_name:
                search_sources.append(source_event.user_display_name)
            search_sources.append(source_event.record_type)
            search_sources.append(str(source_event.record_id))

            source_text = draw(st.sampled_from(search_sources))
            # Take a substring of length 1-min(5, len)
            if len(source_text) > 0:
                max_len = min(5, len(source_text))
                substr_len = draw(st.integers(min_value=1, max_value=max_len))
                start_pos = draw(
                    st.integers(
                        min_value=0,
                        max_value=len(source_text) - substr_len,
                    )
                )
                result["search_query"] = source_text[start_pos:start_pos + substr_len]

    return result


@st.composite
def st_dataset_with_filters(draw: st.DrawFn) -> tuple[list[AuditEvent], dict]:
    """Generate a dataset of audit events and a filter combination.

    Returns:
        A tuple of (events, filter_combination).
    """
    company_id = draw(st.integers(min_value=1, max_value=100))
    user_ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=1000),
            min_size=2,
            max_size=6,
            unique=True,
        )
    )

    # Generate 5-30 events
    num_events = draw(st.integers(min_value=5, max_value=30))
    events = draw(
        st.lists(
            st_audit_event(company_id=company_id, user_ids=user_ids),
            min_size=num_events,
            max_size=num_events,
        )
    )

    # Generate filter combination based on the events
    filter_combo = draw(st_filter_combination(events))

    return (events, filter_combo)


# ---------------------------------------------------------------------------
# Filter application helpers (pure functions for individual filter logic)
# ---------------------------------------------------------------------------


def _apply_user_filter(events: list[AuditEvent], user_id: int) -> set[int]:
    """Return indices of events matching user_id filter."""
    return {i for i, e in enumerate(events) if e.user_id == user_id}


def _apply_date_range_filter(
    events: list[AuditEvent],
    date_start: datetime | None,
    date_end: datetime | None,
) -> set[int]:
    """Return indices of events within the date range (inclusive)."""
    result = set(range(len(events)))
    if date_start is not None:
        result = {i for i in result if events[i].timestamp >= date_start}
    if date_end is not None:
        result = {i for i in result if events[i].timestamp <= date_end}
    return result


def _apply_record_type_filter(
    events: list[AuditEvent], record_type: str
) -> set[int]:
    """Return indices of events matching record_type filter."""
    return {i for i, e in enumerate(events) if e.record_type == record_type}


def _apply_operation_type_filter(
    events: list[AuditEvent], operation_type: str
) -> set[int]:
    """Return indices of events matching operation_type filter."""
    return {i for i, e in enumerate(events) if e.operation_type == operation_type}


def _apply_search_filter(events: list[AuditEvent], search_query: str) -> set[int]:
    """Return indices of events matching the search query (case-insensitive substring).

    Searches against: change_reason, record_type, user_display_name,
    and record_id as string.
    """
    query_lower = search_query.lower()
    result = set()
    for i, e in enumerate(events):
        searchable_fields = [
            e.record_type,
            str(e.record_id),
        ]
        if e.change_reason:
            searchable_fields.append(e.change_reason)
        if e.user_display_name:
            searchable_fields.append(e.user_display_name)

        for field in searchable_fields:
            if query_lower in field.lower():
                result.add(i)
                break

    return result


def _apply_all_filters_combined(
    events: list[AuditEvent], filter_combo: dict
) -> set[int]:
    """Apply all filters simultaneously (AND logic) and return matching indices."""
    # Start with all events
    result = set(range(len(events)))

    if filter_combo["user_id"] is not None:
        result &= _apply_user_filter(events, filter_combo["user_id"])

    if filter_combo["date_start"] is not None or filter_combo["date_end"] is not None:
        result &= _apply_date_range_filter(
            events, filter_combo["date_start"], filter_combo["date_end"]
        )

    if filter_combo["record_type"] is not None:
        result &= _apply_record_type_filter(events, filter_combo["record_type"])

    if filter_combo["operation_type"] is not None:
        result &= _apply_operation_type_filter(
            events, filter_combo["operation_type"]
        )

    if filter_combo["search_query"] is not None:
        result &= _apply_search_filter(events, filter_combo["search_query"])

    return result


# ---------------------------------------------------------------------------
# Property 9: Filter AND-combination with search
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 9: Filter AND-combination with search
@settings(max_examples=100, deadline=None)
@given(data=st_dataset_with_filters())
@pytest.mark.asyncio
async def test_filter_and_combination_with_search(
    data: tuple[list[AuditEvent], dict],
) -> None:
    """For any combination of filters and search query applied simultaneously,
    the result set SHALL equal the intersection of applying each filter and
    the search individually.

    This test:
    1. Generates a dataset of audit events
    2. Generates a combination of multiple filters + optional search
    3. Applies all filters combined (AND logic) to get expected result
    4. Computes the intersection of individual filter applications
    5. Verifies both approaches yield the same result set
    6. Verifies the service returns exactly the expected events

    **Validates: Requirements 3.5, 5.3**
    """
    events, filter_combo = data

    if not events:
        return  # Skip empty datasets

    # Compute expected result via combined application (AND logic)
    expected_indices = _apply_all_filters_combined(events, filter_combo)

    # Compute expected result via intersection of individual filters
    individual_results: list[set[int]] = []

    if filter_combo["user_id"] is not None:
        individual_results.append(
            _apply_user_filter(events, filter_combo["user_id"])
        )

    if filter_combo["date_start"] is not None or filter_combo["date_end"] is not None:
        individual_results.append(
            _apply_date_range_filter(
                events, filter_combo["date_start"], filter_combo["date_end"]
            )
        )

    if filter_combo["record_type"] is not None:
        individual_results.append(
            _apply_record_type_filter(events, filter_combo["record_type"])
        )

    if filter_combo["operation_type"] is not None:
        individual_results.append(
            _apply_operation_type_filter(events, filter_combo["operation_type"])
        )

    if filter_combo["search_query"] is not None:
        individual_results.append(
            _apply_search_filter(events, filter_combo["search_query"])
        )

    # Intersection of all individual filter results
    if individual_results:
        intersection_indices = individual_results[0]
        for result_set in individual_results[1:]:
            intersection_indices &= result_set
    else:
        intersection_indices = set(range(len(events)))

    # Property 1: Combined application equals intersection of individual applications
    assert expected_indices == intersection_indices, (
        f"Combined filter application must equal intersection of individual "
        f"filter applications.\n"
        f"Combined result indices: {sorted(expected_indices)}\n"
        f"Intersection result indices: {sorted(intersection_indices)}\n"
        f"Filters applied: {filter_combo}"
    )

    # Property 2: Verify via the service that the same result is produced
    # Mock _query_version_table to return our generated events filtered
    # by the service's internal logic
    service = AuditTrailService()
    test_company_id = events[0].company_id if events else 1

    # Build the filters object
    test_filters = AuditTrailFilters(
        user_id=filter_combo["user_id"],
        date_start=filter_combo["date_start"],
        date_end=filter_combo["date_end"],
        record_type=filter_combo["record_type"],
        operation_type=filter_combo["operation_type"],
    )
    test_search_query = filter_combo["search_query"]

    # Mock _query_version_table to simulate filtering at the DB level
    # The service applies filters inside _query_version_table, so we
    # simulate what the DB would return after applying those filters
    async def mock_query_version_table(
        session, config, company_id, filters, search_query, cross_company=False
    ):
        """Return events matching the config's record_type after applying filters."""
        matched_events = []
        for event in events:
            # Filter by record_type (the service queries per-table)
            if event.record_type != config.record_type:
                continue

            # Apply user_id filter
            if filters.user_id is not None and event.user_id != filters.user_id:
                continue

            # Apply date range filter
            if filters.date_start is not None and event.timestamp < filters.date_start:
                continue
            if filters.date_end is not None and event.timestamp > filters.date_end:
                continue

            # Apply operation_type filter
            if (
                filters.operation_type is not None
                and event.operation_type != filters.operation_type
            ):
                continue

            # Apply search query (ILIKE substring match)
            if search_query:
                query_lower = search_query.lower()
                searchable = [
                    event.record_type,
                    str(event.record_id),
                ]
                if event.change_reason:
                    searchable.append(event.change_reason)
                if event.user_display_name:
                    searchable.append(event.user_display_name)

                matched = any(
                    query_lower in field.lower() for field in searchable
                )
                if not matched:
                    continue

            matched_events.append(event)

        return matched_events

    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        page = await service.list_events(
            session=session,
            company_id=test_company_id,
            filters=test_filters,
            search_query=test_search_query,
            cursor=None,
            page_size=200,  # Large enough to get all results
        )

    # Get the set of events returned by the service
    service_event_set = {
        (e.transaction_id, e.record_type, e.record_id, e.timestamp)
        for e in page.events
    }

    # Get the expected set of events
    expected_event_set = {
        (
            events[i].transaction_id,
            events[i].record_type,
            events[i].record_id,
            events[i].timestamp,
        )
        for i in expected_indices
    }

    # Property 3: Service result matches expected intersection
    assert service_event_set == expected_event_set, (
        f"Service result must match the intersection of individual filters.\n"
        f"Service returned {len(service_event_set)} events, "
        f"expected {len(expected_event_set)} events.\n"
        f"Missing from service: {expected_event_set - service_event_set}\n"
        f"Extra in service: {service_event_set - expected_event_set}\n"
        f"Filters: {filter_combo}"
    )

    # Property 4: Every event in the result satisfies ALL filters
    for event in page.events:
        if filter_combo["user_id"] is not None:
            assert event.user_id == filter_combo["user_id"], (
                f"Event user_id={event.user_id} does not match "
                f"filter user_id={filter_combo['user_id']}"
            )

        if filter_combo["date_start"] is not None:
            assert event.timestamp >= filter_combo["date_start"], (
                f"Event timestamp={event.timestamp} is before "
                f"date_start={filter_combo['date_start']}"
            )

        if filter_combo["date_end"] is not None:
            assert event.timestamp <= filter_combo["date_end"], (
                f"Event timestamp={event.timestamp} is after "
                f"date_end={filter_combo['date_end']}"
            )

        if filter_combo["record_type"] is not None:
            assert event.record_type == filter_combo["record_type"], (
                f"Event record_type={event.record_type} does not match "
                f"filter record_type={filter_combo['record_type']}"
            )

        if filter_combo["operation_type"] is not None:
            assert event.operation_type == filter_combo["operation_type"], (
                f"Event operation_type={event.operation_type} does not match "
                f"filter operation_type={filter_combo['operation_type']}"
            )

        if filter_combo["search_query"] is not None:
            query_lower = filter_combo["search_query"].lower()
            searchable = [
                event.record_type,
                str(event.record_id),
            ]
            if event.change_reason:
                searchable.append(event.change_reason)
            if event.user_display_name:
                searchable.append(event.user_display_name)

            matched = any(query_lower in f.lower() for f in searchable)
            assert matched, (
                f"Event does not match search query "
                f"'{filter_combo['search_query']}'. "
                f"Searchable fields: {searchable}"
            )
