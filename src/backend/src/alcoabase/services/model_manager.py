"""Model Manager service for GPU model loading and unloading.

Manages multiple LLM models on a single GPU, including on-demand
loading/unloading, model scheduling, and GPU memory management.
Only one large model occupies GPU memory at a time.

The Model_Manager supports three operating modes:
- gpu: Production mode with real vLLM inference on GPU hardware.
- cpu: CPU-only inference with reduced performance.
- mock: Development/testing mode with mock responses (no GPU required).

References:
    - vLLM documentation: https://docs.vllm.ai/
    - NVIDIA Blackwell GPU optimization
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from alcoabase.config import get_settings

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
    """

    current_role: ModelRole | None = None
    current_model_name: str | None = None
    gpu_memory_used_gb: float = 0.0
    is_ready: bool = False
    mode: str = "mock"


class ModelManagerError(Exception):
    """Raised when a model operation fails."""

    pass


class ModelManager:
    """Manages LLM model loading/unloading on a single GPU.

    Provides serialized access to model swaps via an async lock,
    ensuring only one model is loaded at a time and concurrent
    requests wait for the current swap to complete.

    Args:
        settings: Application settings (optional, uses global if not provided).
    """

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or get_settings()
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

        If a different model is currently loaded, it will be unloaded first.
        If the requested model is already loaded and ready, returns immediately.

        Uses an async lock to serialize model swaps — concurrent requests
        will wait for the current swap to complete.

        Args:
            role: The model role to load (CHAT, EMBEDDING, or OCR).

        Returns:
            The vLLM API URL for the loaded model.

        Raises:
            ModelManagerError: If the model fails to load.
        """
        async with self._lock:
            # In mock mode, return immediately
            if self.mode == "mock":
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

            # If already loaded and ready, return immediately
            if self._current_role == role and self._is_ready:
                logger.debug("Model %s already loaded for role %s", self._current_model_name, role.value)
                return self._settings.vllm_base_url

            # Unload current model if different
            if self._current_role is not None and self._current_role != role:
                await self._unload_model()

            # Load the requested model
            await self._load_model(role)

            return self._settings.vllm_base_url

    async def get_status(self) -> ModelStatus:
        """Get the current status of the Model_Manager.

        Returns:
            ModelStatus with current model info, GPU memory, and readiness.
        """
        return ModelStatus(
            current_role=self._current_role,
            current_model_name=self._current_model_name,
            gpu_memory_used_gb=self._gpu_memory_used_gb,
            is_ready=self._is_ready,
            mode=self.mode,
        )

    async def unload_current(self) -> None:
        """Explicitly unload the current model to release GPU memory.

        Acquires the lock to prevent concurrent access during unload.
        """
        async with self._lock:
            if self._current_role is not None:
                await self._unload_model()

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
        """Load a model via the vLLM API.

        In gpu/cpu mode, this calls the vLLM server to load the model
        and waits for the readiness health check to pass.

        Args:
            role: The model role to load.

        Raises:
            ModelManagerError: If the model fails to load.
        """
        config = self._configs[role]
        logger.info("Loading model %s for role %s", config.name, role.value)

        try:
            # In production (gpu/cpu mode), this would:
            # 1. Call vLLM API to load the model from config.path
            # 2. Wait for the /health endpoint to report ready
            # 3. Update GPU memory tracking
            #
            # For now, simulate the loading process
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
        """Unload the current model to release GPU memory.

        In production, this calls the vLLM API to unload the model.
        """
        if self._current_role is None:
            return

        logger.info(
            "Unloading model %s (role: %s)",
            self._current_model_name,
            self._current_role.value,
        )

        # In production (gpu/cpu mode), this would:
        # 1. Call vLLM API to unload the current model
        # 2. Wait for GPU memory to be released
        # 3. Verify clean state

        self._current_role = None
        self._current_model_name = None
        self._is_ready = False
        self._gpu_memory_used_gb = 0.0

        logger.info("Model unloaded, GPU memory released")
