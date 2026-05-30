"""Risk Classification Service for AI Risk & Compliance Framework.

Encapsulates business logic for managing AI task type registry, company risk
profiles, tier resolution, and dashboard statistics.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 1.3, 1.4, 1.5, 1.6, 3.1–3.11, 9.7
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.risk_framework import (
    AIOperationLog,
    AITaskType,
    CompanyRiskProfile,
    HITLCheckpoint,
    RiskAssessmentRecord,
    RiskTier,
    RiskTierOverride,
)
from alcoabase.schemas.risk_framework import (
    AITaskTypeDetailResponse,
    AITaskTypeResponse,
    CompanyRiskProfileResponse,
    CreateProfileRequest,
    DashboardStatsResponse,
    PaginatedResult,
    RiskTierOverrideResponse,
    TierDefinitionResponse,
    UpdateProfileRequest,
)


# ---------------------------------------------------------------------------
# Tier-to-Control Mapping (Static Configuration)
# ---------------------------------------------------------------------------

TIER_DEFINITIONS: dict[str, TierDefinitionResponse] = {
    "high": TierDefinitionResponse(
        tier_level="high",
        display_name="High Risk",
        description=(
            "AI operations that generate GxP-regulated content entering "
            "approval workflows or produce compliance assessments influencing "
            "approval decisions."
        ),
        hitl_required=True,
        hitl_blocks_visibility=True,
        audit_depth="full",
        validations=[
            "format_validation",
            "cross_reference_check",
            "completeness_check",
        ],
        provenance_required=True,
        expiry_hours=72,
        rate_limit=None,
        output_label=None,
        enforcement_type="automatic",
    ),
    "medium": TierDefinitionResponse(
        tier_level="medium",
        display_name="Medium Risk",
        description=(
            "AI operations that identify affected documents or gaps but do "
            "not modify records. Output informs human decision-making."
        ),
        hitl_required=True,
        hitl_blocks_visibility=False,
        audit_depth="standard",
        validations=["format_validation"],
        provenance_required=False,
        expiry_hours=72,
        rate_limit=None,
        output_label="ai_assisted",
        enforcement_type="automatic",
    ),
    "low": TierDefinitionResponse(
        tier_level="low",
        display_name="Low Risk",
        description=(
            "AI operations that retrieve or summarize existing approved "
            "content without creating new regulated records."
        ),
        hitl_required=False,
        hitl_blocks_visibility=False,
        audit_depth="minimal",
        validations=[],
        provenance_required=False,
        expiry_hours=None,
        rate_limit=100,
        output_label="ai_generated",
        enforcement_type="automatic",
    ),
}


# Tier ordering for escalation/de-escalation comparison
_TIER_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def _is_deescalation(from_tier: str, to_tier: str) -> bool:
    """Determine if a tier change is a de-escalation (lowering risk).

    Args:
        from_tier: The current/default tier value.
        to_tier: The proposed new tier value.

    Returns:
        True if the change lowers the risk tier.
    """
    return _TIER_ORDER.get(to_tier, 0) < _TIER_ORDER.get(from_tier, 0)


class RiskClassificationService:
    """Manages AI task type registry, risk profiles, and tier resolution.

    All methods accept an AsyncSession for database operations, following
    the project's dependency injection pattern.
    """

    async def get_task_types(
        self,
        session: AsyncSession,
        company_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedResult[AITaskTypeResponse]:
        """Return paginated list of AI task types for a company.

        Includes both system-defined (global) task types and company-custom
        task types. Each entry includes the company-specific tier override
        if one exists in the active profile.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.
            limit: Maximum items per page (1-100).
            offset: Number of items to skip.

        Returns:
            PaginatedResult containing AITaskTypeResponse items.
        """
        # Clamp pagination parameters
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        # Build base query: system-defined OR company-custom for this company
        base_filter = or_(
            AITaskType.company_id.is_(None),
            AITaskType.company_id == company_id,
        )

        # Count total
        count_stmt = select(func.count()).select_from(AITaskType).where(base_filter)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Fetch paginated task types ordered by task_type_id ascending
        query = (
            select(AITaskType)
            .where(base_filter)
            .order_by(AITaskType.task_type_id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(query)
        task_types = result.scalars().all()

        # Get active profile overrides for this company
        overrides_map = await self._get_active_overrides_map(session, company_id)

        items = [
            AITaskTypeResponse(
                id=tt.id,
                task_type_id=tt.task_type_id,
                display_name=tt.display_name,
                module_reference=tt.module_reference,
                default_risk_tier=tt.default_risk_tier,
                company_tier=overrides_map.get(tt.task_type_id),
                is_active=tt.is_active,
                is_system_defined=tt.is_system_defined,
            )
            for tt in task_types
        ]

        return PaginatedResult[AITaskTypeResponse](
            items=items, total=total, limit=limit, offset=offset
        )

    async def get_task_type(
        self,
        session: AsyncSession,
        task_type_id: str,
        company_id: int,
    ) -> AITaskTypeDetailResponse:
        """Return full detail of a single AI task type.

        Includes risk factors, control set for the effective tier, and
        any company-specific tier override.

        Args:
            session: Active async database session.
            task_type_id: The task type string identifier.
            company_id: Company ID for tenant scoping.

        Returns:
            AITaskTypeDetailResponse with full details.

        Raises:
            ValueError: If the task_type_id is not found.
        """
        # Query task type (system-defined or company-custom)
        stmt = select(AITaskType).where(
            and_(
                AITaskType.task_type_id == task_type_id,
                or_(
                    AITaskType.company_id.is_(None),
                    AITaskType.company_id == company_id,
                ),
            )
        )
        result = await session.execute(stmt)
        tt = result.scalar_one_or_none()

        if tt is None:
            raise ValueError(
                f"AI task type '{task_type_id}' not found in registry."
            )

        # Get company tier override
        overrides_map = await self._get_active_overrides_map(session, company_id)
        company_tier = overrides_map.get(task_type_id)

        # Determine effective tier for control set lookup
        effective_tier = company_tier or tt.default_risk_tier
        control_set = TIER_DEFINITIONS.get(effective_tier)

        return AITaskTypeDetailResponse(
            id=tt.id,
            task_type_id=tt.task_type_id,
            display_name=tt.display_name,
            description=tt.description,
            module_reference=tt.module_reference,
            default_risk_tier=tt.default_risk_tier,
            company_tier=company_tier,
            risk_factors=tt.risk_factors or [],
            is_active=tt.is_active,
            is_system_defined=tt.is_system_defined,
            control_set=control_set,
            created_at=tt.created_at,
            updated_at=tt.updated_at,
        )

    async def get_effective_tier(
        self,
        session: AsyncSession,
        task_type_id: str,
        company_id: int,
    ) -> RiskTier:
        """Resolve the effective risk tier for a task type and company.

        Resolution order:
        1. Check active CompanyRiskProfile overrides for this task_type_id
        2. Fall back to AITaskType.default_risk_tier
        3. Raise ValueError if task_type_id not found in registry

        Args:
            session: Active async database session.
            task_type_id: The task type string identifier.
            company_id: Company ID for tenant scoping.

        Returns:
            The effective RiskTier enum value.

        Raises:
            ValueError: If the task_type_id is not found in the registry.
        """
        # Step 1: Check active profile overrides
        overrides_map = await self._get_active_overrides_map(session, company_id)
        if task_type_id in overrides_map:
            return RiskTier(overrides_map[task_type_id])

        # Step 2: Fall back to default tier from registry
        stmt = select(AITaskType.default_risk_tier).where(
            and_(
                AITaskType.task_type_id == task_type_id,
                or_(
                    AITaskType.company_id.is_(None),
                    AITaskType.company_id == company_id,
                ),
            )
        )
        result = await session.execute(stmt)
        default_tier = result.scalar_one_or_none()

        if default_tier is None:
            raise ValueError(
                f"AI task type '{task_type_id}' not found in registry."
            )

        return RiskTier(default_tier)

    async def create_profile(
        self,
        session: AsyncSession,
        company_id: int,
        data: CreateProfileRequest,
        user_id: int,
    ) -> CompanyRiskProfileResponse:
        """Create a new Company Risk Profile.

        Business rules:
        - Deactivates any previous active profile for the company
        - Validates all override task_type_ids exist in the registry
        - Enforces de-escalation rules (justification ≥50 chars,
          regulatory_reference, approved_by)
        - Creates RiskAssessmentRecord for every tier change

        Args:
            session: Active async database session.
            company_id: Company ID for the profile.
            data: Validated profile creation request.
            user_id: ID of the user creating the profile.

        Returns:
            CompanyRiskProfileResponse for the created profile.

        Raises:
            ValueError: If override task_type_ids are invalid or
                de-escalation rules are violated.
        """
        # 1. Validate all override task_type_ids exist in registry
        override_task_type_ids = [o.task_type_id for o in data.overrides]
        await self._validate_task_type_ids(
            session, override_task_type_ids, company_id
        )

        # 2. Get default tiers for all overridden task types to check
        #    escalation/de-escalation and create assessment records
        default_tiers = await self._get_default_tiers_map(
            session, override_task_type_ids, company_id
        )

        # 3. Validate de-escalation rules
        for override in data.overrides:
            default_tier = default_tiers.get(override.task_type_id)
            if default_tier and _is_deescalation(
                default_tier, override.assigned_tier
            ):
                self._validate_deescalation_override(override)

        # 4. Deactivate previous active profile
        await self._deactivate_active_profile(session, company_id)

        # 5. Create new profile
        profile = CompanyRiskProfile(
            company_id=company_id,
            profile_name=data.profile_name,
            description=data.description,
            regulatory_frameworks=data.regulatory_frameworks,
            is_active=True,
            created_by=user_id,
        )
        session.add(profile)
        await session.flush()

        # 6. Create tier overrides and assessment records
        override_models = []
        for override in data.overrides:
            override_model = RiskTierOverride(
                profile_id=profile.id,
                task_type_id=override.task_type_id,
                assigned_tier=override.assigned_tier,
                justification=override.justification,
                regulatory_reference=override.regulatory_reference,
                approved_by=override.approved_by,
                approval_date=(
                    datetime.now(timezone.utc)
                    if override.approved_by
                    else None
                ),
            )
            session.add(override_model)
            override_models.append(override_model)

            # Create RiskAssessmentRecord for tier change
            default_tier = default_tiers.get(override.task_type_id)
            if default_tier and default_tier != override.assigned_tier:
                assessment = RiskAssessmentRecord(
                    company_id=company_id,
                    task_type_id=override.task_type_id,
                    previous_tier=default_tier,
                    new_tier=override.assigned_tier,
                    assessor_user_id=user_id,
                    assessment_date=datetime.now(timezone.utc),
                    justification=override.justification,
                    regulatory_references=(
                        [override.regulatory_reference]
                        if override.regulatory_reference
                        else []
                    ),
                )
                session.add(assessment)

        await session.flush()

        # 7. Build response with overrides
        override_responses = [
            RiskTierOverrideResponse(
                id=om.id,
                task_type_id=om.task_type_id,
                assigned_tier=om.assigned_tier,
                justification=om.justification,
                regulatory_reference=om.regulatory_reference,
                approved_by=om.approved_by,
                approval_date=om.approval_date,
                created_at=om.created_at or datetime.now(timezone.utc),
            )
            for om in override_models
        ]

        return CompanyRiskProfileResponse(
            id=profile.id,
            company_id=profile.company_id,
            profile_name=profile.profile_name,
            description=profile.description,
            regulatory_frameworks=profile.regulatory_frameworks,
            is_active=profile.is_active,
            overrides=override_responses,
            created_by=profile.created_by,
            created_at=profile.created_at or datetime.now(timezone.utc),
            updated_at=profile.updated_at,
        )

    async def update_profile(
        self,
        session: AsyncSession,
        profile_id: UUID,
        company_id: int,
        data: UpdateProfileRequest,
    ) -> CompanyRiskProfileResponse:
        """Update an existing Company Risk Profile.

        Supports partial updates. If overrides are provided, replaces all
        existing overrides (full replacement semantics). Enforces the same
        de-escalation rules as profile creation.

        Args:
            session: Active async database session.
            profile_id: UUID of the profile to update.
            company_id: Company ID for tenant scoping.
            data: Validated partial update request.

        Returns:
            CompanyRiskProfileResponse for the updated profile.

        Raises:
            ValueError: If profile not found, doesn't belong to company,
                or validation fails.
        """
        # Fetch existing profile
        stmt = select(CompanyRiskProfile).where(
            and_(
                CompanyRiskProfile.id == profile_id,
                CompanyRiskProfile.company_id == company_id,
            )
        )
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile is None:
            raise ValueError(
                f"Profile '{profile_id}' not found for company {company_id}."
            )

        # Update scalar fields if provided
        if data.profile_name is not None:
            profile.profile_name = data.profile_name
        if data.description is not None:
            profile.description = data.description
        if data.regulatory_frameworks is not None:
            profile.regulatory_frameworks = data.regulatory_frameworks

        # Update overrides if provided (full replacement)
        if data.overrides is not None:
            override_task_type_ids = [o.task_type_id for o in data.overrides]
            await self._validate_task_type_ids(
                session, override_task_type_ids, company_id
            )

            default_tiers = await self._get_default_tiers_map(
                session, override_task_type_ids, company_id
            )

            # Validate de-escalation rules
            for override in data.overrides:
                default_tier = default_tiers.get(override.task_type_id)
                if default_tier and _is_deescalation(
                    default_tier, override.assigned_tier
                ):
                    self._validate_deescalation_override(override)

            # Delete existing overrides for this profile
            from sqlalchemy import delete

            await session.execute(
                delete(RiskTierOverride).where(
                    RiskTierOverride.profile_id == profile_id
                )
            )

            # Create new overrides and assessment records
            for override in data.overrides:
                override_model = RiskTierOverride(
                    profile_id=profile.id,
                    task_type_id=override.task_type_id,
                    assigned_tier=override.assigned_tier,
                    justification=override.justification,
                    regulatory_reference=override.regulatory_reference,
                    approved_by=override.approved_by,
                    approval_date=(
                        datetime.now(timezone.utc)
                        if override.approved_by
                        else None
                    ),
                )
                session.add(override_model)

                # Create RiskAssessmentRecord for tier change
                default_tier = default_tiers.get(override.task_type_id)
                if default_tier and default_tier != override.assigned_tier:
                    assessment = RiskAssessmentRecord(
                        company_id=company_id,
                        task_type_id=override.task_type_id,
                        previous_tier=default_tier,
                        new_tier=override.assigned_tier,
                        assessor_user_id=profile.created_by,
                        assessment_date=datetime.now(timezone.utc),
                        justification=override.justification,
                        regulatory_references=(
                            [override.regulatory_reference]
                            if override.regulatory_reference
                            else []
                        ),
                    )
                    session.add(assessment)

        await session.flush()

        # Reload profile with overrides for response
        return await self._build_profile_response(session, profile)

    async def get_active_profile(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> CompanyRiskProfileResponse | None:
        """Return the active Company Risk Profile for a company.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.

        Returns:
            CompanyRiskProfileResponse if an active profile exists, None otherwise.
        """
        stmt = select(CompanyRiskProfile).where(
            and_(
                CompanyRiskProfile.company_id == company_id,
                CompanyRiskProfile.is_active.is_(True),
            )
        )
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile is None:
            return None

        return await self._build_profile_response(session, profile)

    async def get_profile_history(
        self,
        session: AsyncSession,
        company_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedResult[CompanyRiskProfileResponse]:
        """Return paginated history of all profiles for a company.

        Includes both active and deactivated profiles, ordered by
        created_at descending (most recent first).

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.
            limit: Maximum items per page (1-100).
            offset: Number of items to skip.

        Returns:
            PaginatedResult containing CompanyRiskProfileResponse items.
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        # Count total profiles for this company
        count_stmt = (
            select(func.count())
            .select_from(CompanyRiskProfile)
            .where(CompanyRiskProfile.company_id == company_id)
        )
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Fetch paginated profiles
        query = (
            select(CompanyRiskProfile)
            .where(CompanyRiskProfile.company_id == company_id)
            .order_by(CompanyRiskProfile.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(query)
        profiles = result.scalars().all()

        items = []
        for profile in profiles:
            response = await self._build_profile_response(session, profile)
            items.append(response)

        return PaginatedResult[CompanyRiskProfileResponse](
            items=items, total=total, limit=limit, offset=offset
        )

    async def get_dashboard_stats(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> DashboardStatsResponse:
        """Return dashboard statistics for the risk framework.

        Computes:
        - Count of AI operations by tier in the last 30 days
        - Count of pending HITL checkpoints
        - Count of expired checkpoints
        - Count of blocked operations
        - Active profile name

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.

        Returns:
            DashboardStatsResponse with computed statistics.
        """
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        # Operations by tier (last 30 days)
        ops_stmt = (
            select(
                AIOperationLog.risk_tier,
                func.count().label("count"),
            )
            .where(
                and_(
                    AIOperationLog.company_id == company_id,
                    AIOperationLog.created_at >= thirty_days_ago,
                )
            )
            .group_by(AIOperationLog.risk_tier)
        )
        ops_result = await session.execute(ops_stmt)
        operations_by_tier: dict[str, int] = {
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for row in ops_result:
            if row.risk_tier in operations_by_tier:
                operations_by_tier[row.risk_tier] = row.count

        # Pending checkpoints
        pending_stmt = (
            select(func.count())
            .select_from(HITLCheckpoint)
            .where(
                and_(
                    HITLCheckpoint.company_id == company_id,
                    HITLCheckpoint.status == "pending",
                )
            )
        )
        pending_result = await session.execute(pending_stmt)
        pending_checkpoints = pending_result.scalar_one()

        # Expired checkpoints
        expired_stmt = (
            select(func.count())
            .select_from(HITLCheckpoint)
            .where(
                and_(
                    HITLCheckpoint.company_id == company_id,
                    HITLCheckpoint.status == "expired",
                )
            )
        )
        expired_result = await session.execute(expired_stmt)
        expired_checkpoints = expired_result.scalar_one()

        # Blocked operations (last 30 days)
        blocked_stmt = (
            select(func.count())
            .select_from(AIOperationLog)
            .where(
                and_(
                    AIOperationLog.company_id == company_id,
                    AIOperationLog.gate_result == "blocked",
                    AIOperationLog.created_at >= thirty_days_ago,
                )
            )
        )
        blocked_result = await session.execute(blocked_stmt)
        blocked_operations = blocked_result.scalar_one()

        # Active profile name
        profile_stmt = select(CompanyRiskProfile.profile_name).where(
            and_(
                CompanyRiskProfile.company_id == company_id,
                CompanyRiskProfile.is_active.is_(True),
            )
        )
        profile_result = await session.execute(profile_stmt)
        active_profile_name = profile_result.scalar_one_or_none()

        return DashboardStatsResponse(
            operations_by_tier=operations_by_tier,
            pending_checkpoints=pending_checkpoints,
            expired_checkpoints=expired_checkpoints,
            blocked_operations=blocked_operations,
            active_profile_name=active_profile_name,
        )

    # ------------------------------------------------------------------
    # Private helper methods
    # ------------------------------------------------------------------

    async def _get_active_overrides_map(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> dict[str, str]:
        """Get a mapping of task_type_id -> assigned_tier from active profile.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict mapping task_type_id to the overridden tier string.
            Empty dict if no active profile exists.
        """
        # Find active profile
        profile_stmt = select(CompanyRiskProfile.id).where(
            and_(
                CompanyRiskProfile.company_id == company_id,
                CompanyRiskProfile.is_active.is_(True),
            )
        )
        profile_result = await session.execute(profile_stmt)
        profile_id = profile_result.scalar_one_or_none()

        if profile_id is None:
            return {}

        # Get overrides for this profile
        overrides_stmt = select(
            RiskTierOverride.task_type_id,
            RiskTierOverride.assigned_tier,
        ).where(RiskTierOverride.profile_id == profile_id)
        overrides_result = await session.execute(overrides_stmt)

        return {row.task_type_id: row.assigned_tier for row in overrides_result}

    async def _validate_task_type_ids(
        self,
        session: AsyncSession,
        task_type_ids: list[str],
        company_id: int,
    ) -> None:
        """Validate that all task_type_ids exist in the registry.

        Args:
            session: Active async database session.
            task_type_ids: List of task type IDs to validate.
            company_id: Company ID for tenant scoping.

        Raises:
            ValueError: If any task_type_id is not found in the registry.
        """
        if not task_type_ids:
            return

        stmt = select(AITaskType.task_type_id).where(
            and_(
                AITaskType.task_type_id.in_(task_type_ids),
                or_(
                    AITaskType.company_id.is_(None),
                    AITaskType.company_id == company_id,
                ),
            )
        )
        result = await session.execute(stmt)
        found_ids = {row[0] for row in result}

        missing = set(task_type_ids) - found_ids
        if missing:
            raise ValueError(
                f"Invalid task_type_id values not found in registry: "
                f"{', '.join(sorted(missing))}"
            )

    async def _get_default_tiers_map(
        self,
        session: AsyncSession,
        task_type_ids: list[str],
        company_id: int,
    ) -> dict[str, str]:
        """Get default tiers for a list of task type IDs.

        Args:
            session: Active async database session.
            task_type_ids: List of task type IDs to look up.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict mapping task_type_id to its default_risk_tier string.
        """
        if not task_type_ids:
            return {}

        stmt = select(
            AITaskType.task_type_id,
            AITaskType.default_risk_tier,
        ).where(
            and_(
                AITaskType.task_type_id.in_(task_type_ids),
                or_(
                    AITaskType.company_id.is_(None),
                    AITaskType.company_id == company_id,
                ),
            )
        )
        result = await session.execute(stmt)
        return {row.task_type_id: row.default_risk_tier for row in result}

    def _validate_deescalation_override(self, override) -> None:
        """Validate that a de-escalation override meets all requirements.

        De-escalation requires:
        - justification ≥ 50 characters
        - regulatory_reference is provided (non-empty)
        - approved_by is provided

        Args:
            override: The RiskTierOverrideEntry to validate.

        Raises:
            ValueError: If any de-escalation requirement is not met.
        """
        errors: list[str] = []

        if len(override.justification) < 50:
            errors.append(
                f"De-escalation override for '{override.task_type_id}' "
                f"requires justification of at least 50 characters "
                f"(got {len(override.justification)})."
            )

        if not override.regulatory_reference:
            errors.append(
                f"De-escalation override for '{override.task_type_id}' "
                f"requires a regulatory_reference."
            )

        if not override.approved_by:
            errors.append(
                f"De-escalation override for '{override.task_type_id}' "
                f"requires an approved_by user."
            )

        if errors:
            raise ValueError(" ".join(errors))

    async def _deactivate_active_profile(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> None:
        """Deactivate the currently active profile for a company.

        Args:
            session: Active async database session.
            company_id: Company ID for tenant scoping.
        """
        stmt = (
            update(CompanyRiskProfile)
            .where(
                and_(
                    CompanyRiskProfile.company_id == company_id,
                    CompanyRiskProfile.is_active.is_(True),
                )
            )
            .values(is_active=False)
        )
        await session.execute(stmt)

    async def _build_profile_response(
        self,
        session: AsyncSession,
        profile: CompanyRiskProfile,
    ) -> CompanyRiskProfileResponse:
        """Build a CompanyRiskProfileResponse from a profile model.

        Loads the associated overrides and constructs the response schema.

        Args:
            session: Active async database session.
            profile: The CompanyRiskProfile model instance.

        Returns:
            CompanyRiskProfileResponse with overrides populated.
        """
        # Load overrides for this profile
        overrides_stmt = select(RiskTierOverride).where(
            RiskTierOverride.profile_id == profile.id
        )
        overrides_result = await session.execute(overrides_stmt)
        overrides = overrides_result.scalars().all()

        override_responses = [
            RiskTierOverrideResponse(
                id=o.id,
                task_type_id=o.task_type_id,
                assigned_tier=o.assigned_tier,
                justification=o.justification,
                regulatory_reference=o.regulatory_reference,
                approved_by=o.approved_by,
                approval_date=o.approval_date,
                created_at=o.created_at,
            )
            for o in overrides
        ]

        return CompanyRiskProfileResponse(
            id=profile.id,
            company_id=profile.company_id,
            profile_name=profile.profile_name,
            description=profile.description,
            regulatory_frameworks=profile.regulatory_frameworks,
            is_active=profile.is_active,
            overrides=override_responses,
            created_by=profile.created_by,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )
