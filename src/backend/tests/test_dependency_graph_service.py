"""Unit tests for DependencyGraphService query methods.

Tests get_edges (filtering, pagination, company scoping) and
get_document_dependencies (upstream/downstream grouping, empty groups,
document existence validation).

References:
    - Requirements: 1.8, 1.9, 1.11, 1.15
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.impact_analysis import DependencyEdge
from alcoabase.schemas.impact_analysis import GraphFilters, PaginationParams
from alcoabase.services.dependency_graph import DependencyGraphService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> DependencyGraphService:
    """Create a DependencyGraphService instance."""
    return DependencyGraphService()


@pytest.fixture
def sample_edge() -> DependencyEdge:
    """Create a sample DependencyEdge for testing."""
    edge = DependencyEdge(
        id=1,
        source_document_uuid="2025-00001",
        target_document_uuid="2025-00002",
        dependency_type="validates",
        confidence_score=1.0,
        detected_references=["REQ-001", "REQ-002"],
        last_verified_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
        company_id=1,
        created_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
    )
    return edge


def _make_edge(
    id: int,
    source: str,
    target: str,
    dep_type: str = "validates",
    company_id: int = 1,
) -> DependencyEdge:
    """Helper to create DependencyEdge instances for tests."""
    return DependencyEdge(
        id=id,
        source_document_uuid=source,
        target_document_uuid=target,
        dependency_type=dep_type,
        confidence_score=1.0,
        detected_references=[],
        last_verified_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
        company_id=company_id,
        created_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Helper to set up mock session execute responses
# ---------------------------------------------------------------------------


def _mock_session_for_get_edges(
    edges: list[DependencyEdge], total_count: int
) -> AsyncMock:
    """Create a mock session that returns edges and count for get_edges."""
    session = AsyncMock()

    # First call: count query, second call: edges query
    count_result = MagicMock()
    count_result.scalar_one.return_value = total_count

    edges_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = edges
    edges_result.scalars.return_value = scalars_mock

    session.execute = AsyncMock(side_effect=[count_result, edges_result])
    return session


def _mock_session_for_doc_deps(
    doc_exists: bool,
    upstream_edges: list[DependencyEdge] | None = None,
    downstream_edges: list[DependencyEdge] | None = None,
) -> AsyncMock:
    """Create a mock session for get_document_dependencies."""
    session = AsyncMock()

    if upstream_edges is None:
        upstream_edges = []
    if downstream_edges is None:
        downstream_edges = []

    # First call: document existence check (count query)
    exists_result = MagicMock()
    exists_result.scalar_one.return_value = 1 if doc_exists else 0

    # Second call: upstream edges query
    upstream_result = MagicMock()
    upstream_scalars = MagicMock()
    upstream_scalars.all.return_value = upstream_edges
    upstream_result.scalars.return_value = upstream_scalars

    # Third call: downstream edges query
    downstream_result = MagicMock()
    downstream_scalars = MagicMock()
    downstream_scalars.all.return_value = downstream_edges
    downstream_result.scalars.return_value = downstream_scalars

    session.execute = AsyncMock(
        side_effect=[exists_result, upstream_result, downstream_result]
    )
    return session


# ---------------------------------------------------------------------------
# Tests: get_edges
# ---------------------------------------------------------------------------


class TestGetEdges:
    """Tests for DependencyGraphService.get_edges."""

    @pytest.mark.asyncio
    async def test_returns_edges_with_total_count(
        self, service: DependencyGraphService
    ):
        """get_edges returns edges list and total_count."""
        edges = [_make_edge(1, "2025-00001", "2025-00002")]
        session = _mock_session_for_get_edges(edges, total_count=1)

        result = await service.get_edges(session, company_id=1)

        assert result["edges"] == edges
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_edges(
        self, service: DependencyGraphService
    ):
        """get_edges returns empty list and zero count when no edges exist."""
        session = _mock_session_for_get_edges([], total_count=0)

        result = await service.get_edges(session, company_id=1)

        assert result["edges"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_applies_default_pagination(
        self, service: DependencyGraphService
    ):
        """get_edges uses default pagination (limit=20, offset=0) when none provided."""
        session = _mock_session_for_get_edges([], total_count=0)

        await service.get_edges(session, company_id=1)

        # Verify execute was called (count + data queries)
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_accepts_custom_pagination(
        self, service: DependencyGraphService
    ):
        """get_edges accepts custom pagination parameters."""
        session = _mock_session_for_get_edges([], total_count=0)
        pagination = PaginationParams(limit=100, offset=50)

        result = await service.get_edges(
            session, company_id=1, pagination=pagination
        )

        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_accepts_filters(self, service: DependencyGraphService):
        """get_edges accepts filter parameters."""
        edges = [_make_edge(1, "2025-00001", "2025-00002", "validates")]
        session = _mock_session_for_get_edges(edges, total_count=1)
        filters = GraphFilters(
            source_document_uuid="2025-00001",
            dependency_type="validates",
        )

        result = await service.get_edges(
            session, company_id=1, filters=filters
        )

        assert result["edges"] == edges
        assert result["total_count"] == 1

    @pytest.mark.asyncio
    async def test_pagination_limit_max_200(
        self, service: DependencyGraphService
    ):
        """PaginationParams enforces max limit of 200."""
        with pytest.raises(Exception):
            PaginationParams(limit=201, offset=0)

    @pytest.mark.asyncio
    async def test_pagination_limit_min_1(
        self, service: DependencyGraphService
    ):
        """PaginationParams enforces min limit of 1."""
        with pytest.raises(Exception):
            PaginationParams(limit=0, offset=0)


# ---------------------------------------------------------------------------
# Tests: get_document_dependencies
# ---------------------------------------------------------------------------


class TestGetDocumentDependencies:
    """Tests for DependencyGraphService.get_document_dependencies."""

    @pytest.mark.asyncio
    async def test_returns_none_when_document_not_found(
        self, service: DependencyGraphService
    ):
        """Returns None when document doesn't exist in company scope (404 case)."""
        session = _mock_session_for_doc_deps(doc_exists=False)

        result = await service.get_document_dependencies(
            session, company_id=1, document_uuid="2025-99999"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_empty_groups_when_no_edges(
        self, service: DependencyGraphService
    ):
        """Returns empty groups for all dependency types when no edges exist."""
        session = _mock_session_for_doc_deps(
            doc_exists=True, upstream_edges=[], downstream_edges=[]
        )

        result = await service.get_document_dependencies(
            session, company_id=1, document_uuid="2025-00001"
        )

        assert result is not None
        assert result["document_uuid"] == "2025-00001"

        # All dependency types should be present with empty lists
        expected_types = [
            "validates",
            "references",
            "implements",
            "trains_on",
            "derived_from",
        ]
        for dep_type in expected_types:
            assert dep_type in result["upstream"]
            assert result["upstream"][dep_type] == []
            assert dep_type in result["downstream"]
            assert result["downstream"][dep_type] == []

    @pytest.mark.asyncio
    async def test_groups_upstream_edges_by_type(
        self, service: DependencyGraphService
    ):
        """Upstream edges are correctly grouped by dependency_type."""
        upstream = [
            _make_edge(1, "2025-00003", "2025-00001", "validates"),
            _make_edge(2, "2025-00004", "2025-00001", "references"),
        ]
        session = _mock_session_for_doc_deps(
            doc_exists=True, upstream_edges=upstream, downstream_edges=[]
        )

        result = await service.get_document_dependencies(
            session, company_id=1, document_uuid="2025-00001"
        )

        assert result is not None
        assert len(result["upstream"]["validates"]) == 1
        assert len(result["upstream"]["references"]) == 1
        assert result["upstream"]["validates"][0].id == 1
        assert result["upstream"]["references"][0].id == 2

    @pytest.mark.asyncio
    async def test_groups_downstream_edges_by_type(
        self, service: DependencyGraphService
    ):
        """Downstream edges are correctly grouped by dependency_type."""
        downstream = [
            _make_edge(1, "2025-00001", "2025-00005", "implements"),
            _make_edge(2, "2025-00001", "2025-00006", "trains_on"),
        ]
        session = _mock_session_for_doc_deps(
            doc_exists=True, upstream_edges=[], downstream_edges=downstream
        )

        result = await service.get_document_dependencies(
            session, company_id=1, document_uuid="2025-00001"
        )

        assert result is not None
        assert len(result["downstream"]["implements"]) == 1
        assert len(result["downstream"]["trains_on"]) == 1

    @pytest.mark.asyncio
    async def test_includes_document_uuid_in_response(
        self, service: DependencyGraphService
    ):
        """Response includes the queried document_uuid."""
        session = _mock_session_for_doc_deps(doc_exists=True)

        result = await service.get_document_dependencies(
            session, company_id=1, document_uuid="2025-00001"
        )

        assert result is not None
        assert result["document_uuid"] == "2025-00001"


# ---------------------------------------------------------------------------
# Tests: _document_exists_in_company
# ---------------------------------------------------------------------------


class TestDocumentExistsInCompany:
    """Tests for DependencyGraphService._document_exists_in_company."""

    @pytest.mark.asyncio
    async def test_returns_true_when_document_exists(
        self, service: DependencyGraphService
    ):
        """Returns True when document exists in company scope."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 1
        session.execute = AsyncMock(return_value=result_mock)

        exists = await service._document_exists_in_company(
            session, company_id=1, document_uuid="2025-00001"
        )

        assert exists is True

    @pytest.mark.asyncio
    async def test_returns_false_when_document_not_found(
        self, service: DependencyGraphService
    ):
        """Returns False when document doesn't exist in company scope."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=result_mock)

        exists = await service._document_exists_in_company(
            session, company_id=1, document_uuid="2025-99999"
        )

        assert exists is False

    @pytest.mark.asyncio
    async def test_returns_false_for_wrong_company(
        self, service: DependencyGraphService
    ):
        """Returns False when document exists but in different company."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=result_mock)

        exists = await service._document_exists_in_company(
            session, company_id=2, document_uuid="2025-00001"
        )

        assert exists is False
