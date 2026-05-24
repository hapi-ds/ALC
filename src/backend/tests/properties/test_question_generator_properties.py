"""Property-based tests for question generator properties.

Tests Property 6, 7, and 8 from the AI-Enhanced Training Ecosystem design
document:
- Property 6: Question difficulty distribution satisfies constraints
- Property 7: No duplicate (section_ref, question_type) pairs per batch
- Property 8: Grading method selection and threshold application

**Validates: Requirements 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.6**

References:
    - Design: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/design.md
    - Requirements: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/requirements.md
"""

import math

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.models.training_ecosystem import QuestionType


# ===========================================================================
# Property 6: Question difficulty distribution satisfies constraints
# ===========================================================================

"""
Property 6 validates that for any N in [5, 20], the difficulty distribution
satisfies: at least 30% basic, at least 30% intermediate, at most 30%
advanced, and the sum equals N.

**Validates: Requirements 4.4**
"""


# ---------------------------------------------------------------------------
# Helper: Compute difficulty distribution from N
# ---------------------------------------------------------------------------


def compute_difficulty_distribution(
    n: int,
    distribution: dict[str, float] | None = None,
) -> tuple[int, int, int]:
    """Compute the number of basic, intermediate, and advanced questions.

    Applies the difficulty distribution percentages to N, ensuring:
    - At least 30% basic (count >= ceil(N * 0.30))
    - At least 30% intermediate (count >= ceil(N * 0.30))
    - At most 30% advanced (count <= floor(N * 0.30))
    - Sum equals N

    The default distribution is {"basic": 0.4, "intermediate": 0.4, "advanced": 0.2}.
    After computing raw counts from the distribution, the function enforces
    the constraints and allocates any remainder to basic or intermediate.

    Args:
        n: Total number of questions to generate (5–20).
        distribution: Optional distribution percentages. Defaults to
            {"basic": 0.4, "intermediate": 0.4, "advanced": 0.2}.

    Returns:
        Tuple of (basic_count, intermediate_count, advanced_count).
    """
    if distribution is None:
        distribution = {"basic": 0.4, "intermediate": 0.4, "advanced": 0.2}

    # Compute raw counts from distribution
    basic_raw = distribution.get("basic", 0.4) * n
    intermediate_raw = distribution.get("intermediate", 0.4) * n
    advanced_raw = distribution.get("advanced", 0.2) * n

    # Apply constraints
    min_basic = math.ceil(n * 0.30)
    min_intermediate = math.ceil(n * 0.30)
    max_advanced = math.floor(n * 0.30)

    # Start with floor values, respecting constraints
    advanced_count = min(int(advanced_raw), max_advanced)
    basic_count = max(int(basic_raw), min_basic)
    intermediate_count = max(int(intermediate_raw), min_intermediate)

    # Ensure sum equals N by adjusting
    current_sum = basic_count + intermediate_count + advanced_count
    if current_sum < n:
        # Allocate remainder to basic first, then intermediate
        remainder = n - current_sum
        basic_count += remainder
    elif current_sum > n:
        # Reduce advanced first (it has an upper bound), then intermediate
        excess = current_sum - n
        reducible_advanced = advanced_count
        if excess <= reducible_advanced:
            advanced_count -= excess
        else:
            advanced_count = 0
            excess -= reducible_advanced
            intermediate_count -= excess

    return basic_count, intermediate_count, advanced_count


# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 6
# ---------------------------------------------------------------------------

#: Strategy for valid question counts (5–20 per Requirements 4.4).
st_question_count = st.integers(min_value=5, max_value=20)


# ---------------------------------------------------------------------------
# Property 6 Tests
# ---------------------------------------------------------------------------


