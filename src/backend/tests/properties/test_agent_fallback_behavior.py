"""Property-based tests for agent fallback behavior.

Tests Property 18 from the AI-Driven Change Impact Analysis design document,
validating that when the Change Impact Analyst archetype is not found in the
registry, the system falls back to the Regulatory Compliance Auditor with an
appended system prompt suffix, and records "fallback_used" in job metadata.

**Validates: Requirements 7.5**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md (Property 18)
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md (7.5)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.gap_analysis import (
    CHANGE_IMPACT_ANALYST,
    FALLBACK_AGENT,
    GapAnalysisService,
    _FALLBACK_PROMPT_SUFFIX,
)
from alcoabase.services.impact_analysis import ImpactAnalysisService

# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_archetype_entry(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random archetype entry (not the Change Impact Analyst).

    Returns:
        Dict mimicking an archetype definition with random name, system_prompt,
        and contextual_tuning values.
    """
    # Generate a name that is NOT "Change Impact Analyst"
    name = draw(
        st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=3,
            max_size=50,
        ).filter(
            lambda s: s.strip() != CHANGE_IMPACT_ANALYST
            and s.strip() != FALLBACK_AGENT
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
def st_fallback_archetype(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a Regulatory Compliance Auditor archetype entry.

    Returns:
        Dict mimicking the fallback archetype definition with random
        system_prompt and contextual_tuning values.
    """
    system_prompt = draw(
        st.text(min_size=10, max_size=200).filter(lambda s: s.strip())
    )
    temperature = draw(st.floats(min_value=0.0, max_value=1.0))
    max_tokens = draw(st.integers(min_value=256, max_value=8192))

    return {
        "archetype": FALLBACK_AGENT,
        "name": FALLBACK_AGENT,
        "system_prompt": system_prompt,
        "contextual_tuning": {
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    }


@st.composite
def st_primary_archetype(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a Change Impact Analyst archetype entry.

    Returns:
        Dict mimicking the primary archetype definition with random
        system_prompt and contextual_tuning values.
    """
    system_prompt = draw(
        st.text(min_size=10, max_size=200).filter(lambda s: s.strip())
    )
    temperature = draw(st.floats(min_value=0.0, max_value=1.0))
    max_tokens = draw(st.integers(min_value=256, max_value=8192))

    return {
        "archetype": CHANGE_IMPACT_ANALYST,
        "name": CHANGE_IMPACT_ANALYST,
        "system_prompt": system_prompt,
        "contextual_tuning": {
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    }


@st.composite
def st_registry_without_primary(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a registry state that does NOT contain the Change Impact Analyst.

    May or may not contain the Regulatory Compliance Auditor fallback.

    Returns:
        List of archetype dicts without the primary agent.
    """
    # Include 0-5 random non-primary, non-fallback archetypes
    other_archetypes = draw(
        st.lists(st_archetype_entry(), min_size=0, max_size=5)
    )
    # Decide whether to include the fallback agent
    include_fallback = draw(st.booleans())
    if include_fallback:
        fallback = draw(st_fallback_archetype())
        other_archetypes.append(fallback)
    return other_archetypes


@st.composite
def st_registry_with_primary(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a registry state that DOES contain the Change Impact Analyst.

    Returns:
        List of archetype dicts including the primary agent.
    """
    # Include 0-3 random non-primary archetypes
    other_archetypes = draw(
        st.lists(st_archetype_entry(), min_size=0, max_size=3)
    )
    primary = draw(st_primary_archetype())
    other_archetypes.append(primary)
    return other_archetypes


@st.composite
def st_dependency_type(draw: st.DrawFn) -> str:
    """Generate a valid dependency type for gap analysis.

    Returns:
        One of the valid dependency type strings.
    """
    return draw(
        st.sampled_from(
            ["validates", "references", "implements", "trains_on", "derived_from"]
        )
    )


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


def _make_gap_analysis_service(
    archetypes: list[dict[str, Any]],
) -> GapAnalysisService:
    """Create a GapAnalysisService with mocked dependencies and given archetypes.

    Args:
        archetypes: List of archetype dicts for the mock registry.

    Returns:
        GapAnalysisService instance with mocked session, knowledge_service,
        inference_client, and the configured agent_registry.
    """
    registry = _make_mock_registry(archetypes)
    session = AsyncMock()
    knowledge_service = MagicMock()
    inference_client = MagicMock()
    return GapAnalysisService(
        session=session,
        knowledge_service=knowledge_service,
        inference_client=inference_client,
        agent_registry=registry,
    )


def _has_fallback_agent(archetypes: list[dict[str, Any]]) -> bool:
    """Check if the archetype list contains the Regulatory Compliance Auditor.

    Args:
        archetypes: List of archetype dicts.

    Returns:
        True if the fallback agent is present.
    """
    return any(a.get("archetype") == FALLBACK_AGENT for a in archetypes)


def _has_primary_agent(archetypes: list[dict[str, Any]]) -> bool:
    """Check if the archetype list contains the Change Impact Analyst.

    Args:
        archetypes: List of archetype dicts.

    Returns:
        True if the primary agent is present.
    """
    return any(a.get("archetype") == CHANGE_IMPACT_ANALYST for a in archetypes)


# ---------------------------------------------------------------------------
# Property 18: Agent Fallback Behavior — ImpactAnalysisService
# ---------------------------------------------------------------------------


# Feature: ai-driven-change-impact-analysis, Property 18: Agent Fallback Behavior
@settings(max_examples=50)
@given(archetypes=st_registry_without_primary())
def test_impact_analysis_fallback_when_primary_missing(
    archetypes: list[dict[str, Any]],
) -> None:
    """When the Change Impact Analyst archetype is NOT in the registry,
    ImpactAnalysisService._get_agent_config SHALL return fallback_used=True
    if the Regulatory Compliance Auditor is present, and the system prompt
    SHALL include the fallback suffix.

    If neither agent is present, fallback_used SHALL be False (default config).

    **Validates: Requirements 7.5**
    """
    registry = _make_mock_registry(archetypes)
    service = ImpactAnalysisService(agent_registry=registry)

    system_prompt, temperature, max_tokens, fallback_used = service._get_agent_config()

    has_fallback = _has_fallback_agent(archetypes)

    if has_fallback:
        # Fallback should be used and recorded
        assert fallback_used is True, (
            "fallback_used must be True when primary agent is missing "
            "but Regulatory Compliance Auditor is available"
        )
        # System prompt should contain the fallback suffix content
        assert "Change Impact Analyst" in system_prompt, (
            "Fallback system prompt must mention Change Impact Analyst role"
        )
    else:
        # No fallback agent available — default config used
        assert fallback_used is False, (
            "fallback_used must be False when neither primary nor fallback "
            "agent is in the registry"
        )


# Feature: ai-driven-change-impact-analysis, Property 18: Agent Fallback Behavior
@settings(max_examples=50)
@given(archetypes=st_registry_with_primary())
def test_impact_analysis_no_fallback_when_primary_present(
    archetypes: list[dict[str, Any]],
) -> None:
    """When the Change Impact Analyst archetype IS in the registry,
    ImpactAnalysisService._get_agent_config SHALL return fallback_used=False
    and use the primary agent's configuration.

    **Validates: Requirements 7.5**
    """
    registry = _make_mock_registry(archetypes)
    service = ImpactAnalysisService(agent_registry=registry)

    system_prompt, temperature, max_tokens, fallback_used = service._get_agent_config()

    assert fallback_used is False, (
        "fallback_used must be False when the Change Impact Analyst is present"
    )

    # Find the primary archetype to verify config is used
    primary = next(
        a for a in archetypes if a.get("archetype") == CHANGE_IMPACT_ANALYST
    )
    expected_temp = primary["contextual_tuning"]["temperature"]
    expected_tokens = primary["contextual_tuning"]["max_tokens"]

    assert temperature == expected_temp, (
        f"Temperature should match primary archetype: {expected_temp}, got {temperature}"
    )
    assert max_tokens == expected_tokens, (
        f"Max tokens should match primary archetype: {expected_tokens}, got {max_tokens}"
    )


# ---------------------------------------------------------------------------
# Property 18: Agent Fallback Behavior — GapAnalysisService
# ---------------------------------------------------------------------------


# Feature: ai-driven-change-impact-analysis, Property 18: Agent Fallback Behavior
@settings(max_examples=50)
@given(
    archetypes=st_registry_without_primary(),
    dependency_type=st_dependency_type(),
)
def test_gap_analysis_fallback_when_primary_missing(
    archetypes: list[dict[str, Any]],
    dependency_type: str,
) -> None:
    """When the Change Impact Analyst archetype is NOT in the registry,
    GapAnalysisService._get_agent_config SHALL return fallback_used=True
    if the Regulatory Compliance Auditor is present, and the system prompt
    SHALL include the fallback prompt suffix.

    If neither agent is present, fallback_used SHALL be False (default config).

    **Validates: Requirements 7.5**
    """
    registry = _make_mock_registry(archetypes)
    service = _make_gap_analysis_service(archetypes)

    system_prompt, temperature, max_tokens, fallback_used = (
        service._get_agent_config(dependency_type)
    )

    has_fallback = _has_fallback_agent(archetypes)

    if has_fallback:
        # Fallback should be used and recorded
        assert fallback_used is True, (
            "fallback_used must be True when primary agent is missing "
            "but Regulatory Compliance Auditor is available"
        )
        # System prompt should contain the fallback suffix
        assert _FALLBACK_PROMPT_SUFFIX in system_prompt, (
            "Fallback system prompt must include the _FALLBACK_PROMPT_SUFFIX"
        )
    else:
        # No fallback agent available — default config used
        assert fallback_used is False, (
            "fallback_used must be False when neither primary nor fallback "
            "agent is in the registry"
        )


# Feature: ai-driven-change-impact-analysis, Property 18: Agent Fallback Behavior
@settings(max_examples=50)
@given(
    archetypes=st_registry_with_primary(),
    dependency_type=st_dependency_type(),
)
def test_gap_analysis_no_fallback_when_primary_present(
    archetypes: list[dict[str, Any]],
    dependency_type: str,
) -> None:
    """When the Change Impact Analyst archetype IS in the registry,
    GapAnalysisService._get_agent_config SHALL return fallback_used=False
    and use the primary agent's configuration.

    **Validates: Requirements 7.5**
    """
    registry = _make_mock_registry(archetypes)
    service = _make_gap_analysis_service(archetypes)

    system_prompt, temperature, max_tokens, fallback_used = (
        service._get_agent_config(dependency_type)
    )

    assert fallback_used is False, (
        "fallback_used must be False when the Change Impact Analyst is present"
    )

    # Find the primary archetype to verify config is used
    primary = next(
        a for a in archetypes if a.get("archetype") == CHANGE_IMPACT_ANALYST
    )
    expected_temp = primary["contextual_tuning"]["temperature"]
    expected_tokens = primary["contextual_tuning"]["max_tokens"]

    assert temperature == expected_temp, (
        f"Temperature should match primary archetype: {expected_temp}, got {temperature}"
    )
    assert max_tokens == expected_tokens, (
        f"Max tokens should match primary archetype: {expected_tokens}, got {max_tokens}"
    )


# ---------------------------------------------------------------------------
# Property 18: Fallback metadata recording
# ---------------------------------------------------------------------------


# Feature: ai-driven-change-impact-analysis, Property 18: Agent Fallback Behavior
@settings(max_examples=50)
@given(archetypes=st_registry_without_primary())
def test_gap_analysis_fallback_metadata_recorded(
    archetypes: list[dict[str, Any]],
) -> None:
    """When fallback is used, GapAnalysisService.get_fallback_metadata SHALL
    return a dict with "fallback_used" key containing the missing and used
    archetype names. When fallback is NOT used, it SHALL return None.

    **Validates: Requirements 7.5**
    """
    registry = _make_mock_registry(archetypes)
    service = _make_gap_analysis_service(archetypes)

    metadata = service.get_fallback_metadata()
    has_fallback = _has_fallback_agent(archetypes)

    if has_fallback:
        assert metadata is not None, (
            "get_fallback_metadata must return metadata when fallback is used"
        )
        assert "fallback_used" in metadata, (
            "Metadata must contain 'fallback_used' key"
        )
        assert metadata["fallback_used"]["missing_archetype"] == CHANGE_IMPACT_ANALYST
        assert metadata["fallback_used"]["used_archetype"] == FALLBACK_AGENT
    else:
        assert metadata is None, (
            "get_fallback_metadata must return None when no fallback is used"
        )
