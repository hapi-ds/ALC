"""Integration tests for the full ingestion pipeline flow.

Tests the end-to-end pipeline behavior with mocked external services:
- Full pipeline: submit → Stage 1 → Stage 2 → sanitization → indexed
- Deduplication across submissions
- Retry flow: failed record → retry → success
- State transition history correctness
- Audit log entries at each stage

External dependencies (PostgreSQL, MinIO, Redis, Celery) are mocked.

Requirements: 1.1, 1.6, 2.1, 2.4, 2.6, 10.1, 10.2, 12.1, 12.2, 12.3
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.ingestion.schemas.ingestion import (
    LiteratureSearchResultInput,
)
from alcoabase.literature.ingestion.services.ingestion_service import (
    IngestionPipelineService,
)
from alcoabase.literature.ingestion.services.state_machine import IngestionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AsyncSessionCtx:
    """Async context manager that returns the mock session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _make_session_factory(session):
    """Create a session factory returning the given mock session."""

    def factory():
        return _AsyncSessionCtx(session)

    return factory


def _make_result(
    title: str = "Test Paper on CRISPR",
    doi: str | None = "10.1000/test.123",
    source_id: str = "pubmed",
    external_id: str = "PM12345",
    abstract: str | None = "This paper discusses CRISPR gene therapy.",
) -> LiteratureSearchResultInput:
    """Create a valid LiteratureSearchResultInput for testing."""
    return LiteratureSearchResultInput(
        title=title,
        authors=["Author A", "Author B"],
        doi=doi,
        source_id=source_id,
        external_id=external_id,
        url="http://example.com/paper",
        abstract=abstract,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock async DB session with basic operations."""
    session = AsyncMock()
    _added_objects: list = []
    _next_id = 1

    def _track_add(obj):
        _added_objects.append(obj)

    session.add = MagicMock(side_effect=_track_add)

    async def _mock_flush():
        nonlocal _next_id
        for obj in _added_objects:
            if hasattr(obj, "id") and obj.id is None:
                obj.id = _next_id
                _next_id += 1

    session.flush = AsyncMock(side_effect=_mock_flush)
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)

    # Default execute returns no duplicate
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def mock_storage_manager():
    sm = AsyncMock()
    sm.get_company_usage_bytes = AsyncMock(return_value=0)
    sm.store_file = AsyncMock()
    sm.delete_object = AsyncMock(return_value=True)
    return sm


@pytest.fixture
def mock_unpaywall_adapter():
    adapter = AsyncMock()
    adapter.resolve_doi = AsyncMock(return_value=MagicMock(
        url="http://publisher.example.com/paper.pdf",
        content_type="application/pdf",
        host_type="publisher",
    ))
    return adapter


@pytest.fixture
def mock_sanitization_pipeline():
    return AsyncMock()


@pytest.fixture
def mock_audit_logger():
    return AsyncMock()


@pytest.fixture
def mock_rate_limiter():
    return AsyncMock()


@pytest.fixture
def mock_circuit_breaker():
    return AsyncMock()


@pytest.fixture
def service(
    mock_session,
    mock_storage_manager,
    mock_unpaywall_adapter,
    mock_sanitization_pipeline,
    mock_audit_logger,
    mock_rate_limiter,
    mock_circuit_breaker,
):
    """Build an IngestionPipelineService with all mocked dependencies."""
    return IngestionPipelineService(
        session_factory=_make_session_factory(mock_session),
        storage_manager=mock_storage_manager,
        unpaywall_adapter=mock_unpaywall_adapter,
        sanitization_pipeline=mock_sanitization_pipeline,
        audit_logger=mock_audit_logger,
        rate_limiter=mock_rate_limiter,
        circuit_breaker=mock_circuit_breaker,
    )


# ---------------------------------------------------------------------------
# Test: Full Pipeline Submit → Stage 1 → Stage 2 (mocked)
# Requirements: 1.1, 12.1, 12.2, 12.3
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullPipelineFlow:
    """Test the full ingestion pipeline flow with mocked services."""

    @pytest.mark.asyncio
    async def test_submit_batch_creates_records_and_dispatches_tasks(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Submit batch creates IngestionRecords and dispatches Stage 1 tasks.

        After submit_batch, records are created and Celery send_task is
        called for each new record to dispatch Stage 1 processing.
        """
        results = [_make_result(), _make_result(doi="10.1000/other", external_id="PM99")]

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_stage1_tasks"
        ) as mock_dispatch:
            response = await service.submit_batch(
                results=results, company_id=1, user_id=42
            )

        assert response.batch_id is not None
        assert response.submitted_count == 2
        assert response.duplicate_count == 0
        mock_dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_with_abstract_sets_abstract_indexed_state(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Results with abstracts start in abstract_indexed state."""
        results = [_make_result(abstract="A valid abstract.")]

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_stage1_tasks"
        ):
            response = await service.submit_batch(
                results=results, company_id=1, user_id=42
            )

        # Record was added to session; verify the model received abstract_indexed
        added_calls = mock_session.add.call_args_list
        # Filter for IngestionRecord objects (skip audit log entries)
        record_calls = [
            c for c in added_calls
            if hasattr(c[0][0], "state") and hasattr(c[0][0], "batch_id")
        ]
        assert len(record_calls) >= 1
        record = record_calls[0][0][0]
        assert record.state == IngestionState.ABSTRACT_INDEXED.value

    @pytest.mark.asyncio
    async def test_submit_without_abstract_sets_metadata_only_state(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Results without abstracts start in metadata_only state."""
        results = [_make_result(abstract=None)]

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_stage1_tasks"
        ):
            response = await service.submit_batch(
                results=results, company_id=1, user_id=42
            )

        added_calls = mock_session.add.call_args_list
        record_calls = [
            c for c in added_calls
            if hasattr(c[0][0], "state") and hasattr(c[0][0], "batch_id")
        ]
        assert len(record_calls) >= 1
        record = record_calls[0][0][0]
        assert record.state == IngestionState.METADATA_ONLY.value

    @pytest.mark.asyncio
    async def test_celery_task_dispatch_uses_send_task(
        self, service: IngestionPipelineService
    ) -> None:
        """Stage 1 dispatch calls celery_app.send_task with correct params."""
        with patch(
            "alcoabase.tasks.celery_app.celery_app.send_task"
        ) as mock_send:
            service._dispatch_stage1_tasks(
                record_ids=[10, 20],
                company_id=1,
                user_id=42,
                batch_id="test-batch-id",
            )

        assert mock_send.call_count == 2
        first_call = mock_send.call_args_list[0]
        assert "ingest_stage1_metadata" in first_call[0][0]
        assert first_call[1]["kwargs"]["record_id"] == 10
        assert first_call[1]["kwargs"]["company_id"] == 1


