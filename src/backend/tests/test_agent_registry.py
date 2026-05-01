"""Unit and property-based tests for Agent Registry service.

Tests cover:
- YAML validation (rejects invalid, accepts valid)
- Agent YAML portability round-trip (export then import)
- Schema version checking
- Agent import/export
- Agent selection audit trail

References:
    - Task 15.9: Property-based tests: YAML validation
    - Task 15.10: Property-based tests: agent YAML portability round-trip
"""

import json
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from alcoabase.services.agent_registry import (
    AgentDefinition,
    AgentRegistry,
    AgentValidationError,
    UnsupportedSchemaVersionError,
    SUPPORTED_SCHEMA_VERSIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def schema_path() -> Path:
    """Path to the agent definition JSON Schema."""
    return Path(__file__).parent.parent / "../../agents/schema/agent-definition-v1.json"


@pytest.fixture
def registry(schema_path: Path) -> AgentRegistry:
    """Create an AgentRegistry with the real schema."""
    return AgentRegistry(schema_path=schema_path)


@pytest.fixture
def valid_agent_yaml() -> str:
    """A valid agent definition YAML string."""
    return """
schema_version: "1.0"
agent_type: "generation"
name: "Test Agent"
description: "A test agent for unit testing"
system_prompt: "You are a helpful test agent."
dspy_modules:
  - name: "generate"
    type: "ChainOfThought"
    params:
      temperature: 0.3
      max_tokens: 2048
knowledge_scopes:
  tags: ["SOP", "Test"]
example_usage: "Use this agent for testing purposes."
"""


@pytest.fixture
def examples_dir() -> Path:
    """Path to the example agents directory."""
    return Path(__file__).parent.parent / "../../agents/examples"


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def valid_agent_data_strategy():
    """Strategy for generating valid agent definition data."""
    return st.fixed_dictionaries({
        "schema_version": st.just("1.0"),
        "agent_type": st.just("generation"),
        "name": st.text(min_size=1, max_size=100, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters=" -_"
        )).filter(lambda x: x.strip()),
        "description": st.text(min_size=1, max_size=500, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters=" -_.,!?"
        )).filter(lambda x: x.strip()),
        "system_prompt": st.text(min_size=1, max_size=200, alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters=" -_.,!?"
        )).filter(lambda x: x.strip()),
        "dspy_modules": st.lists(
            st.fixed_dictionaries({
                "name": st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_"),
                "type": st.sampled_from(["ChainOfThought", "ColBERTv2Retriever", "Predict"]),
            }),
            min_size=1,
            max_size=3,
        ),
        "knowledge_scopes": st.fixed_dictionaries({
            "tags": st.lists(
                st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"),
                min_size=1,
                max_size=5,
            ),
        }),
    })


def invalid_agent_data_strategy():
    """Strategy for generating invalid agent definition data."""
    return st.one_of(
        # Missing required field 'name'
        st.fixed_dictionaries({
            "schema_version": st.just("1.0"),
            "description": st.just("Missing name"),
            "system_prompt": st.just("prompt"),
            "dspy_modules": st.just([{"name": "m", "type": "t"}]),
            "knowledge_scopes": st.just({"tags": ["SOP"]}),
        }),
        # Missing required field 'system_prompt'
        st.fixed_dictionaries({
            "schema_version": st.just("1.0"),
            "name": st.just("Test"),
            "description": st.just("desc"),
            "dspy_modules": st.just([{"name": "m", "type": "t"}]),
            "knowledge_scopes": st.just({"tags": ["SOP"]}),
        }),
        # Empty dspy_modules array
        st.fixed_dictionaries({
            "schema_version": st.just("1.0"),
            "name": st.just("Test"),
            "description": st.just("desc"),
            "system_prompt": st.just("prompt"),
            "dspy_modules": st.just([]),
            "knowledge_scopes": st.just({"tags": ["SOP"]}),
        }),
        # Invalid schema version
        st.fixed_dictionaries({
            "schema_version": st.just("99.0"),
            "name": st.just("Test"),
            "description": st.just("desc"),
            "system_prompt": st.just("prompt"),
            "dspy_modules": st.just([{"name": "m", "type": "t"}]),
            "knowledge_scopes": st.just({"tags": ["SOP"]}),
        }),
        # Missing knowledge_scopes
        st.fixed_dictionaries({
            "schema_version": st.just("1.0"),
            "name": st.just("Test"),
            "description": st.just("desc"),
            "system_prompt": st.just("prompt"),
            "dspy_modules": st.just([{"name": "m", "type": "t"}]),
        }),
    )


