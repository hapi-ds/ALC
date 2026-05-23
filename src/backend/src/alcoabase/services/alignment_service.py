"""Alignment service for video-to-SOP alignment operations.

Orchestrates frame extraction, vision analysis, audio transcription,
SOP linking, step comparison, and discrepancy report generation for
training video documents.

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Section 4)
    - Requirements: 5.1-5.9, 6.1-6.10, 7.1-7.9, 8.1-8.10, 9.1-9.10
"""

from __future__ import annotations

import asyncio
import base64
import logging
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from alcoabase.config import get_settings
from alcoabase.services.job_tracker import JobTracker

if TYPE_CHECKING:
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.knowledge_service import KnowledgeService
    from alcoabase.services.model_manager import ModelManager

logger = logging.getLogger(__name__)


class AudioExtractionError(Exception):
    """Raised when ffmpeg fails to extract audio from a video file (Req 7.6)."""

    pass


class SpeechModelUnavailableError(Exception):
    """Raised when the speech-to-text model is not available (Req 7.5)."""

    pass


# Frame analysis system prompt (Req 6.3)
_FRAME_ANALYSIS_PROMPT = (
    "You are analyzing a frame from a training video. "
    "Provide a concise description (maximum 200 words) covering:\n\n"
    "1. The primary action or procedure being performed\n"
    "2. Any equipment, tools, or materials visible\n"
    "3. Any safety equipment or PPE visible\n"
    "4. Any text or labels visible in the frame\n\n"
    "Output a concise, factual description of the observed step."
)

# Audio transcription constants (Req 7.1-7.9)
_AUDIO_CHUNK_DURATION_SECONDS = 30
_AUDIO_MOCK_PLACEHOLDER = (
    "[AUDIO_PENDING: Audio transcription requires speech-to-text model]"
)
_MAX_TRANSCRIPT_SEGMENTS = 1000

# Placeholder text for mock mode (Req 6.10)
_FRAME_MOCK_PLACEHOLDER = (
    "[FRAME_PENDING: Frame analysis requires Vision_Model]"
)


def should_abort_frame_analysis(total_frames: int, failure_count: int) -> bool:
    """Determine whether frame analysis should be aborted due to failures.

    The operation is aborted when more than 50% of frames fail analysis
    (Requirement 6.8). For zero total frames, always abort since no
    meaningful analysis is possible.

    Args:
        total_frames: Total number of frames to analyze (must be >= 0).
        failure_count: Number of frames that failed analysis (must be >= 0).

    Returns:
        True if the analysis should be aborted, False if it should continue.
    """
    if total_frames <= 0:
        return True
    return failure_count > total_frames / 2


# Default fallback values (Req 9.4, 9.9)
_SEVERITY_FALLBACK: str = "major"
_RECOMMENDATION_FALLBACK: str = "Manual review is required for this discrepancy."


def resolve_severity(
    model_response: str | None,
) -> str:
    """Resolve discrepancy severity from a Chat_Model response.

    Parses the model response to extract a severity classification.
    When the model fails (returns None or an unparseable response),
    falls back to "major" (Requirement 9.4).

    Args:
        model_response: The raw Chat_Model response text, or None if
            the model call failed (timeout, HTTP error, etc.).

    Returns:
        One of "critical", "major", or "minor". Defaults to "major"
        when the model response is None, empty, or unparseable.
    """
    if model_response is None or not model_response.strip():
        return _SEVERITY_FALLBACK

    response_upper = model_response.strip().upper()
    if "CRITICAL" in response_upper:
        return "critical"
    elif "MINOR" in response_upper:
        return "minor"
    elif "MAJOR" in response_upper:
        return "major"

    # Unparseable response: fallback to "major" (Req 9.4)
    return _SEVERITY_FALLBACK


def resolve_recommendation(
    model_response: str | None,
    max_length: int = 500,
) -> str:
    """Resolve discrepancy recommendation from a Chat_Model response.

    Parses the model response to extract a recommendation. When the model
    fails (returns None or empty), falls back to a generic text indicating
    manual review is required (Requirement 9.9).

    Args:
        model_response: The raw Chat_Model response text, or None if
            the model call failed (timeout, HTTP error, etc.).
        max_length: Maximum allowed recommendation length (default 500).

    Returns:
        The recommendation text (capped at max_length characters), or
        the generic fallback text when the model response is unavailable.
    """
    if model_response is None or not model_response.strip():
        return _RECOMMENDATION_FALLBACK

    return model_response.strip()[:max_length]


