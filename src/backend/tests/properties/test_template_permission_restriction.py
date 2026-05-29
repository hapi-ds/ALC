"""Property-based tests for Template-Based Permission Restriction.

Tests Property 20 from the admin-dashboard-user-management design document,
validating that for any role+template combination with varying action sets,
access is granted only when BOTH the base role AND the template grant the action
(most restrictive wins policy).

**Validates: Requirements 13.1, 13.2, 13.3**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 20)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (13.1, 13.2, 13.3)
"""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.company import CompanyMembership
from alcoabase.models.document import Document
from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.models.user import Role, User
from alcoabase.services.rbac import (
    ACTIONS,
    DEFAULT_ROLE_PERMISSIONS,
    AccessDenied,
    AccessGranted,
    RBACService,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROLE_NAMES = list(DEFAULT_ROLE_PERMISSIONS.keys())

# Template actions are a subset: read, write, approve
# Note: "write" in template maps to "update" in base role for documents
TEMPLATE_ACTIONS = ["read", "write", "approve"]

# Document-level actions that the base role uses
DOCUMENT_ACTIONS = ["create", "read", "update", "delete", "approve"]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_role_name(draw: st.DrawFn) -> str:
    """Generate a valid role name from the predefined set.

    Returns:
        A role name string.
    """
    return draw(st.sampled_from(ROLE_NAMES))


@st.composite
def st_template_action(draw: st.DrawFn) -> str:
    """Generate a valid template action.

    Returns:
        An action string from the template action set.
    """
    return draw(st.sampled_from(TEMPLATE_ACTIONS))


@st.composite
def st_document_action(draw: st.DrawFn) -> str:
    """Generate a valid document-level action.

    Returns:
        An action string from the document action set.
    """
    return draw(st.sampled_from(DOCUMENT_ACTIONS))


@st.composite
def st_template_role_permissions(draw: st.DrawFn) -> dict[str, list[str]]:
    """Generate a random role_permissions mapping for a template.

    Each role may or may not be present, and if present, has a random
    subset of template actions.

    Returns:
        A dict mapping role names to lists of template action strings.
    """
    # Choose which roles to include in the template
    included_roles = draw(
        st.lists(
            st.sampled_from(ROLE_NAMES),
            min_size=0,
            max_size=len(ROLE_NAMES),
            unique=True,
        )
    )

    permissions: dict[str, list[str]] = {}
    for role in included_roles:
        actions = draw(
            st.lists(
                st.sampled_from(TEMPLATE_ACTIONS),
                min_size=0,
                max_size=len(TEMPLATE_ACTIONS),
                unique=True,
            )
        )
        permissions[role] = actions

    return permissions


@st.composite
def st_permission_scenario(draw: st.DrawFn) -> dict:
    """Generate a complete permission evaluation scenario.

    Produces a role name, a template's role_permissions, and an action
    to check, along with the expected outcome.

    Returns:
        A dict with keys: role_name, template_permissions, action,
        base_role_grants, template_grants, expected_access.
    """
    role_name = draw(st_role_name())
    template_permissions = draw(st_template_role_permissions())
    action = draw(st_template_action())

    # Determine if base role grants the action on "documents"
    base_role_perms = DEFAULT_ROLE_PERMISSIONS[role_name]
    base_documents_actions = base_role_perms.get("documents", [])
    base_role_grants = action in base_documents_actions

    # Determine if template grants the action for this role
    template_role_actions = template_permissions.get(role_name, None)
    if template_role_actions is None:
        # Role not listed in template → deny
        template_grants = False
    else:
        template_grants = action in template_role_actions

    # Most restrictive wins: access only if BOTH grant
    expected_access = base_role_grants and template_grants

    return {
        "role_name": role_name,
        "template_permissions": template_permissions,
        "action": action,
        "base_role_grants": base_role_grants,
        "template_grants": template_grants,
        "expected_access": expected_access,
    }


# ---------------------------------------------------------------------------
# Helper: Build mock session for check_document_access
# ---------------------------------------------------------------------------


def build_mock_session(
    user: User,
    membership: CompanyMembership,
    role: Role,
    template: PermissionTemplate | None,
) -> AsyncMock:
    """Build a mock AsyncSession that returns the given objects in sequence.

    The RBACService.check_document_access calls:
    1. check_permission → which queries User, then CompanyMembership, then Role
    2. Queries PermissionTemplate by (company_id, document_type)
    3. get_role_for_user → queries CompanyMembership, then Role

    Args:
        user: The User object to return.
        membership: The CompanyMembership object to return.
        role: The Role object to return.
        template: The PermissionTemplate to return (or None).

    Returns:
        A configured AsyncMock session.
    """
    session = AsyncMock()

    # Build mock results for sequential execute calls
    # Call 1: select(User) in check_permission
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    # Call 2: select(CompanyMembership) in check_permission
    membership_result = MagicMock()
    membership_result.scalar_one_or_none.return_value = membership

    # Call 3: select(Role) in _get_role_permissions
    role_result = MagicMock()
    role_result.scalar_one_or_none.return_value = role

    # Call 4: select(PermissionTemplate) in check_document_access
    template_result = MagicMock()
    template_result.scalar_one_or_none.return_value = template

    # Call 5: select(CompanyMembership) in get_role_for_user
    membership_result_2 = MagicMock()
    membership_result_2.scalar_one_or_none.return_value = membership

    # Call 6: select(Role) in get_role_for_user
    role_result_2 = MagicMock()
    role_result_2.scalar_one_or_none.return_value = role

    session.execute = AsyncMock(
        side_effect=[
            user_result,
            membership_result,
            role_result,
            template_result,
            membership_result_2,
            role_result_2,
        ]
    )

    return session


# ---------------------------------------------------------------------------
# Property 20: Template-Based Permission Restriction (Most Restrictive Wins)
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(scenario=st_permission_scenario())
@pytest.mark.asyncio
async def test_template_restriction_most_restrictive_wins(
    scenario: dict,
) -> None:
    """For any role+template combination, access SHALL be granted only when
    BOTH the base role AND the template grant the action.

    This validates the "most restrictive wins" policy: if either the base
    role or the template denies the action, access is denied.

    **Validates: Requirements 13.1, 13.2, 13.3**
    """
    role_name = scenario["role_name"]
    template_permissions = scenario["template_permissions"]
    action = scenario["action"]
    expected_access = scenario["expected_access"]

    # Build test objects
    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
    )

    role = Role(
        id=10,
        name=role_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_name],
        is_system=True,
    )

    membership = CompanyMembership(
        id=1,
        user_id=1,
        company_id=100,
        role=role_name,
        role_id=10,
    )

    document = Document(
        id=1,
        document_uuid="2025-00001",
        title="Test Document",
        folder_path="/test",
        document_type="SOP",
        current_status="Draft",
        created_by=1,
        company_id=100,
    )

    template = PermissionTemplate(
        id=1,
        name="Test Template",
        document_type="SOP",
        role_permissions=template_permissions,
        company_id=100,
        is_default=False,
        created_by=1,
    )

    # Build mock session
    session = build_mock_session(user, membership, role, template)

    # Execute
    service = RBACService()
    result = await service.check_document_access(
        user_id=1,
        company_id=100,
        document=document,
        action=action,
        session=session,
    )

    # Verify
    if expected_access:
        assert isinstance(result, AccessGranted), (
            f"Expected AccessGranted for role='{role_name}', action='{action}', "
            f"template_permissions={template_permissions}. "
            f"Base role grants: {scenario['base_role_grants']}, "
            f"Template grants: {scenario['template_grants']}. "
            f"Got: {result}"
        )
    else:
        assert isinstance(result, AccessDenied), (
            f"Expected AccessDenied for role='{role_name}', action='{action}', "
            f"template_permissions={template_permissions}. "
            f"Base role grants: {scenario['base_role_grants']}, "
            f"Template grants: {scenario['template_grants']}. "
            f"Got: {result}"
        )


