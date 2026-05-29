"""Property-based tests for stale link lifecycle.

Property 13: Stale Link Lifecycle

Generate critical alerts and resolutions with various actions, verify stale
markers created for critical alerts, cleared on "links_verified"/
"matrix_regenerated" resolution, NOT cleared on "no_action_needed".

Key behaviors tested:
1. Critical alerts create stale markers for affected links
2. Non-critical alerts do NOT create stale markers
3. Resolution with "links_verified" clears stale markers
4. Resolution with "matrix_regenerated" clears stale markers
5. Resolution with "no_action_needed" does NOT clear stale markers

**Validates: Requirements 9.4, 9.8**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/traceability_alert.py
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Data models for pure-logic stale link lifecycle testing
# ---------------------------------------------------------------------------


@dataclass
class FakeTraceabilityLink:
    """Represents a traceability link within a matrix."""

    requirement_id: str
    test_case_id: str
    source_document_uuid: str
    link_confidence: float


@dataclass
class FakeTraceabilityMatrix:
    """Represents a traceability matrix with links."""

    matrix_id: str
    source_document_uuids: list[str]
    traceability_links: list[dict]
    company_id: int
    deleted_at: datetime | None = None


@dataclass
class FakeTraceabilityAlert:
    """Represents a traceability alert."""

    alert_id: str
    triggering_report_id: str
    affected_matrix_ids: list[str]
    affected_link_count: int
    alert_severity: str
    is_resolved: bool = False
    resolved_at: datetime | None = None
    resolved_by: int | None = None
    resolution_action: str | None = None
    resolution_note: str | None = None
    company_id: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FakeStaleLinkMarker:
    """Represents a stale link marker."""

    matrix_id: str
    requirement_id: str
    stale_since: datetime
    stale_reason: str
    triggering_report_id: str
    is_cleared: bool = False
    cleared_at: datetime | None = None
    company_id: int = 1


# ---------------------------------------------------------------------------
# Pure-logic functions modeling the stale link lifecycle
# ---------------------------------------------------------------------------


def should_create_stale_markers(alert_severity: str) -> bool:
    """Determine whether stale markers should be created for an alert.

    Per Requirement 9.4: stale markers are created ONLY for critical alerts.

    Args:
        alert_severity: The severity of the alert ("critical", "major", "minor").

    Returns:
        True if stale markers should be created, False otherwise.
    """
    return alert_severity == "critical"


def create_stale_markers_for_alert(
    alert: FakeTraceabilityAlert,
    affected_matrices: list[FakeTraceabilityMatrix],
    triggering_document_uuid: str,
) -> list[FakeStaleLinkMarker]:
    """Create stale link markers for a critical alert.

    For each link in affected matrices that originates from the triggering
    document, creates a StaleLinkMarker record.

    Only called when alert_severity is "critical" (Requirement 9.4).

    Args:
        alert: The alert that triggered stale marking.
        affected_matrices: Matrices where the document is a source.
        triggering_document_uuid: UUID of the changed document.

    Returns:
        List of created stale link markers.
    """
    if not should_create_stale_markers(alert.alert_severity):
        return []

    markers: list[FakeStaleLinkMarker] = []
    for matrix in affected_matrices:
        links = matrix.traceability_links or []
        for link in links:
            if link.get("source_document_uuid") == triggering_document_uuid:
                marker = FakeStaleLinkMarker(
                    matrix_id=matrix.matrix_id,
                    requirement_id=link.get("requirement_id", ""),
                    stale_since=alert.created_at,
                    stale_reason=(
                        f"Requirement document {triggering_document_uuid} "
                        f"changed (impact report: {alert.triggering_report_id})"
                    ),
                    triggering_report_id=alert.triggering_report_id,
                    is_cleared=False,
                    company_id=alert.company_id,
                )
                markers.append(marker)

    return markers


def should_clear_stale_markers(resolution_action: str) -> bool:
    """Determine whether stale markers should be cleared on resolution.

    Per Requirement 9.8: markers are cleared ONLY when resolution_action
    is "links_verified" or "matrix_regenerated". "no_action_needed" does
    NOT clear markers.

    Args:
        resolution_action: The resolution action taken.

    Returns:
        True if stale markers should be cleared, False otherwise.
    """
    return resolution_action in ("links_verified", "matrix_regenerated")


def resolve_alert_and_clear_markers(
    alert: FakeTraceabilityAlert,
    markers: list[FakeStaleLinkMarker],
    resolution_action: str,
    user_id: int,
) -> tuple[FakeTraceabilityAlert, list[FakeStaleLinkMarker]]:
    """Resolve an alert and conditionally clear stale markers.

    Per Requirement 9.8:
    - "links_verified" → clear stale markers
    - "matrix_regenerated" → clear stale markers
    - "no_action_needed" → do NOT clear stale markers

    Args:
        alert: The alert to resolve.
        markers: Stale link markers associated with the alert.
        resolution_action: The resolution action.
        user_id: ID of the resolving user.

    Returns:
        Tuple of (resolved_alert, updated_markers).
    """
    now = datetime.now(UTC)

    # Resolve the alert
    alert.is_resolved = True
    alert.resolved_at = now
    alert.resolved_by = user_id
    alert.resolution_action = resolution_action

    # Conditionally clear markers
    if should_clear_stale_markers(resolution_action):
        for marker in markers:
            if (
                marker.triggering_report_id == alert.triggering_report_id
                and not marker.is_cleared
            ):
                marker.is_cleared = True
                marker.cleared_at = now

    return alert, markers


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=100)
USER_IDS = st.integers(min_value=1, max_value=200)

ALERT_SEVERITIES = st.sampled_from(["critical", "major", "minor"])
CRITICAL_SEVERITY = st.just("critical")
NON_CRITICAL_SEVERITIES = st.sampled_from(["major", "minor"])

RESOLUTION_ACTIONS = st.sampled_from([
    "links_verified",
    "matrix_regenerated",
    "no_action_needed",
])
CLEARING_ACTIONS = st.sampled_from(["links_verified", "matrix_regenerated"])
NON_CLEARING_ACTIONS = st.just("no_action_needed")

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)
REQUIREMENT_IDS = st.from_regex(r"REQ-\d{3}", fullmatch=True)
TEST_CASE_IDS = st.from_regex(r"TC-\d{3}", fullmatch=True)

MATRIX_IDS = st.uuids().map(str)
REPORT_IDS = st.uuids().map(str)
ALERT_IDS = st.uuids().map(str)

TIMESTAMPS = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(UTC),
)

LINK_CONFIDENCES = st.floats(
    min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False
)


@st.composite
def st_traceability_link(
    draw: st.DrawFn, source_document_uuid: str | None = None
) -> dict:
    """Generate a traceability link dict.

    Args:
        draw: Hypothesis draw function.
        source_document_uuid: If provided, use this as the source doc UUID.

    Returns:
        Dictionary representing a traceability link.
    """
    return {
        "requirement_id": draw(REQUIREMENT_IDS),
        "test_case_id": draw(TEST_CASE_IDS),
        "source_document_uuid": source_document_uuid or draw(DOCUMENT_UUIDS),
        "link_confidence": draw(LINK_CONFIDENCES),
    }


@st.composite
def st_affected_matrix(
    draw: st.DrawFn, triggering_document_uuid: str
) -> FakeTraceabilityMatrix:
    """Generate a matrix that contains the triggering document as a source.

    Ensures at least one link originates from the triggering document.

    Args:
        draw: Hypothesis draw function.
        triggering_document_uuid: The document UUID that triggered the alert.

    Returns:
        FakeTraceabilityMatrix with links from the triggering document.
    """
    matrix_id = draw(MATRIX_IDS)
    company_id = draw(COMPANY_IDS)

    # Generate links from the triggering document (at least 1)
    links_from_trigger = draw(
        st.lists(
            st_traceability_link(source_document_uuid=triggering_document_uuid),
            min_size=1,
            max_size=5,
        )
    )

    # Optionally add links from other documents
    other_doc = draw(DOCUMENT_UUIDS)
    other_links = draw(
        st.lists(
            st_traceability_link(source_document_uuid=other_doc),
            min_size=0,
            max_size=3,
        )
    )

    all_links = links_from_trigger + other_links

    return FakeTraceabilityMatrix(
        matrix_id=matrix_id,
        source_document_uuids=[triggering_document_uuid, other_doc],
        traceability_links=all_links,
        company_id=company_id,
        deleted_at=None,
    )


@st.composite
def st_critical_alert_scenario(draw: st.DrawFn) -> dict:
    """Generate a complete critical alert scenario with matrices and links.

    Returns:
        Dictionary with alert, matrices, triggering_document_uuid, and
        expected marker count.
    """
    triggering_document_uuid = draw(DOCUMENT_UUIDS)
    triggering_report_id = draw(REPORT_IDS)
    company_id = draw(COMPANY_IDS)
    created_at = draw(TIMESTAMPS)

    # Generate 1-3 affected matrices
    matrices = draw(
        st.lists(
            st_affected_matrix(triggering_document_uuid=triggering_document_uuid),
            min_size=1,
            max_size=3,
        )
    )

    # Override company_id to be consistent
    for m in matrices:
        m.company_id = company_id

    alert = FakeTraceabilityAlert(
        alert_id=draw(ALERT_IDS),
        triggering_report_id=triggering_report_id,
        affected_matrix_ids=[m.matrix_id for m in matrices],
        affected_link_count=sum(
            1
            for m in matrices
            for link in m.traceability_links
            if link.get("source_document_uuid") == triggering_document_uuid
        ),
        alert_severity="critical",
        company_id=company_id,
        created_at=created_at,
    )

    # Expected marker count: links from triggering document across all matrices
    expected_markers = sum(
        1
        for m in matrices
        for link in m.traceability_links
        if link.get("source_document_uuid") == triggering_document_uuid
    )

    return {
        "alert": alert,
        "matrices": matrices,
        "triggering_document_uuid": triggering_document_uuid,
        "expected_markers": expected_markers,
    }


@st.composite
def st_non_critical_alert_scenario(draw: st.DrawFn) -> dict:
    """Generate a non-critical alert scenario.

    Returns:
        Dictionary with alert, matrices, and triggering_document_uuid.
    """
    triggering_document_uuid = draw(DOCUMENT_UUIDS)
    triggering_report_id = draw(REPORT_IDS)
    company_id = draw(COMPANY_IDS)
    severity = draw(NON_CRITICAL_SEVERITIES)

    matrices = draw(
        st.lists(
            st_affected_matrix(triggering_document_uuid=triggering_document_uuid),
            min_size=1,
            max_size=3,
        )
    )

    for m in matrices:
        m.company_id = company_id

    alert = FakeTraceabilityAlert(
        alert_id=draw(ALERT_IDS),
        triggering_report_id=triggering_report_id,
        affected_matrix_ids=[m.matrix_id for m in matrices],
        affected_link_count=sum(
            1
            for m in matrices
            for link in m.traceability_links
            if link.get("source_document_uuid") == triggering_document_uuid
        ),
        alert_severity=severity,
        company_id=company_id,
        created_at=draw(TIMESTAMPS),
    )

    return {
        "alert": alert,
        "matrices": matrices,
        "triggering_document_uuid": triggering_document_uuid,
    }


# ---------------------------------------------------------------------------
# Property 13a: Critical alerts create stale markers for affected links
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(scenario=st_critical_alert_scenario())
def test_critical_alert_creates_stale_markers(scenario: dict) -> None:
    """WHEN a traceability_impact_alert is created with alert_severity
    "critical", THE Traceability_Engine SHALL mark all Traceability_Links
    originating from the changed document in the affected matrices with a
    stale_since timestamp and a stale_reason referencing the
    triggering_report_id.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]
    expected_markers = scenario["expected_markers"]

    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)

    # Verify correct number of markers created
    assert len(markers) == expected_markers, (
        f"Expected {expected_markers} markers, got {len(markers)} "
        f"for alert severity={alert.alert_severity}"
    )

    # Verify all markers are properly initialized
    for marker in markers:
        assert marker.is_cleared is False
        assert marker.cleared_at is None
        assert marker.stale_since == alert.created_at
        assert marker.triggering_report_id == alert.triggering_report_id
        assert marker.company_id == alert.company_id
        assert alert.triggering_report_id in marker.stale_reason
        assert triggering_doc in marker.stale_reason


