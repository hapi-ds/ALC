"""Unit tests for IngestionPipelineService.

Tests:
    - submit_batch(): batch size validation, duplicate detection, record creation
    - check_duplicate(): DOI-based and source+external_id-based matching
    - transition_state(): valid transitions succeed, invalid rejected, history recorded
    - retry_failed_record(): validates FAILED state, enforces max retries (3)
    - Quota enforcement during submission

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.4
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.ingestion.exceptions import (
    BatchTooLargeError,
    MaxRetriesExceededError,
    StorageQuotaExceededError,
)
from alcoabase.literature.ingestion.schemas.ingestion import (
    LiteratureSearchResultInput,
)
from alcoabase.literature.ingestion.services.ingestion_service import (
    MAX_BATCH_SIZE,
    MAX_RETRIES,
    QUOTA_EXCEEDED_THRESHOLD,
    QUOTA_WARNING_THRESHOLD,
    IngestionPipelineService,
)
from alcoabase.literature.ingestion.services.state_machine import IngestionState


@pytest.fixture
def mock_session():
    """Create a mock async session that supports context manager."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)

    # Default execute returns a result with scalar_one_or_none → None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    return session


class _AsyncSessionCtx:
    """Async context manager that returns the mock session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def mock_session_factory(mock_session):
    """Session factory that yields our mock session via async context manager."""

    def factory():
        return _AsyncSessionCtx(mock_session)

    return factory


@pytest.fixture
def mock_storage_manager() -> AsyncMock:
    sm = AsyncMock()
    sm.get_company_usage_bytes = AsyncMock(return_value=0)
    return sm


@pytest.fixture
def mock_unpaywall_adapter() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_sanitization_pipeline() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_audit_logger() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_rate_limiter() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_circuit_breaker() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_session_factory,
    mock_storage_manager,
    mock_unpaywall_adapter,
    mock_sanitization_pipeline,
    mock_audit_logger,
    mock_rate_limiter,
    mock_circuit_breaker,
) -> IngestionPipelineService:
    return IngestionPipelineService(
        session_factory=mock_session_factory,
        storage_manager=mock_storage_manager,
        unpaywall_adapter=mock_unpaywall_adapter,
        sanitization_pipeline=mock_sanitization_pipeline,
        audit_logger=mock_audit_logger,
        rate_limiter=mock_rate_limiter,
        circuit_breaker=mock_circuit_breaker,
    )


def _make_result(
    title: str = "Test Paper",
    doi: str | None = "10.1000/test",
    source_id: str = "pubmed",
    external_id: str = "PM12345",
) -> LiteratureSearchResultInput:
    return LiteratureSearchResultInput(
        title=title,
        authors=["Author A"],
        doi=doi,
        source_id=source_id,
        external_id=external_id,
        url="http://example.com/paper",
    )


# ─── submit_batch Tests ──────────────────────────────────────────────────────


class TestSubmitBatch:
    """Test batch submission logic."""

    @pytest.mark.asyncio
    async def test_batch_too_large_raises(self, service: IngestionPipelineService) -> None:
        """Batch exceeding MAX_BATCH_SIZE (100) raises BatchTooLargeError."""
        results = [_make_result(external_id=f"PM{i}") for i in range(101)]

        with pytest.raises(BatchTooLargeError) as exc_info:
            await service.submit_batch(results, company_id=1, user_id=1)

        assert exc_info.value.batch_size == 101
        assert exc_info.value.max_batch_size == MAX_BATCH_SIZE

    @pytest.mark.asyncio
    async def test_quota_exceeded_raises(
        self, service: IngestionPipelineService, mock_storage_manager: AsyncMock
    ) -> None:
        """If storage quota is exceeded, submission is rejected."""
        # Make get_company_usage_bytes return a very high value
        mock_storage_manager.get_company_usage_bytes.return_value = (
            10240 * 1024 * 1024  # 10240 MB = 100% of default quota
        )

        results = [_make_result()]

        with pytest.raises(StorageQuotaExceededError):
            await service.submit_batch(results, company_id=1, user_id=1)

    @pytest.mark.asyncio
    async def test_max_batch_size_value(self) -> None:
        """Confirm MAX_BATCH_SIZE is 100."""
        assert MAX_BATCH_SIZE == 100

    @pytest.mark.asyncio
    async def test_max_retries_value(self) -> None:
        """Confirm MAX_RETRIES is 3."""
        assert MAX_RETRIES == 3


# ─── check_duplicate Tests ───────────────────────────────────────────────────


class TestCheckDuplicate:
    """Test deduplication logic."""

    @pytest.mark.asyncio
    async def test_doi_based_matching(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Duplicate is detected by matching company_id + DOI."""
        # Mock execute to return an existing record ID
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 42
        mock_session.execute.return_value = mock_result

        result = await service.check_duplicate(
            company_id=1, doi="10.1000/exists", source_id=None, external_id=None
        )

        assert result == 42

    @pytest.mark.asyncio
    async def test_source_external_id_matching(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Duplicate detected by matching company_id + source_id + external_id."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 77
        mock_session.execute.return_value = mock_result

        result = await service.check_duplicate(
            company_id=1, doi=None, source_id="pubmed", external_id="PM99999"
        )

        assert result == 77

    @pytest.mark.asyncio
    async def test_no_duplicate_returns_none(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """No match returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.check_duplicate(
            company_id=1, doi="10.1000/new", source_id="pubmed", external_id="PM_new"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_no_identifiers_returns_none(
        self, service: IngestionPipelineService
    ) -> None:
        """If no DOI and no source+external_id, returns None (nothing to match)."""
        result = await service.check_duplicate(
            company_id=1, doi=None, source_id=None, external_id=None
        )

        assert result is None


# ─── transition_state Tests ──────────────────────────────────────────────────


class TestTransitionState:
    """Test state transition logic."""

    @pytest.mark.asyncio
    async def test_valid_transition_succeeds(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Valid state transitions return True and persist."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.METADATA_ONLY.value
        mock_record.state_history = []
        mock_session.get.return_value = mock_record

        result = await service.transition_state(
            record_id=10,
            target_state=IngestionState.ABSTRACT_INDEXED,
            company_id=1,
            triggering_event="metadata_processed",
        )

        assert result is True
        assert mock_record.state == IngestionState.ABSTRACT_INDEXED.value

    @pytest.mark.asyncio
    async def test_invalid_transition_rejected(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Invalid state transitions return False."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.METADATA_ONLY.value
        mock_session.get.return_value = mock_record

        result = await service.transition_state(
            record_id=10,
            target_state=IngestionState.INDEXED,
            company_id=1,
            triggering_event="skip_attempt",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_record_not_found_returns_false(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Non-existent record returns False."""
        mock_session.get.return_value = None

        result = await service.transition_state(
            record_id=999,
            target_state=IngestionState.ABSTRACT_INDEXED,
            company_id=1,
            triggering_event="test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_company_mismatch_returns_false(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Wrong company_id returns False."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.METADATA_ONLY.value
        mock_session.get.return_value = mock_record

        result = await service.transition_state(
            record_id=10,
            target_state=IngestionState.ABSTRACT_INDEXED,
            company_id=999,
            triggering_event="test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_transition_records_history(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """State history is appended on successful transition."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.ABSTRACT_INDEXED.value
        mock_record.state_history = [{"from_state": None, "to_state": "abstract_indexed"}]
        mock_session.get.return_value = mock_record

        await service.transition_state(
            record_id=10,
            target_state=IngestionState.FULL_TEXT_PENDING,
            company_id=1,
            triggering_event="full_text_requested",
        )

        assert len(mock_record.state_history) == 2
        latest = mock_record.state_history[-1]
        assert latest["from_state"] == "abstract_indexed"
        assert latest["to_state"] == "full_text_pending"
        assert latest["triggering_event"] == "full_text_requested"


# ─── retry_failed_record Tests ───────────────────────────────────────────────


class TestRetryFailedRecord:
    """Test retry logic from FAILED state."""

    @pytest.mark.asyncio
    async def test_retry_from_failed_state(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Retry from FAILED restores the failed_from_state."""
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
                record_id=10, company_id=1, user_id=1
            )

        assert result is True
        assert mock_record.state == IngestionState.FULL_TEXT_PENDING.value
        assert mock_record.retry_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exceeded_raises(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Retry count >= 3 raises MaxRetriesExceededError."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.FAILED.value
        mock_record.failed_from_state = IngestionState.FULL_TEXT_PENDING.value
        mock_record.retry_count = 3
        mock_record.error_message = "last error"
        mock_session.get.return_value = mock_record

        with pytest.raises(MaxRetriesExceededError) as exc_info:
            await service.retry_failed_record(
                record_id=10, company_id=1, user_id=1
            )

        assert exc_info.value.retry_count == 3
        assert exc_info.value.max_retries == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_not_failed_state_returns_false(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Record not in FAILED state returns False."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.ABSTRACT_INDEXED.value
        mock_session.get.return_value = mock_record

        result = await service.retry_failed_record(
            record_id=10, company_id=1, user_id=1
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_no_failed_from_state_returns_false(
        self, service: IngestionPipelineService, mock_session: AsyncMock
    ) -> None:
        """Record with no failed_from_state cannot be retried."""
        mock_record = MagicMock()
        mock_record.company_id = 1
        mock_record.state = IngestionState.FAILED.value
        mock_record.failed_from_state = None
        mock_record.retry_count = 0
        mock_session.get.return_value = mock_record

        result = await service.retry_failed_record(
            record_id=10, company_id=1, user_id=1
        )

        assert result is False


# ─── Quota Enforcement Tests ─────────────────────────────────────────────────


class TestQuotaEnforcement:
    """Test storage quota thresholds."""

    def test_threshold_values(self) -> None:
        """Verify quota threshold constants."""
        assert QUOTA_WARNING_THRESHOLD == 0.90
        assert QUOTA_EXCEEDED_THRESHOLD == 1.00

    @pytest.mark.asyncio
    async def test_check_quota_no_usage(
        self, service: IngestionPipelineService, mock_storage_manager: AsyncMock
    ) -> None:
        """Zero usage returns no warning and no exceeded."""
        mock_storage_manager.get_company_usage_bytes.return_value = 0

        warning, exceeded = await service.check_quota(company_id=1)

        assert warning is False
        assert exceeded is False

    @pytest.mark.asyncio
    async def test_check_quota_at_warning_threshold(
        self, service: IngestionPipelineService, mock_storage_manager: AsyncMock
    ) -> None:
        """Usage at 90% triggers warning but not exceeded."""
        # Default quota is 10240 MB
        quota_bytes = 10240 * 1024 * 1024
        mock_storage_manager.get_company_usage_bytes.return_value = int(
            quota_bytes * 0.91
        )

        warning, exceeded = await service.check_quota(company_id=1)

        assert warning is True
        assert exceeded is False

    @pytest.mark.asyncio
    async def test_check_quota_exceeded(
        self, service: IngestionPipelineService, mock_storage_manager: AsyncMock
    ) -> None:
        """Usage at 100% triggers both warning and exceeded."""
        quota_bytes = 10240 * 1024 * 1024
        mock_storage_manager.get_company_usage_bytes.return_value = quota_bytes

        warning, exceeded = await service.check_quota(company_id=1)

        assert warning is True
        assert exceeded is True