@settings(max_examples=200, deadline=None)
@given(
    role_name=st.sampled_from(ROLE_NAMES),
    action=st.sampled_from(TEMPLATE_ACTIONS),
)
@pytest.mark.asyncio
async def test_template_denies_when_base_role_denies(
    role_name: str,
    action: str,
) -> None:
    """When the base role does NOT grant an action on documents, access
    SHALL be denied regardless of what the template allows.

    This validates that the template cannot expand permissions beyond
    what the base role grants.

    **Validates: Requirements 13.1, 13.2**
    """
    # Check if base role denies this action
    base_documents_actions = DEFAULT_ROLE_PERMISSIONS[role_name].get("documents", [])
    if action in base_documents_actions:
        # Base role grants this action — skip this case (not testing denial)
        return

    # Template grants the action for this role
    template_permissions = {role_name: TEMPLATE_ACTIONS[:]}  # All template actions

    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
    )

    role = Role(
        id=10,
        name=role_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_name],
        is_system=True,
    )

    membership = CompanyMembership(
        id=1,
        user_id=1,
        company_id=100,
        role=role_name,
        role_id=10,
    )

    document = Document(
        id=1,
        document_uuid="2025-00001",
        title="Test Document",
        folder_path="/test",
        document_type="SOP",
        current_status="Draft",
        created_by=1,
        company_id=100,
    )

    template = PermissionTemplate(
        id=1,
        name="Test Template",
        document_type="SOP",
        role_permissions=template_permissions,
        company_id=100,
        is_default=False,
        created_by=1,
    )

    session = build_mock_session(user, membership, role, template)

    service = RBACService()
    result = await service.check_document_access(
        user_id=1,
        company_id=100,
        document=document,
        action=action,
        session=session,
    )

    assert isinstance(result, AccessDenied), (
        f"Expected AccessDenied when base role '{role_name}' does not grant "
        f"'{action}' on documents, even though template grants it. Got: {result}"
    )


