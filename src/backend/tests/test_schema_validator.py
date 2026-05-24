"""Unit tests for the SchemaValidator service.

Tests cover:
- Loading v1.0 and v2.0 schemas
- Version detection and support checking
- Validation dispatch to correct schema
- Error message formatting with field paths
- Unsupported version rejection
- v1.0 definitions validate without v2.0 fields

References:
    - Requirements: 1.1, 1.6, 1.7, 1.10
"""

from pathlib import Path

import pytest

from alcoabase.services.schema_validator import SchemaValidator, SUPPORTED_VERSIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def schema_dir() -> Path:
    """Path to the schema directory."""
    return Path(__file__).parent.parent / "../../agents/schema"


@pytest.fixture
def validator(schema_dir: Path) -> SchemaValidator:
    """Create a SchemaValidator with real schema files."""
    return SchemaValidator(schema_dir=schema_dir)


@pytest.fixture
def valid_v1_data() -> dict:
    """A minimal valid v1.0 agent definition."""
    return {
        "schema_version": "1.0",
        "name": "Test Agent",
        "description": "A test agent",
        "system_prompt": "You are a test agent.",
        "dspy_modules": [{"name": "generate", "type": "ChainOfThought"}],
        "knowledge_scopes": {"tags": ["SOP"]},
    }


@pytest.fixture
def valid_v2_data() -> dict:
    """A minimal valid v2.0 agent definition."""
    return {
        "schema_version": "2.0",
        "name": "Test Agent v2",
        "description": "A v2 test agent",
        "archetype": "Regulatory Compliance Auditor",
        "system_prompt": "You are a compliance auditor.",
        "dspy_modules": [{"name": "analyze", "type": "ChainOfThought"}],
        "knowledge_scopes": {"tags": ["Compliance"]},
    }


# ---------------------------------------------------------------------------
# Tests: Schema Loading
# ---------------------------------------------------------------------------


class TestSchemaLoading:
    """Tests for schema file loading."""

    def test_loads_both_schemas(self, validator: SchemaValidator) -> None:
        """Both v1.0 and v2.0 schemas are loaded on initialization."""
        assert "1.0" in validator._schemas
        assert "2.0" in validator._schemas

    def test_missing_schema_dir_logs_warning(self, tmp_path: Path) -> None:
        """Missing schema files result in empty schemas dict entries."""
        validator = SchemaValidator(schema_dir=tmp_path)
        # Schemas not loaded since files don't exist
        assert "1.0" not in validator._schemas
        assert "2.0" not in validator._schemas


# ---------------------------------------------------------------------------
# Tests: Version Detection
# ---------------------------------------------------------------------------


class TestVersionDetection:
    """Tests for schema version extraction and support checking."""

    def test_get_schema_version_v1(self, validator: SchemaValidator) -> None:
        """Extracts version '1.0' from data."""
        data = {"schema_version": "1.0", "name": "test"}
        assert validator.get_schema_version(data) == "1.0"

    def test_get_schema_version_v2(self, validator: SchemaValidator) -> None:
        """Extracts version '2.0' from data."""
        data = {"schema_version": "2.0", "name": "test"}
        assert validator.get_schema_version(data) == "2.0"

    def test_get_schema_version_missing(self, validator: SchemaValidator) -> None:
        """Returns empty string when schema_version is missing."""
        data = {"name": "test"}
        assert validator.get_schema_version(data) == ""

    def test_is_supported_version_v1(self, validator: SchemaValidator) -> None:
        """Version '1.0' is supported."""
        assert validator.is_supported_version("1.0") is True

    def test_is_supported_version_v2(self, validator: SchemaValidator) -> None:
        """Version '2.0' is supported."""
        assert validator.is_supported_version("2.0") is True

    def test_is_supported_version_unsupported(self, validator: SchemaValidator) -> None:
        """Unsupported versions return False."""
        assert validator.is_supported_version("3.0") is False
        assert validator.is_supported_version("") is False
        assert validator.is_supported_version("1.1") is False


# ---------------------------------------------------------------------------
# Tests: v1.0 Validation
# ---------------------------------------------------------------------------


