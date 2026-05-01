"""Tests for the audit middleware.

Validates that the AuditMiddleware correctly:
- Injects server-side UTC timestamps into request state
- Extracts user_id from X-User-Id header
- Extracts reason_for_change from X-Change-Reason header
- Requires X-Change-Reason on mutating requests (POST, PUT, PATCH, DELETE)
- Allows GET/HEAD/OPTIONS requests without X-Change-Reason
- Exempts health/docs endpoints from the change reason requirement
"""

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from alcoabase.middleware.audit_middleware import (
    AuditMiddleware,
    _extract_user_id,
    _is_mutating_gxp_request,
)


# ---------------------------------------------------------------------------
# Test application fixture
# ---------------------------------------------------------------------------


def _create_test_app(require_reason: bool = True) -> FastAPI:
    """Create a minimal FastAPI app with AuditMiddleware for testing."""
    app = FastAPI()
    app.add_middleware(AuditMiddleware, require_reason_for_mutations=require_reason)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/documents")
    async def list_documents(request: Request) -> dict:
        return {
            "audit_user_id": request.state.audit_user_id,
            "audit_reason": request.state.audit_reason,
            "audit_timestamp": request.state.audit_timestamp.isoformat(),
        }

    @app.post("/api/documents")
    async def create_document(request: Request) -> dict:
        return {
            "audit_user_id": request.state.audit_user_id,
            "audit_reason": request.state.audit_reason,
            "audit_timestamp": request.state.audit_timestamp.isoformat(),
        }

    @app.put("/api/documents/1")
    async def update_document(request: Request) -> dict:
        return {
            "audit_user_id": request.state.audit_user_id,
            "audit_reason": request.state.audit_reason,
            "audit_timestamp": request.state.audit_timestamp.isoformat(),
        }

    @app.patch("/api/documents/1")
    async def patch_document(request: Request) -> dict:
        return {
            "audit_user_id": request.state.audit_user_id,
            "audit_reason": request.state.audit_reason,
            "audit_timestamp": request.state.audit_timestamp.isoformat(),
        }

    @app.delete("/api/documents/1")
    async def delete_document(request: Request) -> dict:
        return {
            "audit_user_id": request.state.audit_user_id,
            "audit_reason": request.state.audit_reason,
            "audit_timestamp": request.state.audit_timestamp.isoformat(),
        }

    return app


@pytest.fixture
def client() -> TestClient:
    """Test client with audit middleware enabled."""
    app = _create_test_app(require_reason=True)
    return TestClient(app)


@pytest.fixture
def client_no_reason_required() -> TestClient:
    """Test client with reason requirement disabled."""
    app = _create_test_app(require_reason=False)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests: Server-side UTC timestamp injection
# ---------------------------------------------------------------------------


class TestTimestampInjection:
    """Tests for server-side UTC timestamp generation."""

    def test_timestamp_is_utc(self, client: TestClient) -> None:
        """Audit timestamp uses UTC timezone."""
        response = client.get("/api/documents")
        assert response.status_code == 200
        ts = datetime.fromisoformat(response.json()["audit_timestamp"])
        assert ts.tzinfo == timezone.utc

    def test_timestamp_is_recent(self, client: TestClient) -> None:
        """Audit timestamp is generated at request time (within 2 seconds)."""
        before = datetime.now(timezone.utc)
        response = client.get("/api/documents")
        after = datetime.now(timezone.utc)
        assert response.status_code == 200
        ts = datetime.fromisoformat(response.json()["audit_timestamp"])
        assert before <= ts <= after

    def test_timestamp_independent_of_client(self, client: TestClient) -> None:
        """Timestamp is server-generated, not from any client header."""
        response = client.get(
            "/api/documents",
            headers={"X-Client-Timestamp": "2000-01-01T00:00:00+00:00"},
        )
        assert response.status_code == 200
        ts = datetime.fromisoformat(response.json()["audit_timestamp"])
        # Should be recent, not year 2000
        assert ts.year >= 2024


# ---------------------------------------------------------------------------
# Tests: User ID extraction
# ---------------------------------------------------------------------------


class TestUserIdExtraction:
    """Tests for user_id extraction from request headers."""

    def test_extracts_user_id_from_header(self, client: TestClient) -> None:
        """User ID is extracted from X-User-Id header."""
        response = client.get(
            "/api/documents", headers={"X-User-Id": "user-42"}
        )
        assert response.status_code == 200
        assert response.json()["audit_user_id"] == "user-42"

    def test_user_id_none_when_header_missing(self, client: TestClient) -> None:
        """User ID is None when X-User-Id header is not provided."""
        response = client.get("/api/documents")
        assert response.status_code == 200
        assert response.json()["audit_user_id"] is None

    def test_user_id_preserves_value(self, client: TestClient) -> None:
        """User ID value is preserved exactly as provided."""
        response = client.get(
            "/api/documents", headers={"X-User-Id": "admin@example.com"}
        )
        assert response.status_code == 200
        assert response.json()["audit_user_id"] == "admin@example.com"


# ---------------------------------------------------------------------------
# Tests: Reason for change extraction
# ---------------------------------------------------------------------------


