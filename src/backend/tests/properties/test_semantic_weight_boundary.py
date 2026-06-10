"""Property-based tests for semantic weight boundary behavior.

Property 8: Semantic weight boundary behavior
- Generate two ranked lists
- Assert semantic_weight=0.0 → ranking determined entirely by BM25 ranks
- Assert semantic_weight=1.0 → ranking determined entirely by kNN ranks

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

# Feature: Step_9-3_high-dimensional-embedding-hybrid-indexing

from unittest.mock import AsyncMock

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridQueryEngine,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# RRF k parameter in valid range
st_rrf_k = st.integers(min_value=1, max_value=200)


@st.composite
def st_ranked_list(draw: st.DrawFn, min_size: int = 1, max_size: int = 20) -> list[dict]:
    """Generate a ranked list of documents with unique _id values."""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    # Generate unique string IDs
    ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=3,
                max_size=10,
            ),
            min_size=size,
            max_size=size,
            unique=True,
        )
    )
    return [{"_id": doc_id, "title": f"Doc {doc_id}"} for doc_id in ids]


@st.composite
def st_two_ranked_lists(draw: st.DrawFn) -> tuple[list[dict], list[dict]]:
    """Generate two ranked lists with some overlap and some unique docs."""
    # Generate shared doc IDs (appear in both lists)
    shared_count = draw(st.integers(min_value=1, max_value=8))
    shared_ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=3,
                max_size=10,
            ),
            min_size=shared_count,
            max_size=shared_count,
            unique=True,
        )
    )

    # Generate unique doc IDs for BM25 only
    bm25_only_count = draw(st.integers(min_value=0, max_value=5))
    bm25_only_ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=3,
                max_size=10,
            ).filter(lambda x: x not in shared_ids),
            min_size=bm25_only_count,
            max_size=bm25_only_count,
            unique=True,
        )
    )

    # Generate unique doc IDs for kNN only
    knn_only_count = draw(st.integers(min_value=0, max_value=5))
    all_existing = set(shared_ids) | set(bm25_only_ids)
    knn_only_ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=3,
                max_size=10,
            ).filter(lambda x: x not in all_existing),
            min_size=knn_only_count,
            max_size=knn_only_count,
            unique=True,
        )
    )

    # Build BM25 list: shared + bm25_only, shuffled
    bm25_ids = list(shared_ids) + list(bm25_only_ids)
    bm25_ids = draw(st.permutations(bm25_ids))
    bm25_results = [{"_id": doc_id, "title": f"Doc {doc_id}"} for doc_id in bm25_ids]

    # Build kNN list: shared + knn_only, shuffled
    knn_ids = list(shared_ids) + list(knn_only_ids)
    knn_ids = draw(st.permutations(knn_ids))
    knn_results = [{"_id": doc_id, "title": f"Doc {doc_id}"} for doc_id in knn_ids]

    return (bm25_results, knn_results)


# ---------------------------------------------------------------------------
# Helper: create a HybridQueryEngine instance with mocked dependencies
# ---------------------------------------------------------------------------


def _make_engine(rrf_k: int = 60) -> HybridQueryEngine:
    """Create a HybridQueryEngine with mocked dependencies for unit testing."""
    mock_index_manager = AsyncMock()
    mock_inference_client = AsyncMock()
    mock_model_manager = AsyncMock()

    engine = HybridQueryEngine(
        index_manager=mock_index_manager,
        inference_client=mock_inference_client,
        model_manager=mock_model_manager,
        model_name="test-embedding-model",
        default_rrf_k=rrf_k,
    )
    return engine


# ---------------------------------------------------------------------------
# Property 8: Semantic weight boundary behavior
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    lists=st_two_ranked_lists(),
    k=st_rrf_k,
)
def test_semantic_weight_zero_ranking_by_bm25_only(
    lists: tuple[list[dict], list[dict]],
    k: int,
) -> None:
    """At semantic_weight=0.0, ranking is determined entirely by BM25 ranks.

    Documents only appearing in the kNN list should have score 0.0 (since
    their BM25 contribution is 0 and semantic_weight=0 means kNN contributes
    nothing).

    Among documents with non-zero scores (those in BM25 list), their order
    should match the BM25 rank order (lower BM25 rank = higher RRF score).

    **Validates: Requirements 6.4**
    """
    bm25_results, knn_results = lists
    engine = _make_engine(rrf_k=k)

    fused = engine._apply_rrf(bm25_results, knn_results, k, semantic_weight=0.0)

    # Build expected BM25 rank map
    bm25_ids_ordered = [doc["_id"] for doc in bm25_results]
    knn_only_ids = {doc["_id"] for doc in knn_results} - set(bm25_ids_ordered)

    # Documents only in kNN should have score 0.0
    for result in fused:
        if result["_id"] in knn_only_ids:
            assert result["relevance_score"] == 0.0, (
                f"Doc '{result['_id']}' is kNN-only but has non-zero score "
                f"{result['relevance_score']} at semantic_weight=0.0"
            )

    # Extract fused docs that have non-zero scores (BM25 docs)
    nonzero_results = [r for r in fused if r["relevance_score"] > 0.0]

    # Verify ordering among non-zero scored docs matches BM25 rank order
    # Lower BM25 rank → higher RRF score → appears earlier in fused list
    for i in range(len(nonzero_results) - 1):
        id_a = nonzero_results[i]["_id"]
        id_b = nonzero_results[i + 1]["_id"]

        rank_a = bm25_ids_ordered.index(id_a) + 1  # 1-based rank
        rank_b = bm25_ids_ordered.index(id_b) + 1

        score_a = nonzero_results[i]["relevance_score"]
        score_b = nonzero_results[i + 1]["relevance_score"]

        # If scores differ, the one with lower BM25 rank must have higher score
        if score_a != score_b:
            assert rank_a < rank_b, (
                f"At semantic_weight=0.0, doc '{id_a}' (BM25 rank {rank_a}) "
                f"should come before doc '{id_b}' (BM25 rank {rank_b}) "
                f"but scores are {score_a} vs {score_b}."
            )


@settings(max_examples=100)
@given(
    lists=st_two_ranked_lists(),
    k=st_rrf_k,
)
def test_semantic_weight_one_ranking_by_knn_only(
    lists: tuple[list[dict], list[dict]],
    k: int,
) -> None:
    """At semantic_weight=1.0, ranking is determined entirely by kNN ranks.

    Documents only appearing in the BM25 list should have score 0.0 (since
    their kNN contribution is 0 and semantic_weight=1.0 means BM25 contributes
    nothing).

    Among documents with non-zero scores (those in kNN list), their order
    should match the kNN rank order (lower kNN rank = higher RRF score).

    **Validates: Requirements 6.4**
    """
    bm25_results, knn_results = lists
    engine = _make_engine(rrf_k=k)

    fused = engine._apply_rrf(bm25_results, knn_results, k, semantic_weight=1.0)

    # Build expected kNN rank map
    knn_ids_ordered = [doc["_id"] for doc in knn_results]
    bm25_only_ids = {doc["_id"] for doc in bm25_results} - set(knn_ids_ordered)

    # Documents only in BM25 should have score 0.0
    for result in fused:
        if result["_id"] in bm25_only_ids:
            assert result["relevance_score"] == 0.0, (
                f"Doc '{result['_id']}' is BM25-only but has non-zero score "
                f"{result['relevance_score']} at semantic_weight=1.0"
            )

    # Extract fused docs that have non-zero scores (kNN docs)
    nonzero_results = [r for r in fused if r["relevance_score"] > 0.0]

    # Verify ordering among non-zero scored docs matches kNN rank order
    # Lower kNN rank → higher RRF score → appears earlier in fused list
    for i in range(len(nonzero_results) - 1):
        id_a = nonzero_results[i]["_id"]
        id_b = nonzero_results[i + 1]["_id"]

        rank_a = knn_ids_ordered.index(id_a) + 1  # 1-based rank
        rank_b = knn_ids_ordered.index(id_b) + 1

        score_a = nonzero_results[i]["relevance_score"]
        score_b = nonzero_results[i + 1]["relevance_score"]

        # If scores differ, the one with lower kNN rank must have higher score
        if score_a != score_b:
            assert rank_a < rank_b, (
                f"At semantic_weight=1.0, doc '{id_a}' (kNN rank {rank_a}) "
                f"should come before doc '{id_b}' (kNN rank {rank_b}) "
                f"but scores are {score_a} vs {score_b}."
            )
