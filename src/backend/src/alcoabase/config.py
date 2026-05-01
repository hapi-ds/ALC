"""Application configuration loaded from environment variables.

Uses pydantic-settings to provide typed, validated configuration with
automatic loading from .env files and environment variables. All secrets
and service URLs are configured here — never hardcoded.

Usage:
    from alcoabase.config import get_settings

    settings = get_settings()
    print(settings.database_url)
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AlcoaBase application settings.

    All values are loaded from environment variables or a .env file.
    See .env.example for documentation of each variable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Database (PostgreSQL)
    # ─────────────────────────────────────────────────────────────────────

    database_url: str = Field(
        default="postgresql+asyncpg://alcoabase:changeme_postgres@localhost:5432/alcoabase",
        description="PostgreSQL async connection URL (asyncpg driver).",
        alias="DATABASE_URL",
    )

    # ─────────────────────────────────────────────────────────────────────
    # MinIO (S3-compatible object storage)
    # ─────────────────────────────────────────────────────────────────────

    minio_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO server endpoint (host:port).",
        alias="MINIO_ENDPOINT",
    )
    minio_access_key: str = Field(
        default="alcoabase",
        description="MinIO access key (root user).",
        alias="MINIO_ACCESS_KEY",
    )
    minio_secret_key: str = Field(
        default="changeme_minio",
        description="MinIO secret key (root password).",
        alias="MINIO_SECRET_KEY",
    )
    minio_bucket: str = Field(
        default="alcoabase",
        description="Default MinIO bucket for document storage.",
        alias="MINIO_BUCKET",
    )
    minio_use_ssl: bool = Field(
        default=False,
        description="Whether to use SSL/TLS for MinIO connections.",
        alias="MINIO_USE_SSL",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Redis (Celery broker)
    # ─────────────────────────────────────────────────────────────────────

    redis_url: str = Field(
        default="redis://:changeme_redis@localhost:6379/0",
        description="Redis connection URL for Celery broker.",
        alias="REDIS_URL",
    )

    # ─────────────────────────────────────────────────────────────────────
    # OpenSearch (vectors + search)
    # ─────────────────────────────────────────────────────────────────────

    opensearch_url: str = Field(
        default="http://localhost:9200",
        description="OpenSearch cluster URL for vector storage and hybrid search.",
        alias="OPENSEARCH_URL",
    )

    # ─────────────────────────────────────────────────────────────────────
    # vLLM (local LLM inference)
    # ─────────────────────────────────────────────────────────────────────

    vllm_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for the vLLM inference server.",
        alias="VLLM_BASE_URL",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Model Configuration
    # ─────────────────────────────────────────────────────────────────────

    model_chat_name: str = Field(
        default="meta-llama/Llama-3.3-70B-Instruct",
        description="HuggingFace model identifier for the chat/generation LLM.",
        alias="MODEL_CHAT_NAME",
    )
    model_chat_path: str = Field(
        default="/models/llama-3.3-70b-instruct",
        description="Local filesystem path to pre-downloaded chat model weights.",
        alias="MODEL_CHAT_PATH",
    )
    model_chat_max_gpu_memory_gb: int = Field(
        default=60,
        description="Maximum GPU memory (GB) allocated for the chat model.",
        alias="MODEL_CHAT_MAX_GPU_MEMORY_GB",
    )
    model_embedding_name: str = Field(
        default="intfloat/multilingual-e5-large-instruct",
        description="HuggingFace model identifier for the multilingual embedding model.",
        alias="MODEL_EMBEDDING_NAME",
    )
    model_embedding_path: str = Field(
        default="/models/multilingual-e5-large-instruct",
        description="Local filesystem path to pre-downloaded embedding model weights.",
        alias="MODEL_EMBEDDING_PATH",
    )
    model_embedding_dimension: int = Field(
        default=1024,
        description="Output dimension of the embedding model vectors.",
        alias="MODEL_EMBEDDING_DIMENSION",
    )
    model_ocr_name: str = Field(
        default="Qwen/Qwen2.5-VL-72B-Instruct",
        description="HuggingFace model identifier for the vision/OCR model.",
        alias="MODEL_OCR_NAME",
    )
    model_ocr_path: str = Field(
        default="/models/qwen2.5-vl-72b-instruct",
        description="Local filesystem path to pre-downloaded OCR model weights.",
        alias="MODEL_OCR_PATH",
    )
    gpu_device_id: int = Field(
        default=0,
        description="CUDA device ID for GPU model loading.",
        alias="GPU_DEVICE_ID",
    )
    model_manager_mode: Literal["gpu", "cpu", "mock"] = Field(
        default="mock",
        description=(
            "Model manager operating mode: "
            "'gpu' for production GPU inference, "
            "'cpu' for CPU-only inference, "
            "'mock' for development/testing with mock responses."
        ),
        alias="MODEL_MANAGER_MODE",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Application
    # ─────────────────────────────────────────────────────────────────────

    secret_key: str = Field(
        default="changeme_secret_key_generate_a_random_value",
        description="Secret key for JWT token signing and session encryption.",
        alias="SECRET_KEY",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="List of allowed CORS origins for the frontend.",
        alias="CORS_ORIGINS",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton Settings instance.

    Uses functools.lru_cache to ensure the settings are only loaded once
    from environment variables / .env file during the application lifecycle.

    Returns:
        Settings: The application configuration instance.
    """
    return Settings()
