"""Unit tests for AuditProfileService.

Tests cover:
- create_profile: success, quorum validation, agent validation, default enforcement
- get_profile: found, not found
- get_default_profile: found, not found
- list_profiles: returns active profiles for company
- update_profile: success, quorum validation, default switching
- delete_profile: soft-delete, not found
- validate_agent_assignments: all validation rules

References:
    - Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from alcoabase.services.audit_profile_service import (
    SUPPORTED_FRAMEWORKS,
    AuditProfileService,
)


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes that avoid SQLAlchemy instrumentation
# ---------------------------------------------------------------------------


def _make_agent_ns(
    agent_id: int,
    company_id: int | None = 1,
    agent_type: str = "review",
    is_active: bool = True,
    name: str = "Test Agent",
) -> SimpleNamespace:
    """Create a lightweight agent-like object for testing."""
    return SimpleNamespace(
        id=agent_id,
        company_id=company_id,
        agent_type=agent_type,
        is_active=is_active,
        name=name,
    )


def _make_profile_ns(
    profile_id: int = 1,
    company_id: int = 1,
    name: str = "Test Profile",
    is_default: bool = False,
    is_active: bool = True,
    assigned_agent_ids: list[int] | None = None,
    quorum: int = 1,
) -> SimpleNamespace:
    """Create a lightweight profile-like object for testing."""
    return SimpleNamespace(
        id=profile_id,
        company_id=company_id,
        name=name,
        description=None,
        regulatory_frameworks=["GMP"],
        assigned_agent_ids=assigned_agent_ids or [1, 2],
        quorum=quorum,
        severity_thresholds={"critical": 25.0, "major": 10.0},
        is_default=is_default,
        is_active=is_active,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        updated_at=None,
    )


class FakeScalarResult:
    """Fake result that supports scalar_one_or_none() and scalars().all()."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self._value, list):
            return self._value
        return [self._value] if self._value else []


class FakeSession:
    """Fake async session for testing without a real database."""

    def __init__(self):
        self.added: list = []
        self._execute_results: list = []
        self._committed = False
        self._flushed = False
        self._id_counter = 1

    def add(self, obj):
        obj.id = self._id_counter
        self._id_counter += 1
        self.added.append(obj)

    async def commit(self):
        self._committed = True

    async def flush(self):
        self._flushed = True

    async def refresh(self, obj):
        pass

    def expunge(self, obj):
        pass

    async def execute(self, stmt):
        if self._execute_results:
            return self._execute_results.pop(0)
        return FakeScalarResult(None)

    def set_execute_results(self, *results):
        self._execute_results = list(results)


@pytest.fixture
def fake_session():
    return FakeSession()


@pytest.fixture
def session_factory(fake_session):
    """Create a session factory that returns the fake session."""
    @asynccontextmanager
    async def _factory():
        yield fake_session

    return _factory


@pytest.fixture
def service(session_factory) -> AuditProfileService:
    """Create an AuditProfileService with fake session factory."""
    return AuditProfileService(session_factory=session_factory)


# ---------------------------------------------------------------------------
# SUPPORTED_FRAMEWORKS tests
# ---------------------------------------------------------------------------


class TestSupportedFrameworks:
    """Tests for the SUPPORTED_FRAMEWORKS constant."""

    def test_contains_expected_frameworks(self) -> None:
        """SUPPORTED_FRAMEWORKS contains all 10 expected frameworks."""
        assert len(SUPPORTED_FRAMEWORKS) == 10
        assert "ISO 13485" in SUPPORTED_FRAMEWORKS
        assert "GMP" in SUPPORTED_FRAMEWORKS
        assert "GDP" in SUPPORTED_FRAMEWORKS
        assert "GLP" in SUPPORTED_FRAMEWORKS
        assert "GCP" in SUPPORTED_FRAMEWORKS
        assert "ISO 9001" in SUPPORTED_FRAMEWORKS
        assert "ISO 14001" in SUPPORTED_FRAMEWORKS
        assert "21 CFR Part 11" in SUPPORTED_FRAMEWORKS
        assert "EU GMP Annex 11" in SUPPORTED_FRAMEWORKS
        assert "IVDR" in SUPPORTED_FRAMEWORKS


# ---------------------------------------------------------------------------
# validate_agent_assignments tests
# ---------------------------------------------------------------------------


