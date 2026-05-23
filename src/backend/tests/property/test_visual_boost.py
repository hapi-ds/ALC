"""Property-based tests for visual chunk relevance boost.

Tests Property 8: Visual chunk relevance boost for process queries from the
multimodal-knowledge-base design document.

Property 8 validates that the _apply_visual_boost() method correctly:
- Boosts Visual_Chunk scores by VISUAL_BOOST_FACTOR when query contains keywords
- Leaves all scores unchanged when query lacks keywords
- Never boosts text chunks regardless of query content

**Validates: Requirements 3.5**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 8)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/rag_pipeline.py
"""

from dataclasses import field
from typing import Any
from unittest.mock import patch

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# Constants matching the specification and implementation
# ---------------------------------------------------------------------------

VISUAL_BOOST_KEYWORDS: list[str] = [
    "process", "flow", "flowchart", "diagram", "workflow",
    "steps", "procedure", "decision tree", "sequence",
]
"""Keywords that trigger visual chunk boosting."""


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_relevance_score() -> st.SearchStrategy[float]:
    """Generate relevance scores in the valid range (0.0, 1.0].

    Excludes 0.0 to avoid multiplication edge cases with zero.

    Returns:
        Strategy producing float values between 0.01 and 1.0.
    """
    return st.floats(
        min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False
    )


def st_boost_factor() -> st.SearchStrategy[float]:
    """Generate boost factor values in the valid range [1.0, 3.0].

    Returns:
        Strategy producing float values between 1.0 and 3.0.
    """
    return st.floats(
        min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False
    )


def st_visual_search_result(
    score: st.SearchStrategy[float] | None = None,
) -> st.SearchStrategy[SearchResult]:
    """Generate a SearchResult marked as a visual chunk.

    Args:
        score: Optional strategy for relevance_score. Defaults to st_relevance_score().

    Returns:
        Strategy producing SearchResult with is_visual=True metadata.
    """
    if score is None:
        score = st_relevance_score()

    return st.builds(
        SearchResult,
        document_uuid=st.uuids().map(str),
        title=st.text(min_size=1, max_size=30, alphabet=st.characters(categories=("L", "N", "Z"))),
        version=st.just("1.0"),
        excerpt=st.text(min_size=5, max_size=100),
        relevance_score=score,
        metadata=st.just({"is_visual": True, "content_type": "visual", "visual_type": "flowchart", "source_page": 1}),
        document_type=st.just("SOP"),
        status=st.just("Active"),
        tags=st.just([]),
        created_at=st.just(None),
        updated_at=st.just(None),
    )


def st_text_search_result(
    score: st.SearchStrategy[float] | None = None,
) -> st.SearchStrategy[SearchResult]:
    """Generate a SearchResult marked as a text chunk.

    Args:
        score: Optional strategy for relevance_score. Defaults to st_relevance_score().

    Returns:
        Strategy producing SearchResult with is_visual=False metadata.
    """
    if score is None:
        score = st_relevance_score()

    return st.builds(
        SearchResult,
        document_uuid=st.uuids().map(str),
        title=st.text(min_size=1, max_size=30, alphabet=st.characters(categories=("L", "N", "Z"))),
        version=st.just("1.0"),
        excerpt=st.text(min_size=5, max_size=100),
        relevance_score=score,
        metadata=st.just({"is_visual": False, "content_type": "text"}),
        document_type=st.just("SOP"),
        status=st.just("Active"),
        tags=st.just([]),
        created_at=st.just(None),
        updated_at=st.just(None),
    )


def st_query_with_keyword() -> st.SearchStrategy[str]:
    """Generate queries that contain at least one visual boost keyword.

    Returns:
        Strategy producing query strings containing a keyword.
    """
    keyword = st.sampled_from(VISUAL_BOOST_KEYWORDS)
    prefix = st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "Z")))
    suffix = st.text(min_size=0, max_size=20, alphabet=st.characters(categories=("L", "Z")))

    return st.tuples(prefix, keyword, suffix).map(
        lambda parts: f"{parts[0]} {parts[1]} {parts[2]}".strip()
    )


def st_query_without_keyword() -> st.SearchStrategy[str]:
    """Generate queries that do NOT contain any visual boost keyword.

    Uses a filtered strategy to ensure no keyword appears in the query.

    Returns:
        Strategy producing query strings without any boost keywords.
    """
    # Use words that are unlikely to contain any boost keywords
    safe_words = [
        "document", "report", "analysis", "review", "summary",
        "table", "data", "section", "chapter", "appendix",
        "compliance", "audit", "training", "quality", "batch",
        "material", "equipment", "validation", "calibration", "deviation",
    ]
    return st.lists(
        st.sampled_from(safe_words), min_size=1, max_size=5
    ).map(lambda words: " ".join(words))


def st_mixed_results() -> st.SearchStrategy[list[SearchResult]]:
    """Generate a mixed list of visual and text search results.

    Returns:
        Strategy producing lists with 1-5 results (mix of visual and text).
    """
    return st.lists(
        st.one_of(st_visual_search_result(), st_text_search_result()),
        min_size=1,
        max_size=5,
    )


# ---------------------------------------------------------------------------
# Property 8: Visual Chunk Relevance Boost for Process Queries
# ---------------------------------------------------------------------------


