"""Property-based tests for Membership Soft-Delete.

Tests Property 18 from the admin-dashboard-user-management design document,
validating that when a membership is revoked, the database record persists
with a non-null revoked_at timestamp, and the record remains retrievable
in history queries (list_memberships).

**Validates: Requirements 11.3**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 18)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (11.3)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.company import CompanyMembership
from alcoabase.services.user_management import UserManagementService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VALID_ROLES = ["system_admin", "doc_admin", "it_admin", "member", "viewer"]


@st.composite
def st_membership(draw: st.DrawFn) -> dict:
    """Generate a valid membership record with random IDs and role.

    Returns:
        A dictionary with membership_id, user_id, company_id, and role.
    """
    membership_id = draw(st.integers(min_value=1, max_value=10000))
    user_id = draw(st.integers(min_value=1, max_value=10000))
    company_id = draw(st.integers(min_value=1, max_value=10000))
    role = draw(st.sampled_from(VALID_ROLES))
    return {
        "membership_id": membership_id,
        "user_id": user_id,
        "company_id": company_id,
        "role": role,
    }


@st.composite
def st_membership_list(draw: st.DrawFn) -> list[dict]:
    """Generate a list of memberships for a single user across companies.

    Generates between 1 and 5 memberships with unique company IDs,
    where some may be revoked and some active.

    Returns:
        A list of membership dictionaries with revoked status.
    """
    num = draw(st.integers(min_value=1, max_value=5))
    user_id = draw(st.integers(min_value=1, max_value=10000))
    company_ids = draw(
        st.lists(
            st.integers(min_value=1, max_value=10000),
            min_size=num,
            max_size=num,
            unique=True,
        )
    )
    memberships = []
    for i, company_id in enumerate(company_ids):
        role = draw(st.sampled_from(VALID_ROLES))
        is_revoked = draw(st.booleans())
        memberships.append({
            "membership_id": i + 1,
            "user_id": user_id,
            "company_id": company_id,
            "role": role,
            "is_revoked": is_revoked,
        })
    return memberships


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_membership(
    membership_id: int,
    user_id: int,
    company_id: int,
    role: str,
    revoked_at: datetime | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock CompanyMembership object.

    Args:
        membership_id: The membership ID.
        user_id: The user ID.
        company_id: The company ID.
        role: The role string.
        revoked_at: Optional revocation timestamp.
        created_at: Optional creation timestamp.

    Returns:
        A MagicMock simulating a CompanyMembership instance.
    """
    membership = MagicMock(spec=CompanyMembership)
    membership.id = membership_id
    membership.user_id = user_id
    membership.company_id = company_id
    membership.role = role
    membership.revoked_at = revoked_at
    membership.created_at = created_at or datetime.now(timezone.utc)
    return membership


# ---------------------------------------------------------------------------
# Property 18: Membership Soft-Delete — Record persists with non-null revoked_at
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(data=st_membership())
@pytest.mark.asyncio
async def test_revoke_membership_sets_revoked_at(data: dict) -> None:
    """For any active membership that is revoked, the revoke_membership method
    SHALL set revoked_at to a non-null UTC timestamp, and the record SHALL
    persist (not be deleted from the database).

    **Validates: Requirements 11.3**
    """
    service = UserManagementService()

    # Create a mock membership that simulates an active membership
    mock_membership = _make_mock_membership(
        membership_id=data["membership_id"],
        user_id=data["user_id"],
        company_id=data["company_id"],
        role=data["role"],
        revoked_at=None,  # Active membership
    )

    # Mock session: execute returns the membership
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_membership
    session.execute.return_value = result

    # Perform revocation
    revoked = await service.revoke_membership(
        membership_id=data["membership_id"],
        company_id=data["company_id"],
        session=session,
    )

    # Property: revoked_at is set to a non-null datetime
    assert revoked.revoked_at is not None
    assert isinstance(revoked.revoked_at, datetime)

    # Property: the timestamp is timezone-aware UTC
    assert revoked.revoked_at.tzinfo is not None

    # Property: the record is the same object (not deleted, persists)
    assert revoked.id == data["membership_id"]
    assert revoked.user_id == data["user_id"]
    assert revoked.company_id == data["company_id"]
    assert revoked.role == data["role"]

    # Property: session.flush() was called (record persisted, not deleted)
    session.flush.assert_awaited_once()

    # Property: session.delete() was NOT called (soft delete, not hard delete)
    session.delete.assert_not_called()


# ---------------------------------------------------------------------------
# Property 18: Membership Soft-Delete — Revoked record retrievable in history
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(memberships=st_membership_list())
@pytest.mark.asyncio
async def test_revoked_membership_retrievable_in_history(
    memberships: list[dict],
) -> None:
    """For any user with a mix of active and revoked memberships,
    list_memberships SHALL return ALL memberships (both active and revoked),
    and revoked memberships SHALL have non-null revoked_at timestamps.

    **Validates: Requirements 11.3**
    """
    service = UserManagementService()
    user_id = memberships[0]["user_id"]

    # Build mock membership objects
    mock_rows = []
    for m in memberships:
        revoked_at = datetime.now(timezone.utc) if m["is_revoked"] else None
        mock_membership = _make_mock_membership(
            membership_id=m["membership_id"],
            user_id=m["user_id"],
            company_id=m["company_id"],
            role=m["role"],
            revoked_at=revoked_at,
        )
        company_name = f"Company {m['company_id']}"
        # Each row is a tuple of (membership, company_display_name)
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx, _m=mock_membership, _cn=company_name: (
            _m if idx == 0 else _cn
        )
        mock_rows.append(mock_row)

    # Mock session: execute returns all rows
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = mock_rows
    session.execute.return_value = result

    # Call list_memberships
    result_list = await service.list_memberships(user_id=user_id, session=session)

    # Property: ALL memberships are returned (both active and revoked)
    assert len(result_list) == len(memberships)

    # Property: revoked memberships have non-null revoked_at
    for i, m in enumerate(memberships):
        entry = result_list[i]
        if m["is_revoked"]:
            assert entry["revoked_at"] is not None
            assert isinstance(entry["revoked_at"], datetime)
        else:
            assert entry["revoked_at"] is None

    # Property: all membership data is preserved in history
    for i, m in enumerate(memberships):
        entry = result_list[i]
        assert entry["user_id"] == m["user_id"]
        assert entry["company_id"] == m["company_id"]
        assert entry["role"] == m["role"]


# ---------------------------------------------------------------------------
# Property 18: Membership Soft-Delete — revoked_at timestamp is recent
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(data=st_membership())
@pytest.mark.asyncio
async def test_revoke_membership_timestamp_is_utc_and_recent(data: dict) -> None:
    """For any membership revocation, the revoked_at timestamp SHALL be
    a UTC datetime that is at or after the time the revocation was initiated.

    **Validates: Requirements 11.3**
    """
    service = UserManagementService()

    mock_membership = _make_mock_membership(
        membership_id=data["membership_id"],
        user_id=data["user_id"],
        company_id=data["company_id"],
        role=data["role"],
        revoked_at=None,
    )

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_membership
    session.execute.return_value = result

    before = datetime.now(timezone.utc)

    revoked = await service.revoke_membership(
        membership_id=data["membership_id"],
        company_id=data["company_id"],
        session=session,
    )

    after = datetime.now(timezone.utc)

    # Property: revoked_at is between before and after the call
    assert revoked.revoked_at >= before
    assert revoked.revoked_at <= after

    # Property: timezone is UTC
    assert revoked.revoked_at.tzinfo == timezone.utc