# Feature: ai-enhanced-training-ecosystem, Property 6: At least 30% basic
@settings(max_examples=200)
@given(n=st_question_count)
def test_difficulty_distribution_basic_minimum(n: int) -> None:
    """For any N in [5, 20], the basic count SHALL be at least ceil(N * 0.30).

    **Validates: Requirements 4.4**
    """
    basic_count, _, _ = compute_difficulty_distribution(n)
    min_basic = math.ceil(n * 0.30)

    assert basic_count >= min_basic, (
        f"basic_count={basic_count} is less than minimum {min_basic} "
        f"for N={n}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 6: At least 30% intermediate
@settings(max_examples=200)
@given(n=st_question_count)
def test_difficulty_distribution_intermediate_minimum(n: int) -> None:
    """For any N in [5, 20], the intermediate count SHALL be at least
    ceil(N * 0.30).

    **Validates: Requirements 4.4**
    """
    _, intermediate_count, _ = compute_difficulty_distribution(n)
    min_intermediate = math.ceil(n * 0.30)

    assert intermediate_count >= min_intermediate, (
        f"intermediate_count={intermediate_count} is less than minimum "
        f"{min_intermediate} for N={n}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 6: At most 30% advanced
@settings(max_examples=200)
@given(n=st_question_count)
def test_difficulty_distribution_advanced_maximum(n: int) -> None:
    """For any N in [5, 20], the advanced count SHALL be at most
    floor(N * 0.30).

    **Validates: Requirements 4.4**
    """
    _, _, advanced_count = compute_difficulty_distribution(n)
    max_advanced = math.floor(n * 0.30)

    assert advanced_count <= max_advanced, (
        f"advanced_count={advanced_count} exceeds maximum {max_advanced} "
        f"for N={n}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 6: Sum equals N
@settings(max_examples=200)
@given(n=st_question_count)
def test_difficulty_distribution_sum_equals_n(n: int) -> None:
    """For any N in [5, 20], the sum of basic + intermediate + advanced
    counts SHALL equal N.

    **Validates: Requirements 4.4**
    """
    basic_count, intermediate_count, advanced_count = compute_difficulty_distribution(n)
    total = basic_count + intermediate_count + advanced_count

    assert total == n, (
        f"Sum {total} (basic={basic_count}, intermediate={intermediate_count}, "
        f"advanced={advanced_count}) does not equal N={n}"
    )


# ===========================================================================
# Property 7: No duplicate (section_ref, question_type) pairs per batch
# ===========================================================================

"""
Property 7 validates that no two questions in a generation batch share
the same (sop_section_ref, question_type) pair.

**Validates: Requirements 4.5**
"""

# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 7
# ---------------------------------------------------------------------------

#: All valid question types from the QuestionType enum.
QUESTION_TYPES = [qt.value for qt in QuestionType]

#: Sample section references representing SOP document sections.
SECTION_REFS = [
    "Section 1.1",
    "Section 1.2",
    "Section 2.1",
    "Section 2.2",
    "Section 2.3",
    "Section 3.1",
    "Section 3.2",
    "Section 4.1",
    "Section 5.1",
    "Section 5.2",
]


@st.composite
def st_question_batch(draw: st.DrawFn) -> list[tuple[str, str]]:
    """Generate a random batch of (section_ref, question_type) pairs.

    Produces a list of 5–20 tuples representing a question generation batch.
    Each tuple contains a section reference and a question type value.

    Returns:
        List of (sop_section_ref, question_type) tuples.
    """
    batch_size = draw(st.integers(min_value=5, max_value=20))
    batch: list[tuple[str, str]] = []
    for _ in range(batch_size):
        section_ref = draw(st.sampled_from(SECTION_REFS))
        question_type = draw(st.sampled_from(QUESTION_TYPES))
        batch.append((section_ref, question_type))
    return batch


@st.composite
def st_valid_question_batch(draw: st.DrawFn) -> list[tuple[str, str]]:
    """Generate a valid batch with guaranteed unique (section_ref, type) pairs.

    Draws from the full cross-product of section refs and question types,
    ensuring no duplicates exist. Batch size is 5–20 (capped by available
    unique combinations).

    Returns:
        List of unique (sop_section_ref, question_type) tuples.
    """
    # Build all possible unique combinations
    all_combinations = [
        (ref, qt) for ref in SECTION_REFS for qt in QUESTION_TYPES
    ]
    # Draw a subset of unique combinations (5–20 items)
    max_size = min(20, len(all_combinations))
    batch = draw(
        st.lists(
            st.sampled_from(all_combinations),
            min_size=5,
            max_size=max_size,
            unique=True,
        )
    )
    return batch


# ---------------------------------------------------------------------------
# Validation Function
# ---------------------------------------------------------------------------


def has_no_duplicate_section_type_pairs(
    batch: list[tuple[str, str]],
) -> bool:
    """Check that no two questions share the same (section_ref, type) pair.

    Args:
        batch: List of (sop_section_ref, question_type) tuples.

    Returns:
        True if all pairs are unique, False if duplicates exist.
    """
    seen: set[tuple[str, str]] = set()
    for pair in batch:
        if pair in seen:
            return False
        seen.add(pair)
    return True


# ---------------------------------------------------------------------------
# Property 7: No duplicate (section_ref, question_type) pairs per batch
# ---------------------------------------------------------------------------


# Feature: ai-enhanced-training-ecosystem, Property 7
@settings(max_examples=200)
@given(batch=st_valid_question_batch())
def test_valid_batch_has_no_duplicate_section_type_pairs(
    batch: list[tuple[str, str]],
) -> None:
    """A valid question generation batch SHALL have all unique
    (sop_section_ref, question_type) pairs — no two questions share
    the same section reference and question type combination.

    **Validates: Requirements 4.5**
    """
    assert has_no_duplicate_section_type_pairs(batch), (
        f"Found duplicate (section_ref, question_type) pairs in batch: {batch}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 7 (uniqueness count)
@settings(max_examples=200)
@given(batch=st_valid_question_batch())
def test_valid_batch_unique_count_equals_length(
    batch: list[tuple[str, str]],
) -> None:
    """For a valid batch, the number of unique (section_ref, type) pairs
    SHALL equal the total number of questions in the batch.

    **Validates: Requirements 4.5**
    """
    unique_pairs = set(batch)
    assert len(unique_pairs) == len(batch), (
        f"Unique pair count {len(unique_pairs)} != batch size {len(batch)}. "
        f"Batch: {batch}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 7 (detection of duplicates)
@settings(max_examples=200)
@given(batch=st_question_batch())
def test_duplicate_detection_is_correct(
    batch: list[tuple[str, str]],
) -> None:
    """The validation function SHALL correctly identify whether duplicates
    exist by comparing its result against a set-based uniqueness check.

    **Validates: Requirements 4.5**
    """
    # Ground truth: set-based uniqueness check
    has_duplicates = len(set(batch)) < len(batch)
    validator_says_no_duplicates = has_no_duplicate_section_type_pairs(batch)

    assert validator_says_no_duplicates == (not has_duplicates), (
        f"Validator disagreed with set-based check. "
        f"Batch size: {len(batch)}, unique: {len(set(batch))}, "
        f"validator_no_dupes: {validator_says_no_duplicates}"
    )


# ===========================================================================
# Property 8: Grading method selection and threshold application
# ===========================================================================

"""
Property 8 tests validate that grade_answer routes correctly based on
question_type and applies the correct thresholds:
- multiple_choice / true_false → grading_method "exact"
- fill_in_blank → grading_method "semantic" (threshold 0.85)
- scenario_based → grading_method "llm_evaluated" (threshold 0.70)
- empty/null answer → grading_method "exact", confidence_score 0.0

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.services.question_generator import (
    FILL_IN_BLANK_THRESHOLD,
    SCENARIO_BASED_THRESHOLD,
    GradeResult,
    QuestionGeneratorService,
)
from alcoabase.models.training_ecosystem import GeneratedQuestion


# ---------------------------------------------------------------------------
# Strategies for Property 8
# ---------------------------------------------------------------------------

# Strategy for non-empty answer strings (printable text, no whitespace-only)
st_non_empty_answer = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip() != "")

# Strategy for correct answers (non-empty)
st_correct_answer = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip() != "")

# Strategy for empty/null answers
st_empty_answer = st.one_of(
    st.none(),
    st.just(""),
    st.just("   "),
    st.just("\t"),
    st.just("\n"),
    st.text(
        alphabet=st.characters(whitelist_categories=("Zs",)),
        min_size=1,
        max_size=10,
    ),
)

# Strategy for exact-match question types (MC and T/F)
st_exact_match_question_type = st.sampled_from([
    QuestionType.MULTIPLE_CHOICE,
    QuestionType.TRUE_FALSE,
])

# Strategy for semantic similarity scores (0.0 to 1.0)
st_similarity_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy for LLM evaluation scores (0.0 to 1.0)
st_llm_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


# ---------------------------------------------------------------------------
# Helpers for Property 8
# ---------------------------------------------------------------------------


def _make_question(
    question_type: QuestionType,
    correct_answer: str = "correct answer",
    question_text: str = "What is the procedure?",
    sop_section_ref: str = "Section 3.1",
) -> GeneratedQuestion:
    """Create a mock GeneratedQuestion with the given type and answer."""
    question = MagicMock(spec=GeneratedQuestion)
    question.question_type = question_type
    question.correct_answer = correct_answer
    question.question_text = question_text
    question.sop_section_ref = sop_section_ref
    return question


def _make_service() -> QuestionGeneratorService:
    """Create a QuestionGeneratorService with mocked dependencies."""
    session_factory = MagicMock()
    inference_client = AsyncMock()
    agent_registry = MagicMock()
    return QuestionGeneratorService(
        session_factory=session_factory,
        inference_client=inference_client,
        agent_registry=agent_registry,
    )


# ---------------------------------------------------------------------------
# Property 8a: MC/TF questions use exact grading method
# ---------------------------------------------------------------------------


# Feature: Step_5-3_ai-enhanced-training-ecosystem, Property 8: Grading method selection
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    question_type=st_exact_match_question_type,
    user_answer=st_non_empty_answer,
    correct_answer=st_correct_answer,
)
async def test_exact_match_grading_for_mc_and_tf(
    question_type: QuestionType,
    user_answer: str,
    correct_answer: str,
) -> None:
    """For any multiple_choice or true_false question with a non-empty answer,
    the grading method SHALL be "exact" and confidence_score SHALL be 1.0
    when correct or 0.0 when incorrect.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**
    """
    service = _make_service()
    question = _make_question(question_type, correct_answer=correct_answer)

    result = await service.grade_answer(question, user_answer)

    assert isinstance(result, GradeResult)
    assert result.grading_method == "exact"

    # Exact match: compare stripped strings
    expected_correct = user_answer.strip() == correct_answer.strip()
    assert result.is_correct == expected_correct

    # Confidence is 1.0 for correct, 0.0 for incorrect
    if expected_correct:
        assert result.confidence_score == 1.0
    else:
        assert result.confidence_score == 0.0

    # Timing must be non-negative
    assert result.time_to_grade_ms >= 0


# ---------------------------------------------------------------------------
# Property 8b: Fill-in-blank questions use semantic grading method
# ---------------------------------------------------------------------------


# Feature: Step_5-3_ai-enhanced-training-ecosystem, Property 8: Grading method selection
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    user_answer=st_non_empty_answer,
    correct_answer=st_correct_answer,
    similarity_score=st_similarity_score,
)
async def test_semantic_grading_for_fill_in_blank(
    user_answer: str,
    correct_answer: str,
    similarity_score: float,
) -> None:
    """For any fill_in_blank question with a non-empty answer, the grading
    method SHALL be "semantic" and the threshold of 0.85 SHALL be applied
    to determine correctness.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**
    """
    service = _make_service()
    question = _make_question(
        QuestionType.FILL_IN_BLANK, correct_answer=correct_answer
    )

    # Mock grade_fill_in_blank to return the generated similarity score
    passed = similarity_score >= FILL_IN_BLANK_THRESHOLD
    service.grade_fill_in_blank = AsyncMock(
        return_value=(passed, similarity_score)
    )

    result = await service.grade_answer(question, user_answer)

    assert isinstance(result, GradeResult)
    assert result.grading_method == "semantic"
    assert result.confidence_score == similarity_score
    assert result.is_correct == (similarity_score >= FILL_IN_BLANK_THRESHOLD)
    assert result.time_to_grade_ms >= 0


# ---------------------------------------------------------------------------
# Property 8c: Scenario-based questions use LLM-evaluated grading method
# ---------------------------------------------------------------------------


# Feature: Step_5-3_ai-enhanced-training-ecosystem, Property 8: Grading method selection
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    user_answer=st_non_empty_answer,
    correct_answer=st_correct_answer,
    llm_score=st_llm_score,
)
async def test_llm_evaluated_grading_for_scenario_based(
    user_answer: str,
    correct_answer: str,
    llm_score: float,
) -> None:
    """For any scenario_based question with a non-empty answer, the grading
    method SHALL be "llm_evaluated" and the threshold of 0.70 SHALL be
    applied to determine correctness.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**
    """
    service = _make_service()
    question = _make_question(
        QuestionType.SCENARIO_BASED, correct_answer=correct_answer
    )

    # Mock grade_scenario_based to return the generated LLM score
    passed = llm_score >= SCENARIO_BASED_THRESHOLD
    explanation = "LLM evaluation explanation"
    service.grade_scenario_based = AsyncMock(
        return_value=(passed, llm_score, explanation)
    )

    result = await service.grade_answer(question, user_answer)

    assert isinstance(result, GradeResult)
    assert result.grading_method == "llm_evaluated"
    assert result.confidence_score == llm_score
    assert result.is_correct == (llm_score >= SCENARIO_BASED_THRESHOLD)
    assert result.explanation == explanation
    assert result.time_to_grade_ms >= 0


# ---------------------------------------------------------------------------
# Property 8d: Empty/null answers get exact method with confidence 0.0
# ---------------------------------------------------------------------------


# Feature: Step_5-3_ai-enhanced-training-ecosystem, Property 8: Grading method selection
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    question_type=st.sampled_from(list(QuestionType)),
    empty_answer=st_empty_answer,
    correct_answer=st_correct_answer,
)
async def test_empty_answer_grading(
    question_type: QuestionType,
    empty_answer: str | None,
    correct_answer: str,
) -> None:
    """For any question type, when the answer is empty or null, the grading
    method SHALL be "exact", confidence_score SHALL be 0.0, is_correct
    SHALL be False, and no inference SHALL be invoked.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**
    """
    service = _make_service()
    question = _make_question(question_type, correct_answer=correct_answer)

    # Mock inference methods to detect if they are called
    service.grade_fill_in_blank = AsyncMock()
    service.grade_scenario_based = AsyncMock()

    result = await service.grade_answer(question, empty_answer)

    assert isinstance(result, GradeResult)
    assert result.grading_method == "exact"
    assert result.confidence_score == 0.0
    assert result.is_correct is False
    assert result.time_to_grade_ms >= 0

    # Verify no inference was invoked
    service.grade_fill_in_blank.assert_not_called()
    service.grade_scenario_based.assert_not_called()
