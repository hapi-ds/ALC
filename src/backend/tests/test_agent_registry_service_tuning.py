"""Unit tests for AgentRegistryService tuning parameter resolution and rubric methods.

Tests cover:
- get_tuning_params: default values, agent-specific values, override merging, range validation
- get_system_prompt_with_rubric: rubric appending, no-rubric passthrough

References:
    - Task 6.3: Implement tuning parameter resolution
    - Requirements: 4.1, 4.2, 4.5, 4.6, 4.7
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from alcoabase.models.agent import AgentDefinition as AgentDefinitionDB
from alcoabase.schemas.agent import ContextualTuning
from alcoabase.services.agent_registry import AgentRegistryService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> AgentRegistryService:
    """Create an AgentRegistryService with mocked dependencies."""
    mock_session_factory = MagicMock()
    mock_schema_validator = MagicMock()
    agents_dir = Path("/tmp/agents")
    archetypes_dir = Path("/tmp/archetypes")

    return AgentRegistryService(
        session_factory=mock_session_factory,
        schema_validator=mock_schema_validator,
        agents_dir=agents_dir,
        archetypes_dir=archetypes_dir,
    )


def _make_agent_db(
    agent_id: int = 1,
    contextual_tuning: dict | None = None,
    evaluation_rubric: dict | None = None,
    yaml_content: str = 'system_prompt: "You are a helpful agent."',
) -> AgentDefinitionDB:
    """Create a mock AgentDefinitionDB instance for testing."""
    agent = MagicMock(spec=AgentDefinitionDB)
    agent.id = agent_id
    agent.contextual_tuning = contextual_tuning
    agent.evaluation_rubric = evaluation_rubric
    agent.yaml_content = yaml_content
    return agent


# ---------------------------------------------------------------------------
# Tests: get_tuning_params - defaults
# ---------------------------------------------------------------------------


class TestGetTuningParamsDefaults:
    """Tests for default tuning parameter resolution."""

    def test_returns_defaults_when_no_contextual_tuning(
        self, service: AgentRegistryService
    ) -> None:
        """Agent with no contextual_tuning returns system defaults."""
        agent = _make_agent_db(agent_id=1, contextual_tuning=None)
        service._cache[1] = agent

        result = service.get_tuning_params(1)

        assert result.temperature == 0.3
        assert result.max_tokens == 4096
        assert result.top_p == 1.0
        assert result.frequency_penalty == 0.0
        assert result.presence_penalty == 0.0

    def test_returns_contextual_tuning_instance(
        self, service: AgentRegistryService
    ) -> None:
        """Return type is a ContextualTuning Pydantic model."""
        agent = _make_agent_db(agent_id=1, contextual_tuning=None)
        service._cache[1] = agent

        result = service.get_tuning_params(1)

        assert isinstance(result, ContextualTuning)

    def test_raises_key_error_for_unknown_agent(
        self, service: AgentRegistryService
    ) -> None:
        """Raises KeyError when agent_id is not in cache."""
        with pytest.raises(KeyError, match="Agent not found: 999"):
            service.get_tuning_params(999)


# ---------------------------------------------------------------------------
# Tests: get_tuning_params - agent-specific values
# ---------------------------------------------------------------------------


class TestGetTuningParamsAgentValues:
    """Tests for agent-specific tuning parameter resolution."""

    def test_uses_agent_contextual_tuning(
        self, service: AgentRegistryService
    ) -> None:
        """Agent with contextual_tuning uses those values."""
        agent = _make_agent_db(
            agent_id=2,
            contextual_tuning={
                "temperature": 0.1,
                "max_tokens": 8192,
                "top_p": 0.95,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.05,
            },
        )
        service._cache[2] = agent

        result = service.get_tuning_params(2)

        assert result.temperature == 0.1
        assert result.max_tokens == 8192
        assert result.top_p == 0.95
        assert result.frequency_penalty == 0.1
        assert result.presence_penalty == 0.05

    def test_partial_contextual_tuning_fills_defaults(
        self, service: AgentRegistryService
    ) -> None:
        """Agent with partial contextual_tuning fills missing fields from defaults."""
        agent = _make_agent_db(
            agent_id=3,
            contextual_tuning={"temperature": 0.7},
        )
        service._cache[3] = agent

        result = service.get_tuning_params(3)

        assert result.temperature == 0.7
        assert result.max_tokens == 4096  # default
        assert result.top_p == 1.0  # default
        assert result.frequency_penalty == 0.0  # default
        assert result.presence_penalty == 0.0  # default


# ---------------------------------------------------------------------------
# Tests: get_tuning_params - overrides
# ---------------------------------------------------------------------------


class TestGetTuningParamsOverrides:
    """Tests for invocation-time override merging."""

    def test_overrides_take_precedence_over_agent_defaults(
        self, service: AgentRegistryService
    ) -> None:
        """Overrides replace agent-specific values."""
        agent = _make_agent_db(
            agent_id=4,
            contextual_tuning={
                "temperature": 0.1,
                "max_tokens": 8192,
                "top_p": 0.95,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.05,
            },
        )
        service._cache[4] = agent

        result = service.get_tuning_params(4, overrides={"temperature": 1.5})

        assert result.temperature == 1.5
        assert result.max_tokens == 8192  # agent default preserved
        assert result.top_p == 0.95  # agent default preserved

    def test_overrides_take_precedence_over_system_defaults(
        self, service: AgentRegistryService
    ) -> None:
        """Overrides replace system defaults when agent has no tuning."""
        agent = _make_agent_db(agent_id=5, contextual_tuning=None)
        service._cache[5] = agent

        result = service.get_tuning_params(5, overrides={"max_tokens": 2048})

        assert result.max_tokens == 2048
        assert result.temperature == 0.3  # system default preserved

    def test_empty_overrides_dict_uses_agent_values(
        self, service: AgentRegistryService
    ) -> None:
        """Empty overrides dict doesn't change anything."""
        agent = _make_agent_db(
            agent_id=6,
            contextual_tuning={"temperature": 0.5},
        )
        service._cache[6] = agent

        result = service.get_tuning_params(6, overrides={})

        assert result.temperature == 0.5


