"""Integration tests for literature API endpoint authorization.

Tests role-based access control, X-Change-Reason enforcement, HTTP 403
for unauthorized access attempts, and HTTP 429 with Retry-After header.

Uses httpx AsyncClient with ASGITransport against the FastAPI app,
overriding the get_tenant_context dependency to simulate different roles.

Requirements: 3.7, 3.8, 6.3, 8.7, 14.7
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from math import ceil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.exceptions import RateLimitExceededError
from alcoabase.main import app
from alcoabase.services.rbac import AccessDenied, AccessGranted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant_context(role: str, user_id: int = 42) -> TenantContext:
    """Create a TenantContext for a given role."""
    return TenantContext(
        company_id=1,
        company_slug="test-pharma",
        user_id=user_id,
        membership_role=role,
    )


def _override_tenant(role: str):
    """Return a dependency override function that returns a TenantContext with the given role."""

    async def _override():
        return _make_tenant_context(role)

    return _override


def _override_db_session_noop():
    """Return a dependency override that yields a MagicMock session.

    Used for endpoints where we only test authorization, not DB logic.
    The mock session simulates basic operations:
    - session.get() returns None (triggering 404 on update/delete)
    - session.flush() is a no-op
    - session.refresh() sets minimal attributes on model instances
    - session.add() tracks the added object for refresh simulation
    """

    async def _session():
        mock_session = MagicMock()
        _added_objects: list = []

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.get = AsyncMock(return_value=None)

        def _track_add(obj):
            _added_objects.append(obj)

        mock_session.add = _track_add

        async def _mock_flush():
            from datetime import datetime, timezone

            for obj in _added_objects:
                if not hasattr(obj, "id") or obj.id is None:
                    obj.id = 1
                if hasattr(obj, "created_at") and obj.created_at is None:
                    obj.created_at = datetime.now(timezone.utc)
                if hasattr(obj, "updated_at") and obj.updated_at is None:
                    obj.updated_at = datetime.now(timezone.utc)

        mock_session.flush = _mock_flush

        async def _mock_refresh(obj):
            pass  # flush already set attributes

        mock_session.refresh = _mock_refresh
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.delete = AsyncMock()
        yield mock_session

    return _session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def member_client() -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a member role user."""
    app.dependency_overrides[get_tenant_context] = _override_tenant("member")
    app.dependency_overrides[get_db_session] = _override_db_session_noop()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Integration test",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def document_admin_client() -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a document_admin role user."""
    app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
    app.dependency_overrides[get_db_session] = _override_db_session_noop()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Integration test",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def system_admin_client() -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a system_admin role user.

    Patches RBACService.check_permission to always grant access,
    simulating a system_admin that has all permissions.
    """
    app.dependency_overrides[get_tenant_context] = _override_tenant("system_admin")
    app.dependency_overrides[get_db_session] = _override_db_session_noop()

    with patch(
        "alcoabase.services.rbac.RBACService.check_permission",
        new_callable=AsyncMock,
        return_value=AccessGranted(user_id=42, resource="literature_admin", action="read"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                "X-Change-Reason": "Integration test",
            },
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def viewer_client() -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as a viewer role user (lowest permissions)."""
    app.dependency_overrides[get_tenant_context] = _override_tenant("viewer")
    app.dependency_overrides[get_db_session] = _override_db_session_noop()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Integration test",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Role-Based Access — Member can search
# Requirements: 8.7
# ---------------------------------------------------------------------------


class TestMemberSearchAccess:
    """member role can POST /api/literature/search → 200/202."""

    @pytest.mark.asyncio
    async def test_member_can_search_not_forbidden(
        self, member_client: AsyncClient
    ) -> None:
        """POST /api/literature/search with member role does NOT return 403.

        The gateway service may not be initialized (returns 503) in test env,
        but the important assertion is that the authorization check passes.
        """
        payload = {
            "terms": "CRISPR gene therapy",
            "page_size": 10,
        }
        resp = await member_client.post("/api/literature/search", json=payload)
        # Should NOT be 403 — member is authorized to search
        assert resp.status_code != 403
        # Expect 503 (service not initialized in test env) or 200/202
        assert resp.status_code in (200, 202, 503)


