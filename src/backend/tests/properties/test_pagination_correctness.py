"""Property-based tests for pagination correctness (Property 9).

Tests that the HybridQueryEngine.search() method correctly paginates
results: for a ranked list of N items, page p with page_size s,
the returned results match the slice [(p-1)*s : p*s] and total_count
equals N.

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

# Feature: Step_9-3_high-dimensional-embedding-hybrid-indexing

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import HealthCheck, given, settings

from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridQueryEngine,
    HybridSearchRequest,
)

# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate a list of N ranked result items (as dicts matching OpenSearch format)
st_n_items = st.integers(min_value=0, max_value=200)
st_page_size = st.integers(min_value=1, max_value=100)


@st.composite
def st_pagination_params(draw: st.DrawFn) -> tuple[int, int, int]:
    """Generate (N, page, page_size) where page is valid for N items.

    N: total number of results (0-200)
    page_size: 1-100
    page: 1-based, can go beyond available pages (to test empty slices)
    """
    n = draw(st.integers(min_value=0, max_value=200))
    page_size = draw(st.integers(min_value=1, max_value=100))
    # Allow page to go slightly beyond max to test boundary behavior
    max_page = max(1, (n // page_size) + 2)
    page = draw(st.integers(min_value=1, max_value=max_page))
    return (n, page, page_size)


def _make_fused_result(index: int) -> dict:
    """Create a mock fused result dict with a unique identifier."""
    return {
        "_id": f"doc_{index}",
        "chunk_text": f"chunk text {index}",
        "title": f"title {index}",
        "authors": [f"author_{index}"],
        "doi": f"10.1000/{index}",
        "publication_date": "2024-01-15",
        "source_id": "pubmed",
        "relevance_score": 1.0 / (index + 1),
        "partition_tag": "public_literature",
        "section_heading": f"Section {index}",
        "ingestion_record_id": index + 1,
    }


# ---------------------------------------------------------------------------
# Property 9: Pagination correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.large_base_example])
@given(params=st_pagination_params())
@pytest.mark.asyncio
async def test_pagination_returns_correct_slice(
    params: tuple[int, int, int],
) -> None:
    """For any ranked list of N items, page p and page_size s, the search()
    method returns results matching slice [(p-1)*s : p*s] and total_count
    equals N.

    This tests the pagination logic applied within HybridQueryEngine.search()
    by mocking the OpenSearch client and InferenceClient to return a known
    ranked list of N items, then verifying the response contains the expected
    slice.

    **Validates: Requirements 6.5**
    """
    n, page, page_size = params

    # Build a known ranked list of N items
    all_results = [_make_fused_result(i) for i in range(n)]

    # Mock dependencies
    mock_index_manager = MagicMock()
    mock_index_manager._index_name = MagicMock(return_value="literature-embeddings-1")
    mock_index_manager._client = MagicMock()

    # Mock OpenSearch search to return all N results as BM25 hits
    mock_index_manager._client.search = AsyncMock(
        return_value={
            "hits": {
                "hits": [
                    {"_id": r["_id"], "_score": r["relevance_score"], "_source": r}
                    for r in all_results
                ]
            }
        }
    )

    mock_inference_client = MagicMock()
    # Return a query vector so kNN is also attempted
    mock_inference_client.create_embeddings = AsyncMock(
        return_value=[[0.1] * 1024]
    )

    mock_model_manager = MagicMock()

    engine = HybridQueryEngine(
        index_manager=mock_index_manager,
        inference_client=mock_inference_client,
        model_manager=mock_model_manager,
        model_name="test-embedding-model",
        default_rrf_k=60,
    )

    # Patch _apply_rrf to return our known ranked list directly
    # This isolates the pagination logic from RRF computation
    with patch.object(engine, "_apply_rrf", return_value=all_results):
        request = HybridSearchRequest(
            query="test query",
            company_id=1,
            user_id=1,
            page=page,
            page_size=page_size,
            semantic_weight=0.5,
        )

        response = await engine.search(request)

    # Property: total_count equals N
    assert response.total_count == n, (
        f"total_count should equal N={n}, got {response.total_count}"
    )

    # Property: returned results match the expected slice
    expected_start = (page - 1) * page_size
    expected_end = expected_start + page_size
    expected_slice = all_results[expected_start:expected_end]

    assert len(response.results) == len(expected_slice), (
        f"Expected {len(expected_slice)} results for page={page}, "
        f"page_size={page_size}, N={n}. Got {len(response.results)}."
    )

    # Verify each result matches the expected item from the ranked list
    for i, (actual, expected) in enumerate(zip(response.results, expected_slice)):
        assert actual.chunk_text == expected["chunk_text"], (
            f"Result at position {i} has incorrect chunk_text.\n"
            f"Expected: '{expected['chunk_text']}'\n"
            f"Got: '{actual.chunk_text}'"
        )
        assert actual.ingestion_record_id == expected["ingestion_record_id"], (
            f"Result at position {i} has incorrect ingestion_record_id.\n"
            f"Expected: {expected['ingestion_record_id']}\n"
            f"Got: {actual.ingestion_record_id}"
        )


@settings(max_examples=100, suppress_health_check=[HealthCheck.large_base_example])
@given(params=st_pagination_params())
@pytest.mark.asyncio
async def test_pagination_total_count_equals_n(
    params: tuple[int, int, int],
) -> None:
    """For any ranked list of N items, the response total_count always
    equals N regardless of the page or page_size requested.

    This ensures the total result count is independent of pagination
    parameters and accurately represents the full result set size.

    **Validates: Requirements 6.5**
    """
    n, page, page_size = params

    all_results = [_make_fused_result(i) for i in range(n)]

    mock_index_manager = MagicMock()
    mock_index_manager._index_name = MagicMock(return_value="literature-embeddings-1")
    mock_index_manager._client = MagicMock()
    mock_index_manager._client.search = AsyncMock(
        return_value={
            "hits": {
                "hits": [
                    {"_id": r["_id"], "_score": r["relevance_score"], "_source": r}
                    for r in all_results
                ]
            }
        }
    )

    mock_inference_client = MagicMock()
    mock_inference_client.create_embeddings = AsyncMock(
        return_value=[[0.1] * 1024]
    )
    mock_model_manager = MagicMock()

    engine = HybridQueryEngine(
        index_manager=mock_index_manager,
        inference_client=mock_inference_client,
        model_manager=mock_model_manager,
        model_name="test-embedding-model",
        default_rrf_k=60,
    )

    with patch.object(engine, "_apply_rrf", return_value=all_results):
        request = HybridSearchRequest(
            query="test query",
            company_id=1,
            user_id=1,
            page=page,
            page_size=page_size,
            semantic_weight=0.5,
        )

        response = await engine.search(request)

    # Property: total_count is always N
    assert response.total_count == n, (
        f"total_count must equal N={n} regardless of pagination params "
        f"(page={page}, page_size={page_size}). Got {response.total_count}."
    )

    # Property: response page and page_size reflect the request
    assert response.page == page
    assert response.page_size == page_size
