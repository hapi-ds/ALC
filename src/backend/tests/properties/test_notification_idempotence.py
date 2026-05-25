"""Property-based tests for notification idempotence.

Property 14: Notification Idempotence

For any notification acknowledgment operation, calling acknowledge on the same
notification multiple times SHALL produce the same result (HTTP 200 with existing
acknowledgment details). Additionally, for any attempt to create a notification
where an unacknowledged notification already exists for the same
(report_id, affected_document_uuid, target_user_id) tuple, no duplicate SHALL
be created.

**Validates: Requirements 8.3, 8.8**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/impact_notification.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from hypothesis.stateful import Bundle, RuleBasedStateMachine, rule


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=10)
USER_IDS = st.integers(min_value=1, max_value=50)
NOTIFICATION_IDS = st.integers(min_value=1, max_value=10000)

REPORT_IDS = st.from_regex(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

SEVERITIES = st.sampled_from(["critical", "major", "minor", "unknown"])
NOTIFIABLE_SEVERITIES = st.sampled_from(["critical", "major"])

CHANGE_SUMMARIES = st.text(min_size=1, max_size=200)

TIMESTAMPS = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(UTC),
)


# ---------------------------------------------------------------------------
# Data models for pure-logic notification store testing
# ---------------------------------------------------------------------------


@dataclass
class NotificationRecord:
    """Represents an ImpactNotification record in the store."""

    id: int
    report_id: str
    affected_document_uuid: str
    target_user_id: int
    impact_severity: str
    change_summary: str
    is_acknowledged: bool = False
    acknowledged_at: datetime | None = None
    acknowledged_by: int | None = None
    company_id: int = 1


@dataclass
class NotificationStore:
    """In-memory model of the notification store.

    Models the deduplication and idempotent acknowledgment logic
    from ImpactNotificationService without requiring a database.
    """

    notifications: dict[int, NotificationRecord] = field(default_factory=dict)
    _next_id: int = 1

    def create_notification(
        self,
        report_id: str,
        affected_document_uuid: str,
        target_user_id: int,
        impact_severity: str,
        change_summary: str,
        company_id: int,
    ) -> int | None:
        """Create a notification, deduplicating against existing unacknowledged ones.

        Returns the notification ID if created, None if deduplicated (skipped).
        Models Requirement 8.8: no duplicate for same
        (report_id, affected_document_uuid, target_user_id) tuple.
        """
        # Check for existing unacknowledged notification with same key tuple
        for notif in self.notifications.values():
            if (
                notif.report_id == report_id
                and notif.affected_document_uuid == affected_document_uuid
                and notif.target_user_id == target_user_id
                and not notif.is_acknowledged
            ):
                # Duplicate — skip creation (Requirement 8.8)
                return None

        # Create new notification
        notif_id = self._next_id
        self._next_id += 1
        self.notifications[notif_id] = NotificationRecord(
            id=notif_id,
            report_id=report_id,
            affected_document_uuid=affected_document_uuid,
            target_user_id=target_user_id,
            impact_severity=impact_severity,
            change_summary=change_summary,
            company_id=company_id,
        )
        return notif_id

    def acknowledge_notification(
        self,
        notification_id: int,
        user_id: int,
        company_id: int,
    ) -> NotificationRecord | None:
        """Acknowledge a notification (idempotent).

        Returns the notification record if found, None if not found or wrong company.
        Models Requirement 8.3: idempotent acknowledgment.
        """
        notif = self.notifications.get(notification_id)
        if notif is None or notif.company_id != company_id:
            return None

        # Idempotent: only update if not already acknowledged
        if not notif.is_acknowledged:
            notif.is_acknowledged = True
            notif.acknowledged_at = datetime.now(UTC)
            notif.acknowledged_by = user_id

        return notif

    def count_unacknowledged_for_key(
        self,
        report_id: str,
        affected_document_uuid: str,
        target_user_id: int,
    ) -> int:
        """Count unacknowledged notifications for a given deduplication key."""
        return sum(
            1
            for notif in self.notifications.values()
            if notif.report_id == report_id
            and notif.affected_document_uuid == affected_document_uuid
            and notif.target_user_id == target_user_id
            and not notif.is_acknowledged
        )


# ---------------------------------------------------------------------------
# Composite Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_notification_key(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a notification deduplication key tuple."""
    return {
        "report_id": draw(REPORT_IDS),
        "affected_document_uuid": draw(DOCUMENT_UUIDS),
        "target_user_id": draw(USER_IDS),
    }


@st.composite
def st_notification_create_params(draw: st.DrawFn) -> dict[str, Any]:
    """Generate full parameters for creating a notification."""
    return {
        "report_id": draw(REPORT_IDS),
        "affected_document_uuid": draw(DOCUMENT_UUIDS),
        "target_user_id": draw(USER_IDS),
        "impact_severity": draw(NOTIFIABLE_SEVERITIES),
        "change_summary": draw(CHANGE_SUMMARIES),
        "company_id": draw(COMPANY_IDS),
    }


