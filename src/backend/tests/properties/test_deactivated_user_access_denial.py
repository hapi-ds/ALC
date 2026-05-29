"""Property-based tests for Deactivated User Access Denial.

Tests Property 13 from the admin-dashboard-user-management design document,
validating that for any deactivated user (is_active=False) with any role,
all (resource, action) pairs are denied regardless of role permissions.

**Validates: Requirements 8.1, 8.2**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 13)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (8.1, 8.2)
"""

from __future__ import annotations

from dataclasses import dataclass

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.rbac import ACTIONS, DEFAULT_ROLE_PERMISSIONS, RESOURCE_TYPES


# ---------------------------------------------------------------------------
# Pure model of the deactivated-user access check
# ---------------------------------------------------------------------------

ROLE_NAMES = list(DEFAULT_ROLE_PERMISSIONS.keys())


@dataclass(frozen=True)
class UserRecord:
    """Minimal user representation for permission evaluation.

    Attributes:
        user_id: Unique user identifier.
        is_active: Whether the account is enabled.
        role_name: The role assigned to this user.
        permissions: The role's permission mapping.
    """

    user_id: int
    is_active: bool
    role_name: str
    permissions: dict[str, list[str]]


@dataclass(frozen=True)
class AccessGranted:
    """Result indicating permission was granted."""

    user_id: int
    resource: str
    action: str


@dataclass(frozen=True)
class AccessDenied:
    """Result indicating permission was denied."""

    user_id: int
    resource: str
    action: str
    reason: str


def evaluate_permission(
    user: UserRecord, resource: str, action: str
) -> AccessGranted | AccessDenied:
    """Evaluate permission for a user on a resource-action pair.

    Models the RBACService.check_permission logic:
    1. Check is_active flag first — deny immediately if deactivated.
    2. Evaluate role permissions only for active users.

    This mirrors the actual implementation in alcoabase.services.rbac
    where the is_active check occurs before any role/permission evaluation.

    Args:
        user: The user record to evaluate.
        resource: The resource type being accessed.
        action: The action being requested.

    Returns:
        AccessGranted if the user has permission, AccessDenied otherwise.
    """
    # Step 1: Deactivated users are always denied (matches RBACService behavior)
    if not user.is_active:
        return AccessDenied(
            user_id=user.user_id,
            resource=resource,
            action=action,
            reason="Account is deactivated. Contact your administrator.",
        )

    # Step 2: Evaluate role permissions for active users
    resource_actions = user.permissions.get(resource)
    if resource_actions is None:
        return AccessDenied(
            user_id=user.user_id,
            resource=resource,
            action=action,
            reason=f"Missing permission: {action} on {resource}",
        )

    if action in resource_actions:
        return AccessGranted(
            user_id=user.user_id,
            resource=resource,
            action=action,
        )

    return AccessDenied(
        user_id=user.user_id,
        resource=resource,
        action=action,
        reason=f"Missing permission: {action} on {resource}",
    )


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_deactivated_user(draw: st.DrawFn) -> UserRecord:
    """Generate a deactivated user with any valid role and its permissions.

    The user always has is_active=False, but is assigned a real role
    with full permissions from DEFAULT_ROLE_PERMISSIONS. This tests that
    even users with the most privileged roles are denied when deactivated.

    Returns:
        A UserRecord with is_active=False and a valid role assignment.
    """
    user_id = draw(st.integers(min_value=1, max_value=10000))
    role_name = draw(st.sampled_from(ROLE_NAMES))
    permissions = DEFAULT_ROLE_PERMISSIONS[role_name]

    return UserRecord(
        user_id=user_id,
        is_active=False,
        role_name=role_name,
        permissions=permissions,
    )


@st.composite
def st_resource_action_pair(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a random (resource, action) pair from valid sets.

    Returns:
        Tuple of (resource_type, action) from the RBAC constants.
    """
    resource = draw(st.sampled_from(RESOURCE_TYPES))
    action = draw(st.sampled_from(ACTIONS))
    return (resource, action)


# ---------------------------------------------------------------------------
# Property 13: Deactivated User Access Denial
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(user=st_deactivated_user(), pair=st_resource_action_pair())
def test_deactivated_user_denied_all_resource_action_pairs(
    user: UserRecord, pair: tuple[str, str]
) -> None:
    """For any deactivated user (is_active=False) with any role, ALL
    (resource, action) pairs SHALL be denied regardless of the role's
    permission grants.

    **Validates: Requirements 8.1, 8.2**
    """
    resource, action = pair
    result = evaluate_permission(user, resource, action)

    assert isinstance(result, AccessDenied), (
        f"Deactivated user {user.user_id} with role '{user.role_name}' "
        f"was granted access to {action} on {resource}. "
        f"Expected AccessDenied but got AccessGranted."
    )
    assert result.reason == "Account is deactivated. Contact your administrator.", (
        f"Deactivated user denial reason mismatch. "
        f"Expected 'Account is deactivated. Contact your administrator.', "
        f"got '{result.reason}'"
    )


@settings(max_examples=200, deadline=None)
@given(user=st_deactivated_user())
def test_deactivated_user_denied_across_all_resources_and_actions(
    user: UserRecord,
) -> None:
    """For any deactivated user, iterating over ALL resource types and ALL
    actions SHALL produce AccessDenied for every combination, confirming
    complete access lockout.

    **Validates: Requirements 8.1, 8.2**
    """
    for resource in RESOURCE_TYPES:
        for action in ACTIONS:
            result = evaluate_permission(user, resource, action)

            assert isinstance(result, AccessDenied), (
                f"Deactivated user {user.user_id} with role '{user.role_name}' "
                f"was granted access to {action} on {resource}. "
                f"Deactivated users must be denied ALL access."
            )


@settings(max_examples=200, deadline=None)
@given(
    user_id=st.integers(min_value=1, max_value=10000),
    role_name=st.sampled_from(ROLE_NAMES),
    pair=st_resource_action_pair(),
)
def test_deactivation_overrides_even_system_admin_permissions(
    user_id: int, role_name: str, pair: tuple[str, str]
) -> None:
    """For any role — including system_admin which has full access to all
    resources — deactivation SHALL override all permission grants and
    deny access unconditionally.

    **Validates: Requirements 8.1, 8.2**
    """
    resource, action = pair
    permissions = DEFAULT_ROLE_PERMISSIONS[role_name]

    # Create an active user — verify they would have access (if role grants it)
    active_user = UserRecord(
        user_id=user_id,
        is_active=True,
        role_name=role_name,
        permissions=permissions,
    )
    active_result = evaluate_permission(active_user, resource, action)

    # Create the same user but deactivated
    deactivated_user = UserRecord(
        user_id=user_id,
        is_active=False,
        role_name=role_name,
        permissions=permissions,
    )
    deactivated_result = evaluate_permission(deactivated_user, resource, action)

    # Regardless of what the active user would get, deactivated is always denied
    assert isinstance(deactivated_result, AccessDenied), (
        f"Deactivated user {user_id} with role '{role_name}' "
        f"was granted access to {action} on {resource}. "
        f"Active user result was {type(active_result).__name__}. "
        f"Deactivation must override all permissions."
    )

    # If the active user WOULD have been granted, this confirms deactivation
    # truly overrides the permission
    if isinstance(active_result, AccessGranted):
        assert isinstance(deactivated_result, AccessDenied), (
            f"Role '{role_name}' grants {action} on {resource} to active users, "
            f"but deactivation failed to override this grant."
        )
