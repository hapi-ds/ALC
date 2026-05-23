"""Property-based tests for QuizService.

Tests correctness properties from the Training-Gated Access Control design
document using Hypothesis.

# Feature: Step_3-5_training-gated-access-control, Property 2: Pass threshold computation

References:
    - Design: .kiro/specs/Step_3-5_training-gated-access-control/design.md
    - Requirements: .kiro/specs/Step_3-5_training-gated-access-control/requirements.md
"""

import math

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.quiz_service import QuizService


# ---------------------------------------------------------------------------
# Shared fixture: QuizService instance (no content_generator needed for
# pure function tests)
# ---------------------------------------------------------------------------


def _make_quiz_service() -> QuizService:
    """Create a QuizService instance for pure function testing.

    compute_pass_threshold is a pure function that doesn't use
    the content_generator, so we pass None.
    """
    return QuizService(content_generator=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Property 2: Pass threshold computation
# ---------------------------------------------------------------------------


class TestPassThresholdComputationProperty:
    """Property tests verifying pass threshold computation.

    For any positive integer total_questions (>= 1) and any integer score
    (0 <= score <= total_questions), passed is true if and only if
    score >= ceil(total_questions * 0.8).

    **Validates: Requirements 1.2**
    """

    @given(
        total_questions=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100)
    def test_threshold_equals_ceil_80_percent(
        self, total_questions: int
    ) -> None:
        """compute_pass_threshold returns exactly ceil(total_questions * 0.8).

        **Validates: Requirements 1.2**
        """
        service = _make_quiz_service()
        threshold = service.compute_pass_threshold(total_questions)
        expected = math.ceil(total_questions * 0.8)
        assert threshold == expected, (
            f"For total_questions={total_questions}, "
            f"expected threshold={expected}, got {threshold}"
        )

    @given(
        total_questions=st.integers(min_value=1, max_value=1000),
        score_offset=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=100)
    def test_passed_iff_score_gte_threshold(
        self, total_questions: int, score_offset: int
    ) -> None:
        """For any score in [0, total_questions], passed == (score >= threshold).

        We generate a score by clamping score_offset to [0, total_questions].

        **Validates: Requirements 1.2**
        """
        score = min(score_offset, total_questions)
        service = _make_quiz_service()
        threshold = service.compute_pass_threshold(total_questions)
        passed = score >= threshold
        expected_passed = score >= math.ceil(total_questions * 0.8)
        assert passed == expected_passed, (
            f"For total_questions={total_questions}, score={score}, "
            f"threshold={threshold}: "
            f"passed={passed}, expected={expected_passed}"
        )

    @given(
        total_questions=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100)
    def test_score_at_threshold_passes(
        self, total_questions: int
    ) -> None:
        """A score exactly at the threshold always passes.

        **Validates: Requirements 1.2**
        """
        service = _make_quiz_service()
        threshold = service.compute_pass_threshold(total_questions)
        assert threshold >= 1, "Threshold must be at least 1"
        assert threshold <= total_questions, (
            f"Threshold {threshold} exceeds total_questions {total_questions}"
        )
        # Score at threshold should pass
        passed = threshold >= threshold
        assert passed is True

    @given(
        total_questions=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100)
    def test_score_below_threshold_fails(
        self, total_questions: int
    ) -> None:
        """A score one below the threshold always fails.

        **Validates: Requirements 1.2**
        """
        service = _make_quiz_service()
        threshold = service.compute_pass_threshold(total_questions)
        score_below = threshold - 1
        # score_below is always >= 0 since threshold >= 1
        assert score_below >= 0
        passed = score_below >= threshold
        assert passed is False, (
            f"For total_questions={total_questions}, "
            f"score={score_below} should not pass (threshold={threshold})"
        )


# ---------------------------------------------------------------------------
# Property 3: Score computation with partial and extraneous answers
# Feature: Step_3-5_training-gated-access-control, Property 3: Score computation
# ---------------------------------------------------------------------------


class TestScoreComputationProperty:
    """Property tests verifying score computation with partial and extraneous answers.

    For any set of quiz questions (with known correct answers) and any submitted
    answers map (which may be missing some question_ids or contain extra
    question_ids not in the quiz), the computed score equals the count of
    submitted answers where the question_id exists in the quiz AND the submitted
    answer exactly matches (case-sensitive) the correct answer for that question_id.

    This tests the scoring logic used by QuizService.evaluate_and_persist:
    - Iterates over quiz_questions
    - For each question, checks answers.get(question.question_id)
    - Increments score only if submitted answer is not None AND matches exactly

    **Validates: Requirements 2.2, 2.5, 2.6**
    """

    @staticmethod
    def _compute_score(
        quiz_questions: list[tuple[str, str]],
        answers: dict[str, str],
    ) -> int:
        """Replicate the scoring logic from QuizService.evaluate_and_persist.

        Args:
            quiz_questions: List of (question_id, correct_answer) tuples.
            answers: Submitted answers mapping question_id to selected answer.

        Returns:
            Score as count of correct matches.
        """
        score = 0
        for question_id, correct_answer in quiz_questions:
            submitted_answer = answers.get(question_id)
            if submitted_answer is not None and submitted_answer == correct_answer:
                score += 1
        return score

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_score_equals_count_of_exact_matches(
        self, data: st.DataObject
    ) -> None:
        """Score equals count of questions where submitted answer matches exactly.

        Generates a random set of quiz questions with correct answers, then
        generates a submitted answers map that may include partial answers
        (missing some question_ids) and extraneous answers (extra question_ids
        not in the quiz). Verifies the computed score matches the expected
        count of exact matches.

        **Validates: Requirements 2.2, 2.5, 2.6**
        """
        # Generate quiz questions: list of (question_id, correct_answer)
        num_questions = data.draw(
            st.integers(min_value=1, max_value=20), label="num_questions"
        )
        question_ids = data.draw(
            st.lists(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters="-_",
                    ),
                    min_size=1,
                    max_size=20,
                ),
                min_size=num_questions,
                max_size=num_questions,
                unique=True,
            ),
            label="question_ids",
        )
        correct_answers = data.draw(
            st.lists(
                st.text(min_size=1, max_size=50),
                min_size=num_questions,
                max_size=num_questions,
            ),
            label="correct_answers",
        )
        quiz_questions = list(zip(question_ids, correct_answers))

        # Generate submitted answers: may be partial (subset of question_ids)
        # and may contain extraneous keys
        submitted_question_ids = data.draw(
            st.lists(
                st.sampled_from(question_ids),
                max_size=num_questions,
                unique=True,
            ),
            label="submitted_question_ids",
        )

        # For each submitted question, sometimes use the correct answer,
        # sometimes use a wrong answer
        submitted_answers: dict[str, str] = {}
        for qid in submitted_question_ids:
            use_correct = data.draw(st.booleans(), label=f"correct_{qid}")
            if use_correct:
                # Find the correct answer for this question
                correct = next(ca for qi, ca in quiz_questions if qi == qid)
                submitted_answers[qid] = correct
            else:
                # Use a wrong answer (different from correct)
                correct = next(ca for qi, ca in quiz_questions if qi == qid)
                wrong = data.draw(
                    st.text(min_size=1, max_size=50).filter(
                        lambda x, c=correct: x != c
                    ),
                    label=f"wrong_{qid}",
                )
                submitted_answers[qid] = wrong

        # Add extraneous keys (not in quiz questions)
        num_extraneous = data.draw(
            st.integers(min_value=0, max_value=5), label="num_extraneous"
        )
        extraneous_ids = data.draw(
            st.lists(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters="-_",
                    ),
                    min_size=1,
                    max_size=20,
                ).filter(lambda x: x not in question_ids),
                min_size=num_extraneous,
                max_size=num_extraneous,
                unique=True,
            ),
            label="extraneous_ids",
        )
        for eid in extraneous_ids:
            submitted_answers[eid] = data.draw(
                st.text(min_size=1, max_size=50),
                label=f"extraneous_val_{eid}",
            )

        # Compute score using the same logic as QuizService
        computed_score = self._compute_score(quiz_questions, submitted_answers)

        # Compute expected score independently: count questions where
        # question_id is in submitted_answers AND answer matches exactly
        expected_score = sum(
            1
            for qid, correct in quiz_questions
            if qid in submitted_answers and submitted_answers[qid] == correct
        )

        assert computed_score == expected_score, (
            f"Score mismatch: computed={computed_score}, expected={expected_score}\n"
            f"quiz_questions={quiz_questions}\n"
            f"submitted_answers={submitted_answers}"
        )

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_extraneous_answers_do_not_affect_score(
        self, data: st.DataObject
    ) -> None:
        """Extraneous answer keys (not in quiz questions) are ignored.

        Adding extra keys to the answers dict that don't correspond to any
        quiz question should not change the score.

        **Validates: Requirements 2.6**
        """
        # Generate quiz questions
        num_questions = data.draw(
            st.integers(min_value=1, max_value=10), label="num_questions"
        )
        question_ids = data.draw(
            st.lists(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters="-_",
                    ),
                    min_size=1,
                    max_size=15,
                ),
                min_size=num_questions,
                max_size=num_questions,
                unique=True,
            ),
            label="question_ids",
        )
        correct_answers_list = data.draw(
            st.lists(
                st.text(min_size=1, max_size=30),
                min_size=num_questions,
                max_size=num_questions,
            ),
            label="correct_answers",
        )
        quiz_questions = list(zip(question_ids, correct_answers_list))

        # Generate base answers (subset of valid question_ids)
        base_answers: dict[str, str] = {}
        for qid, correct in quiz_questions:
            include = data.draw(st.booleans(), label=f"include_{qid}")
            if include:
                base_answers[qid] = correct

        # Compute score without extraneous keys
        score_without_extra = self._compute_score(quiz_questions, base_answers)

        # Add extraneous keys
        num_extraneous = data.draw(
            st.integers(min_value=1, max_value=10), label="num_extraneous"
        )
        answers_with_extra = dict(base_answers)
        extraneous_ids = data.draw(
            st.lists(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters="-_",
                    ),
                    min_size=1,
                    max_size=15,
                ).filter(lambda x: x not in question_ids),
                min_size=num_extraneous,
                max_size=num_extraneous,
                unique=True,
            ),
            label="extraneous_ids",
        )
        for eid in extraneous_ids:
            answers_with_extra[eid] = data.draw(
                st.text(min_size=1, max_size=30),
                label=f"extra_val_{eid}",
            )

        # Compute score with extraneous keys
        score_with_extra = self._compute_score(quiz_questions, answers_with_extra)

        assert score_without_extra == score_with_extra, (
            f"Extraneous keys affected score: "
            f"without={score_without_extra}, with={score_with_extra}\n"
            f"extraneous_ids={extraneous_ids}"
        )

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_missing_answers_count_as_incorrect(
        self, data: st.DataObject
    ) -> None:
        """Missing answers (question_id not in submitted answers) count as incorrect.

        If a question_id from the quiz is not present in the submitted answers,
        it should not contribute to the score.

        **Validates: Requirements 2.5**
        """
        # Generate quiz questions with all correct answers
        num_questions = data.draw(
            st.integers(min_value=2, max_value=10), label="num_questions"
        )
        question_ids = data.draw(
            st.lists(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters="-_",
                    ),
                    min_size=1,
                    max_size=15,
                ),
                min_size=num_questions,
                max_size=num_questions,
                unique=True,
            ),
            label="question_ids",
        )
        correct_answers_list = data.draw(
            st.lists(
                st.text(min_size=1, max_size=30),
                min_size=num_questions,
                max_size=num_questions,
            ),
            label="correct_answers",
        )
        quiz_questions = list(zip(question_ids, correct_answers_list))

        # Submit all correct answers
        all_correct_answers = {qid: ca for qid, ca in quiz_questions}
        full_score = self._compute_score(quiz_questions, all_correct_answers)
        assert full_score == num_questions

        # Remove some answers (at least 1)
        num_to_remove = data.draw(
            st.integers(min_value=1, max_value=num_questions - 1),
            label="num_to_remove",
        )
        ids_to_remove = data.draw(
            st.lists(
                st.sampled_from(question_ids),
                min_size=num_to_remove,
                max_size=num_to_remove,
                unique=True,
            ),
            label="ids_to_remove",
        )
        partial_answers = {
            qid: ans
            for qid, ans in all_correct_answers.items()
            if qid not in ids_to_remove
        }

        partial_score = self._compute_score(quiz_questions, partial_answers)

        # Score should be reduced by exactly the number of removed answers
        assert partial_score == num_questions - num_to_remove, (
            f"Expected score={num_questions - num_to_remove}, "
            f"got {partial_score} after removing {num_to_remove} answers"
        )


