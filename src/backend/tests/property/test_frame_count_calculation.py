"""Property-based tests for frame extraction count and interval calculation.

Tests Property 11: Frame extraction count and interval calculation from the
multimodal-knowledge-base design document.

Property 11 validates that for any (duration, requested_interval, max_frames)
combination, the _calculate_interval() method returns an interval that:
- Always produces <= max_frames frames (ceil(duration / returned_interval) <= max_frames)
- Returns the original interval when no adjustment is needed
- Returns the minimal interval that caps at max_frames when adjustment is needed

**Validates: Requirements 5.1, 5.5**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 11)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/alignment_service.py
"""

from __future__ import annotations

import math

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.alignment_service import AlignmentService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_duration() -> st.SearchStrategy[float]:
    """Generate video durations in seconds (1.0 to 36000.0 = 10 hours).

    Returns:
        Strategy producing positive float durations.
    """
    return st.floats(min_value=1.0, max_value=36000.0, allow_nan=False, allow_infinity=False)


def st_interval() -> st.SearchStrategy[int]:
    """Generate requested intervals in seconds (1 to 60).

    Matches the valid range from Requirement 5.1.

    Returns:
        Strategy producing integer intervals in [1, 60].
    """
    return st.integers(min_value=1, max_value=60)


def st_max_frames() -> st.SearchStrategy[int]:
    """Generate max frame counts (1 to 1000).

    The default is 500 per Requirement 5.5, but we test a range.

    Returns:
        Strategy producing positive integer max frame counts.
    """
    return st.integers(min_value=1, max_value=1000)


# ---------------------------------------------------------------------------
# Property 11: Frame extraction count and interval calculation
# ---------------------------------------------------------------------------


# Feature: multimodal-knowledge-base, Property 11: Frame extraction count and interval calculation
class TestFrameCountCalculation:
    """Property tests for frame extraction count and interval calculation.

    For any (duration, requested_interval, max_frames) combination, the
    _calculate_interval() method SHALL return an interval such that the
    resulting frame count does not exceed max_frames. If no adjustment is
    needed, the original interval is returned unchanged.

    **Validates: Requirements 5.1, 5.5**
    """

    @given(
        duration=st_duration(),
        requested_interval=st_interval(),
        max_frames=st_max_frames(),
    )
    @settings(max_examples=500)
    def test_returned_interval_never_exceeds_max_frames(
        self,
        duration: float,
        requested_interval: int,
        max_frames: int,
    ) -> None:
        """The returned interval always produces <= max_frames frames.

        For any valid inputs, ceil(duration / returned_interval) <= max_frames.

        **Validates: Requirements 5.1, 5.5**
        """
        result_interval = AlignmentService._calculate_interval(
            duration, requested_interval, max_frames
        )

        frame_count = math.ceil(duration / result_interval)
        assert frame_count <= max_frames, (
            f"Expected frame_count <= {max_frames}, got {frame_count} "
            f"(duration={duration}, requested_interval={requested_interval}, "
            f"result_interval={result_interval})"
        )

    @given(
        duration=st_duration(),
        requested_interval=st_interval(),
        max_frames=st_max_frames(),
    )
    @settings(max_examples=500)
    def test_original_interval_returned_when_no_adjustment_needed(
        self,
        duration: float,
        requested_interval: int,
        max_frames: int,
    ) -> None:
        """If ceil(duration / requested_interval) <= max_frames, the original
        interval is returned unchanged.

        **Validates: Requirements 5.1, 5.5**
        """
        estimated_frames = math.ceil(duration / requested_interval)

        result_interval = AlignmentService._calculate_interval(
            duration, requested_interval, max_frames
        )

        if estimated_frames <= max_frames:
            assert result_interval == requested_interval, (
                f"Expected original interval {requested_interval} to be returned "
                f"(estimated_frames={estimated_frames} <= max_frames={max_frames}), "
                f"but got {result_interval}"
            )

    @given(
        duration=st_duration(),
        requested_interval=st_interval(),
        max_frames=st_max_frames(),
    )
    @settings(max_examples=500)
    def test_interval_adjusted_when_frames_exceed_max(
        self,
        duration: float,
        requested_interval: int,
        max_frames: int,
    ) -> None:
        """If ceil(duration / requested_interval) > max_frames, the interval
        is increased to ceil(duration / max_frames).

        **Validates: Requirements 5.1, 5.5**
        """
        estimated_frames = math.ceil(duration / requested_interval)

        result_interval = AlignmentService._calculate_interval(
            duration, requested_interval, max_frames
        )

        if estimated_frames > max_frames:
            expected_adjusted = math.ceil(duration / max_frames)
            assert result_interval == expected_adjusted, (
                f"Expected adjusted interval {expected_adjusted} "
                f"(duration={duration}, max_frames={max_frames}), "
                f"but got {result_interval}"
            )

    @given(
        duration=st_duration(),
        requested_interval=st_interval(),
        max_frames=st_max_frames(),
    )
    @settings(max_examples=500)
    def test_returned_interval_is_at_least_requested(
        self,
        duration: float,
        requested_interval: int,
        max_frames: int,
    ) -> None:
        """The returned interval is always >= the requested interval.

        The method only increases the interval, never decreases it.

        **Validates: Requirements 5.1, 5.5**
        """
        result_interval = AlignmentService._calculate_interval(
            duration, requested_interval, max_frames
        )

        assert result_interval >= requested_interval, (
            f"Expected result_interval >= requested_interval "
            f"({result_interval} >= {requested_interval}), "
            f"but interval was decreased"
        )

    @given(
        duration=st_duration(),
        requested_interval=st_interval(),
        max_frames=st_max_frames(),
    )
    @settings(max_examples=500)
    def test_adjustment_is_minimal(
        self,
        duration: float,
        requested_interval: int,
        max_frames: int,
    ) -> None:
        """When adjustment is needed, the returned interval is the smallest
        integer that caps frame count at max_frames.

        For any interval one less than the returned value (if > requested_interval),
        the frame count would exceed max_frames.

        **Validates: Requirements 5.1, 5.5**
        """
        result_interval = AlignmentService._calculate_interval(
            duration, requested_interval, max_frames
        )

        # If the interval was adjusted (result > requested), verify minimality
        if result_interval > requested_interval:
            # One less than the result should exceed max_frames
            smaller_interval = result_interval - 1
            if smaller_interval >= 1:
                frames_with_smaller = math.ceil(duration / smaller_interval)
                assert frames_with_smaller > max_frames, (
                    f"Interval {result_interval} is not minimal: "
                    f"interval {smaller_interval} would produce "
                    f"{frames_with_smaller} frames (<= {max_frames})"
                )
