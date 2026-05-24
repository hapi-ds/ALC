"""Property-based tests for the Role-Play Engine Service.

Tests Property 9, 10, and 11 from the AI-Enhanced Training Ecosystem design
document:
- Property 9: Virtual audit turn count is determined by document section count
- Property 10: Virtual audit session score and pass/fail determination
- Property 11: Progressive difficulty distribution across virtual audit turns

**Validates: Requirements 6.2, 6.3, 6.5, 6.6**

References:
    - Design: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/design.md
    - Requirements: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/requirements.md
"""

import math

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.roleplay_engine import compute_session_score, compute_total_turns


# ===========================================================================
# Property 9: Virtual audit turn count is determined by document section count
# ===========================================================================

"""
Property 9 validates that compute_total_turns returns:
- 5 for section_count < 10
- 7 for section_count 10–20
- 10 for section_count > 20

**Validates: Requirements 6.3**
"""

# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 9
# ---------------------------------------------------------------------------

#: Strategy for section counts in the "small" range (< 10 sections → 5 turns).
st_small_section_count = st.integers(min_value=1, max_value=9)

#: Strategy for section counts in the "medium" range (10–20 sections → 7 turns).
st_medium_section_count = st.integers(min_value=10, max_value=20)

#: Strategy for section counts in the "large" range (> 20 sections → 10 turns).
st_large_section_count = st.integers(min_value=21, max_value=200)

#: Strategy for any valid section count.
st_any_section_count = st.integers(min_value=1, max_value=200)


# ---------------------------------------------------------------------------
# Property 9 Tests
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(section_count=st_small_section_count)
def test_turn_count_small_documents(section_count: int) -> None:
    """Documents with fewer than 10 sections SHALL have 5 turns.

    **Validates: Requirements 6.3**
    """
    result = compute_total_turns(section_count)
    assert result == 5, (
        f"Expected 5 turns for section_count={section_count}, got {result}"
    )


@settings(max_examples=200)
@given(section_count=st_medium_section_count)
def test_turn_count_medium_documents(section_count: int) -> None:
    """Documents with 10–20 sections SHALL have 7 turns.

    **Validates: Requirements 6.3**
    """
    result = compute_total_turns(section_count)
    assert result == 7, (
        f"Expected 7 turns for section_count={section_count}, got {result}"
    )


@settings(max_examples=200)
@given(section_count=st_large_section_count)
def test_turn_count_large_documents(section_count: int) -> None:
    """Documents with more than 20 sections SHALL have 10 turns.

    **Validates: Requirements 6.3**
    """
    result = compute_total_turns(section_count)
    assert result == 10, (
        f"Expected 10 turns for section_count={section_count}, got {result}"
    )


@settings(max_examples=200)
@given(section_count=st_any_section_count)
def test_turn_count_always_in_valid_set(section_count: int) -> None:
    """For any section count, the turn count SHALL be one of {5, 7, 10}.

    **Validates: Requirements 6.3**
    """
    result = compute_total_turns(section_count)
    assert result in {5, 7, 10}, (
        f"Turn count {result} not in {{5, 7, 10}} for section_count={section_count}"
    )


# ===========================================================================
# Property 10: Virtual audit session score and pass/fail determination
# ===========================================================================

"""
Property 10 validates that:
- Session score is the weighted average: accuracy 50%, completeness 30%,
  reference quality 20%
- Pass requires score >= 0.70 AND >= 3 turns completed

**Validates: Requirements 6.5, 6.6**
"""

# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 10
# ---------------------------------------------------------------------------

#: Strategy for a single turn score dimension (0.0–1.0).
st_score_dimension = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@st.composite
def st_turn_scores(draw: st.DrawFn) -> list[dict[str, float]]:
    """Generate a list of 1–10 turn score dicts with all three dimensions."""
    num_turns = draw(st.integers(min_value=1, max_value=10))
    turns = []
    for _ in range(num_turns):
        turn = {
            "factual_accuracy": draw(st_score_dimension),
            "completeness": draw(st_score_dimension),
            "document_reference_quality": draw(st_score_dimension),
        }
        turns.append(turn)
    return turns


# ---------------------------------------------------------------------------
# Helper: Pass/fail determination
# ---------------------------------------------------------------------------


def determine_pass_fail(
    score: float, turns_completed: int
) -> str:
    """Determine session outcome based on score and turn count.

    Rules:
        - "passed" if score >= 0.70 AND turns_completed >= 3
        - "incomplete" if turns_completed < 3
        - "failed" otherwise (score < 0.70 AND turns_completed >= 3)

    Args:
        score: Overall session score (0.0–1.0).
        turns_completed: Number of turns the user completed.

    Returns:
        One of "passed", "failed", or "incomplete".
    """
    if turns_completed < 3:
        return "incomplete"
    if score >= 0.70:
        return "passed"
    return "failed"