class TestVisualBoost:
    """Property tests for visual chunk relevance boost.

    The _apply_visual_boost() method must:
    - Boost Visual_Chunk scores by VISUAL_BOOST_FACTOR when query contains keywords
    - Leave all scores unchanged when query lacks keywords
    - Never boost text chunks regardless of query content

    **Validates: Requirements 3.5**
    """

    @given(
        query=st_query_with_keyword(),
        results=st.lists(st_visual_search_result(), min_size=1, max_size=5),
        boost_factor=st_boost_factor(),
    )
    @settings(max_examples=200)
    def test_visual_chunks_boosted_when_query_has_keyword(
        self,
        query: str,
        results: list[SearchResult],
        boost_factor: float,
    ) -> None:
        """When query contains a boost keyword, visual chunk scores are
        multiplied by the boost factor.

        **Validates: Requirements 3.5**
        """
        pipeline = RAGPipeline()

        with patch.object(
            pipeline._settings, "visual_boost_factor", boost_factor
        ):
            boosted = pipeline._apply_visual_boost(query, results)

        assert len(boosted) == len(results)

        for original, result in zip(results, boosted):
            expected_score = original.relevance_score * boost_factor
            assert abs(result.relevance_score - expected_score) < 1e-9, (
                f"Visual chunk score not boosted correctly. "
                f"Original={original.relevance_score}, "
                f"Expected={expected_score}, Got={result.relevance_score}, "
                f"Boost factor={boost_factor}, Query='{query}'"
            )

    @given(
        query=st_query_without_keyword(),
        results=st_mixed_results(),
    )
    @settings(max_examples=200)
    def test_no_boost_when_query_lacks_keywords(
        self,
        query: str,
        results: list[SearchResult],
    ) -> None:
        """When query does NOT contain any boost keyword, all scores remain
        unchanged regardless of chunk type.

        **Validates: Requirements 3.5**
        """
        pipeline = RAGPipeline()

        boosted = pipeline._apply_visual_boost(query, results)

        assert len(boosted) == len(results)

        for original, result in zip(results, boosted):
            assert result.relevance_score == original.relevance_score, (
                f"Score changed without keyword in query. "
                f"Original={original.relevance_score}, "
                f"Got={result.relevance_score}, Query='{query}'"
            )

    @given(
        query=st_query_with_keyword(),
        results=st.lists(st_text_search_result(), min_size=1, max_size=5),
        boost_factor=st_boost_factor(),
    )
    @settings(max_examples=200)
    def test_text_chunks_never_boosted(
        self,
        query: str,
        results: list[SearchResult],
        boost_factor: float,
    ) -> None:
        """Text chunks are never boosted regardless of query content.

        Even when the query contains boost keywords, text chunks must
        retain their original relevance scores.

        **Validates: Requirements 3.5**
        """
        pipeline = RAGPipeline()

        with patch.object(
            pipeline._settings, "visual_boost_factor", boost_factor
        ):
            boosted = pipeline._apply_visual_boost(query, results)

        assert len(boosted) == len(results)

        for original, result in zip(results, boosted):
            assert result.relevance_score == original.relevance_score, (
                f"Text chunk score was modified. "
                f"Original={original.relevance_score}, "
                f"Got={result.relevance_score}, "
                f"Boost factor={boost_factor}, Query='{query}'"
            )

    @given(
        query=st_query_with_keyword(),
        boost_factor=st_boost_factor(),
        visual_score=st_relevance_score(),
        text_score=st_relevance_score(),
    )
    @settings(max_examples=200)
    def test_mixed_results_only_visual_boosted(
        self,
        query: str,
        boost_factor: float,
        visual_score: float,
        text_score: float,
    ) -> None:
        """In a mixed result set with keyword query, only visual chunks
        get boosted while text chunks remain unchanged.

        **Validates: Requirements 3.5**
        """
        visual_result = SearchResult(
            document_uuid="visual-uuid-001",
            title="Visual Doc",
            version="1.0",
            excerpt="A flowchart showing the process",
            relevance_score=visual_score,
            metadata={"is_visual": True, "content_type": "visual", "visual_type": "flowchart", "source_page": 1},
            document_type="SOP",
            status="Active",
            tags=[],
            created_at=None,
            updated_at=None,
        )
        text_result = SearchResult(
            document_uuid="text-uuid-001",
            title="Text Doc",
            version="1.0",
            excerpt="Some text content about procedures",
            relevance_score=text_score,
            metadata={"is_visual": False, "content_type": "text"},
            document_type="SOP",
            status="Active",
            tags=[],
            created_at=None,
            updated_at=None,
        )

        results = [visual_result, text_result]
        pipeline = RAGPipeline()

        with patch.object(
            pipeline._settings, "visual_boost_factor", boost_factor
        ):
            boosted = pipeline._apply_visual_boost(query, results)

        # Visual chunk should be boosted
        expected_visual_score = visual_score * boost_factor
        assert abs(boosted[0].relevance_score - expected_visual_score) < 1e-9, (
            f"Visual chunk not boosted correctly. "
            f"Expected={expected_visual_score}, Got={boosted[0].relevance_score}"
        )

        # Text chunk should remain unchanged
        assert boosted[1].relevance_score == text_score, (
            f"Text chunk score changed. "
            f"Expected={text_score}, Got={boosted[1].relevance_score}"
        )
