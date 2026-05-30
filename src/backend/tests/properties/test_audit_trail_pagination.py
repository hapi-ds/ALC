"""Property-based tests for Audit Trail Pagination Completeness (Step 6.3).

Tests Property 6 from the audit-trail-viewer design document, validating
that cursor-based pagination with page_size clamped to [1, 200] yields
every matching event exactly once with no duplicates and no gaps when
iterating through all pages.

**Validates: Requirements 2.1, 2.2**

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md (Property 6)
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md
"""

from __future__ import annotations

from datetime import datetime, timezone
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
    """Generate a valid AuditEvent with unique identity.

    Args:
        draw: Hypothesis draw function.
        company_id: Fixed company_id for tenant scoping.

    Returns:
        A valid AuditEvent instance.
    """
    transaction_id = draw(st.integers(min_value=1, max_value=1_000_000))
    timestamp = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2025, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    user_id = draw(st.integers(min_value=1, max_value=10000))
    record_type = draw(st.sampled_from(ALL_RECORD_TYPES))
    record_id = draw(st.integers(min_value=1, max_value=100000))
    operation_type = draw(st.sampled_from(VALID_OPERATION_TYPES))
    change_reason = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))

    return AuditEvent(
        transaction_id=transaction_id,
        timestamp=timestamp,
        user_id=user_id,
        user_display_name=None,
        record_type=record_type,
        record_id=record_id,
        operation_type=operation_type,
        change_reason=change_reason,
        changed_fields=[],
        total_changed_fields=0,
        company_id=company_id,
    )


@st.composite
def st_unique_audit_events(draw: st.DrawFn) -> list[AuditEvent]:
    """Generate a list of audit events with unique composite keys.

    Each event has a unique (timestamp, transaction_id, record_type) tuple
    to ensure cursor-based pagination can distinguish them.

    Returns:
        A list of AuditEvent instances with unique composite keys.
    """
    company_id = draw(st.integers(min_value=1, max_value=100))
    num_events = draw(st.integers(min_value=1, max_value=50))

    events: list[AuditEvent] = []
    seen_keys: set[tuple[datetime, int, str]] = set()

    for _ in range(num_events):
        # Generate events ensuring unique composite cursor keys
        event = draw(st_audit_event(company_id=company_id))
        key = (event.timestamp, event.transaction_id, event.record_type)

        # Ensure uniqueness by adjusting transaction_id if needed
        attempts = 0
        while key in seen_keys and attempts < 100:
            event = draw(st_audit_event(company_id=company_id))
            key = (event.timestamp, event.transaction_id, event.record_type)
            attempts += 1

        if key not in seen_keys:
            seen_keys.add(key)
            events.append(event)

    return events


# ---------------------------------------------------------------------------
# Property 6: Pagination completeness with page size clamping
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 6: Pagination completeness with page size clamping
@settings(max_examples=100, deadline=None)
@given(
    events=st_unique_audit_events(),
    page_size=st.integers(min_value=1, max_value=200),
)
@pytest.mark.asyncio
async def test_pagination_completeness_no_duplicates_no_gaps(
    events: list[AuditEvent],
    page_size: int,
) -> None:
    """For any dataset of audit events and any sequence of cursor-based page
    requests with page_size in [1, 200], iterating through all pages SHALL
    yield every matching event exactly once with no duplicates and no gaps.

    **Validates: Requirements 2.1, 2.2**
    """
    service = AuditTrailService()
    filters = AuditTrailFilters()
    company_id = events[0].company_id if events else 1

    # Mock _query_version_table to return our known set of events
    # The service queries each record type separately, so we distribute
    # events by their record_type
    events_by_type: dict[str, list[AuditEvent]] = {}
    for event in events:
        events_by_type.setdefault(event.record_type, []).append(event)

    async def mock_query_version_table(
        session, config, company_id, filters, search_query, cross_company=False
    ):
        """Return pre-generated events for the given record type."""
        return events_by_type.get(config.record_type, [])

    # Iterate through all pages collecting results
    collected_events: list[AuditEvent] = []
    cursor: str | None = None
    max_iterations = len(events) + 2  # Safety bound to prevent infinite loops

    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        iteration = 0

        while iteration < max_iterations:
            result = await service.list_events(
                session=session,
                company_id=company_id,
                filters=filters,
                search_query=None,
                cursor=cursor,
                page_size=page_size,
            )

            collected_events.extend(result.events)
            cursor = result.next_cursor
            iteration += 1

            # Stop when there's no next page
            if cursor is None:
                break

    # Property 1: Every event from the input appears in the collected output
    # (no gaps)
    input_keys = {
        (e.timestamp, e.transaction_id, e.record_type) for e in events
    }
    output_keys = {
        (e.timestamp, e.transaction_id, e.record_type) for e in collected_events
    }

    missing = input_keys - output_keys
    assert not missing, (
        f"Pagination missed {len(missing)} events. "
        f"Missing keys (timestamp, transaction_id, record_type): "
        f"{list(missing)[:5]}"
    )

    # Property 2: No duplicates in the collected output
    assert len(output_keys) == len(collected_events), (
        f"Pagination produced duplicates. "
        f"Collected {len(collected_events)} events but only "
        f"{len(output_keys)} unique keys. "
        f"Duplicates: {len(collected_events) - len(output_keys)}"
    )

    # Property 3: Total count equals the number of input events
    # (verified on first page since total_count is consistent)
    assert len(collected_events) == len(events), (
        f"Expected {len(events)} total events across all pages, "
        f"got {len(collected_events)}"
    )


