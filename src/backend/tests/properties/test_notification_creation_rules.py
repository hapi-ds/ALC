"""Property-based tests for notification creation rules in ImpactNotificationService.

Property 13: Notification Creation Rules

For any completed impact analysis with affected items, notifications SHALL be
created only for items with impact_severity "critical" or "major". No
notifications SHALL be created for "minor" or "unknown" severity items.

**Validates: Requirements 8.1**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/impact_notification.py
"""

from __future__ import annotations

import uuid

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.impact_notification import _NOTIFIABLE_SEVERITIES


# ---------------------------------------------------------------------------
# Pure logic under test: notification eligibility filtering
# ---------------------------------------------------------------------------

# All valid severity values as defined in the schema
ALL_SEVERITIES = ["critical", "major", "minor", "unknown"]

# Severities that should trigger notifications
NOTIFIABLE = {"critical", "major"}

# Severities that should NOT trigger notifications
NON_NOTIFIABLE = {"minor", "unknown"}


def should_create_notification(item: dict) -> bool:
    """Determine if an affected item should trigger a notification.

    This mirrors the filtering logic in
    ImpactNotificationService.create_notifications:
    - Only items with impact_severity in _NOTIFIABLE_SEVERITIES get notifications
    - Items must also have an affected_document_uuid (non-None)

    Args:
        item: An affected item dict with at least "impact_severity" and
              "affected_document_uuid" keys.

    Returns:
        True if the item should create a notification, False otherwise.
    """
    severity = item.get("impact_severity")
    affected_doc_uuid = item.get("affected_document_uuid")

    if severity not in _NOTIFIABLE_SEVERITIES:
        return False

    if not affected_doc_uuid:
        return False

    return True


def filter_notifiable_items(affected_items: list[dict]) -> list[dict]:
    """Filter affected items to only those that should create notifications.

    This is the pure-logic equivalent of the filtering performed in
    ImpactNotificationService.create_notifications before any DB operations.

    Args:
        affected_items: List of affected item dicts from an impact report.

    Returns:
        Subset of items that would trigger notification creation.
    """
    return [item for item in affected_items if should_create_notification(item)]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_document_uuid() -> st.SearchStrategy[str]:
    """Generate a valid 12-character document UUID."""
    return st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=12,
        max_size=12,
    )


def st_severity() -> st.SearchStrategy[str]:
    """Generate a random severity from all valid values."""
    return st.sampled_from(ALL_SEVERITIES)


def st_notifiable_severity() -> st.SearchStrategy[str]:
    """Generate a severity that should trigger notifications."""
    return st.sampled_from(["critical", "major"])


def st_non_notifiable_severity() -> st.SearchStrategy[str]:
    """Generate a severity that should NOT trigger notifications."""
    return st.sampled_from(["minor", "unknown"])


@st.composite
def st_affected_item(
    draw: st.DrawFn,
    severity: st.SearchStrategy[str] | None = None,
    has_document_uuid: bool = True,
) -> dict:
    """Generate an affected item dict with configurable severity.

    Args:
        draw: Hypothesis draw function.
        severity: Strategy for severity value. Defaults to any valid severity.
        has_document_uuid: Whether to include a document UUID.

    Returns:
        A dict matching the AffectedItemSchema structure.
    """
    if severity is None:
        severity = st_severity()

    sev = draw(severity)
    doc_uuid = draw(st_document_uuid()) if has_document_uuid else None

    return {
        "affected_document_uuid": doc_uuid,
        "training_task_id": draw(st.one_of(st.none(), st.integers(min_value=1, max_value=10000))),
        "affected_document_title": draw(st.text(min_size=1, max_size=50)),
        "dependency_type": draw(
            st.sampled_from(["validates", "references", "implements", "trains_on", "derived_from"])
        ),
        "impact_severity": sev,
        "affected_sections": draw(st.lists(st.text(min_size=1, max_size=30), min_size=0, max_size=5)),
        "change_summary": draw(st.text(min_size=1, max_size=100)),
        "recommended_action": draw(
            st.sampled_from(
                ["update_required", "review_recommended", "retraining_required", "manual_review_required"]
            )
        ),
        "inference_prompt_summary": draw(st.text(min_size=1, max_size=50)),
        "model_response_summary": draw(st.text(min_size=1, max_size=50)),
        "token_count": draw(st.integers(min_value=1, max_value=5000)),
    }


