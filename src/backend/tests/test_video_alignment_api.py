"""Unit tests for Video Alignment API endpoints.

Tests endpoint validations: missing headers, invalid UUID, document not found,
wrong tenant, wrong document_type. Tests HTTP 409 conflict responses include
existing job_id. Tests HTTP 422 precondition failures with clear error messages.

References:
    - Task 11.4: Write unit tests for video alignment API endpoints
    - Requirements: 10.2, 10.4, 10.8
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.document import Document
from alcoabase.services.alignment_service import AlignmentService
from alcoabase.services.job_tracker import JobConflictError, JobTracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession for database operations."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a test TenantContext."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="admin",
    )


@pytest.fixture
def mock_alignment_service() -> AsyncMock:
    """Create a mock AlignmentService."""
    service = AsyncMock(spec=AlignmentService)
    service.extract_frames = AsyncMock(return_value="job-uuid-1234")
    service.analyze_frames = AsyncMock(return_value="job-uuid-5678")
    service.transcribe_audio = AsyncMock(return_value="job-uuid-9012")
    service.link_sop = AsyncMock(return_value={
        "video_document_uuid": "2025-00001",
        "sop_document_uuid": "2025-00002",
        "sop_version": "1.0",
        "linked_at": "2025-01-15T10:30:00Z",
    })
    service.align = AsyncMock(return_value="job-uuid-3456")
    service.get_report = AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_job_tracker() -> AsyncMock:
    """Create a mock JobTracker."""
    tracker = AsyncMock(spec=JobTracker)
    tracker.get_job = AsyncMock(return_value=None)
    return tracker


@pytest.fixture
def training_video_document() -> Document:
    """Create a sample Training Video document."""
    doc = Document(
        id=10,
        document_uuid="2025-00001",
        title="Training Video - Lab Procedure",
        folder_path="/videos/lab-a",
        document_type="Training Video",
        current_status="Draft",
        created_by=42,
        company_id=1,
    )
    return doc


@pytest.fixture
def wrong_type_document() -> Document:
    """Create a document with wrong type (not Training Video)."""
    doc = Document(
        id=11,
        document_uuid="2025-00002",
        title="Standard Operating Procedure",
        folder_path="/sops/lab-a",
        document_type="SOP",
        current_status="Approved",
        created_by=42,
        company_id=1,
    )
    return doc


@pytest.fixture
def wrong_tenant_document() -> Document:
    """Create a document belonging to a different tenant."""
    doc = Document(
        id=12,
        document_uuid="2025-00003",
        title="Other Company Video",
        folder_path="/videos/other",
        document_type="Training Video",
        current_status="Draft",
        created_by=99,
        company_id=999,  # Different company
    )
    return doc


def _mock_scalar_result(value):
    """Create a mock execute result that returns a scalar."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


@pytest_asyncio.fixture
async def client(
    mock_session: AsyncMock,
    tenant_context: TenantContext,
    mock_alignment_service: AsyncMock,
    mock_job_tracker: AsyncMock,
) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""
    from alcoabase.api.video_alignment import (
        get_alignment_service,
        get_job_tracker,
    )

    async def _override_get_db_session():
        yield mock_session

    async def _override_get_tenant_context():
        return tenant_context

    def _override_get_alignment_service():
        return mock_alignment_service

    def _override_get_job_tracker():
        return mock_job_tracker

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_alignment_service] = _override_get_alignment_service
    app.dependency_overrides[get_job_tracker] = _override_get_job_tracker

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Unit test operation",
            "X-User-Id": "42",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Missing required headers
# ---------------------------------------------------------------------------


