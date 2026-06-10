"""Property-based tests for max chunks truncation.

Property 17: Max chunks truncation
- Generate content producing N chunks where N > configured max_chunks_per_document M
- Assert exactly M chunks are indexed (first M in document order)
- Assert truncation is recorded in audit trail

**Validates: Requirements 9.6**

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

# Feature: Step_9-3_high-dimensional-embedding-hybrid-indexing

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.embedding.services.chunking_pipeline import ContentChunk
from alcoabase.literature.embedding.services.embedding_service import EmbeddingService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# max_chunks_per_document: low value (1–20) to make truncation testable
st_max_chunks = st.integers(min_value=1, max_value=20)

# Number of produced chunks: always greater than max_chunks (excess of 1–50)
st_excess_chunks = st.integers(min_value=1, max_value=50)

# Company and record IDs
st_company_id = st.integers(min_value=1, max_value=10_000)
st_record_id = st.integers(min_value=1, max_value=100_000)

EMBEDDING_DIM = 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunks(n: int) -> list[ContentChunk]:
    """Create N synthetic ContentChunk instances in document order."""
    return [
        ContentChunk(
            text=f"chunk text number {i} with some content for embedding",
            chunk_index=i,
            section_heading=f"Section {i % 5}",
            source_field="abstract" if i == 0 else "body",
        )
        for i in range(n)
    ]


def _make_mock_record(record_id: int, company_id: int) -> MagicMock:
    """Create a mock IngestionRecord with required attributes."""
    record = MagicMock()
    record.id = record_id
    record.company_id = company_id
    record.state = "sanitized"
    record.title = "Test Document Title"
    record.abstract = "This is a test abstract for the document."
    record.authors = [{"name": "Author One"}, {"name": "Author Two"}]
    record.doi = "10.1234/test.2024"
    record.publication_date = None
    record.source_id = "pubmed"
    record.external_id = "PM123456"
    record.sanitized_storage_path = "/path/to/sanitized.json"
    record.state_history = []
    return record


def _make_mock_config(max_chunks: int) -> MagicMock:
    """Create a mock EmbeddingConfiguration with a specific max_chunks_per_document."""
    config = MagicMock()
    config.chunk_size_tokens = 512
    config.chunk_overlap_tokens = 50
    config.auto_embed_on_ingest = True
    config.embed_abstract_only = False
    config.max_chunks_per_document = max_chunks
    return config


def _make_mock_settings() -> MagicMock:
    """Create a mock settings object for EmbeddingService."""
    mock = MagicMock()
    mock.model_embedding_name = "test-embedding-model"
    mock.reindex_batch_size = 50
    mock.literature_embedding_queue = "literature_ingestion"
    return mock


def _make_embedding_service(
    record: MagicMock,
    config: MagicMock,
    chunks: list[ContentChunk],
) -> tuple[EmbeddingService, AsyncMock, list]:
    """Create an EmbeddingService with all dependencies mocked.

    The service's _get_chunks is patched to return the provided chunks.
    The session tracks all objects added (audit log entries).

    Returns:
        Tuple of (service, index_manager_mock, audit_log_entries).
    """
    # Track audit log entries written via session.add()
    audit_log_entries: list = []

    # Mock session that supports async context manager
    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=lambda obj: audit_log_entries.append(obj))
    mock_session.commit = AsyncMock()

    # Mock execute for _load_record and _load_config
    # The method opens multiple sessions:
    #   Session 1: _load_record (execute #1), _load_config (execute #2)
    #   Session 2 (after embeddings): _load_record (execute #3)
    # Each session context returns the same mock_session
    result_record = MagicMock()
    result_record.scalar_one_or_none.return_value = record

    result_config = MagicMock()
    result_config.scalar_one_or_none.return_value = config

    mock_session.execute = AsyncMock(
        side_effect=[result_record, result_config, result_record]
    )

    # Session factory returns the same session as async context manager
    session_factory = MagicMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    session_factory.return_value = mock_session_ctx

    # Inference client that returns correct-dimension embeddings
    inference_client = AsyncMock()

    async def _embed_side_effect(model: str, inputs: list[str]) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in inputs]

    inference_client.create_embeddings = AsyncMock(side_effect=_embed_side_effect)

    # Model manager
    model_manager = AsyncMock()
    model_manager.ensure_model = AsyncMock(return_value="http://vllm:8000")

    # Index manager mock
    index_manager = AsyncMock()
    index_manager._embedding_dimension = EMBEDDING_DIM
    index_manager._index_name = MagicMock(
        side_effect=lambda cid: f"literature-embeddings-{cid}"
    )
    index_manager.delete_record_chunks = AsyncMock(return_value=0)
    index_manager.bulk_index_chunks = AsyncMock(
        side_effect=lambda company_id, chunks: len(chunks)
    )

    # Chunking pipeline (not used directly since we patch _get_chunks)
    chunking_pipeline = MagicMock()

    service = EmbeddingService(
        session_factory=session_factory,
        inference_client=inference_client,
        model_manager=model_manager,
        index_manager=index_manager,
        chunking_pipeline=chunking_pipeline,
    )

    # Patch _get_chunks to return our controlled list of chunks
    service._get_chunks = MagicMock(return_value=chunks)

    return service, index_manager, audit_log_entries


# ---------------------------------------------------------------------------
# Property 17: Max chunks truncation
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(
    max_chunks=st_max_chunks,
    excess=st_excess_chunks,
    company_id=st_company_id,
    record_id=st_record_id,
)
@pytest.mark.asyncio
async def test_max_chunks_truncation_indexes_exactly_m_chunks(
    max_chunks: int,
    excess: int,
    company_id: int,
    record_id: int,
) -> None:
    """When content produces N chunks where N > max_chunks_per_document M,
    exactly M chunks SHALL be indexed (first M in document order).

    **Validates: Requirements 9.6**
    """
    total_chunks = max_chunks + excess  # Always > max_chunks
    all_chunks = _make_chunks(total_chunks)

    record = _make_mock_record(record_id, company_id)
    config = _make_mock_config(max_chunks)

    service, index_manager, audit_log_entries = _make_embedding_service(
        record=record,
        config=config,
        chunks=all_chunks,
    )

    with patch("alcoabase.config.get_settings", return_value=_make_mock_settings()):
        result = await service.generate_and_index_embeddings(
            record_id=record_id,
            company_id=company_id,
            user_id=1,
            triggering_event="auto",
        )

    # Assert status is indexed
    assert result["status"] == "indexed", (
        f"Expected status 'indexed', got '{result['status']}'"
    )

    # Assert exactly M chunks were indexed
    assert result["chunk_count"] == max_chunks, (
        f"Expected {max_chunks} chunks indexed, got {result['chunk_count']}. "
        f"Total produced: {total_chunks}, max_chunks_per_document: {max_chunks}."
    )

    # Verify bulk_index_chunks was called with exactly max_chunks chunks
    index_manager.bulk_index_chunks.assert_called_once()
    _, call_kwargs = index_manager.bulk_index_chunks.call_args
    indexed_chunks = call_kwargs["chunks"]
    assert len(indexed_chunks) == max_chunks, (
        f"Expected {max_chunks} chunks passed to bulk_index_chunks, "
        f"got {len(indexed_chunks)}."
    )

    # Verify the indexed chunks are the FIRST M chunks (document order preserved)
    for i, chunk in enumerate(indexed_chunks):
        assert chunk.chunk_index == i, (
            f"Indexed chunk at position {i} has chunk_index={chunk.chunk_index}, "
            f"expected {i}. First M chunks in document order must be indexed."
        )


@settings(max_examples=100, deadline=None)
@given(
    max_chunks=st_max_chunks,
    excess=st_excess_chunks,
    company_id=st_company_id,
    record_id=st_record_id,
)
@pytest.mark.asyncio
async def test_max_chunks_truncation_audit_trail(
    max_chunks: int,
    excess: int,
    company_id: int,
    record_id: int,
) -> None:
    """When chunks are truncated due to max_chunks_per_document, a
    'chunks_truncated' event SHALL be recorded in the audit trail with
    total_chunks_produced and max_chunks_applied.

    **Validates: Requirements 9.6**
    """
    total_chunks = max_chunks + excess  # Always > max_chunks
    all_chunks = _make_chunks(total_chunks)

    record = _make_mock_record(record_id, company_id)
    config = _make_mock_config(max_chunks)

    service, index_manager, audit_log_entries = _make_embedding_service(
        record=record,
        config=config,
        chunks=all_chunks,
    )

    with patch("alcoabase.config.get_settings", return_value=_make_mock_settings()):
        await service.generate_and_index_embeddings(
            record_id=record_id,
            company_id=company_id,
            user_id=1,
            triggering_event="manual",
        )

    # Find the chunks_truncated audit log entry
    truncation_events = [
        entry
        for entry in audit_log_entries
        if hasattr(entry, "event_type") and entry.event_type == "chunks_truncated"
    ]

    assert len(truncation_events) >= 1, (
        f"Expected at least 1 'chunks_truncated' audit log entry, "
        f"found {len(truncation_events)}. "
        f"All event_types: {[e.event_type for e in audit_log_entries if hasattr(e, 'event_type')]}"
    )

    # Verify the truncation event has correct details
    truncation_event = truncation_events[0]
    details = truncation_event.details

    assert details["total_chunks_produced"] == total_chunks, (
        f"Expected total_chunks_produced={total_chunks}, "
        f"got {details.get('total_chunks_produced')}"
    )
    assert details["max_chunks_applied"] == max_chunks, (
        f"Expected max_chunks_applied={max_chunks}, "
        f"got {details.get('max_chunks_applied')}"
    )

    # Verify the event is scoped to the correct company and record
    assert truncation_event.company_id == company_id, (
        f"Expected company_id={company_id}, got {truncation_event.company_id}"
    )
    assert truncation_event.ingestion_record_id == record_id, (
        f"Expected ingestion_record_id={record_id}, "
        f"got {truncation_event.ingestion_record_id}"
    )
