"""Property-based tests for embedding batch size correctness.

Property 10: Embedding batch size correctness
- Generate N content chunks (1–500).
- Assert InferenceClient is called exactly `ceil(N/32)` times.
- Assert each call has at most 32 chunks.
- Assert concatenated results maintain original ordering.

**Validates: Requirements 1.4**

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.embedding.services.chunking_pipeline import ContentChunk
from alcoabase.literature.embedding.services.embedding_service import (
    EmbeddingService,
    _EMBEDDING_BATCH_SIZE,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Number of chunks: 1 to 500
NUM_CHUNKS = st.integers(min_value=1, max_value=500)

# Embedding dimension (fixed for test)
EMBEDDING_DIM = 1024


def _make_chunks(n: int) -> list[ContentChunk]:
    """Create N synthetic ContentChunk instances for testing."""
    return [
        ContentChunk(
            text=f"chunk text number {i}",
            chunk_index=i,
            section_heading=f"Section {i % 5}",
            source_field="body" if i > 0 else "abstract",
        )
        for i in range(n)
    ]


def _make_embedding_side_effect(dim: int):
    """Create a side effect function for create_embeddings mock.

    Returns unique vectors per chunk to verify ordering:
    vector[i] = [i * 0.001] * dim (first element encodes the batch offset).
    """
    call_count = [0]
    accumulated_index = [0]

    async def _side_effect(model: str, inputs: list[str]) -> list[list[float]]:
        results = []
        for j in range(len(inputs)):
            global_idx = accumulated_index[0] + j
            # Encode the global index in the first element for order verification
            vec = [float(global_idx)] + [0.0] * (dim - 1)
            results.append(vec)
        accumulated_index[0] += len(inputs)
        call_count[0] += 1
        return results

    return _side_effect, call_count


def _make_embedding_service() -> tuple[EmbeddingService, AsyncMock]:
    """Create an EmbeddingService with mocked dependencies.

    Returns:
        Tuple of (service, inference_client_mock).
    """
    session_factory = AsyncMock()
    inference_client = AsyncMock()
    model_manager = AsyncMock()
    model_manager.ensure_model = AsyncMock(return_value="http://vllm:8000")
    index_manager = MagicMock()
    chunking_pipeline = MagicMock()

    service = EmbeddingService(
        session_factory=session_factory,
        inference_client=inference_client,
        model_manager=model_manager,
        index_manager=index_manager,
        chunking_pipeline=chunking_pipeline,
    )

    return service, inference_client


# ---------------------------------------------------------------------------
# Property 10a: InferenceClient called exactly ceil(N/32) times
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(n=NUM_CHUNKS)
@pytest.mark.asyncio
async def test_embedding_batch_call_count(n: int) -> None:
    """InferenceClient.create_embeddings SHALL be called exactly ceil(N/32) times
    when generating embeddings for N chunks.

    **Validates: Requirements 1.4**
    """
    service, inference_client = _make_embedding_service()
    chunks = _make_chunks(n)

    side_effect, _ = _make_embedding_side_effect(EMBEDDING_DIM)
    inference_client.create_embeddings = AsyncMock(side_effect=side_effect)

    with patch("alcoabase.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            model_embedding_name="test-model",
        )
        await service._generate_embeddings_with_retry(
            chunks=chunks,
            record_id=1,
            company_id=1,
        )

    expected_calls = math.ceil(n / _EMBEDDING_BATCH_SIZE)
    actual_calls = inference_client.create_embeddings.call_count

    assert actual_calls == expected_calls, (
        f"Expected {expected_calls} calls for {n} chunks "
        f"(batch_size={_EMBEDDING_BATCH_SIZE}), got {actual_calls}"
    )


# ---------------------------------------------------------------------------
# Property 10b: Each call has at most 32 chunks
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(n=NUM_CHUNKS)
@pytest.mark.asyncio
async def test_embedding_batch_max_size(n: int) -> None:
    """Each call to InferenceClient.create_embeddings SHALL have at most 32
    text inputs per batch.

    **Validates: Requirements 1.4**
    """
    service, inference_client = _make_embedding_service()
    chunks = _make_chunks(n)

    # Track batch sizes via the mock
    batch_sizes: list[int] = []

    async def _tracking_side_effect(model: str, inputs: list[str]) -> list[list[float]]:
        batch_sizes.append(len(inputs))
        return [[0.0] * EMBEDDING_DIM for _ in inputs]

    inference_client.create_embeddings = AsyncMock(side_effect=_tracking_side_effect)

    with patch("alcoabase.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            model_embedding_name="test-model",
        )
        await service._generate_embeddings_with_retry(
            chunks=chunks,
            record_id=1,
            company_id=1,
        )

    for i, batch_size in enumerate(batch_sizes):
        assert batch_size <= _EMBEDDING_BATCH_SIZE, (
            f"Batch {i} had {batch_size} inputs, "
            f"exceeds max batch size of {_EMBEDDING_BATCH_SIZE}"
        )


# ---------------------------------------------------------------------------
# Property 10c: Concatenated results maintain original ordering
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(n=NUM_CHUNKS)
@pytest.mark.asyncio
async def test_embedding_batch_ordering_preserved(n: int) -> None:
    """The concatenated embedding results SHALL maintain the same ordering as
    the input chunks (result[i] corresponds to chunk[i]).

    **Validates: Requirements 1.4**
    """
    service, inference_client = _make_embedding_service()
    chunks = _make_chunks(n)

    side_effect, _ = _make_embedding_side_effect(EMBEDDING_DIM)
    inference_client.create_embeddings = AsyncMock(side_effect=side_effect)

    with patch("alcoabase.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            model_embedding_name="test-model",
        )
        result = await service._generate_embeddings_with_retry(
            chunks=chunks,
            record_id=1,
            company_id=1,
        )

    # Verify count matches
    assert len(result) == n, (
        f"Expected {n} embedding vectors, got {len(result)}"
    )

    # Verify ordering: first element of each vector encodes its global index
    for i, embedding in enumerate(result):
        assert embedding[0] == float(i), (
            f"Embedding at position {i} has first element {embedding[0]}, "
            f"expected {float(i)}. Ordering was not preserved."
        )
