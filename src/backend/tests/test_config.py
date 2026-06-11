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
        assert settings.model_chat_name == "Qwen/Qwen3.6-35B-A3B"
        assert settings.model_chat_path == "/models/qwen3.6-35b-a3b"
        assert settings.model_chat_max_gpu_memory_gb == 24

    def test_model_embedding_defaults(self) -> None:
        settings = Settings()
        assert settings.model_embedding_name == "Qwen/Qwen3-Embedding-0.6B"
        assert settings.model_embedding_path == "/models/qwen3-embedding-0.6b"
        assert settings.model_embedding_dimension == 1024

    def test_model_ocr_defaults(self) -> None:
        settings = Settings()
        assert settings.model_ocr_name == "google/gemma-4-E4B-it"
        assert settings.model_ocr_path == "/models/gemma-4-e4b-it"

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


class TestPhase93EmbeddingSettings:
    """Verify Phase 9.3 embedding and hybrid indexing defaults and validation."""

    def test_literature_index_shards_default(self) -> None:
        settings = Settings()
        assert settings.literature_index_shards == 1

    def test_literature_index_replicas_default(self) -> None:
        settings = Settings()
        assert settings.literature_index_replicas == 1

    def test_literature_hnsw_ef_construction_default(self) -> None:
        settings = Settings()
        assert settings.literature_hnsw_ef_construction == 256

    def test_literature_hnsw_m_default(self) -> None:
        settings = Settings()
        assert settings.literature_hnsw_m == 16

    def test_literature_rrf_k_default(self) -> None:
        settings = Settings()
        assert settings.literature_rrf_k == 60

    def test_literature_embedding_queue_default(self) -> None:
        settings = Settings()
        assert settings.literature_embedding_queue == "literature_ingestion"

    def test_reindex_batch_size_default(self) -> None:
        settings = Settings()
        assert settings.reindex_batch_size == 50

    def test_literature_index_shards_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_INDEX_SHARDS": "3"}):
            settings = Settings()
        assert settings.literature_index_shards == 3

    def test_literature_index_replicas_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_INDEX_REPLICAS": "2"}):
            settings = Settings()
        assert settings.literature_index_replicas == 2

    def test_literature_hnsw_ef_construction_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_HNSW_EF_CONSTRUCTION": "512"}):
            settings = Settings()
        assert settings.literature_hnsw_ef_construction == 512

    def test_literature_hnsw_m_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_HNSW_M": "32"}):
            settings = Settings()
        assert settings.literature_hnsw_m == 32

    def test_literature_rrf_k_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_RRF_K": "100"}):
            settings = Settings()
        assert settings.literature_rrf_k == 100

    def test_literature_embedding_queue_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_EMBEDDING_QUEUE": "embedding_q"}):
            settings = Settings()
        assert settings.literature_embedding_queue == "embedding_q"

    def test_reindex_batch_size_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_REINDEX_BATCH_SIZE": "100"}):
            settings = Settings()
        assert settings.reindex_batch_size == 100

    def test_literature_index_shards_rejects_zero(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_INDEX_SHARDS": "0"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_literature_hnsw_m_rejects_zero(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_HNSW_M": "0"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_literature_rrf_k_rejects_zero(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_RRF_K": "0"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_reindex_batch_size_rejects_below_minimum(self) -> None:
        with patch.dict(os.environ, {"ALC_REINDEX_BATCH_SIZE": "5"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_reindex_batch_size_rejects_above_maximum(self) -> None:
        with patch.dict(os.environ, {"ALC_REINDEX_BATCH_SIZE": "300"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_literature_embedding_queue_rejects_empty(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_EMBEDDING_QUEUE": ""}):
            with pytest.raises(ValidationError):
                Settings()

    def test_literature_index_shards_rejects_non_integer(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_INDEX_SHARDS": "abc"}):
            with pytest.raises(ValidationError):
                Settings()


class TestRedactOpensearchUrl:
    """Verify OpenSearch URL credential redaction."""

    def test_redacts_user_and_password(self) -> None:
        from alcoabase.config import _redact_opensearch_url

        url = "http://admin:secret@localhost:9200"
        result = _redact_opensearch_url(url)
        assert "admin" not in result
        assert "secret" not in result
        assert "[REDACTED]@localhost:9200" in result

    def test_preserves_url_without_credentials(self) -> None:
        from alcoabase.config import _redact_opensearch_url

        url = "http://localhost:9200"
        result = _redact_opensearch_url(url)
        assert result == url

    def test_preserves_scheme_and_path(self) -> None:
        from alcoabase.config import _redact_opensearch_url

        url = "https://user:pass@opensearch.internal:9200/path"
        result = _redact_opensearch_url(url)
        assert result.startswith("https://")
        assert "9200" in result
        assert "/path" in result
        assert "user" not in result
        assert "pass" not in result


class TestValidateEmbeddingConfig:
    """Verify startup validation for embedding configuration."""

    def test_passes_with_valid_config(self) -> None:
        from alcoabase.config import validate_embedding_config

        settings = Settings()
        # Defaults are valid (opensearch_url and model_embedding_name have defaults)
        validate_embedding_config(settings)

    def test_fails_with_empty_opensearch_url(self) -> None:
        from alcoabase.config import validate_embedding_config

        with patch.dict(os.environ, {"OPENSEARCH_URL": ""}):
            settings = Settings()
        with pytest.raises(SystemExit):
            validate_embedding_config(settings)

    def test_fails_with_empty_model_embedding_name(self) -> None:
        from alcoabase.config import validate_embedding_config

        with patch.dict(os.environ, {"MODEL_EMBEDDING_NAME": ""}):
            settings = Settings()
        with pytest.raises(SystemExit):
            validate_embedding_config(settings)


class TestLogEmbeddingConfig:
    """Verify config logging outputs correct information."""

    def test_logs_all_settings(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from alcoabase.config import log_embedding_config

        settings = Settings()
        with caplog.at_level(logging.INFO, logger="alcoabase.config"):
            log_embedding_config(settings)

        assert "Phase 9.3 Embedding & Hybrid Indexing configuration:" in caplog.text
        assert "OPENSEARCH_URL:" in caplog.text
        assert "MODEL_EMBEDDING_NAME:" in caplog.text
        assert "MODEL_EMBEDDING_DIMENSION:" in caplog.text
        assert "ALC_LITERATURE_INDEX_SHARDS:" in caplog.text
        assert "ALC_LITERATURE_INDEX_REPLICAS:" in caplog.text
        assert "ALC_LITERATURE_HNSW_EF_CONSTRUCTION:" in caplog.text
        assert "ALC_LITERATURE_HNSW_M:" in caplog.text
        assert "ALC_LITERATURE_RRF_K:" in caplog.text
        assert "ALC_LITERATURE_EMBEDDING_QUEUE:" in caplog.text
        assert "ALC_REINDEX_BATCH_SIZE:" in caplog.text

    def test_redacts_credentials_in_log(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from alcoabase.config import log_embedding_config

        with patch.dict(os.environ, {"OPENSEARCH_URL": "http://admin:secret@os:9200"}):
            settings = Settings()
        with caplog.at_level(logging.INFO, logger="alcoabase.config"):
            log_embedding_config(settings)

        assert "secret" not in caplog.text
        assert "admin" not in caplog.text
        assert "[REDACTED]" in caplog.text


class TestPhase94ScreeningSettings:
    """Verify Phase 9.4 literature screening & contradiction detection defaults and validation."""

    def test_literature_screening_queue_default(self) -> None:
        settings = Settings()
        assert settings.literature_screening_queue == "ai_operations"

    def test_literature_contradiction_queue_default(self) -> None:
        settings = Settings()
        assert settings.literature_contradiction_queue == "ai_operations"

    def test_contradiction_similarity_threshold_default(self) -> None:
        settings = Settings()
        assert settings.contradiction_similarity_threshold == 0.6

    def test_contradiction_max_candidates_default(self) -> None:
        settings = Settings()
        assert settings.contradiction_max_candidates == 10

    def test_contradiction_confidence_threshold_default(self) -> None:
        settings = Settings()
        assert settings.contradiction_confidence_threshold == 0.7

    def test_screening_task_timeout_default(self) -> None:
        settings = Settings()
        assert settings.screening_task_timeout == 1800

    def test_screening_max_concurrent_default(self) -> None:
        settings = Settings()
        assert settings.screening_max_concurrent == 5

    def test_literature_screening_queue_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_SCREENING_QUEUE": "custom_queue"}):
            settings = Settings()
        assert settings.literature_screening_queue == "custom_queue"

    def test_literature_contradiction_queue_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_CONTRADICTION_QUEUE": "contra_queue"}):
            settings = Settings()
        assert settings.literature_contradiction_queue == "contra_queue"

    def test_contradiction_similarity_threshold_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_SIMILARITY_THRESHOLD": "0.75"}):
            settings = Settings()
        assert settings.contradiction_similarity_threshold == 0.75

    def test_contradiction_max_candidates_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_MAX_CANDIDATES": "25"}):
            settings = Settings()
        assert settings.contradiction_max_candidates == 25

    def test_contradiction_confidence_threshold_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_CONFIDENCE_THRESHOLD": "0.85"}):
            settings = Settings()
        assert settings.contradiction_confidence_threshold == 0.85

    def test_screening_task_timeout_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_TASK_TIMEOUT": "3600"}):
            settings = Settings()
        assert settings.screening_task_timeout == 3600

    def test_screening_max_concurrent_env_override(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_MAX_CONCURRENT": "10"}):
            settings = Settings()
        assert settings.screening_max_concurrent == 10

    # Validation: reject out-of-range values

    def test_contradiction_similarity_threshold_rejects_above_one(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_SIMILARITY_THRESHOLD": "1.5"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_contradiction_similarity_threshold_rejects_negative(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_SIMILARITY_THRESHOLD": "-0.1"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_contradiction_max_candidates_rejects_zero(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_MAX_CANDIDATES": "0"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_contradiction_max_candidates_rejects_above_fifty(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_MAX_CANDIDATES": "51"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_contradiction_confidence_threshold_rejects_above_one(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_CONFIDENCE_THRESHOLD": "1.1"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_screening_task_timeout_rejects_below_sixty(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_TASK_TIMEOUT": "30"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_screening_task_timeout_rejects_above_seven_thousand_two_hundred(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_TASK_TIMEOUT": "8000"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_screening_max_concurrent_rejects_zero(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_MAX_CONCURRENT": "0"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_screening_max_concurrent_rejects_above_twenty(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_MAX_CONCURRENT": "21"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_literature_screening_queue_rejects_empty(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_SCREENING_QUEUE": ""}):
            with pytest.raises(ValidationError):
                Settings()

    def test_literature_contradiction_queue_rejects_empty(self) -> None:
        with patch.dict(os.environ, {"ALC_LITERATURE_CONTRADICTION_QUEUE": ""}):
            with pytest.raises(ValidationError):
                Settings()

    def test_contradiction_similarity_threshold_rejects_non_numeric(self) -> None:
        with patch.dict(os.environ, {"ALC_CONTRADICTION_SIMILARITY_THRESHOLD": "abc"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_screening_task_timeout_rejects_non_numeric(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_TASK_TIMEOUT": "not_a_number"}):
            with pytest.raises(ValidationError):
                Settings()

    def test_screening_max_concurrent_rejects_non_numeric(self) -> None:
        with patch.dict(os.environ, {"ALC_SCREENING_MAX_CONCURRENT": "xyz"}):
            with pytest.raises(ValidationError):
                Settings()


class TestValidateScreeningConfig:
    """Verify startup validation for screening configuration."""

    def test_passes_with_valid_defaults(self) -> None:
        from alcoabase.config import validate_screening_config

        settings = Settings()
        validate_screening_config(settings)

    def test_passes_with_custom_valid_values(self) -> None:
        from alcoabase.config import validate_screening_config

        env = {
            "ALC_LITERATURE_SCREENING_QUEUE": "my_queue",
            "ALC_CONTRADICTION_SIMILARITY_THRESHOLD": "0.8",
            "ALC_CONTRADICTION_MAX_CANDIDATES": "20",
            "ALC_CONTRADICTION_CONFIDENCE_THRESHOLD": "0.9",
            "ALC_SCREENING_TASK_TIMEOUT": "600",
            "ALC_SCREENING_MAX_CONCURRENT": "10",
        }
        with patch.dict(os.environ, env):
            settings = Settings()
        validate_screening_config(settings)


class TestLogScreeningConfig:
    """Verify screening config logging outputs correct information."""

    def test_logs_all_settings(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from alcoabase.config import log_screening_config

        settings = Settings()
        with caplog.at_level(logging.INFO, logger="alcoabase.config"):
            log_screening_config(settings)

        assert "Phase 9.4 Literature Screening & Contradiction Detection configuration:" in caplog.text
        assert "ALC_LITERATURE_SCREENING_QUEUE:" in caplog.text
        assert "ALC_LITERATURE_CONTRADICTION_QUEUE:" in caplog.text
        assert "ALC_CONTRADICTION_SIMILARITY_THRESHOLD:" in caplog.text
        assert "ALC_CONTRADICTION_MAX_CANDIDATES:" in caplog.text
        assert "ALC_CONTRADICTION_CONFIDENCE_THRESHOLD:" in caplog.text
        assert "ALC_SCREENING_TASK_TIMEOUT:" in caplog.text
        assert "ALC_SCREENING_MAX_CONCURRENT:" in caplog.text