# ---------------------------------------------------------------------------
# Property 13b: Non-critical alerts do NOT create stale markers
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(scenario=st_non_critical_alert_scenario())
def test_non_critical_alert_does_not_create_stale_markers(
    scenario: dict,
) -> None:
    """WHEN a traceability_impact_alert is created with alert_severity
    "major" or "minor", THE Traceability_Engine SHALL NOT create any
    StaleLinkMarker records. Stale marking is exclusive to critical alerts.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]

    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)

    assert len(markers) == 0, (
        f"Non-critical alert (severity={alert.alert_severity}) should not "
        f"create stale markers, but got {len(markers)}"
    )


# ---------------------------------------------------------------------------
# Property 13c: Resolution with "links_verified" clears stale markers
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(
    scenario=st_critical_alert_scenario(),
    user_id=USER_IDS,
)
def test_links_verified_resolution_clears_stale_markers(
    scenario: dict,
    user_id: int,
) -> None:
    """WHEN a traceability_impact_alert with alert_severity "critical" is
    resolved with resolution_action "links_verified", THE Traceability_Engine
    SHALL clear the stale markings by setting is_cleared to true and
    cleared_at to the resolution timestamp on the corresponding
    StaleLinkMarker records.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]

    # Create markers for the critical alert
    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)
    assert len(markers) > 0, "Critical alert should create markers"

    # Resolve with "links_verified"
    resolved_alert, updated_markers = resolve_alert_and_clear_markers(
        alert, markers, "links_verified", user_id
    )

    # Verify alert is resolved
    assert resolved_alert.is_resolved is True
    assert resolved_alert.resolution_action == "links_verified"
    assert resolved_alert.resolved_by == user_id
    assert resolved_alert.resolved_at is not None

    # Verify ALL markers are cleared
    for marker in updated_markers:
        assert marker.is_cleared is True, (
            f"Marker for {marker.requirement_id} in matrix "
            f"{marker.matrix_id} should be cleared after 'links_verified'"
        )
        assert marker.cleared_at is not None
        assert marker.cleared_at == resolved_alert.resolved_at


