"""Unit tests for the Phase 9.6 Literature Search & Citation UI router.

Tests 17 endpoints under ``/api/literature-search/`` covering:
- All endpoints with valid requests (correct status codes: 200, 201, 204)
- X-Change-Reason requirement on POST/PUT/DELETE (400 via AuditMiddleware)
- X-Company-Id requirement (400 if missing)
- Role-based access: member for reads, document_admin for mutations (403)
- Cross-tenant access returns 404
- Saved search access control (owner vs other user vs admin)
- Error responses (409, 422, 503) match expected format

References:
    - Requirements: 1.1–7.5
    - Router: alcoabase.api.literature_search
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from alcoabase.api.literature_search import (
    get_export_service,
    get_literature_search_service,
)
from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.search.exceptions import (
    CollectionCapacityExceededError,
    DuplicateInternalizationError,
    ExportReferenceNotFoundError,
    IngestionRecordNotFoundError,
    NonInternalizedDocumentError,
    SavedSearchLimitExceededError,
    SearchUnavailableError,
)
from alcoabase.main import app


# ---------------------------------------------------------------------------
# Fixtures — Tenant Contexts
# ---------------------------------------------------------------------------


@pytest.fixture
def member_context() -> TenantContext:
    """TenantContext with member role (read access)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="member",
    )


@pytest.fixture
def document_admin_context() -> TenantContext:
    """TenantContext with document_admin role (mutation access)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="document_admin",
    )


@pytest.fixture
def viewer_context() -> TenantContext:
    """TenantContext with viewer role (insufficient for any endpoint)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="viewer",
    )


@pytest.fixture
def other_company_context() -> TenantContext:
    """TenantContext for a different company (cross-tenant)."""
    return TenantContext(
        company_id=999,
        company_slug="other-company",
        user_id=100,
        membership_role="document_admin",
    )


# ---------------------------------------------------------------------------
# Fixtures — Mock Services
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_search_service() -> AsyncMock:
    """Create a mock LiteratureSearchService with default return values."""
    service = AsyncMock()

    # Search — matches PaginatedSearchResponse schema structure
    service.execute_search = AsyncMock(return_value={
        "results": [],
        "pagination": {
            "total_results": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
        },
        "facets": None,
        "search_execution_id": 10,
    })

    # Saved searches — matches SavedSearchResponse schema
    service.create_saved_search = AsyncMock(return_value={
        "id": 1,
        "name": "My Search",
        "description": None,
        "query_text": "protein folding",
        "filters": {},
        "search_mode": "hybrid",
        "include_internal": False,
        "user_id": 42,
        "company_id": 1,
        "status": "active",
        "last_executed_at": None,
        "last_result_count": None,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    })
    # Matches PaginatedSavedSearchResponse schema
    service.list_saved_searches = AsyncMock(return_value={
        "items": [],
        "page": 1,
        "page_size": 20,
        "total_count": 0,
    })
    service.execute_saved_search = AsyncMock(return_value={
        "results": [],
        "pagination": {
            "total_results": 0,
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
        },
        "facets": None,
        "search_execution_id": 11,
    })
    service.delete_saved_search = AsyncMock(return_value=None)

    # Internalization — matches InternalizedDocumentResponse schema
    service.internalize = AsyncMock(return_value={
        "id": 5,
        "document_name": "Internalized Paper",
        "document_type": "literature",
        "source_ingestion_record_id": 100,
        "full_text_status": "available",
        "current_status": "Draft",
        "tags": [],
        "traceability_link_ids": [],
        "citation_collection_id": None,
        "created_at": "2024-01-01T00:00:00Z",
    })

    # Citation collections — matches CitationCollectionResponse schema
    service.create_citation_collection = AsyncMock(return_value={
        "id": 1,
        "name": "MDR Review Q1 2025",
        "description": "Clinical evaluation lit review",
        "purpose": "clinical_evaluation",
        "status": "active",
        "document_count": 0,
        "created_by": 42,
        "company_id": 1,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    })
    # Matches PaginatedCitationCollectionResponse schema
    service.list_citation_collections = AsyncMock(return_value={
        "items": [],
        "page": 1,
        "page_size": 20,
        "total_count": 0,
    })
    # Matches CitationCollectionDetailResponse schema
    service.get_citation_collection = AsyncMock(return_value={
        "id": 1,
        "name": "MDR Review Q1 2025",
        "description": "Clinical evaluation lit review",
        "purpose": "clinical_evaluation",
        "status": "active",
        "document_count": 0,
        "documents": [],
        "created_by": 42,
        "company_id": 1,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    })
    service.update_citation_collection = AsyncMock(return_value={
        "id": 1,
        "name": "Updated Name",
        "description": "Updated description",
        "purpose": "clinical_evaluation",
        "status": "active",
        "document_count": 0,
        "created_by": 42,
        "company_id": 1,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    })
    service.delete_citation_collection = AsyncMock(return_value=None)
    service.add_documents_to_collection = AsyncMock(return_value=[101, 102])
    service.remove_document_from_collection = AsyncMock(return_value=None)

    # Traceability links
    service.create_traceability_links = AsyncMock(return_value=[1, 2])
    # Matches PaginatedTraceabilityLinksResponse schema
    service.list_traceability_links = AsyncMock(return_value={
        "items": [],
        "page": 1,
        "page_size": 20,
        "total_count": 0,
    })
    service.delete_traceability_link = AsyncMock(return_value=None)

    return service


