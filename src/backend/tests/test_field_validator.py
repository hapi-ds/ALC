"""Unit tests for the shared field_validator module.

Tests validate_single_value for both PDF and manual entry contexts,
ensuring type validation works correctly for all field types.
"""

import pytest

from alcoabase.services.field_validator import (
    FieldValidationError,
    validate_single_value,
)


class TestTextValidation:
    """Text fields always pass validation."""

    def test_any_string_valid(self) -> None:
        result = validate_single_value(
            value="anything goes here!",
            field_type="Text",
            field_uuid="FLD-001",
            field_label="Notes",
        )
        assert result is None

    def test_empty_string_valid(self) -> None:
        result = validate_single_value(
            value="",
            field_type="Text",
            field_uuid="FLD-001",
            field_label="Notes",
        )
        assert result is None


class TestFloatValidation:
    """Float fields must be parseable as float()."""

    def test_integer_string_valid(self) -> None:
        result = validate_single_value(
            value="42",
            field_type="Float",
            field_uuid="FLD-002",
            field_label="Weight",
        )
        assert result is None

    def test_decimal_string_valid(self) -> None:
        result = validate_single_value(
            value="3.14",
            field_type="Float",
            field_uuid="FLD-002",
            field_label="Weight",
        )
        assert result is None

    def test_negative_float_valid(self) -> None:
        result = validate_single_value(
            value="-0.5",
            field_type="Float",
            field_uuid="FLD-002",
            field_label="Weight",
        )
        assert result is None

    def test_scientific_notation_valid(self) -> None:
        result = validate_single_value(
            value="1.5e10",
            field_type="Float",
            field_uuid="FLD-002",
            field_label="Weight",
        )
        assert result is None

    def test_non_numeric_invalid(self) -> None:
        result = validate_single_value(
            value="abc",
            field_type="Float",
            field_uuid="FLD-002",
            field_label="Weight",
        )
        assert result is not None
        assert result.expected_type == "Float"
        assert result.actual_value == "abc"

    def test_empty_string_invalid(self) -> None:
        result = validate_single_value(
            value="",
            field_type="Float",
            field_uuid="FLD-002",
            field_label="Weight",
        )
        assert result is not None


class TestIntegerValidation:
    """Integer fields must be parseable as int()."""

    def test_positive_integer_valid(self) -> None:
        result = validate_single_value(
            value="42",
            field_type="Integer",
            field_uuid="FLD-003",
            field_label="Count",
        )
        assert result is None

    def test_negative_integer_valid(self) -> None:
        result = validate_single_value(
            value="-7",
            field_type="Integer",
            field_uuid="FLD-003",
            field_label="Count",
        )
        assert result is None

    def test_zero_valid(self) -> None:
        result = validate_single_value(
            value="0",
            field_type="Integer",
            field_uuid="FLD-003",
            field_label="Count",
        )
        assert result is None

    def test_decimal_invalid(self) -> None:
        result = validate_single_value(
            value="3.14",
            field_type="Integer",
            field_uuid="FLD-003",
            field_label="Count",
        )
        assert result is not None
        assert result.expected_type == "Integer"

    def test_non_numeric_invalid(self) -> None:
        result = validate_single_value(
            value="hello",
            field_type="Integer",
            field_uuid="FLD-003",
            field_label="Count",
        )
        assert result is not None


class TestDateValidation:
    """Date fields must be parseable as date.fromisoformat()."""

    def test_valid_iso_date(self) -> None:
        result = validate_single_value(
            value="2024-03-15",
            field_type="Date",
            field_uuid="FLD-004",
            field_label="Sample Date",
        )
        assert result is None

    def test_invalid_format(self) -> None:
        result = validate_single_value(
            value="15/03/2024",
            field_type="Date",
            field_uuid="FLD-004",
            field_label="Sample Date",
        )
        assert result is not None
        assert result.expected_type == "Date"

    def test_invalid_date(self) -> None:
        result = validate_single_value(
            value="2024-13-45",
            field_type="Date",
            field_uuid="FLD-004",
            field_label="Sample Date",
        )
        assert result is not None

    def test_non_date_string(self) -> None:
        result = validate_single_value(
            value="not a date",
            field_type="Date",
            field_uuid="FLD-004",
            field_label="Sample Date",
        )
        assert result is not None


class TestBooleanValidationPdfContext:
    """Boolean validation in PDF context accepts checkbox values."""

    @pytest.mark.parametrize("value", ["Yes", "Off", "True", "False", "On", "0", "1"])
    def test_valid_pdf_boolean_values(self, value: str) -> None:
        result = validate_single_value(
            value=value,
            field_type="Boolean",
            field_uuid="FLD-005",
            field_label="Approved",
            context="pdf",
        )
        assert result is None

    def test_invalid_pdf_boolean(self) -> None:
        result = validate_single_value(
            value="maybe",
            field_type="Boolean",
            field_uuid="FLD-005",
            field_label="Approved",
            context="pdf",
        )
        assert result is not None
        assert result.expected_type == "Boolean"

    def test_lowercase_true_invalid_in_pdf_context(self) -> None:
        """In PDF context, 'true' (lowercase) is NOT valid — only 'True'."""
        result = validate_single_value(
            value="true",
            field_type="Boolean",
            field_uuid="FLD-005",
            field_label="Approved",
            context="pdf",
        )
        # "true" is not in {"Yes", "Off", "True", "False", "On", "0", "1"}
        assert result is not None


class TestBooleanValidationManualContext:
    """Boolean validation in manual entry context accepts true/false case-insensitive."""

    @pytest.mark.parametrize("value", ["true", "false", "True", "False", "TRUE", "FALSE"])
    def test_valid_manual_boolean_values(self, value: str) -> None:
        result = validate_single_value(
            value=value,
            field_type="Boolean",
            field_uuid="FLD-005",
            field_label="Approved",
            context="manual",
        )
        assert result is None

    def test_invalid_manual_boolean(self) -> None:
        result = validate_single_value(
            value="yes",
            field_type="Boolean",
            field_uuid="FLD-005",
            field_label="Approved",
            context="manual",
        )
        assert result is not None
        assert result.expected_type == "Boolean"

    def test_numeric_invalid_in_manual_context(self) -> None:
        """In manual context, '1' and '0' are NOT valid."""
        result = validate_single_value(
            value="1",
            field_type="Boolean",
            field_uuid="FLD-005",
            field_label="Approved",
            context="manual",
        )
        assert result is not None


class TestUnknownFieldType:
    """Unknown field types are treated as valid (defensive)."""

    def test_unknown_type_passes(self) -> None:
        result = validate_single_value(
            value="anything",
            field_type="UnknownType",
            field_uuid="FLD-006",
            field_label="Mystery",
        )
        assert result is None


class TestErrorStructure:
    """Verify the error dataclass has correct fields."""

    def test_error_contains_all_fields(self) -> None:
        result = validate_single_value(
            value="bad",
            field_type="Integer",
            field_uuid="FLD-007",
            field_label="Batch Number",
        )
        assert result is not None
        assert isinstance(result, FieldValidationError)
        assert result.field_uuid == "FLD-007"
        assert result.field_label == "Batch Number"
        assert result.expected_type == "Integer"
        assert result.actual_value == "bad"
        assert "bad" in result.message


class TestDefaultContext:
    """Default context is 'pdf'."""

    def test_default_context_is_pdf(self) -> None:
        # "True" is valid in PDF context (default) but case-sensitive
        result = validate_single_value(
            value="True",
            field_type="Boolean",
            field_uuid="FLD-005",
            field_label="Approved",
        )
        assert result is None
