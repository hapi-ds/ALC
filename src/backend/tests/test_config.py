"""Unit tests for alcoabase.config module."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from alcoabase.config import Settings, get_settings


class TestSettingsDefaults:
    """Verify default values match .env.example expectations."""

    def test_database_url_default(self) -> None:
        settings = Settings()
        assert "postgresql+asyncpg://" in settings.database_url
        assert "alcoabase" in settings.database_url

    def test_minio_defaults(self) -> None:
        settings = Settings()
        assert settings.minio_endpoint == "localhost:9000"
        assert settings.minio_access_key == "alcoabase"
        assert settings.minio_secret_key == "changeme_minio"
        assert settings.minio_bucket == "alcoabase"
        assert settings.minio_use_ssl is False

    def test_redis_url_default(self) -> None:
        settings = Settings()
        assert "redis://" in settings.redis_url
        assert "6379" in settings.redis_url

    def test_opensearch_url_default(self) -> None:
        settings = Settings()
        assert settings.opensearch_url == "http://localhost:9200"

    def test_vllm_base_url_default(self) -> None:
        settings = Settings()
        assert settings.vllm_base_url == "http://localhost:8000"

    def test_model_chat_defaults(self) -> None:
        settings = Settings()
        assert settings.model_chat_name == "meta-llama/Llama-3.3-70B-Instruct"
        assert settings.model_chat_path == "/models/llama-3.3-70b-instruct"
        assert settings.model_chat_max_gpu_memory_gb == 60

    def test_model_embedding_defaults(self) -> None:
        settings = Settings()
        assert settings.model_embedding_name == "intfloat/multilingual-e5-large-instruct"
        assert settings.model_embedding_path == "/models/multilingual-e5-large-instruct"
        assert settings.model_embedding_dimension == 1024

    def test_model_ocr_defaults(self) -> None:
        settings = Settings()
        assert settings.model_ocr_name == "Qwen/Qwen2.5-VL-72B-Instruct"
        assert settings.model_ocr_path == "/models/qwen2.5-vl-72b-instruct"

    def test_gpu_device_id_default(self) -> None:
        settings = Settings()
        assert settings.gpu_device_id == 0

    def test_model_manager_mode_default(self) -> None:
        settings = Settings()
        assert settings.model_manager_mode == "mock"

    def test_secret_key_default(self) -> None:
        settings = Settings()
        assert settings.secret_key == "changeme_secret_key_generate_a_random_value"

    def test_cors_origins_default(self) -> None:
        settings = Settings()
        assert settings.cors_origins == ["http://localhost:3000"]


class TestSettingsEnvironmentOverride:
    """Verify environment variables override defaults."""

    def test_database_url_override(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://u:p@host:5432/db"}):
            settings = Settings()
        assert settings.database_url == "postgresql+asyncpg://u:p@host:5432/db"

    def test_minio_override(self) -> None:
        env = {
            "MINIO_ENDPOINT": "minio.local:9000",
            "MINIO_ACCESS_KEY": "mykey",
            "MINIO_SECRET_KEY": "mysecret",
            "MINIO_BUCKET": "mybucket",
            "MINIO_USE_SSL": "true",
        }
        with patch.dict(os.environ, env):
            settings = Settings()
        assert settings.minio_endpoint == "minio.local:9000"
        assert settings.minio_access_key == "mykey"
        assert settings.minio_secret_key == "mysecret"
        assert settings.minio_bucket == "mybucket"
        assert settings.minio_use_ssl is True

    def test_model_manager_mode_gpu(self) -> None:
        with patch.dict(os.environ, {"MODEL_MANAGER_MODE": "gpu"}):
            settings = Settings()
        assert settings.model_manager_mode == "gpu"

    def test_model_manager_mode_cpu(self) -> None:
        with patch.dict(os.environ, {"MODEL_MANAGER_MODE": "cpu"}):
            settings = Settings()
        assert settings.model_manager_mode == "cpu"

    def test_cors_origins_override(self) -> None:
        with patch.dict(os.environ, {"CORS_ORIGINS": '["http://app:3000","http://admin:3001"]'}):
            settings = Settings()
        assert settings.cors_origins == ["http://app:3000", "http://admin:3001"]


class TestSettingsValidation:
    """Verify type validation rejects invalid values."""

    def test_invalid_model_manager_mode_rejected(self) -> None:
        with patch.dict(os.environ, {"MODEL_MANAGER_MODE": "invalid"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_invalid_gpu_memory_type_rejected(self) -> None:
        with patch.dict(os.environ, {"MODEL_CHAT_MAX_GPU_MEMORY_GB": "not_a_number"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_invalid_embedding_dimension_type_rejected(self) -> None:
        with patch.dict(os.environ, {"MODEL_EMBEDDING_DIMENSION": "abc"}):
            with pytest.raises(ValidationError):
                Settings()


class TestGetSettings:
    """Verify the get_settings singleton function."""

    def test_returns_settings_instance(self) -> None:
        # Clear lru_cache to get a fresh instance
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_returns_cached_instance(self) -> None:
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
