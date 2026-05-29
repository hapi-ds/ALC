"""Property-based tests for Activation/Deactivation Round-Trip.

Tests Property 14 from the admin-dashboard-user-management design document,
validating that for any active user, deactivating then reactivating restores
is_active to True and role permissions function identically to before
deactivation.

**Validates: Requirements 8.4**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 14)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (8.4)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.rbac import (
    ACTIONS,
    DEFAULT_ROLE_PERMISSIONS,
    RESOURCE_TYPES,
    RBACService,
)
from alcoabase.services.user_management import UserManagementService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLE_NAMES: list[str] = list(DEFAULT_ROLE_PERMISSIONS.keys())


# ---------------------------------------------------------------------------
# Pure model of user activation state and permission evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UserState:
    """Minimal user state for round-trip testing.

    Attributes:
        user_id: Unique user identifier.
        is_active: Whether the account is enabled.
        role_name: The role assigned to this user.
        permissions: The role's permission mapping (resource -> actions).
    """

    user_id: int
    is_active: bool
    role_name: str
    permissions: dict[str, list[str]]


def evaluate_permission(user: UserState, resource: str, action: str) -> bool:
    """Evaluate whether a user has permission for a resource-action pair.

    Models the RBACService.check_permission logic:
    1. Deactivated users are always denied.
    2. Active users are evaluated against their role permissions.

    Args:
        user: The user state to evaluate.
        resource: The resource type being accessed.
        action: The action being requested.

    Returns:
        True if access is granted, False if denied.
    """
    if not user.is_active:
        return False

    resource_actions = user.permissions.get(resource, [])
    return action in resource_actions


def deactivate(user: UserState) -> UserState:
    """Model the deactivation operation (sets is_active=False).

    Args:
        user: The active user to deactivate.

    Returns:
        A new UserState with is_active=False, preserving role and permissions.
    """
    return UserState(
        user_id=user.user_id,
        is_active=False,
        role_name=user.role_name,
        permissions=user.permissions,
    )


def reactivate(user: UserState) -> UserState:
    """Model the reactivation operation (sets is_active=True).

    Args:
        user: The deactivated user to reactivate.

    Returns:
        A new UserState with is_active=True, preserving role and permissions.
    """
    return UserState(
        user_id=user.user_id,
        is_active=True,
        role_name=user.role_name,
        permissions=user.permissions,
    )


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_active_user(draw: st.DrawFn) -> UserState:
    """Generate an active user with a valid role and its permissions.

    Returns:
        A UserState with is_active=True and a valid role assignment.
    """
    user_id = draw(st.integers(min_value=1, max_value=10000))
    role_name = draw(st.sampled_from(ROLE_NAMES))
    permissions = DEFAULT_ROLE_PERMISSIONS[role_name]

    return UserState(
        user_id=user_id,
        is_active=True,
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
# Property 14: Activation/Deactivation Round-Trip
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(user=st_active_user(), pair=st_resource_action_pair())
def test_deactivate_then_reactivate_restores_is_active(
    user: UserState, pair: tuple[str, str]
) -> None:
    """For any active user, deactivating then reactivating SHALL restore
    is_active to True.

    **Validates: Requirements 8.4**
    """
    resource, action = pair

    # Verify user starts active
    assert user.is_active is True

    # Deactivate
    deactivated = deactivate(user)
    assert deactivated.is_active is False

    # Reactivate
    reactivated = reactivate(deactivated)
    assert reactivated.is_active is True


@settings(max_examples=200, deadline=None)
@given(user=st_active_user(), pair=st_resource_action_pair())
def test_reactivated_user_permissions_match_original(
    user: UserState, pair: tuple[str, str]
) -> None:
    """For any active user, after deactivation and reactivation, role
    permissions SHALL function identically to before deactivation.

    **Validates: Requirements 8.4**
    """
    resource, action = pair

    # Record permission result BEFORE deactivation
    permission_before = evaluate_permission(user, resource, action)

    # Deactivate — all permissions denied
    deactivated = deactivate(user)
    permission_while_deactivated = evaluate_permission(deactivated, resource, action)
    assert permission_while_deactivated is False, (
        f"Deactivated user {user.user_id} with role '{user.role_name}' "
        f"should be denied {action} on {resource} while deactivated."
    )

    # Reactivate
    reactivated = reactivate(deactivated)

    # Record permission result AFTER reactivation
    permission_after = evaluate_permission(reactivated, resource, action)

    # Permissions after reactivation must match permissions before deactivation
    assert permission_after == permission_before, (
        f"Permission mismatch after round-trip for user {user.user_id} "
        f"with role '{user.role_name}' on {action}:{resource}. "
        f"Before deactivation: {permission_before}, "
        f"After reactivation: {permission_after}. "
        f"Reactivation must restore identical role permissions."
    )


@settings(max_examples=200, deadline=None)
@given(user=st_active_user())
def test_reactivated_user_all_permissions_match_original(
    user: UserState,
) -> None:
    """For any active user, after deactivation and reactivation, ALL
    resource-action pairs SHALL produce identical permission results
    as before deactivation.

    **Validates: Requirements 8.4**
    """
    # Record all permission results BEFORE deactivation
    permissions_before: dict[tuple[str, str], bool] = {}
    for resource in RESOURCE_TYPES:
        for action in ACTIONS:
            permissions_before[(resource, action)] = evaluate_permission(
                user, resource, action
            )

    # Deactivate then reactivate
    deactivated = deactivate(user)
    reactivated = reactivate(deactivated)

    # Verify is_active restored
    assert reactivated.is_active is True

    # Verify role name preserved
    assert reactivated.role_name == user.role_name

    # Verify permissions preserved
    assert reactivated.permissions == user.permissions

    # Verify all permission evaluations match
    for resource in RESOURCE_TYPES:
        for action in ACTIONS:
            permission_after = evaluate_permission(reactivated, resource, action)
            expected = permissions_before[(resource, action)]
            assert permission_after == expected, (
                f"Permission mismatch after round-trip for user {user.user_id} "
                f"with role '{user.role_name}' on {action}:{resource}. "
                f"Before: {expected}, After: {permission_after}."
            )


@settings(max_examples=100, deadline=None)
@given(user=st_active_user())
@pytest.mark.asyncio
async def test_service_deactivate_reactivate_roundtrip(
    user: UserState,
) -> None:
    """For any active user, calling UserManagementService.deactivate_user
    followed by reactivate_user SHALL restore is_active to True and
    preserve the user's role assignment.

    **Validates: Requirements 8.4**
    """
    service = UserManagementService()

    # Create a mock user object that behaves like the ORM model
    mock_user = MagicMock()
    mock_user.id = user.user_id
    mock_user.is_active = True
    mock_user.username = f"user_{user.user_id}"

    # Create a mock membership
    mock_membership = MagicMock()
    mock_membership.role = user.role_name
    mock_membership.role_id = 1

    # Mock session
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    # Use a different acting_user_id to avoid self-deactivation check
    acting_user_id = user.user_id + 1

    with (
        patch.object(
            service, "_get_user_or_404", return_value=mock_user
        ) as mock_get_user,
        patch.object(
            service, "_get_active_membership", return_value=mock_membership
        ) as mock_get_membership,
    ):
        # Phase 1: Deactivate
        result = await service.deactivate_user(
            user_id=user.user_id,
            acting_user_id=acting_user_id,
            company_id=1,
            session=mock_session,
        )

        # Verify deactivation set is_active=False
        assert mock_user.is_active is False

        # Phase 2: Reactivate
        result = await service.reactivate_user(
            user_id=user.user_id,
            company_id=1,
            session=mock_session,
        )

        # Verify reactivation restored is_active=True
        assert mock_user.is_active is True

        # Verify role assignment is unchanged
        assert mock_membership.role == user.role_name
        assert mock_membership.role_id == 1
