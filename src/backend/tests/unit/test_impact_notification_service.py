"""Unit tests for ImpactNotificationService.

Tests notification creation, deduplication, acknowledgment, training reset,
and document status computation.

References:
    - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.impact_analysis import ImpactNotification, ImpactReport
from alcoabase.models.training import TrainingTask
from alcoabase.schemas.impact_analysis import PaginationParams
from alcoabase.services.impact_notification import ImpactNotificationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_affected_item(
    severity: str = "critical",
    doc_uuid: str = "2025-00001",
    action: str = "update_required",
    training_task_id: int | None = None,
    change_summary: str = "Section 3.1 contradicts updated requirements",
) -> dict:
    """Create an affected item dict for testing."""
    return {
        "affected_document_uuid": doc_uuid,
        "affected_document_title": "Test Document",
        "dependency_type": "validates",
        "impact_severity": severity,
        "affected_sections": ["Section 3.1"],
        "change_summary": change_summary,
        "recommended_action": action,
        "inference_prompt_summary": "prompt",
        "model_response_summary": "response",
        "token_count": 100,
        "training_task_id": training_task_id,
    }


def _make_notification(
    id: int = 1,
    report_id: str = "rpt-001",
    doc_uuid: str = "2025-00001",
    severity: str = "critical",
    user_id: int = 10,
    company_id: int = 1,
    is_acknowledged: bool = False,
    acknowledged_at: datetime | None = None,
    acknowledged_by: int | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock ImpactNotification instance."""
    notif = MagicMock(spec=ImpactNotification)
    notif.id = id
    notif.report_id = report_id
    notif.affected_document_uuid = doc_uuid
    notif.notification_type = "change_impact"
    notif.impact_severity = severity
    notif.change_summary = "Test change summary"
    notif.target_user_id = user_id
    notif.is_acknowledged = is_acknowledged
    notif.acknowledged_at = acknowledged_at
    notif.acknowledged_by = acknowledged_by
    notif.company_id = company_id
    notif.created_at = created_at or datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
    return notif


def _mock_scalar_result(value):
    """Create a mock execute result that returns a scalar value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    return result


def _mock_scalars_result(values: list):
    """Create a mock execute result that returns scalars."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = values
    result.scalars.return_value = scalars_mock
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> ImpactNotificationService:
    """Create an ImpactNotificationService instance."""
    return ImpactNotificationService()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests: create_notifications
# ---------------------------------------------------------------------------


