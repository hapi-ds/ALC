"""Review analysis utilities for consensus and contradiction detection.

Provides pure functions to analyze multiple agent review reports and identify:
- Consensus findings: same chapter + same severity in 2+ reports
- Contradictions: one agent flags Critical/Major, another finds nothing or Informational

These utilities support the Master Auditor summarization step (Requirements 3.5, 3.6).
"""

from collections import defaultdict
from typing import Any


def detect_consensus(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect consensus findings across multiple agent review reports.

    A finding is "consensus" if and only if 2 or more reports contain findings
    with the same severity level referencing the same chapter/section identifier.

    Args:
        reports: List of report dicts, each containing a "findings" key with a list
            of finding dicts. Each finding must have at minimum "chapter" and "severity".

    Returns:
        List of consensus finding dicts, each containing:
            - chapter: The chapter/section identifier
            - severity: The agreed-upon severity level
            - count: Number of reports that agree
            - descriptions: List of finding descriptions from agreeing reports
    """
    # Count occurrences of each (chapter, severity) pair across reports
    # Key: (chapter, severity) -> list of (report_index, finding)
    pair_occurrences: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for report in reports:
        findings = report.get("findings", [])
        # Track which (chapter, severity) pairs this report contributes
        # Only count one occurrence per report per (chapter, severity) pair
        seen_in_report: set[tuple[str, str]] = set()

        for finding in findings:
            chapter = finding.get("chapter", "")
            severity = finding.get("severity", "")
            if not chapter or not severity:
                continue

            key = (chapter, severity)
            if key not in seen_in_report:
                seen_in_report.add(key)
                pair_occurrences[key].append(finding)

    # Filter to pairs with 2+ occurrences (consensus)
    consensus_findings: list[dict[str, Any]] = []
    for (chapter, severity), findings_list in pair_occurrences.items():
        if len(findings_list) >= 2:
            descriptions = [
                f.get("description", "") for f in findings_list if f.get("description")
            ]
            consensus_findings.append(
                {
                    "chapter": chapter,
                    "severity": severity,
                    "count": len(findings_list),
                    "descriptions": descriptions,
                }
            )

    # Sort by severity weight (Critical first) then by chapter
    severity_order = {"Critical": 0, "Major": 1, "Minor": 2, "Informational": 3}
    consensus_findings.sort(
        key=lambda f: (severity_order.get(f["severity"], 99), f["chapter"])
    )

    return consensus_findings


def detect_contradictions(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect contradictions across multiple agent review reports.

    A "contradiction" exists when one agent reports a finding as Critical or Major
    for a chapter/section while another agent reports no finding or only
    Informational for the same chapter/section.

    Args:
        reports: List of report dicts, each containing a "findings" key with a list
            of finding dicts. Each finding must have at minimum "chapter" and "severity".

    Returns:
        List of contradiction dicts, each containing:
            - chapter: The chapter/section identifier
            - high_severity: The Critical/Major severity reported by one agent
            - high_severity_reports: Indices of reports flagging Critical/Major
            - low_severity_reports: Indices of reports with no finding or Informational
            - details: Description of the contradiction
    """
    if len(reports) < 2:
        return []

    # For each report, build a mapping of chapter -> max severity found
    # None means no finding for that chapter
    report_chapter_severities: list[dict[str, str | None]] = []

    # Collect all chapters mentioned across all reports
    all_chapters: set[str] = set()

    for report in reports:
        chapter_max: dict[str, str | None] = {}
        findings = report.get("findings", [])
        for finding in findings:
            chapter = finding.get("chapter", "")
            severity = finding.get("severity", "")
            if not chapter or not severity:
                continue
            all_chapters.add(chapter)

            # Track the highest severity per chapter in this report
            current = chapter_max.get(chapter)
            if current is None or _severity_rank(severity) < _severity_rank(current):
                chapter_max[chapter] = severity

        report_chapter_severities.append(chapter_max)

    # Check each chapter for contradictions
    contradictions: list[dict[str, Any]] = []
    high_severities = {"Critical", "Major"}

    for chapter in sorted(all_chapters):
        high_reports: list[int] = []
        low_reports: list[int] = []

        for idx, chapter_map in enumerate(report_chapter_severities):
            severity = chapter_map.get(chapter)
            if severity in high_severities:
                high_reports.append(idx)
            elif severity is None or severity == "Informational":
                low_reports.append(idx)
            # Minor is neither high nor "nothing/Informational", so it doesn't
            # trigger a contradiction on either side

        # Contradiction exists when at least one report has Critical/Major
        # AND at least one report has nothing or Informational
        if high_reports and low_reports:
            # Get the highest severity among the high reports
            max_high_severity = "Major"
            for idx in high_reports:
                sev = report_chapter_severities[idx].get(chapter)
                if sev == "Critical":
                    max_high_severity = "Critical"
                    break

            contradictions.append(
                {
                    "chapter": chapter,
                    "high_severity": max_high_severity,
                    "high_severity_reports": high_reports,
                    "low_severity_reports": low_reports,
                    "details": (
                        f"Chapter '{chapter}': {len(high_reports)} report(s) flag "
                        f"{max_high_severity}, but {len(low_reports)} report(s) "
                        f"find nothing or only Informational."
                    ),
                }
            )

    # Sort by severity (Critical contradictions first)
    severity_order = {"Critical": 0, "Major": 1}
    contradictions.sort(
        key=lambda c: (severity_order.get(c["high_severity"], 99), c["chapter"])
    )

    return contradictions


def _severity_rank(severity: str) -> int:
    """Return numeric rank for severity (lower = more severe).

    Args:
        severity: Severity level string.

    Returns:
        Integer rank where 0 is most severe.
    """
    ranks = {"Critical": 0, "Major": 1, "Minor": 2, "Informational": 3}
    return ranks.get(severity, 99)