# ---------------------------------------------------------------------------
# Test: Deduplication Across Submissions
# Requirements: 1.6
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeduplicationAcrossSubmissions:
    """Test that duplicate records are not created on re-submission."""

    @pytest.mark.asyncio
    async def test_duplicate_doi_skipped(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Second submission with same DOI is detected as duplicate."""
        # The session.execute is called multiple times:
        # 1. _get_company_quota_mb (returns None for default quota)
        # 2. _check_duplicate_in_session for first result (no dup)
        # 3. _check_duplicate_in_session for second result (dup found)
        mock_result_quota = MagicMock()
        mock_result_quota.scalar_one_or_none.return_value = None  # default quota

        mock_result_no_dup = MagicMock()
        mock_result_no_dup.scalar_one_or_none.return_value = None

        mock_result_dup = MagicMock()
        mock_result_dup.scalar_one_or_none.return_value = 42  # existing ID

        mock_session.execute = AsyncMock(
            side_effect=[mock_result_quota, mock_result_no_dup, mock_result_dup]
        )

        results = [
            _make_result(doi="10.1000/dup", external_id="PM1"),
            _make_result(doi="10.1000/dup", external_id="PM2"),
        ]

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_stage1_tasks"
        ):
            response = await service.submit_batch(
                results=results, company_id=1, user_id=42
            )

        assert response.duplicate_count == 1
        assert len(response.created_ids) == 1

    @pytest.mark.asyncio
    async def test_duplicate_source_external_id_skipped(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Duplicate detected by source_id + external_id combination."""
        mock_result_dup = MagicMock()
        mock_result_dup.scalar_one_or_none.return_value = 99

        mock_session.execute = AsyncMock(return_value=mock_result_dup)

        results = [_make_result(doi=None, source_id="crossref", external_id="CR001")]

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_stage1_tasks"
        ):
            response = await service.submit_batch(
                results=results, company_id=1, user_id=42
            )

        assert response.duplicate_count == 1
        assert len(response.created_ids) == 0


