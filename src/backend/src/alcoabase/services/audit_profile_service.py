"""Audit Profile Service for company-specific review configurations.

This module provides CRUD operations for audit profiles and validation
logic for agent assignments and quorum constraints.

References:
    - Requirement 4: Company-Specific Audit Profiles
    - Requirement 4.1: AuditProfile database fields
    - Requirement 4.2: Single default per company enforcement
    - Requirement 4.3: CRUD endpoints
    - Requirement 4.4: Agent assignment validation
    - Requirement 4.5: Quorum constraint enforcement
    - Requirement 4.6: Company-scoped operations
    - Requirement 4.7: Supported regulatory frameworks
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.agent import AgentDefinition
from alcoabase.models.audit_profile import AuditProfile
from alcoabase.models.company import CompanyAgentActivation

logger = logging.getLogger(__name__)

# Supported regulatory frameworks (Requirement 4.7)
SUPPORTED_FRAMEWORKS: list[str] = [
    "ISO 13485",
    "GMP",
    "GDP",
    "GLP",
    "GCP",
    "ISO 9001",
    "ISO 14001",
    "21 CFR Part 11",
    "EU GMP Annex 11",
    "IVDR",
]


class AuditProfileService:
    """Manages company-specific audit profiles.

    Provides CRUD operations for audit profiles with validation of
    agent assignments, quorum constraints, and default profile
    uniqueness enforcement.

    Attributes:
        _session_factory: SQLAlchemy async session factory for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the AuditProfileService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
        """
        self._session_factory = session_factory

    async def create_profile(self, data: dict, company_id: int) -> AuditProfile:
        """Create a new audit profile for a company.

        Validates agent assignments and quorum constraints before
        persisting. If is_default is True, atomically unsets any
        existing default profile for the company.

        Args:
            data: Profile data containing name, description,
                regulatory_frameworks, assigned_agent_ids, quorum,
                severity_thresholds, and is_default.
            company_id: The company this profile belongs to.

        Returns:
            The created AuditProfile instance.

        Raises:
            ValueError: If quorum exceeds assigned agent count or
                agent assignment validation fails.
        """
        assigned_agent_ids: list[int] = data.get("assigned_agent_ids", [])
        quorum: int = data.get("quorum", 1)

        # Enforce quorum ≤ len(assigned_agent_ids) (Requirement 4.5)
        if quorum > len(assigned_agent_ids):
            raise ValueError(
                f"Quorum ({quorum}) exceeds assigned agent count "
                f"({len(assigned_agent_ids)})"
            )

        # Validate agent assignments (Requirement 4.4)
        validation_errors = await self.validate_agent_assignments(
            assigned_agent_ids, company_id
        )
        if validation_errors:
            raise ValueError(
                f"Agent assignment validation failed: {'; '.join(validation_errors)}"
            )

        async with self._session_factory() as session:
            # Enforce single default per company (Requirement 4.2)
            is_default: bool = data.get("is_default", False)
            if is_default:
                await self._unset_existing_default(session, company_id)

            profile = AuditProfile(
                company_id=company_id,
                name=data["name"],
                description=data.get("description"),
                regulatory_frameworks=data.get("regulatory_frameworks", []),
                assigned_agent_ids=assigned_agent_ids,
                quorum=quorum,
                severity_thresholds=data.get("severity_thresholds", {
                    "critical": 25.0,
                    "major": 10.0,
                    "minor": 3.0,
                    "informational": 0.5,
                }),
                is_default=is_default,
                is_active=True,
            )

            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            session.expunge(profile)

        logger.info(
            "Created audit profile '%s' (id=%d) for company %d",
            profile.name,
            profile.id,
            company_id,
        )
        return profile

    async def get_profile(
        self, profile_id: int, company_id: int
    ) -> AuditProfile | None:
        """Get an audit profile by ID scoped to a company.

        Args:
            profile_id: The profile primary key.
            company_id: Company scope for multi-tenancy.

        Returns:
            The AuditProfile if found and active, else None.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuditProfile).where(
                    AuditProfile.id == profile_id,
                    AuditProfile.company_id == company_id,
                    AuditProfile.is_active == True,  # noqa: E712
                )
            )
            profile = result.scalar_one_or_none()
            if profile:
                session.expunge(profile)
            return profile

    async def get_default_profile(self, company_id: int) -> AuditProfile | None:
        """Get the default audit profile for a company.

        Args:
            company_id: Company scope for multi-tenancy.

        Returns:
            The default AuditProfile if one exists, else None.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuditProfile).where(
                    AuditProfile.company_id == company_id,
                    AuditProfile.is_default == True,  # noqa: E712
                    AuditProfile.is_active == True,  # noqa: E712
                )
            )
            profile = result.scalar_one_or_none()
            if profile:
                session.expunge(profile)
            return profile

    async def list_profiles(self, company_id: int) -> list[AuditProfile]:
        """List all active audit profiles for a company.

        Args:
            company_id: Company scope for multi-tenancy.

        Returns:
            List of active AuditProfile instances for the company.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuditProfile)
                .where(
                    AuditProfile.company_id == company_id,
                    AuditProfile.is_active == True,  # noqa: E712
                )
                .order_by(AuditProfile.created_at.desc())
            )
            profiles = list(result.scalars().all())
            for profile in profiles:
                session.expunge(profile)
            return profiles

    async def update_profile(
        self, profile_id: int, data: dict, company_id: int
    ) -> AuditProfile:
        """Update an existing audit profile.

        Validates agent assignments and quorum constraints before
        persisting. If is_default is being set to True, atomically
        unsets any existing default profile for the company.

        Args:
            profile_id: The profile primary key.
            data: Updated profile data fields.
            company_id: Company scope for multi-tenancy.

        Returns:
            The updated AuditProfile instance.

        Raises:
            ValueError: If profile not found, quorum exceeds assigned
                agent count, or agent assignment validation fails.
        """
        # Determine the agent IDs and quorum to validate
        assigned_agent_ids: list[int] | None = data.get("assigned_agent_ids")
        quorum: int | None = data.get("quorum")

        # We need to validate quorum against agent IDs
        # If only one is provided, we need the current value of the other
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuditProfile).where(
                    AuditProfile.id == profile_id,
                    AuditProfile.company_id == company_id,
                    AuditProfile.is_active == True,  # noqa: E712
                )
            )
            profile = result.scalar_one_or_none()
            if not profile:
                raise ValueError(
                    f"Audit profile {profile_id} not found for company {company_id}"
                )

            # Resolve effective values for validation
            effective_agent_ids = (
                assigned_agent_ids
                if assigned_agent_ids is not None
                else profile.assigned_agent_ids
            )
            effective_quorum = quorum if quorum is not None else profile.quorum

            # Enforce quorum ≤ len(assigned_agent_ids) (Requirement 4.5)
            if effective_quorum > len(effective_agent_ids):
                raise ValueError(
                    f"Quorum ({effective_quorum}) exceeds assigned agent count "
                    f"({len(effective_agent_ids)})"
                )

            # Validate agent assignments if they changed (Requirement 4.4)
            if assigned_agent_ids is not None:
                validation_errors = await self.validate_agent_assignments(
                    assigned_agent_ids, company_id
                )
                if validation_errors:
                    raise ValueError(
                        f"Agent assignment validation failed: "
                        f"{'; '.join(validation_errors)}"
                    )

            # Enforce single default per company (Requirement 4.2)
            is_default = data.get("is_default")
            if is_default is True and not profile.is_default:
                await self._unset_existing_default(session, company_id)

            # Apply updates
            if "name" in data:
                profile.name = data["name"]
            if "description" in data:
                profile.description = data["description"]
            if "regulatory_frameworks" in data:
                profile.regulatory_frameworks = data["regulatory_frameworks"]
            if assigned_agent_ids is not None:
                profile.assigned_agent_ids = assigned_agent_ids
            if quorum is not None:
                profile.quorum = quorum
            if "severity_thresholds" in data:
                profile.severity_thresholds = data["severity_thresholds"]
            if is_default is not None:
                profile.is_default = is_default

            await session.commit()
            await session.refresh(profile)
            session.expunge(profile)

        logger.info(
            "Updated audit profile '%s' (id=%d) for company %d",
            profile.name,
            profile.id,
            company_id,
        )
        return profile

    async def delete_profile(self, profile_id: int, company_id: int) -> None:
        """Soft-delete an audit profile by setting is_active to False.

        Args:
            profile_id: The profile primary key.
            company_id: Company scope for multi-tenancy.

        Raises:
            ValueError: If profile not found for the given company.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AuditProfile).where(
                    AuditProfile.id == profile_id,
                    AuditProfile.company_id == company_id,
                    AuditProfile.is_active == True,  # noqa: E712
                )
            )
            profile = result.scalar_one_or_none()
            if not profile:
                raise ValueError(
                    f"Audit profile {profile_id} not found for company {company_id}"
                )

            profile.is_active = False
            await session.commit()

        logger.info(
            "Soft-deleted audit profile id=%d for company %d",
            profile_id,
            company_id,
        )

    async def validate_agent_assignments(
        self, agent_ids: list[int], company_id: int
    ) -> list[str]:
        """Validate that all agent IDs are valid for assignment to a profile.

        Checks that each agent ID:
        1. Exists in the database
        2. Is active (is_active=True)
        3. Has agent_type "review"
        4. Belongs to the same company OR is a global agent activated
           for the company

        Args:
            agent_ids: List of agent definition IDs to validate.
            company_id: The company the profile belongs to.

        Returns:
            List of validation error messages. Empty list means all valid.
        """
        if not agent_ids:
            return ["At least one agent must be assigned"]

        errors: list[str] = []

        async with self._session_factory() as session:
            # Fetch all referenced agents in one query
            result = await session.execute(
                select(AgentDefinition).where(
                    AgentDefinition.id.in_(agent_ids)
                )
            )
            agents = {agent.id: agent for agent in result.scalars().all()}

            # Fetch active global agent activations for this company
            activation_result = await session.execute(
                select(CompanyAgentActivation.agent_definition_id).where(
                    CompanyAgentActivation.company_id == company_id,
                    CompanyAgentActivation.is_active == True,  # noqa: E712
                )
            )
            activated_global_ids: set[int] = set(
                activation_result.scalars().all()
            )

            for agent_id in agent_ids:
                agent = agents.get(agent_id)

                if agent is None:
                    errors.append(f"Agent {agent_id} does not exist")
                    continue

                if not agent.is_active:
                    errors.append(f"Agent {agent_id} ({agent.name}) is not active")
                    continue

                if agent.agent_type != "review":
                    errors.append(
                        f"Agent {agent_id} ({agent.name}) has type "
                        f"'{agent.agent_type}', expected 'review'"
                    )
                    continue

                # Check company ownership or global activation
                is_company_agent = agent.company_id == company_id
                is_global_activated = (
                    agent.company_id is None
                    and agent.id in activated_global_ids
                )

                if not is_company_agent and not is_global_activated:
                    errors.append(
                        f"Agent {agent_id} ({agent.name}) does not belong to "
                        f"company {company_id} and is not activated as a "
                        f"global agent for this company"
                    )

        return errors

    async def _unset_existing_default(
        self, session: AsyncSession, company_id: int
    ) -> None:
        """Unset the current default profile for a company.

        Called within an existing session transaction to ensure
        atomicity with the new default being set.

        Args:
            session: Active async DB session (within a transaction).
            company_id: The company whose default to unset.
        """
        result = await session.execute(
            select(AuditProfile).where(
                AuditProfile.company_id == company_id,
                AuditProfile.is_default == True,  # noqa: E712
                AuditProfile.is_active == True,  # noqa: E712
            )
        )
        existing_default = result.scalar_one_or_none()
        if existing_default:
            existing_default.is_default = False
            await session.flush()
            logger.info(
                "Unset default on profile '%s' (id=%d) for company %d",
                existing_default.name,
                existing_default.id,
                company_id,
            )
