"""Property-based tests for open alerts aggregate count correctness.

Property 14: Open alerts aggregate count correctness
For any list of ContradictionAlerts with varying severity and status,
the system SHALL compute total_open_by_severity as the count of alerts
where status is "new" or "acknowledged", grouped by severity.

Resolved and dismissed alerts SHALL NOT be counted in open totals.

**Validates: Requirements 6.7**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from __future__ import annotations

from collections import Counter

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure function under test (mirrors contradiction summary endpoint logic)
# ---------------------------------------------------------------------------

OPEN_STATUSES = ("new", "acknowledged")
VALID_STATUSES = ("new", "acknowledged", "resolved", "dismissed")
VALID_SEVERITIES = ("critical", "major", "minor")


def compute_open_alerts_by_severity(alerts: list[dict]) -> dict[str, int]:
    """Count open alerts (status: new or acknowledged) grouped by severity.

    Args:
        alerts: List of alert dicts, each with "status" and "severity" keys.

    Returns:
        Dict mapping severity to count of open alerts with that severity.
        Only includes severities with count > 0.
    """
    result: dict[str, int] = {}
    for alert in alerts:
        if alert["status"] in OPEN_STATUSES:
            sev = alert["severity"]
            result[sev] = result.get(sev, 0) + 1
    return result


# ---------------------------------------------------------------------------
# Reference implementation for verification
# ---------------------------------------------------------------------------


def _reference_open_count(alerts: list[dict]) -> dict[str, int]:
    """Manual reference computation using Counter for validation."""
    open_alerts = [a for a in alerts if a["status"] in OPEN_STATUSES]
    counts = Counter(a["severity"] for a in open_alerts)
    return dict(counts)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

severity_st = st.sampled_from(list(VALID_SEVERITIES))
status_st = st.sampled_from(list(VALID_STATUSES))

alert_st = st.fixed_dictionaries(
    {
        "severity": severity_st,
        "status": status_st,
    }
)

alerts_list_st = st.lists(alert_st, min_size=0, max_size=100)


# ---------------------------------------------------------------------------
# Property 14: Aggregate matches manual count of open alerts by severity
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(alerts=alerts_list_st)
def test_open_alerts_aggregate_matches_manual_count(alerts: list[dict]) -> None:
    """compute_open_alerts_by_severity SHALL return a dict matching the manual
    count of alerts with status in ("new", "acknowledged") grouped by severity.

    **Validates: Requirements 6.7**
    """
    result = compute_open_alerts_by_severity(alerts)
    expected = _reference_open_count(alerts)
    assert result == expected


# ---------------------------------------------------------------------------
# Property 14: Resolved alerts are not counted
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    severity=severity_st,
    count=st.integers(min_value=1, max_value=50),
)
def test_resolved_alerts_not_counted(severity: str, count: int) -> None:
    """compute_open_alerts_by_severity SHALL NOT count alerts with status
    "resolved" in the open totals.

    **Validates: Requirements 6.7**
    """
    alerts = [{"severity": severity, "status": "resolved"} for _ in range(count)]
    result = compute_open_alerts_by_severity(alerts)
    assert result == {}


# ---------------------------------------------------------------------------
# Property 14: Dismissed alerts are not counted
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    severity=severity_st,
    count=st.integers(min_value=1, max_value=50),
)
def test_dismissed_alerts_not_counted(severity: str, count: int) -> None:
    """compute_open_alerts_by_severity SHALL NOT count alerts with status
    "dismissed" in the open totals.

    **Validates: Requirements 6.7**
    """
    alerts = [{"severity": severity, "status": "dismissed"} for _ in range(count)]
    result = compute_open_alerts_by_severity(alerts)
    assert result == {}


# ---------------------------------------------------------------------------
# Property 14: Only "new" and "acknowledged" contribute to open count
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(alerts=alerts_list_st)
def test_only_new_and_acknowledged_are_open(alerts: list[dict]) -> None:
    """The sum of all values in the result SHALL equal the total number of
    alerts whose status is "new" or "acknowledged".

    **Validates: Requirements 6.7**
    """
    result = compute_open_alerts_by_severity(alerts)
    total_open = sum(result.values())
    expected_total = sum(1 for a in alerts if a["status"] in OPEN_STATUSES)
    assert total_open == expected_total


# ---------------------------------------------------------------------------
# Property 14: Each severity key in result has correct count
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(alerts=alerts_list_st)
def test_each_severity_count_is_correct(alerts: list[dict]) -> None:
    """For each severity in the result, the count SHALL equal the number
    of alerts with that severity AND status in ("new", "acknowledged").

    **Validates: Requirements 6.7**
    """
    result = compute_open_alerts_by_severity(alerts)

    for sev in VALID_SEVERITIES:
        expected = sum(
            1
            for a in alerts
            if a["severity"] == sev and a["status"] in OPEN_STATUSES
        )
        if expected > 0:
            assert result.get(sev, 0) == expected
        else:
            assert sev not in result


# ---------------------------------------------------------------------------
# Property 14: Empty list produces empty result
# ---------------------------------------------------------------------------


def test_empty_alerts_produces_empty_result() -> None:
    """compute_open_alerts_by_severity with an empty list SHALL return
    an empty dict.

    **Validates: Requirements 6.7**
    """
    assert compute_open_alerts_by_severity([]) == {}


# ---------------------------------------------------------------------------
# Property 14: Mixed statuses — only open ones counted
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    new_count=st.integers(min_value=0, max_value=30),
    ack_count=st.integers(min_value=0, max_value=30),
    resolved_count=st.integers(min_value=0, max_value=30),
    dismissed_count=st.integers(min_value=0, max_value=30),
    severity=severity_st,
)
def test_mixed_statuses_single_severity(
    new_count: int,
    ack_count: int,
    resolved_count: int,
    dismissed_count: int,
    severity: str,
) -> None:
    """For a single severity with mixed statuses, the open count SHALL
    equal new_count + ack_count.

    **Validates: Requirements 6.7**
    """
    alerts: list[dict] = (
        [{"severity": severity, "status": "new"}] * new_count
        + [{"severity": severity, "status": "acknowledged"}] * ack_count
        + [{"severity": severity, "status": "resolved"}] * resolved_count
        + [{"severity": severity, "status": "dismissed"}] * dismissed_count
    )
    result = compute_open_alerts_by_severity(alerts)
    expected_open = new_count + ack_count

    if expected_open > 0:
        assert result == {severity: expected_open}
    else:
        assert result == {}