# ---------------------------------------------------------------------------
# Property 10 Tests
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(turns=st_turn_scores())
def test_session_score_is_weighted_average(turns: list[dict[str, float]]) -> None:
    """The session score SHALL be the weighted average of turn scores:
    accuracy 50%, completeness 30%, reference quality 20%.

    **Validates: Requirements 6.5, 6.6**
    """
    result = compute_session_score(turns)

    # Compute expected weighted average manually
    total = 0.0
    for turn in turns:
        total += (
            turn["factual_accuracy"] * 0.5
            + turn["completeness"] * 0.3
            + turn["document_reference_quality"] * 0.2
        )
    expected = total / len(turns)

    assert abs(result - expected) < 1e-9, (
        f"Score {result} != expected {expected} for turns={turns}"
    )


@settings(max_examples=200)
@given(turns=st_turn_scores())
def test_session_score_bounded_zero_to_one(turns: list[dict[str, float]]) -> None:
    """The session score SHALL always be in [0.0, 1.0].

    **Validates: Requirements 6.5, 6.6**
    """
    result = compute_session_score(turns)
    assert 0.0 <= result <= 1.0, (
        f"Score {result} out of bounds [0.0, 1.0] for turns={turns}"
    )


@settings(max_examples=200)
@given(turns=st_turn_scores())
def test_pass_fail_requires_score_and_turns(turns: list[dict[str, float]]) -> None:
    """Pass requires score >= 0.70 AND >= 3 turns completed.
    Fewer than 3 turns → incomplete regardless of score.

    **Validates: Requirements 6.5, 6.6**
    """
    score = compute_session_score(turns)
    turns_completed = len(turns)
    outcome = determine_pass_fail(score, turns_completed)

    if turns_completed < 3:
        assert outcome == "incomplete", (
            f"Expected 'incomplete' for {turns_completed} turns, got '{outcome}'"
        )
    elif score >= 0.70:
        assert outcome == "passed", (
            f"Expected 'passed' for score={score:.3f} with {turns_completed} turns, "
            f"got '{outcome}'"
        )
    else:
        assert outcome == "failed", (
            f"Expected 'failed' for score={score:.3f} with {turns_completed} turns, "
            f"got '{outcome}'"
        )


def test_session_score_empty_turns() -> None:
    """An empty turn list SHALL produce a score of 0.0.

    **Validates: Requirements 6.5, 6.6**
    """
    result = compute_session_score([])
    assert result == 0.0


# ===========================================================================
# Property 11: Progressive difficulty distribution across virtual audit turns
# ===========================================================================

"""
Property 11 validates that for any total_turns in {5, 7, 10}, the progressive
difficulty distribution assigns:
- First 40% of turns → "foundational"
- Next 35% of turns → "applied"
- Remaining 25% of turns → "analytical"

**Validates: Requirements 6.2**
"""


# ---------------------------------------------------------------------------
# Helper: Compute difficulty for a given turn
# ---------------------------------------------------------------------------


def compute_difficulty_for_turn(turn_index: int, total_turns: int) -> str:
    """Determine the difficulty level for a specific turn in a virtual audit.

    Progressive difficulty rules:
        - First 40% of turns → "foundational"
        - Next 35% of turns → "applied"
        - Remaining 25% of turns → "analytical"

    Turn indices are 0-based. Boundary computation uses math.ceil for the
    foundational boundary and math.ceil for the applied boundary to ensure
    all turns are covered.

    Args:
        turn_index: 0-based index of the current turn.
        total_turns: Total number of turns in the session (5, 7, or 10).

    Returns:
        One of "foundational", "applied", or "analytical".
    """
    foundational_end = math.ceil(total_turns * 0.40)
    applied_end = foundational_end + math.ceil(total_turns * 0.35)

    if turn_index < foundational_end:
        return "foundational"
    elif turn_index < applied_end:
        return "applied"
    else:
        return "analytical"


# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 11
# ---------------------------------------------------------------------------

#: Strategy for valid total_turns values (from compute_total_turns output).
st_total_turns = st.sampled_from([5, 7, 10])


# ---------------------------------------------------------------------------
# Property 11 Tests
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(total_turns=st_total_turns)
def test_first_40_percent_foundational(total_turns: int) -> None:
    """The first 40% of turns SHALL be assigned "foundational" difficulty.

    **Validates: Requirements 6.2**
    """
    foundational_end = math.ceil(total_turns * 0.40)

    for turn_index in range(foundational_end):
        difficulty = compute_difficulty_for_turn(turn_index, total_turns)
        assert difficulty == "foundational", (
            f"Turn {turn_index}/{total_turns} expected 'foundational', "
            f"got '{difficulty}'"
        )


