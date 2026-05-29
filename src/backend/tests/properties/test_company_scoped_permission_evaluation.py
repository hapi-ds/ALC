"""Property-based tests for Company-Scoped Permission Evaluation.

Tests Property 4 from the admin-dashboard-user-management design document:
For any user with memberships in multiple companies, permission evaluation
using a given X-Company-Id SHALL use only the role assigned in that specific
company's membership, ignoring roles from other companies.

**Validates: Requirements 2.5**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 4)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (2.5)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
    membership: CompanyMembership | None,
    role: Role | None,
) -> AsyncMock:
    """Build a mock AsyncSession for a single check_permission call.

    The RBACService.check_permission issues queries in this order:
    1. select(User).where(User.id == user_id) → returns user
    2. select(CompanyMembership).where(...) → returns membership for company
    3. select(Role).where(Role.id == membership.role_id) → returns role

    Args:
        user: The User instance to return for the user query.
        membership: The CompanyMembership to return (or None if not a member).
        role: The Role to return (or None if role_id is None).

    Returns:
        A mock AsyncSession configured for a single check_permission call.
    """
    session = AsyncMock()

    # Build sequential results for the execute calls
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    membership_result = MagicMock()
    membership_result.scalar_one_or_none.return_value = membership

    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    # If membership is None, only 2 queries are issued (user + membership)
    # If membership has role_id, 3 queries are issued (user + membership + role)
    if membership is None:
        session.execute = AsyncMock(
            side_effect=[user_result, membership_result]
        )
    elif membership.role_id is not None:
        session.execute = AsyncMock(
            side_effect=[user_result, membership_result, role_result]
        )
    else:
        # Legacy role path - no role query needed (falls back to DEFAULT_ROLE_PERMISSIONS)
        session.execute = AsyncMock(
            side_effect=[user_result, membership_result]
        )

    return session


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_two_distinct_roles(draw: st.DrawFn) -> tuple[str, str]:
    """Generate two distinct role names from the predefined set.

    Returns:
        A tuple of two different role name strings.
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
# Property 4: Company-Scoped Permission Evaluation
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    roles=st_two_distinct_roles(),
    resource_action=st_resource_action(),
)
def test_permission_evaluation_uses_only_target_company_role(
    roles: tuple[str, str],
    resource_action: tuple[str, str],
) -> None:
    """For any user with memberships in multiple companies with different roles,
    permission evaluation using a given company_id SHALL use only the role
    assigned in that specific company's membership, ignoring roles from other
    companies.

    **Validates: Requirements 2.5**
    """
    role_a_name, role_b_name = roles
    resource, action = resource_action

    user_id = 1
    company_a_id = 10
    company_b_id = 20
    role_a_id = 100
    role_b_id = 200

    # Create user (active)
    user = User(
        id=user_id,
        username="multicompany_user",
        email="user@test.local",
        hashed_password="hashed_placeholder",
        full_name="Multi Company User",
        is_active=True,
    )

    # Create roles with their respective permissions
    role_a = Role(
        id=role_a_id,
        name=role_a_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_a_name],
        company_id=company_a_id,
        is_system=True,
    )
    role_b = Role(
        id=role_b_id,
        name=role_b_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_b_name],
        company_id=company_b_id,
        is_system=True,
    )

    # Create memberships in both companies
    membership_a = CompanyMembership(
        id=1,
        user_id=user_id,
        company_id=company_a_id,
        role=role_a_name,
        role_id=role_a_id,
    )
    membership_b = CompanyMembership(
        id=2,
        user_id=user_id,
        company_id=company_b_id,
        role=role_b_name,
        role_id=role_b_id,
    )

    async def _test():
        rbac = RBACService()

        # --- Evaluate permission for company A ---
        session_a = _build_mock_session_for_check(user, membership_a, role_a)
        result_a = await rbac.check_permission(
            user_id=user_id,
            company_id=company_a_id,
            resource=resource,
            action=action,
            session=session_a,
        )

        # Expected result based on role_a's permissions ONLY
        role_a_permissions = DEFAULT_ROLE_PERMISSIONS[role_a_name]
        expected_granted_a = action in role_a_permissions.get(resource, [])

        if expected_granted_a:
            assert isinstance(result_a, AccessGranted), (
                f"Expected AccessGranted for company A (role={role_a_name}) "
                f"on {resource}:{action}, got AccessDenied: {result_a.reason}"
            )
        else:
            assert isinstance(result_a, AccessDenied), (
                f"Expected AccessDenied for company A (role={role_a_name}) "
                f"on {resource}:{action}, got AccessGranted"
            )

        # --- Evaluate permission for company B ---
        session_b = _build_mock_session_for_check(user, membership_b, role_b)
        result_b = await rbac.check_permission(
            user_id=user_id,
            company_id=company_b_id,
            resource=resource,
            action=action,
            session=session_b,
        )

        # Expected result based on role_b's permissions ONLY
        role_b_permissions = DEFAULT_ROLE_PERMISSIONS[role_b_name]
        expected_granted_b = action in role_b_permissions.get(resource, [])

        if expected_granted_b:
            assert isinstance(result_b, AccessGranted), (
                f"Expected AccessGranted for company B (role={role_b_name}) "
                f"on {resource}:{action}, got AccessDenied: {result_b.reason}"
            )
        else:
            assert isinstance(result_b, AccessDenied), (
                f"Expected AccessDenied for company B (role={role_b_name}) "
                f"on {resource}:{action}, got AccessGranted"
            )

        # --- Key property assertion ---
        # When the two roles differ in their grant for this resource:action,
        # the results MUST differ, proving company scoping works correctly.
        if expected_granted_a != expected_granted_b:
            assert type(result_a) != type(result_b), (
                f"Company scoping violated! Same result for different roles. "
                f"Company A role={role_a_name} (expected_granted={expected_granted_a}), "
                f"Company B role={role_b_name} (expected_granted={expected_granted_b}), "
                f"resource={resource}, action={action}. "
                f"Result A: {type(result_a).__name__}, "
                f"Result B: {type(result_b).__name__}"
            )

    _run_async(_test())