# Feature: Step_6-3_audit-trail-viewer, Property 6: Pagination completeness with page size clamping
@settings(max_examples=100, deadline=None)
@given(
    events=st_unique_audit_events(),
    raw_page_size=st.integers(min_value=-100, max_value=500),
)
@pytest.mark.asyncio
async def test_page_size_clamping_preserves_completeness(
    events: list[AuditEvent],
    raw_page_size: int,
) -> None:
    """For any page_size value (including out-of-range values), the service
    SHALL clamp page_size to [1, 200] and still yield every matching event
    exactly once when iterating through all pages.

    This verifies that page_size clamping does not break pagination
    completeness.

    **Validates: Requirements 2.1, 2.2**
    """
    service = AuditTrailService()
    filters = AuditTrailFilters()
    company_id = events[0].company_id if events else 1

    # Expected clamped page_size
    expected_page_size = max(1, min(200, raw_page_size))

    # Mock _query_version_table to return our known set of events
    events_by_type: dict[str, list[AuditEvent]] = {}
    for event in events:
        events_by_type.setdefault(event.record_type, []).append(event)

    async def mock_query_version_table(
        session, config, company_id, filters, search_query, cross_company=False
    ):
        """Return pre-generated events for the given record type."""
        return events_by_type.get(config.record_type, [])

    # Iterate through all pages
    collected_events: list[AuditEvent] = []
    cursor: str | None = None
    max_iterations = len(events) + 2

    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        iteration = 0
        page_sizes_observed: list[int] = []

        while iteration < max_iterations:
            result = await service.list_events(
                session=session,
                company_id=company_id,
                filters=filters,
                search_query=None,
                cursor=cursor,
                page_size=raw_page_size,
            )

            page_sizes_observed.append(len(result.events))
            collected_events.extend(result.events)
            cursor = result.next_cursor
            iteration += 1

            if cursor is None:
                break

    # Property 1: Page size clamping — no page exceeds the clamped max
    for i, observed_size in enumerate(page_sizes_observed):
        assert observed_size <= expected_page_size, (
            f"Page {i} returned {observed_size} events, exceeding "
            f"clamped page_size of {expected_page_size}"
        )

    # Property 2: All events are collected (completeness preserved)
    input_keys = {
        (e.timestamp, e.transaction_id, e.record_type) for e in events
    }
    output_keys = {
        (e.timestamp, e.transaction_id, e.record_type) for e in collected_events
    }

    missing = input_keys - output_keys
    assert not missing, (
        f"Page size clamping caused {len(missing)} events to be missed. "
        f"Raw page_size={raw_page_size}, clamped={expected_page_size}"
    )

    # Property 3: No duplicates
    assert len(output_keys) == len(collected_events), (
        f"Page size clamping caused duplicates. "
        f"Raw page_size={raw_page_size}, clamped={expected_page_size}. "
        f"Collected {len(collected_events)} events but only "
        f"{len(output_keys)} unique."
    )
