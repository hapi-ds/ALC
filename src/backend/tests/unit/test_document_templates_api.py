"""Unit tests for document templates API router.

Tests HTTP status codes, tenant scoping, pagination, filtering,
and error handling for template registration, listing, and retrieval.

Requirements: 1.1, 1.5, 1.6, 1.7, 1.9, 1.10, 1.11, 1.13
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.api.document_templates import get_template_analysis_service
from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT = TenantContext(
    company_id=1,
    company_slug="test-company",
    user_id=42,
    membership_role="admin",
)

NOW = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def mock_service():
    """Mock TemplateAnalysisService."""
    return AsyncMock()


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    return AsyncMock()


@pytest_asyncio.fixture
async def client(mock_service, mock_db_session):
    """Create an httpx AsyncClient with overridden dependencies."""

    def _override_tenant():
        return TENANT

    app.dependency_overrides[get_tenant_context] = _override_tenant
    app.dependency_overrides[get_template_analysis_service] = lambda: mock_service
    app.dependency_overrides[get_db_session] = lambda: mock_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Testing template registration",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


def _make_template_model(
    template_id: int = 1,
    document_id: int = 10,
    document_version_id: int = 100,
    template_name: str = "URS Template v1",
    document_type_target: str = "URS",
    status: str = "active",
    registered_by: int = 42,
    template_analysis: dict | None = None,
):
    """Create a mock DocumentTemplate model object."""
    template = MagicMock()
    template.id = template_id
    template.document_id = document_id
    template.document_version_id = document_version_id
    template.template_name = template_name
    template.document_type_target = document_type_target
    template.status = status
    template.registered_by = registered_by
    template.registered_at = NOW
    template.template_analysis = template_analysis
    return template


# ---------------------------------------------------------------------------
# POST /api/documents/templates/register
# ---------------------------------------------------------------------------


class TestRegisterTemplate:
    """Tests for POST /api/documents/templates/register."""

    @pytest.mark.asyncio
    async def test_register_new_template_returns_202(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """New registration returns 202 with job_id."""
        mock_service.register_template.return_value = (1, "job-uuid-123")

        response = await client.post(
            "/api/documents/templates/register",
            json={
                "document_id": 10,
                "document_version_id": 100,
                "template_name": "URS Template v1",
                "document_type_target": "URS",
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-uuid-123"
        assert data["status"] == "pending"

        mock_service.register_template.assert_called_once_with(
            document_id=10,
            document_version_id=100,
            template_name="URS Template v1",
            document_type_target="URS",
            registered_by=42,
            company_id=1,
        )

    @pytest.mark.asyncio
    async def test_register_duplicate_returns_200(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Duplicate registration returns 200 with existing template."""
        mock_service.register_template.return_value = (1, None)
        mock_service.get_template.return_value = _make_template_model()

        response = await client.post(
            "/api/documents/templates/register",
            json={
                "document_id": 10,
                "document_version_id": 100,
                "template_name": "URS Template v1",
                "document_type_target": "URS",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["template_name"] == "URS Template v1"
        assert data["document_type_target"] == "URS"

    @pytest.mark.asyncio
    async def test_register_not_found_returns_404(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns 404 when document version not found."""
        mock_service.register_template.side_effect = ValueError(
            "Document version 999 not found for document 10"
        )

        response = await client.post(
            "/api/documents/templates/register",
            json={
                "document_id": 10,
                "document_version_id": 999,
                "template_name": "Template",
                "document_type_target": "URS",
            },
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_non_docx_returns_422(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns 422 when file is not .docx."""
        mock_service.register_template.side_effect = ValueError(
            "Only .docx files can be registered as templates. "
            "File has storage key: documents/test/1.0/report.pdf"
        )

        response = await client.post(
            "/api/documents/templates/register",
            json={
                "document_id": 10,
                "document_version_id": 100,
                "template_name": "Template",
                "document_type_target": "URS",
            },
        )

        assert response.status_code == 422
        assert ".docx" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_empty_template_name_returns_422(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns 422 when template_name is empty (Pydantic validation)."""
        response = await client.post(
            "/api/documents/templates/register",
            json={
                "document_id": 10,
                "document_version_id": 100,
                "template_name": "",
                "document_type_target": "URS",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_template_name_too_long_returns_422(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns 422 when template_name exceeds 500 characters."""
        response = await client.post(
            "/api/documents/templates/register",
            json={
                "document_id": 10,
                "document_version_id": 100,
                "template_name": "x" * 501,
                "document_type_target": "URS",
            },
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/documents/templates
# ---------------------------------------------------------------------------


class TestListTemplates:
    """Tests for GET /api/documents/templates."""

    @pytest.mark.asyncio
    async def test_list_templates_returns_paginated(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns paginated list of templates."""
        templates = [
            _make_template_model(template_id=1, template_name="Template A"),
            _make_template_model(template_id=2, template_name="Template B"),
        ]
        mock_service.list_templates.return_value = (templates, 2)

        response = await client.get("/api/documents/templates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["template_name"] == "Template A"
        assert data["items"][1]["template_name"] == "Template B"
        # template_analysis excluded from list view
        assert data["items"][0]["template_analysis"] is None

    @pytest.mark.asyncio
    async def test_list_templates_with_filter(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Filters by document_type_target."""
        mock_service.list_templates.return_value = ([], 0)

        response = await client.get(
            "/api/documents/templates?document_type_target=SOP"
        )

        assert response.status_code == 200
        mock_service.list_templates.assert_called_once_with(
            company_id=1,
            document_type_target="SOP",
            limit=20,
            offset=0,
        )

    @pytest.mark.asyncio
    async def test_list_templates_with_pagination(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Respects limit and offset parameters."""
        mock_service.list_templates.return_value = ([], 0)

        response = await client.get(
            "/api/documents/templates?limit=10&offset=5"
        )

        assert response.status_code == 200
        mock_service.list_templates.assert_called_once_with(
            company_id=1,
            document_type_target=None,
            limit=10,
            offset=5,
        )

    @pytest.mark.asyncio
    async def test_list_templates_limit_max_100(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns 422 when limit exceeds 100."""
        response = await client.get("/api/documents/templates?limit=101")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/documents/templates/{template_id}
# ---------------------------------------------------------------------------


class TestGetTemplate:
    """Tests for GET /api/documents/templates/{template_id}."""

    @pytest.mark.asyncio
    async def test_get_template_returns_full_analysis(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns template with full analysis."""
        analysis = {
            "section_hierarchy": [{"heading": "Introduction", "level": 1}],
            "numbering_scheme": "1.1.1",
            "total_sections": 5,
        }
        mock_service.get_template.return_value = _make_template_model(
            template_analysis=analysis
        )

        response = await client.get("/api/documents/templates/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["template_analysis"] == analysis
        mock_service.get_template.assert_called_once_with(
            template_id=1,
            company_id=1,
        )

    @pytest.mark.asyncio
    async def test_get_template_not_found_returns_404(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Returns 404 when template not found."""
        mock_service.get_template.return_value = None

        response = await client.get("/api/documents/templates/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_template_scoped_to_company(
        self, client: AsyncClient, mock_service: AsyncMock
    ):
        """Template retrieval is scoped to the tenant's company_id."""
        mock_service.get_template.return_value = None

        await client.get("/api/documents/templates/1")

        mock_service.get_template.assert_called_once_with(
            template_id=1,
            company_id=1,
        )
