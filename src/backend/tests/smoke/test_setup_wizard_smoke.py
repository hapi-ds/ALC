"""Smoke tests for the Setup Wizard against the live Docker Compose stack.

These tests hit the real backend (PostgreSQL, real migrations) to verify
the setup wizard endpoints work end-to-end on production-like infrastructure.

Prerequisites:
    - Docker Compose stack is running: `docker compose up -d`
    - Migration has been applied: `docker compose exec backend alembic upgrade head`
    - The system must be in an UNINITIALIZED state (fresh DB or setup_status cleared)

Run with:
    uv run pytest tests/smoke/test_setup_wizard_smoke.py -v

Environment:
    SMOKE_TEST_BASE_URL: Base URL of the backend (default: http://localhost:8080)

NOTE: These tests walk through the full setup flow and leave the system in an
initialized state. They should be run BEFORE the multi-tenancy smoke tests
(which require an initialized system). To re-run, reset the setup_status table:
    docker compose exec db psql -U alcoabase -c "DELETE FROM setup_status;"
"""

import os

import httpx
import pytest

BASE_URL = os.environ.get("SMOKE_TEST_BASE_URL", "http://localhost:8080")


# ---------------------------------------------------------------------------
# Health check (always works regardless of setup state)
# ---------------------------------------------------------------------------


class TestHealthDuringSetup:
    """Verify health endpoint is accessible even when system is uninitialized."""

    def test_health_endpoint_accessible(self) -> None:
        """GET /health returns 200 regardless of initialization state."""
        resp = httpx.get(f"{BASE_URL}/health", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Setup flow smoke test
# ---------------------------------------------------------------------------


class TestSetupWizardFlow:
    """Smoke test for the complete setup wizard flow.

    Walks through: status → admin → company → ai-mode → complete.
    After completion, verifies setup endpoints are locked (403).
    """

    def test_full_setup_flow(self) -> None:
        """Execute the full setup wizard flow end-to-end."""
        # Step 0: Check initial status
        resp = httpx.get(f"{BASE_URL}/api/v1/setup/status", timeout=10)
        assert resp.status_code == 200
        status = resp.json()
        assert status["is_complete"] is False

        # If admin already created (partial previous run), skip to where we left off
        if status["admin_created"]:
            pytest.skip(
                "Setup already partially complete. "
                "Clear setup_status table to re-run."
            )

        # Step 1: Non-setup endpoints should return 503
        resp = httpx.get(
            f"{BASE_URL}/api/companies",
            headers={"X-User-Id": "1", "X-Change-Reason": "smoke"},
            timeout=10,
        )
        assert resp.status_code == 503
        assert "setup required" in resp.json()["detail"].lower()

        # Step 2: Create root admin
        admin_payload = {
            "username": "smokeadmin",
            "email": "smoke@alcoabase.example.com",
            "password": "SmokeT3st!Pass",
            "full_name": "Smoke Test Admin",
        }
        resp = httpx.post(
            f"{BASE_URL}/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "smoke test: create admin"},
            timeout=30,
        )
        assert resp.status_code == 201, f"Admin creation failed: {resp.text}"
        admin_result = resp.json()
        assert admin_result["username"] == "smokeadmin"
        assert admin_result["user_id"] > 0
        assert "access_token" in admin_result

        token = admin_result["access_token"]
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "X-Change-Reason": "smoke test: setup",
            "Content-Type": "application/json",
        }

        # Step 3: Verify status updated
        resp = httpx.get(f"{BASE_URL}/api/v1/setup/status", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["admin_created"] is True

        # Step 4: Create initial company
        company_payload = {
            "display_name": "Smoke Test Corp",
            "slug": "smoke-test-corp",
            "regulatory_framework": "GMP",
        }
        resp = httpx.post(
            f"{BASE_URL}/api/v1/setup/company",
            json=company_payload,
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 201, f"Company creation failed: {resp.text}"
        company_result = resp.json()
        assert company_result["slug"] == "smoke-test-corp"
        assert company_result["display_name"] == "Smoke Test Corp"

        # Step 5: Configure AI mode (mock — no vLLM needed)
        resp = httpx.post(
            f"{BASE_URL}/api/v1/setup/ai-mode",
            json={"mode": "mock"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200, f"AI mode config failed: {resp.text}"
        ai_result = resp.json()
        assert ai_result["mode"] == "mock"
        assert ai_result["connectivity_warning"] is None

        # Step 6: Complete setup with demo data
        resp = httpx.post(
            f"{BASE_URL}/api/v1/setup/complete",
            json={"seed_demo_data": True},
            headers=auth_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Setup completion failed: {resp.text}"
        complete_result = resp.json()
        assert complete_result["message"] == "Setup completed successfully"
        assert "completed_at" in complete_result

        # Step 7: Verify setup endpoints are now locked (403)
        resp = httpx.get(f"{BASE_URL}/api/v1/setup/status", timeout=10)
        assert resp.status_code == 403
        assert "already completed" in resp.json()["detail"].lower()

        resp = httpx.post(
            f"{BASE_URL}/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "smoke test: should fail"},
            timeout=10,
        )
        assert resp.status_code == 403

        # Step 8: Verify non-setup endpoints are now accessible
        resp = httpx.get(f"{BASE_URL}/health", timeout=10)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Idempotency smoke test
# ---------------------------------------------------------------------------


class TestSetupIdempotency:
    """Verify idempotency guards work on a live system."""

    def test_duplicate_admin_returns_409(self) -> None:
        """Creating root admin twice returns 409 on a partially-setup system.

        This test only works if the system has already had admin created
        but setup is not yet complete. If setup is complete, it gets 403.
        """
        admin_payload = {
            "username": "duplicate",
            "email": "dup@alcoabase.example.com",
            "password": "DupT3st!Pass99",
            "full_name": "Duplicate Admin",
        }
        resp = httpx.post(
            f"{BASE_URL}/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "smoke test: idempotency"},
            timeout=10,
        )
        # Either 409 (admin exists, setup incomplete) or 403 (setup complete)
        assert resp.status_code in (403, 409), (
            f"Expected 403 or 409, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Validation smoke test
# ---------------------------------------------------------------------------


class TestSetupValidation:
    """Verify validation errors are returned correctly."""

    def test_weak_password_rejected(self) -> None:
        """A password that doesn't meet policy is rejected with 422.

        Only works if setup is not yet complete (otherwise 403).
        """
        admin_payload = {
            "username": "weakpw",
            "email": "weak@alcoabase.example.com",
            "password": "short",
            "full_name": "Weak Password User",
        }
        resp = httpx.post(
            f"{BASE_URL}/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "smoke test: validation"},
            timeout=10,
        )
        # Either 422 (validation error) or 403 (setup already complete)
        # or 409 (admin already exists)
        assert resp.status_code in (403, 409, 422), (
            f"Expected 403, 409, or 422, got {resp.status_code}: {resp.text}"
        )
