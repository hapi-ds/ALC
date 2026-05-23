"""Property-based tests for RAG pipeline source citation formatting.

Tests Property 14 from the AI Model Integration (vLLM) design document,
validating that the _build_context method formats each chunk with the pattern:
    [Source N: {title} v{version}]
    {excerpt}
where N is the 1-based index, and chunks are separated by double newlines.

**Validates: Requirements 7.4**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 14)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (7.4)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 14: Source citation formatting

import re

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

st_title = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), blacklist_characters="\n\r"),
    min_size=1,
    max_size=50,
)
st_version = st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True)
st_excerpt = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z", "S"), blacklist_characters=""),
    min_size=1,
    max_size=200,
)
st_relevance_score = st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False)


@st.composite
def st_search_result(draw):
    """Generate a random SearchResult object."""
    return SearchResult(
        document_uuid=draw(st.uuids().map(str)),
        title=draw(st_title),
        version=draw(st_version),
        excerpt=draw(st_excerpt),
        relevance_score=draw(st_relevance_score),
        metadata={},
    )


@st.composite
def st_search_result_list(draw):
    """Generate a non-empty list of SearchResult objects (1-10 items)."""
    num_results = draw(st.integers(min_value=1, max_value=10))
    return [draw(st_search_result()) for _ in range(num_results)]


# ---------------------------------------------------------------------------
# Property 14a: Each chunk is formatted as [Source N: {title} v{version}]\n{excerpt}
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 14: Source citation formatting
@settings(max_examples=100, deadline=None)
@given(results=st_search_result_list())
def test_each_chunk_formatted_with_source_header(
    results: list[SearchResult],
) -> None:
    """For any list of SearchResult objects, each chunk SHALL be formatted
    with the pattern [Source N: {title} v{version}] followed by the chunk text.

    **Validates: Requirements 7.4**
    """
    pipeline = RAGPipeline()
    context = pipeline._build_context(results)

    # Split by double newline to get individual chunks
    chunks = context.split("\n\n")

    assert len(chunks) == len(results), (
        f"Expected {len(results)} formatted chunks, got {len(chunks)}."
    )

    for i, (chunk, result) in enumerate(zip(chunks, results), 1):
        expected_header = f"[Source {i}: {result.title} v{result.version}]"
        expected_chunk = f"{expected_header}\n{result.excerpt}"
        assert chunk == expected_chunk, (
            f"Chunk {i} formatting mismatch.\n"
            f"Expected: {expected_chunk!r}\n"
            f"Got:      {chunk!r}"
        )


# ---------------------------------------------------------------------------
# Property 14b: N is 1-based index
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 14: Source citation formatting
@settings(max_examples=100, deadline=None)
@given(results=st_search_result_list())
def test_source_index_is_one_based(
    results: list[SearchResult],
) -> None:
    """For any list of SearchResult objects, the source index N SHALL be
    1-based (starting from 1, incrementing by 1).

    **Validates: Requirements 7.4**
    """
    pipeline = RAGPipeline()
    context = pipeline._build_context(results)

    # Find all [Source N: ...] patterns
    source_indices = [int(m) for m in re.findall(r"\[Source (\d+):", context)]

    expected_indices = list(range(1, len(results) + 1))
    assert source_indices == expected_indices, (
        f"Source indices should be 1-based sequential. "
        f"Expected {expected_indices}, got {source_indices}."
    )


# ---------------------------------------------------------------------------
# Property 14c: Chunks are separated by double newlines
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 14: Source citation formatting
@settings(max_examples=100, deadline=None)
@given(results=st_search_result_list())
def test_chunks_separated_by_double_newlines(
    results: list[SearchResult],
) -> None:
    """For any list of SearchResult objects with more than one result,
    chunks SHALL be separated by double newlines (\\n\\n).

    **Validates: Requirements 7.4**
    """
    pipeline = RAGPipeline()
    context = pipeline._build_context(results)

    if len(results) == 1:
        # Single chunk should have no double newline separator
        assert "\n\n" not in context, (
            "Single chunk should not contain double newline separator."
        )
    else:
        # Multiple chunks: splitting by \n\n should yield exactly len(results) parts
        parts = context.split("\n\n")
        assert len(parts) == len(results), (
            f"Expected {len(results)} chunks separated by double newlines, "
            f"got {len(parts)} parts."
        )


# ---------------------------------------------------------------------------
# Property 14d: All chunks in the input appear in the output
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 14: Source citation formatting
@settings(max_examples=100, deadline=None)
@given(results=st_search_result_list())
def test_all_input_chunks_appear_in_output(
    results: list[SearchResult],
) -> None:
    """For any list of SearchResult objects, all chunk excerpts from the
    input SHALL appear in the output context.

    **Validates: Requirements 7.4**
    """
    pipeline = RAGPipeline()
    context = pipeline._build_context(results)

    for result in results:
        assert result.excerpt in context, (
            f"Excerpt not found in output context: {result.excerpt!r}"
        )


# ---------------------------------------------------------------------------
# Property 14e: Empty input returns empty output
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 14: Source citation formatting
def test_empty_input_returns_empty_context() -> None:
    """When given an empty list of search results, _build_context SHALL
    return an empty string.

    **Validates: Requirements 7.4**
    """
    pipeline = RAGPipeline()
    context = pipeline._build_context([])
    assert context == "", f"Expected empty string, got: {context!r}"
