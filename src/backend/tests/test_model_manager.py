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
    vllm_embedding_url = "http://localhost:8001"


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
        assert status.vllm_reachable is None

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
        assert status.vllm_reachable is None


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


# ---------------------------------------------------------------------------
# Tests: GPU/CPU Mode — Health Check Polling, Timeouts, Unload Failures,
#        vllm_reachable, EMBEDDING routing, Container Restart
# ---------------------------------------------------------------------------
# Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 9.1, 9.2, 9.3, 9.4


from unittest.mock import AsyncMock, patch
import time


class GpuCpuSettings:
    """Settings configured for gpu mode testing."""

    model_chat_name = "Qwen/Qwen3.6-35B-A3B"
    model_chat_path = "/models/qwen3.6-35b-a3b"
    model_chat_max_gpu_memory_gb = 24
    model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
    model_embedding_path = "/models/qwen3-embedding-0.6b"
    model_embedding_dimension = 1024
    model_ocr_name = "google/gemma-4-E4B-it"
    model_ocr_path = "/models/gemma-4-e4b-it"
    model_manager_mode = "gpu"
    vllm_base_url = "http://localhost:8000"
    vllm_embedding_url = "http://localhost:8001"


def _make_gpu_settings(mode: str = "gpu") -> GpuCpuSettings:
    """Create settings for gpu/cpu mode tests."""
    settings = GpuCpuSettings()
    settings.model_manager_mode = mode
    return settings


def _make_client_mock(
    health_returns: list[bool] | bool = True,
    list_models_returns: list[str] | None = None,
) -> AsyncMock:
    """Create a mock InferenceClient.

    Args:
        health_returns: If a list, health_check will return values in order
            (using side_effect). If a bool, always returns that value.
        list_models_returns: List of model names to return from list_models.
    """
    client = AsyncMock()

    if isinstance(health_returns, list):
        client.health_check = AsyncMock(side_effect=health_returns)
    else:
        client.health_check = AsyncMock(return_value=health_returns)

    client.list_models = AsyncMock(
        return_value=list_models_returns or []
    )
    client.close = AsyncMock()
    return client