# ---------------------------------------------------------------------------
# Tests: get_tuning_params - range validation
# ---------------------------------------------------------------------------


class TestGetTuningParamsValidation:
    """Tests for tuning parameter range validation."""

    def test_temperature_below_range_raises(
        self, service: AgentRegistryService
    ) -> None:
        """Temperature below 0.0 raises ValueError."""
        agent = _make_agent_db(agent_id=10, contextual_tuning=None)
        service._cache[10] = agent

        with pytest.raises(ValueError, match="temperature"):
            service.get_tuning_params(10, overrides={"temperature": -0.1})

    def test_temperature_above_range_raises(
        self, service: AgentRegistryService
    ) -> None:
        """Temperature above 2.0 raises ValueError."""
        agent = _make_agent_db(agent_id=11, contextual_tuning=None)
        service._cache[11] = agent

        with pytest.raises(ValueError, match="temperature"):
            service.get_tuning_params(11, overrides={"temperature": 2.1})

    def test_max_tokens_below_one_raises(
        self, service: AgentRegistryService
    ) -> None:
        """max_tokens below 1 raises ValueError."""
        agent = _make_agent_db(agent_id=12, contextual_tuning=None)
        service._cache[12] = agent

        with pytest.raises(ValueError, match="max_tokens"):
            service.get_tuning_params(12, overrides={"max_tokens": 0})

    def test_top_p_above_range_raises(
        self, service: AgentRegistryService
    ) -> None:
        """top_p above 1.0 raises ValueError."""
        agent = _make_agent_db(agent_id=13, contextual_tuning=None)
        service._cache[13] = agent

        with pytest.raises(ValueError, match="top_p"):
            service.get_tuning_params(13, overrides={"top_p": 1.1})

    def test_frequency_penalty_below_range_raises(
        self, service: AgentRegistryService
    ) -> None:
        """frequency_penalty below -2.0 raises ValueError."""
        agent = _make_agent_db(agent_id=14, contextual_tuning=None)
        service._cache[14] = agent

        with pytest.raises(ValueError, match="frequency_penalty"):
            service.get_tuning_params(14, overrides={"frequency_penalty": -2.1})

    def test_presence_penalty_above_range_raises(
        self, service: AgentRegistryService
    ) -> None:
        """presence_penalty above 2.0 raises ValueError."""
        agent = _make_agent_db(agent_id=15, contextual_tuning=None)
        service._cache[15] = agent

        with pytest.raises(ValueError, match="presence_penalty"):
            service.get_tuning_params(15, overrides={"presence_penalty": 2.1})

    def test_boundary_values_accepted(
        self, service: AgentRegistryService
    ) -> None:
        """Boundary values (min/max) are accepted without error."""
        agent = _make_agent_db(agent_id=16, contextual_tuning=None)
        service._cache[16] = agent

        result = service.get_tuning_params(
            16,
            overrides={
                "temperature": 0.0,
                "max_tokens": 1,
                "top_p": 0.0,
                "frequency_penalty": -2.0,
                "presence_penalty": 2.0,
            },
        )

        assert result.temperature == 0.0
        assert result.max_tokens == 1
        assert result.top_p == 0.0
        assert result.frequency_penalty == -2.0
        assert result.presence_penalty == 2.0

    def test_max_boundary_values_accepted(
        self, service: AgentRegistryService
    ) -> None:
        """Maximum boundary values are accepted."""
        agent = _make_agent_db(agent_id=17, contextual_tuning=None)
        service._cache[17] = agent

        result = service.get_tuning_params(
            17,
            overrides={
                "temperature": 2.0,
                "top_p": 1.0,
                "frequency_penalty": 2.0,
                "presence_penalty": 2.0,
            },
        )

        assert result.temperature == 2.0
        assert result.top_p == 1.0
        assert result.frequency_penalty == 2.0
        assert result.presence_penalty == 2.0


