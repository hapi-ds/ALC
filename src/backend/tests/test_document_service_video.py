"""Unit tests for DocumentService video upload handling.

Tests video content type validation, file size validation, ffprobe
metadata extraction, and video document creation flow.

References:
    - Task 11.2: Extend video upload handling in document service
    - Requirements 4.1-4.7: Video file upload and storage
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.document_service import (
    DocumentService,
    VIDEO_CONTENT_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage_service() -> AsyncMock:
    """Create a mock StorageService."""
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value="documents/2025-00001/1.0/document")
    storage.download_file = AsyncMock(return_value=b"file content")
    storage.delete_file = AsyncMock()
    return storage


@pytest.fixture
def mock_uuid_service() -> AsyncMock:
    """Create a mock UUIDService."""
    uuid_svc = AsyncMock()
    uuid_svc.generate_document_uuid = AsyncMock(return_value="2025-00001")
    return uuid_svc


@pytest.fixture
def document_service(
    mock_storage_service: AsyncMock, mock_uuid_service: AsyncMock
) -> DocumentService:
    """Create a DocumentService with mocked dependencies."""
    return DocumentService(
        storage_service=mock_storage_service,
        uuid_service=mock_uuid_service,
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession with flush support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def sample_ffprobe_output() -> bytes:
    """Sample ffprobe JSON output for a valid video."""
    data = {
        "streams": [
            {
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "nb_frames": "3000",
                "duration": "120.5",
            }
        ],
        "format": {
            "duration": "120.5",
            "size": "50000000",
        },
    }
    return json.dumps(data).encode()


# ---------------------------------------------------------------------------
# Test: Video Content Type Validation
# ---------------------------------------------------------------------------


class TestVideoContentTypeValidation:
    """Tests for video content type checking."""

    def test_mp4_is_video_content_type(
        self, document_service: DocumentService
    ) -> None:
        """video/mp4 is recognized as a video content type."""
        assert document_service._is_video_content_type("video/mp4") is True

    def test_avi_is_video_content_type(
        self, document_service: DocumentService
    ) -> None:
        """video/x-msvideo (AVI) is recognized as a video content type."""
        assert document_service._is_video_content_type("video/x-msvideo") is True

    def test_quicktime_is_video_content_type(
        self, document_service: DocumentService
    ) -> None:
        """video/quicktime (MOV) is recognized as a video content type."""
        assert document_service._is_video_content_type("video/quicktime") is True

    def test_webm_is_video_content_type(
        self, document_service: DocumentService
    ) -> None:
        """video/webm is recognized as a video content type."""
        assert document_service._is_video_content_type("video/webm") is True

    def test_pdf_is_not_video_content_type(
        self, document_service: DocumentService
    ) -> None:
        """application/pdf is not a video content type."""
        assert document_service._is_video_content_type("application/pdf") is False

    def test_octet_stream_is_not_video_content_type(
        self, document_service: DocumentService
    ) -> None:
        """application/octet-stream is not a video content type."""
        assert (
            document_service._is_video_content_type("application/octet-stream")
            is False
        )


# ---------------------------------------------------------------------------
# Test: Video Upload Validation
# ---------------------------------------------------------------------------


class TestVideoUploadValidation:
    """Tests for _validate_video_upload()."""

    def test_valid_mp4_passes(
        self, document_service: DocumentService
    ) -> None:
        """A valid MP4 file with non-zero size passes validation."""
        result = document_service._validate_video_upload(
            b"x" * 1024, "video/mp4"
        )
        assert result is None

    def test_empty_file_fails(
        self, document_service: DocumentService
    ) -> None:
        """A zero-byte file fails validation."""
        result = document_service._validate_video_upload(b"", "video/mp4")
        assert result is not None
        assert "greater than 0 bytes" in result

    def test_unsupported_content_type_fails(
        self, document_service: DocumentService
    ) -> None:
        """An unsupported content type fails validation."""
        result = document_service._validate_video_upload(
            b"x" * 1024, "application/pdf"
        )
        assert result is not None
        assert "Unsupported video content type" in result

    @patch("alcoabase.services.document_service.get_settings")
    def test_oversized_file_fails(
        self,
        mock_get_settings: MagicMock,
        document_service: DocumentService,
    ) -> None:
        """A file exceeding max size fails validation."""
        settings = MagicMock()
        settings.video_max_file_size_bytes = 1000
        mock_get_settings.return_value = settings

        result = document_service._validate_video_upload(
            b"x" * 1001, "video/mp4"
        )
        assert result is not None
        assert "exceeds maximum" in result

    @patch("alcoabase.services.document_service.get_settings")
    def test_file_at_max_size_passes(
        self,
        mock_get_settings: MagicMock,
        document_service: DocumentService,
    ) -> None:
        """A file exactly at max size passes validation."""
        settings = MagicMock()
        settings.video_max_file_size_bytes = 1000
        mock_get_settings.return_value = settings

        result = document_service._validate_video_upload(
            b"x" * 1000, "video/mp4"
        )
        assert result is None


# ---------------------------------------------------------------------------
# Test: ffprobe Metadata Extraction
# ---------------------------------------------------------------------------


class TestExtractVideoMetadata:
    """Tests for _extract_video_metadata()."""

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_successful_extraction(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
        sample_ffprobe_output: bytes,
    ) -> None:
        """Successful ffprobe run returns parsed metadata."""
        process = AsyncMock()
        process.communicate = AsyncMock(
            return_value=(sample_ffprobe_output, b"")
        )
        process.returncode = 0
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        result = await document_service._extract_video_metadata(b"fake video")

        assert result["duration_seconds"] == 120.5
        assert result["resolution_width"] == 1920
        assert result["resolution_height"] == 1080
        assert result["frame_count"] == 3000
        assert result["codec"] == "h264"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_ffprobe_timeout_returns_nulls(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
    ) -> None:
        """ffprobe timeout returns null metadata fields."""
        process = AsyncMock()
        process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        process.returncode = None
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        result = await document_service._extract_video_metadata(b"fake video")

        assert result["duration_seconds"] is None
        assert result["resolution_width"] is None
        assert result["resolution_height"] is None
        assert result["frame_count"] is None
        assert result["codec"] is None

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_ffprobe_nonzero_exit_returns_nulls(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
    ) -> None:
        """ffprobe non-zero exit code returns null metadata fields."""
        process = AsyncMock()
        process.communicate = AsyncMock(
            return_value=(b"", b"Error: invalid data")
        )
        process.returncode = 1
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        result = await document_service._extract_video_metadata(b"fake video")

        assert result["duration_seconds"] is None
        assert result["resolution_width"] is None
        assert result["resolution_height"] is None
        assert result["frame_count"] is None
        assert result["codec"] is None

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_ffprobe_no_streams_returns_nulls(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
    ) -> None:
        """ffprobe output with no video streams returns null metadata."""
        output = json.dumps({"streams": [], "format": {}}).encode()
        process = AsyncMock()
        process.communicate = AsyncMock(return_value=(output, b""))
        process.returncode = 0
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        result = await document_service._extract_video_metadata(b"fake video")

        assert result["duration_seconds"] is None
        assert result["resolution_width"] is None


# ---------------------------------------------------------------------------
# Test: Video Document Creation
# ---------------------------------------------------------------------------


class TestCreateVideoDocument:
    """Tests for create_video_document()."""

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_creates_document_with_training_video_type(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
        mock_session: AsyncMock,
        sample_ffprobe_output: bytes,
    ) -> None:
        """create_video_document sets document_type to 'Training Video'."""
        process = AsyncMock()
        process.communicate = AsyncMock(
            return_value=(sample_ffprobe_output, b"")
        )
        process.returncode = 0
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        result = await document_service.create_video_document(
            session=mock_session,
            file_data=b"x" * 1024,
            title="Training Video 1",
            folder_path="/videos",
            tags=["training"],
            user_id=1,
            content_type="video/mp4",
        )

        assert result.document_type == "Training Video"

    @pytest.mark.asyncio
    async def test_rejects_unsupported_content_type(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
    ) -> None:
        """create_video_document raises ValueError for unsupported type."""
        with pytest.raises(ValueError, match="Unsupported video content type"):
            await document_service.create_video_document(
                session=mock_session,
                file_data=b"x" * 1024,
                title="Bad File",
                folder_path="/videos",
                tags=[],
                user_id=1,
                content_type="application/pdf",
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_file(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
    ) -> None:
        """create_video_document raises ValueError for empty file."""
        with pytest.raises(ValueError, match="greater than 0 bytes"):
            await document_service.create_video_document(
                session=mock_session,
                file_data=b"",
                title="Empty Video",
                folder_path="/videos",
                tags=[],
                user_id=1,
                content_type="video/mp4",
            )

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_stores_video_metadata(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
        mock_session: AsyncMock,
        sample_ffprobe_output: bytes,
    ) -> None:
        """create_video_document stores VideoMetadata record."""
        process = AsyncMock()
        process.communicate = AsyncMock(
            return_value=(sample_ffprobe_output, b"")
        )
        process.returncode = 0
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        await document_service.create_video_document(
            session=mock_session,
            file_data=b"x" * 1024,
            title="Training Video 1",
            folder_path="/videos",
            tags=[],
            user_id=1,
            content_type="video/mp4",
        )

        # Find the VideoMetadata that was added
        from alcoabase.models.video import VideoMetadata

        meta_calls = [
            call
            for call in mock_session.add.call_args_list
            if isinstance(call[0][0], VideoMetadata)
        ]
        assert len(meta_calls) == 1
        video_meta = meta_calls[0][0][0]
        assert video_meta.duration_seconds == 120.5
        assert video_meta.resolution_width == 1920
        assert video_meta.resolution_height == 1080
        assert video_meta.frame_count == 3000
        assert video_meta.codec == "h264"

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_ffprobe_failure_stores_null_metadata(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
        mock_session: AsyncMock,
    ) -> None:
        """On ffprobe failure, video is stored with null metadata fields."""
        process = AsyncMock()
        process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        process.returncode = None
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        result = await document_service.create_video_document(
            session=mock_session,
            file_data=b"x" * 1024,
            title="Corrupt Video",
            folder_path="/videos",
            tags=[],
            user_id=1,
            content_type="video/mp4",
        )

        # Document should still be created
        assert result.document_type == "Training Video"

        # VideoMetadata should have null fields
        from alcoabase.models.video import VideoMetadata

        meta_calls = [
            call
            for call in mock_session.add.call_args_list
            if isinstance(call[0][0], VideoMetadata)
        ]
        assert len(meta_calls) == 1
        video_meta = meta_calls[0][0][0]
        assert video_meta.duration_seconds is None
        assert video_meta.resolution_width is None
        assert video_meta.resolution_height is None
        assert video_meta.frame_count is None
        assert video_meta.codec is None

    @pytest.mark.asyncio
    @patch("asyncio.create_subprocess_exec")
    async def test_does_not_trigger_frame_extraction(
        self,
        mock_subprocess: MagicMock,
        document_service: DocumentService,
        mock_session: AsyncMock,
        sample_ffprobe_output: bytes,
    ) -> None:
        """create_video_document does NOT auto-trigger frame extraction (Req 4.7)."""
        process = AsyncMock()
        process.communicate = AsyncMock(
            return_value=(sample_ffprobe_output, b"")
        )
        process.returncode = 0
        process.kill = MagicMock()
        process.wait = AsyncMock()
        mock_subprocess.return_value = process

        await document_service.create_video_document(
            session=mock_session,
            file_data=b"x" * 1024,
            title="Training Video 1",
            folder_path="/videos",
            tags=[],
            user_id=1,
            content_type="video/mp4",
        )

        # Verify no frame extraction related calls were made
        # Only ffprobe should have been called (once), not ffmpeg for frames
        assert mock_subprocess.call_count == 1
        call_args = mock_subprocess.call_args[0]
        # The first argument should be the ffprobe path
        assert "ffprobe" in call_args[0]
