"""Property-based tests for tenant isolation on indexing and search.

Property 5: Tenant isolation on indexing and search
- Index name is exactly `literature-embeddings-{company_id}` for any company_id.
- bulk_index_chunks() rejects chunks with mismatched company_id (TenantIsolationError).
- delete_record_chunks() includes mandatory company_id filter in the query.

**Validates: Requirements 4.1, 4.2, 4.4, 4.5**

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.embedding.exceptions import TenantIsolationError
from alcoabase.literature.embedding.services.index_manager import (
    IndexedChunk,
    LiteratureIndexManager,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=100_000)
RECORD_IDS = st.integers(min_value=1, max_value=100_000)


@st.composite
def st_indexed_chunk(draw: st.DrawFn, *, company_id: int | None = None) -> IndexedChunk:
    """Generate a random IndexedChunk with a given or random company_id."""
    cid = company_id if company_id is not None else draw(COMPANY_IDS)
    return IndexedChunk(
        embedding_vector=[draw(st.floats(min_value=-1.0, max_value=1.0)) for _ in range(8)],
        chunk_text=draw(st.text(min_size=1, max_size=50)),
        title=draw(st.text(min_size=1, max_size=30)),
        abstract_snippet=draw(st.text(max_size=50)),
        authors=[draw(st.text(min_size=1, max_size=20))],
        doi=draw(st.one_of(st.none(), st.text(min_size=5, max_size=20))),
        publication_date=draw(st.one_of(st.none(), st.just("2024-01-15"))),
        source_id=draw(st.one_of(st.none(), st.text(min_size=3, max_size=10))),
        external_id=draw(st.one_of(st.none(), st.text(min_size=3, max_size=10))),
        ingestion_record_id=draw(RECORD_IDS),
        company_id=cid,
        partition_tag=draw(st.sampled_from(["public_literature", "private_knowledge"])),
        section_heading=draw(st.text(max_size=20)),
        chunk_index=draw(st.integers(min_value=0, max_value=100)),
    )


# ---------------------------------------------------------------------------
# Property 5a: Index name is exactly `literature-embeddings-{company_id}`
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(company_id=COMPANY_IDS)
def test_index_name_matches_company_id_format(company_id: int) -> None:
    """For any company_id, the index name SHALL be exactly
    'literature-embeddings-{company_id}'.

    This ensures physical isolation by routing each company to its own index.

    **Validates: Requirements 4.1, 4.2**
    """
    manager = LiteratureIndexManager(
        opensearch_client=MagicMock(),
        embedding_dimension=1024,
    )

    index_name = manager._index_name(company_id)

    assert index_name == f"literature-embeddings-{company_id}", (
        f"Expected 'literature-embeddings-{company_id}', got '{index_name}'"
    )
    # Also verify it starts with the correct prefix
    assert index_name.startswith(LiteratureIndexManager.INDEX_PREFIX), (
        f"Index name '{index_name}' does not start with prefix "
        f"'{LiteratureIndexManager.INDEX_PREFIX}'"
    )


# ---------------------------------------------------------------------------
# Property 5b: bulk_index_chunks rejects mismatched company_id
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    target_company_id=COMPANY_IDS,
    wrong_company_id=COMPANY_IDS,
)
@pytest.mark.asyncio
async def test_bulk_index_rejects_mismatched_company_id(
    target_company_id: int,
    wrong_company_id: int,
) -> None:
    """When bulk_index_chunks is called with chunks whose company_id does NOT
    match the target company_id, the method SHALL raise TenantIsolationError
    before any write occurs.

    **Validates: Requirements 4.1, 4.4**
    """
    # Only test when IDs actually differ
    if target_company_id == wrong_company_id:
        return

    mock_client = AsyncMock()
    manager = LiteratureIndexManager(
        opensearch_client=mock_client,
        embedding_dimension=8,
    )

    # Create a chunk with wrong company_id
    bad_chunk = IndexedChunk(
        embedding_vector=[0.1] * 8,
        chunk_text="test content",
        title="test title",
        abstract_snippet="snippet",
        authors=["Author"],
        doi=None,
        publication_date=None,
        source_id=None,
        external_id=None,
        ingestion_record_id=1,
        company_id=wrong_company_id,
        partition_tag="public_literature",
        section_heading="",
        chunk_index=0,
    )

    with pytest.raises(TenantIsolationError) as exc_info:
        await manager.bulk_index_chunks(
            company_id=target_company_id,
            chunks=[bad_chunk],
        )

    # Verify the error captures the correct IDs
    assert exc_info.value.company_id == target_company_id
    assert exc_info.value.target_company_id == wrong_company_id

    # Verify NO write operations occurred (defense-in-depth)
    mock_client.bulk.assert_not_called()


# ---------------------------------------------------------------------------
# Property 5c: delete_record_chunks includes mandatory company_id filter
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    company_id=COMPANY_IDS,
    record_id=RECORD_IDS,
)
@pytest.mark.asyncio
async def test_delete_record_chunks_includes_company_id_filter(
    company_id: int,
    record_id: int,
) -> None:
    """When delete_record_chunks is called, the constructed query SHALL include
    a mandatory boolean filter for company_id, providing defense-in-depth
    beyond index-level separation.

    **Validates: Requirements 4.5**
    """
    mock_client = AsyncMock()
    mock_client.delete_by_query = AsyncMock(return_value={"deleted": 0})

    manager = LiteratureIndexManager(
        opensearch_client=mock_client,
        embedding_dimension=1024,
    )

    await manager.delete_record_chunks(
        company_id=company_id,
        ingestion_record_id=record_id,
    )

    # Verify delete_by_query was called
    mock_client.delete_by_query.assert_called_once()

    # Extract the query body from the call
    call_kwargs = mock_client.delete_by_query.call_args
    query_body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body")
    target_index = call_kwargs.kwargs.get("index") or call_kwargs[1].get("index")

    # Verify index name matches the company
    assert target_index == f"literature-embeddings-{company_id}", (
        f"Expected index 'literature-embeddings-{company_id}', got '{target_index}'"
    )

    # Verify the query includes a bool.must clause with company_id term filter
    bool_query = query_body["query"]["bool"]
    must_clauses = bool_query["must"]

    # Find the company_id term filter
    company_id_filters = [
        clause for clause in must_clauses
        if "term" in clause and "company_id" in clause["term"]
    ]

    assert len(company_id_filters) == 1, (
        f"Expected exactly one company_id term filter in query, "
        f"found {len(company_id_filters)}. Query: {query_body}"
    )

    # Verify the company_id value matches
    assert company_id_filters[0]["term"]["company_id"] == company_id, (
        f"company_id filter value {company_id_filters[0]['term']['company_id']} "
        f"does not match expected {company_id}"
    )

    # Also verify ingestion_record_id filter is present
    record_filters = [
        clause for clause in must_clauses
        if "term" in clause and "ingestion_record_id" in clause["term"]
    ]
    assert len(record_filters) == 1, (
        f"Expected exactly one ingestion_record_id filter, "
        f"found {len(record_filters)}. Query: {query_body}"
    )
    assert record_filters[0]["term"]["ingestion_record_id"] == record_id
