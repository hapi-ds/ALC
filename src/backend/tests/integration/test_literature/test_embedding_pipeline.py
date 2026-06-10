"""Integration tests for the embedding pipeline (Phase 9.3).

Tests end-to-end flows: StructuredContent → chunks → embeddings → indexed → searchable.
Covers hybrid search accuracy, unified search, company isolation, re-tagging,
and index lifecycle management.

Requires Docker OpenSearch (port 9200) and Redis (port 6379). Tests are skipped
when infrastructure is unavailable. The vLLM InferenceClient is mocked since
the actual model server won't be available in CI.

Requirements: 1.1, 3.1, 4.1, 4.2, 5.6, 6.1, 7.1
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from alcoabase.literature.embedding.exceptions import (
    PartitionTagUpdateError,
    TenantIsolationError,
)
from alcoabase.literature.embedding.services.chunking_pipeline import (
    ChunkingPipeline,
    ContentChunk,
)
from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridQueryEngine,
    HybridSearchRequest,
    HybridSearchResponse,
)
from alcoabase.literature.embedding.services.index_manager import (
    IndexedChunk,
    LiteratureIndexManager,
)
from alcoabase.literature.ingestion.schemas.structured_content import (
    BodySection,
    SourceFormat,
    StructuredContent,
)


# ---------------------------------------------------------------------------
# Infrastructure availability checks
# ---------------------------------------------------------------------------


def _opensearch_available() -> bool:
    """Check if OpenSearch is reachable at localhost:9200."""
    import socket

    try:
        sock = socket.create_connection(("localhost", 9200), timeout=2)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


def _redis_available() -> bool:
    """Check if Redis is reachable at localhost:6379."""
    import socket

    try:
        sock = socket.create_connection(("localhost", 6379), timeout=2)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


OPENSEARCH_AVAILABLE = _opensearch_available()
REDIS_AVAILABLE = _redis_available()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not OPENSEARCH_AVAILABLE,
        reason="OpenSearch not available at localhost:9200",
    ),
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 8  # Small dimension for fast integration tests
COMPANY_A_ID = 9001
COMPANY_B_ID = 9002
TEST_INDEX_PREFIX = "literature-embeddings"


# ---------------------------------------------------------------------------
# Mock Embedding Function
# ---------------------------------------------------------------------------


def _mock_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate a deterministic pseudo-embedding from text.

    Uses a simple hash-based approach to produce consistent vectors for the
    same input while ensuring different texts produce different vectors.
    Normalizes to unit length for cosine similarity.
    """
    # Hash-based deterministic embedding
    hash_val = hash(text)
    raw = [(hash_val * (i + 1) % 1000) / 1000.0 for i in range(dim)]
    # Normalize to unit vector for cosine similarity
    magnitude = math.sqrt(sum(x * x for x in raw))
    if magnitude == 0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / magnitude for x in raw]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def opensearch_client():
    """Create an async OpenSearch client for integration tests."""
    from opensearchpy import AsyncOpenSearch

    client = AsyncOpenSearch(
        hosts=[{"host": "localhost", "port": 9200}],
        use_ssl=False,
        verify_certs=False,
        http_compress=True,
    )
    yield client
    await client.close()


@pytest_asyncio.fixture
async def index_manager(opensearch_client) -> LiteratureIndexManager:
    """Create a LiteratureIndexManager with a real OpenSearch client."""
    manager = LiteratureIndexManager(
        opensearch_client=opensearch_client,
        embedding_dimension=EMBEDDING_DIM,
        shards=1,
        replicas=0,  # No replicas for single-node test
        hnsw_ef_construction=16,
        hnsw_m=4,
    )
    # Reduce retry intervals for tests
    manager._INDEX_CREATION_RETRY_INTERVAL_S = 1
    manager._INDEX_DELETION_RETRY_INTERVAL_S = 1
    return manager


@pytest_asyncio.fixture(autouse=True)
async def cleanup_test_indices(opensearch_client):
    """Clean up any test indices before and after each test."""
    # Cleanup before test
    for company_id in (COMPANY_A_ID, COMPANY_B_ID):
        index_name = f"{TEST_INDEX_PREFIX}-{company_id}"
        try:
            exists = await opensearch_client.indices.exists(index=index_name)
            if exists:
                await opensearch_client.indices.delete(index=index_name)
        except Exception:
            pass

    yield

    # Cleanup after test
    for company_id in (COMPANY_A_ID, COMPANY_B_ID):
        index_name = f"{TEST_INDEX_PREFIX}-{company_id}"
        try:
            exists = await opensearch_client.indices.exists(index=index_name)
            if exists:
                await opensearch_client.indices.delete(index=index_name)
        except Exception:
            pass


