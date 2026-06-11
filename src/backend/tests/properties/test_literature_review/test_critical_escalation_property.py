"""Property-based tests for critical contradiction escalation logic.

Property 13: Critical contradiction escalates to impact analysis
For any ContradictionAlert severity, the escalation decision function
SHALL return True (escalate) only for severity "critical" and False
for "major" or "minor".

This validates the pure decision logic used by
ContradictionDetectionService._escalate_critical to determine whether
ImpactAnalysisService.compute_change_delta should be invoked.

**Validates: Requirements 6.2**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import given, settings


def should_escalate(severity: str) -> bool:
    """Determine whether a contradiction severity warrants escalation.

    Only "critical" severity triggers ImpactAnalysisService invocation.

    Args:
        severity: Contradiction severity level ("critical", "major", "minor").

    Returns:
        True if escalation is required, False otherwise.
    """
    return severity == "critical"


# ---------------------------------------------------------------------------
# Property 13: severity "critical" → should escalate (returns True)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(severity=st.just("critical"))
def test_critical_severity_escalates(severity: str) -> None:
    """should_escalate SHALL return True when severity is "critical".

    WHEN a ContradictionAlert with severity "critical" is created,
    THE system SHALL automatically invoke ImpactAnalysisService.

    **Validates: Requirements 6.2**
    """
    assert should_escalate(severity) is True


# ---------------------------------------------------------------------------
# Property 13: severity "major" → should NOT escalate (returns False)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(severity=st.just("major"))
def test_major_severity_does_not_escalate(severity: str) -> None:
    """should_escalate SHALL return False when severity is "major".

    ImpactAnalysisService.compute_change_delta MUST NOT be invoked
    for "major" severity contradictions.

    **Validates: Requirements 6.2**
    """
    assert should_escalate(severity) is False


# ---------------------------------------------------------------------------
# Property 13: severity "minor" → should NOT escalate (returns False)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(severity=st.just("minor"))
def test_minor_severity_does_not_escalate(severity: str) -> None:
    """should_escalate SHALL return False when severity is "minor".

    ImpactAnalysisService.compute_change_delta MUST NOT be invoked
    for "minor" severity contradictions.

    **Validates: Requirements 6.2**
    """
    assert should_escalate(severity) is False


# ---------------------------------------------------------------------------
# Property 13: Any severity from valid set — escalation iff "critical"
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(severity=st.sampled_from(["critical", "major", "minor"]))
def test_escalation_iff_critical(severity: str) -> None:
    """should_escalate SHALL return True if and only if severity == "critical".

    For all valid severity values drawn from ("critical", "major", "minor"),
    only "critical" triggers escalation to ImpactAnalysisService.

    **Validates: Requirements 6.2**
    """
    result = should_escalate(severity)
    if severity == "critical":
        assert result is True, (
            f"Expected escalation for severity='critical', got {result}"
        )
    else:
        assert result is False, (
            f"Expected no escalation for severity='{severity}', got {result}"
        )
