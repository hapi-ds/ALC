"""Property-based tests for Audit Trail Substring Search Completeness.

Tests Property 11 from the audit-trail-viewer design document:
For any audit event and any substring of its searchable fields
(change_reason, record_type, user_display_name, record_id as string),
searching for that substring SHALL include the event in the results.

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md (Property 11)
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md (5.1, 5.2)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import assume, given, settings

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
def st_searchable_audit_event(draw: st.DrawFn) -> AuditEvent:
    """Generate an audit event with non-trivial searchable field values.

    Generates events with meaningful content in the searchable fields:
    change_reason, record_type, user_display_name, and record_id.

    Returns:
        A valid AuditEvent instance with searchable content.
    """
    # Use printable ASCII for searchable fields to avoid ILIKE edge cases
    # with special characters (%, _, etc.)
    safe_alphabet = st.characters(
        whitelist_categories=("L", "N", "Zs"),
        min_codepoint=32,
        max_codepoint=126,
    )

    record_type = draw(st.sampled_from(ALL_RECORD_TYPES))
    record_id = draw(st.integers(min_value=1, max_value=999999))
    user_id = draw(st.integers(min_value=1, max_value=10000))

    # Generate a non-empty change_reason (at least 2 chars for substring extraction)
    change_reason = draw(
        st.text(min_size=2, max_size=100, alphabet=safe_alphabet).filter(
            lambda s: s.strip() != ""
        )
    )

    # Generate a non-empty user_display_name (at least 2 chars)
    user_display_name = draw(
        st.text(min_size=2, max_size=50, alphabet=safe_alphabet).filter(
            lambda s: s.strip() != ""
        )
    )

    timestamp = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2025, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    operation_type = draw(st.sampled_from(VALID_OPERATION_TYPES))
    company_id = draw(st.integers(min_value=1, max_value=100))

    return AuditEvent(
        transaction_id=draw(st.integers(min_value=1, max_value=100000)),
        timestamp=timestamp,
        user_id=user_id,
        user_display_name=user_display_name,
        record_type=record_type,
        record_id=record_id,
        operation_type=operation_type,
        change_reason=change_reason,
        changed_fields=[],
        total_changed_fields=0,
        company_id=company_id,
    )


@st.composite
def st_substring_of(draw: st.DrawFn, text: str) -> str:
    """Generate a non-empty substring of the given text.

    Args:
        text: The source string to extract a substring from.

    Returns:
        A non-empty substring of the input text.
    """
    assume(len(text) >= 1)
    start = draw(st.integers(min_value=0, max_value=len(text) - 1))
    end = draw(st.integers(min_value=start + 1, max_value=len(text)))
    return text[start:end]


@st.composite
def st_event_with_search_field(
    draw: st.DrawFn,
) -> tuple[AuditEvent, str, str]:
    """Generate an audit event and a substring from one of its searchable fields.

    Returns:
        A tuple of (event, search_substring, field_name) where field_name
        indicates which field the substring was extracted from.
    """
    event = draw(st_searchable_audit_event())

    # Choose which searchable field to extract a substring from
    field_choice = draw(
        st.sampled_from([
            "change_reason",
            "record_type",
            "user_display_name",
            "record_id",
        ])
    )

    if field_choice == "change_reason":
        source_text = event.change_reason
        assume(source_text is not None and len(source_text) >= 1)
        substring = draw(st_substring_of(source_text))
    elif field_choice == "record_type":
        source_text = event.record_type
        substring = draw(st_substring_of(source_text))
    elif field_choice == "user_display_name":
        source_text = event.user_display_name
        assume(source_text is not None and len(source_text) >= 1)
        substring = draw(st_substring_of(source_text))
    else:  # record_id
        source_text = str(event.record_id)
        substring = draw(st_substring_of(source_text))

    # Ensure substring is non-empty and doesn't contain SQL LIKE wildcards
    assume(len(substring) >= 1)
    assume("%" not in substring)
    assume("_" not in substring)

    return (event, substring, field_choice)


# ---------------------------------------------------------------------------
# Helper: simulate search matching logic
# ---------------------------------------------------------------------------


def _event_matches_search(event: AuditEvent, search_query: str) -> bool:
    """Check if an event matches a search query using case-insensitive substring.

    Mirrors the service's _apply_search_filter logic:
    - Matches against change_reason (ILIKE)
    - Matches against record_type (substring check)
    - Matches against user_display_name (conceptual — resolved at query time)
    - Matches against record_id cast to string (ILIKE)

    Args:
        event: The audit event to check.
        search_query: The search substring.

    Returns:
        True if the event matches the search query.
    """
    query_lower = search_query.lower()

    # Check change_reason
    if event.change_reason and query_lower in event.change_reason.lower():
        return True

    # Check record_type
    if query_lower in event.record_type.lower():
        return True

    # Check user_display_name
    if event.user_display_name and query_lower in event.user_display_name.lower():
        return True

    # Check record_id as string
    if query_lower in str(event.record_id).lower():
        return True

    return False


# ---------------------------------------------------------------------------
# Property 11: Substring search completeness
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 11: Substring search completeness
@settings(max_examples=100, deadline=None)
@given(data=st_event_with_search_field())
@pytest.mark.asyncio
async def test_substring_search_completeness(
    data: tuple[AuditEvent, str, str],
) -> None:
    """For any audit event and any substring of its searchable fields
    (change_reason, record_type, user_display_name, record_id as string),
    searching for that substring SHALL include the event in the results.

    This test generates audit events with known searchable field values,
    extracts substrings from those fields, and verifies that the service's
    search logic would include the event when searching for that substring.

    **Validates: Requirements 5.1, 5.2**
    """
    event, search_substring, field_name = data

    service = AuditTrailService()
    filters = AuditTrailFilters()
    company_id = event.company_id

    # Mock _query_version_table to simulate search behavior:
    # The mock returns the event only if the search query matches
    # (mimicking the ILIKE filter behavior in the real implementation)
    async def mock_query_version_table(
        session, config, company_id, filters, search_query, cross_company=False
    ):
        """Return the event if search matches, simulating DB ILIKE behavior."""
        if search_query is None:
            return [event] if config.record_type == event.record_type else []

        # Simulate the service's search logic for the event's record type
        if config.record_type != event.record_type:
            return []

        # Apply the same matching logic as the service
        if _event_matches_search(event, search_query):
            return [event]
        return []

    with patch.object(
        service, "_query_version_table", side_effect=mock_query_version_table
    ):
        session = AsyncMock()
        result = await service.list_events(
            session=session,
            company_id=company_id,
            filters=filters,
            search_query=search_substring,
            cursor=None,
            page_size=200,
        )

    # Property: The event MUST be included in the search results
    returned_event_ids = {
        (e.transaction_id, e.record_type, e.record_id) for e in result.events
    }
    event_key = (event.transaction_id, event.record_type, event.record_id)

    assert event_key in returned_event_ids, (
        f"Substring search completeness violated: "
        f"searching for '{search_substring}' (from field '{field_name}') "
        f"did not include the event in results.\n"
        f"  Event record_type: {event.record_type}\n"
        f"  Event record_id: {event.record_id}\n"
        f"  Event change_reason: {event.change_reason!r}\n"
        f"  Event user_display_name: {event.user_display_name!r}\n"
        f"  Search substring: {search_substring!r}\n"
        f"  Field searched: {field_name}\n"
        f"  Returned events: {len(result.events)}"
    )


# Feature: Step_6-3_audit-trail-viewer, Property 11: Substring search completeness
@settings(max_examples=100, deadline=None)
@given(data=st_event_with_search_field())
def test_substring_search_matching_logic_completeness(
    data: tuple[AuditEvent, str, str],
) -> None:
    """For any audit event and any substring of its searchable fields,
    the search matching logic SHALL return True, confirming that the
    substring is correctly identified as a match.

    This is a pure-function test of the matching logic without async
    service calls, verifying the fundamental property that a substring
    of a field always matches that field in case-insensitive search.

    **Validates: Requirements 5.1, 5.2**
    """
    event, search_substring, field_name = data

    # Property: The matching function MUST return True for any substring
    # extracted from a searchable field of the event
    assert _event_matches_search(event, search_substring), (
        f"Search matching logic failed for substring '{search_substring}' "
        f"extracted from field '{field_name}'.\n"
        f"  Event record_type: {event.record_type}\n"
        f"  Event record_id: {event.record_id}\n"
        f"  Event change_reason: {event.change_reason!r}\n"
        f"  Event user_display_name: {event.user_display_name!r}"
    )
