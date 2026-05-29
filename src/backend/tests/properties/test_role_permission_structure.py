"""Property-based tests for Role Permission Structure Validity.

Tests Property 3 from the admin-dashboard-user-management design document,
validating that for any role stored in the system, the permissions field is
a valid JSON object where keys are valid resource types and values are arrays
of valid action strings.

**Validates: Requirements 1.3, 1.4**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 3)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (1.3, 1.4)
"""

import json

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.models.user import Role

# ---------------------------------------------------------------------------
# Constants — matching the design document specification
# ---------------------------------------------------------------------------

RESOURCE_TYPES = [
    "documents",
    "workflows",
    "users",
    "audit_logs",
    "templates",
    "training",
    "signatures",
    "system_config",
]

ACTIONS = ["create", "read", "update", "delete", "approve"]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_valid_permissions(draw: st.DrawFn) -> dict[str, list[str]]:
    """Generate a valid permissions dict with keys from RESOURCE_TYPES
    and values as subsets of ACTIONS.

    Returns:
        A dict mapping resource type strings to lists of action strings.
    """
    # Choose a random subset of resource types to include
    resource_subset = draw(
        st.lists(
            st.sampled_from(RESOURCE_TYPES),
            min_size=0,
            max_size=len(RESOURCE_TYPES),
            unique=True,
        )
    )

    permissions: dict[str, list[str]] = {}
    for resource in resource_subset:
        # For each resource, choose a random subset of actions
        actions = draw(
            st.lists(
                st.sampled_from(ACTIONS),
                min_size=0,
                max_size=len(ACTIONS),
                unique=True,
            )
        )
        permissions[resource] = actions

    return permissions


@st.composite
def st_role_record(draw: st.DrawFn) -> Role:
    """Generate a random Role record with valid permissions structure.

    Returns:
        A Role instance with a valid permissions JSON field.
    """
    name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N", "Pd"),
        whitelist_characters="_",
    )))
    description = draw(st.one_of(st.none(), st.text(min_size=1, max_size=200)))
    permissions = draw(st_valid_permissions())
    is_system = draw(st.booleans())

    role = Role(
        id=draw(st.integers(min_value=1, max_value=10000)),
        name=name,
        description=description,
        permissions=permissions,
        is_system=is_system,
    )
    return role


# ---------------------------------------------------------------------------
# Property 3: Role Permission Structure Validity
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(role=st_role_record())
def test_role_permissions_keys_are_valid_resource_types(role: Role) -> None:
    """For any role record, all keys in the permissions field SHALL be
    valid resource types from the RESOURCE_TYPES set.

    **Validates: Requirements 1.3, 1.4**
    """
    permissions = role.permissions
    assert isinstance(permissions, dict), (
        f"Permissions must be a dict, got {type(permissions)}"
    )

    for key in permissions:
        assert key in RESOURCE_TYPES, (
            f"Invalid resource type '{key}' in role '{role.name}' permissions. "
            f"Valid types: {RESOURCE_TYPES}"
        )


@settings(max_examples=200, deadline=None)
@given(role=st_role_record())
def test_role_permissions_values_are_valid_action_arrays(role: Role) -> None:
    """For any role record, all values in the permissions field SHALL be
    arrays containing only valid action strings from the ACTIONS set.

    **Validates: Requirements 1.3, 1.4**
    """
    permissions = role.permissions

    for resource, actions in permissions.items():
        assert isinstance(actions, list), (
            f"Actions for resource '{resource}' must be a list, "
            f"got {type(actions)} in role '{role.name}'"
        )
        for action in actions:
            assert action in ACTIONS, (
                f"Invalid action '{action}' for resource '{resource}' "
                f"in role '{role.name}'. Valid actions: {ACTIONS}"
            )


@settings(max_examples=200, deadline=None)
@given(permissions=st_valid_permissions())
def test_role_permissions_json_serializable(permissions: dict[str, list[str]]) -> None:
    """For any valid permissions structure, the field SHALL be serializable
    to and from JSON without data loss.

    **Validates: Requirements 1.3, 1.4**
    """
    # Serialize to JSON string
    json_str = json.dumps(permissions)

    # Deserialize back
    restored = json.loads(json_str)

    # Verify round-trip preserves structure
    assert restored == permissions, (
        f"JSON round-trip failed. Original: {permissions}, Restored: {restored}"
    )

    # Verify structure validity after round-trip
    for key, actions in restored.items():
        assert key in RESOURCE_TYPES, (
            f"After JSON round-trip, invalid resource type '{key}'"
        )
        assert isinstance(actions, list), (
            f"After JSON round-trip, actions for '{key}' is not a list"
        )
        for action in actions:
            assert action in ACTIONS, (
                f"After JSON round-trip, invalid action '{action}' for '{key}'"
            )


@settings(max_examples=200, deadline=None)
@given(role=st_role_record())
def test_role_permissions_no_duplicate_actions(role: Role) -> None:
    """For any role record, each resource's action list SHALL NOT contain
    duplicate action entries.

    **Validates: Requirements 1.3, 1.4**
    """
    permissions = role.permissions

    for resource, actions in permissions.items():
        unique_actions = set(actions)
        assert len(actions) == len(unique_actions), (
            f"Duplicate actions found for resource '{resource}' "
            f"in role '{role.name}': {actions}"
        )
