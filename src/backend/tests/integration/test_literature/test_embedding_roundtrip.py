"""Integration tests for embedding vector round-trip and self-retrieval.

**Property 14: Embedding vector round-trip precision**
Generate embedding, store in OpenSearch, retrieve and compare element-by-element
(tolerance < 1e-6).

**Property 15: Self-retrieval property**
Index text, search with same text, assert top-1 result with similarity ≈ 1.0.

These tests require Docker OpenSearch. When OpenSearch is unavailable, tests are
skipped automatically. A deterministic mock embedding function is used in place
of vLLM to ensure reproducibility without GPU infrastructure.

**Validates: Requirements 14.1, 14.3**
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import uuid

import pytest

from alcoabase.literature.embedding.services.index_manager import (
    IndexedChunk,
    LiteratureIndexManager,
)


# ---------------------------------------------------------------------------
# Helpers: Deterministic mock embedding function
# ---------------------------------------------------------------------------

EMBEDDING_DIMENSION = 128  # Use smaller dimension for fast tests


def deterministic_embedding(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    """Generate a deterministic embedding vector from text using hashing.

    Uses SHA-256 hash of the text to seed a sequence of floats, then
    L2-normalizes the vector so cosine similarity of identical vectors = 1.0.

    Args:
        text: Input text to embed.
        dimension: Number of dimensions for the output vector.

    Returns:
        Normalized float vector of the given dimension.
    """
    # Generate enough hash bytes to fill the dimension
    raw_bytes = b""
    for i in range(math.ceil(dimension * 4 / 32)):
        raw_bytes += hashlib.sha256(f"{text}:{i}".encode()).digest()

    # Convert bytes to floats in [-1, 1]
    vector: list[float] = []
    for j in range(dimension):
        # Take 4 bytes, interpret as unsigned int, map to [-1, 1]
        chunk = raw_bytes[j * 4 : (j + 1) * 4]
        val = int.from_bytes(chunk, "little") / (2**32 - 1)
        vector.append(val * 2.0 - 1.0)

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]

    return vector


# ---------------------------------------------------------------------------
# OpenSearch availability check
# ---------------------------------------------------------------------------


def _opensearch_available() -> bool:
    """Check if OpenSearch is reachable at localhost:9200."""
    try:
        import httpx

        response = httpx.get("http://localhost:9200", timeout=3.0)
        return response.status_code == 200
    except Exception:
        return False


OPENSEARCH_AVAILABLE = _opensearch_available()
SKIP_REASON = "OpenSearch not available at localhost:9200 (Docker not running)"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def opensearch_client():
    """Create an AsyncOpenSearch client for integration tests."""
    from opensearchpy import AsyncOpenSearch

    client = AsyncOpenSearch(
        hosts=[{"host": "localhost", "port": 9200}],
        use_ssl=False,
        verify_certs=False,
        http_auth=("admin", "admin"),
    )
    yield client
    await client.close()


@pytest.fixture
async def index_manager(opensearch_client) -> LiteratureIndexManager:
    """Create a LiteratureIndexManager with real OpenSearch client."""
    return LiteratureIndexManager(
        opensearch_client=opensearch_client,
        embedding_dimension=EMBEDDING_DIMENSION,
        shards=1,
        replicas=0,  # No replicas for single-node test
        hnsw_ef_construction=128,
        hnsw_m=16,
    )


@pytest.fixture
async def test_company_id() -> int:
    """Generate a unique company_id for test isolation."""
    # Use a large random ID to avoid collisions
    return int(uuid.uuid4().int % 1_000_000) + 900_000


@pytest.fixture(autouse=True)
async def cleanup_test_index(opensearch_client, test_company_id):
    """Clean up any test indices after each test."""
    yield
    index_name = f"literature-embeddings-{test_company_id}"
    try:
        exists = await opensearch_client.indices.exists(index=index_name)
        if exists:
            await opensearch_client.indices.delete(index=index_name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test: Property 14 — Embedding Vector Round-Trip Precision
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(not OPENSEARCH_AVAILABLE, reason=SKIP_REASON)
class TestEmbeddingVectorRoundTrip:
    """Property 14: Embedding vector round-trip precision.

    Generate embedding, store in OpenSearch, retrieve and compare
    element-by-element (tolerance < 1e-6).

    **Validates: Requirements 14.1**
    """

    @pytest.mark.asyncio
    async def test_single_vector_roundtrip_precision(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
        test_company_id: int,
    ) -> None:
        """Store a known vector, retrieve it, verify element-by-element precision."""
        text = "Machine learning in pharmaceutical drug discovery processes."
        original_vector = deterministic_embedding(text)

        # Index the chunk
        chunk = IndexedChunk(
            embedding_vector=original_vector,
            chunk_text=text,
            title="Test Document",
            abstract_snippet="Test abstract",
            authors=["Smith, J."],
            doi="10.1000/test001",
            publication_date="2024-06-15",
            source_id="test",
            external_id="TEST001",
            ingestion_record_id=1,
            company_id=test_company_id,
            partition_tag="public_literature",
            section_heading="Introduction",
            chunk_index=0,
        )

        await index_manager.bulk_index_chunks(test_company_id, [chunk])

        # Retrieve the stored vector via _source
        index_name = index_manager._index_name(test_company_id)
        response = await opensearch_client.search(
            index=index_name,
            body={
                "query": {
                    "term": {"ingestion_record_id": 1}
                },
                "_source": ["embedding_vector"],
            },
        )

        hits = response["hits"]["hits"]
        assert len(hits) == 1, f"Expected 1 hit, got {len(hits)}"

        stored_vector = hits[0]["_source"]["embedding_vector"]

        # Compare element-by-element with tolerance < 1e-6
        assert len(stored_vector) == len(original_vector), (
            f"Dimension mismatch: stored={len(stored_vector)}, "
            f"original={len(original_vector)}"
        )

        for i, (original, stored) in enumerate(zip(original_vector, stored_vector)):
            diff = abs(original - stored)
            assert diff < 1e-6, (
                f"Element {i} differs by {diff}: "
                f"original={original}, stored={stored}"
            )

    @pytest.mark.asyncio
    async def test_multiple_vectors_roundtrip_precision(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
        test_company_id: int,
    ) -> None:
        """Store multiple vectors, retrieve all, verify each matches original."""
        texts = [
            "Short text for testing embedding precision.",
            "A moderately longer piece of text that discusses the implications "
            "of using high-dimensional vector spaces for document retrieval in "
            "regulated pharmaceutical environments.",
            "Temperature control is critical during the lyophilization process. "
            "The primary drying phase must maintain product temperature below "
            "the collapse temperature to preserve cake structure and ensure "
            "long-term stability of the biologic drug product.",
        ]

        original_vectors = [deterministic_embedding(t) for t in texts]

        chunks = [
            IndexedChunk(
                embedding_vector=original_vectors[i],
                chunk_text=texts[i],
                title="Multi-Vector Test",
                abstract_snippet="Testing multiple vectors",
                authors=["Doe, A."],
                doi=f"10.1000/multi{i}",
                publication_date="2024-01-10",
                source_id="test",
                external_id=f"MULTI{i}",
                ingestion_record_id=100 + i,
                company_id=test_company_id,
                partition_tag="public_literature",
                section_heading="Results",
                chunk_index=i,
            )
            for i in range(len(texts))
        ]

        await index_manager.bulk_index_chunks(test_company_id, chunks)

        # Retrieve all vectors
        index_name = index_manager._index_name(test_company_id)
        response = await opensearch_client.search(
            index=index_name,
            body={
                "query": {"match_all": {}},
                "_source": ["embedding_vector", "ingestion_record_id"],
                "size": 10,
            },
        )

        hits = response["hits"]["hits"]
        assert len(hits) == 3, f"Expected 3 hits, got {len(hits)}"

        # Match each stored vector to its original by record_id
        for hit in hits:
            record_id = hit["_source"]["ingestion_record_id"]
            idx = record_id - 100
            stored_vector = hit["_source"]["embedding_vector"]
            original = original_vectors[idx]

            assert len(stored_vector) == len(original)
            for j, (orig_val, stored_val) in enumerate(zip(original, stored_vector)):
                diff = abs(orig_val - stored_val)
                assert diff < 1e-6, (
                    f"Record {record_id}, element {j}: diff={diff}, "
                    f"original={orig_val}, stored={stored_val}"
                )

    @pytest.mark.asyncio
    async def test_extreme_values_roundtrip(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
        test_company_id: int,
    ) -> None:
        """Verify round-trip precision for vectors with extreme float values."""
        # Create a vector with deliberately extreme but valid float32 values
        extreme_vector: list[float] = []
        for i in range(EMBEDDING_DIMENSION):
            # Alternate between small and large magnitudes
            if i % 4 == 0:
                extreme_vector.append(1e-7 * (i + 1))
            elif i % 4 == 1:
                extreme_vector.append(-1e-7 * (i + 1))
            elif i % 4 == 2:
                extreme_vector.append(0.999999)
            else:
                extreme_vector.append(-0.999999)

        # Normalize to unit length for valid cosine similarity
        norm = math.sqrt(sum(v * v for v in extreme_vector))
        extreme_vector = [v / norm for v in extreme_vector]

        chunk = IndexedChunk(
            embedding_vector=extreme_vector,
            chunk_text="Extreme value precision test",
            title="Precision Test",
            abstract_snippet="Testing float32 precision",
            authors=["Test"],
            doi=None,
            publication_date=None,
            source_id="test",
            external_id="EXTREME001",
            ingestion_record_id=999,
            company_id=test_company_id,
            partition_tag="public_literature",
            section_heading="",
            chunk_index=0,
        )

        await index_manager.bulk_index_chunks(test_company_id, [chunk])

        index_name = index_manager._index_name(test_company_id)
        response = await opensearch_client.search(
            index=index_name,
            body={
                "query": {"term": {"ingestion_record_id": 999}},
                "_source": ["embedding_vector"],
            },
        )

        hits = response["hits"]["hits"]
        assert len(hits) == 1

        stored_vector = hits[0]["_source"]["embedding_vector"]
        for i, (orig, stored) in enumerate(zip(extreme_vector, stored_vector)):
            diff = abs(orig - stored)
            assert diff < 1e-6, (
                f"Element {i}: diff={diff}, original={orig}, stored={stored}"
            )


# ---------------------------------------------------------------------------
# Test: Property 15 — Self-Retrieval Property
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(not OPENSEARCH_AVAILABLE, reason=SKIP_REASON)
class TestSelfRetrievalProperty:
    """Property 15: Self-retrieval property.

    Index text, search with same text, assert top-1 result matches
    with similarity ≈ 1.0.

    **Validates: Requirements 14.3**
    """

    @pytest.mark.asyncio
    async def test_self_retrieval_exact_match(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
        test_company_id: int,
    ) -> None:
        """Embed text, index it, search with same text — top-1 is self."""
        text = "Quality control procedures for sterile injectable manufacturing."
        embedding = deterministic_embedding(text)

        chunk = IndexedChunk(
            embedding_vector=embedding,
            chunk_text=text,
            title="Self-Retrieval Test",
            abstract_snippet="Testing self-retrieval",
            authors=["QC Team"],
            doi="10.1000/self001",
            publication_date="2024-03-20",
            source_id="test",
            external_id="SELF001",
            ingestion_record_id=200,
            company_id=test_company_id,
            partition_tag="public_literature",
            section_heading="Methods",
            chunk_index=0,
        )

        await index_manager.bulk_index_chunks(test_company_id, [chunk])

        # Search with the same embedding (simulating same text query)
        query_vector = deterministic_embedding(text)
        index_name = index_manager._index_name(test_company_id)

        response = await opensearch_client.search(
            index=index_name,
            body={
                "size": 1,
                "query": {
                    "knn": {
                        "embedding_vector": {
                            "vector": query_vector,
                            "k": 1,
                        }
                    }
                },
            },
        )

        hits = response["hits"]["hits"]
        assert len(hits) == 1, f"Expected 1 hit, got {len(hits)}"

        top_result = hits[0]
        # Verify it's the same document
        assert top_result["_source"]["ingestion_record_id"] == 200
        assert top_result["_source"]["chunk_text"] == text

        # Cosine similarity should be ≈ 1.0 for identical vectors
        # OpenSearch returns score; for cosinesimil space the score
        # is 1 / (1 + cosine_distance) where cosine_distance = 1 - cosine_sim
        # So score = 1 / (1 + (1 - 1.0)) = 1.0 for identical vectors
        # However the scoring may vary by OpenSearch version, so we check >= 0.99
        score = top_result["_score"]
        assert score >= 0.99, (
            f"Self-retrieval score should be ≈ 1.0, got {score}"
        )

    @pytest.mark.asyncio
    async def test_self_retrieval_among_multiple_documents(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
        test_company_id: int,
    ) -> None:
        """Self-retrieval works when index contains multiple different documents."""
        texts = [
            "Protein aggregation studies using dynamic light scattering.",
            "Cleaning validation protocols for multi-product facilities.",
            "Environmental monitoring in aseptic filling operations.",
            "Stability indicating method development for biologics.",
            "Risk assessment methodologies in pharmaceutical manufacturing.",
        ]

        target_text = texts[2]  # "Environmental monitoring..."
        target_record_id = 302

        chunks = []
        for i, text in enumerate(texts):
            embedding = deterministic_embedding(text)
            chunks.append(
                IndexedChunk(
                    embedding_vector=embedding,
                    chunk_text=text,
                    title=f"Document {i}",
                    abstract_snippet=text[:50],
                    authors=[f"Author {i}"],
                    doi=f"10.1000/multi{i}",
                    publication_date="2024-02-01",
                    source_id="test",
                    external_id=f"MULTI{i}",
                    ingestion_record_id=300 + i,
                    company_id=test_company_id,
                    partition_tag="public_literature",
                    section_heading="Abstract",
                    chunk_index=0,
                )
            )

        await index_manager.bulk_index_chunks(test_company_id, chunks)

        # Search for the target text
        query_vector = deterministic_embedding(target_text)
        index_name = index_manager._index_name(test_company_id)

        response = await opensearch_client.search(
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

        hits = response["hits"]["hits"]
        assert len(hits) >= 1

        # Top-1 result should be the target document
        top_result = hits[0]
        assert top_result["_source"]["ingestion_record_id"] == target_record_id, (
            f"Expected record_id={target_record_id}, "
            f"got {top_result['_source']['ingestion_record_id']}"
        )
        assert top_result["_source"]["chunk_text"] == target_text

        # Score should be close to 1.0
        score = top_result["_score"]
        assert score >= 0.99, f"Self-retrieval score should be ≈ 1.0, got {score}"

    @pytest.mark.asyncio
    async def test_self_retrieval_short_text(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
        test_company_id: int,
    ) -> None:
        """Self-retrieval works for short text inputs."""
        short_text = "GMP compliance audit"
        embedding = deterministic_embedding(short_text)

        # Add the target and a distractor
        chunks = [
            IndexedChunk(
                embedding_vector=embedding,
                chunk_text=short_text,
                title="Short Text",
                abstract_snippet=short_text,
                authors=["Auditor"],
                doi=None,
                publication_date="2024-05-01",
                source_id="test",
                external_id="SHORT001",
                ingestion_record_id=400,
                company_id=test_company_id,
                partition_tag="public_literature",
                section_heading="",
                chunk_index=0,
            ),
            IndexedChunk(
                embedding_vector=deterministic_embedding("completely different topic about marine biology"),
                chunk_text="completely different topic about marine biology",
                title="Distractor",
                abstract_snippet="Marine biology",
                authors=["Marine"],
                doi=None,
                publication_date="2024-05-01",
                source_id="test",
                external_id="DISTRACT001",
                ingestion_record_id=401,
                company_id=test_company_id,
                partition_tag="public_literature",
                section_heading="",
                chunk_index=0,
            ),
        ]

        await index_manager.bulk_index_chunks(test_company_id, chunks)

        # Search with same short text
        query_vector = deterministic_embedding(short_text)
        index_name = index_manager._index_name(test_company_id)

        response = await opensearch_client.search(
            index=index_name,
            body={
                "size": 2,
                "query": {
                    "knn": {
                        "embedding_vector": {
                            "vector": query_vector,
                            "k": 2,
                        }
                    }
                },
            },
        )

        hits = response["hits"]["hits"]
        assert len(hits) >= 1

        top_result = hits[0]
        assert top_result["_source"]["ingestion_record_id"] == 400
        assert top_result["_score"] >= 0.99

    @pytest.mark.asyncio
    async def test_self_retrieval_long_text(
        self,
        index_manager: LiteratureIndexManager,
        opensearch_client,
        test_company_id: int,
    ) -> None:
        """Self-retrieval works for longer text inputs (simulating full paragraphs)."""
        long_text = (
            "The pharmaceutical industry is increasingly adopting machine learning "
            "and artificial intelligence techniques for drug discovery, process "
            "optimization, and quality control. This paper reviews recent advances "
            "in the application of deep neural networks to predict drug-target "
            "interactions, optimize formulation parameters, and detect manufacturing "
            "deviations in real-time. We present a comprehensive analysis of "
            "regulatory considerations for AI-driven decision support systems in "
            "GMP-regulated environments, including validation strategies that "
            "satisfy FDA and EMA requirements for computer system validation. "
            "Our findings suggest that hybrid approaches combining physics-based "
            "models with data-driven methods achieve superior performance compared "
            "to purely empirical models, particularly when training data is limited."
        )

        embedding = deterministic_embedding(long_text)

        # Add a distractor with semantically different content
        distractor_text = (
            "Aquatic ecosystems are subject to numerous environmental pressures "
            "including pollution, habitat destruction, and climate change. This "
            "study examines the biodiversity patterns of freshwater invertebrates "
            "in temperate river systems across Northern Europe."
        )

        chunks = [
            IndexedChunk(
                embedding_vector=embedding,
                chunk_text=long_text,
                title="AI in Pharma Review",
                abstract_snippet=long_text[:200],
                authors=["Data Scientist"],
                doi="10.1000/longtext001",
                publication_date="2024-07-01",
                source_id="test",
                external_id="LONG001",
                ingestion_record_id=500,
                company_id=test_company_id,
                partition_tag="public_literature",
                section_heading="Introduction",
                chunk_index=0,
            ),
            IndexedChunk(
                embedding_vector=deterministic_embedding(distractor_text),
                chunk_text=distractor_text,
                title="Aquatic Ecology",
                abstract_snippet=distractor_text[:200],
                authors=["Ecologist"],
                doi="10.1000/ecology001",
                publication_date="2024-07-01",
                source_id="test",
                external_id="ECO001",
                ingestion_record_id=501,
                company_id=test_company_id,
                partition_tag="public_literature",
                section_heading="Introduction",
                chunk_index=0,
            ),
        ]

        await index_manager.bulk_index_chunks(test_company_id, chunks)

        # Search with same long text
        query_vector = deterministic_embedding(long_text)
        index_name = index_manager._index_name(test_company_id)

        response = await opensearch_client.search(
            index=index_name,
            body={
                "size": 2,
                "query": {
                    "knn": {
                        "embedding_vector": {
                            "vector": query_vector,
                            "k": 2,
                        }
                    }
                },
            },
        )

        hits = response["hits"]["hits"]
        assert len(hits) >= 1

        top_result = hits[0]
        assert top_result["_source"]["ingestion_record_id"] == 500
        assert top_result["_score"] >= 0.99

        # Distractor should have a significantly lower score
        if len(hits) > 1:
            distractor_score = hits[1]["_score"]
            assert distractor_score < top_result["_score"], (
                f"Distractor score {distractor_score} should be lower "
                f"than self-retrieval score {top_result['_score']}"
            )
