"""Property-based tests for RAG pipeline grounding flag correctness.

Tests Property 15 from the AI Model Integration (vLLM) design document,
validating that:
- When hybrid_search returns at least one result → grounded=True
- When hybrid_search returns zero results → grounded=False and answer=NO_CONTENT_MESSAGE

**Validates: Requirements 7.2, 7.3**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 15)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (7.2, 7.3)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 15: Grounding flag correctness

from unittest.mock import patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.knowledge_service import SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

st_question = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), blacklist_characters="\n\r"),
    min_size=1,
    max_size=100,
)

st_user_id = st.integers(min_value=1, max_value=10000)

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

st_relevance_score = st.floats(
    min_value=0.01, max_value=0.99, allow_nan=False, allow_infinity=False
)


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
def st_non_empty_search_results(draw):
    """Generate a non-empty list of SearchResult objects (1-10 items)."""
    num_results = draw(st.integers(min_value=1, max_value=10))
    return [draw(st_search_result()) for _ in range(num_results)]


# ---------------------------------------------------------------------------
# Property 15a: When hybrid_search returns at least one result → grounded=True
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 15: Grounding flag correctness
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    user_id=st_user_id,
    results=st_non_empty_search_results(),
)
@pytest.mark.asyncio
async def test_grounded_true_when_results_available(
    question: str,
    user_id: int,
    results: list[SearchResult],
) -> None:
    """For any RAG query where hybrid_search returns at least one result
    and the LLM generates a response, the grounded field SHALL be true.

    **Validates: Requirements 7.2**
    """
    pipeline = RAGPipeline()

    # Mock hybrid_search to return the generated results
    with patch.object(
        pipeline._knowledge_service,
        "hybrid_search",
        return_value=(results, len(results)),
    ):
        response = await pipeline.query(
            question=question,
            user_id=user_id,
        )

    assert response.grounded is True, (
        f"Expected grounded=True when {len(results)} search results available, "
        f"but got grounded={response.grounded}"
    )


# ---------------------------------------------------------------------------
# Property 15b: When hybrid_search returns zero results → grounded=False
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 15: Grounding flag correctness
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    user_id=st_user_id,
)
@pytest.mark.asyncio
async def test_grounded_false_when_no_results(
    question: str,
    user_id: int,
) -> None:
    """For any RAG query where hybrid_search returns zero results,
    the grounded field SHALL be false.

    **Validates: Requirements 7.3**
    """
    pipeline = RAGPipeline()

    # Mock hybrid_search to return empty results
    with patch.object(
        pipeline._knowledge_service,
        "hybrid_search",
        return_value=([], 0),
    ):
        response = await pipeline.query(
            question=question,
            user_id=user_id,
        )

    assert response.grounded is False, (
        f"Expected grounded=False when no search results, "
        f"but got grounded={response.grounded}"
    )


# ---------------------------------------------------------------------------
# Property 15c: When no results → answer equals NO_CONTENT_MESSAGE
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 15: Grounding flag correctness
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    user_id=st_user_id,
)
@pytest.mark.asyncio
async def test_no_results_returns_no_content_message(
    question: str,
    user_id: int,
) -> None:
    """For any RAG query where hybrid_search returns zero results,
    the answer SHALL equal NO_CONTENT_MESSAGE.

    **Validates: Requirements 7.3**
    """
    pipeline = RAGPipeline()

    # Mock hybrid_search to return empty results
    with patch.object(
        pipeline._knowledge_service,
        "hybrid_search",
        return_value=([], 0),
    ):
        response = await pipeline.query(
            question=question,
            user_id=user_id,
        )

    assert response.answer == RAGPipeline.NO_CONTENT_MESSAGE, (
        f"Expected NO_CONTENT_MESSAGE when no results.\n"
        f"Expected: {RAGPipeline.NO_CONTENT_MESSAGE!r}\n"
        f"Got:      {response.answer!r}"
    )


# ---------------------------------------------------------------------------
# Property 15d: When results available → answer is NOT NO_CONTENT_MESSAGE
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 15: Grounding flag correctness
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    user_id=st_user_id,
    results=st_non_empty_search_results(),
)
@pytest.mark.asyncio
async def test_results_available_answer_is_not_no_content_message(
    question: str,
    user_id: int,
    results: list[SearchResult],
) -> None:
    """For any RAG query where hybrid_search returns at least one result,
    the answer SHALL NOT be the NO_CONTENT_MESSAGE (a real response is generated).

    **Validates: Requirements 7.2**
    """
    pipeline = RAGPipeline()

    # Mock hybrid_search to return the generated results
    with patch.object(
        pipeline._knowledge_service,
        "hybrid_search",
        return_value=(results, len(results)),
    ):
        response = await pipeline.query(
            question=question,
            user_id=user_id,
        )

    assert response.answer != RAGPipeline.NO_CONTENT_MESSAGE, (
        f"Expected a generated answer when results are available, "
        f"but got NO_CONTENT_MESSAGE."
    )