class TestMissingHeaders:
    """Tests for missing required headers on video alignment endpoints."""

    @pytest.mark.asyncio
    async def test_missing_x_change_reason_extract_frames(
        self,
        mock_session: AsyncMock,
        tenant_context: TenantContext,
        mock_alignment_service: AsyncMock,
        mock_job_tracker: AsyncMock,
    ):
        """POST extract-frames without X-Change-Reason returns 400 (AuditMiddleware)."""
        from alcoabase.api.video_alignment import (
            get_alignment_service,
            get_job_tracker,
        )

        async def _override_get_db_session():
            yield mock_session

        async def _override_get_tenant_context():
            return tenant_context

        def _override_get_alignment_service():
            return mock_alignment_service

        def _override_get_job_tracker():
            return mock_job_tracker

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
        app.dependency_overrides[get_alignment_service] = _override_get_alignment_service
        app.dependency_overrides[get_job_tracker] = _override_get_job_tracker

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason
            },
        ) as ac:
            response = await ac.post("/api/knowledge/videos/2025-00001/extract-frames")

        app.dependency_overrides.clear()
        # AuditMiddleware rejects mutating requests without X-Change-Reason with 400
        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_x_change_reason_analyze_frames(
        self,
        mock_session: AsyncMock,
        tenant_context: TenantContext,
        mock_alignment_service: AsyncMock,
        mock_job_tracker: AsyncMock,
    ):
        """POST analyze-frames without X-Change-Reason returns 400 (AuditMiddleware)."""
        from alcoabase.api.video_alignment import (
            get_alignment_service,
            get_job_tracker,
        )

        async def _override_get_db_session():
            yield mock_session

        async def _override_get_tenant_context():
            return tenant_context

        def _override_get_alignment_service():
            return mock_alignment_service

        def _override_get_job_tracker():
            return mock_job_tracker

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
        app.dependency_overrides[get_alignment_service] = _override_get_alignment_service
        app.dependency_overrides[get_job_tracker] = _override_get_job_tracker

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
            },
        ) as ac:
            response = await ac.post("/api/knowledge/videos/2025-00001/analyze-frames")

        app.dependency_overrides.clear()
        # AuditMiddleware rejects mutating requests without X-Change-Reason with 400
        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_x_change_reason_link_sop(
        self,
        mock_session: AsyncMock,
        tenant_context: TenantContext,
        mock_alignment_service: AsyncMock,
        mock_job_tracker: AsyncMock,
    ):
        """POST link-sop without X-Change-Reason returns 400 (AuditMiddleware)."""
        from alcoabase.api.video_alignment import (
            get_alignment_service,
            get_job_tracker,
        )

        async def _override_get_db_session():
            yield mock_session

        async def _override_get_tenant_context():
            return tenant_context

        def _override_get_alignment_service():
            return mock_alignment_service

        def _override_get_job_tracker():
            return mock_job_tracker

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
        app.dependency_overrides[get_alignment_service] = _override_get_alignment_service
        app.dependency_overrides[get_job_tracker] = _override_get_job_tracker

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
            },
        ) as ac:
            response = await ac.post(
                "/api/knowledge/videos/2025-00001/link-sop",
                json={"sop_document_uuid": "2025-00002"},
            )

        app.dependency_overrides.clear()
        # AuditMiddleware rejects mutating requests without X-Change-Reason with 400
        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Invalid document_uuid format
# ---------------------------------------------------------------------------


class TestInvalidDocumentUUID:
    """Tests for invalid document_uuid format → 422."""

    @pytest.mark.asyncio
    async def test_invalid_uuid_format_extract_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """Invalid document_uuid format returns 422."""
        # Mock session to return None (no document found after format check)
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.post(
            "/api/knowledge/videos/not-a-valid-uuid/extract-frames"
        )

        assert response.status_code == 422
        assert "Invalid document_uuid format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_uuid_format_analyze_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """Invalid document_uuid format returns 422 for analyze-frames."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.post(
            "/api/knowledge/videos/xyz-bad/analyze-frames"
        )

        assert response.status_code == 422
        assert "Invalid document_uuid format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_uuid_format_report(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """Invalid document_uuid format returns 422 for report endpoint."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.get(
            "/api/knowledge/videos/!!!invalid!!!/report"
        )

        assert response.status_code == 422
        assert "Invalid document_uuid format" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Document not found → 404
# ---------------------------------------------------------------------------