class TestV1Validation:
    """Tests for v1.0 schema validation."""

    def test_valid_v1_passes(
        self, validator: SchemaValidator, valid_v1_data: dict
    ) -> None:
        """Valid v1.0 definition produces no errors."""
        errors = validator.validate(valid_v1_data)
        assert errors == []

    def test_v1_without_v2_fields_passes(
        self, validator: SchemaValidator, valid_v1_data: dict
    ) -> None:
        """v1.0 definitions validate without requiring v2.0 fields."""
        # Ensure no archetype, personality_profile, etc. are needed
        assert "archetype" not in valid_v1_data
        assert "personality_profile" not in valid_v1_data
        assert "contextual_tuning" not in valid_v1_data
        errors = validator.validate(valid_v1_data)
        assert errors == []

    def test_v1_missing_name_fails(
        self, validator: SchemaValidator, valid_v1_data: dict
    ) -> None:
        """v1.0 definition missing 'name' produces an error."""
        del valid_v1_data["name"]
        errors = validator.validate(valid_v1_data)
        assert len(errors) > 0
        assert any("name" in e for e in errors)

    def test_v1_missing_system_prompt_fails(
        self, validator: SchemaValidator, valid_v1_data: dict
    ) -> None:
        """v1.0 definition missing 'system_prompt' produces an error."""
        del valid_v1_data["system_prompt"]
        errors = validator.validate(valid_v1_data)
        assert len(errors) > 0
        assert any("system_prompt" in e for e in errors)

    def test_v1_empty_dspy_modules_fails(
        self, validator: SchemaValidator, valid_v1_data: dict
    ) -> None:
        """v1.0 definition with empty dspy_modules produces an error."""
        valid_v1_data["dspy_modules"] = []
        errors = validator.validate(valid_v1_data)
        assert len(errors) > 0

    def test_v1_with_additional_properties_fails(
        self, validator: SchemaValidator, valid_v1_data: dict
    ) -> None:
        """v1.0 definition with unknown fields produces an error."""
        valid_v1_data["unknown_field"] = "should fail"
        errors = validator.validate(valid_v1_data)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Tests: v2.0 Validation
# ---------------------------------------------------------------------------


