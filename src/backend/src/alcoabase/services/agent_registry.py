"""Agent Registry for YAML-based agent definition management.

This module provides:
- YAML agent definition loading and validation against JSON Schema
- Agent import/export functionality
- Schema version checking
- DSPy pipeline configuration from Agent_Definition (placeholder)
- Agent selection audit trail recording
- AgentRegistryService: Extended registry with DB persistence, archetype management

References:
    - Task 15: Agent Registry (YAML-Based)
    - Design doc Section 11: Agent Registry
    - Design doc Section 2: Agent Registry Service (v2.0)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import jsonschema
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.agent import AgentDefinition as AgentDefinitionDB
from alcoabase.schemas.agent import ContextualTuning, EvaluationRubric, ReloadSummary
from alcoabase.services.agent_file_watcher import AgentFileWatcher
from alcoabase.services.deep_merge import deep_merge
from alcoabase.services.schema_validator import SchemaValidator

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


# ---------------------------------------------------------------------------
# Archetype Definition Type
# ---------------------------------------------------------------------------


class ArchetypeDefinition(TypedDict):
    """Structure representing a loaded archetype definition.

    Attributes:
        archetype: The archetype identifier string.
        name: Default agent name from the archetype.
        description: Default description.
        schema_version: Schema version (always "2.0").
        personality_profile: Default personality configuration.
        contextual_tuning: Default LLM tuning parameters.
        evaluation_rubric: Optional evaluation rubric.
        agent_type: Default agent type.
        system_prompt: Default system prompt.
        dspy_modules: Default DSPy module configurations.
        knowledge_scopes: Default knowledge scope configuration.
    """

    archetype: str
    name: str
    description: str
    schema_version: str
    personality_profile: dict[str, Any]
    contextual_tuning: dict[str, Any]
    evaluation_rubric: dict[str, Any] | None
    agent_type: str
    system_prompt: str
    dspy_modules: list[dict[str, Any]]
    knowledge_scopes: dict[str, Any]


# ---------------------------------------------------------------------------
# Agent Registry Service (v2.0 with DB persistence and archetypes)
# ---------------------------------------------------------------------------


class ArchetypeNotFoundError(Exception):
    """Raised when a requested archetype is not found.

    Attributes:
        archetype_id: The requested archetype identifier.
        available: List of available archetype identifiers.
    """

    def __init__(self, archetype_id: str, available: list[str]) -> None:
        self.archetype_id = archetype_id
        self.available = available
        super().__init__(
            f"Unknown archetype '{archetype_id}'. "
            f"Available archetypes: {', '.join(available)}"
        )


# ---------------------------------------------------------------------------
# Constants for DB-backed Agent Registry Service
# ---------------------------------------------------------------------------

# Default timeout for DB connection check at startup (seconds)
_DB_CONNECT_TIMEOUT = 5.0

# Default contextual tuning values applied when an agent has no tuning config
DEFAULT_TUNING_PARAMS: dict[str, Any] = {
    "temperature": 0.3,
    "max_tokens": 4096,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
}

# Valid ranges for tuning parameters
TUNING_PARAM_RANGES: dict[str, tuple[float, float]] = {
    "temperature": (0.0, 2.0),
    "max_tokens": (1, float("inf")),
    "top_p": (0.0, 1.0),
    "frequency_penalty": (-2.0, 2.0),
    "presence_penalty": (-2.0, 2.0),
}


class AgentImportError(Exception):
    """Raised when an agent YAML import fails validation.

    Attributes:
        errors: List of import validation error messages.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Agent import failed: {'; '.join(errors)}")


class AgentNotFoundError(Exception):
    """Raised when an agent is not found or does not belong to the company."""

    pass


class AgentInUseError(Exception):
    """Raised when attempting to delete an agent that is in an active pipeline."""

    pass


