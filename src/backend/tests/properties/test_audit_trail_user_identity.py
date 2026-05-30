"""Property-based tests for Audit Trail User Identity Resolution.

Tests Property 3 from the Step_6-3_audit-trail-viewer design document,
validating that the AuditTrailService correctly resolves user display names
with fallback behavior: display name when user exists in the users table,
None when the user record is unavailable, and user_id always remains the
numeric identifier.

**Validates: Requirements 1.4**

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md (Property 3)
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.audit_trail_service import AuditTrailService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_user_id(draw: st.DrawFn) -> int:
    """Generate a valid user ID (positive integer).

    Returns:
        A positive integer representing a user ID.
    """
    return draw(st.integers(min_value=1, max_value=100_000))


@st.composite
def st_display_name(draw: st.DrawFn) -> str:
    """Generate a realistic user display name.

    Returns:
        A non-empty string representing a user's full name.
    """
    return draw(
        st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(whitelist_categories=("L", "Zs")),
        ).filter(lambda s: s.strip())
    )


@st.composite
def st_user_id_sets(draw: st.DrawFn) -> tuple[dict[int, str], set[int]]:
    """Generate a set of existing users and a set of all user_ids to resolve.

    Returns a tuple of:
    - existing_users: dict mapping user_id -> display_name for users that exist
    - all_user_ids: set of user_ids to resolve (includes both existing and missing)
    """
    # Generate existing users (1 to 20)
    num_existing = draw(st.integers(min_value=1, max_value=20))
    existing_ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=100_000),
            min_size=num_existing,
            max_size=num_existing,
            unique=True,
        )
    )
    existing_names = draw(
        st.lists(
            st.text(
                min_size=1,
                max_size=100,
                alphabet=st.characters(whitelist_categories=("L", "Zs")),
            ).filter(lambda s: s.strip()),
            min_size=num_existing,
            max_size=num_existing,
        )
    )
    existing_users = dict(zip(existing_ids, existing_names))

    # Generate missing user_ids (IDs that don't exist in the users table)
    num_missing = draw(st.integers(min_value=0, max_value=10))
    missing_ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=100_000).filter(
                lambda x: x not in existing_users
            ),
            min_size=num_missing,
            max_size=num_missing,
            unique=True,
        )
    )

    # All user_ids to resolve includes a mix of existing and missing
    all_user_ids = set(existing_ids) | set(missing_ids)

    return existing_users, all_user_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session_for_user_resolution(
    existing_users: dict[int, str],
) -> AsyncMock:
    """Create a mock session that returns user records for existing users.

    The session simulates the query:
        SELECT users.id, users.full_name WHERE users.id IN (...)

    Args:
        existing_users: Dict mapping user_id -> full_name for users that exist.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()

    async def mock_execute(stmt, *args, **kwargs):
        """Simulate executing a SELECT query against the users table."""
        result = MagicMock()
        # The _batch_resolve_user_names method calls result.all()
        # which returns a list of (id, full_name) tuples
        rows = [(uid, name) for uid, name in existing_users.items()]
        result.all.return_value = rows
        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


# ---------------------------------------------------------------------------
# Property 3: User identity resolution with fallback
# ---------------------------------------------------------------------------


# Feature: Step_6-3_audit-trail-viewer, Property 3: User identity resolution with fallback
@settings(max_examples=100, deadline=None)
@given(data=st_user_id_sets())
@pytest.mark.asyncio
async def test_user_identity_resolution_existing_users_get_display_name(
    data: tuple[dict[int, str], set[int]],
) -> None:
    """For any audit event where the associated user record exists,
    user_display_name SHALL be the user's display name.

    **Validates: Requirements 1.4**
    """
    existing_users, all_user_ids = data
    service = AuditTrailService()
    session = _make_mock_session_for_user_resolution(existing_users)

    # Call the batch resolve method
    name_map = await service._batch_resolve_user_names(session, all_user_ids)

    # Property: For every user that exists, display name matches
    for user_id, expected_name in existing_users.items():
        if user_id in all_user_ids:
            assert name_map[user_id] == expected_name, (
                f"User {user_id} exists with name '{expected_name}' but "
                f"got '{name_map[user_id]}'"
            )


# Feature: Step_6-3_audit-trail-viewer, Property 3: User identity resolution with fallback
@settings(max_examples=100, deadline=None)
@given(data=st_user_id_sets())
@pytest.mark.asyncio
async def test_user_identity_resolution_missing_users_get_none(
    data: tuple[dict[int, str], set[int]],
) -> None:
    """For any audit event where the user record is unavailable,
    user_display_name SHALL be None.

    **Validates: Requirements 1.4**
    """
    existing_users, all_user_ids = data
    service = AuditTrailService()
    session = _make_mock_session_for_user_resolution(existing_users)

    # Call the batch resolve method
    name_map = await service._batch_resolve_user_names(session, all_user_ids)

    # Property: For every user that does NOT exist, display name is None
    missing_ids = all_user_ids - set(existing_users.keys())
    for user_id in missing_ids:
        assert name_map[user_id] is None, (
            f"User {user_id} does not exist but got display name "
            f"'{name_map[user_id]}' instead of None"
        )


# Feature: Step_6-3_audit-trail-viewer, Property 3: User identity resolution with fallback
@settings(max_examples=100, deadline=None)
@given(data=st_user_id_sets())
@pytest.mark.asyncio
async def test_user_identity_resolution_user_id_always_numeric(
    data: tuple[dict[int, str], set[int]],
) -> None:
    """For any audit event, user_id SHALL always be the numeric identifier
    regardless of whether the user record exists or not.

    **Validates: Requirements 1.4**
    """
    existing_users, all_user_ids = data
    service = AuditTrailService()
    session = _make_mock_session_for_user_resolution(existing_users)

    # Call the batch resolve method
    name_map = await service._batch_resolve_user_names(session, all_user_ids)

    # Property: Every user_id in the input set appears as a key in the result
    # (the numeric identifier is preserved as the key)
    for user_id in all_user_ids:
        assert user_id in name_map, (
            f"User ID {user_id} not found in resolved name map. "
            f"The numeric identifier must always be preserved."
        )
        # Verify the key is the numeric integer (not converted to string etc.)
        assert isinstance(user_id, int), (
            f"User ID must be a numeric identifier, got {type(user_id)}"
        )


# Feature: Step_6-3_audit-trail-viewer, Property 3: User identity resolution with fallback
@settings(max_examples=100, deadline=None)
@given(data=st_user_id_sets())
@pytest.mark.asyncio
async def test_user_identity_resolution_completeness(
    data: tuple[dict[int, str], set[int]],
) -> None:
    """For any set of user_ids, the resolution SHALL return a mapping
    for every requested user_id — no IDs are dropped.

    **Validates: Requirements 1.4**
    """
    existing_users, all_user_ids = data
    service = AuditTrailService()
    session = _make_mock_session_for_user_resolution(existing_users)

    # Call the batch resolve method
    name_map = await service._batch_resolve_user_names(session, all_user_ids)

    # Property: The result contains exactly the requested user_ids
    assert set(name_map.keys()) == all_user_ids, (
        f"Expected keys {all_user_ids}, got {set(name_map.keys())}. "
        f"All requested user_ids must be present in the result."
    )
