"""Unit tests for AgentRegistryService YAML export/import methods.

Tests cover:
- export_agent_yaml() builds ordered YAML with canonical field ordering
- export_agent_yaml() omits null-valued fields
- export_agent_yaml() raises AgentNotFoundError for missing agents
- import_agent_yaml() rejects files exceeding 1 MB
- import_agent_yaml() rejects invalid YAML syntax
- import_agent_yaml() rejects unknown fields (via schema validation)
- import_agent_yaml() rejects name conflicts within company scope
- import_agent_yaml() rejects missing required fields
- import_agent_yaml() creates agent on valid input

References:
    - Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from alcoabase.models.agent import AgentDefinition as AgentDefinitionDB
from alcoabase.services.agent_registry import (
    AgentImportError,
    AgentNotFoundError,
    AgentRegistryService,
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


@pytest.fixture
def valid_v2_yaml() -> str:
    """A valid v2.0 agent definition as YAML string."""
    data = {
        "schema_version": "2.0",
        "name": "Test Agent",
        "description": "A test agent for import",
        "archetype": "Regulatory Compliance Auditor",
        "personality_profile": {
            "tone": "formal",
            "verbosity": "detailed",
            "strictness": 0.8,
            "domain_focus": ["compliance"],
            "communication_style": "structured",
        },
        "contextual_tuning": {
            "temperature": 0.2,
            "max_tokens": 4096,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
        "agent_type": "generation",
        "system_prompt": "You are a test agent.",
        "dspy_modules": [{"name": "analyze", "type": "ChainOfThought"}],
        "knowledge_scopes": {"tags": ["test"]},
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# export_agent_yaml tests
# ---------------------------------------------------------------------------


class TestExportAgentYaml:
    """Tests for AgentRegistryService.export_agent_yaml()."""

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_agent(
        self, service: AgentRegistryService
    ) -> None:
        """Raises AgentNotFoundError when agent doesn't exist."""
        with patch.object(service, "get_agent", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(AgentNotFoundError):
                await service.export_agent_yaml(999, 1)

    @pytest.mark.asyncio
    async def test_exports_with_canonical_field_ordering(
        self, service: AgentRegistryService
    ) -> None:
        """Exported YAML has fields in the canonical order."""
        yaml_content = yaml.dump(
            {
                "schema_version": "2.0",
                "name": "Export Test",
                "description": "Test description",
                "archetype": "Technical Writer",
                "personality_profile": {"tone": "casual", "verbosity": "concise", "strictness": 0.5, "domain_focus": ["docs"], "communication_style": "friendly"},
                "contextual_tuning": {"temperature": 0.4, "max_tokens": 4096, "top_p": 1.0, "frequency_penalty": 0.0, "presence_penalty": 0.0},
                "agent_type": "generation",
                "system_prompt": "You are a writer.",
                "dspy_modules": [{"name": "write", "type": "ChainOfThought"}],
                "knowledge_scopes": {"tags": ["docs"]},
            },
            default_flow_style=False,
        )

        mock_agent = MagicMock(spec=AgentDefinitionDB)
        mock_agent.yaml_content = yaml_content
        mock_agent.company_id = 1
        mock_agent.is_active = True

        with patch.object(service, "get_agent", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_agent
            result = await service.export_agent_yaml(1, 1)

        # Parse the result and check field ordering
        lines = result.strip().split("\n")
        field_keys = [line.split(":")[0] for line in lines if not line.startswith(" ") and not line.startswith("-")]

        expected_order = [
            "schema_version",
            "name",
            "description",
            "archetype",
            "personality_profile",
            "contextual_tuning",
            "agent_type",
            "system_prompt",
            "dspy_modules",
            "knowledge_scopes",
        ]
        # evaluation_rubric is omitted because it's null
        assert field_keys == expected_order

    @pytest.mark.asyncio
    async def test_omits_null_fields(
        self, service: AgentRegistryService
    ) -> None:
        """Null-valued fields are omitted from the exported YAML."""
        yaml_content = yaml.dump(
            {
                "schema_version": "2.0",
                "name": "Minimal Agent",
                "description": "Minimal",
                "archetype": "Technical Writer",
                "agent_type": "generation",
                "system_prompt": "You are minimal.",
                "dspy_modules": [{"name": "gen", "type": "ChainOfThought"}],
                "knowledge_scopes": {"tags": ["min"]},
            },
            default_flow_style=False,
        )

        mock_agent = MagicMock(spec=AgentDefinitionDB)
        mock_agent.yaml_content = yaml_content
        mock_agent.company_id = 1
        mock_agent.is_active = True

        with patch.object(service, "get_agent", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_agent
            result = await service.export_agent_yaml(1, 1)

        parsed = yaml.safe_load(result)
        # personality_profile, contextual_tuning, evaluation_rubric should be absent
        assert "personality_profile" not in parsed
        assert "contextual_tuning" not in parsed
        assert "evaluation_rubric" not in parsed


# ---------------------------------------------------------------------------
# import_agent_yaml tests
# ---------------------------------------------------------------------------


class TestImportAgentYaml:
    """Tests for AgentRegistryService.import_agent_yaml()."""

    @pytest.mark.asyncio
    async def test_rejects_file_exceeding_1mb(
        self, service: AgentRegistryService
    ) -> None:
        """Rejects YAML content exceeding 1 MB."""
        large_content = "a" * (1_048_576 + 1)
        with pytest.raises(AgentImportError) as exc_info:
            await service.import_agent_yaml(large_content, 1, 1)
        assert "1 MB" in exc_info.value.errors[0]

    @pytest.mark.asyncio
    async def test_rejects_invalid_yaml_syntax(
        self, service: AgentRegistryService
    ) -> None:
        """Rejects content that isn't valid YAML."""
        invalid_yaml = "{{invalid: yaml: [["
        with pytest.raises(AgentImportError) as exc_info:
            await service.import_agent_yaml(invalid_yaml, 1, 1)
        assert "YAML parse error" in exc_info.value.errors[0]

    @pytest.mark.asyncio
    async def test_rejects_non_mapping_yaml(
        self, service: AgentRegistryService
    ) -> None:
        """Rejects YAML that parses to a non-mapping type."""
        list_yaml = "- item1\n- item2\n"
        with pytest.raises(AgentImportError) as exc_info:
            await service.import_agent_yaml(list_yaml, 1, 1)
        assert "Expected YAML mapping" in exc_info.value.errors[0]

    @pytest.mark.asyncio
    async def test_rejects_unknown_fields(
        self, service: AgentRegistryService, valid_v2_yaml: str
    ) -> None:
        """Rejects YAML with fields not defined in the schema."""
        data = yaml.safe_load(valid_v2_yaml)
        data["unknown_field"] = "should not be here"
        yaml_with_unknown = yaml.dump(data, default_flow_style=False)

        with pytest.raises(AgentImportError) as exc_info:
            await service.import_agent_yaml(yaml_with_unknown, 1, 1)
        # Schema validation should catch the unknown field
        assert any("unknown_field" in e for e in exc_info.value.errors)

    @pytest.mark.asyncio
    async def test_rejects_missing_required_fields(
        self, service: AgentRegistryService
    ) -> None:
        """Rejects YAML missing required fields."""
        incomplete_yaml = yaml.dump(
            {"schema_version": "2.0", "name": "Incomplete"},
            default_flow_style=False,
        )
        with pytest.raises(AgentImportError) as exc_info:
            await service.import_agent_yaml(incomplete_yaml, 1, 1)
        assert len(exc_info.value.errors) > 0

    @pytest.mark.asyncio
    async def test_rejects_name_conflict(
        self, service: AgentRegistryService, valid_v2_yaml: str
    ) -> None:
        """Rejects import when an active agent with the same name exists."""
        # Mock the session to return an existing agent
        mock_existing = MagicMock(spec=AgentDefinitionDB)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        service._session_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        with pytest.raises(AgentImportError) as exc_info:
            await service.import_agent_yaml(valid_v2_yaml, 1, 1)
        assert "already exists" in exc_info.value.errors[0]

    @pytest.mark.asyncio
    async def test_creates_agent_on_valid_input(
        self, service: AgentRegistryService, valid_v2_yaml: str
    ) -> None:
        """Creates agent successfully when all validations pass."""
        # Mock _check_name_conflict to pass (no conflict)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        service._session_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        mock_agent = MagicMock(spec=AgentDefinitionDB)
        mock_agent.id = 42
        mock_agent.name = "Test Agent"

        with patch.object(service, "create_agent", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_agent
            result = await service.import_agent_yaml(valid_v2_yaml, 1, 1)

        assert result.id == 42
        # Verify create_agent was called with parsed data
        call_args = mock_create.call_args
        assert call_args[0][0]["name"] == "Test Agent"
        assert call_args[0][1] == 1  # company_id
        assert call_args[0][2] == 1  # user_id

    @pytest.mark.asyncio
    async def test_rejects_fields_with_invalid_values(
        self, service: AgentRegistryService
    ) -> None:
        """Rejects YAML with fields that have invalid types/values."""
        data = {
            "schema_version": "2.0",
            "name": "Bad Agent",
            "description": "Invalid values",
            "archetype": "Test",
            "personality_profile": {
                "tone": "formal",
                "verbosity": "invalid_enum_value",  # Invalid enum
                "strictness": 5.0,  # Out of range
                "domain_focus": ["test"],
                "communication_style": "normal",
            },
            "agent_type": "generation",
            "system_prompt": "Test",
            "dspy_modules": [{"name": "gen", "type": "ChainOfThought"}],
            "knowledge_scopes": {"tags": ["test"]},
        }
        yaml_content = yaml.dump(data, default_flow_style=False)

        with pytest.raises(AgentImportError) as exc_info:
            await service.import_agent_yaml(yaml_content, 1, 1)
        assert len(exc_info.value.errors) > 0
