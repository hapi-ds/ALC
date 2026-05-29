"""Unit tests for RBACService permission evaluation.

Tests cover:
- Permission evaluation for all five roles against all resource-action pairs
- Deactivated user denial
- Company-scoped evaluation
- Template restriction logic (most restrictive wins)
- seed_default_roles creates exactly five roles with correct permissions
- Edge cases: missing membership, revoked membership, null role_id

References:
    - Requirements 2.1–2.6, 3.1–3.5, 8.2, 13.1–13.3
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.company import CompanyMembership
from alcoabase.models.document import Document
from alcoabase.models.permission_template import PermissionTemplate
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rbac_service() -> RBACService:
    """Create an RBACService instance."""
    return RBACService()


@pytest.fixture
def active_user() -> User:
    """Create an active user for testing."""
    user = User(
        id=10,
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        full_name="Test User",
        is_active=True,
    )
    return user


@pytest.fixture
def deactivated_user() -> User:
    """Create a deactivated user for testing."""
    user = User(
        id=20,
        username="inactive",
        email="inactive@example.com",
        hashed_password="hashed",
        full_name="Inactive User",
        is_active=False,
    )
    return user


def _make_role(name: str, company_id: int = 1) -> Role:
    """Helper to create a Role with default permissions."""
    return Role(
        id=hash(name) % 1000 + 1,
        name=name,
        description=f"{name} role",
        permissions=DEFAULT_ROLE_PERMISSIONS.get(name, {}),
        company_id=company_id,
        is_system=True,
    )


def _make_membership(
    user_id: int,
    company_id: int,
    role: Role,
    revoked: bool = False,
) -> CompanyMembership:
    """Helper to create a CompanyMembership."""
    membership = CompanyMembership(
        id=user_id * 100 + company_id,
        user_id=user_id,
        company_id=company_id,
        role=role.name,
        role_id=role.id,
        revoked_at=datetime(2025, 1, 1, tzinfo=UTC) if revoked else None,
    )
    return membership


def _mock_session_for_check(
    user: User | None,
    membership: CompanyMembership | None,
    role: Role | None,
) -> AsyncMock:
    """Create a mock session that returns user, membership, and role in sequence."""
    session = AsyncMock()

    # Build the sequence of execute results
    results = []

    # First call: user lookup
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    results.append(user_result)

    # Second call: membership lookup
    membership_result = MagicMock()
    membership_result.scalar_one_or_none.return_value = membership
    results.append(membership_result)

    # Third call: role lookup (if membership has role_id)
    if role is not None:
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = role
        results.append(role_result)

    session.execute = AsyncMock(side_effect=results)
    return session


# ---------------------------------------------------------------------------
# Test: Permission evaluation for all five roles (Requirements 3.1–3.5)
# ---------------------------------------------------------------------------


class TestPermissionEvaluationAllRoles:
    """Test that each role grants/denies the correct resource-action pairs."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role_name", list(DEFAULT_ROLE_PERMISSIONS.keys()))
    async def test_granted_permissions(
        self, rbac_service: RBACService, active_user: User, role_name: str
    ) -> None:
        """Each role's defined permissions should be granted."""
        role = _make_role(role_name)
        membership = _make_membership(active_user.id, 1, role)

        for resource, actions in DEFAULT_ROLE_PERMISSIONS[role_name].items():
            for action in actions:
                session = _mock_session_for_check(active_user, membership, role)
                result = await rbac_service.check_permission(
                    user_id=active_user.id,
                    company_id=1,
                    resource=resource,
                    action=action,
                    session=session,
                )
                assert isinstance(result, AccessGranted), (
                    f"{role_name} should have {action} on {resource}"
                )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role_name", list(DEFAULT_ROLE_PERMISSIONS.keys()))
    async def test_denied_permissions(
        self, rbac_service: RBACService, active_user: User, role_name: str
    ) -> None:
        """Actions NOT in a role's definition should be denied."""
        role = _make_role(role_name)
        membership = _make_membership(active_user.id, 1, role)
        role_perms = DEFAULT_ROLE_PERMISSIONS[role_name]

        for resource in RESOURCE_TYPES:
            granted_actions = role_perms.get(resource, [])
            denied_actions = [a for a in ACTIONS if a not in granted_actions]
            for action in denied_actions:
                session = _mock_session_for_check(active_user, membership, role)
                result = await rbac_service.check_permission(
                    user_id=active_user.id,
                    company_id=1,
                    resource=resource,
                    action=action,
                    session=session,
                )
                assert isinstance(result, AccessDenied), (
                    f"{role_name} should NOT have {action} on {resource}"
                )

    @pytest.mark.asyncio
    async def test_system_admin_has_all_permissions(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """system_admin should have full access to all resources."""
        role = _make_role("system_admin")
        membership = _make_membership(active_user.id, 1, role)

        for resource in RESOURCE_TYPES:
            for action in ACTIONS:
                session = _mock_session_for_check(active_user, membership, role)
                result = await rbac_service.check_permission(
                    user_id=active_user.id,
                    company_id=1,
                    resource=resource,
                    action=action,
                    session=session,
                )
                assert isinstance(result, AccessGranted)

    @pytest.mark.asyncio
    async def test_viewer_read_only(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """viewer should only have read access to specific resources."""
        role = _make_role("viewer")
        membership = _make_membership(active_user.id, 1, role)

        # Viewer can read documents, workflows, templates, training
        for resource in ["documents", "workflows", "templates", "training"]:
            session = _mock_session_for_check(active_user, membership, role)
            result = await rbac_service.check_permission(
                user_id=active_user.id,
                company_id=1,
                resource=resource,
                action="read",
                session=session,
            )
            assert isinstance(result, AccessGranted)

        # Viewer cannot create anything
        for resource in RESOURCE_TYPES:
            session = _mock_session_for_check(active_user, membership, role)
            result = await rbac_service.check_permission(
                user_id=active_user.id,
                company_id=1,
                resource=resource,
                action="create",
                session=session,
            )
            assert isinstance(result, AccessDenied)


# ---------------------------------------------------------------------------
# Test: Deactivated user denial (Requirement 8.2)
# ---------------------------------------------------------------------------


class TestDeactivatedUserDenial:
    """Deactivated users should be denied all access regardless of role."""

    @pytest.mark.asyncio
    async def test_deactivated_user_denied_all_resources(
        self, rbac_service: RBACService, deactivated_user: User
    ) -> None:
        """A deactivated user is denied even with system_admin role."""
        # Session only returns user (deactivated check happens before membership)
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = deactivated_user
        session.execute = AsyncMock(return_value=user_result)

        result = await rbac_service.check_permission(
            user_id=deactivated_user.id,
            company_id=1,
            resource="documents",
            action="read",
            session=session,
        )
        assert isinstance(result, AccessDenied)
        assert "deactivated" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_deactivated_user_denied_message(
        self, rbac_service: RBACService, deactivated_user: User
    ) -> None:
        """Denial reason should mention deactivation."""
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = deactivated_user
        session.execute = AsyncMock(return_value=user_result)

        result = await rbac_service.check_permission(
            user_id=deactivated_user.id,
            company_id=1,
            resource="users",
            action="create",
            session=session,
        )
        assert isinstance(result, AccessDenied)
        assert "deactivated" in result.reason.lower()


# ---------------------------------------------------------------------------
# Test: Company-scoped evaluation (Requirement 2.5)
# ---------------------------------------------------------------------------


class TestCompanyScopedEvaluation:
    """Permission evaluation uses only the role from the specified company."""

    @pytest.mark.asyncio
    async def test_uses_company_specific_role(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """User with viewer role in company 1 should be denied create."""
        viewer_role = _make_role("viewer")
        membership = _make_membership(active_user.id, 1, viewer_role)
        session = _mock_session_for_check(active_user, membership, viewer_role)

        result = await rbac_service.check_permission(
            user_id=active_user.id,
            company_id=1,
            resource="documents",
            action="create",
            session=session,
        )
        assert isinstance(result, AccessDenied)

    @pytest.mark.asyncio
    async def test_different_company_different_role(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """User with system_admin role in company 2 should be granted create."""
        admin_role = _make_role("system_admin")
        membership = _make_membership(active_user.id, 2, admin_role)
        session = _mock_session_for_check(active_user, membership, admin_role)

        result = await rbac_service.check_permission(
            user_id=active_user.id,
            company_id=2,
            resource="documents",
            action="create",
            session=session,
        )
        assert isinstance(result, AccessGranted)


# ---------------------------------------------------------------------------
# Test: Template restriction logic (Requirements 13.1–13.3)
# ---------------------------------------------------------------------------


class TestTemplateRestriction:
    """Permission templates apply 'most restrictive wins' policy."""

    @pytest.mark.asyncio
    async def test_template_restricts_base_role(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """If template doesn't grant action, access is denied even if base role allows."""
        role = _make_role("system_admin")
        membership = _make_membership(active_user.id, 1, role)

        # Template only allows "read" for system_admin
        template = PermissionTemplate(
            id=1,
            name="Restricted SOP",
            document_type="SOP",
            role_permissions={"system_admin": ["read"]},
            company_id=1,
            created_by=1,
        )

        document = Document(
            id=1,
            document_uuid="2025-00001",
            title="Test Doc",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            created_by=1,
            company_id=1,
        )

        # Mock session: base check (user, membership, role) + template lookup + role lookup
        session = AsyncMock()
        results = [
            # check_permission: user lookup
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            # check_permission: membership lookup
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            # check_permission: role lookup
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
            # check_document_access: template lookup
            MagicMock(scalar_one_or_none=MagicMock(return_value=template)),
            # get_role_for_user: membership lookup
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            # get_role_for_user: role lookup
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.check_document_access(
            user_id=active_user.id,
            company_id=1,
            document=document,
            action="approve",
            session=session,
        )
        # Template only allows "read", so "approve" should be denied
        assert isinstance(result, AccessDenied)
        assert "template" in result.reason.lower() or "Template" in result.reason

    @pytest.mark.asyncio
    async def test_template_grants_when_both_allow(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """Access granted when both base role AND template allow the action."""
        role = _make_role("system_admin")
        membership = _make_membership(active_user.id, 1, role)

        template = PermissionTemplate(
            id=2,
            name="Open SOP",
            document_type="SOP",
            role_permissions={"system_admin": ["read", "write", "approve"]},
            company_id=1,
            created_by=1,
        )

        document = Document(
            id=2,
            document_uuid="2025-00002",
            title="Open Doc",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            created_by=1,
            company_id=1,
        )

        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=template)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.check_document_access(
            user_id=active_user.id,
            company_id=1,
            document=document,
            action="read",
            session=session,
        )
        assert isinstance(result, AccessGranted)

    @pytest.mark.asyncio
    async def test_no_template_uses_base_role_only(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """When no template exists, base role permission is sufficient."""
        role = _make_role("member")
        membership = _make_membership(active_user.id, 1, role)

        document = Document(
            id=3,
            document_uuid="2025-00003",
            title="No Template Doc",
            folder_path="/docs",
            document_type="Report",
            current_status="Draft",
            created_by=1,
            company_id=1,
        )

        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
            # Template lookup returns None
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.check_document_access(
            user_id=active_user.id,
            company_id=1,
            document=document,
            action="read",
            session=session,
        )
        assert isinstance(result, AccessGranted)

    @pytest.mark.asyncio
    async def test_role_not_in_template_denied(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """If role is not listed in template, access is denied."""
        role = _make_role("member")
        membership = _make_membership(active_user.id, 1, role)

        # Template only lists system_admin and doc_admin
        template = PermissionTemplate(
            id=3,
            name="Restricted Template",
            document_type="SOP",
            role_permissions={
                "system_admin": ["read", "write", "approve"],
                "doc_admin": ["read", "write"],
            },
            company_id=1,
            created_by=1,
        )

        document = Document(
            id=4,
            document_uuid="2025-00004",
            title="Restricted Doc",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            created_by=1,
            company_id=1,
        )

        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=template)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.check_document_access(
            user_id=active_user.id,
            company_id=1,
            document=document,
            action="read",
            session=session,
        )
        assert isinstance(result, AccessDenied)


# ---------------------------------------------------------------------------
# Test: seed_default_roles (Requirement 1.2)
# ---------------------------------------------------------------------------


class TestSeedDefaultRoles:
    """Test that seed_default_roles creates exactly five roles correctly."""

    @pytest.mark.asyncio
    async def test_creates_exactly_five_roles(
        self, rbac_service: RBACService
    ) -> None:
        """seed_default_roles should create exactly 5 roles."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        roles = await rbac_service.seed_default_roles(company_id=1, session=session)

        assert len(roles) == 5

    @pytest.mark.asyncio
    async def test_role_names_match_defaults(
        self, rbac_service: RBACService
    ) -> None:
        """Created roles should have the expected names."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        roles = await rbac_service.seed_default_roles(company_id=1, session=session)
        role_names = {r.name for r in roles}

        expected = {"system_admin", "doc_admin", "it_admin", "member", "viewer"}
        assert role_names == expected

    @pytest.mark.asyncio
    async def test_roles_have_correct_permissions(
        self, rbac_service: RBACService
    ) -> None:
        """Each role should have permissions matching DEFAULT_ROLE_PERMISSIONS."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        roles = await rbac_service.seed_default_roles(company_id=1, session=session)

        for role in roles:
            assert role.permissions == DEFAULT_ROLE_PERMISSIONS[role.name]

    @pytest.mark.asyncio
    async def test_roles_are_system_roles(
        self, rbac_service: RBACService
    ) -> None:
        """All seeded roles should be marked as system roles."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        roles = await rbac_service.seed_default_roles(company_id=1, session=session)

        for role in roles:
            assert role.is_system is True

    @pytest.mark.asyncio
    async def test_roles_scoped_to_company(
        self, rbac_service: RBACService
    ) -> None:
        """All seeded roles should be scoped to the given company."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        roles = await rbac_service.seed_default_roles(company_id=42, session=session)

        for role in roles:
            assert role.company_id == 42

    @pytest.mark.asyncio
    async def test_roles_have_descriptions(
        self, rbac_service: RBACService
    ) -> None:
        """All seeded roles should have non-empty descriptions."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        roles = await rbac_service.seed_default_roles(company_id=1, session=session)

        for role in roles:
            assert role.description is not None
            assert len(role.description) > 0

    @pytest.mark.asyncio
    async def test_session_add_called_for_each_role(
        self, rbac_service: RBACService
    ) -> None:
        """session.add should be called once per role."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        await rbac_service.seed_default_roles(company_id=1, session=session)

        assert session.add.call_count == 5

    @pytest.mark.asyncio
    async def test_session_flush_called(
        self, rbac_service: RBACService
    ) -> None:
        """session.flush should be called after adding roles."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        await rbac_service.seed_default_roles(company_id=1, session=session)

        session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: Edge cases (missing membership, revoked membership, null role_id)
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases in permission evaluation."""

    @pytest.mark.asyncio
    async def test_user_not_found(
        self, rbac_service: RBACService
    ) -> None:
        """Non-existent user should be denied."""
        session = AsyncMock()
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=user_result)

        result = await rbac_service.check_permission(
            user_id=999,
            company_id=1,
            resource="documents",
            action="read",
            session=session,
        )
        assert isinstance(result, AccessDenied)
        assert "not found" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_missing_membership(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """User without membership in the company should be denied."""
        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.check_permission(
            user_id=active_user.id,
            company_id=1,
            resource="documents",
            action="read",
            session=session,
        )
        assert isinstance(result, AccessDenied)
        assert "member" in result.reason.lower() or "not a member" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_revoked_membership_denied(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """Revoked membership should not be found (query filters revoked_at IS NULL)."""
        # The service queries for revoked_at.is_(None), so a revoked membership
        # won't be returned. We simulate this by returning None for membership.
        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            # Membership query returns None because revoked memberships are filtered
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.check_permission(
            user_id=active_user.id,
            company_id=1,
            resource="documents",
            action="read",
            session=session,
        )
        assert isinstance(result, AccessDenied)

    @pytest.mark.asyncio
    async def test_null_role_id_falls_back_to_legacy(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """Membership with null role_id should fall back to legacy role string."""
        # Membership with role_id=None but role="member" (legacy)
        membership = CompanyMembership(
            id=100,
            user_id=active_user.id,
            company_id=1,
            role="member",
            role_id=None,
            revoked_at=None,
        )

        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
        ]
        session.execute = AsyncMock(side_effect=results)

        # member role can read documents
        result = await rbac_service.check_permission(
            user_id=active_user.id,
            company_id=1,
            resource="documents",
            action="read",
            session=session,
        )
        assert isinstance(result, AccessGranted)

    @pytest.mark.asyncio
    async def test_null_role_id_unknown_legacy_role_denied(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """Membership with null role_id and unknown legacy role should be denied."""
        membership = CompanyMembership(
            id=101,
            user_id=active_user.id,
            company_id=1,
            role="unknown_role",
            role_id=None,
            revoked_at=None,
        )

        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.check_permission(
            user_id=active_user.id,
            company_id=1,
            resource="documents",
            action="read",
            session=session,
        )
        assert isinstance(result, AccessDenied)
        assert "role not found" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_role_id_points_to_nonexistent_role(
        self, rbac_service: RBACService, active_user: User
    ) -> None:
        """Membership with role_id pointing to deleted role falls back to legacy."""
        membership = CompanyMembership(
            id=102,
            user_id=active_user.id,
            company_id=1,
            role="viewer",
            role_id=999,  # Points to non-existent role
            revoked_at=None,
        )

        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=active_user)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            # Role lookup returns None (role doesn't exist)
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        session.execute = AsyncMock(side_effect=results)

        # Falls back to legacy "viewer" role which can read documents
        result = await rbac_service.check_permission(
            user_id=active_user.id,
            company_id=1,
            resource="documents",
            action="read",
            session=session,
        )
        assert isinstance(result, AccessGranted)


# ---------------------------------------------------------------------------
# Test: get_role_for_user
# ---------------------------------------------------------------------------


class TestGetRoleForUser:
    """Test the get_role_for_user helper method."""

    @pytest.mark.asyncio
    async def test_returns_role_for_active_membership(
        self, rbac_service: RBACService
    ) -> None:
        """Should return the role when user has active membership."""
        role = _make_role("member")
        membership = _make_membership(10, 1, role)

        session = AsyncMock()
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=membership)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=role)),
        ]
        session.execute = AsyncMock(side_effect=results)

        result = await rbac_service.get_role_for_user(
            user_id=10, company_id=1, session=session
        )
        assert result is not None
        assert result.name == "member"

    @pytest.mark.asyncio
    async def test_returns_none_for_no_membership(
        self, rbac_service: RBACService
    ) -> None:
        """Should return None when user has no membership."""
        session = AsyncMock()
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=membership_result)

        result = await rbac_service.get_role_for_user(
            user_id=10, company_id=1, session=session
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_null_role_id(
        self, rbac_service: RBACService
    ) -> None:
        """Should return None when membership has null role_id."""
        membership = CompanyMembership(
            id=200,
            user_id=10,
            company_id=1,
            role="member",
            role_id=None,
            revoked_at=None,
        )

        session = AsyncMock()
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = membership
        session.execute = AsyncMock(return_value=membership_result)

        result = await rbac_service.get_role_for_user(
            user_id=10, company_id=1, session=session
        )
        assert result is None


# ---------------------------------------------------------------------------
# Test: _has_permission static method
# ---------------------------------------------------------------------------


class TestHasPermission:
    """Test the _has_permission static helper."""

    def test_grants_when_action_in_resource(self) -> None:
        """Should return True when action is in the resource's action list."""
        permissions = {"documents": ["read", "create"]}
        assert RBACService._has_permission(permissions, "documents", "read") is True

    def test_denies_when_action_not_in_resource(self) -> None:
        """Should return False when action is not in the resource's action list."""
        permissions = {"documents": ["read"]}
        assert RBACService._has_permission(permissions, "documents", "delete") is False

    def test_denies_when_resource_not_in_permissions(self) -> None:
        """Should return False when resource is not in permissions dict."""
        permissions = {"documents": ["read"]}
        assert RBACService._has_permission(permissions, "workflows", "read") is False

    def test_denies_for_empty_permissions(self) -> None:
        """Should return False for empty permissions dict."""
        assert RBACService._has_permission({}, "documents", "read") is False

    def test_denies_for_empty_action_list(self) -> None:
        """Should return False when resource has empty action list."""
        permissions = {"documents": []}
        assert RBACService._has_permission(permissions, "documents", "read") is False


# ---------------------------------------------------------------------------
# Test: Constants validation
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify RBAC constants are correctly defined."""

    def test_resource_types_count(self) -> None:
        """Should have exactly 8 resource types."""
        assert len(RESOURCE_TYPES) == 8

    def test_resource_types_values(self) -> None:
        """Should contain all expected resource types."""
        expected = {
            "documents", "workflows", "users", "audit_logs",
            "templates", "training", "signatures", "system_config",
        }
        assert set(RESOURCE_TYPES) == expected

    def test_actions_count(self) -> None:
        """Should have exactly 5 actions."""
        assert len(ACTIONS) == 5

    def test_actions_values(self) -> None:
        """Should contain all expected actions."""
        expected = {"create", "read", "update", "delete", "approve"}
        assert set(ACTIONS) == expected

    def test_default_role_permissions_has_five_roles(self) -> None:
        """Should define permissions for exactly 5 roles."""
        assert len(DEFAULT_ROLE_PERMISSIONS) == 5

    def test_default_role_permissions_role_names(self) -> None:
        """Should have the expected role names."""
        expected = {"system_admin", "doc_admin", "it_admin", "member", "viewer"}
        assert set(DEFAULT_ROLE_PERMISSIONS.keys()) == expected
