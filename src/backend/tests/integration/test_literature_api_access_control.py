"""Integration tests for literature review API access control.

Tests role-based access control, cross-tenant isolation (404 not 403),
X-Change-Reason enforcement on mutations, and configuration validation
(HTTP 422 for out-of-range values).

Uses httpx AsyncClient with ASGITransport against the FastAPI app,
overriding the get_tenant_context dependency to simulate different roles.

Requirements: 2.9, 4.8, 6.5, 8.7, 8.8, 9.9, 9.10, 10.7, 10.8, 10.9
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPANY_A_ID = 1
COMPANY_B_ID = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant_context(
    role: str,
    company_id: int = COMPANY_A_ID,
    user_id: int = 42,
) -> TenantContext:
    """Create a TenantContext for a given role and company."""
    return TenantContext(
        company_id=company_id,
        company_slug=f"company-{company_id}",
        user_id=user_id,
        membership_role=role,
    )


def _override_tenant(role: str, company_id: int = COMPANY_A_ID):
    """Return a dependency override that returns a TenantContext with the given role."""

    async def _override():
        return _make_tenant_context(role, company_id=company_id)

    return _override


def _override_db_session_noop():
    """Return a dependency override that yields a MagicMock session.

    Simulates basic DB operations for authorization-only tests.
    """

    async def _session():
        mock_session = MagicMock()
        _added_objects: list = []

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar_one.return_value = 0
        mock_result.scalar.return_value = 0
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
            pass

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
    """Client authenticated as a member role user (Company A)."""
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
    """Client authenticated as a document_admin role user (Company A)."""
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
    """Client authenticated as a system_admin role user (Company A)."""
    app.dependency_overrides[get_tenant_context] = _override_tenant("system_admin")
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


@pytest_asyncio.fixture
async def cross_tenant_client() -> AsyncGenerator[AsyncClient, None]:
    """Client authenticated as document_admin for Company B (cross-tenant).

    Used to verify that accessing Company A resources returns 404.
    """
    app.dependency_overrides[get_tenant_context] = _override_tenant(
        "document_admin", company_id=COMPANY_B_ID
    )
    app.dependency_overrides[get_db_session] = _override_db_session_noop()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "99",
            "X-Company-Id": "2",
            "X-Change-Reason": "Cross-tenant test",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def no_change_reason_client() -> AsyncGenerator[AsyncClient, None]:
    """Client as document_admin WITHOUT X-Change-Reason header."""
    app.dependency_overrides[get_tenant_context] = _override_tenant("document_admin")
    app.dependency_overrides[get_db_session] = _override_db_session_noop()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            # Deliberately no X-Change-Reason
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample payloads
# ---------------------------------------------------------------------------

_VALID_PROTOCOL_PAYLOAD = {
    "name": "Test Screening Protocol",
    "pico_criteria": {"population": "Adults with diabetes"},
    "inclusion_criteria": ["randomized controlled trial"],
}

_VALID_REVIEW_PAYLOAD = {
    "protocol_id": 1,
    "name": "Test SLR Review",
    "record_filter": {"ingestion_record_ids": [1, 2, 3]},
}

_VALID_OVERRIDE_PAYLOAD = {
    "human_verdict": "include",
    "human_rationale": "Relevant study confirmed by manual review",
}

_VALID_CONTRADICTION_STATUS_PAYLOAD = {
    "status": "acknowledged",
}

_VALID_NOVELTY_STATUS_PAYLOAD = {
    "status": "acknowledged",
}

_VALID_CONFIG_PAYLOAD = {
    "default_batch_size": 50,
    "confidence_threshold": 0.9,
    "max_concurrent": 10,
}


# ===========================================================================
# Test 1: Member role can access GET endpoints, cannot access POST/PUT/DELETE
# Requirements: 8.7, 8.8, 9.9, 9.10, 10.7, 10.8
# ===========================================================================


@pytest.mark.integration
class TestMemberRoleReadAccess:
    """Member role can access GET (read) endpoints."""

    @pytest.mark.asyncio
    async def test_member_can_list_protocols(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/screening/protocols")
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_member_can_get_protocol(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/screening/protocols/1")
        # 404 is expected (no real data), but not 403
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_member_can_list_reviews(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/reviews")
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_member_can_get_review(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/reviews/1")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_member_can_list_decisions(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/reviews/1/decisions")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_member_can_get_progress(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/reviews/1/progress")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_member_can_get_report(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/reviews/1/report")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_member_can_list_contradictions(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/contradictions")
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_member_can_get_contradiction_summary(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/contradictions/summary")
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_member_can_get_contradiction_detail(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/contradictions/1")
        assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_member_can_list_novelty_flags(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.get("/api/literature/novelty")
        assert resp.status_code != 403


@pytest.mark.integration
class TestMemberRoleMutationDenied:
    """Member role cannot access mutation (POST/PUT/DELETE) endpoints."""

    @pytest.mark.asyncio
    async def test_member_cannot_create_protocol(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.post(
            "/api/literature/screening/protocols",
            json=_VALID_PROTOCOL_PAYLOAD,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_update_protocol(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.put(
            "/api/literature/screening/protocols/1",
            json={"name": "Updated"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_delete_protocol(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.delete(
            "/api/literature/screening/protocols/1",
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_activate_protocol(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.post(
            "/api/literature/screening/protocols/1/activate",
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_create_review(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.post(
            "/api/literature/reviews",
            json=_VALID_REVIEW_PAYLOAD,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_initiate_screening(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.post(
            "/api/literature/reviews/1/screen",
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_override_decision(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.put(
            "/api/literature/reviews/1/decisions/1/override",
            json=_VALID_OVERRIDE_PAYLOAD,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_update_contradiction_status(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.put(
            "/api/literature/contradictions/1/status",
            json=_VALID_CONTRADICTION_STATUS_PAYLOAD,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_update_novelty_status(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.put(
            "/api/literature/novelty/1/status",
            json=_VALID_NOVELTY_STATUS_PAYLOAD,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_update_config(
        self, member_client: AsyncClient
    ) -> None:
        resp = await member_client.put(
            "/api/literature/screening/config",
            json=_VALID_CONFIG_PAYLOAD,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_member_cannot_get_config(
        self, member_client: AsyncClient
    ) -> None:
        """Config read requires document_admin (Requirement 11.4)."""
        resp = await member_client.get("/api/literature/screening/config")
        assert resp.status_code == 403


# ===========================================================================
# Test 2: document_admin can access mutation endpoints
# Requirements: 2.9, 8.8, 9.10, 10.8
# ===========================================================================


@pytest.mark.integration
class TestDocumentAdminMutationAccess:
    """document_admin role can access mutation endpoints (except config update)."""

    @pytest.mark.asyncio
    async def test_document_admin_can_create_protocol(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.post(
            "/api/literature/screening/protocols",
            json=_VALID_PROTOCOL_PAYLOAD,
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_update_protocol(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.put(
            "/api/literature/screening/protocols/1",
            json={"name": "Updated Protocol"},
        )
        # 404 is acceptable (no real data); but not 403
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_delete_protocol(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.delete(
            "/api/literature/screening/protocols/1",
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_activate_protocol(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.post(
            "/api/literature/screening/protocols/1/activate",
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_create_review(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.post(
            "/api/literature/reviews",
            json=_VALID_REVIEW_PAYLOAD,
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_initiate_screening(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.post(
            "/api/literature/reviews/1/screen",
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_override_decision(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.put(
            "/api/literature/reviews/1/decisions/1/override",
            json=_VALID_OVERRIDE_PAYLOAD,
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_update_contradiction_status(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.put(
            "/api/literature/contradictions/1/status",
            json=_VALID_CONTRADICTION_STATUS_PAYLOAD,
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_update_novelty_status(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.put(
            "/api/literature/novelty/1/status",
            json=_VALID_NOVELTY_STATUS_PAYLOAD,
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_can_get_config(
        self, document_admin_client: AsyncClient
    ) -> None:
        resp = await document_admin_client.get(
            "/api/literature/screening/config",
        )
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_document_admin_cannot_update_config(
        self, document_admin_client: AsyncClient
    ) -> None:
        """Config updates require system_admin — document_admin is insufficient."""
        resp = await document_admin_client.put(
            "/api/literature/screening/config",
            json=_VALID_CONFIG_PAYLOAD,
        )
        assert resp.status_code == 403


# ===========================================================================
# Test 3: system_admin required for config updates
# Requirements: 8.8, 11.4
# ===========================================================================


@pytest.mark.integration
class TestSystemAdminConfigAccess:
    """system_admin role required for screening configuration updates."""

    @pytest.mark.asyncio
    async def test_system_admin_can_update_config(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json=_VALID_CONFIG_PAYLOAD,
        )
        # Should not be 403 — system_admin has full access
        assert resp.status_code != 403

    @pytest.mark.asyncio
    async def test_system_admin_can_get_config(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.get(
            "/api/literature/screening/config",
        )
        assert resp.status_code != 403


# ===========================================================================
# Test 4: Cross-tenant access returns 404 (not 403)
# Requirements: 10.9
# ===========================================================================


@pytest.mark.integration
class TestCrossTenantAccess404:
    """Accessing resources from another company returns 404, not 403.

    This prevents information leakage about resource existence across tenants.
    """

    @pytest.mark.asyncio
    async def test_cross_tenant_get_protocol_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.get(
            "/api/literature/screening/protocols/1"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_get_review_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.get("/api/literature/reviews/1")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_get_contradiction_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.get(
            "/api/literature/contradictions/1"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_update_protocol_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.put(
            "/api/literature/screening/protocols/1",
            json={"name": "Hacked Protocol"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_delete_protocol_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.delete(
            "/api/literature/screening/protocols/1",
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_override_decision_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.put(
            "/api/literature/reviews/1/decisions/1/override",
            json=_VALID_OVERRIDE_PAYLOAD,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_update_contradiction_status_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.put(
            "/api/literature/contradictions/1/status",
            json=_VALID_CONTRADICTION_STATUS_PAYLOAD,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_update_novelty_status_returns_404(
        self, cross_tenant_client: AsyncClient
    ) -> None:
        resp = await cross_tenant_client.put(
            "/api/literature/novelty/1/status",
            json=_VALID_NOVELTY_STATUS_PAYLOAD,
        )
        assert resp.status_code == 404


# ===========================================================================
# Test 5: Missing X-Change-Reason on mutation → 400
# Requirements: 8.7, 9.9, 10.7
# ===========================================================================


@pytest.mark.integration
class TestXChangeReasonEnforcement:
    """Missing X-Change-Reason header on mutation endpoints returns 400."""

    @pytest.mark.asyncio
    async def test_create_protocol_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.post(
            "/api/literature/screening/protocols",
            json=_VALID_PROTOCOL_PAYLOAD,
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_protocol_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.put(
            "/api/literature/screening/protocols/1",
            json={"name": "Updated"},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_protocol_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.delete(
            "/api/literature/screening/protocols/1",
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_activate_protocol_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.post(
            "/api/literature/screening/protocols/1/activate",
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_review_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.post(
            "/api/literature/reviews",
            json=_VALID_REVIEW_PAYLOAD,
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_initiate_screening_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.post(
            "/api/literature/reviews/1/screen",
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_override_decision_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.put(
            "/api/literature/reviews/1/decisions/1/override",
            json=_VALID_OVERRIDE_PAYLOAD,
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_contradiction_status_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.put(
            "/api/literature/contradictions/1/status",
            json=_VALID_CONTRADICTION_STATUS_PAYLOAD,
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_novelty_status_missing_change_reason(
        self, no_change_reason_client: AsyncClient
    ) -> None:
        resp = await no_change_reason_client.put(
            "/api/literature/novelty/1/status",
            json=_VALID_NOVELTY_STATUS_PAYLOAD,
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_config_missing_change_reason(self) -> None:
        """Config mutation without X-Change-Reason returns 400."""
        app.dependency_overrides[get_tenant_context] = _override_tenant("system_admin")
        app.dependency_overrides[get_db_session] = _override_db_session_noop()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason
            },
        ) as ac:
            resp = await ac.put(
                "/api/literature/screening/config",
                json=_VALID_CONFIG_PAYLOAD,
            )
            assert resp.status_code == 400
            assert "X-Change-Reason" in resp.json()["detail"]

        app.dependency_overrides.clear()


# ===========================================================================
# Test 6: Config update with out-of-range batch_size → 422
# Requirements: 11.6
# ===========================================================================


@pytest.mark.integration
class TestConfigRangeValidation:
    """Configuration updates with out-of-range values return HTTP 422."""

    @pytest.mark.asyncio
    async def test_batch_size_too_low(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json={"default_batch_size": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_batch_size_too_high(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json={"default_batch_size": 101},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_confidence_too_low(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json={"confidence_threshold": 0.3},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_confidence_too_high(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json={"confidence_threshold": 1.5},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_max_concurrent_too_low(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json={"max_concurrent": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_max_concurrent_too_high(
        self, system_admin_client: AsyncClient
    ) -> None:
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json={"max_concurrent": 21},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_config_not_rejected(
        self, system_admin_client: AsyncClient
    ) -> None:
        """In-range values should not return 422."""
        resp = await system_admin_client.put(
            "/api/literature/screening/config",
            json={"default_batch_size": 50, "confidence_threshold": 0.8},
        )
        # Could be 200 or 500 depending on mock, but NOT 422
        assert resp.status_code != 422


# ===========================================================================
# Test: Viewer role (lowest) gets 403 on everything
# Requirements: 4.8, 10.7
# ===========================================================================


@pytest.mark.integration
class TestViewerRoleDenied:
    """Viewer role is denied access to all literature review endpoints."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_list_protocols(
        self, viewer_client: AsyncClient
    ) -> None:
        resp = await viewer_client.get("/api/literature/screening/protocols")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_list_reviews(
        self, viewer_client: AsyncClient
    ) -> None:
        resp = await viewer_client.get("/api/literature/reviews")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_list_contradictions(
        self, viewer_client: AsyncClient
    ) -> None:
        resp = await viewer_client.get("/api/literature/contradictions")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_list_novelty(
        self, viewer_client: AsyncClient
    ) -> None:
        resp = await viewer_client.get("/api/literature/novelty")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_protocol(
        self, viewer_client: AsyncClient
    ) -> None:
        resp = await viewer_client.post(
            "/api/literature/screening/protocols",
            json=_VALID_PROTOCOL_PAYLOAD,
        )
        assert resp.status_code == 403