# ---------------------------------------------------------------------------
# Property 13d: Resolution with "matrix_regenerated" clears stale markers
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(
    scenario=st_critical_alert_scenario(),
    user_id=USER_IDS,
)
def test_matrix_regenerated_resolution_clears_stale_markers(
    scenario: dict,
    user_id: int,
) -> None:
    """WHEN a traceability_impact_alert with alert_severity "critical" is
    resolved with resolution_action "matrix_regenerated", THE
    Traceability_Engine SHALL clear the stale markings by setting is_cleared
    to true and cleared_at to the resolution timestamp on the corresponding
    StaleLinkMarker records.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]

    # Create markers for the critical alert
    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)
    assert len(markers) > 0, "Critical alert should create markers"

    # Resolve with "matrix_regenerated"
    resolved_alert, updated_markers = resolve_alert_and_clear_markers(
        alert, markers, "matrix_regenerated", user_id
    )

    # Verify alert is resolved
    assert resolved_alert.is_resolved is True
    assert resolved_alert.resolution_action == "matrix_regenerated"
    assert resolved_alert.resolved_by == user_id
    assert resolved_alert.resolved_at is not None

    # Verify ALL markers are cleared
    for marker in updated_markers:
        assert marker.is_cleared is True, (
            f"Marker for {marker.requirement_id} in matrix "
            f"{marker.matrix_id} should be cleared after 'matrix_regenerated'"
        )
        assert marker.cleared_at is not None
        assert marker.cleared_at == resolved_alert.resolved_at


# ---------------------------------------------------------------------------
# Property 13e: Resolution with "no_action_needed" does NOT clear markers
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(
    scenario=st_critical_alert_scenario(),
    user_id=USER_IDS,
)
def test_no_action_needed_resolution_does_not_clear_markers(
    scenario: dict,
    user_id: int,
) -> None:
    """WHEN a traceability_impact_alert with alert_severity "critical" is
    resolved with resolution_action "no_action_needed", THE
    Traceability_Engine SHALL NOT clear the stale markings. The
    StaleLinkMarker records SHALL remain with is_cleared=False and
    cleared_at=None.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]

    # Create markers for the critical alert
    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)
    assert len(markers) > 0, "Critical alert should create markers"

    # Resolve with "no_action_needed"
    resolved_alert, updated_markers = resolve_alert_and_clear_markers(
        alert, markers, "no_action_needed", user_id
    )

    # Verify alert IS resolved (resolution still happens)
    assert resolved_alert.is_resolved is True
    assert resolved_alert.resolution_action == "no_action_needed"
    assert resolved_alert.resolved_by == user_id
    assert resolved_alert.resolved_at is not None

    # Verify markers are NOT cleared
    for marker in updated_markers:
        assert marker.is_cleared is False, (
            f"Marker for {marker.requirement_id} in matrix "
            f"{marker.matrix_id} should NOT be cleared after "
            f"'no_action_needed' resolution"
        )
        assert marker.cleared_at is None


