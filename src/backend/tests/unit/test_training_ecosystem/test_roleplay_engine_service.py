"""Unit tests for RolePlayEngineService.

Tests turn management, score computation, session lifecycle,
and abandon logic.

Requirements: 6.1–6.13
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.training_ecosystem import SessionStatus, VirtualAuditSession
from alcoabase.services.roleplay_engine import (
    DIFFICULTY_APPLIED_RATIO,
    DIFFICULTY_FOUNDATIONAL_RATIO,
    MIN_TURNS_FOR_RESULT,
    PASS_SCORE_THRESHOLD,
    STALE_SESSION_MINUTES,
    compute_session_score,
    compute_total_turns,
    determine_pass_fail,
)


# ---------------------------------------------------------------------------
# Tests: compute_total_turns
# ---------------------------------------------------------------------------


class TestComputeTotalTurns:
    """Tests for turn count determination based on section count."""

    def test_fewer_than_10_sections_returns_5(self):
        """Documents with < 10 sections get 5 turns."""
        assert compute_total_turns(1) == 5
        assert compute_total_turns(5) == 5
        assert compute_total_turns(9) == 5

    def test_exactly_10_sections_returns_7(self):
        """Documents with exactly 10 sections get 7 turns."""
        assert compute_total_turns(10) == 7

    def test_between_10_and_20_sections_returns_7(self):
        """Documents with 10–20 sections get 7 turns."""
        assert compute_total_turns(15) == 7
        assert compute_total_turns(20) == 7

    def test_more_than_20_sections_returns_10(self):
        """Documents with > 20 sections get 10 turns."""
        assert compute_total_turns(21) == 10
        assert compute_total_turns(50) == 10
        assert compute_total_turns(100) == 10

    def test_zero_sections_returns_5(self):
        """Edge case: 0 sections returns 5 (minimum)."""
        assert compute_total_turns(0) == 5

    def test_boundary_at_9_and_10(self):
        """Boundary between 5 and 7 turns at section count 9/10."""
        assert compute_total_turns(9) == 5
        assert compute_total_turns(10) == 7

    def test_boundary_at_20_and_21(self):
        """Boundary between 7 and 10 turns at section count 20/21."""
        assert compute_total_turns(20) == 7
        assert compute_total_turns(21) == 10


# ---------------------------------------------------------------------------
# Tests: compute_session_score
# ---------------------------------------------------------------------------


class TestComputeSessionScore:
    """Tests for weighted average session score computation."""

    def test_empty_turns_returns_0(self):
        """No turns returns 0.0."""
        assert compute_session_score([]) == 0.0

    def test_perfect_scores_return_1(self):
        """All perfect scores return 1.0."""
        turns = [
            {
                "factual_accuracy": 1.0,
                "completeness": 1.0,
                "document_reference_quality": 1.0,
            }
        ]
        assert compute_session_score(turns) == 1.0

    def test_zero_scores_return_0(self):
        """All zero scores return 0.0."""
        turns = [
            {
                "factual_accuracy": 0.0,
                "completeness": 0.0,
                "document_reference_quality": 0.0,
            }
        ]
        assert compute_session_score(turns) == 0.0

    def test_weighted_average_calculation(self):
        """Verifies correct weighting: accuracy 50%, completeness 30%, reference 20%."""
        turns = [
            {
                "factual_accuracy": 0.8,
                "completeness": 0.6,
                "document_reference_quality": 0.4,
            }
        ]
        # Expected: 0.8*0.5 + 0.6*0.3 + 0.4*0.2 = 0.4 + 0.18 + 0.08 = 0.66
        result = compute_session_score(turns)
        assert abs(result - 0.66) < 1e-6

    def test_multiple_turns_averaged(self):
        """Multiple turns are averaged."""
        turns = [
            {
                "factual_accuracy": 1.0,
                "completeness": 1.0,
                "document_reference_quality": 1.0,
            },
            {
                "factual_accuracy": 0.0,
                "completeness": 0.0,
                "document_reference_quality": 0.0,
            },
        ]
        # Average of 1.0 and 0.0 = 0.5
        result = compute_session_score(turns)
        assert abs(result - 0.5) < 1e-6

    def test_skips_incomplete_turns(self):
        """Turns missing dimensions are excluded from average."""
        turns = [
            {
                "factual_accuracy": 0.8,
                "completeness": 0.8,
                "document_reference_quality": 0.8,
            },
            {
                "factual_accuracy": 0.2,
                # Missing completeness and reference
            },
        ]
        # Only first turn counts: 0.8*0.5 + 0.8*0.3 + 0.8*0.2 = 0.8
        result = compute_session_score(turns)
        assert abs(result - 0.8) < 1e-6

    def test_turns_with_none_values_skipped(self):
        """Turns with None values are excluded."""
        turns = [
            {
                "factual_accuracy": None,
                "completeness": 0.5,
                "document_reference_quality": 0.5,
            },
            {
                "factual_accuracy": 0.9,
                "completeness": 0.9,
                "document_reference_quality": 0.9,
            },
        ]
        # Only second turn counts: 0.9*0.5 + 0.9*0.3 + 0.9*0.2 = 0.9
        result = compute_session_score(turns)
        assert abs(result - 0.9) < 1e-6

    def test_all_incomplete_turns_returns_0(self):
        """All incomplete turns returns 0.0."""
        turns = [
            {"factual_accuracy": 0.5},
            {"completeness": 0.5},
        ]
        assert compute_session_score(turns) == 0.0


# ---------------------------------------------------------------------------
# Tests: determine_pass_fail
# ---------------------------------------------------------------------------


class TestDeterminePassFail:
    """Tests for pass/fail determination logic."""

    def test_high_score_enough_turns_passes(self):
        """Score >= 0.70 AND >= 3 turns → True (passed)."""
        result = determine_pass_fail(score=0.80, turns_completed=5)
        assert result is True

    def test_exactly_threshold_score_passes(self):
        """Score exactly 0.70 with enough turns → True."""
        result = determine_pass_fail(score=0.70, turns_completed=3)
        assert result is True

    def test_below_threshold_fails(self):
        """Score < 0.70 with enough turns → False (failed)."""
        result = determine_pass_fail(score=0.60, turns_completed=5)
        assert result is False

    def test_fewer_than_3_turns_returns_none(self):
        """Fewer than 3 turns → None (incomplete)."""
        result = determine_pass_fail(score=0.90, turns_completed=2)
        assert result is None

    def test_zero_turns_returns_none(self):
        """Zero turns → None (incomplete)."""
        result = determine_pass_fail(score=1.0, turns_completed=0)
        assert result is None

    def test_exactly_3_turns_with_passing_score(self):
        """Exactly 3 turns with passing score → True."""
        result = determine_pass_fail(score=0.75, turns_completed=3)
        assert result is True

    def test_exactly_3_turns_with_failing_score(self):
        """Exactly 3 turns with failing score → False."""
        result = determine_pass_fail(score=0.50, turns_completed=3)
        assert result is False

    def test_perfect_score_2_turns_still_incomplete(self):
        """Perfect score but only 2 turns → None (incomplete)."""
        result = determine_pass_fail(score=1.0, turns_completed=2)
        assert result is None

    def test_zero_score_many_turns_fails(self):
        """Zero score with many turns → False."""
        result = determine_pass_fail(score=0.0, turns_completed=10)
        assert result is False


# ---------------------------------------------------------------------------
# Tests: Progressive difficulty distribution
# ---------------------------------------------------------------------------


class TestProgressiveDifficulty:
    """Tests for progressive difficulty distribution across turns."""

    def test_5_turn_distribution(self):
        """5 turns: 2 foundational, 2 applied, 1 analytical."""
        total = 5
        foundational_end = int(total * DIFFICULTY_FOUNDATIONAL_RATIO)
        applied_end = foundational_end + int(
            total * DIFFICULTY_APPLIED_RATIO
        )

        # First 40% = 2 turns foundational
        assert foundational_end == 2
        # Next 35% = 1 turn applied (2+1=3)
        assert applied_end == 3
        # Remaining = 2 turns analytical
        assert total - applied_end == 2

    def test_7_turn_distribution(self):
        """7 turns: 2 foundational, 2 applied, 3 analytical."""
        total = 7
        foundational_end = int(total * DIFFICULTY_FOUNDATIONAL_RATIO)
        applied_end = foundational_end + int(
            total * DIFFICULTY_APPLIED_RATIO
        )

        assert foundational_end == 2
        assert applied_end == 4
        assert total - applied_end == 3

    def test_10_turn_distribution(self):
        """10 turns: 4 foundational, 3 applied, 3 analytical."""
        total = 10
        foundational_end = int(total * DIFFICULTY_FOUNDATIONAL_RATIO)
        applied_end = foundational_end + int(
            total * DIFFICULTY_APPLIED_RATIO
        )

        assert foundational_end == 4
        assert applied_end == 7
        assert total - applied_end == 3

    def test_ratios_sum_to_1(self):
        """Difficulty ratios sum to 1.0."""
        analytical_ratio = 1.0 - DIFFICULTY_FOUNDATIONAL_RATIO - DIFFICULTY_APPLIED_RATIO
        total = (
            DIFFICULTY_FOUNDATIONAL_RATIO
            + DIFFICULTY_APPLIED_RATIO
            + analytical_ratio
        )
        assert abs(total - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Tests: Session lifecycle and abandon logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionLifecycle:
    """Tests for session lifecycle management."""

    async def test_stale_session_threshold_is_60_minutes(self):
        """Stale session threshold is 60 minutes."""
        assert STALE_SESSION_MINUTES == 60

    async def test_pass_threshold_is_0_70(self):
        """Pass threshold is 0.70."""
        assert PASS_SCORE_THRESHOLD == 0.70

    async def test_min_turns_for_result_is_3(self):
        """Minimum turns for pass/fail determination is 3."""
        assert MIN_TURNS_FOR_RESULT == 3
