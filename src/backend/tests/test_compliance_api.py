"""Unit tests for Compliance API endpoints.

Tests the compliance scorecard, missing link detection, and anomaly alert
management endpoints including filtering, resolution, and header enforcement.

References:
    - Task 10.3: Implement compliance router
    - Requirements: 6.2, 7.1, 8.4, 8.5
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.api.compliance import (
    get_anomaly_detection_service,
    get_anomaly_service,
    get_compliance_scorecard_service,
    get_missing_link_service,
    get_scorecard_service,
)
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.services.anomaly_detection import AnomalyDetectionService
from alcoabase.services.compliance_scorecard import ComplianceScorecardService
from alcoabase.services.missing_link_service import MissingLink, MissingLinkService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a test TenantContext."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="admin",
    )


@pytest.fixture
def mock_scorecard_service() -> AsyncMock:
    """Create a mock ComplianceScorecardService."""
    return AsyncMock(spec=ComplianceScorecardService)


@pytest.fixture
def mock_missing_link_service() -> AsyncMock:
    """Create a mock MissingLinkService."""
    return AsyncMock(spec=MissingLinkService)


@pytest.fixture
def mock_anomaly_service() -> AsyncMock:
    """Create a mock AnomalyDetectionService."""
    return AsyncMock(spec=AnomalyDetectionService)


class _FakeAnomalyAlert:
    """Fake anomaly alert model object that supports attribute access."""

    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


@pytest.fixture
def sample_scorecard() -> dict:
    """Sample scorecard data as returned by the service."""
    return {
        "overall_score": 82.5,
        "risk_band": "Good",
        "trend": "improving",
        "total_documents_reviewed": 15,
        "documents_with_critical_findings": 2,
        "documents_with_open_action_items": 4,
        "score_by_document_type": {"SOP": 85.0, "Protocol": 78.0},
        "last_updated": datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
    }


@pytest.fixture
def sample_missing_links() -> list[MissingLink]:
    """Sample missing links as returned by the service."""
    return [
        MissingLink(
            document_id=10,
            document_uuid="2025-00010",
            document_title="SOP-001 Manufacturing Process",
            document_type="SOP",
            current_status="Approved",
            missing_items=["training", "signature"],
            affected_user_count=5,
            days_since_approval=30,
            severity="Critical",
        ),
        MissingLink(
            document_id=11,
            document_uuid="2025-00011",
            document_title="Protocol-002 Validation",
            document_type="Protocol",
            current_status="Active",
            missing_items=["training"],
            affected_user_count=2,
            days_since_approval=10,
            severity="Major",
        ),
    ]


@pytest.fixture
def sample_anomaly_alert() -> dict:
    """Sample anomaly alert data."""
    return {
        "id": 1,
        "anomaly_type": "backdated_signature",
        "severity": "Critical",
        "description": "Signature by user 5 has timestamp before document upload",
        "affected_document_id": 10,
        "affected_user_id": 5,
        "detected_at": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
        "is_resolved": False,
        "resolved_at": None,
        "resolution_note": None,
        "created_at": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
    }


@pytest_asyncio.fixture
async def client(
    mock_scorecard_service: AsyncMock,
    mock_missing_link_service: AsyncMock,
    mock_anomaly_service: AsyncMock,
    tenant_context: TenantContext,
) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""

    async def _override_get_tenant_context():
        return tenant_context

    def _override_scorecard():
        return mock_scorecard_service

    def _override_missing_link():
        return mock_missing_link_service

    def _override_anomaly():
        return mock_anomaly_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_compliance_scorecard_service] = _override_scorecard
    app.dependency_overrides[get_missing_link_service] = _override_missing_link
    app.dependency_overrides[get_anomaly_detection_service] = _override_anomaly

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Unit test operation",
            "X-User-Id": "42",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_change_reason(
    mock_scorecard_service: AsyncMock,
    mock_missing_link_service: AsyncMock,
    mock_anomaly_service: AsyncMock,
    tenant_context: TenantContext,
) -> AsyncClient:
    """Create an httpx AsyncClient WITHOUT X-Change-Reason header."""

    async def _override_get_tenant_context():
        return tenant_context

    def _override_scorecard():
        return mock_scorecard_service

    def _override_missing_link():
        return mock_missing_link_service

    def _override_anomaly():
        return mock_anomaly_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_compliance_scorecard_service] = _override_scorecard
    app.dependency_overrides[get_missing_link_service] = _override_missing_link
    app.dependency_overrides[get_anomaly_detection_service] = _override_anomaly

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
# Test: GET /api/compliance/scorecard (Requirement 6.2)
# ---------------------------------------------------------------------------


class TestGetScorecard:
    """Tests for GET /api/compliance/scorecard."""

    @pytest.mark.asyncio
    async def test_get_scorecard_success(
        self,
        client: AsyncClient,
        mock_scorecard_service: AsyncMock,
        sample_scorecard: dict,
    ):
        """Returns 200 with scorecard data."""
        mock_scorecard_service.get_scorecard.return_value = sample_scorecard

        response = await client.get("/api/compliance/scorecard")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_score"] == 82.5
        assert data["risk_band"] == "Good"
        assert data["trend"] == "improving"
        assert data["total_documents_reviewed"] == 15
        assert data["documents_with_critical_findings"] == 2
        assert data["documents_with_open_action_items"] == 4
        assert data["score_by_document_type"] == {"SOP": 85.0, "Protocol": 78.0}
        mock_scorecard_service.get_scorecard.assert_called_once_with(company_id=1)

    @pytest.mark.asyncio
    async def test_get_scorecard_no_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
        mock_scorecard_service: AsyncMock,
        sample_scorecard: dict,
    ):
        """GET requests do not require X-Change-Reason header."""
        mock_scorecard_service.get_scorecard.return_value = sample_scorecard

        response = await client_no_change_reason.get("/api/compliance/scorecard")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: GET /api/compliance/missing-links (Requirement 7.1)
# ---------------------------------------------------------------------------


class TestGetMissingLinks:
    """Tests for GET /api/compliance/missing-links."""

    @pytest.mark.asyncio
    async def test_get_missing_links_success(
        self,
        client: AsyncClient,
        mock_missing_link_service: AsyncMock,
        sample_missing_links: list[MissingLink],
    ):
        """Returns 200 with list of missing links."""
        mock_missing_link_service.detect_missing_links.return_value = (
            sample_missing_links
        )

        response = await client.get("/api/compliance/missing-links")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["document_id"] == 10
        assert data[0]["severity"] == "Critical"
        assert data[0]["missing_items"] == ["training", "signature"]
        assert data[1]["document_id"] == 11
        assert data[1]["severity"] == "Major"
        assert data[1]["missing_items"] == ["training"]
        mock_missing_link_service.detect_missing_links.assert_called_once_with(
            company_id=1
        )

    @pytest.mark.asyncio
    async def test_get_missing_links_empty(
        self,
        client: AsyncClient,
        mock_missing_link_service: AsyncMock,
    ):
        """Returns 200 with empty list when no gaps exist."""
        mock_missing_link_service.detect_missing_links.return_value = []

        response = await client.get("/api/compliance/missing-links")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_missing_links_no_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
        mock_missing_link_service: AsyncMock,
    ):
        """GET requests do not require X-Change-Reason header."""
        mock_missing_link_service.detect_missing_links.return_value = []

        response = await client_no_change_reason.get("/api/compliance/missing-links")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: GET /api/compliance/anomalies (Requirement 8.4)
# ---------------------------------------------------------------------------


class TestListAnomalies:
    """Tests for GET /api/compliance/anomalies."""

    @pytest.mark.asyncio
    async def test_list_anomalies_success(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
        sample_anomaly_alert: dict,
    ):
        """Returns 200 with list of anomaly alerts."""
        mock_anomaly_service.list_alerts.return_value = [
            _FakeAnomalyAlert(sample_anomaly_alert)
        ]

        response = await client.get("/api/compliance/anomalies")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["anomaly_type"] == "backdated_signature"
        assert data[0]["severity"] == "Critical"
        assert data[0]["is_resolved"] is False
        mock_anomaly_service.list_alerts.assert_called_once_with(
            company_id=1,
            anomaly_type=None,
            severity=None,
            is_resolved=None,
            date_from=None,
            date_to=None,
        )

    @pytest.mark.asyncio
    async def test_list_anomalies_with_filters(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
    ):
        """Returns 200 with filtered results when query params are provided."""
        mock_anomaly_service.list_alerts.return_value = []

        response = await client.get(
            "/api/compliance/anomalies",
            params={
                "anomaly_type": "bulk_approval",
                "severity": "Major",
                "is_resolved": "false",
            },
        )

        assert response.status_code == 200
        mock_anomaly_service.list_alerts.assert_called_once_with(
            company_id=1,
            anomaly_type="bulk_approval",
            severity="Major",
            is_resolved=False,
            date_from=None,
            date_to=None,
        )

    @pytest.mark.asyncio
    async def test_list_anomalies_with_date_range(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
    ):
        """Returns 200 with date-filtered results."""
        mock_anomaly_service.list_alerts.return_value = []

        response = await client.get(
            "/api/compliance/anomalies",
            params={
                "date_from": "2025-06-01T00:00:00",
                "date_to": "2025-06-30T23:59:59",
            },
        )

        assert response.status_code == 200
        call_kwargs = mock_anomaly_service.list_alerts.call_args[1]
        assert call_kwargs["date_from"] is not None
        assert call_kwargs["date_to"] is not None

    @pytest.mark.asyncio
    async def test_list_anomalies_empty(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
    ):
        """Returns 200 with empty list when no alerts exist."""
        mock_anomaly_service.list_alerts.return_value = []

        response = await client.get("/api/compliance/anomalies")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_anomalies_no_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
        mock_anomaly_service: AsyncMock,
    ):
        """GET requests do not require X-Change-Reason header."""
        mock_anomaly_service.list_alerts.return_value = []

        response = await client_no_change_reason.get("/api/compliance/anomalies")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: PATCH /api/compliance/anomalies/{anomaly_id}/resolve (Requirement 8.5)
# ---------------------------------------------------------------------------


class TestResolveAnomaly:
    """Tests for PATCH /api/compliance/anomalies/{anomaly_id}/resolve."""

    @pytest.mark.asyncio
    async def test_resolve_anomaly_success(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
        sample_anomaly_alert: dict,
    ):
        """Returns 200 with resolved alert data."""
        resolved_alert = {
            **sample_anomaly_alert,
            "is_resolved": True,
            "resolved_at": datetime(2025, 6, 16, 9, 0, 0, tzinfo=UTC),
            "resolution_note": "Investigated and confirmed legitimate",
        }
        mock_anomaly_service.resolve_alert.return_value = _FakeAnomalyAlert(
            resolved_alert
        )

        response = await client.patch(
            "/api/compliance/anomalies/1/resolve",
            json={"resolution_note": "Investigated and confirmed legitimate"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_resolved"] is True
        assert data["resolution_note"] == "Investigated and confirmed legitimate"
        mock_anomaly_service.resolve_alert.assert_called_once_with(
            anomaly_id=1,
            resolution_note="Investigated and confirmed legitimate",
            company_id=1,
        )

    @pytest.mark.asyncio
    async def test_resolve_anomaly_not_found(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
    ):
        """Returns 404 when anomaly alert is not found."""
        mock_anomaly_service.resolve_alert.side_effect = ValueError(
            "Anomaly alert 999 not found for company 1"
        )

        response = await client.patch(
            "/api/compliance/anomalies/999/resolve",
            json={"resolution_note": "Test resolution"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Anomaly alert not found"

    @pytest.mark.asyncio
    async def test_resolve_anomaly_empty_note_returns_422(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when resolution_note is empty."""
        response = await client.patch(
            "/api/compliance/anomalies/1/resolve",
            json={"resolution_note": ""},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_resolve_anomaly_missing_body_returns_422(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when request body is missing."""
        response = await client.patch(
            "/api/compliance/anomalies/1/resolve",
            json={},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_resolve_anomaly_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """PATCH without X-Change-Reason returns 400."""
        response = await client_no_change_reason.patch(
            "/api/compliance/anomalies/1/resolve",
            json={"resolution_note": "Test resolution"},
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Company scoping (Requirements 6.5, 7.6, 8.6)
# ---------------------------------------------------------------------------


class TestCompanyScoping:
    """Tests that all operations are scoped to the tenant's company."""

    @pytest.mark.asyncio
    async def test_scorecard_passes_company_id(
        self,
        client: AsyncClient,
        mock_scorecard_service: AsyncMock,
        sample_scorecard: dict,
    ):
        """GET scorecard passes company_id from tenant context."""
        mock_scorecard_service.get_scorecard.return_value = sample_scorecard

        await client.get("/api/compliance/scorecard")

        mock_scorecard_service.get_scorecard.assert_called_once_with(company_id=1)

    @pytest.mark.asyncio
    async def test_missing_links_passes_company_id(
        self,
        client: AsyncClient,
        mock_missing_link_service: AsyncMock,
    ):
        """GET missing-links passes company_id from tenant context."""
        mock_missing_link_service.detect_missing_links.return_value = []

        await client.get("/api/compliance/missing-links")

        mock_missing_link_service.detect_missing_links.assert_called_once_with(
            company_id=1
        )

    @pytest.mark.asyncio
    async def test_anomalies_passes_company_id(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
    ):
        """GET anomalies passes company_id from tenant context."""
        mock_anomaly_service.list_alerts.return_value = []

        await client.get("/api/compliance/anomalies")

        call_kwargs = mock_anomaly_service.list_alerts.call_args[1]
        assert call_kwargs["company_id"] == 1

    @pytest.mark.asyncio
    async def test_resolve_passes_company_id(
        self,
        client: AsyncClient,
        mock_anomaly_service: AsyncMock,
        sample_anomaly_alert: dict,
    ):
        """PATCH resolve passes company_id from tenant context."""
        resolved = {**sample_anomaly_alert, "is_resolved": True}
        mock_anomaly_service.resolve_alert.return_value = _FakeAnomalyAlert(
            resolved
        )

        await client.patch(
            "/api/compliance/anomalies/1/resolve",
            json={"resolution_note": "Resolved"},
        )

        mock_anomaly_service.resolve_alert.assert_called_once_with(
            anomaly_id=1,
            resolution_note="Resolved",
            company_id=1,
        )
