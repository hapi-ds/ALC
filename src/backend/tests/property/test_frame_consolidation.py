"""Property-based tests for frame consolidation into steps.

Tests Property 13: Frame consolidation into steps from the
multimodal-knowledge-base design document.

Property 13 validates that for any sequence of frame embeddings with known
cosine similarities, the consolidation logic correctly:
- Merges consecutive frames with similarity > 0.85 into the same step
- Creates separate steps when consecutive frames have similarity <= 0.85
- Produces a number of steps always <= the number of valid frames

**Validates: Requirements 6.5, 6.6**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 13)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/alignment_service.py
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.alignment_service import AlignmentService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_unit_vector(dimension: int = 16) -> st.SearchStrategy[list[float]]:
    """Generate a normalized unit vector of the given dimension.

    Unit vectors have cosine similarity that depends only on their angle,
    making it easier to reason about similarity values.

    Args:
        dimension: Number of dimensions for the vector.

    Returns:
        Strategy producing normalized float vectors.
    """
    return st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=dimension,
        max_size=dimension,
    ).filter(
        lambda v: sum(x * x for x in v) > 0.01  # Avoid near-zero vectors
    ).map(
        lambda v: _normalize(v)
    )


def _normalize(vec: list[float]) -> list[float]:
    """Normalize a vector to unit length."""
    magnitude = sum(x * x for x in vec) ** 0.5
    if magnitude == 0.0:
        return vec
    return [x / magnitude for x in vec]


def st_similarity_sequence(min_size: int = 2, max_size: int = 20) -> st.SearchStrategy[list[bool]]:
    """Generate a sequence of booleans indicating whether consecutive frames
    should be similar (True = similarity > 0.85) or dissimilar (False = similarity <= 0.85).

    The length is (num_frames - 1) since it represents transitions between frames.

    Args:
        min_size: Minimum number of transitions (frames - 1).
        max_size: Maximum number of transitions (frames - 1).

    Returns:
        Strategy producing lists of booleans.
    """
    return st.lists(
        st.booleans(),
        min_size=min_size,
        max_size=max_size,
    )


def st_interval() -> st.SearchStrategy[int]:
    """Generate frame extraction intervals in seconds (1 to 60).

    Returns:
        Strategy producing integer intervals.
    """
    return st.integers(min_value=1, max_value=60)


def st_none_pattern(num_frames: int) -> st.SearchStrategy[list[bool]]:
    """Generate a pattern of which frames have None descriptions.

    At least one frame must be valid (non-None).

    Args:
        num_frames: Total number of frames.

    Returns:
        Strategy producing lists of booleans (True = valid, False = None).
    """
    return st.lists(
        st.booleans(),
        min_size=num_frames,
        max_size=num_frames,
    ).filter(lambda pattern: any(pattern))


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def build_embeddings_from_similarity_pattern(
    similarity_pattern: list[bool],
    dimension: int = 16,
) -> list[list[float]]:
    """Build a sequence of unit vectors with known cosine similarities.

    For each transition marked True, the next vector is very similar to the
    previous (cosine similarity ~0.95). For False, the next vector is
    dissimilar (cosine similarity ~0.3).

    Args:
        similarity_pattern: List of booleans for each consecutive pair.
        dimension: Vector dimension.

    Returns:
        List of (len(similarity_pattern) + 1) unit vectors.
    """
    import random

    num_vectors = len(similarity_pattern) + 1
    vectors: list[list[float]] = []

    # Start with a random unit vector (deterministic seed for reproducibility)
    rng = random.Random(42)
    first = [rng.gauss(0, 1) for _ in range(dimension)]
    vectors.append(_normalize(first))

    for should_be_similar in similarity_pattern:
        prev = vectors[-1]
        if should_be_similar:
            # Create a vector very close to prev (small perturbation)
            # This gives cosine similarity ~0.95+
            perturbation = [rng.gauss(0, 0.1) for _ in range(dimension)]
            new_vec = [p + d for p, d in zip(prev, perturbation)]
        else:
            # Create a vector far from prev (large random component)
            # This gives cosine similarity ~0.0-0.5
            new_vec = [rng.gauss(0, 1) for _ in range(dimension)]
            # Ensure it's actually dissimilar by subtracting the prev component
            dot = sum(a * b for a, b in zip(_normalize(new_vec), prev))
            if dot > 0.7:
                # Flip to ensure dissimilarity
                new_vec = [-x for x in new_vec]

        vectors.append(_normalize(new_vec))

    return vectors


def count_expected_steps(similarity_pattern: list[bool]) -> int:
    """Count the expected number of steps from a similarity pattern.

    Each False transition creates a new step boundary.

    Args:
        similarity_pattern: List of booleans for transitions.

    Returns:
        Expected number of steps.
    """
    if not similarity_pattern:
        return 1  # Single frame = single step

    # Number of steps = number of False transitions + 1
    return sum(1 for s in similarity_pattern if not s) + 1


# ---------------------------------------------------------------------------
# Property 13: Frame consolidation into steps
# ---------------------------------------------------------------------------


# Feature: multimodal-knowledge-base, Property 13: Frame consolidation into steps
class TestFrameConsolidation:
    """Property tests for frame consolidation into steps.

    For any sequence of frame embeddings with known cosine similarities,
    the _consolidate_frames_into_steps() method SHALL:
    - Merge consecutive frames with similarity > 0.85 into the same step
    - Create separate steps when similarity <= 0.85
    - Produce steps count <= number of valid frames

    **Validates: Requirements 6.5, 6.6**
    """

    @given(
        similarity_pattern=st_similarity_sequence(min_size=1, max_size=15),
        interval_used=st_interval(),
    )
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_consecutive_similar_frames_merged_into_same_step(
        self,
        similarity_pattern: list[bool],
        interval_used: int,
    ) -> None:
        """Consecutive frames with cosine similarity > 0.85 are merged into
        the same step.

        **Validates: Requirements 6.5, 6.6**
        """
        num_frames = len(similarity_pattern) + 1
        embeddings = build_embeddings_from_similarity_pattern(similarity_pattern)

        # Verify our embeddings actually have the intended similarities
        for i, should_be_similar in enumerate(similarity_pattern):
            sim = AlignmentService._cosine_similarity(embeddings[i], embeddings[i + 1])
            if should_be_similar:
                assert sim > 0.85, (
                    f"Expected similar pair at index {i} to have sim > 0.85, got {sim}"
                )

        # Build descriptions (all valid)
        descriptions: list[str | None] = [f"Frame {i} description" for i in range(num_frames)]

        # Mock embedding generation to return our controlled embeddings
        service = AlignmentService()
        with patch.object(
            service, "_generate_frame_embeddings", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = embeddings

            steps = await service._consolidate_frames_into_steps(
                descriptions=descriptions,
                interval_used=interval_used,
            )

        # Verify: consecutive similar frames should be in the same step
        # Build expected grouping
        frame_to_step: dict[int, int] = {}
        current_step = 0
        frame_to_step[0] = current_step
        for i, should_be_similar in enumerate(similarity_pattern):
            if not should_be_similar:
                current_step += 1
            frame_to_step[i + 1] = current_step

        # Verify frames that should be in the same step are indeed grouped
        for step_idx, step in enumerate(steps):
            for frame_idx in step.frame_indices:
                assert frame_to_step[frame_idx] == step_idx, (
                    f"Frame {frame_idx} expected in step {frame_to_step[frame_idx]}, "
                    f"but found in step {step_idx}"
                )

    @given(
        similarity_pattern=st_similarity_sequence(min_size=1, max_size=15),
        interval_used=st_interval(),
    )
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_dissimilar_frames_create_separate_steps(
        self,
        similarity_pattern: list[bool],
        interval_used: int,
    ) -> None:
        """Consecutive frames with cosine similarity <= 0.85 create separate steps.

        **Validates: Requirements 6.5, 6.6**
        """
        num_frames = len(similarity_pattern) + 1
        embeddings = build_embeddings_from_similarity_pattern(similarity_pattern)

        # Verify dissimilar pairs actually have sim <= 0.85
        for i, should_be_similar in enumerate(similarity_pattern):
            sim = AlignmentService._cosine_similarity(embeddings[i], embeddings[i + 1])
            if not should_be_similar:
                assert sim <= 0.85, (
                    f"Expected dissimilar pair at index {i} to have sim <= 0.85, got {sim}"
                )

        descriptions: list[str | None] = [f"Frame {i} description" for i in range(num_frames)]

        service = AlignmentService()
        with patch.object(
            service, "_generate_frame_embeddings", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = embeddings

            steps = await service._consolidate_frames_into_steps(
                descriptions=descriptions,
                interval_used=interval_used,
            )

        # The number of steps should equal the expected count
        expected_steps = count_expected_steps(similarity_pattern)
        assert len(steps) == expected_steps, (
            f"Expected {expected_steps} steps from pattern {similarity_pattern}, "
            f"got {len(steps)}"
        )

    @given(
        similarity_pattern=st_similarity_sequence(min_size=1, max_size=15),
        interval_used=st_interval(),
    )
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_step_count_never_exceeds_valid_frame_count(
        self,
        similarity_pattern: list[bool],
        interval_used: int,
    ) -> None:
        """The number of steps is always <= the number of valid frames.

        **Validates: Requirements 6.5, 6.6**
        """
        num_frames = len(similarity_pattern) + 1
        embeddings = build_embeddings_from_similarity_pattern(similarity_pattern)

        descriptions: list[str | None] = [f"Frame {i} description" for i in range(num_frames)]

        service = AlignmentService()
        with patch.object(
            service, "_generate_frame_embeddings", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = embeddings

            steps = await service._consolidate_frames_into_steps(
                descriptions=descriptions,
                interval_used=interval_used,
            )

        valid_frame_count = sum(1 for d in descriptions if d is not None)
        assert len(steps) <= valid_frame_count, (
            f"Expected steps ({len(steps)}) <= valid frames ({valid_frame_count})"
        )

    @given(
        similarity_pattern=st_similarity_sequence(min_size=1, max_size=10),
        interval_used=st_interval(),
    )
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_step_timestamps_are_consistent(
        self,
        similarity_pattern: list[bool],
        interval_used: int,
    ) -> None:
        """Each step has valid start_timestamp < end_timestamp, and timestamps
        are derived from frame indices and interval_used.

        **Validates: Requirements 6.5, 6.6**
        """
        num_frames = len(similarity_pattern) + 1
        embeddings = build_embeddings_from_similarity_pattern(similarity_pattern)

        descriptions: list[str | None] = [f"Frame {i} description" for i in range(num_frames)]

        service = AlignmentService()
        with patch.object(
            service, "_generate_frame_embeddings", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = embeddings

            steps = await service._consolidate_frames_into_steps(
                descriptions=descriptions,
                interval_used=interval_used,
            )

        for step in steps:
            # start_timestamp should be first frame index * interval
            expected_start = float(step.frame_indices[0] * interval_used)
            expected_end = float((step.frame_indices[-1] + 1) * interval_used)

            assert step.start_timestamp == expected_start, (
                f"Expected start_timestamp={expected_start}, got {step.start_timestamp}"
            )
            assert step.end_timestamp == expected_end, (
                f"Expected end_timestamp={expected_end}, got {step.end_timestamp}"
            )
            assert step.start_timestamp < step.end_timestamp, (
                f"start_timestamp ({step.start_timestamp}) must be < "
                f"end_timestamp ({step.end_timestamp})"
            )

    @given(
        similarity_pattern=st_similarity_sequence(min_size=1, max_size=10),
        interval_used=st_interval(),
    )
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_none_descriptions_are_excluded_from_steps(
        self,
        similarity_pattern: list[bool],
        interval_used: int,
    ) -> None:
        """Frames with None descriptions are excluded from consolidation.
        Only valid frames participate in step grouping.

        **Validates: Requirements 6.5, 6.6**
        """
        num_frames = len(similarity_pattern) + 1

        # Make some frames None (but keep at least 2 valid for meaningful test)
        # We'll set every other frame to None if we have enough frames
        descriptions: list[str | None] = []
        for i in range(num_frames):
            if i % 3 == 1 and num_frames > 3:
                descriptions.append(None)
            else:
                descriptions.append(f"Frame {i} description")

        valid_count = sum(1 for d in descriptions if d is not None)
        if valid_count == 0:
            return  # Skip degenerate case

        # Build embeddings only for valid frames
        # Use all-similar pattern for simplicity (all merge into one step)
        valid_embeddings = []
        base_vec = _normalize([1.0] * 16)
        for _ in range(valid_count):
            valid_embeddings.append(base_vec[:])

        service = AlignmentService()
        with patch.object(
            service, "_generate_frame_embeddings", new_callable=AsyncMock
        ) as mock_embed:
            mock_embed.return_value = valid_embeddings

            steps = await service._consolidate_frames_into_steps(
                descriptions=descriptions,
                interval_used=interval_used,
            )

        # All frame_indices in steps should correspond to non-None descriptions
        all_step_frame_indices = []
        for step in steps:
            all_step_frame_indices.extend(step.frame_indices)

        for idx in all_step_frame_indices:
            assert descriptions[idx] is not None, (
                f"Frame index {idx} in steps has None description"
            )

        # Total frame indices should equal valid frame count
        assert len(all_step_frame_indices) == valid_count, (
            f"Expected {valid_count} frame indices in steps, "
            f"got {len(all_step_frame_indices)}"
        )

    @pytest.mark.asyncio
    async def test_empty_descriptions_returns_empty_steps(self) -> None:
        """When all descriptions are None, no steps are produced.

        **Validates: Requirements 6.5, 6.6**
        """
        descriptions: list[str | None] = [None, None, None]

        service = AlignmentService()
        steps = await service._consolidate_frames_into_steps(
            descriptions=descriptions,
            interval_used=5,
        )

        assert steps == [], f"Expected empty steps, got {steps}"