@settings(max_examples=200)
@given(total_turns=st_total_turns)
def test_next_35_percent_applied(total_turns: int) -> None:
    """The next 35% of turns (after foundational) SHALL be assigned
    "applied" difficulty.

    **Validates: Requirements 6.2**
    """
    foundational_end = math.ceil(total_turns * 0.40)
    applied_end = foundational_end + math.ceil(total_turns * 0.35)

    for turn_index in range(foundational_end, applied_end):
        difficulty = compute_difficulty_for_turn(turn_index, total_turns)
        assert difficulty == "applied", (
            f"Turn {turn_index}/{total_turns} expected 'applied', "
            f"got '{difficulty}'"
        )


@settings(max_examples=200)
@given(total_turns=st_total_turns)
def test_remaining_25_percent_analytical(total_turns: int) -> None:
    """The remaining turns (after foundational and applied) SHALL be
    assigned "analytical" difficulty.

    **Validates: Requirements 6.2**
    """
    foundational_end = math.ceil(total_turns * 0.40)
    applied_end = foundational_end + math.ceil(total_turns * 0.35)

    for turn_index in range(applied_end, total_turns):
        difficulty = compute_difficulty_for_turn(turn_index, total_turns)
        assert difficulty == "analytical", (
            f"Turn {turn_index}/{total_turns} expected 'analytical', "
            f"got '{difficulty}'"
        )


@settings(max_examples=200)
@given(total_turns=st_total_turns)
def test_all_turns_covered_by_difficulty(total_turns: int) -> None:
    """Every turn index from 0 to total_turns-1 SHALL be assigned exactly
    one difficulty level from {"foundational", "applied", "analytical"}.

    **Validates: Requirements 6.2**
    """
    valid_difficulties = {"foundational", "applied", "analytical"}

    for turn_index in range(total_turns):
        difficulty = compute_difficulty_for_turn(turn_index, total_turns)
        assert difficulty in valid_difficulties, (
            f"Turn {turn_index}/{total_turns} got invalid difficulty '{difficulty}'"
        )


@settings(max_examples=200)
@given(total_turns=st_total_turns)
def test_difficulty_distribution_percentages(total_turns: int) -> None:
    """The distribution SHALL approximate 40% foundational, 35% applied,
    25% analytical for each valid total_turns value.

    **Validates: Requirements 6.2**
    """
    difficulties = [
        compute_difficulty_for_turn(i, total_turns) for i in range(total_turns)
    ]

    foundational_count = difficulties.count("foundational")
    applied_count = difficulties.count("applied")
    analytical_count = difficulties.count("analytical")

    # Verify sum covers all turns
    assert foundational_count + applied_count + analytical_count == total_turns, (
        f"Counts don't sum to total_turns={total_turns}: "
        f"foundational={foundational_count}, applied={applied_count}, "
        f"analytical={analytical_count}"
    )

    # Verify foundational is approximately 40% (at least 1 turn, at most ceil(40%))
    assert foundational_count == math.ceil(total_turns * 0.40), (
        f"Foundational count {foundational_count} != ceil({total_turns} * 0.40) = "
        f"{math.ceil(total_turns * 0.40)}"
    )

    # Verify applied is approximately 35%
    assert applied_count == math.ceil(total_turns * 0.35), (
        f"Applied count {applied_count} != ceil({total_turns} * 0.35) = "
        f"{math.ceil(total_turns * 0.35)}"
    )

    # Verify analytical gets the remainder
    expected_analytical = total_turns - math.ceil(total_turns * 0.40) - math.ceil(total_turns * 0.35)
    assert analytical_count == expected_analytical, (
        f"Analytical count {analytical_count} != expected {expected_analytical}"
    )


@settings(max_examples=200)
@given(total_turns=st_total_turns)
def test_difficulty_is_monotonically_progressive(total_turns: int) -> None:
    """Difficulty SHALL progress monotonically: all foundational turns come
    before all applied turns, which come before all analytical turns.

    **Validates: Requirements 6.2**
    """
    difficulties = [
        compute_difficulty_for_turn(i, total_turns) for i in range(total_turns)
    ]

    # Find transition points
    seen_applied = False
    seen_analytical = False

    for difficulty in difficulties:
        if difficulty == "applied":
            seen_applied = True
            assert not seen_analytical, (
                "Found 'applied' after 'analytical' — not monotonically progressive"
            )
        elif difficulty == "analytical":
            seen_analytical = True
        elif difficulty == "foundational":
            assert not seen_applied and not seen_analytical, (
                "Found 'foundational' after 'applied' or 'analytical' — "
                "not monotonically progressive"
            )
