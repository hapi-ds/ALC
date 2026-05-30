"""Property-based tests for Audit Trail Tenant Scoping (Property 10).

Tests that audit trail queries scoped to a specific company_id return only
events belonging to that company and no events from other companies.

Feature: Step_6-3_audit-trail-viewer, Property 10: Tenant scoping

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md (Property 10)
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md (4.1)
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
def st_company_ids(draw: st.DrawFn, min_companies: int = 2) -> list[int]:
    """Generate a list of distinct company IDs (at least 2).

    Args:
        min_companies: Minimum number of distinct companies.

    Returns:
        A list of unique company IDs.
    """
    num_companies = draw(st.integers(min_value=min_companies, max_value=5))
    return draw(
        st.lists(
            st.integers(min_value=1, max_value=10000),
            min_size=num_companies,
            max_size=num_companies,
            unique=True,
        )
    )


@st.composite
def st_audit_event(
    draw: st.DrawFn,
    company_id: int,
) -> AuditEvent:
    """Generate a valid AuditEvent belonging to a specific company.

    Args:
        draw: Hypothesis draw function.
        company_id: The company_id to assign to this event.

    Returns:
        An AuditEvent instance with the given company_id.
    """
    transaction_id = draw(st.integers(min_value=1, max_value=999999))
    timestamp = draw(
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
            st.text(
                min_size=1,
                max_size=50,
                alphabet=st.characters(whitelist_categories=("L", "Zs")),
            ),
        )
    )
    record_type = draw(st.sampled_from(ALL_RECORD_TYPES))
    record_id = draw(st.integers(min_value=1, max_value=100000))
    operation_type = draw(st.sampled_from(VALID_OPERATION_TYPES))
    change_reason = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=1,
                max_size=200,
                alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")),
            ),
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
def st_multi_company_events(
    draw: st.DrawFn,
) -> tuple[list[int], dict[int, list[AuditEvent]]]:
    """Generate audit events distributed across multiple companies.

    Ensures each company has at least 1 event and there are at least
    2 companies, so we can verify isolation.

    Returns:
        A tuple of (company_ids, events_by_company) where events_by_company
        maps each company_id to its list of AuditEvent instances.
    """
    company_ids = draw(st_company_ids(min_companies=2))
    events_by_company: dict[int, list[AuditEvent]] = {}

    for cid in company_ids:
        num_events = draw(st.integers(min_value=1, max_value=8))
        events = draw(
            st.lists(
                st_audit_event(company_id=cid),
                min_size=num_events,
                max_size=num_events,
            )
        )
        events_by_company[cid] = events

    return company_ids, events_by_company


# ---------------------------------------------------------------------------
# Property 10: Tenant scoping
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 10: Tenant scoping
@settings(max_examples=100, deadline=None)
@given(data=st_multi_company_events())
@pytest.mark.asyncio
async def test_tenant_scoping_returns_only_target_company_events(
    data: tuple[list[int], dict[int, list[AuditEvent]]],
) -> None:
    """For any audit trail query scoped to a specific company_id, every
    returned event SHALL belong to that company, and no event from another
    company SHALL appear in the results.

    Generate audit events belonging to multiple companies; verify query
    scoped to company_id returns only events from that company and no
    events from other companies.

    **Validates: Requirements 4.1**
    """
    company_ids, events_by_company = data
    service = AuditTrailService()
    filters = AuditTrailFilters()

    # Flatten all events across all companies
    all_events: list[AuditEvent] = []
    for cid_events in events_by_company.values():
        all_events.extend(cid_events)

    # Pick a target company to query
    target_company_id = company_ids[0]
    target_events = events_by_company[target_company_id]

    # Mock _query_version_table to return only events matching the company_id
    # This simulates the service's company scoping behavior
    async def mock_query_version_table(
        session, config, company_id, filters, search_query, cross_company=False
    ):
        """Return events filtered by company_id, simulating DB-level scoping."""
        if cross_company:
            # Return all events for this record type
            return [
                e for e in all_events if e.record_type == config.record_type
            ]
        # Return only events matching the target company_id
        return [
            e
            for e in all_events
            if e.company_id == company_id and e.record_type == config.record_type
        ]

    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        result = await service.list_events(
            session=session,
            company_id=target_company_id,
            filters=filters,
            search_query=None,
            cursor=None,
            page_size=200,
        )

    # Property 1: Every returned event belongs to the target company
    for event in result.events:
        assert event.company_id == target_company_id, (
            f"Event with transaction_id={event.transaction_id} has "
            f"company_id={event.company_id}, expected {target_company_id}. "
            f"Tenant scoping violated: event from another company leaked."
        )

    # Property 2: No events from other companies appear in results
    other_company_ids = [cid for cid in company_ids if cid != target_company_id]
    returned_company_ids = {e.company_id for e in result.events}
    for other_cid in other_company_ids:
        assert other_cid not in returned_company_ids, (
            f"Events from company_id={other_cid} appeared in results "
            f"scoped to company_id={target_company_id}. "
            f"Tenant isolation breach detected."
        )

    # Property 3: All events belonging to the target company are returned
    # (no events from the target company are excluded)
    assert len(result.events) == len(target_events), (
        f"Expected {len(target_events)} events for company_id={target_company_id}, "
        f"got {len(result.events)}. Some events from the target company "
        f"were excluded from results."
    )


# Feature: Step_6-3_audit-trail-viewer, Property 10: Tenant scoping
@settings(max_examples=100, deadline=None)
@given(data=st_multi_company_events())
@pytest.mark.asyncio
async def test_tenant_scoping_each_company_sees_only_own_events(
    data: tuple[list[int], dict[int, list[AuditEvent]]],
) -> None:
    """For any set of companies with audit events, querying each company
    individually SHALL return a disjoint set of events, and the union of
    all company-scoped queries SHALL equal the full event set.

    This verifies complete tenant isolation: no event is shared between
    companies and no event is lost.

    **Validates: Requirements 4.1**
    """
    company_ids, events_by_company = data
    service = AuditTrailService()
    filters = AuditTrailFilters()

    # Flatten all events
    all_events: list[AuditEvent] = []
    for cid_events in events_by_company.values():
        all_events.extend(cid_events)

    async def mock_query_version_table(
        session, config, company_id, filters, search_query, cross_company=False
    ):
        """Return events filtered by company_id."""
        return [
            e
            for e in all_events
            if e.company_id == company_id and e.record_type == config.record_type
        ]

    # Query each company and collect results
    all_returned_events: list[AuditEvent] = []
    returned_by_company: dict[int, list[AuditEvent]] = {}

    for cid in company_ids:
        with patch.object(
            service, "_query_version_table", side_effect=mock_query_version_table
        ):
            session = AsyncMock()
            result = await service.list_events(
                session=session,
                company_id=cid,
                filters=filters,
                search_query=None,
                cursor=None,
                page_size=200,
            )
        returned_by_company[cid] = result.events
        all_returned_events.extend(result.events)

    # Property 1: Results for each company are disjoint (no overlap)
    for i, cid_a in enumerate(company_ids):
        for cid_b in company_ids[i + 1:]:
            events_a = {
                (e.transaction_id, e.record_type, e.timestamp)
                for e in returned_by_company[cid_a]
            }
            events_b = {
                (e.transaction_id, e.record_type, e.timestamp)
                for e in returned_by_company[cid_b]
            }
            # Check company_id isolation (events should not share company)
            for event in returned_by_company[cid_a]:
                assert event.company_id == cid_a, (
                    f"Event in company {cid_a} results has company_id="
                    f"{event.company_id}"
                )
            for event in returned_by_company[cid_b]:
                assert event.company_id == cid_b, (
                    f"Event in company {cid_b} results has company_id="
                    f"{event.company_id}"
                )

    # Property 2: The total number of events across all company queries
    # equals the total number of events generated
    assert len(all_returned_events) == len(all_events), (
        f"Union of all company-scoped queries returned "
        f"{len(all_returned_events)} events, but {len(all_events)} were "
        f"generated. Some events were lost or duplicated."
    )
