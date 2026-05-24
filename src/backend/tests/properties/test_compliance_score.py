"""Property-based tests for compliance score computation.

Tests Property 1 from the multi-agent always-on auditing design document,
validating that the compliance score is deterministic, bounded within
[0.0, 100.0], and matches the defined formula.

**Validates: Requirements 3.4, 6.1**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 1)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (3.4, 6.1)
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.compliance_scorecard import (
    SEVERITY_WEIGHTS,
    compute_compliance_score,
)

# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

#: Valid severity levels matching the SEVERITY_WEIGHTS keys.
SEVERITIES = list(SEVERITY_WEIGHTS.keys())


@st.composite
def st_finding_counts(draw: st.DrawFn) -> dict[str, int]:
    """Generate random finding counts per severity level.

    Each severity level gets a random non-negative count (0–50).
    Some severities may be omitted to test sparse inputs.

    Returns:
        Dictionary mapping severity names to non-negative integer counts.
    """
    included = draw(st.lists(st.sampled_from(SEVERITIES), unique=True, min_size=0, max_size=4))
    counts: dict[str, int] = {}
    for severity in included:
        counts[severity] = draw(st.integers(min_value=0, max_value=50))
    return counts


# ---------------------------------------------------------------------------
# Property 1: Compliance score is deterministic and bounded
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 1: Compliance score is deterministic and bounded
@settings(max_examples=200)
@given(finding_counts=st_finding_counts())
def test_compliance_score_bounded(finding_counts: dict[str, int]) -> None:
    """For any set of findings with severities in {Critical, Major, Minor,
    Informational} and counts >= 0, the compliance score SHALL always be
    in the range [0.0, 100.0].

    **Validates: Requirements 3.4, 6.1**
    """
    score = compute_compliance_score(finding_counts)

    assert 0.0 <= score <= 100.0, (
        f"Score {score} is out of bounds [0.0, 100.0] "
        f"for finding_counts={finding_counts}"
    )


# Feature: multi-agent-always-on-auditing, Property 1: Compliance score matches formula
@settings(max_examples=200)
@given(finding_counts=st_finding_counts())
def test_compliance_score_matches_formula(finding_counts: dict[str, int]) -> None:
    """For any set of findings, the compliance score SHALL equal
    max(0.0, 100.0 - Σ(weight[severity] × count[severity])).

    **Validates: Requirements 3.4, 6.1**
    """
    score = compute_compliance_score(finding_counts)

    # Independently compute expected score using the formula
    expected_penalty = sum(
        SEVERITY_WEIGHTS[severity] * count
        for severity, count in finding_counts.items()
        if severity in SEVERITY_WEIGHTS
    )
    expected_score = max(0.0, 100.0 - expected_penalty)

    assert score == expected_score, (
        f"Score {score} does not match expected {expected_score} "
        f"for finding_counts={finding_counts}"
    )


# Feature: multi-agent-always-on-auditing, Property 1: Compliance score is deterministic
@settings(max_examples=200)
@given(finding_counts=st_finding_counts())
def test_compliance_score_deterministic(finding_counts: dict[str, int]) -> None:
    """For any set of findings, calling compute_compliance_score multiple
    times with the same input SHALL always produce the same output.

    **Validates: Requirements 3.4, 6.1**
    """
    score_1 = compute_compliance_score(finding_counts)
    score_2 = compute_compliance_score(finding_counts)
    score_3 = compute_compliance_score(finding_counts)

    assert score_1 == score_2 == score_3, (
        f"Non-deterministic scores: {score_1}, {score_2}, {score_3} "
        f"for finding_counts={finding_counts}"
    )
