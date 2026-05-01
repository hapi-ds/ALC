"""Agent Registry for YAML-based agent definition management.

This module provides:
- YAML agent definition loading and validation against JSON Schema
- Agent import/export functionality
- Schema version checking
- DSPy pipeline configuration from Agent_Definition (placeholder)
- Agent selection audit trail recording

References:
    - Task 15: Agent Registry (YAML-Based)
    - Design doc Section 11: Agent Registry
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import yaml

logger = logging.getLogger(__name__)

# Supported schema versions
SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

# Default schema path
DEFAULT_SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent.parent / "agents" / "schema" / "agent-definition-v1.json"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class AgentDefinition:
    """A validated agent definition loaded from YAML.

    Attributes:
        id: Unique identifier for this agent instance.
        schema_version: Schema version of the definition.
        agent_type: Type of agent (generation or review).
        name: Human-readable agent name.
        description: Description of the agent's purpose.
        system_prompt: LLM system prompt.
        dspy_modules: List of DSPy module configurations.
        knowledge_scopes: Knowledge retrieval scope configuration.
        example_usage: Optional usage instructions.
        target_document_tag: Document tag for review agents.
        required_chapters: Required chapters for review agents.
        compliance_checklist: Compliance items for review agents.
        severity_rules: Severity classification for review agents.
        source_path: Path the definition was loaded from.
    """

    id: str
    schema_version: str
    agent_type: str
    name: str
    description: str
    system_prompt: str
    dspy_modules: list[dict[str, Any]]
    knowledge_scopes: dict[str, Any]
    example_usage: str = ""
    target_document_tag: str | None = None
    required_chapters: list[dict[str, Any]] | None = None
    compliance_checklist: list[str] | None = None
    severity_rules: dict[str, str] | None = None
    source_path: str | None = None


@dataclass
class DSPyPipelineConfig:
    """Configuration for a DSPy pipeline derived from an Agent_Definition.

    Attributes:
        agent_id: ID of the source agent definition.
        system_prompt: System prompt for the pipeline.
        modules: List of module configurations.
        temperature: Default temperature setting.
        knowledge_tags: Tags for knowledge scope filtering.
    """

    agent_id: str
    system_prompt: str
    modules: list[dict[str, Any]]
    temperature: float
    knowledge_tags: list[str]


@dataclass
class AgentSelectionEvent:
    """Audit trail record for agent selection.

    Attributes:
        event_id: Unique event identifier.
        user_id: ID of the user who selected the agent.
        agent_id: ID of the selected agent.
        agent_name: Name of the selected agent.
        timestamp: When the selection occurred.
        purpose: Why the agent was selected.
    """

    event_id: str
    user_id: int
    agent_id: str
    agent_name: str
    timestamp: datetime
    purpose: str


# ---------------------------------------------------------------------------
# Validation Errors
# ---------------------------------------------------------------------------


class AgentValidationError(Exception):
    """Raised when an agent definition fails validation.

    Attributes:
        errors: List of validation error messages.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Agent validation failed: {'; '.join(errors)}")


class UnsupportedSchemaVersionError(Exception):
    """Raised when an agent definition has an unsupported schema version."""

    def __init__(self, version: str) -> None:
        self.version = version
        supported = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        super().__init__(
            f"Unsupported schema version '{version}'. "
            f"Supported versions: {supported}"
        )


# ---------------------------------------------------------------------------
# Agent Registry
# ---------------------------------------------------------------------------


