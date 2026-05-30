"""Unit tests for the @risk_controlled decorator.

Tests cover:
- Successful execution for each tier (High, Medium, Low)
- Correct result structure per tier
- Exception handling: logs failure and re-raises
- Pre-execution check blocking (unregistered task type, unavailable controls)
- Session extraction from instance and kwargs
- company_id and user_id validation

References:
    - Requirements: 4.2, 4.3, 4.4, 9.1, 9.8
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.risk_framework import (
    AIOperationLog,
    AuditDepth,
    GateResult,
    HITLCheckpoint,
    RiskTier,
)
from alcoabase.services.control_gate import (
    ControlGate,
    ControlUnavailableError,
    PreCheckResult,
    TIER_CONTROL_SETS,
    UnregisteredTaskTypeError,
)
from alcoabase.services.risk_controlled import risk_controlled


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_operation_log() -> AIOperationLog:
    """Create a mock AIOperationLog with a UUID id."""
    log = AIOperationLog(
        id=uuid.uuid4(),
        company_id=1,
        task_type_id="document_generation",
        risk_tier=RiskTier.HIGH.value,
        user_id=1,
        audit_depth=AuditDepth.FULL.value,
        gate_result=GateResult.PASSED.value,
    )
    return log


@pytest.fixture
def mock_checkpoint() -> HITLCheckpoint:
    """Create a mock HITLCheckpoint with a UUID id."""
    return HITLCheckpoint(
        id=uuid.uuid4(),
        company_id=1,
        operation_id="op-123",
        task_type_id="document_generation",
        ai_output_reference="operation:op-123",
        status="pending",
        assigned_reviewer_role="system_admin,doc_admin",
    )


class FakeService:
    """Fake service class with a session attribute for testing."""

    def __init__(self, session: AsyncMock) -> None:
        self.session = session


# ---------------------------------------------------------------------------
# High Tier Tests
# ---------------------------------------------------------------------------


class TestHighTierDecorator:
    """Tests for @risk_controlled with High tier operations."""

    @pytest.mark.asyncio
    async def test_high_tier_returns_pending_review(
        self, mock_session: AsyncMock, mock_operation_log: AIOperationLog, mock_checkpoint: HITLCheckpoint
    ):
        """High tier returns pending_review with operation_id and checkpoint_id."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate_document(self, company_id: int, user_id: int, prompt: str):
            return {"content": "Generated SOP content"}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log, \
             patch.object(ControlGate, "create_hitl_checkpoint") as mock_create_cp:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.HIGH,
                controls=TIER_CONTROL_SETS[RiskTier.HIGH],
                blocking_reason=None,
            )
            mock_post_log.return_value = mock_operation_log
            mock_create_cp.return_value = mock_checkpoint

            result = await generate_document(
                service, company_id=1, user_id=1, prompt="Generate SOP"
            )

        assert result["status"] == "pending_review"
        assert result["operation_id"] == str(mock_operation_log.id)
        assert result["checkpoint_id"] == str(mock_checkpoint.id)
        assert "result" not in result  # High tier blocks output visibility

    @pytest.mark.asyncio
    async def test_high_tier_creates_hitl_checkpoint(
        self, mock_session: AsyncMock, mock_operation_log: AIOperationLog, mock_checkpoint: HITLCheckpoint
    ):
        """High tier creates a HITL checkpoint after logging."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate_document(self, company_id: int, user_id: int):
            return {"content": "output"}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log, \
             patch.object(ControlGate, "create_hitl_checkpoint") as mock_create_cp:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.HIGH,
                controls=TIER_CONTROL_SETS[RiskTier.HIGH],
                blocking_reason=None,
            )
            mock_post_log.return_value = mock_operation_log
            mock_create_cp.return_value = mock_checkpoint

            await generate_document(service, company_id=1, user_id=1)

            mock_create_cp.assert_called_once()
            call_kwargs = mock_create_cp.call_args[1]
            assert call_kwargs["company_id"] == 1
            assert call_kwargs["task_type_id"] == "document_generation"
            assert call_kwargs["tier"] == RiskTier.HIGH


# ---------------------------------------------------------------------------
# Medium Tier Tests
# ---------------------------------------------------------------------------


class TestMediumTierDecorator:
    """Tests for @risk_controlled with Medium tier operations."""

    @pytest.mark.asyncio
    async def test_medium_tier_returns_pending_review_with_result(
        self, mock_session: AsyncMock, mock_operation_log: AIOperationLog, mock_checkpoint: HITLCheckpoint
    ):
        """Medium tier returns pending_review with ai_assisted label and result."""
        service = FakeService(session=mock_session)
        mock_operation_log.risk_tier = RiskTier.MEDIUM.value

        @risk_controlled(task_type_id="change_impact_analysis")
        async def analyze_impact(self, company_id: int, user_id: int, document_id: str):
            return {"affected_documents": ["doc-1", "doc-2"]}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log, \
             patch.object(ControlGate, "create_hitl_checkpoint") as mock_create_cp:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.MEDIUM,
                controls=TIER_CONTROL_SETS[RiskTier.MEDIUM],
                blocking_reason=None,
            )
            mock_post_log.return_value = mock_operation_log
            mock_create_cp.return_value = mock_checkpoint

            result = await analyze_impact(
                service, company_id=1, user_id=1, document_id="doc-123"
            )

        assert result["status"] == "pending_review"
        assert result["output_label"] == "ai_assisted"
        assert result["operation_id"] == str(mock_operation_log.id)
        assert result["checkpoint_id"] == str(mock_checkpoint.id)
        assert result["result"] == {"affected_documents": ["doc-1", "doc-2"]}


# ---------------------------------------------------------------------------
# Low Tier Tests
# ---------------------------------------------------------------------------


class TestLowTierDecorator:
    """Tests for @risk_controlled with Low tier operations."""

    @pytest.mark.asyncio
    async def test_low_tier_returns_completed_immediately(
        self, mock_session: AsyncMock, mock_operation_log: AIOperationLog
    ):
        """Low tier returns completed with ai_generated label and result."""
        service = FakeService(session=mock_session)
        mock_operation_log.risk_tier = RiskTier.LOW.value

        @risk_controlled(task_type_id="document_search")
        async def search_documents(self, company_id: int, user_id: int, query: str):
            return {"results": ["doc-1", "doc-2", "doc-3"]}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.LOW,
                controls=TIER_CONTROL_SETS[RiskTier.LOW],
                blocking_reason=None,
            )
            mock_post_log.return_value = mock_operation_log

            result = await search_documents(
                service, company_id=1, user_id=1, query="SOP procedures"
            )

        assert result["status"] == "completed"
        assert result["output_label"] == "ai_generated"
        assert result["result"] == {"results": ["doc-1", "doc-2", "doc-3"]}

    @pytest.mark.asyncio
    async def test_low_tier_does_not_create_checkpoint(
        self, mock_session: AsyncMock, mock_operation_log: AIOperationLog
    ):
        """Low tier does not create a HITL checkpoint."""
        service = FakeService(session=mock_session)
        mock_operation_log.risk_tier = RiskTier.LOW.value

        @risk_controlled(task_type_id="document_search")
        async def search_documents(self, company_id: int, user_id: int, query: str):
            return {"results": []}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log, \
             patch.object(ControlGate, "create_hitl_checkpoint") as mock_create_cp:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.LOW,
                controls=TIER_CONTROL_SETS[RiskTier.LOW],
                blocking_reason=None,
            )
            mock_post_log.return_value = mock_operation_log

            await search_documents(service, company_id=1, user_id=1, query="test")

            mock_create_cp.assert_not_called()


# ---------------------------------------------------------------------------
# Exception Handling Tests
# ---------------------------------------------------------------------------


class TestExceptionHandling:
    """Tests for exception handling in the decorator."""

    @pytest.mark.asyncio
    async def test_logs_failure_and_reraises_on_exception(
        self, mock_session: AsyncMock, mock_operation_log: AIOperationLog
    ):
        """On exception: logs as failure and re-raises the original exception."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate_document(self, company_id: int, user_id: int):
            raise RuntimeError("Inference failed")

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.HIGH,
                controls=TIER_CONTROL_SETS[RiskTier.HIGH],
                blocking_reason=None,
            )
            mock_post_log.return_value = mock_operation_log

            with pytest.raises(RuntimeError, match="Inference failed"):
                await generate_document(service, company_id=1, user_id=1)

            # Verify post_execution_log was called with failure data
            mock_post_log.assert_called_once()
            call_kwargs = mock_post_log.call_args[1]
            assert call_kwargs["output_data"]["status"] == "failure"
            assert "Inference failed" in call_kwargs["output_data"]["error"]

    @pytest.mark.asyncio
    async def test_reraises_unregistered_task_type_error(
        self, mock_session: AsyncMock
    ):
        """UnregisteredTaskTypeError from pre-check is re-raised directly."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="nonexistent_task")
        async def do_something(self, company_id: int, user_id: int):
            return {"result": "should not reach here"}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check:
            mock_pre_check.side_effect = UnregisteredTaskTypeError("nonexistent_task")

            with pytest.raises(UnregisteredTaskTypeError):
                await do_something(service, company_id=1, user_id=1)

    @pytest.mark.asyncio
    async def test_reraises_control_unavailable_error(
        self, mock_session: AsyncMock
    ):
        """ControlUnavailableError from pre-check is re-raised directly."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate(self, company_id: int, user_id: int):
            return {"result": "should not reach here"}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check:
            mock_pre_check.side_effect = ControlUnavailableError(
                "hitl_reviewer_availability", "No reviewers"
            )

            with pytest.raises(ControlUnavailableError):
                await generate(service, company_id=1, user_id=1)

    @pytest.mark.asyncio
    async def test_failure_logging_error_does_not_suppress_original(
        self, mock_session: AsyncMock
    ):
        """If failure logging itself fails, original exception is still raised."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate(self, company_id: int, user_id: int):
            raise ValueError("Original error")

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.HIGH,
                controls=TIER_CONTROL_SETS[RiskTier.HIGH],
                blocking_reason=None,
            )
            # Failure logging also fails
            mock_post_log.side_effect = Exception("DB connection lost")

            with pytest.raises(ValueError, match="Original error"):
                await generate(service, company_id=1, user_id=1)


# ---------------------------------------------------------------------------
# Validation Tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for input validation and pass-through behavior in the decorator."""

    @pytest.mark.asyncio
    async def test_passes_through_without_company_id(self, mock_session: AsyncMock):
        """Executes function directly (pass-through) if company_id is not in kwargs."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate(self, user_id: int):
            return {"content": "generated"}

        result = await generate(service, user_id=1)
        assert result == {"content": "generated"}

    @pytest.mark.asyncio
    async def test_passes_through_without_user_id(self, mock_session: AsyncMock):
        """Executes function directly (pass-through) if user_id is not in kwargs."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate(self, company_id: int):
            return {"content": "generated"}

        result = await generate(service, company_id=1)
        assert result == {"content": "generated"}

    @pytest.mark.asyncio
    async def test_passes_through_without_session(self):
        """Executes function directly (pass-through) if no session is available."""

        class NoSessionService:
            pass

        service = NoSessionService()

        @risk_controlled(task_type_id="document_generation")
        async def generate(self, company_id: int, user_id: int):
            return {"content": "generated"}

        result = await generate(service, company_id=1, user_id=1)
        assert result == {"content": "generated"}

    @pytest.mark.asyncio
    async def test_extracts_session_from_underscore_attribute(self):
        """Extracts session from _session attribute (ControlGate pattern)."""

        class PrivateSessionService:
            def __init__(self, session):
                self._session = session

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        service = PrivateSessionService(session=mock_session)

        @risk_controlled(task_type_id="document_search")
        async def search(self, company_id: int, user_id: int, query: str):
            return {"results": []}

        mock_operation_log = AIOperationLog(
            id=uuid.uuid4(),
            company_id=1,
            task_type_id="document_search",
            risk_tier=RiskTier.LOW.value,
            user_id=1,
            audit_depth=AuditDepth.MINIMAL.value,
            gate_result=GateResult.PASSED.value,
        )

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check, \
             patch.object(ControlGate, "post_execution_log") as mock_post_log:

            mock_pre_check.return_value = PreCheckResult(
                allowed=True,
                tier=RiskTier.LOW,
                controls=TIER_CONTROL_SETS[RiskTier.LOW],
                blocking_reason=None,
            )
            mock_post_log.return_value = mock_operation_log

            result = await search(service, company_id=1, user_id=1, query="test")

        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Blocked Pre-Check Tests
# ---------------------------------------------------------------------------


class TestBlockedPreCheck:
    """Tests for when pre-execution check blocks the operation."""

    @pytest.mark.asyncio
    async def test_returns_blocked_status_when_not_allowed(
        self, mock_session: AsyncMock
    ):
        """Returns blocked status when pre-check disallows execution."""
        service = FakeService(session=mock_session)

        @risk_controlled(task_type_id="document_generation")
        async def generate(self, company_id: int, user_id: int):
            return {"content": "should not execute"}

        with patch.object(ControlGate, "pre_execution_check") as mock_pre_check:
            mock_pre_check.return_value = PreCheckResult(
                allowed=False,
                tier=RiskTier.HIGH,
                controls=TIER_CONTROL_SETS[RiskTier.HIGH],
                blocking_reason="HITL reviewer pool empty",
            )

            result = await generate(service, company_id=1, user_id=1)

        assert result["status"] == "blocked"
        assert result["blocking_reason"] == "HITL reviewer pool empty"
        assert result["task_type_id"] == "document_generation"
