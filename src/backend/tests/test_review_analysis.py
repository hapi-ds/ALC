"""Tests for review analysis utilities (consensus and contradiction detection).

Covers:
- Task 3.3: Consensus and contradiction detection logic
- Requirements 3.5, 3.6
"""

from alcoabase.services.review_analysis import (
    detect_consensus,
    detect_contradictions,
)


# ---------------------------------------------------------------------------
# Consensus Detection Tests
# ---------------------------------------------------------------------------


class TestDetectConsensus:
    """Tests for detect_consensus function."""

    def test_empty_reports_returns_empty(self):
        """No reports means no consensus."""
        assert detect_consensus([]) == []

    def test_single_report_no_consensus(self):
        """A single report cannot have consensus (needs 2+)."""
        reports = [
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Critical", "description": "Missing"},
                ]
            }
        ]
        assert detect_consensus(reports) == []

    def test_two_reports_same_chapter_same_severity(self):
        """Two reports with same chapter+severity = consensus."""
        reports = [
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Major", "description": "Incomplete section"},
                ]
            },
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Major", "description": "Needs more detail"},
                ]
            },
        ]
        result = detect_consensus(reports)
        assert len(result) == 1
        assert result[0]["chapter"] == "Purpose"
        assert result[0]["severity"] == "Major"
        assert result[0]["count"] == 2
        assert len(result[0]["descriptions"]) == 2

    def test_two_reports_same_chapter_different_severity_no_consensus(self):
        """Same chapter but different severity is NOT consensus."""
        reports = [
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Critical", "description": "Bad"},
                ]
            },
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Minor", "description": "Okay"},
                ]
            },
        ]
        result = detect_consensus(reports)
        assert len(result) == 0

    def test_three_reports_consensus_with_count(self):
        """Three reports agreeing gives count=3."""
        reports = [
            {"findings": [{"chapter": "Scope", "severity": "Minor", "description": "A"}]},
            {"findings": [{"chapter": "Scope", "severity": "Minor", "description": "B"}]},
            {"findings": [{"chapter": "Scope", "severity": "Minor", "description": "C"}]},
        ]
        result = detect_consensus(reports)
        assert len(result) == 1
        assert result[0]["count"] == 3

    def test_multiple_consensus_findings(self):
        """Multiple (chapter, severity) pairs can each be consensus."""
        reports = [
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Critical", "description": "X"},
                    {"chapter": "Scope", "severity": "Major", "description": "Y"},
                ]
            },
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Critical", "description": "Z"},
                    {"chapter": "Scope", "severity": "Major", "description": "W"},
                ]
            },
        ]
        result = detect_consensus(reports)
        assert len(result) == 2
        # Should be sorted: Critical first, then Major
        assert result[0]["severity"] == "Critical"
        assert result[1]["severity"] == "Major"

    def test_duplicate_findings_in_same_report_counted_once(self):
        """Multiple findings for same chapter+severity in one report count as one."""
        reports = [
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Major", "description": "Issue 1"},
                    {"chapter": "Purpose", "severity": "Major", "description": "Issue 2"},
                ]
            },
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Major", "description": "Issue 3"},
                ]
            },
        ]
        result = detect_consensus(reports)
        assert len(result) == 1
        assert result[0]["count"] == 2  # 2 reports, not 3 findings

    def test_findings_with_missing_chapter_ignored(self):
        """Findings without a chapter field are skipped."""
        reports = [
            {"findings": [{"severity": "Major", "description": "No chapter"}]},
            {"findings": [{"severity": "Major", "description": "No chapter either"}]},
        ]
        result = detect_consensus(reports)
        assert len(result) == 0

    def test_findings_with_missing_severity_ignored(self):
        """Findings without a severity field are skipped."""
        reports = [
            {"findings": [{"chapter": "Purpose", "description": "No severity"}]},
            {"findings": [{"chapter": "Purpose", "description": "No severity either"}]},
        ]
        result = detect_consensus(reports)
        assert len(result) == 0

    def test_reports_with_no_findings_key(self):
        """Reports without a findings key are handled gracefully."""
        reports = [
            {},
            {"findings": [{"chapter": "Purpose", "severity": "Major", "description": "X"}]},
        ]
        result = detect_consensus(reports)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Contradiction Detection Tests
# ---------------------------------------------------------------------------


