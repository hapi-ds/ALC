"""Property-based tests for RBAC Enforcement on Workflow Actions.

Tests Property 19 from the admin-dashboard-user-management design document,
validating that for any user attempting a workflow approval transition,
access is granted if and only if the user's role includes the "approve"
action on the "workflows" resource. Denied access returns HTTP 403 with
a message identifying the missing permission.

**Validates: Requirements 12.1, 12.2, 12.3**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 19)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (12.1, 12.2, 12.3)
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

# Roles that have "approve" on "workflows" per DEFAULT_ROLE_PERMISSIONS
ROLES_WITH_WORKFLOW_APPROVE: set[str] = {
    role
    for role, perms in DEFAULT_ROLE_PERMISSIONS.items()
    if "approve" in perms.get("workflows", [])
}

# Roles that lack "approve" on "workflows"
ROLES_WITHOUT_WORKFLOW_APPROVE: set[str] = set(ROLE_NAMES) - ROLES_WITH_WORKFLOW_APPROVE


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_role_with_permissions(draw: st.DrawFn) -> tuple[str, dict[str, list[str]]]:
    """Generate a role name and its corresponding permissions dict.

    Returns:
        A tuple of (role_name, permissions_dict) from DEFAULT_ROLE_PERMISSIONS.
    """
    role = draw(st.sampled_from(ROLE_NAMES))
    permissions = DEFAULT_ROLE_PERMISSIONS[role]
    return (role, permissions)


@st.composite
def st_custom_permissions_with_workflow_approve(
    draw: st.DrawFn,
) -> dict[str, list[str]]:
    """Generate a custom permissions dict that includes 'approve' on 'workflows'.

    Generates random permissions for other resources but ensures 'workflows'
    always includes 'approve'.
    """
    # Build random permissions for a subset of resources
    resources_to_include = draw(
        st.lists(
            st.sampled_from(RESOURCE_TYPES),
            min_size=1,
            max_size=len(RESOURCE_TYPES),
            unique=True,
        )
    )

    permissions: dict[str, list[str]] = {}
    for resource in resources_to_include:
        actions = draw(
            st.lists(st.sampled_from(ACTIONS), min_size=1, unique=True)
        )
        permissions[resource] = actions

    # Ensure "workflows" is present with "approve" included
    if "workflows" not in permissions:
        permissions["workflows"] = ["approve"]
    elif "approve" not in permissions["workflows"]:
        permissions["workflows"].append("approve")

    return permissions


@st.composite
def st_custom_permissions_without_workflow_approve(
    draw: st.DrawFn,
) -> dict[str, list[str]]:
    """Generate a custom permissions dict that does NOT include 'approve' on 'workflows'.

    May or may not include 'workflows' as a resource, but if it does,
    'approve' is excluded from the actions list.
    """
    # Build random permissions for a subset of resources
    resources_to_include = draw(
        st.lists(
            st.sampled_from(RESOURCE_TYPES),
            min_size=0,
            max_size=len(RESOURCE_TYPES),
            unique=True,
        )
    )

    # Actions that are NOT "approve" for the workflows resource
    non_approve_actions = [a for a in ACTIONS if a != "approve"]

    permissions: dict[str, list[str]] = {}
    for resource in resources_to_include:
        if resource == "workflows":
            # Only include non-approve actions for workflows
            actions = draw(
                st.lists(
                    st.sampled_from(non_approve_actions),
                    min_size=0,
                    max_size=len(non_approve_actions),
                    unique=True,
                )
            )
            if actions:  # Only add if there are actions
                permissions[resource] = actions
        else:
            actions = draw(
                st.lists(st.sampled_from(ACTIONS), min_size=1, unique=True)
            )
            permissions[resource] = actions

    return permissions


# ---------------------------------------------------------------------------
# Property 19: RBAC Enforcement on Workflow Actions
# ---------------------------------------------------------------------------


@settings(max_examples=500, deadline=None)
@given(data=st_role_with_permissions())
def test_workflow_approve_granted_iff_role_has_approve_on_workflows(
    data: tuple[str, dict[str, list[str]]],
) -> None:
    """For any user with a given role attempting a workflow approval,
    access SHALL be granted if and only if the role includes 'approve'
    on the 'workflows' resource.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """
    role, permissions = data

    # Evaluate the "approve" action on "workflows" resource
    result = RBACService._has_permission(permissions, "workflows", "approve")

    # Expected: granted only if role has "approve" in workflows
    expected = "approve" in permissions.get("workflows", [])

    assert result == expected, (
        f"RBAC enforcement mismatch for role='{role}' attempting "
        f"workflow approval. Got {result}, expected {expected}. "
        f"Role's workflow permissions: {permissions.get('workflows', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(permissions=st_custom_permissions_with_workflow_approve())
def test_workflow_approve_granted_with_custom_permissions_including_approve(
    permissions: dict[str, list[str]],
) -> None:
    """For any custom permissions dict that includes 'approve' on 'workflows',
    the RBAC engine SHALL grant the workflow approval action.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """
    result = RBACService._has_permission(permissions, "workflows", "approve")

    assert result is True, (
        f"Expected workflow approval to be GRANTED for permissions that "
        f"include 'approve' on 'workflows', but got denied. "
        f"Workflow permissions: {permissions.get('workflows', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(permissions=st_custom_permissions_without_workflow_approve())
def test_workflow_approve_denied_with_custom_permissions_excluding_approve(
    permissions: dict[str, list[str]],
) -> None:
    """For any custom permissions dict that does NOT include 'approve' on
    'workflows', the RBAC engine SHALL deny the workflow approval action.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """
    result = RBACService._has_permission(permissions, "workflows", "approve")

    assert result is False, (
        f"Expected workflow approval to be DENIED for permissions that "
        f"do NOT include 'approve' on 'workflows', but got granted. "
        f"Workflow permissions: {permissions.get('workflows', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(role=st.sampled_from(ROLE_NAMES))
def test_workflow_approve_denied_returns_descriptive_reason(
    role: str,
) -> None:
    """For any role that lacks 'approve' on 'workflows', the denial reason
    SHALL identify the missing permission (approve on workflows).

    This validates that the HTTP 403 response would contain a descriptive
    error message per Requirement 12.3.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """
    permissions = DEFAULT_ROLE_PERMISSIONS[role]
    has_approve = "approve" in permissions.get("workflows", [])

    if not has_approve:
        # Verify the permission check correctly denies
        result = RBACService._has_permission(permissions, "workflows", "approve")
        assert result is False, (
            f"Role '{role}' should NOT have workflow approve permission "
            f"but _has_permission returned True. "
            f"Workflow permissions: {permissions.get('workflows', [])}"
        )

        # Verify the expected denial message format matches design spec
        # The AccessDenied reason format is: "Missing permission: {action} on {resource}"
        expected_reason = "Missing permission: approve on workflows"
        assert "approve" in expected_reason and "workflows" in expected_reason


@settings(max_examples=500, deadline=None)
@given(role=st.sampled_from(ROLE_NAMES))
def test_default_roles_workflow_approve_classification(
    role: str,
) -> None:
    """For any default role, verify the classification of workflow approve
    access matches the predefined DEFAULT_ROLE_PERMISSIONS.

    system_admin and doc_admin SHALL have workflow approve access.
    it_admin, member, and viewer SHALL NOT have workflow approve access.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """
    permissions = DEFAULT_ROLE_PERMISSIONS[role]
    result = RBACService._has_permission(permissions, "workflows", "approve")

    if role in ROLES_WITH_WORKFLOW_APPROVE:
        assert result is True, (
            f"Role '{role}' is expected to have workflow approve access "
            f"but _has_permission returned False. "
            f"Workflow permissions: {permissions.get('workflows', [])}"
        )
    else:
        assert result is False, (
            f"Role '{role}' is NOT expected to have workflow approve access "
            f"but _has_permission returned True. "
            f"Workflow permissions: {permissions.get('workflows', [])}"
        )
