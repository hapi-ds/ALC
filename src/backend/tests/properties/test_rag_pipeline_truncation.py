"""Property-based tests for RAG pipeline context truncation by relevance.

Tests Property 13 from the AI Model Integration (vLLM) design document,
validating that the context truncation algorithm:
1. Removes chunks starting from the lowest relevance score when total tokens exceed 8192
2. Always retains at least the single highest-relevance chunk regardless of its size
3. After truncation, total tokens ≤ 8192 (or only the highest-relevance chunk remains)
4. Chunks are removed in order of ascending relevance score

**Validates: Requirements 7.5, 7.6**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 13)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (7.5, 7.6)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 13: Context truncation by relevance

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline

_MAX_CONTEXT_TOKENS = 8192


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def _count_tokens_for_result(result: SearchResult, index: int) -> int:
    """Count approximate tokens for a single search result including header.

    Mirrors the token counting logic in RAGPipeline._truncate_context.
    """
    header = f"[Source {index}: {result.title} v{result.version}]"
    return len(header.split()) + len(result.excerpt.split())


def _count_total_tokens(results: list[SearchResult]) -> int:
    """Count total tokens across all search results."""
    total = 0
    for i, result in enumerate(results, 1):
        total += _count_tokens_for_result(result, i)
    return total


def _make_excerpt(num_tokens: int) -> str:
    """Create an excerpt string with approximately num_tokens whitespace-split words."""
    return " ".join(f"word{i}" for i in range(num_tokens))


# Strategy for generating relevance scores
st_relevance_score = st.floats(min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False)

# Strategy for generating a SearchResult with a controllable token count
st_title = st.sampled_from(["Doc", "Report", "SOP", "Policy", "Guide"])
st_version = st.sampled_from(["1.0", "2.0", "3.0", "1.1", "2.1"])


@st.composite
def st_search_result_with_tokens(draw, min_tokens: int = 10, max_tokens: int = 100):
    """Generate a SearchResult with a controlled number of excerpt tokens."""
    num_tokens = draw(st.integers(min_value=min_tokens, max_value=max_tokens))
    excerpt = _make_excerpt(num_tokens)
    return SearchResult(
        document_uuid=draw(st.uuids().map(str)),
        title=draw(st_title),
        version=draw(st_version),
        excerpt=excerpt,
        relevance_score=draw(st_relevance_score),
        metadata={},
    )


@st.composite
def st_exceeding_results(draw):
    """Generate a list of SearchResults whose combined tokens exceed 8192.

    Strategy: generate 4-8 results each with 1500-3000 tokens to guarantee
    the total exceeds 8192 without needing a filter.
    """
    num_results = draw(st.integers(min_value=4, max_value=8))
    results = []
    for _ in range(num_results):
        num_tokens = draw(st.integers(min_value=1500, max_value=3000))
        result = SearchResult(
            document_uuid=draw(st.uuids().map(str)),
            title=draw(st_title),
            version=draw(st_version),
            excerpt=_make_excerpt(num_tokens),
            relevance_score=draw(st_relevance_score),
            metadata={},
        )
        results.append(result)
    return results


@st.composite
def st_small_results(draw):
    """Generate a list of SearchResults whose combined tokens are within 8192."""
    num_results = draw(st.integers(min_value=1, max_value=5))
    results = []
    for _ in range(num_results):
        num_tokens = draw(st.integers(min_value=10, max_value=100))
        result = SearchResult(
            document_uuid=draw(st.uuids().map(str)),
            title=draw(st_title),
            version=draw(st_version),
            excerpt=_make_excerpt(num_tokens),
            relevance_score=draw(st_relevance_score),
            metadata={},
        )
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Property 13a: Lowest-relevance chunks are removed first
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 13: Context truncation by relevance
@settings(max_examples=100, deadline=None)
@given(results=st_exceeding_results())
def test_lowest_relevance_chunks_removed_first(
    results: list[SearchResult],
) -> None:
    """For any set of search results whose combined token count exceeds 8192,
    the truncation algorithm SHALL remove chunks starting from the lowest
    relevance score.

    **Validates: Requirements 7.5, 7.6**
    """
    pipeline = RAGPipeline()
    truncated = pipeline._truncate_context(results)

    # All retained results should have relevance >= any removed result
    retained_scores = {r.relevance_score for r in truncated}
    removed = [r for r in results if r not in truncated]
    removed_scores = {r.relevance_score for r in removed}

    if removed_scores and retained_scores:
        # The minimum retained score should be >= the maximum removed score
        # (except for the highest-relevance chunk which is always kept)
        highest_score = max(r.relevance_score for r in results)
        # Among non-highest retained chunks, their scores should be >= removed scores
        non_highest_retained = [
            r for r in truncated if r.relevance_score != highest_score
        ]
        if non_highest_retained and removed:
            min_retained = min(r.relevance_score for r in non_highest_retained)
            max_removed = max(r.relevance_score for r in removed)
            assert min_retained >= max_removed, (
                f"A retained chunk (score={min_retained}) has lower relevance "
                f"than a removed chunk (score={max_removed}). "
                f"Lowest-relevance chunks should be removed first."
            )


# ---------------------------------------------------------------------------
# Property 13b: Highest-relevance chunk is ALWAYS retained
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 13: Context truncation by relevance
@settings(max_examples=100, deadline=None)
@given(results=st_exceeding_results())
def test_highest_relevance_chunk_always_retained(
    results: list[SearchResult],
) -> None:
    """For any set of search results, the highest-relevance chunk SHALL
    always be retained regardless of its size.

    **Validates: Requirements 7.5, 7.6**
    """
    pipeline = RAGPipeline()
    truncated = pipeline._truncate_context(results)

    # Find the highest-relevance chunk in the original results
    highest_result = max(results, key=lambda r: r.relevance_score)

    # It must be present in the truncated results
    assert highest_result in truncated, (
        f"Highest-relevance chunk (score={highest_result.relevance_score}) "
        f"was removed during truncation. It SHALL always be retained."
    )


# ---------------------------------------------------------------------------
# Property 13c: After truncation, total tokens ≤ 8192 or only highest remains
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 13: Context truncation by relevance
@settings(max_examples=100, deadline=None)
@given(results=st_exceeding_results())
def test_truncated_within_token_limit_or_single_highest(
    results: list[SearchResult],
) -> None:
    """After truncation, total tokens SHALL be ≤ 8192, OR only the single
    highest-relevance chunk remains (if it alone exceeds the limit).

    **Validates: Requirements 7.5, 7.6**
    """
    pipeline = RAGPipeline()
    truncated = pipeline._truncate_context(results)

    total_tokens = _count_total_tokens(truncated)

    if len(truncated) == 1:
        # If only one chunk remains, it must be the highest-relevance one
        highest_result = max(results, key=lambda r: r.relevance_score)
        assert truncated[0] is highest_result, (
            "When only one chunk remains, it must be the highest-relevance chunk."
        )
    else:
        # If multiple chunks remain, total must be within limit
        assert total_tokens <= _MAX_CONTEXT_TOKENS, (
            f"After truncation with {len(truncated)} chunks remaining, "
            f"total tokens ({total_tokens}) exceeds limit ({_MAX_CONTEXT_TOKENS})."
        )


# ---------------------------------------------------------------------------
# Property 13d: Chunks are removed in order of ascending relevance score
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 13: Context truncation by relevance
@settings(max_examples=100, deadline=None)
@given(results=st_exceeding_results())
def test_chunks_removed_in_ascending_relevance_order(
    results: list[SearchResult],
) -> None:
    """Chunks SHALL be removed in order of ascending relevance score.
    This means if chunk A (score=0.3) and chunk B (score=0.5) are both
    removed, chunk A must have been removed before chunk B.

    We verify this by checking that the set of removed chunks consists of
    the lowest-scored chunks (excluding the highest which is always kept).

    **Validates: Requirements 7.5, 7.6**
    """
    pipeline = RAGPipeline()
    truncated = pipeline._truncate_context(results)

    retained_set = set(id(r) for r in truncated)
    removed = [r for r in results if id(r) not in retained_set]

    if not removed:
        # Nothing was removed, nothing to verify
        return

    # The highest-relevance chunk must be retained
    highest_result = max(results, key=lambda r: r.relevance_score)
    assert id(highest_result) in retained_set

    # All removed chunks should have scores <= all non-highest retained chunks
    non_highest_retained = [
        r for r in truncated if r is not highest_result
    ]

    if non_highest_retained:
        min_non_highest_retained_score = min(
            r.relevance_score for r in non_highest_retained
        )
        for removed_result in removed:
            assert removed_result.relevance_score <= min_non_highest_retained_score, (
                f"Removed chunk (score={removed_result.relevance_score}) has higher "
                f"relevance than a retained non-highest chunk "
                f"(score={min_non_highest_retained_score}). "
                f"Chunks should be removed in ascending relevance order."
            )


# ---------------------------------------------------------------------------
# Property 13e: Empty input returns empty output
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 13: Context truncation by relevance
def test_empty_input_returns_empty() -> None:
    """When given an empty list of search results, truncation SHALL return
    an empty list.

    **Validates: Requirements 7.5, 7.6**
    """
    pipeline = RAGPipeline()
    result = pipeline._truncate_context([])
    assert result == [], "Empty input should return empty output."


# ---------------------------------------------------------------------------
# Property 13f: Results within limit are not truncated
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 13: Context truncation by relevance
@settings(max_examples=100, deadline=None)
@given(results=st_small_results())
def test_results_within_limit_not_truncated(
    results: list[SearchResult],
) -> None:
    """For any set of search results whose combined token count does NOT
    exceed 8192, all results SHALL be retained without truncation.

    **Validates: Requirements 7.5, 7.6**
    """
    pipeline = RAGPipeline()

    total_tokens = _count_total_tokens(results)
    # The strategy generates small results, but double-check
    if total_tokens > _MAX_CONTEXT_TOKENS:
        return  # Skip this example; it exceeds the limit

    truncated = pipeline._truncate_context(results)

    assert len(truncated) == len(results), (
        f"Results within token limit should not be truncated. "
        f"Expected {len(results)} results, got {len(truncated)}. "
        f"Total tokens: {total_tokens}"
    )
