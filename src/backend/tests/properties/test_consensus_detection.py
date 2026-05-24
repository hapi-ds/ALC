"""Property-based tests for consensus detection correctness.

Tests Property 3 from the multi-agent always-on auditing design document,
validating that consensus detection correctly identifies findings agreed upon
by 2+ agents and that the consensus count never exceeds the total unique
(chapter, severity) pairs across all reports.

**Validates: Requirements 3.5, 3.6**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 3)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (Requirement 3)
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.review_analysis import detect_consensus


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

SEVERITIES = ["Critical", "Major", "Minor", "Informational"]
CHAPTERS = [
    "1.0", "1.1", "1.2", "2.0", "2.1", "2.2", "3.0", "3.1",
    "4.0", "4.1", "5.0", "6.0", "7.0", "8.0", "9.0", "10.0",
]


@st.composite
def st_finding(draw: st.DrawFn) -> dict:
    """Generate a single review finding with chapter and severity.

    Returns:
        A finding dict with chapter, severity, and optional description.
    """
    chapter = draw(st.sampled_from(CHAPTERS))
    severity = draw(st.sampled_from(SEVERITIES))
    description = draw(st.text(min_size=0, max_size=50))
    return {"chapter": chapter, "severity": severity, "description": description}


@st.composite
def st_report(draw: st.DrawFn) -> dict:
    """Generate a single agent review report with a list of findings.

    Returns:
        A report dict containing a "findings" list.
    """
    num_findings = draw(st.integers(min_value=0, max_value=10))
    findings = draw(st.lists(st_finding(), min_size=num_findings, max_size=num_findings))
    return {"findings": findings}


@st.composite
def st_reports(draw: st.DrawFn) -> list[dict]:
    """Generate a list of agent review reports.

    Returns:
        A list of report dicts, simulating multiple agent reviews.
    """
    num_reports = draw(st.integers(min_value=0, max_value=6))
    return draw(st.lists(st_report(), min_size=num_reports, max_size=num_reports))


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@given(reports=st_reports())
@settings(max_examples=200)
def test_consensus_count_bounded_by_unique_pairs(reports: list[dict]) -> None:
    """Property 3: Consensus count ≤ total unique (chapter, severity) pairs.

    For any set of agent reports, the number of consensus findings returned
    by detect_consensus SHALL be ≤ the total number of unique (chapter, severity)
    pairs that exist across all reports.

    **Validates: Requirements 3.5, 3.6**
    """
    consensus = detect_consensus(reports)

    # Compute total unique (chapter, severity) pairs across all reports
    unique_pairs: set[tuple[str, str]] = set()
    for report in reports:
        for finding in report.get("findings", []):
            chapter = finding.get("chapter", "")
            severity = finding.get("severity", "")
            if chapter and severity:
                unique_pairs.add((chapter, severity))

    assert len(consensus) <= len(unique_pairs)


@given(reports=st_reports())
@settings(max_examples=200)
def test_consensus_findings_have_count_at_least_two(reports: list[dict]) -> None:
    """Property 3: Each consensus finding has count >= 2.

    For any set of agent reports, every finding returned by detect_consensus
    must have a count of at least 2, meaning at least 2 reports agree on
    the same (chapter, severity) pair.

    **Validates: Requirements 3.5, 3.6**
    """
    consensus = detect_consensus(reports)

    for finding in consensus:
        assert finding["count"] >= 2, (
            f"Consensus finding for chapter '{finding['chapter']}' with severity "
            f"'{finding['severity']}' has count {finding['count']} < 2"
        )


@given(reports=st_reports())
@settings(max_examples=200)
def test_consensus_pairs_appear_in_at_least_two_reports(reports: list[dict]) -> None:
    """Property 3: No consensus finding has a (chapter, severity) pair appearing in fewer than 2 reports.

    For any set of agent reports, each consensus finding's (chapter, severity)
    pair must actually appear in at least 2 distinct reports.

    **Validates: Requirements 3.5, 3.6**
    """
    consensus = detect_consensus(reports)

    # For each consensus finding, verify the pair appears in 2+ distinct reports
    for finding in consensus:
        chapter = finding["chapter"]
        severity = finding["severity"]

        # Count how many distinct reports contain this (chapter, severity) pair
        report_count = 0
        for report in reports:
            report_findings = report.get("findings", [])
            has_pair = any(
                f.get("chapter") == chapter and f.get("severity") == severity
                for f in report_findings
            )
            if has_pair:
                report_count += 1

        assert report_count >= 2, (
            f"Consensus finding ({chapter}, {severity}) only appears in "
            f"{report_count} report(s), expected at least 2"
        )