# ---------------------------------------------------------------------------
# Tests: get_system_prompt_with_rubric
# ---------------------------------------------------------------------------


class TestGetSystemPromptWithRubric:
    """Tests for system prompt with evaluation rubric appending."""

    def test_returns_prompt_unchanged_when_no_rubric(
        self, service: AgentRegistryService
    ) -> None:
        """System prompt returned as-is when no evaluation_rubric."""
        agent = _make_agent_db(
            agent_id=20,
            evaluation_rubric=None,
            yaml_content='system_prompt: "You are a compliance auditor."',
        )
        service._cache[20] = agent

        result = service.get_system_prompt_with_rubric(20)

        assert result == "You are a compliance auditor."

    def test_returns_prompt_unchanged_when_rubric_has_no_criteria(
        self, service: AgentRegistryService
    ) -> None:
        """System prompt returned as-is when rubric has empty criteria."""
        agent = _make_agent_db(
            agent_id=21,
            evaluation_rubric={"criteria": [], "severity_thresholds": {}, "scoring_method": "weighted_average"},
            yaml_content='system_prompt: "You are a reviewer."',
        )
        service._cache[21] = agent

        result = service.get_system_prompt_with_rubric(21)

        assert result == "You are a reviewer."

    def test_appends_rubric_criteria_to_prompt(
        self, service: AgentRegistryService
    ) -> None:
        """Rubric criteria are appended to the system prompt."""
        agent = _make_agent_db(
            agent_id=22,
            evaluation_rubric={
                "criteria": [
                    {"name": "Regulatory Coverage", "weight": 0.4, "description": "All regulations addressed"},
                    {"name": "Data Completeness", "weight": 0.3, "description": "Supporting data present"},
                ],
                "severity_thresholds": {"critical": 0.9, "major": 0.7},
                "scoring_method": "weighted_average",
            },
            yaml_content='system_prompt: "You are an auditor."',
        )
        service._cache[22] = agent

        result = service.get_system_prompt_with_rubric(22)

        assert result.startswith("You are an auditor.")
        assert "## Evaluation Rubric" in result
        assert "Regulatory Coverage" in result
        assert "All regulations addressed" in result
        assert "Data Completeness" in result
        assert "Supporting data present" in result

    def test_rubric_format_includes_all_criteria(
        self, service: AgentRegistryService
    ) -> None:
        """All criteria names and descriptions appear in the output."""
        criteria = [
            {"name": f"Criterion {i}", "weight": 0.2, "description": f"Description {i}"}
            for i in range(5)
        ]
        agent = _make_agent_db(
            agent_id=23,
            evaluation_rubric={
                "criteria": criteria,
                "severity_thresholds": {},
                "scoring_method": "pass_fail",
            },
            yaml_content='system_prompt: "Base prompt."',
        )
        service._cache[23] = agent

        result = service.get_system_prompt_with_rubric(23)

        for i in range(5):
            assert f"Criterion {i}" in result
            assert f"Description {i}" in result

    def test_raises_key_error_for_unknown_agent(
        self, service: AgentRegistryService
    ) -> None:
        """Raises KeyError when agent_id is not in cache."""
        with pytest.raises(KeyError, match="Agent not found: 999"):
            service.get_system_prompt_with_rubric(999)
