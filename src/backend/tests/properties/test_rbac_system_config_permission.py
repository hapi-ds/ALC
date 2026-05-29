"""Property-based tests for RBAC Permission Enforcement on System Config Endpoints.

Tests Property 1 from the admin-system-configuration design document,
validating that for any user whose role lacks the "system_config" permission,
all system config endpoints return HTTP 403. Conversely, for any user whose
role includes the "system_config" permission, requests are not denied on
permission grounds.

**Validates: Requirements 1.1, 1.2**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md (Property 1)
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md (1.1, 1.2)
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

# The system_config router uses two actions: "read" for GET endpoints,
# "update" for PUT/POST mutation endpoints.
SYSTEM_CONFIG_ACTIONS: list[str] = ["read", "update"]

# Roles that have "system_config" permission (any action)
ROLES_WITH_SYSTEM_CONFIG: set[str] = {
    role
    for role, perms in DEFAULT_ROLE_PERMISSIONS.items()
    if "system_config" in perms
}

# Roles that lack "system_config" permission entirely
ROLES_WITHOUT_SYSTEM_CONFIG: set[str] = set(ROLE_NAMES) - ROLES_WITH_SYSTEM_CONFIG


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_permissions_with_system_config(
    draw: st.DrawFn,
) -> dict[str, list[str]]:
    """Generate a custom permissions dict that includes 'system_config' with at least one action.

    Generates random permissions for other resources but ensures 'system_config'
    always has at least one of 'read' or 'update'.
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

    # Ensure "system_config" is present with at least one relevant action
    system_config_actions = draw(
        st.lists(
            st.sampled_from(SYSTEM_CONFIG_ACTIONS),
            min_size=1,
            max_size=2,
            unique=True,
        )
    )
    if "system_config" not in permissions:
        permissions["system_config"] = system_config_actions
    else:
        # Merge: ensure at least one of read/update is present
        for action in system_config_actions:
            if action not in permissions["system_config"]:
                permissions["system_config"].append(action)

    return permissions


@st.composite
def st_permissions_without_system_config(
    draw: st.DrawFn,
) -> dict[str, list[str]]:
    """Generate a custom permissions dict that does NOT include 'system_config'.

    May include other resources but 'system_config' is never present as a key.
    """
    # Only use non-system_config resources
    other_resources = [r for r in RESOURCE_TYPES if r != "system_config"]

    resources_to_include = draw(
        st.lists(
            st.sampled_from(other_resources),
            min_size=0,
            max_size=len(other_resources),
            unique=True,
        )
    )

    permissions: dict[str, list[str]] = {}
    for resource in resources_to_include:
        actions = draw(
            st.lists(st.sampled_from(ACTIONS), min_size=1, unique=True)
        )
        permissions[resource] = actions

    return permissions


@st.composite
def st_permissions_with_system_config_specific_action(
    draw: st.DrawFn,
    action: str,
) -> dict[str, list[str]]:
    """Generate permissions that include a specific action on 'system_config'.

    Args:
        action: The specific action to ensure is present (e.g., "read" or "update").
    """
    permissions = draw(st_permissions_with_system_config())

    # Ensure the specific action is present
    if action not in permissions.get("system_config", []):
        if "system_config" not in permissions:
            permissions["system_config"] = [action]
        else:
            permissions["system_config"].append(action)

    return permissions


@st.composite
def st_permissions_without_system_config_action(
    draw: st.DrawFn,
    action: str,
) -> dict[str, list[str]]:
    """Generate permissions that do NOT include a specific action on 'system_config'.

    The 'system_config' resource may or may not be present, but if present,
    the specified action is excluded.

    Args:
        action: The action to exclude from system_config permissions.
    """
    other_resources = [r for r in RESOURCE_TYPES if r != "system_config"]

    resources_to_include = draw(
        st.lists(
            st.sampled_from(other_resources),
            min_size=0,
            max_size=len(other_resources),
            unique=True,
        )
    )

    permissions: dict[str, list[str]] = {}
    for resource in resources_to_include:
        actions = draw(
            st.lists(st.sampled_from(ACTIONS), min_size=1, unique=True)
        )
        permissions[resource] = actions

    # Optionally include system_config but WITHOUT the target action
    include_system_config = draw(st.booleans())
    if include_system_config:
        other_actions = [a for a in ACTIONS if a != action]
        sc_actions = draw(
            st.lists(
                st.sampled_from(other_actions),
                min_size=0,
                max_size=len(other_actions),
                unique=True,
            )
        )
        if sc_actions:
            permissions["system_config"] = sc_actions

    return permissions


