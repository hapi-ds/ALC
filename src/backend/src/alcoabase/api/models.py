"""Models API endpoint for Model_Manager status.

Provides a health endpoint reporting which model is currently loaded,
GPU memory usage, and model readiness status.

References:
    - Task 18.12: Create FastAPI endpoint GET /api/models/status
    - Design doc Section 9: Model_Manager health endpoint
"""

from fastapi import APIRouter
from pydantic import BaseModel

from alcoabase.services.model_manager import ModelManager, ModelStatus

router = APIRouter(prefix="/models", tags=["Models"])

# Module-level Model_Manager instance (singleton pattern)
_model_manager: ModelManager | None = None


def get_model_manager() -> ModelManager:
    """Get or create the singleton ModelManager instance.

    Returns:
        The ModelManager instance.
    """
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


class ModelStatusResponse(BaseModel):
    """Response schema for the model status endpoint.

    Attributes:
        current_role: The currently loaded model role, or null if none.
        current_model_name: Name of the currently loaded model.
        gpu_memory_used_gb: Estimated GPU memory usage in GB.
        is_ready: Whether the current model is ready for inference.
        mode: The operating mode (gpu, cpu, mock).
    """

    current_role: str | None = None
    current_model_name: str | None = None
    gpu_memory_used_gb: float = 0.0
    is_ready: bool = False
    mode: str = "mock"


@router.get("/status", response_model=ModelStatusResponse)
async def get_models_status() -> ModelStatusResponse:
    """Get the current Model_Manager status.

    Returns the currently loaded model role, model name, GPU memory usage,
    and readiness status.

    Returns:
        ModelStatusResponse with current model information.
    """
    manager = get_model_manager()
    status: ModelStatus = await manager.get_status()

    return ModelStatusResponse(
        current_role=status.current_role.value if status.current_role else None,
        current_model_name=status.current_model_name,
        gpu_memory_used_gb=status.gpu_memory_used_gb,
        is_ready=status.is_ready,
        mode=status.mode,
    )
