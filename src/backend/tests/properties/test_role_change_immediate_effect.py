"""Property-based tests for Role Change Immediate Effect.

Tests Property 16 from the admin-dashboard-user-management design document:
Change user role from role_A to role_B, verify all subsequent permission
evaluations use role_B's permissions with no stale cache.

**Validates: Requirements 7.4**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 16)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (7.4)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.models.company import CompanyMembership
from alcoabase.models.user import Role, User
from alcoabase.services.rbac import (
    ACTIONS,
    DEFAULT_ROLE_PERMISSIONS,
    RESOURCE_TYPES,
    AccessDenied,
    AccessGranted,
    RBACService,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLE_NAMES = list(DEFAULT_ROLE_PERMISSIONS.keys())


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine synchronously for use within hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Mock session builder
# ---------------------------------------------------------------------------


def _build_mock_session_for_check(
    user: User,
    membership: CompanyMembership,
    role: Role,
) -> AsyncMock:
    """Build a mock AsyncSession for a single check_permission call.

    The RBACService.check_permission issues queries in this order:
    1. select(User).where(User.id == user_id) → returns user
    2. select(CompanyMembership).where(...) → returns membership for company
    3. select(Role).where(Role.id == membership.role_id) → returns role

    Args:
        user: The User instance to return for the user query.
        membership: The CompanyMembership to return.
        role: The Role to return.

    Returns:
        A mock AsyncSession configured for a single check_permission call.
    """
    session = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    membership_result = MagicMock()
    membership_result.scalar_one_or_none.return_value = membership

    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    session.execute = AsyncMock(
        side_effect=[user_result, membership_result, role_result]
    )

    return session


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_two_distinct_roles(draw: st.DrawFn) -> tuple[str, str]:
    """Generate two distinct role names from the predefined set.

    Returns:
        A tuple of (role_a, role_b) where role_a != role_b.
    """
    role_a = draw(st.sampled_from(ROLE_NAMES))
    role_b = draw(st.sampled_from([r for r in ROLE_NAMES if r != role_a]))
    return role_a, role_b


@st.composite
def st_resource_action(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a random (resource, action) pair.

    Returns:
        A tuple of (resource_type, action) strings.
    """
    resource = draw(st.sampled_from(RESOURCE_TYPES))
    action = draw(st.sampled_from(ACTIONS))
    return resource, action


# ---------------------------------------------------------------------------
# Property 16: Role Change Immediate Effect
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    roles=st_two_distinct_roles(),
    resource_action=st_resource_action(),
)
def test_role_change_immediate_effect(
    roles: tuple[str, str],
    resource_action: tuple[str, str],
) -> None:
    """After changing a user's role from role_A to role_B, all subsequent
    permission evaluations SHALL use role_B's permissions with no stale
    cache from role_A.

    This test simulates:
    1. User has role_A → evaluate permission → result matches role_A
    2. Role is changed to role_B (membership.role_id updated)
    3. Evaluate same permission again → result matches role_B (not role_A)

    **Validates: Requirements 7.4**
    """
    role_a_name, role_b_name = roles
    resource, action = resource_action

    user_id = 1
    company_id = 10
    role_a_id = 100
    role_b_id = 200

    # Create active user
    user = User(
        id=user_id,
        username="role_change_user",
        email="rolechange@test.local",
        hashed_password="hashed_placeholder",
        full_name="Role Change User",
        is_active=True,
    )

    # Create both roles
    role_a = Role(
        id=role_a_id,
        name=role_a_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_a_name],
        company_id=company_id,
        is_system=True,
    )
    role_b = Role(
        id=role_b_id,
        name=role_b_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_b_name],
        company_id=company_id,
        is_system=True,
    )

    # Membership initially pointing to role_a
    membership_before = CompanyMembership(
        id=1,
        user_id=user_id,
        company_id=company_id,
        role=role_a_name,
        role_id=role_a_id,
    )

    # Membership after role change pointing to role_b
    membership_after = CompanyMembership(
        id=1,
        user_id=user_id,
        company_id=company_id,
        role=role_b_name,
        role_id=role_b_id,
    )

    async def _test():
        rbac = RBACService()

        # --- Step 1: Evaluate permission with role_A ---
        session_before = _build_mock_session_for_check(
            user, membership_before, role_a
        )
        result_before = await rbac.check_permission(
            user_id=user_id,
            company_id=company_id,
            resource=resource,
            action=action,
            session=session_before,
        )

        # Verify result matches role_A's permissions
        permissions_a = DEFAULT_ROLE_PERMISSIONS[role_a_name]
        expected_granted_a = action in permissions_a.get(resource, [])

        if expected_granted_a:
            assert isinstance(result_before, AccessGranted), (
                f"Before role change: expected AccessGranted for role={role_a_name} "
                f"on {resource}:{action}, got AccessDenied: {result_before.reason}"
            )
        else:
            assert isinstance(result_before, AccessDenied), (
                f"Before role change: expected AccessDenied for role={role_a_name} "
                f"on {resource}:{action}, got AccessGranted"
            )

        # --- Step 2: Simulate role change (membership now points to role_B) ---
        # The role change updates membership.role_id in the database.
        # Since RBACService loads from DB each time (no caching), the next
        # check_permission call should see the new role.

        # --- Step 3: Evaluate permission with role_B ---
        session_after = _build_mock_session_for_check(
            user, membership_after, role_b
        )
        result_after = await rbac.check_permission(
            user_id=user_id,
            company_id=company_id,
            resource=resource,
            action=action,
            session=session_after,
        )

        # Verify result matches role_B's permissions (NOT role_A's)
        permissions_b = DEFAULT_ROLE_PERMISSIONS[role_b_name]
        expected_granted_b = action in permissions_b.get(resource, [])

        if expected_granted_b:
            assert isinstance(result_after, AccessGranted), (
                f"After role change to {role_b_name}: expected AccessGranted "
                f"on {resource}:{action}, got AccessDenied: {result_after.reason}. "
                f"Stale cache from previous role {role_a_name} may be in effect."
            )
        else:
            assert isinstance(result_after, AccessDenied), (
                f"After role change to {role_b_name}: expected AccessDenied "
                f"on {resource}:{action}, got AccessGranted. "
                f"Stale cache from previous role {role_a_name} may be in effect."
            )

        # --- Key property assertion ---
        # When role_A and role_B differ on this resource:action, the results
        # MUST differ, proving no stale cache persists after role change.
        if expected_granted_a != expected_granted_b:
            assert type(result_before) != type(result_after), (
                f"Role change not immediately effective! "
                f"Before (role={role_a_name}): {type(result_before).__name__}, "
                f"After (role={role_b_name}): {type(result_after).__name__}. "
                f"Expected different results for {resource}:{action} since "
                f"role_A grants={expected_granted_a}, role_B grants={expected_granted_b}. "
                f"This indicates stale permission state after role change."
            )

    _run_async(_test())