@pytest.fixture
def chunking_pipeline() -> ChunkingPipeline:
    """Create a ChunkingPipeline with default settings."""
    return ChunkingPipeline(
        chunk_size_tokens=512,
        chunk_overlap_tokens=50,
        max_context_tokens=64,
    )


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient that generates deterministic embeddings."""
    client = AsyncMock()

    async def _create_embeddings(model: str, inputs: list[str]) -> list[list[float]]:
        return [_mock_embedding(text) for text in inputs]

    client.create_embeddings = AsyncMock(side_effect=_create_embeddings)
    return client


@pytest.fixture
def sample_structured_content() -> StructuredContent:
    """Create a sample StructuredContent for testing."""
    title = "Machine Learning Applications in Pharmaceutical Manufacturing"
    abstract = (
        "This study presents novel machine learning approaches for quality control "
        "in pharmaceutical manufacturing processes. We demonstrate improved yield "
        "prediction using deep neural networks trained on historical batch data."
    )
    body_sections = [
        BodySection(
            heading="Introduction",
            text=(
                "Pharmaceutical manufacturing faces increasing pressure to improve "
                "efficiency while maintaining strict quality standards. Machine learning "
                "offers promising solutions for process optimization and quality prediction."
            ),
        ),
        BodySection(
            heading="Methods",
            text=(
                "We collected historical batch records from three manufacturing sites "
                "spanning five years of production data. Features were extracted from "
                "critical process parameters including temperature, pressure, and pH."
            ),
        ),
        BodySection(
            heading="Results",
            text=(
                "The deep learning model achieved 94.5% accuracy in predicting batch "
                "quality outcomes. This represents a significant improvement over "
                "traditional statistical process control methods."
            ),
        ),
    ]
    raw_plaintext = "\n".join(
        [title, abstract, *[s.text for s in body_sections]]
    )
    word_count = len(raw_plaintext.split())

    return StructuredContent(
        source_format=SourceFormat.PDF,
        extracted_title=title,
        extracted_abstract=abstract,
        body_sections=body_sections,
        references=["Smith et al. 2023", "Jones et al. 2022"],
        figure_count=3,
        table_count=2,
        word_count=word_count,
        raw_plaintext=raw_plaintext,
    )


def _build_indexed_chunks(
    chunks: list[ContentChunk],
    company_id: int,
    record_id: int,
    partition_tag: str = "public_literature",
    title: str = "Test Paper",
    doi: str | None = "10.1000/test",
) -> list[IndexedChunk]:
    """Helper to build IndexedChunk list from ContentChunks."""
    return [
        IndexedChunk(
            embedding_vector=_mock_embedding(chunk.text),
            chunk_text=chunk.text,
            title=title,
            abstract_snippet="Test abstract snippet for paper",
            authors=["Smith, J.", "Doe, J."],
            doi=doi,
            publication_date="2024-03-15",
            source_id="pubmed",
            external_id=f"PM{record_id:06d}",
            ingestion_record_id=record_id,
            company_id=company_id,
            partition_tag=partition_tag,
            section_heading=chunk.section_heading,
            chunk_index=chunk.chunk_index,
        )
        for chunk in chunks
    ]


# ---------------------------------------------------------------------------
# Test: End-to-End Pipeline (StructuredContent → chunks → embeddings → indexed → searchable)
# Requirement 1.1
# ---------------------------------------------------------------------------


class TestEndToEndEmbeddingPipeline:
    """Test the full embedding pipeline from StructuredContent to searchable index."""

    @pytest.mark.asyncio
    async def test_structured_content_to_searchable(
        self,
        index_manager: LiteratureIndexManager,
        chunking_pipeline: ChunkingPipeline,
        sample_structured_content: StructuredContent,
        opensearch_client,
    ) -> None:
        """End-to-end: StructuredContent → chunks → embeddings → indexed → searchable.

        Requirement 1.1: WHEN an Ingestion_Record transitions to sanitized,
        the Embedding_Service SHALL dispatch an Embedding_Task to generate
        embeddings for all Content_Chunks.
        """
        # Step 1: Chunk the structured content
        chunks = chunking_pipeline.chunk_structured_content(
            sample_structured_content, max_chunks=500
        )
        assert len(chunks) > 0, "Should produce at least one chunk"

        # Step 2: Generate embeddings (mocked)
        embeddings = [_mock_embedding(chunk.text) for chunk in chunks]
        assert len(embeddings) == len(chunks)
        for emb in embeddings:
            assert len(emb) == EMBEDDING_DIM

        # Step 3: Build indexed chunks
        record_id = 1001
        indexed_chunks = _build_indexed_chunks(
            chunks, COMPANY_A_ID, record_id, title=sample_structured_content.extracted_title
        )

        # Step 4: Index into OpenSearch
        indexed_count = await index_manager.bulk_index_chunks(COMPANY_A_ID, indexed_chunks)
        assert indexed_count == len(chunks)

        # Step 5: Verify searchable via BM25
        index_name = index_manager._index_name(COMPANY_A_ID)
        search_response = await opensearch_client.search(
            index=index_name,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"chunk_text": "machine learning"}},
                            {"term": {"company_id": COMPANY_A_ID}},
                        ]
                    }
                }
            },
        )
        hits = search_response["hits"]["hits"]
        assert len(hits) > 0, "Should find results for 'machine learning'"

        # Verify metadata on first hit
        first_hit = hits[0]["_source"]
        assert first_hit["company_id"] == COMPANY_A_ID
        assert first_hit["ingestion_record_id"] == record_id
        assert first_hit["partition_tag"] == "public_literature"
        assert first_hit["title"] == sample_structured_content.extracted_title

    @pytest.mark.asyncio
    async def test_knn_search_after_indexing(
        self,
        index_manager: LiteratureIndexManager,
        chunking_pipeline: ChunkingPipeline,
        sample_structured_content: StructuredContent,
        opensearch_client,
    ) -> None:
        """kNN vector search returns results after embedding indexing.

        Requirement 3.1: THE Literature_Index_Manager SHALL create one
        OpenSearch index per company using the naming convention
        literature-embeddings-{company_id}.
        """
        chunks = chunking_pipeline.chunk_structured_content(
            sample_structured_content, max_chunks=500
        )
        indexed_chunks = _build_indexed_chunks(chunks, COMPANY_A_ID, 1002)
        await index_manager.bulk_index_chunks(COMPANY_A_ID, indexed_chunks)

        # Search using kNN with a query vector
        query_text = "pharmaceutical quality control"
        query_vector = _mock_embedding(query_text)

        index_name = index_manager._index_name(COMPANY_A_ID)
        knn_response = await opensearch_client.search(
            index=index_name,
            body={
                "size": 5,
                "query": {
                    "knn": {
                        "embedding_vector": {
                            "vector": query_vector,
                            "k": 5,
                        }
                    }
                },
            },
        )
        knn_hits = knn_response["hits"]["hits"]
        assert len(knn_hits) > 0, "kNN search should return results"

        # Each result should have a score
        for hit in knn_hits:
            assert hit["_score"] > 0

    @pytest.mark.asyncio
    async def test_index_stats_after_population(
        self,
        index_manager: LiteratureIndexManager,
        chunking_pipeline: ChunkingPipeline,
        sample_structured_content: StructuredContent,
    ) -> None:
        """Index stats reflect document count after indexing."""
        chunks = chunking_pipeline.chunk_structured_content(
            sample_structured_content, max_chunks=500
        )
        indexed_chunks = _build_indexed_chunks(chunks, COMPANY_A_ID, 1003)
        count = await index_manager.bulk_index_chunks(COMPANY_A_ID, indexed_chunks)

        stats = await index_manager.get_index_stats(COMPANY_A_ID)
        assert stats["health"] in ("green", "yellow")
        assert stats["doc_count"] == count
        assert stats["size_bytes"] > 0


# ---------------------------------------------------------------------------
# Test: Hybrid Search Accuracy (BM25 + kNN merge)
# Requirement 6.1
# ---------------------------------------------------------------------------


class TestHybridSearchAccuracy:
    """Test that hybrid search correctly merges BM25 and kNN results."""

    @pytest.mark.asyncio
    async def test_hybrid_search_returns_relevant_results(
        self,
        index_manager: LiteratureIndexManager,
        mock_inference_client: AsyncMock,
        opensearch_client,
    ) -> None:
        """Hybrid search returns results combining BM25 keyword and kNN semantic.

        Requirement 6.1: THE Hybrid_Query_Engine SHALL execute both a BM25
        keyword search and a kNN semantic search, combining results using RRF.
        """
        # Index multiple documents with distinct content
        docs = [
            ("Machine learning for drug discovery", "public_literature", 2001),
            ("Statistical methods in clinical trials", "public_literature", 2002),
            ("Deep learning protein folding prediction", "public_literature", 2003),
            ("Quality control process automation", "private_knowledge", 2004),
        ]

        for text, tag, record_id in docs:
            chunk = IndexedChunk(
                embedding_vector=_mock_embedding(text),
                chunk_text=text,
                title=text,
                abstract_snippet=text[:100],
                authors=["Test Author"],
                doi=f"10.1000/test-{record_id}",
                publication_date="2024-01-15",
                source_id="pubmed",
                external_id=f"EXT{record_id}",
                ingestion_record_id=record_id,
                company_id=COMPANY_A_ID,
                partition_tag=tag,
                section_heading="",
                chunk_index=0,
            )
            await index_manager.bulk_index_chunks(COMPANY_A_ID, [chunk])

        # Create the hybrid query engine
        mock_model_manager = MagicMock()
        engine = HybridQueryEngine(
            index_manager=index_manager,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            model_name="test-embedding-model",
            default_rrf_k=60,
        )

        # Search for "machine learning drug"
        request = HybridSearchRequest(
            query="machine learning drug",
            company_id=COMPANY_A_ID,
            user_id=1,
            page=1,
            page_size=10,
            semantic_weight=0.5,
        )
        response = await engine.search(request)

        assert isinstance(response, HybridSearchResponse)
        assert response.total_count > 0
        assert len(response.results) > 0
        assert not response.degraded_mode

        # The first result should be the most relevant to "machine learning drug"
        # (BM25 will favor exact keyword match)
        top_result = response.results[0]
        assert "machine learning" in top_result.chunk_text.lower() or (
            "drug" in top_result.chunk_text.lower()
        )

    @pytest.mark.asyncio
    async def test_bm25_only_fallback_when_embedding_fails(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Falls back to BM25-only search when vLLM is unavailable.

        Requirement 6.8: IF the vLLM embedding instance is unavailable,
        THEN fall back to BM25-only search with degraded_mode: true.
        """
        # Index a document
        chunk = IndexedChunk(
            embedding_vector=_mock_embedding("test document for BM25 fallback"),
            chunk_text="test document for BM25 fallback",
            title="BM25 Fallback Test",
            abstract_snippet="BM25 fallback testing",
            authors=["Author"],
            doi="10.1000/bm25",
            publication_date="2024-01-15",
            source_id="pubmed",
            external_id="BM25001",
            ingestion_record_id=3001,
            company_id=COMPANY_A_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )
        await index_manager.bulk_index_chunks(COMPANY_A_ID, [chunk])

        # Create engine with failing inference client
        failing_client = AsyncMock()
        failing_client.create_embeddings = AsyncMock(
            side_effect=ConnectionError("vLLM unavailable")
        )
        mock_model_manager = MagicMock()

        engine = HybridQueryEngine(
            index_manager=index_manager,
            inference_client=failing_client,
            model_manager=mock_model_manager,
            model_name="test-model",
            default_rrf_k=60,
        )

        request = HybridSearchRequest(
            query="BM25 fallback",
            company_id=COMPANY_A_ID,
            user_id=1,
            page=1,
            page_size=10,
        )
        response = await engine.search(request)

        assert response.degraded_mode is True
        assert response.total_count > 0
        assert len(response.results) > 0


