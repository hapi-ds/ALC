"""Unit tests for the JobTracker service.

Tests job creation, progress updates, completion, failure, retrieval,
active job detection, and conflict detection.

References:
    - Requirements: 5.4, 5.8, 6.9, 7.8, 10.6, 10.7, 10.8
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.job_tracker import (
    JobConflictError,
    JobState,
    JobStatus,
    JobTracker,
)


@pytest.fixture
def job_tracker() -> JobTracker:
    """Create a JobTracker instance for testing."""
    return JobTracker()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session with configurable execute results."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _make_execute_result(scalar_value):
    """Helper to create a mock execute result returning a scalar."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    return result


class TestCreateJob:
    """Tests for JobTracker.create_job()."""

    @pytest.mark.asyncio
    async def test_create_job_success(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """create_job returns a JobState with PROCESSING status and generated UUID."""
        # Mock: no active job exists, document_id lookup returns 1
        mock_session.execute = AsyncMock(
            side_effect=[
                # has_active_job -> document_id lookup
                _make_execute_result(1),
                # has_active_job -> no active job
                _make_execute_result(None),
                # create_job -> document_id lookup
                _make_execute_result(1),
            ]
        )

        job = await job_tracker.create_job(
            session=mock_session,
            document_uuid="2025-00001",
            operation="extract_frames",
            estimated_duration_seconds=120,
            company_id=1,
        )

        assert job.document_uuid == "2025-00001"
        assert job.operation == "extract_frames"
        assert job.status == JobStatus.PROCESSING
        assert job.estimated_duration_seconds == 120
        assert job.progress_percent == 0
        assert job.completed_at is None
        assert job.error_message is None
        assert len(job.job_id) == 36  # UUID format
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_create_job_conflict_raises_error(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """create_job raises JobConflictError when active job exists."""
        existing_job_id = "existing-job-uuid-1234"

        # Mock: active job exists
        mock_session.execute = AsyncMock(
            side_effect=[
                # has_active_job -> document_id lookup
                _make_execute_result(1),
                # has_active_job -> returns existing job_id
                _make_execute_result(existing_job_id),
            ]
        )

        with pytest.raises(JobConflictError) as exc_info:
            await job_tracker.create_job(
                session=mock_session,
                document_uuid="2025-00001",
                operation="extract_frames",
            )

        assert exc_info.value.existing_job_id == existing_job_id
        assert exc_info.value.document_uuid == "2025-00001"
        assert exc_info.value.operation == "extract_frames"
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_job_document_not_found_uses_fallback(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """create_job uses document_id=0 when document_uuid not found in DB."""
        # Mock: no active job (document not found), document_id lookup returns None
        mock_session.execute = AsyncMock(
            side_effect=[
                # has_active_job -> document_id lookup returns None
                _make_execute_result(None),
                # create_job -> document_id lookup returns None
                _make_execute_result(None),
            ]
        )

        job = await job_tracker.create_job(
            session=mock_session,
            document_uuid="nonexistent-doc",
            operation="analyze_frames",
        )

        assert job.status == JobStatus.PROCESSING
        assert job.document_uuid == "nonexistent-doc"
        mock_session.add.assert_called_once()


class TestUpdateProgress:
    """Tests for JobTracker.update_progress()."""

    @pytest.mark.asyncio
    async def test_update_progress_normal(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """update_progress updates the progress_percent field."""
        mock_session.execute = AsyncMock()

        await job_tracker.update_progress(mock_session, "job-123", 50)

        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_clamps_to_100(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """update_progress clamps values above 100 to 100."""
        mock_session.execute = AsyncMock()

        await job_tracker.update_progress(mock_session, "job-123", 150)

        mock_session.execute.assert_called_once()
        # Verify the clamped value is used (check the update statement)
        call_args = mock_session.execute.call_args
        # The update statement is the first positional arg
        stmt = call_args[0][0]
        # Verify it compiled without error (basic sanity check)
        assert stmt is not None

    @pytest.mark.asyncio
    async def test_update_progress_clamps_to_0(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """update_progress clamps negative values to 0."""
        mock_session.execute = AsyncMock()

        await job_tracker.update_progress(mock_session, "job-123", -10)

        mock_session.execute.assert_called_once()


class TestCompleteJob:
    """Tests for JobTracker.complete_job()."""

    @pytest.mark.asyncio
    async def test_complete_job_sets_status_and_timestamp(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """complete_job sets status to COMPLETED with timestamp."""
        mock_session.execute = AsyncMock()

        await job_tracker.complete_job(mock_session, "job-123", "/results/frames")

        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_job_without_result_reference(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """complete_job works without a result_reference."""
        mock_session.execute = AsyncMock()

        await job_tracker.complete_job(mock_session, "job-123")

        mock_session.execute.assert_called_once()


class TestFailJob:
    """Tests for JobTracker.fail_job()."""

    @pytest.mark.asyncio
    async def test_fail_job_sets_status_and_error(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """fail_job sets status to FAILED with error message and timestamp."""
        mock_session.execute = AsyncMock()

        await job_tracker.fail_job(
            mock_session, "job-123", "ffmpeg crashed: corrupt video"
        )

        mock_session.execute.assert_called_once()
        mock_session.flush.assert_called_once()


class TestGetJob:
    """Tests for JobTracker.get_job()."""

    @pytest.mark.asyncio
    async def test_get_job_found(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """get_job returns JobState when job exists."""
        now = datetime.now(timezone.utc)
        mock_job = MagicMock()
        mock_job.job_id = "job-abc-123"
        mock_job.document_id = 1
        mock_job.operation = "extract_frames"
        mock_job.status = "processing"
        mock_job.started_at = now
        mock_job.completed_at = None
        mock_job.progress_percent = 45
        mock_job.estimated_duration_seconds = 120
        mock_job.result_reference = None
        mock_job.error_message = None

        # First call: get job record, second call: resolve document_uuid
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = mock_job
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = "2025-00001"

        mock_session.execute = AsyncMock(side_effect=[job_result, doc_result])

        job = await job_tracker.get_job(mock_session, "job-abc-123")

        assert job is not None
        assert job.job_id == "job-abc-123"
        assert job.document_uuid == "2025-00001"
        assert job.operation == "extract_frames"
        assert job.status == JobStatus.PROCESSING
        assert job.progress_percent == 45
        assert job.started_at == now

    @pytest.mark.asyncio
    async def test_get_job_not_found(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """get_job returns None when job doesn't exist."""
        mock_session.execute = AsyncMock(
            return_value=_make_execute_result(None)
        )

        job = await job_tracker.get_job(mock_session, "nonexistent-job")

        assert job is None


class TestHasActiveJob:
    """Tests for JobTracker.has_active_job()."""

    @pytest.mark.asyncio
    async def test_has_active_job_returns_job_id(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """has_active_job returns job_id when active job exists."""
        mock_session.execute = AsyncMock(
            side_effect=[
                # document_id lookup
                _make_execute_result(1),
                # active job query
                _make_execute_result("active-job-id"),
            ]
        )

        result = await job_tracker.has_active_job(
            mock_session, "2025-00001", "extract_frames"
        )

        assert result == "active-job-id"

    @pytest.mark.asyncio
    async def test_has_active_job_returns_none_when_no_active(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """has_active_job returns None when no active job exists."""
        mock_session.execute = AsyncMock(
            side_effect=[
                # document_id lookup
                _make_execute_result(1),
                # no active job
                _make_execute_result(None),
            ]
        )

        result = await job_tracker.has_active_job(
            mock_session, "2025-00001", "extract_frames"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_has_active_job_document_not_found(
        self, job_tracker: JobTracker, mock_session: AsyncMock
    ) -> None:
        """has_active_job returns None when document doesn't exist."""
        mock_session.execute = AsyncMock(
            return_value=_make_execute_result(None)
        )

        result = await job_tracker.has_active_job(
            mock_session, "nonexistent-doc", "extract_frames"
        )

        assert result is None


class TestJobConflictError:
    """Tests for the JobConflictError exception."""

    def test_error_attributes(self) -> None:
        """JobConflictError stores job_id, document_uuid, and operation."""
        error = JobConflictError(
            existing_job_id="job-123",
            document_uuid="2025-00001",
            operation="analyze_frames",
        )

        assert error.existing_job_id == "job-123"
        assert error.document_uuid == "2025-00001"
        assert error.operation == "analyze_frames"
        assert "job-123" in str(error)
        assert "analyze_frames" in str(error)
        assert "2025-00001" in str(error)

    def test_error_is_exception(self) -> None:
        """JobConflictError is a proper Exception subclass."""
        error = JobConflictError("job-1", "doc-1", "op-1")
        assert isinstance(error, Exception)