@settings(max_examples=100, deadline=None)
@given(roles=st_two_distinct_roles())
def test_role_change_all_permissions_reflect_new_role(
    roles: tuple[str, str],
) -> None:
    """After a role change from role_A to role_B, evaluating ALL resource:action
    pairs SHALL produce results consistent with role_B's permission set, with
    no residual permissions from role_A leaking through.

    **Validates: Requirements 7.4**
    """
    role_a_name, role_b_name = roles

    user_id = 1
    company_id = 10
    role_b_id = 200

    # Create active user
    user = User(
        id=user_id,
        username="role_change_user",
        email="rolechange@test.local",
        hashed_password="hashed_placeholder",
        full_name="Role Change User",
        is_active=True,
    )

    # Create role_B (the new role after change)
    role_b = Role(
        id=role_b_id,
        name=role_b_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_b_name],
        company_id=company_id,
        is_system=True,
    )

    # Membership after role change (now pointing to role_B)
    membership_after = CompanyMembership(
        id=1,
        user_id=user_id,
        company_id=company_id,
        role=role_b_name,
        role_id=role_b_id,
    )

    # Find permissions that role_A had but role_B does NOT
    permissions_a = DEFAULT_ROLE_PERMISSIONS[role_a_name]
    permissions_b = DEFAULT_ROLE_PERMISSIONS[role_b_name]

    exclusive_to_a: list[tuple[str, str]] = []
    for resource in RESOURCE_TYPES:
        actions_a = set(permissions_a.get(resource, []))
        actions_b = set(permissions_b.get(resource, []))
        for act in actions_a - actions_b:
            exclusive_to_a.append((resource, act))

    # If role_A has no exclusive permissions over role_B, skip
    if not exclusive_to_a:
        return

    async def _test():
        rbac = RBACService()

        # After role change to role_B, permissions exclusive to role_A
        # MUST be denied — proving no stale permissions leak through
        for resource, action in exclusive_to_a:
            session = _build_mock_session_for_check(
                user, membership_after, role_b
            )
            result = await rbac.check_permission(
                user_id=user_id,
                company_id=company_id,
                resource=resource,
                action=action,
                session=session,
            )

            assert isinstance(result, AccessDenied), (
                f"Stale permission detected after role change! "
                f"Permission {resource}:{action} was granted after changing "
                f"from {role_a_name} to {role_b_name}, but {role_b_name} "
                f"does not include this permission. Previous role's permissions "
                f"are leaking through (no-cache violation)."
            )

    _run_async(_test())
