"""Unit tests for AgentRegistryService archetype operations.

Tests cover:
- list_archetypes() loads all 6 predefined archetypes
- list_archetypes() returns empty list for missing directory
- create_from_archetype() raises ArchetypeNotFoundError for unknown archetype
- create_from_archetype() deep-merges overrides with archetype defaults
- create_from_archetype() validates merged result against v2.0 schema

References:
    - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.agent_registry import (
    AgentRegistryService,
    AgentValidationError,
    ArchetypeDefinition,
    ArchetypeNotFoundError,
)
from alcoabase.services.schema_validator import SchemaValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def schema_validator() -> SchemaValidator:
    """Create a SchemaValidator with real schema files."""
    schema_dir = Path(__file__).parent.parent / "../../agents/schema"
    return SchemaValidator(schema_dir)


@pytest.fixture
def archetypes_dir() -> Path:
    """Path to the archetypes directory."""
    return Path(__file__).parent.parent / "../../agents/archetypes"


@pytest.fixture
def service(schema_validator: SchemaValidator, archetypes_dir: Path) -> AgentRegistryService:
    """Create an AgentRegistryService with mock session factory."""
    return AgentRegistryService(
        session_factory=MagicMock(),
        schema_validator=schema_validator,
        agents_dir=Path(__file__).parent.parent / "../../agents/examples",
        archetypes_dir=archetypes_dir,
    )


# ---------------------------------------------------------------------------
# list_archetypes tests
# ---------------------------------------------------------------------------


class TestListArchetypes:
    """Tests for AgentRegistryService.list_archetypes()."""

    def test_loads_all_six_archetypes(self, service: AgentRegistryService) -> None:
        """All 6 predefined archetypes are loaded from the directory."""
        archetypes = service.list_archetypes()
        assert len(archetypes) == 6

    def test_archetype_names_match_expected(self, service: AgentRegistryService) -> None:
        """Loaded archetypes have the expected archetype identifiers."""
        archetypes = service.list_archetypes()
        names = {a["archetype"] for a in archetypes}
        expected = {
            "Regulatory Compliance Auditor",
            "Data Integrity Specialist",
            "Process Safety Reviewer",
            "Statistical Methods Auditor",
            "Technical Writer",
            "Educational Specialist",
        }
        assert names == expected

    def test_archetype_has_required_fields(self, service: AgentRegistryService) -> None:
        """Each archetype has all required fields populated."""
        archetypes = service.list_archetypes()
        for arch in archetypes:
            assert arch["archetype"]
            assert arch["name"]
            assert arch["description"]
            assert arch["schema_version"] == "2.0"
            assert arch["personality_profile"]
            assert arch["contextual_tuning"]
            assert arch["system_prompt"]
            assert arch["dspy_modules"]
            assert arch["knowledge_scopes"]

    def test_regulatory_auditor_values(self, service: AgentRegistryService) -> None:
        """Regulatory Compliance Auditor has correct default values."""
        archetypes = service.list_archetypes()
        auditor = next(a for a in archetypes if a["archetype"] == "Regulatory Compliance Auditor")
        assert auditor["personality_profile"]["strictness"] == 0.9
        assert auditor["contextual_tuning"]["temperature"] == 0.1
        assert auditor["personality_profile"]["verbosity"] == "detailed"

    def test_technical_writer_values(self, service: AgentRegistryService) -> None:
        """Technical Writer has correct default values."""
        archetypes = service.list_archetypes()
        writer = next(a for a in archetypes if a["archetype"] == "Technical Writer")
        assert writer["personality_profile"]["strictness"] == 0.5
        assert writer["contextual_tuning"]["temperature"] == 0.4
        assert writer["personality_profile"]["verbosity"] == "detailed"

    def test_educational_specialist_values(self, service: AgentRegistryService) -> None:
        """Educational Specialist has correct default values."""
        archetypes = service.list_archetypes()
        edu = next(a for a in archetypes if a["archetype"] == "Educational Specialist")
        assert edu["personality_profile"]["strictness"] == 0.3
        assert edu["contextual_tuning"]["temperature"] == 0.6
        assert edu["personality_profile"]["verbosity"] == "moderate"

    def test_returns_empty_for_missing_directory(
        self, schema_validator: SchemaValidator
    ) -> None:
        """Returns empty list when archetypes directory doesn't exist."""
        svc = AgentRegistryService(
            session_factory=MagicMock(),
            schema_validator=schema_validator,
            agents_dir=Path("/nonexistent"),
            archetypes_dir=Path("/nonexistent/archetypes"),
        )
        assert svc.list_archetypes() == []


