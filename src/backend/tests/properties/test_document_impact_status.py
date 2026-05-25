"""Property-based tests for document impact status computation.

Tests Property 16 from the AI-Driven Change Impact Analysis design document,
validating that the is_up_to_date flag is true if and only if there are zero
unresolved critical or major findings where that document is the target.

The core logic under test:
    is_up_to_date = (outstanding_critical + outstanding_major) == 0

**Validates: Requirements 8.5**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md (Property 16)
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md (8.5)
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.schemas.impact_analysis import DocumentImpactStatusResponse


# ---------------------------------------------------------------------------
# Pure logic: document impact status computation (mirrors service logic)
# ---------------------------------------------------------------------------


def compute_is_up_to_date(outstanding_critical: int, outstanding_major: int) -> bool:
    """Compute the is_up_to_date flag based on outstanding notification counts.

    A document is considered up-to-date if and only if there are zero
    unresolved critical or major findings targeting it.

    Args:
        outstanding_critical: Count of unacknowledged critical notifications.
        outstanding_major: Count of unacknowledged major notifications.

    Returns:
        True if both counts are zero, False otherwise.
    """
    return (outstanding_critical + outstanding_major) == 0


def count_outstanding_by_severity(
    notifications: list[dict],
) -> tuple[int, int]:
    """Count outstanding (unacknowledged) critical and major notifications.

    Filters notifications to only those that are unacknowledged and have
    severity "critical" or "major".

    Args:
        notifications: List of notification dicts with keys:
            - impact_severity: "critical", "major", "minor", or "unknown"
            - is_acknowledged: bool

    Returns:
        Tuple of (critical_count, major_count).
    """
    critical = sum(
        1
        for n in notifications
        if n["impact_severity"] == "critical" and not n["is_acknowledged"]
    )
    major = sum(
        1
        for n in notifications
        if n["impact_severity"] == "major" and not n["is_acknowledged"]
    )
    return critical, major


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

_SEVERITIES = ["critical", "major", "minor", "unknown"]


@st.composite
def st_notification(draw: st.DrawFn) -> dict:
    """Generate a single notification with random severity and acknowledgment state.

    Returns:
        Dictionary with impact_severity and is_acknowledged fields.
    """
    severity = draw(st.sampled_from(_SEVERITIES))
    is_acknowledged = draw(st.booleans())
    return {
        "impact_severity": severity,
        "is_acknowledged": is_acknowledged,
    }


@st.composite
def st_notification_set(draw: st.DrawFn) -> list[dict]:
    """Generate a list of notifications for a document.

    Generates between 0 and 50 notifications with random severities
    and acknowledgment states.

    Returns:
        List of notification dictionaries.
    """
    return draw(st.lists(st_notification(), min_size=0, max_size=50))


@st.composite
def st_outstanding_counts(draw: st.DrawFn) -> tuple[int, int]:
    """Generate random outstanding critical and major counts.

    Returns:
        Tuple of (outstanding_critical, outstanding_major) with values 0-100.
    """
    critical = draw(st.integers(min_value=0, max_value=100))
    major = draw(st.integers(min_value=0, max_value=100))
    return critical, major


# ---------------------------------------------------------------------------
# Property 16: Document Impact Status Computation
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(counts=st_outstanding_counts())
def test_is_up_to_date_true_iff_zero_critical_and_major(
    counts: tuple[int, int],
) -> None:
    """For any document, is_up_to_date SHALL be true if and only if
    there are zero unresolved critical or major findings.

    **Validates: Requirements 8.5**
    """
    outstanding_critical, outstanding_major = counts
    result = compute_is_up_to_date(outstanding_critical, outstanding_major)

    if outstanding_critical == 0 and outstanding_major == 0:
        assert result is True, (
            f"is_up_to_date should be True when critical={outstanding_critical} "
            f"and major={outstanding_major}, but got False"
        )
    else:
        assert result is False, (
            f"is_up_to_date should be False when critical={outstanding_critical} "
            f"and major={outstanding_major}, but got True"
        )


@settings(max_examples=200)
@given(notifications=st_notification_set())
def test_is_up_to_date_from_notification_list(
    notifications: list[dict],
) -> None:
    """For any set of notifications targeting a document, is_up_to_date
    SHALL be true if and only if there are zero unacknowledged critical
    or major notifications.

    This tests the full pipeline: counting outstanding notifications by
    severity, then computing the status flag.

    **Validates: Requirements 8.5**
    """
    critical_count, major_count = count_outstanding_by_severity(notifications)
    result = compute_is_up_to_date(critical_count, major_count)

    # Verify the biconditional: is_up_to_date ↔ (critical + major == 0)
    expected = (critical_count + major_count) == 0
    assert result == expected, (
        f"is_up_to_date={result} but expected={expected} "
        f"(critical={critical_count}, major={major_count}, "
        f"total_notifications={len(notifications)})"
    )


@settings(max_examples=200)
@given(notifications=st_notification_set())
def test_minor_and_unknown_do_not_affect_up_to_date(
    notifications: list[dict],
) -> None:
    """Minor and unknown severity notifications SHALL NOT affect the
    is_up_to_date computation. Only critical and major matter.

    **Validates: Requirements 8.5**
    """
    critical_count, major_count = count_outstanding_by_severity(notifications)

    # Count minor and unknown unacknowledged
    minor_count = sum(
        1
        for n in notifications
        if n["impact_severity"] == "minor" and not n["is_acknowledged"]
    )
    unknown_count = sum(
        1
        for n in notifications
        if n["impact_severity"] == "unknown" and not n["is_acknowledged"]
    )

    result = compute_is_up_to_date(critical_count, major_count)

    # Even with many minor/unknown unacknowledged notifications,
    # is_up_to_date should only depend on critical + major
    if critical_count == 0 and major_count == 0:
        assert result is True, (
            f"is_up_to_date should be True regardless of minor={minor_count} "
            f"and unknown={unknown_count} unacknowledged notifications"
        )


@settings(max_examples=200)
@given(notifications=st_notification_set())
def test_acknowledged_notifications_do_not_affect_status(
    notifications: list[dict],
) -> None:
    """Acknowledged notifications SHALL NOT count toward outstanding
    findings, regardless of their severity.

    **Validates: Requirements 8.5**
    """
    # Acknowledge all notifications
    all_acknowledged = [
        {**n, "is_acknowledged": True} for n in notifications
    ]

    critical_count, major_count = count_outstanding_by_severity(all_acknowledged)
    result = compute_is_up_to_date(critical_count, major_count)

    # With all notifications acknowledged, counts should be zero
    assert critical_count == 0, (
        f"Expected 0 outstanding critical after acknowledging all, got {critical_count}"
    )
    assert major_count == 0, (
        f"Expected 0 outstanding major after acknowledging all, got {major_count}"
    )
    assert result is True, (
        "is_up_to_date should be True when all notifications are acknowledged"
    )


@settings(max_examples=100)
@given(counts=st_outstanding_counts())
def test_document_impact_status_response_schema_consistency(
    counts: tuple[int, int],
) -> None:
    """The DocumentImpactStatusResponse schema SHALL correctly represent
    the computed is_up_to_date value consistent with outstanding counts.

    **Validates: Requirements 8.5**
    """
    outstanding_critical, outstanding_major = counts
    is_up_to_date = compute_is_up_to_date(outstanding_critical, outstanding_major)

    # Construct the response model to verify schema validation passes
    response = DocumentImpactStatusResponse(
        document_uuid="DOC-TEST-001",
        last_analysis_date=None,
        last_analysis_report_id=None,
        outstanding_critical_count=outstanding_critical,
        outstanding_major_count=outstanding_major,
        is_up_to_date=is_up_to_date,
    )

    # Verify the response model fields match our computation
    assert response.is_up_to_date == is_up_to_date
    assert response.outstanding_critical_count == outstanding_critical
    assert response.outstanding_major_count == outstanding_major

    # Verify the biconditional holds in the response
    expected_up_to_date = (
        response.outstanding_critical_count + response.outstanding_major_count
    ) == 0
    assert response.is_up_to_date == expected_up_to_date, (
        f"Response is_up_to_date={response.is_up_to_date} inconsistent with "
        f"counts: critical={response.outstanding_critical_count}, "
        f"major={response.outstanding_major_count}"
    )
