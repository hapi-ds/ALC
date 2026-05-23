"""Property-based tests for visual source citation formatting.

Tests Property 7: Visual source citation formatting from the
multimodal-knowledge-base design document.

Property 7 validates that for any Visual_Chunk with random metadata
(title, version, visual_type, source_page), the _build_context() method
formats the citation correctly:
- Visual chunks: [Source N: {title} v{version} - {visual_type} on page {source_page}]
- Text chunks: [Source N: {title} v{version}]

**Validates: Requirements 3.2, 3.3**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 7)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/rag_pipeline.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VISUAL_TYPES = ["flowchart", "chart", "diagram", "mixed"]


def st_title() -> st.SearchStrategy[str]:
    """Generate realistic document titles (non-empty, printable)."""
    return st.text(
        alphabet=st.characters(
            categories=("L", "N", "P", "S", "Z"),
            exclude_characters="\x00\n\r",
        ),
        min_size=1,
        max_size=80,
    ).filter(lambda s: len(s.strip()) > 0)


def st_version() -> st.SearchStrategy[str]:
    """Generate version strings like '1.0', '2.3', '10.1'."""
    return st.builds(
        lambda major, minor: f"{major}.{minor}",
        major=st.integers(min_value=1, max_value=99),
        minor=st.integers(min_value=0, max_value=99),
    )


def st_visual_type() -> st.SearchStrategy[str]:
    """Generate one of the valid visual type classifications."""
    return st.sampled_from(VISUAL_TYPES)


def st_source_page() -> st.SearchStrategy[int]:
    """Generate page numbers (1-indexed)."""
    return st.integers(min_value=1, max_value=500)


def st_excerpt() -> st.SearchStrategy[str]:
    """Generate non-empty excerpt text."""
    return st.text(
        alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
        min_size=5,
        max_size=200,
    ).filter(lambda s: len(s.strip()) > 0)


def st_visual_search_result() -> st.SearchStrategy[SearchResult]:
    """Generate a SearchResult representing a Visual_Chunk."""
    return st.builds(
        lambda title, version, visual_type, source_page, excerpt: SearchResult(
            document_uuid="doc-" + "a" * 32,
            title=title,
            version=version,
            excerpt=excerpt,
            relevance_score=0.8,
            metadata={
                "is_visual": True,
                "content_type": "visual",
                "visual_type": visual_type,
                "source_page": source_page,
            },
        ),
        title=st_title(),
        version=st_version(),
        visual_type=st_visual_type(),
        source_page=st_source_page(),
        excerpt=st_excerpt(),
    )


def st_text_search_result() -> st.SearchStrategy[SearchResult]:
    """Generate a SearchResult representing a regular text chunk."""
    return st.builds(
        lambda title, version, excerpt: SearchResult(
            document_uuid="doc-" + "b" * 32,
            title=title,
            version=version,
            excerpt=excerpt,
            relevance_score=0.7,
            metadata={},
        ),
        title=st_title(),
        version=st_version(),
        excerpt=st_excerpt(),
    )


# ---------------------------------------------------------------------------
# Property 7: Visual Source Citation Formatting
# ---------------------------------------------------------------------------


class TestVisualCitationFormatting:
    """Property tests for visual source citation formatting.

    For any Visual_Chunk with random metadata, _build_context() must:
    - Format visual chunks with the pattern:
      [Source N: {title} v{version} - {visual_type} on page {source_page}]
    - Format text chunks with the pattern:
      [Source N: {title} v{version}]
    - Always include visual_type and source_page for visual chunks

    **Validates: Requirements 3.2, 3.3**
    """

    def _make_pipeline(self) -> RAGPipeline:
        """Create a RAGPipeline instance for testing _build_context."""
        return RAGPipeline(knowledge_service=None, model_manager=None, inference_client=None)

    @given(result=st_visual_search_result())
    @settings(max_examples=200)
    def test_visual_chunk_citation_contains_correct_pattern(
        self,
        result: SearchResult,
    ) -> None:
        """Visual chunks are formatted with visual_type and page number.

        **Validates: Requirements 3.2, 3.3**
        """
        pipeline = self._make_pipeline()
        context = pipeline._build_context([result])

        visual_type = result.metadata["visual_type"]
        source_page = result.metadata["source_page"]
        expected_header = (
            f"[Source 1: {result.title} v{result.version} "
            f"- {visual_type} on page {source_page}]"
        )

        assert expected_header in context, (
            f"Expected visual citation header not found in context.\n"
            f"Expected: {expected_header!r}\n"
            f"Got context: {context!r}"
        )

    @given(result=st_text_search_result())
    @settings(max_examples=200)
    def test_text_chunk_citation_contains_correct_pattern(
        self,
        result: SearchResult,
    ) -> None:
        """Text chunks are formatted without visual_type or page number.

        **Validates: Requirements 3.2, 3.3**
        """
        pipeline = self._make_pipeline()
        context = pipeline._build_context([result])

        expected_header = f"[Source 1: {result.title} v{result.version}]"

        assert expected_header in context, (
            f"Expected text citation header not found in context.\n"
            f"Expected: {expected_header!r}\n"
            f"Got context: {context!r}"
        )

        # Text chunks should NOT contain " - " visual type pattern
        visual_pattern = f"[Source 1: {result.title} v{result.version} -"
        assert visual_pattern not in context, (
            f"Text chunk citation should not contain visual type pattern.\n"
            f"Got context: {context!r}"
        )

    @given(result=st_visual_search_result())
    @settings(max_examples=200)
    def test_visual_chunk_always_includes_type_and_page(
        self,
        result: SearchResult,
    ) -> None:
        """Visual chunks always include visual_type and source_page in citation.

        **Validates: Requirements 3.2, 3.3**
        """
        pipeline = self._make_pipeline()
        context = pipeline._build_context([result])

        visual_type = result.metadata["visual_type"]
        source_page = result.metadata["source_page"]

        # The visual type must appear in the context
        assert f"- {visual_type} on page" in context, (
            f"Visual type '{visual_type}' not found in citation.\n"
            f"Context: {context!r}"
        )

        # The page number must appear in the context
        assert f"on page {source_page}]" in context, (
            f"Source page '{source_page}' not found in citation.\n"
            f"Context: {context!r}"
        )

    @given(
        visual_result=st_visual_search_result(),
        text_result=st_text_search_result(),
    )
    @settings(max_examples=200)
    def test_mixed_results_format_each_type_correctly(
        self,
        visual_result: SearchResult,
        text_result: SearchResult,
    ) -> None:
        """When both visual and text chunks are present, each is formatted
        according to its type.

        **Validates: Requirements 3.2, 3.3**
        """
        pipeline = self._make_pipeline()
        context = pipeline._build_context([visual_result, text_result])

        # Visual chunk (Source 1) should have visual formatting
        visual_type = visual_result.metadata["visual_type"]
        source_page = visual_result.metadata["source_page"]
        expected_visual_header = (
            f"[Source 1: {visual_result.title} v{visual_result.version} "
            f"- {visual_type} on page {source_page}]"
        )
        assert expected_visual_header in context, (
            f"Visual citation header not found.\n"
            f"Expected: {expected_visual_header!r}\n"
            f"Context: {context!r}"
        )

        # Text chunk (Source 2) should have text formatting
        expected_text_header = (
            f"[Source 2: {text_result.title} v{text_result.version}]"
        )
        assert expected_text_header in context, (
            f"Text citation header not found.\n"
            f"Expected: {expected_text_header!r}\n"
            f"Context: {context!r}"
        )
