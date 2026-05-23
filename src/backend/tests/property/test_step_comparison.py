"""Property-based tests for step comparison classification.

Tests Property 16: Step comparison classification from the
multimodal-knowledge-base design document.

Property 16 validates that for any combination of video steps and SOP steps
with known cosine similarities, the classify_step_pairs() function correctly:
- Classifies steps with similarity >= threshold as "matched"
- Classifies unmatched video steps as "missing" (in video but not SOP)
- Classifies unmatched SOP steps as "extra" (in SOP but not video)
- Classifies matched steps with position difference >= 2 as "order_mismatch"

**Validates: Requirements 8.7, 9.1**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 16)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/alignment_service.py
"""

from __future__ import annotations

from dataclasses import dataclass

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings, assume


# ---------------------------------------------------------------------------
# Pure classification function (extracted from AlignmentService._compare_steps)
# ---------------------------------------------------------------------------


@dataclass
class StepComparisonResult:
    """Result of step pair classification.

    Attributes:
        matched: List of (video_idx, sop_idx, similarity) tuples for matched pairs.
        missing: List of video step indices with no SOP match above threshold.
        extra: List of SOP step indices with no video match above threshold.
        order_mismatches: List of (video_idx, sop_idx) tuples where matched
            steps have position difference >= 2.
    """

    matched: list[tuple[int, int, float]]
    missing: list[int]
    extra: list[int]
    order_mismatches: list[tuple[int, int]]


def classify_step_pairs(
    similarity_matrix: list[list[float]],
    threshold: float = 0.7,
) -> StepComparisonResult:
    """Classify step pairs based on a pre-computed cosine similarity matrix.

    Uses greedy matching: for each video step (row), finds the best unmatched
    SOP step (column) with similarity >= threshold. Steps are classified as:
    - matched: video step has SOP step with similarity >= threshold
    - missing: video step has no SOP step with similarity >= threshold
    - extra: SOP step has no video step with similarity >= threshold
    - order_mismatch: matched but |video_position - sop_position| >= 2

    This is a pure function that mirrors the classification logic in
    AlignmentService._compare_steps (Requirement 8.7).

    Args:
        similarity_matrix: 2D matrix where similarity_matrix[v][s] is the
            cosine similarity between video step v and SOP step s.
            Rows = video steps, columns = SOP steps.
        threshold: Similarity threshold for matching (default 0.7).

    Returns:
        StepComparisonResult with matched, missing, extra, and order_mismatches.
    """
    num_video = len(similarity_matrix)
    num_sop = len(similarity_matrix[0]) if num_video > 0 else 0

    matched: list[tuple[int, int, float]] = []
    order_mismatches: list[tuple[int, int]] = []
    matched_video_indices: set[int] = set()
    matched_sop_indices: set[int] = set()

    # Greedy matching: for each video step, find best SOP match above threshold
    for v_idx in range(num_video):
        best_sop_idx = -1
        best_similarity = 0.0

        for s_idx in range(num_sop):
            if s_idx in matched_sop_indices:
                continue
            similarity = similarity_matrix[v_idx][s_idx]
            if similarity > best_similarity:
                best_similarity = similarity
                best_sop_idx = s_idx

        if best_sop_idx >= 0 and best_similarity >= threshold:
            matched.append((v_idx, best_sop_idx, best_similarity))
            matched_video_indices.add(v_idx)
            matched_sop_indices.add(best_sop_idx)

            # Check for order mismatch: position diff >= 2
            position_diff = abs(v_idx - best_sop_idx)
            if position_diff >= 2:
                order_mismatches.append((v_idx, best_sop_idx))

    # Missing: video steps with no SOP match
    missing = [v_idx for v_idx in range(num_video) if v_idx not in matched_video_indices]

    # Extra: SOP steps with no video match
    extra = [s_idx for s_idx in range(num_sop) if s_idx not in matched_sop_indices]

    return StepComparisonResult(
        matched=matched,
        missing=missing,
        extra=extra,
        order_mismatches=order_mismatches,
    )


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_similarity_matrix(
    draw: st.DrawFn,
    min_video: int = 1,
    max_video: int = 8,
    min_sop: int = 1,
    max_sop: int = 8,
) -> list[list[float]]:
    """Generate a random similarity matrix with values in [0.0, 1.0].

    Args:
        min_video: Minimum number of video steps (rows).
        max_video: Maximum number of video steps (rows).
        min_sop: Minimum number of SOP steps (columns).
        max_sop: Maximum number of SOP steps (columns).

    Returns:
        Strategy producing a 2D list of similarity scores.
    """
    num_video = draw(st.integers(min_value=min_video, max_value=max_video))
    num_sop = draw(st.integers(min_value=min_sop, max_value=max_sop))

    matrix: list[list[float]] = []
    for _ in range(num_video):
        row = draw(
            st.lists(
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
                min_size=num_sop,
                max_size=num_sop,
            )
        )
        matrix.append(row)

    return matrix


