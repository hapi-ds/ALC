"""Unit tests for the VigilanceEscalationService.

Tests cover:
- EscalationResult dataclass correctness
- escalate_signal orchestration with parallel sub-tasks
- _invoke_impact_analysis retry logic
- _invoke_contradiction_detection retry logic
- _dispatch_notifications admin user lookup
- _add_to_slr_reviews active review matching
- Independent failure isolation between sub-tasks
- Audit logging of escalation chain
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.vigilance.services.vigilance_escalation_service import (
    EscalationResult,
    VigilanceEscalationService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()

    # The session_factory() returns a context manager directly (not a coroutine)
    context_manager = AsyncMock()
    context_manager.__aenter__ = AsyncMock(return_value=session)
    context_manager.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = context_manager
    return factory, session


@pytest.fixture
def mock_impact_analysis():
    """Create a mock ImpactAnalysisService."""
    service = AsyncMock()
    return service


@pytest.fixture
def mock_contradiction_detection():
    """Create a mock ContradictionDetectionService."""
    service = AsyncMock()
    return service


@pytest.fixture
def mock_slr_review():
    """Create a mock SLRReviewService."""
    service = AsyncMock()
    return service


@pytest.fixture
def service(
    mock_session_factory,
    mock_impact_analysis,
    mock_contradiction_detection,
    mock_slr_review,
):
    """Create a VigilanceEscalationService with mocked dependencies."""
    factory, _ = mock_session_factory
    return VigilanceEscalationService(
        session_factory=factory,
        impact_analysis_service=mock_impact_analysis,
        contradiction_detection_service=mock_contradiction_detection,
        slr_review_service=mock_slr_review,
        escalation_retries=1,  # Use 1 retry for fast tests
    )


def _make_signal_mock(
    *,
    signal_id: int = 1,
    product_id: int = 10,
    company_id: int = 100,
    ingestion_record_id: int = 200,
    severity: str = "critical",
    evidence_summary: str = "Test evidence summary for testing.",
    regulatory_references: list[str] | None = None,
) -> MagicMock:
    """Create a mock VigilanceSignal."""
    signal = MagicMock()
    signal.id = signal_id
    signal.product_id = product_id
    signal.company_id = company_id
    signal.ingestion_record_id = ingestion_record_id
    signal.severity = severity
    signal.evidence_summary = evidence_summary
    signal.regulatory_references = regulatory_references or [
        "MDR Article 87(1)(a)"
    ]
    return signal


def _make_product_mock(
    *,
    product_id: int = 10,
    name: str = "Test Device",
    device_class: str = "IIb",
) -> MagicMock:
    """Create a mock MedicalProduct."""
    product = MagicMock()
    product.id = product_id
    product.name = name
    product.device_class = device_class
    return product


# ---------------------------------------------------------------------------
# EscalationResult Dataclass Tests
# ---------------------------------------------------------------------------


class TestEscalationResult:
    """Tests for the EscalationResult frozen dataclass."""

    def test_creation_with_defaults(self):
        """Test creating an EscalationResult with default values."""
        result = EscalationResult(signal_id=1)
        assert result.signal_id == 1
        assert result.impact_analysis_task_id is None
        assert result.contradiction_alert_ids == []
        assert result.notification_recipient_ids == []
        assert result.slr_reviews_updated == []
        assert result.failed_subtasks == []
        assert isinstance(result.escalation_timestamp, datetime)

    def test_creation_with_all_fields(self):
        """Test creating an EscalationResult with all fields populated."""
        ts = datetime.now(tz=timezone.utc)
        result = EscalationResult(
            signal_id=5,
            impact_analysis_task_id=42,
            contradiction_alert_ids=[1, 2, 3],
            notification_recipient_ids=[10, 20],
            slr_reviews_updated=[100],
            failed_subtasks=["slr_inclusion"],
            escalation_timestamp=ts,
        )
        assert result.signal_id == 5
        assert result.impact_analysis_task_id == 42
        assert result.contradiction_alert_ids == [1, 2, 3]
        assert result.notification_recipient_ids == [10, 20]
        assert result.slr_reviews_updated == [100]
        assert result.failed_subtasks == ["slr_inclusion"]
        assert result.escalation_timestamp == ts

    def test_frozen_immutability(self):
        """EscalationResult should be frozen (immutable)."""
        result = EscalationResult(signal_id=1)
        with pytest.raises(AttributeError):
            result.signal_id = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# VigilanceEscalationService Init Tests
# ---------------------------------------------------------------------------


class TestServiceInit:
    """Tests for VigilanceEscalationService initialization."""

    def test_default_retries(
        self,
        mock_session_factory,
        mock_impact_analysis,
        mock_contradiction_detection,
        mock_slr_review,
    ):
        """Default escalation_retries should be 3."""
        factory, _ = mock_session_factory
        svc = VigilanceEscalationService(
            session_factory=factory,
            impact_analysis_service=mock_impact_analysis,
            contradiction_detection_service=mock_contradiction_detection,
            slr_review_service=mock_slr_review,
        )
        assert svc._escalation_retries == 3

    def test_custom_retries(
        self,
        mock_session_factory,
        mock_impact_analysis,
        mock_contradiction_detection,
        mock_slr_review,
    ):
        """Custom escalation_retries should be stored."""
        factory, _ = mock_session_factory
        svc = VigilanceEscalationService(
            session_factory=factory,
            impact_analysis_service=mock_impact_analysis,
            contradiction_detection_service=mock_contradiction_detection,
            slr_review_service=mock_slr_review,
            escalation_retries=5,
        )
        assert svc._escalation_retries == 5

    def test_retry_interval(self, service):
        """RETRY_INTERVAL_S should be 300 seconds (5 minutes)."""
        assert service.RETRY_INTERVAL_S == 300

    def test_max_retries(self, service):
        """MAX_RETRIES class constant should be 3."""
        assert VigilanceEscalationService.MAX_RETRIES == 3


# ---------------------------------------------------------------------------
# escalate_signal Tests
# ---------------------------------------------------------------------------


class TestEscalateSignal:
    """Tests for the escalate_signal orchestration method."""

    @pytest.mark.asyncio
    async def test_successful_escalation_all_subtasks(
        self,
        service,
        mock_session_factory,
        mock_impact_analysis,
        mock_contradiction_detection,
    ):
        """All sub-tasks succeed: result should contain all task outputs."""
        _, session = mock_session_factory
        signal = _make_signal_mock()
        product = _make_product_mock()

        session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=signal)
        )
        session.get.return_value = product

        # Mock the four sub-tasks
        with (
            patch.object(
                service,
                "_invoke_impact_analysis",
                return_value=42,
            ),
            patch.object(
                service,
                "_invoke_contradiction_detection",
                return_value=[1, 2],
            ),
            patch.object(
                service,
                "_dispatch_notifications",
                return_value=[10, 20],
            ),
            patch.object(
                service,
                "_add_to_slr_reviews",
                return_value=[100],
            ),
        ):
            result = await service.escalate_signal(signal_id=1, company_id=100)

        assert result["signal_id"] == 1
        assert result["impact_analysis_task_id"] == 42
        assert result["contradiction_alert_ids"] == [1, 2]
        assert result["notification_recipient_ids"] == [10, 20]
        assert result["slr_reviews_updated"] == [100]
        assert result["failed_subtasks"] == []
        assert "escalation_timestamp" in result

    @pytest.mark.asyncio
    async def test_partial_failure_does_not_block_others(
        self,
        service,
        mock_session_factory,
    ):
        """Failure in one sub-task should not block the others."""
        _, session = mock_session_factory
        signal = _make_signal_mock()
        product = _make_product_mock()

        session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=signal)
        )
        session.get.return_value = product

        # Impact analysis fails, others succeed
        with (
            patch.object(
                service,
                "_invoke_impact_analysis",
                side_effect=RuntimeError("Service unavailable"),
            ),
            patch.object(
                service,
                "_invoke_contradiction_detection",
                return_value=[5],
            ),
            patch.object(
                service,
                "_dispatch_notifications",
                return_value=[10],
            ),
            patch.object(
                service,
                "_add_to_slr_reviews",
                return_value=[],
            ),
        ):
            result = await service.escalate_signal(signal_id=1, company_id=100)

        assert "impact_analysis" in result["failed_subtasks"]
        assert result["contradiction_alert_ids"] == [5]
        assert result["notification_recipient_ids"] == [10]
        assert result["slr_reviews_updated"] == []

    @pytest.mark.asyncio
    async def test_all_subtasks_fail(
        self,
        service,
        mock_session_factory,
    ):
        """If all sub-tasks fail, they should all appear in failed_subtasks."""
        _, session = mock_session_factory
        signal = _make_signal_mock()
        product = _make_product_mock()

        session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=signal)
        )
        session.get.return_value = product

        with (
            patch.object(
                service,
                "_invoke_impact_analysis",
                side_effect=RuntimeError("fail"),
            ),
            patch.object(
                service,
                "_invoke_contradiction_detection",
                side_effect=RuntimeError("fail"),
            ),
            patch.object(
                service,
                "_dispatch_notifications",
                side_effect=RuntimeError("fail"),
            ),
            patch.object(
                service,
                "_add_to_slr_reviews",
                side_effect=RuntimeError("fail"),
            ),
        ):
            result = await service.escalate_signal(signal_id=1, company_id=100)

        assert len(result["failed_subtasks"]) == 4
        assert result["impact_analysis_task_id"] is None
        assert result["contradiction_alert_ids"] == []
        assert result["notification_recipient_ids"] == []
        assert result["slr_reviews_updated"] == []


# ---------------------------------------------------------------------------
# _invoke_impact_analysis Tests
# ---------------------------------------------------------------------------


class TestInvokeImpactAnalysis:
    """Tests for the _invoke_impact_analysis retry logic."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(
        self,
        service,
        mock_impact_analysis,
    ):
        """Should return task_id on successful first attempt."""
        mock_impact_analysis.compute_change_delta = AsyncMock()

        result = await service._invoke_impact_analysis(
            signal_id=1, product_id=10, company_id=100
        )

        assert result == 1  # task_id == signal_id
        mock_impact_analysis.compute_change_delta.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_all_retries_exhausted(
        self,
        mock_session_factory,
        mock_contradiction_detection,
        mock_slr_review,
    ):
        """Should return None after all retries are exhausted."""
        factory, _ = mock_session_factory
        impact = AsyncMock()
        impact.compute_change_delta = AsyncMock(
            side_effect=RuntimeError("unavailable")
        )

        # Use escalation_retries=1 and no sleep to keep test fast
        svc = VigilanceEscalationService(
            session_factory=factory,
            impact_analysis_service=impact,
            contradiction_detection_service=mock_contradiction_detection,
            slr_review_service=mock_slr_review,
            escalation_retries=1,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await svc._invoke_impact_analysis(
                signal_id=1, product_id=10, company_id=100
            )

        assert result is None


# ---------------------------------------------------------------------------
# _invoke_contradiction_detection Tests
# ---------------------------------------------------------------------------


class TestInvokeContradictionDetection:
    """Tests for _invoke_contradiction_detection."""

    @pytest.mark.asyncio
    async def test_success_returns_alert_ids(
        self,
        service,
        mock_session_factory,
        mock_contradiction_detection,
    ):
        """Successful detection should return alert IDs."""
        _, session = mock_session_factory
        mock_contradiction_detection.analyze_record = AsyncMock(
            return_value={"alerts_created": 2, "contradiction_count": 2}
        )
        # Mock the DB query that fetches alert IDs
        session.execute.return_value = MagicMock(
            all=MagicMock(return_value=[(5,), (6,)])
        )

        result = await service._invoke_contradiction_detection(
            record_id=200, company_id=100
        )

        assert result == [5, 6]

    @pytest.mark.asyncio
    async def test_no_alerts_returns_empty(
        self,
        service,
        mock_contradiction_detection,
    ):
        """No contradictions found should return empty list."""
        mock_contradiction_detection.analyze_record = AsyncMock(
            return_value={"alerts_created": 0, "contradiction_count": 0}
        )

        result = await service._invoke_contradiction_detection(
            record_id=200, company_id=100
        )

        assert result == []


# ---------------------------------------------------------------------------
# _find_admin_users Tests
# ---------------------------------------------------------------------------


class TestFindAdminUsers:
    """Tests for the _find_admin_users helper."""

    @pytest.mark.asyncio
    async def test_returns_admin_user_ids(self, service, mock_session_factory):
        """Should return user_ids for document_admin and system_admin."""
        _, session = mock_session_factory
        session.execute.return_value = MagicMock(
            all=MagicMock(return_value=[(1,), (2,), (3,)])
        )

        result = await service._find_admin_users(session, company_id=100)

        assert result == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_admins(
        self, service, mock_session_factory
    ):
        """Should return empty list when no admins found."""
        _, session = mock_session_factory
        session.execute.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )

        result = await service._find_admin_users(session, company_id=100)

        assert result == []


# ---------------------------------------------------------------------------
# _load_signal Tests
# ---------------------------------------------------------------------------


class TestLoadSignal:
    """Tests for the _load_signal helper."""

    @pytest.mark.asyncio
    async def test_raises_on_not_found(self, service, mock_session_factory):
        """Should raise ValueError if signal not found."""
        _, session = mock_session_factory
        session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        )

        with pytest.raises(ValueError, match="not found"):
            await service._load_signal(session, signal_id=999, company_id=100)

    @pytest.mark.asyncio
    async def test_returns_signal_on_success(
        self, service, mock_session_factory
    ):
        """Should return the signal when found."""
        _, session = mock_session_factory
        signal = _make_signal_mock()
        session.execute.return_value = MagicMock(
            scalar_one_or_none=MagicMock(return_value=signal)
        )

        result = await service._load_signal(session, signal_id=1, company_id=100)

        assert result.id == 1
        assert result.severity == "critical"