# ---------------------------------------------------------------------------
# Property 1: RBAC Permission Enforcement on System Config Endpoints
# ---------------------------------------------------------------------------


@settings(max_examples=500, deadline=None)
@given(
    role=st.sampled_from(ROLE_NAMES),
    action=st.sampled_from(SYSTEM_CONFIG_ACTIONS),
)
def test_default_roles_system_config_access(
    role: str,
    action: str,
) -> None:
    """For any default role and any system_config action (read/update),
    access SHALL be granted if and only if the role's permissions include
    that action on the 'system_config' resource.

    **Validates: Requirements 1.1, 1.2**
    """
    permissions = DEFAULT_ROLE_PERMISSIONS[role]
    result = RBACService._has_permission(permissions, "system_config", action)

    expected = action in permissions.get("system_config", [])

    assert result == expected, (
        f"RBAC enforcement mismatch for role='{role}' attempting "
        f"system_config:{action}. Got {result}, expected {expected}. "
        f"Role's system_config permissions: {permissions.get('system_config', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(permissions=st_permissions_without_system_config())
def test_roles_without_system_config_denied_all_actions(
    permissions: dict[str, list[str]],
) -> None:
    """For any permissions dict that does NOT include 'system_config' as a
    resource, ALL system config endpoint actions (read and update) SHALL
    be denied (HTTP 403).

    **Validates: Requirements 1.1, 1.2**
    """
    for action in SYSTEM_CONFIG_ACTIONS:
        result = RBACService._has_permission(permissions, "system_config", action)

        assert result is False, (
            f"Expected system_config:{action} to be DENIED for permissions "
            f"that do not include 'system_config' resource, but got granted. "
            f"Permissions keys: {list(permissions.keys())}"
        )


@settings(max_examples=500, deadline=None)
@given(permissions=st_permissions_with_system_config())
def test_roles_with_system_config_not_denied_on_permission_grounds(
    permissions: dict[str, list[str]],
) -> None:
    """For any permissions dict that includes 'system_config' with at least
    one action, the request SHALL NOT be denied on permission grounds for
    the actions that are present.

    **Validates: Requirements 1.1, 1.2**
    """
    system_config_perms = permissions.get("system_config", [])

    for action in SYSTEM_CONFIG_ACTIONS:
        result = RBACService._has_permission(permissions, "system_config", action)

        if action in system_config_perms:
            assert result is True, (
                f"Expected system_config:{action} to be GRANTED for permissions "
                f"that include '{action}' on 'system_config', but got denied. "
                f"system_config permissions: {system_config_perms}"
            )
        else:
            assert result is False, (
                f"Expected system_config:{action} to be DENIED for permissions "
                f"that do NOT include '{action}' on 'system_config', but got granted. "
                f"system_config permissions: {system_config_perms}"
            )


@settings(max_examples=500, deadline=None)
@given(permissions=st_permissions_with_system_config_specific_action(action="read"))
def test_system_config_read_granted_when_permission_present(
    permissions: dict[str, list[str]],
) -> None:
    """For any permissions dict that includes 'read' on 'system_config',
    the RBAC engine SHALL grant access to read endpoints (GET).

    This validates that require_permission("system_config", "read") passes
    for all GET endpoints: /ai-hardware, /storage/usage, /storage/quotas,
    /backups/schedule, /backups/retention, /backups/history, /backups/status/{id},
    /health/status, /health/history/{service}, /health/config, /services,
    /services/{service}/metrics, /snapshots, /snapshots/{id}/diff.

    **Validates: Requirements 1.1, 1.2**
    """
    result = RBACService._has_permission(permissions, "system_config", "read")

    assert result is True, (
        f"Expected system_config:read to be GRANTED for permissions that "
        f"include 'read' on 'system_config', but got denied. "
        f"system_config permissions: {permissions.get('system_config', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(permissions=st_permissions_with_system_config_specific_action(action="update"))
def test_system_config_update_granted_when_permission_present(
    permissions: dict[str, list[str]],
) -> None:
    """For any permissions dict that includes 'update' on 'system_config',
    the RBAC engine SHALL grant access to mutation endpoints (PUT/POST).

    This validates that require_permission("system_config", "update") passes
    for all mutation endpoints: PUT /ai-hardware, POST /ai-hardware/restart-vllm,
    PUT /storage/quotas/{id}, PUT /backups/schedule, PUT /backups/retention,
    POST /backups/trigger, PUT /health/config, POST /snapshots/{id}/rollback.

    **Validates: Requirements 1.1, 1.2**
    """
    result = RBACService._has_permission(permissions, "system_config", "update")

    assert result is True, (
        f"Expected system_config:update to be GRANTED for permissions that "
        f"include 'update' on 'system_config', but got denied. "
        f"system_config permissions: {permissions.get('system_config', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(permissions=st_permissions_without_system_config_action(action="read"))
def test_system_config_read_denied_when_permission_absent(
    permissions: dict[str, list[str]],
) -> None:
    """For any permissions dict that does NOT include 'read' on 'system_config',
    the RBAC engine SHALL deny access to all read endpoints (HTTP 403).

    **Validates: Requirements 1.1, 1.2**
    """
    result = RBACService._has_permission(permissions, "system_config", "read")

    assert result is False, (
        f"Expected system_config:read to be DENIED for permissions that "
        f"do NOT include 'read' on 'system_config', but got granted. "
        f"system_config permissions: {permissions.get('system_config', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(permissions=st_permissions_without_system_config_action(action="update"))
def test_system_config_update_denied_when_permission_absent(
    permissions: dict[str, list[str]],
) -> None:
    """For any permissions dict that does NOT include 'update' on 'system_config',
    the RBAC engine SHALL deny access to all mutation endpoints (HTTP 403).

    **Validates: Requirements 1.1, 1.2**
    """
    result = RBACService._has_permission(permissions, "system_config", "update")

    assert result is False, (
        f"Expected system_config:update to be DENIED for permissions that "
        f"do NOT include 'update' on 'system_config', but got granted. "
        f"system_config permissions: {permissions.get('system_config', [])}"
    )


@settings(max_examples=500, deadline=None)
@given(role=st.sampled_from(ROLE_NAMES))
def test_default_roles_system_config_classification(
    role: str,
) -> None:
    """For any default role, verify the classification of system_config
    access matches the predefined DEFAULT_ROLE_PERMISSIONS.

    system_admin and it_admin SHALL have system_config access.
    doc_admin, member, and viewer SHALL NOT have system_config access.

    **Validates: Requirements 1.1, 1.2**
    """
    permissions = DEFAULT_ROLE_PERMISSIONS[role]

    has_read = RBACService._has_permission(permissions, "system_config", "read")
    has_update = RBACService._has_permission(permissions, "system_config", "update")

    if role in ROLES_WITH_SYSTEM_CONFIG:
        # system_admin and it_admin should have at least read access
        system_config_perms = permissions.get("system_config", [])
        assert has_read == ("read" in system_config_perms), (
            f"Role '{role}' system_config:read mismatch. "
            f"Expected {'granted' if 'read' in system_config_perms else 'denied'}, "
            f"got {'granted' if has_read else 'denied'}."
        )
        assert has_update == ("update" in system_config_perms), (
            f"Role '{role}' system_config:update mismatch. "
            f"Expected {'granted' if 'update' in system_config_perms else 'denied'}, "
            f"got {'granted' if has_update else 'denied'}."
        )
    else:
        # doc_admin, member, viewer should have NO system_config access
        assert has_read is False, (
            f"Role '{role}' should NOT have system_config:read access "
            f"but _has_permission returned True."
        )
        assert has_update is False, (
            f"Role '{role}' should NOT have system_config:update access "
            f"but _has_permission returned True."
        )