class TestHealthCheckPolling:
    """Tests for health check polling during model load (Req 1.2)."""

    @pytest.mark.asyncio
    async def test_health_check_polls_until_healthy(self) -> None:
        """Health check should poll multiple times until server is ready.

        Validates: Requirements 1.2
        """
        settings = _make_gpu_settings("gpu")
        # health_check returns False 3 times, then True
        health_responses = [False, False, False, True]
        client = _make_client_mock(health_returns=health_responses)

        manager = ModelManager(settings=settings, inference_client=client)

        with patch.object(manager, "_restart_container"):
            url = await manager.ensure_model(ModelRole.CHAT)

        assert url == settings.vllm_base_url
        assert manager._is_ready is True
        assert manager._current_role == ModelRole.CHAT
        # health_check should have been called 4 times (3 False + 1 True)
        assert client.health_check.call_count == 4

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_single_poll_success(self) -> None:
        """If health check passes on first try, no extra polling needed.

        Validates: Requirements 1.2
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=[True])

        manager = ModelManager(settings=settings, inference_client=client)

        with patch.object(manager, "_restart_container"):
            url = await manager.ensure_model(ModelRole.CHAT)

        assert url == settings.vllm_base_url
        assert client.health_check.call_count == 1

        await manager.shutdown()


class TestHealthCheckTimeout:
    """Tests for timeout raising ModelManagerError (Req 1.3)."""

    @pytest.mark.asyncio
    async def test_timeout_raises_model_manager_error_with_details(self) -> None:
        """Timeout should raise ModelManagerError with model name, role, elapsed time.

        Validates: Requirements 1.3
        """
        settings = _make_gpu_settings("gpu")
        # health_check always returns False to trigger timeout
        client = _make_client_mock(health_returns=False)

        manager = ModelManager(settings=settings, inference_client=client)

        # Patch timeout to a very short value to avoid long test
        with (
            patch.object(manager, "_restart_container"),
            patch(
                "alcoabase.services.model_manager._GPU_LOAD_TIMEOUT", 0.1
            ),
            patch(
                "alcoabase.services.model_manager._HEALTH_POLL_INTERVAL", 0.01
            ),
        ):
            with pytest.raises(ModelManagerError) as exc_info:
                await manager.ensure_model(ModelRole.CHAT)

        error_msg = str(exc_info.value)
        # Should contain model name, role, and timeout info
        assert settings.model_chat_name in error_msg
        assert "chat" in error_msg
        assert "timeout" in error_msg.lower()

        # State should be not-ready after timeout
        assert manager._is_ready is False
        assert manager._current_role is None

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_cpu_mode_uses_longer_timeout(self) -> None:
        """CPU mode should use the longer timeout (300s vs 120s for gpu).

        Validates: Requirements 1.2
        """
        settings = _make_gpu_settings("cpu")
        client = _make_client_mock(health_returns=False)

        manager = ModelManager(settings=settings, inference_client=client)

        # Use very short timeouts for testing
        with (
            patch.object(manager, "_restart_container"),
            patch(
                "alcoabase.services.model_manager._CPU_LOAD_TIMEOUT", 0.1
            ),
            patch(
                "alcoabase.services.model_manager._HEALTH_POLL_INTERVAL", 0.01
            ),
        ):
            with pytest.raises(ModelManagerError) as exc_info:
                await manager.ensure_model(ModelRole.OCR)

        error_msg = str(exc_info.value)
        assert settings.model_ocr_name in error_msg
        assert "ocr" in error_msg

        await manager.shutdown()


class TestUnloadFailurePreventsLoad:
    """Tests for unload failure preventing new load attempt (Req 1.9)."""

    @pytest.mark.asyncio
    async def test_unload_failure_prevents_new_load(self) -> None:
        """If _unload_model fails, state is not-ready and new load is NOT attempted.

        Validates: Requirements 1.9
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=True)

        manager = ModelManager(settings=settings, inference_client=client)

        # Manually set state as if CHAT is loaded
        manager._current_role = ModelRole.CHAT
        manager._current_model_name = settings.model_chat_name
        manager._is_ready = True

        # Make _unload_model raise ModelManagerError (simulating real behavior
        # where _unload_model resets state before raising)
        async def failing_unload() -> None:
            manager._current_role = None
            manager._current_model_name = None
            manager._is_ready = False
            manager._gpu_memory_used_gb = 0.0
            raise ModelManagerError(
                f"Model {settings.model_chat_name} failed to unload: timeout after 60.0s"
            )

        with patch.object(manager, "_unload_model", side_effect=failing_unload):
            with patch.object(manager, "_load_model") as mock_load:
                with pytest.raises(ModelManagerError) as exc_info:
                    await manager.ensure_model(ModelRole.OCR)

                # _load_model should NOT have been called
                mock_load.assert_not_called()

        # State should be not-ready
        assert manager._is_ready is False
        assert manager._current_role is None

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_unload_failure_propagates_error(self) -> None:
        """Unload failure error should propagate to the caller.

        Validates: Requirements 1.5, 1.9
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=True)

        manager = ModelManager(settings=settings, inference_client=client)

        # Set state as if OCR is loaded
        manager._current_role = ModelRole.OCR
        manager._current_model_name = settings.model_ocr_name
        manager._is_ready = True

        error_message = "Model google/gemma-4-E4B-it failed to unload: timeout after 60.0s"

        async def failing_unload() -> None:
            raise ModelManagerError(error_message)

        with patch.object(manager, "_unload_model", side_effect=failing_unload):
            with pytest.raises(ModelManagerError, match="failed to unload"):
                await manager.ensure_model(ModelRole.CHAT)

        await manager.shutdown()


class TestVllmReachableStatus:
    """Tests for vllm_reachable field in get_status (Req 9.1, 9.2, 9.3, 9.4)."""

    @pytest.mark.asyncio
    async def test_vllm_reachable_true_when_healthy(self) -> None:
        """get_status returns vllm_reachable=True when health check succeeds.

        Validates: Requirements 9.1, 9.2
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=True)

        manager = ModelManager(settings=settings, inference_client=client)
        status = await manager.get_status()

        assert status.vllm_reachable is True
        assert status.mode == "gpu"

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_vllm_reachable_false_when_unhealthy(self) -> None:
        """get_status returns vllm_reachable=False when health check fails.

        Validates: Requirements 9.1, 9.4
        """
        settings = _make_gpu_settings("gpu")
        client = AsyncMock()
        client.health_check = AsyncMock(return_value=False)
        client.close = AsyncMock()

        manager = ModelManager(settings=settings, inference_client=client)
        status = await manager.get_status()

        assert status.vllm_reachable is False

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_vllm_reachable_false_on_exception(self) -> None:
        """get_status returns vllm_reachable=False when health check raises.

        Validates: Requirements 9.4
        """
        settings = _make_gpu_settings("gpu")
        client = AsyncMock()
        client.health_check = AsyncMock(side_effect=Exception("Connection refused"))
        client.close = AsyncMock()

        manager = ModelManager(settings=settings, inference_client=client)
        status = await manager.get_status()

        assert status.vllm_reachable is False

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_vllm_reachable_none_in_mock_mode(self) -> None:
        """get_status returns vllm_reachable=None in mock mode.

        Validates: Requirements 9.3
        """
        settings = _make_gpu_settings("mock")
        client = _make_client_mock(health_returns=True)

        manager = ModelManager(settings=settings, inference_client=client)
        status = await manager.get_status()

        assert status.vllm_reachable is None
        # health_check should NOT have been called in mock mode
        client.health_check.assert_not_called()

        await manager.shutdown()


