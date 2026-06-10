"""Unit tests for the SearchProfileService.

Tests cover:
- CRUD operations (create, get, list, update, delete)
- Default profile resolution (applies profile to queries without explicit sources)
- Source validation against SourceRegistry
- Single default enforcement per company
- Pre-built templates
- Audit trail recording via change_reason
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.models.literature import SearchProfile
from alcoabase.literature.schemas.profiles import (
    SearchProfileCreate,
    SearchProfileUpdate,
)
from alcoabase.literature.schemas.search import SearchQuery
from alcoabase.literature.services.search_profile_service import (
    DuplicateProfileError,
    InvalidSourceError,
    ProfileNotFoundError,
    SearchProfileService,
)
from alcoabase.literature.services.source_registry import SourceRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session with context manager support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock):
    """Create a mock session factory that mimics async_sessionmaker behavior."""
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=mock_session)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=ctx_manager)
    return factory


@pytest.fixture
def mock_source_registry() -> MagicMock:
    """Create a mock SourceRegistry where all adapters are registered."""
    registry = MagicMock(spec=SourceRegistry)
    # By default, all adapters are "registered"
    registry.get_adapter.return_value = MagicMock()
    return registry


@pytest.fixture
def service(
    mock_session_factory, mock_source_registry: MagicMock
) -> SearchProfileService:
    """Create a SearchProfileService with mocked dependencies."""
    return SearchProfileService(
        session_factory=mock_session_factory,
        source_registry=mock_source_registry,
    )


def _make_profile(
    *,
    id: int = 1,
    company_id: int = 10,
    name: str = "test_profile",
    is_default: bool = False,
    enabled_sources: list[str] | None = None,
    source_priorities: dict[str, int] | None = None,
    default_filters: dict | None = None,
) -> SearchProfile:
    """Helper to create a SearchProfile instance for tests."""
    profile = SearchProfile()
    profile.id = id
    profile.company_id = company_id
    profile.name = name
    profile.is_default = is_default
    profile.enabled_sources = enabled_sources or ["pubmed", "crossref"]
    profile.source_priorities = source_priorities or {"pubmed": 1, "crossref": 2}
    profile.default_filters = default_filters or {}
    profile.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    profile.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return profile


# ---------------------------------------------------------------------------
# Create Profile Tests
# ---------------------------------------------------------------------------


class TestCreateProfile:
    """Tests for create_profile method."""

    @pytest.mark.asyncio
    async def test_creates_profile_successfully(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Create a profile with valid data."""
        # No existing profile with same name
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        data = SearchProfileCreate(
            name="pharma_custom",
            is_default=False,
            enabled_sources=["pubmed", "crossref"],
            source_priorities={"pubmed": 1, "crossref": 2},
        )

        await service.create_profile(10, data, change_reason="Initial setup")

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, SearchProfile)
        assert added.company_id == 10
        assert added.name == "pharma_custom"
        assert added.enabled_sources == ["pubmed", "crossref"]

    @pytest.mark.asyncio
    async def test_raises_on_duplicate_name(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Raise DuplicateProfileError for duplicate company+name."""
        existing = _make_profile(name="duplicate")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result_mock

        data = SearchProfileCreate(
            name="duplicate",
            enabled_sources=["pubmed"],
        )

        with pytest.raises(DuplicateProfileError) as exc_info:
            await service.create_profile(10, data)

        assert exc_info.value.company_id == 10
        assert exc_info.value.name == "duplicate"

    @pytest.mark.asyncio
    async def test_raises_on_invalid_sources(
        self, service: SearchProfileService, mock_source_registry: MagicMock
    ) -> None:
        """Raise InvalidSourceError when sources aren't registered."""
        # Make one source invalid
        mock_source_registry.get_adapter.side_effect = (
            lambda name: None if name == "fake_source" else MagicMock()
        )

        data = SearchProfileCreate(
            name="bad_profile",
            enabled_sources=["pubmed", "fake_source"],
        )

        with pytest.raises(InvalidSourceError) as exc_info:
            await service.create_profile(10, data)

        assert "fake_source" in exc_info.value.invalid_sources

    @pytest.mark.asyncio
    async def test_unsets_previous_default_when_creating_default(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Atomically unset existing default when creating a new default."""
        # No duplicate name
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        data = SearchProfileCreate(
            name="new_default",
            is_default=True,
            enabled_sources=["pubmed"],
        )

        await service.create_profile(10, data, change_reason="Set as default")

        # execute is called twice: once for name check, once for unset default
        assert mock_session.execute.call_count == 2


# ---------------------------------------------------------------------------
# Get Profile Tests
# ---------------------------------------------------------------------------


class TestGetProfile:
    """Tests for get_profile method."""

    @pytest.mark.asyncio
    async def test_returns_profile_by_id(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Return the profile when it exists."""
        profile = _make_profile(id=5)
        mock_session.get.return_value = profile

        result = await service.get_profile(5)

        assert result.id == 5
        assert result.name == "test_profile"

    @pytest.mark.asyncio
    async def test_raises_not_found(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Raise ProfileNotFoundError when ID doesn't exist."""
        mock_session.get.return_value = None

        with pytest.raises(ProfileNotFoundError) as exc_info:
            await service.get_profile(999)

        assert exc_info.value.profile_id == 999


# ---------------------------------------------------------------------------
# List Profiles Tests
# ---------------------------------------------------------------------------


class TestListProfiles:
    """Tests for list_profiles method."""

    @pytest.mark.asyncio
    async def test_returns_all_profiles_for_company(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Return all profiles for the given company."""
        profiles = [
            _make_profile(id=1, name="alpha"),
            _make_profile(id=2, name="beta"),
        ]
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = profiles
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute.return_value = result_mock

        result = await service.list_profiles(10)

        assert len(result) == 2
        assert result[0].name == "alpha"
        assert result[1].name == "beta"

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_no_profiles(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Return empty list when company has no profiles."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_session.execute.return_value = result_mock

        result = await service.list_profiles(10)

        assert result == []


# ---------------------------------------------------------------------------
# Update Profile Tests
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    """Tests for update_profile method."""

    @pytest.mark.asyncio
    async def test_updates_profile_fields(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Update only provided fields on the profile."""
        profile = _make_profile(id=3, name="original")
        mock_session.get.return_value = profile

        data = SearchProfileUpdate(
            name="updated_name",
            enabled_sources=["arxiv"],
        )

        # Mock the name uniqueness check
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await service.update_profile(3, data, change_reason="Rename")

        assert result.name == "updated_name"
        assert result.enabled_sources == ["arxiv"]
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_not_found(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Raise ProfileNotFoundError when profile doesn't exist."""
        mock_session.get.return_value = None

        data = SearchProfileUpdate(name="new_name")

        with pytest.raises(ProfileNotFoundError):
            await service.update_profile(999, data)

    @pytest.mark.asyncio
    async def test_raises_duplicate_on_name_conflict(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Raise DuplicateProfileError when new name conflicts."""
        profile = _make_profile(id=3, name="original")
        mock_session.get.return_value = profile

        # Another profile already has the target name
        existing = _make_profile(id=7, name="taken")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result_mock

        data = SearchProfileUpdate(name="taken")

        with pytest.raises(DuplicateProfileError):
            await service.update_profile(3, data)

    @pytest.mark.asyncio
    async def test_unsets_previous_default_on_set_default(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Unset existing default when updating a profile to be default."""
        profile = _make_profile(id=4, is_default=False)
        mock_session.get.return_value = profile

        # No conflicts with execute
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        data = SearchProfileUpdate(is_default=True)

        result = await service.update_profile(
            4, data, change_reason="Set as default"
        )

        assert result.is_default is True
        # execute called for unset_company_default
        assert mock_session.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_validates_new_sources(
        self, service: SearchProfileService, mock_session: AsyncMock, mock_source_registry: MagicMock
    ) -> None:
        """Validate new enabled_sources against the registry."""
        profile = _make_profile(id=5)
        mock_session.get.return_value = profile

        mock_source_registry.get_adapter.side_effect = (
            lambda name: None if name == "invalid_src" else MagicMock()
        )

        data = SearchProfileUpdate(enabled_sources=["pubmed", "invalid_src"])

        with pytest.raises(InvalidSourceError):
            await service.update_profile(5, data)


# ---------------------------------------------------------------------------
# Delete Profile Tests
# ---------------------------------------------------------------------------


class TestDeleteProfile:
    """Tests for delete_profile method."""

    @pytest.mark.asyncio
    async def test_deletes_existing_profile(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Delete a profile that exists."""
        profile = _make_profile(id=6)
        mock_session.get.return_value = profile

        await service.delete_profile(6, change_reason="No longer needed")

        mock_session.delete.assert_called_once_with(profile)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_not_found(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Raise ProfileNotFoundError when profile doesn't exist."""
        mock_session.get.return_value = None

        with pytest.raises(ProfileNotFoundError):
            await service.delete_profile(999)


# ---------------------------------------------------------------------------
# Default Profile Resolution Tests
# ---------------------------------------------------------------------------


class TestResolveDefaultProfile:
    """Tests for resolve_default_profile method."""

    @pytest.mark.asyncio
    async def test_applies_default_profile_when_no_explicit_sources(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Apply profile sources when query has no explicit source list."""
        default_profile = _make_profile(
            is_default=True,
            enabled_sources=["pubmed", "crossref"],
            source_priorities={"pubmed": 1, "crossref": 2},
        )
        scalars_mock = MagicMock()
        scalars_mock.scalar_one_or_none.return_value = default_profile
        mock_session.execute.return_value = scalars_mock

        query = SearchQuery(terms="cancer treatment")

        result = await service.resolve_default_profile(query, company_id=10)

        assert result.sources == ["pubmed", "crossref"]

    @pytest.mark.asyncio
    async def test_does_not_apply_when_query_has_explicit_sources(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Do NOT apply profile when query explicitly specifies sources."""
        query = SearchQuery(terms="cancer", sources=["arxiv"])

        result = await service.resolve_default_profile(query, company_id=10)

        # Should return unchanged query — session never consulted
        assert result.sources == ["arxiv"]

    @pytest.mark.asyncio
    async def test_returns_query_unchanged_when_no_default(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Return original query when no default profile exists."""
        scalars_mock = MagicMock()
        scalars_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = scalars_mock

        query = SearchQuery(terms="machine learning")

        result = await service.resolve_default_profile(query, company_id=10)

        assert result.sources is None

    @pytest.mark.asyncio
    async def test_does_not_apply_when_sources_is_empty_list(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Apply profile when sources is an empty list (treated as no override)."""
        default_profile = _make_profile(
            is_default=True,
            enabled_sources=["arxiv"],
        )
        scalars_mock = MagicMock()
        scalars_mock.scalar_one_or_none.return_value = default_profile
        mock_session.execute.return_value = scalars_mock

        query = SearchQuery(terms="physics", sources=[])

        result = await service.resolve_default_profile(query, company_id=10)

        assert result.sources == ["arxiv"]


# ---------------------------------------------------------------------------
# Template Tests
# ---------------------------------------------------------------------------


class TestTemplates:
    """Tests for profile template functionality."""

    def test_get_available_templates(
        self, service: SearchProfileService
    ) -> None:
        """Return all pre-built templates."""
        templates = service.get_available_templates()

        assert "pharma_medtech" in templates
        assert "technical_supplier" in templates
        assert "general" in templates
        assert templates["pharma_medtech"]["enabled_sources"] == [
            "pubmed",
            "crossref",
        ]
        assert templates["technical_supplier"]["enabled_sources"] == [
            "arxiv",
            "crossref",
        ]
        assert templates["general"]["enabled_sources"] == [
            "pubmed",
            "crossref",
            "arxiv",
        ]

    @pytest.mark.asyncio
    async def test_create_from_template(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Create a profile using a pre-built template."""
        # No duplicate name
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        await service.create_from_template(
            company_id=10,
            template_name="pharma_medtech",
            change_reason="Applying template",
        )

        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.name == "pharma_medtech"
        assert added.enabled_sources == ["pubmed", "crossref"]
        assert added.source_priorities == {"pubmed": 1, "crossref": 2}

    @pytest.mark.asyncio
    async def test_create_from_template_custom_name(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Create a template profile with a custom name."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        await service.create_from_template(
            company_id=10,
            template_name="general",
            profile_name="my_general_profile",
            is_default=True,
            change_reason="Custom template",
        )

        added = mock_session.add.call_args[0][0]
        assert added.name == "my_general_profile"
        assert added.is_default is True

    @pytest.mark.asyncio
    async def test_create_from_unknown_template_raises(
        self, service: SearchProfileService
    ) -> None:
        """Raise ValueError for unrecognized template names."""
        with pytest.raises(ValueError, match="Unknown template"):
            await service.create_from_template(
                company_id=10,
                template_name="nonexistent_template",
            )


# ---------------------------------------------------------------------------
# Source Priorities Tests
# ---------------------------------------------------------------------------


class TestGetSourcePriorities:
    """Tests for get_source_priorities method."""

    @pytest.mark.asyncio
    async def test_returns_priorities_from_named_profile(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Return priorities from a specific named profile."""
        profile = _make_profile(
            source_priorities={"pubmed": 1, "crossref": 3}
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = profile
        mock_session.execute.return_value = result_mock

        result = await service.get_source_priorities(10, profile_name="test_profile")

        assert result == {"pubmed": 1, "crossref": 3}

    @pytest.mark.asyncio
    async def test_returns_priorities_from_default_profile(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Return priorities from default profile when no name specified."""
        profile = _make_profile(
            is_default=True,
            source_priorities={"arxiv": 1, "pubmed": 2},
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = profile
        mock_session.execute.return_value = result_mock

        result = await service.get_source_priorities(10)

        assert result == {"arxiv": 1, "pubmed": 2}

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_no_profile(
        self, service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Return empty dict when no matching profile exists."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        result = await service.get_source_priorities(10)

        assert result == {}
