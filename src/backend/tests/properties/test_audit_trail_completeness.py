"""Property-based tests for Audit Trail Completeness.

Tests Property 12 from the admin-dashboard-user-management design document,
validating that all user management mutations (create, update, deactivate,
reactivate, password reset, role change, membership change) trigger
session.flush() which activates SQLAlchemy-Continuum versioning. The
AuditMiddleware ensures X-Change-Reason is present on all mutations, and
the audit context (acting user ID, timestamp, reason) is stored on
request.state for Continuum's transaction context.

**Validates: Requirements 6.7, 7.5, 8.5, 9.4, 11.5, 14.2**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 12)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.company import CompanyMembership
from alcoabase.models.user import Role, User
from alcoabase.schemas.admin_users import UserCreateRequest, UserUpdateRequest
from alcoabase.services.user_management import UserManagementService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VALID_ROLES = ["system_admin", "doc_admin", "it_admin", "member", "viewer"]


@st.composite
def st_mutation_type(draw: st.DrawFn) -> str:
    """Generate a random user management mutation type.

    Returns:
        One of the seven mutation operation names.
    """
    return draw(
        st.sampled_from([
            "create",
            "update",
            "deactivate",
            "reactivate",
            "role_change",
            "membership_assign",
            "membership_revoke",
        ])
    )


@st.composite
def st_user_create_payload(draw: st.DrawFn) -> dict:
    """Generate a valid user creation payload.

    Returns:
        A dictionary with username, email, full_name, and role.
    """
    username = draw(
        st.from_regex(r"[a-zA-Z][a-zA-Z0-9_.]{2,19}", fullmatch=True)
    )
    email = draw(st.emails())
    full_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "Zs"),
    )))
    role = draw(st.sampled_from(VALID_ROLES))
    return {
        "username": username,
        "email": str(email),
        "full_name": full_name,
        "role": role,
    }


@st.composite
def st_user_update_payload(draw: st.DrawFn) -> dict:
    """Generate a valid user update payload with at least one field set.

    Returns:
        A dictionary with optional full_name, email, and role fields.
    """
    fields: dict = {}
    if draw(st.booleans()):
        fields["full_name"] = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=("L", "Zs"),
        )))
    if draw(st.booleans()):
        fields["email"] = str(draw(st.emails()))
    if draw(st.booleans()):
        fields["role"] = draw(st.sampled_from(VALID_ROLES))
    # Ensure at least one field is set
    if not fields:
        fields["full_name"] = "Updated Name"
    return fields


@st.composite
def st_audit_context(draw: st.DrawFn) -> dict:
    """Generate audit context metadata (acting user ID, company ID).

    Returns:
        A dictionary with acting_user_id and company_id.
    """
    acting_user_id = draw(st.integers(min_value=1, max_value=10000))
    company_id = draw(st.integers(min_value=1, max_value=10000))
    target_user_id = draw(
        st.integers(min_value=1, max_value=10000).filter(
            lambda x: x != acting_user_id
        )
    )
    return {
        "acting_user_id": acting_user_id,
        "company_id": company_id,
        "target_user_id": target_user_id,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_user(user_id: int, is_active: bool = True) -> MagicMock:
    """Create a mock User object.

    Args:
        user_id: The user's ID.
        is_active: Whether the user is active.

    Returns:
        A MagicMock simulating a User instance.
    """
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = f"user_{user_id}"
    user.email = f"user_{user_id}@example.com"
    user.full_name = f"User {user_id}"
    user.is_active = is_active
    user.hashed_password = "$2b$12$existinghash"
    return user


def _make_mock_role(role_name: str, role_id: int = 1) -> MagicMock:
    """Create a mock Role object.

    Args:
        role_name: The role name.
        role_id: The role ID.

    Returns:
        A MagicMock simulating a Role instance.
    """
    role = MagicMock(spec=Role)
    role.id = role_id
    role.name = role_name
    return role


def _make_mock_membership(
    membership_id: int,
    user_id: int,
    company_id: int,
    role: str,
) -> MagicMock:
    """Create a mock CompanyMembership object.

    Args:
        membership_id: The membership ID.
        user_id: The user ID.
        company_id: The company ID.
        role: The role string.

    Returns:
        A MagicMock simulating a CompanyMembership instance.
    """
    membership = MagicMock(spec=CompanyMembership)
    membership.id = membership_id
    membership.user_id = user_id
    membership.company_id = company_id
    membership.role = role
    membership.role_id = 1
    membership.revoked_at = None
    membership.created_at = datetime.now(timezone.utc)
    return membership


def _make_session_for_create(mock_role: MagicMock) -> AsyncMock:
    """Create a mock session configured for user creation flow.

    The session mocks:
    - Username uniqueness check (no existing user)
    - Email uniqueness check (no existing user)
    - Role lookup (returns mock_role)

    Args:
        mock_role: The mock role to return from role lookup.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()
    call_count = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        # First two calls: uniqueness checks (return None = no conflict)
        # Third call: role lookup (return the role)
        if call_count["n"] <= 2:
            result.scalar_one_or_none.return_value = None
        else:
            result.scalar_one_or_none.return_value = mock_role
        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _make_session_for_update(
    mock_user: MagicMock,
    mock_role: MagicMock,
    mock_membership: MagicMock,
    has_email_change: bool = False,
) -> AsyncMock:
    """Create a mock session configured for user update flow.

    The update flow calls:
    1. _get_user_or_404 → returns user
    2. (if email changed) _check_email_unique → returns None (no conflict)
    3. (if role changed) _get_role_by_name → returns role
    4. (if role changed) _get_active_membership → returns membership

    Args:
        mock_user: The mock user to return.
        mock_role: The mock role to return for role changes.
        mock_membership: The mock membership to return.
        has_email_change: Whether the update includes an email change.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()
    call_count = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        if call_count["n"] == 1:
            # First call: _get_user_or_404
            result.scalar_one_or_none.return_value = mock_user
        elif call_count["n"] == 2:
            if has_email_change:
                # Email uniqueness check: return None (no conflict)
                result.scalar_one_or_none.return_value = None
            else:
                # Role lookup
                result.scalar_one_or_none.return_value = mock_role
        elif call_count["n"] == 3:
            if has_email_change:
                # Role lookup (after email check)
                result.scalar_one_or_none.return_value = mock_role
            else:
                # Membership lookup
                result.scalar_one_or_none.return_value = mock_membership
        else:
            # Membership lookup
            result.scalar_one_or_none.return_value = mock_membership
        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()
    return session


def _make_session_for_deactivate(
    mock_user: MagicMock,
    mock_membership: MagicMock,
) -> AsyncMock:
    """Create a mock session configured for deactivation/reactivation.

    Args:
        mock_user: The mock user to return.
        mock_membership: The mock membership to return.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()
    call_count = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        if call_count["n"] == 1:
            result.scalar_one_or_none.return_value = mock_user
        else:
            result.scalar_one_or_none.return_value = mock_membership
        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()
    return session