@st.composite
def st_affected_items_list(draw: st.DrawFn) -> list[dict]:
    """Generate a list of affected items with random severities."""
    return draw(st.lists(st_affected_item(), min_size=1, max_size=20))


# ---------------------------------------------------------------------------
# Property 13: Only critical/major items create notifications
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(items=st.lists(st_affected_item(), min_size=1, max_size=30))
def test_only_critical_and_major_create_notifications(items: list[dict]) -> None:
    """For any list of affected items with random severities, notifications
    SHALL be created only for items with impact_severity "critical" or "major".

    **Validates: Requirements 8.1**
    """
    notifiable = filter_notifiable_items(items)

    for item in notifiable:
        assert item["impact_severity"] in NOTIFIABLE, (
            f"Non-notifiable severity {item['impact_severity']!r} passed filter"
        )


@settings(max_examples=100)
@given(items=st.lists(st_affected_item(severity=st_non_notifiable_severity()), min_size=1, max_size=20))
def test_minor_and_unknown_never_create_notifications(items: list[dict]) -> None:
    """For any list of affected items where all severities are "minor" or
    "unknown", no notifications SHALL be created.

    **Validates: Requirements 8.1**
    """
    notifiable = filter_notifiable_items(items)
    assert len(notifiable) == 0, (
        f"Expected 0 notifications for non-notifiable items, got {len(notifiable)}"
    )


@settings(max_examples=100)
@given(items=st.lists(st_affected_item(severity=st_notifiable_severity()), min_size=1, max_size=20))
def test_all_critical_major_items_create_notifications(items: list[dict]) -> None:
    """For any list of affected items where all severities are "critical" or
    "major" (and have document UUIDs), all items SHALL create notifications.

    **Validates: Requirements 8.1**
    """
    notifiable = filter_notifiable_items(items)
    assert len(notifiable) == len(items), (
        f"Expected {len(items)} notifications, got {len(notifiable)}"
    )


# ---------------------------------------------------------------------------
# Property 13: Notification count matches critical/major count
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(items=st.lists(st_affected_item(), min_size=1, max_size=30))
def test_notification_count_equals_critical_major_with_doc_uuid(items: list[dict]) -> None:
    """The number of notifications created SHALL equal the number of items
    with severity "critical" or "major" that also have an affected_document_uuid.

    **Validates: Requirements 8.1**
    """
    notifiable = filter_notifiable_items(items)

    expected_count = sum(
        1
        for item in items
        if item.get("impact_severity") in NOTIFIABLE and item.get("affected_document_uuid")
    )

    assert len(notifiable) == expected_count


# ---------------------------------------------------------------------------
# Property 13: Items without document UUID never create notifications
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    items=st.lists(
        st_affected_item(severity=st_notifiable_severity(), has_document_uuid=False),
        min_size=1,
        max_size=10,
    )
)
def test_items_without_document_uuid_never_create_notifications(items: list[dict]) -> None:
    """Even with critical/major severity, items without an
    affected_document_uuid SHALL NOT create notifications (these are
    training-task-only items without a document target).

    **Validates: Requirements 8.1**
    """
    notifiable = filter_notifiable_items(items)
    assert len(notifiable) == 0


# ---------------------------------------------------------------------------
# Property 13: _NOTIFIABLE_SEVERITIES matches expected set
# ---------------------------------------------------------------------------


def test_notifiable_severities_constant_matches_spec() -> None:
    """The _NOTIFIABLE_SEVERITIES constant SHALL contain exactly
    "critical" and "major" as defined in the design document.

    **Validates: Requirements 8.1**
    """
    assert _NOTIFIABLE_SEVERITIES == frozenset({"critical", "major"})


# ---------------------------------------------------------------------------
# Property 13: Filtering is partition-preserving
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(items=st.lists(st_affected_item(), min_size=0, max_size=30))
def test_filtering_partitions_items_correctly(items: list[dict]) -> None:
    """For any list of affected items, the filtered (notifiable) set and
    the excluded set SHALL form a complete partition of the original list.
    Every item is either notifiable or excluded, never both, never lost.

    **Validates: Requirements 8.1**
    """
    notifiable = filter_notifiable_items(items)
    excluded = [item for item in items if not should_create_notification(item)]

    assert len(notifiable) + len(excluded) == len(items)
