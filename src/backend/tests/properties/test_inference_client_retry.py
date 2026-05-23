"""Property-based tests for InferenceClient retry policy correctness.

Tests Property 12 from the AI Model Integration (vLLM) design document,
validating that:
- HTTP 503 responses trigger exactly 2 retries (3 total attempts)
- Connection errors trigger exactly 2 retries (3 total attempts)
- 4xx responses (400, 401, 403, 404, 422) do NOT trigger retries (1 attempt)

**Validates: Requirements 6.2, 6.3**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 12)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (6.2, 6.3)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 12: Retry policy correctness

from unittest.mock import AsyncMock, patch

import httpx
import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.inference_client import (
    InferenceClient,
    InferenceConnectionError,
    InferenceError,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# 4xx status codes that should NOT be retried
NON_RETRYABLE_4XX_CODES = [400, 401, 403, 404, 422]

st_non_retryable_status = st.sampled_from(NON_RETRYABLE_4XX_CODES)

# Strategy for generating a simple model name
st_model_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_/"),
    min_size=1,
    max_size=30,
)

# Strategy for generating simple message content
st_message_content = st.text(min_size=1, max_size=100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chat_payload(model: str, content: str) -> dict:
    """Build a minimal chat completion payload for testing."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.3,
        "max_tokens": 2048,
        "stream": False,
    }


def _make_success_response() -> httpx.Response:
    """Create a mock successful chat completion response."""
    return httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "test response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
    )


def _make_503_response() -> httpx.Response:
    """Create a mock HTTP 503 response."""
    return httpx.Response(
        status_code=503,
        text="Service Unavailable",
    )


def _make_4xx_response(status_code: int) -> httpx.Response:
    """Create a mock 4xx error response."""
    return httpx.Response(
        status_code=status_code,
        text=f"Client error {status_code}",
    )


# ---------------------------------------------------------------------------
# Property 12a: HTTP 503 triggers exactly 2 retries (3 total attempts)
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 12: Retry policy correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    model=st_model_name,
    content=st_message_content,
)
async def test_503_triggers_retries_then_fails(model: str, content: str) -> None:
    """For any HTTP request that receives HTTP 503 on all attempts,
    the InferenceClient SHALL retry exactly 2 additional times (3 total)
    and then raise an InferenceError.

    **Validates: Requirements 6.2, 6.3**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    # Mock the httpx client to always return 503
    mock_request = AsyncMock(return_value=_make_503_response())

    with patch.object(client._client, "request", mock_request):
        with patch("alcoabase.services.inference_client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(InferenceError) as exc_info:
                await client.chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                )

    # Verify exactly 3 total attempts were made
    assert mock_request.call_count == 3, (
        f"Expected 3 total attempts for 503, got {mock_request.call_count}"
    )
    assert exc_info.value.status_code == 503

    await client.close()


# ---------------------------------------------------------------------------
# Property 12b: HTTP 503 with eventual success retries correctly
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 12: Retry policy correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    model=st_model_name,
    content=st_message_content,
    fail_count=st.integers(min_value=1, max_value=2),
)
async def test_503_retries_then_succeeds(
    model: str, content: str, fail_count: int
) -> None:
    """For any HTTP request that receives HTTP 503 followed by a success,
    the InferenceClient SHALL retry and return the successful response.

    **Validates: Requirements 6.2, 6.3**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    # Return 503 for fail_count times, then succeed
    responses = [_make_503_response() for _ in range(fail_count)] + [
        _make_success_response()
    ]
    mock_request = AsyncMock(side_effect=responses)

    with patch.object(client._client, "request", mock_request):
        with patch("alcoabase.services.inference_client.asyncio.sleep", new_callable=AsyncMock):
            result = await client.chat_completion(
                model=model,
                messages=[{"role": "user", "content": content}],
            )

    # Should have made fail_count + 1 total attempts
    assert mock_request.call_count == fail_count + 1, (
        f"Expected {fail_count + 1} attempts, got {mock_request.call_count}"
    )
    assert result == "test response"

    await client.close()


# ---------------------------------------------------------------------------
# Property 12c: Connection errors trigger exactly 2 retries (3 total)
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 12: Retry policy correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    model=st_model_name,
    content=st_message_content,
)
async def test_connection_error_triggers_retries(model: str, content: str) -> None:
    """For any HTTP request that encounters a connection error on all attempts,
    the InferenceClient SHALL retry exactly 2 additional times (3 total)
    and then raise an InferenceConnectionError.

    **Validates: Requirements 6.2, 6.3**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    # Mock the httpx client to always raise ConnectError
    mock_request = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with patch.object(client._client, "request", mock_request):
        with patch("alcoabase.services.inference_client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(InferenceConnectionError):
                await client.chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                )

    # Verify exactly 3 total attempts were made
    assert mock_request.call_count == 3, (
        f"Expected 3 total attempts for connection error, got {mock_request.call_count}"
    )

    await client.close()


# ---------------------------------------------------------------------------
# Property 12d: 4xx responses do NOT trigger retries (exactly 1 attempt)
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 12: Retry policy correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    model=st_model_name,
    content=st_message_content,
    status_code=st_non_retryable_status,
)
async def test_4xx_does_not_retry(
    model: str, content: str, status_code: int
) -> None:
    """For any HTTP request that receives a 4xx response (400, 401, 403, 404, 422),
    the InferenceClient SHALL NOT retry and SHALL raise an error immediately
    with exactly 1 attempt.

    **Validates: Requirements 6.2, 6.3**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    mock_request = AsyncMock(return_value=_make_4xx_response(status_code))

    with patch.object(client._client, "request", mock_request):
        with patch("alcoabase.services.inference_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(InferenceError) as exc_info:
                await client.chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                )

    # Verify exactly 1 attempt was made (no retries)
    assert mock_request.call_count == 1, (
        f"Expected 1 attempt for {status_code}, got {mock_request.call_count}"
    )
    # Verify no sleep was called (no backoff)
    mock_sleep.assert_not_called()
    # Verify the error contains the correct status code
    assert exc_info.value.status_code == status_code

    await client.close()


# ---------------------------------------------------------------------------
# Property 12e: Exponential backoff delays are correct (1s, 2s)
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 12: Retry policy correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    model=st_model_name,
    content=st_message_content,
)
async def test_503_backoff_delays_are_correct(model: str, content: str) -> None:
    """For any HTTP request that receives HTTP 503 on all attempts,
    the InferenceClient SHALL use exponential backoff with delays of
    1s after the first failure and 2s after the second failure.

    **Validates: Requirements 6.2, 6.3**
    """
    client = InferenceClient(base_url="http://localhost:8000")

    mock_request = AsyncMock(return_value=_make_503_response())

    with patch.object(client._client, "request", mock_request):
        with patch("alcoabase.services.inference_client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(InferenceError):
                await client.chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": content}],
                )

    # Verify backoff delays: 1s after first failure, 2s after second
    assert mock_sleep.call_count == 2, (
        f"Expected 2 sleep calls, got {mock_sleep.call_count}"
    )
    sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
    assert sleep_args == [1.0, 2.0], (
        f"Expected backoff delays [1.0, 2.0], got {sleep_args}"
    )

    await client.close()