class TestEmbeddingRoleRouting:
    """Tests for EMBEDDING role returning embedding URL without swap (Req 1.1)."""

    @pytest.mark.asyncio
    async def test_embedding_returns_embedding_url_without_swap(self) -> None:
        """EMBEDDING role should return vllm_embedding_url without calling list_models or health_check.

        Validates: Requirements 1.1
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=True)

        manager = ModelManager(settings=settings, inference_client=client)

        url = await manager.ensure_model(ModelRole.EMBEDDING)

        assert url == settings.vllm_embedding_url
        # Should NOT call list_models or health_check for EMBEDDING
        client.list_models.assert_not_called()
        client.health_check.assert_not_called()

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_embedding_does_not_affect_main_instance_state(self) -> None:
        """EMBEDDING role should not change the main instance model state.

        Validates: Requirements 1.1
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(
            health_returns=True,
            list_models_returns=[settings.model_chat_name],
        )

        manager = ModelManager(settings=settings, inference_client=client)

        # Load CHAT first
        with patch.object(manager, "_restart_container"):
            await manager.ensure_model(ModelRole.CHAT)

        assert manager._current_role == ModelRole.CHAT

        # Now request EMBEDDING — should not change main instance state
        url = await manager.ensure_model(ModelRole.EMBEDDING)

        assert url == settings.vllm_embedding_url
        # Main instance state should still be CHAT
        assert manager._current_role == ModelRole.CHAT
        assert manager._is_ready is True

        await manager.shutdown()


class TestContainerRestart:
    """Tests for container restart subprocess call for CHAT↔OCR swap (Req 1.1, 1.4)."""

    @pytest.mark.asyncio
    async def test_chat_to_ocr_swap_calls_docker_compose(self) -> None:
        """Swapping from CHAT to OCR should call docker compose stop and up.

        Validates: Requirements 1.1, 1.4
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=[True, True])

        manager = ModelManager(settings=settings, inference_client=client)

        # Set state as if CHAT is loaded
        manager._current_role = ModelRole.CHAT
        manager._current_model_name = settings.model_chat_name
        manager._is_ready = True

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            # Need to also mock the unload's health polling
            # _unload_model restarts container and polls health
            # _load_model restarts container and polls health
            await manager.ensure_model(ModelRole.OCR)

        # subprocess.run should have been called for docker compose commands
        assert mock_subprocess.call_count >= 2  # stop + up for unload, stop + up for load

        # Verify docker compose commands were called
        calls = mock_subprocess.call_args_list
        docker_commands = [call[0][0] for call in calls]

        # Should contain stop and up commands
        has_stop = any("stop" in cmd for cmd in docker_commands)
        has_up = any("up" in cmd for cmd in docker_commands)
        assert has_stop, f"Expected 'stop' command, got: {docker_commands}"
        assert has_up, f"Expected 'up' command, got: {docker_commands}"

        # Final state should be OCR
        assert manager._current_role == ModelRole.OCR
        assert manager._current_model_name == settings.model_ocr_name

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_ocr_to_chat_swap_calls_docker_compose(self) -> None:
        """Swapping from OCR to CHAT should call docker compose commands.

        Validates: Requirements 1.1
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=[True, True])

        manager = ModelManager(settings=settings, inference_client=client)

        # Set state as if OCR is loaded
        manager._current_role = ModelRole.OCR
        manager._current_model_name = settings.model_ocr_name
        manager._is_ready = True

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            await manager.ensure_model(ModelRole.CHAT)

        # subprocess.run should have been called
        assert mock_subprocess.call_count >= 2

        # Final state should be CHAT
        assert manager._current_role == ModelRole.CHAT
        assert manager._current_model_name == settings.model_chat_name

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_gpu_mode_uses_vllm_service_name(self) -> None:
        """GPU mode should use 'vllm' as the docker compose service name.

        Validates: Requirements 1.1
        """
        settings = _make_gpu_settings("gpu")
        client = _make_client_mock(health_returns=[True])

        manager = ModelManager(settings=settings, inference_client=client)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            await manager.ensure_model(ModelRole.CHAT)

        # Check that 'vllm' service name was used (not 'vllm-cpu')
        calls = mock_subprocess.call_args_list
        for call in calls:
            cmd = call[0][0]
            if "stop" in cmd or "up" in cmd:
                assert "vllm" in cmd, f"Expected 'vllm' in command: {cmd}"

        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_cpu_mode_uses_vllm_cpu_service_name(self) -> None:
        """CPU mode should use 'vllm-cpu' as the docker compose service name.

        Validates: Requirements 1.1
        """
        settings = _make_gpu_settings("cpu")
        client = _make_client_mock(health_returns=[True])

        manager = ModelManager(settings=settings, inference_client=client)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            await manager.ensure_model(ModelRole.OCR)

        # Check that 'vllm-cpu' service name was used
        calls = mock_subprocess.call_args_list
        has_cpu_service = any(
            "vllm-cpu" in call[0][0] for call in calls
            if isinstance(call[0][0], list)
        )
        # Also check if it's passed as a list element
        for call in calls:
            cmd = call[0][0]
            if isinstance(cmd, list) and ("stop" in cmd or "up" in cmd):
                assert "vllm-cpu" in cmd

        await manager.shutdown()