class TestDetectContradictions:
    """Tests for detect_contradictions function."""

    def test_empty_reports_returns_empty(self):
        """No reports means no contradictions."""
        assert detect_contradictions([]) == []

    def test_single_report_no_contradictions(self):
        """A single report cannot have contradictions."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Critical", "description": "Bad"}]}
        ]
        assert detect_contradictions(reports) == []

    def test_critical_vs_nothing_is_contradiction(self):
        """One report Critical, another has nothing for same chapter = contradiction."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Critical", "description": "Bad"}]},
            {"findings": []},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 1
        assert result[0]["chapter"] == "Purpose"
        assert result[0]["high_severity"] == "Critical"
        assert 0 in result[0]["high_severity_reports"]
        assert 1 in result[0]["low_severity_reports"]

    def test_major_vs_informational_is_contradiction(self):
        """One report Major, another Informational for same chapter = contradiction."""
        reports = [
            {"findings": [{"chapter": "Scope", "severity": "Major", "description": "Issue"}]},
            {"findings": [{"chapter": "Scope", "severity": "Informational", "description": "Note"}]},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 1
        assert result[0]["chapter"] == "Scope"
        assert result[0]["high_severity"] == "Major"

    def test_critical_vs_informational_is_contradiction(self):
        """One report Critical, another Informational = contradiction."""
        reports = [
            {"findings": [{"chapter": "Procedure", "severity": "Critical", "description": "X"}]},
            {"findings": [{"chapter": "Procedure", "severity": "Informational", "description": "Y"}]},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 1
        assert result[0]["high_severity"] == "Critical"

    def test_major_vs_minor_no_contradiction(self):
        """Major vs Minor is NOT a contradiction (Minor is not 'nothing or Informational')."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Major", "description": "X"}]},
            {"findings": [{"chapter": "Purpose", "severity": "Minor", "description": "Y"}]},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 0

    def test_minor_vs_nothing_no_contradiction(self):
        """Minor vs nothing is NOT a contradiction (Minor is not Critical/Major)."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Minor", "description": "X"}]},
            {"findings": []},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 0

    def test_both_critical_no_contradiction(self):
        """Both reports Critical for same chapter = no contradiction (they agree)."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Critical", "description": "X"}]},
            {"findings": [{"chapter": "Purpose", "severity": "Critical", "description": "Y"}]},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 0

    def test_multiple_contradictions(self):
        """Multiple chapters can each have contradictions."""
        reports = [
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Critical", "description": "X"},
                    {"chapter": "Scope", "severity": "Major", "description": "Y"},
                ]
            },
            {"findings": []},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 2
        # Critical contradiction should come first
        assert result[0]["high_severity"] == "Critical"
        assert result[1]["high_severity"] == "Major"

    def test_three_reports_mixed(self):
        """Three reports: two flag Critical, one has nothing = contradiction."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Critical", "description": "A"}]},
            {"findings": [{"chapter": "Purpose", "severity": "Critical", "description": "B"}]},
            {"findings": []},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 1
        assert result[0]["high_severity"] == "Critical"
        assert len(result[0]["high_severity_reports"]) == 2
        assert len(result[0]["low_severity_reports"]) == 1

    def test_report_with_no_findings_key(self):
        """Reports without findings key treated as having no findings."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Major", "description": "X"}]},
            {},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 1
        assert result[0]["chapter"] == "Purpose"

    def test_different_chapters_no_contradiction(self):
        """Different chapters don't create contradictions between each other."""
        reports = [
            {"findings": [{"chapter": "Purpose", "severity": "Critical", "description": "X"}]},
            {"findings": [{"chapter": "Scope", "severity": "Critical", "description": "Y"}]},
        ]
        # Report 0 has nothing for Scope, Report 1 has nothing for Purpose
        # Both are contradictions since one has Critical and the other has nothing
        result = detect_contradictions(reports)
        assert len(result) == 2

    def test_highest_severity_reported_in_contradiction(self):
        """When multiple high-severity findings exist, report the highest."""
        reports = [
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Critical", "description": "X"},
                ]
            },
            {
                "findings": [
                    {"chapter": "Purpose", "severity": "Major", "description": "Y"},
                ]
            },
            {"findings": []},
        ]
        result = detect_contradictions(reports)
        assert len(result) == 1
        # Report 2 has nothing, reports 0 and 1 have Critical and Major
        # The highest is Critical
        assert result[0]["high_severity"] == "Critical"
