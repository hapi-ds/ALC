"""Unit tests for embedding generation in KnowledgeService.

Tests batching with various chunk counts, empty input handling,
dimension mismatch validation, mock mode behavior, HTTP error
handling, and timeout scenarios.

References:
    - Task 5.5: Write unit tests for embedding generation
    - Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
"""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.inference_client import (
    InferenceError,
    InferenceTimeoutError,
)
from alcoabase.services.knowledge_service import KnowledgeService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_model_manager() -> MagicMock:
    """Create a mock ModelManager in gpu mode."""
    mm = MagicMock()
    mm.mode = "gpu"
    mm.ensure_model = AsyncMock(return_value="http://localhost:8001")
    return mm


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient that returns valid embeddings."""
    client = AsyncMock()

    async def _create_embeddings(model: str, inputs: list[str]) -> list[list[float]]:
        """Return vectors of dimension 1024 for each input."""
        return [[0.1] * 1024 for _ in inputs]

    client.create_embeddings = AsyncMock(side_effect=_create_embeddings)
    return client


@pytest.fixture
def knowledge_service(
    mock_model_manager: MagicMock,
    mock_inference_client: AsyncMock,
) -> KnowledgeService:
    """Create a KnowledgeService with mocked dependencies in gpu mode."""
    with patch("alcoabase.services.knowledge_service.get_settings") as mock_settings:
        settings = MagicMock()
        settings.model_embedding_dimension = 1024
        settings.model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        mock_settings.return_value = settings

        svc = KnowledgeService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )
    return svc


@pytest.fixture
def mock_knowledge_service() -> KnowledgeService:
    """Create a KnowledgeService in mock mode (no model_manager)."""
    with patch("alcoabase.services.knowledge_service.get_settings") as mock_settings:
        settings = MagicMock()
        settings.model_embedding_dimension = 1024
        settings.model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        mock_settings.return_value = settings

        svc = KnowledgeService(model_manager=None, inference_client=None)
    return svc


# ---------------------------------------------------------------------------
# Tests: Batching with various chunk counts
# ---------------------------------------------------------------------------


class TestEmbeddingBatching:
    """Tests for batch size constraint (max 32 chunks per request)."""

    @pytest.mark.asyncio
    async def test_single_chunk_one_batch(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """1 chunk should result in exactly 1 API call."""
        chunks = ["chunk 1"]
        await knowledge_service.generate_embeddings(chunks)
        assert mock_inference_client.create_embeddings.call_count == 1

    @pytest.mark.asyncio
    async def test_32_chunks_one_batch(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """32 chunks should result in exactly 1 API call (batch size = 32)."""
        chunks = [f"chunk {i}" for i in range(32)]
        await knowledge_service.generate_embeddings(chunks)
        assert mock_inference_client.create_embeddings.call_count == 1

    @pytest.mark.asyncio
    async def test_33_chunks_two_batches(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """33 chunks should result in 2 API calls (32 + 1)."""
        chunks = [f"chunk {i}" for i in range(33)]
        await knowledge_service.generate_embeddings(chunks)
        assert mock_inference_client.create_embeddings.call_count == 2

    @pytest.mark.asyncio
    async def test_64_chunks_two_batches(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """64 chunks should result in exactly 2 API calls (32 + 32)."""
        chunks = [f"chunk {i}" for i in range(64)]
        await knowledge_service.generate_embeddings(chunks)
        assert mock_inference_client.create_embeddings.call_count == 2

    @pytest.mark.asyncio
    async def test_100_chunks_four_batches(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """100 chunks should result in 4 API calls (ceil(100/32) = 4)."""
        chunks = [f"chunk {i}" for i in range(100)]
        await knowledge_service.generate_embeddings(chunks)
        expected_calls = math.ceil(100 / 32)
        assert mock_inference_client.create_embeddings.call_count == expected_calls

    @pytest.mark.asyncio
    async def test_batch_sizes_are_correct(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Each batch should contain at most 32 inputs."""
        chunks = [f"chunk {i}" for i in range(100)]
        await knowledge_service.generate_embeddings(chunks)

        for call in mock_inference_client.create_embeddings.call_args_list:
            _, kwargs = call
            inputs = kwargs.get("inputs") or call[0][1] if len(call[0]) > 1 else kwargs["inputs"]
            assert len(inputs) <= 32

    @pytest.mark.asyncio
    async def test_results_concatenated_in_order(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Results from multiple batches should be concatenated in input order."""
        call_count = [0]

        async def _create_embeddings_indexed(model: str, inputs: list[str]) -> list[list[float]]:
            """Return vectors where first element encodes the batch index."""
            batch_idx = call_count[0]
            call_count[0] += 1
            return [[float(batch_idx)] + [0.0] * 1023 for _ in inputs]

        mock_inference_client.create_embeddings = AsyncMock(
            side_effect=_create_embeddings_indexed
        )

        chunks = [f"chunk {i}" for i in range(33)]
        result = await knowledge_service.generate_embeddings(chunks)

        assert len(result) == 33
        # First 32 chunks from batch 0
        for i in range(32):
            assert result[i][0] == 0.0
        # Last chunk from batch 1
        assert result[32][0] == 1.0


# ---------------------------------------------------------------------------
# Tests: Empty input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    """Tests for empty input handling."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_without_http_calls(
        self,
        knowledge_service: KnowledgeService,
        mock_model_manager: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Empty input should return empty list without calling ensure_model or create_embeddings."""
        result = await knowledge_service.generate_embeddings([])

        assert result == []
        mock_model_manager.ensure_model.assert_not_called()
        mock_inference_client.create_embeddings.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Dimension mismatch
# ---------------------------------------------------------------------------


class TestDimensionMismatch:
    """Tests for embedding dimension validation."""

    @pytest.mark.asyncio
    async def test_wrong_dimension_raises_value_error(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Vectors with wrong dimension should raise ValueError."""

        async def _wrong_dim(model: str, inputs: list[str]) -> list[list[float]]:
            return [[0.1] * 512 for _ in inputs]  # 512 instead of 1024

        mock_inference_client.create_embeddings = AsyncMock(side_effect=_wrong_dim)

        with pytest.raises(ValueError, match="dimension mismatch"):
            await knowledge_service.generate_embeddings(["test chunk"])

    @pytest.mark.asyncio
    async def test_dimension_mismatch_error_message_includes_expected_and_actual(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """ValueError message should include expected and actual dimensions."""

        async def _wrong_dim(model: str, inputs: list[str]) -> list[list[float]]:
            return [[0.1] * 768 for _ in inputs]

        mock_inference_client.create_embeddings = AsyncMock(side_effect=_wrong_dim)

        with pytest.raises(ValueError) as exc_info:
            await knowledge_service.generate_embeddings(["test chunk"])

        error_msg = str(exc_info.value)
        assert "1024" in error_msg
        assert "768" in error_msg


# ---------------------------------------------------------------------------
# Tests: Mock mode
# ---------------------------------------------------------------------------


class TestMockMode:
    """Tests for mock mode (no model_manager) behavior."""

    @pytest.mark.asyncio
    async def test_mock_mode_returns_vectors_of_correct_dimension(
        self,
        mock_knowledge_service: KnowledgeService,
    ) -> None:
        """Mock mode should return random vectors of exactly 1024 dimensions."""
        chunks = ["chunk 1", "chunk 2", "chunk 3"]
        result = await mock_knowledge_service.generate_embeddings(chunks)

        assert len(result) == 3
        for vec in result:
            assert len(vec) == 1024

    @pytest.mark.asyncio
    async def test_mock_mode_returns_normalized_vectors(
        self,
        mock_knowledge_service: KnowledgeService,
    ) -> None:
        """Mock mode vectors should be approximately unit-normalized."""
        chunks = ["test chunk"]
        result = await mock_knowledge_service.generate_embeddings(chunks)

        vec = result[0]
        magnitude = sum(v * v for v in vec) ** 0.5
        assert abs(magnitude - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_mock_mode_no_http_calls(
        self,
        mock_knowledge_service: KnowledgeService,
    ) -> None:
        """Mock mode should not have model_manager or inference_client."""
        assert mock_knowledge_service._model_manager is None
        assert mock_knowledge_service._inference_client is None

        # Should still work without errors
        result = await mock_knowledge_service.generate_embeddings(["test"])
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_mock_mode_different_chunks_produce_different_vectors(
        self,
        mock_knowledge_service: KnowledgeService,
    ) -> None:
        """Mock mode should produce different random vectors for different chunks."""
        chunks = ["chunk a", "chunk b"]
        result = await mock_knowledge_service.generate_embeddings(chunks)

        # Vectors should not be identical (random generation)
        assert result[0] != result[1]


# ---------------------------------------------------------------------------
# Tests: HTTP error handling
# ---------------------------------------------------------------------------


class TestHTTPErrorHandling:
    """Tests for HTTP error propagation and logging."""

    @pytest.mark.asyncio
    async def test_inference_error_propagates(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """InferenceError from create_embeddings should propagate to caller."""
        mock_inference_client.create_embeddings = AsyncMock(
            side_effect=InferenceError(
                "Request failed: HTTP 500",
                status_code=500,
                endpoint="http://localhost:8001/v1/embeddings",
            )
        )

        with pytest.raises(InferenceError) as exc_info:
            await knowledge_service.generate_embeddings(["test chunk"])

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_error_on_second_batch_propagates(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Error on a subsequent batch should still propagate."""
        call_count = [0]

        async def _fail_on_second(model: str, inputs: list[str]) -> list[list[float]]:
            call_count[0] += 1
            if call_count[0] == 2:
                raise InferenceError(
                    "Request failed: HTTP 503",
                    status_code=503,
                    endpoint="http://localhost:8001/v1/embeddings",
                )
            return [[0.1] * 1024 for _ in inputs]

        mock_inference_client.create_embeddings = AsyncMock(side_effect=_fail_on_second)

        # 33 chunks = 2 batches; second batch fails
        with pytest.raises(InferenceError) as exc_info:
            await knowledge_service.generate_embeddings(
                [f"chunk {i}" for i in range(33)]
            )

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_error_logged_before_propagation(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Errors should be logged at ERROR level before propagating."""
        mock_inference_client.create_embeddings = AsyncMock(
            side_effect=InferenceError(
                "Request failed: HTTP 500",
                status_code=500,
                endpoint="http://localhost:8001/v1/embeddings",
            )
        )

        with patch("alcoabase.services.knowledge_service.logger") as mock_logger:
            with pytest.raises(InferenceError):
                await knowledge_service.generate_embeddings(["test chunk"])

            mock_logger.error.assert_called_once()
            log_msg = mock_logger.error.call_args[0][0]
            assert "Embedding generation failed" in log_msg


# ---------------------------------------------------------------------------
# Tests: Timeout handling
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Tests for 30s timeout behavior."""

    @pytest.mark.asyncio
    async def test_timeout_raises_inference_timeout_error(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """InferenceTimeoutError from create_embeddings should propagate."""
        mock_inference_client.create_embeddings = AsyncMock(
            side_effect=InferenceTimeoutError(
                "Request to http://localhost:8001/v1/embeddings timed out after 30.0s",
                endpoint="http://localhost:8001/v1/embeddings",
            )
        )

        with pytest.raises(InferenceTimeoutError) as exc_info:
            await knowledge_service.generate_embeddings(["test chunk"])

        assert "30.0s" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_logged_before_propagation(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Timeout errors should be logged at ERROR level."""
        mock_inference_client.create_embeddings = AsyncMock(
            side_effect=InferenceTimeoutError(
                "Request timed out after 30.0s",
                endpoint="http://localhost:8001/v1/embeddings",
            )
        )

        with patch("alcoabase.services.knowledge_service.logger") as mock_logger:
            with pytest.raises(InferenceTimeoutError):
                await knowledge_service.generate_embeddings(["test chunk"])

            mock_logger.error.assert_called_once()