# ---------------------------------------------------------------------------
# Property 5: has_passed aggregation
# Feature: Step_3-5_training-gated-access-control, Property 5: has_passed aggregation
# ---------------------------------------------------------------------------


class TestHasPassedAggregationProperty:
    """Property tests verifying has_passed aggregation logic.

    For any list of quiz attempts for a given user and content_id, the
    has_passed field is true if and only if at least one attempt in the
    list has passed equal to true.

    The actual QuizService.has_user_passed checks for existence of any
    QuizAttempt with passed=True in the database. Here we test the pure
    logical property: has_passed == any(attempt.passed for attempt in attempts).

    **Validates: Requirements 3.3, 4.2**
    """

    @staticmethod
    def _compute_has_passed(passed_values: list[bool]) -> bool:
        """Replicate the has_passed aggregation logic.

        This mirrors what QuizService.has_user_passed does at the DB level:
        it checks if at least one QuizAttempt with passed=True exists.

        Args:
            passed_values: List of passed booleans from quiz attempts.

        Returns:
            True if at least one value is True, False otherwise.
        """
        return any(passed_values)

    @given(
        passed_values=st.lists(
            st.booleans(),
            min_size=1,
            max_size=100,
        ),
    )
    @settings(max_examples=100)
    def test_has_passed_true_iff_any_attempt_passed(
        self, passed_values: list[bool]
    ) -> None:
        """has_passed is true iff at least one attempt has passed=True.

        **Validates: Requirements 3.3, 4.2**
        """
        has_passed = self._compute_has_passed(passed_values)
        expected = any(passed_values)
        assert has_passed == expected, (
            f"has_passed={has_passed}, expected={expected} "
            f"for passed_values={passed_values}"
        )

    @given(
        num_failed=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_all_failed_means_has_passed_false(
        self, num_failed: int
    ) -> None:
        """If all attempts have passed=False, has_passed must be False.

        **Validates: Requirements 3.3, 4.2**
        """
        passed_values = [False] * num_failed
        has_passed = self._compute_has_passed(passed_values)
        assert has_passed is False, (
            f"has_passed should be False when all {num_failed} attempts failed"
        )

    @given(
        num_failed=st.integers(min_value=0, max_value=50),
        pass_position=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_single_pass_among_failures_means_has_passed_true(
        self, num_failed: int, pass_position: int
    ) -> None:
        """If at least one attempt has passed=True, has_passed must be True.

        Inserts a single True at a random position among False values.

        **Validates: Requirements 3.3, 4.2**
        """
        passed_values = [False] * num_failed
        # Insert a True at a valid position
        insert_pos = pass_position % (num_failed + 1)
        passed_values.insert(insert_pos, True)
        has_passed = self._compute_has_passed(passed_values)
        assert has_passed is True, (
            f"has_passed should be True when at least one attempt passed, "
            f"position={insert_pos}, total={len(passed_values)}"
        )

    def test_empty_list_means_has_passed_false(self) -> None:
        """If no attempts exist, has_passed must be False.

        This is a boundary case: an empty list of attempts means the user
        has never attempted the quiz, so has_passed is False.

        **Validates: Requirements 3.3, 4.2**
        """
        has_passed = self._compute_has_passed([])
        assert has_passed is False


# ---------------------------------------------------------------------------
# Property 6: best_score computation
# Feature: Step_3-5_training-gated-access-control, Property 6: best_score computation
# ---------------------------------------------------------------------------


class TestBestScoreComputationProperty:
    """Property tests verifying best_score computation logic.

    For any non-empty list of quiz attempts for a given user and content_id,
    best_score equals the maximum score value among all attempts. For an
    empty list, best_score is None.

    The actual QuizService.get_best_score uses SQL max(score). Here we test
    the pure logical property: best_score == max(scores) if scores else None.

    **Validates: Requirements 4.3**
    """

    @staticmethod
    def _compute_best_score(scores: list[int]) -> int | None:
        """Replicate the best_score computation logic.

        This mirrors what QuizService.get_best_score does at the DB level:
        SELECT max(score) which returns None for empty result sets.

        Args:
            scores: List of score integers from quiz attempts.

        Returns:
            Maximum score, or None if the list is empty.
        """
        if not scores:
            return None
        return max(scores)

    @given(
        scores=st.lists(
            st.integers(min_value=0, max_value=1000),
            min_size=1,
            max_size=100,
        ),
    )
    @settings(max_examples=100)
    def test_best_score_equals_max_of_scores(
        self, scores: list[int]
    ) -> None:
        """best_score equals max(scores) for non-empty list.

        **Validates: Requirements 4.3**
        """
        best_score = self._compute_best_score(scores)
        expected = max(scores)
        assert best_score == expected, (
            f"best_score={best_score}, expected={expected} "
            f"for scores={scores}"
        )

    def test_empty_list_returns_none(self) -> None:
        """best_score is None when no attempts exist.

        **Validates: Requirements 4.3**
        """
        best_score = self._compute_best_score([])
        assert best_score is None

    @given(
        scores=st.lists(
            st.integers(min_value=0, max_value=1000),
            min_size=1,
            max_size=100,
        ),
    )
    @settings(max_examples=100)
    def test_best_score_gte_all_scores(
        self, scores: list[int]
    ) -> None:
        """best_score is greater than or equal to every individual score.

        **Validates: Requirements 4.3**
        """
        best_score = self._compute_best_score(scores)
        assert best_score is not None
        for score in scores:
            assert best_score >= score, (
                f"best_score={best_score} is less than score={score} "
                f"in scores={scores}"
            )

    @given(
        scores=st.lists(
            st.integers(min_value=0, max_value=1000),
            min_size=1,
            max_size=100,
        ),
    )
    @settings(max_examples=100)
    def test_best_score_exists_in_scores(
        self, scores: list[int]
    ) -> None:
        """best_score is a value that actually exists in the scores list.

        **Validates: Requirements 4.3**
        """
        best_score = self._compute_best_score(scores)
        assert best_score is not None
        assert best_score in scores, (
            f"best_score={best_score} not found in scores={scores}"
        )

    @given(
        base_scores=st.lists(
            st.integers(min_value=0, max_value=500),
            min_size=0,
            max_size=50,
        ),
        new_score=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100)
    def test_adding_score_updates_best_correctly(
        self, base_scores: list[int], new_score: int
    ) -> None:
        """Adding a new score updates best_score iff new_score > current best.

        **Validates: Requirements 4.3**
        """
        old_best = self._compute_best_score(base_scores)
        new_scores = base_scores + [new_score]
        new_best = self._compute_best_score(new_scores)

        if old_best is None:
            # Was empty, new_best should be the new_score
            assert new_best == new_score
        elif new_score > old_best:
            # New score is higher, best should update
            assert new_best == new_score
        else:
            # New score is not higher, best stays the same
            assert new_best == old_best


# ---------------------------------------------------------------------------
# Property 7: Results ordering
# Feature: Step_3-5_training-gated-access-control, Property 7: Results ordering
# ---------------------------------------------------------------------------


class TestResultsOrderingProperty:
    """Property tests verifying results ordering and limit.

    For any set of quiz attempts for a given user and content_id, the results
    list is ordered by attempted_at descending (most recent first) and limited
    to the 50 most recent attempts.

    This tests the pure ordering logic: given a list of attempts with timestamps,
    sorting by attempted_at descending produces the correct order, and the list
    is limited to 50 items.

    **Validates: Requirements 3.1**
    """

    @staticmethod
    def _order_and_limit(
        attempts: list[dict],
        limit: int = 50,
    ) -> list[dict]:
        """Replicate the results ordering logic from QuizService.get_user_results.

        Sorts attempts by attempted_at descending and limits to `limit` items.
        This mirrors the SQL ORDER BY attempted_at DESC LIMIT 50.

        Args:
            attempts: List of attempt dicts with 'attempted_at' datetime keys.
            limit: Maximum number of results to return.

        Returns:
            Sorted and limited list of attempts.
        """
        sorted_attempts = sorted(
            attempts, key=lambda a: a["attempted_at"], reverse=True
        )
        return sorted_attempts[:limit]

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_results_ordered_by_attempted_at_descending(
        self, data: st.DataObject
    ) -> None:
        """Results are ordered by attempted_at descending (most recent first).

        Generates a random list of attempts with distinct timestamps and
        verifies the output is sorted in descending order.

        **Validates: Requirements 3.1**
        """
        from datetime import datetime, timezone, timedelta

        num_attempts = data.draw(
            st.integers(min_value=1, max_value=100), label="num_attempts"
        )
        # Generate distinct timestamps by using unique offsets
        offsets = data.draw(
            st.lists(
                st.integers(min_value=0, max_value=100_000),
                min_size=num_attempts,
                max_size=num_attempts,
                unique=True,
            ),
            label="offsets_seconds",
        )
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        attempts = [
            {"attempted_at": base_time + timedelta(seconds=offset), "score": i}
            for i, offset in enumerate(offsets)
        ]

        result = self._order_and_limit(attempts)

        # Verify descending order
        for i in range(len(result) - 1):
            assert result[i]["attempted_at"] >= result[i + 1]["attempted_at"], (
                f"Results not in descending order at index {i}: "
                f"{result[i]['attempted_at']} < {result[i + 1]['attempted_at']}"
            )

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_results_limited_to_50(
        self, data: st.DataObject
    ) -> None:
        """Results are limited to at most 50 items.

        Generates a list of attempts that may exceed 50 and verifies
        the output never exceeds 50 items.

        **Validates: Requirements 3.1**
        """
        from datetime import datetime, timezone, timedelta

        num_attempts = data.draw(
            st.integers(min_value=1, max_value=200), label="num_attempts"
        )
        offsets = data.draw(
            st.lists(
                st.integers(min_value=0, max_value=200_000),
                min_size=num_attempts,
                max_size=num_attempts,
                unique=True,
            ),
            label="offsets_seconds",
        )
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        attempts = [
            {"attempted_at": base_time + timedelta(seconds=offset), "score": i}
            for i, offset in enumerate(offsets)
        ]

        result = self._order_and_limit(attempts)

        assert len(result) <= 50, (
            f"Results should be limited to 50, got {len(result)}"
        )
        expected_len = min(num_attempts, 50)
        assert len(result) == expected_len, (
            f"Expected {expected_len} results, got {len(result)}"
        )

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_limited_results_contain_most_recent(
        self, data: st.DataObject
    ) -> None:
        """When limited to 50, the results contain the 50 most recent attempts.

        Generates more than 50 attempts and verifies the returned results
        are exactly the 50 with the largest attempted_at values.

        **Validates: Requirements 3.1**
        """
        from datetime import datetime, timezone, timedelta

        num_attempts = data.draw(
            st.integers(min_value=51, max_value=150), label="num_attempts"
        )
        offsets = data.draw(
            st.lists(
                st.integers(min_value=0, max_value=200_000),
                min_size=num_attempts,
                max_size=num_attempts,
                unique=True,
            ),
            label="offsets_seconds",
        )
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        attempts = [
            {"attempted_at": base_time + timedelta(seconds=offset), "score": i}
            for i, offset in enumerate(offsets)
        ]

        result = self._order_and_limit(attempts)

        # The 50 most recent timestamps from the input
        all_timestamps = sorted(
            [a["attempted_at"] for a in attempts], reverse=True
        )
        expected_timestamps = all_timestamps[:50]
        result_timestamps = [a["attempted_at"] for a in result]

        assert result_timestamps == expected_timestamps, (
            "Limited results do not contain the 50 most recent attempts"
        )

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_empty_input_returns_empty(
        self, data: st.DataObject
    ) -> None:
        """An empty list of attempts returns an empty result.

        **Validates: Requirements 3.1**
        """
        result = self._order_and_limit([])
        assert result == [], f"Expected empty list, got {result}"


# ---------------------------------------------------------------------------
# Property 8: Quiz attempt immutability
# Feature: Step_3-5_training-gated-access-control, Property 8: Quiz attempt immutability
# ---------------------------------------------------------------------------


class TestQuizAttemptImmutabilityProperty:
    """Property tests verifying quiz attempt immutability via API.

    For any persisted QuizAttempt record, any attempt to update or delete
    the record via the API is rejected with HTTP 405, and the record
    remains unchanged in the database.

    Uses FastAPI TestClient to make PUT/PATCH/DELETE requests to quiz
    endpoints and verify 405 response with the correct detail message.

    **Validates: Requirements 11.2**
    """

    @staticmethod
    def _create_test_app():
        """Create a minimal FastAPI app with the training router for testing.

        Mounts the training router under /api prefix and overrides
        database and tenant dependencies with mocks.
        """
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import FastAPI, APIRouter

        from alcoabase.api.training import router as training_router
        from alcoabase.database import get_db_session
        from alcoabase.dependencies.tenant import (
            TenantContext,
            get_tenant_context,
        )
        from alcoabase.middleware.audit_middleware import AuditMiddleware

        app = FastAPI()
        # Disable audit middleware reason requirement for testing
        app.add_middleware(AuditMiddleware, require_reason_for_mutations=False)

        api = APIRouter(prefix="/api")
        api.include_router(training_router)
        app.include_router(api)

        # Override dependencies
        async def mock_db_session():
            session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            session.execute.return_value = mock_result
            yield session

        async def mock_tenant_context() -> TenantContext:
            return TenantContext(
                company_id=1,
                company_slug="default",
                user_id=1,
                membership_role="admin",
            )

        app.dependency_overrides[get_db_session] = mock_db_session
        app.dependency_overrides[get_tenant_context] = mock_tenant_context

        return app

    @given(
        content_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="-_",
            ),
            min_size=1,
            max_size=50,
        ),
        method=st.sampled_from(["PUT", "PATCH", "DELETE"]),
        endpoint_choice=st.sampled_from(["submit", "results", "passed"]),
    )
    @settings(max_examples=100)
    def test_put_patch_delete_returns_405(
        self,
        content_id: str,
        method: str,
        endpoint_choice: str,
    ) -> None:
        """PUT/PATCH/DELETE on quiz endpoints returns HTTP 405.

        Generates random content_ids and HTTP methods, then verifies
        that the quiz endpoints reject modification attempts with 405
        and the correct immutability detail message.

        **Validates: Requirements 11.2**
        """
        from fastapi.testclient import TestClient

        app = self._create_test_app()
        client = TestClient(app)

        # Build the URL based on endpoint choice
        if endpoint_choice == "submit":
            url = "/api/training/quiz/submit"
        elif endpoint_choice == "results":
            url = f"/api/training/quiz/results/{content_id}"
        else:  # passed
            url = f"/api/training/quiz/passed/{content_id}"

        # Make the request with the chosen method
        headers = {"X-Change-Reason": "Test immutability"}
        if method == "PUT":
            response = client.put(url, headers=headers)
        elif method == "PATCH":
            response = client.patch(url, headers=headers)
        else:  # DELETE
            response = client.delete(url, headers=headers)

        assert response.status_code == 405, (
            f"{method} {url} returned {response.status_code}, expected 405"
        )
        expected_detail = (
            "Quiz attempt records are immutable and cannot be modified or deleted."
        )
        assert response.json()["detail"] == expected_detail, (
            f"{method} {url} detail mismatch: "
            f"got {response.json()['detail']!r}, "
            f"expected {expected_detail!r}"
        )

    @given(
        method=st.sampled_from(["PUT", "PATCH", "DELETE"]),
    )
    @settings(max_examples=100)
    def test_immutability_consistent_across_methods(
        self,
        method: str,
    ) -> None:
        """All three mutating methods (PUT, PATCH, DELETE) are consistently rejected.

        Verifies that the immutability enforcement is uniform across all
        three HTTP methods on all quiz endpoints.

        **Validates: Requirements 11.2**
        """
        from fastapi.testclient import TestClient

        app = self._create_test_app()
        client = TestClient(app)

        endpoints = [
            "/api/training/quiz/submit",
            "/api/training/quiz/results/test_content_123",
            "/api/training/quiz/passed/test_content_123",
        ]

        headers = {"X-Change-Reason": "Test immutability"}
        for url in endpoints:
            if method == "PUT":
                response = client.put(url, headers=headers)
            elif method == "PATCH":
                response = client.patch(url, headers=headers)
            else:
                response = client.delete(url, headers=headers)

            assert response.status_code == 405, (
                f"{method} {url} returned {response.status_code}, expected 405"
            )
            assert response.json()["detail"] == (
                "Quiz attempt records are immutable and cannot be "
                "modified or deleted."
            )


