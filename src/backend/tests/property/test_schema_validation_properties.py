"""Property-based tests for schema validation.

Tests Property 1: Valid v2.0 agent definitions pass schema validation from the
modular-agent-registry-personality-framework design document.

Property 1 validates that for any agent definition dict containing all required
v1.0 fields plus a valid archetype string (1-100 chars), and optional
personality_profile, contextual_tuning, and evaluation_rubric with all values
within valid ranges, the schema validator SHALL return zero validation errors.

Feature: modular-agent-registry, Property 1: Valid v2.0 agent definitions pass schema validation

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 1.10**

References:
    - Design: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/design.md (Property 1)
    - Requirements: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/requirements.md
    - Implementation: src/backend/src/alcoabase/services/schema_validator.py
    - Schema: agents/schema/agent-definition-v2.json
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.schema_validator import SchemaValidator


# ---------------------------------------------------------------------------
# Path to schema directory
# ---------------------------------------------------------------------------

SCHEMA_DIR = Path(__file__).resolve().parents[4] / "agents" / "schema"


# ---------------------------------------------------------------------------
# Hypothesis Strategies for valid v2.0 agent definitions
# ---------------------------------------------------------------------------

# Non-empty printable strings within length bounds
def bounded_text(min_size: int = 1, max_size: int = 50) -> st.SearchStrategy[str]:
    """Generate non-empty printable text within length bounds."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            whitelist_characters=" _-./",
        ),
        min_size=min_size,
        max_size=max_size,
    ).filter(lambda s: s.strip() != "" if min_size > 0 else True)


# Strategy for a valid dspy_module item
dspy_module_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries({
    "name": bounded_text(1, 30),
    "type": bounded_text(1, 30),
})

# Strategy for a valid dspy_module item with optional params
dspy_module_with_params_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries(
    {
        "name": bounded_text(1, 30),
        "type": bounded_text(1, 30),
    },
    optional={
        "params": st.dictionaries(
            keys=bounded_text(1, 15),
            values=st.one_of(
                st.integers(min_value=0, max_value=10000),
                st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
                st.text(min_size=1, max_size=20),
                st.booleans(),
            ),
            min_size=0,
            max_size=3,
        ),
    },
)

# Strategy for knowledge_scopes
knowledge_scopes_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries({
    "tags": st.lists(bounded_text(1, 30), min_size=0, max_size=5),
})

# Strategy for personality_profile
personality_profile_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries({
    "tone": bounded_text(1, 100),
    "verbosity": st.sampled_from(["concise", "moderate", "detailed"]),
    "strictness": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "domain_focus": st.lists(bounded_text(1, 30), min_size=0, max_size=20),
    "communication_style": bounded_text(1, 200),
})

