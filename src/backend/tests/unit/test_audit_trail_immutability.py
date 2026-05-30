"""Unit tests for audit trail immutability enforcement.

Tests that PUT, PATCH, and DELETE requests to /api/audit-trail endpoints
always return HTTP 403 with the ALCOA+ immutability message, regardless
of the requesting user's role or permissions.

Requirements: 8.1, 8.2, 8.4
"""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from alcoabase.api.audit_trail import router as audit_trail_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Create a test client with the audit trail router mounted.

    No dependency overrides needed since the immutability handlers
    do not use any dependencies (they reject unconditionally).
    """
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(audit_trail_router)
    app.include_router(api)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Immutability enforcement tests
# ---------------------------------------------------------------------------

IMMUTABILITY_MESSAGE = "Audit records are immutable per ALCOA+ and CFR 21 Part 11"


class TestImmutabilityEnforcement:
    """Tests for PUT, PATCH, DELETE blocking on audit trail endpoints."""

    def test_put_root_returns_403(self, client: TestClient) -> None:
        """PUT /api/audit-trail returns HTTP 403 with immutability message."""
        response = client.put("/api/audit-trail/")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_patch_root_returns_403(self, client: TestClient) -> None:
        """PATCH /api/audit-trail returns HTTP 403 with immutability message."""
        response = client.patch("/api/audit-trail/")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_delete_root_returns_403(self, client: TestClient) -> None:
        """DELETE /api/audit-trail returns HTTP 403 with immutability message."""
        response = client.delete("/api/audit-trail/")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_put_subpath_returns_403(self, client: TestClient) -> None:
        """PUT /api/audit-trail/{path} returns HTTP 403."""
        response = client.put("/api/audit-trail/some/nested/path")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_patch_subpath_returns_403(self, client: TestClient) -> None:
        """PATCH /api/audit-trail/{path} returns HTTP 403."""
        response = client.patch("/api/audit-trail/documents/1/42")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_delete_subpath_returns_403(self, client: TestClient) -> None:
        """DELETE /api/audit-trail/{path} returns HTTP 403."""
        response = client.delete("/api/audit-trail/export/some-job-id")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_put_with_body_returns_403(self, client: TestClient) -> None:
        """PUT with a JSON body still returns HTTP 403."""
        response = client.put(
            "/api/audit-trail/documents/1/42",
            json={"change_reason": "Attempted modification"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_delete_with_auth_headers_returns_403(self, client: TestClient) -> None:
        """DELETE with auth headers still returns HTTP 403 (no role bypass)."""
        response = client.delete(
            "/api/audit-trail/1",
            headers={
                "Authorization": "Bearer admin-token",
                "X-User-Id": "1",
                "X-Company-Id": "1",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_response_body_format(self, client: TestClient) -> None:
        """Response body is a JSON object with 'detail' key."""
        response = client.put("/api/audit-trail/")
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)
        assert body["detail"] == IMMUTABILITY_MESSAGE