# ---------------------------------------------------------------------------
# Test: Role-Based Access — Member cannot configure
# Requirements: 3.7, 3.8
# ---------------------------------------------------------------------------


class TestMemberCannotConfigure:
    """member role cannot POST /api/literature/sources/{company_id}/configurations → 403."""

    @pytest.mark.asyncio
    async def test_member_cannot_create_source_configuration(
        self, member_client: AsyncClient
    ) -> None:
        """POST /api/literature/sources/1/configurations returns 403 for member."""
        payload = {
            "source_adapter_name": "pubmed",
            "is_enabled": True,
            "priority": 1,
        }
        resp = await member_client.post(
            "/api/literature/sources/1/configurations", json=payload
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_update_source_configuration(
        self, member_client: AsyncClient
    ) -> None:
        """PUT /api/literature/sources/1/configurations/1 returns 403 for member."""
        payload = {"is_enabled": False}
        resp = await member_client.put(
            "/api/literature/sources/1/configurations/1", json=payload
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_delete_source_configuration(
        self, member_client: AsyncClient
    ) -> None:
        """DELETE /api/literature/sources/1/configurations/1 returns 403 for member."""
        resp = await member_client.delete(
            "/api/literature/sources/1/configurations/1"
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_create_search_profile(
        self, member_client: AsyncClient
    ) -> None:
        """POST /api/literature/sources/1/profiles returns 403 for member."""
        payload = {
            "name": "pharma_default",
            "is_default": True,
            "enabled_sources": ["pubmed", "crossref"],
            "source_priorities": {"pubmed": 1, "crossref": 2},
            "default_filters": {},
        }
        resp = await member_client.post(
            "/api/literature/sources/1/profiles", json=payload
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_update_search_profile(
        self, member_client: AsyncClient
    ) -> None:
        """PUT /api/literature/sources/1/profiles/1 returns 403 for member."""
        payload = {"name": "updated_name"}
        resp = await member_client.put(
            "/api/literature/sources/1/profiles/1", json=payload
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_delete_search_profile(
        self, member_client: AsyncClient
    ) -> None:
        """DELETE /api/literature/sources/1/profiles/1 returns 403 for member."""
        resp = await member_client.delete(
            "/api/literature/sources/1/profiles/1"
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test: Role-Based Access — document_admin can configure
# Requirements: 3.7
# ---------------------------------------------------------------------------


class TestDocumentAdminCanConfigure:
    """document_admin can POST/PUT/DELETE configurations and profiles.

    These tests verify the endpoint does NOT return 403 for document_admin.
    The actual DB operation may return 404 (mock DB) but authorization passes.
    """

    @pytest.mark.asyncio
    async def test_document_admin_can_create_configuration(
        self, document_admin_client: AsyncClient
    ) -> None:
        """POST /api/literature/sources/1/configurations does not return 403."""
        payload = {
            "source_adapter_name": "pubmed",
            "is_enabled": True,
            "priority": 1,
        }
        resp = await document_admin_client.post(
            "/api/literature/sources/1/configurations", json=payload
        )
        # Not 403 means authorization passed
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_update_configuration(
        self, document_admin_client: AsyncClient
    ) -> None:
        """PUT /api/literature/sources/1/configurations/1 does not return 403."""
        payload = {"is_enabled": False}
        resp = await document_admin_client.put(
            "/api/literature/sources/1/configurations/1", json=payload
        )
        # Not 403 means authorization passed (expect 404 from mock DB)
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_delete_configuration(
        self, document_admin_client: AsyncClient
    ) -> None:
        """DELETE /api/literature/sources/1/configurations/1 does not return 403."""
        resp = await document_admin_client.delete(
            "/api/literature/sources/1/configurations/1"
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_create_profile(
        self, document_admin_client: AsyncClient
    ) -> None:
        """POST /api/literature/sources/1/profiles does not return 403."""
        payload = {
            "name": "pharma_default",
            "is_default": True,
            "enabled_sources": ["pubmed"],
            "source_priorities": {"pubmed": 1},
            "default_filters": {},
        }
        resp = await document_admin_client.post(
            "/api/literature/sources/1/profiles", json=payload
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_update_profile(
        self, document_admin_client: AsyncClient
    ) -> None:
        """PUT /api/literature/sources/1/profiles/1 does not return 403."""
        payload = {"name": "updated_profile"}
        resp = await document_admin_client.put(
            "/api/literature/sources/1/profiles/1", json=payload
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_delete_profile(
        self, document_admin_client: AsyncClient
    ) -> None:
        """DELETE /api/literature/sources/1/profiles/1 does not return 403."""
        resp = await document_admin_client.delete(
            "/api/literature/sources/1/profiles/1"
        )
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Test: Role-Based Access — system_admin can manage rate limits/proxy
# Requirements: 14.3, 14.4
# ---------------------------------------------------------------------------


class TestSystemAdminCanManageAdmin:
    """system_admin can GET/PUT admin/rate-limits and admin/proxy."""

    @pytest.mark.asyncio
    async def test_system_admin_can_get_rate_limits(
        self, system_admin_client: AsyncClient
    ) -> None:
        """GET /api/literature/admin/rate-limits does not return 403."""
        resp = await system_admin_client.get("/api/literature/admin/rate-limits")
        assert resp.status_code != 403
        # Expect 200 (empty list if no service registered)
        assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_system_admin_can_update_rate_limit(
        self, system_admin_client: AsyncClient
    ) -> None:
        """PUT /api/literature/admin/rate-limits/pubmed does not return 403."""
        payload = {"requests_per_second": 50}
        resp = await system_admin_client.put(
            "/api/literature/admin/rate-limits/pubmed", json=payload
        )
        # Not 403 — may be 503 (service not init) or 404 (source not found)
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_system_admin_can_get_proxy(
        self, system_admin_client: AsyncClient
    ) -> None:
        """GET /api/literature/admin/proxy does not return 403."""
        resp = await system_admin_client.get("/api/literature/admin/proxy")
        assert resp.status_code != 403
        # Expect 404 (no config) or 200
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_system_admin_can_update_proxy(
        self, system_admin_client: AsyncClient
    ) -> None:
        """PUT /api/literature/admin/proxy does not return 403."""
        payload = {
            "proxy_url": "http://proxy.internal:8080",
            "is_active": True,
        }
        resp = await system_admin_client.put(
            "/api/literature/admin/proxy", json=payload
        )
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Test: Unauthorized access — viewer/member cannot access admin endpoints
# Requirements: 3.8, 14.7
# ---------------------------------------------------------------------------


class TestUnauthorizedAccess403:
    """Test HTTP 403 for unauthorized access attempts."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_search(self) -> None:
        """POST /api/literature/search returns 403 for viewer role.

        viewer is not in the allowed roles (member, admin, document_admin, system_admin).
        """
        app.dependency_overrides[get_tenant_context] = _override_tenant("viewer")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                "X-Change-Reason": "Test",
            },
        ) as client:
            payload = {"terms": "test query"}
            resp = await client.post("/api/literature/search", json=payload)
            assert resp.status_code == 403

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_configuration(
        self, viewer_client: AsyncClient
    ) -> None:
        """POST /api/literature/sources/1/configurations returns 403 for viewer."""
        payload = {
            "source_adapter_name": "pubmed",
            "is_enabled": True,
            "priority": 1,
        }
        resp = await viewer_client.post(
            "/api/literature/sources/1/configurations", json=payload
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_access_admin_rate_limits(self) -> None:
        """GET /api/literature/admin/rate-limits returns 403 for member role."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("member")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        with patch(
            "alcoabase.services.rbac.RBACService.check_permission",
            new_callable=AsyncMock,
            return_value=AccessDenied(
                user_id=42,
                resource="literature_admin",
                action="read",
                reason="Missing permission: read on literature_admin",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-User-Id": "42", "X-Company-Id": "1"},
            ) as client:
                resp = await client.get("/api/literature/admin/rate-limits")
                assert resp.status_code == 403

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_access_admin_proxy(self) -> None:
        """GET /api/literature/admin/proxy returns 403 for member role."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("member")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        with patch(
            "alcoabase.services.rbac.RBACService.check_permission",
            new_callable=AsyncMock,
            return_value=AccessDenied(
                user_id=42,
                resource="literature_admin",
                action="read",
                reason="Missing permission: read on literature_admin",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-User-Id": "42", "X-Company-Id": "1"},
            ) as client:
                resp = await client.get("/api/literature/admin/proxy")
                assert resp.status_code == 403

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_document_admin_cannot_update_rate_limits(self) -> None:
        """PUT /api/literature/admin/rate-limits/pubmed returns 403 for document_admin."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        with patch(
            "alcoabase.services.rbac.RBACService.check_permission",
            new_callable=AsyncMock,
            return_value=AccessDenied(
                user_id=42,
                resource="literature_admin",
                action="update",
                reason="Missing permission: update on literature_admin",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "X-User-Id": "42",
                    "X-Company-Id": "1",
                    "X-Change-Reason": "Test",
                },
            ) as client:
                payload = {"requests_per_second": 100}
                resp = await client.put(
                    "/api/literature/admin/rate-limits/pubmed", json=payload
                )
                assert resp.status_code == 403

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: X-Change-Reason Enforcement on Mutation Endpoints
# Requirements: 14.7
# ---------------------------------------------------------------------------


class TestXChangeReasonEnforcement:
    """Test X-Change-Reason enforcement on mutation endpoints.

    Missing X-Change-Reason on mutations should return 400 or 422.
    """

    @pytest.mark.asyncio
    async def test_create_config_missing_change_reason(self) -> None:
        """POST /api/literature/sources/1/configurations without X-Change-Reason → 400/422."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason header
            },
        ) as client:
            payload = {
                "source_adapter_name": "pubmed",
                "is_enabled": True,
                "priority": 1,
            }
            resp = await client.post(
                "/api/literature/sources/1/configurations", json=payload
            )
            assert resp.status_code in (400, 422)

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_config_missing_change_reason(self) -> None:
        """PUT /api/literature/sources/1/configurations/1 without X-Change-Reason → 400/422."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
            },
        ) as client:
            payload = {"is_enabled": False}
            resp = await client.put(
                "/api/literature/sources/1/configurations/1", json=payload
            )
            assert resp.status_code in (400, 422)

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_config_missing_change_reason(self) -> None:
        """DELETE /api/literature/sources/1/configurations/1 without X-Change-Reason → 400/422."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
            },
        ) as client:
            resp = await client.delete(
                "/api/literature/sources/1/configurations/1"
            )
            assert resp.status_code in (400, 422)

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_profile_missing_change_reason(self) -> None:
        """POST /api/literature/sources/1/profiles without X-Change-Reason → 400/422."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
            },
        ) as client:
            payload = {
                "name": "test_profile",
                "is_default": False,
                "enabled_sources": ["pubmed"],
                "source_priorities": {},
                "default_filters": {},
            }
            resp = await client.post(
                "/api/literature/sources/1/profiles", json=payload
            )
            assert resp.status_code in (400, 422)

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_profile_missing_change_reason(self) -> None:
        """PUT /api/literature/sources/1/profiles/1 without X-Change-Reason → 400/422."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
            },
        ) as client:
            payload = {"name": "new_name"}
            resp = await client.put(
                "/api/literature/sources/1/profiles/1", json=payload
            )
            assert resp.status_code in (400, 422)

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_profile_missing_change_reason(self) -> None:
        """DELETE /api/literature/sources/1/profiles/1 without X-Change-Reason → 400/422."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
            },
        ) as client:
            resp = await client.delete(
                "/api/literature/sources/1/profiles/1"
            )
            assert resp.status_code in (400, 422)

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_missing_change_reason_returns_422(self) -> None:
        """POST /api/literature/search without X-Change-Reason → 422.

        The search endpoint declares X-Change-Reason as a required Header(...),
        so FastAPI returns 422 (validation error) when it's missing.
        """
        app.dependency_overrides[get_tenant_context] = _override_tenant("member")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason
            },
        ) as client:
            payload = {"terms": "test query"}
            resp = await client.post("/api/literature/search", json=payload)
            assert resp.status_code in (400, 422)

        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: HTTP 429 Response with Retry-After Header