# Strategy for contextual_tuning
contextual_tuning_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries(
    {},
    optional={
        "temperature": st.floats(
            min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
        "max_tokens": st.integers(min_value=1, max_value=131072),
        "top_p": st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        "frequency_penalty": st.floats(
            min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
        "presence_penalty": st.floats(
            min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
    },
)

# Strategy for a single evaluation criterion
evaluation_criterion_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries({
    "name": bounded_text(1, 50),
    "weight": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "description": bounded_text(1, 100),
})

# Strategy for severity_thresholds
severity_thresholds_strategy: st.SearchStrategy[dict[str, float]] = st.fixed_dictionaries({
    "critical": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "major": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "minor": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    "informational": st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
})

# Strategy for evaluation_rubric
evaluation_rubric_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries({
    "criteria": st.lists(evaluation_criterion_strategy, min_size=1, max_size=50),
    "severity_thresholds": severity_thresholds_strategy,
    "scoring_method": st.sampled_from(["weighted_average", "pass_fail", "tiered"]),
})

# Strategy for required_chapters (needed for review agents)
required_chapter_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries(
    {
        "name": bounded_text(1, 30),
        "required": st.booleans(),
    },
    optional={
        "description": bounded_text(1, 50),
    },
)

# Strategy for severity_rules (needed for review agents)
severity_rules_strategy: st.SearchStrategy[dict[str, str]] = st.fixed_dictionaries(
    {},
    optional={
        "critical": bounded_text(1, 50),
        "major": bounded_text(1, 50),
        "minor": bounded_text(1, 50),
        "informational": bounded_text(1, 50),
    },
)


@st.composite
def valid_v2_generation_agent(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid v2.0 agent definition with agent_type='generation'.

    Includes all required fields and optionally includes personality_profile,
    contextual_tuning, and evaluation_rubric with values within valid ranges.

    Returns:
        A valid v2.0 agent definition dictionary.
    """
    definition: dict[str, Any] = {
        "schema_version": "2.0",
        "name": draw(bounded_text(1, 200)),
        "description": draw(bounded_text(1, 200)),
        "archetype": draw(bounded_text(1, 100)),
        "agent_type": "generation",
        "system_prompt": draw(bounded_text(1, 500)),
        "dspy_modules": draw(
            st.lists(
                dspy_module_with_params_strategy,
                min_size=1,
                max_size=3,
            )
        ),
        "knowledge_scopes": draw(knowledge_scopes_strategy),
    }

    # Optionally add personality_profile
    if draw(st.booleans()):
        definition["personality_profile"] = draw(personality_profile_strategy)

    # Optionally add contextual_tuning
    if draw(st.booleans()):
        definition["contextual_tuning"] = draw(contextual_tuning_strategy)

    # Optionally add evaluation_rubric
    if draw(st.booleans()):
        definition["evaluation_rubric"] = draw(evaluation_rubric_strategy)

    return definition


@st.composite
def valid_v2_review_agent(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid v2.0 agent definition with agent_type='review'.

    Review agents require additional fields: target_document_tag,
    required_chapters, compliance_checklist, and severity_rules.

    Returns:
        A valid v2.0 review agent definition dictionary.
    """
    definition: dict[str, Any] = {
        "schema_version": "2.0",
        "name": draw(bounded_text(1, 200)),
        "description": draw(bounded_text(1, 200)),
        "archetype": draw(bounded_text(1, 100)),
        "agent_type": "review",
        "system_prompt": draw(bounded_text(1, 500)),
        "dspy_modules": draw(
            st.lists(
                dspy_module_with_params_strategy,
                min_size=1,
                max_size=3,
            )
        ),
        "knowledge_scopes": draw(knowledge_scopes_strategy),
        # Review-specific required fields
        "target_document_tag": draw(bounded_text(1, 50)),
        "required_chapters": draw(
            st.lists(required_chapter_strategy, min_size=1, max_size=5)
        ),
        "compliance_checklist": draw(
            st.lists(bounded_text(1, 50), min_size=1, max_size=5)
        ),
        "severity_rules": draw(severity_rules_strategy),
    }

    # Optionally add personality_profile
    if draw(st.booleans()):
        definition["personality_profile"] = draw(personality_profile_strategy)

    # Optionally add contextual_tuning
    if draw(st.booleans()):
        definition["contextual_tuning"] = draw(contextual_tuning_strategy)

    # Optionally add evaluation_rubric
    if draw(st.booleans()):
        definition["evaluation_rubric"] = draw(evaluation_rubric_strategy)

    return definition


@st.composite
def valid_v2_agent_definition(draw: st.DrawFn) -> dict[str, Any]:
    """Generate any valid v2.0 agent definition (generation or review).

    Randomly chooses between generation and review agent types,
    ensuring all conditional requirements are met.

    Returns:
        A valid v2.0 agent definition dictionary.
    """
    if draw(st.booleans()):
        return draw(valid_v2_generation_agent())
    else:
        return draw(valid_v2_review_agent())


# ---------------------------------------------------------------------------
# Property 1: Valid v2.0 agent definitions pass schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidationProperty1:
    """Property tests for schema validation of v2.0 agent definitions.

    For any agent definition dict containing all required v1.0 fields plus a
    valid archetype string (1-100 chars), and optional personality_profile
    (with strictness in [0.0, 1.0], verbosity in {concise, moderate, detailed}),
    contextual_tuning (with temperature in [0.0, 2.0], max_tokens in [1, 131072],
    top_p in [0.0, 1.0], frequency_penalty in [-2.0, 2.0], presence_penalty in
    [-2.0, 2.0]), and evaluation_rubric (with criteria weights in [0.0, 1.0],
    scoring_method in {weighted_average, pass_fail, tiered}), the schema validator
    SHALL return zero validation errors.

    Feature: modular-agent-registry, Property 1: Valid v2.0 agent definitions pass schema validation

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 1.10**
    """

    def setup_method(self) -> None:
        """Set up the schema validator for each test method."""
        self.validator = SchemaValidator(SCHEMA_DIR)

    @given(definition=valid_v2_generation_agent())
    @settings(max_examples=100)
    def test_valid_generation_agents_pass_validation(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Valid v2.0 generation agent definitions produce zero validation errors.

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 1.10**
        """
        errors = self.validator.validate(definition)
        assert errors == [], (
            f"Valid v2.0 generation agent should have no validation errors, "
            f"got: {errors}\n"
            f"Definition: {definition}"
        )

    @given(definition=valid_v2_review_agent())
    @settings(max_examples=100)
    def test_valid_review_agents_pass_validation(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Valid v2.0 review agent definitions produce zero validation errors.

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 1.10**
        """
        errors = self.validator.validate(definition)
        assert errors == [], (
            f"Valid v2.0 review agent should have no validation errors, "
            f"got: {errors}\n"
            f"Definition: {definition}"
        )

    @given(definition=valid_v2_agent_definition())
    @settings(max_examples=100)
    def test_all_valid_v2_definitions_pass_validation(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Any valid v2.0 agent definition (generation or review) produces
        zero validation errors.

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 1.10**
        """
        errors = self.validator.validate(definition)
        assert errors == [], (
            f"Valid v2.0 agent definition should have no validation errors, "
            f"got: {errors}\n"
            f"Definition: {definition}"
        )