class AgentRegistry:
    """Registry for managing YAML-based agent definitions.

    Loads, validates, imports, and exports agent definitions. Maintains
    an in-memory registry of available agents and an audit trail of
    agent selections.

    Attributes:
        _agents: Dictionary of loaded agent definitions by ID.
        _schema: Loaded JSON Schema for validation.
        _selection_log: Audit trail of agent selections.
    """

    def __init__(self, schema_path: Path | None = None) -> None:
        """Initialize the AgentRegistry.

        Args:
            schema_path: Path to the JSON Schema file for validation.
                Uses the default path if not provided.
        """
        self._agents: dict[str, AgentDefinition] = {}
        self._selection_log: list[AgentSelectionEvent] = []

        # Load JSON Schema
        schema_file = schema_path or DEFAULT_SCHEMA_PATH
        self._schema = self._load_schema(schema_file)

    def _load_schema(self, schema_path: Path) -> dict[str, Any]:
        """Load the JSON Schema for agent definition validation.

        Args:
            schema_path: Path to the JSON Schema file.

        Returns:
            Parsed JSON Schema dictionary.
        """
        if schema_path.exists():
            with open(schema_path) as f:
                return json.load(f)
        else:
            logger.warning(
                "Schema file not found at %s, using minimal schema",
                schema_path,
            )
            # Minimal fallback schema
            return {
                "type": "object",
                "required": [
                    "schema_version", "name", "description",
                    "system_prompt", "dspy_modules", "knowledge_scopes",
                ],
            }

    # -----------------------------------------------------------------------
    # YAML Loading and Validation (Task 15.2)
    # -----------------------------------------------------------------------

    def load_agents(self, agents_dir: Path) -> list[AgentDefinition]:
        """Load and validate all YAML agent definitions from a directory.

        Scans the directory for .yaml and .yml files, parses each,
        validates against the JSON Schema, and returns valid definitions.

        Args:
            agents_dir: Path to directory containing agent YAML files.

        Returns:
            List of validated AgentDefinition objects.

        Raises:
            FileNotFoundError: If the directory does not exist.
        """
        if not agents_dir.exists():
            raise FileNotFoundError(f"Agents directory not found: {agents_dir}")

        loaded: list[AgentDefinition] = []

        for yaml_file in sorted(agents_dir.glob("*.yaml")):
            try:
                agent = self._load_single_agent(yaml_file)
                self._agents[agent.id] = agent
                loaded.append(agent)
                logger.info("Loaded agent: %s (%s)", agent.name, yaml_file.name)
            except (AgentValidationError, UnsupportedSchemaVersionError) as e:
                logger.warning("Skipping invalid agent file %s: %s", yaml_file.name, e)

        for yml_file in sorted(agents_dir.glob("*.yml")):
            try:
                agent = self._load_single_agent(yml_file)
                self._agents[agent.id] = agent
                loaded.append(agent)
                logger.info("Loaded agent: %s (%s)", agent.name, yml_file.name)
            except (AgentValidationError, UnsupportedSchemaVersionError) as e:
                logger.warning("Skipping invalid agent file %s: %s", yml_file.name, e)

        return loaded

    def _load_single_agent(self, yaml_path: Path) -> AgentDefinition:
        """Load and validate a single agent YAML file.

        Args:
            yaml_path: Path to the YAML file.

        Returns:
            Validated AgentDefinition.

        Raises:
            AgentValidationError: If the YAML is invalid.
            UnsupportedSchemaVersionError: If schema version is unsupported.
        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise AgentValidationError(
                [f"Expected YAML mapping, got {type(data).__name__}"]
            )

        return self._validate_and_create(data, source_path=str(yaml_path))

    def validate(self, data: dict[str, Any]) -> list[str]:
        """Validate agent definition data against the JSON Schema.

        Args:
            data: Parsed YAML data to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        # JSON Schema validation
        validator = jsonschema.Draft7Validator(self._schema)
        for error in validator.iter_errors(data):
            path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
            errors.append(f"{path}: {error.message}")

        return errors

    def _validate_and_create(
        self, data: dict[str, Any], source_path: str | None = None
    ) -> AgentDefinition:
        """Validate data and create an AgentDefinition.

        Args:
            data: Parsed YAML data.
            source_path: Optional source file path.

        Returns:
            Validated AgentDefinition.

        Raises:
            UnsupportedSchemaVersionError: If schema version is unsupported.
            AgentValidationError: If validation fails.
        """
        # Check schema version first (Task 15.4)
        schema_version = data.get("schema_version", "")
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaVersionError(schema_version)

        # Validate against JSON Schema
        errors = self.validate(data)
        if errors:
            raise AgentValidationError(errors)

        # Create AgentDefinition
        return AgentDefinition(
            id=str(uuid.uuid4()),
            schema_version=data["schema_version"],
            agent_type=data.get("agent_type", "generation"),
            name=data["name"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            dspy_modules=data["dspy_modules"],
            knowledge_scopes=data["knowledge_scopes"],
            example_usage=data.get("example_usage", ""),
            target_document_tag=data.get("target_document_tag"),
            required_chapters=data.get("required_chapters"),
            compliance_checklist=data.get("compliance_checklist"),
            severity_rules=data.get("severity_rules"),
            source_path=source_path,
        )

    # -----------------------------------------------------------------------
    # Import/Export (Task 15.3)
    # -----------------------------------------------------------------------

    def export_agent(self, agent_id: str) -> bytes:
        """Export an agent definition as YAML bytes.

        Args:
            agent_id: ID of the agent to export.

        Returns:
            YAML-encoded agent definition as bytes.

        Raises:
            KeyError: If agent_id is not found in the registry.
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent not found: {agent_id}")

        agent = self._agents[agent_id]
        data = self._agent_to_dict(agent)

        yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        return yaml_str.encode("utf-8")

    def import_agent(self, yaml_bytes: bytes) -> AgentDefinition:
        """Import and validate an agent definition from YAML bytes.

        Args:
            yaml_bytes: YAML-encoded agent definition.

        Returns:
            Validated AgentDefinition.

        Raises:
            AgentValidationError: If the YAML is invalid.
            UnsupportedSchemaVersionError: If schema version is unsupported.
        """
        try:
            data = yaml.safe_load(yaml_bytes.decode("utf-8"))
        except yaml.YAMLError as e:
            raise AgentValidationError([f"YAML parse error: {e}"])

        if not isinstance(data, dict):
            raise AgentValidationError(
                [f"Expected YAML mapping, got {type(data).__name__}"]
            )

        agent = self._validate_and_create(data, source_path="imported")
        self._agents[agent.id] = agent
        return agent

    def _agent_to_dict(self, agent: AgentDefinition) -> dict[str, Any]:
        """Convert an AgentDefinition to a dictionary for YAML export.

        Args:
            agent: The agent definition to convert.

        Returns:
            Dictionary suitable for YAML serialization.
        """
        data: dict[str, Any] = {
            "schema_version": agent.schema_version,
            "agent_type": agent.agent_type,
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "dspy_modules": agent.dspy_modules,
            "knowledge_scopes": agent.knowledge_scopes,
        }

        if agent.example_usage:
            data["example_usage"] = agent.example_usage

        if agent.agent_type == "review":
            if agent.target_document_tag:
                data["target_document_tag"] = agent.target_document_tag
            if agent.required_chapters:
                data["required_chapters"] = agent.required_chapters
            if agent.compliance_checklist:
                data["compliance_checklist"] = agent.compliance_checklist
            if agent.severity_rules:
                data["severity_rules"] = agent.severity_rules

        return data

    # -----------------------------------------------------------------------
    # Schema Version Checking (Task 15.4)
    # -----------------------------------------------------------------------

    def check_schema_version(self, version: str) -> bool:
        """Check if a schema version is supported.

        Args:
            version: Schema version string to check.

        Returns:
            True if the version is supported.
        """
        return version in SUPPORTED_SCHEMA_VERSIONS

    # -----------------------------------------------------------------------
    # DSPy Pipeline Configuration (Task 15.6)
    # -----------------------------------------------------------------------

    def get_pipeline_config(self, agent_id: str) -> DSPyPipelineConfig:
        """Get DSPy pipeline configuration from an Agent_Definition.

        Extracts the system prompt, module chain, temperature, and
        knowledge scopes to configure a DSPy pipeline (placeholder).

        Args:
            agent_id: ID of the agent definition.

        Returns:
            DSPyPipelineConfig for pipeline initialization.

        Raises:
            KeyError: If agent_id is not found.
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent not found: {agent_id}")

        agent = self._agents[agent_id]

        # Extract default temperature from first generation module
        temperature = 0.3  # default
        for module in agent.dspy_modules:
            params = module.get("params", {})
            if "temperature" in params:
                temperature = params["temperature"]
                break

        return DSPyPipelineConfig(
            agent_id=agent.id,
            system_prompt=agent.system_prompt,
            modules=agent.dspy_modules,
            temperature=temperature,
            knowledge_tags=agent.knowledge_scopes.get("tags", []),
        )

    # -----------------------------------------------------------------------
    # Agent Selection Audit Trail (Task 15.7)
    # -----------------------------------------------------------------------

    def record_selection(
        self, user_id: int, agent_id: str, purpose: str = "query"
    ) -> AgentSelectionEvent:
        """Record an agent selection event in the audit trail.

        Args:
            user_id: ID of the user selecting the agent.
            agent_id: ID of the selected agent.
            purpose: Purpose of the selection (e.g., "query", "generation").

        Returns:
            The recorded AgentSelectionEvent.

        Raises:
            KeyError: If agent_id is not found.
        """
        if agent_id not in self._agents:
            raise KeyError(f"Agent not found: {agent_id}")

        agent = self._agents[agent_id]

        event = AgentSelectionEvent(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            agent_id=agent_id,
            agent_name=agent.name,
            timestamp=datetime.now(UTC),
            purpose=purpose,
        )
        self._selection_log.append(event)

        logger.info(
            "Agent selection recorded: user=%d, agent=%s (%s), purpose=%s",
            user_id,
            agent.name,
            agent_id,
            purpose,
        )

        return event

    def get_selection_log(self) -> list[AgentSelectionEvent]:
        """Get the full agent selection audit trail.

        Returns:
            List of all agent selection events.
        """
        return list(self._selection_log)

    # -----------------------------------------------------------------------
    # Registry Access
    # -----------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> AgentDefinition | None:
        """Get an agent definition by ID.

        Args:
            agent_id: The agent identifier.

        Returns:
            The AgentDefinition, or None if not found.
        """
        return self._agents.get(agent_id)

    def list_agents(
        self, agent_type: str | None = None
    ) -> list[AgentDefinition]:
        """List all registered agents, optionally filtered by type.

        Args:
            agent_type: Optional filter by agent type.

        Returns:
            List of matching AgentDefinition objects.
        """
        agents = list(self._agents.values())
        if agent_type:
            agents = [a for a in agents if a.agent_type == agent_type]
        return agents

    def register_agent(self, agent: AgentDefinition) -> None:
        """Register an agent definition in the registry.

        Args:
            agent: The agent definition to register.
        """
        self._agents[agent.id] = agent