class TestDocumentNotFound:
    """Tests for document not found → 404."""

    @pytest.mark.asyncio
    async def test_document_not_found_extract_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """Non-existent document returns 404."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.post(
            "/api/knowledge/videos/2025-99999/extract-frames"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_document_not_found_analyze_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """Non-existent document returns 404 for analyze-frames."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.post(
            "/api/knowledge/videos/2025-88888/analyze-frames"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_document_not_found_align(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """Non-existent document returns 404 for align."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.post(
            "/api/knowledge/videos/2025-77777/align"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_document_not_found_report(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """Non-existent document returns 404 for report."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.get(
            "/api/knowledge/videos/2025-66666/report"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Wrong tenant (company_id mismatch) → 403
# ---------------------------------------------------------------------------


class TestWrongTenant:
    """Tests for wrong tenant (company_id mismatch) → 403."""

    @pytest.mark.asyncio
    async def test_wrong_tenant_extract_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        wrong_tenant_document: Document,
    ):
        """Document belonging to different company returns 403."""
        mock_session.execute.return_value = _mock_scalar_result(wrong_tenant_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00003/extract-frames"
        )

        assert response.status_code == 403
        assert "does not belong to your company" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_wrong_tenant_analyze_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        wrong_tenant_document: Document,
    ):
        """Document belonging to different company returns 403 for analyze."""
        mock_session.execute.return_value = _mock_scalar_result(wrong_tenant_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00003/analyze-frames"
        )

        assert response.status_code == 403
        assert "does not belong to your company" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_wrong_tenant_report(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        wrong_tenant_document: Document,
    ):
        """Document belonging to different company returns 403 for report."""
        mock_session.execute.return_value = _mock_scalar_result(wrong_tenant_document)

        response = await client.get(
            "/api/knowledge/videos/2025-00003/report"
        )

        assert response.status_code == 403
        assert "does not belong to your company" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Wrong document_type (not "Training Video") → 422
# ---------------------------------------------------------------------------


class TestWrongDocumentType:
    """Tests for wrong document_type → 422."""

    @pytest.mark.asyncio
    async def test_wrong_type_extract_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        wrong_type_document: Document,
    ):
        """Non-Training Video document returns 422."""
        mock_session.execute.return_value = _mock_scalar_result(wrong_type_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00002/extract-frames"
        )

        assert response.status_code == 422
        assert "not a Training Video" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_wrong_type_analyze_frames(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        wrong_type_document: Document,
    ):
        """Non-Training Video document returns 422 for analyze-frames."""
        mock_session.execute.return_value = _mock_scalar_result(wrong_type_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00002/analyze-frames"
        )

        assert response.status_code == 422
        assert "not a Training Video" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_wrong_type_align(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        wrong_type_document: Document,
    ):
        """Non-Training Video document returns 422 for align."""
        mock_session.execute.return_value = _mock_scalar_result(wrong_type_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00002/align"
        )

        assert response.status_code == 422
        assert "not a Training Video" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_wrong_type_transcribe_audio(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        wrong_type_document: Document,
    ):
        """Non-Training Video document returns 422 for transcribe-audio."""
        mock_session.execute.return_value = _mock_scalar_result(wrong_type_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00002/transcribe-audio"
        )

        assert response.status_code == 422
        assert "not a Training Video" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: HTTP 409 conflict responses include existing job_id
# ---------------------------------------------------------------------------