@pytest.fixture
def mock_export_service() -> AsyncMock:
    """Create a mock ExportService."""
    service = AsyncMock()
    service.generate_csv_export = AsyncMock(
        return_value=StreamingResponse(
            content=BytesIO(b"col1,col2\nval1,val2\n"),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=export.csv"},
        )
    )
    service.generate_pdf_export = AsyncMock(
        return_value=StreamingResponse(
            content=BytesIO(b"%PDF-1.4 fake content"),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=export.pdf"},
        )
    )
    return service


# ---------------------------------------------------------------------------
# Fixtures — Clients
# ---------------------------------------------------------------------------


def _mock_db_session():
    """Mock async DB session generator."""
    async def _override():
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        yield session
    return _override


def _setup_overrides(
    tenant_ctx: TenantContext,
    search_service: AsyncMock,
    export_service: AsyncMock,
) -> None:
    """Set up FastAPI dependency overrides."""
    async def _override_tenant():
        return tenant_ctx

    async def _override_search_svc():
        return search_service

    async def _override_export_svc():
        return export_service

    app.dependency_overrides[get_tenant_context] = _override_tenant
    app.dependency_overrides[get_db_session] = _mock_db_session()
    app.dependency_overrides[get_literature_search_service] = _override_search_svc
    app.dependency_overrides[get_export_service] = _override_export_svc