@settings(max_examples=100, deadline=None)
@given(roles=st_two_distinct_roles())
def test_permission_evaluation_ignores_other_company_roles(
    roles: tuple[str, str],
) -> None:
    """For any user with a role in company A and a different role in company B,
    evaluating permissions in company A SHALL NOT be influenced by the role
    in company B. Specifically, permissions exclusive to role_b must be denied
    when evaluating in company A's context.

    **Validates: Requirements 2.5**
    """
    role_a_name, role_b_name = roles

    # Find resource:action pairs that role_b grants but role_a does NOT
    permissions_a = DEFAULT_ROLE_PERMISSIONS[role_a_name]
    permissions_b = DEFAULT_ROLE_PERMISSIONS[role_b_name]

    exclusive_to_b: list[tuple[str, str]] = []
    for resource in RESOURCE_TYPES:
        actions_a = set(permissions_a.get(resource, []))
        actions_b = set(permissions_b.get(resource, []))
        for act in actions_b - actions_a:
            exclusive_to_b.append((resource, act))

    # If role_b has no exclusive permissions over role_a, skip
    if not exclusive_to_b:
        return

    user_id = 1
    company_a_id = 10
    company_b_id = 20
    role_a_id = 100
    role_b_id = 200

    # Create user
    user = User(
        id=user_id,
        username="multicompany_user",
        email="user@test.local",
        hashed_password="hashed_placeholder",
        full_name="Multi Company User",
        is_active=True,
    )

    # Create roles
    role_a = Role(
        id=role_a_id,
        name=role_a_name,
        permissions=permissions_a,
        company_id=company_a_id,
        is_system=True,
    )

    # Create membership for company A only (the one being evaluated)
    membership_a = CompanyMembership(
        id=1,
        user_id=user_id,
        company_id=company_a_id,
        role=role_a_name,
        role_id=role_a_id,
    )

    async def _test():
        rbac = RBACService()

        # For each permission exclusive to role_b, verify it's denied
        # when evaluating in company A's context
        for resource, action in exclusive_to_b:
            session = _build_mock_session_for_check(user, membership_a, role_a)
            result = await rbac.check_permission(
                user_id=user_id,
                company_id=company_a_id,
                resource=resource,
                action=action,
                session=session,
            )

            assert isinstance(result, AccessDenied), (
                f"Company scoping violated! Permission {resource}:{action} "
                f"was granted in company A (role={role_a_name}) but should "
                f"only be available in company B (role={role_b_name}). "
                f"The RBAC engine must not leak permissions across companies."
            )

    _run_async(_test())
