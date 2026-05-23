"""Property-based tests for frame analysis abort threshold.

Tests Property 14: Frame analysis abort threshold from the
multimodal-knowledge-base design document.

Property 14 validates that for any frame analysis operation:
- If more than 50% of frames fail Vision_Model analysis, the system SHALL
  abort (should_abort = True).
- If 50% or fewer frames fail, the system SHALL continue and produce a
  Step_Sequence from the successful frames (should_abort = False).

**Validates: Requirements 6.8**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 14)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/alignment_service.py
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.alignment_service import should_abort_frame_analysis


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_total_frames() -> st.SearchStrategy[int]:
    """Generate total frame counts (1 to 1000).

    Covers realistic video frame extraction outputs.

    Returns:
        Strategy producing positive integer frame counts.
    """
    return st.integers(min_value=1, max_value=1000)


def st_failure_count(max_value: int = 1000) -> st.SearchStrategy[int]:
    """Generate failure counts (0 to max_value).

    Args:
        max_value: Upper bound for failure count.

    Returns:
        Strategy producing non-negative integer failure counts.
    """
    return st.integers(min_value=0, max_value=max_value)


# ---------------------------------------------------------------------------
# Property 14: Frame analysis abort threshold
# ---------------------------------------------------------------------------


# Feature: multimodal-knowledge-base, Property 14: Frame analysis abort threshold
class TestFrameAnalysisAbortThreshold:
    """Property tests for frame analysis abort threshold.

    For any (total_frames, failure_count) combination, the abort decision
    SHALL be: abort when failure_count > total_frames / 2, continue otherwise.

    **Validates: Requirements 6.8**
    """

    @given(
        total_frames=st_total_frames(),
        data=st.data(),
    )
    @settings(max_examples=500)
    def test_abort_when_failures_exceed_half(
        self,
        total_frames: int,
        data: st.DataObject,
    ) -> None:
        """When failure_count > total_frames / 2, should_abort returns True.

        **Validates: Requirements 6.8**
        """
        # Generate a failure count that strictly exceeds 50%
        min_abort_failures = total_frames // 2 + 1
        failure_count = data.draw(
            st.integers(min_value=min_abort_failures, max_value=total_frames),
            label="failure_count",
        )

        result = should_abort_frame_analysis(total_frames, failure_count)

        assert result is True, (
            f"Expected abort (True) when failure_count={failure_count} > "
            f"total_frames/2={total_frames / 2} "
            f"(total_frames={total_frames})"
        )

    @given(
        total_frames=st_total_frames(),
        data=st.data(),
    )
    @settings(max_examples=500)
    def test_continue_when_failures_at_or_below_half(
        self,
        total_frames: int,
        data: st.DataObject,
    ) -> None:
        """When failure_count <= total_frames / 2, should_abort returns False.

        **Validates: Requirements 6.8**
        """
        # Generate a failure count at or below 50%
        max_continue_failures = total_frames // 2
        failure_count = data.draw(
            st.integers(min_value=0, max_value=max_continue_failures),
            label="failure_count",
        )

        result = should_abort_frame_analysis(total_frames, failure_count)

        assert result is False, (
            f"Expected continue (False) when failure_count={failure_count} <= "
            f"total_frames/2={total_frames / 2} "
            f"(total_frames={total_frames})"
        )

    @given(
        total_frames=st_total_frames(),
    )
    @settings(max_examples=500)
    def test_zero_failures_never_aborts(
        self,
        total_frames: int,
    ) -> None:
        """When no frames fail (failure_count=0), should_abort returns False.

        **Validates: Requirements 6.8**
        """
        result = should_abort_frame_analysis(total_frames, 0)

        assert result is False, (
            f"Expected continue (False) when failure_count=0 "
            f"(total_frames={total_frames})"
        )

    @given(
        total_frames=st_total_frames(),
    )
    @settings(max_examples=500)
    def test_all_failures_always_aborts(
        self,
        total_frames: int,
    ) -> None:
        """When all frames fail (failure_count=total_frames), should_abort
        returns True.

        **Validates: Requirements 6.8**
        """
        result = should_abort_frame_analysis(total_frames, total_frames)

        assert result is True, (
            f"Expected abort (True) when all frames fail "
            f"(failure_count={total_frames}, total_frames={total_frames})"
        )

    @given(
        total_frames=st.integers(min_value=2, max_value=1000).filter(
            lambda x: x % 2 == 0
        ),
    )
    @settings(max_examples=500)
    def test_exact_half_does_not_abort(
        self,
        total_frames: int,
    ) -> None:
        """When exactly 50% of frames fail (failure_count == total_frames / 2),
        should_abort returns False (abort requires STRICTLY more than 50%).

        **Validates: Requirements 6.8**
        """
        failure_count = total_frames // 2

        result = should_abort_frame_analysis(total_frames, failure_count)

        assert result is False, (
            f"Expected continue (False) when exactly half fail: "
            f"failure_count={failure_count}, total_frames={total_frames}"
        )