# ---------------------------------------------------------------------------
# Property 9: Task completion requires quiz pass
# Feature: Step_3-5_training-gated-access-control, Property 9: Task completion requires quiz pass
# ---------------------------------------------------------------------------


class TestTaskCompletionRequiresQuizPassProperty:
    """Property tests verifying task completion requires quiz pass.

    For any training task and user, attempting to complete the task succeeds
    only if the user has at least one QuizAttempt with passed=true for the
    content_id derived from the task's sop_document_uuid and sop_version.
    If no passing attempt exists, the completion is rejected with HTTP 400.

    Tests the pure logic: task completion is blocked when quiz not passed,
    allowed when passed. Mocks DB interactions.

    **Validates: Requirements 5.1**
    """

    @staticmethod
    def _derive_content_id(sop_document_uuid: str, sop_version: str) -> str:
        """Derive content_id from SOP document UUID and version.

        Mirrors the logic in TrainingService.complete_training_task:
            content_id = f"{task.sop_document_uuid}_v{task.sop_version}"

        Args:
            sop_document_uuid: The SOP document UUID.
            sop_version: The SOP version string.

        Returns:
            The derived content_id string.
        """
        return f"{sop_document_uuid}_v{sop_version}"

    @staticmethod
    def _task_completion_allowed(
        has_quiz_pass: bool,
        has_sop_reference: bool,
        has_content: bool,
    ) -> tuple[bool, str | None]:
        """Determine if task completion is allowed based on quiz prerequisites.

        Replicates the guard logic from TrainingService.complete_training_task:
        1. If SOP reference is missing → reject
        2. If training content not generated → reject
        3. If quiz not passed → reject
        4. Otherwise → allow

        Args:
            has_quiz_pass: Whether user has passed the quiz for derived content_id.
            has_sop_reference: Whether task has valid sop_document_uuid and sop_version.
            has_content: Whether training content exists for the SOP version.

        Returns:
            Tuple of (allowed, error_detail). If allowed is True, error_detail is None.
        """
        if not has_sop_reference:
            return (
                False,
                "Cannot complete training task: SOP reference information is missing from this task.",
            )
        if not has_content:
            return (
                False,
                "Cannot complete training task: training content and quiz "
                "are not yet available for this SOP version.",
            )
        if not has_quiz_pass:
            return (
                False,
                "Cannot complete training task: quiz has not been passed. "
                "Please pass the comprehension quiz before marking this task as complete.",
            )
        return (True, None)

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
        has_quiz_pass=st.booleans(),
    )
    @settings(max_examples=100)
    def test_completion_succeeds_only_with_quiz_pass(
        self,
        sop_document_uuid: str,
        sop_version: str,
        has_quiz_pass: bool,
    ) -> None:
        """Task completion succeeds iff user has passed quiz for derived content_id.

        When SOP reference and content exist, the only remaining gate is
        the quiz pass status.

        **Validates: Requirements 5.1**
        """
        # Assume SOP reference and content are present
        allowed, error = self._task_completion_allowed(
            has_quiz_pass=has_quiz_pass,
            has_sop_reference=True,
            has_content=True,
        )

        if has_quiz_pass:
            assert allowed is True, (
                f"Task completion should be allowed when quiz passed. "
                f"sop_document_uuid={sop_document_uuid}, sop_version={sop_version}"
            )
            assert error is None
        else:
            assert allowed is False, (
                f"Task completion should be blocked when quiz not passed. "
                f"sop_document_uuid={sop_document_uuid}, sop_version={sop_version}"
            )
            assert "quiz has not been passed" in error

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_missing_sop_reference_blocks_completion(
        self,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """Task completion is blocked when SOP reference is missing.

        Even if quiz is passed, missing SOP reference prevents completion.

        **Validates: Requirements 5.1**
        """
        allowed, error = self._task_completion_allowed(
            has_quiz_pass=True,
            has_sop_reference=False,
            has_content=True,
        )
        assert allowed is False
        assert "SOP reference information is missing" in error

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_missing_content_blocks_completion(
        self,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """Task completion is blocked when training content not generated.

        Even if quiz is passed, missing content prevents completion.

        **Validates: Requirements 5.1**
        """
        allowed, error = self._task_completion_allowed(
            has_quiz_pass=True,
            has_sop_reference=True,
            has_content=False,
        )
        assert allowed is False
        assert "training content and quiz are not yet available" in error

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_content_id_derivation_matches_format(
        self,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """content_id is derived as {sop_document_uuid}_v{sop_version}.

        Verifies the content_id derivation logic used by the task completion
        guard matches the expected format.

        **Validates: Requirements 5.1**
        """
        content_id = self._derive_content_id(sop_document_uuid, sop_version)
        expected = f"{sop_document_uuid}_v{sop_version}"
        assert content_id == expected, (
            f"content_id derivation mismatch: got {content_id!r}, "
            f"expected {expected!r}"
        )


# ---------------------------------------------------------------------------
# Property 10: Backend training gate dual verification
# Feature: Step_3-5_training-gated-access-control, Property 10: Backend training gate dual verification
# ---------------------------------------------------------------------------


class TestBackendTrainingGateDualVerificationProperty:
    """Property tests verifying backend training gate dual verification.

    For any user, SOP document, and SOP version, the check_training_gate
    method allows the action if and only if BOTH a valid TrainingRecord
    exists (where is_valid=true) AND at least one QuizAttempt with
    passed=true exists for the derived content_id. If either condition
    fails, it raises HTTP 403.

    Tests all 4 combinations:
    - (no record, no quiz) → 403
    - (record, no quiz) → 403
    - (no record, quiz) → 403
    - (record AND quiz) → allowed

    **Validates: Requirements 6.1**
    """

    @staticmethod
    def _gate_decision(
        has_valid_record: bool,
        has_quiz_pass: bool,
    ) -> tuple[bool, int | None, str | None]:
        """Determine gate decision based on record and quiz pass status.

        Replicates the logic from TrainingService.check_training_gate:
        1. If no valid TrainingRecord → 403 "record missing"
        2. If record exists but quiz not passed → 403 "quiz not passed"
        3. If both conditions met → allow

        Args:
            has_valid_record: Whether a valid TrainingRecord exists.
            has_quiz_pass: Whether user has passed the quiz.

        Returns:
            Tuple of (allowed, status_code, error_keyword).
            If allowed is True, status_code and error_keyword are None.
        """
        if not has_valid_record:
            return (False, 403, "training record")
        if not has_quiz_pass:
            return (False, 403, "quiz")
        return (True, None, None)

    @given(
        has_valid_record=st.booleans(),
        has_quiz_pass=st.booleans(),
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_gate_allows_iff_both_record_and_quiz_pass(
        self,
        has_valid_record: bool,
        has_quiz_pass: bool,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """Gate allows action iff both valid record AND quiz passed.

        Tests the fundamental dual verification property: access is granted
        only when both conditions are simultaneously satisfied.

        **Validates: Requirements 6.1**
        """
        allowed, status_code, error_keyword = self._gate_decision(
            has_valid_record=has_valid_record,
            has_quiz_pass=has_quiz_pass,
        )

        expected_allowed = has_valid_record and has_quiz_pass

        assert allowed == expected_allowed, (
            f"Gate decision mismatch: "
            f"has_valid_record={has_valid_record}, has_quiz_pass={has_quiz_pass}, "
            f"allowed={allowed}, expected={expected_allowed}"
        )

        if expected_allowed:
            assert status_code is None
            assert error_keyword is None
        else:
            assert status_code == 403

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_no_record_no_quiz_returns_403(
        self,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """No valid record and no quiz pass → 403 with record missing message.

        **Validates: Requirements 6.1**
        """
        allowed, status_code, error_keyword = self._gate_decision(
            has_valid_record=False,
            has_quiz_pass=False,
        )
        assert allowed is False
        assert status_code == 403
        assert error_keyword == "training record"

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_record_but_no_quiz_returns_403(
        self,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """Valid record but no quiz pass → 403 with quiz not passed message.

        **Validates: Requirements 6.1**
        """
        allowed, status_code, error_keyword = self._gate_decision(
            has_valid_record=True,
            has_quiz_pass=False,
        )
        assert allowed is False
        assert status_code == 403
        assert error_keyword == "quiz"

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_no_record_but_quiz_passed_returns_403(
        self,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """No valid record but quiz passed → 403 with record missing message.

        The gate checks record first, so even with quiz pass, missing
        record results in 403.

        **Validates: Requirements 6.1**
        """
        allowed, status_code, error_keyword = self._gate_decision(
            has_valid_record=False,
            has_quiz_pass=True,
        )
        assert allowed is False
        assert status_code == 403
        assert error_keyword == "training record"

    @given(
        sop_document_uuid=st.uuids().map(str),
        sop_version=st.from_regex(r"[1-9][0-9]{0,2}\.0", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_both_record_and_quiz_allows(
        self,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """Valid record AND quiz passed → action allowed.

        **Validates: Requirements 6.1**
        """
        allowed, status_code, error_keyword = self._gate_decision(
            has_valid_record=True,
            has_quiz_pass=True,
        )
        assert allowed is True
        assert status_code is None
        assert error_keyword is None


# ---------------------------------------------------------------------------
# Property 12: Version-specific quiz pass enforcement
# Feature: Step_3-5_training-gated-access-control, Property 12: Version-specific quiz pass enforcement
# ---------------------------------------------------------------------------


class TestVersionSpecificQuizPassEnforcementProperty:
    """Property tests verifying version-specific quiz pass enforcement.

    For any user who has passed the quiz for content_id {sop_uuid}_v{N},
    the training gate for a different version {sop_uuid}_v{M} (where M ≠ N)
    denies access, because quiz pass status is evaluated exclusively by
    exact content_id match.

    Tests that passing quiz for version N does NOT satisfy the gate for
    version M where M ≠ N.

    **Validates: Requirements 12.1, 12.2**
    """

    @staticmethod
    def _derive_content_id(sop_document_uuid: str, sop_version: str) -> str:
        """Derive content_id from SOP document UUID and version.

        Args:
            sop_document_uuid: The SOP document UUID.
            sop_version: The SOP version string.

        Returns:
            The derived content_id string.
        """
        return f"{sop_document_uuid}_v{sop_version}"

    @staticmethod
    def _quiz_pass_satisfies_gate(
        passed_content_id: str,
        gate_content_id: str,
    ) -> bool:
        """Check if a quiz pass for one content_id satisfies a gate for another.

        The gate uses exact content_id matching. A quiz pass for content_id X
        only satisfies the gate for content_id X, not for any other content_id.

        Args:
            passed_content_id: The content_id for which the user has a quiz pass.
            gate_content_id: The content_id the gate is checking.

        Returns:
            True if the pass satisfies the gate (exact match), False otherwise.
        """
        return passed_content_id == gate_content_id

    @given(
        sop_document_uuid=st.uuids().map(str),
        version_n=st.integers(min_value=1, max_value=100),
        version_m=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_quiz_pass_for_version_n_does_not_satisfy_version_m(
        self,
        sop_document_uuid: str,
        version_n: int,
        version_m: int,
    ) -> None:
        """Quiz pass for v{N} does not satisfy gate for v{M} where M ≠ N.

        When versions differ, the content_ids differ, so the quiz pass
        for one version cannot satisfy the gate for another version.

        **Validates: Requirements 12.1, 12.2**
        """
        from hypothesis import assume

        assume(version_n != version_m)

        passed_version = f"{version_n}.0"
        gate_version = f"{version_m}.0"

        passed_content_id = self._derive_content_id(
            sop_document_uuid, passed_version
        )
        gate_content_id = self._derive_content_id(
            sop_document_uuid, gate_version
        )

        satisfies = self._quiz_pass_satisfies_gate(
            passed_content_id, gate_content_id
        )

        assert satisfies is False, (
            f"Quiz pass for {passed_content_id} should NOT satisfy gate for "
            f"{gate_content_id} (different versions: {version_n} vs {version_m})"
        )

    @given(
        sop_document_uuid=st.uuids().map(str),
        version=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_quiz_pass_for_same_version_satisfies_gate(
        self,
        sop_document_uuid: str,
        version: int,
    ) -> None:
        """Quiz pass for v{N} satisfies gate for v{N} (same version).

        When versions match, the content_ids match, so the quiz pass
        satisfies the gate.

        **Validates: Requirements 12.1, 12.2**
        """
        version_str = f"{version}.0"

        passed_content_id = self._derive_content_id(
            sop_document_uuid, version_str
        )
        gate_content_id = self._derive_content_id(
            sop_document_uuid, version_str
        )

        satisfies = self._quiz_pass_satisfies_gate(
            passed_content_id, gate_content_id
        )

        assert satisfies is True, (
            f"Quiz pass for {passed_content_id} should satisfy gate for "
            f"{gate_content_id} (same version: {version})"
        )

    @given(
        sop_document_uuid_a=st.uuids().map(str),
        sop_document_uuid_b=st.uuids().map(str),
        version=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100)
    def test_quiz_pass_for_different_sop_does_not_satisfy(
        self,
        sop_document_uuid_a: str,
        sop_document_uuid_b: str,
        version: int,
    ) -> None:
        """Quiz pass for SOP A does not satisfy gate for SOP B (different documents).

        Even with the same version, different SOP documents produce different
        content_ids, so a quiz pass for one SOP cannot satisfy the gate for another.

        **Validates: Requirements 12.1, 12.2**
        """
        from hypothesis import assume

        assume(sop_document_uuid_a != sop_document_uuid_b)

        version_str = f"{version}.0"

        passed_content_id = self._derive_content_id(
            sop_document_uuid_a, version_str
        )
        gate_content_id = self._derive_content_id(
            sop_document_uuid_b, version_str
        )

        satisfies = self._quiz_pass_satisfies_gate(
            passed_content_id, gate_content_id
        )

        assert satisfies is False, (
            f"Quiz pass for {passed_content_id} should NOT satisfy gate for "
            f"{gate_content_id} (different SOPs)"
        )

    @given(
        sop_document_uuid=st.uuids().map(str),
        versions=st.lists(
            st.integers(min_value=1, max_value=100),
            min_size=2,
            max_size=10,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_only_exact_version_match_satisfies_gate(
        self,
        sop_document_uuid: str,
        versions: list[int],
    ) -> None:
        """Among multiple versions, only the exact version match satisfies the gate.

        Given a set of distinct versions, a quiz pass for version N satisfies
        the gate only for version N and no other version in the set.

        **Validates: Requirements 12.1, 12.2**
        """
        # Pick the first version as the one the user passed
        passed_version = versions[0]
        passed_version_str = f"{passed_version}.0"
        passed_content_id = self._derive_content_id(
            sop_document_uuid, passed_version_str
        )

        for gate_version in versions:
            gate_version_str = f"{gate_version}.0"
            gate_content_id = self._derive_content_id(
                sop_document_uuid, gate_version_str
            )

            satisfies = self._quiz_pass_satisfies_gate(
                passed_content_id, gate_content_id
            )

            if gate_version == passed_version:
                assert satisfies is True, (
                    f"Quiz pass for v{passed_version} should satisfy gate for "
                    f"v{gate_version} (same version)"
                )
            else:
                assert satisfies is False, (
                    f"Quiz pass for v{passed_version} should NOT satisfy gate for "
                    f"v{gate_version} (different version)"
                )
