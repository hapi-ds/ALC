"""ControlGate service for runtime enforcement of risk-tier-appropriate controls.

This module implements the Control_Gate — the runtime enforcement engine that:
- Resolves the applicable risk tier for a given AI task type and company
- Verifies pre-execution conditions (HITL reviewer availability, audit writability)
- Blocks operations when task types are unregistered or controls unavailable
- Logs operations at tier-appropriate audit depth (synchronously for High/Medium)
- Creates HITL checkpoints for High/Medium tier operations

The ControlGate accepts an AsyncSession via dependency injection and uses
models from alcoabase.models.risk_framework.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 4.1–4.10, 6.1–6.4, 6.8, 6.9
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from alcoabase.models.user import Role, User, UserRole

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class UnregisteredTaskTypeError(Exception):
    """Raised when a task_type_id is not found in the AI Task Type registry.

    This indicates the AI feature has not been registered before attempting
    to invoke inference, violating Requirement 1.7.
    """

    def __init__(self, task_type_id: str) -> None:
        self.task_type_id = task_type_id
        super().__init__(
            f"Task type '{task_type_id}' is not registered in the AI Task Type registry. "
            f"All AI features must register a task type before invoking inference."
        )


class ControlUnavailableError(Exception):
    """Raised when a required control cannot be enforced.

    This occurs when:
    - HITL reviewer pool is empty for the company (no system_admin or doc_admin)
    - Audit trail service is unreachable (cannot write to ai_operation_logs)

    The operation is blocked and inference is NOT executed.
    """

    def __init__(self, control_name: str, reason: str) -> None:
        self.control_name = control_name
        self.reason = reason
        super().__init__(
            f"Required control '{control_name}' is unavailable: {reason}"
        )


class AuditWriteError(Exception):
    """Raised when an audit log write fails for a High or Medium tier operation.

    Per Requirement 6.8, if the audit log write fails for High/Medium tiers,
    the AI output MUST NOT be returned to the caller. This ensures no AI
    operation result is delivered without a corresponding audit trail entry.
    """

    def __init__(self, task_type_id: str, tier: RiskTier, original_error: Exception) -> None:
        self.task_type_id = task_type_id
        self.tier = tier
        self.original_error = original_error
        super().__init__(
            f"Audit log write failed for {tier.value}-tier operation '{task_type_id}'. "
            f"AI output cannot be returned without audit trail. "
            f"Original error: {original_error}"
        )


# ---------------------------------------------------------------------------
# ControlSet Dataclass and Tier Mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlSet:
    """Defines the control measures enforced for a specific risk tier.

    Attributes:
        hitl_required: Whether a HITL checkpoint is required.
        hitl_blocks_visibility: Whether HITL blocks output visibility (High)
            or only automated actions (Medium).
        audit_depth: The granularity of audit logging for this tier.
        validations: List of validation requirement names to enforce.
        provenance_required: Whether generation provenance record is required.
        expiry_hours: Hours until unreviewed output expires (None for Low).
        rate_limit: Rate limit per user per hour (None if no limit).
        output_label: Metadata label applied to output (None for High).
    """

    hitl_required: bool
    hitl_blocks_visibility: bool
    audit_depth: AuditDepth
    validations: list[str]
    provenance_required: bool
    expiry_hours: int | None
    rate_limit: int | None
    output_label: str | None


TIER_CONTROL_SETS: dict[RiskTier, ControlSet] = {
    RiskTier.HIGH: ControlSet(
        hitl_required=True,
        hitl_blocks_visibility=True,
        audit_depth=AuditDepth.FULL,
        validations=["format_validation", "cross_reference_check", "completeness_check"],
        provenance_required=True,
        expiry_hours=72,
        rate_limit=None,
        output_label=None,
    ),
    RiskTier.MEDIUM: ControlSet(
        hitl_required=True,
        hitl_blocks_visibility=False,
        audit_depth=AuditDepth.STANDARD,
        validations=["format_validation"],
        provenance_required=False,
        expiry_hours=72,
        rate_limit=None,
        output_label="ai_assisted",
    ),
    RiskTier.LOW: ControlSet(
        hitl_required=False,
        hitl_blocks_visibility=False,
        audit_depth=AuditDepth.MINIMAL,
        validations=[],
        provenance_required=False,
        expiry_hours=None,
        rate_limit=100,
        output_label="ai_generated",
    ),
}


# ---------------------------------------------------------------------------
# PreCheckResult Dataclass
# ---------------------------------------------------------------------------


@dataclass
class PreCheckResult:
    """Result of a pre-execution control gate check.

    Attributes:
        allowed: Whether the operation is allowed to proceed.
        tier: The resolved risk tier for the operation.
        controls: The ControlSet applicable to the resolved tier.
        blocking_reason: Reason the operation was blocked (None if allowed).
    """

    allowed: bool
    tier: RiskTier
    controls: ControlSet
    blocking_reason: str | None


# ---------------------------------------------------------------------------
# ControlGate Service
# ---------------------------------------------------------------------------


class ControlGate:
    """Enforces tier-appropriate controls before and after AI operations.

    The ControlGate is the runtime enforcement point in the AI execution
    pipeline. It resolves risk tiers, verifies pre-conditions, logs
    operations at the appropriate audit depth, and creates HITL checkpoints.

    Args:
        session: AsyncSession for database operations (dependency injection).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def pre_execution_check(
        self,
        task_type_id: str,
        company_id: int,
        user_id: int,
    ) -> PreCheckResult:
        """Verify all pre-execution controls before allowing an AI operation.

        Resolves the applicable risk tier, then verifies:
        1. Task type is registered in the AI Task Type registry
        2. For High/Medium: HITL reviewer availability (system_admin or doc_admin)
        3. For High/Medium: Audit trail writability

        Args:
            task_type_id: The registered AI task type identifier.
            company_id: The company ID for tenant scoping.
            user_id: The user initiating the operation.

        Returns:
            PreCheckResult indicating whether the operation may proceed.

        Raises:
            UnregisteredTaskTypeError: If task_type_id is not in the registry.
            ControlUnavailableError: If required controls cannot be enforced.
        """
        start_time = time.monotonic()

        # Step 1: Resolve task type from registry
        task_type = await self._resolve_task_type(task_type_id, company_id)

        # Step 2: Resolve effective tier (company override or default)
        tier = await self._get_effective_tier(task_type_id, company_id, task_type)

        # Step 3: Get the control set for this tier
        controls = TIER_CONTROL_SETS[tier]

        # Step 4: Verify pre-conditions for High/Medium tiers
        if tier in (RiskTier.HIGH, RiskTier.MEDIUM):
            # Verify HITL reviewer availability
            await self._verify_hitl_reviewer_availability(company_id)

            # Verify audit trail writability
            await self._verify_audit_trail_writability()

        # Log performance warning if check exceeds 500ms
        elapsed_ms = (time.monotonic() - start_time) * 1000
        if elapsed_ms > 500:
            logger.warning(
                "Pre-execution check exceeded 500ms threshold: %.1fms "
                "(task_type=%s, company=%d)",
                elapsed_ms,
                task_type_id,
                company_id,
            )

        return PreCheckResult(
            allowed=True,
            tier=tier,
            controls=controls,
            blocking_reason=None,
        )

    async def post_execution_log(
        self,
        task_type_id: str,
        company_id: int,
        user_id: int,
        tier: RiskTier,
        input_data: dict | None,
        output_data: dict | None,
        model_name: str | None,
        inference_duration_ms: int | None,
        token_count_input: int | None,
        token_count_output: int | None,
        source_document_ids: list[str] | None,
        gate_result: GateResult,
        blocking_reason: str | None,
        controls_enforced: list[str],
        controls_satisfied: dict[str, bool],
    ) -> AIOperationLog:
        """Create audit log entries after an AI operation completes.

        Creates an AIOperationLog at the tier-appropriate audit depth,
        then creates a ControlEnforcementLog. For High/Medium tiers,
        writes are synchronous — if they fail, raises AuditWriteError.

        Args:
            task_type_id: The AI task type identifier.
            company_id: The company ID.
            user_id: The user who initiated the operation.
            tier: The resolved risk tier.
            input_data: Input data for the operation (filtered by audit depth).
            output_data: Output data from the operation (filtered by audit depth).
            model_name: Name of the AI model used.
            inference_duration_ms: Duration of inference in milliseconds.
            token_count_input: Number of input tokens.
            token_count_output: Number of output tokens.
            source_document_ids: Array of referenced document IDs.
            gate_result: Whether the operation passed or was blocked.
            blocking_reason: Reason for blocking (if blocked).
            controls_enforced: Array of control names that were enforced.
            controls_satisfied: Mapping of control name to satisfaction boolean.

        Returns:
            The created AIOperationLog instance.

        Raises:
            AuditWriteError: If audit log write fails for High/Medium tier.
        """
        controls = TIER_CONTROL_SETS[tier]
        audit_depth = controls.audit_depth

        # Filter data based on audit depth
        filtered_input = self._filter_by_audit_depth(input_data, audit_depth, is_input=True)
        filtered_output = self._filter_by_audit_depth(output_data, audit_depth, is_input=False)

        # Determine which fields to persist based on audit depth
        log_model_name = model_name if audit_depth in (AuditDepth.FULL, AuditDepth.STANDARD) else None
        log_token_input = token_count_input if audit_depth in (AuditDepth.FULL, AuditDepth.STANDARD) else None
        log_token_output = token_count_output  # Always logged per Req 6.3
        log_source_docs = source_document_ids if audit_depth in (AuditDepth.FULL, AuditDepth.STANDARD) else None

        try:
            # Create AIOperationLog
            operation_log = AIOperationLog(
                id=uuid.uuid4(),
                company_id=company_id,
                task_type_id=task_type_id,
                risk_tier=tier.value,
                user_id=user_id,
                audit_depth=audit_depth.value,
                input_data=filtered_input,
                output_data=filtered_output,
                model_name=log_model_name,
                inference_duration_ms=inference_duration_ms,
                token_count_input=log_token_input,
                token_count_output=log_token_output,
                gate_result=gate_result.value,
                blocking_reason=blocking_reason,
                source_document_ids=log_source_docs,
            )
            self._session.add(operation_log)

            # Flush to get the operation_log.id for the enforcement log FK
            await self._session.flush()

            # Create ControlEnforcementLog
            enforcement_log = ControlEnforcementLog(
                id=uuid.uuid4(),
                company_id=company_id,
                operation_log_id=operation_log.id,
                task_type_id=task_type_id,
                risk_tier=tier.value,
                controls_enforced=controls_enforced,
                controls_satisfied=controls_satisfied,
                overall_result=gate_result.value,
                blocking_reason=blocking_reason,
                enforcement_duration_ms=None,
            )
            self._session.add(enforcement_log)

            # For High/Medium: synchronous write before returning
            if tier in (RiskTier.HIGH, RiskTier.MEDIUM):
                await self._session.flush()

            return operation_log

        except Exception as e:
            # For High/Medium tiers: raise AuditWriteError, do NOT return output
            if tier in (RiskTier.HIGH, RiskTier.MEDIUM):
                raise AuditWriteError(
                    task_type_id=task_type_id,
                    tier=tier,
                    original_error=e,
                ) from e
            # For Low tier: log the error but don't block
            logger.error(
                "Audit log write failed for low-tier operation '%s': %s",
                task_type_id,
                e,
            )
            raise

    async def create_hitl_checkpoint(
        self,
        company_id: int,
        operation_id: str,
        task_type_id: str,
        ai_output_reference: str,
        tier: RiskTier,
    ) -> HITLCheckpoint:
        """Create a HITL checkpoint for a High or Medium tier operation.

        The checkpoint expires after 72 hours. Until reviewed, the AI output
        is blocked from user-visible persistence (High) or from triggering
        automated actions (Medium).

        Args:
            company_id: The company ID.
            operation_id: Reference to the AI operation log.
            task_type_id: The AI task type identifier.
            ai_output_reference: URI or storage key for the AI output.
            tier: The resolved risk tier (should be HIGH or MEDIUM).

        Returns:
            The created HITLCheckpoint instance.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=72)

        checkpoint = HITLCheckpoint(
            id=uuid.uuid4(),
            company_id=company_id,
            operation_id=operation_id,
            task_type_id=task_type_id,
            ai_output_reference=ai_output_reference,
            status=CheckpointStatus.PENDING.value,
            assigned_reviewer_role="system_admin,doc_admin",
            expires_at=expires_at,
        )
        self._session.add(checkpoint)
        await self._session.flush()

        return checkpoint

    # -----------------------------------------------------------------------
    # Private helper methods
    # -----------------------------------------------------------------------

    async def _resolve_task_type(
        self, task_type_id: str, company_id: int
    ) -> AITaskType:
        """Resolve a task type from the registry.

        Looks up both system-defined (company_id=NULL) and company-specific
        task types.

        Args:
            task_type_id: The task type identifier to look up.
            company_id: The company ID for company-specific task types.

        Returns:
            The AITaskType model instance.

        Raises:
            UnregisteredTaskTypeError: If the task type is not found.
        """
        stmt = select(AITaskType).where(
            AITaskType.task_type_id == task_type_id,
            AITaskType.is_active.is_(True),
            (AITaskType.company_id.is_(None)) | (AITaskType.company_id == company_id),
        )
        result = await self._session.execute(stmt)
        task_type = result.scalar_one_or_none()

        if task_type is None:
            raise UnregisteredTaskTypeError(task_type_id)

        return task_type

    async def _get_effective_tier(
        self, task_type_id: str, company_id: int, task_type: AITaskType
    ) -> RiskTier:
        """Resolve the effective risk tier for a task type and company.

        Checks for a company-specific override first, then falls back to
        the task type's default risk tier.

        Args:
            task_type_id: The task type identifier.
            company_id: The company ID.
            task_type: The resolved AITaskType model.

        Returns:
            The effective RiskTier.
        """
        # Check for company-specific override via active profile
        stmt = select(CompanyRiskProfile).where(
            CompanyRiskProfile.company_id == company_id,
            CompanyRiskProfile.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile is not None:
            # Look for an override for this task type
            override_stmt = select(RiskTierOverride).where(
                RiskTierOverride.profile_id == profile.id,
                RiskTierOverride.task_type_id == task_type_id,
            )
            override_result = await self._session.execute(override_stmt)
            override = override_result.scalar_one_or_none()

            if override is not None:
                return RiskTier(override.assigned_tier)

        # Fall back to default risk tier
        return RiskTier(task_type.default_risk_tier)

    async def _verify_hitl_reviewer_availability(self, company_id: int) -> None:
        """Verify at least one HITL reviewer exists for the company.

        A HITL reviewer is a user with system_admin or doc_admin role
        scoped to the given company (or global system roles).

        Args:
            company_id: The company ID to check.

        Raises:
            ControlUnavailableError: If no eligible reviewers exist.
        """
        # Query for users with system_admin or doc_admin roles for this company
        stmt = (
            select(User.id)
            .join(UserRole, User.id == UserRole.c.user_id)
            .join(Role, Role.id == UserRole.c.role_id)
            .where(
                User.is_active.is_(True),
                Role.name.in_(["system_admin", "doc_admin"]),
                (Role.company_id == company_id) | (Role.company_id.is_(None)),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        reviewer = result.scalar_one_or_none()

        if reviewer is None:
            raise ControlUnavailableError(
                control_name="hitl_reviewer_availability",
                reason=(
                    f"No users with system_admin or doc_admin role found for "
                    f"company {company_id}. At least one qualified reviewer is "
                    f"required for High/Medium tier operations."
                ),
            )

    async def _verify_audit_trail_writability(self) -> None:
        """Verify the audit trail is writable (can write to ai_operation_logs).

        Performs a lightweight check by verifying the session can execute
        a simple query against the ai_operation_logs table.

        Raises:
            ControlUnavailableError: If the audit trail is unreachable.
        """
        try:
            # Lightweight check: verify we can query the table
            stmt = select(AIOperationLog.id).limit(0)
            await self._session.execute(stmt)
        except Exception as e:
            raise ControlUnavailableError(
                control_name="audit_trail_writability",
                reason=(
                    f"Cannot verify audit trail writability. "
                    f"The ai_operation_logs table is unreachable: {e}"
                ),
            ) from e

    def _filter_by_audit_depth(
        self,
        data: dict | None,
        audit_depth: AuditDepth,
        is_input: bool,
    ) -> dict | None:
        """Filter operation data based on the tier's audit depth.

        - FULL: Store complete data (truncated to 50,000 chars if needed)
        - STANDARD: Store input summary (first 1000 chars) or full output
        - MINIMAL: Store None (no input/output data)

        Args:
            data: The raw input or output data.
            audit_depth: The audit depth for the tier.
            is_input: Whether this is input data (True) or output data (False).

        Returns:
            Filtered data dict or None.
        """
        if data is None:
            return None

        if audit_depth == AuditDepth.MINIMAL:
            return None

        if audit_depth == AuditDepth.STANDARD and is_input:
            # Store input summary (first 1000 characters of string representation)
            summary = str(data)[:1000]
            return {"summary": summary}

        if audit_depth == AuditDepth.FULL:
            # Truncate large values to 50,000 characters
            return self._truncate_data(data, max_chars=50000)

        # STANDARD output: full output (truncated to 50,000 chars)
        return self._truncate_data(data, max_chars=50000)

    def _truncate_data(self, data: dict, max_chars: int) -> dict:
        """Truncate string values in a dict to max_chars.

        Args:
            data: The data dict to truncate.
            max_chars: Maximum characters for string values.

        Returns:
            Dict with truncated string values.
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str) and len(value) > max_chars:
                result[key] = value[:max_chars] + "...[truncated]"
            else:
                result[key] = value
        return result
