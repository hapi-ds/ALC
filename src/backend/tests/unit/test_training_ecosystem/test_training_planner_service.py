"""Unit tests for TrainingPlannerService.

Tests priority computation edge cases, compliance percentage calculation,
and schedule generation logic.

Requirements: 1.1–1.10, 2.1–2.8
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.training_ecosystem import PriorityLevel
from alcoabase.services.training_planner import (
    TrainingPlannerService,
    compute_compliance_percentage,
    compute_priority,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    mock_factory = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_cm
    mock_factory._session = session
    return mock_factory


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    return AsyncMock()


@pytest.fixture
def mock_agent_registry():
    """Create a mock AgentRegistryService."""
    registry = MagicMock()
    registry._load_archetype_raw = MagicMock(return_value={
        "archetype": "Educational Specialist",
        "system_prompt": "You are an Educational Specialist.",
        "contextual_tuning": {"temperature": 0.6, "max_tokens": 8192},
    })
    return registry


@pytest.fixture
def service(mock_session_factory, mock_inference_client, mock_agent_registry):
    """Create a TrainingPlannerService with mocked dependencies."""
    return TrainingPlannerService(
        session_factory=mock_session_factory,
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
    )


# ---------------------------------------------------------------------------
# Tests: compute_priority
# ---------------------------------------------------------------------------


class TestComputePriority:
    """Tests for the compute_priority pure function."""

    def test_no_deadline_returns_low(self):
        """No deadline means Low priority."""
        result = compute_priority(deadline=None, blocks_access=False)
        assert result == PriorityLevel.LOW

    def test_no_deadline_with_access_gate_returns_medium(self):
        """No deadline + blocks_access elevates Low → Medium."""
        result = compute_priority(deadline=None, blocks_access=True)
        assert result == PriorityLevel.MEDIUM

    def test_deadline_within_7_days_is_critical(self):
        """Deadline within 7 days returns Critical."""
        deadline = datetime.now(UTC) + timedelta(days=5)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.CRITICAL

    def test_deadline_exactly_7_days_is_critical(self):
        """Deadline exactly 7 days away returns Critical."""
        deadline = datetime.now(UTC) + timedelta(days=7)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.CRITICAL

    def test_deadline_overdue_is_critical(self):
        """Overdue deadline (past) returns Critical."""
        deadline = datetime.now(UTC) - timedelta(days=3)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.CRITICAL

    def test_deadline_within_30_days_is_high(self):
        """Deadline within 30 days (but > 7) returns High."""
        deadline = datetime.now(UTC) + timedelta(days=15)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.HIGH

    def test_deadline_exactly_30_days_is_high(self):
        """Deadline exactly 30 days away returns High."""
        deadline = datetime.now(UTC) + timedelta(days=30)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.HIGH

    def test_deadline_within_90_days_is_medium(self):
        """Deadline within 90 days (but > 30) returns Medium."""
        deadline = datetime.now(UTC) + timedelta(days=60)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.MEDIUM

    def test_deadline_exactly_90_days_is_medium(self):
        """Deadline exactly 90 days away returns Medium."""
        deadline = datetime.now(UTC) + timedelta(days=90)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.MEDIUM

    def test_deadline_beyond_90_days_is_low(self):
        """Deadline more than 90 days away returns Low."""
        deadline = datetime.now(UTC) + timedelta(days=120)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.LOW

    def test_access_gate_elevates_low_to_medium(self):
        """blocks_access elevates Low → Medium."""
        deadline = datetime.now(UTC) + timedelta(days=120)
        result = compute_priority(deadline=deadline, blocks_access=True)
        assert result == PriorityLevel.MEDIUM

    def test_access_gate_elevates_medium_to_high(self):
        """blocks_access elevates Medium → High."""
        deadline = datetime.now(UTC) + timedelta(days=60)
        result = compute_priority(deadline=deadline, blocks_access=True)
        assert result == PriorityLevel.HIGH

    def test_access_gate_elevates_high_to_critical(self):
        """blocks_access elevates High → Critical."""
        deadline = datetime.now(UTC) + timedelta(days=15)
        result = compute_priority(deadline=deadline, blocks_access=True)
        assert result == PriorityLevel.CRITICAL

    def test_access_gate_critical_stays_critical(self):
        """blocks_access on Critical stays Critical (no double-elevation)."""
        deadline = datetime.now(UTC) + timedelta(days=3)
        result = compute_priority(deadline=deadline, blocks_access=True)
        assert result == PriorityLevel.CRITICAL

    def test_far_future_deadline_is_low(self):
        """Very far future deadline (years away) is Low."""
        deadline = datetime.now(UTC) + timedelta(days=365)
        result = compute_priority(deadline=deadline, blocks_access=False)
        assert result == PriorityLevel.LOW


# ---------------------------------------------------------------------------
# Tests: compute_compliance_percentage
# ---------------------------------------------------------------------------


class TestComputeCompliancePercentage:
    """Tests for the compute_compliance_percentage pure function."""

    def test_zero_total_returns_100(self):
        """No requirements means fully compliant (100.0)."""
        result = compute_compliance_percentage(completed=0, total=0)
        assert result == 100.0

    def test_all_completed_returns_100(self):
        """All items completed returns 100.0."""
        result = compute_compliance_percentage(completed=10, total=10)
        assert result == 100.0

    def test_none_completed_returns_0(self):
        """No items completed returns 0.0."""
        result = compute_compliance_percentage(completed=0, total=10)
        assert result == 0.0

    def test_partial_completion(self):
        """Partial completion returns correct percentage."""
        result = compute_compliance_percentage(completed=7, total=10)
        assert result == 70.0

    def test_rounds_to_one_decimal(self):
        """Result is rounded to 1 decimal place."""
        result = compute_compliance_percentage(completed=1, total=3)
        assert result == 33.3

    def test_two_thirds_rounds_correctly(self):
        """2/3 rounds to 66.7."""
        result = compute_compliance_percentage(completed=2, total=3)
        assert result == 66.7

    def test_single_item_completed(self):
        """Single item out of many."""
        result = compute_compliance_percentage(completed=1, total=100)
        assert result == 1.0

    def test_large_numbers(self):
        """Works with large numbers."""
        result = compute_compliance_percentage(completed=999, total=1000)
        assert result == 99.9


# ---------------------------------------------------------------------------
# Tests: TrainingPlannerService.request_schedule_generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRequestScheduleGeneration:
    """Tests for schedule generation dispatch."""

    async def test_returns_job_id(self, service, mock_session_factory):
        """Successful request returns a UUID job_id."""
        session = mock_session_factory._session

        # Mock user exists
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = MagicMock(id=1)

        # Mock training task count > 0
        mock_task_count_result = MagicMock()
        mock_task_count_result.scalar_one.return_value = 3

        # Mock document count > 0
        mock_doc_count_result = MagicMock()
        mock_doc_count_result.scalar_one.return_value = 2

        session.execute = AsyncMock(
            side_effect=[
                mock_user_result,
                mock_task_count_result,
                mock_doc_count_result,
            ]
        )

        with patch(
            "alcoabase.tasks.training_tasks.generate_training_schedule"
        ) as mock_task:
            mock_task.delay = MagicMock()
            job_id = await service.request_schedule_generation(
                user_id=1, company_id=1
            )

        assert job_id is not None
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    async def test_raises_404_for_nonexistent_user(
        self, service, mock_session_factory
    ):
        """Raises HTTPException 404 when user does not exist."""
        session = mock_session_factory._session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.request_schedule_generation(user_id=999, company_id=1)

        assert exc_info.value.status_code == 404
