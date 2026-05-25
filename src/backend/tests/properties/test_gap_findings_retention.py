"""Property-based tests for gap findings retention.

Property 9: Gap Findings Retention

For any gap analysis producing more than 100 Gap_Findings, the system SHALL
retain exactly the 100 highest-severity findings (critical > major > minor)
and record the total count of detected gaps in job metadata. The retained set
SHALL always include all critical findings before major findings, and all major
findings before minor findings.

**Validates: Requirements 4.10**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/gap_analysis.py
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.gap_analysis import (
    MAX_GAP_FINDINGS,
    SEVERITY_PRIORITY,
    limit_gap_findings,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

SEVERITIES = st.sampled_from(["critical", "major", "minor"])

GAP_TYPES = st.sampled_from(["missing", "contradicts", "incomplete", "outdated"])

@st.composite
def st_gap_finding(draw: st.DrawFn, index: int = 0) -> dict:
    """Generate a single gap finding dict matching GapFindingSchema structure.

    Uses lightweight fixed-format strings to keep generation fast while
    varying the severity (the property under test).
    """
    severity = draw(SEVERITIES)
    gap_type = draw(GAP_TYPES)
    return {
        "source_section": f"Source Section {index}",
        "source_content_excerpt": f"Source excerpt {index}",
        "target_section": f"Target Section {index}",
        "target_content_excerpt": f"Target excerpt {index}",
        "gap_type": gap_type,
        "severity": severity,
        "remediation_suggestion": f"Fix gap {index}",
        "inference_prompt_summary": f"Prompt {index}",
        "model_response_summary": f"Response {index}",
        "token_count": draw(st.integers(min_value=10, max_value=5000)),
    }


@st.composite
def st_findings_over_limit(draw: st.DrawFn) -> list[dict]:
    """Generate a list of >100 gap findings with random severities.

    Uses a fixed count range close to the limit to keep generation fast
    while still exercising the limiting logic.
    """
    count = draw(st.integers(min_value=101, max_value=200))
    findings = []
    for i in range(count):
        severity = draw(SEVERITIES)
        gap_type = draw(GAP_TYPES)
        findings.append({
            "source_section": f"Source Section {i}",
            "source_content_excerpt": f"Source excerpt {i}",
            "target_section": f"Target Section {i}",
            "target_content_excerpt": f"Target excerpt {i}",
            "gap_type": gap_type,
            "severity": severity,
            "remediation_suggestion": f"Fix gap {i}",
            "inference_prompt_summary": f"Prompt {i}",
            "model_response_summary": f"Response {i}",
            "token_count": 100 + i,
        })
    return findings


@st.composite
def st_findings_at_or_under_limit(draw: st.DrawFn) -> list[dict]:
    """Generate a list of <=100 gap findings."""
    count = draw(st.integers(min_value=0, max_value=100))
    findings = []
    for i in range(count):
        severity = draw(SEVERITIES)
        gap_type = draw(GAP_TYPES)
        findings.append({
            "source_section": f"Source Section {i}",
            "source_content_excerpt": f"Source excerpt {i}",
            "target_section": f"Target Section {i}",
            "target_content_excerpt": f"Target excerpt {i}",
            "gap_type": gap_type,
            "severity": severity,
            "remediation_suggestion": f"Fix gap {i}",
            "inference_prompt_summary": f"Prompt {i}",
            "model_response_summary": f"Response {i}",
            "token_count": 100 + i,
        })
    return findings


# ---------------------------------------------------------------------------
# Property 9: Gap Findings Retention — Top 100 by severity
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(findings=st_findings_over_limit())
def test_retains_exactly_100_when_over_limit(findings: list[dict]) -> None:
    """For any gap analysis producing more than 100 Gap_Findings, the system
    SHALL retain exactly 100 findings.

    **Validates: Requirements 4.10**
    """
    result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

    assert len(result) == 100


@settings(max_examples=100)
@given(findings=st_findings_over_limit())
def test_retained_findings_sorted_by_severity_priority(
    findings: list[dict],
) -> None:
    """The retained set SHALL always include all critical findings before
    major findings, and all major findings before minor findings. The output
    list SHALL be sorted by severity priority (critical > major > minor).

    **Validates: Requirements 4.10**
    """
    result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

    # Verify the result is sorted by severity priority
    for i in range(len(result) - 1):
        current_priority = SEVERITY_PRIORITY.get(
            result[i].get("severity", "minor"), 2
        )
        next_priority = SEVERITY_PRIORITY.get(
            result[i + 1].get("severity", "minor"), 2
        )
        assert current_priority <= next_priority, (
            f"Finding at index {i} has severity '{result[i]['severity']}' "
            f"(priority {current_priority}) but finding at index {i + 1} has "
            f"severity '{result[i + 1]['severity']}' (priority {next_priority}). "
            f"Results must be sorted by severity priority."
        )


@settings(max_examples=100)
@given(findings=st_findings_over_limit())
def test_highest_severity_findings_retained_first(
    findings: list[dict],
) -> None:
    """The system SHALL retain the 100 highest-severity findings. All critical
    findings SHALL be included before major findings, and all major findings
    before minor findings. If there are more than 100 critical+major findings,
    minor findings SHALL be excluded first.

    **Validates: Requirements 4.10**
    """
    result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

    # Count severities in the input
    input_critical = sum(
        1 for f in findings if f.get("severity") == "critical"
    )
    input_major = sum(1 for f in findings if f.get("severity") == "major")
    input_minor = sum(1 for f in findings if f.get("severity") == "minor")

    # Count severities in the result
    result_critical = sum(
        1 for f in result if f.get("severity") == "critical"
    )
    result_major = sum(1 for f in result if f.get("severity") == "major")
    result_minor = sum(1 for f in result if f.get("severity") == "minor")

    # All critical findings should be retained if they fit within 100
    if input_critical <= 100:
        assert result_critical == input_critical, (
            f"Expected all {input_critical} critical findings to be retained, "
            f"but got {result_critical}"
        )

    # If critical + major fit within 100, all major should be retained
    if input_critical + input_major <= 100:
        assert result_major == input_major, (
            f"Expected all {input_major} major findings to be retained "
            f"(critical + major = {input_critical + input_major} <= 100), "
            f"but got {result_major}"
        )

    # Minor findings should only appear if there's room after critical + major
    if input_critical + input_major >= 100:
        assert result_minor == 0, (
            f"Expected 0 minor findings (critical + major >= 100), "
            f"but got {result_minor}"
        )


@settings(max_examples=100)
@given(findings=st_findings_at_or_under_limit())
def test_returns_all_when_at_or_under_limit(findings: list[dict]) -> None:
    """When findings count is <= 100, all findings SHALL be returned
    (sorted by severity priority).

    **Validates: Requirements 4.10**
    """
    result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

    assert len(result) == len(findings)


@settings(max_examples=100)
@given(findings=st_findings_at_or_under_limit())
def test_under_limit_still_sorted_by_severity(findings: list[dict]) -> None:
    """Even when findings count is <= 100, the returned list SHALL be sorted
    by severity priority (critical > major > minor).

    **Validates: Requirements 4.10**
    """
    result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

    for i in range(len(result) - 1):
        current_priority = SEVERITY_PRIORITY.get(
            result[i].get("severity", "minor"), 2
        )
        next_priority = SEVERITY_PRIORITY.get(
            result[i + 1].get("severity", "minor"), 2
        )
        assert current_priority <= next_priority, (
            f"Finding at index {i} has severity '{result[i]['severity']}' "
            f"(priority {current_priority}) but finding at index {i + 1} has "
            f"severity '{result[i + 1]['severity']}' (priority {next_priority}). "
            f"Results must be sorted by severity priority."
        )


@settings(max_examples=100)
@given(findings=st_findings_over_limit())
def test_retained_findings_are_subset_of_input(findings: list[dict]) -> None:
    """All retained findings SHALL be from the original input set — no findings
    are fabricated or modified during the limiting process.

    **Validates: Requirements 4.10**
    """
    result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

    # Each result finding must exist in the original input
    for finding in result:
        assert finding in findings, (
            f"Retained finding not found in original input: {finding}"
        )