class TestCreateNotifications:
    """Tests for ImpactNotificationService.create_notifications."""

    @pytest.mark.asyncio
    async def test_creates_notifications_for_critical_and_major(
        self, service, mock_session
    ):
        """Only creates notifications for critical and major severity items."""
        items = [
            _make_affected_item(severity="critical", doc_uuid="2025-00001"),
            _make_affected_item(severity="major", doc_uuid="2025-00002"),
            _make_affected_item(severity="minor", doc_uuid="2025-00003"),
            _make_affected_item(severity="unknown", doc_uuid="2025-00004"),
        ]

        # Mock: Document.created_by lookup returns user_id=10
        doc_owner_result = _mock_scalar_result(10)
        # Mock: no existing unacknowledged notification
        no_existing_result = _mock_scalar_result(None)

        # For critical: doc lookup, dedup check
        # For major: doc lookup, dedup check
        # minor and unknown are skipped before any DB calls
        mock_session.execute = AsyncMock(
            side_effect=[
                doc_owner_result,  # critical: doc owner lookup
                no_existing_result,  # critical: dedup check
                doc_owner_result,  # major: doc owner lookup
                no_existing_result,  # major: dedup check
            ]
        )

        # Mock flush to assign IDs
        call_count = [0]

        async def mock_flush():
            call_count[0] += 1
            # Simulate ID assignment on the last added notification
            for call in mock_session.add.call_args_list:
                notif = call[0][0]
                if not hasattr(notif, "_id_assigned"):
                    notif.id = call_count[0]
                    notif._id_assigned = True

        mock_session.flush = mock_flush

        result = await service.create_notifications(
            session=mock_session,
            report_id="rpt-001",
            affected_items=items,
            company_id=1,
        )

        # Only critical and major should create notifications
        assert len(result) == 2
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_minor_and_unknown_severity(self, service, mock_session):
        """Minor and unknown severity items do not create notifications."""
        items = [
            _make_affected_item(severity="minor", doc_uuid="2025-00001"),
            _make_affected_item(severity="unknown", doc_uuid="2025-00002"),
        ]

        result = await service.create_notifications(
            session=mock_session,
            report_id="rpt-001",
            affected_items=items,
            company_id=1,
        )

        assert result == []
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicates_against_existing_unacknowledged(
        self, service, mock_session
    ):
        """Skips creating notification if unacknowledged one already exists."""
        items = [
            _make_affected_item(severity="critical", doc_uuid="2025-00001"),
        ]

        # Mock: doc owner lookup returns user_id=10
        doc_owner_result = _mock_scalar_result(10)
        # Mock: existing unacknowledged notification found (returns an ID)
        existing_result = _mock_scalar_result(42)

        mock_session.execute = AsyncMock(
            side_effect=[doc_owner_result, existing_result]
        )

        result = await service.create_notifications(
            session=mock_session,
            report_id="rpt-001",
            affected_items=items,
            company_id=1,
        )

        assert result == []
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_targets_document_owner(self, service, mock_session):
        """Notification targets the document owner (Document.created_by)."""
        items = [
            _make_affected_item(severity="critical", doc_uuid="2025-00001"),
        ]

        # Mock: doc owner is user 42
        doc_owner_result = _mock_scalar_result(42)
        no_existing_result = _mock_scalar_result(None)

        mock_session.execute = AsyncMock(
            side_effect=[doc_owner_result, no_existing_result]
        )

        # Track what gets added
        async def mock_flush():
            for call in mock_session.add.call_args_list:
                notif = call[0][0]
                if not hasattr(notif, "_id_assigned"):
                    notif.id = 1
                    notif._id_assigned = True

        mock_session.flush = mock_flush

        await service.create_notifications(
            session=mock_session,
            report_id="rpt-001",
            affected_items=items,
            company_id=1,
        )

        # Verify the notification targets user 42
        added_notif = mock_session.add.call_args[0][0]
        assert added_notif.target_user_id == 42

    @pytest.mark.asyncio
    async def test_skips_when_document_not_found(self, service, mock_session):
        """Skips notification when document is not found in company scope."""
        items = [
            _make_affected_item(severity="critical", doc_uuid="2025-99999"),
        ]

        # Mock: document not found (created_by returns None)
        doc_not_found_result = _mock_scalar_result(None)

        mock_session.execute = AsyncMock(side_effect=[doc_not_found_result])

        result = await service.create_notifications(
            session=mock_session,
            report_id="rpt-001",
            affected_items=items,
            company_id=1,
        )

        assert result == []
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_items_without_document_uuid(self, service, mock_session):
        """Items without affected_document_uuid (e.g., training tasks) are skipped."""
        items = [
            {
                "affected_document_uuid": None,
                "impact_severity": "critical",
                "training_task_id": 5,
                "change_summary": "Training invalidated",
                "recommended_action": "retraining_required",
            },
        ]

        result = await service.create_notifications(
            session=mock_session,
            report_id="rpt-001",
            affected_items=items,
            company_id=1,
        )

        assert result == []
        mock_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: acknowledge_notification
# ---------------------------------------------------------------------------


