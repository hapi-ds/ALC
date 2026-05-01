"""Unit tests for the Model Manager service.

Tests model swap serialization, error handling, and mock mode behavior.

References:
    - Task 18.14: Write unit tests for model swap serialization,
      error handling, mock mode returns correct-dimension embeddings
"""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from alcoabase.services.model_manager import (
    ModelManager,
    ModelManagerError,
    ModelRole,
    ModelStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockSettings:
    """Mock settings for testing without real environment variables."""

    model_chat_name = "test-chat-model"
    model_chat_path = "/models/test-chat"
    model_chat_max_gpu_memory_gb = 60
    model_embedding_name = "test-embedding-model"
    model_embedding_path = "/models/test-embedding"
    model_embedding_dimension = 1024
    model_ocr_name = "test-ocr-model"
    model_ocr_path = "/models/test-ocr"
    gpu_device_id = 0
    model_manager_mode = "mock"
    vllm_base_url = "http://localhost:8000"


@pytest.fixture
def mock_settings() -> MockSettings:
    """Create mock settings for testing."""
    return MockSettings()


@pytest.fixture
def model_manager(mock_settings: MockSettings) -> ModelManager:
    """Create a ModelManager instance with mock settings."""
    return ModelManager(settings=mock_settings)


# ---------------------------------------------------------------------------
# Tests: Basic Initialization
# ---------------------------------------------------------------------------


class TestModelManagerInit:
    """Tests for ModelManager initialization."""

    def test_initial_state_has_no_model_loaded(
        self, model_manager: ModelManager
    ) -> None:
        """ModelManager should start with no model loaded."""
        assert model_manager._current_role is None
        assert model_manager._current_model_name is None
        assert model_manager._is_ready is False

    def test_mode_returns_configured_mode(
        self, model_manager: ModelManager
    ) -> None:
        """Mode property should return the configured mode."""
        assert model_manager.mode == "mock"


# ---------------------------------------------------------------------------
# Tests: ensure_model (Mock Mode)
# ---------------------------------------------------------------------------


class TestEnsureModelMock:
    """Tests for ensure_model in mock mode."""

    @pytest.mark.asyncio
    async def test_ensure_model_chat_loads_successfully(
        self, model_manager: ModelManager
    ) -> None:
        """ensure_model(CHAT) should load the chat model in mock mode."""
        url = await model_manager.ensure_model(ModelRole.CHAT)

        assert url == "http://localhost:8000"
        assert model_manager._current_role == ModelRole.CHAT
        assert model_manager._current_model_name == "test-chat-model"
        assert model_manager._is_ready is True

    @pytest.mark.asyncio
    async def test_ensure_model_embedding_loads_successfully(
        self, model_manager: ModelManager
    ) -> None:
        """ensure_model(EMBEDDING) should load the embedding model."""
        url = await model_manager.ensure_model(ModelRole.EMBEDDING)

        assert url == "http://localhost:8000"
        assert model_manager._current_role == ModelRole.EMBEDDING
        assert model_manager._current_model_name == "test-embedding-model"
        assert model_manager._is_ready is True

    @pytest.mark.asyncio
    async def test_ensure_model_ocr_loads_successfully(
        self, model_manager: ModelManager
    ) -> None:
        """ensure_model(OCR) should load the OCR model."""
        url = await model_manager.ensure_model(ModelRole.OCR)

        assert url == "http://localhost:8000"
        assert model_manager._current_role == ModelRole.OCR
        assert model_manager._current_model_name == "test-ocr-model"
        assert model_manager._is_ready is True

    @pytest.mark.asyncio
    async def test_ensure_model_same_role_returns_immediately(
        self, model_manager: ModelManager
    ) -> None:
        """Calling ensure_model with same role should not reload."""
        await model_manager.ensure_model(ModelRole.CHAT)
        # Second call should be a no-op (same role already loaded)
        url = await model_manager.ensure_model(ModelRole.CHAT)

        assert url == "http://localhost:8000"
        assert model_manager._current_role == ModelRole.CHAT

    @pytest.mark.asyncio
    async def test_ensure_model_different_role_swaps_model(
        self, model_manager: ModelManager
    ) -> None:
        """Switching roles should unload current and load new model."""
        await model_manager.ensure_model(ModelRole.CHAT)
        assert model_manager._current_role == ModelRole.CHAT

        await model_manager.ensure_model(ModelRole.EMBEDDING)
        assert model_manager._current_role == ModelRole.EMBEDDING
        assert model_manager._current_model_name == "test-embedding-model"


# ---------------------------------------------------------------------------
# Tests: Model Swap Serialization (Concurrent Access)
# ---------------------------------------------------------------------------


class TestModelSwapSerialization:
    """Tests for concurrent model swap serialization via async lock."""

    @pytest.mark.asyncio
    async def test_concurrent_ensure_model_serialized(
        self, model_manager: ModelManager
    ) -> None:
        """Concurrent ensure_model calls should be serialized by the lock."""
        results: list[ModelRole] = []

        async def load_chat() -> None:
            await model_manager.ensure_model(ModelRole.CHAT)
            results.append(model_manager._current_role)  # type: ignore

        async def load_embedding() -> None:
            await model_manager.ensure_model(ModelRole.EMBEDDING)
            results.append(model_manager._current_role)  # type: ignore

        # Run concurrently — the lock ensures serialization
        await asyncio.gather(load_chat(), load_embedding())

        # Both should have completed (order depends on scheduling)
        assert len(results) == 2
        # The final state should be one of the two roles
        assert model_manager._current_role in (ModelRole.CHAT, ModelRole.EMBEDDING)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests_all_complete(
        self, model_manager: ModelManager
    ) -> None:
        """Multiple concurrent requests should all complete without errors."""
        roles = [ModelRole.CHAT, ModelRole.EMBEDDING, ModelRole.OCR, ModelRole.CHAT]
        results: list[str] = []

        async def load_model(role: ModelRole) -> None:
            url = await model_manager.ensure_model(role)
            results.append(url)

        await asyncio.gather(*[load_model(r) for r in roles])

        # All requests should have completed
        assert len(results) == 4
        assert all(url == "http://localhost:8000" for url in results)


# ---------------------------------------------------------------------------
# Tests: get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    """Tests for the get_status health endpoint."""

    @pytest.mark.asyncio
    async def test_status_when_no_model_loaded(
        self, model_manager: ModelManager
    ) -> None:
        """Status should show no model when none is loaded."""
        status = await model_manager.get_status()

        assert status.current_role is None
        assert status.current_model_name is None
        assert status.is_ready is False
        assert status.mode == "mock"

    @pytest.mark.asyncio
    async def test_status_after_model_loaded(
        self, model_manager: ModelManager
    ) -> None:
        """Status should reflect the loaded model."""
        await model_manager.ensure_model(ModelRole.CHAT)
        status = await model_manager.get_status()

        assert status.current_role == ModelRole.CHAT
        assert status.current_model_name == "test-chat-model"
        assert status.is_ready is True
        assert status.mode == "mock"


# ---------------------------------------------------------------------------
# Tests: unload_current
# ---------------------------------------------------------------------------


class TestUnloadCurrent:
    """Tests for explicit GPU memory release."""

    @pytest.mark.asyncio
    async def test_unload_releases_model(
        self, model_manager: ModelManager
    ) -> None:
        """unload_current should release the model and reset state."""
        await model_manager.ensure_model(ModelRole.CHAT)
        assert model_manager._current_role == ModelRole.CHAT

        await model_manager.unload_current()

        assert model_manager._current_role is None
        assert model_manager._current_model_name is None
        assert model_manager._is_ready is False
        assert model_manager._gpu_memory_used_gb == 0.0

    @pytest.mark.asyncio
    async def test_unload_when_nothing_loaded_is_noop(
        self, model_manager: ModelManager
    ) -> None:
        """unload_current with no model loaded should be a no-op."""
        await model_manager.unload_current()

        assert model_manager._current_role is None
        assert model_manager._is_ready is False


# ---------------------------------------------------------------------------
# Tests: Mock Mode Embeddings
# ---------------------------------------------------------------------------


class TestMockEmbeddings:
    """Tests for mock mode embedding generation."""

    @pytest.mark.asyncio
    async def test_mock_embedding_correct_dimension(
        self, model_manager: ModelManager
    ) -> None:
        """Mock embeddings should have the configured dimension (1024)."""
        embedding = await model_manager.get_mock_embedding("test text")

        assert len(embedding) == 1024
        assert all(isinstance(v, float) for v in embedding)

    @pytest.mark.asyncio
    async def test_mock_embedding_deterministic(
        self, model_manager: ModelManager
    ) -> None:
        """Same input text should produce same mock embedding."""
        emb1 = await model_manager.get_mock_embedding("hello world")
        emb2 = await model_manager.get_mock_embedding("hello world")

        assert emb1 == emb2

    @pytest.mark.asyncio
    async def test_mock_embedding_different_for_different_text(
        self, model_manager: ModelManager
    ) -> None:
        """Different input text should produce different mock embeddings."""
        emb1 = await model_manager.get_mock_embedding("hello")
        emb2 = await model_manager.get_mock_embedding("world")

        assert emb1 != emb2


# ---------------------------------------------------------------------------
# Tests: Mock Mode Completions
# ---------------------------------------------------------------------------


class TestMockCompletions:
    """Tests for mock mode LLM completions."""

    @pytest.mark.asyncio
    async def test_mock_completion_returns_string(
        self, model_manager: ModelManager
    ) -> None:
        """Mock completion should return a non-empty string."""
        response = await model_manager.get_mock_completion("What is GxP?")

        assert isinstance(response, str)
        assert len(response) > 0
        assert "Mock LLM Response" in response

    @pytest.mark.asyncio
    async def test_mock_completion_includes_prompt_info(
        self, model_manager: ModelManager
    ) -> None:
        """Mock completion should reference the prompt length."""
        prompt = "Tell me about ALCOA+ principles"
        response = await model_manager.get_mock_completion(prompt)

        assert str(len(prompt)) in response


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling on failed model load."""

    @pytest.mark.asyncio
    async def test_failed_load_leaves_clean_state(self) -> None:
        """A failed model load should not leave GPU in inconsistent state."""
        settings = MockSettings()
        settings.model_manager_mode = "gpu"  # type: ignore
        manager = ModelManager(settings=settings)

        # Patch _load_model to simulate failure
        async def failing_load(role: ModelRole) -> None:
            raise RuntimeError("Insufficient GPU memory")

        manager._load_model = failing_load  # type: ignore

        with pytest.raises(RuntimeError):
            await manager.ensure_model(ModelRole.CHAT)

        # State should be clean after failure
        assert manager._current_role is None
        assert manager._current_model_name is None
        assert manager._is_ready is False
        assert manager._gpu_memory_used_gb == 0.0

    @pytest.mark.asyncio
    async def test_custom_embedding_dimension(self) -> None:
        """Mock embeddings should respect custom dimension settings."""
        settings = MockSettings()
        settings.model_embedding_dimension = 512
        manager = ModelManager(settings=settings)

        embedding = await manager.get_mock_embedding("test")
        assert len(embedding) == 512
