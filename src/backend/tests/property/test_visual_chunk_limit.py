"""Property-based tests for visual chunk limit per query.

Tests Property 9: Visual chunk limit per query from the
multimodal-knowledge-base design document.

Property 9 validates that the _limit_visual_chunks() method caps
Visual_Chunks at MAX_VISUAL_CHUNKS_PER_QUERY (3) per query, filling
remaining slots with text chunks up to top_k (5).

The method ensures:
- At most 3 visual chunks in the final result
- Total results don't exceed top_k (5)
- Results are sorted by relevance score descending

**Validates: Requirements 3.6**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 9)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/rag_pipeline.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# Constants matching the specification
# ---------------------------------------------------------------------------

MAX_VISUAL_CHUNKS_PER_QUERY: int = 3
"""Maximum visual chunks allowed per query (Requirement 3.6)."""

DEFAULT_TOP_K: int = 5
"""Default number of total results returned per query."""


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_relevance_score() -> st.SearchStrategy[float]:
    """Generate a relevance score between 0.0 and 1.0.

    Returns:
        Strategy producing float values in [0.01, 1.0].
    """
    return st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)


def st_visual_search_result() -> st.SearchStrategy[SearchResult]:
    """Generate a SearchResult marked as a visual chunk.

    Returns:
        Strategy producing SearchResult instances with is_visual=True
        and content_type="visual".
    """
    return st.builds(
        SearchResult,
        document_uuid=st.uuids().map(str),
        title=st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
        version=st.just("1.0"),
        excerpt=st.text(min_size=10, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
        relevance_score=st_relevance_score(),
        metadata=st.just({"is_visual": True, "content_type": "visual", "visual_type": "diagram"}),
    )


def st_text_search_result() -> st.SearchStrategy[SearchResult]:
    """Generate a SearchResult marked as a text chunk.

    Returns:
        Strategy producing SearchResult instances with default text metadata.
    """
    return st.builds(
        SearchResult,
        document_uuid=st.uuids().map(str),
        title=st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
        version=st.just("1.0"),
        excerpt=st.text(min_size=10, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
        relevance_score=st_relevance_score(),
        metadata=st.just({"content_type": "text"}),
    )


# ---------------------------------------------------------------------------
# Property 9: Visual chunk limit per query
# ---------------------------------------------------------------------------


class TestVisualChunkLimit:
    """Property tests for visual chunk limit per query.

    The _limit_visual_chunks() method caps Visual_Chunks at
    MAX_VISUAL_CHUNKS_PER_QUERY (3) per query, filling remaining
    slots with text chunks up to top_k (5).

    **Validates: Requirements 3.6**
    """

    @given(
        visual_chunks=st.lists(st_visual_search_result(), min_size=0, max_size=10),
        text_chunks=st.lists(st_text_search_result(), min_size=0, max_size=10),
    )
    @settings(max_examples=300)
    def test_at_most_3_visual_chunks_in_result(
        self,
        visual_chunks: list[SearchResult],
        text_chunks: list[SearchResult],
    ) -> None:
        """Generate result sets with 0-10 visual chunks, verify max 3 in final context.

        Regardless of how many visual chunks are in the input, the output
        must contain at most MAX_VISUAL_CHUNKS_PER_QUERY (3) visual chunks.

        **Validates: Requirements 3.6**
        """
        pipeline = RAGPipeline(top_k=DEFAULT_TOP_K)
        combined_input = visual_chunks + text_chunks

        result = pipeline._limit_visual_chunks(combined_input)

        # Count visual chunks in result
        visual_in_result = [
            r for r in result
            if r.metadata.get("is_visual", False) or r.metadata.get("content_type") == "visual"
        ]

        assert len(visual_in_result) <= MAX_VISUAL_CHUNKS_PER_QUERY, (
            f"Expected at most {MAX_VISUAL_CHUNKS_PER_QUERY} visual chunks, "
            f"but got {len(visual_in_result)} from input with "
            f"{len(visual_chunks)} visual and {len(text_chunks)} text chunks"
        )

    @given(
        visual_chunks=st.lists(st_visual_search_result(), min_size=0, max_size=10),
        text_chunks=st.lists(st_text_search_result(), min_size=0, max_size=10),
    )
    @settings(max_examples=300)
    def test_total_results_do_not_exceed_top_k(
        self,
        visual_chunks: list[SearchResult],
        text_chunks: list[SearchResult],
    ) -> None:
        """Total results never exceed top_k (5).

        The combined count of visual and text chunks in the output
        must not exceed the configured top_k limit.

        **Validates: Requirements 3.6**
        """
        pipeline = RAGPipeline(top_k=DEFAULT_TOP_K)
        combined_input = visual_chunks + text_chunks

        result = pipeline._limit_visual_chunks(combined_input)

        assert len(result) <= DEFAULT_TOP_K, (
            f"Expected at most {DEFAULT_TOP_K} total results, "
            f"but got {len(result)} from input with "
            f"{len(visual_chunks)} visual and {len(text_chunks)} text chunks"
        )

    @given(
        visual_chunks=st.lists(st_visual_search_result(), min_size=0, max_size=10),
        text_chunks=st.lists(st_text_search_result(), min_size=0, max_size=10),
    )
    @settings(max_examples=300)
    def test_results_sorted_by_relevance_descending(
        self,
        visual_chunks: list[SearchResult],
        text_chunks: list[SearchResult],
    ) -> None:
        """Results are sorted by relevance score descending.

        The output list must be ordered from highest to lowest
        relevance_score.

        **Validates: Requirements 3.6**
        """
        pipeline = RAGPipeline(top_k=DEFAULT_TOP_K)
        combined_input = visual_chunks + text_chunks

        result = pipeline._limit_visual_chunks(combined_input)

        if len(result) > 1:
            scores = [r.relevance_score for r in result]
            for i in range(len(scores) - 1):
                assert scores[i] >= scores[i + 1], (
                    f"Results not sorted descending: score[{i}]={scores[i]} < "
                    f"score[{i + 1}]={scores[i + 1]}. Full scores: {scores}"
                )