# ---------------------------------------------------------------------------
# Property 14: Acknowledge Idempotence
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    params=st_notification_create_params(),
    ack_user_id=USER_IDS,
    ack_count=st.integers(min_value=2, max_value=10),
)
def test_acknowledge_idempotence_same_result(
    params: dict[str, Any],
    ack_user_id: int,
    ack_count: int,
) -> None:
    """For any notification acknowledgment operation, calling acknowledge on
    the same notification multiple times SHALL produce the same result.

    The notification remains acknowledged with the original timestamp and user.
    Subsequent calls do not modify the record.

    **Validates: Requirements 8.3**
    """
    store = NotificationStore()

    # Create a notification
    notif_id = store.create_notification(**params)
    assert notif_id is not None

    # First acknowledgment
    first_result = store.acknowledge_notification(
        notif_id, ack_user_id, params["company_id"]
    )
    assert first_result is not None
    assert first_result.is_acknowledged is True
    assert first_result.acknowledged_by == ack_user_id
    assert first_result.acknowledged_at is not None

    # Capture state after first acknowledgment
    first_acknowledged_at = first_result.acknowledged_at
    first_acknowledged_by = first_result.acknowledged_by

    # Subsequent acknowledgments (idempotent)
    for _ in range(ack_count - 1):
        result = store.acknowledge_notification(
            notif_id, ack_user_id, params["company_id"]
        )
        assert result is not None
        # Same result every time
        assert result.is_acknowledged is True
        assert result.acknowledged_by == first_acknowledged_by
        assert result.acknowledged_at == first_acknowledged_at


@settings(max_examples=100)
@given(
    params=st_notification_create_params(),
    ack_user_id_1=USER_IDS,
    ack_user_id_2=USER_IDS,
)
def test_acknowledge_idempotence_different_users(
    params: dict[str, Any],
    ack_user_id_1: int,
    ack_user_id_2: int,
) -> None:
    """For any notification already acknowledged by one user, a subsequent
    acknowledge call (even by a different user) SHALL return the same
    acknowledgment details without modification.

    **Validates: Requirements 8.3**
    """
    store = NotificationStore()

    # Create and acknowledge
    notif_id = store.create_notification(**params)
    assert notif_id is not None

    first_result = store.acknowledge_notification(
        notif_id, ack_user_id_1, params["company_id"]
    )
    assert first_result is not None
    assert first_result.is_acknowledged is True

    original_acknowledged_at = first_result.acknowledged_at
    original_acknowledged_by = first_result.acknowledged_by

    # Second acknowledgment by a different user
    second_result = store.acknowledge_notification(
        notif_id, ack_user_id_2, params["company_id"]
    )
    assert second_result is not None
    # Original acknowledgment details preserved (idempotent)
    assert second_result.acknowledged_by == original_acknowledged_by
    assert second_result.acknowledged_at == original_acknowledged_at


# ---------------------------------------------------------------------------
# Property 14: Creation Deduplication
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    params=st_notification_create_params(),
    duplicate_count=st.integers(min_value=2, max_value=10),
)
def test_no_duplicate_notifications_created(
    params: dict[str, Any],
    duplicate_count: int,
) -> None:
    """For any attempt to create a notification where an unacknowledged
    notification already exists for the same (report_id, affected_document_uuid,
    target_user_id) tuple, no duplicate SHALL be created.

    **Validates: Requirements 8.8**
    """
    store = NotificationStore()

    # First creation succeeds
    first_id = store.create_notification(**params)
    assert first_id is not None

    # Subsequent creation attempts with same key are deduplicated
    for _ in range(duplicate_count - 1):
        result = store.create_notification(**params)
        assert result is None  # Skipped — duplicate

    # Only one notification exists for this key
    count = store.count_unacknowledged_for_key(
        params["report_id"],
        params["affected_document_uuid"],
        params["target_user_id"],
    )
    assert count == 1


@settings(max_examples=100)
@given(
    params=st_notification_create_params(),
    ack_user_id=USER_IDS,
)
def test_creation_allowed_after_acknowledgment(
    params: dict[str, Any],
    ack_user_id: int,
) -> None:
    """After a notification is acknowledged, a new notification for the same
    (report_id, affected_document_uuid, target_user_id) tuple SHALL be allowed
    since the deduplication only applies to unacknowledged notifications.

    **Validates: Requirements 8.8**
    """
    store = NotificationStore()

    # Create and acknowledge
    first_id = store.create_notification(**params)
    assert first_id is not None

    store.acknowledge_notification(first_id, ack_user_id, params["company_id"])

    # Now a new creation for the same key should succeed
    # (the existing one is acknowledged, so no unacknowledged duplicate exists)
    second_id = store.create_notification(**params)
    assert second_id is not None
    assert second_id != first_id

    # Two notifications exist total (one acknowledged, one not)
    assert len(store.notifications) == 2


