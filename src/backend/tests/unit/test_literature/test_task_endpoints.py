"""Unit tests for literature async task endpoints.

Tests cover:
- GET /api/literature/tasks/{task_id}: status polling, state mapping, 404 handling
- DELETE /api/literature/tasks/{task_id}: cancellation, partial result retention
- Role enforcement via TenantContext dependency

References:
    - Requirements 15.2, 15.4, 15.5
    - Task 15.3: Implement async task endpoints
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a test TenantContext with member role."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="member",
    )


@pytest_asyncio.fixture
async def client(tenant_context: TenantContext) -> AsyncClient:
    """Create an httpx AsyncClient with overridden tenant dependency."""

    async def _override_get_tenant_context():
        return tenant_context

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_async_result(
    task_id: str,
    state: str = "PENDING",
    result: object = None,
    info: object = None,
) -> MagicMock:
    """Create a mock Celery AsyncResult with the given state and info."""
    mock = MagicMock()
    mock.id = task_id
    mock.state = state
    mock.result = result
    mock.info = info
    return mock


def _mock_backend_with_record() -> MagicMock:
    """Create a mock backend that reports the task exists."""
    backend = MagicMock()
    backend.get_task_meta.return_value = {
        "status": "STARTED",
        "result": {"progress_percent": 10},
    }
    return backend


def _mock_backend_no_record() -> MagicMock:
    """Create a mock backend that reports no task record (unknown task)."""
    backend = MagicMock()
    backend.get_task_meta.return_value = {"status": "PENDING", "result": None}
    return backend


# ---------------------------------------------------------------------------
# Tests: GET /api/literature/tasks/{task_id}
# ---------------------------------------------------------------------------


class TestGetTaskStatus:
    """Tests for GET /api/literature/tasks/{task_id}."""

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_task(self, client: AsyncClient) -> None:
        """Return 404 when task_id does not exist in the backend."""
        mock_result = _mock_async_result("unknown-id", state="PENDING")

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ), patch(
            "alcoabase.api.literature_router.celery_app",
        ) as mock_celery:
            mock_celery.backend = _mock_backend_no_record()
            resp = await client.get("/api/literature/tasks/unknown-id")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_queued_status_for_pending_task(
        self, client: AsyncClient
    ) -> None:
        """Return queued status for a task known to the backend in PENDING state."""
        # info has progress data indicating the task was actually queued
        mock_result = _mock_async_result(
            "task-123", state="PENDING", info={"progress_percent": 0}
        )

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ), patch(
            "alcoabase.api.literature_router.celery_app",
        ) as mock_celery:
            # Backend reports it exists (result is not None)
            mock_celery.backend = MagicMock()
            mock_celery.backend.get_task_meta.return_value = {
                "status": "PENDING",
                "result": {"progress_percent": 0},
            }
            resp = await client.get("/api/literature/tasks/task-123")

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-123"
        assert data["status"] == "queued"
        assert data["progress_percent"] == 0

    @pytest.mark.asyncio
    async def test_returns_running_status_with_progress(
        self, client: AsyncClient
    ) -> None:
        """Return running status with progress for STARTED state."""
        mock_result = _mock_async_result(
            "task-456", state="STARTED", info={"progress_percent": 45}
        )

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ):
            resp = await client.get("/api/literature/tasks/task-456")

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-456"
        assert data["status"] == "running"
        assert data["progress_percent"] == 45

    @pytest.mark.asyncio
    async def test_returns_completed_status_with_results(
        self, client: AsyncClient
    ) -> None:
        """Return completed status with full results for SUCCESS state."""
        search_response_data = {
            "results": [],
            "total_count": 0,
            "partial_results": None,
            "query_id": "q-789",
        }
        mock_result = _mock_async_result(
            "task-789", state="SUCCESS", result=search_response_data
        )

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ):
            resp = await client.get("/api/literature/tasks/task-789")

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-789"
        assert data["status"] == "completed"
        assert data["progress_percent"] == 100
        assert data["partial_results"] is not None
        assert data["partial_results"]["query_id"] == "q-789"

    @pytest.mark.asyncio
    async def test_returns_failed_status_with_error(
        self, client: AsyncClient
    ) -> None:
        """Return failed status with error message for FAILURE state."""
        mock_result = _mock_async_result(
            "task-fail", state="FAILURE", info=Exception("Search timed out")
        )

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ):
            resp = await client.get("/api/literature/tasks/task-fail")

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-fail"
        assert data["status"] == "failed"
        assert "Search timed out" in data["error_message"]

    @pytest.mark.asyncio
    async def test_maps_revoked_to_failed(self, client: AsyncClient) -> None:
        """Map REVOKED Celery state to failed TaskStatus."""
        mock_result = _mock_async_result(
            "task-revoked",
            state="REVOKED",
            info={"error_message": "Task cancelled"},
        )

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ):
            resp = await client.get("/api/literature/tasks/task-revoked")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert "cancelled" in data["error_message"].lower()


# ---------------------------------------------------------------------------
# Tests: DELETE /api/literature/tasks/{task_id}
# ---------------------------------------------------------------------------


class TestCancelTask:
    """Tests for DELETE /api/literature/tasks/{task_id}."""

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_task(self, client: AsyncClient) -> None:
        """Return 404 when cancelling a non-existent task."""
        mock_result = _mock_async_result("unknown-id", state="PENDING")

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ), patch(
            "alcoabase.api.literature_router.celery_app",
        ) as mock_celery:
            mock_celery.backend = _mock_backend_no_record()
            resp = await client.delete(
                "/api/literature/tasks/unknown-id",
                headers={"X-Change-Reason": "Cancel test"},
            )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cancels_running_task_and_returns_partial_results(
        self, client: AsyncClient
    ) -> None:
        """Cancel a running task and return partial results."""
        partial = {
            "results": [],
            "total_count": 5,
            "partial_results": {
                "timed_out_sources": ["arxiv"],
                "errored_sources": [],
                "unavailable_sources": [],
            },
            "query_id": "q-cancel",
        }
        mock_result = _mock_async_result(
            "task-running",
            state="STARTED",
            info={"progress_percent": 60, "partial_results": partial},
        )

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ), patch(
            "alcoabase.api.literature_router.celery_app",
        ) as mock_celery:
            mock_celery.control = MagicMock()
            resp = await client.delete(
                "/api/literature/tasks/task-running",
                headers={"X-Change-Reason": "No longer needed"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-running"
        assert data["status"] == "failed"
        assert data["error_message"] == "Task cancelled by user."
        assert data["progress_percent"] == 60
        assert data["partial_results"] is not None

        # Verify revoke was called
        mock_celery.control.revoke.assert_called_once_with(
            "task-running", terminate=True, signal="SIGTERM"
        )

    @pytest.mark.asyncio
    async def test_cancels_queued_task(self, client: AsyncClient) -> None:
        """Cancel a queued (not yet started) task."""
        mock_result = _mock_async_result(
            "task-queued",
            state="PENDING",
            info={"progress_percent": 0},
        )

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ), patch(
            "alcoabase.api.literature_router.celery_app",
        ) as mock_celery:
            # Backend shows it's a known task (has result data)
            mock_celery.backend = MagicMock()
            mock_celery.backend.get_task_meta.return_value = {
                "status": "PENDING",
                "result": {"progress_percent": 0},
            }
            mock_celery.control = MagicMock()
            resp = await client.delete(
                "/api/literature/tasks/task-queued",
                headers={"X-Change-Reason": "Changed my mind"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "task-queued"
        assert data["status"] == "failed"
        assert data["error_message"] == "Task cancelled by user."
        mock_celery.control.revoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_requires_change_reason_header(
        self, client: AsyncClient
    ) -> None:
        """DELETE without X-Change-Reason header returns 400."""
        # The AuditMiddleware should reject this before reaching the endpoint
        # but also the endpoint itself uses Header(...) making it required
        mock_result = _mock_async_result("task-123", state="STARTED")

        with patch(
            "alcoabase.api.literature_router.AsyncResult",
            return_value=mock_result,
        ):
            resp = await client.delete("/api/literature/tasks/task-123")

        # Either 400 from AuditMiddleware or 422 from FastAPI Header validation
        assert resp.status_code in (400, 422)
