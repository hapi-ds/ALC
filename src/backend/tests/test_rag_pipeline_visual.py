"""Unit tests for RAG Pipeline visual chunk handling.

Tests cover:
- Visual boost application for process-related queries
- Visual chunk limit enforcement
- Visual-aware context building
- Citation content_type and visual_type fields

References:
    - Task 5.1: Extend RAGPipeline with visual chunk handling
    - Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7
"""

import pytest

from alcoabase.services.knowledge_service import SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline, SourceCitation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pipeline() -> RAGPipeline:
    """Create a RAGPipeline for testing visual chunk methods."""
    return RAGPipeline(top_k=5)


@pytest.fixture
def visual_result() -> SearchResult:
    """A visual chunk search result."""
    return SearchResult(
        document_uuid="doc-001",
        title="Process Flow SOP",
        version="2.0",
        excerpt="Flowchart showing steps: Start -> Prepare -> Execute -> Review -> End",
        relevance_score=0.7,
        metadata={
            "is_visual": True,
            "content_type": "visual",
            "visual_type": "flowchart",
            "source_page": 5,
        },
    )


@pytest.fixture
def text_result() -> SearchResult:
    """A regular text chunk search result."""
    return SearchResult(
        document_uuid="doc-002",
        title="Cleaning SOP",
        version="1.0",
        excerpt="All personnel must follow the cleaning procedure.",
        relevance_score=0.8,
        metadata={"page": 3},
    )


@pytest.fixture
def mixed_results() -> list[SearchResult]:
    """A mix of visual and text search results."""
    return [
        SearchResult(
            document_uuid="doc-001",
            title="Process Flow SOP",
            version="2.0",
            excerpt="Flowchart: Start -> Prepare -> Execute",
            relevance_score=0.7,
            metadata={
                "is_visual": True,
                "content_type": "visual",
                "visual_type": "flowchart",
                "source_page": 5,
            },
        ),
        SearchResult(
            document_uuid="doc-002",
            title="Cleaning SOP",
            version="1.0",
            excerpt="All personnel must follow the cleaning procedure.",
            relevance_score=0.8,
            metadata={"page": 3},
        ),
        SearchResult(
            document_uuid="doc-003",
            title="Decision Tree Doc",
            version="1.0",
            excerpt="Decision tree: If condition A then path B else path C",
            relevance_score=0.6,
            metadata={
                "is_visual": True,
                "content_type": "visual",
                "visual_type": "diagram",
                "source_page": 2,
            },
        ),
        SearchResult(
            document_uuid="doc-004",
            title="Safety Guidelines",
            version="3.0",
            excerpt="Safety protocols for handling chemicals.",
            relevance_score=0.75,
            metadata={"page": 1},
        ),
    ]


# ---------------------------------------------------------------------------
# Visual Boost Tests (Requirement 3.5)
# ---------------------------------------------------------------------------


class TestApplyVisualBoost:
    """Tests for _apply_visual_boost method."""

    def test_boost_applied_when_query_contains_keyword(
        self, pipeline: RAGPipeline, visual_result: SearchResult
    ) -> None:
        """Visual chunks get boosted score when query has process keywords."""
        results = [visual_result]
        boosted = pipeline._apply_visual_boost("show me the process flow", results)

        assert boosted[0].relevance_score == pytest.approx(0.7 * 1.5)

    def test_no_boost_when_query_lacks_keywords(
        self, pipeline: RAGPipeline, visual_result: SearchResult
    ) -> None:
        """Visual chunks keep original score when no keywords match."""
        results = [visual_result]
        boosted = pipeline._apply_visual_boost("what is the temperature?", results)

        assert boosted[0].relevance_score == pytest.approx(0.7)

    def test_text_chunks_never_boosted(
        self, pipeline: RAGPipeline, text_result: SearchResult
    ) -> None:
        """Text chunks are never boosted regardless of query keywords."""
        results = [text_result]
        boosted = pipeline._apply_visual_boost("show me the process flow", results)

        assert boosted[0].relevance_score == pytest.approx(0.8)

    def test_boost_applied_to_multiple_visual_chunks(
        self, pipeline: RAGPipeline, mixed_results: list[SearchResult]
    ) -> None:
        """All visual chunks in results get boosted for keyword queries."""
        boosted = pipeline._apply_visual_boost("workflow diagram", mixed_results)

        # Visual chunks should be boosted
        assert boosted[0].relevance_score == pytest.approx(0.7 * 1.5)  # doc-001
        assert boosted[2].relevance_score == pytest.approx(0.6 * 1.5)  # doc-003

        # Text chunks should remain unchanged
        assert boosted[1].relevance_score == pytest.approx(0.8)  # doc-002
        assert boosted[3].relevance_score == pytest.approx(0.75)  # doc-004

    def test_boost_keyword_case_insensitive(
        self, pipeline: RAGPipeline, visual_result: SearchResult
    ) -> None:
        """Keyword matching is case-insensitive."""
        results = [visual_result]
        boosted = pipeline._apply_visual_boost("PROCESS FLOW", results)

        assert boosted[0].relevance_score == pytest.approx(0.7 * 1.5)

    def test_boost_uses_configurable_factor(
        self, pipeline: RAGPipeline, visual_result: SearchResult
    ) -> None:
        """Boost factor comes from settings (default 1.5)."""
        results = [visual_result]
        boosted = pipeline._apply_visual_boost("process", results)

        # Default factor is 1.5
        assert boosted[0].relevance_score == pytest.approx(0.7 * 1.5)

    def test_boost_with_content_type_visual_metadata(
        self, pipeline: RAGPipeline
    ) -> None:
        """Chunks identified by content_type='visual' also get boosted."""
        result = SearchResult(
            document_uuid="doc-x",
            title="Chart Doc",
            version="1.0",
            excerpt="Chart data",
            relevance_score=0.5,
            metadata={"content_type": "visual", "visual_type": "chart"},
        )
        boosted = pipeline._apply_visual_boost("process steps", [result])

        assert boosted[0].relevance_score == pytest.approx(0.5 * 1.5)

    def test_boost_empty_results(self, pipeline: RAGPipeline) -> None:
        """Empty results list returns empty list."""
        boosted = pipeline._apply_visual_boost("process", [])
        assert boosted == []


