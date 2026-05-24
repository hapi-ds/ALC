"""Unit tests for the ComplianceScorecardService.

Tests the compliance score computation, risk band classification,
trend detection, and scorecard aggregation logic.

References:
    - Requirements 6.1, 6.2, 6.3, 6.4, 6.5
"""

from alcoabase.services.compliance_scorecard import (
    SEVERITY_WEIGHTS,
    classify_risk_band,
    compute_compliance_score,
    determine_trend,
)


# ---------------------------------------------------------------------------
# compute_compliance_score tests
# ---------------------------------------------------------------------------


class TestComputeComplianceScore:
    """Tests for the compute_compliance_score function."""

    def test_no_findings_returns_100(self):
        """Empty findings should yield a perfect score."""
        assert compute_compliance_score({}) == 100.0

    def test_single_critical_finding(self):
        """One Critical finding deducts 25 points."""
        score = compute_compliance_score({"Critical": 1})
        assert score == 75.0

    def test_single_major_finding(self):
        """One Major finding deducts 10 points."""
        score = compute_compliance_score({"Major": 1})
        assert score == 90.0

    def test_single_minor_finding(self):
        """One Minor finding deducts 3 points."""
        score = compute_compliance_score({"Minor": 1})
        assert score == 97.0

    def test_single_informational_finding(self):
        """One Informational finding deducts 0.5 points."""
        score = compute_compliance_score({"Informational": 1})
        assert score == 99.5

    def test_mixed_findings(self):
        """Mixed findings: 2 Critical + 3 Major + 5 Minor = 100 - 95 = 5.0."""
        score = compute_compliance_score({
            "Critical": 2,
            "Major": 3,
            "Minor": 5,
        })
        assert score == 5.0

    def test_score_clamped_at_zero(self):
        """Score cannot go below 0.0 even with many findings."""
        score = compute_compliance_score({"Critical": 10})
        assert score == 0.0

    def test_large_penalty_clamped(self):
        """Very large penalties still clamp to 0.0."""
        score = compute_compliance_score({
            "Critical": 100,
            "Major": 100,
            "Minor": 100,
            "Informational": 100,
        })
        assert score == 0.0

    def test_unknown_severity_ignored(self):
        """Unknown severity keys are ignored (weight defaults to 0.0)."""
        score = compute_compliance_score({"Unknown": 100})
        assert score == 100.0

    def test_zero_counts(self):
        """Zero counts should not affect the score."""
        score = compute_compliance_score({
            "Critical": 0,
            "Major": 0,
            "Minor": 0,
            "Informational": 0,
        })
        assert score == 100.0

    def test_all_severities_one_each(self):
        """One of each severity: 25 + 10 + 3 + 0.5 = 38.5, score = 61.5."""
        score = compute_compliance_score({
            "Critical": 1,
            "Major": 1,
            "Minor": 1,
            "Informational": 1,
        })
        assert score == 61.5

    def test_score_precision(self):
        """Score should handle fractional results correctly."""
        # 3 Informational = 1.5 penalty, score = 98.5
        score = compute_compliance_score({"Informational": 3})
        assert score == 98.5


# ---------------------------------------------------------------------------
# classify_risk_band tests
# ---------------------------------------------------------------------------


class TestClassifyRiskBand:
    """Tests for the classify_risk_band function."""

    def test_excellent_at_100(self):
        assert classify_risk_band(100.0) == "Excellent"

    def test_excellent_at_90(self):
        assert classify_risk_band(90.0) == "Excellent"

    def test_good_at_89(self):
        assert classify_risk_band(89.0) == "Good"

    def test_good_at_75(self):
        assert classify_risk_band(75.0) == "Good"

    def test_needs_attention_at_74(self):
        assert classify_risk_band(74.0) == "Needs Attention"

    def test_needs_attention_at_50(self):
        assert classify_risk_band(50.0) == "Needs Attention"

    def test_at_risk_at_49(self):
        assert classify_risk_band(49.0) == "At Risk"

    def test_at_risk_at_25(self):
        assert classify_risk_band(25.0) == "At Risk"

    def test_critical_at_24(self):
        assert classify_risk_band(24.0) == "Critical"

    def test_critical_at_0(self):
        assert classify_risk_band(0.0) == "Critical"

    def test_boundary_89_99(self):
        """Score 89.99 should be Good."""
        assert classify_risk_band(89.99) == "Good"

    def test_boundary_74_99(self):
        """Score 74.99 should be Needs Attention."""
        assert classify_risk_band(74.99) == "Needs Attention"


# ---------------------------------------------------------------------------
# determine_trend tests
# ---------------------------------------------------------------------------


class TestDetermineTrend:
    """Tests for the determine_trend function."""

    def test_improving_when_current_higher(self):
        """Trend is improving when current > previous by more than 2."""
        assert determine_trend(85.0, 80.0) == "improving"

    def test_declining_when_current_lower(self):
        """Trend is declining when current < previous by more than 2."""
        assert determine_trend(75.0, 80.0) == "declining"

    def test_stable_when_similar(self):
        """Trend is stable when difference is within ±2."""
        assert determine_trend(80.0, 79.0) == "stable"

    def test_stable_at_exact_boundary(self):
        """Trend is stable when difference is exactly 2.0."""
        assert determine_trend(82.0, 80.0) == "stable"

    def test_stable_when_current_none(self):
        """Trend is stable when current period has no data."""
        assert determine_trend(None, 80.0) == "stable"

    def test_stable_when_previous_none(self):
        """Trend is stable when previous period has no data."""
        assert determine_trend(80.0, None) == "stable"

    def test_stable_when_both_none(self):
        """Trend is stable when both periods have no data."""
        assert determine_trend(None, None) == "stable"

    def test_improving_large_difference(self):
        """Large positive difference is improving."""
        assert determine_trend(95.0, 50.0) == "improving"

    def test_declining_large_difference(self):
        """Large negative difference is declining."""
        assert determine_trend(30.0, 90.0) == "declining"


# ---------------------------------------------------------------------------
# SEVERITY_WEIGHTS constant tests
# ---------------------------------------------------------------------------


class TestSeverityWeights:
    """Tests for the SEVERITY_WEIGHTS constant."""

    def test_critical_weight(self):
        assert SEVERITY_WEIGHTS["Critical"] == 25.0

    def test_major_weight(self):
        assert SEVERITY_WEIGHTS["Major"] == 10.0

    def test_minor_weight(self):
        assert SEVERITY_WEIGHTS["Minor"] == 3.0

    def test_informational_weight(self):
        assert SEVERITY_WEIGHTS["Informational"] == 0.5

    def test_all_weights_positive(self):
        """All severity weights must be positive."""
        for weight in SEVERITY_WEIGHTS.values():
            assert weight > 0.0
