"""Model Manager service for GPU model loading and unloading.

Manages multiple LLM models on a single GPU, including on-demand
loading/unloading, model scheduling, and GPU memory management.
Only one large model occupies GPU memory at a time.

The Model_Manager supports three operating modes:
- gpu: Production mode with real vLLM inference on GPU hardware.
- cpu: CPU-only inference with reduced performance.
- mock: Development/testing mode with mock responses (no GPU required).

Architecture:
- EMBEDDING role → dedicated always-on vLLM instance (small: ~2 GB)
- CHAT/OCR role → shared main vLLM instance (container restart for swap)

References:
    - vLLM documentation: https://docs.vllm.ai/
    - NVIDIA Blackwell GPU optimization
"""

from __future__ import annotations

import asyncio
import logging
import random
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from alcoabase.config import get_settings

if TYPE_CHECKING:
    from alcoabase.services.inference_client import InferenceClient

logger = logging.getLogger(__name__)


class ModelRole(Enum):
    """Roles for models managed by the Model_Manager.

    Each role corresponds to a different model that can be loaded
    on the GPU. Only one model is loaded at a time.
    """

    CHAT = "chat"
    EMBEDDING = "embedding"
    OCR = "ocr"


@dataclass
class ModelConfig:
    """Configuration for a specific model role.

    Attributes:
        name: HuggingFace model identifier.
        path: Local filesystem path to pre-downloaded weights.
        max_gpu_memory_gb: Maximum GPU memory allocation (for CHAT only).
        dimension: Output embedding dimension (for EMBEDDING only).
    """

    name: str
    path: str
    max_gpu_memory_gb: int | None = None
    dimension: int | None = None


@dataclass
class ModelStatus:
    """Current status of the Model_Manager.

    Attributes:
        current_role: The currently loaded model role, or None if no model loaded.
        current_model_name: Name of the currently loaded model.
        gpu_memory_used_gb: Estimated GPU memory usage in GB.
        is_ready: Whether the current model is ready for inference.
        mode: The operating mode (gpu, cpu, mock).
        vllm_reachable: Whether the vLLM server is reachable. None in mock mode.
    """

    current_role: ModelRole | None = None
    current_model_name: str | None = None
    gpu_memory_used_gb: float = 0.0
    is_ready: bool = False
    mode: str = "mock"
    vllm_reachable: bool | None = None


class ModelManagerError(Exception):
    """Raised when a model operation fails."""

    pass


# Health check polling interval in seconds
_HEALTH_POLL_INTERVAL = 2.0

# Timeouts for health check polling (seconds)
_GPU_LOAD_TIMEOUT = 120.0
_CPU_LOAD_TIMEOUT = 300.0
_UNLOAD_TIMEOUT = 60.0

# Docker compose service names
_VLLM_GPU_SERVICE = "vllm"
_VLLM_CPU_SERVICE = "vllm-cpu"


