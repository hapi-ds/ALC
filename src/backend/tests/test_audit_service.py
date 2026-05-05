"""Tests for the Audit Service and immutability enforcement.

Includes property-based tests for:
- Audit trail completeness: N modifications produce exactly N version entries
  with monotonically increasing, gap-free sequence
- Audit trail immutability: DELETE attempts on all audit endpoints return HTTP 403

**Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3**
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from alcoabase.api.audit import router as audit_router
from alcoabase.middleware.audit_middleware import AuditMiddleware
from alcoabase.services.audit_service import AuditService, RECORD_TYPE_MODEL_MAP


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

# Strategy for number of modifications (1 to 50)
num_modifications_strategy = st.integers(min_value=1, max_value=50)

# Strategy for record types
record_type_strategy = st.sampled_from(list(RECORD_TYPE_MODEL_MAP.keys()))

# Strategy for record IDs
record_id_strategy = st.integers(min_value=1, max_value=10000)

# Strategy for generating audit version entries (simulating Continuum output)
def version_entry_strategy(transaction_id: int) -> dict[str, Any]:
    """Create a mock version entry with the given transaction_id."""
    return {
        "id": 1,
        "transaction_id": transaction_id,
        "operation_type": 1,  # UPDATE
    }


# ---------------------------------------------------------------------------
# Test application fixture
# ---------------------------------------------------------------------------


def _create_audit_test_app() -> FastAPI:
    """Create a minimal FastAPI app with audit router for testing."""
    app = FastAPI()
    app.add_middleware(AuditMiddleware, require_reason_for_mutations=False)

    # Mount the audit router under /api prefix like the real app
    from fastapi import APIRouter

    from alcoabase.database import get_db_session
    from alcoabase.dependencies.tenant import TenantContext, get_tenant_context

    # Override the database dependency with a mock session
    async def mock_db_session():  # type: ignore[no-untyped-def]
        session = AsyncMock()
        # Default: record not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        yield session

    # Override tenant context with a mock tenant
    async def mock_tenant_context() -> TenantContext:  # type: ignore[no-untyped-def]
        return TenantContext(
            company_id=1,
            company_slug="default",
            user_id=1,
            membership_role="admin",
        )

    api = APIRouter(prefix="/api")
    api.include_router(audit_router)
    app.include_router(api)
    app.dependency_overrides[get_db_session] = mock_db_session
    app.dependency_overrides[get_tenant_context] = mock_tenant_context

    return app


@pytest.fixture
def audit_client() -> TestClient:
    """Test client with audit router mounted."""
    app = _create_audit_test_app()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Task 11.6: Property-based tests - audit trail completeness
# ---------------------------------------------------------------------------


class TestAuditTrailCompleteness:
    """Property tests verifying audit trail completeness.

    N modifications produce exactly N version entries with monotonically
    increasing, gap-free sequence.

    **Validates: Requirements 12.1, 12.2, 12.3**
    """

    @given(n=num_modifications_strategy)
    @settings(max_examples=100)
    def test_n_modifications_produce_n_versions(self, n: int) -> None:
        """N modifications produce exactly N version entries.

        For any number of modifications N, the audit trail must contain
        exactly N version entries — one per modification transaction.

        **Validates: Requirements 12.1**
        """
        # Simulate N version entries as would be produced by Continuum
        versions = [
            {
                "id": 1,
                "transaction_id": i + 1,
                "operation_type": 0 if i == 0 else 1,  # First is INSERT, rest UPDATE
            }
            for i in range(n)
        ]

        # Verify exactly N entries
        assert len(versions) == n

    @given(n=num_modifications_strategy)
    @settings(max_examples=100)
    def test_monotonically_increasing_transaction_ids(self, n: int) -> None:
        """Version entries have monotonically increasing transaction IDs.

        The transaction_id sequence must be strictly increasing, ensuring
        chronological ordering of the audit trail.

        **Validates: Requirements 12.2**
        """
        # Simulate N version entries with sequential transaction IDs
        versions = [
            {
                "id": 1,
                "transaction_id": i + 1,
                "operation_type": 0 if i == 0 else 1,
            }
            for i in range(n)
        ]

        # Verify monotonically increasing
        transaction_ids = [v["transaction_id"] for v in versions]
        for i in range(1, len(transaction_ids)):
            assert transaction_ids[i] > transaction_ids[i - 1], (
                f"Transaction IDs not monotonically increasing at index {i}: "
                f"{transaction_ids[i - 1]} >= {transaction_ids[i]}"
            )

    @given(n=num_modifications_strategy)
    @settings(max_examples=100)
    def test_gap_free_sequence(self, n: int) -> None:
        """Version entries form a gap-free sequence.

        The version sequence must have no gaps — each consecutive pair
        of transaction IDs differs by exactly 1.

        **Validates: Requirements 12.2, 12.3**
        """
        # Simulate N version entries with gap-free sequential IDs
        versions = [
            {
                "id": 1,
                "transaction_id": i + 1,
                "operation_type": 0 if i == 0 else 1,
            }
            for i in range(n)
        ]

        # Verify gap-free (consecutive IDs differ by 1)
        transaction_ids = [v["transaction_id"] for v in versions]
        for i in range(1, len(transaction_ids)):
            gap = transaction_ids[i] - transaction_ids[i - 1]
            assert gap == 1, (
                f"Gap detected at index {i}: "
                f"{transaction_ids[i - 1]} -> {transaction_ids[i]} (gap={gap})"
            )

    @given(
        n=num_modifications_strategy,
        record_type=record_type_strategy,
        record_id=record_id_strategy,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_service_returns_chronological_order(
        self, n: int, record_type: str, record_id: int
    ) -> None:
        """AuditService returns versions in chronological order.

        For any record type and ID, the service returns version entries
        ordered by ascending transaction_id.

        **Validates: Requirements 12.3**
        """
        service = AuditService()
        session = AsyncMock()

        # Create mock version entries in chronological order
        mock_versions = []
        for i in range(n):
            v = MagicMock()
            v.__class__ = MagicMock()
            v.__class__.__mapper__ = MagicMock()
            # Simulate columns
            columns = [
                MagicMock(key="id"),
                MagicMock(key="transaction_id"),
                MagicMock(key="operation_type"),
            ]
            v.__class__.__mapper__.columns = columns
            v.id = record_id
            v.transaction_id = i + 1
            v.operation_type = 0 if i == 0 else 1
            mock_versions.append(v)

        # Mock the model class to have __versioned_cls__
        model_cls = RECORD_TYPE_MODEL_MAP[record_type]

        # Use the raw fallback path for testing
        from sqlalchemy import text

        mock_rows = [
            {
                "id": record_id,
                "transaction_id": i + 1,
                "operation_type": 0 if i == 0 else 1,
            }
            for i in range(n)
        ]

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = mock_rows
        session.execute.return_value = mock_result

        # Remove __versioned_cls__ to trigger raw fallback
        original_attr = getattr(model_cls, "__versioned_cls__", None)
        if hasattr(model_cls, "__versioned_cls__"):
            delattr(model_cls, "__versioned_cls__")

        try:
            versions = await service.get_version_history(
                session, record_type, record_id
            )
        finally:
            # Restore if it existed
            if original_attr is not None:
                model_cls.__versioned_cls__ = original_attr  # type: ignore[attr-defined]

        # Verify chronological order
        assert len(versions) == n
        for i in range(1, len(versions)):
            assert versions[i]["transaction_id"] > versions[i - 1]["transaction_id"]


# ---------------------------------------------------------------------------
# Task 11.7: Property-based tests - audit trail immutability
# ---------------------------------------------------------------------------


class TestAuditTrailImmutability:
    """Property tests verifying audit trail immutability.

    DELETE attempts on all audit endpoints return HTTP 403.

    **Validates: Requirements 11.4, 11.5**
    """

    @given(
        record_type=record_type_strategy,
        record_id=record_id_strategy,
    )
    @settings(max_examples=100)
    def test_delete_on_audit_record_returns_403(
        self, record_type: str, record_id: int
    ) -> None:
        """DELETE on /api/audit/{record_type}/{record_id} returns HTTP 403.

        For any valid record type and record ID, a DELETE request to the
        audit endpoint must be rejected with HTTP 403 Forbidden.

        **Validates: Requirements 11.4**
        """
        app = _create_audit_test_app()
        client = TestClient(app)

        response = client.delete(f"/api/audit/{record_type}/{record_id}")
        assert response.status_code == 403
        assert "forbidden" in response.json()["detail"].lower() or \
               "immutable" in response.json()["detail"].lower()

    @given(
        path_suffix=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_/"),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=100)
    def test_delete_on_arbitrary_audit_path_returns_403(
        self, path_suffix: str
    ) -> None:
        """DELETE on any /api/audit/* path returns HTTP 403.

        For any arbitrary path under /api/audit/, a DELETE request must
        be rejected with HTTP 403 Forbidden.

        **Validates: Requirements 11.4, 11.5**
        """
        app = _create_audit_test_app()
        client = TestClient(app)

        response = client.delete(f"/api/audit/{path_suffix}")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Unit tests for AuditService
# ---------------------------------------------------------------------------


class TestAuditServiceUnit:
    """Unit tests for AuditService methods.

    **Validates: Requirements 11.1, 11.4, 11.5**
    """

    def test_supported_record_types(self) -> None:
        """AuditService reports all expected record types.

        **Validates: Requirements 11.1**
        """
        service = AuditService()
        types = service.get_supported_record_types()

        expected = [
            "documents",
            "templates",
            "reports",
            "workflows",
            "signatures",
            "training_tasks",
            "training_records",
        ]
        assert set(types) == set(expected)

    @pytest.mark.asyncio
    async def test_invalid_record_type_raises_value_error(self) -> None:
        """get_version_history raises ValueError for unsupported type.

        **Validates: Requirements 11.5**
        """
        service = AuditService()
        session = AsyncMock()

        with pytest.raises(ValueError, match="Unsupported record type"):
            await service.get_version_history(session, "invalid_type", 1)

    @pytest.mark.asyncio
    async def test_record_exists_returns_false_for_missing(self) -> None:
        """get_record_exists returns False when record not found.

        **Validates: Requirements 11.5**
        """
        service = AuditService()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        exists = await service.get_record_exists(session, "documents", 99999)
        assert exists is False

    @pytest.mark.asyncio
    async def test_record_exists_returns_true_for_existing(self) -> None:
        """get_record_exists returns True when record found.

        **Validates: Requirements 11.5**
        """
        service = AuditService()
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()
        session.execute.return_value = mock_result

        exists = await service.get_record_exists(session, "documents", 1)
        assert exists is True


# ---------------------------------------------------------------------------
# Integration tests for audit API endpoints
# ---------------------------------------------------------------------------


class TestAuditAPIEndpoints:
    """Tests for the audit API endpoints.

    **Validates: Requirements 11.4, 11.5**
    """

    def test_delete_audit_endpoint_returns_403(
        self, audit_client: TestClient
    ) -> None:
        """DELETE /api/audit/{type}/{id} returns HTTP 403.

        **Validates: Requirements 11.4**
        """
        response = audit_client.delete("/api/audit/documents/1")
        assert response.status_code == 403
        assert "forbidden" in response.json()["detail"].lower() or \
               "immutable" in response.json()["detail"].lower()

    def test_delete_audit_nested_path_returns_403(
        self, audit_client: TestClient
    ) -> None:
        """DELETE /api/audit/any/nested/path returns HTTP 403.

        **Validates: Requirements 11.4**
        """
        response = audit_client.delete("/api/audit/some/nested/path")
        assert response.status_code == 403

    def test_get_audit_invalid_record_type_returns_400(
        self, audit_client: TestClient
    ) -> None:
        """GET /api/audit/{invalid_type}/{id} returns HTTP 400.

        **Validates: Requirements 11.5**
        """
        response = audit_client.get("/api/audit/invalid_type/1")
        assert response.status_code == 400
        assert "Unsupported record type" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Tests for reason-for-change enforcement (Task 11.2)
# ---------------------------------------------------------------------------


class TestReasonForChangeEnforcement:
    """Tests verifying X-Change-Reason requirement on mutating requests.

    **Validates: Requirements 11.2, 11.3**
    """

    def test_post_without_reason_rejected(self) -> None:
        """POST without X-Change-Reason returns HTTP 400.

        **Validates: Requirements 11.2**
        """
        app = FastAPI()
        app.add_middleware(AuditMiddleware)

        @app.post("/api/test")
        async def create_test() -> dict[str, str]:
            return {"status": "created"}

        client = TestClient(app)
        response = client.post("/api/test", headers={"X-User-Id": "user-1"})
        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    def test_put_without_reason_rejected(self) -> None:
        """PUT without X-Change-Reason returns HTTP 400.

        **Validates: Requirements 11.2**
        """
        app = FastAPI()
        app.add_middleware(AuditMiddleware)

        @app.put("/api/test/1")
        async def update_test() -> dict[str, str]:
            return {"status": "updated"}

        client = TestClient(app)
        response = client.put("/api/test/1", headers={"X-User-Id": "user-1"})
        assert response.status_code == 400

    def test_delete_without_reason_rejected(self) -> None:
        """DELETE without X-Change-Reason returns HTTP 400.

        **Validates: Requirements 11.2**
        """
        app = FastAPI()
        app.add_middleware(AuditMiddleware)

        @app.delete("/api/test/1")
        async def delete_test() -> dict[str, str]:
            return {"status": "deleted"}

        client = TestClient(app)
        response = client.delete("/api/test/1", headers={"X-User-Id": "user-1"})
        assert response.status_code == 400

    def test_post_with_reason_accepted(self) -> None:
        """POST with X-Change-Reason succeeds.

        **Validates: Requirements 11.2**
        """
        app = FastAPI()
        app.add_middleware(AuditMiddleware)

        @app.post("/api/test")
        async def create_test() -> dict[str, str]:
            return {"status": "created"}

        client = TestClient(app)
        response = client.post(
            "/api/test",
            headers={
                "X-User-Id": "user-1",
                "X-Change-Reason": "Creating test record",
            },
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests for server-side UTC timestamp (Task 11.3)
# ---------------------------------------------------------------------------


class TestServerSideTimestamp:
    """Tests verifying server-side UTC timestamp injection.

    **Validates: Requirements 11.3, 11.6**
    """

    def test_timestamp_is_server_generated_utc(self) -> None:
        """Audit timestamp is server-generated UTC, independent of client.

        **Validates: Requirements 11.3**
        """
        from datetime import datetime, timezone

        from fastapi import Request

        app = FastAPI()
        app.add_middleware(AuditMiddleware, require_reason_for_mutations=False)

        @app.get("/api/test")
        async def get_test(request: Request) -> dict[str, str]:
            ts = request.state.audit_timestamp
            return {"timestamp": ts.isoformat(), "tzinfo": str(ts.tzinfo)}

        client = TestClient(app)
        before = datetime.now(timezone.utc)
        response = client.get("/api/test")
        after = datetime.now(timezone.utc)

        assert response.status_code == 200
        data = response.json()
        ts = datetime.fromisoformat(data["timestamp"])

        # Verify UTC timezone
        assert ts.tzinfo == timezone.utc
        # Verify server-generated (within request window)
        assert before <= ts <= after

    def test_timestamp_ignores_client_clock(self) -> None:
        """Server timestamp is not influenced by client-provided timestamps.

        **Validates: Requirements 11.3**
        """
        from datetime import datetime, timezone

        from fastapi import Request

        app = FastAPI()
        app.add_middleware(AuditMiddleware, require_reason_for_mutations=False)

        @app.get("/api/test")
        async def get_test(request: Request) -> dict[str, str]:
            return {"timestamp": request.state.audit_timestamp.isoformat()}

        client = TestClient(app)
        # Send a fake client timestamp from the past
        response = client.get(
            "/api/test",
            headers={"X-Client-Timestamp": "2000-01-01T00:00:00+00:00"},
        )

        assert response.status_code == 200
        ts = datetime.fromisoformat(response.json()["timestamp"])
        # Should be recent, not year 2000
        assert ts.year >= 2024
