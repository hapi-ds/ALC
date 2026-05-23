"""Property-based tests for Knowledge Service embedding generation.

Tests Properties 6, 7, and 8 from the AI Model Integration (vLLM) design document:

- Property 6: Embedding batch size constraint
  For any list of N text chunks (N > 0), the number of embedding API requests
  sent to vLLM SHALL equal ceil(N / 32), and each individual request SHALL
  contain at most 32 input strings.

- Property 7: Embedding order preservation
  For any list of text chunks sent for embedding generation, the returned
  embedding vectors SHALL be in exactly the same order as the input chunks,
  regardless of batching.

- Property 8: Embedding dimension validation
  For any embedding response from vLLM where any vector has a dimension not
  equal to the configured model_embedding_dimension (default 1024), the system
  SHALL raise a ValueError.

**Validates: Requirements 3.2, 3.3, 3.4**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Properties 6, 7, 8)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (3.2, 3.3, 3.4)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 6: Embedding batch size constraint
# Feature: Step_4-3_ai-model-integration-vllm, Property 7: Embedding order preservation
# Feature: Step_4-3_ai-model-integration-vllm, Property 8: Embedding dimension validation

import math
from unittest.mock import AsyncMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.knowledge_service import KnowledgeService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate lists of 1 to 200 text chunks (non-empty strings)
st_chunks = st.lists(
    st.text(min_size=1, max_size=100, alphabet=st.characters(categories=("L", "N", "Z"))),
    min_size=1,
    max_size=200,
)

# Generate chunk counts for dimension validation (1 to 50)
st_chunk_count = st.integers(min_value=1, max_value=50)

# Generate wrong dimensions (anything except 1024)
st_wrong_dimension = st.integers(min_value=1, max_value=4096).filter(lambda d: d != 1024)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMBEDDING_DIMENSION = 1024


def _make_model_manager_mock() -> AsyncMock:
    """Create a mock ModelManager in gpu mode with ensure_model returning a URL."""
    manager = AsyncMock()
    manager.mode = "gpu"
    manager.ensure_model = AsyncMock(return_value="http://localhost:8001")
    return manager


def _make_inference_client_mock(
    dimension: int = EMBEDDING_DIMENSION,
    track_calls: bool = False,
) -> tuple[AsyncMock, list[list[str]]]:
    """Create a mock InferenceClient that returns embeddings of given dimension.

    When track_calls=True, records each batch of inputs passed to create_embeddings.

    Returns:
        Tuple of (mock_client, recorded_calls_list).
    """
    recorded_calls: list[list[str]] = []

    async def mock_create_embeddings(model: str, inputs: list[str]) -> list[list[float]]:
        recorded_calls.append(inputs)
        # Return vectors where each vector is [float(global_index)] * dimension
        # This allows us to verify order preservation
        return [[0.0] * dimension for _ in inputs]

    client = AsyncMock()
    client.create_embeddings = AsyncMock(side_effect=mock_create_embeddings)
    return client, recorded_calls


def _make_order_tracking_client(dimension: int = EMBEDDING_DIMENSION) -> tuple[AsyncMock, list[list[str]]]:
    """Create a mock InferenceClient that returns order-identifiable embeddings.

    Each embedding vector starts with the chunk's position index as a float marker,
    allowing verification that output order matches input order.

    Returns:
        Tuple of (mock_client, recorded_calls_list).
    """
    call_index = [0]  # mutable counter for tracking global position
    recorded_calls: list[list[str]] = []

    async def mock_create_embeddings(model: str, inputs: list[str]) -> list[list[float]]:
        recorded_calls.append(inputs)
        results = []
        for _ in inputs:
            # Use the global index as a marker in the first element
            vector = [float(call_index[0])] * dimension
            call_index[0] += 1
            results.append(vector)
        return results

    client = AsyncMock()
    client.create_embeddings = AsyncMock(side_effect=mock_create_embeddings)
    return client, recorded_calls


def _make_settings_mock() -> object:
    """Create a mock settings object for KnowledgeService."""

    class MockSettings:
        model_embedding_dimension = EMBEDDING_DIMENSION
        model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        model_manager_mode = "gpu"
        vllm_base_url = "http://localhost:8000"
        vllm_embedding_url = "http://localhost:8001"

    return MockSettings()


# ---------------------------------------------------------------------------
# Property 6: Embedding batch size constraint
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 6: Embedding batch size constraint
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(chunks=st_chunks)
async def test_embedding_batch_size_constraint(chunks: list[str]) -> None:
    """For any list of N text chunks (N > 0), the number of embedding API
    requests sent to vLLM SHALL equal ceil(N / 32), and each individual
    request SHALL contain at most 32 input strings.

    **Validates: Requirements 3.2**
    """
    model_manager = _make_model_manager_mock()
    client, recorded_calls = _make_inference_client_mock(track_calls=True)

    with patch("alcoabase.services.knowledge_service.get_settings", return_value=_make_settings_mock()):
        service = KnowledgeService(
            model_manager=model_manager,
            inference_client=client,
        )

    await service.generate_embeddings(chunks)

    n = len(chunks)
    expected_num_requests = math.ceil(n / 32)

    # Verify the number of API calls equals ceil(N / 32)
    assert len(recorded_calls) == expected_num_requests, (
        f"Expected {expected_num_requests} API requests for {n} chunks, "
        f"got {len(recorded_calls)}"
    )

    # Verify each individual request contains at most 32 inputs
    for i, call_inputs in enumerate(recorded_calls):
        assert len(call_inputs) <= 32, (
            f"Batch {i} contained {len(call_inputs)} inputs, exceeding max of 32"
        )


# ---------------------------------------------------------------------------
# Property 7: Embedding order preservation
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 7: Embedding order preservation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    num_chunks=st.integers(min_value=1, max_value=200),
)
async def test_embedding_order_preservation(num_chunks: int) -> None:
    """For any list of text chunks sent for embedding generation, the returned
    embedding vectors SHALL be in exactly the same order as the input chunks,
    regardless of batching.

    **Validates: Requirements 3.3**
    """
    # Generate indexed chunks so we can verify order
    chunks = [f"chunk_{i}" for i in range(num_chunks)]

    model_manager = _make_model_manager_mock()
    client, recorded_calls = _make_order_tracking_client()

    with patch("alcoabase.services.knowledge_service.get_settings", return_value=_make_settings_mock()):
        service = KnowledgeService(
            model_manager=model_manager,
            inference_client=client,
        )

    embeddings = await service.generate_embeddings(chunks)

    # Verify we got the right number of embeddings
    assert len(embeddings) == num_chunks, (
        f"Expected {num_chunks} embeddings, got {len(embeddings)}"
    )

    # Verify order: each embedding's marker (first element) should match
    # its position index
    for i, embedding in enumerate(embeddings):
        assert embedding[0] == float(i), (
            f"Embedding at position {i} has marker {embedding[0]}, "
            f"expected {float(i)}. Order was not preserved."
        )


# ---------------------------------------------------------------------------
# Property 8: Embedding dimension validation
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 8: Embedding dimension validation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    num_chunks=st_chunk_count,
    wrong_dim=st_wrong_dimension,
)
async def test_embedding_dimension_validation(num_chunks: int, wrong_dim: int) -> None:
    """For any embedding response from vLLM where any vector has a dimension
    not equal to the configured model_embedding_dimension (default 1024),
    the system SHALL raise a ValueError.

    **Validates: Requirements 3.4**
    """
    chunks = [f"chunk_{i}" for i in range(num_chunks)]

    model_manager = _make_model_manager_mock()
    # Create a client that returns vectors with the wrong dimension
    client, _ = _make_inference_client_mock(dimension=wrong_dim)

    with patch("alcoabase.services.knowledge_service.get_settings", return_value=_make_settings_mock()):
        service = KnowledgeService(
            model_manager=model_manager,
            inference_client=client,
        )

    with pytest.raises(ValueError, match="Embedding dimension mismatch"):
        await service.generate_embeddings(chunks)