@settings(max_examples=200, deadline=None)
@given(
    role_name=st.sampled_from(ROLE_NAMES),
    action=st.sampled_from(TEMPLATE_ACTIONS),
)
@pytest.mark.asyncio
async def test_template_denies_when_role_not_in_template(
    role_name: str,
    action: str,
) -> None:
    """When a role is NOT listed in the template's role_permissions,
    access SHALL be denied even if the base role grants the action.

    **Validates: Requirements 13.1, 13.2, 13.3**
    """
    # Only test when base role grants the action (otherwise denial is from base)
    base_documents_actions = DEFAULT_ROLE_PERMISSIONS[role_name].get("documents", [])
    if action not in base_documents_actions:
        return

    # Template does NOT include this role at all
    other_roles = [r for r in ROLE_NAMES if r != role_name]
    template_permissions = {r: TEMPLATE_ACTIONS[:] for r in other_roles}

    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
    )

    role = Role(
        id=10,
        name=role_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_name],
        is_system=True,
    )

    membership = CompanyMembership(
        id=1,
        user_id=1,
        company_id=100,
        role=role_name,
        role_id=10,
    )

    document = Document(
        id=1,
        document_uuid="2025-00001",
        title="Test Document",
        folder_path="/test",
        document_type="SOP",
        current_status="Draft",
        created_by=1,
        company_id=100,
    )

    template = PermissionTemplate(
        id=1,
        name="Test Template",
        document_type="SOP",
        role_permissions=template_permissions,
        company_id=100,
        is_default=False,
        created_by=1,
    )

    session = build_mock_session(user, membership, role, template)

    service = RBACService()
    result = await service.check_document_access(
        user_id=1,
        company_id=100,
        document=document,
        action=action,
        session=session,
    )

    assert isinstance(result, AccessDenied), (
        f"Expected AccessDenied when role '{role_name}' is not listed in "
        f"template role_permissions, even though base role grants '{action}'. "
        f"Got: {result}"
    )


@settings(max_examples=200, deadline=None)
@given(
    role_name=st.sampled_from(ROLE_NAMES),
    template_actions=st.lists(
        st.sampled_from(TEMPLATE_ACTIONS),
        min_size=0,
        max_size=len(TEMPLATE_ACTIONS),
        unique=True,
    ),
    action=st.sampled_from(TEMPLATE_ACTIONS),
)
@pytest.mark.asyncio
async def test_template_denies_when_action_not_in_template(
    role_name: str,
    template_actions: list[str],
    action: str,
) -> None:
    """When a role IS listed in the template but the specific action is NOT
    in the template's allowed actions for that role, access SHALL be denied.

    **Validates: Requirements 13.1, 13.2, 13.3**
    """
    # Only test when base role grants the action
    base_documents_actions = DEFAULT_ROLE_PERMISSIONS[role_name].get("documents", [])
    if action not in base_documents_actions:
        return

    # Only test when template does NOT include this action
    if action in template_actions:
        return

    template_permissions = {role_name: template_actions}

    user = User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
    )

    role = Role(
        id=10,
        name=role_name,
        permissions=DEFAULT_ROLE_PERMISSIONS[role_name],
        is_system=True,
    )

    membership = CompanyMembership(
        id=1,
        user_id=1,
        company_id=100,
        role=role_name,
        role_id=10,
    )

    document = Document(
        id=1,
        document_uuid="2025-00001",
        title="Test Document",
        folder_path="/test",
        document_type="SOP",
        current_status="Draft",
        created_by=1,
        company_id=100,
    )

    template = PermissionTemplate(
        id=1,
        name="Test Template",
        document_type="SOP",
        role_permissions=template_permissions,
        company_id=100,
        is_default=False,
        created_by=1,
    )

    session = build_mock_session(user, membership, role, template)

    service = RBACService()
    result = await service.check_document_access(
        user_id=1,
        company_id=100,
        document=document,
        action=action,
        session=session,
    )

    assert isinstance(result, AccessDenied), (
        f"Expected AccessDenied when template does not grant '{action}' "
        f"for role '{role_name}' (template_actions={template_actions}). "
        f"Got: {result}"
    )
