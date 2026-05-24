"""Property-based tests for schema version routing.

Tests Property 2: Schema version routing from the
modular-agent-registry-personality-framework design document.

Property 2 validates that for any agent definition dict:
- If schema_version is "1.0", validation succeeds without requiring archetype,
  personality_profile, contextual_tuning, or evaluation_rubric fields
- If schema_version is "2.0", validation requires the archetype field
- If schema_version is any other string, validation returns an error indicating
  unsupported version

Feature: modular-agent-registry, Property 2: Schema version routing

**Validates: Requirements 1.6, 1.7**

References:
    - Design: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/design.md (Property 2)
    - Requirements: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/requirements.md
    - Implementation: src/backend/src/alcoabase/services/schema_validator.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings, assume

from alcoabase.services.schema_validator import SchemaValidator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_DIR = Path(__file__).resolve().parents[4] / "agents" / "schema"


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def valid_v1_definition(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a random valid v1.0 agent definition.

    Produces definitions with all required v1.0 fields (schema_version, name,
    description, system_prompt, dspy_modules, knowledge_scopes) but WITHOUT
    any v2.0-only fields (archetype, personality_profile, contextual_tuning,
    evaluation_rubric).
    """
    name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_"
    )))
    description = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_."
    )))
    system_prompt = draw(st.text(min_size=1, max_size=200, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_."
    )))

    # Generate dspy_modules (at least 1 item required)
    num_modules = draw(st.integers(min_value=1, max_value=3))
    dspy_modules = []
    for _ in range(num_modules):
        module_name = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="_"
        )))
        module_type = draw(st.sampled_from(["ChainOfThought", "ColBERTv2Retriever", "Predict"]))
        dspy_modules.append({"name": module_name, "type": module_type})

    # Generate knowledge_scopes with tags
    num_tags = draw(st.integers(min_value=1, max_value=5))
    tags = draw(st.lists(
        st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="_-"
        )),
        min_size=num_tags,
        max_size=num_tags,
    ))

    definition: dict[str, Any] = {
        "schema_version": "1.0",
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "dspy_modules": dspy_modules,
        "knowledge_scopes": {"tags": tags},
    }

    return definition


@st.composite
def v2_definition_without_archetype(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a v2.0 agent definition that is missing the required archetype field.

    This should always fail validation because v2.0 requires archetype.
    """
    name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_"
    )))
    description = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_."
    )))
    system_prompt = draw(st.text(min_size=1, max_size=200, alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"), whitelist_characters="-_."
    )))

    # Generate dspy_modules
    module_name = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="_"
    )))
    module_type = draw(st.sampled_from(["ChainOfThought", "ColBERTv2Retriever", "Predict"]))

    # Generate knowledge_scopes
    tags = draw(st.lists(
        st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="_-"
        )),
        min_size=1,
        max_size=5,
    ))

    definition: dict[str, Any] = {
        "schema_version": "2.0",
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "dspy_modules": [{"name": module_name, "type": module_type}],
        "knowledge_scopes": {"tags": tags},
        # Deliberately omit archetype to test that v2.0 requires it
    }

    return definition


def unsupported_version_strings() -> st.SearchStrategy[str]:
    """Generate random version strings that are NOT "1.0" or "2.0".

    Includes empty strings, numeric-looking strings, and arbitrary text.
    """
    return st.one_of(
        st.just(""),
        st.just("0.0"),
        st.just("1.1"),
        st.just("2.1"),
        st.just("3.0"),
        st.just("v1.0"),
        st.just("v2.0"),
        st.text(min_size=0, max_size=20, alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="._-"
        )).filter(lambda s: s not in ("1.0", "2.0")),
    )


# ---------------------------------------------------------------------------
# Property 2: Schema version routing
# ---------------------------------------------------------------------------


class TestSchemaVersionRoutingProperties:
    """Property tests for schema version routing.

    For any agent definition dict:
    - schema_version "1.0" validates without v2.0 fields
    - schema_version "2.0" requires archetype
    - any other schema_version produces an unsupported version error

    Feature: modular-agent-registry, Property 2: Schema version routing

    **Validates: Requirements 1.6, 1.7**
    """

    def setup_method(self) -> None:
        """Set up the SchemaValidator with the project schema directory."""
        self.validator = SchemaValidator(SCHEMA_DIR)

    @given(definition=valid_v1_definition())
    @settings(max_examples=100)
    def test_v1_definitions_pass_without_v2_fields(
        self,
        definition: dict[str, Any],
    ) -> None:
        """For any valid v1.0 definition (without archetype, personality_profile,
        contextual_tuning, evaluation_rubric), validation passes with zero errors.

        **Validates: Requirements 1.6**
        """
        errors = self.validator.validate(definition)

        assert errors == [], (
            f"Valid v1.0 definition should pass validation but got errors: {errors}. "
            f"Definition: {definition}"
        )

    @given(definition=v2_definition_without_archetype())
    @settings(max_examples=100)
    def test_v2_definitions_without_archetype_fail(
        self,
        definition: dict[str, Any],
    ) -> None:
        """For any v2.0 definition without archetype, validation fails with an
        error mentioning archetype.

        **Validates: Requirements 1.7**
        """
        errors = self.validator.validate(definition)

        assert len(errors) > 0, (
            f"v2.0 definition without archetype should fail validation. "
            f"Definition: {definition}"
        )

        # At least one error should mention 'archetype'
        archetype_errors = [e for e in errors if "archetype" in e.lower()]
        assert len(archetype_errors) > 0, (
            f"v2.0 validation errors should mention 'archetype' as required. "
            f"Got errors: {errors}"
        )

    @given(version=unsupported_version_strings())
    @settings(max_examples=100)
    def test_unsupported_versions_produce_error(
        self,
        version: str,
    ) -> None:
        """For any random version string that is NOT "1.0" or "2.0", validation
        returns an error indicating unsupported version.

        **Validates: Requirements 1.7**
        """
        # Build a minimal definition with the unsupported version
        definition: dict[str, Any] = {
            "schema_version": version,
            "name": "test-agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent.",
            "dspy_modules": [{"name": "analyze", "type": "ChainOfThought"}],
            "knowledge_scopes": {"tags": ["test"]},
        }

        errors = self.validator.validate(definition)

        assert len(errors) > 0, (
            f"Unsupported version '{version}' should produce validation errors. "
            f"Definition: {definition}"
        )

        # Error should mention 'unsupported' or the version string
        error_text = " ".join(errors).lower()
        assert "unsupported" in error_text or "version" in error_text, (
            f"Error for unsupported version '{version}' should mention "
            f"'unsupported' or 'version'. Got errors: {errors}"
        )
