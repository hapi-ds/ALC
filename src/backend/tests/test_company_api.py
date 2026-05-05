"""Unit tests for Company CRUD API endpoints.

Tests creation, retrieval, update, listing, deactivation, and reactivation
of company entities via the /api/companies endpoints.

References:
    - Task 7.2: Write unit tests for Company CRUD endpoints
    - Requirements 1.1, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 13.1, 13.4
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from alcoabase.database import get_db_session
from alcoabase.main import app
from alcoabase.models.company import Company


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession for database operations."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def sample_company() -> Company:
    """Create a sample Company model instance."""
    company = Company(
        id=1,
        slug="acme-pharma",
        display_name="Acme Pharma Inc.",
        regulatory_framework="ISO_13485",
        audit_config={"retention_years": 15},
        is_active=True,
    )
    company.created_at = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    return company


@pytest.fixture
def inactive_company() -> Company:
    """Create an inactive Company model instance."""
    company = Company(
        id=2,
        slug="old-corp",
        display_name="Old Corp",
        regulatory_framework="GMP",
        audit_config={},
        is_active=False,
    )
    company.created_at = datetime(2025, 1, 10, 8, 0, 0, tzinfo=UTC)
    return company


@pytest_asyncio.fixture
async def client(mock_session: AsyncMock) -> AsyncClient:
    """Create an httpx AsyncClient with the FastAPI app and overridden DB session.

    Includes the X-Change-Reason header required by AuditMiddleware for
    mutating requests to GxP-relevant endpoints.
    """

    async def _override_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Unit test operation",
            "X-User-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: POST /api/companies — Create Company
# ---------------------------------------------------------------------------


class TestCreateCompany:
    """Tests for POST /api/companies."""

    @pytest.mark.asyncio
    async def test_create_company_success(
        self, client: AsyncClient, mock_session: AsyncMock
    ) -> None:
        """POST /api/companies returns 201 with valid payload."""
        # Simulate DB assigning id and defaults on flush
        def _simulate_add(obj):
            obj.id = 1
            obj.is_active = True
            obj.created_at = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

        mock_session.add = MagicMock(side_effect=_simulate_add)

        payload = {
            "slug": "acme-pharma",
            "display_name": "Acme Pharma Inc.",
            "regulatory_framework": "ISO_13485",
            "audit_config": {"retention_years": 15},
        }

        response = await client.post("/api/companies", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "acme-pharma"
        assert data["display_name"] == "Acme Pharma Inc."
        assert data["regulatory_framework"] == "ISO_13485"
        assert data["audit_config"] == {"retention_years": 15}
        assert data["is_active"] is True
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_company_duplicate_slug_409(
        self, client: AsyncClient, mock_session: AsyncMock
    ) -> None:
        """POST /api/companies returns 409 when slug already exists."""
        mock_session.flush.side_effect = IntegrityError(
            statement="INSERT INTO companies",
            params={},
            orig=Exception("duplicate key"),
        )

        payload = {
            "slug": "acme-pharma",
            "display_name": "Acme Pharma Inc.",
            "regulatory_framework": "ISO_13485",
        }

        response = await client.post("/api/companies", json=payload)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_company_missing_fields_422(
        self, client: AsyncClient
    ) -> None:
        """POST /api/companies returns 422 when required fields are missing."""
        payload = {"slug": "acme-pharma"}  # missing display_name and regulatory_framework

        response = await client.post("/api/companies", json=payload)

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: GET /api/companies — List Companies
# ---------------------------------------------------------------------------


class TestListCompanies:
    """Tests for GET /api/companies."""

    @pytest.mark.asyncio
    async def test_list_companies_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_company: Company,
    ) -> None:
        """GET /api/companies returns 200 with list of companies."""
        # Mock the execute result chain: result.scalars().all()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_company]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        response = await client.get("/api/companies")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["slug"] == "acme-pharma"
        assert data[0]["display_name"] == "Acme Pharma Inc."


# ---------------------------------------------------------------------------
# Test: GET /api/companies/{slug} — Get Company
# ---------------------------------------------------------------------------


class TestGetCompany:
    """Tests for GET /api/companies/{slug}."""

    @pytest.mark.asyncio
    async def test_get_company_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_company: Company,
    ) -> None:
        """GET /api/companies/{slug} returns 200 when company exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_company
        mock_session.execute.return_value = mock_result

        response = await client.get("/api/companies/acme-pharma")

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "acme-pharma"
        assert data["display_name"] == "Acme Pharma Inc."
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_company_not_found_404(
        self, client: AsyncClient, mock_session: AsyncMock
    ) -> None:
        """GET /api/companies/{slug} returns 404 when company does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        response = await client.get("/api/companies/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: PATCH /api/companies/{slug} — Update Company
# ---------------------------------------------------------------------------


class TestUpdateCompany:
    """Tests for PATCH /api/companies/{slug}."""

    @pytest.mark.asyncio
    async def test_update_company_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_company: Company,
    ) -> None:
        """PATCH /api/companies/{slug} returns 200 with updated fields."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_company
        mock_session.execute.return_value = mock_result

        payload = {"display_name": "Acme Pharma Global"}

        response = await client.patch("/api/companies/acme-pharma", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Acme Pharma Global"
        assert data["slug"] == "acme-pharma"

    @pytest.mark.asyncio
    async def test_update_company_not_found_404(
        self, client: AsyncClient, mock_session: AsyncMock
    ) -> None:
        """PATCH /api/companies/{slug} returns 404 when company does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        payload = {"display_name": "New Name"}

        response = await client.patch("/api/companies/nonexistent", json=payload)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: POST /api/companies/{slug}/deactivate — Deactivate Company
# ---------------------------------------------------------------------------


class TestDeactivateCompany:
    """Tests for POST /api/companies/{slug}/deactivate."""

    @pytest.mark.asyncio
    async def test_deactivate_company_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_company: Company,
    ) -> None:
        """POST /api/companies/{slug}/deactivate returns 200 and sets is_active=False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_company
        mock_session.execute.return_value = mock_result

        response = await client.post("/api/companies/acme-pharma/deactivate")

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        assert sample_company.is_active is False

    @pytest.mark.asyncio
    async def test_deactivate_company_already_inactive_409(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        inactive_company: Company,
    ) -> None:
        """POST /api/companies/{slug}/deactivate returns 409 when already inactive."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = inactive_company
        mock_session.execute.return_value = mock_result

        response = await client.post("/api/companies/old-corp/deactivate")

        assert response.status_code == 409
        assert "already inactive" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: POST /api/companies/{slug}/reactivate — Reactivate Company
# ---------------------------------------------------------------------------


class TestReactivateCompany:
    """Tests for POST /api/companies/{slug}/reactivate."""

    @pytest.mark.asyncio
    async def test_reactivate_company_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        inactive_company: Company,
    ) -> None:
        """POST /api/companies/{slug}/reactivate returns 200 and sets is_active=True."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = inactive_company
        mock_session.execute.return_value = mock_result

        response = await client.post("/api/companies/old-corp/reactivate")

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True
        assert inactive_company.is_active is True

    @pytest.mark.asyncio
    async def test_reactivate_company_already_active_409(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_company: Company,
    ) -> None:
        """POST /api/companies/{slug}/reactivate returns 409 when already active."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_company
        mock_session.execute.return_value = mock_result

        response = await client.post("/api/companies/acme-pharma/reactivate")

        assert response.status_code == 409
        assert "already active" in response.json()["detail"].lower()
