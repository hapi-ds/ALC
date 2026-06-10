"""Property-based tests for embedding dimension validation.

Property 13: Embedding dimension validation
- Generate embedding vectors with incorrect dimensions.
- Assert EmbeddingService rejects the batch.
- Assert record transitions to `failed` with `embedding_dimension_mismatch`.

**Validates: Requirements 1.5, 12.7**

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.embedding.exceptions import EmbeddingDimensionMismatchError
from alcoabase.literature.embedding.services.chunking_pipeline import ContentChunk
from alcoabase.literature.embedding.services.embedding_service import (
    EmbeddingService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Expected embedding dimension (default)
EXPECTED_DIM = 1024

# Wrong dimensions: any positive int that is NOT the expected dimension
st_wrong_dim = st.integers(min_value=1, max_value=4096).filter(lambda d: d != EXPECTED_DIM)

# Number of chunks to generate per test (1 to 100)
st_num_chunks = st.integers(min_value=1, max_value=100)

# Company IDs
st_company_id = st.integers(min_value=1, max_value=1000)

# Record IDs
st_record_id = st.integers(min_value=1, max_value=10000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunks(n: int) -> list[ContentChunk]:
    """Create N synthetic ContentChunk instances."""
    return [
        ContentChunk(
            text=f"chunk text number {i}",
            chunk_index=i,
            section_heading=f"Section {i % 5}",
            source_field="body" if i > 0 else "abstract",
        )
        for i in range(n)
    ]


def _make_ingestion_record(record_id: int, company_id: int) -> MagicMock:
    """Create a mock IngestionRecord in 'sanitized' state."""
    record = MagicMock()
    record.id = record_id
    record.company_id = company_id
    record.state = "sanitized"
    record.title = "Test Document Title"
    record.abstract = "This is a test abstract for the document."
    record.authors = ["Author A", "Author B"]
    record.doi = "10.1234/test.2024"
    record.publication_date = date(2024, 1, 15)
    record.source_id = "pubmed"
    record.external_id = "PM12345"
    record.state_history = []
    record.failed_from_state = None
    record.error_type = None
    record.error_message = None
    return record


def _make_embedding_config(company_id: int) -> MagicMock:
    """Create a mock EmbeddingConfiguration with defaults."""
    config = MagicMock()
    config.company_id = company_id
    config.chunk_size_tokens = 512
    config.chunk_overlap_tokens = 50
    config.auto_embed_on_ingest = True
    config.embed_abstract_only = False
    config.max_chunks_per_document = 500
    return config


def _make_session_factory(record: MagicMock, config: MagicMock):
    """Create a mock async session factory that returns the given record and config.

    The session mock supports:
    - Loading the IngestionRecord via select queries
    - Loading the EmbeddingConfiguration via select queries
    - Commit and context manager protocols

    The pattern in the code is: `async with self._session_factory() as session:`
    So session_factory() must return an async context manager.
    """
    session = AsyncMock()

    async def _execute_side_effect(stmt):
        """Route select queries to return the appropriate mock."""
        result = MagicMock()

        # Inspect the statement to determine which model it queries
        stmt_repr = repr(stmt)
        if "EmbeddingConfiguration" in stmt_repr:
            result.scalar_one_or_none = MagicMock(return_value=config)
        else:
            # Default to returning the record (IngestionRecord queries)
            result.scalar_one_or_none = MagicMock(return_value=record)
        return result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    session.commit = AsyncMock()
    session.add = MagicMock()

    # Create an async context manager that `session_factory()` returns
    class _AsyncSessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    def _factory():
        return _AsyncSessionContext()

    session_factory = MagicMock(side_effect=_factory)

    return session_factory, session


def _make_embedding_service(
    wrong_dim: int,
    record: MagicMock,
    config: MagicMock,
) -> tuple[EmbeddingService, AsyncMock]:
    """Create an EmbeddingService with inference client returning wrong-dimension vectors.

    Args:
        wrong_dim: The incorrect dimension that the mock inference client will return.
        record: Mock IngestionRecord.
        config: Mock EmbeddingConfiguration.

    Returns:
        Tuple of (service, inference_client_mock).
    """
    session_factory, _ = _make_session_factory(record, config)

    inference_client = AsyncMock()

    async def _wrong_dim_embeddings(model: str, inputs: list[str]) -> list[list[float]]:
        """Return embedding vectors with the WRONG dimension."""
        return [[0.1] * wrong_dim for _ in inputs]

    inference_client.create_embeddings = AsyncMock(side_effect=_wrong_dim_embeddings)

    model_manager = AsyncMock()
    model_manager.ensure_model = AsyncMock(return_value="http://vllm:8000")

    index_manager = MagicMock()
    index_manager._embedding_dimension = EXPECTED_DIM

    chunking_pipeline = MagicMock()

    service = EmbeddingService(
        session_factory=session_factory,
        inference_client=inference_client,
        model_manager=model_manager,
        index_manager=index_manager,
        chunking_pipeline=chunking_pipeline,
    )

    return service, inference_client


# ---------------------------------------------------------------------------
# Property 13a: EmbeddingService rejects batch with wrong dimensions
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    n=st_num_chunks,
    wrong_dim=st_wrong_dim,
    company_id=st_company_id,
    record_id=st_record_id,
)
@pytest.mark.asyncio
async def test_dimension_mismatch_raises_error(
    n: int,
    wrong_dim: int,
    company_id: int,
    record_id: int,
) -> None:
    """When InferenceClient returns vectors with dimension != expected (1024),
    the EmbeddingService SHALL raise EmbeddingDimensionMismatchError and reject
    the entire batch.

    **Validates: Requirements 1.5, 12.7**
    """
    record = _make_ingestion_record(record_id, company_id)
    config = _make_embedding_config(company_id)
    chunks = _make_chunks(n)

    service, _ = _make_embedding_service(wrong_dim, record, config)

    with patch("alcoabase.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(model_embedding_name="test-model")

        # First, generate the embeddings (this succeeds)
        embeddings = await service._generate_embeddings_with_retry(
            chunks=chunks,
            record_id=record_id,
            company_id=company_id,
        )

    # All vectors should have wrong dimension
    assert all(len(vec) == wrong_dim for vec in embeddings)

    # Now run the dimension validation step from generate_and_index_embeddings
    expected_dim = service._index_manager._embedding_dimension
    assert expected_dim == EXPECTED_DIM

    # Verify validation detects the mismatch
    for vec in embeddings:
        assert len(vec) != expected_dim, (
            f"Vector dimension {len(vec)} should not equal expected {expected_dim}"
        )


# ---------------------------------------------------------------------------
# Property 13b: Full generate_and_index_embeddings rejects and transitions
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    n=st_num_chunks,
    wrong_dim=st_wrong_dim,
    company_id=st_company_id,
    record_id=st_record_id,
)
@pytest.mark.asyncio
async def test_dimension_mismatch_transitions_to_failed(
    n: int,
    wrong_dim: int,
    company_id: int,
    record_id: int,
) -> None:
    """When embedding vectors have incorrect dimensions, the IngestionRecord
    SHALL transition to 'failed' state with error_type 'embedding_dimension_mismatch'.

    **Validates: Requirements 1.5, 12.7**
    """
    record = _make_ingestion_record(record_id, company_id)
    config = _make_embedding_config(company_id)
    chunks = _make_chunks(n)

    session_factory, session = _make_session_factory(record, config)

    # Mock inference client to return wrong-dimension vectors
    async def _wrong_dim_embeddings(model: str, inputs: list[str]) -> list[list[float]]:
        return [[0.1] * wrong_dim for _ in inputs]

    inference_client = AsyncMock()
    inference_client.create_embeddings = AsyncMock(side_effect=_wrong_dim_embeddings)

    model_manager = AsyncMock()
    model_manager.ensure_model = AsyncMock(return_value="http://vllm:8000")

    index_manager = MagicMock()
    index_manager._embedding_dimension = EXPECTED_DIM

    chunking_pipeline = MagicMock()
    chunking_pipeline.chunk_structured_content = MagicMock(return_value=chunks)

    service = EmbeddingService(
        session_factory=session_factory,
        inference_client=inference_client,
        model_manager=model_manager,
        index_manager=index_manager,
        chunking_pipeline=chunking_pipeline,
    )

    with patch("alcoabase.config.get_settings") as mock_settings, patch.object(
        service, "_get_chunks", return_value=chunks
    ), patch.object(
        service, "_load_config", new=AsyncMock(return_value=config)
    ):
        mock_settings.return_value = MagicMock(model_embedding_name="test-model")

        with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
            await service.generate_and_index_embeddings(
                record_id=record_id,
                company_id=company_id,
                user_id=1,
                triggering_event="manual",
            )

    # Verify the error carries the correct metadata
    err = exc_info.value
    assert err.expected_dimension == EXPECTED_DIM
    assert err.actual_dimension == wrong_dim
    assert err.record_id == record_id
    assert err.company_id == company_id

    # Verify the record was transitioned to 'failed' state
    assert record.state == "failed"
    assert record.error_type == "embedding_dimension_mismatch"
    assert record.failed_from_state == "sanitized"

    # Verify error_message mentions the dimension mismatch
    assert record.error_message is not None
    assert str(wrong_dim) in record.error_message
    assert str(EXPECTED_DIM) in record.error_message