# Requirements: 6.3, 8.7
# ---------------------------------------------------------------------------


class TestRateLimitResponse429:
    """Test HTTP 429 response includes Retry-After header.

    Mocks the gateway service to raise RateLimitExceededError.
    """

    @pytest.mark.asyncio
    async def test_429_response_includes_retry_after_header(self) -> None:
        """When gateway raises RateLimitExceededError, response has 429 + Retry-After."""
        retry_seconds = 42.7

        # Create a mock gateway service that raises RateLimitExceededError
        mock_gateway = MagicMock()
        mock_gateway.should_dispatch_async.return_value = False
        mock_gateway.search = AsyncMock(
            side_effect=RateLimitExceededError(
                "Company rate limit exceeded for source 'pubmed'.",
                retry_after_seconds=retry_seconds,
                company_id=1,
                source_adapter_name="pubmed",
            )
        )

        app.dependency_overrides[get_tenant_context] = _override_tenant("member")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        # Set the mock gateway service on app state
        original_gateway = getattr(app.state, "literature_gateway_service", None)
        app.state.literature_gateway_service = mock_gateway

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "X-User-Id": "42",
                    "X-Company-Id": "1",
                    "X-Change-Reason": "Rate limit test",
                },
            ) as client:
                payload = {"terms": "CRISPR therapy"}
                resp = await client.post("/api/literature/search", json=payload)

                # Verify HTTP 429 status
                assert resp.status_code == 429

                # Verify Retry-After header is present
                assert "retry-after" in resp.headers
                retry_after_value = int(resp.headers["retry-after"])
                assert retry_after_value == ceil(retry_seconds)

                # Verify response body includes retry info
                body = resp.json()
                assert "retry_after_seconds" in body
                assert body["retry_after_seconds"] == retry_seconds
        finally:
            # Restore original state
            if original_gateway is not None:
                app.state.literature_gateway_service = original_gateway
            elif hasattr(app.state, "literature_gateway_service"):
                del app.state.literature_gateway_service
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_429_retry_after_rounds_up(self) -> None:
        """Retry-After header value is ceiling of fractional seconds."""
        retry_seconds = 3.2

        mock_gateway = MagicMock()
        mock_gateway.should_dispatch_async.return_value = False
        mock_gateway.search = AsyncMock(
            side_effect=RateLimitExceededError(
                "Rate limit exceeded.",
                retry_after_seconds=retry_seconds,
                company_id=1,
            )
        )

        app.dependency_overrides[get_tenant_context] = _override_tenant("member")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()
        app.state.literature_gateway_service = mock_gateway

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "X-User-Id": "42",
                    "X-Company-Id": "1",
                    "X-Change-Reason": "Rate limit test",
                },
            ) as client:
                payload = {"terms": "test query"}
                resp = await client.post("/api/literature/search", json=payload)

                assert resp.status_code == 429
                # ceil(3.2) = 4
                assert resp.headers["retry-after"] == "4"
        finally:
            if hasattr(app.state, "literature_gateway_service"):
                del app.state.literature_gateway_service
            app.dependency_overrides.clear()
