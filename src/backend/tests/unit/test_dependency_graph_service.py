"""Unit tests for DependencyGraphService build methods.

Tests full build, incremental build, timeout handling, skip-on-error behavior,
edge CRUD, filtering, pagination, and deduplication.

Mocks CrossReferenceService and KnowledgeService.

References:
    - Requirements: 1.1–1.15
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.impact_analysis import DependencyEdge
from alcoabase.services.cross_reference import CrossReference
from alcoabase.services.dependency_graph import (
    BUILD_TIMEOUT_SECONDS,
    SEMANTIC_SIMILARITY_THRESHOLD,
    DependencyGraphService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(
    id: int,
    uuid: str,
    title: str = "Test Doc",
    doc_type: str = "SOP",
    company_id: int = 1,
) -> Document:
    """Create a Document instance for testing."""
    doc = Document(
        id=id,
        document_uuid=uuid,
        title=title,
        document_type=doc_type,
        current_status="Active",
        folder_path="/test",
        created_by=1,
    )
    doc.company_id = company_id
    return doc


def _make_cross_reference(
    ref_type: str = "requirement",
    ref_id: str = "REQ-00001",
    ref_text: str = "See REQ-00001 for details",
    source_doc_id: int = 1,
    source_doc_title: str = "Test Doc",
) -> CrossReference:
    """Create a CrossReference instance for testing."""
    return CrossReference(
        reference_type=ref_type,
        reference_identifier=ref_id,
        reference_text=ref_text,
        source_document_id=source_doc_id,
        source_document_title=source_doc_title,
    )


def _make_search_result(document_uuid: str, relevance_score: float, excerpt: str = "text"):
    """Create a mock search result."""
    result = MagicMock()
    result.document_uuid = document_uuid
    result.relevance_score = relevance_score
    result.excerpt = excerpt
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cross_reference_service() -> MagicMock:
    """Create a mock CrossReferenceService."""
    svc = MagicMock()
    svc.extract_references_from_text = MagicMock(return_value=[])
    return svc


@pytest.fixture
def mock_knowledge_service() -> MagicMock:
    """Create a mock KnowledgeService."""
    svc = MagicMock()
    svc.hybrid_search = MagicMock(return_value=([], 0))
    svc.generate_embeddings = AsyncMock(return_value=[[0.1] * 128])
    return svc


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock):
    """Create a mock async session factory matching async_sessionmaker pattern.

    The real async_sessionmaker is called as:
        async with session_factory() as session:
            ...
    So factory() must return an async context manager.
    """
    class _MockContextManager:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, *args):
            return False

    def factory():
        return _MockContextManager()

    return factory


@pytest.fixture
def service(
    mock_session_factory,
    mock_cross_reference_service,
    mock_knowledge_service,
) -> DependencyGraphService:
    """Create a DependencyGraphService with mocked dependencies."""
    return DependencyGraphService(
        session_factory=mock_session_factory,
        cross_reference_service=mock_cross_reference_service,
        knowledge_service=mock_knowledge_service,
    )


# ---------------------------------------------------------------------------
# Tests: build_full_graph
# ---------------------------------------------------------------------------


class TestBuildFullGraph:
    """Tests for DependencyGraphService.build_full_graph."""

    @pytest.mark.asyncio
    async def test_full_build_processes_all_documents(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Full build scans all documents and creates edges."""
        doc1 = _make_document(1, "2025-00001", "URS Doc", "URS")
        doc2 = _make_document(2, "2025-00002", "MVP Doc", "MVP")

        # Mock: get all documents query
        docs_result = MagicMock()
        docs_scalars = MagicMock()
        docs_scalars.all.return_value = [doc1, doc2]
        docs_result.scalars.return_value = docs_scalars

        # Mock: TrainingTask query (no training tasks)
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        # Mock: GenerationProvenance query (no provenance)
        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(
            side_effect=[docs_result, training_result, prov_result]
        )

        # Mock: KnowledgeService returns no text (no edges from cross-refs)
        mock_knowledge_service.hybrid_search.return_value = ([], 0)

        result = await service.build_full_graph(company_id=1)

        assert result["status"] == "completed"
        assert result["documents_processed"] == 2
        assert result["skipped_documents"] == []
        assert result["unprocessed_documents"] == []

    @pytest.mark.asyncio
    async def test_full_build_creates_edges_from_cross_references(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Full build creates edges when cross-references are found."""
        doc1 = _make_document(1, "2025-00001", "MVP Doc", "MVP")
        doc2 = _make_document(2, "2025-00002", "URS Doc", "URS")

        # Mock: get all documents
        docs_result = MagicMock()
        docs_scalars = MagicMock()
        docs_scalars.all.return_value = [doc1, doc2]
        docs_result.scalars.return_value = docs_scalars

        # Mock: no DB-linked edges
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        # Mock: document version query for text extraction
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = MagicMock(
            id=1, uploaded_at=datetime(2025, 1, 1, tzinfo=UTC)
        )

        # We need multiple execute calls: docs, training, prov, then per-doc queries
        mock_session.execute = AsyncMock(
            side_effect=[docs_result, training_result, prov_result]
            + [version_result] * 10  # Extra for document text extraction calls
        )

        # Mock: KnowledgeService returns text for documents
        search_result = _make_search_result("2025-00001", 0.9, "MVP validates REQ-00001")
        mock_knowledge_service.hybrid_search.return_value = ([search_result], 1)

        # Mock: CrossReferenceService finds a reference
        ref = _make_cross_reference("requirement", "REQ-00001", "See REQ-00001", 1, "MVP Doc")
        mock_cross_reference_service.extract_references_from_text.return_value = [ref]

        result = await service.build_full_graph(company_id=1)

        assert result["status"] == "completed"
        assert result["edges_created"] >= 1

    @pytest.mark.asyncio
    async def test_full_build_skips_failed_documents(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Documents that fail processing are skipped and recorded."""
        doc1 = _make_document(1, "2025-00001", "Good Doc")
        doc2 = _make_document(2, "2025-00002", "Bad Doc")

        # Mock: get all documents
        docs_result = MagicMock()
        docs_scalars = MagicMock()
        docs_scalars.all.return_value = [doc1, doc2]
        docs_result.scalars.return_value = docs_scalars

        # Mock: no DB-linked edges
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(
            side_effect=[docs_result, training_result, prov_result]
        )

        # Mock _process_document_edges to succeed for doc1, fail for doc2
        call_count = [0]
        original_process = service._process_document_edges

        async def mock_process(session, doc, all_docs, company_id):
            call_count[0] += 1
            if doc.document_uuid == "2025-00002":
                raise RuntimeError("Storage unavailable")
            return []

        service._process_document_edges = mock_process

        result = await service.build_full_graph(company_id=1)

        assert result["documents_processed"] == 1
        assert "2025-00002" in result["skipped_documents"]
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_full_build_timeout_returns_partial_success(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Build returns partial_success when timeout is exceeded."""
        docs = [_make_document(i, f"2025-{i:05d}", f"Doc {i}") for i in range(1, 6)]

        # Mock: get all documents
        docs_result = MagicMock()
        docs_scalars = MagicMock()
        docs_scalars.all.return_value = docs
        docs_result.scalars.return_value = docs_scalars

        # Mock: no DB-linked edges
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(
            side_effect=[docs_result, training_result, prov_result]
        )

        # Patch time.monotonic to simulate timeout after 2 documents
        start = 0.0
        call_count = [0]

        def mock_monotonic():
            call_count[0] += 1
            # First call is the start_time capture
            if call_count[0] <= 1:
                return start
            # After 2 docs processed, exceed timeout
            if call_count[0] <= 3:
                return start + 100  # Within timeout
            return start + BUILD_TIMEOUT_SECONDS + 1  # Exceed timeout

        async def mock_process(session, doc, all_docs, company_id):
            return []

        service._process_document_edges = mock_process

        with patch("alcoabase.services.dependency_graph.time.monotonic", side_effect=mock_monotonic):
            result = await service.build_full_graph(company_id=1)

        assert result["status"] == "partial_success"
        assert len(result["unprocessed_documents"]) > 0

    @pytest.mark.asyncio
    async def test_full_build_creates_db_linked_edges(
        self, service, mock_session, mock_knowledge_service
    ):
        """Full build creates trains_on and derived_from edges from DB records."""
        doc1 = _make_document(1, "2025-00001", "SOP Doc", "SOP")

        # Mock: get all documents
        docs_result = MagicMock()
        docs_scalars = MagicMock()
        docs_scalars.all.return_value = [doc1]
        docs_result.scalars.return_value = docs_scalars

        # Mock: TrainingTask query returns a SOP UUID
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = ["2025-00001"]
        training_result.scalars.return_value = training_scalars

        # Mock: GenerationProvenance query (no provenance)
        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        # Mock: upsert execute call (returns None for INSERT statements)
        upsert_result = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[docs_result, training_result, prov_result, upsert_result]
        )

        # Mock _process_document_edges to return no additional edges
        service._process_document_edges = AsyncMock(return_value=[])

        result = await service.build_full_graph(company_id=1)

        # Should have created at least 1 edge (trains_on from SOP)
        assert result["edges_created"] >= 1
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Tests: build_incremental_graph
# ---------------------------------------------------------------------------


class TestBuildIncrementalGraph:
    """Tests for DependencyGraphService.build_incremental_graph."""

    @pytest.mark.asyncio
    async def test_incremental_with_no_last_build_delegates_to_full(
        self, service, mock_session
    ):
        """Incremental build with no last_build_at delegates to full build."""
        # Mock full build to track it was called
        service.build_full_graph = AsyncMock(return_value={
            "status": "completed",
            "edges_created": 5,
            "documents_processed": 3,
            "skipped_documents": [],
            "unprocessed_documents": [],
        })

        result = await service.build_incremental_graph(company_id=1, last_build_at=None)

        service.build_full_graph.assert_called_once_with(1)
        assert result["status"] == "completed"
        assert result["edges_created"] == 5

    @pytest.mark.asyncio
    async def test_incremental_processes_only_modified_documents(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Incremental build only processes documents modified since last build."""
        last_build = datetime(2025, 1, 10, tzinfo=UTC)
        modified_doc = _make_document(1, "2025-00001", "Modified Doc")

        # Mock: modified documents query
        modified_result = MagicMock()
        modified_scalars = MagicMock()
        modified_scalars.all.return_value = [modified_doc]
        modified_result.scalars.return_value = modified_scalars

        # Mock: all documents query
        all_docs_result = MagicMock()
        all_docs_scalars = MagicMock()
        all_docs_scalars.all.return_value = [modified_doc, _make_document(2, "2025-00002", "Unchanged")]
        all_docs_result.scalars.return_value = all_docs_scalars

        # Mock: no DB-linked edges
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(
            side_effect=[modified_result, all_docs_result, training_result, prov_result]
        )

        # Track which documents are processed
        processed_uuids = []

        async def mock_process(session, doc, all_docs, company_id):
            processed_uuids.append(doc.document_uuid)
            return []

        service._process_document_edges = mock_process
        service._prune_stale_edges = AsyncMock(return_value=0)

        result = await service.build_incremental_graph(company_id=1, last_build_at=last_build)

        assert result["status"] == "completed"
        assert result["documents_processed"] == 1
        # Only the modified document should be processed
        assert "2025-00001" in processed_uuids
        assert "2025-00002" not in processed_uuids

    @pytest.mark.asyncio
    async def test_incremental_returns_completed_when_no_modified_docs(
        self, service, mock_session
    ):
        """Incremental build returns completed with zero counts when no docs modified."""
        last_build = datetime(2025, 1, 10, tzinfo=UTC)

        # Mock: no modified documents
        modified_result = MagicMock()
        modified_scalars = MagicMock()
        modified_scalars.all.return_value = []
        modified_result.scalars.return_value = modified_scalars

        mock_session.execute = AsyncMock(side_effect=[modified_result])

        result = await service.build_incremental_graph(company_id=1, last_build_at=last_build)

        assert result["status"] == "completed"
        assert result["edges_created"] == 0
        assert result["documents_processed"] == 0

    @pytest.mark.asyncio
    async def test_incremental_prunes_stale_edges(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Incremental build prunes stale edges from modified documents."""
        last_build = datetime(2025, 1, 10, tzinfo=UTC)
        modified_doc = _make_document(1, "2025-00001", "Modified Doc")

        # Mock: modified documents query
        modified_result = MagicMock()
        modified_scalars = MagicMock()
        modified_scalars.all.return_value = [modified_doc]
        modified_result.scalars.return_value = modified_scalars

        # Mock: all documents query
        all_docs_result = MagicMock()
        all_docs_scalars = MagicMock()
        all_docs_scalars.all.return_value = [modified_doc]
        all_docs_result.scalars.return_value = all_docs_scalars

        # Mock: no DB-linked edges
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(
            side_effect=[modified_result, all_docs_result, training_result, prov_result]
        )

        # Mock prune to return 2 pruned edges
        service._prune_stale_edges = AsyncMock(return_value=2)
        service._process_document_edges = AsyncMock(return_value=[])

        result = await service.build_incremental_graph(company_id=1, last_build_at=last_build)

        assert result["edges_pruned"] == 2
        service._prune_stale_edges.assert_called_once()

    @pytest.mark.asyncio
    async def test_incremental_timeout_returns_partial_success(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Incremental build returns partial_success on timeout."""
        last_build = datetime(2025, 1, 10, tzinfo=UTC)
        docs = [_make_document(i, f"2025-{i:05d}", f"Doc {i}") for i in range(1, 6)]

        # Mock: modified documents query
        modified_result = MagicMock()
        modified_scalars = MagicMock()
        modified_scalars.all.return_value = docs
        modified_result.scalars.return_value = modified_scalars

        # Mock: all documents query
        all_docs_result = MagicMock()
        all_docs_scalars = MagicMock()
        all_docs_scalars.all.return_value = docs
        all_docs_result.scalars.return_value = all_docs_scalars

        # Mock: no DB-linked edges
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(
            side_effect=[modified_result, all_docs_result, training_result, prov_result]
        )

        # Patch time.monotonic to simulate timeout after 2 documents
        start = 0.0
        call_count = [0]

        def mock_monotonic():
            call_count[0] += 1
            if call_count[0] <= 1:
                return start
            if call_count[0] <= 3:
                return start + 100
            return start + BUILD_TIMEOUT_SECONDS + 1

        service._prune_stale_edges = AsyncMock(return_value=0)
        service._process_document_edges = AsyncMock(return_value=[])

        with patch("alcoabase.services.dependency_graph.time.monotonic", side_effect=mock_monotonic):
            result = await service.build_incremental_graph(company_id=1, last_build_at=last_build)

        assert result["status"] == "partial_success"
        assert len(result["unprocessed_documents"]) > 0

    @pytest.mark.asyncio
    async def test_incremental_skips_failed_documents(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Incremental build skips documents that fail and records them."""
        last_build = datetime(2025, 1, 10, tzinfo=UTC)
        doc1 = _make_document(1, "2025-00001", "Good Doc")
        doc2 = _make_document(2, "2025-00002", "Bad Doc")

        # Mock: modified documents query
        modified_result = MagicMock()
        modified_scalars = MagicMock()
        modified_scalars.all.return_value = [doc1, doc2]
        modified_result.scalars.return_value = modified_scalars

        # Mock: all documents query
        all_docs_result = MagicMock()
        all_docs_scalars = MagicMock()
        all_docs_scalars.all.return_value = [doc1, doc2]
        all_docs_result.scalars.return_value = all_docs_scalars

        # Mock: no DB-linked edges
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(
            side_effect=[modified_result, all_docs_result, training_result, prov_result]
        )

        # Mock: prune succeeds for doc1, fails for doc2
        prune_call_count = [0]

        async def mock_prune(session, doc, company_id):
            prune_call_count[0] += 1
            if doc.document_uuid == "2025-00002":
                raise RuntimeError("Failed to prune")
            return 0

        service._prune_stale_edges = mock_prune
        service._process_document_edges = AsyncMock(return_value=[])

        result = await service.build_incremental_graph(company_id=1, last_build_at=last_build)

        assert result["documents_processed"] == 1
        assert "2025-00002" in result["skipped_documents"]


# ---------------------------------------------------------------------------
# Tests: _upsert_edge (deduplication)
# ---------------------------------------------------------------------------


class TestUpsertEdge:
    """Tests for edge deduplication via upsert."""

    @pytest.mark.asyncio
    async def test_upsert_executes_insert_on_conflict_update(
        self, service, mock_session
    ):
        """Upsert uses PostgreSQL INSERT...ON CONFLICT DO UPDATE."""
        edge_data = {
            "source_document_uuid": "2025-00001",
            "target_document_uuid": "2025-00002",
            "dependency_type": "validates",
            "confidence_score": 1.0,
            "detected_references": ["REQ-001"],
            "last_verified_at": datetime(2025, 1, 15, tzinfo=UTC),
            "company_id": 1,
        }

        await service._upsert_edge(mock_session, edge_data)

        # Verify execute was called (the upsert statement)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_called_multiple_times_for_same_edge(
        self, service, mock_session
    ):
        """Multiple upserts for same edge tuple execute without error."""
        edge_data = {
            "source_document_uuid": "2025-00001",
            "target_document_uuid": "2025-00002",
            "dependency_type": "validates",
            "confidence_score": 0.8,
            "detected_references": ["REQ-001"],
            "last_verified_at": datetime(2025, 1, 15, tzinfo=UTC),
            "company_id": 1,
        }

        # Call upsert twice with same key but different confidence
        await service._upsert_edge(mock_session, edge_data)
        edge_data["confidence_score"] = 1.0
        edge_data["detected_references"] = ["REQ-001", "REQ-002"]
        await service._upsert_edge(mock_session, edge_data)

        assert mock_session.execute.call_count == 2


# ---------------------------------------------------------------------------
# Tests: _prune_stale_edges
# ---------------------------------------------------------------------------


class TestPruneStaleEdges:
    """Tests for stale edge pruning during incremental builds."""

    @pytest.mark.asyncio
    async def test_prune_removes_edges_with_missing_references(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Edges whose references are no longer in document text are pruned."""
        doc = _make_document(1, "2025-00001", "Test Doc")

        # Mock: _get_document_text returns current text
        service._get_document_text = AsyncMock(return_value="Current content without old refs")

        # Mock: CrossReferenceService finds no references in current text
        mock_cross_reference_service.extract_references_from_text.return_value = []

        # Mock: existing edges from this document
        stale_edge = MagicMock()
        stale_edge.detected_references = ["REQ-OLD-001"]

        edges_result = MagicMock()
        edges_scalars = MagicMock()
        edges_scalars.all.return_value = [stale_edge]
        edges_result.scalars.return_value = edges_scalars

        mock_session.execute = AsyncMock(return_value=edges_result)

        pruned = await service._prune_stale_edges(mock_session, doc, company_id=1)

        assert pruned == 1
        mock_session.delete.assert_called_once_with(stale_edge)

    @pytest.mark.asyncio
    async def test_prune_keeps_edges_with_present_references(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """Edges whose references are still present are not pruned."""
        doc = _make_document(1, "2025-00001", "Test Doc")

        # Mock: _get_document_text returns current text
        service._get_document_text = AsyncMock(return_value="Content with REQ-00001")

        # Mock: CrossReferenceService finds the reference
        ref = _make_cross_reference("requirement", "REQ-00001")
        mock_cross_reference_service.extract_references_from_text.return_value = [ref]

        # Mock: existing edge still has the reference
        valid_edge = MagicMock()
        valid_edge.detected_references = ["REQ-00001"]

        edges_result = MagicMock()
        edges_scalars = MagicMock()
        edges_scalars.all.return_value = [valid_edge]
        edges_result.scalars.return_value = edges_scalars

        mock_session.execute = AsyncMock(return_value=edges_result)

        pruned = await service._prune_stale_edges(mock_session, doc, company_id=1)

        assert pruned == 0
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_prune_skips_db_linked_edges(
        self, service, mock_session, mock_cross_reference_service, mock_knowledge_service
    ):
        """DB-linked edges (TrainingTask, GenerationProvenance, semantic) are not pruned."""
        doc = _make_document(1, "2025-00001", "Test Doc")

        service._get_document_text = AsyncMock(return_value="Some content")
        mock_cross_reference_service.extract_references_from_text.return_value = []

        # Mock: edges with DB-linked references
        training_edge = MagicMock()
        training_edge.detected_references = ["TrainingTask:2025-00001"]

        provenance_edge = MagicMock()
        provenance_edge.detected_references = ["GenerationProvenance:gen-123"]

        semantic_edge = MagicMock()
        semantic_edge.detected_references = ["semantic:2025-00001->2025-00002"]

        edges_result = MagicMock()
        edges_scalars = MagicMock()
        edges_scalars.all.return_value = [training_edge, provenance_edge, semantic_edge]
        edges_result.scalars.return_value = edges_scalars

        mock_session.execute = AsyncMock(return_value=edges_result)

        pruned = await service._prune_stale_edges(mock_session, doc, company_id=1)

        assert pruned == 0
        mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_prune_returns_zero_when_no_text(
        self, service, mock_session, mock_cross_reference_service
    ):
        """Prune returns 0 when document text cannot be extracted (conservative)."""
        doc = _make_document(1, "2025-00001", "Test Doc")

        service._get_document_text = AsyncMock(return_value=None)

        pruned = await service._prune_stale_edges(mock_session, doc, company_id=1)

        assert pruned == 0


# ---------------------------------------------------------------------------
# Tests: _classify_dependency_type
# ---------------------------------------------------------------------------


class TestClassifyDependencyType:
    """Tests for dependency type classification logic."""

    def test_validates_mvp_to_urs(self, service):
        """MVP doc referencing URS requirement is classified as 'validates'."""
        ref = _make_cross_reference("requirement", "REQ-001")
        source = _make_document(1, "2025-00001", "MVP Doc", "MVP")
        target = _make_document(2, "2025-00002", "URS Doc", "URS")

        result = service._classify_dependency_type(ref, source, target)
        assert result == "validates"

    def test_validates_iq_to_urs(self, service):
        """IQ doc referencing URS requirement is classified as 'validates'."""
        ref = _make_cross_reference("requirement", "REQ-001")
        source = _make_document(1, "2025-00001", "IQ Doc", "IQ")
        target = _make_document(2, "2025-00002", "URS Doc", "URS")

        result = service._classify_dependency_type(ref, source, target)
        assert result == "validates"

    def test_implements_test_case(self, service):
        """Test case reference is classified as 'implements'."""
        ref = _make_cross_reference("test_case", "TC-00001")
        source = _make_document(1, "2025-00001", "Test Plan", "SOP")
        target = _make_document(2, "2025-00002", "URS Doc", "URS")

        result = service._classify_dependency_type(ref, source, target)
        assert result == "implements"

    def test_references_default(self, service):
        """Non-specific references default to 'references' type."""
        ref = _make_cross_reference("section", "1.2.3")
        source = _make_document(1, "2025-00001", "SOP A", "SOP")
        target = _make_document(2, "2025-00002", "SOP B", "SOP")

        result = service._classify_dependency_type(ref, source, target)
        assert result == "references"


# ---------------------------------------------------------------------------
# Tests: _compute_semantic_edges
# ---------------------------------------------------------------------------


class TestComputeSemanticEdges:
    """Tests for semantic similarity edge computation."""

    @pytest.mark.asyncio
    async def test_rejects_below_threshold(
        self, service, mock_knowledge_service
    ):
        """Semantic edges below 0.5 similarity are not created."""
        doc = _make_document(1, "2025-00001", "Source Doc")
        all_docs = [doc, _make_document(2, "2025-00002", "Target Doc")]

        # Mock: search returns result below threshold
        low_result = _make_search_result("2025-00002", 0.3, "low similarity")
        mock_knowledge_service.hybrid_search.return_value = ([low_result], 1)

        edges = await service._compute_semantic_edges(
            doc, all_docs, company_id=1, doc_text="A" * 100
        )

        assert len(edges) == 0

    @pytest.mark.asyncio
    async def test_creates_edge_above_threshold(
        self, service, mock_knowledge_service
    ):
        """Semantic edges at or above 0.5 similarity are created."""
        doc = _make_document(1, "2025-00001", "Source Doc")
        all_docs = [doc, _make_document(2, "2025-00002", "Target Doc")]

        # Mock: search returns result above threshold
        high_result = _make_search_result("2025-00002", 0.7, "high similarity")
        mock_knowledge_service.hybrid_search.return_value = ([high_result], 1)

        edges = await service._compute_semantic_edges(
            doc, all_docs, company_id=1, doc_text="A" * 100
        )

        assert len(edges) == 1
        assert edges[0]["target_document_uuid"] == "2025-00002"
        assert edges[0]["dependency_type"] == "references"
        assert 0.5 <= edges[0]["confidence_score"] <= 0.8

    @pytest.mark.asyncio
    async def test_confidence_capped_at_0_8(
        self, service, mock_knowledge_service
    ):
        """Semantic edge confidence is capped at 0.8 maximum."""
        doc = _make_document(1, "2025-00001", "Source Doc")
        all_docs = [doc, _make_document(2, "2025-00002", "Target Doc")]

        # Mock: search returns perfect similarity
        perfect_result = _make_search_result("2025-00002", 1.0, "perfect match")
        mock_knowledge_service.hybrid_search.return_value = ([perfect_result], 1)

        edges = await service._compute_semantic_edges(
            doc, all_docs, company_id=1, doc_text="A" * 100
        )

        assert len(edges) == 1
        assert edges[0]["confidence_score"] <= 0.8

    @pytest.mark.asyncio
    async def test_skips_self_references(
        self, service, mock_knowledge_service
    ):
        """Semantic edges do not include self-references."""
        doc = _make_document(1, "2025-00001", "Source Doc")
        all_docs = [doc]

        # Mock: search returns the same document
        self_result = _make_search_result("2025-00001", 0.9, "self match")
        mock_knowledge_service.hybrid_search.return_value = ([self_result], 1)

        edges = await service._compute_semantic_edges(
            doc, all_docs, company_id=1, doc_text="A" * 100
        )

        assert len(edges) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_for_short_text(
        self, service, mock_knowledge_service
    ):
        """Semantic edges are not computed for very short text (<50 chars)."""
        doc = _make_document(1, "2025-00001", "Source Doc")
        all_docs = [doc, _make_document(2, "2025-00002", "Target Doc")]

        edges = await service._compute_semantic_edges(
            doc, all_docs, company_id=1, doc_text="Short"
        )

        assert len(edges) == 0
        mock_knowledge_service.hybrid_search.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_knowledge_service_failure_gracefully(
        self, service, mock_knowledge_service
    ):
        """Semantic edge computation handles KnowledgeService errors gracefully."""
        doc = _make_document(1, "2025-00001", "Source Doc")
        all_docs = [doc, _make_document(2, "2025-00002", "Target Doc")]

        mock_knowledge_service.generate_embeddings = AsyncMock(
            side_effect=RuntimeError("Service unavailable")
        )

        edges = await service._compute_semantic_edges(
            doc, all_docs, company_id=1, doc_text="A" * 100
        )

        # Should return empty list, not raise
        assert len(edges) == 0


# ---------------------------------------------------------------------------
# Tests: _build_db_linked_edges
# ---------------------------------------------------------------------------


class TestBuildDbLinkedEdges:
    """Tests for database-linked edge construction."""

    @pytest.mark.asyncio
    async def test_creates_trains_on_edges(self, service, mock_session):
        """Creates trains_on edges from TrainingTask records."""
        # Mock: TrainingTask query returns SOP UUIDs
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = ["2025-00001", "2025-00002"]
        training_result.scalars.return_value = training_scalars

        # Mock: GenerationProvenance query (empty)
        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = []
        prov_result.scalars.return_value = prov_scalars

        mock_session.execute = AsyncMock(side_effect=[training_result, prov_result])

        edges = await service._build_db_linked_edges(mock_session, company_id=1)

        trains_on_edges = [e for e in edges if e["dependency_type"] == "trains_on"]
        assert len(trains_on_edges) == 2
        assert all(e["confidence_score"] == 0.9 for e in trains_on_edges)

    @pytest.mark.asyncio
    async def test_creates_derived_from_edges(self, service, mock_session):
        """Creates derived_from edges from GenerationProvenance records."""
        # Mock: TrainingTask query (empty)
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        # Mock: GenerationProvenance query
        prov_record = MagicMock()
        prov_record.document_id = 10
        prov_record.source_document_uuids = ["2025-00001", "2025-00002"]
        prov_record.generation_id = "gen-abc-123"

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = [prov_record]
        prov_result.scalars.return_value = prov_scalars

        # Mock: document UUID lookup for generated doc
        gen_doc_result = MagicMock()
        gen_doc_result.scalar_one_or_none.return_value = "2025-00010"

        mock_session.execute = AsyncMock(
            side_effect=[training_result, prov_result, gen_doc_result]
        )

        edges = await service._build_db_linked_edges(mock_session, company_id=1)

        derived_edges = [e for e in edges if e["dependency_type"] == "derived_from"]
        assert len(derived_edges) == 2
        assert all(e["confidence_score"] == 0.9 for e in derived_edges)
        assert all(e["target_document_uuid"] == "2025-00010" for e in derived_edges)

    @pytest.mark.asyncio
    async def test_skips_provenance_with_no_generated_doc(self, service, mock_session):
        """Skips GenerationProvenance records where generated doc UUID is not found."""
        # Mock: TrainingTask query (empty)
        training_result = MagicMock()
        training_scalars = MagicMock()
        training_scalars.all.return_value = []
        training_result.scalars.return_value = training_scalars

        # Mock: GenerationProvenance query
        prov_record = MagicMock()
        prov_record.document_id = 10
        prov_record.source_document_uuids = ["2025-00001"]
        prov_record.generation_id = "gen-abc-123"

        prov_result = MagicMock()
        prov_scalars = MagicMock()
        prov_scalars.all.return_value = [prov_record]
        prov_result.scalars.return_value = prov_scalars

        # Mock: document UUID lookup returns None
        gen_doc_result = MagicMock()
        gen_doc_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[training_result, prov_result, gen_doc_result]
        )

        edges = await service._build_db_linked_edges(mock_session, company_id=1)

        assert len(edges) == 0
