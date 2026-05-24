"""Property-based tests for tuning parameter resolution.

Tests Properties 4, 5, and 6 from the modular-agent-registry-personality-framework
design document:

- Property 4: Tuning parameter resolution with defaults
- Property 5: Invocation override precedence and range validation
- Property 6: Evaluation rubric appended to system prompt

Feature: modular-agent-registry, Properties 4, 5, 6: Tuning resolution

**Validates: Requirements 4.1, 4.2, 4.5, 4.6, 4.7**

References:
    - Design: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/design.md
    - Requirements: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/requirements.md
    - Implementation: src/backend/src/alcoabase/services/agent_registry.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import hypothesis.strategies as st
import yaml
from hypothesis import given, settings

from alcoabase.models.agent import AgentDefinition as AgentDefinitionDB
from alcoabase.services.agent_registry import (
    DEFAULT_TUNING_PARAMS,
    TUNING_PARAM_RANGES,
    AgentRegistryService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> AgentRegistryService:
    """Create an AgentRegistryService with a mock session_factory."""
    mock_session_factory = MagicMock()
    mock_schema_validator = MagicMock()
    return AgentRegistryService(
        session_factory=mock_session_factory,
        schema_validator=mock_schema_validator,
        agents_dir=Path("/tmp/agents"),
        archetypes_dir=Path("/tmp/archetypes"),
    )


def _make_agent_db(
    agent_id: int,
    contextual_tuning: dict[str, Any] | None = None,
    evaluation_rubric: dict[str, Any] | None = None,
    system_prompt: str = "You are a helpful agent.",
) -> AgentDefinitionDB:
    """Create a mock AgentDefinitionDB object with the given fields."""
    agent = MagicMock(spec=AgentDefinitionDB)
    agent.id = agent_id
    agent.contextual_tuning = contextual_tuning
    agent.evaluation_rubric = evaluation_rubric
    agent.yaml_content = yaml.dump({"system_prompt": system_prompt})
    return agent


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for valid contextual tuning dicts (all params within range)
valid_temperature = st.floats(min_value=0.0, max_value=2.0, allow_nan=False)
valid_max_tokens = st.integers(min_value=1, max_value=131072)
valid_top_p = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
valid_frequency_penalty = st.floats(min_value=-2.0, max_value=2.0, allow_nan=False)
valid_presence_penalty = st.floats(min_value=-2.0, max_value=2.0, allow_nan=False)


@st.composite
def valid_tuning_dict(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid contextual tuning dictionary with all params in range."""
    return {
        "temperature": draw(valid_temperature),
        "max_tokens": draw(valid_max_tokens),
        "top_p": draw(valid_top_p),
        "frequency_penalty": draw(valid_frequency_penalty),
        "presence_penalty": draw(valid_presence_penalty),
    }


