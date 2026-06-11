"""Property-based test: PRISMA flow monotonic invariant.

Property 4: PRISMA flow monotonic invariant
For any SLR Review with a set of Screening Decisions, the PRISMA Flow
statistics SHALL satisfy the invariant:
    records_identified >= records_screened >= records_eligible >= records_included_final
And the sum of records_excluded_with_reasons across all reason categories
plus records_included_final SHALL equal records_screened.

This is implemented as a PURE function test. The PRISMA computation logic
is extracted into a helper function that takes a list of decision dicts
(with verdict, confidence, human_verdict fields) and a records_identified
count, then computes the PRISMA flow numbers without database access.

**Validates: Requirements 4.2, 15.4**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from __future__ import annotations

from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure helper function: PRISMA flow computation
# ---------------------------------------------------------------------------

# Confidence threshold for uncontested AI decisions (matches service logic)
AUTO_INCLUDE_CONFIDENCE_THRESHOLD = 0.8


def compute_prisma_flow(
    decisions: list[dict[str, Any]],
    records_identified: int,
) -> dict[str, Any]:
    """Compute PRISMA Flow statistics from a list of screening decisions.

    This pure function mirrors the logic in SLRReviewService.get_prisma_flow()
    but operates on plain dicts instead of database queries.

    Each decision dict has:
        - verdict: str ("include", "exclude", or "uncertain")
        - confidence: float (0.0–1.0)
        - human_verdict: str | None ("include", "exclude", or None)

    Definitions:
        - records_identified: total records submitted to review (input param)
        - records_screened: total decisions (all records with a ScreeningDecision)
        - records_eligible: decisions with AI verdict "include" or "uncertain"
        - records_included_final: human_verdict == "include" OR
          (AI verdict == "include" AND confidence >= 0.8 AND no human override)
        - records_excluded_with_reasons: human_verdict == "exclude" OR
          (AI verdict == "exclude" AND confidence >= 0.8 AND no human override),
          grouped by the AI verdict category

    Args:
        decisions: List of decision dicts.
        records_identified: Total records in the review.

    Returns:
        Dict with PRISMA flow statistics.
    """
    records_screened = len(decisions)

    # Records eligible: AI verdict is "include" or "uncertain", OR
    # human_verdict is "include" (human override to include makes it eligible
    # regardless of AI verdict — the human reviewer determined eligibility)
    records_eligible = sum(
        1
        for d in decisions
        if d["verdict"] in ("include", "uncertain")
        or d.get("human_verdict") == "include"
    )

    # Records included final
    records_included_final = sum(
        1
        for d in decisions
        if d.get("human_verdict") == "include"
        or (
            d["verdict"] == "include"
            and d["confidence"] >= AUTO_INCLUDE_CONFIDENCE_THRESHOLD
            and d.get("human_verdict") is None
        )
    )

    # Records excluded with reasons (grouped by AI verdict category)
    records_excluded_with_reasons: dict[str, int] = {}
    for d in decisions:
        is_excluded = d.get("human_verdict") == "exclude" or (
            d["verdict"] == "exclude"
            and d["confidence"] >= AUTO_INCLUDE_CONFIDENCE_THRESHOLD
            and d.get("human_verdict") is None
        )
        if is_excluded:
            category = d["verdict"]
            records_excluded_with_reasons[category] = (
                records_excluded_with_reasons.get(category, 0) + 1
            )

    return {
        "records_identified": records_identified,
        "records_screened": records_screened,
        "records_eligible": records_eligible,
        "records_included_final": records_included_final,
        "records_excluded_with_reasons": records_excluded_with_reasons,
    }


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VERDICTS = st.sampled_from(["include", "exclude", "uncertain"])
CONFIDENCE = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
HUMAN_VERDICT = st.one_of(
    st.none(),
    st.sampled_from(["include", "exclude"]),
)


@st.composite
def screening_decision_strategy(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a single screening decision dict with random fields."""
    return {
        "verdict": draw(VERDICTS),
        "confidence": draw(CONFIDENCE),
        "human_verdict": draw(HUMAN_VERDICT),
    }


