"""Unit tests for the require_permission FastAPI dependency.

Tests cover:
- Successful permission grant returns TenantContext
- Deactivated user receives HTTP 403
- Missing permission receives HTTP 403 with descriptive message
- Dependency chains on top of get_tenant_context
- Factory returns a callable dependency

References:
    - Requirements: 2.6, 8.2, 12.1, 12.2, 12.3
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.services.rbac import AccessDenied, AccessGranted


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Create a sample TenantContext."""
    return TenantContext(
        company_id=1,
        company_slug="acme-corp",
        user_id=10,
        membership_role="system_admin",
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    return AsyncMock()


# ---------------------------------------------------------------------------
# Test: Factory returns a callable
# ---------------------------------------------------------------------------


class TestRequirePermissionFactory:
    """Test that require_permission factory produces valid dependencies."""

    def test_returns_callable(self) -> None:
        """require_permission should return a callable dependency."""
        dep = require_permission("users", "read")
        assert callable(dep)

    def test_different_resources_produce_different_deps(self) -> None:
        """Different resource/action combos should produce distinct dependencies."""
        dep1 = require_permission("users", "read")
        dep2 = require_permission("documents", "create")
        # They are different function objects
        assert dep1 is not dep2


# ---------------------------------------------------------------------------
# Test: Successful permission grant (Requirement 2.6)
# ---------------------------------------------------------------------------


class TestPermissionGranted:
    """Test that successful permission checks return TenantContext."""

    @pytest.mark.asyncio
    async def test_returns_tenant_context_on_grant(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """Dependency should return TenantContext when permission is granted."""
        dep = require_permission("users", "read")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessGranted(
                    user_id=10, resource="users", action="read"
                )
            )

            result = await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert result is tenant_ctx
        assert result.company_id == 1
        assert result.user_id == 10

    @pytest.mark.asyncio
    async def test_calls_rbac_service_with_correct_args(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """Dependency should pass correct args to RBACService.check_permission."""
        dep = require_permission("documents", "create")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessGranted(
                    user_id=10, resource="documents", action="create"
                )
            )

            await dep(tenant_ctx=tenant_ctx, session=mock_session)

            mock_service.check_permission.assert_awaited_once_with(
                user_id=10,
                company_id=1,
                resource="documents",
                action="create",
                session=mock_session,
            )


# ---------------------------------------------------------------------------
# Test: Permission denied raises HTTP 403 (Requirements 8.2, 12.3)
# ---------------------------------------------------------------------------


class TestPermissionDenied:
    """Test that denied permissions raise HTTP 403."""

    @pytest.mark.asyncio
    async def test_raises_403_on_denial(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """Dependency should raise HTTPException 403 when permission is denied."""
        dep = require_permission("users", "create")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessDenied(
                    user_id=10,
                    resource="users",
                    action="create",
                    reason="Missing permission: create on users",
                )
            )

            with pytest.raises(HTTPException) as exc_info:
                await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert exc_info.value.status_code == 403
        assert "Missing permission: create on users" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_deactivated_user_403_message(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """Deactivated user should get 403 with deactivation message."""
        dep = require_permission("documents", "read")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessDenied(
                    user_id=10,
                    resource="documents",
                    action="read",
                    reason="Account is deactivated. Contact your administrator.",
                )
            )

            with pytest.raises(HTTPException) as exc_info:
                await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert exc_info.value.status_code == 403
        assert "deactivated" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_not_a_member_403_message(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """User not a member of company should get 403 with membership message."""
        dep = require_permission("workflows", "approve")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessDenied(
                    user_id=10,
                    resource="workflows",
                    action="approve",
                    reason="Not a member of the specified company.",
                )
            )

            with pytest.raises(HTTPException) as exc_info:
                await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert exc_info.value.status_code == 403
        assert "member" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_descriptive_error_for_workflow_denial(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """Workflow permission denial should include resource and action in message."""
        dep = require_permission("workflows", "approve")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessDenied(
                    user_id=10,
                    resource="workflows",
                    action="approve",
                    reason="Missing permission: approve on workflows",
                )
            )

            with pytest.raises(HTTPException) as exc_info:
                await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert "approve" in exc_info.value.detail
        assert "workflows" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Test: Workflow and document permission integration (Requirements 12.1, 12.2)
# ---------------------------------------------------------------------------


class TestWorkflowDocumentPermissions:
    """Test RBAC dependency for workflow and document permission scenarios."""

    @pytest.mark.asyncio
    async def test_workflow_approve_granted_for_authorized_role(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """User with workflows:approve permission gets access granted (Req 12.1)."""
        dep = require_permission("workflows", "approve")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessGranted(
                    user_id=10, resource="workflows", action="approve"
                )
            )

            result = await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert result is tenant_ctx

    @pytest.mark.asyncio
    async def test_document_update_granted_for_authorized_role(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """User with documents:update permission gets access granted (Req 12.2)."""
        dep = require_permission("documents", "update")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessGranted(
                    user_id=10, resource="documents", action="update"
                )
            )

            result = await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert result is tenant_ctx

    @pytest.mark.asyncio
    async def test_document_update_denied_returns_403(
        self, tenant_ctx: TenantContext, mock_session: AsyncMock
    ) -> None:
        """User without documents:update permission gets 403 (Req 12.2, 12.3)."""
        dep = require_permission("documents", "update")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessDenied(
                    user_id=10,
                    resource="documents",
                    action="update",
                    reason="Missing permission: update on documents",
                )
            )

            with pytest.raises(HTTPException) as exc_info:
                await dep(tenant_ctx=tenant_ctx, session=mock_session)

        assert exc_info.value.status_code == 403
        assert "update" in exc_info.value.detail
        assert "documents" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_deactivated_system_admin_denied_regardless_of_role(
        self, mock_session: AsyncMock
    ) -> None:
        """Even system_admin gets 403 when deactivated (Req 8.2)."""
        admin_ctx = TenantContext(
            company_id=1,
            company_slug="acme-corp",
            user_id=10,
            membership_role="system_admin",
        )
        dep = require_permission("users", "create")

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBACService:
            mock_service = MockRBACService.return_value
            mock_service.check_permission = AsyncMock(
                return_value=AccessDenied(
                    user_id=10,
                    resource="users",
                    action="create",
                    reason="Account is deactivated. Contact your administrator.",
                )
            )

            with pytest.raises(HTTPException) as exc_info:
                await dep(tenant_ctx=admin_ctx, session=mock_session)

        assert exc_info.value.status_code == 403
        assert "deactivated" in exc_info.value.detail.lower()
