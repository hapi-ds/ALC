"""Property-based tests for Membership Uniqueness enforcement.

Tests Property 17 from the admin-dashboard-user-management design document,
validating that for any (user_id, company_id) pair that already has an active
membership, attempting to create a duplicate membership SHALL be rejected
with HTTP 409 conflict.

**Validates: Requirements 11.2**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 17)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (11.2)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from fastapi import HTTPException
from hypothesis import given, settings

from alcoabase.services.user_management import UserManagementService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VALID_ROLES = ["system_admin", "doc_admin", "it_admin", "member", "viewer"]


@st.composite
def st_user_company_pair(draw: st.DrawFn) -> tuple[int, int]:
    """Generate a valid (user_id, company_id) pair.

    Returns:
        Tuple of (user_id, company_id) with positive integers.
    """
    user_id = draw(st.integers(min_value=1, max_value=10000))
    company_id = draw(st.integers(min_value=1, max_value=10000))
    return (user_id, company_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session_with_existing_membership() -> AsyncMock:
    """Create a mock AsyncSession that simulates an existing active membership.

    The mock session's execute method returns a result where
    scalar_one_or_none() returns a truthy value (a mock membership),
    simulating that an active membership already exists for the
    (user_id, company_id) pair.

    Returns:
        A mock AsyncSession.
    """
    session = AsyncMock()
    result = MagicMock()
    # Return a truthy value to indicate an existing active membership
    result.scalar_one_or_none.return_value = MagicMock()
    session.execute.return_value = result
    return session


def _make_mock_session_no_existing_membership() -> AsyncMock:
    """Create a mock AsyncSession that simulates no existing active membership.

    The first execute call (membership check) returns None.
    The second execute call (role lookup) returns a mock role object.

    Returns:
        A mock AsyncSession.
    """
    session = AsyncMock()

    # First call: membership check returns None (no existing membership)
    membership_result = MagicMock()
    membership_result.scalar_one_or_none.return_value = None

    # Second call: role lookup returns a mock role
    role_result = MagicMock()
    mock_role = MagicMock()
    mock_role.id = 1
    role_result.scalar_one_or_none.return_value = mock_role

    session.execute.side_effect = [membership_result, role_result]
    session.add = MagicMock()
    session.flush = AsyncMock()

    return session


# ---------------------------------------------------------------------------
# Property 17: Membership Uniqueness — Duplicate rejected with 409
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    pair=st_user_company_pair(),
    role=st.sampled_from(VALID_ROLES),
)
@pytest.mark.asyncio
async def test_duplicate_membership_rejected_with_409(
    pair: tuple[int, int],
    role: str,
) -> None:
    """For any (user_id, company_id) pair that already has an active membership,
    attempting to assign a new membership SHALL be rejected with HTTP 409.

    **Validates: Requirements 11.2**
    """
    user_id, company_id = pair
    service = UserManagementService()
    session = _make_mock_session_with_existing_membership()

    with pytest.raises(HTTPException) as exc_info:
        await service.assign_membership(user_id, company_id, role, session)

    assert exc_info.value.status_code == 409
    assert "active membership" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Property 17: Membership Uniqueness — Role variation does not bypass check
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    pair=st_user_company_pair(),
    existing_role=st.sampled_from(VALID_ROLES),
    new_role=st.sampled_from(VALID_ROLES),
)
@pytest.mark.asyncio
async def test_duplicate_membership_rejected_regardless_of_role(
    pair: tuple[int, int],
    existing_role: str,
    new_role: str,
) -> None:
    """For any (user_id, company_id) pair with an active membership,
    attempting to create another membership with ANY role (same or different)
    SHALL be rejected with HTTP 409.

    **Validates: Requirements 11.2**
    """
    user_id, company_id = pair
    service = UserManagementService()
    session = _make_mock_session_with_existing_membership()

    with pytest.raises(HTTPException) as exc_info:
        await service.assign_membership(user_id, company_id, new_role, session)

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# Property 17: Membership Uniqueness — New membership succeeds when no active exists
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    pair=st_user_company_pair(),
    role=st.sampled_from(VALID_ROLES),
)
@pytest.mark.asyncio
async def test_membership_creation_succeeds_when_no_active_exists(
    pair: tuple[int, int],
    role: str,
) -> None:
    """For any (user_id, company_id) pair that does NOT have an active
    membership, assigning a membership SHALL succeed without raising
    an exception.

    **Validates: Requirements 11.2**
    """
    user_id, company_id = pair
    service = UserManagementService()
    session = _make_mock_session_no_existing_membership()

    # Should not raise — no duplicate found
    result = await service.assign_membership(user_id, company_id, role, session)

    assert result is not None
    assert result.user_id == user_id
    assert result.company_id == company_id
    assert result.role == role
