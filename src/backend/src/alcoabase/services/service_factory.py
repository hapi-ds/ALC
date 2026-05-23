"""Service factory for creating properly wired service instances.

Creates a single shared InferenceClient and passes it to all services
that need vLLM communication (ModelManager, KnowledgeService, RAGPipeline).

Usage:
    from alcoabase.services.service_factory import (
        get_inference_client,
        get_model_manager,
        get_knowledge_service,
        get_rag_pipeline,
        shutdown_services,
    )

References:
    - Requirements 2.9, 6.6, 6.7: Shared InferenceClient with connection pooling
"""

from __future__ import annotations

import logging

from alcoabase.config import get_settings

logger = logging.getLogger(__name__)

# Module-level singleton instances
_inference_client: "InferenceClient | None" = None
_model_manager: "ModelManager | None" = None
_knowledge_service: "KnowledgeService | None" = None
_rag_pipeline: "RAGPipeline | None" = None


def get_inference_client() -> "InferenceClient":
    """Get or create the shared InferenceClient singleton.

    Creates a single httpx.AsyncClient with connection pooling (max 10
    connections) that is reused across all services for the application
    lifetime.

    Returns:
        The shared InferenceClient instance.
    """
    global _inference_client
    if _inference_client is None:
        from alcoabase.services.inference_client import InferenceClient

        settings = get_settings()
        _inference_client = InferenceClient(
            base_url=settings.vllm_base_url,
            embedding_base_url=settings.vllm_embedding_url,
            max_connections=10,
            connect_timeout=10.0,
        )
        logger.info(
            "InferenceClient created (base_url=%s, embedding_url=%s)",
            settings.vllm_base_url,
            settings.vllm_embedding_url,
        )
    return _inference_client


def get_model_manager() -> "ModelManager":
    """Get or create the ModelManager singleton with shared InferenceClient.

    The ModelManager receives the shared InferenceClient so that all
    health checks and model listing calls use the same connection pool.

    Returns:
        The ModelManager instance.
    """
    global _model_manager
    if _model_manager is None:
        from alcoabase.services.model_manager import ModelManager

        settings = get_settings()
        client = get_inference_client() if settings.model_manager_mode != "mock" else None
        _model_manager = ModelManager(
            settings=settings,
            inference_client=client,
        )
        logger.info("ModelManager created (mode=%s)", settings.model_manager_mode)
    return _model_manager


def get_knowledge_service() -> "KnowledgeService":
    """Get or create the KnowledgeService singleton with shared dependencies.

    The KnowledgeService receives both the ModelManager and the shared
    InferenceClient for embedding generation and OCR calls.

    Returns:
        The KnowledgeService instance.
    """
    global _knowledge_service
    if _knowledge_service is None:
        from alcoabase.services.knowledge_service import KnowledgeService

        settings = get_settings()
        model_manager = get_model_manager()
        client = get_inference_client() if settings.model_manager_mode != "mock" else None
        _knowledge_service = KnowledgeService(
            model_manager=model_manager,
            inference_client=client,
        )
        logger.info("KnowledgeService created")
    return _knowledge_service


def get_rag_pipeline() -> "RAGPipeline":
    """Get or create the RAGPipeline singleton with shared dependencies.

    The RAGPipeline receives the KnowledgeService, ModelManager, and
    the shared InferenceClient for chat completion calls.

    Returns:
        The RAGPipeline instance.
    """
    global _rag_pipeline
    if _rag_pipeline is None:
        from alcoabase.services.rag_pipeline import RAGPipeline

        settings = get_settings()
        knowledge_service = get_knowledge_service()
        model_manager = get_model_manager()
        client = get_inference_client() if settings.model_manager_mode != "mock" else None
        _rag_pipeline = RAGPipeline(
            knowledge_service=knowledge_service,
            model_manager=model_manager,
            inference_client=client,
        )
        logger.info("RAGPipeline created")
    return _rag_pipeline


async def shutdown_services() -> None:
    """Shutdown all services and release resources.

    Closes the shared InferenceClient via ModelManager.shutdown(),
    which releases all httpx connections within 5 seconds.

    Should be called during application shutdown (lifespan handler).
    """
    global _model_manager, _inference_client, _knowledge_service, _rag_pipeline

    if _model_manager is not None:
        await _model_manager.shutdown()
        logger.info("ModelManager shutdown complete")

    # Reset all singletons so they can be recreated if needed (e.g., tests)
    _model_manager = None
    _inference_client = None
    _knowledge_service = None
    _rag_pipeline = None


def reset_services() -> None:
    """Reset all service singletons (for testing purposes only).

    Does NOT close the InferenceClient — use shutdown_services() for
    graceful cleanup. This is only for test isolation.
    """
    global _model_manager, _inference_client, _knowledge_service, _rag_pipeline
    _model_manager = None
    _inference_client = None
    _knowledge_service = None
    _rag_pipeline = None


# Type imports for annotations (avoid circular imports at runtime)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.knowledge_service import KnowledgeService
    from alcoabase.services.model_manager import ModelManager
    from alcoabase.services.rag_pipeline import RAGPipeline