class TestV2Validation:
    """Tests for v2.0 schema validation."""

    def test_valid_v2_minimal_passes(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """Minimal valid v2.0 definition (archetype required, optional fields omitted) passes."""
        errors = validator.validate(valid_v2_data)
        assert errors == []

    def test_v2_missing_archetype_fails(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition missing 'archetype' produces an error."""
        del valid_v2_data["archetype"]
        errors = validator.validate(valid_v2_data)
        assert len(errors) > 0
        assert any("archetype" in e for e in errors)

    def test_v2_with_personality_profile_passes(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition with valid personality_profile passes."""
        valid_v2_data["personality_profile"] = {
            "tone": "formal and precise",
            "verbosity": "detailed",
            "strictness": 0.9,
            "domain_focus": ["regulatory", "compliance"],
            "communication_style": "structured findings",
        }
        errors = validator.validate(valid_v2_data)
        assert errors == []

    def test_v2_strictness_out_of_range_fails(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition with strictness > 1.0 produces an error."""
        valid_v2_data["personality_profile"] = {
            "tone": "formal",
            "verbosity": "detailed",
            "strictness": 1.5,
            "domain_focus": ["regulatory"],
            "communication_style": "structured",
        }
        errors = validator.validate(valid_v2_data)
        assert len(errors) > 0
        assert any("strictness" in e or "1.5" in e for e in errors)

    def test_v2_with_contextual_tuning_passes(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition with valid contextual_tuning passes."""
        valid_v2_data["contextual_tuning"] = {
            "temperature": 0.1,
            "max_tokens": 8192,
            "top_p": 0.95,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.0,
        }
        errors = validator.validate(valid_v2_data)
        assert errors == []

    def test_v2_temperature_out_of_range_fails(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition with temperature > 2.0 produces an error."""
        valid_v2_data["contextual_tuning"] = {
            "temperature": 2.5,
        }
        errors = validator.validate(valid_v2_data)
        assert len(errors) > 0
        assert any("temperature" in e or "2.5" in e for e in errors)

    def test_v2_with_evaluation_rubric_passes(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition with valid evaluation_rubric passes."""
        valid_v2_data["evaluation_rubric"] = {
            "criteria": [
                {"name": "Coverage", "weight": 0.5, "description": "Covers all areas"},
            ],
            "severity_thresholds": {
                "critical": 0.9,
                "major": 0.7,
                "minor": 0.4,
                "informational": 0.2,
            },
            "scoring_method": "weighted_average",
        }
        errors = validator.validate(valid_v2_data)
        assert errors == []

    def test_v2_invalid_scoring_method_fails(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition with invalid scoring_method produces an error."""
        valid_v2_data["evaluation_rubric"] = {
            "criteria": [
                {"name": "Coverage", "weight": 0.5, "description": "Covers all areas"},
            ],
            "severity_thresholds": {
                "critical": 0.9,
                "major": 0.7,
                "minor": 0.4,
                "informational": 0.2,
            },
            "scoring_method": "invalid_method",
        }
        errors = validator.validate(valid_v2_data)
        assert len(errors) > 0

    def test_v2_optional_fields_omitted_passes(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """v2.0 definition without optional personality/tuning/rubric passes."""
        # valid_v2_data already omits these optional fields
        assert "personality_profile" not in valid_v2_data
        assert "contextual_tuning" not in valid_v2_data
        assert "evaluation_rubric" not in valid_v2_data
        errors = validator.validate(valid_v2_data)
        assert errors == []


# ---------------------------------------------------------------------------
# Tests: Unsupported Version Rejection
# ---------------------------------------------------------------------------


class TestUnsupportedVersionRejection:
    """Tests for unsupported schema version handling."""

    def test_unsupported_version_returns_error(
        self, validator: SchemaValidator
    ) -> None:
        """Unsupported schema version returns a clear error message."""
        data = {
            "schema_version": "3.0",
            "name": "Test",
            "description": "desc",
            "system_prompt": "prompt",
            "dspy_modules": [{"name": "m", "type": "t"}],
            "knowledge_scopes": {"tags": ["SOP"]},
        }
        errors = validator.validate(data)
        assert len(errors) == 1
        assert "Unsupported schema version '3.0'" in errors[0]
        assert "1.0" in errors[0]
        assert "2.0" in errors[0]

    def test_empty_version_returns_error(
        self, validator: SchemaValidator
    ) -> None:
        """Empty schema version returns an error."""
        data = {
            "schema_version": "",
            "name": "Test",
        }
        errors = validator.validate(data)
        assert len(errors) == 1
        assert "Unsupported schema version" in errors[0]

    def test_missing_version_returns_error(
        self, validator: SchemaValidator
    ) -> None:
        """Missing schema_version field returns an error."""
        data = {"name": "Test"}
        errors = validator.validate(data)
        assert len(errors) == 1
        assert "Unsupported schema version" in errors[0]


# ---------------------------------------------------------------------------
# Tests: Error Message Formatting
# ---------------------------------------------------------------------------


class TestErrorFormatting:
    """Tests for validation error message formatting with field paths."""

    def test_error_includes_field_path(
        self, validator: SchemaValidator, valid_v2_data: dict
    ) -> None:
        """Validation errors include dotted field paths."""
        valid_v2_data["personality_profile"] = {
            "tone": "formal",
            "verbosity": "invalid_value",
            "strictness": 0.5,
            "domain_focus": ["test"],
            "communication_style": "structured",
        }
        errors = validator.validate(valid_v2_data)
        assert len(errors) > 0
        # Should reference the nested field path
        assert any("personality_profile" in e and "verbosity" in e for e in errors)

    def test_multiple_errors_reported(
        self, validator: SchemaValidator
    ) -> None:
        """Multiple validation errors are all reported."""
        data = {
            "schema_version": "1.0",
            # Missing name, description, system_prompt, dspy_modules, knowledge_scopes
        }
        errors = validator.validate(data)
        # Should have errors for multiple missing required fields
        assert len(errors) >= 3