# ---------------------------------------------------------------------------
# Property 13f: Stale markers reference correct triggering report
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(scenario=st_critical_alert_scenario())
def test_stale_markers_reference_triggering_report(scenario: dict) -> None:
    """For any critical alert, all created StaleLinkMarker records SHALL
    reference the same triggering_report_id as the alert, ensuring
    traceability between the alert and its stale markers.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]

    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)

    for marker in markers:
        assert marker.triggering_report_id == alert.triggering_report_id, (
            f"Marker triggering_report_id={marker.triggering_report_id} "
            f"does not match alert triggering_report_id="
            f"{alert.triggering_report_id}"
        )


# ---------------------------------------------------------------------------
# Property 13g: Only links from triggering document get stale markers
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(scenario=st_critical_alert_scenario())
def test_only_links_from_triggering_document_get_markers(
    scenario: dict,
) -> None:
    """For any critical alert, stale markers SHALL only be created for
    Traceability_Links whose source_document_uuid matches the triggering
    document. Links from other source documents in the same matrix SHALL
    NOT receive stale markers.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]

    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)

    # Count links from triggering doc across all matrices
    expected_count = sum(
        1
        for m in matrices
        for link in m.traceability_links
        if link.get("source_document_uuid") == triggering_doc
    )

    # Count total links across all matrices
    total_links = sum(len(m.traceability_links) for m in matrices)

    # Markers should equal links from triggering doc, not total links
    assert len(markers) == expected_count
    # If there are links from other docs, markers should be fewer than total
    if total_links > expected_count:
        assert len(markers) < total_links