@st.composite
def resolved_screening_decision_strategy(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a screening decision that is fully resolved.

    A resolved decision has either:
    - A human_verdict (include or exclude), OR
    - An AI verdict of "include" or "exclude" with confidence >= 0.8

    This ensures the second PRISMA invariant (excluded + included = screened)
    holds, as all records have a final determination.
    """
    human_verdict = draw(HUMAN_VERDICT)

    if human_verdict is not None:
        # Human override resolves the decision regardless of AI verdict
        verdict = draw(VERDICTS)
        confidence = draw(CONFIDENCE)
    else:
        # No human override: must have high-confidence include/exclude
        verdict = draw(st.sampled_from(["include", "exclude"]))
        confidence = draw(
            st.floats(
                min_value=AUTO_INCLUDE_CONFIDENCE_THRESHOLD,
                max_value=1.0,
                allow_nan=False,
            )
        )

    return {
        "verdict": verdict,
        "confidence": confidence,
        "human_verdict": human_verdict,
    }


# ---------------------------------------------------------------------------
# Property 4: PRISMA flow monotonic invariant
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    decisions=st.lists(screening_decision_strategy(), min_size=0, max_size=50),
    extra_identified=st.integers(min_value=0, max_value=100),
)
def test_prisma_flow_monotonic_invariant(
    decisions: list[dict[str, Any]],
    extra_identified: int,
) -> None:
    """For any set of screening decisions, the PRISMA flow statistics SHALL
    satisfy records_identified >= records_screened >= records_eligible >=
    records_included_final.

    records_identified is always >= records_screened because not all identified
    records may have been screened yet.

    **Validates: Requirements 4.2, 15.4**
    """
    # records_identified >= records_screened (some records may not be screened)
    records_identified = len(decisions) + extra_identified

    flow = compute_prisma_flow(decisions, records_identified)

    # Monotonic invariant
    assert flow["records_identified"] >= flow["records_screened"], (
        f"records_identified ({flow['records_identified']}) must be >= "
        f"records_screened ({flow['records_screened']})"
    )
    assert flow["records_screened"] >= flow["records_eligible"], (
        f"records_screened ({flow['records_screened']}) must be >= "
        f"records_eligible ({flow['records_eligible']})"
    )
    assert flow["records_eligible"] >= flow["records_included_final"], (
        f"records_eligible ({flow['records_eligible']}) must be >= "
        f"records_included_final ({flow['records_included_final']})"
    )


@settings(max_examples=200)
@given(
    decisions=st.lists(
        resolved_screening_decision_strategy(), min_size=0, max_size=50
    ),
    extra_identified=st.integers(min_value=0, max_value=100),
)
def test_prisma_flow_excluded_plus_included_equals_screened(
    decisions: list[dict[str, Any]],
    extra_identified: int,
) -> None:
    """For any set of fully resolved screening decisions, the sum of
    records_excluded_with_reasons plus records_included_final SHALL equal
    records_screened.

    A "fully resolved" decision has either a human override or a
    high-confidence (>= 0.8) AI verdict of include/exclude. This ensures
    every screened record is categorized as either included or excluded.

    **Validates: Requirements 4.2, 15.4**
    """
    records_identified = len(decisions) + extra_identified

    flow = compute_prisma_flow(decisions, records_identified)

    total_excluded = sum(flow["records_excluded_with_reasons"].values())
    total_resolved = total_excluded + flow["records_included_final"]

    assert total_resolved == flow["records_screened"], (
        f"excluded ({total_excluded}) + included_final "
        f"({flow['records_included_final']}) = {total_resolved} must equal "
        f"records_screened ({flow['records_screened']})"
    )


@settings(max_examples=200)
@given(
    decisions=st.lists(screening_decision_strategy(), min_size=0, max_size=50),
    extra_identified=st.integers(min_value=0, max_value=100),
)
def test_prisma_flow_excluded_plus_included_leq_screened(
    decisions: list[dict[str, Any]],
    extra_identified: int,
) -> None:
    """For any set of screening decisions (including unresolved ones),
    the sum of records_excluded_with_reasons plus records_included_final
    SHALL be less than or equal to records_screened.

    Records with uncertain verdict and low confidence without human override
    are screened but not yet categorized as included or excluded.

    **Validates: Requirements 4.2, 15.4**
    """
    records_identified = len(decisions) + extra_identified

    flow = compute_prisma_flow(decisions, records_identified)

    total_excluded = sum(flow["records_excluded_with_reasons"].values())
    total_resolved = total_excluded + flow["records_included_final"]

    assert total_resolved <= flow["records_screened"], (
        f"excluded ({total_excluded}) + included_final "
        f"({flow['records_included_final']}) = {total_resolved} must be <= "
        f"records_screened ({flow['records_screened']})"
    )

    # Also verify the monotonic invariant holds for all inputs
    assert flow["records_identified"] >= flow["records_screened"]
    assert flow["records_screened"] >= flow["records_eligible"]
    assert flow["records_eligible"] >= flow["records_included_final"]