# ---------------------------------------------------------------------------
# Test: Unified Search Across Both Indices
# Requirement 7.1
# ---------------------------------------------------------------------------


class TestUnifiedSearch:
    """Test unified search across literature and internal document indices."""

    @pytest.mark.asyncio
    async def test_unified_search_includes_both_partitions(
        self,
        index_manager: LiteratureIndexManager,
        mock_inference_client: AsyncMock,
        opensearch_client,
    ) -> None:
        """Unified search queries both literature and internal documents.

        Requirement 7.1: THE Hybrid_Query_Engine SHALL support a unified
        search mode that queries both the literature index and the existing
        internal document index within a single request.
        """
        # Index public literature
        lit_chunk = IndexedChunk(
            embedding_vector=_mock_embedding("regulatory compliance GMP guidelines"),
            chunk_text="regulatory compliance GMP guidelines for manufacturing",
            title="GMP Compliance Literature Review",
            abstract_snippet="A review of GMP compliance",
            authors=["Regulatory Expert"],
            doi="10.1000/gmp",
            publication_date="2024-02-20",
            source_id="pubmed",
            external_id="GMP001",
            ingestion_record_id=4001,
            company_id=COMPANY_A_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )

        # Index private knowledge
        internal_chunk = IndexedChunk(
            embedding_vector=_mock_embedding("internal SOP for GMP compliance audit"),
            chunk_text="internal SOP for GMP compliance audit procedures",
            title="Internal GMP Audit SOP",
            abstract_snippet="Internal audit procedures",
            authors=["QA Team"],
            doi=None,
            publication_date="2024-03-01",
            source_id=None,
            external_id="INT001",
            ingestion_record_id=4002,
            company_id=COMPANY_A_ID,
            partition_tag="private_knowledge",
            section_heading="Procedures",
            chunk_index=0,
        )

        await index_manager.bulk_index_chunks(COMPANY_A_ID, [lit_chunk, internal_chunk])

        # Create engine
        mock_model_manager = MagicMock()
        engine = HybridQueryEngine(
            index_manager=index_manager,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            model_name="test-model",
            default_rrf_k=60,
        )

        # Unified search
        request = HybridSearchRequest(
            query="GMP compliance",
            company_id=COMPANY_A_ID,
            user_id=1,
            page=1,
            page_size=10,
            include_internal=True,
        )
        response = await engine.unified_search(request)

        assert response.total_count >= 2
        # Should have results from both partitions
        partition_tags = {r.partition_tag for r in response.results}
        assert "public_literature" in partition_tags
        assert "private_knowledge" in partition_tags

    @pytest.mark.asyncio
    async def test_unified_search_partition_filter(
        self,
        index_manager: LiteratureIndexManager,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Unified search respects partition_filter parameter.

        Requirement 5.3: THE Hybrid_Query_Engine SHALL accept a
        partition_filter parameter.
        """
        # Index both types
        chunks = [
            IndexedChunk(
                embedding_vector=_mock_embedding("literature content about vaccines"),
                chunk_text="literature content about vaccines",
                title="Vaccine Research",
                abstract_snippet="Vaccine literature",
                authors=["Researcher"],
                doi="10.1000/vax",
                publication_date="2024-01-01",
                source_id="pubmed",
                external_id="VAX001",
                ingestion_record_id=5001,
                company_id=COMPANY_A_ID,
                partition_tag="public_literature",
                section_heading="",
                chunk_index=0,
            ),
            IndexedChunk(
                embedding_vector=_mock_embedding("private vaccine production SOP"),
                chunk_text="private vaccine production SOP",
                title="Vaccine Production SOP",
                abstract_snippet="Internal SOP",
                authors=["QA"],
                doi=None,
                publication_date="2024-01-15",
                source_id=None,
                external_id="INT_VAX",
                ingestion_record_id=5002,
                company_id=COMPANY_A_ID,
                partition_tag="private_knowledge",
                section_heading="",
                chunk_index=0,
            ),
        ]
        await index_manager.bulk_index_chunks(COMPANY_A_ID, chunks)

        mock_model_manager = MagicMock()
        engine = HybridQueryEngine(
            index_manager=index_manager,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            model_name="test-model",
            default_rrf_k=60,
        )

        # Filter to only public_literature
        request = HybridSearchRequest(
            query="vaccine",
            company_id=COMPANY_A_ID,
            user_id=1,
            partition_filter="public_literature",
            page=1,
            page_size=10,
            include_internal=True,
        )
        response = await engine.unified_search(request)

        # All results should be public_literature only
        for result in response.results:
            assert result.partition_tag == "public_literature"


# ---------------------------------------------------------------------------
# Test: Company Index Isolation
# Requirements 4.1, 4.2
# ---------------------------------------------------------------------------


class TestCompanyIndexIsolation:
    """Test that company A's data is not visible to company B."""

    @pytest.mark.asyncio
    async def test_company_a_data_not_visible_to_company_b(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Data indexed for company A is NOT searchable by company B.

        Requirement 4.1: THE Literature_Index_Manager SHALL enforce that
        all indexing operations include the company_id field matching the
        authenticated company context.

        Requirement 4.2: THE Literature_Index_Manager SHALL enforce that
        all search operations query only the index belonging to the
        requesting company.
        """
        # Index data for Company A
        chunk_a = IndexedChunk(
            embedding_vector=_mock_embedding("confidential company A data"),
            chunk_text="confidential company A proprietary research data",
            title="Company A Secret Research",
            abstract_snippet="Top secret",
            authors=["A Researcher"],
            doi="10.1000/company-a",
            publication_date="2024-01-01",
            source_id="internal",
            external_id="A001",
            ingestion_record_id=6001,
            company_id=COMPANY_A_ID,
            partition_tag="private_knowledge",
            section_heading="",
            chunk_index=0,
        )
        await index_manager.bulk_index_chunks(COMPANY_A_ID, [chunk_a])

        # Index data for Company B
        chunk_b = IndexedChunk(
            embedding_vector=_mock_embedding("company B public data"),
            chunk_text="company B published research findings",
            title="Company B Research",
            abstract_snippet="B research",
            authors=["B Researcher"],
            doi="10.1000/company-b",
            publication_date="2024-02-01",
            source_id="pubmed",
            external_id="B001",
            ingestion_record_id=6002,
            company_id=COMPANY_B_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )
        await index_manager.bulk_index_chunks(COMPANY_B_ID, [chunk_b])

        # Search Company B's index — should NOT see Company A's data
        index_b = index_manager._index_name(COMPANY_B_ID)
        search_response = await opensearch_client.search(
            index=index_b,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"chunk_text": "confidential company A"}},
                            {"term": {"company_id": COMPANY_B_ID}},
                        ]
                    }
                }
            },
        )
        hits = search_response["hits"]["hits"]
        assert len(hits) == 0, "Company A data should NOT appear in Company B's index"

        # Search Company A's index — should NOT see Company B's data
        index_a = index_manager._index_name(COMPANY_A_ID)
        search_response = await opensearch_client.search(
            index=index_a,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"chunk_text": "company B published research"}},
                            {"term": {"company_id": COMPANY_A_ID}},
                        ]
                    }
                }
            },
        )
        hits = search_response["hits"]["hits"]
        assert len(hits) == 0, "Company B data should NOT appear in Company A's index"

    @pytest.mark.asyncio
    async def test_cross_tenant_indexing_rejected(
        self,
        index_manager: LiteratureIndexManager,
    ) -> None:
        """Indexing chunks with mismatched company_id raises TenantIsolationError.

        Requirement 4.1: Before writing any document, validate that the
        document's company_id equals the target company_id.
        """
        # Try to index a chunk with company_id=B into company A's index
        malicious_chunk = IndexedChunk(
            embedding_vector=_mock_embedding("malicious cross-tenant"),
            chunk_text="should not be indexed here",
            title="Malicious",
            abstract_snippet="Bad",
            authors=["Attacker"],
            doi=None,
            publication_date="2024-01-01",
            source_id="internal",
            external_id="MAL001",
            ingestion_record_id=7001,
            company_id=COMPANY_B_ID,  # Mismatched!
            partition_tag="private_knowledge",
            section_heading="",
            chunk_index=0,
        )

        with pytest.raises(TenantIsolationError):
            await index_manager.bulk_index_chunks(COMPANY_A_ID, [malicious_chunk])

    @pytest.mark.asyncio
    async def test_separate_indices_per_company(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Each company gets its own physical OpenSearch index.

        Requirement 3.1: THE Literature_Index_Manager SHALL create one
        OpenSearch index per company.
        """
        # Ensure indices for both companies
        await index_manager.ensure_index_exists(COMPANY_A_ID)
        await index_manager.ensure_index_exists(COMPANY_B_ID)

        # Verify both exist as separate indices
        index_a = index_manager._index_name(COMPANY_A_ID)
        index_b = index_manager._index_name(COMPANY_B_ID)

        assert await opensearch_client.indices.exists(index=index_a)
        assert await opensearch_client.indices.exists(index=index_b)
        assert index_a != index_b


# ---------------------------------------------------------------------------
# Test: Re-tagging (Atomic partition_tag update)
# Requirement 5.6
# ---------------------------------------------------------------------------


class TestRetagging:
    """Test atomic partition_tag updates for ingestion records."""

    @pytest.mark.asyncio
    async def test_retag_public_to_private(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Re-tagging updates all chunks for a record atomically.

        Requirement 5.6: WHEN a re-tagging request is submitted,
        THE Literature_Index_Manager SHALL atomically update the
        partition_tag for all Content_Chunks belonging to that record.
        """
        record_id = 8001

        # Index multiple chunks for a single record as public_literature
        chunks = [
            IndexedChunk(
                embedding_vector=_mock_embedding(f"chunk {i} content for retagging"),
                chunk_text=f"chunk {i} content for retagging test",
                title="Retag Test Paper",
                abstract_snippet="Retagging test",
                authors=["Author"],
                doi="10.1000/retag",
                publication_date="2024-03-01",
                source_id="pubmed",
                external_id="RETAG001",
                ingestion_record_id=record_id,
                company_id=COMPANY_A_ID,
                partition_tag="public_literature",
                section_heading=f"Section {i}",
                chunk_index=i,
            )
            for i in range(5)
        ]
        await index_manager.bulk_index_chunks(COMPANY_A_ID, chunks)

        # Re-tag from public_literature to private_knowledge
        updated = await index_manager.update_partition_tags(
            company_id=COMPANY_A_ID,
            ingestion_record_id=record_id,
            new_tag="private_knowledge",
        )
        assert updated == 5

        # Verify all chunks now have private_knowledge tag
        index_name = index_manager._index_name(COMPANY_A_ID)
        search_response = await opensearch_client.search(
            index=index_name,
            body={
                "query": {
                    "term": {"ingestion_record_id": record_id}
                },
                "size": 10,
            },
        )
        hits = search_response["hits"]["hits"]
        assert len(hits) == 5
        for hit in hits:
            assert hit["_source"]["partition_tag"] == "private_knowledge"

    @pytest.mark.asyncio
    async def test_retag_does_not_affect_other_records(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Re-tagging one record does not modify other records.

        Only chunks belonging to the specified ingestion_record_id
        should be updated.
        """
        record_a = 8010
        record_b = 8011

        # Index chunks for two different records
        chunk_a = IndexedChunk(
            embedding_vector=_mock_embedding("record A content"),
            chunk_text="record A content to retag",
            title="Record A",
            abstract_snippet="A",
            authors=["A"],
            doi="10.1000/a",
            publication_date="2024-01-01",
            source_id="pubmed",
            external_id="A010",
            ingestion_record_id=record_a,
            company_id=COMPANY_A_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )
        chunk_b = IndexedChunk(
            embedding_vector=_mock_embedding("record B content"),
            chunk_text="record B content should stay public",
            title="Record B",
            abstract_snippet="B",
            authors=["B"],
            doi="10.1000/b",
            publication_date="2024-01-01",
            source_id="pubmed",
            external_id="B010",
            ingestion_record_id=record_b,
            company_id=COMPANY_A_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )
        await index_manager.bulk_index_chunks(COMPANY_A_ID, [chunk_a, chunk_b])

        # Retag only record A
        await index_manager.update_partition_tags(
            company_id=COMPANY_A_ID,
            ingestion_record_id=record_a,
            new_tag="private_knowledge",
        )

        # Verify record B is still public_literature
        index_name = index_manager._index_name(COMPANY_A_ID)
        search_response = await opensearch_client.search(
            index=index_name,
            body={
                "query": {"term": {"ingestion_record_id": record_b}},
            },
        )
        hits = search_response["hits"]["hits"]
        assert len(hits) == 1
        assert hits[0]["_source"]["partition_tag"] == "public_literature"


# ---------------------------------------------------------------------------
# Test: Index Lifecycle (create → populate → delete on company removal)
# Requirements 3.1, 4.6
# ---------------------------------------------------------------------------


class TestIndexLifecycle:
    """Test index creation, population, and deletion on company removal."""

    @pytest.mark.asyncio
    async def test_index_created_on_first_indexing(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Index is automatically created when first chunk is indexed.

        Requirement 3.4: WHEN the Literature_Index_Manager receives a
        request to index documents for a company whose index does not yet
        exist, it SHALL create the company's index before proceeding.
        """
        # Verify index doesn't exist yet
        index_name = index_manager._index_name(COMPANY_A_ID)
        exists = await opensearch_client.indices.exists(index=index_name)
        assert not exists

        # Index a chunk — should trigger index creation
        chunk = IndexedChunk(
            embedding_vector=_mock_embedding("auto create index test"),
            chunk_text="auto create index test",
            title="Auto Create",
            abstract_snippet="Test",
            authors=["Author"],
            doi=None,
            publication_date="2024-01-01",
            source_id="pubmed",
            external_id="AUTO001",
            ingestion_record_id=9001,
            company_id=COMPANY_A_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )
        await index_manager.bulk_index_chunks(COMPANY_A_ID, [chunk])

        # Verify index now exists
        exists = await opensearch_client.indices.exists(index=index_name)
        assert exists

    @pytest.mark.asyncio
    async def test_index_already_exists_skips_creation(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Ensure_index_exists is idempotent — doesn't fail if index exists.

        Requirement 3.8: IF the index already exists when creation is
        triggered, THEN skip creation without error.
        """
        await index_manager.ensure_index_exists(COMPANY_A_ID)
        # Second call should not raise
        await index_manager.ensure_index_exists(COMPANY_A_ID)

        index_name = index_manager._index_name(COMPANY_A_ID)
        exists = await opensearch_client.indices.exists(index=index_name)
        assert exists

    @pytest.mark.asyncio
    async def test_delete_company_index_removes_all_data(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Deleting a company index removes all its data.

        Requirement 4.6: WHEN a company is deleted or deactivated,
        THE Literature_Index_Manager SHALL delete the entire company's
        OpenSearch index.
        """
        # Index some data
        chunk = IndexedChunk(
            embedding_vector=_mock_embedding("data to be deleted"),
            chunk_text="data that should be deleted on company removal",
            title="Delete Test",
            abstract_snippet="Delete",
            authors=["Author"],
            doi=None,
            publication_date="2024-01-01",
            source_id="pubmed",
            external_id="DEL001",
            ingestion_record_id=9101,
            company_id=COMPANY_A_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )
        await index_manager.bulk_index_chunks(COMPANY_A_ID, [chunk])

        # Verify index exists with data
        index_name = index_manager._index_name(COMPANY_A_ID)
        assert await opensearch_client.indices.exists(index=index_name)

        # Delete the company index
        result = await index_manager.delete_company_index(COMPANY_A_ID)
        assert result is True

        # Verify index no longer exists
        exists = await opensearch_client.indices.exists(index=index_name)
        assert not exists

    @pytest.mark.asyncio
    async def test_delete_nonexistent_index_succeeds(
        self,
        index_manager: LiteratureIndexManager,
    ) -> None:
        """Deleting a non-existent index returns True without error."""
        result = await index_manager.delete_company_index(99999)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_record_chunks_removes_only_target(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Deleting chunks by record_id removes only that record's data.

        Other records' chunks should remain untouched.
        """
        record_to_delete = 9201
        record_to_keep = 9202

        chunks = [
            IndexedChunk(
                embedding_vector=_mock_embedding(f"delete me {i}"),
                chunk_text=f"chunk to delete {i}",
                title="Delete Target",
                abstract_snippet="Delete",
                authors=["A"],
                doi=None,
                publication_date="2024-01-01",
                source_id="pubmed",
                external_id=f"DEL{i}",
                ingestion_record_id=record_to_delete,
                company_id=COMPANY_A_ID,
                partition_tag="public_literature",
                section_heading="",
                chunk_index=i,
            )
            for i in range(3)
        ]
        keep_chunk = IndexedChunk(
            embedding_vector=_mock_embedding("keep me"),
            chunk_text="this chunk should remain",
            title="Keep",
            abstract_snippet="Keep",
            authors=["B"],
            doi=None,
            publication_date="2024-01-01",
            source_id="pubmed",
            external_id="KEEP001",
            ingestion_record_id=record_to_keep,
            company_id=COMPANY_A_ID,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )
        await index_manager.bulk_index_chunks(COMPANY_A_ID, chunks + [keep_chunk])

        # Delete record_to_delete
        deleted = await index_manager.delete_record_chunks(COMPANY_A_ID, record_to_delete)
        assert deleted == 3

        # Verify kept record still exists
        index_name = index_manager._index_name(COMPANY_A_ID)
        search_response = await opensearch_client.search(
            index=index_name,
            body={
                "query": {"term": {"ingestion_record_id": record_to_keep}},
            },
        )
        hits = search_response["hits"]["hits"]
        assert len(hits) == 1
        assert hits[0]["_source"]["chunk_text"] == "this chunk should remain"

    @pytest.mark.asyncio
    async def test_index_mapping_has_knn_vector_field(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
    ) -> None:
        """Created index has kNN vector field with HNSW configuration.

        Requirement 3.3: THE Literature_Index_Manager SHALL configure the
        kNN vector field to use the HNSW algorithm.
        """
        await index_manager.ensure_index_exists(COMPANY_A_ID)

        index_name = index_manager._index_name(COMPANY_A_ID)
        mapping = await opensearch_client.indices.get_mapping(index=index_name)
        properties = mapping[index_name]["mappings"]["properties"]

        # Verify knn_vector field
        assert "embedding_vector" in properties
        assert properties["embedding_vector"]["type"] == "knn_vector"
        assert properties["embedding_vector"]["dimension"] == EMBEDDING_DIM

        # Verify BM25 text fields
        assert properties["chunk_text"]["type"] == "text"
        assert properties["title"]["type"] == "text"

        # Verify metadata fields
        assert properties["company_id"]["type"] == "integer"
        assert properties["partition_tag"]["type"] == "keyword"
        assert properties["ingestion_record_id"]["type"] == "integer"
