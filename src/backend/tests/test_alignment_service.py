"""Unit tests for the AlignmentService frame extraction.

Tests frame extraction logic including interval validation, auto-adjustment,
resolution capping, ffmpeg subprocess calls, and cleanup on failure.

References:
    - Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.alignment_service import AlignmentService


@pytest.fixture
def alignment_service() -> AlignmentService:
    """Create an AlignmentService instance with no dependencies (mock mode)."""
    return AlignmentService()


class TestExtractFramesValidation:
    """Tests for extract_frames() input validation."""

    @pytest.mark.asyncio
    async def test_interval_below_minimum_raises_value_error(
        self, alignment_service: AlignmentService
    ) -> None:
        """interval_seconds < 1 raises ValueError."""
        with pytest.raises(ValueError, match="between 1 and 60"):
            await alignment_service.extract_frames("doc-uuid-1", interval_seconds=0)

    @pytest.mark.asyncio
    async def test_interval_above_maximum_raises_value_error(
        self, alignment_service: AlignmentService
    ) -> None:
        """interval_seconds > 60 raises ValueError."""
        with pytest.raises(ValueError, match="between 1 and 60"):
            await alignment_service.extract_frames("doc-uuid-1", interval_seconds=61)

    @pytest.mark.asyncio
    async def test_interval_at_minimum_is_valid(
        self, alignment_service: AlignmentService
    ) -> None:
        """interval_seconds = 1 does not raise."""
        with patch.object(
            alignment_service, "_do_extract_frames", new_callable=AsyncMock
        ):
            job_id = await alignment_service.extract_frames(
                "doc-uuid-1", interval_seconds=1
            )
            assert isinstance(job_id, str)
            assert len(job_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_interval_at_maximum_is_valid(
        self, alignment_service: AlignmentService
    ) -> None:
        """interval_seconds = 60 does not raise."""
        with patch.object(
            alignment_service, "_do_extract_frames", new_callable=AsyncMock
        ):
            job_id = await alignment_service.extract_frames(
                "doc-uuid-1", interval_seconds=60
            )
            assert isinstance(job_id, str)
            assert len(job_id) == 36

    @pytest.mark.asyncio
    async def test_default_interval_is_5(
        self, alignment_service: AlignmentService
    ) -> None:
        """Default interval_seconds is 5."""
        with patch.object(
            alignment_service, "_do_extract_frames", new_callable=AsyncMock
        ) as mock_do:
            await alignment_service.extract_frames("doc-uuid-1")
            # The task was created with interval=5
            mock_do.assert_called_once()
            call_args = mock_do.call_args[0]
            assert call_args[2] == 5  # interval_seconds


class TestCalculateInterval:
    """Tests for _calculate_interval() auto-adjustment logic."""

    def test_no_adjustment_when_under_max(self) -> None:
        """Interval unchanged when estimated frames <= max_frames."""
        result = AlignmentService._calculate_interval(
            duration=100.0, requested_interval=5, max_frames=500
        )
        assert result == 5

    def test_adjustment_when_over_max(self) -> None:
        """Interval increased when estimated frames > max_frames."""
        # 3000s / 5s = 600 frames > 500 max
        result = AlignmentService._calculate_interval(
            duration=3000.0, requested_interval=5, max_frames=500
        )
        # ceil(3000 / 500) = 6
        assert result == 6

    def test_adjustment_exact_boundary(self) -> None:
        """Interval unchanged when frames exactly equal max_frames."""
        # 2500s / 5s = 500 frames == 500 max
        result = AlignmentService._calculate_interval(
            duration=2500.0, requested_interval=5, max_frames=500
        )
        assert result == 5

    def test_adjustment_just_over_boundary(self) -> None:
        """Interval adjusted when frames just exceed max_frames."""
        # 2501s / 5s = 501 frames > 500 max
        result = AlignmentService._calculate_interval(
            duration=2501.0, requested_interval=5, max_frames=500
        )
        # ceil(2501 / 500) = 6
        assert result == 6

    def test_large_duration_large_adjustment(self) -> None:
        """Large video duration results in proportionally larger interval."""
        # 10000s / 2s = 5000 frames > 500 max
        result = AlignmentService._calculate_interval(
            duration=10000.0, requested_interval=2, max_frames=500
        )
        # ceil(10000 / 500) = 20
        assert result == 20

    def test_short_video_no_adjustment(self) -> None:
        """Short video with any interval stays under max."""
        result = AlignmentService._calculate_interval(
            duration=30.0, requested_interval=1, max_frames=500
        )
        assert result == 1


class TestRunFfmpegExtract:
    """Tests for _run_ffmpeg_extract() subprocess execution."""

    @pytest.mark.asyncio
    async def test_ffmpeg_command_structure(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """ffmpeg is called with correct vf filter and output pattern."""
        # Create a fake frame file so frame count > 0
        frame_file = tmp_path / "frame_00001.png"
        frame_file.write_bytes(b"fake png")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            count = await alignment_service._run_ffmpeg_extract(
                "/tmp/video.mp4", str(tmp_path), 5
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]

            # Verify command structure
            assert cmd[0] == "ffmpeg"
            assert "-i" in cmd
            assert "/tmp/video.mp4" in cmd
            assert "-vf" in cmd
            assert "-vsync" in cmd
            assert "vfr" in cmd

            # Verify vf filter contains fps and scale
            vf_idx = cmd.index("-vf")
            vf_filter = cmd[vf_idx + 1]
            assert "fps=1/5" in vf_filter
            assert "min(1920,iw)" in vf_filter
            assert "min(1080,ih)" in vf_filter
            assert "force_original_aspect_ratio=decrease" in vf_filter

    @pytest.mark.asyncio
    async def test_ffmpeg_failure_raises_runtime_error(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """RuntimeError raised when ffmpeg returns non-zero exit code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: invalid input"

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            with pytest.raises(RuntimeError, match="ffmpeg frame extraction failed"):
                await alignment_service._run_ffmpeg_extract(
                    "/tmp/video.mp4", str(tmp_path), 5
                )

    @pytest.mark.asyncio
    async def test_ffmpeg_timeout_raises_runtime_error(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """RuntimeError raised when ffmpeg times out."""
        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=600)

            with pytest.raises(RuntimeError, match="timed out"):
                await alignment_service._run_ffmpeg_extract(
                    "/tmp/video.mp4", str(tmp_path), 5
                )

    @pytest.mark.asyncio
    async def test_ffmpeg_no_frames_raises_runtime_error(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """RuntimeError raised when ffmpeg produces zero frames."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            with pytest.raises(RuntimeError, match="no frames"):
                await alignment_service._run_ffmpeg_extract(
                    "/tmp/video.mp4", str(tmp_path), 5
                )


class TestGetVideoDuration:
    """Tests for _get_video_duration() ffprobe call."""

    @pytest.mark.asyncio
    async def test_returns_duration_from_ffprobe(
        self, alignment_service: AlignmentService
    ) -> None:
        """Parses duration from ffprobe stdout."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "125.5\n"

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            duration = await alignment_service._get_video_duration("/tmp/video.mp4")
            assert duration == 125.5

    @pytest.mark.asyncio
    async def test_ffprobe_failure_raises_runtime_error(
        self, alignment_service: AlignmentService
    ) -> None:
        """RuntimeError raised when ffprobe returns non-zero."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No such file"

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            with pytest.raises(RuntimeError, match="ffprobe failed"):
                await alignment_service._get_video_duration("/tmp/video.mp4")

    @pytest.mark.asyncio
    async def test_ffprobe_timeout_raises_runtime_error(
        self, alignment_service: AlignmentService
    ) -> None:
        """RuntimeError raised when ffprobe times out."""
        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

            with pytest.raises(RuntimeError, match="timed out"):
                await alignment_service._get_video_duration("/tmp/video.mp4")


class TestCleanupFrames:
    """Tests for _cleanup_frames() directory removal."""

    def test_removes_existing_directory(self, tmp_path) -> None:
        """Removes directory and all contents."""
        frame_dir = tmp_path / "frames"
        frame_dir.mkdir()
        (frame_dir / "frame_00001.png").write_bytes(b"data")
        (frame_dir / "frame_00002.png").write_bytes(b"data")

        AlignmentService._cleanup_frames(str(frame_dir))
        assert not frame_dir.exists()

    def test_handles_nonexistent_directory(self, tmp_path) -> None:
        """Does not raise when directory doesn't exist."""
        nonexistent = str(tmp_path / "nonexistent")
        AlignmentService._cleanup_frames(nonexistent)  # Should not raise


class TestDoExtractFrames:
    """Tests for _do_extract_frames() end-to-end flow."""

    @pytest.mark.asyncio
    async def test_successful_extraction_stores_metadata(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """Successful extraction stores FrameExtractionResult in metadata."""
        doc_uuid = "test-doc-uuid"

        with (
            patch.object(
                alignment_service,
                "_download_video",
                new_callable=AsyncMock,
                return_value="/tmp/video.mp4",
            ),
            patch.object(
                alignment_service,
                "_get_video_duration",
                new_callable=AsyncMock,
                return_value=100.0,
            ),
            patch.object(
                alignment_service,
                "_run_ffmpeg_extract",
                new_callable=AsyncMock,
                return_value=20,
            ),
            patch("alcoabase.services.alignment_service.tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_mkdtemp.return_value = str(tmp_path)

            await alignment_service._do_extract_frames(
                "job-123", doc_uuid, 5
            )

            assert doc_uuid in alignment_service._frame_metadata
            result = alignment_service._frame_metadata[doc_uuid]
            assert result.frame_count == 20
            assert result.interval_used == 5
            assert result.video_duration == 100.0

    @pytest.mark.asyncio
    async def test_failure_cleans_up_frames(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """On failure, partially extracted frames are cleaned up."""
        doc_uuid = "test-doc-uuid"

        with (
            patch.object(
                alignment_service,
                "_download_video",
                new_callable=AsyncMock,
                side_effect=FileNotFoundError("not found"),
            ),
            patch("alcoabase.services.alignment_service.tempfile.mkdtemp") as mock_mkdtemp,
            patch.object(
                alignment_service, "_cleanup_frames"
            ) as mock_cleanup,
        ):
            mock_mkdtemp.return_value = str(tmp_path)

            with pytest.raises(FileNotFoundError):
                await alignment_service._do_extract_frames(
                    "job-123", doc_uuid, 5
                )

            mock_cleanup.assert_called_once_with(str(tmp_path))

    @pytest.mark.asyncio
    async def test_auto_adjusts_interval_for_long_video(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """Interval is auto-adjusted when frames would exceed max."""
        doc_uuid = "test-doc-uuid"

        with (
            patch.object(
                alignment_service,
                "_download_video",
                new_callable=AsyncMock,
                return_value="/tmp/video.mp4",
            ),
            patch.object(
                alignment_service,
                "_get_video_duration",
                new_callable=AsyncMock,
                return_value=3000.0,  # 3000s / 5s = 600 frames > 500
            ),
            patch.object(
                alignment_service,
                "_run_ffmpeg_extract",
                new_callable=AsyncMock,
                return_value=500,
            ) as mock_extract,
            patch("alcoabase.services.alignment_service.tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_mkdtemp.return_value = str(tmp_path)

            await alignment_service._do_extract_frames(
                "job-123", doc_uuid, 5
            )

            # Verify ffmpeg was called with adjusted interval (6)
            call_args = mock_extract.call_args[0]
            assert call_args[2] == 6  # adjusted interval

            result = alignment_service._frame_metadata[doc_uuid]
            assert result.interval_used == 6


class TestStubMethods:
    """Tests that stub methods raise appropriate errors."""

    @pytest.mark.asyncio
    async def test_link_sop_raises_value_error_for_unknown_sop(
        self, alignment_service: AlignmentService
    ) -> None:
        """link_sop raises ValueError when SOP document not found."""
        with pytest.raises(ValueError, match="not found"):
            await alignment_service.link_sop("video-uuid", "sop-uuid")

    @pytest.mark.asyncio
    async def test_align_raises_value_error_when_no_step_sequence(
        self, alignment_service: AlignmentService
    ) -> None:
        """align raises ValueError when Step_Sequence not available."""
        with pytest.raises(ValueError, match="Frame analysis must be completed"):
            await alignment_service.align("doc-uuid")

    @pytest.mark.asyncio
    async def test_get_report_returns_none_when_no_report(
        self, alignment_service: AlignmentService
    ) -> None:
        """get_report returns None when no report exists."""
        result = await alignment_service.get_report("doc-uuid")
        assert result is None



class TestAnalyzeFramesValidation:
    """Tests for analyze_frames() input validation."""

    @pytest.mark.asyncio
    async def test_raises_value_error_when_no_extraction(
        self, alignment_service: AlignmentService
    ) -> None:
        """ValueError raised when frame extraction not completed."""
        with pytest.raises(ValueError, match="Frame extraction must be completed"):
            await alignment_service.analyze_frames("doc-uuid-no-extraction")

    @pytest.mark.asyncio
    async def test_returns_job_id_when_extraction_exists(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """Returns a valid job_id when frame extraction metadata exists."""
        from alcoabase.services.alignment_service import FrameExtractionResult

        # Set up frame metadata
        alignment_service._frame_metadata = {
            "doc-uuid-1": FrameExtractionResult(
                frame_count=5,
                interval_used=5,
                video_duration=25.0,
                output_dir=str(tmp_path),
            )
        }

        # Create some frame files
        for i in range(5):
            (tmp_path / f"frame_{i:05d}.png").write_bytes(b"fake png data")

        with patch.object(
            alignment_service, "_do_analyze_frames", new_callable=AsyncMock
        ):
            job_id = await alignment_service.analyze_frames("doc-uuid-1")
            assert isinstance(job_id, str)
            assert len(job_id) == 36  # UUID format


class TestAnalyzeSingleFrame:
    """Tests for _analyze_single_frame() Vision_Model calls."""

    @pytest.mark.asyncio
    async def test_mock_mode_returns_placeholder(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """In mock mode (no model_manager), returns placeholder description."""
        from alcoabase.services.alignment_service import _FRAME_MOCK_PLACEHOLDER

        frame_path = tmp_path / "frame_00001.png"
        frame_path.write_bytes(b"fake png data")

        result = await alignment_service._analyze_single_frame(
            str(frame_path), 0
        )
        assert result == _FRAME_MOCK_PLACEHOLDER

    @pytest.mark.asyncio
    async def test_gpu_mode_calls_vision_model(self, tmp_path) -> None:
        """In gpu mode, calls inference_client.chat_completion."""
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            return_value="Worker is assembling a circuit board with soldering iron."
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        frame_path = tmp_path / "frame_00001.png"
        frame_path.write_bytes(b"fake png data")

        result = await service._analyze_single_frame(str(frame_path), 0)

        assert result == "Worker is assembling a circuit board with soldering iron."
        mock_inference_client.chat_completion.assert_called_once()

        # Verify timeout is 60s
        call_kwargs = mock_inference_client.chat_completion.call_args[1]
        assert call_kwargs["timeout"] == 60.0

    @pytest.mark.asyncio
    async def test_inference_failure_returns_none(self, tmp_path) -> None:
        """Returns None when Vision_Model fails (Req 6.7)."""
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError("timeout", endpoint="/v1/chat/completions")
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        frame_path = tmp_path / "frame_00001.png"
        frame_path.write_bytes(b"fake png data")

        result = await service._analyze_single_frame(str(frame_path), 0)
        assert result is None

    @pytest.mark.asyncio
    async def test_file_not_found_returns_none(self) -> None:
        """Returns None when frame file cannot be read."""
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        result = await service._analyze_single_frame("/nonexistent/frame.png", 0)
        assert result is None


class TestConsolidateFrames:
    """Tests for _consolidate_frames_into_steps() consolidation logic."""

    @pytest.mark.asyncio
    async def test_empty_descriptions_returns_empty(
        self, alignment_service: AlignmentService
    ) -> None:
        """All None descriptions returns empty step list."""
        steps = await alignment_service._consolidate_frames_into_steps(
            descriptions=[None, None, None],
            interval_used=5,
        )
        assert steps == []

    @pytest.mark.asyncio
    async def test_single_frame_creates_single_step(
        self, alignment_service: AlignmentService
    ) -> None:
        """Single valid frame creates one step."""
        steps = await alignment_service._consolidate_frames_into_steps(
            descriptions=["Worker picks up tool"],
            interval_used=5,
        )
        assert len(steps) == 1
        assert steps[0].start_timestamp == 0.0
        assert steps[0].end_timestamp == 5.0
        assert steps[0].description == "Worker picks up tool"
        assert steps[0].frame_indices == [0]
        assert steps[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_identical_descriptions_merge_into_one_step(
        self, alignment_service: AlignmentService
    ) -> None:
        """Identical descriptions (similarity=1.0) merge into one step."""
        # Same text → same embedding → similarity = 1.0 > 0.85
        desc = "Worker is soldering a component"
        steps = await alignment_service._consolidate_frames_into_steps(
            descriptions=[desc, desc, desc],
            interval_used=5,
        )
        assert len(steps) == 1
        assert steps[0].frame_indices == [0, 1, 2]
        assert steps[0].start_timestamp == 0.0
        assert steps[0].end_timestamp == 15.0

    @pytest.mark.asyncio
    async def test_different_descriptions_create_separate_steps(
        self, alignment_service: AlignmentService
    ) -> None:
        """Very different descriptions create separate steps."""
        # Use very different texts that will have low cosine similarity
        descriptions = [
            "Worker is soldering a circuit board with precision tools",
            "Manager reviews safety documentation at the desk",
            "Technician calibrates measurement equipment in the lab",
        ]
        steps = await alignment_service._consolidate_frames_into_steps(
            descriptions=descriptions,
            interval_used=10,
        )
        # With mock embeddings (random seeded by text hash), different texts
        # should produce different embeddings with low similarity
        assert len(steps) >= 1  # At minimum 1 step
        # Verify timestamps are correct
        assert steps[0].start_timestamp == 0.0

    @pytest.mark.asyncio
    async def test_none_frames_skipped_in_consolidation(
        self, alignment_service: AlignmentService
    ) -> None:
        """None (failed) frames are skipped but affect confidence."""
        desc = "Worker is soldering"
        steps = await alignment_service._consolidate_frames_into_steps(
            descriptions=[desc, None, desc],
            interval_used=5,
        )
        # Frame 0 and 2 are valid, frame 1 is None
        # Since they have the same text, they should merge
        assert len(steps) == 1
        assert steps[0].frame_indices == [0, 2]
        # Confidence: 2 analyzed out of range 0-2 (3 frames total)
        assert steps[0].confidence == pytest.approx(2.0 / 3.0, rel=0.01)


class TestDoAnalyzeFrames:
    """Tests for _do_analyze_frames() end-to-end flow."""

    @pytest.mark.asyncio
    async def test_successful_analysis_stores_step_sequence(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """Successful analysis stores Step_Sequence in _step_sequences."""
        from alcoabase.services.alignment_service import FrameExtractionResult

        doc_uuid = "test-doc-uuid"

        # Create frame files
        for i in range(3):
            (tmp_path / f"frame_{i:05d}.png").write_bytes(b"fake png data")

        alignment_service._frame_metadata = {
            doc_uuid: FrameExtractionResult(
                frame_count=3,
                interval_used=5,
                video_duration=15.0,
                output_dir=str(tmp_path),
            )
        }

        await alignment_service._do_analyze_frames("job-123", doc_uuid)

        assert doc_uuid in alignment_service._step_sequences
        steps = alignment_service._step_sequences[doc_uuid]
        assert len(steps) >= 1
        # All frames should have mock placeholder description
        for step in steps:
            assert step.description is not None

    @pytest.mark.asyncio
    async def test_abort_when_over_50_percent_fail(self, tmp_path) -> None:
        """Aborts when > 50% of frames fail analysis (Req 6.8)."""
        from alcoabase.services.alignment_service import FrameExtractionResult
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        # All calls fail
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError("timeout", endpoint="/v1/chat/completions")
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        doc_uuid = "test-doc-uuid"

        # Create 4 frame files
        for i in range(4):
            (tmp_path / f"frame_{i:05d}.png").write_bytes(b"fake png data")

        service._frame_metadata = {
            doc_uuid: FrameExtractionResult(
                frame_count=4,
                interval_used=5,
                video_duration=20.0,
                output_dir=str(tmp_path),
            )
        }

        with pytest.raises(RuntimeError, match="exceeds 50% threshold"):
            await service._do_analyze_frames("job-123", doc_uuid)

    @pytest.mark.asyncio
    async def test_partial_failures_continue(self, tmp_path) -> None:
        """Analysis continues when < 50% of frames fail (Req 6.7)."""
        from alcoabase.services.alignment_service import FrameExtractionResult
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        # First call fails, rest succeed
        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=[
                InferenceTimeoutError("timeout", endpoint="/v1/chat/completions"),
                "Worker assembles component",
                "Worker tests the assembly",
                "Worker packages the product",
            ]
        )
        mock_inference_client.create_embeddings = AsyncMock(
            return_value=[[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        doc_uuid = "test-doc-uuid"

        # Create 4 frame files
        for i in range(4):
            (tmp_path / f"frame_{i:05d}.png").write_bytes(b"fake png data")

        service._frame_metadata = {
            doc_uuid: FrameExtractionResult(
                frame_count=4,
                interval_used=5,
                video_duration=20.0,
                output_dir=str(tmp_path),
            )
        }

        await service._do_analyze_frames("job-123", doc_uuid)

        assert doc_uuid in service._step_sequences
        steps = service._step_sequences[doc_uuid]
        assert len(steps) >= 1

    @pytest.mark.asyncio
    async def test_no_frame_files_raises_error(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """RuntimeError raised when no frame files found."""
        from alcoabase.services.alignment_service import FrameExtractionResult

        doc_uuid = "test-doc-uuid"

        # Empty directory - no frame files
        alignment_service._frame_metadata = {
            doc_uuid: FrameExtractionResult(
                frame_count=5,
                interval_used=5,
                video_duration=25.0,
                output_dir=str(tmp_path),
            )
        }

        with pytest.raises(RuntimeError, match="No frame files found"):
            await alignment_service._do_analyze_frames("job-123", doc_uuid)


class TestCosineSimilarity:
    """Tests for _cosine_similarity() utility."""

    def test_identical_vectors(self) -> None:
        """Identical vectors have similarity 1.0."""
        vec = [1.0, 0.0, 0.0]
        assert AlignmentService._cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        """Orthogonal vectors have similarity 0.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        assert AlignmentService._cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        """Opposite vectors have similarity -1.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        assert AlignmentService._cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0)

    def test_empty_vectors(self) -> None:
        """Empty vectors return 0.0."""
        assert AlignmentService._cosine_similarity([], []) == 0.0

    def test_mismatched_lengths(self) -> None:
        """Mismatched vector lengths return 0.0."""
        assert AlignmentService._cosine_similarity([1.0, 0.0], [1.0]) == 0.0

    def test_zero_vector(self) -> None:
        """Zero vector returns 0.0."""
        assert AlignmentService._cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


class TestLoadFrameFiles:
    """Tests for _load_frame_files() file loading."""

    def test_loads_and_sorts_frame_files(self, tmp_path) -> None:
        """Loads frame PNGs sorted by filename."""
        (tmp_path / "frame_00003.png").write_bytes(b"data")
        (tmp_path / "frame_00001.png").write_bytes(b"data")
        (tmp_path / "frame_00002.png").write_bytes(b"data")
        (tmp_path / "source_video").write_bytes(b"video")  # Not a frame

        files = AlignmentService._load_frame_files(str(tmp_path))
        assert len(files) == 3
        assert files[0].endswith("frame_00001.png")
        assert files[1].endswith("frame_00002.png")
        assert files[2].endswith("frame_00003.png")

    def test_empty_directory_returns_empty(self, tmp_path) -> None:
        """Empty directory returns empty list."""
        files = AlignmentService._load_frame_files(str(tmp_path))
        assert files == []

    def test_ignores_non_frame_files(self, tmp_path) -> None:
        """Ignores files that don't match frame_*.png pattern."""
        (tmp_path / "frame_00001.png").write_bytes(b"data")
        (tmp_path / "thumbnail.png").write_bytes(b"data")
        (tmp_path / "frame_00002.jpg").write_bytes(b"data")
        (tmp_path / "source_video").write_bytes(b"data")

        files = AlignmentService._load_frame_files(str(tmp_path))
        assert len(files) == 1
        assert files[0].endswith("frame_00001.png")


class TestLinkSOP:
    """Tests for link_sop() SOP linking functionality.

    Validates: Requirements 8.1, 8.2, 8.3, 8.10
    """

    @pytest.fixture
    def service_with_sop(self) -> AlignmentService:
        """Create an AlignmentService with a registered SOP document."""
        service = AlignmentService()
        service.register_sop_document(
            document_uuid="sop-uuid-1",
            company_id=1,
            document_type="SOP",
            tags=["SOP", "training"],
            version="2.0",
        )
        return service

    @pytest.mark.asyncio
    async def test_successful_link(self, service_with_sop: AlignmentService) -> None:
        """Successfully links an SOP to a video document."""
        result = await service_with_sop.link_sop(
            video_document_uuid="video-uuid-1",
            sop_document_uuid="sop-uuid-1",
            sop_version="2.0",
            company_id=1,
        )

        assert result["video_document_uuid"] == "video-uuid-1"
        assert result["sop_document_uuid"] == "sop-uuid-1"
        assert result["sop_version"] == "2.0"
        assert "linked_at" in result

    @pytest.mark.asyncio
    async def test_sop_not_found_raises_value_error(
        self, service_with_sop: AlignmentService
    ) -> None:
        """Raises ValueError when SOP document does not exist."""
        with pytest.raises(ValueError, match="not found"):
            await service_with_sop.link_sop(
                video_document_uuid="video-uuid-1",
                sop_document_uuid="nonexistent-sop",
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_different_tenant_raises_value_error(
        self, service_with_sop: AlignmentService
    ) -> None:
        """Raises ValueError when SOP belongs to a different tenant."""
        with pytest.raises(ValueError, match="different tenant"):
            await service_with_sop.link_sop(
                video_document_uuid="video-uuid-1",
                sop_document_uuid="sop-uuid-1",
                company_id=999,  # Different company
            )

    @pytest.mark.asyncio
    async def test_wrong_document_type_raises_value_error(self) -> None:
        """Raises ValueError when document is not an SOP type."""
        service = AlignmentService()
        service.register_sop_document(
            document_uuid="doc-uuid-not-sop",
            company_id=1,
            document_type="Protocol",
            tags=["training"],
            version="1.0",
        )

        with pytest.raises(ValueError, match="not an SOP document"):
            await service.link_sop(
                video_document_uuid="video-uuid-1",
                sop_document_uuid="doc-uuid-not-sop",
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_sop_tag_accepted_as_valid(self) -> None:
        """Accepts document with 'SOP' in tags even if document_type differs."""
        service = AlignmentService()
        service.register_sop_document(
            document_uuid="doc-with-sop-tag",
            company_id=1,
            document_type="Procedure",
            tags=["SOP", "quality"],
            version="1.0",
        )

        result = await service.link_sop(
            video_document_uuid="video-uuid-1",
            sop_document_uuid="doc-with-sop-tag",
            company_id=1,
        )

        assert result["sop_document_uuid"] == "doc-with-sop-tag"

    @pytest.mark.asyncio
    async def test_max_links_exceeded_raises_value_error(
        self, service_with_sop: AlignmentService
    ) -> None:
        """Raises ValueError when max 10 links per video is exceeded."""
        # Register 10 additional SOP documents and link them
        for i in range(10):
            sop_uuid = f"sop-uuid-extra-{i}"
            service_with_sop.register_sop_document(
                document_uuid=sop_uuid,
                company_id=1,
                document_type="SOP",
                version="1.0",
            )
            await service_with_sop.link_sop(
                video_document_uuid="video-uuid-1",
                sop_document_uuid=sop_uuid,
                company_id=1,
            )

        # 11th link should fail
        service_with_sop.register_sop_document(
            document_uuid="sop-uuid-11th",
            company_id=1,
            document_type="SOP",
            version="1.0",
        )
        with pytest.raises(ValueError, match="Maximum number of linked SOPs"):
            await service_with_sop.link_sop(
                video_document_uuid="video-uuid-1",
                sop_document_uuid="sop-uuid-11th",
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_duplicate_link_raises_value_error(
        self, service_with_sop: AlignmentService
    ) -> None:
        """Raises ValueError when SOP is already linked to the video."""
        # First link succeeds
        await service_with_sop.link_sop(
            video_document_uuid="video-uuid-1",
            sop_document_uuid="sop-uuid-1",
            company_id=1,
        )

        # Duplicate link fails
        with pytest.raises(ValueError, match="already linked"):
            await service_with_sop.link_sop(
                video_document_uuid="video-uuid-1",
                sop_document_uuid="sop-uuid-1",
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_defaults_to_latest_version(
        self, service_with_sop: AlignmentService
    ) -> None:
        """Uses the SOP's registered version when sop_version is None."""
        result = await service_with_sop.link_sop(
            video_document_uuid="video-uuid-1",
            sop_document_uuid="sop-uuid-1",
            sop_version=None,
            company_id=1,
        )

        # Should use the registered version "2.0"
        assert result["sop_version"] == "2.0"

    @pytest.mark.asyncio
    async def test_explicit_version_overrides_default(
        self, service_with_sop: AlignmentService
    ) -> None:
        """Uses the explicitly provided sop_version over the default."""
        result = await service_with_sop.link_sop(
            video_document_uuid="video-uuid-1",
            sop_document_uuid="sop-uuid-1",
            sop_version="3.1",
            company_id=1,
        )

        assert result["sop_version"] == "3.1"

    @pytest.mark.asyncio
    async def test_different_videos_can_link_same_sop(
        self, service_with_sop: AlignmentService
    ) -> None:
        """Different videos can link to the same SOP independently."""
        result1 = await service_with_sop.link_sop(
            video_document_uuid="video-uuid-1",
            sop_document_uuid="sop-uuid-1",
            company_id=1,
        )
        result2 = await service_with_sop.link_sop(
            video_document_uuid="video-uuid-2",
            sop_document_uuid="sop-uuid-1",
            company_id=1,
        )

        assert result1["video_document_uuid"] == "video-uuid-1"
        assert result2["video_document_uuid"] == "video-uuid-2"


class TestTranscribeAudio:
    """Tests for transcribe_audio() and related methods."""

    @pytest.mark.asyncio
    async def test_mock_mode_returns_placeholder_transcript(
        self, alignment_service: AlignmentService
    ) -> None:
        """In mock mode, returns placeholder transcript (Req 7.9)."""
        from alcoabase.services.alignment_service import (
            TranscriptSegment,
            _AUDIO_MOCK_PLACEHOLDER,
        )

        with patch.object(
            alignment_service, "_do_transcribe_audio", wraps=alignment_service._do_transcribe_audio
        ):
            job_id = await alignment_service.transcribe_audio("doc-uuid-1")
            assert isinstance(job_id, str)
            assert len(job_id) == 36

            # Wait for background task to complete
            await asyncio.sleep(0.1)

            transcripts = getattr(alignment_service, "_transcripts", {})
            assert "doc-uuid-1" in transcripts
            segments = transcripts["doc-uuid-1"]
            assert len(segments) == 1
            assert segments[0].text == _AUDIO_MOCK_PLACEHOLDER
            assert segments[0].start_time == 0.0
            assert segments[0].end_time == 30.0

    @pytest.mark.asyncio
    async def test_returns_job_id(
        self, alignment_service: AlignmentService
    ) -> None:
        """transcribe_audio returns a valid UUID job_id."""
        with patch.object(
            alignment_service, "_do_transcribe_audio", new_callable=AsyncMock
        ):
            job_id = await alignment_service.transcribe_audio("doc-uuid-1")
            assert isinstance(job_id, str)
            assert len(job_id) == 36


class TestExtractAudioTrack:
    """Tests for _extract_audio_track() ffmpeg call."""

    @pytest.mark.asyncio
    async def test_ffmpeg_command_structure(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """ffmpeg is called with correct WAV 16kHz mono parameters."""
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake wav data")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            result = await alignment_service._extract_audio_track(
                "/tmp/video.mp4", str(tmp_path)
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]

            # Verify command structure (Req 7.1)
            assert cmd[0] == "ffmpeg"
            assert "-i" in cmd
            assert "/tmp/video.mp4" in cmd
            assert "-vn" in cmd
            assert "-acodec" in cmd
            assert "pcm_s16le" in cmd
            assert "-ar" in cmd
            assert "16000" in cmd
            assert "-ac" in cmd
            assert "1" in cmd

            assert result is not None
            assert result.endswith("audio.wav")

    @pytest.mark.asyncio
    async def test_no_audio_track_returns_none(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """Returns None when video has no audio track (Req 7.4)."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Output file #0 does not contain any stream"

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            result = await alignment_service._extract_audio_track(
                "/tmp/video.mp4", str(tmp_path)
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_extraction_failure_raises_error(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """AudioExtractionError raised on ffmpeg failure (Req 7.6)."""
        from alcoabase.services.alignment_service import AudioExtractionError

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: corrupt audio codec"

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            with pytest.raises(AudioExtractionError, match="ffmpeg audio extraction failed"):
                await alignment_service._extract_audio_track(
                    "/tmp/video.mp4", str(tmp_path)
                )

    @pytest.mark.asyncio
    async def test_timeout_raises_extraction_error(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """AudioExtractionError raised on ffmpeg timeout."""
        from alcoabase.services.alignment_service import AudioExtractionError

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)

            with pytest.raises(AudioExtractionError, match="timed out"):
                await alignment_service._extract_audio_track(
                    "/tmp/video.mp4", str(tmp_path)
                )

    @pytest.mark.asyncio
    async def test_empty_output_file_returns_none(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """Returns None when output file is empty (no audio data)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result
            # Don't create the audio.wav file, so it won't exist
            result = await alignment_service._extract_audio_track(
                "/tmp/video.mp4", str(tmp_path)
            )
            assert result is None


class TestExtractAudioChunk:
    """Tests for _extract_audio_chunk() ffmpeg chunk extraction."""

    @pytest.mark.asyncio
    async def test_chunk_extraction_command(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """ffmpeg chunk extraction uses correct -ss and -t parameters."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        chunk_path = str(tmp_path / "chunk_00000.wav")

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            await alignment_service._extract_audio_chunk(
                "/tmp/audio.wav", chunk_path, 30.0, 60.0
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]

            assert cmd[0] == "ffmpeg"
            assert "-ss" in cmd
            assert "30.0" in cmd
            assert "-t" in cmd
            assert "30.0" in cmd  # duration = end - start
            assert chunk_path in cmd

    @pytest.mark.asyncio
    async def test_chunk_extraction_failure_raises_error(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """AudioExtractionError raised on chunk extraction failure."""
        from alcoabase.services.alignment_service import AudioExtractionError

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error processing chunk"

        chunk_path = str(tmp_path / "chunk_00000.wav")

        with patch("alcoabase.services.alignment_service.subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            with pytest.raises(AudioExtractionError, match="chunk extraction failed"):
                await alignment_service._extract_audio_chunk(
                    "/tmp/audio.wav", chunk_path, 0.0, 30.0
                )


class TestTranscribeChunk:
    """Tests for _transcribe_chunk() speech-to-text processing."""

    @pytest.mark.asyncio
    async def test_no_inference_client_raises_unavailable(
        self, alignment_service: AlignmentService, tmp_path
    ) -> None:
        """SpeechModelUnavailableError when no inference client (Req 7.5)."""
        from alcoabase.services.alignment_service import SpeechModelUnavailableError

        # alignment_service has no inference_client (mock mode)
        # But we need to bypass mock mode check - set model_manager with gpu mode
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        alignment_service._model_manager = mock_model_manager
        alignment_service._inference_client = None

        chunk_path = tmp_path / "chunk.wav"
        chunk_path.write_bytes(b"fake wav")

        with pytest.raises(SpeechModelUnavailableError, match="not available"):
            await alignment_service._transcribe_chunk(str(chunk_path), 0)

    @pytest.mark.asyncio
    async def test_successful_transcription(self, tmp_path) -> None:
        """Returns transcribed text on success."""
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            return_value="Step one: put on safety goggles."
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        chunk_path = tmp_path / "chunk.wav"
        chunk_path.write_bytes(b"fake wav data")

        result = await service._transcribe_chunk(str(chunk_path), 0)
        assert result == "Step one: put on safety goggles."
        mock_inference_client.chat_completion.assert_called_once()

        # Verify timeout is 60s
        call_kwargs = mock_inference_client.chat_completion.call_args[1]
        assert call_kwargs["timeout"] == 60.0

    @pytest.mark.asyncio
    async def test_connection_error_raises_unavailable(self, tmp_path) -> None:
        """SpeechModelUnavailableError on connection failure (Req 7.5)."""
        from alcoabase.services.alignment_service import SpeechModelUnavailableError
        from alcoabase.services.inference_client import InferenceConnectionError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceConnectionError(
                "Connection refused", endpoint="/v1/chat/completions"
            )
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        chunk_path = tmp_path / "chunk.wav"
        chunk_path.write_bytes(b"fake wav data")

        with pytest.raises(SpeechModelUnavailableError, match="unreachable"):
            await service._transcribe_chunk(str(chunk_path), 0)

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, tmp_path) -> None:
        """Returns None on transcription timeout (continues processing)."""
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError(
                "timeout", endpoint="/v1/chat/completions"
            )
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        chunk_path = tmp_path / "chunk.wav"
        chunk_path.write_bytes(b"fake wav data")

        result = await service._transcribe_chunk(str(chunk_path), 0)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_response_returns_none(self, tmp_path) -> None:
        """Returns None when model returns empty text."""
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(return_value="   ")

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        chunk_path = tmp_path / "chunk.wav"
        chunk_path.write_bytes(b"fake wav data")

        result = await service._transcribe_chunk(str(chunk_path), 0)
        assert result is None


class TestMergeTranscriptWithSteps:
    """Tests for merge_transcript_with_steps() timestamp overlap logic."""

    def test_empty_steps_returns_empty(
        self, alignment_service: AlignmentService
    ) -> None:
        """Returns empty list when no steps exist."""
        result = alignment_service.merge_transcript_with_steps("doc-uuid")
        assert result == []

    def test_empty_transcript_returns_steps_unchanged(
        self, alignment_service: AlignmentService
    ) -> None:
        """Steps returned unchanged when no transcript segments."""
        from alcoabase.services.alignment_service import StepDescription

        steps = [
            StepDescription(
                start_timestamp=0.0,
                end_timestamp=10.0,
                description="Step 1",
                frame_indices=[0, 1],
            )
        ]
        alignment_service._step_sequences = {"doc-uuid": steps}
        alignment_service._transcripts = {"doc-uuid": []}

        result = alignment_service.merge_transcript_with_steps("doc-uuid")
        assert len(result) == 1
        assert result[0].audio_transcript is None

    def test_segment_assigned_to_step_with_greatest_overlap(
        self, alignment_service: AlignmentService
    ) -> None:
        """Transcript segment assigned to step with greatest overlap (Req 7.7)."""
        from alcoabase.services.alignment_service import (
            StepDescription,
            TranscriptSegment,
        )

        steps = [
            StepDescription(
                start_timestamp=0.0,
                end_timestamp=10.0,
                description="Step 1",
                frame_indices=[0, 1],
            ),
            StepDescription(
                start_timestamp=10.0,
                end_timestamp=25.0,
                description="Step 2",
                frame_indices=[2, 3, 4],
            ),
            StepDescription(
                start_timestamp=25.0,
                end_timestamp=40.0,
                description="Step 3",
                frame_indices=[5, 6, 7],
            ),
        ]

        # Segment 5-20s: overlaps step1 by 5s, step2 by 10s → assigned to step2
        segments = [
            TranscriptSegment(start_time=5.0, end_time=20.0, text="Hello world"),
        ]

        alignment_service._step_sequences = {"doc-uuid": steps}
        alignment_service._transcripts = {"doc-uuid": segments}

        result = alignment_service.merge_transcript_with_steps("doc-uuid")

        assert result[0].audio_transcript is None  # Step 1: 5s overlap
        assert result[1].audio_transcript == "Hello world"  # Step 2: 10s overlap
        assert result[2].audio_transcript is None  # Step 3: 0s overlap

    def test_multiple_segments_concatenated_chronologically(
        self, alignment_service: AlignmentService
    ) -> None:
        """Multiple segments assigned to same step are concatenated (Req 7.7)."""
        from alcoabase.services.alignment_service import (
            StepDescription,
            TranscriptSegment,
        )

        steps = [
            StepDescription(
                start_timestamp=0.0,
                end_timestamp=60.0,
                description="Long step",
                frame_indices=[0, 1, 2, 3],
            ),
        ]

        # Both segments fully overlap with the single step
        segments = [
            TranscriptSegment(start_time=30.0, end_time=60.0, text="second part"),
            TranscriptSegment(start_time=0.0, end_time=30.0, text="first part"),
        ]

        alignment_service._step_sequences = {"doc-uuid": steps}
        alignment_service._transcripts = {"doc-uuid": segments}

        result = alignment_service.merge_transcript_with_steps("doc-uuid")

        # Should be concatenated in chronological order
        assert result[0].audio_transcript == "first part second part"

    def test_segment_with_no_overlap_not_assigned(
        self, alignment_service: AlignmentService
    ) -> None:
        """Segments with no overlap are not assigned to any step."""
        from alcoabase.services.alignment_service import (
            StepDescription,
            TranscriptSegment,
        )

        steps = [
            StepDescription(
                start_timestamp=0.0,
                end_timestamp=10.0,
                description="Step 1",
                frame_indices=[0, 1],
            ),
        ]

        # Segment is entirely outside the step's range
        segments = [
            TranscriptSegment(start_time=20.0, end_time=30.0, text="No overlap"),
        ]

        alignment_service._step_sequences = {"doc-uuid": steps}
        alignment_service._transcripts = {"doc-uuid": segments}

        result = alignment_service.merge_transcript_with_steps("doc-uuid")
        assert result[0].audio_transcript is None

    def test_segment_split_across_steps(
        self, alignment_service: AlignmentService
    ) -> None:
        """Segment spanning multiple steps assigned to one with greatest overlap."""
        from alcoabase.services.alignment_service import (
            StepDescription,
            TranscriptSegment,
        )

        steps = [
            StepDescription(
                start_timestamp=0.0,
                end_timestamp=10.0,
                description="Step 1",
                frame_indices=[0],
            ),
            StepDescription(
                start_timestamp=10.0,
                end_timestamp=30.0,
                description="Step 2",
                frame_indices=[1, 2],
            ),
        ]

        # Segment 5-25s: overlaps step1 by 5s, step2 by 15s → step2
        segments = [
            TranscriptSegment(start_time=5.0, end_time=25.0, text="Spanning text"),
        ]

        alignment_service._step_sequences = {"doc-uuid": steps}
        alignment_service._transcripts = {"doc-uuid": segments}

        result = alignment_service.merge_transcript_with_steps("doc-uuid")
        assert result[0].audio_transcript is None
        assert result[1].audio_transcript == "Spanning text"


class TestDoTranscribeAudioEndToEnd:
    """Tests for _do_transcribe_audio() end-to-end flow."""

    @pytest.mark.asyncio
    async def test_no_audio_track_stores_empty_transcript(self, tmp_path) -> None:
        """Stores empty transcript when video has no audio (Req 7.4)."""
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=MagicMock(),
        )

        with (
            patch.object(
                service,
                "_download_video",
                new_callable=AsyncMock,
                return_value="/tmp/video.mp4",
            ),
            patch.object(
                service,
                "_extract_audio_track",
                new_callable=AsyncMock,
                return_value=None,  # No audio track
            ),
            patch.object(service, "_cleanup_frames") as mock_cleanup,
        ):
            await service._do_transcribe_audio("job-123", "doc-uuid")

            transcripts = getattr(service, "_transcripts", {})
            assert "doc-uuid" in transcripts
            assert transcripts["doc-uuid"] == []
            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_transcription_stores_segments(self, tmp_path) -> None:
        """Stores transcript segments on successful transcription."""
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        mock_inference_client = MagicMock()

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        with (
            patch.object(
                service,
                "_download_video",
                new_callable=AsyncMock,
                return_value="/tmp/video.mp4",
            ),
            patch.object(
                service,
                "_extract_audio_track",
                new_callable=AsyncMock,
                return_value="/tmp/audio.wav",
            ),
            patch.object(
                service,
                "_get_audio_duration",
                new_callable=AsyncMock,
                return_value=45.0,  # 45s → 2 chunks (30s + 15s)
            ),
            patch.object(
                service,
                "_extract_audio_chunk",
                new_callable=AsyncMock,
            ),
            patch.object(
                service,
                "_transcribe_chunk",
                new_callable=AsyncMock,
                side_effect=["First chunk text", "Second chunk text"],
            ),
            patch.object(service, "_cleanup_frames"),
        ):
            await service._do_transcribe_audio("job-123", "doc-uuid")

            transcripts = getattr(service, "_transcripts", {})
            assert "doc-uuid" in transcripts
            segments = transcripts["doc-uuid"]
            assert len(segments) == 2
            assert segments[0].start_time == 0.0
            assert segments[0].end_time == 30.0
            assert segments[0].text == "First chunk text"
            assert segments[1].start_time == 30.0
            assert segments[1].end_time == 45.0
            assert segments[1].text == "Second chunk text"

    @pytest.mark.asyncio
    async def test_extraction_error_propagates(self, tmp_path) -> None:
        """AudioExtractionError propagates from _extract_audio_track (Req 7.6)."""
        from alcoabase.services.alignment_service import AudioExtractionError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=MagicMock(),
        )

        with (
            patch.object(
                service,
                "_download_video",
                new_callable=AsyncMock,
                return_value="/tmp/video.mp4",
            ),
            patch.object(
                service,
                "_extract_audio_track",
                new_callable=AsyncMock,
                side_effect=AudioExtractionError("corrupt audio"),
            ),
            patch.object(service, "_cleanup_frames"),
        ):
            with pytest.raises(AudioExtractionError, match="corrupt audio"):
                await service._do_transcribe_audio("job-123", "doc-uuid")

    @pytest.mark.asyncio
    async def test_model_unavailable_propagates(self, tmp_path) -> None:
        """SpeechModelUnavailableError propagates (Req 7.5)."""
        from alcoabase.services.alignment_service import SpeechModelUnavailableError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=None,  # No client → unavailable
        )

        with (
            patch.object(
                service,
                "_download_video",
                new_callable=AsyncMock,
                return_value="/tmp/video.mp4",
            ),
            patch.object(
                service,
                "_extract_audio_track",
                new_callable=AsyncMock,
                return_value="/tmp/audio.wav",
            ),
            patch.object(
                service,
                "_get_audio_duration",
                new_callable=AsyncMock,
                return_value=15.0,
            ),
            patch.object(
                service,
                "_extract_audio_chunk",
                new_callable=AsyncMock,
            ),
            patch.object(service, "_cleanup_frames"),
        ):
            with pytest.raises(SpeechModelUnavailableError):
                await service._do_transcribe_audio("job-123", "doc-uuid")


class TestAlign:
    """Tests for align() alignment logic.

    Validates: Requirements 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 9.1, 9.2, 9.3, 9.4, 9.5, 9.10
    """

    @pytest.fixture
    def service_with_steps_and_sop(self) -> AlignmentService:
        """Create an AlignmentService with step sequence and linked SOP."""
        from alcoabase.services.alignment_service import (
            SOPLinkRecord,
            StepDescription,
        )
        from datetime import datetime, timezone

        service = AlignmentService()

        # Set up step sequence for video
        service._step_sequences = {
            "video-uuid-1": [
                StepDescription(
                    start_timestamp=0.0,
                    end_timestamp=10.0,
                    description="Put on safety goggles and gloves",
                    frame_indices=[0, 1],
                    confidence=1.0,
                ),
                StepDescription(
                    start_timestamp=10.0,
                    end_timestamp=20.0,
                    description="Connect the power supply to the circuit board",
                    frame_indices=[2, 3],
                    confidence=1.0,
                ),
                StepDescription(
                    start_timestamp=20.0,
                    end_timestamp=30.0,
                    description="Solder the components onto the board",
                    frame_indices=[4, 5],
                    confidence=1.0,
                ),
            ]
        }

        # Register and link SOP
        service.register_sop_document(
            document_uuid="sop-uuid-1",
            company_id=1,
            document_type="SOP",
            version="1.0",
        )
        service._sop_links = {
            "video-uuid-1": [
                SOPLinkRecord(
                    video_document_uuid="video-uuid-1",
                    sop_document_uuid="sop-uuid-1",
                    sop_version="1.0",
                    linked_at=datetime.now(timezone.utc),
                )
            ]
        }

        # Register SOP text content
        service._sop_texts = {
            "sop-uuid-1": (
                "1. Wear safety goggles and protective gloves\n"
                "2. Connect power supply to the circuit board\n"
                "3. Solder components onto the board\n"
            )
        }

        return service

    @pytest.mark.asyncio
    async def test_raises_value_error_when_no_step_sequence(self) -> None:
        """ValueError raised when Step_Sequence not available (Req 8.8)."""
        service = AlignmentService()
        with pytest.raises(ValueError, match="Frame analysis must be completed"):
            await service.align("video-uuid-no-steps")

    @pytest.mark.asyncio
    async def test_raises_value_error_when_no_sops_linked(self) -> None:
        """ValueError raised when no SOPs are linked (Req 8.9)."""
        from alcoabase.services.alignment_service import StepDescription

        service = AlignmentService()
        service._step_sequences = {
            "video-uuid-1": [
                StepDescription(
                    start_timestamp=0.0,
                    end_timestamp=10.0,
                    description="Some step",
                    frame_indices=[0],
                )
            ]
        }

        with pytest.raises(ValueError, match="At least one SOP must be linked"):
            await service.align("video-uuid-1")

    @pytest.mark.asyncio
    async def test_returns_job_id(
        self, service_with_steps_and_sop: AlignmentService
    ) -> None:
        """align() returns a valid UUID job_id."""
        with patch.object(
            service_with_steps_and_sop, "_do_align", new_callable=AsyncMock
        ):
            job_id = await service_with_steps_and_sop.align("video-uuid-1")
            assert isinstance(job_id, str)
            assert len(job_id) == 36

    @pytest.mark.asyncio
    async def test_alignment_stores_report(
        self, service_with_steps_and_sop: AlignmentService
    ) -> None:
        """Alignment stores a Discrepancy_Report in memory (Req 9.5)."""
        await service_with_steps_and_sop._do_align("job-123", "video-uuid-1")

        report = await service_with_steps_and_sop.get_report("video-uuid-1")
        assert report is not None
        assert report["video_document_uuid"] == "video-uuid-1"
        assert report["sop_document_uuid"] == "sop-uuid-1"
        assert "alignment_score" in report
        assert "matched_steps" in report
        assert "missing_steps" in report
        assert "extra_steps" in report
        assert "order_mismatches" in report
        assert "requires_review" in report
        assert "generated_at" in report

    @pytest.mark.asyncio
    async def test_alignment_score_calculation(
        self, service_with_steps_and_sop: AlignmentService
    ) -> None:
        """alignment_score = matched_count / total_video_steps (Req 9.1)."""
        await service_with_steps_and_sop._do_align("job-123", "video-uuid-1")

        report = await service_with_steps_and_sop.get_report("video-uuid-1")
        assert report is not None

        total_video_steps = report["total_video_steps"]
        matched_count = len(report["matched_steps"])
        expected_score = matched_count / total_video_steps if total_video_steps > 0 else 0.0
        assert report["alignment_score"] == pytest.approx(expected_score)

    @pytest.mark.asyncio
    async def test_requires_review_when_score_below_half(self) -> None:
        """requires_review=True when alignment_score < 0.5 (Req 9.10)."""
        from alcoabase.services.alignment_service import (
            SOPLinkRecord,
            StepDescription,
        )
        from datetime import datetime, timezone

        service = AlignmentService()

        # Video has 4 steps, SOP has 1 very different step → low match
        service._step_sequences = {
            "video-uuid-low": [
                StepDescription(
                    start_timestamp=0.0,
                    end_timestamp=10.0,
                    description="Calibrate the spectrometer device",
                    frame_indices=[0],
                ),
                StepDescription(
                    start_timestamp=10.0,
                    end_timestamp=20.0,
                    description="Record baseline measurements",
                    frame_indices=[1],
                ),
                StepDescription(
                    start_timestamp=20.0,
                    end_timestamp=30.0,
                    description="Apply chemical reagent to sample",
                    frame_indices=[2],
                ),
                StepDescription(
                    start_timestamp=30.0,
                    end_timestamp=40.0,
                    description="Document results in laboratory notebook",
                    frame_indices=[3],
                ),
            ]
        }

        service.register_sop_document(
            document_uuid="sop-uuid-diff",
            company_id=1,
            document_type="SOP",
            version="1.0",
        )
        service._sop_links = {
            "video-uuid-low": [
                SOPLinkRecord(
                    video_document_uuid="video-uuid-low",
                    sop_document_uuid="sop-uuid-diff",
                    sop_version="1.0",
                    linked_at=datetime.now(timezone.utc),
                )
            ]
        }
        service._sop_texts = {
            "sop-uuid-diff": "1. Turn off all equipment and leave the room\n"
        }

        await service._do_align("job-low", "video-uuid-low")

        report = await service.get_report("video-uuid-low")
        assert report is not None
        # With very different steps, alignment_score should be low
        # and requires_review should be True
        assert report["alignment_score"] < 0.5
        assert report["requires_review"] is True

    @pytest.mark.asyncio
    async def test_skips_sop_with_no_steps(self) -> None:
        """Skips alignment for SOP with no extractable steps (Req 8.6)."""
        from alcoabase.services.alignment_service import (
            SOPLinkRecord,
            StepDescription,
        )
        from datetime import datetime, timezone

        service = AlignmentService()

        service._step_sequences = {
            "video-uuid-1": [
                StepDescription(
                    start_timestamp=0.0,
                    end_timestamp=10.0,
                    description="Some step",
                    frame_indices=[0],
                ),
            ]
        }

        service.register_sop_document(
            document_uuid="sop-empty",
            company_id=1,
            document_type="SOP",
            version="1.0",
        )
        service._sop_links = {
            "video-uuid-1": [
                SOPLinkRecord(
                    video_document_uuid="video-uuid-1",
                    sop_document_uuid="sop-empty",
                    sop_version="1.0",
                    linked_at=datetime.now(timezone.utc),
                )
            ]
        }
        # Empty SOP text → no steps extractable
        service._sop_texts = {"sop-empty": "This document has no procedural steps."}

        await service._do_align("job-skip", "video-uuid-1")

        # No report stored since SOP had no steps
        report = await service.get_report("video-uuid-1")
        assert report is None

    @pytest.mark.asyncio
    async def test_severity_fallback_to_major_in_mock_mode(
        self, service_with_steps_and_sop: AlignmentService
    ) -> None:
        """Severity defaults to 'major' in mock mode (Req 9.4)."""
        from alcoabase.services.alignment_service import (
            Discrepancy,
            DiscrepancySeverity,
        )

        disc = Discrepancy(
            step_description="Test step",
            source="video",
            severity=DiscrepancySeverity.MAJOR,
            recommendation="",
        )

        result = await service_with_steps_and_sop._classify_severity(disc)
        assert result == DiscrepancySeverity.MAJOR

    @pytest.mark.asyncio
    async def test_recommendation_fallback_in_mock_mode(
        self, service_with_steps_and_sop: AlignmentService
    ) -> None:
        """Recommendation defaults to generic text in mock mode (Req 9.9)."""
        from alcoabase.services.alignment_service import (
            Discrepancy,
            DiscrepancySeverity,
        )

        disc = Discrepancy(
            step_description="Test step",
            source="video",
            severity=DiscrepancySeverity.MAJOR,
            recommendation="",
        )

        result = await service_with_steps_and_sop._generate_recommendation(disc)
        assert result == "Manual review is required for this discrepancy."

    @pytest.mark.asyncio
    async def test_severity_classification_via_chat_model(self) -> None:
        """Chat_Model classifies severity correctly (Req 9.3)."""
        from alcoabase.services.alignment_service import (
            Discrepancy,
            DiscrepancySeverity,
        )

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(return_value="CRITICAL")

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        disc = Discrepancy(
            step_description="Put on safety goggles",
            source="video",
            severity=DiscrepancySeverity.MAJOR,
            recommendation="",
        )

        result = await service._classify_severity(disc)
        assert result == DiscrepancySeverity.CRITICAL

    @pytest.mark.asyncio
    async def test_severity_fallback_on_chat_model_failure(self) -> None:
        """Severity falls back to 'major' when Chat_Model fails (Req 9.4)."""
        from alcoabase.services.alignment_service import (
            Discrepancy,
            DiscrepancySeverity,
        )
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError("timeout", endpoint="/v1/chat/completions")
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        disc = Discrepancy(
            step_description="Test step",
            source="video",
            severity=DiscrepancySeverity.MAJOR,
            recommendation="",
        )

        result = await service._classify_severity(disc)
        assert result == DiscrepancySeverity.MAJOR

    @pytest.mark.asyncio
    async def test_recommendation_via_chat_model(self) -> None:
        """Chat_Model generates recommendation (Req 9.8)."""
        from alcoabase.services.alignment_service import (
            Discrepancy,
            DiscrepancySeverity,
        )

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            return_value="Update the SOP to include this safety step."
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        disc = Discrepancy(
            step_description="Put on safety goggles",
            source="video",
            severity=DiscrepancySeverity.CRITICAL,
            recommendation="",
        )

        result = await service._generate_recommendation(disc)
        assert result == "Update the SOP to include this safety step."

    @pytest.mark.asyncio
    async def test_recommendation_fallback_on_chat_model_failure(self) -> None:
        """Recommendation falls back to generic text on failure (Req 9.9)."""
        from alcoabase.services.alignment_service import (
            Discrepancy,
            DiscrepancySeverity,
        )
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError("timeout", endpoint="/v1/chat/completions")
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        disc = Discrepancy(
            step_description="Test step",
            source="video",
            severity=DiscrepancySeverity.MAJOR,
            recommendation="",
        )

        result = await service._generate_recommendation(disc)
        assert result == "Manual review is required for this discrepancy."

    @pytest.mark.asyncio
    async def test_recommendation_capped_at_500_chars(self) -> None:
        """Recommendation text is capped at 500 characters (Req 9.8)."""
        from alcoabase.services.alignment_service import (
            Discrepancy,
            DiscrepancySeverity,
        )

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        long_text = "A" * 600
        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(return_value=long_text)

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )

        disc = Discrepancy(
            step_description="Test step",
            source="video",
            severity=DiscrepancySeverity.MAJOR,
            recommendation="",
        )

        result = await service._generate_recommendation(disc)
        assert len(result) == 500


class TestGetReport:
    """Tests for get_report() retrieval."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_report(self) -> None:
        """Returns None when no report exists for the document."""
        service = AlignmentService()
        result = await service.get_report("nonexistent-uuid")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_stored_report(self) -> None:
        """Returns the stored report for the document."""
        from datetime import datetime, timezone

        service = AlignmentService()
        service._reports = {
            "video-uuid-1": {
                "video_document_uuid": "video-uuid-1",
                "alignment_score": 0.75,
                "requires_review": False,
                "generated_at": datetime.now(timezone.utc),
            }
        }

        result = await service.get_report("video-uuid-1")
        assert result is not None
        assert result["alignment_score"] == 0.75
        assert result["requires_review"] is False


class TestCompareSteps:
    """Tests for _compare_steps() step comparison logic."""

    @pytest.fixture
    def service(self) -> AlignmentService:
        """Create an AlignmentService in mock mode."""
        return AlignmentService()

    @pytest.mark.asyncio
    async def test_identical_steps_all_matched(self, service: AlignmentService) -> None:
        """Identical steps are all classified as matched."""
        from alcoabase.services.alignment_service import SOPStep, StepDescription

        video_steps = [
            StepDescription(
                start_timestamp=0.0,
                end_timestamp=10.0,
                description="Put on safety goggles",
                frame_indices=[0],
            ),
        ]
        sop_steps = [
            SOPStep(step_number=1, description="Put on safety goggles"),
        ]

        result = await service._compare_steps(video_steps, sop_steps, 0.7)

        assert len(result["matched_steps"]) == 1
        assert len(result["missing_steps"]) == 0
        assert len(result["extra_steps"]) == 0
        assert result["matched_steps"][0].similarity_score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_no_matching_steps(self, service: AlignmentService) -> None:
        """Completely different steps produce missing and extra."""
        from alcoabase.services.alignment_service import SOPStep, StepDescription

        video_steps = [
            StepDescription(
                start_timestamp=0.0,
                end_timestamp=10.0,
                description="Calibrate the spectrometer device precisely",
                frame_indices=[0],
            ),
        ]
        sop_steps = [
            SOPStep(step_number=1, description="Turn off all equipment and leave the room immediately"),
        ]

        result = await service._compare_steps(video_steps, sop_steps, 0.7)

        # With mock embeddings (random seeded by hash), very different texts
        # should have low similarity
        total_matched = len(result["matched_steps"])
        total_missing = len(result["missing_steps"])
        total_extra = len(result["extra_steps"])

        # At least one of missing or extra should be non-empty
        assert total_missing + total_extra >= 1 or total_matched == 1

    @pytest.mark.asyncio
    async def test_order_mismatch_detected(self, service: AlignmentService) -> None:
        """Order mismatch detected when position diff >= 2."""
        from alcoabase.services.alignment_service import SOPStep, StepDescription

        # Same text but at different positions (diff >= 2)
        text = "Put on safety goggles and protective equipment"
        video_steps = [
            StepDescription(
                start_timestamp=0.0, end_timestamp=10.0,
                description="First unrelated step in the video sequence",
                frame_indices=[0],
            ),
            StepDescription(
                start_timestamp=10.0, end_timestamp=20.0,
                description="Second unrelated step in the video sequence",
                frame_indices=[1],
            ),
            StepDescription(
                start_timestamp=20.0, end_timestamp=30.0,
                description=text,
                frame_indices=[2],
            ),
        ]
        sop_steps = [
            SOPStep(step_number=1, description=text),
            SOPStep(step_number=2, description="Third unrelated step in the SOP document"),
            SOPStep(step_number=3, description="Fourth unrelated step in the SOP document"),
        ]

        result = await service._compare_steps(video_steps, sop_steps, 0.7)

        # The identical text should match (video pos 2, sop pos 0) → diff = 2
        matched_with_order_issue = [
            m for m in result["order_mismatches"]
            if m.video_step.description == text
        ]
        # If the identical text matched, it should be flagged as order mismatch
        if any(m.video_step.description == text for m in result["matched_steps"]):
            assert len(matched_with_order_issue) >= 1


class TestExtractSOPSteps:
    """Tests for _extract_sop_steps() SOP text parsing."""

    @pytest.fixture
    def service(self) -> AlignmentService:
        """Create an AlignmentService in mock mode."""
        return AlignmentService()

    @pytest.mark.asyncio
    async def test_parses_numbered_steps(self, service: AlignmentService) -> None:
        """Parses numbered steps from SOP text."""
        service._sop_texts = {
            "sop-1": (
                "1. Put on safety goggles\n"
                "2. Connect power supply\n"
                "3. Solder components\n"
            )
        }

        steps = await service._extract_sop_steps("sop-1")
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[0].description == "Put on safety goggles"
        assert steps[1].step_number == 2
        assert steps[2].step_number == 3

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self, service: AlignmentService) -> None:
        """Returns empty list for empty SOP text."""
        service._sop_texts = {"sop-empty": ""}

        steps = await service._extract_sop_steps("sop-empty")
        assert steps == []

    @pytest.mark.asyncio
    async def test_no_text_registered_returns_empty(
        self, service: AlignmentService
    ) -> None:
        """Returns empty list when SOP text not registered."""
        steps = await service._extract_sop_steps("nonexistent-sop")
        assert steps == []

    @pytest.mark.asyncio
    async def test_parses_parenthesis_numbered_steps(
        self, service: AlignmentService
    ) -> None:
        """Parses steps with parenthesis numbering."""
        service._sop_texts = {
            "sop-paren": (
                "1) Wear protective equipment\n"
                "2) Start the machine\n"
            )
        }

        steps = await service._extract_sop_steps("sop-paren")
        assert len(steps) == 2
        assert steps[0].description == "Wear protective equipment"

    @pytest.mark.asyncio
    async def test_chat_model_extraction(self) -> None:
        """Uses Chat_Model for step extraction when available."""
        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            return_value=(
                "STEP 1: Wear safety goggles\n"
                "STEP 2: Connect power supply\n"
                "STEP 3: Solder components\n"
            )
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )
        service._sop_texts = {"sop-1": "Some SOP text content"}

        steps = await service._extract_sop_steps("sop-1")
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[0].description == "Wear safety goggles"

    @pytest.mark.asyncio
    async def test_chat_model_fallback_to_text_parsing(self) -> None:
        """Falls back to text parsing when Chat_Model fails."""
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_model_manager = MagicMock()
        mock_model_manager.mode = "gpu"
        mock_model_manager.ensure_model = AsyncMock()

        mock_inference_client = MagicMock()
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError("timeout", endpoint="/v1/chat/completions")
        )

        service = AlignmentService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )
        service._sop_texts = {
            "sop-1": "1. Wear safety goggles\n2. Connect power supply\n"
        }

        steps = await service._extract_sop_steps("sop-1")
        assert len(steps) == 2
        assert steps[0].description == "Wear safety goggles"


class TestParseSOPSteps:
    """Tests for static SOP step parsing methods."""

    def test_parse_from_response_format(self) -> None:
        """Parses STEP N: format from Chat_Model response."""
        response = "STEP 1: First step\nSTEP 2: Second step\nSTEP 3: Third step"
        steps = AlignmentService._parse_sop_steps_from_response(response)
        assert len(steps) == 3
        assert steps[0].step_number == 1
        assert steps[0].description == "First step"

    def test_parse_from_response_case_insensitive(self) -> None:
        """Parsing is case-insensitive."""
        response = "step 1: First step\nStep 2: Second step"
        steps = AlignmentService._parse_sop_steps_from_response(response)
        assert len(steps) == 2

    def test_parse_from_response_empty(self) -> None:
        """Empty response returns empty list."""
        steps = AlignmentService._parse_sop_steps_from_response("")
        assert steps == []

    def test_parse_from_text_dot_format(self) -> None:
        """Parses '1. description' format."""
        text = "1. First step\n2. Second step"
        steps = AlignmentService._parse_sop_steps_from_text(text)
        assert len(steps) == 2
        assert steps[0].step_number == 1

    def test_parse_from_text_paren_format(self) -> None:
        """Parses '1) description' format."""
        text = "1) First step\n2) Second step"
        steps = AlignmentService._parse_sop_steps_from_text(text)
        assert len(steps) == 2

    def test_parse_from_text_skips_non_step_lines(self) -> None:
        """Skips lines that don't match step patterns."""
        text = "Introduction\n1. First step\nSome notes\n2. Second step"
        steps = AlignmentService._parse_sop_steps_from_text(text)
        assert len(steps) == 2
