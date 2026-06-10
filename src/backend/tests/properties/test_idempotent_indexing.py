"""Property-based tests for idempotent indexing.

Property 11: Idempotent indexing
- Index a record, then re-index (delete + re-insert)
- Assert identical chunk count, texts, and vectors as fresh indexing
- Mock OpenSearch to verify delete-then-insert sequence
- Verify calling twice produces same results

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

# Feature: Step_9-3_high-dimensional-embedding-hybrid-indexing

from unittest.mock import AsyncMock, call

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.embedding.services.index_manager import (
    IndexedChunk,
    LiteratureIndexManager,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

st_company_id = st.integers(min_value=1, max_value=10_000)
st_record_id = st.integers(min_value=1, max_value=1_000_000)


def _make_embedding(dim: int = 1024) -> list[float]:
    """Create a deterministic embedding vector of given dimension.

    Uses a lightweight approach: fixed pattern rather than fully random floats,
    since the property under test is about delete/insert ordering not vector content.
    """
    import math

    return [math.sin(i * 0.01) for i in range(dim)]


@st.composite
def st_indexed_chunks(
    draw: st.DrawFn,
    company_id: int,
    record_id: int,
) -> list[IndexedChunk]:
    """Generate a list of 1-5 IndexedChunks for a given company/record.

    Uses deterministic embeddings to keep the data small and fast while
    still testing the idempotency property across varied chunk counts and text.
    """
    num_chunks = draw(st.integers(min_value=1, max_value=5))
    chunks: list[IndexedChunk] = []
    for i in range(num_chunks):
        text = draw(st.text(min_size=1, max_size=80, alphabet=st.characters(categories=("L", "N", "Z"))))
        title = draw(st.text(min_size=0, max_size=30, alphabet=st.characters(categories=("L", "N", "Z"))))
        section = draw(st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "N", "Z"))))
        chunks.append(
            IndexedChunk(
                embedding_vector=_make_embedding(1024),
                chunk_text=text,
                title=title,
                abstract_snippet=text[:200],
                authors=["Author A"],
                doi=None,
                publication_date=None,
                source_id="pubmed",
                external_id=f"ext-{record_id}-{i}",
                ingestion_record_id=record_id,
                company_id=company_id,
                partition_tag="public_literature",
                section_heading=section,
                chunk_index=i,
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Property 11: Idempotent indexing - delete-then-insert sequence verification
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    company_id=st_company_id,
    record_id=st_record_id,
    data=st.data(),
)
@pytest.mark.asyncio
async def test_idempotent_index_delete_before_insert(
    company_id: int,
    record_id: int,
    data: st.DataObject,
) -> None:
    """The _idempotent_index method always calls delete_record_chunks BEFORE
    bulk_index_chunks, ensuring stale vectors are removed before new ones are
    inserted.

    This verifies the delete-then-insert sequence that guarantees idempotency:
    re-indexing the same record produces the same final state regardless of
    whether chunks previously existed.

    **Validates: Requirements 8.4, 12.4**
    """
    chunks = data.draw(st_indexed_chunks(company_id, record_id))

    # Create mock OpenSearch client
    mock_client = AsyncMock()
    mock_client.delete_by_query = AsyncMock(return_value={"deleted": 3})
    mock_client.bulk = AsyncMock(return_value={"errors": False, "items": []})
    mock_client.indices = AsyncMock()
    mock_client.indices.exists = AsyncMock(return_value=True)

    manager = LiteratureIndexManager(
        opensearch_client=mock_client,
        embedding_dimension=1024,
    )

    # Mock the methods directly on the manager to track call order
    call_order: list[str] = []
    original_delete = manager.delete_record_chunks
    original_bulk = manager.bulk_index_chunks

    async def tracked_delete(company_id: int, ingestion_record_id: int) -> int:
        call_order.append("delete")
        return await original_delete(company_id=company_id, ingestion_record_id=ingestion_record_id)

    async def tracked_bulk(company_id: int, chunks: list[IndexedChunk]) -> int:
        call_order.append("bulk_index")
        return await original_bulk(company_id=company_id, chunks=chunks)

    manager.delete_record_chunks = tracked_delete  # type: ignore[assignment]
    manager.bulk_index_chunks = tracked_bulk  # type: ignore[assignment]

    # Import EmbeddingService to test _idempotent_index
    from alcoabase.literature.embedding.services.embedding_service import (
        EmbeddingService,
    )

    # Create a minimal EmbeddingService with the mocked index_manager
    service = EmbeddingService(
        session_factory=AsyncMock(),
        inference_client=AsyncMock(),
        model_manager=AsyncMock(),
        index_manager=manager,
        chunking_pipeline=AsyncMock(),
    )

    # Call _idempotent_index
    result = await service._idempotent_index(
        company_id=company_id,
        record_id=record_id,
        chunks=chunks,
    )

    # Assert delete was called before bulk_index
    assert call_order == ["delete", "bulk_index"], (
        f"Expected call order ['delete', 'bulk_index'], got {call_order}. "
        f"Idempotent indexing requires delete BEFORE insert."
    )

    # Assert the result is the number of chunks indexed
    assert result == len(chunks), (
        f"Expected {len(chunks)} chunks indexed, got {result}."
    )


@settings(max_examples=100)
@given(
    company_id=st_company_id,
    record_id=st_record_id,
    data=st.data(),
)
@pytest.mark.asyncio
async def test_idempotent_index_produces_same_results_on_reindex(
    company_id: int,
    record_id: int,
    data: st.DataObject,
) -> None:
    """Calling _idempotent_index twice with the same chunks produces identical
    results: same chunk count, same texts, and same vectors are passed to
    bulk_index_chunks each time.

    This confirms that re-indexing (delete + re-insert) is truly idempotent:
    the final indexed state is identical whether it's a first index or a
    re-index operation.

    **Validates: Requirements 8.4, 12.4**
    """
    chunks = data.draw(st_indexed_chunks(company_id, record_id))

    # Track all bulk_index_chunks calls to compare payloads
    bulk_calls: list[list[IndexedChunk]] = []

    mock_client = AsyncMock()
    mock_client.delete_by_query = AsyncMock(return_value={"deleted": 0})
    mock_client.bulk = AsyncMock(return_value={"errors": False, "items": []})
    mock_client.indices = AsyncMock()
    mock_client.indices.exists = AsyncMock(return_value=True)

    manager = LiteratureIndexManager(
        opensearch_client=mock_client,
        embedding_dimension=1024,
    )

    original_bulk = manager.bulk_index_chunks

    async def capturing_bulk(company_id: int, chunks: list[IndexedChunk]) -> int:
        bulk_calls.append(list(chunks))
        return await original_bulk(company_id=company_id, chunks=chunks)

    manager.bulk_index_chunks = capturing_bulk  # type: ignore[assignment]

    from alcoabase.literature.embedding.services.embedding_service import (
        EmbeddingService,
    )

    service = EmbeddingService(
        session_factory=AsyncMock(),
        inference_client=AsyncMock(),
        model_manager=AsyncMock(),
        index_manager=manager,
        chunking_pipeline=AsyncMock(),
    )

    # First indexing
    result_1 = await service._idempotent_index(
        company_id=company_id,
        record_id=record_id,
        chunks=chunks,
    )

    # Second indexing (re-index) with same chunks
    result_2 = await service._idempotent_index(
        company_id=company_id,
        record_id=record_id,
        chunks=chunks,
    )

    # Assert both calls produced the same chunk count
    assert result_1 == result_2, (
        f"Re-indexing produced different chunk counts: "
        f"first={result_1}, second={result_2}."
    )

    # Assert both calls passed identical chunks to bulk_index
    assert len(bulk_calls) == 2, (
        f"Expected 2 bulk_index calls, got {len(bulk_calls)}."
    )

    first_chunks = bulk_calls[0]
    second_chunks = bulk_calls[1]

    assert len(first_chunks) == len(second_chunks), (
        f"Chunk count mismatch: first={len(first_chunks)}, "
        f"second={len(second_chunks)}."
    )

    for i, (c1, c2) in enumerate(zip(first_chunks, second_chunks)):
        assert c1.chunk_text == c2.chunk_text, (
            f"Chunk {i} text differs between indexing calls: "
            f"'{c1.chunk_text}' vs '{c2.chunk_text}'."
        )
        assert c1.embedding_vector == c2.embedding_vector, (
            f"Chunk {i} embedding vector differs between indexing calls."
        )
        assert c1.chunk_index == c2.chunk_index, (
            f"Chunk {i} index differs: {c1.chunk_index} vs {c2.chunk_index}."
        )
        assert c1.ingestion_record_id == c2.ingestion_record_id, (
            f"Chunk {i} record_id differs: "
            f"{c1.ingestion_record_id} vs {c2.ingestion_record_id}."
        )


@settings(max_examples=100)
@given(
    company_id=st_company_id,
    record_id=st_record_id,
    data=st.data(),
)
@pytest.mark.asyncio
async def test_idempotent_index_delete_targets_correct_record(
    company_id: int,
    record_id: int,
    data: st.DataObject,
) -> None:
    """The delete step within _idempotent_index targets the specific record_id
    and company_id, ensuring only that record's chunks are removed before
    re-insertion.

    This validates that the delete operation is properly scoped so that
    re-indexing one record does not affect other records in the same index.

    **Validates: Requirements 8.4, 12.4**
    """
    chunks = data.draw(st_indexed_chunks(company_id, record_id))

    mock_client = AsyncMock()
    mock_client.delete_by_query = AsyncMock(return_value={"deleted": 2})
    mock_client.bulk = AsyncMock(return_value={"errors": False, "items": []})
    mock_client.indices = AsyncMock()
    mock_client.indices.exists = AsyncMock(return_value=True)

    manager = LiteratureIndexManager(
        opensearch_client=mock_client,
        embedding_dimension=1024,
    )

    from alcoabase.literature.embedding.services.embedding_service import (
        EmbeddingService,
    )

    service = EmbeddingService(
        session_factory=AsyncMock(),
        inference_client=AsyncMock(),
        model_manager=AsyncMock(),
        index_manager=manager,
        chunking_pipeline=AsyncMock(),
    )

    await service._idempotent_index(
        company_id=company_id,
        record_id=record_id,
        chunks=chunks,
    )

    # Verify delete_by_query was called with the correct parameters
    mock_client.delete_by_query.assert_called_once()
    _, kwargs = mock_client.delete_by_query.call_args
    actual_index = kwargs["index"]
    actual_body = kwargs["body"]

    # Verify correct index is targeted
    expected_index = f"literature-embeddings-{company_id}"
    assert actual_index == expected_index, (
        f"Delete targeted index '{actual_index}', expected '{expected_index}'."
    )

    # Verify the query filters on the correct record_id
    must_clauses = actual_body["query"]["bool"]["must"]
    term_filters = {}
    for clause in must_clauses:
        if "term" in clause:
            for field, value in clause["term"].items():
                term_filters[field] = value

    assert term_filters.get("ingestion_record_id") == record_id, (
        f"Delete query targeted record_id {term_filters.get('ingestion_record_id')}, "
        f"expected {record_id}."
    )
    assert term_filters.get("company_id") == company_id, (
        f"Delete query targeted company_id {term_filters.get('company_id')}, "
        f"expected {company_id}."
    )
