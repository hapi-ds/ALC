"""Property-based tests for compliance readiness score formula.

Property 12: Compliance Readiness Score Formula

Generate random metric inputs (coverage %, confidence, orphan counts,
completeness), verify formula produces correct clamped result matching:
    (coverage_percentage × 0.40)
  + (avg_confidence × 100 × 0.25)
  + (max(0, 100 − orphans_req × 5 − orphans_tc × 3) × 0.20)
  + (completeness × 0.15)

The completeness_score is 100 if all source and target documents had at
least one extraction, otherwise (documents_with_extractions / total_documents × 100).

**Validates: Requirements 7.2**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/coverage_metrics.py
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.coverage_metrics import compute_compliance_readiness_score


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Coverage percentage: 0.0 to 100.0 (2 decimal places)
COVERAGE_PERCENTAGE = st.floats(
    min_value=0.0,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
).map(lambda x: round(x, 2))

# Average link confidence: 0.0 to 1.0 (2 decimal places)
AVG_LINK_CONFIDENCE = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
).map(lambda x: round(x, 2))

# Orphan counts: non-negative integers
ORPHAN_REQ_COUNT = st.integers(min_value=0, max_value=100)
ORPHAN_TC_COUNT = st.integers(min_value=0, max_value=100)

# Document counts for completeness calculation
TOTAL_DOCS = st.integers(min_value=0, max_value=50)


@st.composite
def st_compliance_inputs(draw: st.DrawFn) -> dict:
    """Generate random inputs for compute_compliance_readiness_score.

    Produces a dictionary with:
        - metrics: dict with coverage_percentage, average_link_confidence,
          orphan_requirements_count, orphan_test_cases_count
        - source_docs_with_extractions: list of doc dicts
        - target_docs_with_extractions: list of doc dicts
        - total_docs: int (>= docs_with_extractions)

    Returns:
        Dictionary with all inputs needed for the function call.
    """
    coverage_pct = draw(COVERAGE_PERCENTAGE)
    avg_confidence = draw(AVG_LINK_CONFIDENCE)
    orphan_req = draw(ORPHAN_REQ_COUNT)
    orphan_tc = draw(ORPHAN_TC_COUNT)
    total_docs = draw(TOTAL_DOCS)

    # Generate docs with extractions (cannot exceed total_docs)
    if total_docs > 0:
        source_extraction_count = draw(
            st.integers(min_value=0, max_value=total_docs)
        )
        target_extraction_count = draw(
            st.integers(
                min_value=0, max_value=total_docs - source_extraction_count
            )
        )
    else:
        source_extraction_count = 0
        target_extraction_count = 0

    source_docs_with_extractions = [
        {"document_uuid": f"src-{i}"} for i in range(source_extraction_count)
    ]
    target_docs_with_extractions = [
        {"document_uuid": f"tgt-{i}"} for i in range(target_extraction_count)
    ]

    metrics = {
        "coverage_percentage": coverage_pct,
        "average_link_confidence": avg_confidence,
        "orphan_requirements_count": orphan_req,
        "orphan_test_cases_count": orphan_tc,
    }

    return {
        "metrics": metrics,
        "source_docs_with_extractions": source_docs_with_extractions,
        "target_docs_with_extractions": target_docs_with_extractions,
        "total_docs": total_docs,
    }


# ---------------------------------------------------------------------------
# Property 12a: Score matches the defined formula
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 12: Compliance Readiness Score Formula
@settings(max_examples=10)
@given(inputs=st_compliance_inputs())
def test_compliance_readiness_score_matches_formula(inputs: dict) -> None:
    """For any set of coverage metrics, the compliance_readiness_score SHALL
    equal: (coverage_percentage × 0.40) + (average_link_confidence × 100 × 0.25)
    + (max(0, 100 − orphan_requirements_count × 5 − orphan_test_cases_count × 3) × 0.20)
    + (completeness_score × 0.15), clamped to [0.0, 100.0].

    **Validates: Requirements 7.2**
    """
    metrics = inputs["metrics"]
    source_docs_with_extractions = inputs["source_docs_with_extractions"]
    target_docs_with_extractions = inputs["target_docs_with_extractions"]
    total_docs = inputs["total_docs"]

    result = compute_compliance_readiness_score(
        metrics=metrics,
        source_docs_with_extractions=source_docs_with_extractions,
        target_docs_with_extractions=target_docs_with_extractions,
        total_docs=total_docs,
    )

    # Independently compute expected score
    coverage_pct = metrics["coverage_percentage"]
    avg_confidence = metrics["average_link_confidence"]
    orphan_req = metrics["orphan_requirements_count"]
    orphan_tc = metrics["orphan_test_cases_count"]

    link_quality_score = avg_confidence * 100
    orphan_penalty = max(0, 100 - (orphan_req * 5) - (orphan_tc * 3))

    docs_with_extractions = len(source_docs_with_extractions) + len(
        target_docs_with_extractions
    )
    if total_docs > 0 and docs_with_extractions >= total_docs:
        completeness_score = 100.0
    elif total_docs > 0:
        completeness_score = (docs_with_extractions / total_docs) * 100
    else:
        completeness_score = 0.0

    expected = (
        (coverage_pct * 0.40)
        + (link_quality_score * 0.25)
        + (orphan_penalty * 0.20)
        + (completeness_score * 0.15)
    )
    expected = max(0.0, min(100.0, expected))
    expected = round(expected, 2)

    assert result == expected, (
        f"Score {result} does not match expected {expected} "
        f"for metrics={metrics}, total_docs={total_docs}, "
        f"docs_with_extractions={docs_with_extractions}"
    )


# ---------------------------------------------------------------------------
# Property 12b: Score is always clamped to [0.0, 100.0]
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 12: Compliance Readiness Score Formula
@settings(max_examples=10)
@given(inputs=st_compliance_inputs())
def test_compliance_readiness_score_bounded(inputs: dict) -> None:
    """For any set of coverage metrics, the compliance_readiness_score SHALL
    always be in the range [0.0, 100.0].

    **Validates: Requirements 7.2**
    """
    result = compute_compliance_readiness_score(
        metrics=inputs["metrics"],
        source_docs_with_extractions=inputs["source_docs_with_extractions"],
        target_docs_with_extractions=inputs["target_docs_with_extractions"],
        total_docs=inputs["total_docs"],
    )

    assert 0.0 <= result <= 100.0, (
        f"Score {result} is out of bounds [0.0, 100.0] "
        f"for metrics={inputs['metrics']}"
    )


# ---------------------------------------------------------------------------
# Property 12c: Score is deterministic
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 12: Compliance Readiness Score Formula
@settings(max_examples=10)
@given(inputs=st_compliance_inputs())
def test_compliance_readiness_score_deterministic(inputs: dict) -> None:
    """For any set of coverage metrics, calling compute_compliance_readiness_score
    multiple times with the same input SHALL always produce the same output.

    **Validates: Requirements 7.2**
    """
    kwargs = {
        "metrics": inputs["metrics"],
        "source_docs_with_extractions": inputs["source_docs_with_extractions"],
        "target_docs_with_extractions": inputs["target_docs_with_extractions"],
        "total_docs": inputs["total_docs"],
    }

    score_1 = compute_compliance_readiness_score(**kwargs)
    score_2 = compute_compliance_readiness_score(**kwargs)
    score_3 = compute_compliance_readiness_score(**kwargs)

    assert score_1 == score_2 == score_3, (
        f"Non-deterministic scores: {score_1}, {score_2}, {score_3} "
        f"for metrics={inputs['metrics']}"
    )


# ---------------------------------------------------------------------------
# Property 12d: Zero total_requirements yields score 0.0 when all else is zero
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 12: Compliance Readiness Score Formula
@settings(max_examples=10)
@given(
    orphan_req=ORPHAN_REQ_COUNT,
    orphan_tc=ORPHAN_TC_COUNT,
)
def test_compliance_readiness_score_zero_coverage_zero_confidence(
    orphan_req: int,
    orphan_tc: int,
) -> None:
    """When coverage_percentage is 0.0 and average_link_confidence is 0.0
    and total_docs is 0, the score SHALL equal max(0, orphan_penalty × 0.20),
    clamped to [0.0, 100.0].

    **Validates: Requirements 7.2**
    """
    metrics = {
        "coverage_percentage": 0.0,
        "average_link_confidence": 0.0,
        "orphan_requirements_count": orphan_req,
        "orphan_test_cases_count": orphan_tc,
    }

    result = compute_compliance_readiness_score(
        metrics=metrics,
        source_docs_with_extractions=[],
        target_docs_with_extractions=[],
        total_docs=0,
    )

    # With zero coverage, zero confidence, zero completeness:
    # score = 0 + 0 + orphan_penalty * 0.20 + 0
    orphan_penalty = max(0, 100 - (orphan_req * 5) - (orphan_tc * 3))
    expected = round(max(0.0, min(100.0, orphan_penalty * 0.20)), 2)

    assert result == expected, (
        f"Score {result} does not match expected {expected} "
        f"for orphan_req={orphan_req}, orphan_tc={orphan_tc}"
    )


# ---------------------------------------------------------------------------
# Property 12e: Full coverage and confidence yields maximum score
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 12: Compliance Readiness Score Formula
def test_compliance_readiness_score_perfect_inputs() -> None:
    """When coverage is 100%, confidence is 1.0, zero orphans, and all docs
    have extractions, the score SHALL be 100.0.

    **Validates: Requirements 7.2**
    """
    metrics = {
        "coverage_percentage": 100.0,
        "average_link_confidence": 1.0,
        "orphan_requirements_count": 0,
        "orphan_test_cases_count": 0,
    }

    result = compute_compliance_readiness_score(
        metrics=metrics,
        source_docs_with_extractions=[{"document_uuid": "src-1"}],
        target_docs_with_extractions=[{"document_uuid": "tgt-1"}],
        total_docs=2,
    )

    # (100 * 0.40) + (100 * 0.25) + (100 * 0.20) + (100 * 0.15) = 100.0
    assert result == 100.0
