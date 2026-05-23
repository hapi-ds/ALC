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

def get_model_manager() -> ModelManager:
    """Get the singleton ModelManager instance via service factory.

    Uses the service factory to ensure the shared InferenceClient is
    properly wired.

    Returns:
        The properly wired ModelManager instance.
    """
    from alcoabase.services.service_factory import (
        get_model_manager as _factory_get_model_manager,
    )

    return _factory_get_model_manager()


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