class DiscrepancySeverity(str, Enum):
    """Severity rating for alignment discrepancies."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class StepDescription:
    """A single step extracted from video frame analysis.

    Attributes:
        start_timestamp: Start time in seconds within the video.
        end_timestamp: End time in seconds within the video.
        description: Textual description of the observed action.
        frame_indices: List of frame indices belonging to this step.
        confidence: Confidence score (0.0-1.0).
        audio_transcript: Optional merged audio transcript for this step.
    """

    start_timestamp: float
    end_timestamp: float
    description: str
    frame_indices: list[int] = field(default_factory=list)
    confidence: float = 1.0
    audio_transcript: str | None = None


@dataclass
class SOPStep:
    """A procedural step extracted from an SOP document.

    Attributes:
        step_number: Sequential step number from the SOP.
        description: Textual description of the step.
    """

    step_number: int
    description: str


@dataclass
class MatchedStep:
    """A video step matched to an SOP step.

    Attributes:
        video_step: The video step that was matched.
        sop_step: The SOP step it was matched to.
        similarity_score: Cosine similarity score (0.0-1.0).
    """

    video_step: StepDescription
    sop_step: SOPStep
    similarity_score: float


@dataclass
class Discrepancy:
    """A discrepancy between video and SOP.

    Attributes:
        step_description: Description of the discrepant step.
        source: Origin of the step ("video" or "sop").
        severity: Severity rating of the discrepancy.
        recommendation: Suggested corrective action.
    """

    step_description: str
    source: str  # "video" or "sop"
    severity: DiscrepancySeverity
    recommendation: str


@dataclass
class OrderMismatch:
    """Steps matched but in wrong order.

    Attributes:
        video_step: The video step involved.
        sop_step: The SOP step involved.
        video_position: Position in the video sequence.
        sop_position: Position in the SOP sequence.
        severity: Severity rating of the mismatch.
    """

    video_step: StepDescription
    sop_step: SOPStep
    video_position: int
    sop_position: int
    severity: DiscrepancySeverity


@dataclass
class TranscriptSegment:
    """A single segment of transcribed audio.

    Attributes:
        start_time: Start time in seconds within the video.
        end_time: End time in seconds within the video.
        text: Transcribed text for this segment.
    """

    start_time: float
    end_time: float
    text: str


@dataclass
class FrameExtractionResult:
    """Result metadata from frame extraction.

    Attributes:
        frame_count: Total number of frames extracted.
        interval_used: Actual interval used (may be adjusted).
        video_duration: Duration of the video in seconds.
        output_dir: Directory where frames were stored.
    """

    frame_count: int
    interval_used: int
    video_duration: float
    output_dir: str


@dataclass
class SOPLinkRecord:
    """Association record linking a Video_Document to an SOP document.

    Attributes:
        video_document_uuid: UUID of the Video_Document.
        sop_document_uuid: UUID of the linked SOP document.
        sop_version: Version of the SOP at the time of linking.
        linked_at: Timestamp when the link was created.
    """

    video_document_uuid: str
    sop_document_uuid: str
    sop_version: str
    linked_at: datetime


# Maximum number of SOP documents that can be linked to a single video (Req 8.1)
_MAX_SOP_LINKS_PER_VIDEO = 10


class AlignmentService:
    """Orchestrates video-to-SOP alignment operations.

    Manages frame extraction, vision analysis, audio transcription,
    SOP linking, step comparison, and discrepancy report generation.

    Args:
        model_manager: ModelManager for ensuring models are loaded.
        inference_client: InferenceClient for vLLM API calls.
        knowledge_service: KnowledgeService for embedding generation.
    """

    def __init__(
        self,
        model_manager: ModelManager | None = None,
        inference_client: InferenceClient | None = None,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        """Initialize AlignmentService with optional dependencies.

        Args:
            model_manager: Optional ModelManager for model loading.
            inference_client: Optional InferenceClient for vLLM API calls.
            knowledge_service: Optional KnowledgeService for embeddings.
        """
        self._settings = get_settings()
        self._model_manager = model_manager
        self._inference_client = inference_client
        self._knowledge_service = knowledge_service
        self._job_tracker = JobTracker()

    async def extract_frames(
        self,
        document_uuid: str,
        interval_seconds: int = 5,
    ) -> str:
        """Extract frames from a video at the specified interval.

        Downloads video from MinIO, runs ffmpeg to extract PNG frames.
        Auto-adjusts interval if frame count would exceed VIDEO_MAX_FRAMES.
        Caps resolution at 1920x1080.

        Args:
            document_uuid: UUID of the Video_Document.
            interval_seconds: Seconds between frame extractions (1-60).

        Returns:
            job_id for tracking the async operation.

        Raises:
            ValueError: If interval_seconds is out of range [1, 60].
            FileNotFoundError: If video file not found.
        """
        # Validate interval range
        if interval_seconds < 1 or interval_seconds > 60:
            raise ValueError(
                f"interval_seconds must be between 1 and 60, got {interval_seconds}"
            )

        # Create job for tracking (uses in-memory tracking for now)
        job_id = str(uuid.uuid4())

        # Run extraction in background
        asyncio.create_task(
            self._do_extract_frames(job_id, document_uuid, interval_seconds)
        )

        return job_id

    async def _do_extract_frames(
        self,
        job_id: str,
        document_uuid: str,
        interval_seconds: int,
    ) -> None:
        """Perform the actual frame extraction work.

        Downloads the video, probes duration, adjusts interval if needed,
        runs ffmpeg, and stores metadata. Cleans up on failure.

        Args:
            job_id: The job ID for progress tracking.
            document_uuid: UUID of the Video_Document.
            interval_seconds: Requested interval between frames.
        """
        output_dir = tempfile.mkdtemp(prefix=f"frames_{document_uuid}_")

        try:
            # Download video from MinIO (placeholder: use storage service)
            video_path = await self._download_video(document_uuid, output_dir)

            # Get video duration via ffprobe
            duration = await self._get_video_duration(video_path)

            # Auto-adjust interval if frame count would exceed max
            max_frames = self._settings.video_max_frames
            adjusted_interval = self._calculate_interval(
                duration, interval_seconds, max_frames
            )

            # Run ffmpeg to extract frames
            frame_count = await self._run_ffmpeg_extract(
                video_path, output_dir, adjusted_interval
            )

            # Store frame metadata
            self._frame_metadata: dict[str, FrameExtractionResult] = getattr(
                self, "_frame_metadata", {}
            )
            self._frame_metadata[document_uuid] = FrameExtractionResult(
                frame_count=frame_count,
                interval_used=adjusted_interval,
                video_duration=duration,
                output_dir=output_dir,
            )

            logger.info(
                "Frame extraction completed for %s: %d frames at %ds interval",
                document_uuid,
                frame_count,
                adjusted_interval,
            )

        except Exception as e:
            # Clean up partially extracted frames on failure
            self._cleanup_frames(output_dir)
            logger.error(
                "Frame extraction failed for %s: %s", document_uuid, str(e)
            )
            raise

    async def _download_video(
        self, document_uuid: str, output_dir: str
    ) -> str:
        """Download video file from MinIO to a local temp path.

        Args:
            document_uuid: UUID of the Video_Document.
            output_dir: Directory to store the downloaded video.

        Returns:
            Path to the downloaded video file.

        Raises:
            FileNotFoundError: If the video file cannot be found.
        """
        from alcoabase.services.storage_service import StorageService

        storage = StorageService()
        video_key = f"documents/{document_uuid}/video"
        video_path = os.path.join(output_dir, "source_video")

        try:
            video_bytes = await storage.download_file(video_key)
            with open(video_path, "wb") as f:
                f.write(video_bytes)
            return video_path
        except Exception as e:
            raise FileNotFoundError(
                f"Video file not found for document {document_uuid}: {e}"
            ) from e

    async def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe.

        Args:
            video_path: Path to the video file.

        Returns:
            Duration of the video in seconds.

        Raises:
            RuntimeError: If ffprobe fails to extract duration.
        """
        ffprobe_path = self._settings.ffprobe_path
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffprobe failed: {result.stderr.strip()}"
                )
            return float(result.stdout.strip())
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("ffprobe timed out after 30 seconds") from e
        except ValueError as e:
            raise RuntimeError(
                f"Could not parse duration from ffprobe output: {result.stdout}"
            ) from e

    @staticmethod
    def _calculate_interval(
        duration: float,
        requested_interval: int,
        max_frames: int,
    ) -> int:
        """Calculate the actual interval, adjusting if frames would exceed max.

        If duration / requested_interval would produce more than max_frames,
        the interval is increased to cap at max_frames.

        Args:
            duration: Video duration in seconds.
            requested_interval: User-requested interval in seconds.
            max_frames: Maximum allowed frame count.

        Returns:
            The adjusted interval in seconds (>= requested_interval).
        """
        estimated_frames = math.ceil(duration / requested_interval)
        if estimated_frames <= max_frames:
            return requested_interval

        # Increase interval to cap at max_frames
        adjusted = math.ceil(duration / max_frames)
        logger.info(
            "Auto-adjusted interval from %ds to %ds to cap frames at %d "
            "(video duration: %.1fs)",
            requested_interval,
            adjusted,
            max_frames,
            duration,
        )
        return adjusted

    async def _run_ffmpeg_extract(
        self,
        video_path: str,
        output_dir: str,
        interval: int,
    ) -> int:
        """Run ffmpeg to extract frames at the given interval.

        Uses the ffmpeg command with fps filter and resolution cap at 1920x1080.

        Args:
            video_path: Path to the source video file.
            output_dir: Directory to store extracted frame PNGs.
            interval: Interval in seconds between frames.

        Returns:
            Number of frames extracted.

        Raises:
            RuntimeError: If ffmpeg fails.
        """
        ffmpeg_path = self._settings.ffmpeg_path
        output_pattern = os.path.join(output_dir, "frame_%05d.png")

        # Build ffmpeg command with resolution cap at 1920x1080
        # Scale filter: min(1920,iw):min(1080,ih) with aspect ratio preservation
        vf_filter = (
            f"fps=1/{interval},"
            f"scale='min(1920,iw)':min(1080,ih):"
            f"force_original_aspect_ratio=decrease"
        )

        cmd = [
            ffmpeg_path,
            "-i", video_path,
            "-vf", vf_filter,
            "-vsync", "vfr",
            output_pattern,
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for long videos
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg frame extraction failed: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                "ffmpeg frame extraction timed out after 600 seconds"
            ) from e

        # Count extracted frames
        frame_count = len(
            [
                f
                for f in os.listdir(output_dir)
                if f.startswith("frame_") and f.endswith(".png")
            ]
        )

        if frame_count == 0:
            raise RuntimeError(
                "ffmpeg produced no frames — video may be corrupt or empty"
            )

        return frame_count

    @staticmethod
    def _cleanup_frames(output_dir: str) -> None:
        """Remove the frame extraction directory and all contents.

        Args:
            output_dir: Directory to remove.
        """
        try:
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
                logger.debug("Cleaned up frame directory: %s", output_dir)
        except OSError as e:
            logger.warning(
                "Failed to clean up frame directory %s: %s", output_dir, e
            )

    async def analyze_frames(
        self,
        document_uuid: str,
    ) -> str:
        """Analyze extracted frames via Vision_Model.

        Processes frames sequentially, consolidates similar descriptions
        into steps using embedding cosine similarity (threshold 0.85).

        Args:
            document_uuid: UUID of the Video_Document.

        Returns:
            job_id for tracking the async operation.

        Raises:
            ValueError: If frame extraction not completed.
        """
        # Validate that frame extraction has been completed (Req 6.1)
        frame_metadata = getattr(self, "_frame_metadata", {})
        if document_uuid not in frame_metadata:
            raise ValueError(
                "Frame extraction must be completed before frame analysis "
                "can be performed."
            )

        # Create job for tracking
        job_id = str(uuid.uuid4())

        # Run analysis in background
        asyncio.create_task(
            self._do_analyze_frames(job_id, document_uuid)
        )

        return job_id

    async def _do_analyze_frames(
        self,
        job_id: str,
        document_uuid: str,
    ) -> None:
        """Perform the actual frame analysis work.

        Loads extracted frames, sends each to the Vision_Model sequentially,
        consolidates similar frames into steps, and stores the Step_Sequence.

        Args:
            job_id: The job ID for progress tracking.
            document_uuid: UUID of the Video_Document.
        """
        extraction_result = self._frame_metadata[document_uuid]
        output_dir = extraction_result.output_dir
        interval_used = extraction_result.interval_used
        frame_count = extraction_result.frame_count

        try:
            # Load frame file paths sorted by index
            frame_files = self._load_frame_files(output_dir)

            if not frame_files:
                raise RuntimeError(
                    "No frame files found in extraction directory"
                )

            # Analyze each frame sequentially (Req 6.4)
            descriptions: list[str | None] = []
            failure_count = 0

            for i, frame_path in enumerate(frame_files):
                description = await self._analyze_single_frame(frame_path, i)
                descriptions.append(description)
                if description is None:
                    failure_count += 1

                # Abort if > 50% fail (Req 6.8)
                total_processed = i + 1
                if failure_count > total_processed / 2 and total_processed >= 2:
                    # Check if we've already exceeded 50% of total frames
                    if failure_count > frame_count / 2:
                        logger.error(
                            "Frame analysis aborted for %s: %d/%d frames failed "
                            "(> 50%% threshold)",
                            document_uuid,
                            failure_count,
                            total_processed,
                        )
                        # Clean up partial results
                        self._step_sequences: dict[str, list[StepDescription]] = (
                            getattr(self, "_step_sequences", {})
                        )
                        self._step_sequences.pop(document_uuid, None)
                        raise RuntimeError(
                            f"Frame analysis aborted: {failure_count}/{total_processed} "
                            f"frames failed analysis (exceeds 50% threshold)"
                        )

            # Final check: abort if > 50% of all frames failed (Req 6.8)
            if failure_count > frame_count / 2:
                logger.error(
                    "Frame analysis aborted for %s: %d/%d frames failed "
                    "(> 50%% threshold)",
                    document_uuid,
                    failure_count,
                    frame_count,
                )
                self._step_sequences: dict[str, list[StepDescription]] = (
                    getattr(self, "_step_sequences", {})
                )
                self._step_sequences.pop(document_uuid, None)
                raise RuntimeError(
                    f"Frame analysis aborted: {failure_count}/{frame_count} "
                    f"frames failed analysis (exceeds 50% threshold)"
                )

            # Consolidate similar frames into steps (Req 6.5)
            steps = await self._consolidate_frames_into_steps(
                descriptions=descriptions,
                interval_used=interval_used,
            )

            # Store Step_Sequence in memory (Req 6.6)
            self._step_sequences: dict[str, list[StepDescription]] = getattr(
                self, "_step_sequences", {}
            )
            self._step_sequences[document_uuid] = steps

            logger.info(
                "Frame analysis completed for %s: %d frames → %d steps "
                "(%d frames failed)",
                document_uuid,
                frame_count,
                len(steps),
                failure_count,
            )

        except Exception as e:
            logger.error(
                "Frame analysis failed for %s: %s", document_uuid, str(e)
            )
            raise

    @staticmethod
    def _load_frame_files(output_dir: str) -> list[str]:
        """Load and sort extracted frame PNG file paths.

        Args:
            output_dir: Directory containing extracted frames.

        Returns:
            Sorted list of absolute paths to frame PNG files.
        """
        frame_files = [
            os.path.join(output_dir, f)
            for f in sorted(os.listdir(output_dir))
            if f.startswith("frame_") and f.endswith(".png")
        ]
        return frame_files

    async def _analyze_single_frame(
        self,
        frame_path: str,
        frame_index: int,
    ) -> str | None:
        """Analyze a single frame via the Vision_Model.

        In mock mode, returns a placeholder description.
        In gpu/cpu mode, sends the frame to the Vision_Model with a
        training-video-specific prompt.

        Args:
            frame_path: Path to the frame PNG file.
            frame_index: Index of the frame in the sequence.

        Returns:
            Description text, or None if analysis failed.
        """
        # Mock mode: return placeholder (Req 6.10)
        if (
            self._model_manager is None
            or self._inference_client is None
            or self._model_manager.mode not in ("gpu", "cpu")
        ):
            return _FRAME_MOCK_PLACEHOLDER

        from alcoabase.services.inference_client import (
            InferenceConnectionError,
            InferenceError,
            InferenceTimeoutError,
        )
        from alcoabase.services.model_manager import ModelRole

        try:
            # Ensure OCR/Vision model is loaded (Req 6.1)
            await self._model_manager.ensure_model(ModelRole.OCR)

            # Read and encode frame
            with open(frame_path, "rb") as f:
                frame_bytes = f.read()
            b64_image = base64.b64encode(frame_bytes).decode("utf-8")

            # Build multimodal message with frame-specific prompt (Req 6.3)
            model_name = self._settings.model_ocr_name
            messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": _FRAME_ANALYSIS_PROMPT,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_image}",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Analyze this training video frame and describe "
                                "the action being performed."
                            ),
                        },
                    ],
                },
            ]

            # Send to Vision_Model with 60s timeout (Req 6.4)
            description = await self._inference_client.chat_completion(
                model=model_name,
                messages=messages,
                max_tokens=512,
                temperature=0.1,
                timeout=60.0,
            )

            if description and description.strip():
                return description.strip()
            return None

        except (InferenceTimeoutError, InferenceError, InferenceConnectionError) as e:
            # Mark frame as unanalyzed, continue (Req 6.7)
            logger.warning(
                "Vision_Model failed for frame %d (%s): %s",
                frame_index,
                frame_path,
                str(e),
            )
            return None
        except OSError as e:
            logger.warning(
                "Failed to read frame %d (%s): %s",
                frame_index,
                frame_path,
                str(e),
            )
            return None

    async def _consolidate_frames_into_steps(
        self,
        descriptions: list[str | None],
        interval_used: int,
    ) -> list[StepDescription]:
        """Consolidate consecutive similar frames into steps.

        Generates embeddings for frame descriptions and merges consecutive
        frames with cosine similarity > 0.85 into single steps.

        Args:
            descriptions: List of frame descriptions (None for failed frames).
            interval_used: Interval in seconds between frames.

        Returns:
            List of StepDescription objects forming the Step_Sequence.
        """
        threshold = self._settings.frame_similarity_threshold

        # Filter out None descriptions but track indices
        valid_frames: list[tuple[int, str]] = [
            (i, desc) for i, desc in enumerate(descriptions) if desc is not None
        ]

        if not valid_frames:
            return []

        # Generate embeddings for all valid descriptions
        valid_texts = [desc for _, desc in valid_frames]
        embeddings = await self._generate_frame_embeddings(valid_texts)

        # Group consecutive frames by similarity (Req 6.5)
        groups: list[list[int]] = []  # Each group is a list of valid_frames indices
        current_group: list[int] = [0]

        for i in range(1, len(valid_frames)):
            similarity = self._cosine_similarity(embeddings[i - 1], embeddings[i])
            if similarity > threshold:
                current_group.append(i)
            else:
                groups.append(current_group)
                current_group = [i]

        # Don't forget the last group
        groups.append(current_group)

        # Convert groups to StepDescription objects
        steps: list[StepDescription] = []
        total_frames = len(descriptions)

        for step_idx, group in enumerate(groups):
            # Get frame indices from the original sequence
            frame_indices = [valid_frames[g][0] for g in group]

            # Calculate timestamps
            start_frame_idx = frame_indices[0]
            end_frame_idx = frame_indices[-1]
            start_timestamp = float(start_frame_idx * interval_used)
            end_timestamp = float((end_frame_idx + 1) * interval_used)

            # Use the first frame's description as the step description
            # (representative of the group)
            description = valid_frames[group[0]][1]

            # Calculate confidence: ratio of analyzed frames in this step's range
            # (Req 6.6)
            range_start = frame_indices[0]
            range_end = frame_indices[-1]
            total_in_range = range_end - range_start + 1
            analyzed_in_range = len(frame_indices)
            confidence = analyzed_in_range / total_in_range if total_in_range > 0 else 1.0

            steps.append(
                StepDescription(
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    description=description,
                    frame_indices=frame_indices,
                    confidence=confidence,
                )
            )

        return steps

    async def _generate_frame_embeddings(
        self, texts: list[str]
    ) -> list[list[float]]:
        """Generate embeddings for frame descriptions.

        Uses KnowledgeService if available, otherwise generates mock embeddings.

        Args:
            texts: List of description texts to embed.

        Returns:
            List of embedding vectors.
        """
        if self._knowledge_service is not None:
            return await self._knowledge_service.generate_embeddings(texts)

        # Fallback: use inference client directly if available
        if (
            self._inference_client is not None
            and self._model_manager is not None
            and self._model_manager.mode in ("gpu", "cpu")
        ):
            from alcoabase.services.model_manager import ModelRole

            await self._model_manager.ensure_model(ModelRole.EMBEDDING)
            model_name = self._settings.model_embedding_name
            return await self._inference_client.create_embeddings(
                model=model_name,
                inputs=texts,
            )

        # Mock mode: generate deterministic mock embeddings
        import random

        dimension = self._settings.model_embedding_dimension
        embeddings: list[list[float]] = []
        for text in texts:
            seed = hash(text) % (2**32)
            rng = random.Random(seed)
            vec = [rng.gauss(0, 1) for _ in range(dimension)]
            magnitude = sum(v * v for v in vec) ** 0.5
            if magnitude > 0:
                vec = [v / magnitude for v in vec]
            embeddings.append(vec)
        return embeddings

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec_a: First vector.
            vec_b: Second vector.

        Returns:
            Cosine similarity value between -1.0 and 1.0.
        """
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = sum(a * a for a in vec_a) ** 0.5
        magnitude_b = sum(b * b for b in vec_b) ** 0.5

        if magnitude_a == 0.0 or magnitude_b == 0.0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    async def transcribe_audio(
        self,
        document_uuid: str,
    ) -> str:
        """Extract and transcribe audio from video.

        Extracts audio via ffmpeg (WAV 16kHz mono), segments into
        30-second chunks, processes through speech-to-text model.

        Args:
            document_uuid: UUID of the Video_Document.

        Returns:
            job_id for tracking the async operation.
        """
        # Create job for tracking
        job_id = str(uuid.uuid4())

        # Run transcription in background
        asyncio.create_task(
            self._do_transcribe_audio(job_id, document_uuid)
        )

        return job_id

    async def _do_transcribe_audio(
        self,
        job_id: str,
        document_uuid: str,
    ) -> None:
        """Perform the actual audio transcription work.

        1. Download video from MinIO
        2. Extract audio via ffmpeg (WAV 16kHz mono)
        3. Segment into 30-second chunks
        4. Process each chunk through speech-to-text model
        5. Store transcript segments with timestamps

        Args:
            job_id: The job ID for progress tracking.
            document_uuid: UUID of the Video_Document.
        """
        output_dir = tempfile.mkdtemp(prefix=f"audio_{document_uuid}_")

        try:
            # Mock mode: return placeholder transcript (Req 7.9)
            if (
                self._model_manager is None
                or self._model_manager.mode == "mock"
            ):
                placeholder_segment = TranscriptSegment(
                    start_time=0.0,
                    end_time=30.0,
                    text=_AUDIO_MOCK_PLACEHOLDER,
                )
                self._transcripts: dict[str, list[TranscriptSegment]] = getattr(
                    self, "_transcripts", {}
                )
                self._transcripts[document_uuid] = [placeholder_segment]
                logger.info(
                    "Mock mode: stored placeholder transcript for %s",
                    document_uuid,
                )
                return

            # Download video from MinIO
            video_path = await self._download_video(document_uuid, output_dir)

            # Extract audio via ffmpeg (WAV 16kHz mono) (Req 7.1)
            audio_path = await self._extract_audio_track(video_path, output_dir)

            # If no audio track, store empty transcript (Req 7.4)
            if audio_path is None:
                self._transcripts: dict[str, list[TranscriptSegment]] = getattr(
                    self, "_transcripts", {}
                )
                self._transcripts[document_uuid] = []
                logger.info(
                    "No audio track found for %s, stored empty transcript",
                    document_uuid,
                )
                return

            # Get audio duration
            audio_duration = await self._get_audio_duration(audio_path)

            # Segment into 30-second chunks (Req 7.2)
            chunk_count = math.ceil(audio_duration / _AUDIO_CHUNK_DURATION_SECONDS)
            chunk_count = min(chunk_count, _MAX_TRANSCRIPT_SEGMENTS)

            # Process each chunk through speech-to-text model (Req 7.2)
            segments: list[TranscriptSegment] = []
            for i in range(chunk_count):
                start_time = i * _AUDIO_CHUNK_DURATION_SECONDS
                end_time = min(
                    (i + 1) * _AUDIO_CHUNK_DURATION_SECONDS, audio_duration
                )

                # Extract chunk audio
                chunk_path = os.path.join(output_dir, f"chunk_{i:05d}.wav")
                await self._extract_audio_chunk(
                    audio_path, chunk_path, start_time, end_time
                )

                # Transcribe chunk
                text = await self._transcribe_chunk(chunk_path, i)

                if text:
                    segments.append(
                        TranscriptSegment(
                            start_time=start_time,
                            end_time=end_time,
                            text=text,
                        )
                    )

            # Store transcript (Req 7.3)
            self._transcripts: dict[str, list[TranscriptSegment]] = getattr(
                self, "_transcripts", {}
            )
            self._transcripts[document_uuid] = segments[:_MAX_TRANSCRIPT_SEGMENTS]

            logger.info(
                "Audio transcription completed for %s: %d segments",
                document_uuid,
                len(segments),
            )

        except AudioExtractionError:
            # Re-raise extraction failures (Req 7.6)
            raise
        except SpeechModelUnavailableError:
            # Re-raise model unavailable (Req 7.5)
            raise
        except Exception as e:
            logger.error(
                "Audio transcription failed for %s: %s", document_uuid, str(e)
            )
            raise
        finally:
            # Clean up temporary files
            self._cleanup_frames(output_dir)

    async def _extract_audio_track(
        self,
        video_path: str,
        output_dir: str,
    ) -> str | None:
        """Extract audio track from video as WAV 16kHz mono.

        Uses ffmpeg: ffmpeg -i {video_path} -vn -acodec pcm_s16le -ar 16000 -ac 1 {output.wav}

        Args:
            video_path: Path to the source video file.
            output_dir: Directory to store the extracted audio.

        Returns:
            Path to the extracted WAV file, or None if no audio track.

        Raises:
            AudioExtractionError: If ffmpeg fails for reasons other than
                missing audio track.
        """
        ffmpeg_path = self._settings.ffmpeg_path
        audio_path = os.path.join(output_dir, "audio.wav")

        cmd = [
            ffmpeg_path,
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path,
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for long videos
            )

            if result.returncode != 0:
                stderr = result.stderr.strip().lower()
                # Check if the error indicates no audio stream
                if (
                    "does not contain any stream" in stderr
                    or "no audio" in stderr
                    or "output file #0 does not contain any stream" in stderr
                    or "stream map" in stderr
                ):
                    logger.info(
                        "No audio track found in video: %s", video_path
                    )
                    return None

                raise AudioExtractionError(
                    f"ffmpeg audio extraction failed: {result.stderr.strip()}"
                )

        except subprocess.TimeoutExpired as e:
            raise AudioExtractionError(
                "ffmpeg audio extraction timed out after 300 seconds"
            ) from e

        # Verify the output file exists and has content
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            logger.info("No audio track found in video: %s", video_path)
            return None

        return audio_path

    async def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds using ffprobe.

        Args:
            audio_path: Path to the audio WAV file.

        Returns:
            Duration of the audio in seconds.

        Raises:
            RuntimeError: If ffprobe fails to extract duration.
        """
        ffprobe_path = self._settings.ffprobe_path
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffprobe failed on audio: {result.stderr.strip()}"
                )
            return float(result.stdout.strip())
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                "ffprobe timed out on audio after 30 seconds"
            ) from e
        except ValueError as e:
            raise RuntimeError(
                f"Could not parse audio duration: {result.stdout}"
            ) from e

    async def _extract_audio_chunk(
        self,
        audio_path: str,
        chunk_path: str,
        start_time: float,
        end_time: float,
    ) -> None:
        """Extract a time-range chunk from the audio file.

        Args:
            audio_path: Path to the full audio WAV file.
            chunk_path: Path to write the chunk WAV file.
            start_time: Start time in seconds.
            end_time: End time in seconds.

        Raises:
            AudioExtractionError: If ffmpeg fails to extract the chunk.
        """
        ffmpeg_path = self._settings.ffmpeg_path
        duration = end_time - start_time

        cmd = [
            ffmpeg_path,
            "-i", audio_path,
            "-ss", str(start_time),
            "-t", str(duration),
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            chunk_path,
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise AudioExtractionError(
                    f"ffmpeg chunk extraction failed: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired as e:
            raise AudioExtractionError(
                f"ffmpeg chunk extraction timed out for segment "
                f"{start_time:.1f}-{end_time:.1f}s"
            ) from e

    async def _transcribe_chunk(
        self,
        chunk_path: str,
        chunk_index: int,
    ) -> str | None:
        """Transcribe a single audio chunk via speech-to-text model.

        Args:
            chunk_path: Path to the audio chunk WAV file.
            chunk_index: Index of the chunk for logging.

        Returns:
            Transcribed text, or None if transcription failed.

        Raises:
            SpeechModelUnavailableError: If the speech-to-text model is
                not available (Req 7.5).
        """
        if self._inference_client is None:
            raise SpeechModelUnavailableError(
                "Audio transcription is not available: "
                "no inference client configured"
            )

        from alcoabase.services.inference_client import (
            InferenceConnectionError,
            InferenceError,
            InferenceTimeoutError,
        )

        try:
            # Read chunk audio and encode as base64
            with open(chunk_path, "rb") as f:
                audio_bytes = f.read()
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

            # Use chat completion with audio transcription prompt
            model_name = self._settings.model_ocr_name
            messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": (
                        "You are a speech-to-text transcription system. "
                        "Transcribe the audio content accurately. "
                        "Output only the transcribed text, nothing else."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "audio_url",
                            "audio_url": {
                                "url": f"data:audio/wav;base64,{b64_audio}",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Transcribe this audio segment.",
                        },
                    ],
                },
            ]

            text = await self._inference_client.chat_completion(
                model=model_name,
                messages=messages,
                max_tokens=512,
                temperature=0.0,
                timeout=60.0,
            )

            if text and text.strip():
                return text.strip()
            return None

        except InferenceConnectionError as e:
            raise SpeechModelUnavailableError(
                f"Audio transcription is not available: "
                f"speech-to-text model unreachable: {e}"
            ) from e
        except (InferenceTimeoutError, InferenceError) as e:
            logger.warning(
                "Transcription failed for chunk %d: %s", chunk_index, str(e)
            )
            return None
        except OSError as e:
            logger.warning(
                "Failed to read audio chunk %d (%s): %s",
                chunk_index,
                chunk_path,
                str(e),
            )
            return None

    def merge_transcript_with_steps(
        self,
        document_uuid: str,
    ) -> list[StepDescription]:
        """Merge audio transcript segments with the Step_Sequence.

        Assigns each transcript segment to the step whose timestamp range
        overlaps with the segment's time range by the greatest duration.
        Enriches each step with concatenated text of all assigned transcript
        segments in chronological order (Req 7.7).

        Args:
            document_uuid: UUID of the Video_Document.

        Returns:
            Updated list of StepDescription with audio_transcript populated.
        """
        step_sequences = getattr(self, "_step_sequences", {})
        transcripts = getattr(self, "_transcripts", {})

        steps = step_sequences.get(document_uuid, [])
        segments = transcripts.get(document_uuid, [])

        if not steps or not segments:
            return steps

        # For each transcript segment, find the step with greatest overlap
        step_assignments: dict[int, list[TranscriptSegment]] = {
            i: [] for i in range(len(steps))
        }

        for segment in segments:
            best_step_idx = -1
            best_overlap = 0.0

            for step_idx, step in enumerate(steps):
                # Calculate overlap duration
                overlap_start = max(segment.start_time, step.start_timestamp)
                overlap_end = min(segment.end_time, step.end_timestamp)
                overlap = max(0.0, overlap_end - overlap_start)

                if overlap > best_overlap:
                    best_overlap = overlap
                    best_step_idx = step_idx

            if best_step_idx >= 0 and best_overlap > 0.0:
                step_assignments[best_step_idx].append(segment)

        # Concatenate assigned segments into each step's audio_transcript
        for step_idx, assigned_segments in step_assignments.items():
            if assigned_segments:
                # Sort by start_time for chronological order
                assigned_segments.sort(key=lambda s: s.start_time)
                concatenated = " ".join(seg.text for seg in assigned_segments)
                steps[step_idx].audio_transcript = concatenated

        return steps

    async def link_sop(
        self,
        video_document_uuid: str,
        sop_document_uuid: str,
        sop_version: str | None = None,
        company_id: int = 0,
    ) -> dict[str, Any]:
        """Link an SOP document to a Video_Document.

        Validates SOP exists, belongs to same tenant, and is of type SOP.
        Maximum 10 SOPs per video.

        Args:
            video_document_uuid: UUID of the Video_Document.
            sop_document_uuid: UUID of the SOP document to link.
            sop_version: Optional specific version (defaults to latest).
            company_id: Tenant company ID for validation.

        Returns:
            Dictionary with link details.

        Raises:
            ValueError: If validation fails or max links reached.
        """
        # Initialize in-memory SOP links storage (Req 8.1)
        # Key: video_document_uuid -> list of SOPLinkRecord
        self._sop_links: dict[str, list[SOPLinkRecord]] = getattr(
            self, "_sop_links", {}
        )

        # Initialize in-memory SOP document registry for validation
        # Key: sop_document_uuid -> dict with company_id, document_type, tags, version
        self._sop_documents: dict[str, dict[str, Any]] = getattr(
            self, "_sop_documents", {}
        )

        # 1. Validate SOP document exists (Req 8.2)
        if sop_document_uuid not in self._sop_documents:
            raise ValueError(
                f"SOP document '{sop_document_uuid}' not found"
            )

        sop_doc = self._sop_documents[sop_document_uuid]

        # 2. Validate same tenant / company_id (Req 8.2)
        if sop_doc.get("company_id") != company_id:
            raise ValueError(
                f"SOP document '{sop_document_uuid}' belongs to a different tenant"
            )

        # 3. Validate document_type is "SOP" or tags contain "SOP" (Req 8.2)
        doc_type = sop_doc.get("document_type", "")
        tags = sop_doc.get("tags", [])
        if doc_type != "SOP" and "SOP" not in tags:
            raise ValueError(
                f"Document '{sop_document_uuid}' is not an SOP document "
                f"(document_type='{doc_type}', tags={tags})"
            )

        # Get existing links for this video
        existing_links = self._sop_links.get(video_document_uuid, [])

        # 4. Check max 10 links per video (Req 8.1, 8.10)
        if len(existing_links) >= _MAX_SOP_LINKS_PER_VIDEO:
            raise ValueError(
                f"Maximum number of linked SOPs ({_MAX_SOP_LINKS_PER_VIDEO}) "
                f"has been reached for video '{video_document_uuid}'"
            )

        # 5. Check no duplicate link (Req 8.3)
        for link in existing_links:
            if link.sop_document_uuid == sop_document_uuid:
                raise ValueError(
                    f"SOP document '{sop_document_uuid}' is already linked "
                    f"to video '{video_document_uuid}'"
                )

        # 6. Determine SOP version (use provided or default from registry)
        resolved_version = sop_version or sop_doc.get("version", "1.0")

        # 7. Create association record (Req 8.1)
        linked_at = datetime.now(timezone.utc)
        link_record = SOPLinkRecord(
            video_document_uuid=video_document_uuid,
            sop_document_uuid=sop_document_uuid,
            sop_version=resolved_version,
            linked_at=linked_at,
        )

        # Store the link
        if video_document_uuid not in self._sop_links:
            self._sop_links[video_document_uuid] = []
        self._sop_links[video_document_uuid].append(link_record)

        logger.info(
            "Linked SOP '%s' (v%s) to video '%s' (total links: %d)",
            sop_document_uuid,
            resolved_version,
            video_document_uuid,
            len(self._sop_links[video_document_uuid]),
        )

        # Return dict with link details
        return {
            "video_document_uuid": video_document_uuid,
            "sop_document_uuid": sop_document_uuid,
            "sop_version": resolved_version,
            "linked_at": linked_at,
        }

    def register_sop_document(
        self,
        document_uuid: str,
        company_id: int,
        document_type: str = "SOP",
        tags: list[str] | None = None,
        version: str = "1.0",
    ) -> None:
        """Register an SOP document in the in-memory registry for validation.

        This is a helper for testing and in-memory operation until the API
        layer handles DB lookups.

        Args:
            document_uuid: UUID of the SOP document.
            company_id: Tenant company ID.
            document_type: Document type (default "SOP").
            tags: Optional list of tags.
            version: Document version (default "1.0").
        """
        self._sop_documents: dict[str, dict[str, Any]] = getattr(
            self, "_sop_documents", {}
        )
        self._sop_documents[document_uuid] = {
            "company_id": company_id,
            "document_type": document_type,
            "tags": tags or [],
            "version": version,
        }

    def register_sop_text(
        self,
        document_uuid: str,
        text_content: str,
    ) -> None:
        """Register SOP text content for alignment processing.

        This is a helper for testing and in-memory operation until the API
        layer handles DB lookups for SOP document text.

        Args:
            document_uuid: UUID of the SOP document.
            text_content: Full text content of the SOP document.
        """
        self._sop_texts: dict[str, str] = getattr(self, "_sop_texts", {})
        self._sop_texts[document_uuid] = text_content

    async def align(
        self,
        document_uuid: str,
    ) -> str:
        """Run alignment between video steps and linked SOPs.

        1. Load Step_Sequence for the video
        2. For each linked SOP: extract procedural steps via Chat_Model
        3. Compare using semantic similarity (threshold 0.7)
        4. Classify severity of each discrepancy via Chat_Model
        5. Generate and store Discrepancy_Report

        Args:
            document_uuid: UUID of the Video_Document.

        Returns:
            job_id for tracking the async operation.

        Raises:
            ValueError: If Step_Sequence not available or no SOPs linked.
        """
        # 1. Validate Step_Sequence exists (Req 8.8)
        step_sequences = getattr(self, "_step_sequences", {})
        if document_uuid not in step_sequences or not step_sequences[document_uuid]:
            raise ValueError(
                "Frame analysis must be completed before alignment can be performed."
            )

        # 2. Validate at least one SOP is linked (Req 8.9)
        sop_links = getattr(self, "_sop_links", {})
        linked_sops = sop_links.get(document_uuid, [])
        if not linked_sops:
            raise ValueError(
                "At least one SOP must be linked before alignment can be performed."
            )

        # Create job for tracking
        job_id = str(uuid.uuid4())

        # Run alignment in background
        asyncio.create_task(
            self._do_align(job_id, document_uuid)
        )

        return job_id

    async def _do_align(
        self,
        job_id: str,
        document_uuid: str,
    ) -> None:
        """Perform the actual alignment work.

        For each linked SOP:
        1. Extract procedural steps via Chat_Model
        2. Compare video steps vs SOP steps using semantic similarity
        3. Classify discrepancies (matched/missing/extra/order_mismatch)
        4. Assess severity via Chat_Model (fallback to "major")
        5. Generate recommendations via Chat_Model (fallback to generic)
        6. Calculate alignment_score and store Discrepancy_Report

        Args:
            job_id: The job ID for progress tracking.
            document_uuid: UUID of the Video_Document.
        """
        try:
            video_steps = self._step_sequences[document_uuid]
            linked_sops = self._sop_links[document_uuid]
            threshold = self._settings.alignment_match_threshold

            # Process each linked SOP independently (Req 8.4)
            for link_record in linked_sops:
                sop_uuid = link_record.sop_document_uuid

                # Extract SOP steps via Chat_Model (Req 8.5)
                sop_steps = await self._extract_sop_steps(sop_uuid)

                # Skip if no steps could be extracted (Req 8.6)
                if not sop_steps:
                    logger.warning(
                        "No procedural steps identified in SOP '%s', skipping alignment",
                        sop_uuid,
                    )
                    continue

                # Compare video steps vs SOP steps (Req 8.7)
                comparison = await self._compare_steps(
                    video_steps, sop_steps, threshold
                )

                # Classify severity for each discrepancy (Req 9.2, 9.3, 9.4)
                for disc in comparison["missing_steps"]:
                    disc.severity = await self._classify_severity(disc)
                    disc.recommendation = await self._generate_recommendation(disc)

                for disc in comparison["extra_steps"]:
                    disc.severity = await self._classify_severity(disc)
                    disc.recommendation = await self._generate_recommendation(disc)

                for mismatch in comparison["order_mismatches"]:
                    mismatch.severity = await self._classify_severity_order(mismatch)

                # Calculate alignment_score (Req 9.1)
                total_video_steps = len(video_steps)
                matched_count = len(comparison["matched_steps"])
                alignment_score = (
                    matched_count / total_video_steps
                    if total_video_steps > 0
                    else 0.0
                )

                # Set requires_review if score < 0.5 (Req 9.10)
                requires_review = alignment_score < 0.5

                # Store Discrepancy_Report in memory (Req 9.5)
                report = {
                    "video_document_uuid": document_uuid,
                    "sop_document_uuid": sop_uuid,
                    "alignment_score": alignment_score,
                    "total_video_steps": total_video_steps,
                    "total_sop_steps": len(sop_steps),
                    "matched_steps": comparison["matched_steps"],
                    "missing_steps": comparison["missing_steps"],
                    "extra_steps": comparison["extra_steps"],
                    "order_mismatches": comparison["order_mismatches"],
                    "requires_review": requires_review,
                    "generated_at": datetime.now(timezone.utc),
                    "job_id": job_id,
                }

                self._reports: dict[str, dict[str, Any]] = getattr(
                    self, "_reports", {}
                )
                self._reports[document_uuid] = report

            logger.info(
                "Alignment completed for video '%s' with %d linked SOPs",
                document_uuid,
                len(linked_sops),
            )

        except Exception as e:
            logger.error(
                "Alignment failed for %s: %s", document_uuid, str(e)
            )
            raise

    async def _extract_sop_steps(
        self,
        sop_document_uuid: str,
    ) -> list[SOPStep]:
        """Extract procedural steps from an SOP document via Chat_Model.

        Uses the Chat_Model with a step-extraction prompt to identify
        numbered or sequential procedural steps from the SOP text (Req 8.5).

        In mock mode or when no inference client is available, parses
        the SOP text directly by splitting on newlines and looking for
        numbered patterns.

        Args:
            sop_document_uuid: UUID of the SOP document.

        Returns:
            List of SOPStep objects extracted from the SOP text.
        """
        # Get SOP text content
        sop_texts = getattr(self, "_sop_texts", {})
        sop_text = sop_texts.get(sop_document_uuid, "")

        if not sop_text:
            return []

        # Try Chat_Model extraction if available
        if (
            self._inference_client is not None
            and self._model_manager is not None
            and self._model_manager.mode in ("gpu", "cpu")
        ):
            try:
                from alcoabase.services.model_manager import ModelRole

                await self._model_manager.ensure_model(ModelRole.CHAT)

                model_name = self._settings.model_chat_name
                messages: list[dict[str, Any]] = [
                    {
                        "role": "system",
                        "content": (
                            "You are a document analysis system. Extract all numbered "
                            "or sequential procedural steps from the following SOP document. "
                            "Output each step on a separate line in the format:\n"
                            "STEP <number>: <description>\n\n"
                            "Preserve the original ordering from the document. "
                            "If no procedural steps are found, output: NO_STEPS_FOUND"
                        ),
                    },
                    {
                        "role": "user",
                        "content": sop_text,
                    },
                ]

                response = await self._inference_client.chat_completion(
                    model=model_name,
                    messages=messages,
                    max_tokens=2048,
                    temperature=0.1,
                    timeout=60.0,
                )

                if response and "NO_STEPS_FOUND" not in response:
                    return self._parse_sop_steps_from_response(response)

            except Exception as e:
                logger.warning(
                    "Chat_Model SOP extraction failed for '%s': %s, "
                    "falling back to text parsing",
                    sop_document_uuid,
                    str(e),
                )

        # Fallback: parse SOP text directly
        return self._parse_sop_steps_from_text(sop_text)

    @staticmethod
    def _parse_sop_steps_from_response(response: str) -> list[SOPStep]:
        """Parse SOP steps from Chat_Model response.

        Expects lines in format: STEP <number>: <description>

        Args:
            response: Chat_Model response text.

        Returns:
            List of SOPStep objects.
        """
        import re

        steps: list[SOPStep] = []
        for line in response.strip().split("\n"):
            line = line.strip()
            # Match "STEP N: description" pattern
            match = re.match(r"STEP\s+(\d+)\s*:\s*(.+)", line, re.IGNORECASE)
            if match:
                step_number = int(match.group(1))
                description = match.group(2).strip()
                if description:
                    steps.append(SOPStep(step_number=step_number, description=description))
        return steps

    @staticmethod
    def _parse_sop_steps_from_text(text: str) -> list[SOPStep]:
        """Parse SOP steps directly from document text.

        Looks for numbered patterns like "1.", "1)", "Step 1:", etc.

        Args:
            text: Raw SOP document text.

        Returns:
            List of SOPStep objects.
        """
        import re

        steps: list[SOPStep] = []
        step_number = 0

        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            # Match common step patterns: "1.", "1)", "Step 1:", "1 -"
            match = re.match(
                r"(?:step\s+)?(\d+)[.):\-]\s*(.+)", line, re.IGNORECASE
            )
            if match:
                step_number = int(match.group(1))
                description = match.group(2).strip()
                if description:
                    steps.append(SOPStep(step_number=step_number, description=description))

        return steps

    async def _compare_steps(
        self,
        video_steps: list[StepDescription],
        sop_steps: list[SOPStep],
        threshold: float,
    ) -> dict[str, Any]:
        """Compare video steps against SOP steps using semantic similarity.

        Generates embeddings for both sets of steps and computes pairwise
        cosine similarity to classify each step as matched, missing, extra,
        or order_mismatch (Req 8.7).

        Args:
            video_steps: Steps extracted from the video.
            sop_steps: Steps extracted from the SOP.
            threshold: Similarity threshold for matching (default 0.7).

        Returns:
            Dictionary with matched_steps, missing_steps, extra_steps,
            and order_mismatches lists.
        """
        # Generate embeddings for all steps
        video_texts = [step.description for step in video_steps]
        sop_texts = [step.description for step in sop_steps]

        all_texts = video_texts + sop_texts
        all_embeddings = await self._generate_frame_embeddings(all_texts)

        video_embeddings = all_embeddings[: len(video_texts)]
        sop_embeddings = all_embeddings[len(video_texts):]

        # Compute pairwise similarity matrix
        similarity_matrix: list[list[float]] = []
        for v_emb in video_embeddings:
            row = [self._cosine_similarity(v_emb, s_emb) for s_emb in sop_embeddings]
            similarity_matrix.append(row)

        # Find best matches for each video step
        matched_steps: list[MatchedStep] = []
        order_mismatches: list[OrderMismatch] = []
        matched_video_indices: set[int] = set()
        matched_sop_indices: set[int] = set()

        # Greedy matching: for each video step, find best SOP match above threshold
        for v_idx, video_step in enumerate(video_steps):
            best_sop_idx = -1
            best_similarity = 0.0

            for s_idx, similarity in enumerate(similarity_matrix[v_idx]):
                if s_idx in matched_sop_indices:
                    continue
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_sop_idx = s_idx

            if best_sop_idx >= 0 and best_similarity >= threshold:
                sop_step = sop_steps[best_sop_idx]
                matched_steps.append(
                    MatchedStep(
                        video_step=video_step,
                        sop_step=sop_step,
                        similarity_score=best_similarity,
                    )
                )
                matched_video_indices.add(v_idx)
                matched_sop_indices.add(best_sop_idx)

                # Check for order mismatch: position diff >= 2 (Req 8.7)
                position_diff = abs(v_idx - best_sop_idx)
                if position_diff >= 2:
                    order_mismatches.append(
                        OrderMismatch(
                            video_step=video_step,
                            sop_step=sop_step,
                            video_position=v_idx,
                            sop_position=best_sop_idx,
                            severity=DiscrepancySeverity.MAJOR,  # Default, will be classified
                        )
                    )

        # Missing steps: video steps with no SOP match (Req 8.7)
        missing_steps: list[Discrepancy] = []
        for v_idx, video_step in enumerate(video_steps):
            if v_idx not in matched_video_indices:
                missing_steps.append(
                    Discrepancy(
                        step_description=video_step.description,
                        source="video",
                        severity=DiscrepancySeverity.MAJOR,  # Default, will be classified
                        recommendation="",
                    )
                )

        # Extra steps: SOP steps with no video match (Req 8.7)
        extra_steps: list[Discrepancy] = []
        for s_idx, sop_step in enumerate(sop_steps):
            if s_idx not in matched_sop_indices:
                extra_steps.append(
                    Discrepancy(
                        step_description=sop_step.description,
                        source="sop",
                        severity=DiscrepancySeverity.MAJOR,  # Default, will be classified
                        recommendation="",
                    )
                )

        return {
            "matched_steps": matched_steps,
            "missing_steps": missing_steps,
            "extra_steps": extra_steps,
            "order_mismatches": order_mismatches,
        }

    async def _classify_severity(
        self,
        discrepancy: Discrepancy,
    ) -> DiscrepancySeverity:
        """Classify severity of a discrepancy via Chat_Model.

        Uses the Chat_Model to assess GxP impact (patient safety, data
        integrity, product quality). Falls back to "major" on failure (Req 9.4).

        Args:
            discrepancy: The discrepancy to classify.

        Returns:
            Severity rating (critical, major, or minor).
        """
        if (
            self._inference_client is not None
            and self._model_manager is not None
            and self._model_manager.mode in ("gpu", "cpu")
        ):
            try:
                from alcoabase.services.model_manager import ModelRole

                await self._model_manager.ensure_model(ModelRole.CHAT)

                model_name = self._settings.model_chat_name
                messages: list[dict[str, Any]] = [
                    {
                        "role": "system",
                        "content": (
                            "You are a GxP compliance assessor. Classify the severity "
                            "of the following discrepancy between a training video and "
                            "an SOP document. Consider patient safety, data integrity, "
                            "and product quality impact.\n\n"
                            "Respond with exactly one word: CRITICAL, MAJOR, or MINOR.\n\n"
                            "- CRITICAL: Safety-related steps involving PPE, hazardous "
                            "materials, patient contact, or sterile technique.\n"
                            "- MAJOR: Procedural steps missing or in wrong order.\n"
                            "- MINOR: Steps with partial match (same intent but different wording)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Discrepancy: {discrepancy.step_description}\n"
                            f"Source: {discrepancy.source}\n"
                            f"Type: {'Missing from SOP' if discrepancy.source == 'video' else 'Extra in SOP'}"
                        ),
                    },
                ]

                response = await self._inference_client.chat_completion(
                    model=model_name,
                    messages=messages,
                    max_tokens=10,
                    temperature=0.0,
                    timeout=60.0,
                )

                if response:
                    response_upper = response.strip().upper()
                    if "CRITICAL" in response_upper:
                        return DiscrepancySeverity.CRITICAL
                    elif "MINOR" in response_upper:
                        return DiscrepancySeverity.MINOR
                    elif "MAJOR" in response_upper:
                        return DiscrepancySeverity.MAJOR

            except Exception as e:
                logger.warning(
                    "Chat_Model severity classification failed: %s, "
                    "defaulting to 'major'",
                    str(e),
                )

        # Fallback to "major" (Req 9.4)
        return DiscrepancySeverity.MAJOR

    async def _classify_severity_order(
        self,
        mismatch: OrderMismatch,
    ) -> DiscrepancySeverity:
        """Classify severity of an order mismatch via Chat_Model.

        Falls back to "major" on failure (Req 9.4).

        Args:
            mismatch: The order mismatch to classify.

        Returns:
            Severity rating (critical, major, or minor).
        """
        if (
            self._inference_client is not None
            and self._model_manager is not None
            and self._model_manager.mode in ("gpu", "cpu")
        ):
            try:
                from alcoabase.services.model_manager import ModelRole

                await self._model_manager.ensure_model(ModelRole.CHAT)

                model_name = self._settings.model_chat_name
                messages: list[dict[str, Any]] = [
                    {
                        "role": "system",
                        "content": (
                            "You are a GxP compliance assessor. Classify the severity "
                            "of the following order mismatch between a training video "
                            "and an SOP document. Consider patient safety, data integrity, "
                            "and product quality impact.\n\n"
                            "Respond with exactly one word: CRITICAL, MAJOR, or MINOR.\n\n"
                            "- CRITICAL: Safety-related steps where order is critical "
                            "(e.g., PPE before hazardous work).\n"
                            "- MAJOR: Procedural steps in wrong order.\n"
                            "- MINOR: Steps where order difference is cosmetic."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Video step (position {mismatch.video_position}): "
                            f"{mismatch.video_step.description}\n"
                            f"SOP step (position {mismatch.sop_position}): "
                            f"{mismatch.sop_step.description}\n"
                            f"Position difference: {abs(mismatch.video_position - mismatch.sop_position)}"
                        ),
                    },
                ]

                response = await self._inference_client.chat_completion(
                    model=model_name,
                    messages=messages,
                    max_tokens=10,
                    temperature=0.0,
                    timeout=60.0,
                )

                if response:
                    response_upper = response.strip().upper()
                    if "CRITICAL" in response_upper:
                        return DiscrepancySeverity.CRITICAL
                    elif "MINOR" in response_upper:
                        return DiscrepancySeverity.MINOR
                    elif "MAJOR" in response_upper:
                        return DiscrepancySeverity.MAJOR

            except Exception as e:
                logger.warning(
                    "Chat_Model order mismatch severity classification failed: %s, "
                    "defaulting to 'major'",
                    str(e),
                )

        # Fallback to "major" (Req 9.4)
        return DiscrepancySeverity.MAJOR

    async def _generate_recommendation(
        self,
        discrepancy: Discrepancy,
    ) -> str:
        """Generate a recommendation for a discrepancy via Chat_Model.

        Falls back to generic text on failure (Req 9.9).

        Args:
            discrepancy: The discrepancy to generate a recommendation for.

        Returns:
            Recommendation text (max 500 characters).
        """
        if (
            self._inference_client is not None
            and self._model_manager is not None
            and self._model_manager.mode in ("gpu", "cpu")
        ):
            try:
                from alcoabase.services.model_manager import ModelRole

                await self._model_manager.ensure_model(ModelRole.CHAT)

                model_name = self._settings.model_chat_name
                messages: list[dict[str, Any]] = [
                    {
                        "role": "system",
                        "content": (
                            "You are a GxP compliance advisor. Generate a brief "
                            "corrective action recommendation (maximum 500 characters) "
                            "for the following discrepancy between a training video "
                            "and an SOP document. Be specific and actionable."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Discrepancy: {discrepancy.step_description}\n"
                            f"Source: {discrepancy.source}\n"
                            f"Severity: {discrepancy.severity.value}\n"
                            f"Type: {'Step observed in video but missing from SOP' if discrepancy.source == 'video' else 'Step in SOP but not observed in video'}"
                        ),
                    },
                ]

                response = await self._inference_client.chat_completion(
                    model=model_name,
                    messages=messages,
                    max_tokens=256,
                    temperature=0.3,
                    timeout=60.0,
                )

                if response and response.strip():
                    # Cap at 500 characters (Req 9.8)
                    return response.strip()[:500]

            except Exception as e:
                logger.warning(
                    "Chat_Model recommendation generation failed: %s, "
                    "using generic fallback",
                    str(e),
                )

        # Fallback to generic recommendation (Req 9.9)
        return "Manual review is required for this discrepancy."

    async def get_report(
        self,
        document_uuid: str,
    ) -> dict[str, Any] | None:
        """Retrieve the latest Discrepancy_Report for a video.

        Args:
            document_uuid: UUID of the Video_Document.

        Returns:
            The most recent DiscrepancyReport as a dict, or None if none exists.
        """
        reports = getattr(self, "_reports", {})
        return reports.get(document_uuid)