@st.composite
def partial_valid_overrides(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a partial override dict with a random subset of valid params."""
    all_params = {
        "temperature": draw(valid_temperature),
        "max_tokens": draw(valid_max_tokens),
        "top_p": draw(valid_top_p),
        "frequency_penalty": draw(valid_frequency_penalty),
        "presence_penalty": draw(valid_presence_penalty),
    }
    # Pick a random non-empty subset of keys
    keys = draw(
        st.lists(
            st.sampled_from(list(all_params.keys())),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    return {k: all_params[k] for k in keys}


@st.composite
def out_of_range_overrides(draw: st.DrawFn) -> dict[str, Any]:
    """Generate an override dict where at least one param is out of range."""
    # Pick which parameter to make invalid
    invalid_param = draw(st.sampled_from(list(TUNING_PARAM_RANGES.keys())))
    min_val, max_val = TUNING_PARAM_RANGES[invalid_param]

    # Generate an out-of-range value
    if invalid_param == "max_tokens":
        # max_tokens must be >= 1, so go below
        invalid_value = draw(st.integers(min_value=-1000, max_value=0))
    elif max_val == float("inf"):
        # Only lower bound matters
        invalid_value = min_val - draw(
            st.floats(min_value=0.01, max_value=100.0, allow_nan=False)
        )
    else:
        # Either below min or above max
        below = min_val - draw(
            st.floats(min_value=0.01, max_value=100.0, allow_nan=False)
        )
        above = max_val + draw(
            st.floats(min_value=0.01, max_value=100.0, allow_nan=False)
        )
        invalid_value = draw(st.sampled_from([below, above]))

    return {invalid_param: invalid_value}


# Strategy for criterion names and descriptions
criterion_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    min_size=1,
    max_size=50,
)
criterion_description = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z", "P")),
    min_size=1,
    max_size=100,
)


@st.composite
def evaluation_rubric_with_criteria(
    draw: st.DrawFn,
) -> dict[str, Any]:
    """Generate an evaluation rubric with at least one criterion."""
    num_criteria = draw(st.integers(min_value=1, max_value=5))
    criteria = []
    for _ in range(num_criteria):
        criteria.append(
            {
                "name": draw(criterion_name),
                "weight": draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)),
                "description": draw(criterion_description),
            }
        )
    return {
        "criteria": criteria,
        "severity_thresholds": {
            "critical": 0.9,
            "major": 0.7,
            "minor": 0.4,
            "informational": 0.2,
        },
        "scoring_method": "weighted_average",
    }


# Strategy for system prompts
system_prompt_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z", "P")),
    min_size=1,
    max_size=200,
)


# ---------------------------------------------------------------------------
# Property 4: Tuning parameter resolution with defaults
# ---------------------------------------------------------------------------


class TestTuningParameterResolutionWithDefaults:
    """Property tests for tuning parameter resolution with defaults.

    For any agent definition, if contextual_tuning is None then get_tuning_params
    SHALL return the default values (temperature=0.3, max_tokens=4096, top_p=1.0,
    frequency_penalty=0.0, presence_penalty=0.0); if contextual_tuning is specified
    then get_tuning_params SHALL return those specified values.

    Feature: modular-agent-registry, Property 4: Tuning parameter resolution with defaults

    **Validates: Requirements 4.1, 4.2**
    """

    @given(agent_id=st.integers(min_value=1, max_value=1000))
    @settings(max_examples=100)
    def test_no_tuning_returns_defaults(self, agent_id: int) -> None:
        """When contextual_tuning is None, get_tuning_params returns system defaults.

        **Validates: Requirements 4.1, 4.2**
        """
        service = _make_service()
        agent = _make_agent_db(agent_id=agent_id, contextual_tuning=None)
        service._cache[agent_id] = agent

        result = service.get_tuning_params(agent_id)

        assert result.temperature == DEFAULT_TUNING_PARAMS["temperature"]
        assert result.max_tokens == DEFAULT_TUNING_PARAMS["max_tokens"]
        assert result.top_p == DEFAULT_TUNING_PARAMS["top_p"]
        assert result.frequency_penalty == DEFAULT_TUNING_PARAMS["frequency_penalty"]
        assert result.presence_penalty == DEFAULT_TUNING_PARAMS["presence_penalty"]

    @given(agent_id=st.integers(min_value=1, max_value=1000), tuning=valid_tuning_dict())
    @settings(max_examples=100)
    def test_specified_tuning_returns_agent_values(
        self, agent_id: int, tuning: dict[str, Any]
    ) -> None:
        """When contextual_tuning is specified, get_tuning_params returns those values.

        **Validates: Requirements 4.1, 4.2**
        """
        service = _make_service()
        agent = _make_agent_db(agent_id=agent_id, contextual_tuning=tuning)
        service._cache[agent_id] = agent

        result = service.get_tuning_params(agent_id)

        assert result.temperature == tuning["temperature"]
        assert result.max_tokens == tuning["max_tokens"]
        assert result.top_p == tuning["top_p"]
        assert result.frequency_penalty == tuning["frequency_penalty"]
        assert result.presence_penalty == tuning["presence_penalty"]


# ---------------------------------------------------------------------------
# Property 5: Invocation override precedence and range validation
# ---------------------------------------------------------------------------


class TestInvocationOverridePrecedence:
    """Property tests for invocation override precedence and range validation.

    For any agent with contextual_tuning and any set of invocation-time override
    parameters, if all override values are within valid ranges then get_tuning_params
    SHALL return the override values for overridden parameters and agent defaults for
    non-overridden parameters; if any override value is outside valid ranges then
    get_tuning_params SHALL raise a validation error.

    Feature: modular-agent-registry, Property 5: Invocation override precedence and range validation

    **Validates: Requirements 4.6, 4.7**
    """

    @given(
        agent_id=st.integers(min_value=1, max_value=1000),
        agent_tuning=valid_tuning_dict(),
        overrides=partial_valid_overrides(),
    )
    @settings(max_examples=100)
    def test_valid_overrides_take_precedence(
        self,
        agent_id: int,
        agent_tuning: dict[str, Any],
        overrides: dict[str, Any],
    ) -> None:
        """Valid overrides take precedence over agent defaults for overridden params.

        **Validates: Requirements 4.6, 4.7**
        """
        service = _make_service()
        agent = _make_agent_db(agent_id=agent_id, contextual_tuning=agent_tuning)
        service._cache[agent_id] = agent

        result = service.get_tuning_params(agent_id, overrides=overrides)

        # Overridden params should have override values
        for param, value in overrides.items():
            assert getattr(result, param) == value, (
                f"Override param '{param}' should be {value}, got {getattr(result, param)}"
            )

        # Non-overridden params should have agent tuning values
        for param in DEFAULT_TUNING_PARAMS:
            if param not in overrides:
                assert getattr(result, param) == agent_tuning[param], (
                    f"Non-overridden param '{param}' should be {agent_tuning[param]}, "
                    f"got {getattr(result, param)}"
                )

    @given(
        agent_id=st.integers(min_value=1, max_value=1000),
        agent_tuning=valid_tuning_dict(),
        bad_overrides=out_of_range_overrides(),
    )
    @settings(max_examples=100)
    def test_out_of_range_overrides_raise_value_error(
        self,
        agent_id: int,
        agent_tuning: dict[str, Any],
        bad_overrides: dict[str, Any],
    ) -> None:
        """Out-of-range override values raise ValueError indicating which param is invalid.

        **Validates: Requirements 4.6, 4.7**
        """
        service = _make_service()
        agent = _make_agent_db(agent_id=agent_id, contextual_tuning=agent_tuning)
        service._cache[agent_id] = agent

        try:
            service.get_tuning_params(agent_id, overrides=bad_overrides)
            # Should not reach here
            assert False, (
                f"Expected ValueError for out-of-range overrides: {bad_overrides}"
            )
        except ValueError as e:
            # Verify the error message mentions the out-of-range parameter
            error_msg = str(e)
            invalid_param = next(iter(bad_overrides))
            assert invalid_param in error_msg, (
                f"Error message should mention '{invalid_param}', got: {error_msg}"
            )


# ---------------------------------------------------------------------------
# Property 6: Evaluation rubric appended to system prompt
# ---------------------------------------------------------------------------


class TestEvaluationRubricAppendedToSystemPrompt:
    """Property tests for evaluation rubric appended to system prompt.

    For any agent definition with a non-null evaluation_rubric containing criteria
    with names and descriptions, get_system_prompt_with_rubric SHALL return a string
    that contains the original system_prompt AND contains each criterion name and
    description from the rubric.

    Feature: modular-agent-registry, Property 6: Evaluation rubric appended to system prompt

    **Validates: Requirements 4.5**
    """

    @given(
        agent_id=st.integers(min_value=1, max_value=1000),
        system_prompt=system_prompt_strategy,
        rubric=evaluation_rubric_with_criteria(),
    )
    @settings(max_examples=100)
    def test_rubric_criteria_appended_to_prompt(
        self,
        agent_id: int,
        system_prompt: str,
        rubric: dict[str, Any],
    ) -> None:
        """System prompt contains original prompt and all rubric criterion names/descriptions.

        **Validates: Requirements 4.5**
        """
        service = _make_service()
        agent = _make_agent_db(
            agent_id=agent_id,
            evaluation_rubric=rubric,
            system_prompt=system_prompt,
        )
        service._cache[agent_id] = agent

        result = service.get_system_prompt_with_rubric(agent_id)

        # Result must contain the original system prompt
        assert system_prompt in result, (
            f"Result should contain original system_prompt '{system_prompt}'"
        )

        # Result must contain each criterion name and description
        for criterion in rubric["criteria"]:
            assert criterion["name"] in result, (
                f"Result should contain criterion name '{criterion['name']}'"
            )
            assert criterion["description"] in result, (
                f"Result should contain criterion description '{criterion['description']}'"
            )

    @given(
        agent_id=st.integers(min_value=1, max_value=1000),
        system_prompt=system_prompt_strategy,
    )
    @settings(max_examples=100)
    def test_no_rubric_returns_prompt_unchanged(
        self,
        agent_id: int,
        system_prompt: str,
    ) -> None:
        """When evaluation_rubric is None, returns the system prompt unchanged.

        **Validates: Requirements 4.5**
        """
        service = _make_service()
        agent = _make_agent_db(
            agent_id=agent_id,
            evaluation_rubric=None,
            system_prompt=system_prompt,
        )
        service._cache[agent_id] = agent

        result = service.get_system_prompt_with_rubric(agent_id)

        assert result == system_prompt, (
            f"Without rubric, result should equal system_prompt. "
            f"Expected '{system_prompt}', got '{result}'"
        )
