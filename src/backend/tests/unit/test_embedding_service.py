"""Unit tests for EmbeddingService orchestrator.

Tests state transitions, retry logic, idempotent indexing,
configuration respect, and re-indexing operations with fully
mocked external dependencies.

References:
    - Requirements: 1.1, 1.6, 1.7, 8.1, 8.4, 8.8, 8.10
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch target for get_settings (imported locally in service methods)
_SETTINGS_PATCH = "alcoabase.config.get_settings"

from alcoabase.literature.embedding.exceptions import (
    EmbeddingDimensionMismatchError,
    EmbeddingGenerationError,
    IndexingUnavailableError,
    ReindexAlreadyActiveError,
)
from alcoabase.literature.embedding.models.embedding_config import (
    EmbeddingConfiguration,
)
from alcoabase.literature.embedding.models.reindex_job import ReindexJob
from alcoabase.literature.embedding.services.chunking_pipeline import ContentChunk
from alcoabase.literature.embedding.services.embedding_service import (
    EmbeddingService,
    _EMBEDDING_BATCH_SIZE,
    _MAX_RETRIES,
    _RETRY_DELAYS_SECONDS,
)
from alcoabase.literature.embedding.services.index_manager import (
    LiteratureIndexManager,
)
from alcoabase.literature.ingestion.models.ingestion import (
    IngestionAuditLog,
    IngestionRecord,
)
from alcoabase.services.inference_client import InferenceClient
from alcoabase.services.model_manager import ModelManager, ModelRole


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create an async session factory that yields the mock session."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx)
    return factory


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    client = AsyncMock(spec=InferenceClient)
    # By default, return 1024-dim vectors
    client.create_embeddings = AsyncMock(
        side_effect=lambda model, inputs: [[0.1] * 1024 for _ in inputs]
    )
    return client


@pytest.fixture
def mock_model_manager():
    """Create a mock ModelManager."""
    manager = AsyncMock(spec=ModelManager)
    manager.ensure_model = AsyncMock(return_value="http://vllm:8000")
    return manager


@pytest.fixture
def mock_index_manager():
    """Create a mock LiteratureIndexManager."""
    manager = AsyncMock(spec=LiteratureIndexManager)
    manager._embedding_dimension = 1024
    manager._index_name = MagicMock(
        side_effect=lambda cid: f"literature-embeddings-{cid}"
    )
    manager.delete_record_chunks = AsyncMock(return_value=0)
    manager.bulk_index_chunks = AsyncMock(return_value=5)
    manager.ensure_index_exists = AsyncMock()
    return manager


@pytest.fixture
def mock_chunking_pipeline():
    """Create a mock ChunkingPipeline (not used directly — service creates its own)."""
    from alcoabase.literature.embedding.services.chunking_pipeline import (
        ChunkingPipeline,
    )

    return MagicMock(spec=ChunkingPipeline)


@pytest.fixture
def sample_record():
    """Create a sample IngestionRecord for testing."""
    record = MagicMock(spec=IngestionRecord)
    record.id = 42
    record.company_id = 1
    record.state = "sanitized"
    record.title = "Test Paper on Machine Learning"
    record.abstract = "This is a test abstract about machine learning methods."
    record.authors = [{"name": "John Doe"}, {"name": "Jane Smith"}]
    record.doi = "10.1234/test.2025"
    record.publication_date = datetime(2025, 1, 15, tzinfo=timezone.utc)
    record.source_id = "pubmed"
    record.external_id = "PM12345"
    record.sanitized_storage_path = None
    record.state_history = []
    return record


@pytest.fixture
def default_config():
    """Create a default EmbeddingConfiguration."""
    config = MagicMock(spec=EmbeddingConfiguration)
    config.chunk_size_tokens = 512
    config.chunk_overlap_tokens = 50
    config.auto_embed_on_ingest = True
    config.embed_abstract_only = False
    config.max_chunks_per_document = 500
    return config


@pytest.fixture
def embedding_service(
    mock_session_factory,
    mock_inference_client,
    mock_model_manager,
    mock_index_manager,
    mock_chunking_pipeline,
):
    """Create an EmbeddingService instance with mocked dependencies."""
    return EmbeddingService(
        session_factory=mock_session_factory,
        inference_client=mock_inference_client,
        model_manager=mock_model_manager,
        index_manager=mock_index_manager,
        chunking_pipeline=mock_chunking_pipeline,
    )


# ===========================================================================
# Helper to set up session returning a record and config
# ===========================================================================


def _setup_session_returns(mock_session, record, config):
    """Configure mock_session.execute to return record then config on successive calls."""
    result_record = MagicMock()
    result_record.scalar_one_or_none = MagicMock(return_value=record)

    result_config = MagicMock()
    result_config.scalar_one_or_none = MagicMock(return_value=config)

    mock_session.execute = AsyncMock(
        side_effect=[result_record, result_config]
    )


# ===========================================================================
# Test: State Transition sanitized → indexed (Req 1.1, 1.6)
# ===========================================================================


class TestStateTransitionToIndexed:
    """Test successful embedding generation transitions record to 'indexed'."""

    @pytest.mark.asyncio
    async def test_successful_embedding_transitions_to_indexed(
        self,
        mock_session_factory,
        mock_inference_client,
        mock_model_manager,
        mock_index_manager,
    ):
        """When embedding succeeds, the record transitions sanitized → indexed."""
        # Set up session with record and config
        record = MagicMock(spec=IngestionRecord)
        record.id = 42
        record.company_id = 1
        record.state = "sanitized"
        record.title = "Test Paper"
        record.abstract = "Some abstract text for embedding."
        record.authors = ["Author A"]
        record.doi = "10.1234/test"
        record.publication_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        record.source_id = "pubmed"
        record.external_id = "PM001"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        # Mock session to return record and config
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            result = await service.generate_and_index_embeddings(
                record_id=42, company_id=1, user_id=1
            )

        assert result["status"] == "indexed"
        assert record.state == "indexed"

    @pytest.mark.asyncio
    async def test_state_history_updated_on_success(
        self,
        mock_session_factory,
        mock_inference_client,
        mock_model_manager,
        mock_index_manager,
    ):
        """State history JSONB is updated with the transition entry."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 10
        record.company_id = 2
        record.state = "sanitized"
        record.title = "Paper"
        record.abstract = "Abstract text."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "crossref"
        record.external_id = "CR001"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_mock, result_config, result_mock, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            await service.generate_and_index_embeddings(
                record_id=10, company_id=2, user_id=5
            )

        # state_history should have an entry for sanitized → indexed
        assert record.state_history is not None
        assert len(record.state_history) == 1
        entry = record.state_history[0]
        assert entry["from_state"] == "sanitized"
        assert entry["to_state"] == "indexed"


