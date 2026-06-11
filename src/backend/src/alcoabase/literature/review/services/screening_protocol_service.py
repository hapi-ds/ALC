"""CRUD operations and versioning for Screening Protocols.

Manages creation, updates (with auto-versioning), activation, archival,
and validation of screening criteria definitions. All operations are
company-scoped and emit audit trail events via logging.

References:
    - Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.literature.review.exceptions import (
    InvalidStateTransitionError,
    NoCriteriaDefinedError,
    ProtocolNotFoundError,
)
from alcoabase.literature.review.models.screening_protocol import (
    ScreeningProtocol,
)
from alcoabase.literature.review.models.slr_review import SLRReview

logger = logging.getLogger(__name__)


class ScreeningProtocolService:
    """Manages Screening Protocol lifecycle with versioning.

    Responsibilities:
        - Create protocols with validated PICO + custom criteria
        - Auto-increment version on updates
        - Preserve old versions for in-progress reviews
        - Enforce at-least-one-criterion validation
        - Manage status transitions (draft → active → archived)
        - Company-scope all queries
        - Emit audit trail events via structured logging
    """

    # Valid status transitions
    _VALID_TRANSITIONS: dict[str, list[str]] = {
        "draft": ["active", "archived"],
        "active": ["archived"],
        "archived": [],
    }

    async def create_protocol(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        user_id: int,
        name: str,
        description: str | None = None,
        pico_criteria: dict[str, str | None] | None = None,
        inclusion_criteria: list[str] | None = None,
        exclusion_criteria: list[str] | None = None,
        publication_date_from: str | None = None,
        publication_date_to: str | None = None,
        allowed_publication_types: list[str] | None = None,
        allowed_languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Screening Protocol in draft status.

        Validates that at least one criterion is defined (PICO field,
        inclusion criterion, or exclusion criterion). Sets version to 1
        and status to "draft".

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            user_id: Creating user.
            name: Protocol name (1–200 chars).
            description: Optional description (max 5000 chars).
            pico_criteria: Dict with population, intervention, comparison, outcome.
            inclusion_criteria: List of keyword/regex patterns (max 20).
            exclusion_criteria: List of keyword/regex patterns (max 20).
            publication_date_from: Optional ISO-8601 start date.
            publication_date_to: Optional ISO-8601 end date.
            allowed_publication_types: Optional list of allowed types.
            allowed_languages: Optional list of ISO 639-1 codes.

        Returns:
            Dict with created protocol fields including id and version.

        Raises:
            NoCriteriaDefinedError: If no criteria are defined.
        """
        pico = pico_criteria or {}
        inc = inclusion_criteria or []
        exc = exclusion_criteria or []

        self._validate_has_criteria(pico, inc, exc)

        protocol = ScreeningProtocol(
            company_id=company_id,
            created_by=user_id,
            name=name,
            description=description,
            version=1,
            status="draft",
            pico_population=pico.get("population"),
            pico_intervention=pico.get("intervention"),
            pico_comparison=pico.get("comparison"),
            pico_outcome=pico.get("outcome"),
            inclusion_criteria=inc,
            exclusion_criteria=exc,
            publication_date_from=publication_date_from,
            publication_date_to=publication_date_to,
            allowed_publication_types=allowed_publication_types,
            allowed_languages=allowed_languages,
        )

        session.add(protocol)
        await session.flush()
        await session.refresh(protocol)

        logger.info(
            "Screening protocol created: id=%d, company_id=%d, user_id=%d, name='%s'",
            protocol.id,
            company_id,
            user_id,
            name,
        )

        return self._to_dict(protocol)

    async def update_protocol(
        self,
        session: AsyncSession,
        *,
        protocol_id: int,
        company_id: int,
        user_id: int,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update a protocol, auto-incrementing version.

        If the protocol is active with in-progress reviews, creates a new
        version while preserving the original for those reviews. Validates
        that criteria remain after the update.

        Args:
            protocol_id: Target protocol.
            company_id: Tenant scope.
            user_id: Updating user.
            **fields: Fields to update. Supported keys: name, description,
                pico_criteria, inclusion_criteria, exclusion_criteria,
                publication_date_from, publication_date_to,
                allowed_publication_types, allowed_languages.

        Returns:
            Updated protocol dict with new version number.

        Raises:
            ProtocolNotFoundError: If protocol not found in this company.
            NoCriteriaDefinedError: If update leaves zero criteria.
        """
        protocol = await self._get_protocol_or_raise(session, protocol_id, company_id)

        # Check if we need to create a new version (active + in-progress reviews)
        if protocol.status == "active":
            has_in_progress = await self._has_in_progress_reviews(session, protocol_id)
            if has_in_progress:
                return await self._create_new_version(
                    session,
                    protocol=protocol,
                    company_id=company_id,
                    user_id=user_id,
                    fields=fields,
                )

        # Apply updates directly
        self._apply_fields(protocol, fields)

        # Validate criteria remain
        pico = {
            "population": protocol.pico_population,
            "intervention": protocol.pico_intervention,
            "comparison": protocol.pico_comparison,
            "outcome": protocol.pico_outcome,
        }
        inc = protocol.inclusion_criteria or []
        exc = protocol.exclusion_criteria or []
        self._validate_has_criteria(pico, inc, exc, protocol_id=protocol_id)

        # Auto-increment version
        protocol.version += 1

        await session.flush()
        await session.refresh(protocol)

        logger.info(
            "Screening protocol updated: id=%d, version=%d, company_id=%d, user_id=%d",
            protocol.id,
            protocol.version,
            company_id,
            user_id,
        )

        return self._to_dict(protocol)

    async def activate_protocol(
        self,
        session: AsyncSession,
        *,
        protocol_id: int,
        company_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """Transition protocol from draft to active.

        Only draft protocols may be activated.

        Args:
            protocol_id: Target protocol.
            company_id: Tenant scope.
            user_id: Activating user.

        Returns:
            Updated protocol dict.

        Raises:
            ProtocolNotFoundError: If protocol not found in this company.
            InvalidStateTransitionError: If not in draft status.
        """
        protocol = await self._get_protocol_or_raise(session, protocol_id, company_id)

        if protocol.status != "draft":
            raise InvalidStateTransitionError(
                f"Cannot activate protocol in '{protocol.status}' status. "
                "Only draft protocols can be activated.",
                current_state=protocol.status,
                target_state="active",
            )

        protocol.status = "active"
        await session.flush()
        await session.refresh(protocol)

        logger.info(
            "Screening protocol activated: id=%d, company_id=%d, user_id=%d",
            protocol.id,
            company_id,
            user_id,
        )

        return self._to_dict(protocol)

    async def archive_protocol(
        self,
        session: AsyncSession,
        *,
        protocol_id: int,
        company_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """Soft-delete protocol by transitioning to archived.

        Both draft and active protocols may be archived.

        Args:
            protocol_id: Target protocol.
            company_id: Tenant scope.
            user_id: Archiving user.

        Returns:
            Updated protocol dict.

        Raises:
            ProtocolNotFoundError: If protocol not found in this company.
            InvalidStateTransitionError: If protocol is already archived.
        """
        protocol = await self._get_protocol_or_raise(session, protocol_id, company_id)

        if protocol.status == "archived":
            raise InvalidStateTransitionError(
                "Protocol is already archived.",
                current_state="archived",
                target_state="archived",
            )

        protocol.status = "archived"
        await session.flush()
        await session.refresh(protocol)

        logger.info(
            "Screening protocol archived: id=%d, company_id=%d, user_id=%d",
            protocol.id,
            company_id,
            user_id,
        )

        return self._to_dict(protocol)

    async def list_protocols(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List protocols for a company with pagination and optional status filter.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            status: Optional status filter (draft, active, archived).
            page: Page number (1-indexed).
            page_size: Items per page (1–100).

        Returns:
            Tuple of (protocols_list, total_count).
        """
        # Build base filter
        conditions = [ScreeningProtocol.company_id == company_id]
        if status is not None:
            conditions.append(ScreeningProtocol.status == status)

        # Count total
        count_stmt = select(func.count(ScreeningProtocol.id)).where(*conditions)
        total_result = await session.execute(count_stmt)
        total_count = total_result.scalar_one()

        # Fetch page
        offset = (page - 1) * page_size
        list_stmt = (
            select(ScreeningProtocol)
            .where(*conditions)
            .order_by(ScreeningProtocol.updated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(list_stmt)
        protocols = result.scalars().all()

        return [self._to_dict(p) for p in protocols], total_count

    async def get_protocol(
        self,
        session: AsyncSession,
        *,
        protocol_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Get full protocol details including version history.

        Args:
            session: Active async DB session.
            protocol_id: Target protocol.
            company_id: Tenant scope.

        Returns:
            Protocol dict with full details and version_history field.

        Raises:
            ProtocolNotFoundError: If not found in this company.
        """
        protocol = await self._get_protocol_or_raise(session, protocol_id, company_id)

        result = self._to_dict(protocol)

        # Include version history: all versions of protocols with the same
        # name in this company (supports the versioning pattern where new
        # versions are created as separate rows for in-progress reviews)
        history_stmt = (
            select(ScreeningProtocol)
            .where(
                ScreeningProtocol.company_id == company_id,
                ScreeningProtocol.name == protocol.name,
            )
            .order_by(ScreeningProtocol.version.desc())
        )
        history_result = await session.execute(history_stmt)
        history_rows = history_result.scalars().all()

        result["version_history"] = [
            {
                "id": p.id,
                "version": p.version,
                "status": p.status,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in history_rows
        ]

        return result

    # ─── Private Helpers ──────────────────────────────────────────────────

    async def _get_protocol_or_raise(
        self,
        session: AsyncSession,
        protocol_id: int,
        company_id: int,
    ) -> ScreeningProtocol:
        """Fetch a protocol by ID within company scope, or raise.

        Args:
            session: Active async DB session.
            protocol_id: Protocol primary key.
            company_id: Tenant scope.

        Returns:
            The ScreeningProtocol instance.

        Raises:
            ProtocolNotFoundError: If not found.
        """
        stmt = select(ScreeningProtocol).where(
            ScreeningProtocol.id == protocol_id,
            ScreeningProtocol.company_id == company_id,
        )
        result = await session.execute(stmt)
        protocol = result.scalar_one_or_none()

        if protocol is None:
            raise ProtocolNotFoundError(
                f"Screening protocol id={protocol_id} not found "
                f"in company_id={company_id}.",
                protocol_id=protocol_id,
                company_id=company_id,
            )

        return protocol

    async def _has_in_progress_reviews(
        self,
        session: AsyncSession,
        protocol_id: int,
    ) -> bool:
        """Check if a protocol has associated reviews in progress.

        A review is considered in-progress if its status is one of:
        screening_in_progress, human_review_in_progress.

        Args:
            session: Active async DB session.
            protocol_id: Protocol primary key.

        Returns:
            True if in-progress reviews exist.
        """
        in_progress_states = ("screening_in_progress", "human_review_in_progress")
        stmt = select(func.count(SLRReview.id)).where(
            SLRReview.protocol_id == protocol_id,
            SLRReview.status.in_(in_progress_states),
        )
        result = await session.execute(stmt)
        count = result.scalar_one()
        return count > 0

    async def _create_new_version(
        self,
        session: AsyncSession,
        *,
        protocol: ScreeningProtocol,
        company_id: int,
        user_id: int,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a new version of a protocol, preserving the old for in-progress reviews.

        The old protocol row is kept (in-progress reviews still reference it).
        A new row is created with the updated fields and incremented version.

        Args:
            session: Active async DB session.
            protocol: The existing protocol to version from.
            company_id: Tenant scope.
            user_id: User performing the update.
            fields: Fields to apply on the new version.

        Returns:
            Dict of the newly created protocol version.

        Raises:
            NoCriteriaDefinedError: If the new version has no criteria.
        """
        # Start from current values
        new_protocol = ScreeningProtocol(
            company_id=company_id,
            created_by=user_id,
            name=protocol.name,
            description=protocol.description,
            version=protocol.version + 1,
            status=protocol.status,
            pico_population=protocol.pico_population,
            pico_intervention=protocol.pico_intervention,
            pico_comparison=protocol.pico_comparison,
            pico_outcome=protocol.pico_outcome,
            inclusion_criteria=list(protocol.inclusion_criteria or []),
            exclusion_criteria=list(protocol.exclusion_criteria or []),
            publication_date_from=protocol.publication_date_from,
            publication_date_to=protocol.publication_date_to,
            allowed_publication_types=(
                list(protocol.allowed_publication_types)
                if protocol.allowed_publication_types
                else None
            ),
            allowed_languages=(
                list(protocol.allowed_languages) if protocol.allowed_languages else None
            ),
        )

        # Apply the update fields on the new version
        self._apply_fields(new_protocol, fields)

        # Validate criteria remain
        pico = {
            "population": new_protocol.pico_population,
            "intervention": new_protocol.pico_intervention,
            "comparison": new_protocol.pico_comparison,
            "outcome": new_protocol.pico_outcome,
        }
        inc = new_protocol.inclusion_criteria or []
        exc = new_protocol.exclusion_criteria or []
        self._validate_has_criteria(pico, inc, exc)

        session.add(new_protocol)
        await session.flush()
        await session.refresh(new_protocol)

        logger.info(
            "Screening protocol new version created: id=%d, version=%d, "
            "original_id=%d, company_id=%d, user_id=%d",
            new_protocol.id,
            new_protocol.version,
            protocol.id,
            company_id,
            user_id,
        )

        return self._to_dict(new_protocol)

    def _apply_fields(
        self, protocol: ScreeningProtocol, fields: dict[str, Any]
    ) -> None:
        """Apply update fields to a protocol instance.

        Supports: name, description, pico_criteria (dict), inclusion_criteria,
        exclusion_criteria, publication_date_from, publication_date_to,
        allowed_publication_types, allowed_languages.

        Args:
            protocol: Protocol instance to update.
            fields: Dict of fields to apply.
        """
        if "name" in fields and fields["name"] is not None:
            protocol.name = fields["name"]
        if "description" in fields:
            protocol.description = fields["description"]
        if "pico_criteria" in fields and fields["pico_criteria"] is not None:
            pico = fields["pico_criteria"]
            protocol.pico_population = pico.get("population")
            protocol.pico_intervention = pico.get("intervention")
            protocol.pico_comparison = pico.get("comparison")
            protocol.pico_outcome = pico.get("outcome")
        if "inclusion_criteria" in fields and fields["inclusion_criteria"] is not None:
            protocol.inclusion_criteria = fields["inclusion_criteria"]
        if "exclusion_criteria" in fields and fields["exclusion_criteria"] is not None:
            protocol.exclusion_criteria = fields["exclusion_criteria"]
        if "publication_date_from" in fields:
            protocol.publication_date_from = fields["publication_date_from"]
        if "publication_date_to" in fields:
            protocol.publication_date_to = fields["publication_date_to"]
        if "allowed_publication_types" in fields:
            protocol.allowed_publication_types = fields["allowed_publication_types"]
        if "allowed_languages" in fields:
            protocol.allowed_languages = fields["allowed_languages"]

    def _validate_has_criteria(
        self,
        pico: dict[str, str | None],
        inclusion_criteria: list[str],
        exclusion_criteria: list[str],
        *,
        protocol_id: int | None = None,
    ) -> None:
        """Validate that at least one criterion is defined.

        A valid protocol must have at least one of:
        - A non-empty PICO field (population, intervention, comparison, outcome)
        - At least one inclusion criterion
        - At least one exclusion criterion

        Args:
            pico: PICO criteria dict.
            inclusion_criteria: List of inclusion patterns.
            exclusion_criteria: List of exclusion patterns.
            protocol_id: Optional protocol ID (for error context on updates).

        Raises:
            NoCriteriaDefinedError: If no criteria are defined.
        """
        has_pico = any(v is not None and str(v).strip() != "" for v in pico.values())
        has_inclusion = len(inclusion_criteria) > 0
        has_exclusion = len(exclusion_criteria) > 0

        if not (has_pico or has_inclusion or has_exclusion):
            raise NoCriteriaDefinedError(
                "At least one screening criterion must be defined: "
                "provide a PICO field, inclusion criterion, or exclusion criterion.",
                protocol_id=protocol_id,
            )

    def _to_dict(self, protocol: ScreeningProtocol) -> dict[str, Any]:
        """Convert a ScreeningProtocol ORM instance to a plain dict.

        Args:
            protocol: ORM instance to serialize.

        Returns:
            Dict representation suitable for API responses.
        """
        return {
            "id": protocol.id,
            "company_id": protocol.company_id,
            "name": protocol.name,
            "description": protocol.description,
            "version": protocol.version,
            "status": protocol.status,
            "created_by": protocol.created_by,
            "pico_criteria": {
                "population": protocol.pico_population,
                "intervention": protocol.pico_intervention,
                "comparison": protocol.pico_comparison,
                "outcome": protocol.pico_outcome,
            },
            "inclusion_criteria": protocol.inclusion_criteria or [],
            "exclusion_criteria": protocol.exclusion_criteria or [],
            "publication_date_from": protocol.publication_date_from,
            "publication_date_to": protocol.publication_date_to,
            "allowed_publication_types": protocol.allowed_publication_types,
            "allowed_languages": protocol.allowed_languages,
            "created_at": (
                protocol.created_at.isoformat() if protocol.created_at else None
            ),
            "updated_at": (
                protocol.updated_at.isoformat() if protocol.updated_at else None
            ),
        }
