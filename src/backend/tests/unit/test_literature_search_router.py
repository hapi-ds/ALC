"""Unit tests for the literature search router (hybrid + unified endpoints).

Tests validate:
- HTTP 400 when X-Company-Id header is missing
- HTTP 403 when user lacks member role
- HTTP 422 when query is empty or whitespace-only
- HTTP 200 with empty results when company index doesn't exist
- HTTP 200 with search results on successful search
- HTTP 503 when search service is unavailable

References:
    - Requirements: 10.1, 10.2, 10.8, 10.9, 10.10, 4.7, 6.9
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.embedding.exceptions import SearchServiceUnavailableError
from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridSearchResponse,
    HybridSearchResult,
)
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


@pytest.fixture
def viewer_tenant_context() -> TenantContext:
    """Create a test TenantContext with viewer role (insufficient)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="viewer",
    )


@pytest.fixture
def mock_index_manager() -> MagicMock:
    """Create a mock LiteratureIndexManager."""
    manager = MagicMock()
    manager._index_name = MagicMock(return_value="literature-embeddings-1")
    manager._client = MagicMock()
    manager._client.indices = MagicMock()
    manager._client.indices.exists = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_query_engine() -> AsyncMock:
    """Create a mock HybridQueryEngine."""
    engine = AsyncMock()
    engine.search = AsyncMock(
        return_value=HybridSearchResponse(
            results=[
                HybridSearchResult(
                    chunk_text="Test result chunk text.",
                    title="Test Paper Title",
                    authors=["Author A"],
                    doi="10.1234/test.2024",
                    publication_date="2024-01-15",
                    source_id="pubmed",
                    relevance_score=0.85,
                    partition_tag="public_literature",
                    section_heading="Abstract",
                    ingestion_record_id=100,
                )
            ],
            total_count=1,
            page=1,
            page_size=20,
            degraded_mode=False,
        )
    )
    engine.unified_search = AsyncMock(
        return_value=HybridSearchResponse(
            results=[
                HybridSearchResult(
                    chunk_text="Unified result chunk text.",
                    title="Unified Paper Title",
                    authors=["Author B"],
                    doi=None,
                    publication_date=None,
                    source_id=None,
                    relevance_score=0.72,
                    partition_tag="private_knowledge",
                    section_heading="Methods",
                    ingestion_record_id=200,
                )
            ],
            total_count=1,
            page=1,
            page_size=20,
            degraded_mode=False,
            partial_results=False,
        )
    )
    return engine


