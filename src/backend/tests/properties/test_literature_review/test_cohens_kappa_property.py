"""Property-based tests for Cohen's kappa computation correctness.

Property 10: Cohen's kappa computation correctness
For any list of (AI_verdict, human_verdict) pairs where both are in
{"include", "exclude"}, the computed Cohen's kappa SHALL equal
(P_observed - P_expected) / (1 - P_expected), where:
    P_observed = proportion of agreements
    P_expected = probability of chance agreement
When P_expected == 1.0, kappa SHALL equal 0.0.

**Validates: Requirements 4.6**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.review.services.kappa import compute_cohens_kappa


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_verdict_strategy = st.sampled_from(["include", "exclude"])

_verdict_pair_strategy = st.tuples(_verdict_strategy, _verdict_strategy)

_verdict_pairs_strategy = st.lists(
    _verdict_pair_strategy,
    min_size=1,
    max_size=200,
)


def _reference_kappa(verdict_pairs: list[tuple[str, str]]) -> float:
    """Independent reference implementation of Cohen's kappa."""
    total = len(verdict_pairs)
    if total == 0:
        return 0.0

    agreements = sum(1 for ai_v, h_v in verdict_pairs if ai_v == h_v)
    ai_include = sum(1 for ai_v, _ in verdict_pairs if ai_v == "include")
    human_include = sum(1 for _, h_v in verdict_pairs if h_v == "include")

    ai_exclude = total - ai_include
    human_exclude = total - human_include

    p_observed = agreements / total
    p_expected = (
        (ai_include / total) * (human_include / total)
        + (ai_exclude / total) * (human_exclude / total)
    )

    if p_expected >= 1.0:
        return 0.0

    return (p_observed - p_expected) / (1.0 - p_expected)


# ---------------------------------------------------------------------------
# Property 10: Kappa matches formula for arbitrary verdict pairs
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(verdict_pairs=_verdict_pairs_strategy)
def test_kappa_matches_formula(
    verdict_pairs: list[tuple[str, str]],
) -> None:
    """Cohen's kappa SHALL equal (P_observed - P_expected) / (1 - P_expected)
    for any list of verdict pairs.

    **Validates: Requirements 4.6**
    """
    result = compute_cohens_kappa(verdict_pairs)
    expected = _reference_kappa(verdict_pairs)

    assert result == pytest.approx(expected, abs=1e-10), (
        f"Kappa mismatch: got {result}, expected {expected} "
        f"for {len(verdict_pairs)} pairs"
    )


# ---------------------------------------------------------------------------
# Property 10: P_expected == 1.0 implies kappa == 0.0
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    n=st.integers(min_value=1, max_value=100),
    verdict=_verdict_strategy,
)
def test_kappa_zero_when_p_expected_one(
    n: int,
    verdict: str,
) -> None:
    """When all AI and all human verdicts are the same category (making
    P_expected == 1.0), kappa SHALL be 0.0.

    **Validates: Requirements 4.6**
    """
    # All AI and all human say the same thing → P_expected = 1.0
    pairs = [(verdict, verdict)] * n
    result = compute_cohens_kappa(pairs)
    assert result == pytest.approx(0.0, abs=1e-10)


# ---------------------------------------------------------------------------
# Property 10: Kappa == 1.0 for perfect agreement (when not trivial)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    includes=st.integers(min_value=1, max_value=50),
    excludes=st.integers(min_value=1, max_value=50),
)
def test_kappa_one_for_perfect_nontrivial_agreement(
    includes: int,
    excludes: int,
) -> None:
    """When AI and human agree perfectly AND both categories are present,
    kappa SHALL equal 1.0.

    **Validates: Requirements 4.6**
    """
    pairs = [("include", "include")] * includes + [("exclude", "exclude")] * excludes
    result = compute_cohens_kappa(pairs)
    assert result == pytest.approx(1.0, abs=1e-10)


# ---------------------------------------------------------------------------
# Property 10: Kappa is bounded [-1, 1]
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(verdict_pairs=_verdict_pairs_strategy)
def test_kappa_bounded(
    verdict_pairs: list[tuple[str, str]],
) -> None:
    """Cohen's kappa SHALL always be in the range [-1, 1].

    **Validates: Requirements 4.6**
    """
    result = compute_cohens_kappa(verdict_pairs)
    assert -1.0 <= result <= 1.0 + 1e-10, (
        f"Kappa {result} out of bounds for {len(verdict_pairs)} pairs"
    )


# ---------------------------------------------------------------------------
# Property 10: Empty list returns 0.0
# ---------------------------------------------------------------------------


def test_kappa_empty_list_returns_zero() -> None:
    """When given an empty list of verdict pairs, kappa SHALL be 0.0.

    **Validates: Requirements 4.6**
    """
    assert compute_cohens_kappa([]) == 0.0


# ---------------------------------------------------------------------------
# Property 10: Complete disagreement yields negative kappa
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    includes_as_excludes=st.integers(min_value=1, max_value=50),
    excludes_as_includes=st.integers(min_value=1, max_value=50),
)
def test_kappa_negative_for_systematic_disagreement(
    includes_as_excludes: int,
    excludes_as_includes: int,
) -> None:
    """When AI and human systematically disagree (AI includes what human
    excludes and vice versa), kappa SHALL be negative.

    **Validates: Requirements 4.6**
    """
    pairs = (
        [("include", "exclude")] * includes_as_excludes
        + [("exclude", "include")] * excludes_as_includes
    )
    result = compute_cohens_kappa(pairs)
    assert result < 0.0, (
        f"Expected negative kappa for systematic disagreement, got {result}"
    )
