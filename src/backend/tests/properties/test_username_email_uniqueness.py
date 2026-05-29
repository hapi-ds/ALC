"""Property-based tests for Username and Email Uniqueness Enforcement.

Tests Property 10 from the admin-dashboard-user-management design document,
validating that for any username or email that already exists in the system,
attempting to create a new user or update an existing user to use that
username/email SHALL be rejected with a 409 conflict error.

**Validates: Requirements 6.2, 6.3, 7.3**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 10)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (6.2, 6.3, 7.3)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from fastapi import HTTPException
from hypothesis import given, settings

from alcoabase.schemas.admin_users import UserCreateRequest, UserUpdateRequest
from alcoabase.services.user_management import UserManagementService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_valid_username(draw: st.DrawFn) -> str:
    """Generate a valid username matching ^[a-zA-Z0-9_.-]+$ with length 3-100.

    Returns:
        A valid username string.
    """
    length = draw(st.integers(min_value=3, max_value=30))
    username = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-",
            min_size=length,
            max_size=length,
        )
    )
    return username


@st.composite
def st_valid_email(draw: st.DrawFn) -> str:
    """Generate a valid email address.

    Returns:
        A valid email string in the form local@domain.tld.
    """
    local_len = draw(st.integers(min_value=1, max_value=15))
    local = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
            min_size=local_len,
            max_size=local_len,
        )
    )
    domain = draw(st.sampled_from(["example.com", "test.org", "company.io", "mail.net"]))
    return f"{local}@{domain}"


VALID_ROLES = ["system_admin", "doc_admin", "it_admin", "member", "viewer"]


def _make_mock_session_with_existing_user(
    existing_user_id: int,
) -> AsyncMock:
    """Create a mock AsyncSession that simulates finding an existing user.

    The mock session's execute method returns a result where
    scalar_one_or_none() returns the existing_user_id, simulating
    that a user with the given username/email already exists.

    Args:
        existing_user_id: The ID to return as the existing user.

    Returns:
        A mock AsyncSession.
    """
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_user_id
    session.execute.return_value = result
    return session


def _make_mock_session_no_existing_user() -> AsyncMock:
    """Create a mock AsyncSession that simulates no existing user found.

    The mock session's execute method returns a result where
    scalar_one_or_none() returns None, simulating that no user
    with the given username/email exists.

    Returns:
        A mock AsyncSession.
    """
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# Property 10: Username and Email Uniqueness Enforcement — Creation
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    username=st_valid_username(),
    email=st_valid_email(),
    existing_user_id=st.integers(min_value=1, max_value=10000),
)
@pytest.mark.asyncio
async def test_duplicate_username_rejected_on_creation(
    username: str,
    email: str,
    existing_user_id: int,
) -> None:
    """For any username that already exists in the system, attempting to
    create a new user with that username SHALL be rejected with HTTP 409.

    **Validates: Requirements 6.2**
    """
    service = UserManagementService()
    session = _make_mock_session_with_existing_user(existing_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await service._check_username_unique(username, session)

    assert exc_info.value.status_code == 409
    assert username in exc_info.value.detail


@settings(max_examples=100, deadline=None)
@given(
    username=st_valid_username(),
    email=st_valid_email(),
    existing_user_id=st.integers(min_value=1, max_value=10000),
)
@pytest.mark.asyncio
async def test_duplicate_email_rejected_on_creation(
    username: str,
    email: str,
    existing_user_id: int,
) -> None:
    """For any email that already exists in the system, attempting to
    create a new user with that email SHALL be rejected with HTTP 409.

    **Validates: Requirements 6.3**
    """
    service = UserManagementService()
    session = _make_mock_session_with_existing_user(existing_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await service._check_email_unique(email, session)

    assert exc_info.value.status_code == 409
    assert email in exc_info.value.detail


# ---------------------------------------------------------------------------
# Property 10: Username and Email Uniqueness Enforcement — Update
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    email=st_valid_email(),
    existing_user_id=st.integers(min_value=1, max_value=10000),
    updating_user_id=st.integers(min_value=10001, max_value=20000),
)
@pytest.mark.asyncio
async def test_duplicate_email_rejected_on_update(
    email: str,
    existing_user_id: int,
    updating_user_id: int,
) -> None:
    """For any email that already exists for a different user, attempting
    to update a user's email to that value SHALL be rejected with HTTP 409.

    **Validates: Requirements 7.3**
    """
    service = UserManagementService()
    # Session returns an existing user ID (different from the updating user)
    session = _make_mock_session_with_existing_user(existing_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await service._check_email_unique(
            email, session, exclude_user_id=updating_user_id
        )

    assert exc_info.value.status_code == 409
    assert email in exc_info.value.detail


# ---------------------------------------------------------------------------
# Property 10: Uniqueness passes when no duplicate exists
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    username=st_valid_username(),
)
@pytest.mark.asyncio
async def test_unique_username_accepted(
    username: str,
) -> None:
    """For any username that does NOT exist in the system, the uniqueness
    check SHALL pass without raising an exception.

    **Validates: Requirements 6.2**
    """
    service = UserManagementService()
    session = _make_mock_session_no_existing_user()

    # Should not raise — no duplicate found
    await service._check_username_unique(username, session)


@settings(max_examples=100, deadline=None)
@given(
    email=st_valid_email(),
)
@pytest.mark.asyncio
async def test_unique_email_accepted(
    email: str,
) -> None:
    """For any email that does NOT exist in the system, the uniqueness
    check SHALL pass without raising an exception.

    **Validates: Requirements 6.3**
    """
    service = UserManagementService()
    session = _make_mock_session_no_existing_user()

    # Should not raise — no duplicate found
    await service._check_email_unique(email, session)


# ---------------------------------------------------------------------------
# Property 10: Full create_user flow with duplicate username
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    username=st_valid_username(),
    email=st_valid_email(),
    full_name=st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "Zs"))),
    role=st.sampled_from(VALID_ROLES),
    company_id=st.integers(min_value=1, max_value=100),
    existing_user_id=st.integers(min_value=1, max_value=10000),
)
@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_username(
    username: str,
    email: str,
    full_name: str,
    role: str,
    company_id: int,
    existing_user_id: int,
) -> None:
    """For any valid user creation payload where the username already exists,
    the create_user method SHALL raise HTTPException with status 409.

    **Validates: Requirements 6.2**
    """
    service = UserManagementService()

    # Mock session: first execute call (username check) finds a duplicate
    session = AsyncMock()
    username_result = MagicMock()
    username_result.scalar_one_or_none.return_value = existing_user_id
    session.execute.return_value = username_result

    payload = UserCreateRequest(
        username=username,
        email=email,
        full_name=full_name.strip() or "Test User",
        role=role,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_user(payload, company_id, session)

    assert exc_info.value.status_code == 409
    assert username in exc_info.value.detail


# ---------------------------------------------------------------------------
# Property 10: Full create_user flow with duplicate email
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    username=st_valid_username(),
    email=st_valid_email(),
    full_name=st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "Zs"))),
    role=st.sampled_from(VALID_ROLES),
    company_id=st.integers(min_value=1, max_value=100),
    existing_user_id=st.integers(min_value=1, max_value=10000),
)
@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_email(
    username: str,
    email: str,
    full_name: str,
    role: str,
    company_id: int,
    existing_user_id: int,
) -> None:
    """For any valid user creation payload where the email already exists,
    the create_user method SHALL raise HTTPException with status 409.

    **Validates: Requirements 6.3**
    """
    service = UserManagementService()

    # Mock session: first execute call (username check) passes,
    # second execute call (email check) finds a duplicate
    session = AsyncMock()
    username_result = MagicMock()
    username_result.scalar_one_or_none.return_value = None  # Username is unique

    email_result = MagicMock()
    email_result.scalar_one_or_none.return_value = existing_user_id  # Email is duplicate

    session.execute.side_effect = [username_result, email_result]

    payload = UserCreateRequest(
        username=username,
        email=email,
        full_name=full_name.strip() or "Test User",
        role=role,
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_user(payload, company_id, session)

    assert exc_info.value.status_code == 409
    assert email in exc_info.value.detail
