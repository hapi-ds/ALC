"""Unit tests for Celery audit export task.

Tests cover:
- Successful export: events fetched, PDF generated, uploaded to MinIO, access logged
- Timeout handling: SoftTimeLimitExceeded caught, status set to "failed"
- Error handling: exception caught, no partial PDF stored, error message returned
- MinIO upload with 72-hour expiry
- Presigned URL generation for download

References:
    - Requirements: 7.5, 7.9, 7.10
    - Task 6.2: Write unit tests for Celery export task
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from alcoabase.tasks.audit_export_tasks import (
    _PDF_EXPIRY_SECONDS,
    _cleanup_partial_pdf,
    _export_audit_pdf_async,
    export_audit_pdf_task,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TASK_MODULE = "alcoabase.tasks.audit_export_tasks"


# ---------------------------------------------------------------------------
# Tests: Task configuration
# ---------------------------------------------------------------------------


class TestTaskConfiguration:
    """Tests for Celery task registration and configuration."""

    def test_task_soft_time_limit_is_300(self) -> None:
        """Task should have 300s soft time limit per requirement 7.5."""
        assert export_audit_pdf_task.soft_time_limit == 300

    def test_task_max_retries_is_zero(self) -> None:
        """Task should not retry on failure."""
        assert export_audit_pdf_task.max_retries == 0

    def test_task_queue_is_default(self) -> None:
        """Task should run on the default queue."""
        assert export_audit_pdf_task.queue == "default"

    def test_task_name(self) -> None:
        """Task should have the expected registered name."""
        assert export_audit_pdf_task.name == (
            "alcoabase.tasks.audit_export_tasks.export_audit_pdf_task"
        )

    def test_pdf_expiry_is_72_hours(self) -> None:
        """PDF expiry constant should be 72 hours in seconds."""
        assert _PDF_EXPIRY_SECONDS == 72 * 60 * 60
        assert _PDF_EXPIRY_SECONDS == 259200


# ---------------------------------------------------------------------------
# Tests: Successful export
# ---------------------------------------------------------------------------


class TestSuccessfulExport:
    """Tests for the happy-path export pipeline."""

    @patch(f"{TASK_MODULE}._export_audit_pdf_async")
    def test_successful_export_returns_completed_status(
        self, mock_async: MagicMock
    ) -> None:
        """Successful export returns status='completed' with download_url."""
        mock_async.return_value = {
            "status": "completed",
            "download_url": "https://minio.local/exports/audit-trail/job-1.pdf",
        }

        result = export_audit_pdf_task(
            job_id="job-1",
            company_id=1,
            filters=None,
            search_query=None,
            requesting_user_id=5,
        )

        assert result["status"] == "completed"
        assert "download_url" in result
        assert "job-1" in result["download_url"]

    @patch(f"{TASK_MODULE}._export_audit_pdf_async")
    def test_successful_export_passes_all_parameters(
        self, mock_async: MagicMock
    ) -> None:
        """Task passes all parameters to the async implementation."""
        mock_async.return_value = {"status": "completed", "download_url": "url"}

        export_audit_pdf_task(
            job_id="job-abc",
            company_id=42,
            filters={"record_type": "documents"},
            search_query="test query",
            requesting_user_id=7,
        )

        mock_async.assert_called_once_with(
            job_id="job-abc",
            company_id=42,
            filters={"record_type": "documents"},
            search_query="test query",
            requesting_user_id=7,
        )


# ---------------------------------------------------------------------------
# Tests: Timeout handling
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Tests for SoftTimeLimitExceeded handling (requirement 7.9)."""

    @patch(f"{TASK_MODULE}._cleanup_partial_pdf")
    @patch(f"{TASK_MODULE}._export_audit_pdf_async")
    def test_timeout_returns_failed_status(
        self, mock_async: MagicMock, mock_cleanup: MagicMock
    ) -> None:
        """SoftTimeLimitExceeded returns status='failed' with timeout message."""
        mock_async.side_effect = SoftTimeLimitExceeded()
        mock_cleanup.return_value = None

        result = export_audit_pdf_task(
            job_id="job-timeout",
            company_id=1,
            filters=None,
            search_query=None,
            requesting_user_id=1,
        )

        assert result["status"] == "failed"
        assert "timed out" in result["error_message"]
        assert "300" in result["error_message"]

    @patch(f"{TASK_MODULE}._cleanup_partial_pdf")
    @patch(f"{TASK_MODULE}._export_audit_pdf_async")
    def test_timeout_triggers_cleanup(
        self, mock_async: MagicMock, mock_cleanup: MagicMock
    ) -> None:
        """SoftTimeLimitExceeded triggers cleanup of partial PDF."""
        mock_async.side_effect = SoftTimeLimitExceeded()
        mock_cleanup.return_value = None

        export_audit_pdf_task(
            job_id="job-timeout-cleanup",
            company_id=1,
            filters=None,
            search_query=None,
            requesting_user_id=1,
        )

        mock_cleanup.assert_called_once_with("job-timeout-cleanup")


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for generic exception handling (requirement 7.9)."""

    @patch(f"{TASK_MODULE}._cleanup_partial_pdf")
    @patch(f"{TASK_MODULE}._export_audit_pdf_async")
    def test_exception_returns_failed_status(
        self, mock_async: MagicMock, mock_cleanup: MagicMock
    ) -> None:
        """Generic exception returns status='failed' with error message."""
        mock_async.side_effect = RuntimeError("Database connection lost")
        mock_cleanup.return_value = None

        result = export_audit_pdf_task(
            job_id="job-error",
            company_id=1,
            filters=None,
            search_query=None,
            requesting_user_id=1,
        )

        assert result["status"] == "failed"
        assert "Database connection lost" in result["error_message"]

    @patch(f"{TASK_MODULE}._cleanup_partial_pdf")
    @patch(f"{TASK_MODULE}._export_audit_pdf_async")
    def test_exception_triggers_cleanup(
        self, mock_async: MagicMock, mock_cleanup: MagicMock
    ) -> None:
        """Generic exception triggers cleanup to prevent partial PDF storage."""
        mock_async.side_effect = ValueError("Invalid filter")
        mock_cleanup.return_value = None

        export_audit_pdf_task(
            job_id="job-cleanup",
            company_id=1,
            filters=None,
            search_query=None,
            requesting_user_id=1,
        )

        mock_cleanup.assert_called_once_with("job-cleanup")

    @patch(f"{TASK_MODULE}._cleanup_partial_pdf")
    @patch(f"{TASK_MODULE}._export_audit_pdf_async")
    def test_error_message_is_string_of_exception(
        self, mock_async: MagicMock, mock_cleanup: MagicMock
    ) -> None:
        """Error message should be the string representation of the exception."""
        mock_async.side_effect = ConnectionError("Redis unavailable")
        mock_cleanup.return_value = None

        result = export_audit_pdf_task(
            job_id="job-conn",
            company_id=1,
            filters=None,
            search_query=None,
            requesting_user_id=1,
        )

        assert result["error_message"] == "Redis unavailable"


# ---------------------------------------------------------------------------
# Tests: MinIO upload with 72-hour expiry
# ---------------------------------------------------------------------------


class TestMinIOUploadAndPresignedURL:
    """Tests for MinIO upload and presigned URL generation (requirement 7.10)."""

    @pytest.fixture
    def mock_s3_client(self) -> AsyncMock:
        """Create a mock S3/MinIO client."""
        client = AsyncMock()
        client.head_bucket = AsyncMock()
        client.put_object = AsyncMock()
        client.generate_presigned_url = AsyncMock(
            return_value="https://minio.local/exports/audit-trail/job-1.pdf?sig=abc"
        )
        client.delete_object = AsyncMock()
        return client

    @pytest.fixture
    def mock_session_factory(self) -> MagicMock:
        """Create a mock async session factory."""
        session = AsyncMock()
        # Mock company query
        company_mock = MagicMock()
        company_mock.display_name = "Test Pharma"
        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = company_mock

        # Mock user query
        user_mock = MagicMock()
        user_mock.full_name = "Test User"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user_mock

        session.execute = AsyncMock(
            side_effect=[company_result, user_result]
        )
        return session

    @pytest.mark.asyncio
    @patch(f"{TASK_MODULE}._get_bucket_name", return_value="test-bucket")
    @patch(f"{TASK_MODULE}._get_storage_client_kwargs")
    @patch(f"{TASK_MODULE}._get_async_session_factory")
    async def test_upload_uses_correct_object_key(
        self,
        mock_session_factory_fn: MagicMock,
        mock_client_kwargs: MagicMock,
        mock_bucket: MagicMock,
        mock_s3_client: AsyncMock,
        mock_session_factory: AsyncMock,
    ) -> None:
        """PDF is uploaded to exports/audit-trail/{job_id}.pdf."""
        from alcoabase.schemas.audit_trail import AuditEvent, AuditTrailPage

        # Setup mocks
        mock_client_kwargs.return_value = {"service_name": "s3"}

        # Mock session factory as async context manager
        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session_factory)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=session_cm)
        mock_session_factory_fn.return_value = factory

        # Mock AuditTrailService
        mock_page = AuditTrailPage(
            events=[
                AuditEvent(
                    transaction_id=1,
                    timestamp="2025-06-15T14:00:00Z",
                    user_id=1,
                    user_display_name="Alice",
                    record_type="documents",
                    record_id=42,
                    operation_type="UPDATE",
                    change_reason="Test",
                    changed_fields=["title"],
                    total_changed_fields=1,
                    company_id=1,
                )
            ],
            next_cursor=None,
            total_count=1,
        )

        # Mock aioboto3 session
        s3_cm = AsyncMock()
        s3_cm.__aenter__ = AsyncMock(return_value=mock_s3_client)
        s3_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "alcoabase.services.audit_trail_service.AuditTrailService"
            ) as mock_ats_cls,
            patch(
                "alcoabase.services.audit_pdf_exporter.AuditPDFExporter"
            ) as mock_pdf_cls,
            patch(
                "alcoabase.services.audit_access_logger.AuditAccessLogger"
            ) as mock_logger_cls,
            patch("aioboto3.Session") as mock_boto_session,
        ):
            mock_ats = AsyncMock()
            mock_ats.list_events = AsyncMock(return_value=mock_page)
            mock_ats_cls.return_value = mock_ats

            mock_pdf = MagicMock()
            mock_pdf.generate_pdf = MagicMock(return_value=b"%PDF-fake")
            mock_pdf_cls.return_value = mock_pdf

            mock_logger = AsyncMock()
            mock_logger.log_access = AsyncMock()
            mock_logger_cls.return_value = mock_logger

            mock_boto_session.return_value.client = MagicMock(
                return_value=s3_cm
            )

            result = await _export_audit_pdf_async(
                job_id="job-upload-test",
                company_id=1,
                filters=None,
                search_query=None,
                requesting_user_id=5,
            )

        # Verify upload was called with correct key
        mock_s3_client.put_object.assert_called_once()
        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["Key"] == "exports/audit-trail/job-upload-test.pdf"
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["ContentType"] == "application/pdf"
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    @patch(f"{TASK_MODULE}._get_bucket_name", return_value="test-bucket")
    @patch(f"{TASK_MODULE}._get_storage_client_kwargs")
    @patch(f"{TASK_MODULE}._get_async_session_factory")
    async def test_presigned_url_uses_72_hour_expiry(
        self,
        mock_session_factory_fn: MagicMock,
        mock_client_kwargs: MagicMock,
        mock_bucket: MagicMock,
        mock_s3_client: AsyncMock,
        mock_session_factory: AsyncMock,
    ) -> None:
        """Presigned URL is generated with 72-hour (259200s) expiry."""
        from alcoabase.schemas.audit_trail import AuditEvent, AuditTrailPage

        mock_client_kwargs.return_value = {"service_name": "s3"}

        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session_factory)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=session_cm)
        mock_session_factory_fn.return_value = factory

        mock_page = AuditTrailPage(
            events=[
                AuditEvent(
                    transaction_id=1,
                    timestamp="2025-06-15T14:00:00Z",
                    user_id=1,
                    user_display_name="Alice",
                    record_type="documents",
                    record_id=42,
                    operation_type="UPDATE",
                    change_reason="Test",
                    changed_fields=["title"],
                    total_changed_fields=1,
                    company_id=1,
                )
            ],
            next_cursor=None,
            total_count=1,
        )

        s3_cm = AsyncMock()
        s3_cm.__aenter__ = AsyncMock(return_value=mock_s3_client)
        s3_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "alcoabase.services.audit_trail_service.AuditTrailService"
            ) as mock_ats_cls,
            patch(
                "alcoabase.services.audit_pdf_exporter.AuditPDFExporter"
            ) as mock_pdf_cls,
            patch(
                "alcoabase.services.audit_access_logger.AuditAccessLogger"
            ) as mock_logger_cls,
            patch("aioboto3.Session") as mock_boto_session,
        ):
            mock_ats = AsyncMock()
            mock_ats.list_events = AsyncMock(return_value=mock_page)
            mock_ats_cls.return_value = mock_ats

            mock_pdf = MagicMock()
            mock_pdf.generate_pdf = MagicMock(return_value=b"%PDF-fake")
            mock_pdf_cls.return_value = mock_pdf

            mock_logger = AsyncMock()
            mock_logger.log_access = AsyncMock()
            mock_logger_cls.return_value = mock_logger

            mock_boto_session.return_value.client = MagicMock(
                return_value=s3_cm
            )

            await _export_audit_pdf_async(
                job_id="job-expiry-test",
                company_id=1,
                filters=None,
                search_query=None,
                requesting_user_id=5,
            )

        # Verify presigned URL was generated with 72-hour expiry
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={
                "Bucket": "test-bucket",
                "Key": "exports/audit-trail/job-expiry-test.pdf",
            },
            ExpiresIn=259200,
        )

    @pytest.mark.asyncio
    @patch(f"{TASK_MODULE}._get_bucket_name", return_value="test-bucket")
    @patch(f"{TASK_MODULE}._get_storage_client_kwargs")
    @patch(f"{TASK_MODULE}._get_async_session_factory")
    async def test_presigned_url_returned_in_result(
        self,
        mock_session_factory_fn: MagicMock,
        mock_client_kwargs: MagicMock,
        mock_bucket: MagicMock,
        mock_s3_client: AsyncMock,
        mock_session_factory: AsyncMock,
    ) -> None:
        """Result download_url is the presigned URL from MinIO."""
        from alcoabase.schemas.audit_trail import AuditEvent, AuditTrailPage

        mock_client_kwargs.return_value = {"service_name": "s3"}

        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session_factory)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=session_cm)
        mock_session_factory_fn.return_value = factory

        mock_page = AuditTrailPage(
            events=[
                AuditEvent(
                    transaction_id=1,
                    timestamp="2025-06-15T14:00:00Z",
                    user_id=1,
                    user_display_name="Alice",
                    record_type="documents",
                    record_id=42,
                    operation_type="UPDATE",
                    change_reason="Test",
                    changed_fields=["title"],
                    total_changed_fields=1,
                    company_id=1,
                )
            ],
            next_cursor=None,
            total_count=1,
        )

        expected_url = "https://minio.local/signed/job-url-test.pdf?token=xyz"
        mock_s3_client.generate_presigned_url = AsyncMock(
            return_value=expected_url
        )

        s3_cm = AsyncMock()
        s3_cm.__aenter__ = AsyncMock(return_value=mock_s3_client)
        s3_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "alcoabase.services.audit_trail_service.AuditTrailService"
            ) as mock_ats_cls,
            patch(
                "alcoabase.services.audit_pdf_exporter.AuditPDFExporter"
            ) as mock_pdf_cls,
            patch(
                "alcoabase.services.audit_access_logger.AuditAccessLogger"
            ) as mock_logger_cls,
            patch("aioboto3.Session") as mock_boto_session,
        ):
            mock_ats = AsyncMock()
            mock_ats.list_events = AsyncMock(return_value=mock_page)
            mock_ats_cls.return_value = mock_ats

            mock_pdf = MagicMock()
            mock_pdf.generate_pdf = MagicMock(return_value=b"%PDF-fake")
            mock_pdf_cls.return_value = mock_pdf

            mock_logger = AsyncMock()
            mock_logger.log_access = AsyncMock()
            mock_logger_cls.return_value = mock_logger

            mock_boto_session.return_value.client = MagicMock(
                return_value=s3_cm
            )

            result = await _export_audit_pdf_async(
                job_id="job-url-test",
                company_id=1,
                filters=None,
                search_query=None,
                requesting_user_id=5,
            )

        assert result["download_url"] == expected_url


# ---------------------------------------------------------------------------
# Tests: Access logging on export
# ---------------------------------------------------------------------------


class TestAccessLogging:
    """Tests for audit access logging during export."""

    @pytest.mark.asyncio
    @patch(f"{TASK_MODULE}._get_bucket_name", return_value="test-bucket")
    @patch(f"{TASK_MODULE}._get_storage_client_kwargs")
    @patch(f"{TASK_MODULE}._get_async_session_factory")
    async def test_export_logs_access_with_event_count(
        self,
        mock_session_factory_fn: MagicMock,
        mock_client_kwargs: MagicMock,
        mock_bucket: MagicMock,
    ) -> None:
        """Successful export logs access with action='export' and event_count."""
        from alcoabase.schemas.audit_trail import AuditEvent, AuditTrailPage

        mock_client_kwargs.return_value = {"service_name": "s3"}

        # Mock session
        session = AsyncMock()
        company_mock = MagicMock()
        company_mock.display_name = "Test Pharma"
        company_result = MagicMock()
        company_result.scalar_one_or_none.return_value = company_mock
        user_mock = MagicMock()
        user_mock.full_name = "Test User"
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user_mock
        session.execute = AsyncMock(
            side_effect=[company_result, user_result]
        )

        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=session_cm)
        mock_session_factory_fn.return_value = factory

        mock_page = AuditTrailPage(
            events=[
                AuditEvent(
                    transaction_id=i,
                    timestamp="2025-06-15T14:00:00Z",
                    user_id=1,
                    user_display_name="Alice",
                    record_type="documents",
                    record_id=i,
                    operation_type="UPDATE",
                    change_reason="Test",
                    changed_fields=["title"],
                    total_changed_fields=1,
                    company_id=1,
                )
                for i in range(3)
            ],
            next_cursor=None,
            total_count=3,
        )

        mock_s3 = AsyncMock()
        mock_s3.head_bucket = AsyncMock()
        mock_s3.put_object = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(return_value="https://url")
        s3_cm = AsyncMock()
        s3_cm.__aenter__ = AsyncMock(return_value=mock_s3)
        s3_cm.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "alcoabase.services.audit_trail_service.AuditTrailService"
            ) as mock_ats_cls,
            patch(
                "alcoabase.services.audit_pdf_exporter.AuditPDFExporter"
            ) as mock_pdf_cls,
            patch(
                "alcoabase.services.audit_access_logger.AuditAccessLogger"
            ) as mock_logger_cls,
            patch("aioboto3.Session") as mock_boto_session,
        ):
            mock_ats = AsyncMock()
            mock_ats.list_events = AsyncMock(return_value=mock_page)
            mock_ats_cls.return_value = mock_ats

            mock_pdf = MagicMock()
            mock_pdf.generate_pdf = MagicMock(return_value=b"%PDF-fake")
            mock_pdf_cls.return_value = mock_pdf

            mock_logger = AsyncMock()
            mock_logger.log_access = AsyncMock()
            mock_logger_cls.return_value = mock_logger

            mock_boto_session.return_value.client = MagicMock(
                return_value=s3_cm
            )

            await _export_audit_pdf_async(
                job_id="job-log-test",
                company_id=1,
                filters={"record_type": "documents"},
                search_query=None,
                requesting_user_id=5,
            )

            # Verify access logger was called
            mock_logger.log_access.assert_called_once()
            call_kwargs = mock_logger.log_access.call_args[1]
            assert call_kwargs["user_id"] == 5
            assert call_kwargs["company_id"] == 1
            assert call_kwargs["action"] == "export"
            assert call_kwargs["event_count"] == 3


# ---------------------------------------------------------------------------
# Tests: Cleanup partial PDF
# ---------------------------------------------------------------------------


class TestCleanupPartialPDF:
    """Tests for _cleanup_partial_pdf helper."""

    @pytest.mark.asyncio
    @patch(f"{TASK_MODULE}._get_bucket_name", return_value="test-bucket")
    @patch(f"{TASK_MODULE}._get_storage_client_kwargs")
    async def test_cleanup_deletes_object(
        self,
        mock_client_kwargs: MagicMock,
        mock_bucket: MagicMock,
    ) -> None:
        """Cleanup deletes the PDF object from MinIO."""
        mock_client_kwargs.return_value = {"service_name": "s3"}

        mock_s3 = AsyncMock()
        mock_s3.delete_object = AsyncMock()
        s3_cm = AsyncMock()
        s3_cm.__aenter__ = AsyncMock(return_value=mock_s3)
        s3_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aioboto3.Session") as mock_boto_session:
            mock_boto_session.return_value.client = MagicMock(
                return_value=s3_cm
            )
            await _cleanup_partial_pdf("job-cleanup-test")

        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="exports/audit-trail/job-cleanup-test.pdf",
        )

    @pytest.mark.asyncio
    @patch(f"{TASK_MODULE}._get_bucket_name", return_value="test-bucket")
    @patch(f"{TASK_MODULE}._get_storage_client_kwargs")
    async def test_cleanup_does_not_raise_on_failure(
        self,
        mock_client_kwargs: MagicMock,
        mock_bucket: MagicMock,
    ) -> None:
        """Cleanup swallows exceptions (best-effort)."""
        mock_client_kwargs.return_value = {"service_name": "s3"}

        mock_s3 = AsyncMock()
        mock_s3.delete_object = AsyncMock(
            side_effect=RuntimeError("Network error")
        )
        s3_cm = AsyncMock()
        s3_cm.__aenter__ = AsyncMock(return_value=mock_s3)
        s3_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aioboto3.Session") as mock_boto_session:
            mock_boto_session.return_value.client = MagicMock(
                return_value=s3_cm
            )
            # Should not raise
            await _cleanup_partial_pdf("job-fail-cleanup")


# ---------------------------------------------------------------------------
# Tests: Zero events returns failed
# ---------------------------------------------------------------------------


class TestZeroEventsExport:
    """Tests for export with no matching events."""

    @pytest.mark.asyncio
    @patch(f"{TASK_MODULE}._get_bucket_name", return_value="test-bucket")
    @patch(f"{TASK_MODULE}._get_storage_client_kwargs")
    @patch(f"{TASK_MODULE}._get_async_session_factory")
    async def test_zero_events_returns_failed(
        self,
        mock_session_factory_fn: MagicMock,
        mock_client_kwargs: MagicMock,
        mock_bucket: MagicMock,
    ) -> None:
        """Export with zero matching events returns failed status."""
        from alcoabase.schemas.audit_trail import AuditTrailPage

        mock_client_kwargs.return_value = {"service_name": "s3"}

        session = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__ = AsyncMock(return_value=session)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        factory = MagicMock(return_value=session_cm)
        mock_session_factory_fn.return_value = factory

        empty_page = AuditTrailPage(
            events=[],
            next_cursor=None,
            total_count=0,
        )

        with (
            patch(
                "alcoabase.services.audit_trail_service.AuditTrailService"
            ) as mock_ats_cls,
            patch(
                "alcoabase.services.audit_pdf_exporter.AuditPDFExporter"
            ) as mock_pdf_cls,
            patch(
                "alcoabase.services.audit_access_logger.AuditAccessLogger"
            ) as mock_logger_cls,
        ):
            mock_ats = AsyncMock()
            mock_ats.list_events = AsyncMock(return_value=empty_page)
            mock_ats_cls.return_value = mock_ats

            mock_pdf = MagicMock()
            mock_pdf_cls.return_value = mock_pdf

            mock_logger = AsyncMock()
            mock_logger_cls.return_value = mock_logger

            result = await _export_audit_pdf_async(
                job_id="job-empty",
                company_id=1,
                filters=None,
                search_query=None,
                requesting_user_id=5,
            )

        assert result["status"] == "failed"
        assert "No events" in result["error_message"]
        # PDF should not have been generated
        mock_pdf.generate_pdf.assert_not_called()