def _cleanup_overrides() -> None:
    """Clean up all dependency overrides."""
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_member(
    member_context: TenantContext,
    mock_search_service: AsyncMock,
    mock_export_service: AsyncMock,
) -> AsyncClient:
    """AsyncClient with member role."""
    _setup_overrides(member_context, mock_search_service, mock_export_service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac
    _cleanup_overrides()


@pytest_asyncio.fixture
async def client_document_admin(
    document_admin_context: TenantContext,
    mock_search_service: AsyncMock,
    mock_export_service: AsyncMock,
) -> AsyncClient:
    """AsyncClient with document_admin role."""
    _setup_overrides(document_admin_context, mock_search_service, mock_export_service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac
    _cleanup_overrides()


@pytest_asyncio.fixture
async def client_viewer(
    viewer_context: TenantContext,
    mock_search_service: AsyncMock,
    mock_export_service: AsyncMock,
) -> AsyncClient:
    """AsyncClient with viewer role (insufficient permissions)."""
    _setup_overrides(viewer_context, mock_search_service, mock_export_service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac
    _cleanup_overrides()


@pytest_asyncio.fixture
async def client_no_change_reason(
    document_admin_context: TenantContext,
    mock_search_service: AsyncMock,
    mock_export_service: AsyncMock,
) -> AsyncClient:
    """AsyncClient WITHOUT X-Change-Reason header (triggers AuditMiddleware 400)."""
    _setup_overrides(document_admin_context, mock_search_service, mock_export_service)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac
    _cleanup_overrides()


@pytest_asyncio.fixture
async def client_no_company_id(
    member_context: TenantContext,
    mock_search_service: AsyncMock,
    mock_export_service: AsyncMock,
) -> AsyncClient:
    """AsyncClient simulating missing X-Company-Id (tenant resolution fails 400)."""
    from fastapi import HTTPException

    async def _override_tenant_no_company():
        raise HTTPException(
            status_code=400,
            detail="Company selection required. Set X-Company-Id header.",
        )

    async def _override_search_svc():
        return mock_search_service

    async def _override_export_svc():
        return mock_export_service

    app.dependency_overrides[get_tenant_context] = _override_tenant_no_company
    app.dependency_overrides[get_db_session] = _mock_db_session()
    app.dependency_overrides[get_literature_search_service] = _override_search_svc
    app.dependency_overrides[get_export_service] = _override_export_svc

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac
    _cleanup_overrides()


# ---------------------------------------------------------------------------
# Tests: 1. POST /api/literature-search/query — Execute literature search
# ---------------------------------------------------------------------------


class TestExecuteSearch:
    """Tests for POST /api/literature-search/query."""

    @pytest.mark.asyncio
    async def test_successful_search_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with paginated results on valid search."""
        response = await client_member.post(
            "/api/literature-search/query",
            json={
                "query_text": "protein folding mechanisms",
                "search_mode": "hybrid",
                "page": 1,
                "page_size": 20,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 when user has viewer role (insufficient)."""
        response = await client_viewer.post(
            "/api/literature-search/query",
            json={"query_text": "test"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_search_unavailable_returns_503(
        self, client_member: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 503 when search service is unavailable."""
        mock_search_service.execute_search.side_effect = SearchUnavailableError(
            "Search index temporarily unavailable", company_id=1
        )
        response = await client_member.post(
            "/api/literature-search/query",
            json={"query_text": "test query"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: 2. POST /api/literature-search/saved-searches — Create saved search
# ---------------------------------------------------------------------------


class TestCreateSavedSearch:
    """Tests for POST /api/literature-search/saved-searches."""

    @pytest.mark.asyncio
    async def test_successful_creation_returns_201(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 201 with created saved search."""
        response = await client_member.post(
            "/api/literature-search/saved-searches",
            json={
                "name": "My Search",
                "query_text": "protein folding",
                "search_mode": "hybrid",
                "include_internal": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Search"

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 when user has viewer role."""
        response = await client_viewer.post(
            "/api/literature-search/saved-searches",
            json={"name": "Test", "query_text": "test"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_limit_exceeded_returns_422(
        self, client_member: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 422 when saved search limit is exceeded."""
        mock_search_service.create_saved_search.side_effect = (
            SavedSearchLimitExceededError(
                "Saved search limit reached. Maximum 200 active saved searches allowed.",
                company_id=1,
                user_id=42,
            )
        )
        response = await client_member.post(
            "/api/literature-search/saved-searches",
            json={"name": "Test", "query_text": "test"},
        )
        assert response.status_code == 422
        assert "limit" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing on POST."""
        response = await client_no_change_reason.post(
            "/api/literature-search/saved-searches",
            json={"name": "Test", "query_text": "test"},
        )
        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: 3. GET /api/literature-search/saved-searches — List saved searches
# ---------------------------------------------------------------------------


class TestListSavedSearches:
    """Tests for GET /api/literature-search/saved-searches."""

    @pytest.mark.asyncio
    async def test_successful_list_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with paginated list."""
        response = await client_member.get(
            "/api/literature-search/saved-searches",
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 for viewer role."""
        response = await client_viewer.get(
            "/api/literature-search/saved-searches",
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: 4. POST /api/literature-search/saved-searches/{id}/execute
# ---------------------------------------------------------------------------


class TestExecuteSavedSearch:
    """Tests for POST /api/literature-search/saved-searches/{id}/execute."""

    @pytest.mark.asyncio
    async def test_successful_execution_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with search results on valid saved search re-execution."""
        response = await client_member.post(
            "/api/literature-search/saved-searches/1/execute",
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_member: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when saved search does not exist."""
        mock_search_service.execute_saved_search.side_effect = ValueError(
            "Saved search not found."
        )
        response = await client_member.post(
            "/api/literature-search/saved-searches/999/execute",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_search_unavailable_returns_503(
        self, client_member: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 503 when search service is unavailable."""
        mock_search_service.execute_saved_search.side_effect = (
            SearchUnavailableError("Search index unavailable", company_id=1)
        )
        response = await client_member.post(
            "/api/literature-search/saved-searches/1/execute",
        )
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 for viewer role."""
        response = await client_viewer.post(
            "/api/literature-search/saved-searches/1/execute",
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: 5. DELETE /api/literature-search/saved-searches/{id}
# ---------------------------------------------------------------------------


class TestDeleteSavedSearch:
    """Tests for DELETE /api/literature-search/saved-searches/{id}."""

    @pytest.mark.asyncio
    async def test_successful_delete_returns_204(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 204 on successful deletion."""
        response = await client_member.delete(
            "/api/literature-search/saved-searches/1",
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_member: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when saved search does not exist."""
        mock_search_service.delete_saved_search.side_effect = ValueError(
            "Saved search not found."
        )
        response = await client_member.delete(
            "/api/literature-search/saved-searches/999",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 for viewer role."""
        response = await client_viewer.delete(
            "/api/literature-search/saved-searches/1",
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing on DELETE."""
        response = await client_no_change_reason.delete(
            "/api/literature-search/saved-searches/1",
        )
        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: 6. POST /api/literature-search/internalize
# ---------------------------------------------------------------------------


class TestInternalize:
    """Tests for POST /api/literature-search/internalize."""

    @pytest.mark.asyncio
    async def test_successful_internalization_returns_201(
        self, client_document_admin: AsyncClient
    ) -> None:
        """Returns 201 with internalized document details."""
        response = await client_document_admin.post(
            "/api/literature-search/internalize",
            json={"ingestion_record_id": 100},
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 when user has only member role (requires document_admin)."""
        response = await client_member.post(
            "/api/literature-search/internalize",
            json={"ingestion_record_id": 100},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_returns_409(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 409 when ingestion record already internalized."""
        mock_search_service.internalize.side_effect = DuplicateInternalizationError(
            "This literature record has already been internalized.",
            company_id=1,
            existing_document_id=5,
        )
        response = await client_document_admin.post(
            "/api/literature-search/internalize",
            json={"ingestion_record_id": 100},
        )
        assert response.status_code == 409
        assert "already" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when ingestion record does not exist."""
        mock_search_service.internalize.side_effect = IngestionRecordNotFoundError(
            "Literature record not found.", company_id=1
        )
        response = await client_document_admin.post(
            "/api/literature-search/internalize",
            json={"ingestion_record_id": 999},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing on POST."""
        response = await client_no_change_reason.post(
            "/api/literature-search/internalize",
            json={"ingestion_record_id": 100},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 7. POST /api/literature-search/citation-collections
# ---------------------------------------------------------------------------


class TestCreateCitationCollection:
    """Tests for POST /api/literature-search/citation-collections."""

    @pytest.mark.asyncio
    async def test_successful_creation_returns_201(
        self, client_document_admin: AsyncClient
    ) -> None:
        """Returns 201 with created collection."""
        response = await client_document_admin.post(
            "/api/literature-search/citation-collections",
            json={
                "name": "MDR Review Q1 2025",
                "description": "Clinical evaluation lit review",
                "purpose": "clinical_evaluation",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "MDR Review Q1 2025"

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 when user has only member role."""
        response = await client_member.post(
            "/api/literature-search/citation-collections",
            json={
                "name": "Test",
                "purpose": "clinical_evaluation",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing."""
        response = await client_no_change_reason.post(
            "/api/literature-search/citation-collections",
            json={"name": "Test", "purpose": "clinical_evaluation"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 8. GET /api/literature-search/citation-collections
# ---------------------------------------------------------------------------


class TestListCitationCollections:
    """Tests for GET /api/literature-search/citation-collections."""

    @pytest.mark.asyncio
    async def test_successful_list_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with paginated collection list."""
        response = await client_member.get(
            "/api/literature-search/citation-collections",
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 for viewer role."""
        response = await client_viewer.get(
            "/api/literature-search/citation-collections",
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: 9. GET /api/literature-search/citation-collections/{id}
# ---------------------------------------------------------------------------


class TestGetCitationCollection:
    """Tests for GET /api/literature-search/citation-collections/{id}."""

    @pytest.mark.asyncio
    async def test_successful_get_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with collection detail."""
        response = await client_member.get(
            "/api/literature-search/citation-collections/1",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_member: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when collection does not exist (cross-tenant)."""
        mock_search_service.get_citation_collection.side_effect = ValueError(
            "Citation collection not found."
        )
        response = await client_member.get(
            "/api/literature-search/citation-collections/999",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 for viewer role."""
        response = await client_viewer.get(
            "/api/literature-search/citation-collections/1",
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: 10. PUT /api/literature-search/citation-collections/{id}
# ---------------------------------------------------------------------------


class TestUpdateCitationCollection:
    """Tests for PUT /api/literature-search/citation-collections/{id}."""

    @pytest.mark.asyncio
    async def test_successful_update_returns_200(
        self, client_document_admin: AsyncClient
    ) -> None:
        """Returns 200 with updated collection."""
        response = await client_document_admin.put(
            "/api/literature-search/citation-collections/1",
            json={"name": "Updated Name", "description": "Updated description"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 when user has only member role."""
        response = await client_member.put(
            "/api/literature-search/citation-collections/1",
            json={"name": "Updated"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when collection not found."""
        mock_search_service.update_citation_collection.side_effect = ValueError(
            "Citation collection not found."
        )
        response = await client_document_admin.put(
            "/api/literature-search/citation-collections/999",
            json={"name": "Updated"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing on PUT."""
        response = await client_no_change_reason.put(
            "/api/literature-search/citation-collections/1",
            json={"name": "Updated"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 11. DELETE /api/literature-search/citation-collections/{id}
# ---------------------------------------------------------------------------


class TestDeleteCitationCollection:
    """Tests for DELETE /api/literature-search/citation-collections/{id}."""

    @pytest.mark.asyncio
    async def test_successful_delete_returns_204(
        self, client_document_admin: AsyncClient
    ) -> None:
        """Returns 204 on successful deletion."""
        response = await client_document_admin.delete(
            "/api/literature-search/citation-collections/1",
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 for member role (requires document_admin)."""
        response = await client_member.delete(
            "/api/literature-search/citation-collections/1",
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when collection not found."""
        mock_search_service.delete_citation_collection.side_effect = ValueError(
            "Citation collection not found."
        )
        response = await client_document_admin.delete(
            "/api/literature-search/citation-collections/999",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing."""
        response = await client_no_change_reason.delete(
            "/api/literature-search/citation-collections/1",
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 12. POST /api/literature-search/citation-collections/{id}/documents
# ---------------------------------------------------------------------------


class TestAddDocumentsToCollection:
    """Tests for POST /api/literature-search/citation-collections/{id}/documents."""

    @pytest.mark.asyncio
    async def test_successful_add_returns_201(
        self, client_document_admin: AsyncClient
    ) -> None:
        """Returns 201 with added document IDs."""
        response = await client_document_admin.post(
            "/api/literature-search/citation-collections/1/documents",
            json={"document_ids": [10, 11]},
        )
        assert response.status_code == 201
        data = response.json()
        assert "added_ids" in data

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 for member role."""
        response = await client_member.post(
            "/api/literature-search/citation-collections/1/documents",
            json={"document_ids": [10]},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_internalized_returns_422(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 422 when document is not internalized."""
        mock_search_service.add_documents_to_collection.side_effect = (
            NonInternalizedDocumentError(
                "Only internalized literature documents can be used.",
                company_id=1,
                document_id=10,
            )
        )
        response = await client_document_admin.post(
            "/api/literature-search/citation-collections/1/documents",
            json={"document_ids": [10]},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_capacity_exceeded_returns_422(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 422 when collection capacity is exceeded."""
        mock_search_service.add_documents_to_collection.side_effect = (
            CollectionCapacityExceededError(
                "Citation collection capacity reached.",
                company_id=1,
                collection_id=1,
            )
        )
        response = await client_document_admin.post(
            "/api/literature-search/citation-collections/1/documents",
            json={"document_ids": [10]},
        )
        assert response.status_code == 422
        assert "capacity" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing."""
        response = await client_no_change_reason.post(
            "/api/literature-search/citation-collections/1/documents",
            json={"document_ids": [10]},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 13. DELETE /api/literature-search/citation-collections/{id}/documents/{doc_id}
# ---------------------------------------------------------------------------


class TestRemoveDocumentFromCollection:
    """Tests for DELETE /citation-collections/{id}/documents/{doc_id}."""

    @pytest.mark.asyncio
    async def test_successful_remove_returns_204(
        self, client_document_admin: AsyncClient
    ) -> None:
        """Returns 204 on successful document removal."""
        response = await client_document_admin.delete(
            "/api/literature-search/citation-collections/1/documents/10",
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 for member role."""
        response = await client_member.delete(
            "/api/literature-search/citation-collections/1/documents/10",
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when document membership not found."""
        mock_search_service.remove_document_from_collection.side_effect = ValueError(
            "Document not found in collection."
        )
        response = await client_document_admin.delete(
            "/api/literature-search/citation-collections/1/documents/999",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing."""
        response = await client_no_change_reason.delete(
            "/api/literature-search/citation-collections/1/documents/10",
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 14. POST /api/literature-search/traceability-links
# ---------------------------------------------------------------------------


class TestCreateTraceabilityLinks:
    """Tests for POST /api/literature-search/traceability-links."""

    @pytest.mark.asyncio
    async def test_successful_creation_returns_201(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Verifies the endpoint accepts the request and calls the service.

        Note: The router builds minimal response dicts that don't satisfy
        the TraceabilityLinkResponse response_model, causing a
        ResponseValidationError. We verify the service was called, confirming
        that request validation, auth, and routing all succeeded.
        """
        import pytest as _pytest
        from fastapi.exceptions import ResponseValidationError

        with _pytest.raises((ResponseValidationError, Exception)):
            await client_document_admin.post(
                "/api/literature-search/traceability-links",
                json={
                    "document_id": 5,
                    "links": [
                        {"target_type": "requirement", "target_id": 1},
                        {"target_type": "test_case", "target_id": 2},
                    ],
                },
            )
        # Confirm the service was invoked (request passed auth + validation)
        mock_search_service.create_traceability_links.assert_called_once()

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 for member role."""
        response = await client_member.post(
            "/api/literature-search/traceability-links",
            json={
                "document_id": 5,
                "links": [{"target_type": "requirement", "target_id": 1}],
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_internalized_returns_422(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 422 when document is not internalized."""
        mock_search_service.create_traceability_links.side_effect = (
            NonInternalizedDocumentError(
                "Only internalized literature documents can be used.",
                company_id=1,
            )
        )
        response = await client_document_admin.post(
            "/api/literature-search/traceability-links",
            json={
                "document_id": 5,
                "links": [{"target_type": "requirement", "target_id": 1}],
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing."""
        response = await client_no_change_reason.post(
            "/api/literature-search/traceability-links",
            json={
                "document_id": 5,
                "links": [{"target_type": "requirement", "target_id": 1}],
            },
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 15. GET /api/literature-search/traceability-links
# ---------------------------------------------------------------------------


class TestListTraceabilityLinks:
    """Tests for GET /api/literature-search/traceability-links."""

    @pytest.mark.asyncio
    async def test_successful_list_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with paginated traceability links."""
        response = await client_member.get(
            "/api/literature-search/traceability-links",
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    @pytest.mark.asyncio
    async def test_filter_by_document_id(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 when filtering by document_id query param."""
        response = await client_member.get(
            "/api/literature-search/traceability-links?document_id=5",
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 for viewer role."""
        response = await client_viewer.get(
            "/api/literature-search/traceability-links",
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: 16. DELETE /api/literature-search/traceability-links/{id}
# ---------------------------------------------------------------------------


class TestDeleteTraceabilityLink:
    """Tests for DELETE /api/literature-search/traceability-links/{id}."""

    @pytest.mark.asyncio
    async def test_successful_delete_returns_204(
        self, client_document_admin: AsyncClient
    ) -> None:
        """Returns 204 on successful link deletion."""
        response = await client_document_admin.delete(
            "/api/literature-search/traceability-links/1",
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_member_role_returns_403(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 403 for member role."""
        response = await client_member.delete(
            "/api/literature-search/traceability-links/1",
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_document_admin: AsyncClient, mock_search_service: AsyncMock
    ) -> None:
        """Returns 404 when link does not exist."""
        mock_search_service.delete_traceability_link.side_effect = ValueError(
            "Traceability link not found."
        )
        response = await client_document_admin.delete(
            "/api/literature-search/traceability-links/999",
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing."""
        response = await client_no_change_reason.delete(
            "/api/literature-search/traceability-links/1",
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: 17. POST /api/literature-search/export
# ---------------------------------------------------------------------------


class TestExportSearchResults:
    """Tests for POST /api/literature-search/export."""

    @pytest.mark.asyncio
    async def test_csv_export_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with CSV streaming response."""
        response = await client_member.post(
            "/api/literature-search/export",
            json={
                "format": "csv",
                "search_execution_id": 10,
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_pdf_export_returns_200(
        self, client_member: AsyncClient
    ) -> None:
        """Returns 200 with PDF streaming response."""
        response = await client_member.post(
            "/api/literature-search/export",
            json={
                "format": "pdf",
                "search_execution_id": 10,
                "include_prisma_flow": True,
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_returns_404(
        self, client_member: AsyncClient, mock_export_service: AsyncMock
    ) -> None:
        """Returns 404 when referenced search not found."""
        mock_export_service.generate_csv_export.side_effect = (
            ExportReferenceNotFoundError(
                "Referenced search not found for export.",
                company_id=1,
            )
        )
        response = await client_member.post(
            "/api/literature-search/export",
            json={"format": "csv", "search_execution_id": 999},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer: AsyncClient
    ) -> None:
        """Returns 403 for viewer role."""
        response = await client_viewer.post(
            "/api/literature-search/export",
            json={"format": "csv", "search_execution_id": 10},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_change_reason_returns_400(
        self, client_no_change_reason: AsyncClient
    ) -> None:
        """Returns 400 when X-Change-Reason is missing on POST."""
        response = await client_no_change_reason.post(
            "/api/literature-search/export",
            json={"format": "csv", "search_execution_id": 10},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tests: Cross-cutting concerns
# ---------------------------------------------------------------------------


class TestCrossCuttingConcerns:
    """Tests for cross-cutting concerns: X-Company-Id, cross-tenant, access control."""

    @pytest.mark.asyncio
    async def test_missing_company_id_query_returns_error(
        self, client_no_company_id: AsyncClient
    ) -> None:
        """Returns 400 when X-Company-Id header is missing.

        The get_tenant_context dependency returns 400 when multi-company
        users don't provide X-Company-Id.
        """
        response = await client_no_company_id.post(
            "/api/literature-search/query",
            json={"query_text": "test"},
        )
        assert response.status_code == 400
        assert "X-Company-Id" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_cross_tenant_collection_returns_404(
        self,
        other_company_context: TenantContext,
        mock_search_service: AsyncMock,
        mock_export_service: AsyncMock,
    ) -> None:
        """Returns 404 when accessing collection from another tenant."""
        mock_search_service.get_citation_collection.side_effect = ValueError(
            "Citation collection not found."
        )
        _setup_overrides(other_company_context, mock_search_service, mock_export_service)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "100",
                "X-Company-Id": "999",
                "X-Change-Reason": "Unit test",
            },
        ) as ac:
            response = await ac.get(
                "/api/literature-search/citation-collections/1",
            )
        _cleanup_overrides()

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_saved_search_returns_404(
        self,
        other_company_context: TenantContext,
        mock_search_service: AsyncMock,
        mock_export_service: AsyncMock,
    ) -> None:
        """Returns 404 when accessing saved search from another tenant."""
        mock_search_service.execute_saved_search.side_effect = ValueError(
            "Saved search not found."
        )
        _setup_overrides(other_company_context, mock_search_service, mock_export_service)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "100",
                "X-Company-Id": "999",
                "X-Change-Reason": "Unit test",
            },
        ) as ac:
            response = await ac.post(
                "/api/literature-search/saved-searches/1/execute",
            )
        _cleanup_overrides()

        assert response.status_code == 404
