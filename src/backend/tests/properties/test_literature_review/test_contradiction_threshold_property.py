"""Property-based tests for contradiction alert creation threshold.

Property 11: Contradiction alert creation threshold
For any ContradictionAnalysisResult with varying contradiction_found (True/False)
and confidence (0.0–1.0), the system SHALL create a Contradiction_Alert if and only
if contradiction_found is True AND confidence >= 0.7 (the default threshold).

No alert SHALL be created for results below the threshold or with
contradiction_found=False.

**Validates: Requirements 5.6**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from __future__ import annotations

from dataclasses import dataclass

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Domain model (mirrors ContradictionAnalysisResult from the service)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContradictionAnalysisResult:
    """Result of analyzing one literature-vs-internal-doc pair."""

    contradiction_found: bool
    contradiction_description: str
    severity: str
    affected_internal_sections: list[str]
    evidence_from_literature: str
    recommended_action: str
    confidence: float


# ---------------------------------------------------------------------------
# Pure function extracted from ContradictionDetectionService alert creation logic
# ---------------------------------------------------------------------------


def should_create_alert(
    result: ContradictionAnalysisResult, confidence_threshold: float = 0.7
) -> bool:
    """Determine whether a ContradictionAlert should be created.

    An alert is created if and only if:
    - contradiction_found is True, AND
    - confidence >= confidence_threshold

    Args:
        result: The analysis result for a literature-vs-internal-doc pair.
        confidence_threshold: Minimum confidence to create an alert (default 0.7).

    Returns:
        True if an alert should be created, False otherwise.
    """
    return result.contradiction_found and result.confidence >= confidence_threshold


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

severity_st = st.sampled_from(["critical", "major", "minor"])

contradiction_analysis_result_st = st.builds(
    ContradictionAnalysisResult,
    contradiction_found=st.booleans(),
    contradiction_description=st.text(min_size=0, max_size=50),
    severity=severity_st,
    affected_internal_sections=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    evidence_from_literature=st.text(min_size=0, max_size=50),
    recommended_action=st.text(min_size=0, max_size=50),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)

confidence_threshold_st = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)


# ---------------------------------------------------------------------------
# Property 11: Alert created iff contradiction_found AND confidence >= threshold
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(result=contradiction_analysis_result_st, threshold=confidence_threshold_st)
def test_alert_iff_contradiction_found_and_confidence_above_threshold(
    result: ContradictionAnalysisResult, threshold: float
) -> None:
    """should_create_alert returns True iff contradiction_found is True AND
    confidence >= threshold.

    **Validates: Requirements 5.6**
    """
    expected = result.contradiction_found and result.confidence >= threshold
    assert should_create_alert(result, threshold) == expected


# ---------------------------------------------------------------------------
# Property 11: No alert when contradiction_found is False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    threshold=confidence_threshold_st,
)
def test_no_alert_when_contradiction_not_found(
    confidence: float, threshold: float
) -> None:
    """should_create_alert SHALL return False when contradiction_found is False,
    regardless of confidence value.

    **Validates: Requirements 5.6**
    """
    result = ContradictionAnalysisResult(
        contradiction_found=False,
        contradiction_description="Some description",
        severity="major",
        affected_internal_sections=["section-1"],
        evidence_from_literature="Some evidence",
        recommended_action="Some action",
        confidence=confidence,
    )
    assert should_create_alert(result, threshold) is False


# ---------------------------------------------------------------------------
# Property 11: No alert when confidence is below threshold
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    threshold=st.floats(
        min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    data=st.data(),
)
def test_no_alert_when_confidence_below_threshold(
    threshold: float, data: st.DataObject
) -> None:
    """should_create_alert SHALL return False when confidence < threshold,
    even when contradiction_found is True.

    **Validates: Requirements 5.6**
    """
    # Generate confidence strictly below threshold
    confidence = data.draw(
        st.floats(
            min_value=0.0,
            max_value=max(0.0, threshold - 1e-10),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    result = ContradictionAnalysisResult(
        contradiction_found=True,
        contradiction_description="Contradiction detected",
        severity="critical",
        affected_internal_sections=["section-A"],
        evidence_from_literature="Evidence text",
        recommended_action="Update SOP",
        confidence=confidence,
    )
    assert should_create_alert(result, threshold) is False


# ---------------------------------------------------------------------------
# Property 11: Alert created when both conditions met
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    threshold=confidence_threshold_st,
    data=st.data(),
)
def test_alert_created_when_both_conditions_met(
    threshold: float, data: st.DataObject
) -> None:
    """should_create_alert SHALL return True when contradiction_found is True
    AND confidence >= threshold.

    **Validates: Requirements 5.6**
    """
    # Generate confidence at or above threshold
    confidence = data.draw(
        st.floats(
            min_value=threshold,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    result = ContradictionAnalysisResult(
        contradiction_found=True,
        contradiction_description="Critical contradiction found",
        severity="critical",
        affected_internal_sections=["section-1", "section-2"],
        evidence_from_literature="Strong evidence from paper",
        recommended_action="Immediate review required",
        confidence=confidence,
    )
    assert should_create_alert(result, threshold) is True


# ---------------------------------------------------------------------------
# Property 11: Default threshold is 0.7
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_default_threshold_is_0_7(confidence: float) -> None:
    """should_create_alert with default threshold SHALL create an alert iff
    contradiction_found is True AND confidence >= 0.7.

    **Validates: Requirements 5.6**
    """
    result = ContradictionAnalysisResult(
        contradiction_found=True,
        contradiction_description="A contradiction",
        severity="major",
        affected_internal_sections=[],
        evidence_from_literature="Evidence",
        recommended_action="Action",
        confidence=confidence,
    )
    expected = confidence >= 0.7
    assert should_create_alert(result) == expected


# ---------------------------------------------------------------------------
# Property 11: Boundary — confidence exactly at threshold creates alert
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(threshold=confidence_threshold_st, severity=severity_st)
def test_confidence_at_boundary_creates_alert(
    threshold: float, severity: str
) -> None:
    """should_create_alert SHALL return True when confidence == threshold
    and contradiction_found is True (boundary condition).

    **Validates: Requirements 5.6**
    """
    result = ContradictionAnalysisResult(
        contradiction_found=True,
        contradiction_description="Boundary test",
        severity=severity,
        affected_internal_sections=["section-X"],
        evidence_from_literature="Boundary evidence",
        recommended_action="Boundary action",
        confidence=threshold,
    )
    assert should_create_alert(result, threshold) is True
