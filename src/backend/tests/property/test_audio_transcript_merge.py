"""Property-based tests for audio transcript segment merge by timestamp overlap.

Tests Property 15: Audio transcript segment merge by timestamp overlap from the
multimodal-knowledge-base design document.

Property 15 validates that for any combination of step sequences and transcript
segments, the merge_transcript_with_steps() method correctly:
- Assigns each segment to the step with the greatest overlap duration
- Does not assign segments with no overlap to any step
- Concatenates multiple segments assigned to the same step in chronological order

**Validates: Requirements 7.7**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 15)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/alignment_service.py
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings, assume

from alcoabase.services.alignment_service import (
    AlignmentService,
    StepDescription,
    TranscriptSegment,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_step_sequence(draw: st.DrawFn) -> list[StepDescription]:
    """Generate a non-empty list of non-overlapping steps with valid timestamps.

    Steps are generated with increasing, non-overlapping timestamp ranges
    to simulate a realistic step sequence extracted from video frames.

    Returns:
        Strategy producing lists of StepDescription objects.
    """
    num_steps = draw(st.integers(min_value=1, max_value=8))
    steps: list[StepDescription] = []
    current_time = 0.0

    for i in range(num_steps):
        # Each step has a duration between 1.0 and 30.0 seconds
        duration = draw(st.floats(min_value=1.0, max_value=30.0, allow_nan=False, allow_infinity=False))
        # Optional gap between steps (0.0 to 5.0 seconds)
        gap = draw(st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False))

        start = current_time + gap
        end = start + duration

        steps.append(
            StepDescription(
                start_timestamp=start,
                end_timestamp=end,
                description=f"Step {i} description",
                frame_indices=[i],
                confidence=1.0,
                audio_transcript=None,
            )
        )
        current_time = end

    return steps


@st.composite
def st_transcript_segments(
    draw: st.DrawFn,
    time_range: tuple[float, float],
) -> list[TranscriptSegment]:
    """Generate a list of transcript segments within a given time range.

    Segments may overlap with steps or fall entirely outside step ranges.

    Args:
        time_range: Tuple of (min_start, max_end) for segment timestamps.

    Returns:
        Strategy producing lists of TranscriptSegment objects.
    """
    min_time, max_time = time_range
    num_segments = draw(st.integers(min_value=1, max_value=10))
    segments: list[TranscriptSegment] = []

    for i in range(num_segments):
        start = draw(
            st.floats(
                min_value=min_time,
                max_value=max_time - 0.1,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        # Segment duration between 0.5 and 15.0 seconds
        duration = draw(
            st.floats(
                min_value=0.5,
                max_value=15.0,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        end = min(start + duration, max_time + 20.0)  # Allow extending beyond steps

        segments.append(
            TranscriptSegment(
                start_time=start,
                end_time=end,
                text=f"Segment {i} text",
            )
        )

    return segments


@st.composite
def st_non_overlapping_segments(
    draw: st.DrawFn,
    steps: list[StepDescription],
) -> list[TranscriptSegment]:
    """Generate transcript segments that do NOT overlap with any step.

    Places segments in gaps between steps or before/after all steps.

    Args:
        steps: The step sequence to avoid overlapping with.

    Returns:
        Strategy producing segments with zero overlap to any step.
    """
    # Find gaps between steps and before/after
    gaps: list[tuple[float, float]] = []

    # Gap before first step (if first step doesn't start at 0)
    if steps[0].start_timestamp > 1.0:
        gaps.append((0.0, steps[0].start_timestamp - 0.01))

    # Gaps between consecutive steps
    for i in range(len(steps) - 1):
        gap_start = steps[i].end_timestamp + 0.01
        gap_end = steps[i + 1].start_timestamp - 0.01
        if gap_end > gap_start + 0.1:
            gaps.append((gap_start, gap_end))

    # Gap after last step
    last_end = steps[-1].end_timestamp + 0.01
    gaps.append((last_end, last_end + 50.0))

    assume(len(gaps) > 0)

    num_segments = draw(st.integers(min_value=1, max_value=5))
    segments: list[TranscriptSegment] = []

    for i in range(num_segments):
        gap_idx = draw(st.integers(min_value=0, max_value=len(gaps) - 1))
        gap_start, gap_end = gaps[gap_idx]
        seg_start = draw(
            st.floats(
                min_value=gap_start,
                max_value=gap_end - 0.05,
                allow_nan=False,
                allow_infinity=False,
            )
        )
        seg_duration = draw(
            st.floats(
                min_value=0.01,
                max_value=min(gap_end - seg_start, 5.0),
                allow_nan=False,
                allow_infinity=False,
            )
        )
        seg_end = seg_start + seg_duration

        # Ensure no overlap with any step
        has_overlap = False
        for step in steps:
            overlap_start = max(seg_start, step.start_timestamp)
            overlap_end = min(seg_end, step.end_timestamp)
            if overlap_end > overlap_start:
                has_overlap = True
                break

        if not has_overlap:
            segments.append(
                TranscriptSegment(
                    start_time=seg_start,
                    end_time=seg_end,
                    text=f"Non-overlapping segment {i}",
                )
            )

    assume(len(segments) > 0)
    return segments


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def compute_overlap(segment: TranscriptSegment, step: StepDescription) -> float:
    """Compute the overlap duration between a segment and a step.

    Args:
        segment: The transcript segment.
        step: The step description.

    Returns:
        Overlap duration in seconds (>= 0.0).
    """
    overlap_start = max(segment.start_time, step.start_timestamp)
    overlap_end = min(segment.end_time, step.end_timestamp)
    return max(0.0, overlap_end - overlap_start)


def find_best_step_for_segment(
    segment: TranscriptSegment,
    steps: list[StepDescription],
) -> int:
    """Find the step index with the greatest overlap for a segment.

    Args:
        segment: The transcript segment.
        steps: List of steps.

    Returns:
        Index of the best step, or -1 if no overlap exists.
    """
    best_idx = -1
    best_overlap = 0.0

    for idx, step in enumerate(steps):
        overlap = compute_overlap(segment, step)
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = idx

    return best_idx


# ---------------------------------------------------------------------------
# Property 15: Audio transcript segment merge by timestamp overlap
# ---------------------------------------------------------------------------


# Feature: multimodal-knowledge-base, Property 15: Audio transcript segment merge
class TestAudioTranscriptMerge:
    """Property tests for audio transcript segment merge by timestamp overlap.

    For any combination of step sequences and transcript segments,
    merge_transcript_with_steps() SHALL:
    - Assign each segment to the step with the greatest overlap duration
    - Not assign segments with no overlap to any step
    - Concatenate multiple segments assigned to the same step chronologically

    **Validates: Requirements 7.7**
    """

    @given(data=st.data())
    @settings(max_examples=200)
    def test_segment_assigned_to_step_with_greatest_overlap(
        self,
        data: st.DataObject,
    ) -> None:
        """Each transcript segment is assigned to the step whose timestamp
        range overlaps with the segment's time range by the greatest duration.

        **Validates: Requirements 7.7**
        """
        steps = data.draw(st_step_sequence())
        # Generate segments within a range that covers the steps
        max_time = steps[-1].end_timestamp + 10.0
        segments = data.draw(st_transcript_segments(time_range=(0.0, max_time)))

        # Set up the service with test data
        service = AlignmentService()
        service._step_sequences = {"doc-uuid": [
            StepDescription(
                start_timestamp=s.start_timestamp,
                end_timestamp=s.end_timestamp,
                description=s.description,
                frame_indices=s.frame_indices,
                confidence=s.confidence,
                audio_transcript=None,
            )
            for s in steps
        ]}
        service._transcripts = {"doc-uuid": segments}

        result = service.merge_transcript_with_steps("doc-uuid")

        # Verify each segment was assigned to the correct step
        for segment in segments:
            expected_step_idx = find_best_step_for_segment(segment, steps)

            if expected_step_idx >= 0:
                # Segment should appear in the expected step's transcript
                assert result[expected_step_idx].audio_transcript is not None, (
                    f"Segment '{segment.text}' should be assigned to step {expected_step_idx} "
                    f"but audio_transcript is None"
                )
                assert segment.text in result[expected_step_idx].audio_transcript, (
                    f"Segment '{segment.text}' not found in step {expected_step_idx}'s "
                    f"audio_transcript: '{result[expected_step_idx].audio_transcript}'"
                )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_segments_with_no_overlap_not_assigned(
        self,
        data: st.DataObject,
    ) -> None:
        """Segments with no overlap to any step are not assigned to any step.

        **Validates: Requirements 7.7**
        """
        steps = data.draw(st_step_sequence())
        # Ensure there are gaps for non-overlapping segments
        assume(steps[0].start_timestamp > 1.0 or len(steps) > 1)

        segments = data.draw(st_non_overlapping_segments(steps=steps))

        service = AlignmentService()
        service._step_sequences = {"doc-uuid": [
            StepDescription(
                start_timestamp=s.start_timestamp,
                end_timestamp=s.end_timestamp,
                description=s.description,
                frame_indices=s.frame_indices,
                confidence=s.confidence,
                audio_transcript=None,
            )
            for s in steps
        ]}
        service._transcripts = {"doc-uuid": segments}

        result = service.merge_transcript_with_steps("doc-uuid")

        # No step should have any of the non-overlapping segment texts
        for step in result:
            if step.audio_transcript is not None:
                for segment in segments:
                    assert segment.text not in step.audio_transcript, (
                        f"Non-overlapping segment '{segment.text}' was incorrectly "
                        f"assigned to a step with transcript: '{step.audio_transcript}'"
                    )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_multiple_segments_concatenated_chronologically(
        self,
        data: st.DataObject,
    ) -> None:
        """Multiple segments assigned to the same step are concatenated
        in chronological order (sorted by start_time).

        **Validates: Requirements 7.7**
        """
        # Create a single step with a wide time range
        step_start = 0.0
        step_end = data.draw(
            st.floats(min_value=30.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        )

        step = StepDescription(
            start_timestamp=step_start,
            end_timestamp=step_end,
            description="Wide step",
            frame_indices=[0],
            confidence=1.0,
            audio_transcript=None,
        )

        # Generate multiple segments that all overlap with this step
        num_segments = data.draw(st.integers(min_value=2, max_value=6))
        segments: list[TranscriptSegment] = []

        for i in range(num_segments):
            seg_start = data.draw(
                st.floats(
                    min_value=step_start,
                    max_value=step_end - 1.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            seg_duration = data.draw(
                st.floats(
                    min_value=0.5,
                    max_value=min(5.0, step_end - seg_start),
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            segments.append(
                TranscriptSegment(
                    start_time=seg_start,
                    end_time=seg_start + seg_duration,
                    text=f"Chronological segment {i}",
                )
            )

        service = AlignmentService()
        service._step_sequences = {"doc-uuid": [step]}
        service._transcripts = {"doc-uuid": segments}

        result = service.merge_transcript_with_steps("doc-uuid")

        # All segments should be assigned to the single step
        assert result[0].audio_transcript is not None, (
            "Expected audio_transcript to be populated with multiple segments"
        )

        # Verify chronological ordering: segments sorted by start_time
        sorted_segments = sorted(segments, key=lambda s: s.start_time)
        expected_text = " ".join(seg.text for seg in sorted_segments)
        assert result[0].audio_transcript == expected_text, (
            f"Expected chronological concatenation:\n"
            f"  Expected: '{expected_text}'\n"
            f"  Got: '{result[0].audio_transcript}'"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_steps_without_overlapping_segments_have_no_transcript(
        self,
        data: st.DataObject,
    ) -> None:
        """Steps that have no overlapping transcript segments retain
        audio_transcript as None.

        **Validates: Requirements 7.7**
        """
        steps = data.draw(st_step_sequence())
        assume(len(steps) >= 2)

        # Generate segments that only overlap with the first step
        first_step = steps[0]
        num_segments = data.draw(st.integers(min_value=1, max_value=3))
        segments: list[TranscriptSegment] = []

        for i in range(num_segments):
            seg_start = data.draw(
                st.floats(
                    min_value=first_step.start_timestamp,
                    max_value=first_step.end_timestamp - 0.2,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            max_duration = max(0.1, min(2.0, first_step.end_timestamp - seg_start))
            seg_duration = data.draw(
                st.floats(
                    min_value=0.1,
                    max_value=max_duration,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
            seg_end = seg_start + seg_duration
            # Ensure segment only overlaps with first step
            # (ends before second step starts)
            if len(steps) > 1:
                seg_end = min(seg_end, steps[1].start_timestamp - 0.01)
                if seg_end <= seg_start:
                    continue

            segments.append(
                TranscriptSegment(
                    start_time=seg_start,
                    end_time=seg_end,
                    text=f"First step segment {i}",
                )
            )

        assume(len(segments) > 0)

        service = AlignmentService()
        service._step_sequences = {"doc-uuid": [
            StepDescription(
                start_timestamp=s.start_timestamp,
                end_timestamp=s.end_timestamp,
                description=s.description,
                frame_indices=s.frame_indices,
                confidence=s.confidence,
                audio_transcript=None,
            )
            for s in steps
        ]}
        service._transcripts = {"doc-uuid": segments}

        result = service.merge_transcript_with_steps("doc-uuid")

        # First step should have transcript
        assert result[0].audio_transcript is not None, (
            "First step should have audio_transcript from overlapping segments"
        )

        # Remaining steps should have no transcript (no overlapping segments)
        for i in range(1, len(result)):
            assert result[i].audio_transcript is None, (
                f"Step {i} should have no audio_transcript but got: "
                f"'{result[i].audio_transcript}'"
            )
