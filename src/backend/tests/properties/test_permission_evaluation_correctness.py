"""Property-based tests for Permission Evaluation Correctness.

Tests Property 1 from the admin-dashboard-user-management design document,
validating that for any (role, resource, action) tuple, the RBAC engine
grants access if and only if DEFAULT_ROLE_PERMISSIONS[role][resource]
contains the action.

**Validates: Requirements 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 1)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (2.1, 2.4, 3.1–3.5)
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.rbac import (
    ACTIONS,
    DEFAULT_ROLE_PERMISSIONS,
    RESOURCE_TYPES,
    RBACService,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLE_NAMES: list[str] = list(DEFAULT_ROLE_PERMISSIONS.keys())


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_role_resource_action(draw: st.DrawFn) -> tuple[str, str, str]:
    """Generate a random (role, resource, action) tuple from valid sets.

    Returns:
        A tuple of (role_name, resource_type, action) drawn from the
        defined RBAC constants.
    """
    role = draw(st.sampled_from(ROLE_NAMES))
    resource = draw(st.sampled_from(RESOURCE_TYPES))
    action = draw(st.sampled_from(ACTIONS))
    return (role, resource, action)


# ---------------------------------------------------------------------------
# Property 1: Permission Evaluation Correctness
# ---------------------------------------------------------------------------


@settings(max_examples=500, deadline=None)
@given(data=st_role_resource_action())
def test_permission_evaluation_matches_default_role_permissions(
    data: tuple[str, str, str],
) -> None:
    """For any (role, resource, action) tuple drawn from valid sets,
    the RBAC engine SHALL grant access if and only if
    DEFAULT_ROLE_PERMISSIONS[role][resource] contains the action.

    **Validates: Requirements 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5**
    """
    role, resource, action = data

    # Build the permissions dict for this role (as it would be stored in DB)
    permissions = DEFAULT_ROLE_PERMISSIONS[role]

    # Evaluate using the static _has_permission method
    result = RBACService._has_permission(permissions, resource, action)

    # Compute expected result from the definition
    expected = action in permissions.get(resource, [])

    assert result == expected, (
        f"Permission evaluation mismatch for role='{role}', "
        f"resource='{resource}', action='{action}'. "
        f"Got {result}, expected {expected}. "
        f"Role permissions for resource: {permissions.get(resource, [])}"
    )


@settings(max_examples=500, deadline=None)
@given(
    role=st.sampled_from(ROLE_NAMES),
    resource=st.sampled_from(RESOURCE_TYPES),
    action=st.sampled_from(ACTIONS),
)
def test_permission_denied_when_resource_not_in_role(
    role: str, resource: str, action: str
) -> None:
    """For any (role, resource, action) where the role does NOT have the
    resource in its permissions, the RBAC engine SHALL deny access.

    **Validates: Requirements 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5**
    """
    permissions = DEFAULT_ROLE_PERMISSIONS[role]

    if resource not in permissions:
        # Resource not granted to this role at all — must be denied
        result = RBACService._has_permission(permissions, resource, action)
        assert result is False, (
            f"Expected denial for role='{role}', resource='{resource}', "
            f"action='{action}' (resource not in role permissions), "
            f"but got granted."
        )


@settings(max_examples=500, deadline=None)
@given(
    role=st.sampled_from(ROLE_NAMES),
    resource=st.sampled_from(RESOURCE_TYPES),
    action=st.sampled_from(ACTIONS),
)
def test_permission_denied_when_action_not_in_resource(
    role: str, resource: str, action: str
) -> None:
    """For any (role, resource, action) where the resource IS in the role's
    permissions but the action is NOT listed, the RBAC engine SHALL deny access.

    **Validates: Requirements 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5**
    """
    permissions = DEFAULT_ROLE_PERMISSIONS[role]

    if resource in permissions and action not in permissions[resource]:
        # Resource exists but action not granted — must be denied
        result = RBACService._has_permission(permissions, resource, action)
        assert result is False, (
            f"Expected denial for role='{role}', resource='{resource}', "
            f"action='{action}' (action not in resource permissions: "
            f"{permissions[resource]}), but got granted."
        )


@settings(max_examples=500, deadline=None)
@given(
    role=st.sampled_from(ROLE_NAMES),
    resource=st.sampled_from(RESOURCE_TYPES),
    action=st.sampled_from(ACTIONS),
)
def test_permission_granted_when_action_in_resource(
    role: str, resource: str, action: str
) -> None:
    """For any (role, resource, action) where the resource IS in the role's
    permissions AND the action IS listed, the RBAC engine SHALL grant access.

    **Validates: Requirements 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5**
    """
    permissions = DEFAULT_ROLE_PERMISSIONS[role]

    if resource in permissions and action in permissions[resource]:
        # Both resource and action are granted — must be allowed
        result = RBACService._has_permission(permissions, resource, action)
        assert result is True, (
            f"Expected grant for role='{role}', resource='{resource}', "
            f"action='{action}' (action in resource permissions: "
            f"{permissions[resource]}), but got denied."
        )