class TestAcknowledgeNotification:
    """Tests for ImpactNotificationService.acknowledge_notification."""

    @pytest.mark.asyncio
    async def test_marks_notification_as_acknowledged(self, service, mock_session):
        """Acknowledging sets is_acknowledged=True and records user/timestamp."""
        notif = _make_notification(id=1, is_acknowledged=False)

        result_mock = _mock_scalar_result(notif)
        mock_session.execute = AsyncMock(return_value=result_mock)

        response = await service.acknowledge_notification(
            session=mock_session,
            notification_id=1,
            user_id=5,
            company_id=1,
        )

        assert response is not None
        assert notif.is_acknowledged is True
        assert notif.acknowledged_by == 5
        assert notif.acknowledged_at is not None

    @pytest.mark.asyncio
    async def test_idempotent_acknowledge(self, service, mock_session):
        """Calling acknowledge twice returns same result without modification."""
        ack_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        notif = _make_notification(
            id=1,
            is_acknowledged=True,
            acknowledged_at=ack_time,
            acknowledged_by=5,
        )

        result_mock = _mock_scalar_result(notif)
        mock_session.execute = AsyncMock(return_value=result_mock)

        response = await service.acknowledge_notification(
            session=mock_session,
            notification_id=1,
            user_id=5,
            company_id=1,
        )

        assert response is not None
        # Should not modify the already-acknowledged notification
        assert notif.acknowledged_at == ack_time
        assert notif.acknowledged_by == 5

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_company(self, service, mock_session):
        """Returns None when notification not found or wrong company."""
        result_mock = _mock_scalar_result(None)
        mock_session.execute = AsyncMock(return_value=result_mock)

        response = await service.acknowledge_notification(
            session=mock_session,
            notification_id=999,
            user_id=5,
            company_id=1,
        )

        assert response is None

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_notification(
        self, service, mock_session
    ):
        """Returns None when notification ID does not exist."""
        result_mock = _mock_scalar_result(None)
        mock_session.execute = AsyncMock(return_value=result_mock)

        response = await service.acknowledge_notification(
            session=mock_session,
            notification_id=12345,
            user_id=5,
            company_id=1,
        )

        assert response is None


# ---------------------------------------------------------------------------
# Tests: get_unacknowledged
# ---------------------------------------------------------------------------


class TestGetUnacknowledged:
    """Tests for ImpactNotificationService.get_unacknowledged."""

    @pytest.mark.asyncio
    async def test_returns_sorted_by_severity_then_date(
        self, service, mock_session
    ):
        """Results are sorted by severity (critical first) then date (newest first)."""
        notif_critical = _make_notification(
            id=1,
            severity="critical",
            created_at=datetime(2025, 1, 10, tzinfo=UTC),
        )
        notif_major = _make_notification(
            id=2,
            severity="major",
            created_at=datetime(2025, 1, 15, tzinfo=UTC),
        )

        # Mock: count query returns 2
        count_result = _mock_scalar_result(2)
        # Mock: notifications query returns sorted list
        notifs_result = _mock_scalars_result([notif_critical, notif_major])

        mock_session.execute = AsyncMock(
            side_effect=[count_result, notifs_result]
        )

        result = await service.get_unacknowledged(
            session=mock_session,
            user_id=10,
            company_id=1,
        )

        assert result["total_count"] == 2
        assert len(result["notifications"]) == 2

    @pytest.mark.asyncio
    async def test_respects_pagination(self, service, mock_session):
        """Pagination limits and offsets are applied."""
        notif = _make_notification(id=1, severity="critical")

        count_result = _mock_scalar_result(5)
        notifs_result = _mock_scalars_result([notif])

        mock_session.execute = AsyncMock(
            side_effect=[count_result, notifs_result]
        )

        pagination = PaginationParams(limit=1, offset=2)
        result = await service.get_unacknowledged(
            session=mock_session,
            user_id=10,
            company_id=1,
            pagination=pagination,
        )

        assert result["total_count"] == 5
        assert len(result["notifications"]) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_notifications(
        self, service, mock_session
    ):
        """Returns empty list and zero count when no unacknowledged notifications."""
        count_result = _mock_scalar_result(0)
        notifs_result = _mock_scalars_result([])

        mock_session.execute = AsyncMock(
            side_effect=[count_result, notifs_result]
        )

        result = await service.get_unacknowledged(
            session=mock_session,
            user_id=10,
            company_id=1,
        )

        assert result["total_count"] == 0
        assert result["notifications"] == []

    @pytest.mark.asyncio
    async def test_uses_default_pagination_when_none(self, service, mock_session):
        """Uses default PaginationParams when none provided."""
        count_result = _mock_scalar_result(0)
        notifs_result = _mock_scalars_result([])

        mock_session.execute = AsyncMock(
            side_effect=[count_result, notifs_result]
        )

        result = await service.get_unacknowledged(
            session=mock_session,
            user_id=10,
            company_id=1,
            pagination=None,
        )

        assert result["total_count"] == 0
        assert result["notifications"] == []


# ---------------------------------------------------------------------------
# Tests: reset_training_tasks
# ---------------------------------------------------------------------------


