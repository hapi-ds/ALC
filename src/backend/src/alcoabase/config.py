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
    vllm_embedding_url: str = Field(
        default="http://localhost:8001",
        description="Base URL for the dedicated embedding vLLM instance.",
        alias="VLLM_EMBEDDING_URL",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Model Configuration
    # ─────────────────────────────────────────────────────────────────────

    model_chat_name: str = Field(
        default="Qwen/Qwen3.6-35B-A3B",
        description="HuggingFace model identifier for the chat/generation LLM.",
        alias="MODEL_CHAT_NAME",
    )
    model_chat_path: str = Field(
        default="/models/qwen3.6-35b-a3b",
        description="Local filesystem path to pre-downloaded chat model weights.",
        alias="MODEL_CHAT_PATH",
    )
    model_chat_max_gpu_memory_gb: int = Field(
        default=24,
        description="Maximum GPU memory (GB) allocated for the chat model.",
        alias="MODEL_CHAT_MAX_GPU_MEMORY_GB",
    )
    model_embedding_name: str = Field(
        default="Qwen/Qwen3-Embedding-0.6B",
        description="HuggingFace model identifier for the multilingual embedding model.",
        alias="MODEL_EMBEDDING_NAME",
    )
    model_embedding_path: str = Field(
        default="/models/qwen3-embedding-0.6b",
        description="Local filesystem path to pre-downloaded embedding model weights.",
        alias="MODEL_EMBEDDING_PATH",
    )
    model_embedding_dimension: int = Field(
        default=1024,
        description="Output dimension of the embedding model vectors.",
        alias="MODEL_EMBEDDING_DIMENSION",
    )
    model_ocr_name: str = Field(
        default="google/gemma-4-E4B-it",
        description="HuggingFace model identifier for the vision/OCR model.",
        alias="MODEL_OCR_NAME",
    )
    model_ocr_path: str = Field(
        default="/models/gemma-4-e4b-it",
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
    # Electronic Signatures (PAdES)
    # ─────────────────────────────────────────────────────────────────────

    signature_mode: Literal["pades", "hash"] = Field(
        default="hash",
        description=(
            "Signature mode: 'pades' for production cryptographic PAdES signatures "
            "with pyHanko + x.509 certificates, 'hash' for development/testing "
            "with SHA-256 hash-based tamper detection only."
        ),
        alias="SIGNATURE_MODE",
    )
    signature_key_path: str | None = Field(
        default=None,
        description="Path to PEM-encoded private key file (RSA ≥ 2048-bit or ECDSA P-256/P-384). Required when SIGNATURE_MODE=pades.",
        alias="SIGNATURE_KEY_PATH",
    )
    signature_cert_path: str | None = Field(
        default=None,
        description="Path to PEM-encoded certificate chain file (signer cert + intermediate CAs). Required when SIGNATURE_MODE=pades.",
        alias="SIGNATURE_CERT_PATH",
    )
    signature_key_password: str | None = Field(
        default=None,
        description="Passphrase for encrypted private keys. Leave empty or omit for unencrypted keys.",
        alias="SIGNATURE_KEY_PASSWORD",
    )
    signature_tsa_url: str | None = Field(
        default=None,
        description="RFC 3161 Timestamp Authority URL for long-term validation. Optional.",
        alias="SIGNATURE_TSA_URL",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Multimodal Knowledge Base
    # ─────────────────────────────────────────────────────────────────────

    enable_visual_indexing: bool = Field(
        default=True,
        description="Enable or disable visual content indexing during document processing.",
        alias="ENABLE_VISUAL_INDEXING",
    )
    visual_boost_factor: float = Field(
        default=1.5,
        ge=1.0,
        le=3.0,
        description="Boost factor for visual chunks in process-related RAG queries (1.0-3.0).",
        alias="VISUAL_BOOST_FACTOR",
    )
    max_visual_pages_per_document: int = Field(
        default=100,
        ge=1,
        description="Maximum number of visual pages to process per document.",
        alias="MAX_VISUAL_PAGES_PER_DOCUMENT",
    )
    video_max_file_size_bytes: int = Field(
        default=2_147_483_648,
        ge=1,
        description="Maximum video file size in bytes (default 2 GB).",
        alias="VIDEO_MAX_FILE_SIZE_BYTES",
    )
    video_max_frames: int = Field(
        default=500,
        ge=1,
        description="Maximum number of frames to extract from a video.",
        alias="VIDEO_MAX_FRAMES",
    )
    frame_similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Cosine similarity threshold for consolidating similar frames into steps.",
        alias="FRAME_SIMILARITY_THRESHOLD",
    )
    alignment_match_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Semantic similarity threshold for matching video steps to SOP steps.",
        alias="ALIGNMENT_MATCH_THRESHOLD",
    )
    ffmpeg_path: str = Field(
        default="ffmpeg",
        description="Path to the ffmpeg binary.",
        alias="FFMPEG_PATH",
    )
    ffprobe_path: str = Field(
        default="ffprobe",
        description="Path to the ffprobe binary.",
        alias="FFPROBE_PATH",
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

    # ─────────────────────────────────────────────────────────────────────
    # Literature Search Gateway (Phase 9.1)
    # ─────────────────────────────────────────────────────────────────────

    literature_enabled: bool = Field(
        default=False,
        description=(
            "Enable the literature search gateway. When False, skip initialization "
            "and return HTTP 503 on all literature endpoints."
        ),
        alias="ALC_LITERATURE_ENABLED",
    )
    literature_encryption_key: str | None = Field(
        default=None,
        description=(
            "32-byte AES-256-GCM master key for encrypting API keys at rest. "
            "Required when literature_enabled is True."
        ),
        alias="ALC_LITERATURE_ENCRYPTION_KEY",
    )
    literature_adapter_dir: str | None = Field(
        default=None,
        description=(
            "Filesystem path to scan for adapter modules at startup. "
            "Defaults to the built-in adapters directory if not set."
        ),
        alias="ALC_LITERATURE_ADAPTER_DIR",
    )
    literature_proxy_url: str | None = Field(
        default=None,
        description="HTTP/HTTPS proxy URL for outbound literature API requests.",
        alias="ALC_LITERATURE_PROXY_URL",
    )
    literature_proxy_user: str | None = Field(
        default=None,
        description="Username for proxy authentication.",
        alias="ALC_LITERATURE_PROXY_USER",
    )
    literature_proxy_password: str | None = Field(
        default=None,
        description="Password for proxy authentication.",
        alias="ALC_LITERATURE_PROXY_PASSWORD",
    )
    literature_health_check_interval_seconds: int = Field(
        default=300,
        description="Interval in seconds between periodic adapter health checks.",
        alias="ALC_LITERATURE_HEALTH_CHECK_INTERVAL_SECONDS",
    )
    literature_async_result_ttl_seconds: int = Field(
        default=3600,
        description="TTL in seconds for async search task results stored in Redis.",
        alias="ALC_LITERATURE_ASYNC_RESULT_TTL_SECONDS",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Literature Ingestion Pipeline (Phase 9.2)
    # ─────────────────────────────────────────────────────────────────────

    ingestion_unpaywall_api_url: str = Field(
        default="https://api.unpaywall.org",
        description="Base URL for the Unpaywall API used for DOI resolution.",
        alias="ALC_UNPAYWALL_API_URL",
    )
    ingestion_literature_bucket: str = Field(
        default="alcoabase-literature",
        description="MinIO bucket name for literature file storage.",
        alias="ALC_LITERATURE_BUCKET",
    )
    ingestion_max_file_size_mb: int = Field(
        default=100,
        description="Maximum allowed file size in MB for literature downloads.",
        alias="ALC_LITERATURE_MAX_FILE_SIZE_MB",
    )
    ingestion_retention_days: int = Field(
        default=365,
        description="Default retention period in days for downloaded full-text files.",
        alias="ALC_LITERATURE_RETENTION_DAYS",
    )
    ingestion_storage_quota_mb: int = Field(
        default=10240,
        description="Default storage quota in MB per company for literature files.",
        alias="ALC_LITERATURE_STORAGE_QUOTA_MB",
    )
    ingestion_queue_name: str = Field(
        default="literature_ingestion",
        description="Celery queue name for ingestion pipeline tasks.",
        alias="ALC_LITERATURE_QUEUE_NAME",
    )
    ingestion_cleanup_cron: str = Field(
        default="0 2 * * *",
        description="Cron expression for the retention cleanup periodic task (default: daily at 02:00 UTC).",
        alias="ALC_LITERATURE_CLEANUP_CRON",
    )
    ingestion_user_agent: str = Field(
        default="AlcoaBase/1.0 (Literature Ingestion)",
        description="User-Agent header value for outbound HTTP requests to Unpaywall and publishers.",
        alias="ALC_LITERATURE_USER_AGENT",
    )

    # ─────────────────────────────────────────────────────────────────────
    # ALC Corporate Seed
    # ─────────────────────────────────────────────────────────────────────

    alc_seed_default_password: str = Field(
        default="AlcCorp2024!",
        description="Default password for ALC corporate seed user accounts.",
        alias="ALC_SEED_DEFAULT_PASSWORD",
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
