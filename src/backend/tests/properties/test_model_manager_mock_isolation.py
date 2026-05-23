"""Property-based tests for mock mode isolation.

Tests Property 11 from the AI Model Integration (vLLM) design document,
validating that:
- For any inference operation (chat completion, embedding generation,
  OCR extraction) when `MODEL_MANAGER_MODE` is 'mock', the system SHALL
  return mock/placeholder responses without making any HTTP requests to
  any vLLM server, and mock embeddings SHALL have exactly
  `model_embedding_dimension` dimensions.

**Validates: Requirements 2.7, 3.7, 4.8, 5.1, 5.2**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 11)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (2.7, 3.7, 4.8, 5.1, 5.2)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 11: Mock mode isolation

from unittest.mock import AsyncMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.model_manager import ModelManager, ModelRole


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# All valid ModelRole values
st_model_role = st.sampled_from(list(ModelRole))

# Random text for embedding generation
st_text = st.text(min_size=1, max_size=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_EMBEDDING_DIMENSION = 1024


def _make_mock_settings() -> object:
    """Create a mock settings object configured in mock mode."""

    class MockSettings:
        model_manager_mode = "mock"
        vllm_base_url = "http://localhost:8000"
        vllm_embedding_url = "http://localhost:8001"
        model_chat_name = "Qwen/Qwen3.6-35B-A3B"
        model_chat_path = "/models/qwen3.6-35b-a3b"
        model_chat_max_gpu_memory_gb = 24
        model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        model_embedding_path = "/models/qwen3-embedding-0.6b"
        model_embedding_dimension = MOCK_EMBEDDING_DIMENSION
        model_ocr_name = "google/gemma-4-E4B-it"
        model_ocr_path = "/models/gemma-4-e4b-it"

    return MockSettings()


def _make_inference_client_mock() -> AsyncMock:
    """Create a mock InferenceClient that tracks all calls.

    All methods are mocked so we can verify NONE of them are called
    during mock mode operations.
    """
    client = AsyncMock()
    client.health_check = AsyncMock(return_value=True)
    client.list_models = AsyncMock(return_value=[])
    client.chat_completion = AsyncMock(return_value="real response")
    client.create_embeddings = AsyncMock(return_value=[[0.1] * 1024])
    client.close = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Property 11a: ensure_model in mock mode makes NO HTTP calls
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 11: Mock mode isolation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(role=st_model_role)
async def test_ensure_model_mock_no_http_calls(role: ModelRole) -> None:
    """For any ModelRole, calling ensure_model in mock mode SHALL NOT make
    any HTTP requests (health_check, list_models, etc. never called).

    **Validates: Requirements 5.1**
    """
    mock_settings = _make_mock_settings()
    client_mock = _make_inference_client_mock()

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    await manager.ensure_model(role)

    # Verify NO HTTP calls were made
    client_mock.health_check.assert_not_called()
    client_mock.list_models.assert_not_called()
    client_mock.chat_completion.assert_not_called()
    client_mock.create_embeddings.assert_not_called()

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 11b: ensure_model in mock mode sets correct state
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 11: Mock mode isolation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(role=st_model_role)
async def test_ensure_model_mock_state_update(role: ModelRole) -> None:
    """For any ModelRole in mock mode, ensure_model SHALL update state:
    is_ready=True, current_role set to the requested role, gpu_memory=0.0.

    **Validates: Requirements 5.1**
    """
    mock_settings = _make_mock_settings()
    client_mock = _make_inference_client_mock()

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    url = await manager.ensure_model(role)

    # Verify state is updated correctly
    assert manager._is_ready is True, "is_ready should be True after mock ensure_model"
    assert manager._current_role == role, (
        f"current_role should be {role}, got {manager._current_role}"
    )
    assert manager._gpu_memory_used_gb == 0.0, (
        f"gpu_memory should be 0.0 in mock mode, got {manager._gpu_memory_used_gb}"
    )
    # Verify URL returned is the configured vllm_base_url
    assert url == mock_settings.vllm_base_url, (
        f"Expected {mock_settings.vllm_base_url}, got {url}"
    )

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 11c: get_status in mock mode returns vllm_reachable=None
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 11: Mock mode isolation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(role=st_model_role)
async def test_get_status_mock_vllm_reachable_none(role: ModelRole) -> None:
    """For any state in mock mode, get_status SHALL return
    vllm_reachable=None without making any HTTP requests.

    **Validates: Requirements 5.1**
    """
    mock_settings = _make_mock_settings()
    client_mock = _make_inference_client_mock()

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    # Load a model first to have some state
    await manager.ensure_model(role)

    # Reset mock call counts before get_status
    client_mock.health_check.reset_mock()

    status = await manager.get_status()

    # Verify vllm_reachable is None in mock mode
    assert status.vllm_reachable is None, (
        f"vllm_reachable should be None in mock mode, got {status.vllm_reachable}"
    )
    # Verify no health check was performed
    client_mock.health_check.assert_not_called()
    # Verify mode is reported correctly
    assert status.mode == "mock", f"mode should be 'mock', got {status.mode}"

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 11d: Mock embeddings have exactly model_embedding_dimension dims
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 11: Mock mode isolation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(text=st_text)
async def test_mock_embedding_dimension(text: str) -> None:
    """For any input text, mock embeddings SHALL have exactly
    model_embedding_dimension (1024) dimensions.

    **Validates: Requirements 5.2**
    """
    mock_settings = _make_mock_settings()
    client_mock = _make_inference_client_mock()

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    embedding = await manager.get_mock_embedding(text)

    # Verify dimension is exactly model_embedding_dimension
    assert len(embedding) == MOCK_EMBEDDING_DIMENSION, (
        f"Mock embedding should have {MOCK_EMBEDDING_DIMENSION} dimensions, "
        f"got {len(embedding)}"
    )
    # Verify all values are floats
    assert all(isinstance(v, float) for v in embedding), (
        "All embedding values should be floats"
    )
    # Verify no HTTP calls were made
    client_mock.create_embeddings.assert_not_called()

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 11e: Mock completion returns without HTTP calls
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 11: Mock mode isolation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(text=st_text)
async def test_mock_completion_no_http_calls(text: str) -> None:
    """For any input prompt in mock mode, get_mock_completion SHALL return
    a mock response string without making any HTTP requests.

    **Validates: Requirements 2.7**
    """
    mock_settings = _make_mock_settings()
    client_mock = _make_inference_client_mock()

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    response = await manager.get_mock_completion(text)

    # Verify a non-empty string is returned
    assert isinstance(response, str), "Mock completion should return a string"
    assert len(response) > 0, "Mock completion should not be empty"
    # Verify no HTTP calls were made
    client_mock.chat_completion.assert_not_called()
    client_mock.health_check.assert_not_called()

    await manager.shutdown()