# ---------------------------------------------------------------------------
# create_from_archetype tests
# ---------------------------------------------------------------------------


class TestCreateFromArchetype:
    """Tests for AgentRegistryService.create_from_archetype()."""

    @pytest.mark.asyncio
    async def test_unknown_archetype_raises_error(
        self, service: AgentRegistryService
    ) -> None:
        """Unknown archetype_id raises ArchetypeNotFoundError with available list."""
        with pytest.raises(ArchetypeNotFoundError) as exc_info:
            await service.create_from_archetype(
                "Nonexistent Archetype", "Test Agent", None, 1, 1
            )
        assert "Nonexistent Archetype" in str(exc_info.value)
        assert len(exc_info.value.available) == 6

    @pytest.mark.asyncio
    async def test_creates_agent_from_archetype_no_overrides(
        self, service: AgentRegistryService, archetypes_dir: Path
    ) -> None:
        """Creates agent from archetype with no overrides, using archetype defaults."""
        # Mock the DB session for create_agent
        mock_agent = MagicMock()
        mock_agent.id = 1
        mock_agent.name = "My Auditor"
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service._session_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        # Patch create_agent to avoid actual DB interaction
        with patch.object(service, "create_agent", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_agent
            result = await service.create_from_archetype(
                "Regulatory Compliance Auditor", "My Auditor", None, 1, 1
            )

        # Verify create_agent was called with correct data
        call_args = mock_create.call_args
        agent_data = call_args[0][0]
        assert agent_data["name"] == "My Auditor"
        assert agent_data["archetype"] == "Regulatory Compliance Auditor"
        assert agent_data["personality_profile"]["strictness"] == 0.9
        assert agent_data["contextual_tuning"]["temperature"] == 0.1
        assert call_args[0][1] == 1  # company_id
        assert call_args[0][2] == 1  # user_id

    @pytest.mark.asyncio
    async def test_deep_merges_overrides(
        self, service: AgentRegistryService
    ) -> None:
        """Overrides are deep-merged with archetype defaults."""
        overrides = {
            "personality_profile": {"strictness": 0.7},
            "contextual_tuning": {"temperature": 0.3},
            "description": "Custom description",
        }

        with patch.object(service, "create_agent", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(id=1)
            await service.create_from_archetype(
                "Regulatory Compliance Auditor", "Custom Auditor", overrides, 1, 1
            )

        agent_data = mock_create.call_args[0][0]
        # Overridden values
        assert agent_data["personality_profile"]["strictness"] == 0.7
        assert agent_data["contextual_tuning"]["temperature"] == 0.3
        assert agent_data["description"] == "Custom description"
        # Preserved defaults (not overridden)
        assert agent_data["personality_profile"]["verbosity"] == "detailed"
        assert agent_data["personality_profile"]["tone"] == "formal and authoritative"
        assert agent_data["contextual_tuning"]["max_tokens"] == 8192

    @pytest.mark.asyncio
    async def test_validation_failure_raises_error(
        self, service: AgentRegistryService
    ) -> None:
        """Invalid overrides that break schema validation raise AgentValidationError."""
        # Override strictness to an invalid value (> 1.0)
        overrides = {
            "personality_profile": {"strictness": 5.0},
        }

        with pytest.raises(AgentValidationError):
            await service.create_from_archetype(
                "Regulatory Compliance Auditor", "Bad Agent", overrides, 1, 1
            )