@settings(max_examples=100)
@given(
    key=st_notification_key(),
    severities=st.lists(NOTIFIABLE_SEVERITIES, min_size=2, max_size=5),
    company_id=COMPANY_IDS,
)
def test_deduplication_ignores_severity_differences(
    key: dict[str, Any],
    severities: list[str],
    company_id: int,
) -> None:
    """For any sequence of creation attempts with the same deduplication key
    but different severities, only the first SHALL be created. The deduplication
    is based on (report_id, affected_document_uuid, target_user_id), not severity.

    **Validates: Requirements 8.8**
    """
    store = NotificationStore()

    first_severity = severities[0]
    first_id = store.create_notification(
        report_id=key["report_id"],
        affected_document_uuid=key["affected_document_uuid"],
        target_user_id=key["target_user_id"],
        impact_severity=first_severity,
        change_summary="Initial finding",
        company_id=company_id,
    )
    assert first_id is not None

    # Subsequent attempts with different severities are still deduplicated
    for severity in severities[1:]:
        result = store.create_notification(
            report_id=key["report_id"],
            affected_document_uuid=key["affected_document_uuid"],
            target_user_id=key["target_user_id"],
            impact_severity=severity,
            change_summary="Duplicate attempt",
            company_id=company_id,
        )
        assert result is None

    # Only one notification exists
    count = store.count_unacknowledged_for_key(
        key["report_id"],
        key["affected_document_uuid"],
        key["target_user_id"],
    )
    assert count == 1


@settings(max_examples=100)
@given(
    report_id=REPORT_IDS,
    doc_uuid_1=DOCUMENT_UUIDS,
    doc_uuid_2=DOCUMENT_UUIDS,
    user_id=USER_IDS,
    company_id=COMPANY_IDS,
    severity=NOTIFIABLE_SEVERITIES,
)
def test_different_keys_create_separate_notifications(
    report_id: str,
    doc_uuid_1: str,
    doc_uuid_2: str,
    user_id: int,
    company_id: int,
    severity: str,
) -> None:
    """Notifications with different deduplication keys (different
    affected_document_uuid) SHALL each be created independently.
    Deduplication only applies to the exact same tuple.

    **Validates: Requirements 8.8**
    """
    from hypothesis import assume

    assume(doc_uuid_1 != doc_uuid_2)

    store = NotificationStore()

    id_1 = store.create_notification(
        report_id=report_id,
        affected_document_uuid=doc_uuid_1,
        target_user_id=user_id,
        impact_severity=severity,
        change_summary="Finding for doc 1",
        company_id=company_id,
    )
    id_2 = store.create_notification(
        report_id=report_id,
        affected_document_uuid=doc_uuid_2,
        target_user_id=user_id,
        impact_severity=severity,
        change_summary="Finding for doc 2",
        company_id=company_id,
    )

    # Both should be created (different keys)
    assert id_1 is not None
    assert id_2 is not None
    assert id_1 != id_2
    assert len(store.notifications) == 2


# ---------------------------------------------------------------------------
# Property 14: Combined acknowledge + creation interaction
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    params=st_notification_create_params(),
    ack_user_id=USER_IDS,
    repeat_count=st.integers(min_value=1, max_value=5),
)
def test_acknowledge_then_recreate_cycle_idempotent(
    params: dict[str, Any],
    ack_user_id: int,
    repeat_count: int,
) -> None:
    """For any cycle of create → acknowledge → create, each cycle SHALL
    produce exactly one new unacknowledged notification. The total number
    of notifications equals the number of completed cycles plus one for
    the final unacknowledged notification.

    **Validates: Requirements 8.3, 8.8**
    """
    store = NotificationStore()

    for i in range(repeat_count):
        # Create
        notif_id = store.create_notification(**params)
        assert notif_id is not None

        # Only one unacknowledged at any time
        count = store.count_unacknowledged_for_key(
            params["report_id"],
            params["affected_document_uuid"],
            params["target_user_id"],
        )
        assert count == 1

        # Acknowledge
        result = store.acknowledge_notification(
            notif_id, ack_user_id, params["company_id"]
        )
        assert result is not None
        assert result.is_acknowledged is True

        # Zero unacknowledged after acknowledgment
        count = store.count_unacknowledged_for_key(
            params["report_id"],
            params["affected_document_uuid"],
            params["target_user_id"],
        )
        assert count == 0

    # Total notifications = repeat_count (all acknowledged)
    assert len(store.notifications) == repeat_count


@settings(max_examples=50)
@given(
    params=st_notification_create_params(),
    wrong_company_id=COMPANY_IDS,
)
def test_acknowledge_wrong_company_returns_none(
    params: dict[str, Any],
    wrong_company_id: int,
) -> None:
    """For any acknowledge attempt with a company_id that does not match
    the notification's company_id, the operation SHALL return None (not found).
    The notification remains unacknowledged.

    **Validates: Requirements 8.3**
    """
    from hypothesis import assume

    assume(wrong_company_id != params["company_id"])

    store = NotificationStore()

    notif_id = store.create_notification(**params)
    assert notif_id is not None

    # Attempt acknowledge with wrong company
    result = store.acknowledge_notification(
        notif_id, 1, wrong_company_id
    )
    assert result is None

    # Notification remains unacknowledged
    notif = store.notifications[notif_id]
    assert notif.is_acknowledged is False
    assert notif.acknowledged_at is None
    assert notif.acknowledged_by is None