class TestValidateAgentAssignments:
    """Tests for AuditProfileService.validate_agent_assignments()."""

    @pytest.mark.asyncio
    async def test_empty_agent_ids_returns_error(self, service) -> None:
        """Empty agent_ids list returns a validation error."""
        errors = await service.validate_agent_assignments([], company_id=1)
        assert len(errors) == 1
        assert "At least one agent" in errors[0]

    @pytest.mark.asyncio
    async def test_nonexistent_agent_returns_error(
        self, service, fake_session
    ) -> None:
        """Agent ID that doesn't exist returns an error."""
        fake_session.set_execute_results(
            FakeScalarResult([]),  # agents query - no agents found
            FakeScalarResult([]),  # activations query - scalars().all() returns []
        )
        errors = await service.validate_agent_assignments([999], company_id=1)
        assert len(errors) == 1
        assert "does not exist" in errors[0]

    @pytest.mark.asyncio
    async def test_inactive_agent_returns_error(
        self, service, fake_session
    ) -> None:
        """Inactive agent returns a validation error."""
        agent = _make_agent_ns(1, company_id=1, is_active=False)
        fake_session.set_execute_results(
            FakeScalarResult([agent]),  # agents query
            FakeScalarResult([]),  # activations query
        )
        errors = await service.validate_agent_assignments([1], company_id=1)
        assert len(errors) == 1
        assert "not active" in errors[0]

    @pytest.mark.asyncio
    async def test_non_review_agent_returns_error(
        self, service, fake_session
    ) -> None:
        """Agent with type != 'review' returns a validation error."""
        agent = _make_agent_ns(1, company_id=1, agent_type="generation")
        fake_session.set_execute_results(
            FakeScalarResult([agent]),  # agents query
            FakeScalarResult([]),  # activations query
        )
        errors = await service.validate_agent_assignments([1], company_id=1)
        assert len(errors) == 1
        assert "expected 'review'" in errors[0]

    @pytest.mark.asyncio
    async def test_agent_from_different_company_not_activated_returns_error(
        self, service, fake_session
    ) -> None:
        """Agent from another company (not global+activated) returns error."""
        agent = _make_agent_ns(1, company_id=2, agent_type="review")
        fake_session.set_execute_results(
            FakeScalarResult([agent]),  # agents query
            FakeScalarResult([]),  # activations query (not activated)
        )
        errors = await service.validate_agent_assignments([1], company_id=1)
        assert len(errors) == 1
        assert "does not belong to company" in errors[0]

    @pytest.mark.asyncio
    async def test_global_agent_activated_for_company_is_valid(
        self, service, fake_session
    ) -> None:
        """Global agent activated for the company passes validation."""
        agent = _make_agent_ns(1, company_id=None, agent_type="review")
        fake_session.set_execute_results(
            FakeScalarResult([agent]),  # agents query
            FakeScalarResult([1]),  # activations query (agent 1 is activated)
        )
        errors = await service.validate_agent_assignments([1], company_id=1)
        assert errors == []

    @pytest.mark.asyncio
    async def test_company_owned_review_agent_is_valid(
        self, service, fake_session
    ) -> None:
        """Company-owned review agent passes validation."""
        agent = _make_agent_ns(1, company_id=1, agent_type="review")
        fake_session.set_execute_results(
            FakeScalarResult([agent]),  # agents query
            FakeScalarResult([]),  # activations query
        )
        errors = await service.validate_agent_assignments([1], company_id=1)
        assert errors == []

    @pytest.mark.asyncio
    async def test_multiple_agents_mixed_validity(
        self, service, fake_session
    ) -> None:
        """Multiple agents with mixed validity returns errors for invalid ones."""
        valid_agent = _make_agent_ns(1, company_id=1, agent_type="review")
        invalid_agent = _make_agent_ns(2, company_id=1, agent_type="generation")
        fake_session.set_execute_results(
            FakeScalarResult([valid_agent, invalid_agent]),  # agents query
            FakeScalarResult([]),  # activations query
        )
        errors = await service.validate_agent_assignments([1, 2], company_id=1)
        assert len(errors) == 1
        assert "expected 'review'" in errors[0]


# ---------------------------------------------------------------------------
# create_profile tests
# ---------------------------------------------------------------------------