class AgentRegistryService:
    """Extended agent registry with DB persistence, archetype management, and hot-reload.

    Provides CRUD operations backed by PostgreSQL, archetype-based agent
    instantiation with deep-merge overrides, and an in-memory cache for
    fast reads.

    Attributes:
        _session_factory: SQLAlchemy async session factory.
        _schema_validator: Schema validator for v1.0/v2.0 definitions.
        _agents_dir: Path to the agents YAML directory.
        _archetypes_dir: Path to the archetypes YAML directory.
        _cache: In-memory cache of active agents keyed by ID.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        schema_validator: SchemaValidator,
        agents_dir: Path,
        archetypes_dir: Path,
    ) -> None:
        """Initialize the AgentRegistryService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
            schema_validator: Validator for agent definition schemas.
            agents_dir: Path to the directory containing agent YAML files.
            archetypes_dir: Path to the directory containing archetype YAML files.
        """
        self._session_factory = session_factory
        self._schema_validator = schema_validator
        self._agents_dir = agents_dir
        self._archetypes_dir = archetypes_dir
        self._cache: dict[int, AgentDefinitionDB] = {}
        self._watcher: AgentFileWatcher | None = None

    # -----------------------------------------------------------------------
    # Initialization (Requirements 7.1, 7.5, 7.6)
    # -----------------------------------------------------------------------

    async def initialize(self) -> None:
        """Load active agents from DB into memory and sync YAML agents.

        On startup:
        1. Attempt to connect to the database within 5 seconds.
        2. If successful, load all active agents into the in-memory cache.
        3. Scan YAML agent files and sync with DB (create records for
           YAML agents not already in DB, matched by name within company scope).

        If the database is unreachable within the timeout, falls back to
        YAML-only loading and logs a warning.
        """
        db_available = await self._check_db_connection()

        if db_available:
            await self._load_agents_from_db()
            await self._sync_yaml_agents_with_db()
        else:
            logger.warning(
                "Database unreachable within %s seconds at startup. "
                "Falling back to YAML-only agent loading.",
                _DB_CONNECT_TIMEOUT,
            )
            self._load_agents_from_yaml_only()

    async def _check_db_connection(self) -> bool:
        """Check if the database is reachable within the timeout.

        Returns:
            True if a simple query succeeds within the timeout, False otherwise.
        """
        try:
            async with asyncio.timeout(_DB_CONNECT_TIMEOUT):
                async with self._session_factory() as session:
                    await session.execute(select(AgentDefinitionDB.id).limit(1))
            return True
        except (TimeoutError, Exception) as e:
            logger.warning("DB connection check failed: %s", e)
            return False

    async def _load_agents_from_db(self) -> None:
        """Load all active agents from the database into the in-memory cache."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentDefinitionDB).where(
                    AgentDefinitionDB.is_active == True  # noqa: E712
                )
            )
            agents = result.scalars().all()

            for agent in agents:
                session.expunge(agent)
                self._cache[agent.id] = agent

        logger.info("Loaded %d active agents from database.", len(self._cache))

    async def _sync_yaml_agents_with_db(self) -> None:
        """Sync YAML agent files with the database.

        For each YAML agent file, check if a matching agent (by name)
        exists in the DB within the same company scope. If not, create
        a new DB record.
        """
        if not self._agents_dir.exists():
            logger.warning("Agents directory not found: %s", self._agents_dir)
            return

        yaml_files = list(self._agents_dir.glob("*.yaml")) + list(
            self._agents_dir.glob("*.yml")
        )

        if not yaml_files:
            return

        async with self._session_factory() as session:
            for yaml_file in yaml_files:
                try:
                    await self._sync_single_yaml_agent(session, yaml_file)
                except Exception as e:
                    logger.warning(
                        "Failed to sync YAML agent %s: %s", yaml_file.name, e
                    )

            await session.commit()

    async def _sync_single_yaml_agent(
        self, session: AsyncSession, yaml_path: Path
    ) -> None:
        """Sync a single YAML agent file with the database.

        If an agent with the same name exists in the DB (within the same
        company scope), skip it. Otherwise, create a new DB record.

        Args:
            session: Active async DB session.
            yaml_path: Path to the YAML agent file.
        """
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            logger.warning("Skipping %s: not a valid YAML mapping", yaml_path.name)
            return

        # Validate against schema
        errors = self._schema_validator.validate(data)
        if errors:
            logger.warning(
                "Skipping %s: validation errors: %s", yaml_path.name, errors
            )
            return

        agent_name = data.get("name", "")
        company_id = data.get("company_id")  # None for system-level agents

        # Check if agent already exists by name within company scope
        existing = await session.execute(
            select(AgentDefinitionDB).where(
                AgentDefinitionDB.name == agent_name,
                AgentDefinitionDB.company_id == company_id,
                AgentDefinitionDB.is_active == True,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none() is not None:
            return  # Already synced

        # Create new DB record from YAML
        yaml_content = yaml_path.read_text()
        agent_db = AgentDefinitionDB(
            name=agent_name,
            description=data.get("description", ""),
            agent_type=data.get("agent_type", "generation"),
            schema_version=data.get("schema_version", "1.0"),
            yaml_content=yaml_content,
            is_active=True,
            created_by=1,  # System user for YAML imports
            company_id=company_id,
            archetype=data.get("archetype"),
            personality_profile=data.get("personality_profile"),
            contextual_tuning=data.get("contextual_tuning"),
            evaluation_rubric=data.get("evaluation_rubric"),
        )
        session.add(agent_db)
        await session.flush()

        # Add to cache
        session.expunge(agent_db)
        self._cache[agent_db.id] = agent_db

        logger.info("Synced YAML agent to DB: %s (id=%d)", agent_name, agent_db.id)

    def _load_agents_from_yaml_only(self) -> None:
        """Fallback: load agents from YAML files when DB is unreachable.

        Logs each loaded agent but does not persist to DB.
        """
        if not self._agents_dir.exists():
            logger.warning("Agents directory not found: %s", self._agents_dir)
            return

        yaml_files = list(self._agents_dir.glob("*.yaml")) + list(
            self._agents_dir.glob("*.yml")
        )

        for yaml_file in yaml_files:
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    continue

                errors = self._schema_validator.validate(data)
                if errors:
                    logger.warning(
                        "Skipping %s: validation errors: %s",
                        yaml_file.name,
                        errors,
                    )
                    continue

                logger.info(
                    "Loaded agent from YAML (no DB): %s", data.get("name", "unknown")
                )
            except Exception as e:
                logger.warning("Failed to load YAML agent %s: %s", yaml_file.name, e)

    # -----------------------------------------------------------------------
    # Hot-Reload: File Watcher Integration (Requirements 3.6, 3.7)
    # -----------------------------------------------------------------------

    async def start_watcher(self) -> None:
        """Start the file watcher for hot-reload of agent YAML definitions.

        Creates an AgentFileWatcher instance watching the agents directory
        and starts it as a background task. File changes trigger the
        _on_file_change callback to update the registry.
        """
        self._watcher = AgentFileWatcher(
            agents_dir=self._agents_dir,
            on_change=self._on_file_change,
        )
        await self._watcher.start()
        logger.info("Agent registry file watcher started.")

    async def stop_watcher(self) -> None:
        """Stop the file watcher background task.

        Gracefully stops the watcher if it is running.
        """
        if self._watcher is not None:
            await self._watcher.stop()
            self._watcher = None
            logger.info("Agent registry file watcher stopped.")

    async def _on_file_change(
        self, action: str, file_path: Path, data: dict[str, Any] | None
    ) -> None:
        """Callback invoked by the file watcher on YAML file changes.

        Handles add, modify, and remove actions:
        - add: Validate against schema, create/load agent into cache and DB.
        - modify: Validate against schema, update agent in cache and DB.
        - remove: Mark agent as inactive (remove from cache, update DB).

        Args:
            action: The change type ("add", "modify", or "remove").
            file_path: Path to the changed file.
            data: Parsed YAML dict for add/modify, None for remove.
        """
        if action == "add" and data is not None:
            errors = self._schema_validator.validate(data)
            if errors:
                logger.warning(
                    "Hot-reload: new file %s failed validation: %s",
                    file_path,
                    errors,
                )
                return

            agent_name = data.get("name", "")
            try:
                agent = await self.create_agent(data, company_id=data.get("company_id"), user_id=1)
                logger.info(
                    "Hot-reload: loaded new agent '%s' from %s",
                    agent_name,
                    file_path.name,
                )
            except Exception as e:
                logger.warning(
                    "Hot-reload: failed to load agent from %s: %s",
                    file_path.name,
                    e,
                )

        elif action == "modify" and data is not None:
            errors = self._schema_validator.validate(data)
            if errors:
                logger.warning(
                    "Hot-reload: modified file %s failed validation, "
                    "retaining previous definition: %s",
                    file_path,
                    errors,
                )
                return

            agent_name = data.get("name", "")
            # Find existing agent by name in cache to update it
            existing_agent = self._find_cached_agent_by_name(agent_name)
            if existing_agent:
                try:
                    await self.update_agent(
                        existing_agent.id, data, existing_agent.company_id
                    )
                    logger.info(
                        "Hot-reload: updated agent '%s' from %s",
                        agent_name,
                        file_path.name,
                    )
                except Exception as e:
                    logger.warning(
                        "Hot-reload: failed to update agent '%s': %s",
                        agent_name,
                        e,
                    )
            else:
                # Agent not in cache yet — treat as new
                try:
                    agent = await self.create_agent(
                        data, company_id=data.get("company_id"), user_id=1
                    )
                    logger.info(
                        "Hot-reload: loaded modified agent '%s' from %s",
                        agent_name,
                        file_path.name,
                    )
                except Exception as e:
                    logger.warning(
                        "Hot-reload: failed to load modified agent from %s: %s",
                        file_path.name,
                        e,
                    )

        elif action == "remove":
            # Find agent by file path stem (filename without extension) or name
            agent_name = file_path.stem
            existing_agent = self._find_cached_agent_by_name(agent_name)
            if existing_agent:
                try:
                    # Soft-delete: set is_active=False in DB and remove from cache
                    async with self._session_factory() as session:
                        result = await session.execute(
                            select(AgentDefinitionDB).where(
                                AgentDefinitionDB.id == existing_agent.id,
                            )
                        )
                        agent_db = result.scalar_one_or_none()
                        if agent_db:
                            agent_db.is_active = False
                            await session.commit()

                    self._cache.pop(existing_agent.id, None)
                    logger.info(
                        "Hot-reload: deactivated agent '%s' (file removed: %s)",
                        existing_agent.name,
                        file_path.name,
                    )
                except Exception as e:
                    logger.warning(
                        "Hot-reload: failed to deactivate agent for %s: %s",
                        file_path.name,
                        e,
                    )

    def _find_cached_agent_by_name(self, name: str) -> AgentDefinitionDB | None:
        """Find an agent in the cache by name.

        Args:
            name: The agent name to search for.

        Returns:
            The cached AgentDefinitionDB if found, None otherwise.
        """
        for agent in self._cache.values():
            if agent.name == name:
                return agent
        return None

    async def reload(self) -> ReloadSummary:
        """Trigger an immediate rescan of the agents directory.

        Compares current YAML files on disk with the in-memory cache to
        determine which agents are new, updated, or removed. Returns a
        summary of all changes made.

        Returns:
            ReloadSummary with lists of loaded, updated, deactivated agents
            and any errors encountered.
        """
        loaded: list[str] = []
        updated: list[str] = []
        deactivated: list[str] = []
        errors: list[dict[str, str]] = []

        if not self._agents_dir.exists():
            logger.warning("Agents directory not found for reload: %s", self._agents_dir)
            return ReloadSummary(
                loaded=loaded, updated=updated, deactivated=deactivated, errors=errors
            )

        # Gather all current YAML files
        yaml_files = list(self._agents_dir.glob("*.yaml")) + list(
            self._agents_dir.glob("*.yml")
        )

        # Track which cached agents are still present on disk
        seen_agent_names: set[str] = set()

        for yaml_file in yaml_files:
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    errors.append({
                        "file": str(yaml_file),
                        "error": f"Expected YAML mapping, got {type(data).__name__}",
                    })
                    continue

                # Validate against schema
                validation_errors = self._schema_validator.validate(data)
                if validation_errors:
                    errors.append({
                        "file": str(yaml_file),
                        "error": "; ".join(validation_errors),
                    })
                    continue

                agent_name = data.get("name", "")
                seen_agent_names.add(agent_name)

                # Check if agent already exists in cache
                existing = self._find_cached_agent_by_name(agent_name)
                if existing:
                    # Update existing agent
                    try:
                        await self.update_agent(
                            existing.id, data, existing.company_id
                        )
                        updated.append(agent_name)
                    except Exception as e:
                        errors.append({
                            "file": str(yaml_file),
                            "error": str(e),
                        })
                else:
                    # Load new agent
                    try:
                        await self.create_agent(
                            data, company_id=data.get("company_id"), user_id=1
                        )
                        loaded.append(agent_name)
                    except Exception as e:
                        errors.append({
                            "file": str(yaml_file),
                            "error": str(e),
                        })

            except yaml.YAMLError as e:
                errors.append({
                    "file": str(yaml_file),
                    "error": f"YAML parse error: {e}",
                })
            except OSError as e:
                errors.append({
                    "file": str(yaml_file),
                    "error": f"File read error: {e}",
                })

        # Deactivate agents that are no longer on disk
        agents_to_deactivate: list[AgentDefinitionDB] = []
        for agent in list(self._cache.values()):
            if agent.name not in seen_agent_names:
                agents_to_deactivate.append(agent)

        for agent in agents_to_deactivate:
            try:
                async with self._session_factory() as session:
                    result = await session.execute(
                        select(AgentDefinitionDB).where(
                            AgentDefinitionDB.id == agent.id,
                        )
                    )
                    agent_db = result.scalar_one_or_none()
                    if agent_db:
                        agent_db.is_active = False
                        await session.commit()

                self._cache.pop(agent.id, None)
                deactivated.append(agent.name)
            except Exception as e:
                errors.append({
                    "file": f"agent:{agent.name}",
                    "error": f"Failed to deactivate: {e}",
                })

        logger.info(
            "Reload complete: %d loaded, %d updated, %d deactivated, %d errors",
            len(loaded),
            len(updated),
            len(deactivated),
            len(errors),
        )

        return ReloadSummary(
            loaded=loaded, updated=updated, deactivated=deactivated, errors=errors
        )

    # -----------------------------------------------------------------------
    # CRUD Operations
    # -----------------------------------------------------------------------

    async def create_agent(
        self, data: dict[str, Any], company_id: int, user_id: int
    ) -> AgentDefinitionDB:
        """Create a new agent definition, persist to DB, and cache.

        Args:
            data: Agent definition dictionary (validated externally or here).
            company_id: Company scope for multi-tenancy.
            user_id: ID of the creating user.

        Returns:
            The persisted AgentDefinitionDB instance.

        Raises:
            AgentValidationError: If the definition fails schema validation.
        """
        errors = self._schema_validator.validate(data)
        if errors:
            raise AgentValidationError(errors)

        yaml_content = yaml.dump(data, default_flow_style=False, allow_unicode=True)

        agent = AgentDefinitionDB(
            name=data["name"],
            description=data.get("description", ""),
            agent_type=data.get("agent_type", "generation"),
            schema_version=data["schema_version"],
            yaml_content=yaml_content,
            is_active=True,
            created_by=user_id,
            company_id=company_id,
            archetype=data.get("archetype"),
            personality_profile=data.get("personality_profile"),
            contextual_tuning=data.get("contextual_tuning"),
            evaluation_rubric=data.get("evaluation_rubric"),
        )

        async with self._session_factory() as session:
            session.add(agent)
            await session.commit()
            await session.refresh(agent)
            session.expunge(agent)

        # Update in-memory cache on success
        self._cache[agent.id] = agent
        logger.info("Created agent '%s' (id=%d)", agent.name, agent.id)
        return agent

    async def get_agent(
        self, agent_id: int, company_id: int
    ) -> AgentDefinitionDB | None:
        """Get an agent by ID scoped to a company.

        Args:
            agent_id: The agent primary key.
            company_id: Company scope for multi-tenancy.

        Returns:
            The AgentDefinitionDB if found and active, else None.
        """
        cached = self._cache.get(agent_id)
        if cached and cached.company_id == company_id and cached.is_active:
            return cached

        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentDefinitionDB).where(
                    AgentDefinitionDB.id == agent_id,
                    AgentDefinitionDB.company_id == company_id,
                    AgentDefinitionDB.is_active == True,  # noqa: E712
                )
            )
            agent = result.scalar_one_or_none()
            if agent:
                session.expunge(agent)
                self._cache[agent.id] = agent
            return agent

    async def list_agents(
        self, company_id: int, archetype: str | None = None
    ) -> list[AgentDefinitionDB]:
        """List active agents for a company, optionally filtered by archetype.

        Args:
            company_id: Company scope for multi-tenancy.
            archetype: Optional archetype filter.

        Returns:
            List of matching active AgentDefinitionDB instances.
        """
        async with self._session_factory() as session:
            stmt = select(AgentDefinitionDB).where(
                AgentDefinitionDB.company_id == company_id,
                AgentDefinitionDB.is_active == True,  # noqa: E712
            )
            if archetype:
                stmt = stmt.where(AgentDefinitionDB.archetype == archetype)

            result = await session.execute(stmt)
            agents = list(result.scalars().all())

            # Expunge and update cache
            for agent in agents:
                session.expunge(agent)
                self._cache[agent.id] = agent

            return agents

    async def update_agent(
        self, agent_id: int, data: dict[str, Any], company_id: int
    ) -> AgentDefinitionDB:
        """Update an existing agent definition.

        Validates the new data, updates the DB record, and on success
        updates the in-memory cache. On DB failure, memory is unchanged.

        Args:
            agent_id: The agent primary key.
            data: Updated agent definition dictionary.
            company_id: Company scope for multi-tenancy.

        Returns:
            The updated AgentDefinitionDB instance.

        Raises:
            AgentNotFoundError: If agent not found or not in company scope.
            AgentValidationError: If the definition fails schema validation.
        """
        errors = self._schema_validator.validate(data)
        if errors:
            raise AgentValidationError(errors)

        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentDefinitionDB).where(
                    AgentDefinitionDB.id == agent_id,
                    AgentDefinitionDB.company_id == company_id,
                    AgentDefinitionDB.is_active == True,  # noqa: E712
                )
            )
            agent = result.scalar_one_or_none()
            if not agent:
                raise AgentNotFoundError(
                    f"Agent {agent_id} not found for company {company_id}"
                )

            yaml_content = yaml.dump(
                data, default_flow_style=False, allow_unicode=True
            )

            agent.name = data["name"]
            agent.description = data.get("description", "")
            agent.agent_type = data.get("agent_type", "generation")
            agent.schema_version = data["schema_version"]
            agent.yaml_content = yaml_content
            agent.archetype = data.get("archetype")
            agent.personality_profile = data.get("personality_profile")
            agent.contextual_tuning = data.get("contextual_tuning")
            agent.evaluation_rubric = data.get("evaluation_rubric")

            await session.commit()
            await session.refresh(agent)
            session.expunge(agent)

        # Update in-memory cache on success
        self._cache[agent.id] = agent
        logger.info("Updated agent '%s' (id=%d)", agent.name, agent.id)
        return agent

    async def delete_agent(self, agent_id: int, company_id: int) -> None:
        """Soft-delete an agent by setting is_active to False.

        Persists the soft-delete to the database first, then removes
        from the in-memory cache on success. Returns 409 if agent is
        in an active pipeline.

        Args:
            agent_id: The agent primary key.
            company_id: Company scope for multi-tenancy.

        Raises:
            AgentNotFoundError: If agent not found or not in company scope.
            AgentInUseError: If agent is assigned to an active pipeline.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentDefinitionDB).where(
                    AgentDefinitionDB.id == agent_id,
                    AgentDefinitionDB.company_id == company_id,
                    AgentDefinitionDB.is_active == True,  # noqa: E712
                )
            )
            agent = result.scalar_one_or_none()
            if not agent:
                raise AgentNotFoundError(
                    f"Agent {agent_id} not found for company {company_id}"
                )

            # Check if agent is in an active pipeline
            if await self._is_agent_in_active_pipeline(session, agent_id):
                raise AgentInUseError(
                    f"Agent {agent_id} is assigned to an active pipeline"
                )

            agent.is_active = False
            await session.commit()

        # Remove from cache
        self._cache.pop(agent_id, None)
        logger.info("Soft-deleted agent id=%d", agent_id)

    async def _is_agent_in_active_pipeline(
        self, session: AsyncSession, agent_id: int
    ) -> bool:
        """Check if an agent is currently assigned to an active pipeline.

        This is a placeholder implementation. In a full system, this would
        query a pipeline assignments table to determine if the agent is in use.

        Args:
            session: Active async DB session.
            agent_id: The agent's primary key.

        Returns:
            True if the agent is in an active pipeline, False otherwise.
        """
        # Placeholder: always returns False until pipeline tracking is implemented
        return False

    # -----------------------------------------------------------------------
    # Archetype Operations
    # -----------------------------------------------------------------------

    def list_archetypes(self) -> list[ArchetypeDefinition]:
        """Load and return all archetype definitions from the archetypes directory.

        Scans the archetypes directory for .yaml and .yml files, parses each,
        and returns them as a list of ArchetypeDefinition dicts.

        Returns:
            List of archetype definitions with their default configurations.
            Returns an empty list if the directory doesn't exist or contains
            no valid archetype files.
        """
        archetypes: list[ArchetypeDefinition] = []

        if not self._archetypes_dir.exists():
            logger.warning(
                "Archetypes directory not found: %s", self._archetypes_dir
            )
            return archetypes

        yaml_files = sorted(self._archetypes_dir.glob("*.yaml")) + sorted(
            self._archetypes_dir.glob("*.yml")
        )

        for yaml_file in yaml_files:
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    logger.warning(
                        "Skipping non-mapping archetype file: %s", yaml_file.name
                    )
                    continue

                archetype_def: ArchetypeDefinition = {
                    "archetype": data.get("archetype", ""),
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "schema_version": data.get("schema_version", "2.0"),
                    "personality_profile": data.get("personality_profile", {}),
                    "contextual_tuning": data.get("contextual_tuning", {}),
                    "evaluation_rubric": data.get("evaluation_rubric"),
                    "agent_type": data.get("agent_type", "generation"),
                    "system_prompt": data.get("system_prompt", ""),
                    "dspy_modules": data.get("dspy_modules", []),
                    "knowledge_scopes": data.get("knowledge_scopes", {}),
                }
                archetypes.append(archetype_def)
                logger.debug("Loaded archetype: %s", archetype_def["archetype"])

            except yaml.YAMLError as e:
                logger.warning(
                    "Failed to parse archetype file %s: %s", yaml_file.name, e
                )
            except OSError as e:
                logger.warning(
                    "Failed to read archetype file %s: %s", yaml_file.name, e
                )

        return archetypes

    def _load_archetype_raw(self, archetype_id: str) -> dict[str, Any] | None:
        """Load the raw YAML data for a specific archetype by its identifier.

        Scans archetype files and returns the full parsed YAML dict for the
        archetype matching the given ID. This includes all fields (including
        review-agent-specific fields like target_document_tag).

        Args:
            archetype_id: The archetype identifier to search for.

        Returns:
            The full parsed YAML dict if found, None otherwise.
        """
        if not self._archetypes_dir.exists():
            return None

        yaml_files = sorted(self._archetypes_dir.glob("*.yaml")) + sorted(
            self._archetypes_dir.glob("*.yml")
        )

        for yaml_file in yaml_files:
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)

                if isinstance(data, dict) and data.get("archetype") == archetype_id:
                    return data
            except (yaml.YAMLError, OSError):
                continue

        return None

    async def create_from_archetype(
        self,
        archetype_id: str,
        name: str,
        overrides: dict[str, Any] | None,
        company_id: int,
        user_id: int,
    ) -> AgentDefinitionDB:
        """Create a new agent from a predefined archetype with optional overrides.

        Finds the archetype by matching the `archetype` field in the YAML files,
        deep-merges any overrides with archetype defaults, validates the merged
        result against the v2.0 schema, and persists to the database.

        Args:
            archetype_id: The archetype identifier to base the agent on.
            name: Display name for the new agent.
            overrides: Optional dict with partial overrides for personality_profile,
                contextual_tuning, knowledge_scopes, and/or description.
            company_id: Company scope for multi-tenancy.
            user_id: ID of the creating user.

        Returns:
            The persisted AgentDefinitionDB instance.

        Raises:
            ArchetypeNotFoundError: If archetype_id doesn't match any archetype.
            AgentValidationError: If the merged definition fails v2.0 schema validation.
        """
        # Load the full raw archetype data (includes all fields like
        # target_document_tag, required_chapters, etc.)
        raw_archetype = self._load_archetype_raw(archetype_id)

        if raw_archetype is None:
            # Get available archetypes for the error message
            archetypes = self.list_archetypes()
            available_ids = [a["archetype"] for a in archetypes]
            raise ArchetypeNotFoundError(archetype_id, available_ids)

        # Start with a copy of the full archetype data
        agent_data: dict[str, Any] = dict(raw_archetype)

        # Set the agent name from the request
        agent_data["name"] = name

        # Apply overrides via deep merge
        if overrides:
            if "personality_profile" in overrides and overrides["personality_profile"]:
                agent_data["personality_profile"] = deep_merge(
                    agent_data.get("personality_profile", {}),
                    overrides["personality_profile"],
                )

            if "contextual_tuning" in overrides and overrides["contextual_tuning"]:
                agent_data["contextual_tuning"] = deep_merge(
                    agent_data.get("contextual_tuning", {}),
                    overrides["contextual_tuning"],
                )

            if "knowledge_scopes" in overrides and overrides["knowledge_scopes"]:
                agent_data["knowledge_scopes"] = deep_merge(
                    agent_data.get("knowledge_scopes", {}),
                    overrides["knowledge_scopes"],
                )

            if "description" in overrides and overrides["description"]:
                agent_data["description"] = overrides["description"]

        # Validate merged result against v2.0 schema
        errors = self._schema_validator.validate(agent_data)
        if errors:
            raise AgentValidationError(errors)

        # Persist to DB
        return await self.create_agent(agent_data, company_id, user_id)

    # -----------------------------------------------------------------------
    # Tuning Parameter Resolution (Requirements 4.1, 4.2, 4.6, 4.7)
    # -----------------------------------------------------------------------

    def get_tuning_params(
        self, agent_id: int, overrides: dict[str, Any] | None = None
    ) -> ContextualTuning:
        """Resolve contextual tuning parameters for an agent.

        Looks up the agent in the in-memory cache, starts with the agent's
        contextual_tuning values (or system defaults if not set), merges any
        invocation-time overrides, validates all values are within valid ranges,
        and returns a ContextualTuning object.

        Args:
            agent_id: The agent's database primary key.
            overrides: Optional dict of parameter overrides that take precedence
                over agent defaults. Keys should match ContextualTuning field names.

        Returns:
            A ContextualTuning instance with the resolved parameter values.

        Raises:
            KeyError: If agent_id is not found in the cache.
            ValueError: If any resolved parameter value is outside its valid range.
        """
        if agent_id not in self._cache:
            raise KeyError(f"Agent not found: {agent_id}")

        agent = self._cache[agent_id]

        # Start with defaults
        base_params = dict(DEFAULT_TUNING_PARAMS)

        # If agent has contextual_tuning, use those as the base
        if agent.contextual_tuning is not None:
            base_params.update(agent.contextual_tuning)

        # Merge overrides if provided (overrides take precedence)
        if overrides:
            base_params.update(overrides)

        # Validate all parameter ranges
        self._validate_tuning_ranges(base_params)

        return ContextualTuning(**base_params)

    def _validate_tuning_ranges(self, params: dict[str, Any]) -> None:
        """Validate that all tuning parameters are within valid ranges.

        Args:
            params: Dictionary of tuning parameter values to validate.

        Raises:
            ValueError: If any parameter is outside its valid range,
                indicating which parameter is out of range.
        """
        for param_name, (min_val, max_val) in TUNING_PARAM_RANGES.items():
            if param_name not in params:
                continue

            value = params[param_name]

            if value < min_val or value > max_val:
                if max_val == float("inf"):
                    raise ValueError(
                        f"Parameter '{param_name}' value {value} is out of range "
                        f"(must be >= {min_val})"
                    )
                raise ValueError(
                    f"Parameter '{param_name}' value {value} is out of range "
                    f"(must be between {min_val} and {max_val})"
                )

    # -----------------------------------------------------------------------
    # System Prompt with Rubric (Requirement 4.5)
    # -----------------------------------------------------------------------

    def get_system_prompt_with_rubric(self, agent_id: int) -> str:
        """Get the agent's system prompt with evaluation rubric appended.

        If the agent has an evaluation_rubric with criteria defined, appends
        a formatted rubric section to the system prompt. Otherwise returns
        the system prompt unchanged.

        Args:
            agent_id: The agent's database primary key.

        Returns:
            The system prompt string, optionally with rubric criteria appended.

        Raises:
            KeyError: If agent_id is not found in the cache.
        """
        if agent_id not in self._cache:
            raise KeyError(f"Agent not found: {agent_id}")

        agent = self._cache[agent_id]

        # Get the base system prompt from the YAML content
        yaml_data = yaml.safe_load(agent.yaml_content)
        system_prompt: str = yaml_data.get("system_prompt", "")

        # If no evaluation rubric or no criteria, return prompt as-is
        if not agent.evaluation_rubric:
            return system_prompt

        rubric_data = agent.evaluation_rubric
        criteria = rubric_data.get("criteria")

        if not criteria:
            return system_prompt

        # Append rubric section
        rubric_section = "\n\n## Evaluation Rubric\n"
        for criterion in criteria:
            name = criterion.get("name", "")
            description = criterion.get("description", "")
            rubric_section += f"- **{name}**: {description}\n"

        return system_prompt + rubric_section

    # -----------------------------------------------------------------------
    # YAML Export/Import (Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7)
    # -----------------------------------------------------------------------

    # Maximum import file size: 1 MB
    _MAX_IMPORT_SIZE = 1_048_576

    # Canonical field ordering for YAML export
    _EXPORT_FIELD_ORDER = [
        "schema_version",
        "name",
        "description",
        "archetype",
        "personality_profile",
        "contextual_tuning",
        "evaluation_rubric",
        "agent_type",
        "system_prompt",
        "dspy_modules",
        "knowledge_scopes",
    ]

    async def export_agent_yaml(self, agent_id: int, company_id: int) -> str:
        """Export an agent definition as a YAML string with canonical field ordering.

        Retrieves the agent from cache or DB, builds an ordered dict with
        fields in the specified order, omits null-valued fields, and returns
        the YAML string.

        Args:
            agent_id: The agent's database primary key.
            company_id: Company scope for multi-tenancy.

        Returns:
            YAML string representation of the agent definition.

        Raises:
            AgentNotFoundError: If agent not found or not in company scope.
        """
        agent = await self.get_agent(agent_id, company_id)
        if agent is None:
            raise AgentNotFoundError(
                f"Agent {agent_id} not found for company {company_id}"
            )

        # Parse the stored YAML content to get all fields
        yaml_data = yaml.safe_load(agent.yaml_content)

        # Build ordered dict with canonical field ordering, omitting None values
        ordered: OrderedDict[str, Any] = OrderedDict()

        for field_name in self._EXPORT_FIELD_ORDER:
            value = yaml_data.get(field_name)
            if value is not None:
                ordered[field_name] = value

        return yaml.dump(
            dict(ordered),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    async def import_agent_yaml(
        self, yaml_content: str, company_id: int, user_id: int
    ) -> AgentDefinitionDB:
        """Import an agent definition from a YAML string.

        Validates file size, parses YAML, validates against schema (which
        rejects unknown fields), checks for name conflicts within the
        company scope, and creates the agent.

        Args:
            yaml_content: Raw YAML string to import.
            company_id: Company scope for multi-tenancy.
            user_id: ID of the importing user.

        Returns:
            The created AgentDefinitionDB instance.

        Raises:
            AgentImportError: If the import fails validation (size, schema,
                name conflict, or missing/invalid fields).
        """
        # Check file size limit (1 MB)
        content_size = len(yaml_content.encode("utf-8"))
        if content_size > self._MAX_IMPORT_SIZE:
            raise AgentImportError(
                [f"File exceeds 1 MB size limit (size: {content_size} bytes)"]
            )

        # Parse YAML content
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise AgentImportError([f"YAML parse error: {e}"])

        if not isinstance(data, dict):
            raise AgentImportError(
                [f"Expected YAML mapping, got {type(data).__name__}"]
            )

        # Validate against schema (rejects unknown fields via additionalProperties: false)
        errors = self._schema_validator.validate(data)
        if errors:
            raise AgentImportError(errors)

        # Check for name conflicts within company scope
        agent_name = data.get("name", "")
        await self._check_name_conflict(agent_name, company_id)

        # Create the agent
        return await self.create_agent(data, company_id, user_id)

    async def _check_name_conflict(
        self, name: str, company_id: int
    ) -> None:
        """Check if an active agent with the given name exists in the company.

        Args:
            name: Agent name to check.
            company_id: Company scope for multi-tenancy.

        Raises:
            AgentImportError: If an active agent with the same name exists.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentDefinitionDB).where(
                    AgentDefinitionDB.name == name,
                    AgentDefinitionDB.company_id == company_id,
                    AgentDefinitionDB.is_active == True,  # noqa: E712
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                raise AgentImportError(
                    [f"Agent with name '{name}' already exists in this company"]
                )