# ---------------------------------------------------------------------------
# Test: Retry Flow
# Requirements: 2.4, 2.6
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRetryFlow:
    """Test retry flow: failed → retry → success."""

    @pytest.mark.asyncio
    async def test_retry_transitions_back_to_failed_from_state(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Retry from FAILED → restores the failed_from_state."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.FAILED.value
        mock_record.failed_from_state = IngestionState.FULL_TEXT_PENDING.value
        mock_record.retry_count = 0
        mock_record.error_type = "timeout"
        mock_record.error_message = "Connection timed out"
        mock_record.state_history = []
        mock_session.get.return_value = mock_record

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_retry_task"
        ):
            result = await service.retry_failed_record(
                record_id=10, company_id=1, user_id=42
            )

        assert result is True
        assert mock_record.state == IngestionState.FULL_TEXT_PENDING.value
        assert mock_record.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_increments_retry_count(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Each retry increments retry_count."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.FAILED.value
        mock_record.failed_from_state = IngestionState.FULL_TEXT_DOWNLOADED.value
        mock_record.retry_count = 1
        mock_record.error_type = "parse_error"
        mock_record.error_message = "Malformed PDF"
        mock_record.state_history = []
        mock_session.get.return_value = mock_record

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_retry_task"
        ):
            result = await service.retry_failed_record(
                record_id=10, company_id=1, user_id=42
            )

        assert result is True
        assert mock_record.retry_count == 2

    @pytest.mark.asyncio
    async def test_retry_dispatches_correct_celery_task(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Retry dispatches the correct Celery task for the target state."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.FAILED.value
        mock_record.failed_from_state = IngestionState.FULL_TEXT_PENDING.value
        mock_record.retry_count = 0
        mock_record.error_type = "timeout"
        mock_record.error_message = "Timeout"
        mock_record.state_history = []
        mock_session.get.return_value = mock_record

        with patch(
            "alcoabase.tasks.celery_app.celery_app.send_task"
        ) as mock_send:
            result = await service.retry_failed_record(
                record_id=10, company_id=1, user_id=42
            )

        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert "stage2_download" in call_args[0][0]


# ---------------------------------------------------------------------------
# Test: State Transition History
# Requirements: 2.6
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStateTransitionHistory:
    """Test that state transitions are correctly recorded in history."""

    @pytest.mark.asyncio
    async def test_transition_appends_to_history(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Each state transition appends an entry to state_history."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.ABSTRACT_INDEXED.value
        mock_record.state_history = [
            {
                "timestamp": "2025-01-01T00:00:00+00:00",
                "from_state": None,
                "to_state": "abstract_indexed",
                "triggering_event": "batch_submission",
            }
        ]
        mock_session.get.return_value = mock_record

        result = await service.transition_state(
            record_id=10,
            target_state=IngestionState.FULL_TEXT_PENDING,
            company_id=1,
            triggering_event="full_text_dispatch",
        )

        assert result is True
        assert len(mock_record.state_history) == 2
        latest = mock_record.state_history[-1]
        assert latest["from_state"] == "abstract_indexed"
        assert latest["to_state"] == "full_text_pending"
        assert latest["triggering_event"] == "full_text_dispatch"
        assert "timestamp" in latest

    @pytest.mark.asyncio
    async def test_failed_transition_records_error_details(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Transition to FAILED records error details on the record."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.FULL_TEXT_PENDING.value
        mock_record.state_history = []
        mock_session.get.return_value = mock_record

        result = await service.transition_state(
            record_id=10,
            target_state=IngestionState.FAILED,
            company_id=1,
            triggering_event="download_timeout",
            error_details={"error_type": "timeout", "error_message": "Timed out"},
        )

        assert result is True
        assert mock_record.state == IngestionState.FAILED.value
        assert mock_record.failed_from_state == IngestionState.FULL_TEXT_PENDING.value
        assert mock_record.error_type == "timeout"
        assert mock_record.error_message == "Timed out"


# ---------------------------------------------------------------------------
# Test: Audit Log Entries
# Requirements: 10.1, 10.2
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAuditLogEntries:
    """Test that audit log entries are created at each stage."""

    @pytest.mark.asyncio
    async def test_batch_submission_creates_audit_entries(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """submit_batch adds IngestionAuditLog entries for created records."""
        results = [_make_result()]

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_stage1_tasks"
        ):
            await service.submit_batch(results=results, company_id=1, user_id=42)

        # session.add is called for both IngestionRecord AND IngestionAuditLog
        add_calls = mock_session.add.call_args_list
        # At least 2 calls: 1 record + 1 audit log
        assert len(add_calls) >= 2

        # Find audit log entries
        from alcoabase.literature.ingestion.models.ingestion import IngestionAuditLog

        audit_entries = [
            c[0][0] for c in add_calls
            if isinstance(c[0][0], IngestionAuditLog)
        ]
        assert len(audit_entries) >= 1
        assert audit_entries[0].event_type == "record_created"
        assert audit_entries[0].company_id == 1

    @pytest.mark.asyncio
    async def test_state_transition_creates_audit_entry(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """transition_state adds an IngestionAuditLog entry."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.METADATA_ONLY.value
        mock_record.state_history = []
        mock_session.get.return_value = mock_record

        await service.transition_state(
            record_id=10,
            target_state=IngestionState.ABSTRACT_INDEXED,
            company_id=1,
            triggering_event="metadata_processed",
        )

        # Check that an audit log entry was added
        from alcoabase.literature.ingestion.models.ingestion import IngestionAuditLog

        add_calls = mock_session.add.call_args_list
        audit_entries = [
            c[0][0] for c in add_calls
            if isinstance(c[0][0], IngestionAuditLog)
        ]
        assert len(audit_entries) == 1
        assert audit_entries[0].event_type == "state_transition"
        assert audit_entries[0].details["from_state"] == "metadata_only"
        assert audit_entries[0].details["to_state"] == "abstract_indexed"

    @pytest.mark.asyncio
    async def test_retry_creates_audit_entry(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """retry_failed_record creates an audit entry with retry details."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.FAILED.value
        mock_record.failed_from_state = IngestionState.FULL_TEXT_PENDING.value
        mock_record.retry_count = 0
        mock_record.error_type = "timeout"
        mock_record.error_message = "Timeout"
        mock_record.state_history = []
        mock_session.get.return_value = mock_record

        with patch(
            "alcoabase.literature.ingestion.services.ingestion_service.IngestionPipelineService._dispatch_retry_task"
        ):
            await service.retry_failed_record(
                record_id=10, company_id=1, user_id=42
            )

        from alcoabase.literature.ingestion.models.ingestion import IngestionAuditLog

        add_calls = mock_session.add.call_args_list
        audit_entries = [
            c[0][0] for c in add_calls
            if isinstance(c[0][0], IngestionAuditLog)
        ]
        assert len(audit_entries) == 1
        assert audit_entries[0].event_type == "retry_initiated"
        assert audit_entries[0].user_id == 42