def _make_session_for_membership_assign(mock_role: MagicMock) -> AsyncMock:
    """Create a mock session configured for membership assignment.

    Args:
        mock_role: The mock role to return from role lookup.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()
    call_count = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        if call_count["n"] == 1:
            # First call: check existing membership (none found)
            result.scalar_one_or_none.return_value = None
        else:
            # Second call: role lookup
            result.scalar_one_or_none.return_value = mock_role
        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _make_session_for_membership_revoke(mock_membership: MagicMock) -> AsyncMock:
    """Create a mock session configured for membership revocation.

    Args:
        mock_membership: The mock membership to return.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()

    async def mock_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_membership
        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — Create user triggers flush
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(
    payload_data=st_user_create_payload(),
    ctx=st_audit_context(),
)
@pytest.mark.asyncio
async def test_create_user_triggers_audit_flush(
    payload_data: dict,
    ctx: dict,
) -> None:
    """For any user creation mutation, session.flush() SHALL be called
    (triggering SQLAlchemy-Continuum versioning), ensuring an audit record
    is created with the acting user context.

    **Validates: Requirements 6.7, 14.2**
    """
    service = UserManagementService()
    mock_role = _make_mock_role(payload_data["role"])
    session = _make_session_for_create(mock_role)

    payload = UserCreateRequest(**payload_data)

    user, temp_password = await service.create_user(
        payload=payload,
        company_id=ctx["company_id"],
        session=session,
    )

    # Property: session.flush() was called at least once (triggers Continuum)
    assert session.flush.call_count >= 1, (
        "create_user must call session.flush() to trigger "
        "SQLAlchemy-Continuum audit versioning"
    )

    # Property: session.add() was called (record persisted, not discarded)
    assert session.add.call_count >= 1, (
        "create_user must call session.add() to persist the user record"
    )


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — Update user triggers flush
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(
    update_data=st_user_update_payload(),
    ctx=st_audit_context(),
)
@pytest.mark.asyncio
async def test_update_user_triggers_audit_flush(
    update_data: dict,
    ctx: dict,
) -> None:
    """For any user update mutation (profile or role change), session.flush()
    SHALL be called, triggering SQLAlchemy-Continuum versioning for the
    modified fields.

    **Validates: Requirements 7.5, 14.2**
    """
    service = UserManagementService()
    mock_user = _make_mock_user(ctx["target_user_id"])
    mock_role = _make_mock_role(update_data.get("role", "member"))
    mock_membership = _make_mock_membership(
        membership_id=1,
        user_id=ctx["target_user_id"],
        company_id=ctx["company_id"],
        role="member",
    )
    has_email = "email" in update_data and update_data["email"] != mock_user.email
    session = _make_session_for_update(
        mock_user, mock_role, mock_membership, has_email_change=has_email
    )

    payload = UserUpdateRequest(**update_data)

    await service.update_user(
        user_id=ctx["target_user_id"],
        payload=payload,
        company_id=ctx["company_id"],
        session=session,
    )

    # Property: session.flush() was called (triggers Continuum versioning)
    assert session.flush.call_count >= 1, (
        "update_user must call session.flush() to trigger "
        "SQLAlchemy-Continuum audit versioning"
    )


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — Deactivate user triggers flush
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(ctx=st_audit_context())
@pytest.mark.asyncio
async def test_deactivate_user_triggers_audit_flush(ctx: dict) -> None:
    """For any user deactivation mutation, session.flush() SHALL be called,
    triggering SQLAlchemy-Continuum versioning for the is_active field change.

    **Validates: Requirements 8.5, 14.2**
    """
    service = UserManagementService()
    mock_user = _make_mock_user(ctx["target_user_id"], is_active=True)
    mock_membership = _make_mock_membership(
        membership_id=1,
        user_id=ctx["target_user_id"],
        company_id=ctx["company_id"],
        role="member",
    )
    session = _make_session_for_deactivate(mock_user, mock_membership)

    await service.deactivate_user(
        user_id=ctx["target_user_id"],
        acting_user_id=ctx["acting_user_id"],
        company_id=ctx["company_id"],
        session=session,
    )

    # Property: session.flush() was called (triggers Continuum versioning)
    assert session.flush.call_count >= 1, (
        "deactivate_user must call session.flush() to trigger "
        "SQLAlchemy-Continuum audit versioning"
    )

    # Property: is_active was set to False (the mutation occurred)
    assert mock_user.is_active is False


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — Reactivate user triggers flush
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(ctx=st_audit_context())
@pytest.mark.asyncio
async def test_reactivate_user_triggers_audit_flush(ctx: dict) -> None:
    """For any user reactivation mutation, session.flush() SHALL be called,
    triggering SQLAlchemy-Continuum versioning for the is_active field change.

    **Validates: Requirements 8.5, 14.2**
    """
    service = UserManagementService()
    mock_user = _make_mock_user(ctx["target_user_id"], is_active=False)
    mock_membership = _make_mock_membership(
        membership_id=1,
        user_id=ctx["target_user_id"],
        company_id=ctx["company_id"],
        role="member",
    )
    session = _make_session_for_deactivate(mock_user, mock_membership)

    await service.reactivate_user(
        user_id=ctx["target_user_id"],
        company_id=ctx["company_id"],
        session=session,
    )

    # Property: session.flush() was called (triggers Continuum versioning)
    assert session.flush.call_count >= 1, (
        "reactivate_user must call session.flush() to trigger "
        "SQLAlchemy-Continuum audit versioning"
    )

    # Property: is_active was set to True (the mutation occurred)
    assert mock_user.is_active is True


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — Password reset triggers flush
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(ctx=st_audit_context())
@pytest.mark.asyncio
async def test_password_reset_triggers_audit_flush(ctx: dict) -> None:
    """For any password reset mutation, session.flush() SHALL be called,
    triggering SQLAlchemy-Continuum versioning for the password change.
    The password value itself SHALL NOT appear in the audit record.

    **Validates: Requirements 9.4, 14.2**
    """
    from alcoabase.services.password_reset import reset_password

    mock_user = _make_mock_user(ctx["target_user_id"])
    session = AsyncMock()

    async def mock_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_user
        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()

    with patch(
        "alcoabase.services.password_reset._pwd_context"
    ) as mock_pwd_context:
        mock_pwd_context.hash.return_value = (
            "$2b$12$mockedhashvalue0000000000000000000000000000000000000"
        )

        temp_password = await reset_password(
            user_id=ctx["target_user_id"],
            session=session,
        )

    # Property: session.flush() was called (triggers Continuum versioning)
    assert session.flush.call_count >= 1, (
        "reset_password must call session.flush() to trigger "
        "SQLAlchemy-Continuum audit versioning"
    )

    # Property: a temporary password was returned (mutation occurred)
    assert temp_password is not None
    assert len(temp_password) > 0


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — Membership assign triggers flush
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(
    role=st.sampled_from(VALID_ROLES),
    ctx=st_audit_context(),
)
@pytest.mark.asyncio
async def test_membership_assign_triggers_audit_flush(
    role: str,
    ctx: dict,
) -> None:
    """For any membership assignment mutation, session.flush() SHALL be called,
    triggering SQLAlchemy-Continuum versioning for the new membership record.

    **Validates: Requirements 11.5, 14.2**
    """
    service = UserManagementService()
    mock_role = _make_mock_role(role)
    session = _make_session_for_membership_assign(mock_role)

    await service.assign_membership(
        user_id=ctx["target_user_id"],
        company_id=ctx["company_id"],
        role=role,
        session=session,
    )

    # Property: session.flush() was called (triggers Continuum versioning)
    assert session.flush.call_count >= 1, (
        "assign_membership must call session.flush() to trigger "
        "SQLAlchemy-Continuum audit versioning"
    )

    # Property: session.add() was called (record persisted)
    assert session.add.call_count >= 1, (
        "assign_membership must call session.add() to persist the membership"
    )


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — Membership revoke triggers flush
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(ctx=st_audit_context())
@pytest.mark.asyncio
async def test_membership_revoke_triggers_audit_flush(ctx: dict) -> None:
    """For any membership revocation mutation, session.flush() SHALL be called,
    triggering SQLAlchemy-Continuum versioning for the revoked_at field change.

    **Validates: Requirements 11.5, 14.2**
    """
    service = UserManagementService()
    mock_membership = _make_mock_membership(
        membership_id=1,
        user_id=ctx["target_user_id"],
        company_id=ctx["company_id"],
        role="member",
    )
    session = _make_session_for_membership_revoke(mock_membership)

    revoked = await service.revoke_membership(
        membership_id=1,
        company_id=ctx["company_id"],
        session=session,
    )

    # Property: session.flush() was called (triggers Continuum versioning)
    assert session.flush.call_count >= 1, (
        "revoke_membership must call session.flush() to trigger "
        "SQLAlchemy-Continuum audit versioning"
    )

    # Property: revoked_at was set (the mutation occurred)
    assert revoked.revoked_at is not None