class ModelManager:
    """Manages LLM model loading/unloading on a single GPU.

    Routes inference requests to the correct vLLM instance:
    - EMBEDDING requests → dedicated embedding vLLM instance (always on)
    - CHAT/OCR requests → main vLLM instance (may require container restart)

    Provides serialized access to model swaps via an async lock,
    ensuring only one model is loaded at a time and concurrent
    requests wait for the current swap to complete.

    Args:
        settings: Application settings (optional, uses global if not provided).
        inference_client: Optional InferenceClient for HTTP communication with vLLM.
    """

    def __init__(
        self,
        settings: Any | None = None,
        inference_client: InferenceClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._inference_client = inference_client
        self._lock = asyncio.Lock()
        self._current_role: ModelRole | None = None
        self._current_model_name: str | None = None
        self._is_ready: bool = False
        self._gpu_memory_used_gb: float = 0.0

        # Build model configs from settings
        self._configs: dict[ModelRole, ModelConfig] = {
            ModelRole.CHAT: ModelConfig(
                name=self._settings.model_chat_name,
                path=self._settings.model_chat_path,
                max_gpu_memory_gb=self._settings.model_chat_max_gpu_memory_gb,
            ),
            ModelRole.EMBEDDING: ModelConfig(
                name=self._settings.model_embedding_name,
                path=self._settings.model_embedding_path,
                dimension=self._settings.model_embedding_dimension,
            ),
            ModelRole.OCR: ModelConfig(
                name=self._settings.model_ocr_name,
                path=self._settings.model_ocr_path,
            ),
        }

    @property
    def mode(self) -> str:
        """The current operating mode (gpu, cpu, mock)."""
        return self._settings.model_manager_mode

    async def ensure_model(self, role: ModelRole) -> str:
        """Ensure the requested model is loaded and ready.

        For EMBEDDING role in gpu/cpu mode: returns the embedding instance URL
        immediately (always-on, no swap needed).

        For CHAT/OCR role in gpu/cpu mode: checks if the main vLLM instance
        has the correct model loaded, restarts the container if not.

        In mock mode: simulates loading without HTTP calls.

        Uses an async lock to serialize model swaps — concurrent requests
        will wait for the current swap to complete.

        Args:
            role: The model role to load (CHAT, EMBEDDING, or OCR).

        Returns:
            The vLLM API URL for the loaded model.

        Raises:
            ModelManagerError: If the model fails to load.
        """
        # In mock mode, return immediately with simulated state
        if self.mode == "mock":
            async with self._lock:
                self._current_role = role
                self._current_model_name = self._configs[role].name
                self._is_ready = True
                self._gpu_memory_used_gb = 0.0
                logger.info(
                    "Mock mode: simulated loading model %s for role %s",
                    self._current_model_name,
                    role.value,
                )
                return self._settings.vllm_base_url

        # EMBEDDING role: always-on dedicated instance, no swap needed
        if role == ModelRole.EMBEDDING:
            logger.debug(
                "EMBEDDING role: returning dedicated embedding URL %s",
                self._settings.vllm_embedding_url,
            )
            return self._settings.vllm_embedding_url

        # CHAT/OCR role: may need container restart on main instance
        # Check idempotency without lock first
        if self._current_role == role and self._is_ready:
            logger.debug(
                "Model %s already loaded for role %s",
                self._current_model_name,
                role.value,
            )
            return self._settings.vllm_base_url

        # Acquire lock for model swap
        async with self._lock:
            # Double-check after acquiring lock (another coroutine may have loaded it)
            if self._current_role == role and self._is_ready:
                logger.debug(
                    "Model %s already loaded for role %s (after lock)",
                    self._current_model_name,
                    role.value,
                )
                return self._settings.vllm_base_url

            # Check if the correct model is already loaded on the vLLM instance
            if self._inference_client is not None:
                try:
                    loaded_models = await self._inference_client.list_models()
                    config = self._configs[role]
                    if config.name in loaded_models:
                        # Model is already loaded on vLLM, update state
                        self._current_role = role
                        self._current_model_name = config.name
                        self._is_ready = True
                        logger.info(
                            "Model %s already loaded on vLLM for role %s",
                            config.name,
                            role.value,
                        )
                        return self._settings.vllm_base_url
                except Exception as e:
                    logger.warning(
                        "Failed to check loaded models: %s", str(e)
                    )

            # Unload current model if different role is loaded
            if self._current_role is not None and self._current_role != role:
                await self._unload_model()

            # Load the requested model
            await self._load_model(role)

            return self._settings.vllm_base_url

    async def get_status(self) -> ModelStatus:
        """Get the current status of the Model_Manager.

        In gpu/cpu mode, performs a health check against the vLLM server
        with a 5-second timeout to determine reachability.

        In mock mode, sets vllm_reachable to None.

        Returns:
            ModelStatus with current model info, GPU memory, readiness,
            and vLLM reachability.
        """
        vllm_reachable: bool | None = None

        if self.mode != "mock" and self._inference_client is not None:
            try:
                vllm_reachable = await self._inference_client.health_check()
            except Exception:
                vllm_reachable = False
                logger.warning(
                    "vLLM health check failed during get_status"
                )

        return ModelStatus(
            current_role=self._current_role,
            current_model_name=self._current_model_name,
            gpu_memory_used_gb=self._gpu_memory_used_gb,
            is_ready=self._is_ready,
            mode=self.mode,
            vllm_reachable=vllm_reachable,
        )

    async def unload_current(self) -> None:
        """Explicitly unload the current model to release GPU memory.

        Acquires the lock to prevent concurrent access during unload.
        """
        async with self._lock:
            if self._current_role is not None:
                await self._unload_model()

    async def shutdown(self) -> None:
        """Close the InferenceClient and release all connections.

        Should be called during application shutdown.
        """
        if self._inference_client is not None:
            await self._inference_client.close()
            logger.info("ModelManager shutdown: InferenceClient closed")

    async def get_mock_embedding(self, text: str) -> list[float]:
        """Generate a mock embedding vector for development/testing.

        Returns a random vector of the correct dimension configured
        for the embedding model.

        Args:
            text: The input text (used for deterministic seeding).

        Returns:
            A list of floats representing the mock embedding.
        """
        dimension = self._configs[ModelRole.EMBEDDING].dimension or 1024
        # Use text hash for deterministic mock embeddings
        seed = hash(text) % (2**32)
        rng = random.Random(seed)
        return [rng.gauss(0, 1) for _ in range(dimension)]

    async def get_mock_completion(self, prompt: str) -> str:
        """Generate a mock LLM completion for development/testing.

        Args:
            prompt: The input prompt.

        Returns:
            A mock response string.
        """
        return (
            f"[Mock LLM Response] This is a mock response for development/testing. "
            f"Prompt length: {len(prompt)} characters. "
            f"In production, this would be generated by {self._configs[ModelRole.CHAT].name}."
        )

    async def _load_model(self, role: ModelRole) -> None:
        """Load a model via container restart and health check polling.

        In gpu/cpu mode, restarts the vLLM container with the correct model
        arguments and polls /health until the server is ready.

        Args:
            role: The model role to load.

        Raises:
            ModelManagerError: If the model fails to load (unreachable or timeout).
        """
        config = self._configs[role]
        logger.info("Loading model %s for role %s", config.name, role.value)

        try:
            # Restart the vLLM container with the new model
            self._restart_container(config)

            # Determine timeout based on mode
            timeout = (
                _GPU_LOAD_TIMEOUT if self.mode == "gpu" else _CPU_LOAD_TIMEOUT
            )

            # Poll /health until ready
            await self._poll_health_until_ready(timeout, config.name, role.value)

            # Update internal state
            self._current_role = role
            self._current_model_name = config.name
            self._is_ready = True

            # Estimate GPU memory based on role
            if role == ModelRole.CHAT:
                self._gpu_memory_used_gb = float(config.max_gpu_memory_gb or 60)
            elif role == ModelRole.EMBEDDING:
                self._gpu_memory_used_gb = 4.0
            elif role == ModelRole.OCR:
                self._gpu_memory_used_gb = 40.0

            logger.info(
                "Model %s loaded successfully (estimated %.1f GB GPU memory)",
                config.name,
                self._gpu_memory_used_gb,
            )
        except ModelManagerError:
            # Ensure clean state on failure
            self._current_role = None
            self._current_model_name = None
            self._is_ready = False
            self._gpu_memory_used_gb = 0.0
            raise
        except Exception as e:
            # Ensure clean state on failure
            self._current_role = None
            self._current_model_name = None
            self._is_ready = False
            self._gpu_memory_used_gb = 0.0
            raise ModelManagerError(
                f"Failed to load model {config.name} for role {role.value}: {e}"
            ) from e

    async def _unload_model(self) -> None:
        """Unload the current model by restarting the container to idle state.

        In gpu/cpu mode, restarts the container and polls until idle.
        Timeout: 60 seconds.

        Raises:
            ModelManagerError: If the unload fails (timeout or unreachable).
        """
        if self._current_role is None:
            return

        model_name = self._current_model_name
        role_value = self._current_role.value

        logger.info(
            "Unloading model %s (role: %s)",
            model_name,
            role_value,
        )

        if self.mode == "mock":
            # Mock mode: immediate state reset
            self._current_role = None
            self._current_model_name = None
            self._is_ready = False
            self._gpu_memory_used_gb = 0.0
            logger.info("Model unloaded, GPU memory released")
            return

        # gpu/cpu mode: restart container to release the model
        try:
            service_name = (
                _VLLM_GPU_SERVICE if self.mode == "gpu" else _VLLM_CPU_SERVICE
            )
            cmd = ["docker", "compose", "restart", service_name]
            logger.info("Restarting container for unload: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise ModelManagerError(
                    f"Model {model_name} failed to unload: "
                    f"container restart failed with exit code {result.returncode}: "
                    f"{result.stderr[:500]}"
                )

            # Poll until the server is back up (idle state)
            start_time = time.monotonic()
            while (time.monotonic() - start_time) < _UNLOAD_TIMEOUT:
                await asyncio.sleep(_HEALTH_POLL_INTERVAL)
                if self._inference_client is not None:
                    try:
                        healthy = await self._inference_client.health_check()
                        if healthy:
                            break
                    except Exception:
                        continue

            elapsed = time.monotonic() - start_time
            if elapsed >= _UNLOAD_TIMEOUT:
                # Reset state even on timeout
                self._current_role = None
                self._current_model_name = None
                self._is_ready = False
                self._gpu_memory_used_gb = 0.0
                raise ModelManagerError(
                    f"Model {model_name} failed to unload: "
                    f"timeout after {elapsed:.1f}s"
                )

            # Clean state after successful unload
            self._current_role = None
            self._current_model_name = None
            self._is_ready = False
            self._gpu_memory_used_gb = 0.0
            logger.info("Model unloaded, GPU memory released")

        except ModelManagerError:
            # Propagate ModelManagerError as-is, ensure state is not-ready
            self._current_role = None
            self._current_model_name = None
            self._is_ready = False
            self._gpu_memory_used_gb = 0.0
            raise
        except Exception as e:
            self._current_role = None
            self._current_model_name = None
            self._is_ready = False
            self._gpu_memory_used_gb = 0.0
            raise ModelManagerError(
                f"Model {model_name} failed to unload: {e}"
            ) from e

    def _restart_container(self, config: ModelConfig) -> None:
        """Restart the vLLM container with the specified model configuration.

        Uses docker compose to restart the appropriate service with
        the model path as an environment variable override.

        Args:
            config: The model configuration to load.

        Raises:
            ModelManagerError: If the container restart command fails.
        """
        service_name = (
            _VLLM_GPU_SERVICE if self.mode == "gpu" else _VLLM_CPU_SERVICE
        )

        # Stop the current container
        stop_cmd = ["docker", "compose", "stop", service_name]
        logger.info("Stopping container: %s", " ".join(stop_cmd))

        try:
            result = subprocess.run(
                stop_cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "Container stop returned non-zero: %s", result.stderr[:500]
                )
        except subprocess.TimeoutExpired:
            logger.warning("Container stop timed out, proceeding with restart")

        # Start with new model arguments via environment override
        # The vLLM container reads MODEL_PATH from environment
        start_cmd = ["docker", "compose", "up", "-d", service_name]
        env_override = {"MODEL_PATH": config.path, "MODEL_NAME": config.name}

        logger.info(
            "Starting container with model %s: %s (env: %s)",
            config.name,
            " ".join(start_cmd),
            env_override,
        )

        try:
            import os

            env = {**os.environ, **env_override}
            result = subprocess.run(
                start_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            if result.returncode != 0:
                raise ModelManagerError(
                    f"Failed to start vLLM container for model {config.name}: "
                    f"exit code {result.returncode}: {result.stderr[:500]}"
                )
        except subprocess.TimeoutExpired as e:
            raise ModelManagerError(
                f"Failed to start vLLM container for model {config.name}: "
                f"docker compose command timed out"
            ) from e

    async def _poll_health_until_ready(
        self,
        timeout: float,
        model_name: str,
        role_value: str,
    ) -> None:
        """Poll the vLLM /health endpoint until it returns HTTP 200.

        Args:
            timeout: Maximum time to wait in seconds.
            model_name: Name of the model being loaded (for error messages).
            role_value: Role value string (for error messages).

        Raises:
            ModelManagerError: If the server is unreachable or times out.
        """
        if self._inference_client is None:
            raise ModelManagerError(
                f"Model {model_name} for role {role_value} failed to load: "
                f"no InferenceClient configured"
            )

        start_time = time.monotonic()
        last_error: str | None = None

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                raise ModelManagerError(
                    f"Model {model_name} for role {role_value} failed to load: "
                    f"health check timeout after {elapsed:.1f}s"
                )

            try:
                healthy = await self._inference_client.health_check()
                if healthy:
                    logger.info(
                        "Health check passed for model %s after %.1fs",
                        model_name,
                        elapsed,
                    )
                    return
            except Exception as e:
                last_error = str(e)
                logger.debug(
                    "Health check attempt failed (%.1fs elapsed): %s",
                    elapsed,
                    last_error,
                )

            await asyncio.sleep(_HEALTH_POLL_INTERVAL)
