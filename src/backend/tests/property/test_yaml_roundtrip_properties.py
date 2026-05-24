"""Property-based tests for YAML round-trip and import validation.

Tests Property 7: YAML serialization round-trip and Property 8: Import
validation rejects invalid definitions from the modular-agent-registry-
personality-framework design document.

Property 7: For any valid v2.0 agent definition, exporting to YAML and
re-importing SHALL produce an agent definition with identical values for all
schema-defined fields (schema_version, name, description, archetype,
personality_profile, contextual_tuning, evaluation_rubric, agent_type,
system_prompt, dspy_modules, knowledge_scopes), with null-valued optional
fields omitted from the YAML output, and field ordering preserved.

Property 8: For any YAML content that contains fields not defined in the
schema, OR is missing required fields, OR contains fields with values outside
their valid ranges, the import operation SHALL reject the content with a
validation error.

Feature: modular-agent-registry, Property 7: YAML serialization round-trip
Feature: modular-agent-registry, Property 8: Import validation rejects invalid definitions

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.7, 5.5**

References:
    - Design: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/design.md
    - Requirements: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/requirements.md
    - Implementation: src/backend/src/alcoabase/services/agent_registry.py
    - Schema: agents/schema/agent-definition-v2.json
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

import hypothesis.strategies as st
import yaml
from hypothesis import given, settings

from alcoabase.services.schema_validator import SchemaValidator


# ---------------------------------------------------------------------------
# Path to schema directory
# ---------------------------------------------------------------------------

SCHEMA_DIR = Path(__file__).resolve().parents[4] / "agents" / "schema"


# ---------------------------------------------------------------------------
# Canonical field ordering for YAML export (from AgentRegistryService)
# ---------------------------------------------------------------------------

EXPORT_FIELD_ORDER = [
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


# ---------------------------------------------------------------------------
# Hypothesis Strategies for valid v2.0 agent definitions
# (Reused patterns from test_schema_validation_properties.py)
# ---------------------------------------------------------------------------


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


# Strategy for a valid dspy_module item with optional params
dspy_module_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries(
    {
        "name": bounded_text(1, 30),
        "type": bounded_text(1, 30),
    },
    optional={
        "params": st.dictionaries(
            keys=bounded_text(1, 15),
            values=st.one_of(
                st.integers(min_value=0, max_value=10000),
                st.floats(
                    min_value=0.0, max_value=2.0,
                    allow_nan=False, allow_infinity=False,
                ),
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
    "strictness": st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
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
    "weight": st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    "description": bounded_text(1, 100),
})

# Strategy for severity_thresholds
severity_thresholds_strategy: st.SearchStrategy[dict[str, float]] = st.fixed_dictionaries({
    "critical": st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    "major": st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    "minor": st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    "informational": st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
})

# Strategy for evaluation_rubric
evaluation_rubric_strategy: st.SearchStrategy[dict[str, Any]] = st.fixed_dictionaries({
    "criteria": st.lists(evaluation_criterion_strategy, min_size=1, max_size=50),
    "severity_thresholds": severity_thresholds_strategy,
    "scoring_method": st.sampled_from(["weighted_average", "pass_fail", "tiered"]),
})


@st.composite
def valid_v2_generation_agent_for_export(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid v2.0 generation agent definition suitable for export/import.

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
            st.lists(dspy_module_strategy, min_size=1, max_size=3)
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


# ---------------------------------------------------------------------------
# Helper: simulate export/import round-trip without DB
# ---------------------------------------------------------------------------


def export_to_yaml(definition: dict[str, Any]) -> str:
    """Simulate the export_agent_yaml logic: order fields, omit None values.

    This mirrors the AgentRegistryService.export_agent_yaml method logic
    without requiring a database connection.
    """
    ordered: OrderedDict[str, Any] = OrderedDict()

    for field_name in EXPORT_FIELD_ORDER:
        value = definition.get(field_name)
        if value is not None:
            ordered[field_name] = value

    return yaml.dump(
        dict(ordered),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def import_from_yaml(yaml_content: str, validator: SchemaValidator) -> tuple[dict[str, Any] | None, list[str]]:
    """Simulate the import_agent_yaml validation logic without DB.

    Parses YAML, validates against schema, and returns the parsed data
    and any validation errors.

    Returns:
        Tuple of (parsed_data_or_None, list_of_errors).
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return None, [f"YAML parse error: {e}"]

    if not isinstance(data, dict):
        return None, [f"Expected YAML mapping, got {type(data).__name__}"]

    errors = validator.validate(data)
    if errors:
        return None, errors

    return data, []