class TestCreateProfile:
    """Tests for AuditProfileService.create_profile()."""

    @pytest.mark.asyncio
    async def test_quorum_exceeds_agents_raises_error(self, service) -> None:
        """Quorum > len(assigned_agent_ids) raises ValueError."""
        data = {
            "name": "Test",
            "assigned_agent_ids": [1, 2],
            "quorum": 5,
            "regulatory_frameworks": ["GMP"],
        }
        with pytest.raises(ValueError, match="Quorum.*exceeds"):
            await service.create_profile(data, company_id=1)

    @pytest.mark.asyncio
    async def test_quorum_equal_to_agents_is_valid(
        self, service, fake_session
    ) -> None:
        """Quorum == len(assigned_agent_ids) is valid."""
        agent1 = _make_agent_ns(1, company_id=1, agent_type="review")
        agent2 = _make_agent_ns(2, company_id=1, agent_type="review")
        fake_session.set_execute_results(
            FakeScalarResult([agent1, agent2]),  # agents query (validate)
            FakeScalarResult([]),  # activations query (validate)
        )
        data = {
            "name": "Test",
            "assigned_agent_ids": [1, 2],
            "quorum": 2,
            "regulatory_frameworks": ["GMP"],
            "is_default": False,
        }
        profile = await service.create_profile(data, company_id=1)
        assert profile.quorum == 2

    @pytest.mark.asyncio
    async def test_invalid_agents_raises_error(
        self, service, fake_session
    ) -> None:
        """Invalid agent assignments raise ValueError."""
        fake_session.set_execute_results(
            FakeScalarResult([]),  # agents query - none found
            FakeScalarResult([]),  # activations query
        )
        data = {
            "name": "Test",
            "assigned_agent_ids": [999],
            "quorum": 1,
            "regulatory_frameworks": ["GMP"],
        }
        with pytest.raises(ValueError, match="Agent assignment validation failed"):
            await service.create_profile(data, company_id=1)

    @pytest.mark.asyncio
    async def test_successful_creation(self, service, fake_session) -> None:
        """Successful profile creation with valid data."""
        agent = _make_agent_ns(1, company_id=1, agent_type="review")
        fake_session.set_execute_results(
            FakeScalarResult([agent]),  # agents query (validate)
            FakeScalarResult([]),  # activations query (validate)
        )
        data = {
            "name": "GMP Profile",
            "description": "For GMP compliance",
            "assigned_agent_ids": [1],
            "quorum": 1,
            "regulatory_frameworks": ["GMP", "GDP"],
            "is_default": False,
        }
        profile = await service.create_profile(data, company_id=1)
        assert profile.name == "GMP Profile"
        assert profile.company_id == 1
        assert profile.quorum == 1
        assert profile.is_active is True

    @pytest.mark.asyncio
    async def test_create_default_unsets_previous(
        self, service, fake_session
    ) -> None:
        """Creating a default profile unsets the previous default."""
        agent = _make_agent_ns(1, company_id=1, agent_type="review")
        existing_default = _make_profile_ns(profile_id=10, is_default=True)

        fake_session.set_execute_results(
            FakeScalarResult([agent]),  # agents query (validate)
            FakeScalarResult([]),  # activations query (validate)
            FakeScalarResult(existing_default),  # unset default query
        )
        data = {
            "name": "New Default",
            "assigned_agent_ids": [1],
            "quorum": 1,
            "regulatory_frameworks": ["GMP"],
            "is_default": True,
        }
        profile = await service.create_profile(data, company_id=1)
        assert profile.is_default is True
        # The existing default should have been unset
        assert existing_default.is_default is False


# ---------------------------------------------------------------------------
# delete_profile tests
# ---------------------------------------------------------------------------


class TestDeleteProfile:
    """Tests for AuditProfileService.delete_profile()."""

    @pytest.mark.asyncio
    async def test_soft_delete_sets_inactive(self, service, fake_session) -> None:
        """Soft-delete sets is_active to False."""
        profile = _make_profile_ns(profile_id=1)
        fake_session.set_execute_results(FakeScalarResult(profile))

        await service.delete_profile(profile_id=1, company_id=1)
        assert profile.is_active is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises_error(
        self, service, fake_session
    ) -> None:
        """Deleting a non-existent profile raises ValueError."""
        fake_session.set_execute_results(FakeScalarResult(None))

        with pytest.raises(ValueError, match="not found"):
            await service.delete_profile(profile_id=999, company_id=1)


# ---------------------------------------------------------------------------
# get_profile tests
# ---------------------------------------------------------------------------