# ---------------------------------------------------------------------------
# Property 12: Audit Trail Completeness — AuditMiddleware enforces X-Change-Reason
# ---------------------------------------------------------------------------


# Feature: Step_6-1_admin-dashboard-user-management, Property 12: Audit Trail Completeness
@settings(max_examples=50, deadline=None)
@given(
    mutation_method=st.sampled_from(["POST", "PUT", "PATCH", "DELETE"]),
    path=st.sampled_from([
        "/api/admin/users",
        "/api/admin/users/1",
        "/api/admin/users/1/deactivate",
        "/api/admin/users/1/reactivate",
        "/api/admin/users/1/reset-password",
        "/api/admin/memberships",
        "/api/admin/memberships/1",
    ]),
    reason=st.text(min_size=1, max_size=200, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs", "P"),
    )),
)
@pytest.mark.asyncio
async def test_audit_middleware_stores_change_reason(
    mutation_method: str,
    path: str,
    reason: str,
) -> None:
    """For any mutating request to admin endpoints with a valid X-Change-Reason
    header, the AuditMiddleware SHALL store the reason on request.state
    for SQLAlchemy-Continuum's transaction context.

    **Validates: Requirements 6.7, 7.5, 8.5, 9.4, 11.5, 14.2**
    """
    from alcoabase.middleware.audit_middleware import AuditMiddleware

    # Create a mock ASGI app
    mock_app = AsyncMock()

    middleware = AuditMiddleware(mock_app, require_reason_for_mutations=True)

    # Create a mock request with the required headers
    mock_request = MagicMock()
    mock_request.method = mutation_method
    mock_request.url.path = path

    # Use a MagicMock for headers that supports both dict-like access and .get()
    headers_data = {
        "X-Change-Reason": reason,
        "X-User-Id": "42",
    }
    mock_headers = MagicMock()
    mock_headers.get = lambda key, default=None: headers_data.get(key, default)
    mock_request.headers = mock_headers

    # Mock request.state as a simple namespace
    class MockState:
        pass

    mock_request.state = MockState()

    # Mock call_next to return a response
    mock_response = MagicMock()
    mock_response.status_code = 200
    call_next = AsyncMock(return_value=mock_response)

    response = await middleware.dispatch(mock_request, call_next)

    # Property: the middleware stored the audit reason on request.state
    assert hasattr(mock_request.state, "audit_reason"), (
        "AuditMiddleware must store X-Change-Reason on request.state.audit_reason"
    )
    assert mock_request.state.audit_reason == reason, (
        f"Expected audit_reason='{reason}', got '{mock_request.state.audit_reason}'"
    )

    # Property: the middleware stored the acting user ID
    assert hasattr(mock_request.state, "audit_user_id"), (
        "AuditMiddleware must store acting user ID on request.state.audit_user_id"
    )
    assert mock_request.state.audit_user_id == "42"

    # Property: the middleware stored a timestamp
    assert hasattr(mock_request.state, "audit_timestamp"), (
        "AuditMiddleware must store a timestamp on request.state.audit_timestamp"
    )
    assert isinstance(mock_request.state.audit_timestamp, datetime)
    assert mock_request.state.audit_timestamp.tzinfo is not None

    # Property: the request was passed through (not rejected)
    call_next.assert_awaited_once()
