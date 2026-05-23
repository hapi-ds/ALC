"""Property-based tests for InferenceClient chat response extraction.

Tests Property 5 from the AI Model Integration (vLLM) design document,
validating that:
- For any valid chat completion response JSON from vLLM containing
  `choices[0].message.content`, the extracted answer exactly equals
  that content string with no modification (no trimming, encoding
  changes, or other transformations).

**Validates: Requirements 2.4**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 5)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (2.4)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 5: Chat response extraction

from unittest.mock import AsyncMock, patch

import httpx
import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.inference_client import InferenceClient


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for generating arbitrary content strings that vLLM might return.
# Includes whitespace, unicode, special characters, empty-ish strings, etc.
st_response_content = st.text(min_size=1, max_size=500)

# Strategy for content with leading/trailing whitespace to verify no trimming
st_whitespace_content = st.text(min_size=1, max_size=200).map(
    lambda s: f"  {s}  \n\t"
)

# Strategy for model names
st_model_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_/"),
    min_size=1,
    max_size=30,
)

# Strategy for generating valid chat completion response IDs
st_response_id = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=5,
    max_size=30,
).map(lambda s: f"chatcmpl-{s}")

# Strategy for finish reasons
st_finish_reason = st.sampled_from(["stop", "length", "content_filter"])

# Strategy for token usage counts
st_token_count = st.integers(min_value=1, max_value=10000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chat_response(
    content: str,
    response_id: str = "chatcmpl-test",
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> httpx.Response:
    """Create a mock successful chat completion response with given content."""
    return httpx.Response(
        status_code=200,
        json={
            "id": response_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        },
    )


# ---------------------------------------------------------------------------
# Property 5a: Response content is returned without modification
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 5: Chat response extraction
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    content=st_response_content,
    model=st_model_name,
)
async def test_chat_response_extracted_without_modification(
    content: str, model: str
) -> None:
    """For any valid chat completion response JSON from vLLM containing
    choices[0].message.content, the extracted answer SHALL exactly equal
    that content string with no modification.

    **Validates: Requirements 2.4**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    mock_request = AsyncMock(return_value=_make_chat_response(content))

    with patch.object(client._client, "request", mock_request):
        result = await client.chat_completion(
            model=model,
            messages=[{"role": "user", "content": "test question"}],
        )

    # The extracted result must be EXACTLY the content string — no modification
    assert result == content, (
        f"Response content was modified.\n"
        f"Expected: {content!r}\n"
        f"Got:      {result!r}"
    )

    await client.close()


# ---------------------------------------------------------------------------
# Property 5b: Whitespace in content is preserved (no trimming)
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 5: Chat response extraction
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    content=st_whitespace_content,
    model=st_model_name,
)
async def test_chat_response_preserves_whitespace(
    content: str, model: str
) -> None:
    """For any valid chat completion response with leading/trailing whitespace
    in choices[0].message.content, the extracted answer SHALL preserve all
    whitespace exactly as received — no stripping or trimming.

    **Validates: Requirements 2.4**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    mock_request = AsyncMock(return_value=_make_chat_response(content))

    with patch.object(client._client, "request", mock_request):
        result = await client.chat_completion(
            model=model,
            messages=[{"role": "user", "content": "test question"}],
        )

    assert result == content, (
        f"Whitespace was modified in response content.\n"
        f"Expected: {content!r}\n"
        f"Got:      {result!r}"
    )

    await client.close()


# ---------------------------------------------------------------------------
# Property 5c: Response extraction is independent of response metadata
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 5: Chat response extraction
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    content=st_response_content,
    model=st_model_name,
    response_id=st_response_id,
    finish_reason=st_finish_reason,
    prompt_tokens=st_token_count,
    completion_tokens=st_token_count,
)
async def test_chat_response_independent_of_metadata(
    content: str,
    model: str,
    response_id: str,
    finish_reason: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """For any valid chat completion response with varying metadata (id,
    finish_reason, usage tokens), the extracted answer SHALL always be
    exactly choices[0].message.content regardless of other response fields.

    **Validates: Requirements 2.4**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    mock_request = AsyncMock(
        return_value=_make_chat_response(
            content=content,
            response_id=response_id,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    )

    with patch.object(client._client, "request", mock_request):
        result = await client.chat_completion(
            model=model,
            messages=[{"role": "user", "content": "test question"}],
        )

    assert result == content, (
        f"Response content was modified or affected by metadata.\n"
        f"Expected: {content!r}\n"
        f"Got:      {result!r}"
    )

    await client.close()