class TestReasonExtraction:
    """Tests for reason_for_change extraction from X-Change-Reason header."""

    def test_extracts_reason_from_header(self, client: TestClient) -> None:
        """Reason is extracted from X-Change-Reason header."""
        response = client.post(
            "/api/documents",
            headers={
                "X-User-Id": "user-1",
                "X-Change-Reason": "Initial document creation",
            },
        )
        assert response.status_code == 200
        assert response.json()["audit_reason"] == "Initial document creation"

    def test_reason_none_on_get_request(self, client: TestClient) -> None:
        """Reason is None when header is not provided on GET."""
        response = client.get("/api/documents")
        assert response.status_code == 200
        assert response.json()["audit_reason"] is None


# ---------------------------------------------------------------------------
# Tests: Mutating request enforcement
# ---------------------------------------------------------------------------


class TestMutatingRequestEnforcement:
    """Tests for X-Change-Reason requirement on mutating requests."""

    def test_post_without_reason_returns_400(self, client: TestClient) -> None:
        """POST without X-Change-Reason returns HTTP 400."""
        response = client.post(
            "/api/documents", headers={"X-User-Id": "user-1"}
        )
        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    def test_put_without_reason_returns_400(self, client: TestClient) -> None:
        """PUT without X-Change-Reason returns HTTP 400."""
        response = client.put(
            "/api/documents/1", headers={"X-User-Id": "user-1"}
        )
        assert response.status_code == 400

    def test_patch_without_reason_returns_400(self, client: TestClient) -> None:
        """PATCH without X-Change-Reason returns HTTP 400."""
        response = client.patch(
            "/api/documents/1", headers={"X-User-Id": "user-1"}
        )
        assert response.status_code == 400

    def test_delete_without_reason_returns_400(self, client: TestClient) -> None:
        """DELETE without X-Change-Reason returns HTTP 400."""
        response = client.delete(
            "/api/documents/1", headers={"X-User-Id": "user-1"}
        )
        assert response.status_code == 400

    def test_post_with_reason_succeeds(self, client: TestClient) -> None:
        """POST with X-Change-Reason succeeds."""
        response = client.post(
            "/api/documents",
            headers={
                "X-User-Id": "user-1",
                "X-Change-Reason": "Creating new document",
            },
        )
        assert response.status_code == 200

    def test_put_with_reason_succeeds(self, client: TestClient) -> None:
        """PUT with X-Change-Reason succeeds."""
        response = client.put(
            "/api/documents/1",
            headers={
                "X-User-Id": "user-1",
                "X-Change-Reason": "Updating document",
            },
        )
        assert response.status_code == 200

    def test_empty_reason_returns_400(self, client: TestClient) -> None:
        """Empty X-Change-Reason header returns HTTP 400."""
        response = client.post(
            "/api/documents",
            headers={"X-User-Id": "user-1", "X-Change-Reason": ""},
        )
        assert response.status_code == 400

    def test_whitespace_only_reason_returns_400(self, client: TestClient) -> None:
        """Whitespace-only X-Change-Reason header returns HTTP 400."""
        response = client.post(
            "/api/documents",
            headers={"X-User-Id": "user-1", "X-Change-Reason": "   "},
        )
        assert response.status_code == 400

    def test_get_without_reason_succeeds(self, client: TestClient) -> None:
        """GET requests do not require X-Change-Reason."""
        response = client.get("/api/documents")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests: Exempt endpoints
# ---------------------------------------------------------------------------


class TestExemptEndpoints:
    """Tests for endpoints exempt from X-Change-Reason requirement."""

    def test_health_endpoint_exempt(self, client: TestClient) -> None:
        """Health endpoint does not require X-Change-Reason."""
        response = client.get("/health")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests: Configurable enforcement
# ---------------------------------------------------------------------------


class TestConfigurableEnforcement:
    """Tests for the require_reason_for_mutations configuration."""

    def test_disabled_enforcement_allows_post_without_reason(
        self, client_no_reason_required: TestClient
    ) -> None:
        """POST without reason succeeds when enforcement is disabled."""
        response = client_no_reason_required.post(
            "/api/documents", headers={"X-User-Id": "user-1"}
        )
        assert response.status_code == 200

    def test_disabled_enforcement_still_injects_context(
        self, client_no_reason_required: TestClient
    ) -> None:
        """Audit context is still injected when enforcement is disabled."""
        response = client_no_reason_required.get(
            "/api/documents", headers={"X-User-Id": "user-99"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["audit_user_id"] == "user-99"
        assert data["audit_timestamp"] is not None


# ---------------------------------------------------------------------------
# Tests: Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_extract_user_id_from_header(self) -> None:
        """_extract_user_id reads X-User-Id header."""
        from starlette.testclient import TestClient as _TC
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/test")
        async def _test(request: Request) -> dict:
            return {"user_id": _extract_user_id(request)}

        tc = _TC(app)
        resp = tc.get("/test", headers={"X-User-Id": "abc"})
        assert resp.json()["user_id"] == "abc"

    def test_extract_user_id_returns_none(self) -> None:
        """_extract_user_id returns None when header missing."""
        from starlette.testclient import TestClient as _TC
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/test")
        async def _test(request: Request) -> dict:
            return {"user_id": _extract_user_id(request)}

        tc = _TC(app)
        resp = tc.get("/test")
        assert resp.json()["user_id"] is None
