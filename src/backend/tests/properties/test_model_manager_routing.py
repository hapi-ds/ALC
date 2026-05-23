"""Property-based tests for role-to-endpoint routing correctness.

Tests Property 1 from the AI Model Integration (vLLM) design document,
validating that:
- EMBEDDING role → returns `vllm_embedding_url` (http://localhost:8001)
- CHAT role → returns `vllm_base_url` (http://localhost:8000)
- OCR role → returns `vllm_base_url` (http://localhost:8000)

For any valid ModelRole (CHAT, EMBEDDING, OCR), calling `ensure_model`
in gpu/cpu mode SHALL result in an HTTP request directed to the correct
vLLM instance URL with the correct model path for that role as configured
in settings.

**Validates: Requirements 1.1**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 1)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (1.1)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 1: Role-to-endpoint routing correctness

from unittest.mock import AsyncMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.model_manager import ModelManager, ModelRole


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# All valid ModelRole values
st_model_role = st.sampled_from(list(ModelRole))

# Operating modes that use real vLLM routing (not mock)
st_real_mode = st.sampled_from(["gpu", "cpu"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Expected URL mapping per role
EXPECTED_URLS = {
    ModelRole.EMBEDDING: "http://localhost:8001",
    ModelRole.CHAT: "http://localhost:8000",
    ModelRole.OCR: "http://localhost:8000",
}


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


def _make_inference_client_mock(model_name: str) -> AsyncMock:
    """Create a mock InferenceClient that reports the expected model as loaded."""
    client = AsyncMock()
    client.health_check = AsyncMock(return_value=True)
    client.list_models = AsyncMock(return_value=[model_name])
    client.close = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# Property 1a: EMBEDDING role returns the dedicated embedding URL
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 1: Role-to-endpoint routing correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(mode=st_real_mode)
async def test_embedding_role_routes_to_embedding_url(mode: str) -> None:
    """For any real mode (gpu/cpu), calling ensure_model(EMBEDDING) SHALL
    return the dedicated embedding vLLM instance URL (vllm_embedding_url).

    **Validates: Requirements 1.1**
    """
    mock_settings = _make_settings(mode)
    client_mock = _make_inference_client_mock(mock_settings.model_embedding_name)

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    url = await manager.ensure_model(ModelRole.EMBEDDING)

    assert url == mock_settings.vllm_embedding_url, (
        f"EMBEDDING role should route to {mock_settings.vllm_embedding_url}, "
        f"got {url}"
    )

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 1b: CHAT role returns the main vLLM base URL
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 1: Role-to-endpoint routing correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(mode=st_real_mode)
async def test_chat_role_routes_to_base_url(mode: str) -> None:
    """For any real mode (gpu/cpu), calling ensure_model(CHAT) SHALL
    return the main vLLM base URL (vllm_base_url).

    **Validates: Requirements 1.1**
    """
    mock_settings = _make_settings(mode)
    client_mock = _make_inference_client_mock(mock_settings.model_chat_name)

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    url = await manager.ensure_model(ModelRole.CHAT)

    assert url == mock_settings.vllm_base_url, (
        f"CHAT role should route to {mock_settings.vllm_base_url}, got {url}"
    )

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 1c: OCR role returns the main vLLM base URL
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 1: Role-to-endpoint routing correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(mode=st_real_mode)
async def test_ocr_role_routes_to_base_url(mode: str) -> None:
    """For any real mode (gpu/cpu), calling ensure_model(OCR) SHALL
    return the main vLLM base URL (vllm_base_url).

    **Validates: Requirements 1.1**
    """
    mock_settings = _make_settings(mode)
    client_mock = _make_inference_client_mock(mock_settings.model_ocr_name)

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    url = await manager.ensure_model(ModelRole.OCR)

    assert url == mock_settings.vllm_base_url, (
        f"OCR role should route to {mock_settings.vllm_base_url}, got {url}"
    )

    await manager.shutdown()


# ---------------------------------------------------------------------------
# Property 1d: All roles route to the correct URL (combined property)
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 1: Role-to-endpoint routing correctness
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    role=st_model_role,
    mode=st_real_mode,
)
async def test_any_role_routes_to_correct_url(role: ModelRole, mode: str) -> None:
    """For any valid ModelRole (CHAT, EMBEDDING, OCR) in any real mode (gpu/cpu),
    calling ensure_model SHALL return the correct vLLM instance URL for that role.

    - EMBEDDING → vllm_embedding_url (http://localhost:8001)
    - CHAT → vllm_base_url (http://localhost:8000)
    - OCR → vllm_base_url (http://localhost:8000)

    **Validates: Requirements 1.1**
    """
    mock_settings = _make_settings(mode)

    # Determine which model name the client should report as loaded
    model_name_map = {
        ModelRole.CHAT: mock_settings.model_chat_name,
        ModelRole.EMBEDDING: mock_settings.model_embedding_name,
        ModelRole.OCR: mock_settings.model_ocr_name,
    }
    client_mock = _make_inference_client_mock(model_name_map[role])

    manager = ModelManager(
        settings=mock_settings,
        inference_client=client_mock,
    )

    url = await manager.ensure_model(role)

    expected_url = EXPECTED_URLS[role]
    assert url == expected_url, (
        f"Role {role.value} in {mode} mode should route to {expected_url}, "
        f"got {url}"
    )

    await manager.shutdown()
