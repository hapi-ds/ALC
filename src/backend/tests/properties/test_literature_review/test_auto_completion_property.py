"""Property-based tests for auto-completion threshold logic.

Property 9: Auto-completion threshold logic
For any set of screening decisions and a confidence threshold, the system SHALL
auto-transition to screening_complete if and only if every decision is "resolved".

A decision is "resolved" when:
- human_verdict is not None (human override present), OR
- verdict in ("include", "exclude") AND confidence >= threshold AND human_verdict is None

The system SHALL NOT transition when:
- The decisions list is empty
- Any decision lacks resolution (e.g., verdict="uncertain", or confidence < threshold
  without a human override)

**Validates: Requirements 4.5**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure function extracted from SLRReviewService._check_auto_completion
# ---------------------------------------------------------------------------


def check_auto_completion_pure(
    decisions: list[dict], confidence_threshold: float
) -> bool:
    """Check if all decisions meet auto-completion criteria.

    A decision is "resolved" if:
    - human_verdict is not None, OR
    - verdict in (include, exclude) AND confidence >= threshold AND human_verdict is None
    """
    if not decisions:
        return False
    for d in decisions:
        has_human = d.get("human_verdict") is not None
        ai_confident = (
            d["verdict"] in ("include", "exclude")
            and d["confidence"] >= confidence_threshold
            and d.get("human_verdict") is None
        )
        if not (has_human or ai_confident):
            return False
    return True


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Confidence threshold strategy: realistic range 0.5–1.0
confidence_threshold_st = st.floats(min_value=0.5, max_value=1.0, allow_nan=False)

# Verdicts the AI can produce
ai_verdicts = st.sampled_from(["include", "exclude", "uncertain"])

# Human verdicts (when present)
human_verdicts = st.sampled_from(["include", "exclude"])


def resolved_decision_st(threshold: float) -> st.SearchStrategy[dict]:
    """Generate a decision that IS resolved given the threshold.

    Resolved means either:
    - Has a human override, OR
    - AI verdict is include/exclude with confidence >= threshold and no human override
    """
    # Option 1: Human override present (any AI verdict/confidence is fine)
    human_override = st.fixed_dictionaries(
        {
            "verdict": ai_verdicts,
            "confidence": st.floats(
                min_value=0.0, max_value=1.0, allow_nan=False
            ),
            "human_verdict": human_verdicts,
        }
    )

    # Option 2: AI confident with no human override
    ai_confident = st.fixed_dictionaries(
        {
            "verdict": st.sampled_from(["include", "exclude"]),
            "confidence": st.floats(
                min_value=threshold, max_value=1.0, allow_nan=False
            ),
            "human_verdict": st.none(),
        }
    )

    return st.one_of(human_override, ai_confident)


def unresolved_decision_st(threshold: float) -> st.SearchStrategy[dict]:
    """Generate a decision that is NOT resolved given the threshold.

    Unresolved means:
    - No human override AND (verdict is uncertain OR confidence < threshold)
    """
    # Option 1: Uncertain verdict, no human override
    uncertain = st.fixed_dictionaries(
        {
            "verdict": st.just("uncertain"),
            "confidence": st.floats(
                min_value=0.0, max_value=1.0, allow_nan=False
            ),
            "human_verdict": st.none(),
        }
    )

    # Option 2: Include/exclude but below threshold, no human override
    below_threshold = st.fixed_dictionaries(
        {
            "verdict": st.sampled_from(["include", "exclude"]),
            "confidence": st.floats(
                min_value=0.0,
                max_value=max(0.0, threshold - 1e-10),
                allow_nan=False,
                allow_infinity=False,
            ),
            "human_verdict": st.none(),
        }
    )

    return st.one_of(uncertain, below_threshold)


# ---------------------------------------------------------------------------
# Property 9: Empty decisions list → returns False
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(threshold=confidence_threshold_st)
def test_empty_decisions_returns_false(threshold: float) -> None:
    """check_auto_completion_pure SHALL return False for an empty list.

    **Validates: Requirements 4.5**
    """
    assert check_auto_completion_pure([], threshold) is False


# ---------------------------------------------------------------------------
# Property 9: All resolved → returns True
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    threshold=confidence_threshold_st,
    data=st.data(),
)
def test_all_resolved_returns_true(threshold: float, data: st.DataObject) -> None:
    """check_auto_completion_pure SHALL return True when ALL decisions are resolved.

    A decision is resolved when it has a human override OR an AI verdict
    in (include, exclude) with confidence >= threshold.

    **Validates: Requirements 4.5**
    """
    decisions = data.draw(
        st.lists(resolved_decision_st(threshold), min_size=1, max_size=30)
    )
    assert check_auto_completion_pure(decisions, threshold) is True


# ---------------------------------------------------------------------------
# Property 9: Any unresolved → returns False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    threshold=confidence_threshold_st,
    data=st.data(),
)
def test_any_unresolved_returns_false(
    threshold: float, data: st.DataObject
) -> None:
    """check_auto_completion_pure SHALL return False when ANY decision is unresolved.

    At least one decision lacks resolution (uncertain verdict or confidence
    below threshold without human override).

    **Validates: Requirements 4.5**
    """
    # Generate at least one unresolved decision mixed with resolved ones
    resolved_list = data.draw(
        st.lists(resolved_decision_st(threshold), min_size=0, max_size=20)
    )
    unresolved_list = data.draw(
        st.lists(unresolved_decision_st(threshold), min_size=1, max_size=10)
    )

    # Combine and shuffle
    all_decisions = resolved_list + unresolved_list
    shuffled = data.draw(st.permutations(all_decisions))

    assert check_auto_completion_pure(list(shuffled), threshold) is False


# ---------------------------------------------------------------------------
# Property 9: Human override always resolves regardless of AI confidence
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    threshold=confidence_threshold_st,
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    verdict=ai_verdicts,
    human_verdict=human_verdicts,
)
def test_human_override_always_resolves(
    threshold: float,
    confidence: float,
    verdict: str,
    human_verdict: str,
) -> None:
    """A single decision with human_verdict is always resolved, regardless
    of AI verdict or confidence.

    **Validates: Requirements 4.5**
    """
    decisions = [
        {
            "verdict": verdict,
            "confidence": confidence,
            "human_verdict": human_verdict,
        }
    ]
    assert check_auto_completion_pure(decisions, threshold) is True


# ---------------------------------------------------------------------------
# Property 9: Threshold boundary — confidence exactly at threshold is resolved
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    threshold=confidence_threshold_st,
    verdict=st.sampled_from(["include", "exclude"]),
)
def test_confidence_at_threshold_is_resolved(
    threshold: float,
    verdict: str,
) -> None:
    """A decision with confidence == threshold and verdict include/exclude
    (no human override) SHALL be resolved.

    **Validates: Requirements 4.5**
    """
    decisions = [
        {
            "verdict": verdict,
            "confidence": threshold,
            "human_verdict": None,
        }
    ]
    assert check_auto_completion_pure(decisions, threshold) is True


# ---------------------------------------------------------------------------
# Property 9: Uncertain verdict without human override is never resolved
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    threshold=confidence_threshold_st,
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_uncertain_without_human_is_never_resolved(
    threshold: float,
    confidence: float,
) -> None:
    """A decision with verdict "uncertain" and no human override SHALL
    never be resolved, regardless of confidence.

    **Validates: Requirements 4.5**
    """
    decisions = [
        {
            "verdict": "uncertain",
            "confidence": confidence,
            "human_verdict": None,
        }
    ]
    assert check_auto_completion_pure(decisions, threshold) is False
