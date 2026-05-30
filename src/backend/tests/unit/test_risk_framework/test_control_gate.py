"""Unit tests for the ControlGate service.

Tests cover:
- Pre-execution check: tier resolution, HITL reviewer verification, audit writability
- Post-execution log: AIOperationLog and ControlEnforcementLog creation
- Blocking on unregistered task types
- Blocking when required controls are unavailable
- AuditWriteError for High/Medium tier log failures
- ControlSet dataclass and TIER_CONTROL_SETS mapping
- HITL checkpoint creation

References:
    - Requirements: 4.1–4.10, 6.1–6.4, 6.8, 6.9
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.risk_framework import (
    AIOperationLog,
    AITaskType,
    AuditDepth,
    CheckpointStatus,
    CompanyRiskProfile,
    ControlEnforcementLog,
    GateResult,
    HITLCheckpoint,
    RiskTier,
    RiskTierOverride,
)
from alcoabase.services.control_gate import (
    AuditWriteError,
    ControlGate,
    ControlSet,
    ControlUnavailableError,
    PreCheckResult,
    TIER_CONTROL_SETS,
    UnregisteredTaskTypeError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession for ControlGate tests."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def control_gate(mock_session: AsyncMock) -> ControlGate:
    """Create a ControlGate instance with a mock session."""
    return ControlGate(session=mock_session)


@pytest.fixture
def sample_task_type() -> AITaskType:
    """Create a sample AITaskType for testing."""
    task = AITaskType(
        id=uuid.uuid4(),
        task_type_id="document_generation",
        display_name="Document Generation",
        description="Generates GxP-regulated content",
        module_reference="5.4",
        default_risk_tier=RiskTier.HIGH.value,
        risk_factors=["Generates GxP-regulated content"],
        is_active=True,
        is_system_defined=True,
        company_id=None,
    )
    return task


# ---------------------------------------------------------------------------
# TIER_CONTROL_SETS Tests
# ---------------------------------------------------------------------------


class TestTierControlSets:
    """Tests for the static TIER_CONTROL_SETS mapping."""

    def test_high_tier_controls(self):
        """High tier requires HITL, blocks visibility, full audit depth."""
        controls = TIER_CONTROL_SETS[RiskTier.HIGH]
        assert controls.hitl_required is True
        assert controls.hitl_blocks_visibility is True
        assert controls.audit_depth == AuditDepth.FULL
        assert "format_validation" in controls.validations
        assert "cross_reference_check" in controls.validations
        assert "completeness_check" in controls.validations
        assert controls.provenance_required is True
        assert controls.expiry_hours == 72
        assert controls.rate_limit is None
        assert controls.output_label is None

    def test_medium_tier_controls(self):
        """Medium tier requires HITL, does not block visibility, standard audit."""
        controls = TIER_CONTROL_SETS[RiskTier.MEDIUM]
        assert controls.hitl_required is True
        assert controls.hitl_blocks_visibility is False
        assert controls.audit_depth == AuditDepth.STANDARD
        assert controls.validations == ["format_validation"]
        assert controls.provenance_required is False
        assert controls.expiry_hours == 72
        assert controls.rate_limit is None
        assert controls.output_label == "ai_assisted"

    def test_low_tier_controls(self):
        """Low tier: no HITL, minimal audit, rate limited."""
        controls = TIER_CONTROL_SETS[RiskTier.LOW]
        assert controls.hitl_required is False
        assert controls.hitl_blocks_visibility is False
        assert controls.audit_depth == AuditDepth.MINIMAL
        assert controls.validations == []
        assert controls.provenance_required is False
        assert controls.expiry_hours is None
        assert controls.rate_limit == 100
        assert controls.output_label == "ai_generated"

    def test_all_tiers_have_control_sets(self):
        """Every RiskTier enum value has a corresponding ControlSet."""
        for tier in RiskTier:
            assert tier in TIER_CONTROL_SETS
            assert isinstance(TIER_CONTROL_SETS[tier], ControlSet)


# ---------------------------------------------------------------------------
# Pre-Execution Check Tests
# ---------------------------------------------------------------------------


class TestPreExecutionCheck:
    """Tests for ControlGate.pre_execution_check."""

    @pytest.mark.asyncio
    async def test_blocks_unregistered_task_type(
        self, control_gate: ControlGate, mock_session: AsyncMock
    ):
        """Unregistered task_type_id raises UnregisteredTaskTypeError."""
        # Mock: task type not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(UnregisteredTaskTypeError) as exc_info:
            await control_gate.pre_execution_check(
                task_type_id="nonexistent_task",
                company_id=1,
                user_id=1,
            )

        assert "nonexistent_task" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_allows_registered_low_tier_task(
        self, control_gate: ControlGate, mock_session: AsyncMock
    ):
        """Registered Low-tier task passes without HITL/audit checks."""
        low_task = AITaskType(
            id=uuid.uuid4(),
            task_type_id="document_search",
            display_name="Document Search",
            description="Search",
            module_reference="4.1",
            default_risk_tier=RiskTier.LOW.value,
            risk_factors=[],
            is_active=True,
            is_system_defined=True,
            company_id=None,
        )

        # First call: resolve task type
        # Second call: check for company profile (returns None)
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = low_task

        mock_result_profile = MagicMock()
        mock_result_profile.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [mock_result_task, mock_result_profile]

        result = await control_gate.pre_execution_check(
            task_type_id="document_search",
            company_id=1,
            user_id=1,
        )

        assert result.allowed is True
        assert result.tier == RiskTier.LOW
        assert result.controls == TIER_CONTROL_SETS[RiskTier.LOW]
        assert result.blocking_reason is None

    @pytest.mark.asyncio
    async def test_high_tier_blocks_when_no_reviewers(
        self, control_gate: ControlGate, mock_session: AsyncMock, sample_task_type: AITaskType
    ):
        """High-tier task blocked when no HITL reviewers available."""
        # First call: resolve task type (HIGH)
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = sample_task_type

        # Second call: no company profile
        mock_result_profile = MagicMock()
        mock_result_profile.scalar_one_or_none.return_value = None

        # Third call: no reviewers found
        mock_result_reviewers = MagicMock()
        mock_result_reviewers.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [
            mock_result_task,
            mock_result_profile,
            mock_result_reviewers,
        ]

        with pytest.raises(ControlUnavailableError) as exc_info:
            await control_gate.pre_execution_check(
                task_type_id="document_generation",
                company_id=1,
                user_id=1,
            )

        assert "hitl_reviewer_availability" in exc_info.value.control_name

    @pytest.mark.asyncio
    async def test_high_tier_passes_with_reviewer_and_audit(
        self, control_gate: ControlGate, mock_session: AsyncMock, sample_task_type: AITaskType
    ):
        """High-tier task passes when reviewers exist and audit is writable."""
        # First call: resolve task type (HIGH)
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = sample_task_type

        # Second call: no company profile
        mock_result_profile = MagicMock()
        mock_result_profile.scalar_one_or_none.return_value = None

        # Third call: reviewer found
        mock_result_reviewers = MagicMock()
        mock_result_reviewers.scalar_one_or_none.return_value = 1  # user_id

        # Fourth call: audit trail writable
        mock_result_audit = MagicMock()

        mock_session.execute.side_effect = [
            mock_result_task,
            mock_result_profile,
            mock_result_reviewers,
            mock_result_audit,
        ]

        result = await control_gate.pre_execution_check(
            task_type_id="document_generation",
            company_id=1,
            user_id=1,
        )

        assert result.allowed is True
        assert result.tier == RiskTier.HIGH
        assert result.controls == TIER_CONTROL_SETS[RiskTier.HIGH]

    @pytest.mark.asyncio
    async def test_uses_company_override_tier(
        self, control_gate: ControlGate, mock_session: AsyncMock, sample_task_type: AITaskType
    ):
        """Uses company profile override tier instead of default."""
        profile_id = uuid.uuid4()
        profile = CompanyRiskProfile(
            id=profile_id,
            company_id=1,
            profile_name="Custom Profile",
            regulatory_frameworks=["GMP"],
            is_active=True,
            created_by=1,
        )
        override = RiskTierOverride(
            id=uuid.uuid4(),
            profile_id=profile_id,
            task_type_id="document_generation",
            assigned_tier=RiskTier.LOW.value,
            justification="De-escalated for testing",
        )

        # First call: resolve task type
        mock_result_task = MagicMock()
        mock_result_task.scalar_one_or_none.return_value = sample_task_type

        # Second call: company profile found
        mock_result_profile = MagicMock()
        mock_result_profile.scalar_one_or_none.return_value = profile

        # Third call: override found
        mock_result_override = MagicMock()
        mock_result_override.scalar_one_or_none.return_value = override

        mock_session.execute.side_effect = [
            mock_result_task,
            mock_result_profile,
            mock_result_override,
        ]

        result = await control_gate.pre_execution_check(
            task_type_id="document_generation",
            company_id=1,
            user_id=1,
        )

        # Should use the override tier (LOW), not the default (HIGH)
        assert result.tier == RiskTier.LOW
        assert result.allowed is True


# ---------------------------------------------------------------------------
# Post-Execution Log Tests
# ---------------------------------------------------------------------------


class TestPostExecutionLog:
    """Tests for ControlGate.post_execution_log."""

    @pytest.mark.asyncio
    async def test_creates_operation_and_enforcement_logs(
        self, control_gate: ControlGate, mock_session: AsyncMock
    ):
        """Creates both AIOperationLog and ControlEnforcementLog."""
        result = await control_gate.post_execution_log(
            task_type_id="document_generation",
            company_id=1,
            user_id=1,
            tier=RiskTier.HIGH,
            input_data={"prompt": "Generate SOP"},
            output_data={"content": "Generated content"},
            model_name="gemma-4",
            inference_duration_ms=1500,
            token_count_input=100,
            token_count_output=500,
            source_document_ids=["doc-1", "doc-2"],
            gate_result=GateResult.PASSED,
            blocking_reason=None,
            controls_enforced=["hitl_checkpoint", "format_validation"],
            controls_satisfied={"hitl_checkpoint": True, "format_validation": True},
        )

        # Verify session.add was called twice (operation log + enforcement log)
        assert mock_session.add.call_count == 2
        # Verify flush was called (synchronous for HIGH tier)
        assert mock_session.flush.call_count >= 1

        # Verify the returned object is an AIOperationLog
        assert isinstance(result, AIOperationLog)
        assert result.task_type_id == "document_generation"
        assert result.risk_tier == RiskTier.HIGH.value
        assert result.audit_depth == AuditDepth.FULL.value

    @pytest.mark.asyncio
    async def test_high_tier_raises_audit_write_error_on_failure(
        self, control_gate: ControlGate, mock_session: AsyncMock
    ):
        """High-tier log failure raises AuditWriteError."""
        mock_session.flush.side_effect = Exception("DB connection lost")

        with pytest.raises(AuditWriteError) as exc_info:
            await control_gate.post_execution_log(
                task_type_id="document_generation",
                company_id=1,
                user_id=1,
                tier=RiskTier.HIGH,
                input_data=None,
                output_data=None,
                model_name=None,
                inference_duration_ms=None,
                token_count_input=None,
                token_count_output=None,
                source_document_ids=None,
                gate_result=GateResult.PASSED,
                blocking_reason=None,
                controls_enforced=[],
                controls_satisfied={},
            )

        assert exc_info.value.tier == RiskTier.HIGH
        assert "document_generation" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_medium_tier_raises_audit_write_error_on_failure(
        self, control_gate: ControlGate, mock_session: AsyncMock
    ):
        """Medium-tier log failure raises AuditWriteError."""
        mock_session.flush.side_effect = Exception("DB timeout")

        with pytest.raises(AuditWriteError):
            await control_gate.post_execution_log(
                task_type_id="change_impact_analysis",
                company_id=1,
                user_id=1,
                tier=RiskTier.MEDIUM,
                input_data=None,
                output_data=None,
                model_name=None,
                inference_duration_ms=None,
                token_count_input=None,
                token_count_output=None,
                source_document_ids=None,
                gate_result=GateResult.PASSED,
                blocking_reason=None,
                controls_enforced=[],
                controls_satisfied={},
            )

    @pytest.mark.asyncio
    async def test_minimal_audit_depth_filters_data(
        self, control_gate: ControlGate, mock_session: AsyncMock
    ):
        """Low-tier (minimal audit) stores no input/output data."""
        result = await control_gate.post_execution_log(
            task_type_id="document_search",
            company_id=1,
            user_id=1,
            tier=RiskTier.LOW,
            input_data={"query": "find SOPs"},
            output_data={"results": ["doc1", "doc2"]},
            model_name="gemma-4",
            inference_duration_ms=200,
            token_count_input=50,
            token_count_output=100,
            source_document_ids=["doc-1"],
            gate_result=GateResult.PASSED,
            blocking_reason=None,
            controls_enforced=[],
            controls_satisfied={},
        )

        assert result.input_data is None
        assert result.output_data is None
        assert result.model_name is None
        assert result.token_count_input is None
        # token_count_output is always logged
        assert result.token_count_output == 100


# ---------------------------------------------------------------------------
# HITL Checkpoint Tests
# ---------------------------------------------------------------------------


class TestCreateHitlCheckpoint:
    """Tests for ControlGate.create_hitl_checkpoint."""

    @pytest.mark.asyncio
    async def test_creates_checkpoint_with_72h_expiry(
        self, control_gate: ControlGate, mock_session: AsyncMock
    ):
        """Creates a HITL checkpoint with 72-hour expiry and pending status."""
        result = await control_gate.create_hitl_checkpoint(
            company_id=1,
            operation_id="op-123",
            task_type_id="document_generation",
            ai_output_reference="s3://outputs/op-123.json",
            tier=RiskTier.HIGH,
        )

        assert isinstance(result, HITLCheckpoint)
        assert result.company_id == 1
        assert result.operation_id == "op-123"
        assert result.task_type_id == "document_generation"
        assert result.status == CheckpointStatus.PENDING.value
        assert result.ai_output_reference == "s3://outputs/op-123.json"
        # Verify 72-hour expiry window
        assert result.expires_at is not None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# Exception Tests
# ---------------------------------------------------------------------------


class TestExceptions:
    """Tests for custom exception classes."""

    def test_unregistered_task_type_error(self):
        """UnregisteredTaskTypeError contains task_type_id."""
        err = UnregisteredTaskTypeError("my_task")
        assert err.task_type_id == "my_task"
        assert "my_task" in str(err)
        assert "not registered" in str(err)

    def test_control_unavailable_error(self):
        """ControlUnavailableError contains control name and reason."""
        err = ControlUnavailableError("hitl_reviewer_availability", "No reviewers")
        assert err.control_name == "hitl_reviewer_availability"
        assert err.reason == "No reviewers"
        assert "hitl_reviewer_availability" in str(err)

    def test_audit_write_error(self):
        """AuditWriteError contains task_type_id, tier, and original error."""
        original = Exception("connection refused")
        err = AuditWriteError("document_generation", RiskTier.HIGH, original)
        assert err.task_type_id == "document_generation"
        assert err.tier == RiskTier.HIGH
        assert err.original_error is original
        assert "document_generation" in str(err)
        assert "high" in str(err)
