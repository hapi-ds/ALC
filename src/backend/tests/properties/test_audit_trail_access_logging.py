"""Property-based tests for Audit Trail Access Logging Completeness.

Tests Property 16 from the audit-trail-viewer design document,
validating that every audit trail interaction (view or export) creates
an entry in the audit_access_log table containing user_id, timestamp,
action type, and applied filters.

**Validates: Requirements 11.1, 11.2**

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md (Property 16)
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.audit_access_log import AuditAccessLog
from alcoabase.services.audit_access_logger import AuditAccessLogger


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VALID_ACTIONS = ["view", "export"]

VALID_RECORD_TYPES = [
    "documents",
    "templates",
    "reports",
    "workflows",
    "signatures",
    "training_tasks",
    "training_records",
]

VALID_OPERATION_TYPES = ["INSERT", "UPDATE", "DELETE"]


@st.composite
def st_access_context(draw: st.DrawFn) -> dict:
    """Generate a valid access context with user_id and company_id.

    Returns:
        A dictionary with user_id and company_id.
    """
    user_id = draw(st.integers(min_value=1, max_value=10000))
    company_id = draw(st.integers(min_value=1, max_value=10000))
    return {
        "user_id": user_id,
        "company_id": company_id,
    }


@st.composite
def st_action_type(draw: st.DrawFn) -> str:
    """Generate a valid action type for audit access logging.

    Returns:
        Either "view" or "export".
    """
    return draw(st.sampled_from(VALID_ACTIONS))


@st.composite
def st_filters_applied(draw: st.DrawFn) -> dict | None:
    """Generate optional filter parameters that may be applied during access.

    Returns:
        A dictionary of active filters or None if no filters applied.
    """
    has_filters = draw(st.booleans())
    if not has_filters:
        return None

    filters: dict = {}
    if draw(st.booleans()):
        filters["user_id"] = draw(st.integers(min_value=1, max_value=10000))
    if draw(st.booleans()):
        filters["date_start"] = draw(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 12, 31),
            )
        ).isoformat()
    if draw(st.booleans()):
        filters["date_end"] = draw(
            st.datetimes(
                min_value=datetime(2020, 1, 1),
                max_value=datetime(2030, 12, 31),
            )
        ).isoformat()
    if draw(st.booleans()):
        filters["record_type"] = draw(st.sampled_from(VALID_RECORD_TYPES))
    if draw(st.booleans()):
        filters["operation_type"] = draw(
            st.sampled_from(VALID_OPERATION_TYPES)
        )
    if draw(st.booleans()):
        filters["search"] = draw(
            st.text(min_size=1, max_size=50, alphabet=st.characters(
                whitelist_categories=("L", "N", "Zs"),
            ))
        )

    # Return None if no filters were actually added
    return filters if filters else None


@st.composite
def st_event_count(draw: st.DrawFn) -> int | None:
    """Generate an optional event count (populated for export actions).

    Returns:
        An integer event count or None.
    """
    has_count = draw(st.booleans())
    if not has_count:
        return None
    return draw(st.integers(min_value=0, max_value=100000))


# ---------------------------------------------------------------------------
# Property 16: Access logging completeness — View action
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 16: Access logging completeness
@settings(max_examples=100, deadline=None)
@given(
    ctx=st_access_context(),
    filters_applied=st_filters_applied(),
)
@pytest.mark.asyncio
async def test_view_action_creates_access_log_entry(
    ctx: dict,
    filters_applied: dict | None,
) -> None:
    """For any audit trail view interaction, the AuditAccessLogger SHALL
    create an entry in audit_access_log containing user_id, timestamp,
    action type ("view"), and applied filters.

    **Validates: Requirements 11.1, 11.2**
    """
    logger = AuditAccessLogger()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    await logger.log_access(
        session=session,
        user_id=ctx["user_id"],
        company_id=ctx["company_id"],
        action="view",
        filters_applied=filters_applied,
    )

    # Property: session.add() was called exactly once (record created)
    assert session.add.call_count == 1, (
        "log_access must call session.add() to create an AuditAccessLog record"
    )

    # Extract the AuditAccessLog record that was added
    added_record = session.add.call_args[0][0]
    assert isinstance(added_record, AuditAccessLog), (
        "log_access must add an AuditAccessLog instance to the session"
    )

    # Property: user_id is correctly stored
    assert added_record.user_id == ctx["user_id"], (
        f"Expected user_id={ctx['user_id']}, got {added_record.user_id}"
    )

    # Property: company_id is correctly stored
    assert added_record.company_id == ctx["company_id"], (
        f"Expected company_id={ctx['company_id']}, got {added_record.company_id}"
    )

    # Property: action type is "view"
    assert added_record.action == "view", (
        f"Expected action='view', got '{added_record.action}'"
    )

    # Property: filters_applied matches what was provided
    assert added_record.filters_applied == filters_applied, (
        f"Expected filters_applied={filters_applied}, "
        f"got {added_record.filters_applied}"
    )

    # Property: session.commit() was called (fire-and-forget pattern)
    assert session.commit.call_count == 1, (
        "log_access must call session.commit() to persist the record"
    )


# ---------------------------------------------------------------------------
# Property 16: Access logging completeness — Export action
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 16: Access logging completeness
@settings(max_examples=100, deadline=None)
@given(
    ctx=st_access_context(),
    filters_applied=st_filters_applied(),
    event_count=st.integers(min_value=1, max_value=100000),
)
@pytest.mark.asyncio
async def test_export_action_creates_access_log_entry(
    ctx: dict,
    filters_applied: dict | None,
    event_count: int,
) -> None:
    """For any audit trail export interaction, the AuditAccessLogger SHALL
    create an entry in audit_access_log containing user_id, timestamp,
    action type ("export"), applied filters, and event count.

    **Validates: Requirements 11.1, 11.2**
    """
    logger = AuditAccessLogger()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    await logger.log_access(
        session=session,
        user_id=ctx["user_id"],
        company_id=ctx["company_id"],
        action="export",
        filters_applied=filters_applied,
        event_count=event_count,
    )

    # Property: session.add() was called exactly once (record created)
    assert session.add.call_count == 1, (
        "log_access must call session.add() to create an AuditAccessLog record"
    )

    # Extract the AuditAccessLog record that was added
    added_record = session.add.call_args[0][0]
    assert isinstance(added_record, AuditAccessLog), (
        "log_access must add an AuditAccessLog instance to the session"
    )

    # Property: user_id is correctly stored
    assert added_record.user_id == ctx["user_id"], (
        f"Expected user_id={ctx['user_id']}, got {added_record.user_id}"
    )

    # Property: company_id is correctly stored
    assert added_record.company_id == ctx["company_id"], (
        f"Expected company_id={ctx['company_id']}, got {added_record.company_id}"
    )

    # Property: action type is "export"
    assert added_record.action == "export", (
        f"Expected action='export', got '{added_record.action}'"
    )

    # Property: filters_applied matches what was provided
    assert added_record.filters_applied == filters_applied, (
        f"Expected filters_applied={filters_applied}, "
        f"got {added_record.filters_applied}"
    )

    # Property: event_count is correctly stored for export actions
    assert added_record.event_count == event_count, (
        f"Expected event_count={event_count}, got {added_record.event_count}"
    )

    # Property: session.commit() was called (fire-and-forget pattern)
    assert session.commit.call_count == 1, (
        "log_access must call session.commit() to persist the record"
    )


# ---------------------------------------------------------------------------
# Property 16: Access logging completeness — Both actions create records
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 16: Access logging completeness
@settings(max_examples=100, deadline=None)
@given(
    ctx=st_access_context(),
    action=st_action_type(),
    filters_applied=st_filters_applied(),
    event_count=st_event_count(),
)
@pytest.mark.asyncio
async def test_any_interaction_creates_complete_access_log(
    ctx: dict,
    action: str,
    filters_applied: dict | None,
    event_count: int | None,
) -> None:
    """For any audit trail interaction (view or export), the system SHALL
    create an entry in audit_access_log containing user_id, timestamp
    (via server_default), action type, and applied filters.

    **Validates: Requirements 11.1, 11.2**
    """
    logger = AuditAccessLogger()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    await logger.log_access(
        session=session,
        user_id=ctx["user_id"],
        company_id=ctx["company_id"],
        action=action,
        filters_applied=filters_applied,
        event_count=event_count,
    )

    # Property: An AuditAccessLog record is always created
    assert session.add.call_count == 1, (
        f"log_access(action='{action}') must always create an "
        "AuditAccessLog record via session.add()"
    )

    added_record = session.add.call_args[0][0]
    assert isinstance(added_record, AuditAccessLog), (
        "The added record must be an AuditAccessLog instance"
    )

    # Property: All required fields are populated
    assert added_record.user_id == ctx["user_id"], (
        "user_id must be stored in the access log entry"
    )
    assert added_record.company_id == ctx["company_id"], (
        "company_id must be stored in the access log entry"
    )
    assert added_record.action == action, (
        f"action must be '{action}' in the access log entry"
    )
    assert added_record.filters_applied == filters_applied, (
        "filters_applied must be stored in the access log entry"
    )

    # Property: timestamp is handled by server_default (func.now()),
    # so we verify the model column exists and has server_default configured
    timestamp_col = AuditAccessLog.__table__.c.timestamp
    assert timestamp_col.server_default is not None, (
        "AuditAccessLog.timestamp must have a server_default for "
        "automatic timestamp generation"
    )

    # Property: The record is committed to the database
    assert session.commit.call_count == 1, (
        "log_access must commit the record to persist it"
    )