# ---------------------------------------------------------------------------
# Property 7: YAML serialization round-trip
# ---------------------------------------------------------------------------


class TestYAMLRoundTripProperty7:
    """Property tests for YAML serialization round-trip.

    For any valid v2.0 agent definition, exporting to YAML and re-importing
    SHALL produce an agent definition with identical values for all schema-defined
    fields (schema_version, name, description, archetype, personality_profile,
    contextual_tuning, evaluation_rubric, agent_type, system_prompt, dspy_modules,
    knowledge_scopes), with null-valued optional fields omitted from the YAML
    output, and field ordering preserved.

    Feature: modular-agent-registry, Property 7: YAML serialization round-trip

    **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.7, 5.5**
    """

    def setup_method(self) -> None:
        """Set up the schema validator for each test method."""
        self.validator = SchemaValidator(SCHEMA_DIR)

    @given(definition=valid_v2_generation_agent_for_export())
    @settings(max_examples=100)
    def test_roundtrip_preserves_all_fields(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Exporting and re-importing a valid v2.0 definition preserves all fields.

        **Validates: Requirements 9.1, 9.2**
        """
        # Export to YAML
        yaml_output = export_to_yaml(definition)

        # Re-import from YAML
        reimported, errors = import_from_yaml(yaml_output, self.validator)

        assert errors == [], (
            f"Re-imported YAML should have no validation errors, "
            f"got: {errors}\n"
            f"YAML output:\n{yaml_output}"
        )
        assert reimported is not None

        # Compare all schema-defined fields
        schema_fields = [
            "schema_version", "name", "description", "archetype",
            "personality_profile", "contextual_tuning", "evaluation_rubric",
            "agent_type", "system_prompt", "dspy_modules", "knowledge_scopes",
        ]

        for field_name in schema_fields:
            original_value = definition.get(field_name)
            reimported_value = reimported.get(field_name)

            # Null-valued optional fields are omitted from export
            if original_value is None:
                assert reimported_value is None, (
                    f"Field '{field_name}' was None in original but "
                    f"'{reimported_value}' after round-trip"
                )
            else:
                assert reimported_value == original_value, (
                    f"Field '{field_name}' mismatch after round-trip.\n"
                    f"Original: {original_value}\n"
                    f"Reimported: {reimported_value}"
                )

    @given(definition=valid_v2_generation_agent_for_export())
    @settings(max_examples=100)
    def test_roundtrip_omits_null_optional_fields(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Null-valued optional fields are omitted from the YAML output.

        **Validates: Requirements 9.1**
        """
        yaml_output = export_to_yaml(definition)
        reimported = yaml.safe_load(yaml_output)

        optional_fields = [
            "personality_profile", "contextual_tuning", "evaluation_rubric",
        ]

        for field_name in optional_fields:
            if definition.get(field_name) is None:
                assert field_name not in reimported, (
                    f"Null field '{field_name}' should be omitted from YAML output "
                    f"but was present with value: {reimported.get(field_name)}"
                )

    @given(definition=valid_v2_generation_agent_for_export())
    @settings(max_examples=100)
    def test_roundtrip_preserves_field_ordering(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Exported YAML preserves the canonical field ordering.

        **Validates: Requirements 9.3**
        """
        yaml_output = export_to_yaml(definition)

        # Parse YAML preserving key order (PyYAML returns ordered dicts by default
        # in Python 3.7+ since dicts are insertion-ordered)
        reimported = yaml.safe_load(yaml_output)
        reimported_keys = list(reimported.keys())

        # Filter EXPORT_FIELD_ORDER to only include fields present in the output
        expected_order = [
            f for f in EXPORT_FIELD_ORDER if f in reimported_keys
        ]

        assert reimported_keys == expected_order, (
            f"Field ordering not preserved.\n"
            f"Expected: {expected_order}\n"
            f"Got: {reimported_keys}"
        )

    @given(definition=valid_v2_generation_agent_for_export())
    @settings(max_examples=100)
    def test_exported_yaml_is_valid_against_schema(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Exported YAML always passes schema validation when re-parsed.

        **Validates: Requirements 9.2**
        """
        yaml_output = export_to_yaml(definition)
        reimported = yaml.safe_load(yaml_output)

        errors = self.validator.validate(reimported)
        assert errors == [], (
            f"Exported YAML should pass schema validation, got errors: {errors}\n"
            f"YAML output:\n{yaml_output}"
        )


# ---------------------------------------------------------------------------
# Strategies for generating invalid definitions (Property 8)
# ---------------------------------------------------------------------------


@st.composite
def definition_with_unknown_fields(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a v2.0 definition that includes unknown/extra fields.

    Starts with a valid definition and adds fields not in the schema.
    """
    definition = draw(valid_v2_generation_agent_for_export())

    # Add 1-3 unknown fields
    num_extra = draw(st.integers(min_value=1, max_value=3))
    for _ in range(num_extra):
        # Generate a field name that is NOT in the schema
        extra_key = draw(
            bounded_text(3, 20).filter(
                lambda k: k not in {
                    "schema_version", "name", "description", "archetype",
                    "personality_profile", "contextual_tuning", "evaluation_rubric",
                    "agent_type", "system_prompt", "dspy_modules", "knowledge_scopes",
                    "example_usage", "target_document_tag", "required_chapters",
                    "compliance_checklist", "severity_rules",
                }
            )
        )
        definition[extra_key] = draw(
            st.one_of(
                st.text(min_size=1, max_size=20),
                st.integers(min_value=0, max_value=100),
                st.booleans(),
            )
        )

    return definition


@st.composite
def definition_missing_required_fields(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a v2.0 definition that is missing one or more required fields."""
    definition = draw(valid_v2_generation_agent_for_export())

    # Required fields for v2.0 generation agents
    required_fields = [
        "schema_version", "name", "description",
        "system_prompt", "dspy_modules", "knowledge_scopes", "archetype",
    ]

    # Remove 1-3 required fields
    num_to_remove = draw(st.integers(min_value=1, max_value=3))
    fields_to_remove = draw(
        st.lists(
            st.sampled_from(required_fields),
            min_size=num_to_remove,
            max_size=num_to_remove,
            unique=True,
        )
    )

    for field_name in fields_to_remove:
        definition.pop(field_name, None)

    return definition


@st.composite
def definition_with_out_of_range_values(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a v2.0 definition with values outside valid ranges."""
    definition = draw(valid_v2_generation_agent_for_export())

    # Choose which field to make invalid
    invalid_choice = draw(st.sampled_from([
        "strictness_too_high",
        "strictness_too_low",
        "temperature_too_high",
        "temperature_too_low",
        "max_tokens_too_low",
        "top_p_too_high",
        "frequency_penalty_too_high",
        "presence_penalty_too_low",
        "invalid_verbosity",
        "invalid_scoring_method",
    ]))

    if invalid_choice == "strictness_too_high":
        definition["personality_profile"] = {
            "tone": "formal",
            "verbosity": "detailed",
            "strictness": draw(st.floats(
                min_value=1.01, max_value=10.0,
                allow_nan=False, allow_infinity=False,
            )),
            "domain_focus": ["test"],
            "communication_style": "structured",
        }
    elif invalid_choice == "strictness_too_low":
        definition["personality_profile"] = {
            "tone": "formal",
            "verbosity": "detailed",
            "strictness": draw(st.floats(
                min_value=-10.0, max_value=-0.01,
                allow_nan=False, allow_infinity=False,
            )),
            "domain_focus": ["test"],
            "communication_style": "structured",
        }
    elif invalid_choice == "temperature_too_high":
        definition["contextual_tuning"] = {
            "temperature": draw(st.floats(
                min_value=2.01, max_value=100.0,
                allow_nan=False, allow_infinity=False,
            )),
        }
    elif invalid_choice == "temperature_too_low":
        definition["contextual_tuning"] = {
            "temperature": draw(st.floats(
                min_value=-100.0, max_value=-0.01,
                allow_nan=False, allow_infinity=False,
            )),
        }
    elif invalid_choice == "max_tokens_too_low":
        definition["contextual_tuning"] = {
            "max_tokens": draw(st.integers(min_value=-1000, max_value=0)),
        }
    elif invalid_choice == "top_p_too_high":
        definition["contextual_tuning"] = {
            "top_p": draw(st.floats(
                min_value=1.01, max_value=10.0,
                allow_nan=False, allow_infinity=False,
            )),
        }
    elif invalid_choice == "frequency_penalty_too_high":
        definition["contextual_tuning"] = {
            "frequency_penalty": draw(st.floats(
                min_value=2.01, max_value=100.0,
                allow_nan=False, allow_infinity=False,
            )),
        }
    elif invalid_choice == "presence_penalty_too_low":
        definition["contextual_tuning"] = {
            "presence_penalty": draw(st.floats(
                min_value=-100.0, max_value=-2.01,
                allow_nan=False, allow_infinity=False,
            )),
        }
    elif invalid_choice == "invalid_verbosity":
        definition["personality_profile"] = {
            "tone": "formal",
            "verbosity": draw(bounded_text(1, 20).filter(
                lambda v: v not in {"concise", "moderate", "detailed"}
            )),
            "strictness": 0.5,
            "domain_focus": ["test"],
            "communication_style": "structured",
        }
    elif invalid_choice == "invalid_scoring_method":
        definition["evaluation_rubric"] = {
            "criteria": [{"name": "test", "weight": 0.5, "description": "test"}],
            "severity_thresholds": {
                "critical": 0.9,
                "major": 0.7,
                "minor": 0.4,
                "informational": 0.2,
            },
            "scoring_method": draw(bounded_text(1, 20).filter(
                lambda v: v not in {"weighted_average", "pass_fail", "tiered"}
            )),
        }

    return definition


# ---------------------------------------------------------------------------
# Property 8: Import validation rejects invalid definitions
# ---------------------------------------------------------------------------


class TestImportValidationProperty8:
    """Property tests for import validation rejecting invalid definitions.

    For any YAML content that contains fields not defined in the schema, OR is
    missing required fields, OR contains fields with values outside their valid
    ranges, the import operation SHALL reject the content with a validation error.

    Feature: modular-agent-registry, Property 8: Import validation rejects invalid definitions

    **Validates: Requirements 9.4, 9.7, 5.5**
    """

    def setup_method(self) -> None:
        """Set up the schema validator for each test method."""
        self.validator = SchemaValidator(SCHEMA_DIR)

    @given(definition=definition_with_unknown_fields())
    @settings(max_examples=100)
    def test_unknown_fields_rejected(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Definitions with unknown fields are rejected with validation errors.

        **Validates: Requirements 9.4**
        """
        yaml_content = yaml.dump(
            definition, default_flow_style=False, allow_unicode=True
        )

        _, errors = import_from_yaml(yaml_content, self.validator)

        assert len(errors) > 0, (
            f"Definition with unknown fields should be rejected, "
            f"but passed validation.\n"
            f"Definition keys: {list(definition.keys())}"
        )

    @given(definition=definition_missing_required_fields())
    @settings(max_examples=100)
    def test_missing_required_fields_rejected(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Definitions missing required fields are rejected with validation errors.

        **Validates: Requirements 9.7**
        """
        yaml_content = yaml.dump(
            definition, default_flow_style=False, allow_unicode=True
        )

        _, errors = import_from_yaml(yaml_content, self.validator)

        assert len(errors) > 0, (
            f"Definition missing required fields should be rejected, "
            f"but passed validation.\n"
            f"Definition keys: {list(definition.keys())}"
        )

    @given(definition=definition_with_out_of_range_values())
    @settings(max_examples=100)
    def test_out_of_range_values_rejected(
        self,
        definition: dict[str, Any],
    ) -> None:
        """Definitions with out-of-range values are rejected with validation errors.

        **Validates: Requirements 5.5, 9.7**
        """
        yaml_content = yaml.dump(
            definition, default_flow_style=False, allow_unicode=True
        )

        _, errors = import_from_yaml(yaml_content, self.validator)

        assert len(errors) > 0, (
            f"Definition with out-of-range values should be rejected, "
            f"but passed validation.\n"
            f"Definition: {definition}"
        )
