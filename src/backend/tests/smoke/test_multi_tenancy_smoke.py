"""Smoke tests for multi-tenancy against the live Docker Compose stack.

These tests hit the real backend (PostgreSQL, real migrations) to verify
the multi-tenancy endpoints work end-to-end on production-like infrastructure.

Prerequisites:
    - Docker Compose stack is running: `docker compose up -d`
    - Migration has been applied: `docker compose exec backend alembic upgrade head`
    - A test user with id=1 exists in the database

Run with:
    uv run pytest tests/smoke/test_multi_tenancy_smoke.py -v --timeout=30

Environment:
    SMOKE_TEST_BASE_URL: Base URL of the backend (default: http://localhost:8080)
"""

import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("SMOKE_TEST_BASE_URL", "http://localhost:8080")
HEADERS = {
    "X-User-Id": "1",
    "X-Change-Reason": "smoke test",
    "Content-Type": "application/json",
}


def _unique_slug() -> str:
    """Generate a unique slug for each test run to avoid conflicts."""
    return f"smoke-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def slug() -> str:
    """Provide a unique company slug per test."""
    return _unique_slug()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Verify the backend is reachable before running other tests."""

    def test_health_endpoint(self) -> None:
        """GET /health returns 200."""
        resp = httpx.get(f"{BASE_URL}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------


class TestCompanyCRUD:
    """Smoke tests for company creation, retrieval, and lifecycle."""

    def test_create_and_get_company(self, slug: str) -> None:
        """Create a company and retrieve it by slug."""
        payload = {
            "slug": slug,
            "display_name": "Smoke Test Corp",
            "regulatory_framework": "GMP",
            "audit_config": {"retention_years": 7},
        }

        # Create
        resp = httpx.post(
            f"{BASE_URL}/api/companies", json=payload, headers=HEADERS, timeout=10
        )
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        data = resp.json()
        assert data["slug"] == slug
        assert data["is_active"] is True
        assert data["regulatory_framework"] == "GMP"

        # Get
        resp = httpx.get(
            f"{BASE_URL}/api/companies/{slug}", headers=HEADERS, timeout=10
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == slug

    def test_duplicate_slug_returns_409(self, slug: str) -> None:
        """Creating two companies with the same slug returns 409."""
        payload = {
            "slug": slug,
            "display_name": "First",
            "regulatory_framework": "ISO_13485",
        }
        resp1 = httpx.post(
            f"{BASE_URL}/api/companies", json=payload, headers=HEADERS, timeout=10
        )
        assert resp1.status_code == 201

        payload["display_name"] = "Second"
        resp2 = httpx.post(
            f"{BASE_URL}/api/companies", json=payload, headers=HEADERS, timeout=10
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]

    def test_deactivate_and_reactivate(self, slug: str) -> None:
        """Deactivate a company, then reactivate it."""
        # Create
        payload = {
            "slug": slug,
            "display_name": "Lifecycle Co",
            "regulatory_framework": "GDP",
        }
        httpx.post(
            f"{BASE_URL}/api/companies", json=payload, headers=HEADERS, timeout=10
        )

        # Deactivate
        resp = httpx.post(
            f"{BASE_URL}/api/companies/{slug}/deactivate",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # Deactivate again → 409
        resp = httpx.post(
            f"{BASE_URL}/api/companies/{slug}/deactivate",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 409

        # Reactivate
        resp = httpx.post(
            f"{BASE_URL}/api/companies/{slug}/reactivate",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    def test_list_companies(self, slug: str) -> None:
        """List companies includes the newly created one."""
        payload = {
            "slug": slug,
            "display_name": "Listed Co",
            "regulatory_framework": "ISO_9001",
        }
        httpx.post(
            f"{BASE_URL}/api/companies", json=payload, headers=HEADERS, timeout=10
        )

        resp = httpx.get(
            f"{BASE_URL}/api/companies", headers=HEADERS, timeout=10
        )
        assert resp.status_code == 200
        slugs = [c["slug"] for c in resp.json()]
        assert slug in slugs


# ---------------------------------------------------------------------------
# Membership management
# ---------------------------------------------------------------------------


class TestMembership:
    """Smoke tests for membership CRUD."""

    def test_add_and_list_members(self, slug: str) -> None:
        """Add a member and verify they appear in the member list."""
        # Create company
        httpx.post(
            f"{BASE_URL}/api/companies",
            json={
                "slug": slug,
                "display_name": "Member Co",
                "regulatory_framework": "ISO_13485",
            },
            headers=HEADERS,
            timeout=10,
        )

        # Add member
        resp = httpx.post(
            f"{BASE_URL}/api/companies/{slug}/members",
            json={"user_id": 1, "role": "admin"},
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "admin"

        # List members
        resp = httpx.get(
            f"{BASE_URL}/api/companies/{slug}/members",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 1
        assert any(m["user_id"] == 1 for m in members)

    def test_revoke_membership(self, slug: str) -> None:
        """Revoke a membership and verify revoked_at is set."""
        # Create company + add member
        httpx.post(
            f"{BASE_URL}/api/companies",
            json={
                "slug": slug,
                "display_name": "Revoke Co",
                "regulatory_framework": "GMP",
            },
            headers=HEADERS,
            timeout=10,
        )
        httpx.post(
            f"{BASE_URL}/api/companies/{slug}/members",
            json={"user_id": 1, "role": "member"},
            headers=HEADERS,
            timeout=10,
        )

        # Revoke
        resp = httpx.delete(
            f"{BASE_URL}/api/companies/{slug}/members/1",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["revoked_at"] is not None

        # Revoke again → 409
        resp = httpx.delete(
            f"{BASE_URL}/api/companies/{slug}/members/1",
            headers=HEADERS,
            timeout=10,
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Tenant context resolution
# ---------------------------------------------------------------------------


class TestTenantContext:
    """Smoke tests for tenant context resolution via X-Company-Id header."""

    def test_single_membership_auto_resolves(self, slug: str) -> None:
        """User with one membership doesn't need X-Company-Id header."""
        # Create company + add member
        httpx.post(
            f"{BASE_URL}/api/companies",
            json={
                "slug": slug,
                "display_name": "Auto Co",
                "regulatory_framework": "ISO_13485",
            },
            headers=HEADERS,
            timeout=10,
        )
        httpx.post(
            f"{BASE_URL}/api/companies/{slug}/members",
            json={"user_id": 1, "role": "admin"},
            headers=HEADERS,
            timeout=10,
        )

        # Access a tenant-scoped endpoint without X-Company-Id
        # (documents endpoint uses get_tenant_context)
        resp = httpx.get(
            f"{BASE_URL}/api/documents",
            headers={"X-User-Id": "1", "X-Change-Reason": "smoke"},
            timeout=10,
        )
        # Should succeed (200) since user has exactly one active membership
        assert resp.status_code == 200

    def test_deactivated_company_returns_403(self, slug: str) -> None:
        """Accessing a deactivated company's tenant context returns 403."""
        # Create company + add member
        httpx.post(
            f"{BASE_URL}/api/companies",
            json={
                "slug": slug,
                "display_name": "Deact Co",
                "regulatory_framework": "GMP",
            },
            headers=HEADERS,
            timeout=10,
        )
        resp = httpx.post(
            f"{BASE_URL}/api/companies/{slug}/members",
            json={"user_id": 1, "role": "admin"},
            headers=HEADERS,
            timeout=10,
        )
        company_id = resp.json()["company_id"]

        # Deactivate
        httpx.post(
            f"{BASE_URL}/api/companies/{slug}/deactivate",
            headers=HEADERS,
            timeout=10,
        )

        # Try to access tenant-scoped endpoint → 403
        resp = httpx.get(
            f"{BASE_URL}/api/documents",
            headers={
                "X-User-Id": "1",
                "X-Company-Id": str(company_id),
                "X-Change-Reason": "smoke",
            },
            timeout=10,
        )
        assert resp.status_code == 403
        assert "inactive" in resp.json()["detail"].lower()