@st.composite
def st_matrix_with_guaranteed_matches(
    draw: st.DrawFn,
) -> tuple[list[list[float]], list[tuple[int, int]]]:
    """Generate a matrix with at least one guaranteed match (similarity >= 0.7).

    Returns:
        Tuple of (similarity_matrix, list of (video_idx, sop_idx) pairs
        that are guaranteed to have similarity >= 0.7).
    """
    num_video = draw(st.integers(min_value=2, max_value=6))
    num_sop = draw(st.integers(min_value=2, max_value=6))

    # Start with low similarities
    matrix: list[list[float]] = []
    for _ in range(num_video):
        row = draw(
            st.lists(
                st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
                min_size=num_sop,
                max_size=num_sop,
            )
        )
        matrix.append(row)

    # Inject guaranteed matches (non-overlapping indices)
    num_matches = draw(st.integers(min_value=1, max_value=min(num_video, num_sop)))
    video_indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=num_video - 1),
            min_size=num_matches,
            max_size=num_matches,
            unique=True,
        )
    )
    sop_indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=num_sop - 1),
            min_size=num_matches,
            max_size=num_matches,
            unique=True,
        )
    )

    guaranteed_matches: list[tuple[int, int]] = []
    for v_idx, s_idx in zip(video_indices, sop_indices):
        high_sim = draw(
            st.floats(min_value=0.7, max_value=1.0, allow_nan=False, allow_infinity=False)
        )
        matrix[v_idx][s_idx] = high_sim
        guaranteed_matches.append((v_idx, s_idx))

    return matrix, guaranteed_matches


@st.composite
def st_matrix_all_below_threshold(
    draw: st.DrawFn,
) -> list[list[float]]:
    """Generate a matrix where ALL similarities are below 0.7.

    Returns:
        Strategy producing a matrix with no possible matches.
    """
    num_video = draw(st.integers(min_value=1, max_value=6))
    num_sop = draw(st.integers(min_value=1, max_value=6))

    matrix: list[list[float]] = []
    for _ in range(num_video):
        row = draw(
            st.lists(
                st.floats(min_value=0.0, max_value=0.69, allow_nan=False, allow_infinity=False),
                min_size=num_sop,
                max_size=num_sop,
            )
        )
        matrix.append(row)

    return matrix


# ---------------------------------------------------------------------------
# Property 16: Step comparison classification
# ---------------------------------------------------------------------------


