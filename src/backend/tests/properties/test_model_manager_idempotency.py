"""Property-based tests for same-role idempotency.

Tests Property 3 from the AI Model Integration (vLLM) design document,
validating that:
- For any ModelRole that is already loaded and ready (is_ready=true,
  current_role matches), calling `ensure_model` with that same role
  SHALL return immediately without sending any HTTP requests to the
  vLLM server and without acquiring the model swap lock.

**Validates: Requirements 1.7, 10.2**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 3)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (1.7, 10.2)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 3: Same-role idempotency

from unittest.mock import AsyncMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.model_manager import ModelManager, ModelRole


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# CHAT and OCR roles that go through the idempotency check path
# (EMBEDDING always returns immediately regardless, so it's excluded)
st_swappable_role = st.sampled_from([ModelRole.CHAT, ModelRole.OCR])

# Operating modes that use real vLLM routing (not mock)
st_real_mode = st.sampled_from(["gpu", "cpu"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(mode: str) -> object:
    """Create a mock settings object with standard test configuration."""

    class MockSettings:
        model_manager_mode = mode
        vllm_base_url = "http://localhost:8000"
        vllm_embedding_url = "http://localhost:8001"
        model_chat_name = "Qwen/Qwen3.6-35B-A3B"
        model_chat_path = "/models/qwen3.6-35b-a3b"
        model_chat_max_gpu_memory_gb = 24
        model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        model_embedding_path = "/models/qwen3-embedding-0.6b"
        model_embedding_dimension = 1024
        model_ocr_name = "google/gemma-4-E4B-it"
        model_ocr_path = "/models/gemma-4-e4b-it"

    return MockSettings()


def _make_inference_client_mock() -> AsyncMock:
    """Create a mock InferenceClient that tracks call counts."""
    client = AsyncMock()
    client.health_check = AsyncMock(return_value=True)
    client.list_models = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Property 3: Same-role idempotency — no HTTP calls on second invocation
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 3: Same-role idempotency
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(role=st_swappable_role, mode=st_real_mode)
async def test_same_role_no_http_calls_on_second_invocation(
    role: ModelRole, mode: str
) -> None:
    """For any CHAT/OCR role already loaded and ready, calling ensure_model
    with the same role SHALL return immediately without sending any HTTP
    requests to the vLLM server.

    **Validates: Requirements 1.7, 10.2**
    """
    mock_settings = _make_settings(mode)
    client_mock = _make_inference_client_mock()

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    # Simulate that the model is already loaded and ready
    manager._current_role = role
    manager._current_model_name = (
        mock_settings.model_chat_name
        if role == ModelRole.CHAT
        else mock_settings.model_ocr_name
    )
    manager._is_ready = True

    # Reset call counts to track only the second invocation
    client_mock.health_check.reset_mock()
    client_mock.list_models.reset_mock()

    # Call ensure_model with the same role
    url = await manager.ensure_model(role)

    # Verify correct URL returned
    assert url == mock_settings.vllm_base_url, (
        f"Expected {mock_settings.vllm_base_url}, got {url}"
    )

    # Verify NO HTTP calls were made
    client_mock.health_check.assert_not_called()
    client_mock.list_models.assert_not_called()

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 3: Same-role idempotency — lock NOT acquired
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 3: Same-role idempotency
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(role=st_swappable_role, mode=st_real_mode)
async def test_same_role_does_not_acquire_lock(
    role: ModelRole, mode: str
) -> None:
    """For any CHAT/OCR role already loaded and ready, calling ensure_model
    with the same role SHALL return without acquiring the model swap lock.

    We verify this by holding the lock externally — if ensure_model tried
    to acquire it, it would block indefinitely (deadlock). Since it returns
    immediately, the lock was not acquired.

    **Validates: Requirements 1.7, 10.2**
    """
    mock_settings = _make_settings(mode)
    client_mock = _make_inference_client_mock()

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    # Simulate that the model is already loaded and ready
    manager._current_role = role
    manager._current_model_name = (
        mock_settings.model_chat_name
        if role == ModelRole.CHAT
        else mock_settings.model_ocr_name
    )
    manager._is_ready = True

    # Hold the lock externally — if ensure_model tries to acquire it,
    # it would block forever (since asyncio.Lock is not reentrant)
    async with manager._lock:
        # This should return immediately without trying to acquire the lock
        url = await manager.ensure_model(role)

    assert url == mock_settings.vllm_base_url, (
        f"Expected {mock_settings.vllm_base_url}, got {url}"
    )

    await manager.shutdown()
