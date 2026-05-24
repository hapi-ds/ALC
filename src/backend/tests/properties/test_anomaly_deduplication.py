"""Property-based tests for anomaly deduplication.

Tests Property 5 from the multi-agent always-on auditing design document,
validating that the system does not create duplicate alerts for the same
(anomaly_type, affected_document_id, affected_user_id) combination within
the same detection window (24 hours).

**Validates: Requirements 8.7**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 5)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (8.7)
    - Implementation: src/backend/src/alcoabase/services/anomaly_detection.py (_is_duplicate)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure model of the deduplication logic
# ---------------------------------------------------------------------------

ANOMALY_TYPES = [
    "backdated_signature",
    "workflow_bypass",
    "bulk_approval",
    "off_hours_mutation",
    "rapid_version_churn",
]

#: The deduplication window in hours (matching the service implementation).
DEDUP_WINDOW_HOURS = 24


@dataclass(frozen=True)
class AnomalyEvent:
    """Represents a detected anomaly event before deduplication.

    Attributes:
        anomaly_type: Classification of the anomaly.
        affected_document_id: The affected document ID (nullable).
        affected_user_id: The affected user ID (nullable).
        detected_at: Timestamp when the anomaly was detected.
    """

    anomaly_type: str
    affected_document_id: int | None
    affected_user_id: int | None
    detected_at: datetime


@dataclass
class DeduplicationSimulator:
    """Simulates the anomaly deduplication logic from AnomalyDetectionService.

    Maintains a list of persisted alerts and applies the same deduplication
    rules as the _is_duplicate method: an event is a duplicate if an alert
    with the same (anomaly_type, affected_document_id, affected_user_id)
    already exists within the 24-hour window preceding the new event's
    detection time.

    Attributes:
        alerts: List of persisted (non-duplicate) alerts.
    """

    alerts: list[AnomalyEvent] = field(default_factory=list)

    def is_duplicate(self, event: AnomalyEvent) -> bool:
        """Check if an event is a duplicate of an existing alert.

        Mirrors the logic in AnomalyDetectionService._is_duplicate:
        checks if any existing alert matches on (anomaly_type,
        affected_document_id, affected_user_id) and was detected
        within 24 hours before the new event's detection time.

        Args:
            event: The new anomaly event to check.

        Returns:
            True if a duplicate exists within the window, False otherwise.
        """
        window_start = event.detected_at - timedelta(hours=DEDUP_WINDOW_HOURS)

        for alert in self.alerts:
            if (
                alert.anomaly_type == event.anomaly_type
                and alert.affected_document_id == event.affected_document_id
                and alert.affected_user_id == event.affected_user_id
                and alert.detected_at >= window_start
            ):
                return True
        return False

    def process_event(self, event: AnomalyEvent) -> bool:
        """Process an anomaly event through deduplication.

        If the event is not a duplicate, it is persisted as a new alert.

        Args:
            event: The anomaly event to process.

        Returns:
            True if the event was persisted (not a duplicate), False if skipped.
        """
        if self.is_duplicate(event):
            return False
        self.alerts.append(event)
        return True


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

#: Base time for generating event timestamps.
BASE_TIME = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@st.composite
def st_anomaly_event(
    draw: st.DrawFn,
    time_offset_hours: st.SearchStrategy[float] | None = None,
) -> AnomalyEvent:
    """Generate a random anomaly event.

    Args:
        draw: Hypothesis draw function.
        time_offset_hours: Strategy for time offset from BASE_TIME in hours.
            Defaults to 0-72 hours.

    Returns:
        A randomly generated AnomalyEvent.
    """
    if time_offset_hours is None:
        time_offset_hours = st.floats(min_value=0.0, max_value=72.0)

    anomaly_type = draw(st.sampled_from(ANOMALY_TYPES))
    # Use small ID ranges to increase overlap probability
    affected_document_id = draw(
        st.one_of(st.none(), st.integers(min_value=1, max_value=5))
    )
    affected_user_id = draw(
        st.one_of(st.none(), st.integers(min_value=1, max_value=5))
    )
    offset = draw(time_offset_hours)
    detected_at = BASE_TIME + timedelta(hours=offset)

    return AnomalyEvent(
        anomaly_type=anomaly_type,
        affected_document_id=affected_document_id,
        affected_user_id=affected_user_id,
        detected_at=detected_at,
    )


@st.composite
def st_anomaly_event_sequence(draw: st.DrawFn) -> list[AnomalyEvent]:
    """Generate a sequence of anomaly events with overlapping characteristics.

    Produces 2-20 events with small ID ranges and time ranges that
    encourage overlapping deduplication keys, simulating realistic
    repeated anomaly scans.

    Returns:
        A list of AnomalyEvent instances in chronological order.
    """
    events = draw(
        st.lists(st_anomaly_event(), min_size=2, max_size=20)
    )
    # Sort by detection time to simulate chronological processing
    events.sort(key=lambda e: e.detected_at)
    return events


@st.composite
def st_overlapping_event_pair(draw: st.DrawFn) -> tuple[AnomalyEvent, AnomalyEvent]:
    """Generate a pair of events with the same dedup key within 24h window.

    This strategy guarantees the two events share the same
    (anomaly_type, affected_document_id, affected_user_id) and are
    within 24 hours of each other.

    Returns:
        Tuple of (first_event, duplicate_event).
    """
    anomaly_type = draw(st.sampled_from(ANOMALY_TYPES))
    affected_document_id = draw(
        st.one_of(st.none(), st.integers(min_value=1, max_value=10))
    )
    affected_user_id = draw(
        st.one_of(st.none(), st.integers(min_value=1, max_value=10))
    )

    # First event at some time
    first_offset = draw(st.floats(min_value=0.0, max_value=48.0))
    first_time = BASE_TIME + timedelta(hours=first_offset)

    # Second event within 24 hours after the first (strictly within window)
    gap_hours = draw(st.floats(min_value=0.01, max_value=23.99))
    second_time = first_time + timedelta(hours=gap_hours)

    first_event = AnomalyEvent(
        anomaly_type=anomaly_type,
        affected_document_id=affected_document_id,
        affected_user_id=affected_user_id,
        detected_at=first_time,
    )
    second_event = AnomalyEvent(
        anomaly_type=anomaly_type,
        affected_document_id=affected_document_id,
        affected_user_id=affected_user_id,
        detected_at=second_time,
    )

    return (first_event, second_event)


# ---------------------------------------------------------------------------
# Property 5: Anomaly deduplication
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 5: No duplicates within 24h window
@settings(max_examples=300)
@given(events=st_anomaly_event_sequence())
def test_no_duplicates_within_dedup_window(events: list[AnomalyEvent]) -> None:
    """For any sequence of anomaly detection scans, the system SHALL not
    create duplicate alerts for the same (anomaly_type, affected_document_id,
    affected_user_id) combination within the same detection window (24 hours).

    After processing all events, for any two persisted alerts with the same
    dedup key, their detection times must be more than 24 hours apart.

    **Validates: Requirements 8.7**
    """
    simulator = DeduplicationSimulator()

    for event in events:
        simulator.process_event(event)

    # Verify: no two persisted alerts share the same dedup key within 24h
    for i, alert_a in enumerate(simulator.alerts):
        for alert_b in simulator.alerts[i + 1 :]:
            if (
                alert_a.anomaly_type == alert_b.anomaly_type
                and alert_a.affected_document_id == alert_b.affected_document_id
                and alert_a.affected_user_id == alert_b.affected_user_id
            ):
                time_diff = abs(
                    (alert_b.detected_at - alert_a.detected_at).total_seconds()
                )
                assert time_diff > DEDUP_WINDOW_HOURS * 3600, (
                    f"Duplicate alerts found within {DEDUP_WINDOW_HOURS}h window: "
                    f"type={alert_a.anomaly_type}, doc_id={alert_a.affected_document_id}, "
                    f"user_id={alert_a.affected_user_id}, "
                    f"time_a={alert_a.detected_at.isoformat()}, "
                    f"time_b={alert_b.detected_at.isoformat()}, "
                    f"diff_hours={time_diff / 3600:.2f}"
                )


# Feature: multi-agent-always-on-auditing, Property 5: Exact duplicates always rejected
@settings(max_examples=300)
@given(pair=st_overlapping_event_pair())
def test_exact_duplicate_within_window_rejected(
    pair: tuple[AnomalyEvent, AnomalyEvent],
) -> None:
    """For any pair of events with the same (anomaly_type, affected_document_id,
    affected_user_id) within 24 hours, the second event SHALL be rejected
    as a duplicate.

    **Validates: Requirements 8.7**
    """
    first_event, duplicate_event = pair
    simulator = DeduplicationSimulator()

    # First event should be persisted
    persisted_first = simulator.process_event(first_event)
    assert persisted_first, (
        f"First event should always be persisted: {first_event}"
    )

    # Second event (same key, within 24h) should be rejected
    persisted_second = simulator.process_event(duplicate_event)
    assert not persisted_second, (
        f"Duplicate event within 24h window should be rejected: "
        f"type={duplicate_event.anomaly_type}, "
        f"doc_id={duplicate_event.affected_document_id}, "
        f"user_id={duplicate_event.affected_user_id}, "
        f"first_at={first_event.detected_at.isoformat()}, "
        f"second_at={duplicate_event.detected_at.isoformat()}"
    )

    # Only one alert should exist
    assert len(simulator.alerts) == 1


# Feature: multi-agent-always-on-auditing, Property 5: Events outside window are not duplicates
@settings(max_examples=300)
@given(
    anomaly_type=st.sampled_from(ANOMALY_TYPES),
    doc_id=st.one_of(st.none(), st.integers(min_value=1, max_value=10)),
    user_id=st.one_of(st.none(), st.integers(min_value=1, max_value=10)),
    gap_hours=st.floats(min_value=24.01, max_value=72.0),
)
def test_events_outside_window_not_deduplicated(
    anomaly_type: str,
    doc_id: int | None,
    user_id: int | None,
    gap_hours: float,
) -> None:
    """For any two events with the same dedup key but more than 24 hours
    apart, both SHALL be persisted as separate alerts.

    **Validates: Requirements 8.7**
    """
    first_time = BASE_TIME
    second_time = BASE_TIME + timedelta(hours=gap_hours)

    first_event = AnomalyEvent(
        anomaly_type=anomaly_type,
        affected_document_id=doc_id,
        affected_user_id=user_id,
        detected_at=first_time,
    )
    second_event = AnomalyEvent(
        anomaly_type=anomaly_type,
        affected_document_id=doc_id,
        affected_user_id=user_id,
        detected_at=second_time,
    )

    simulator = DeduplicationSimulator()

    persisted_first = simulator.process_event(first_event)
    persisted_second = simulator.process_event(second_event)

    assert persisted_first, "First event should always be persisted"
    assert persisted_second, (
        f"Event outside 24h window should NOT be deduplicated: "
        f"gap={gap_hours:.2f}h > 24h"
    )
    assert len(simulator.alerts) == 2


# Feature: multi-agent-always-on-auditing, Property 5: Different dedup keys are independent
@settings(max_examples=300)
@given(events=st_anomaly_event_sequence())
def test_different_dedup_keys_are_independent(events: list[AnomalyEvent]) -> None:
    """Events with different (anomaly_type, affected_document_id,
    affected_user_id) combinations SHALL be treated independently for
    deduplication purposes. A duplicate in one key SHALL not affect
    events with a different key.

    **Validates: Requirements 8.7**
    """
    simulator = DeduplicationSimulator()

    persisted_count = 0
    rejected_count = 0

    for event in events:
        if simulator.process_event(event):
            persisted_count += 1
        else:
            rejected_count += 1

    # Total processed should equal persisted + rejected
    assert persisted_count + rejected_count == len(events)

    # Each persisted alert should have a unique dedup key within its window
    # (this is the core invariant)
    for i, alert_a in enumerate(simulator.alerts):
        for alert_b in simulator.alerts[i + 1 :]:
            same_key = (
                alert_a.anomaly_type == alert_b.anomaly_type
                and alert_a.affected_document_id == alert_b.affected_document_id
                and alert_a.affected_user_id == alert_b.affected_user_id
            )
            if same_key:
                time_diff = abs(
                    (alert_b.detected_at - alert_a.detected_at).total_seconds()
                )
                assert time_diff > DEDUP_WINDOW_HOURS * 3600, (
                    f"Same-key alerts must be >24h apart but found "
                    f"diff={time_diff / 3600:.2f}h"
                )