# ---------------------------------------------------------------------------
# Unit Tests: YAML Validation
# ---------------------------------------------------------------------------


class TestYAMLValidation:
    """Tests for YAML agent definition validation."""

    def test_valid_yaml_accepted(
        self, registry: AgentRegistry, valid_agent_yaml: str
    ) -> None:
        """Valid YAML agent definition is accepted."""
        agent = registry.import_agent(valid_agent_yaml.encode("utf-8"))

        assert agent.name == "Test Agent"
        assert agent.agent_type == "generation"
        assert agent.schema_version == "1.0"

    def test_invalid_yaml_missing_name_rejected(
        self, registry: AgentRegistry
    ) -> None:
        """YAML missing required 'name' field is rejected."""
        invalid_yaml = """
schema_version: "1.0"
description: "Missing name field"
system_prompt: "prompt"
dspy_modules:
  - name: "gen"
    type: "ChainOfThought"
knowledge_scopes:
  tags: ["SOP"]
"""
        with pytest.raises(AgentValidationError) as exc_info:
            registry.import_agent(invalid_yaml.encode("utf-8"))

        assert len(exc_info.value.errors) > 0

    def test_unsupported_schema_version_rejected(
        self, registry: AgentRegistry
    ) -> None:
        """YAML with unsupported schema version is rejected."""
        invalid_yaml = """
schema_version: "99.0"
name: "Test"
description: "desc"
system_prompt: "prompt"
dspy_modules:
  - name: "gen"
    type: "ChainOfThought"
knowledge_scopes:
  tags: ["SOP"]
"""
        with pytest.raises(UnsupportedSchemaVersionError) as exc_info:
            registry.import_agent(invalid_yaml.encode("utf-8"))

        assert "99.0" in str(exc_info.value)

    def test_empty_dspy_modules_rejected(
        self, registry: AgentRegistry
    ) -> None:
        """YAML with empty dspy_modules array is rejected."""
        invalid_yaml = """
schema_version: "1.0"
name: "Test"
description: "desc"
system_prompt: "prompt"
dspy_modules: []
knowledge_scopes:
  tags: ["SOP"]
"""
        with pytest.raises(AgentValidationError):
            registry.import_agent(invalid_yaml.encode("utf-8"))

    def test_malformed_yaml_rejected(
        self, registry: AgentRegistry
    ) -> None:
        """Malformed YAML is rejected with descriptive error."""
        malformed = b"{{{{not valid yaml: [["
        with pytest.raises(AgentValidationError) as exc_info:
            registry.import_agent(malformed)

        assert "YAML parse error" in exc_info.value.errors[0] or len(exc_info.value.errors) > 0

    def test_load_example_agents(
        self, registry: AgentRegistry, examples_dir: Path
    ) -> None:
        """Example agent YAML files load successfully."""
        if not examples_dir.exists():
            pytest.skip("Examples directory not found")

        agents = registry.load_agents(examples_dir)
        assert len(agents) >= 3  # sop-drafting, deviation-report, protocol-summary


# ---------------------------------------------------------------------------
# Unit Tests: Import/Export
# ---------------------------------------------------------------------------


class TestImportExport:
    """Tests for agent import and export."""

    def test_export_produces_valid_yaml(
        self, registry: AgentRegistry, valid_agent_yaml: str
    ) -> None:
        """Exported YAML is valid and parseable."""
        agent = registry.import_agent(valid_agent_yaml.encode("utf-8"))
        exported = registry.export_agent(agent.id)

        # Should be valid YAML
        data = yaml.safe_load(exported)
        assert data["name"] == "Test Agent"
        assert data["schema_version"] == "1.0"

    def test_export_nonexistent_agent_raises(
        self, registry: AgentRegistry
    ) -> None:
        """Exporting a non-existent agent raises KeyError."""
        with pytest.raises(KeyError):
            registry.export_agent("nonexistent-id")

    def test_import_registers_agent(
        self, registry: AgentRegistry, valid_agent_yaml: str
    ) -> None:
        """Imported agent is registered and retrievable."""
        agent = registry.import_agent(valid_agent_yaml.encode("utf-8"))

        retrieved = registry.get_agent(agent.id)
        assert retrieved is not None
        assert retrieved.name == agent.name


# ---------------------------------------------------------------------------
# Unit Tests: Schema Version Checking
# ---------------------------------------------------------------------------