class TestResetTrainingTasks:
    """Tests for ImpactNotificationService.reset_training_tasks."""

    @pytest.mark.asyncio
    async def test_resets_completed_training_task_by_id(
        self, service, mock_session
    ):
        """Sets is_completed=false for a completed training task by ID."""
        items = [
            _make_affected_item(
                severity="critical",
                action="retraining_required",
                training_task_id=10,
            ),
        ]

        # Mock: TrainingTask found and is_completed=True
        task = MagicMock(spec=TrainingTask)
        task.id = 10
        task.is_completed = True
        task.completed_at = datetime(2025, 1, 10, tzinfo=UTC)

        task_result = _mock_scalar_result(task)
        mock_session.execute = AsyncMock(return_value=task_result)

        result = await service.reset_training_tasks(
            session=mock_session,
            affected_items=items,
            report_id="rpt-001",
        )

        assert result["reset_count"] == 1
        assert result["failures"] == []
        assert task.is_completed is False
        assert task.completed_at is None

    @pytest.mark.asyncio
    async def test_idempotent_reset_already_incomplete(
        self, service, mock_session
    ):
        """If is_completed is already False, no update occurs (idempotent)."""
        items = [
            _make_affected_item(
                severity="critical",
                action="retraining_required",
                training_task_id=10,
            ),
        ]

        # Mock: TrainingTask found but already incomplete
        task = MagicMock(spec=TrainingTask)
        task.id = 10
        task.is_completed = False
        task.completed_at = None

        task_result = _mock_scalar_result(task)
        mock_session.execute = AsyncMock(return_value=task_result)

        result = await service.reset_training_tasks(
            session=mock_session,
            affected_items=items,
            report_id="rpt-001",
        )

        # Still counts as "reset" (idempotent success)
        assert result["reset_count"] == 1
        assert result["failures"] == []
        # Should remain False
        assert task.is_completed is False

    @pytest.mark.asyncio
    async def test_records_failure_when_task_not_found(
        self, service, mock_session
    ):
        """Records failure when training task ID is not found."""
        items = [
            _make_affected_item(
                severity="critical",
                action="retraining_required",
                training_task_id=999,
            ),
        ]

        # Mock: TrainingTask not found
        task_result = _mock_scalar_result(None)
        mock_session.execute = AsyncMock(return_value=task_result)

        result = await service.reset_training_tasks(
            session=mock_session,
            affected_items=items,
            report_id="rpt-001",
        )

        assert result["reset_count"] == 0
        assert len(result["failures"]) == 1
        assert result["failures"][0]["training_task_id"] == 999
        assert "not found" in result["failures"][0]["reason"]

    @pytest.mark.asyncio
    async def test_resets_tasks_by_document_uuid(self, service, mock_session):
        """Resets all completed training tasks for a document UUID."""
        items = [
            {
                "affected_document_uuid": "2025-00001",
                "impact_severity": "critical",
                "recommended_action": "retraining_required",
                "training_task_id": None,
                "change_summary": "Procedural change",
            },
        ]

        # Mock: find completed tasks for the document
        task1 = MagicMock(spec=TrainingTask)
        task1.id = 1
        task1.is_completed = True
        task1.completed_at = datetime(2025, 1, 5, tzinfo=UTC)

        task2 = MagicMock(spec=TrainingTask)
        task2.id = 2
        task2.is_completed = True
        task2.completed_at = datetime(2025, 1, 8, tzinfo=UTC)

        tasks_result = _mock_scalars_result([task1, task2])
        mock_session.execute = AsyncMock(return_value=tasks_result)

        result = await service.reset_training_tasks(
            session=mock_session,
            affected_items=items,
            report_id="rpt-001",
        )

        assert result["reset_count"] == 2
        assert result["failures"] == []
        assert task1.is_completed is False
        assert task1.completed_at is None
        assert task2.is_completed is False
        assert task2.completed_at is None

    @pytest.mark.asyncio
    async def test_skips_non_retraining_items(self, service, mock_session):
        """Items without recommended_action 'retraining_required' are skipped."""
        items = [
            _make_affected_item(severity="critical", action="update_required"),
            _make_affected_item(severity="major", action="review_recommended"),
        ]

        result = await service.reset_training_tasks(
            session=mock_session,
            affected_items=items,
            report_id="rpt-001",
        )

        assert result["reset_count"] == 0
        assert result["failures"] == []
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_records_database_error_as_failure(
        self, service, mock_session
    ):
        """Database errors are recorded as failures without crashing."""
        items = [
            _make_affected_item(
                severity="critical",
                action="retraining_required",
                training_task_id=10,
            ),
        ]

        # Mock: database error on execute
        mock_session.execute = AsyncMock(
            side_effect=RuntimeError("Connection lost")
        )

        result = await service.reset_training_tasks(
            session=mock_session,
            affected_items=items,
            report_id="rpt-001",
        )

        assert result["reset_count"] == 0
        assert len(result["failures"]) == 1
        assert "RuntimeError" in result["failures"][0]["reason"]


