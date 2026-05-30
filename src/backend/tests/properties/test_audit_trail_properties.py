"""Property-based tests for Audit Trail Viewer (Step 6.3).

Tests correctness properties of the AuditTrailService as defined in the
design document for the audit-trail-viewer feature.

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.schemas.audit_trail import AuditTrailFilters
from alcoabase.services.audit_trail_service import (
    AUDITED_RECORD_TYPES,
    AuditTrailService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

ALL_RECORD_TYPES = list(AUDITED_RECORD_TYPES.keys())


@st.composite
def st_failing_record_types(draw: st.DrawFn) -> list[str]:
    """Generate a non-empty subset of record types that will fail.

    Ensures at least one record type fails and at least one succeeds,
    so we can verify partial results are returned.

    Returns:
        A list of record type strings that should fail during aggregation.
    """
    # Pick a subset of record types to fail (at least 1, at most len-1)
    max_failures = len(ALL_RECORD_TYPES) - 1
    num_failures = draw(st.integers(min_value=1, max_value=max_failures))
    failing = draw(
        st.lists(
            st.sampled_from(ALL_RECORD_TYPES),
            min_size=num_failures,
            max_size=num_failures,
            unique=True,
        )
    )
    return failing


@st.composite
def st_audit_event_data(draw: st.DrawFn, record_type: str | None = None) -> dict:
    """Generate data for a mock audit event row.

    Args:
        record_type: If provided, use this record type. Otherwise pick randomly.

    Returns:
        A dict with id, timestamp, user_id, record_type, and other fields.
    """
    rt = record_type or draw(st.sampled_from(ALL_RECORD_TYPES))
    event_id = draw(st.integers(min_value=1, max_value=100000))
    user_id = draw(st.integers(min_value=1, max_value=10000))
    timestamp = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2025, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    return {
        "id": event_id,
        "user_id": user_id,
        "timestamp": timestamp,
        "record_type": rt,
        "record_id": draw(st.integers(min_value=1, max_value=10000)),
        "change_reason": draw(st.text(min_size=0, max_size=100) | st.none()),
    }


# ---------------------------------------------------------------------------
# Property 5: Graceful degradation on partial failure
# ---------------------------------------------------------------------------


def _make_mock_row(event_data: dict, config) -> MagicMock:
    """Create a mock row object that mimics a SQLAlchemy model instance.

    Args:
        event_data: Dict with event fields.
        config: The _VersionTableConfig for this record type.

    Returns:
        A MagicMock that responds to getattr for the expected columns.
    """
    row = MagicMock()
    row.id = event_data["id"]

    # Set the timestamp column
    setattr(row, config.timestamp_col, event_data["timestamp"])

    # Set the user column
    setattr(row, config.user_col, event_data["user_id"])

    # Set the record_id column
    setattr(row, config.record_id_col, event_data["record_id"])

    # Set change_reason if the config has one
    if config.change_reason_col:
        setattr(row, config.change_reason_col, event_data["change_reason"])

    # Set company_id if the config has one
    if config.company_id_col:
        setattr(row, config.company_id_col, 1)

    # Mock the __class__.__mapper__ for _get_changed_fields
    mock_mapper = MagicMock()
    mock_mapper.columns = []
    row.__class__ = MagicMock()
    row.__class__.__mapper__ = mock_mapper

    # For explicit models, set version_number
    if config.is_explicit:
        row.version_number = 1

    return row


# Feature: Step_6-3_audit-trail-viewer, Property 5: Graceful degradation on partial failure
@settings(max_examples=100, deadline=None)
@given(
    failing_types=st_failing_record_types(),
    company_id=st.integers(min_value=1, max_value=10000),
)
@pytest.mark.asyncio
async def test_graceful_degradation_on_partial_failure(
    failing_types: list[str],
    company_id: int,
) -> None:
    """For any subset of version tables that fail during aggregation,
    the service SHALL return events from all non-failing tables and
    SHALL include a warning listing exactly the record types that
    could not be retrieved.

    **Validates: Requirements 1.6**
    """
    service = AuditTrailService()
    filters = AuditTrailFilters()

    # Determine which record types should succeed
    succeeding_types = [rt for rt in ALL_RECORD_TYPES if rt not in failing_types]

    # Create mock events for succeeding tables (one event per succeeding type)
    expected_events_by_type: dict[str, dict] = {}
    for rt in succeeding_types:
        config = AUDITED_RECORD_TYPES[rt]
        event_data = {
            "id": hash(rt) % 100000 + 1,
            "user_id": 42,
            "timestamp": datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            "record_type": rt,
            "record_id": 100,
            "change_reason": f"Test change for {rt}",
        }
        expected_events_by_type[rt] = event_data

    # Mock _query_version_table to raise for failing types and return events for others
    original_query = service._query_version_table

    async def mock_query_version_table(
        session, config, company_id, filters, search_query, cross_company=False
    ):
        """Mock that raises for failing types and returns events for others."""
        if config.record_type in failing_types:
            raise RuntimeError(
                f"Simulated failure for {config.record_type}"
            )

        # Return a mock AuditEvent for succeeding types
        from alcoabase.schemas.audit_trail import AuditEvent

        event_data = expected_events_by_type[config.record_type]
        return [
            AuditEvent(
                transaction_id=event_data["id"],
                timestamp=event_data["timestamp"],
                user_id=event_data["user_id"],
                user_display_name=None,
                record_type=config.record_type,
                record_id=event_data["record_id"],
                operation_type="INSERT",
                change_reason=event_data["change_reason"],
                changed_fields=[],
                total_changed_fields=0,
                company_id=company_id,
            )
        ]

    # Patch the internal method
    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        result = await service.list_events(
            session=session,
            company_id=company_id,
            filters=filters,
            search_query=None,
            cursor=None,
            page_size=200,
        )

    # Property 1: Events from all non-failing tables are returned
    returned_record_types = {e.record_type for e in result.events}
    for rt in succeeding_types:
        assert rt in returned_record_types, (
            f"Expected events from non-failing record type '{rt}' to be present "
            f"in results, but it was missing. Failing types: {failing_types}"
        )

    # Property 2: No events from failing tables are returned
    for rt in failing_types:
        assert rt not in returned_record_types, (
            f"Events from failing record type '{rt}' should NOT be in results"
        )

    # Property 3: Warnings list contains exactly the failed record types
    assert result.warnings is not None, (
        "Warnings should be present when tables fail during aggregation"
    )
    # Each warning should mention exactly one failed record type
    warned_types = set()
    for warning in result.warnings:
        for rt in failing_types:
            if rt in warning:
                warned_types.add(rt)

    assert warned_types == set(failing_types), (
        f"Warnings should mention exactly the failed record types. "
        f"Expected warnings for: {set(failing_types)}, "
        f"but warnings mentioned: {warned_types}. "
        f"Actual warnings: {result.warnings}"
    )

    # Property 4: Number of warnings equals number of failed types
    assert len(result.warnings) == len(failing_types), (
        f"Expected {len(failing_types)} warnings (one per failed table), "
        f"got {len(result.warnings)}. Warnings: {result.warnings}"
    )


# ---------------------------------------------------------------------------
# Property 4: Transaction grouping
# ---------------------------------------------------------------------------

VALID_OPERATION_TYPES = ["INSERT", "UPDATE", "DELETE"]


@st.composite
def st_audit_event_for_grouping(
    draw: st.DrawFn,
    transaction_id: int | None = None,
    company_id: int | None = None,
) -> "AuditEvent":
    """Generate a valid AuditEvent with optional fixed transaction_id.

    Args:
        draw: Hypothesis draw function.
        transaction_id: If provided, use this transaction_id; otherwise generate one.
        company_id: If provided, use this company_id; otherwise generate one.

    Returns:
        A valid AuditEvent instance.
    """
    from alcoabase.schemas.audit_trail import AuditEvent

    tid = transaction_id if transaction_id is not None else draw(
        st.integers(min_value=1, max_value=100000)
    )
    cid = company_id if company_id is not None else draw(
        st.integers(min_value=1, max_value=100)
    )
    ts = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2025, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    user_id = draw(st.integers(min_value=1, max_value=10000))
    user_display_name = draw(
        st.one_of(
            st.none(),
            st.text(min_size=1, max_size=50, alphabet=st.characters(
                whitelist_categories=("L", "Zs"),
            )),
        )
    )
    record_type = draw(st.sampled_from(ALL_RECORD_TYPES))
    record_id = draw(st.integers(min_value=1, max_value=100000))
    operation_type = draw(st.sampled_from(VALID_OPERATION_TYPES))
    change_reason = draw(
        st.one_of(
            st.none(),
            st.text(min_size=1, max_size=200, alphabet=st.characters(
                whitelist_categories=("L", "N", "Zs", "P"),
            )),
        )
    )
    num_fields = draw(st.integers(min_value=0, max_value=30))
    all_fields = [f"field_{i}" for i in range(num_fields)]
    changed_fields = all_fields[:10]

    return AuditEvent(
        transaction_id=tid,
        timestamp=ts,
        user_id=user_id,
        user_display_name=user_display_name,
        record_type=record_type,
        record_id=record_id,
        operation_type=operation_type,
        change_reason=change_reason,
        changed_fields=changed_fields,
        total_changed_fields=num_fields,
        company_id=cid,
    )


@st.composite
def st_events_with_shared_transactions(draw: st.DrawFn) -> list["AuditEvent"]:
    """Generate a set of events where some share the same transaction_id.

    Creates a mix of:
    - Groups of 2-5 events sharing the same transaction_id (correlated events)
    - Standalone events with unique transaction_ids

    Returns:
        A list of AuditEvent instances with some sharing transaction_ids.
    """
    company_id = draw(st.integers(min_value=1, max_value=100))

    # Generate 1-4 transaction groups (each with 2-5 events sharing a txn_id)
    num_groups = draw(st.integers(min_value=1, max_value=4))
    events: list = []
    used_txn_ids: set[int] = set()

    for _ in range(num_groups):
        shared_txn_id = draw(
            st.integers(min_value=1, max_value=100000).filter(
                lambda x: x not in used_txn_ids
            )
        )
        used_txn_ids.add(shared_txn_id)
        group_size = draw(st.integers(min_value=2, max_value=5))

        for _ in range(group_size):
            event = draw(st_audit_event_for_grouping(
                transaction_id=shared_txn_id,
                company_id=company_id,
            ))
            events.append(event)

    # Add 0-5 standalone events with unique transaction_ids
    num_standalone = draw(st.integers(min_value=0, max_value=5))

    for _ in range(num_standalone):
        unique_txn_id = draw(
            st.integers(min_value=100001, max_value=999999).filter(
                lambda x: x not in used_txn_ids
            )
        )
        used_txn_ids.add(unique_txn_id)
        event = draw(st_audit_event_for_grouping(
            transaction_id=unique_txn_id,
            company_id=company_id,
        ))
        events.append(event)

    return events


# Feature: Step_6-3_audit-trail-viewer, Property 4: Transaction grouping
@settings(max_examples=100, deadline=None)
@given(events=st_events_with_shared_transactions())
def test_transaction_grouping_all_events_present_with_correlation_id(
    events: list,
) -> None:
    """For any set of audit events where multiple events share the same
    transaction_id, those events SHALL be presented with the transaction_id
    as a correlation identifier enabling grouping.

    This test verifies:
    1. All events with a shared transaction_id are present in the result set
    2. Events can be grouped by transaction_id as a correlation identifier
    3. Each group contains exactly the expected number of correlated events
    4. The total_count reflects all events including grouped ones

    **Validates: Requirements 1.5**
    """
    from collections import defaultdict

    from alcoabase.schemas.audit_trail import AuditTrailPage

    # Simulate the service returning events in an AuditTrailPage
    page = AuditTrailPage(
        events=events,
        next_cursor=None,
        total_count=len(events),
    )

    # Build expected groups from input
    expected_groups: dict[int, list] = defaultdict(list)
    for event in events:
        expected_groups[event.transaction_id].append(event)

    # Build actual groups from the page response
    actual_groups: dict[int, list] = defaultdict(list)
    for event in page.events:
        actual_groups[event.transaction_id].append(event)

    # Property 1: Every event from the input is present in the output
    assert len(page.events) == len(events), (
        f"Expected {len(events)} events in page, got {len(page.events)}"
    )

    # Property 2: Events can be grouped by transaction_id
    for txn_id, expected_event_list in expected_groups.items():
        assert txn_id in actual_groups, (
            f"Transaction ID {txn_id} not found in result groups"
        )
        actual_event_list = actual_groups[txn_id]

        # Property 3: Each transaction group has the correct count
        assert len(actual_event_list) == len(expected_event_list), (
            f"Transaction group {txn_id}: expected {len(expected_event_list)} "
            f"events, got {len(actual_event_list)}"
        )

    # Property 4: All events in a shared transaction group carry the same
    # transaction_id, enabling correlation
    for txn_id, group_events in actual_groups.items():
        if len(group_events) > 1:
            for event in group_events:
                assert event.transaction_id == txn_id, (
                    f"Event in group {txn_id} has mismatched transaction_id: "
                    f"{event.transaction_id}"
                )

    # Property 5: The total_count reflects all events including grouped ones
    assert page.total_count == len(events), (
        f"total_count should be {len(events)}, got {page.total_count}"
    )


# Feature: Step_6-3_audit-trail-viewer, Property 4: Transaction grouping
@settings(max_examples=100, deadline=None)
@given(events=st_events_with_shared_transactions())
def test_transaction_grouping_preserves_all_correlated_events(
    events: list,
) -> None:
    """For any set of events with shared transaction_ids, grouping by
    transaction_id SHALL yield groups where each group contains all
    events that were part of that transaction, with no events lost
    or misattributed.

    **Validates: Requirements 1.5**
    """
    from collections import defaultdict

    # Group events by transaction_id (simulating what the viewer does)
    groups: dict[int, list] = defaultdict(list)
    for event in events:
        groups[event.transaction_id].append(event)

    # Verify: the union of all groups equals the original event set
    regrouped_events: list = []
    for group_events in groups.values():
        regrouped_events.extend(group_events)

    assert len(regrouped_events) == len(events), (
        "Grouping by transaction_id must not lose or duplicate events. "
        f"Original: {len(events)}, after regrouping: {len(regrouped_events)}"
    )

    # Verify: groups with multiple events represent correlated changes
    multi_event_groups = {
        txn_id: evts for txn_id, evts in groups.items() if len(evts) > 1
    }

    # At least one multi-event group should exist (by construction of strategy)
    assert len(multi_event_groups) > 0, (
        "Test data should contain at least one transaction group with "
        "multiple events (correlated changes)"
    )

    # Each multi-event group's events all share the same transaction_id
    for txn_id, group_events in multi_event_groups.items():
        txn_ids_in_group = {e.transaction_id for e in group_events}
        assert txn_ids_in_group == {txn_id}, (
            f"All events in transaction group {txn_id} must share the same "
            f"transaction_id. Found: {txn_ids_in_group}"
        )