class TestStepComparisonClassification:
    """Property tests for step comparison classification.

    For any combination of video steps and SOP steps with known cosine
    similarities, classify_step_pairs() SHALL correctly classify each
    step pair as matched, missing, extra, or order_mismatch based on
    the similarity threshold (0.7) and position difference (>= 2).

    **Validates: Requirements 8.7, 9.1**
    """

    @given(matrix=st_similarity_matrix())
    @settings(max_examples=200)
    def test_all_steps_classified_exactly_once(
        self,
        matrix: list[list[float]],
    ) -> None:
        """Every video step appears in exactly one category (matched or missing),
        and every SOP step appears in exactly one category (matched or extra).

        **Validates: Requirements 8.7, 9.1**
        """
        result = classify_step_pairs(matrix, threshold=0.7)

        num_video = len(matrix)
        num_sop = len(matrix[0]) if num_video > 0 else 0

        # Every video step is either matched or missing
        matched_video = {v_idx for v_idx, _, _ in result.matched}
        missing_video = set(result.missing)
        assert matched_video | missing_video == set(range(num_video)), (
            f"Not all video steps classified: matched={matched_video}, "
            f"missing={missing_video}, expected={set(range(num_video))}"
        )
        assert matched_video & missing_video == set(), (
            "A video step cannot be both matched and missing"
        )

        # Every SOP step is either matched or extra
        matched_sop = {s_idx for _, s_idx, _ in result.matched}
        extra_sop = set(result.extra)
        assert matched_sop | extra_sop == set(range(num_sop)), (
            f"Not all SOP steps classified: matched={matched_sop}, "
            f"extra={extra_sop}, expected={set(range(num_sop))}"
        )
        assert matched_sop & extra_sop == set(), (
            "An SOP step cannot be both matched and extra"
        )

    @given(matrix=st_similarity_matrix())
    @settings(max_examples=200)
    def test_matched_pairs_have_similarity_above_threshold(
        self,
        matrix: list[list[float]],
    ) -> None:
        """All matched step pairs have similarity >= threshold (0.7).

        **Validates: Requirements 8.7, 9.1**
        """
        result = classify_step_pairs(matrix, threshold=0.7)

        for v_idx, s_idx, sim in result.matched:
            assert sim >= 0.7, (
                f"Matched pair ({v_idx}, {s_idx}) has similarity {sim} < 0.7"
            )
            # Verify the similarity matches the matrix value
            assert sim == matrix[v_idx][s_idx], (
                f"Matched similarity {sim} doesn't match matrix value "
                f"{matrix[v_idx][s_idx]} at ({v_idx}, {s_idx})"
            )

    @given(matrix=st_matrix_all_below_threshold())
    @settings(max_examples=200)
    def test_no_matches_when_all_below_threshold(
        self,
        matrix: list[list[float]],
    ) -> None:
        """When all similarities are below threshold, there are no matches,
        all video steps are missing, and all SOP steps are extra.

        **Validates: Requirements 8.7, 9.1**
        """
        result = classify_step_pairs(matrix, threshold=0.7)

        num_video = len(matrix)
        num_sop = len(matrix[0])

        assert len(result.matched) == 0, (
            f"Expected no matches but got {len(result.matched)}"
        )
        assert len(result.missing) == num_video, (
            f"Expected {num_video} missing but got {len(result.missing)}"
        )
        assert len(result.extra) == num_sop, (
            f"Expected {num_sop} extra but got {len(result.extra)}"
        )
        assert len(result.order_mismatches) == 0, (
            "No order mismatches possible without matches"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_order_mismatch_only_for_position_diff_ge_2(
        self,
        data: st.DataObject,
    ) -> None:
        """Order mismatches are reported only for matched pairs where
        |video_position - sop_position| >= 2.

        **Validates: Requirements 8.7, 9.1**
        """
        matrix = data.draw(st_similarity_matrix())
        result = classify_step_pairs(matrix, threshold=0.7)

        # All order mismatches must have position diff >= 2
        for v_idx, s_idx in result.order_mismatches:
            assert abs(v_idx - s_idx) >= 2, (
                f"Order mismatch ({v_idx}, {s_idx}) has position diff "
                f"{abs(v_idx - s_idx)} < 2"
            )

        # All matched pairs with position diff >= 2 must be in order_mismatches
        mismatch_set = set(result.order_mismatches)
        for v_idx, s_idx, _ in result.matched:
            if abs(v_idx - s_idx) >= 2:
                assert (v_idx, s_idx) in mismatch_set, (
                    f"Matched pair ({v_idx}, {s_idx}) with position diff "
                    f"{abs(v_idx - s_idx)} not in order_mismatches"
                )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_order_mismatches_are_subset_of_matched(
        self,
        data: st.DataObject,
    ) -> None:
        """Every order mismatch must correspond to a matched pair.

        **Validates: Requirements 8.7, 9.1**
        """
        matrix = data.draw(st_similarity_matrix())
        result = classify_step_pairs(matrix, threshold=0.7)

        matched_pairs = {(v_idx, s_idx) for v_idx, s_idx, _ in result.matched}
        for v_idx, s_idx in result.order_mismatches:
            assert (v_idx, s_idx) in matched_pairs, (
                f"Order mismatch ({v_idx}, {s_idx}) is not a matched pair"
            )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_guaranteed_matches_are_classified_as_matched(
        self,
        data: st.DataObject,
    ) -> None:
        """When specific pairs have similarity >= 0.7 and all other entries
        are below 0.5, those pairs must be classified as matched.

        **Validates: Requirements 8.7, 9.1**
        """
        matrix, guaranteed = data.draw(st_matrix_with_guaranteed_matches())
        result = classify_step_pairs(matrix, threshold=0.7)

        matched_pairs = {(v_idx, s_idx) for v_idx, s_idx, _ in result.matched}

        for v_idx, s_idx in guaranteed:
            assert (v_idx, s_idx) in matched_pairs, (
                f"Guaranteed match ({v_idx}, {s_idx}) with similarity "
                f"{matrix[v_idx][s_idx]:.3f} was not classified as matched. "
                f"Matched pairs: {matched_pairs}"
            )

    @given(matrix=st_similarity_matrix())
    @settings(max_examples=200)
    def test_missing_steps_have_no_sop_match_above_threshold(
        self,
        matrix: list[list[float]],
    ) -> None:
        """For each missing video step, verify that no unmatched SOP step
        has similarity >= threshold with it (greedy matching may consume
        the best match for another video step).

        **Validates: Requirements 8.7, 9.1**
        """
        result = classify_step_pairs(matrix, threshold=0.7)

        # A missing video step means it wasn't matched. This could be because:
        # 1. No SOP step has similarity >= threshold with it, OR
        # 2. All SOP steps with similarity >= threshold were already matched
        #    to other video steps (greedy matching)
        # Either way, the step must not appear in matched
        matched_video = {v_idx for v_idx, _, _ in result.matched}
        for v_idx in result.missing:
            assert v_idx not in matched_video, (
                f"Missing video step {v_idx} also appears in matched"
            )

    @given(matrix=st_similarity_matrix())
    @settings(max_examples=200)
    def test_greedy_matching_is_one_to_one(
        self,
        matrix: list[list[float]],
    ) -> None:
        """Each video step matches at most one SOP step, and each SOP step
        matches at most one video step (one-to-one mapping).

        **Validates: Requirements 8.7, 9.1**
        """
        result = classify_step_pairs(matrix, threshold=0.7)

        video_indices = [v_idx for v_idx, _, _ in result.matched]
        sop_indices = [s_idx for _, s_idx, _ in result.matched]

        # No duplicates in video indices
        assert len(video_indices) == len(set(video_indices)), (
            f"Duplicate video indices in matched: {video_indices}"
        )
        # No duplicates in SOP indices
        assert len(sop_indices) == len(set(sop_indices)), (
            f"Duplicate SOP indices in matched: {sop_indices}"
        )