# ---------------------------------------------------------------------------
# Visual Chunk Limit Tests (Requirement 3.6)
# ---------------------------------------------------------------------------


class TestLimitVisualChunks:
    """Tests for _limit_visual_chunks method."""

    def test_limits_visual_chunks_to_max(self, pipeline: RAGPipeline) -> None:
        """At most MAX_VISUAL_CHUNKS_PER_QUERY visual chunks are returned."""
        results = [
            SearchResult(
                document_uuid=f"doc-v{i}",
                title=f"Visual Doc {i}",
                version="1.0",
                excerpt=f"Visual content {i}",
                relevance_score=0.9 - i * 0.1,
                metadata={"is_visual": True, "content_type": "visual", "visual_type": "diagram"},
            )
            for i in range(5)
        ]

        limited = pipeline._limit_visual_chunks(results)

        visual_count = sum(
            1 for r in limited
            if r.metadata.get("is_visual", False)
        )
        assert visual_count <= pipeline.MAX_VISUAL_CHUNKS_PER_QUERY

    def test_fills_remaining_slots_with_text(self, pipeline: RAGPipeline) -> None:
        """Remaining slots after visual cap are filled with text chunks."""
        visual_results = [
            SearchResult(
                document_uuid=f"doc-v{i}",
                title=f"Visual Doc {i}",
                version="1.0",
                excerpt=f"Visual content {i}",
                relevance_score=0.9 - i * 0.05,
                metadata={"is_visual": True, "content_type": "visual", "visual_type": "diagram"},
            )
            for i in range(5)
        ]
        text_results = [
            SearchResult(
                document_uuid=f"doc-t{i}",
                title=f"Text Doc {i}",
                version="1.0",
                excerpt=f"Text content {i}",
                relevance_score=0.8 - i * 0.1,
                metadata={"page": i + 1},
            )
            for i in range(3)
        ]

        limited = pipeline._limit_visual_chunks(visual_results + text_results)

        # Should have 3 visual + 2 text = 5 (top_k)
        visual_count = sum(1 for r in limited if r.metadata.get("is_visual", False))
        text_count = sum(1 for r in limited if not r.metadata.get("is_visual", False))
        assert visual_count == 3
        assert text_count == 2
        assert len(limited) == 5

    def test_fewer_visual_than_limit_keeps_all(
        self, pipeline: RAGPipeline
    ) -> None:
        """When fewer visual chunks than limit, all are kept."""
        results = [
            SearchResult(
                document_uuid="doc-v1",
                title="Visual Doc",
                version="1.0",
                excerpt="Visual content",
                relevance_score=0.9,
                metadata={"is_visual": True, "content_type": "visual", "visual_type": "flowchart"},
            ),
            SearchResult(
                document_uuid="doc-t1",
                title="Text Doc",
                version="1.0",
                excerpt="Text content",
                relevance_score=0.8,
                metadata={"page": 1},
            ),
        ]

        limited = pipeline._limit_visual_chunks(results)

        assert len(limited) == 2
        visual_count = sum(1 for r in limited if r.metadata.get("is_visual", False))
        assert visual_count == 1

    def test_results_sorted_by_relevance(
        self, pipeline: RAGPipeline, mixed_results: list[SearchResult]
    ) -> None:
        """Returned results are sorted by relevance score descending."""
        limited = pipeline._limit_visual_chunks(mixed_results)

        scores = [r.relevance_score for r in limited]
        assert scores == sorted(scores, reverse=True)

    def test_no_visual_chunks_returns_text_only(
        self, pipeline: RAGPipeline
    ) -> None:
        """When no visual chunks exist, only text chunks are returned."""
        results = [
            SearchResult(
                document_uuid=f"doc-t{i}",
                title=f"Text Doc {i}",
                version="1.0",
                excerpt=f"Text content {i}",
                relevance_score=0.9 - i * 0.1,
                metadata={"page": i + 1},
            )
            for i in range(4)
        ]

        limited = pipeline._limit_visual_chunks(results)

        assert len(limited) == 4
        assert all(not r.metadata.get("is_visual", False) for r in limited)

    def test_empty_results(self, pipeline: RAGPipeline) -> None:
        """Empty results list returns empty list."""
        limited = pipeline._limit_visual_chunks([])
        assert limited == []