@pytest_asyncio.fixture
async def client(
    tenant_context: TenantContext,
    mock_index_manager: MagicMock,
    mock_query_engine: AsyncMock,
) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""

    async def _override_get_tenant_context():
        return tenant_context

    async def _override_get_db_session():
        """Provide a mock session that accepts audit log writes without DB."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_db_session] = _override_get_db_session

    # Set up app state with mocked services
    app.state.literature_index_manager = mock_index_manager
    app.state.hybrid_query_engine = mock_query_engine

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

    # Cleanup
    app.dependency_overrides.clear()
    if hasattr(app.state, "literature_index_manager"):
        del app.state.literature_index_manager
    if hasattr(app.state, "hybrid_query_engine"):
        del app.state.hybrid_query_engine


@pytest_asyncio.fixture
async def client_no_company_header(
    tenant_context: TenantContext,
    mock_index_manager: MagicMock,
    mock_query_engine: AsyncMock,
) -> AsyncClient:
    """Create an httpx AsyncClient WITHOUT X-Company-Id header."""

    async def _override_get_tenant_context():
        return tenant_context

    async def _override_get_db_session():
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.state.literature_index_manager = mock_index_manager
    app.state.hybrid_query_engine = mock_query_engine

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
    if hasattr(app.state, "literature_index_manager"):
        del app.state.literature_index_manager
    if hasattr(app.state, "hybrid_query_engine"):
        del app.state.hybrid_query_engine


@pytest_asyncio.fixture
async def client_viewer_role(
    viewer_tenant_context: TenantContext,
    mock_index_manager: MagicMock,
    mock_query_engine: AsyncMock,
) -> AsyncClient:
    """Create an httpx AsyncClient with viewer role (insufficient perms)."""

    async def _override_get_tenant_context():
        return viewer_tenant_context

    async def _override_get_db_session():
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.state.literature_index_manager = mock_index_manager
    app.state.hybrid_query_engine = mock_query_engine

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

    app.dependency_overrides.clear()
    if hasattr(app.state, "literature_index_manager"):
        del app.state.literature_index_manager
    if hasattr(app.state, "hybrid_query_engine"):
        del app.state.hybrid_query_engine


# ---------------------------------------------------------------------------
# Tests: POST /api/literature/search/hybrid
# ---------------------------------------------------------------------------


class TestHybridSearchEndpoint:
    """Tests for POST /api/literature/search/hybrid."""

    @pytest.mark.asyncio
    async def test_successful_hybrid_search(self, client: AsyncClient) -> None:
        """Returns 200 with results on valid search request."""
        response = await client.post(
            "/api/literature/search/hybrid",
            json={"query": "protein folding mechanisms"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Test Paper Title"
        assert data["results"][0]["partition_tag"] == "public_literature"
        assert data["degraded_mode"] is False

    @pytest.mark.asyncio
    async def test_missing_company_id_header_returns_400(
        self, client_no_company_header: AsyncClient
    ) -> None:
        """Returns 400 when X-Company-Id header is not provided."""
        response = await client_no_company_header.post(
            "/api/literature/search/hybrid",
            json={"query": "test query"},
        )
        assert response.status_code == 400
        assert "X-Company-Id" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer_role: AsyncClient
    ) -> None:
        """Returns 403 when user has only viewer role."""
        response = await client_viewer_role.post(
            "/api/literature/search/hybrid",
            json={"query": "test query"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_query_returns_422(self, client: AsyncClient) -> None:
        """Returns 422 when query is empty string."""
        response = await client.post(
            "/api/literature/search/hybrid",
            json={"query": ""},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when query is whitespace-only."""
        response = await client.post(
            "/api/literature/search/hybrid",
            json={"query": "   "},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_index_not_exists_returns_empty_200(
        self,
        client: AsyncClient,
        mock_index_manager: MagicMock,
    ) -> None:
        """Returns 200 with empty results when company index doesn't exist."""
        mock_index_manager._client.indices.exists = AsyncMock(return_value=False)

        response = await client.post(
            "/api/literature/search/hybrid",
            json={"query": "test query"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_search_service_unavailable_returns_503(
        self,
        client: AsyncClient,
        mock_query_engine: AsyncMock,
    ) -> None:
        """Returns 503 when search service raises unavailable error."""
        mock_query_engine.search.side_effect = SearchServiceUnavailableError(
            "OpenSearch unreachable", company_id=1
        )

        response = await client.post(
            "/api/literature/search/hybrid",
            json={"query": "test query"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: POST /api/literature/search/unified
# ---------------------------------------------------------------------------


class TestUnifiedSearchEndpoint:
    """Tests for POST /api/literature/search/unified."""

    @pytest.mark.asyncio
    async def test_successful_unified_search(self, client: AsyncClient) -> None:
        """Returns 200 with results on valid unified search request."""
        response = await client.post(
            "/api/literature/search/unified",
            json={"query": "regulatory compliance", "include_internal": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["partition_tag"] == "private_knowledge"

    @pytest.mark.asyncio
    async def test_missing_company_id_header_returns_400(
        self, client_no_company_header: AsyncClient
    ) -> None:
        """Returns 400 when X-Company-Id header is not provided."""
        response = await client_no_company_header.post(
            "/api/literature/search/unified",
            json={"query": "test query"},
        )
        assert response.status_code == 400
        assert "X-Company-Id" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_viewer_role_returns_403(
        self, client_viewer_role: AsyncClient
    ) -> None:
        """Returns 403 when user has only viewer role."""
        response = await client_viewer_role.post(
            "/api/literature/search/unified",
            json={"query": "test query"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_query_returns_422(self, client: AsyncClient) -> None:
        """Returns 422 when query is empty string."""
        response = await client.post(
            "/api/literature/search/unified",
            json={"query": ""},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when query is whitespace-only."""
        response = await client.post(
            "/api/literature/search/unified",
            json={"query": "   "},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_index_not_exists_returns_empty_200(
        self,
        client: AsyncClient,
        mock_index_manager: MagicMock,
    ) -> None:
        """Returns 200 with empty results when company index doesn't exist."""
        mock_index_manager._client.indices.exists = AsyncMock(return_value=False)

        response = await client.post(
            "/api/literature/search/unified",
            json={"query": "test query"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_search_service_unavailable_returns_503(
        self,
        client: AsyncClient,
        mock_query_engine: AsyncMock,
    ) -> None:
        """Returns 503 when search service raises unavailable error."""
        mock_query_engine.unified_search.side_effect = (
            SearchServiceUnavailableError("OpenSearch unreachable", company_id=1)
        )

        response = await client.post(
            "/api/literature/search/unified",
            json={"query": "test query"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_include_internal_defaults_to_true(
        self,
        client: AsyncClient,
        mock_query_engine: AsyncMock,
    ) -> None:
        """include_internal defaults to True in the unified search."""
        response = await client.post(
            "/api/literature/search/unified",
            json={"query": "test query"},
        )
        assert response.status_code == 200
        # Verify unified_search was called (not search)
        mock_query_engine.unified_search.assert_called_once()
        call_args = mock_query_engine.unified_search.call_args[0][0]
        assert call_args.include_internal is True
