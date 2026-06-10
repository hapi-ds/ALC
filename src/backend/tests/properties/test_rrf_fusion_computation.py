"""Property-based tests for RRF fusion computation correctness.

Property 7: RRF fusion computation correctness
- Generate two ranked lists of document IDs with varying overlap.
- Generate k (1–200) and semantic_weight (0.0–1.0).
- Assert RRF score equals `(1-w) * 1/(k + bm25_rank) + w * 1/(k + knn_rank)`.
- Assert final list sorted by RRF score descending.

**Validates: Requirements 6.1, 6.3**

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import assume, given, settings

from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridQueryEngine,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Unique document IDs (strings mimicking OpenSearch _id values)
DOC_IDS = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=10,
)

# RRF k parameter: integer between 1 and 200
RRF_K = st.integers(min_value=1, max_value=200)

# Semantic weight: float between 0.0 and 1.0
SEMANTIC_WEIGHT = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@st.composite
def st_ranked_list(draw: st.DrawFn) -> list[dict[str, str]]:
    """Generate a ranked list of unique document dicts with '_id' keys."""
    ids = draw(
        st.lists(DOC_IDS, min_size=1, max_size=20, unique=True)
    )
    return [{"_id": doc_id} for doc_id in ids]


@st.composite
def st_two_ranked_lists(
    draw: st.DrawFn,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Generate two ranked lists with varying overlap.

    Some IDs appear in both lists, some in only one.
    """
    # Generate a pool of unique IDs
    all_ids = draw(
        st.lists(DOC_IDS, min_size=2, max_size=30, unique=True)
    )

    # Decide which IDs go into each list
    bm25_mask = draw(
        st.lists(st.booleans(), min_size=len(all_ids), max_size=len(all_ids))
    )
    knn_mask = draw(
        st.lists(st.booleans(), min_size=len(all_ids), max_size=len(all_ids))
    )

    bm25_ids = [all_ids[i] for i in range(len(all_ids)) if bm25_mask[i]]
    knn_ids = [all_ids[i] for i in range(len(all_ids)) if knn_mask[i]]

    # Ensure at least one ID in at least one list
    assume(len(bm25_ids) > 0 or len(knn_ids) > 0)

    bm25_results = [{"_id": doc_id} for doc_id in bm25_ids]
    knn_results = [{"_id": doc_id} for doc_id in knn_ids]

    return bm25_results, knn_results


def _make_engine() -> HybridQueryEngine:
    """Create a HybridQueryEngine instance with mocked dependencies."""
    return HybridQueryEngine(
        index_manager=MagicMock(),
        inference_client=AsyncMock(),
        model_manager=AsyncMock(),
        model_name="test-embedding-model",
        default_rrf_k=60,
    )


# ---------------------------------------------------------------------------
# Property 7a: RRF score computation correctness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    data=st.data(),
    k=RRF_K,
    semantic_weight=SEMANTIC_WEIGHT,
)
def test_rrf_score_computation_matches_formula(
    data: st.DataObject,
    k: int,
    semantic_weight: float,
) -> None:
    """For every document in the fused results, its relevance_score SHALL equal
    the RRF formula: (1-w) * 1/(k + bm25_rank) + w * 1/(k + knn_rank).

    Documents appearing in only one list get 0 contribution from the other.
    Ranks are 1-based.

    **Validates: Requirements 6.1, 6.3**
    """
    bm25_results, knn_results = data.draw(st_two_ranked_lists())

    engine = _make_engine()
    fused = engine._apply_rrf(bm25_results, knn_results, k, semantic_weight)

    # Build expected rank maps (1-based)
    bm25_rank_map: dict[str, int] = {
        doc["_id"]: rank for rank, doc in enumerate(bm25_results, start=1)
    }
    knn_rank_map: dict[str, int] = {
        doc["_id"]: rank for rank, doc in enumerate(knn_results, start=1)
    }

    for doc in fused:
        doc_id = doc["_id"]
        actual_score = doc["relevance_score"]

        # Compute expected score
        bm25_contribution = 0.0
        if doc_id in bm25_rank_map:
            bm25_rank = bm25_rank_map[doc_id]
            bm25_contribution = (1.0 - semantic_weight) * (1.0 / (k + bm25_rank))

        knn_contribution = 0.0
        if doc_id in knn_rank_map:
            knn_rank = knn_rank_map[doc_id]
            knn_contribution = semantic_weight * (1.0 / (k + knn_rank))

        expected_score = bm25_contribution + knn_contribution

        assert abs(actual_score - expected_score) < 1e-10, (
            f"Doc '{doc_id}': expected RRF score {expected_score}, "
            f"got {actual_score}. "
            f"k={k}, w={semantic_weight}, "
            f"bm25_rank={bm25_rank_map.get(doc_id)}, "
            f"knn_rank={knn_rank_map.get(doc_id)}"
        )


# ---------------------------------------------------------------------------
# Property 7b: Results sorted by RRF score descending
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    data=st.data(),
    k=RRF_K,
    semantic_weight=SEMANTIC_WEIGHT,
)
def test_rrf_results_sorted_descending_by_score(
    data: st.DataObject,
    k: int,
    semantic_weight: float,
) -> None:
    """The fused result list SHALL be sorted by RRF score in descending order.

    **Validates: Requirements 6.1, 6.3**
    """
    bm25_results, knn_results = data.draw(st_two_ranked_lists())

    engine = _make_engine()
    fused = engine._apply_rrf(bm25_results, knn_results, k, semantic_weight)

    # Verify descending order
    scores = [doc["relevance_score"] for doc in fused]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Results not sorted descending at index {i}: "
            f"score[{i}]={scores[i]} < score[{i+1}]={scores[i+1]}. "
            f"k={k}, w={semantic_weight}"
        )


# ---------------------------------------------------------------------------
# Property 7c: All documents from both lists appear in fused output
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    data=st.data(),
    k=RRF_K,
    semantic_weight=SEMANTIC_WEIGHT,
)
def test_rrf_fusion_includes_all_documents(
    data: st.DataObject,
    k: int,
    semantic_weight: float,
) -> None:
    """Every document from either the BM25 or kNN list SHALL appear in the
    fused output exactly once.

    **Validates: Requirements 6.1, 6.3**
    """
    bm25_results, knn_results = data.draw(st_two_ranked_lists())

    engine = _make_engine()
    fused = engine._apply_rrf(bm25_results, knn_results, k, semantic_weight)

    # Collect all expected IDs (union of both lists)
    expected_ids = {doc["_id"] for doc in bm25_results} | {
        doc["_id"] for doc in knn_results
    }
    actual_ids = {doc["_id"] for doc in fused}

    assert actual_ids == expected_ids, (
        f"Fused results missing or extra docs. "
        f"Expected {expected_ids}, got {actual_ids}"
    )

    # Verify no duplicates
    assert len(fused) == len(actual_ids), (
        f"Fused results contain duplicates: "
        f"{len(fused)} results but {len(actual_ids)} unique IDs"
    )