# ---------------------------------------------------------------------------
# Build Context Tests (Requirement 3.2)
# ---------------------------------------------------------------------------


class TestBuildContextVisual:
    """Tests for visual-aware _build_context method."""

    def test_visual_chunk_formatted_with_type_and_page(
        self, pipeline: RAGPipeline, visual_result: SearchResult
    ) -> None:
        """Visual chunks include visual_type and source_page in header."""
        context = pipeline._build_context([visual_result])

        assert "[Source 1: Process Flow SOP v2.0 - flowchart on page 5]" in context
        assert visual_result.excerpt in context

    def test_text_chunk_formatted_without_visual_info(
        self, pipeline: RAGPipeline, text_result: SearchResult
    ) -> None:
        """Text chunks use the standard format without visual info."""
        context = pipeline._build_context([text_result])

        assert "[Source 1: Cleaning SOP v1.0]" in context
        assert "flowchart" not in context
        assert "on page" not in context

    def test_mixed_results_formatted_correctly(
        self, pipeline: RAGPipeline, mixed_results: list[SearchResult]
    ) -> None:
        """Mixed results have correct formatting for each type."""
        context = pipeline._build_context(mixed_results)

        # Visual chunk
        assert "[Source 1: Process Flow SOP v2.0 - flowchart on page 5]" in context
        # Text chunk
        assert "[Source 2: Cleaning SOP v1.0]" in context
        # Another visual chunk
        assert "[Source 3: Decision Tree Doc v1.0 - diagram on page 2]" in context
        # Another text chunk
        assert "[Source 4: Safety Guidelines v3.0]" in context


# ---------------------------------------------------------------------------
# Citation Content Type Tests (Requirement 3.3)
# ---------------------------------------------------------------------------


class TestCitationVisualFields:
    """Tests for content_type and visual_type in citations."""

    def test_visual_citation_has_content_type_visual(
        self, pipeline: RAGPipeline, visual_result: SearchResult
    ) -> None:
        """Visual chunk citations have content_type='visual'."""
        citations = pipeline._extract_citations([visual_result])

        assert citations[0].content_type == "visual"
        assert citations[0].visual_type == "flowchart"

    def test_text_citation_has_content_type_text(
        self, pipeline: RAGPipeline, text_result: SearchResult
    ) -> None:
        """Text chunk citations have content_type='text'."""
        citations = pipeline._extract_citations([text_result])

        assert citations[0].content_type == "text"
        assert citations[0].visual_type is None

    def test_mixed_citations_have_correct_types(
        self, pipeline: RAGPipeline, mixed_results: list[SearchResult]
    ) -> None:
        """Mixed results produce citations with correct content types."""
        citations = pipeline._extract_citations(mixed_results)

        # Find citations by document_uuid
        citation_map = {c.document_uuid: c for c in citations}

        assert citation_map["doc-001"].content_type == "visual"
        assert citation_map["doc-001"].visual_type == "flowchart"
        assert citation_map["doc-002"].content_type == "text"
        assert citation_map["doc-002"].visual_type is None
        assert citation_map["doc-003"].content_type == "visual"
        assert citation_map["doc-003"].visual_type == "diagram"

    def test_is_visual_metadata_triggers_visual_content_type(
        self, pipeline: RAGPipeline
    ) -> None:
        """is_visual=True in metadata triggers content_type='visual'."""
        result = SearchResult(
            document_uuid="doc-x",
            title="Test",
            version="1.0",
            excerpt="content",
            relevance_score=0.5,
            metadata={"is_visual": True, "visual_type": "chart"},
        )
        citations = pipeline._extract_citations([result])

        assert citations[0].content_type == "visual"
        assert citations[0].visual_type == "chart"