# ===========================================================================
# Test: State Transition sanitized → failed (Req 1.7)
# ===========================================================================


class TestStateTransitionToFailed:
    """Test that failures transition record to 'failed' state."""

    @pytest.mark.asyncio
    async def test_vllm_failure_transitions_to_failed(
        self,
        mock_session_factory,
        mock_model_manager,
        mock_index_manager,
    ):
        """When vLLM fails after retries, record transitions to 'failed'."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 99
        record.company_id = 1
        record.state = "sanitized"
        record.title = "Fail Paper"
        record.abstract = "Abstract for failure test."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM999"
        record.sanitized_storage_path = None
        record.state_history = []
        record.failed_from_state = None
        record.error_type = None
        record.error_message = None

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        # The service opens multiple sessions — the first loads record+config,
        # then the failure session loads the record again
        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        # InferenceClient that always fails
        failing_client = AsyncMock(spec=InferenceClient)
        failing_client.create_embeddings = AsyncMock(
            side_effect=RuntimeError("vLLM connection refused")
        )

        service = EmbeddingService(
            session_factory=factory,
            inference_client=failing_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(EmbeddingGenerationError):
                    await service.generate_and_index_embeddings(
                        record_id=99, company_id=1, user_id=1
                    )

        # Record should be transitioned to 'failed'
        assert record.state == "failed"
        assert record.error_type == "embedding_generation_error"

    @pytest.mark.asyncio
    async def test_dimension_mismatch_transitions_to_failed(
        self,
        mock_session_factory,
        mock_model_manager,
        mock_index_manager,
    ):
        """When embedding dimensions are wrong, record transitions to 'failed'."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 50
        record.company_id = 3
        record.state = "sanitized"
        record.title = "Dim Mismatch Paper"
        record.abstract = "Abstract for dimension mismatch test."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM050"
        record.sanitized_storage_path = None
        record.state_history = []
        record.failed_from_state = None
        record.error_type = None
        record.error_message = None

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        # Return vectors with wrong dimension (768 instead of 1024)
        bad_client = AsyncMock(spec=InferenceClient)
        bad_client.create_embeddings = AsyncMock(
            side_effect=lambda model, inputs: [[0.1] * 768 for _ in inputs]
        )

        index_mgr = AsyncMock(spec=LiteratureIndexManager)
        index_mgr._embedding_dimension = 1024
        index_mgr._index_name = MagicMock(
            side_effect=lambda cid: f"literature-embeddings-{cid}"
        )

        service = EmbeddingService(
            session_factory=factory,
            inference_client=bad_client,
            model_manager=mock_model_manager,
            index_manager=index_mgr,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            with pytest.raises(EmbeddingDimensionMismatchError):
                await service.generate_and_index_embeddings(
                    record_id=50, company_id=3, user_id=1
                )

        assert record.state == "failed"
        assert record.error_type == "embedding_dimension_mismatch"


# ===========================================================================
# Test: Retry Logic with Exponential Backoff (Req 1.7)
# ===========================================================================


class TestRetryLogic:
    """Test exponential backoff retry behavior."""

    @pytest.mark.asyncio
    async def test_retries_with_correct_backoff_delays(
        self,
        mock_model_manager,
        mock_index_manager,
    ):
        """The service retries 3 times with 30s, 2min, 10min delays."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 1
        record.company_id = 1
        record.state = "sanitized"
        record.title = "Retry Paper"
        record.abstract = "Abstract for retry test."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM_RETRY"
        record.sanitized_storage_path = None
        record.state_history = []
        record.failed_from_state = None
        record.error_type = None
        record.error_message = None

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        failing_client = AsyncMock(spec=InferenceClient)
        failing_client.create_embeddings = AsyncMock(
            side_effect=RuntimeError("Timeout")
        )

        service = EmbeddingService(
            session_factory=factory,
            inference_client=failing_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            with patch("asyncio.sleep", side_effect=mock_sleep):
                with pytest.raises(EmbeddingGenerationError):
                    await service.generate_and_index_embeddings(
                        record_id=1, company_id=1, user_id=1
                    )

        # Should have retried with backoff delays: 30s, 120s (first two retries)
        # Third attempt fails without sleep after
        assert failing_client.create_embeddings.call_count == _MAX_RETRIES
        assert sleep_calls == [30, 120]  # Only sleeps between retries, not after last

    @pytest.mark.asyncio
    async def test_succeeds_on_second_attempt(
        self,
        mock_model_manager,
        mock_index_manager,
    ):
        """The service succeeds when vLLM recovers on the second attempt."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 7
        record.company_id = 1
        record.state = "sanitized"
        record.title = "Retry Success"
        record.abstract = "Test abstract."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM_R2"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        # Fail first, succeed second
        call_count = {"n": 0}

        async def flaky_embeddings(model, inputs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Temporary failure")
            return [[0.1] * 1024 for _ in inputs]

        flaky_client = AsyncMock(spec=InferenceClient)
        flaky_client.create_embeddings = AsyncMock(side_effect=flaky_embeddings)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=flaky_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await service.generate_and_index_embeddings(
                    record_id=7, company_id=1, user_id=1
                )

        assert result["status"] == "indexed"
        assert record.state == "indexed"


# ===========================================================================
# Test: Idempotent Indexing - Delete Then Insert (Req 8.4)
# ===========================================================================


class TestIdempotentIndexing:
    """Test delete-then-insert idempotent indexing pattern."""

    @pytest.mark.asyncio
    async def test_deletes_existing_before_inserting(
        self,
        mock_model_manager,
        mock_inference_client,
    ):
        """Existing chunks are deleted before new ones are inserted."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 20
        record.company_id = 5
        record.state = "sanitized"
        record.title = "Idempotent Test"
        record.abstract = "Test abstract for idempotent indexing."
        record.authors = ["Author X"]
        record.doi = "10.9999/idem"
        record.publication_date = datetime(2024, 6, 1, tzinfo=timezone.utc)
        record.source_id = "crossref"
        record.external_id = "CR_ID"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        index_mgr = AsyncMock(spec=LiteratureIndexManager)
        index_mgr._embedding_dimension = 1024
        index_mgr._index_name = MagicMock(
            side_effect=lambda cid: f"literature-embeddings-{cid}"
        )
        index_mgr.delete_record_chunks = AsyncMock(return_value=3)
        index_mgr.bulk_index_chunks = AsyncMock(return_value=2)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            index_manager=index_mgr,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            result = await service.generate_and_index_embeddings(
                record_id=20, company_id=5, user_id=1
            )

        # Verify delete was called before bulk_index
        index_mgr.delete_record_chunks.assert_called_with(
            company_id=5, ingestion_record_id=20
        )
        index_mgr.bulk_index_chunks.assert_called_once()
        assert result["status"] == "indexed"

    @pytest.mark.asyncio
    async def test_retries_insert_on_failure(
        self,
        mock_model_manager,
        mock_inference_client,
    ):
        """If insert fails after delete, retries the full delete+insert sequence."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 25
        record.company_id = 5
        record.state = "sanitized"
        record.title = "Insert Retry"
        record.abstract = "Abstract for insert retry."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM_IR"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        # Index manager: first bulk_index fails, second succeeds
        call_count = {"n": 0}

        async def flaky_bulk_index(company_id, chunks):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("OpenSearch transient error")
            return len(chunks)

        index_mgr = AsyncMock(spec=LiteratureIndexManager)
        index_mgr._embedding_dimension = 1024
        index_mgr._index_name = MagicMock(
            side_effect=lambda cid: f"literature-embeddings-{cid}"
        )
        index_mgr.delete_record_chunks = AsyncMock(return_value=0)
        index_mgr.bulk_index_chunks = AsyncMock(side_effect=flaky_bulk_index)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            index_manager=index_mgr,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await service.generate_and_index_embeddings(
                    record_id=25, company_id=5, user_id=1
                )

        # Delete should have been called twice (once per attempt)
        assert index_mgr.delete_record_chunks.call_count == 2
        assert result["status"] == "indexed"


# ===========================================================================
# Test: Configuration Respect (Req 8.8 - auto_embed_on_ingest, embed_abstract_only, max_chunks)
# ===========================================================================


class TestConfigurationRespect:
    """Test that per-company EmbeddingConfiguration is respected."""

    @pytest.mark.asyncio
    async def test_auto_embed_disabled_skips_processing(
        self,
        mock_model_manager,
        mock_inference_client,
        mock_index_manager,
    ):
        """When auto_embed_on_ingest=False, auto-triggered tasks are skipped."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 30
        record.company_id = 10
        record.state = "sanitized"
        record.title = "No Auto"
        record.abstract = "Should be skipped."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM_NA"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = False  # Disabled
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        result = await service.generate_and_index_embeddings(
            record_id=30, company_id=10, user_id=None, triggering_event="auto"
        )

        assert result["status"] == "skipped_auto_disabled"
        mock_inference_client.create_embeddings.assert_not_called()

    @pytest.mark.asyncio
    async def test_manual_trigger_ignores_auto_embed_flag(
        self,
        mock_model_manager,
        mock_inference_client,
        mock_index_manager,
    ):
        """Manual trigger works even when auto_embed_on_ingest=False."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 31
        record.company_id = 10
        record.state = "sanitized"
        record.title = "Manual Trigger"
        record.abstract = "Should process manually."
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM_MT"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = False  # Disabled
        config.embed_abstract_only = False
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            result = await service.generate_and_index_embeddings(
                record_id=31, company_id=10, user_id=1, triggering_event="manual"
            )

        assert result["status"] == "indexed"

    @pytest.mark.asyncio
    async def test_embed_abstract_only_skips_no_abstract(
        self,
        mock_model_manager,
        mock_inference_client,
        mock_index_manager,
    ):
        """When embed_abstract_only=True and no abstract, skips the record."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 32
        record.company_id = 1
        record.state = "sanitized"
        record.title = "No Abstract Paper"
        record.abstract = None  # No abstract
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM_NOA"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = True  # Abstract only
        config.max_chunks_per_document = 500

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=mock_inference_client,
            model_manager=mock_model_manager,
            index_manager=mock_index_manager,
            chunking_pipeline=MagicMock(),
        )

        result = await service.generate_and_index_embeddings(
            record_id=32, company_id=1, user_id=1
        )

        assert result["status"] == "skipped_no_content"
        mock_inference_client.create_embeddings.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_chunks_per_document_truncates(
        self,
        mock_model_manager,
        mock_index_manager,
    ):
        """When chunks exceed max_chunks_per_document, only the first N are indexed."""
        record = MagicMock(spec=IngestionRecord)
        record.id = 33
        record.company_id = 1
        record.state = "sanitized"
        record.title = "Long Paper"
        # Long abstract producing many chunks
        record.abstract = " ".join(["word"] * 2000)
        record.authors = []
        record.doi = None
        record.publication_date = None
        record.source_id = "pubmed"
        record.external_id = "PM_LONG"
        record.sanitized_storage_path = None
        record.state_history = []

        config = MagicMock(spec=EmbeddingConfiguration)
        config.chunk_size_tokens = 512
        config.chunk_overlap_tokens = 50
        config.auto_embed_on_ingest = True
        config.embed_abstract_only = False
        config.max_chunks_per_document = 3  # Low limit

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_record = MagicMock()
        result_record.scalar_one_or_none = MagicMock(return_value=record)
        result_config = MagicMock()
        result_config.scalar_one_or_none = MagicMock(return_value=config)

        session.execute = AsyncMock(
            side_effect=[result_record, result_config, result_record, result_config]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        # InferenceClient that returns proper dimension vectors
        embedding_client = AsyncMock(spec=InferenceClient)
        embedding_client.create_embeddings = AsyncMock(
            side_effect=lambda model, inputs: [[0.1] * 1024 for _ in inputs]
        )

        # Set up index_manager to return count of chunks sent
        index_mgr = AsyncMock(spec=LiteratureIndexManager)
        index_mgr._embedding_dimension = 1024
        index_mgr._index_name = MagicMock(
            side_effect=lambda cid: f"literature-embeddings-{cid}"
        )
        index_mgr.delete_record_chunks = AsyncMock(return_value=0)

        chunks_indexed = []

        async def capture_bulk_index(company_id, chunks):
            chunks_indexed.extend(chunks)
            return len(chunks)

        index_mgr.bulk_index_chunks = AsyncMock(side_effect=capture_bulk_index)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=embedding_client,
            model_manager=mock_model_manager,
            index_manager=index_mgr,
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.return_value = MagicMock(model_embedding_name="test-model")
            result = await service.generate_and_index_embeddings(
                record_id=33, company_id=1, user_id=1
            )

        assert result["status"] == "indexed"
        # Max 3 chunks should have been indexed
        assert len(chunks_indexed) <= 3


# ===========================================================================
# Test: Reindex Initiation, Progress, and Cancellation (Req 8.1, 8.8, 8.10)
# ===========================================================================


class TestReindexOperations:
    """Test re-indexing job lifecycle."""

    @pytest.mark.asyncio
    async def test_initiate_reindex_creates_job(self):
        """Initiating reindex creates a ReindexJob and returns a task_id."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        # No active job
        result_no_job = MagicMock()
        result_no_job.scalar_one_or_none = MagicMock(return_value=None)

        # Count returns 100 records
        result_count = MagicMock()
        result_count.scalar_one = MagicMock(return_value=100)

        session.execute = AsyncMock(
            side_effect=[result_no_job, result_count]
        )

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=AsyncMock(),
            model_manager=AsyncMock(),
            index_manager=AsyncMock(),
            chunking_pipeline=MagicMock(),
        )

        with patch(_SETTINGS_PATCH) as mock_settings:
            settings = MagicMock()
            settings.reindex_batch_size = 50
            settings.literature_embedding_queue = "literature_ingestion"
            mock_settings.return_value = settings

            with patch("alcoabase.tasks.celery_app.celery_app") as mock_celery:
                mock_celery.send_task = MagicMock()
                task_id = await service.initiate_reindex(
                    company_id=1, user_id=1, reason="Model upgrade"
                )

        assert task_id is not None
        assert len(task_id) == 36  # UUID format
        session.add.assert_called()
        mock_celery.send_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_initiate_reindex_rejects_if_already_active(self):
        """If a re-index job is already active, raises ReindexAlreadyActiveError."""
        existing_job = MagicMock(spec=ReindexJob)
        existing_job.task_id = "existing-uuid-1234"
        existing_job.company_id = 1
        existing_job.status = "in_progress"
        existing_job.total_records = 50
        existing_job.records_processed = 20
        existing_job.records_failed = 0

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_active = MagicMock()
        result_active.scalar_one_or_none = MagicMock(return_value=existing_job)

        session.execute = AsyncMock(side_effect=[result_active])

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=AsyncMock(),
            model_manager=AsyncMock(),
            index_manager=AsyncMock(),
            chunking_pipeline=MagicMock(),
        )

        with pytest.raises(ReindexAlreadyActiveError) as exc_info:
            await service.initiate_reindex(
                company_id=1, user_id=1, reason="Test"
            )

        assert exc_info.value.active_task_id == "existing-uuid-1234"

    @pytest.mark.asyncio
    async def test_cancel_reindex_sets_cancelled_status(self):
        """Cancelling a reindex job sets status to 'cancelled'."""
        job = MagicMock(spec=ReindexJob)
        job.task_id = "cancel-test-uuid"
        job.company_id = 1
        job.status = "in_progress"

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_job = MagicMock()
        result_job.scalar_one_or_none = MagicMock(return_value=job)

        session.execute = AsyncMock(side_effect=[result_job])

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=AsyncMock(),
            model_manager=AsyncMock(),
            index_manager=AsyncMock(),
            chunking_pipeline=MagicMock(),
        )

        result = await service.cancel_reindex(
            task_id="cancel-test-uuid", company_id=1, user_id=5
        )

        assert result is True
        assert job.status == "cancelled"
        assert job.cancelled_by == 5

    @pytest.mark.asyncio
    async def test_cancel_already_terminal_returns_false(self):
        """Cancelling a completed/cancelled job returns False."""
        job = MagicMock(spec=ReindexJob)
        job.task_id = "done-uuid"
        job.company_id = 1
        job.status = "completed"

        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_job = MagicMock()
        result_job.scalar_one_or_none = MagicMock(return_value=job)

        session.execute = AsyncMock(side_effect=[result_job])

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=AsyncMock(),
            model_manager=AsyncMock(),
            index_manager=AsyncMock(),
            chunking_pipeline=MagicMock(),
        )

        result = await service.cancel_reindex(
            task_id="done-uuid", company_id=1, user_id=5
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_reindex_progress_returns_status(self):
        """Getting progress returns proper metrics for an active job."""
        job = MagicMock(spec=ReindexJob)
        job.task_id = "progress-uuid"
        job.company_id = 1
        job.status = "in_progress"
        job.total_records = 100
        job.total_batches = 2
        job.current_batch = 1
        job.records_processed = 50
        job.records_failed = 2
        job.started_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        session = AsyncMock()
        session.execute = AsyncMock()

        result_job = MagicMock()
        result_job.scalar_one_or_none = MagicMock(return_value=job)
        session.execute = AsyncMock(side_effect=[result_job])

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=AsyncMock(),
            model_manager=AsyncMock(),
            index_manager=AsyncMock(),
            chunking_pipeline=MagicMock(),
        )

        progress = await service.get_reindex_progress(
            task_id="progress-uuid", company_id=1
        )

        assert progress["status"] == "in_progress"
        assert progress["records_processed"] == 50
        assert progress["records_failed"] == 2
        # 52/100 = 52%
        assert progress["percentage"] == pytest.approx(52.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_get_reindex_progress_not_found(self):
        """Getting progress for unknown task returns not_found."""
        session = AsyncMock()

        result_none = MagicMock()
        result_none.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(side_effect=[result_none])

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=AsyncMock(),
            model_manager=AsyncMock(),
            index_manager=AsyncMock(),
            chunking_pipeline=MagicMock(),
        )

        progress = await service.get_reindex_progress(
            task_id="nonexistent", company_id=1
        )

        assert progress["status"] == "not_found"
        assert progress["percentage"] == 0


# ===========================================================================
# Test: Record Not Found
# ===========================================================================


class TestRecordNotFound:
    """Test behavior when IngestionRecord doesn't exist."""

    @pytest.mark.asyncio
    async def test_returns_not_found_for_missing_record(self):
        """When record is missing, returns not_found status without error."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()

        result_none = MagicMock()
        result_none.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(side_effect=[result_none])

        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=ctx)

        service = EmbeddingService(
            session_factory=factory,
            inference_client=AsyncMock(),
            model_manager=AsyncMock(),
            index_manager=AsyncMock(),
            chunking_pipeline=MagicMock(),
        )

        result = await service.generate_and_index_embeddings(
            record_id=999, company_id=1, user_id=1
        )

        assert result["status"] == "not_found"
        assert result["chunk_count"] == 0