# ---------------------------------------------------------------------------
# Tests: get_document_status
# ---------------------------------------------------------------------------


class TestGetDocumentStatus:
    """Tests for ImpactNotificationService.get_document_status."""

    @pytest.mark.asyncio
    async def test_is_up_to_date_when_no_outstanding_findings(
        self, service, mock_session
    ):
        """is_up_to_date is True when no unacknowledged critical/major notifications."""
        # Mock: 0 critical, 0 major, no report
        critical_count = _mock_scalar_result(0)
        major_count = _mock_scalar_result(0)

        report_result = MagicMock()
        report_result.one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[critical_count, major_count, report_result]
        )

        status = await service.get_document_status(
            session=mock_session,
            document_uuid="2025-00001",
            company_id=1,
        )

        assert status.is_up_to_date is True
        assert status.outstanding_critical_count == 0
        assert status.outstanding_major_count == 0
        assert status.last_analysis_date is None
        assert status.last_analysis_report_id is None

    @pytest.mark.asyncio
    async def test_not_up_to_date_with_critical_findings(
        self, service, mock_session
    ):
        """is_up_to_date is False when unacknowledged critical notifications exist."""
        critical_count = _mock_scalar_result(2)
        major_count = _mock_scalar_result(0)

        report_result = MagicMock()
        report_result.one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[critical_count, major_count, report_result]
        )

        status = await service.get_document_status(
            session=mock_session,
            document_uuid="2025-00001",
            company_id=1,
        )

        assert status.is_up_to_date is False
        assert status.outstanding_critical_count == 2

    @pytest.mark.asyncio
    async def test_not_up_to_date_with_major_findings(
        self, service, mock_session
    ):
        """is_up_to_date is False when unacknowledged major notifications exist."""
        critical_count = _mock_scalar_result(0)
        major_count = _mock_scalar_result(3)

        report_result = MagicMock()
        report_result.one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[critical_count, major_count, report_result]
        )

        status = await service.get_document_status(
            session=mock_session,
            document_uuid="2025-00001",
            company_id=1,
        )

        assert status.is_up_to_date is False
        assert status.outstanding_major_count == 3

    @pytest.mark.asyncio
    async def test_includes_latest_report_info(self, service, mock_session):
        """Returns last_analysis_date and report_id from latest report."""
        critical_count = _mock_scalar_result(0)
        major_count = _mock_scalar_result(0)

        analysis_time = datetime(2025, 1, 15, 14, 30, 0, tzinfo=UTC)
        report_row = MagicMock()
        report_row.analysis_timestamp = analysis_time
        report_row.report_id = "rpt-abc-123"

        report_result = MagicMock()
        report_result.one_or_none.return_value = report_row

        mock_session.execute = AsyncMock(
            side_effect=[critical_count, major_count, report_result]
        )

        status = await service.get_document_status(
            session=mock_session,
            document_uuid="2025-00001",
            company_id=1,
        )

        assert status.last_analysis_date == analysis_time
        assert status.last_analysis_report_id == "rpt-abc-123"
        assert status.is_up_to_date is True

    @pytest.mark.asyncio
    async def test_document_uuid_in_response(self, service, mock_session):
        """Response includes the queried document_uuid."""
        critical_count = _mock_scalar_result(0)
        major_count = _mock_scalar_result(0)

        report_result = MagicMock()
        report_result.one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[critical_count, major_count, report_result]
        )

        status = await service.get_document_status(
            session=mock_session,
            document_uuid="2025-00042",
            company_id=1,
        )

        assert status.document_uuid == "2025-00042"