class TestGetProfile:
    """Tests for AuditProfileService.get_profile()."""

    @pytest.mark.asyncio
    async def test_returns_profile_when_found(
        self, service, fake_session
    ) -> None:
        """Returns the profile when it exists."""
        profile = _make_profile_ns(profile_id=5, name="Found Profile")
        fake_session.set_execute_results(FakeScalarResult(profile))

        result = await service.get_profile(profile_id=5, company_id=1)
        assert result is not None
        assert result.name == "Found Profile"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, service, fake_session
    ) -> None:
        """Returns None when profile doesn't exist."""
        fake_session.set_execute_results(FakeScalarResult(None))

        result = await service.get_profile(profile_id=999, company_id=1)
        assert result is None


# ---------------------------------------------------------------------------
# get_default_profile tests
# ---------------------------------------------------------------------------


class TestGetDefaultProfile:
    """Tests for AuditProfileService.get_default_profile()."""

    @pytest.mark.asyncio
    async def test_returns_default_when_exists(
        self, service, fake_session
    ) -> None:
        """Returns the default profile when one exists."""
        profile = _make_profile_ns(profile_id=3, is_default=True)
        fake_session.set_execute_results(FakeScalarResult(profile))

        result = await service.get_default_profile(company_id=1)
        assert result is not None
        assert result.is_default is True

    @pytest.mark.asyncio
    async def test_returns_none_when_no_default(
        self, service, fake_session
    ) -> None:
        """Returns None when no default profile exists."""
        fake_session.set_execute_results(FakeScalarResult(None))

        result = await service.get_default_profile(company_id=1)
        assert result is None


# ---------------------------------------------------------------------------
# list_profiles tests
# ---------------------------------------------------------------------------


class TestListProfiles:
    """Tests for AuditProfileService.list_profiles()."""

    @pytest.mark.asyncio
    async def test_returns_all_active_profiles(
        self, service, fake_session
    ) -> None:
        """Returns all active profiles for the company."""
        profiles = [
            _make_profile_ns(profile_id=1, name="Profile A"),
            _make_profile_ns(profile_id=2, name="Profile B"),
        ]
        fake_session.set_execute_results(FakeScalarResult(profiles))

        result = await service.list_profiles(company_id=1)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(
        self, service, fake_session
    ) -> None:
        """Returns empty list when no profiles exist."""
        fake_session.set_execute_results(FakeScalarResult([]))

        result = await service.list_profiles(company_id=1)
        assert result == []


# ---------------------------------------------------------------------------
# update_profile tests
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    """Tests for AuditProfileService.update_profile()."""

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises_error(
        self, service, fake_session
    ) -> None:
        """Updating a non-existent profile raises ValueError."""
        fake_session.set_execute_results(FakeScalarResult(None))

        with pytest.raises(ValueError, match="not found"):
            await service.update_profile(
                profile_id=999, data={"name": "New"}, company_id=1
            )

    @pytest.mark.asyncio
    async def test_update_quorum_exceeds_agents_raises_error(
        self, service, fake_session
    ) -> None:
        """Updating quorum > agent count raises ValueError."""
        profile = _make_profile_ns(
            profile_id=1, assigned_agent_ids=[1, 2], quorum=2
        )
        fake_session.set_execute_results(FakeScalarResult(profile))

        with pytest.raises(ValueError, match="Quorum.*exceeds"):
            await service.update_profile(
                profile_id=1, data={"quorum": 5}, company_id=1
            )

    @pytest.mark.asyncio
    async def test_update_name_succeeds(self, service, fake_session) -> None:
        """Updating just the name succeeds without re-validating agents."""
        profile = _make_profile_ns(profile_id=1, name="Old Name")
        fake_session.set_execute_results(FakeScalarResult(profile))

        result = await service.update_profile(
            profile_id=1, data={"name": "New Name"}, company_id=1
        )
        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_update_to_default_unsets_previous(
        self, service, fake_session
    ) -> None:
        """Setting is_default=True unsets the previous default."""
        profile = _make_profile_ns(profile_id=1, is_default=False)
        existing_default = _make_profile_ns(profile_id=2, is_default=True)

        fake_session.set_execute_results(
            FakeScalarResult(profile),  # get profile query
            FakeScalarResult(existing_default),  # unset default query
        )

        result = await service.update_profile(
            profile_id=1, data={"is_default": True}, company_id=1
        )
        assert result.is_default is True
        assert existing_default.is_default is False