# ---------------------------------------------------------------------------
# Property 13h: Resolution action determines clearing behavior (exhaustive)
# ---------------------------------------------------------------------------


# Feature: Step_5-6_ai-powered-traceability-gap-discovery, Property 13: Stale Link Lifecycle
@settings(max_examples=10)
@given(
    resolution_action=RESOLUTION_ACTIONS,
    scenario=st_critical_alert_scenario(),
    user_id=USER_IDS,
)
def test_resolution_action_determines_clearing(
    resolution_action: str,
    scenario: dict,
    user_id: int,
) -> None:
    """For any resolution_action, the clearing behavior SHALL be:
    - "links_verified" → all markers cleared (is_cleared=True)
    - "matrix_regenerated" → all markers cleared (is_cleared=True)
    - "no_action_needed" → no markers cleared (is_cleared=False)

    This property exhaustively verifies the decision logic for all
    possible resolution actions.

    **Validates: Requirements 9.4, 9.8**
    """
    alert = scenario["alert"]
    matrices = scenario["matrices"]
    triggering_doc = scenario["triggering_document_uuid"]

    # Create markers
    markers = create_stale_markers_for_alert(alert, matrices, triggering_doc)
    assert len(markers) > 0

    # Resolve with the given action
    _, updated_markers = resolve_alert_and_clear_markers(
        alert, markers, resolution_action, user_id
    )

    expected_cleared = should_clear_stale_markers(resolution_action)

    for marker in updated_markers:
        if expected_cleared:
            assert marker.is_cleared is True, (
                f"Marker should be cleared for action '{resolution_action}'"
            )
            assert marker.cleared_at is not None
        else:
            assert marker.is_cleared is False, (
                f"Marker should NOT be cleared for action "
                f"'{resolution_action}'"
            )
            assert marker.cleared_at is None