class TestSchemaVersionChecking:
    """Tests for schema version checking."""

    def test_supported_version_accepted(
        self, registry: AgentRegistry
    ) -> None:
        """Supported schema version returns True."""
        assert registry.check_schema_version("1.0") is True

    def test_unsupported_version_rejected(
        self, registry: AgentRegistry
    ) -> None:
        """Unsupported schema version returns False."""
        assert registry.check_schema_version("2.0") is False
        assert registry.check_schema_version("0.1") is False
        assert registry.check_schema_version("") is False


# ---------------------------------------------------------------------------
# Unit Tests: Agent Selection Audit Trail
# ---------------------------------------------------------------------------


class TestAgentSelectionAudit:
    """Tests for agent selection audit trail."""

    def test_selection_recorded(
        self, registry: AgentRegistry, valid_agent_yaml: str
    ) -> None:
        """Agent selection is recorded in audit trail."""
        agent = registry.import_agent(valid_agent_yaml.encode("utf-8"))

        event = registry.record_selection(
            user_id=42, agent_id=agent.id, purpose="generation"
        )

        assert event.user_id == 42
        assert event.agent_id == agent.id
        assert event.agent_name == "Test Agent"
        assert event.purpose == "generation"

    def test_selection_log_accumulates(
        self, registry: AgentRegistry, valid_agent_yaml: str
    ) -> None:
        """Multiple selections accumulate in the log."""
        agent = registry.import_agent(valid_agent_yaml.encode("utf-8"))

        registry.record_selection(user_id=1, agent_id=agent.id, purpose="query")
        registry.record_selection(user_id=2, agent_id=agent.id, purpose="generation")

        log = registry.get_selection_log()
        assert len(log) == 2


# ---------------------------------------------------------------------------
# Property-Based Tests: YAML Validation (Task 15.9)
# ---------------------------------------------------------------------------


class TestYAMLValidationProperty:
    """Property-based tests for YAML validation.

    **Validates: Requirements 19 AC 3, 20 AC 1-2**
    """

    @given(data=valid_agent_data_strategy())
    @settings(max_examples=50)
    def test_valid_definitions_always_accepted(
        self, data: dict
    ) -> None:
        """All valid agent definitions are accepted by the registry.

        **Validates: Requirements 19 AC 3**
        """
        schema_path = Path(__file__).parent.parent / "../../agents/schema/agent-definition-v1.json"
        registry = AgentRegistry(schema_path=schema_path)

        yaml_bytes = yaml.dump(data).encode("utf-8")
        agent = registry.import_agent(yaml_bytes)

        assert agent.name == data["name"]
        assert agent.schema_version == "1.0"

    @given(data=invalid_agent_data_strategy())
    @settings(max_examples=50)
    def test_invalid_definitions_always_rejected(
        self, data: dict
    ) -> None:
        """All invalid agent definitions are rejected by the registry.

        **Validates: Requirements 20 AC 1-2**
        """
        schema_path = Path(__file__).parent.parent / "../../agents/schema/agent-definition-v1.json"
        registry = AgentRegistry(schema_path=schema_path)

        yaml_bytes = yaml.dump(data).encode("utf-8")

        with pytest.raises((AgentValidationError, UnsupportedSchemaVersionError)):
            registry.import_agent(yaml_bytes)


# ---------------------------------------------------------------------------
# Property-Based Tests: Agent YAML Portability Round-Trip (Task 15.10)
# ---------------------------------------------------------------------------


class TestAgentPortabilityRoundTrip:
    """Property-based tests for agent YAML portability.

    **Validates: Requirements 20 AC 4**
    """

    @given(data=valid_agent_data_strategy())
    @settings(max_examples=50)
    def test_export_import_roundtrip_preserves_definition(
        self, data: dict
    ) -> None:
        """Export then import produces an equivalent agent definition.

        **Validates: Requirements 20 AC 4**
        """
        schema_path = Path(__file__).parent.parent / "../../agents/schema/agent-definition-v1.json"
        registry = AgentRegistry(schema_path=schema_path)

        # Import original
        yaml_bytes = yaml.dump(data).encode("utf-8")
        original = registry.import_agent(yaml_bytes)

        # Export
        exported = registry.export_agent(original.id)

        # Import into fresh registry
        registry2 = AgentRegistry(schema_path=schema_path)
        reimported = registry2.import_agent(exported)

        # Verify equivalence
        assert reimported.name == original.name
        assert reimported.description == original.description
        assert reimported.system_prompt == original.system_prompt
        assert reimported.schema_version == original.schema_version
        assert reimported.agent_type == original.agent_type
        assert reimported.dspy_modules == original.dspy_modules
        assert reimported.knowledge_scopes == original.knowledge_scopes