class TestConflictResponses:
    """Tests for HTTP 409 conflict responses including existing job_id."""

    @pytest.mark.asyncio
    async def test_conflict_extract_frames_includes_job_id(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """409 on extract-frames includes existing job_id in detail."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.extract_frames.side_effect = JobConflictError(
            existing_job_id="existing-job-abc-123",
            document_uuid="2025-00001",
            operation="extract_frames",
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/extract-frames"
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "existing-job-abc-123" in detail
        assert "already in progress" in detail

    @pytest.mark.asyncio
    async def test_conflict_analyze_frames_includes_job_id(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """409 on analyze-frames includes existing job_id in detail."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.analyze_frames.side_effect = JobConflictError(
            existing_job_id="existing-job-def-456",
            document_uuid="2025-00001",
            operation="analyze_frames",
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/analyze-frames"
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "existing-job-def-456" in detail

    @pytest.mark.asyncio
    async def test_conflict_transcribe_audio_includes_job_id(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """409 on transcribe-audio includes existing job_id in detail."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.transcribe_audio.side_effect = JobConflictError(
            existing_job_id="existing-job-ghi-789",
            document_uuid="2025-00001",
            operation="transcribe_audio",
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/transcribe-audio"
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "existing-job-ghi-789" in detail

    @pytest.mark.asyncio
    async def test_conflict_align_includes_job_id(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """409 on align includes existing job_id in detail."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.align.side_effect = JobConflictError(
            existing_job_id="existing-job-jkl-012",
            document_uuid="2025-00001",
            operation="align",
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/align"
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "existing-job-jkl-012" in detail
        assert "already in progress" in detail


# ---------------------------------------------------------------------------
# Test: HTTP 422 precondition failures with clear error messages
# ---------------------------------------------------------------------------


class TestPreconditionFailures:
    """Tests for HTTP 422 precondition failures (e.g., frame extraction not completed)."""

    @pytest.mark.asyncio
    async def test_analyze_frames_without_extraction(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Analyze frames before extraction returns 422 with clear message."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.analyze_frames.side_effect = ValueError(
            "Frame extraction must be completed before frame analysis can be performed."
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/analyze-frames"
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Frame extraction must be completed" in detail

    @pytest.mark.asyncio
    async def test_align_without_step_sequence(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Align without completed step sequence returns 422."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.align.side_effect = ValueError(
            "Frame analysis must be completed before alignment can be performed."
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/align"
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Frame analysis must be completed" in detail

    @pytest.mark.asyncio
    async def test_align_without_linked_sops(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Align without linked SOPs returns 422."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.align.side_effect = ValueError(
            "At least one SOP must be linked before alignment can be performed."
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/align"
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "At least one SOP must be linked" in detail

    @pytest.mark.asyncio
    async def test_extract_frames_value_error(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """ValueError from extract_frames returns 422 with message."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.extract_frames.side_effect = ValueError(
            "Video file is corrupt and cannot be processed."
        )

        response = await client.post(
            "/api/knowledge/videos/2025-00001/extract-frames"
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "corrupt" in detail


# ---------------------------------------------------------------------------
# Test: Successful endpoint responses
# ---------------------------------------------------------------------------


class TestSuccessfulResponses:
    """Tests for successful endpoint responses with correct status codes."""

    @pytest.mark.asyncio
    async def test_extract_frames_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Successful extract-frames returns 202 with job_id."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00001/extract-frames"
        )

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-uuid-1234"
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_analyze_frames_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Successful analyze-frames returns 202 with job_id."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00001/analyze-frames"
        )

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-uuid-5678"
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_transcribe_audio_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Successful transcribe-audio returns 202 with job_id."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00001/transcribe-audio"
        )

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-uuid-9012"
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_align_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Successful align returns 202 with job_id."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)

        response = await client.post(
            "/api/knowledge/videos/2025-00001/align"
        )

        assert response.status_code == 202
        data = response.json()
        assert data["job_id"] == "job-uuid-3456"
        assert data["status"] == "processing"

    @pytest.mark.asyncio
    async def test_report_not_found(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        mock_alignment_service: AsyncMock,
        training_video_document: Document,
    ):
        """Report endpoint returns 404 when no report exists."""
        mock_session.execute.return_value = _mock_scalar_result(training_video_document)
        mock_alignment_service.get_report.return_value = None

        response = await client.get(
            "/api/knowledge/videos/2025-00001/report"
        )

        assert response.status_code == 404
        assert "No alignment report" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Job status endpoint
# ---------------------------------------------------------------------------


class TestJobStatusEndpoint:
    """Tests for GET /jobs/{job_id} endpoint."""

    @pytest.mark.asyncio
    async def test_job_not_found(
        self,
        client: AsyncClient,
        mock_job_tracker: AsyncMock,
    ):
        """Non-existent job_id returns 404."""
        mock_job_tracker.get_job.return_value = None

        response = await client.get(
            "/api/knowledge/videos/jobs/nonexistent-job-id"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
