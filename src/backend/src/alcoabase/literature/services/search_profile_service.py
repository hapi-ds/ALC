"""Search profile service for per-company search configuration management.

Provides CRUD operations for search profiles, default profile resolution
for queries, pre-built profile templates, and validation against the
source registry. Enforces single default per company atomically.

References:
    - Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.literature.models.literature import SearchProfile
from alcoabase.literature.schemas.profiles import (
    SearchProfileCreate,
    SearchProfileUpdate,
)
from alcoabase.literature.schemas.search import SearchQuery
from alcoabase.literature.services.source_registry import SourceRegistry

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ─── Pre-built Profile Templates ─────────────────────────────────────────────

PROFILE_TEMPLATES: dict[str, dict] = {
    "pharma_medtech": {
        "enabled_sources": ["pubmed", "crossref"],
        "source_priorities": {"pubmed": 1, "crossref": 2},
        "default_filters": {},
    },
    "technical_supplier": {
        "enabled_sources": ["arxiv", "crossref"],
        "source_priorities": {"arxiv": 1, "crossref": 2},
        "default_filters": {},
    },
    "general": {
        "enabled_sources": ["pubmed", "crossref", "arxiv"],
        "source_priorities": {"pubmed": 1, "crossref": 2, "arxiv": 3},
        "default_filters": {},
    },
}


# ─── Exceptions ───────────────────────────────────────────────────────────────


class ProfileNotFoundError(Exception):
    """Raised when a search profile cannot be found."""

    def __init__(self, profile_id: int) -> None:
        self.profile_id = profile_id
        super().__init__(f"Search profile with id={profile_id} not found.")


class DuplicateProfileError(Exception):
    """Raised when a profile name already exists for a company."""

    def __init__(self, company_id: int, name: str) -> None:
        self.company_id = company_id
        self.name = name
        super().__init__(
            f"Search profile '{name}' already exists for company_id={company_id}."
        )


class InvalidSourceError(Exception):
    """Raised when a referenced source adapter is not registered."""

    def __init__(self, invalid_sources: list[str]) -> None:
        self.invalid_sources = invalid_sources
        super().__init__(
            f"Source adapters not registered: {', '.join(invalid_sources)}"
        )


# ─── Search Profile Service ──────────────────────────────────────────────────


class SearchProfileService:
    """Manages per-company search profiles with CRUD, templates, and defaults.

    Provides:
    - Full CRUD for search profiles scoped to a company.
    - Default profile resolution: applies profile settings to queries
      that don't explicitly override sources.
    - Validation of referenced source adapters against the SourceRegistry.
    - Atomic enforcement of single default per company.
    - Pre-built templates for common regulatory verticals.

    Attributes:
        _session_factory: Async session factory for database access.
        _source_registry: SourceRegistry for validating adapter references.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        source_registry: SourceRegistry,
    ) -> None:
        """Initialize SearchProfileService.

        Args:
            session_factory: SQLAlchemy async session factory for creating
                database sessions.
            source_registry: SourceRegistry instance for validating that
                referenced source adapters are registered.
        """
        self._session_factory = session_factory
        self._source_registry = source_registry

    # ─── CRUD Operations ──────────────────────────────────────────────────

    async def create_profile(
        self,
        company_id: int,
        data: SearchProfileCreate,
        *,
        change_reason: str = "",
    ) -> SearchProfile:
        """Create a new search profile for a company.

        Validates that all referenced source adapters are registered.
        If is_default is True, atomically unsets any existing default
        for the company.

        Args:
            company_id: The company this profile belongs to.
            data: Profile creation data.
            change_reason: X-Change-Reason value for audit trail.

        Returns:
            The created SearchProfile instance.

        Raises:
            DuplicateProfileError: If a profile with the same name exists
                for this company.
            InvalidSourceError: If any enabled_sources are not registered
                in the SourceRegistry.
        """
        # Validate source adapters
        self._validate_sources(data.enabled_sources)

        async with self._session_factory() as session:
            # Check for duplicate name
            existing = await self._get_profile_by_name(
                session, company_id, data.name
            )
            if existing is not None:
                raise DuplicateProfileError(company_id, data.name)

            # Enforce single default per company
            if data.is_default:
                await self._unset_company_default(session, company_id)

            profile = SearchProfile(
                company_id=company_id,
                name=data.name,
                is_default=data.is_default,
                enabled_sources=data.enabled_sources,
                source_priorities=data.source_priorities,
                default_filters=data.default_filters,
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)

            logger.info(
                "Created search profile '%s' for company_id=%d "
                "(is_default=%s, reason='%s').",
                profile.name,
                company_id,
                profile.is_default,
                change_reason,
            )
            return profile

    async def get_profile(self, profile_id: int) -> SearchProfile:
        """Retrieve a search profile by ID.

        Args:
            profile_id: The profile's primary key.

        Returns:
            The SearchProfile instance.

        Raises:
            ProfileNotFoundError: If no profile with the given ID exists.
        """
        async with self._session_factory() as session:
            profile = await session.get(SearchProfile, profile_id)
            if profile is None:
                raise ProfileNotFoundError(profile_id)
            return profile

    async def list_profiles(self, company_id: int) -> list[SearchProfile]:
        """List all search profiles for a company.

        Args:
            company_id: The company to list profiles for.

        Returns:
            List of SearchProfile instances (may be empty).
        """
        async with self._session_factory() as session:
            stmt = (
                select(SearchProfile)
                .where(SearchProfile.company_id == company_id)
                .order_by(SearchProfile.name)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_profile(
        self,
        profile_id: int,
        data: SearchProfileUpdate,
        *,
        change_reason: str = "",
    ) -> SearchProfile:
        """Update an existing search profile.

        Only non-None fields in the update data are applied. If
        enabled_sources are updated, validates them against the registry.
        If is_default is set to True, atomically unsets any existing
        default for the company.

        Args:
            profile_id: The profile's primary key.
            data: Profile update data (partial).
            change_reason: X-Change-Reason value for audit trail.

        Returns:
            The updated SearchProfile instance.

        Raises:
            ProfileNotFoundError: If no profile with the given ID exists.
            DuplicateProfileError: If the new name conflicts with an
                existing profile for the same company.
            InvalidSourceError: If any enabled_sources are not registered.
        """
        async with self._session_factory() as session:
            profile = await session.get(SearchProfile, profile_id)
            if profile is None:
                raise ProfileNotFoundError(profile_id)

            # Validate new source list if provided
            if data.enabled_sources is not None:
                self._validate_sources(data.enabled_sources)

            # Check name uniqueness if changing name
            if data.name is not None and data.name != profile.name:
                existing = await self._get_profile_by_name(
                    session, profile.company_id, data.name
                )
                if existing is not None:
                    raise DuplicateProfileError(profile.company_id, data.name)

            # Enforce single default per company
            if data.is_default is True and not profile.is_default:
                await self._unset_company_default(session, profile.company_id)

            # Apply updates
            if data.name is not None:
                profile.name = data.name
            if data.is_default is not None:
                profile.is_default = data.is_default
            if data.enabled_sources is not None:
                profile.enabled_sources = data.enabled_sources
            if data.source_priorities is not None:
                profile.source_priorities = data.source_priorities
            if data.default_filters is not None:
                profile.default_filters = data.default_filters

            await session.commit()
            await session.refresh(profile)

            logger.info(
                "Updated search profile id=%d (name='%s', reason='%s').",
                profile_id,
                profile.name,
                change_reason,
            )
            return profile

    async def delete_profile(
        self,
        profile_id: int,
        *,
        change_reason: str = "",
    ) -> None:
        """Delete a search profile.

        Args:
            profile_id: The profile's primary key.
            change_reason: X-Change-Reason value for audit trail.

        Raises:
            ProfileNotFoundError: If no profile with the given ID exists.
        """
        async with self._session_factory() as session:
            profile = await session.get(SearchProfile, profile_id)
            if profile is None:
                raise ProfileNotFoundError(profile_id)

            profile_name = profile.name
            company_id = profile.company_id
            await session.delete(profile)
            await session.commit()

            logger.info(
                "Deleted search profile '%s' (id=%d, company_id=%d, reason='%s').",
                profile_name,
                profile_id,
                company_id,
                change_reason,
            )

    # ─── Default Profile Resolution ──────────────────────────────────────

    async def resolve_default_profile(
        self,
        query: SearchQuery,
        company_id: int,
    ) -> SearchQuery:
        """Apply the default profile's settings to a query if no explicit overrides.

        If the query already specifies sources (via the `sources` field),
        the profile is NOT applied — explicit overrides take precedence.

        If no default profile exists for the company, the query is returned
        unchanged.

        Args:
            query: The incoming search query.
            company_id: The company context for profile lookup.

        Returns:
            A new SearchQuery with profile settings applied, or the
            original query if no profile applies.
        """
        # If query explicitly specifies sources, don't apply profile
        if query.sources is not None and len(query.sources) > 0:
            return query

        # Find default profile for the company
        default_profile = await self._get_default_profile(company_id)
        if default_profile is None:
            return query

        # Apply the profile's enabled_sources and source_priorities
        # by creating a new query with the profile's sources applied
        updated_data = query.model_dump()
        updated_data["sources"] = default_profile.enabled_sources

        return SearchQuery.model_validate(updated_data)

    async def get_source_priorities(
        self,
        company_id: int,
        profile_name: str | None = None,
    ) -> dict[str, int]:
        """Get source priorities from a specific or default profile.

        Args:
            company_id: The company context.
            profile_name: Optional specific profile name to look up.
                If None, uses the default profile.

        Returns:
            Dict mapping source adapter names to priority values.
            Empty dict if no applicable profile exists.
        """
        if profile_name is not None:
            async with self._session_factory() as session:
                profile = await self._get_profile_by_name(
                    session, company_id, profile_name
                )
                if profile is not None:
                    return dict(profile.source_priorities)
                return {}

        default_profile = await self._get_default_profile(company_id)
        if default_profile is not None:
            return dict(default_profile.source_priorities)
        return {}

    # ─── Profile Templates ────────────────────────────────────────────────

    def get_available_templates(self) -> dict[str, dict]:
        """Return the available pre-built profile templates.

        Returns:
            Dict mapping template name to template configuration containing
            enabled_sources, source_priorities, and default_filters.
        """
        return dict(PROFILE_TEMPLATES)

    async def create_from_template(
        self,
        company_id: int,
        template_name: str,
        *,
        profile_name: str | None = None,
        is_default: bool = False,
        change_reason: str = "",
    ) -> SearchProfile:
        """Create a search profile from a pre-built template.

        Args:
            company_id: The company to create the profile for.
            template_name: Name of the template to use. Must be one of:
                "pharma_medtech", "technical_supplier", "general".
            profile_name: Optional custom name for the profile. Defaults
                to the template name if not provided.
            is_default: Whether this should be the company's default profile.
            change_reason: X-Change-Reason value for audit trail.

        Returns:
            The created SearchProfile instance.

        Raises:
            ValueError: If template_name is not a recognized template.
            DuplicateProfileError: If a profile with the resulting name
                already exists for this company.
            InvalidSourceError: If template sources are not registered.
        """
        if template_name not in PROFILE_TEMPLATES:
            available = ", ".join(sorted(PROFILE_TEMPLATES.keys()))
            msg = (
                f"Unknown template '{template_name}'. "
                f"Available templates: {available}"
            )
            raise ValueError(msg)

        template = PROFILE_TEMPLATES[template_name]
        name = profile_name if profile_name is not None else template_name

        create_data = SearchProfileCreate(
            name=name,
            is_default=is_default,
            enabled_sources=template["enabled_sources"],
            source_priorities=template["source_priorities"],
            default_filters=template["default_filters"],
        )

        return await self.create_profile(
            company_id, create_data, change_reason=change_reason
        )

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _validate_sources(self, sources: list[str]) -> None:
        """Validate that all source adapter names are registered.

        Args:
            sources: List of source adapter names to validate.

        Raises:
            InvalidSourceError: If any sources are not registered.
        """
        if not sources:
            return

        invalid_sources: list[str] = [
            source
            for source in sources
            if self._source_registry.get_adapter(source) is None
        ]

        if invalid_sources:
            raise InvalidSourceError(invalid_sources)

    async def _get_default_profile(
        self, company_id: int
    ) -> SearchProfile | None:
        """Retrieve the default profile for a company.

        Args:
            company_id: The company to look up.

        Returns:
            The default SearchProfile, or None if none is set.
        """
        async with self._session_factory() as session:
            stmt = select(SearchProfile).where(
                SearchProfile.company_id == company_id,
                SearchProfile.is_default == True,  # noqa: E712
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def _get_profile_by_name(
        self,
        session: AsyncSession,
        company_id: int,
        name: str,
    ) -> SearchProfile | None:
        """Look up a profile by company and name within an existing session.

        Args:
            session: Active async session.
            company_id: The company context.
            name: Profile name to search for.

        Returns:
            The matching SearchProfile, or None if not found.
        """
        stmt = select(SearchProfile).where(
            SearchProfile.company_id == company_id,
            SearchProfile.name == name,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _unset_company_default(
        self, session: AsyncSession, company_id: int
    ) -> None:
        """Atomically unset any existing default profile for a company.

        Uses a bulk UPDATE statement to ensure atomicity regardless of
        the number of profiles.

        Args:
            session: Active async session (changes are not committed here).
            company_id: The company whose default should be cleared.
        """
        stmt = (
            update(SearchProfile)
            .where(
                SearchProfile.company_id == company_id,
                SearchProfile.is_default == True,  # noqa: E712
            )
            .values(is_default=False)
        )
        await session.execute(stmt)
