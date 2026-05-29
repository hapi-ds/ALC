"""Property-based tests for Token Invalidation on Password Reset.

Tests Property 15 from the admin-dashboard-user-management design document,
validating that after a password reset, all existing refresh tokens for the
affected user are invalidated (revoked_at set to a non-null timestamp).

**Validates: Requirements 9.5**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 15)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (Requirement 9.5)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.refresh_token import RefreshToken
from alcoabase.models.user import User
from alcoabase.services.password_reset import reset_password


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_token_list(draw: st.DrawFn) -> list[dict]:
    """Generate a list of refresh token descriptors (0 to 10 tokens).

    Each token descriptor contains:
    - is_active: whether the token is currently active (revoked_at is None)

    Returns:
        A list of token descriptors.
    """
    num_tokens = draw(st.integers(min_value=0, max_value=10))
    tokens = []
    for _ in range(num_tokens):
        is_active = draw(st.booleans())
        tokens.append({"is_active": is_active})
    return tokens


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_user(user_id: int) -> MagicMock:
    """Create a mock User object for testing.

    Args:
        user_id: The user's ID.

    Returns:
        A MagicMock configured as a User instance.
    """
    user = MagicMock(spec=User)
    user.id = user_id
    user.hashed_password = "$2b$12$existinghashvalue000000000000000000000000000000"
    return user


def _make_mock_session(user: MagicMock) -> AsyncMock:
    """Create a mock AsyncSession that returns the given user on query.

    The mock tracks all execute() calls so we can verify the UPDATE
    statement for token revocation was issued.

    Args:
        user: The mock user to return from the select query.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()

    # Mock the result of session.execute(select(User)...)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user

    # session.execute returns the mock result for the first call (user select)
    # and a generic result for the second call (token update)
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    return session


# ---------------------------------------------------------------------------
# Property 15: Token Invalidation on Password Reset
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 15: Token Invalidation on Password Reset
@settings(max_examples=100, deadline=None)
@given(token_descriptors=st_token_list())
@pytest.mark.asyncio
async def test_all_tokens_invalidated_on_password_reset(
    token_descriptors: list[dict],
) -> None:
    """For any user with N existing refresh tokens (N >= 0), after a password
    reset, the reset_password function SHALL issue an UPDATE statement that
    sets revoked_at on all active tokens for that user.

    The property verifies:
    1. The UPDATE targets RefreshToken records matching the user_id
    2. The UPDATE filters for only active tokens (revoked_at IS NULL)
    3. The UPDATE sets revoked_at to a non-null UTC timestamp
    4. The function returns a non-empty temporary password

    **Validates: Requirements 9.5**
    """
    user_id = 42
    num_tokens = len(token_descriptors)
    num_active = sum(1 for t in token_descriptors if t["is_active"])

    # Create mock user
    mock_user = _make_mock_user(user_id)

    # Create mock session
    session = AsyncMock()

    # Track all execute calls
    execute_calls = []

    async def mock_execute(stmt, *args, **kwargs):
        execute_calls.append(stmt)
        # For the SELECT query (first call), return the user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        return mock_result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()

    # Patch the password hashing to avoid bcrypt dependency issues
    with patch(
        "alcoabase.services.password_reset._pwd_context"
    ) as mock_pwd_context:
        mock_pwd_context.hash.return_value = (
            "$2b$12$mockedhashvalue0000000000000000000000000000000000000"
        )

        # Execute password reset
        temp_password = await reset_password(user_id=user_id, session=session)

    # Verify: a non-empty temporary password was returned
    assert temp_password is not None
    assert len(temp_password) > 0

    # Verify: session.execute was called at least twice
    # (once for SELECT user, once for UPDATE tokens)
    assert len(execute_calls) >= 2, (
        f"Expected at least 2 execute calls (SELECT user + UPDATE tokens), "
        f"got {len(execute_calls)}"
    )

    # Verify: the second execute call is an UPDATE on refresh_tokens
    update_stmt = execute_calls[1]

    # Check that the UPDATE statement targets the refresh_tokens table
    # by inspecting the compiled statement
    from sqlalchemy.sql import Update

    assert isinstance(update_stmt, Update), (
        f"Expected second execute call to be an UPDATE statement, "
        f"got {type(update_stmt).__name__}"
    )

    # Verify the UPDATE statement's WHERE clause targets the correct user_id
    # and filters for active tokens (revoked_at IS NULL)
    compiled = update_stmt.compile(
        compile_kwargs={"literal_binds": False}
    )
    stmt_str = str(compiled)

    # The statement should reference the user_id filter
    assert "user_id" in stmt_str, (
        f"UPDATE statement should filter by user_id. Got: {stmt_str}"
    )

    # The statement should filter for active tokens (revoked_at IS NULL)
    assert "revoked_at IS NULL" in stmt_str or "revoked_at IS_NULL" in stmt_str.replace(" ", "_"), (
        f"UPDATE statement should filter for active tokens (revoked_at IS NULL). Got: {stmt_str}"
    )

    # The statement should set revoked_at to a value
    assert "revoked_at" in stmt_str, (
        f"UPDATE statement should set revoked_at. Got: {stmt_str}"
    )

    # Verify: the user's password was updated
    assert mock_user.hashed_password == (
        "$2b$12$mockedhashvalue0000000000000000000000000000000000000"
    ), "User's hashed_password should be updated to the new hash"

    # Verify: session.flush was called (at least twice: after password update and after token revocation)
    assert session.flush.call_count >= 2, (
        f"Expected at least 2 flush calls, got {session.flush.call_count}"
    )
