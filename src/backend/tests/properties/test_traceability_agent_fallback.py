"""Property-based tests for Traceability Analyst agent fallback behavior.

Property 10: Agent Fallback Behavior

Remove Traceability Analyst from registry, execute with random inputs, verify
Change Impact Analyst used as fallback with prompt suffix, verify "fallback_used"
recorded in matrix metadata.

When Traceability Analyst is missing but Change Impact Analyst is present,
fallback_used=True and the prompt contains the traceability suffix.

**Validates: Requirements 6.5**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/traceability_matrix.py
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.traceability_matrix import TraceabilityMatrixService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIMARY_AGENT = "Traceability Analyst"
_FALLBACK_AGENT = "Change Impact Analyst"

# The suffix appended to the Change Impact Analyst prompt when used as fallback
_TRACEABILITY_SUFFIX = (
    "\n\nAdditional context: You are acting as a "
    "Traceability Analyst. Focus on requirement-to-test "
    "traceability mapping rather than change impact "
    "assessment. Extract requirements and test cases "
    "from documents, identifying IDs, text, section "
    "headings, and acceptance criteria. Output structured "
    "JSON matching the expected schema exactly."
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_random_archetype(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random archetype entry that is NOT the primary or fallback.

    Returns:
        Dict mimicking an archetype definition with random name, system_prompt,
        and contextual_tuning values.
    """
    name = draw(
        st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=3,
            max_size=50,
        ).filter(
            lambda s: s.strip() != _PRIMARY_AGENT
            and s.strip() != _FALLBACK_AGENT
        )
    )
    system_prompt = draw(
        st.text(min_size=10, max_size=200).filter(lambda s: s.strip())
    )
    temperature = draw(st.floats(min_value=0.0, max_value=1.0))
    max_tokens = draw(st.integers(min_value=256, max_value=8192))

    return {
        "archetype": name.strip(),
        "name": name.strip(),
        "system_prompt": system_prompt,
        "contextual_tuning": {
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    }


@st.composite
def st_change_impact_analyst(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a Change Impact Analyst archetype entry (the fallback agent).

    Returns:
        Dict mimicking the Change Impact Analyst archetype with random
        system_prompt and contextual_tuning values.
    """
    system_prompt = draw(
        st.text(min_size=10, max_size=200).filter(lambda s: s.strip())
    )
    temperature = draw(st.floats(min_value=0.0, max_value=1.0))
    max_tokens = draw(st.integers(min_value=256, max_value=8192))

    return {
        "archetype": _FALLBACK_AGENT,
        "name": _FALLBACK_AGENT,
        "system_prompt": system_prompt,
        "contextual_tuning": {
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    }


@st.composite
def st_traceability_analyst(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a Traceability Analyst archetype entry (the primary agent).

    Returns:
        Dict mimicking the Traceability Analyst archetype with random
        system_prompt and contextual_tuning values. Includes all required
        schema fields to pass agent-definition-v2.json validation.
    """
    system_prompt = draw(
        st.text(min_size=10, max_size=200).filter(lambda s: s.strip())
    )
    temperature = draw(st.floats(min_value=0.0, max_value=1.0))
    max_tokens = draw(st.integers(min_value=256, max_value=8192))

    return {
        "archetype": _PRIMARY_AGENT,
        "name": _PRIMARY_AGENT,
        "description": "Specialized agent for traceability analysis.",
        "schema_version": "2.0",
        "agent_type": "review",
        "system_prompt": system_prompt,
        "contextual_tuning": {
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        "dspy_modules": [
            {"name": "requirement_extraction", "type": "ChainOfThought"},
            {"name": "link_establishment", "type": "ChainOfThought"},
        ],
        "knowledge_scopes": {"tags": ["Traceability"]},
        "target_document_tag": "All",
        "required_chapters": [
            {"name": "Requirements List", "required": True},
        ],
        "compliance_checklist": ["All requirements extracted"],
        "severity_rules": {
            "critical": "Safety-critical",
            "major": "Functional",
            "minor": "Informational",
            "informational": "Optional",
        },
        "evaluation_rubric": {
            "scoring_method": "weighted_average",
            "criteria": [
                {
                    "name": "Accuracy",
                    "weight": 0.5,
                    "description": "Accuracy of extraction",
                },
            ],
            "severity_thresholds": {
                "critical": 0.9,
                "major": 0.7,
                "minor": 0.4,
                "informational": 0.2,
            },
        },
    }


@st.composite
def st_registry_without_primary(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a registry that does NOT contain the Traceability Analyst.

    Always includes the Change Impact Analyst (fallback agent) to test
    the fallback path.

    Returns:
        List of archetype dicts without the primary agent but with fallback.
    """
    other_archetypes = draw(
        st.lists(st_random_archetype(), min_size=0, max_size=3)
    )
    fallback = draw(st_change_impact_analyst())
    other_archetypes.append(fallback)
    return other_archetypes


@st.composite
def st_registry_without_both(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a registry that contains NEITHER the primary NOR the fallback.

    Returns:
        List of archetype dicts without either agent.
    """
    return draw(st.lists(st_random_archetype(), min_size=0, max_size=5))


@st.composite
def st_registry_with_primary(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a registry that DOES contain the Traceability Analyst.

    Returns:
        List of archetype dicts including the primary agent.
    """
    other_archetypes = draw(
        st.lists(st_random_archetype(), min_size=0, max_size=3)
    )
    primary = draw(st_traceability_analyst())
    other_archetypes.append(primary)
    return other_archetypes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_registry(archetypes: list[dict[str, Any]]) -> MagicMock:
    """Create a mock AgentRegistryService that returns the given archetypes.

    Args:
        archetypes: List of archetype dicts to return from list_archetypes().

    Returns:
        MagicMock with list_archetypes configured.
    """
    registry = MagicMock()
    registry.list_archetypes.return_value = archetypes
    return registry


def _make_service(archetypes: list[dict[str, Any]]) -> TraceabilityMatrixService:
    """Create a TraceabilityMatrixService with mocked agent registry.

    Args:
        archetypes: List of archetype dicts for the mock registry.

    Returns:
        TraceabilityMatrixService instance with the configured agent_registry.
    """
    registry = _make_mock_registry(archetypes)
    return TraceabilityMatrixService(agent_registry=registry)


# ---------------------------------------------------------------------------
# Property 10: Agent Fallback Behavior — Fallback when primary missing
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(archetypes=st_registry_without_primary())
def test_fallback_used_when_traceability_analyst_missing(
    archetypes: list[dict[str, Any]],
) -> None:
    """When the Traceability Analyst archetype is NOT in the registry but
    Change Impact Analyst IS present, _get_agent_config SHALL return
    fallback_used=True and the system prompt SHALL contain the traceability
    suffix appended to the Change Impact Analyst's prompt.

    **Validates: Requirements 6.5**
    """
    service = _make_service(archetypes)

    system_prompt, temperature, max_tokens, fallback_used = (
        service._get_agent_config()
    )

    # Fallback must be used
    assert fallback_used is True, (
        "fallback_used must be True when Traceability Analyst is missing "
        "but Change Impact Analyst is available"
    )

    # System prompt must contain the traceability suffix
    assert "Traceability Analyst" in system_prompt, (
        "Fallback system prompt must mention Traceability Analyst role"
    )
    assert "requirement-to-test traceability mapping" in system_prompt, (
        "Fallback system prompt must instruct focus on traceability mapping"
    )

    # Find the Change Impact Analyst archetype to verify config is used
    fallback_archetype = next(
        a for a in archetypes if a.get("archetype") == _FALLBACK_AGENT
    )
    expected_base_prompt = fallback_archetype["system_prompt"]

    # The system prompt should start with the fallback agent's original prompt
    assert system_prompt.startswith(expected_base_prompt), (
        "Fallback system prompt must start with the Change Impact Analyst's "
        "original system prompt"
    )

    # The suffix should be appended
    assert _TRACEABILITY_SUFFIX in system_prompt, (
        "Fallback system prompt must include the traceability suffix"
    )


# ---------------------------------------------------------------------------
# Property 10: Agent Fallback Behavior — No fallback when primary present
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(archetypes=st_registry_with_primary())
def test_no_fallback_when_traceability_analyst_present(
    archetypes: list[dict[str, Any]],
) -> None:
    """When the Traceability Analyst archetype IS in the registry,
    _get_agent_config SHALL return fallback_used=False and use the
    primary agent's configuration directly.

    **Validates: Requirements 6.5**
    """
    service = _make_service(archetypes)

    system_prompt, temperature, max_tokens, fallback_used = (
        service._get_agent_config()
    )

    assert fallback_used is False, (
        "fallback_used must be False when the Traceability Analyst is present"
    )

    # Find the primary archetype to verify config is used
    primary = next(
        a for a in archetypes if a.get("archetype") == _PRIMARY_AGENT
    )
    expected_prompt = primary["system_prompt"]
    expected_temp = primary["contextual_tuning"]["temperature"]
    expected_tokens = primary["contextual_tuning"]["max_tokens"]

    assert system_prompt == expected_prompt, (
        f"System prompt should match primary archetype's prompt"
    )
    assert temperature == expected_temp, (
        f"Temperature should match primary archetype: {expected_temp}, "
        f"got {temperature}"
    )
    assert max_tokens == expected_tokens, (
        f"Max tokens should match primary archetype: {expected_tokens}, "
        f"got {max_tokens}"
    )


# ---------------------------------------------------------------------------
# Property 10: Agent Fallback Behavior — Default config when neither present
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(archetypes=st_registry_without_both())
def test_default_config_when_neither_agent_present(
    archetypes: list[dict[str, Any]],
) -> None:
    """When NEITHER the Traceability Analyst NOR the Change Impact Analyst
    is in the registry, _get_agent_config SHALL return fallback_used=False
    and use the default configuration.

    **Validates: Requirements 6.5**
    """
    service = _make_service(archetypes)

    system_prompt, temperature, max_tokens, fallback_used = (
        service._get_agent_config()
    )

    # No fallback used — default config
    assert fallback_used is False, (
        "fallback_used must be False when neither primary nor fallback "
        "agent is in the registry"
    )

    # Default values
    assert temperature == 0.15, (
        f"Default temperature should be 0.15, got {temperature}"
    )
    assert max_tokens == 4096, (
        f"Default max_tokens should be 4096, got {max_tokens}"
    )


# ---------------------------------------------------------------------------
# Property 10: Agent Fallback Behavior — Fallback temperature and max_tokens
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(archetypes=st_registry_without_primary())
def test_fallback_uses_change_impact_analyst_tuning(
    archetypes: list[dict[str, Any]],
) -> None:
    """When fallback is used, the temperature and max_tokens SHALL be taken
    from the Change Impact Analyst's contextual_tuning configuration.

    **Validates: Requirements 6.5**
    """
    service = _make_service(archetypes)

    system_prompt, temperature, max_tokens, fallback_used = (
        service._get_agent_config()
    )

    assert fallback_used is True

    # Find the Change Impact Analyst archetype
    fallback_archetype = next(
        a for a in archetypes if a.get("archetype") == _FALLBACK_AGENT
    )
    expected_temp = fallback_archetype["contextual_tuning"]["temperature"]
    expected_tokens = fallback_archetype["contextual_tuning"]["max_tokens"]

    assert temperature == expected_temp, (
        f"Fallback temperature should match Change Impact Analyst: "
        f"{expected_temp}, got {temperature}"
    )
    assert max_tokens == expected_tokens, (
        f"Fallback max_tokens should match Change Impact Analyst: "
        f"{expected_tokens}, got {max_tokens}"
    )
