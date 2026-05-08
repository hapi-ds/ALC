"""Unit tests for field configuration Pydantic schemas.

Tests validation rules for TextFieldConfig, FloatFieldConfig,
IntegerFieldConfig, DateFieldConfig, and BooleanFieldConfig models.

References:
    - Requirements 2.1-2.8: Text field properties
    - Requirements 3.1-3.7: Float field properties
    - Requirements 4.1-4.6: Integer field properties
    - Requirements 5.1-5.6: Date field properties
    - Requirements 6.1-6.5: Boolean field properties
"""

import pytest
from pydantic import ValidationError

from alcoabase.schemas.template import (
    BooleanFieldConfig,
    DateFieldConfig,
    FloatFieldConfig,
    IntegerFieldConfig,
    TextFieldConfig,
)


# ---------------------------------------------------------------------------
# TextFieldConfig Tests
# ---------------------------------------------------------------------------


class TestTextFieldConfig:
    """Tests for TextFieldConfig validation."""

    def test_valid_full_config(self) -> None:
        config = TextFieldConfig(
            min_length=5,
            max_length=100,
            placeholder="Enter text here",
            regex_pattern=r"^[A-Z]{2}-\d{4}$",
        )
        assert config.min_length == 5
        assert config.max_length == 100
        assert config.placeholder == "Enter text here"
        assert config.regex_pattern == r"^[A-Z]{2}-\d{4}$"

    def test_all_optional_defaults_to_none(self) -> None:
        config = TextFieldConfig()
        assert config.min_length is None
        assert config.max_length is None
        assert config.placeholder is None
        assert config.regex_pattern is None

    def test_min_length_zero_is_valid(self) -> None:
        config = TextFieldConfig(min_length=0)
        assert config.min_length == 0

    def test_min_length_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TextFieldConfig(min_length=-1)

    def test_max_length_one_is_valid(self) -> None:
        config = TextFieldConfig(max_length=1)
        assert config.max_length == 1

    def test_max_length_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TextFieldConfig(max_length=0)

    def test_min_exceeds_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="min_length must not exceed max_length"):
            TextFieldConfig(min_length=20, max_length=10)

    def test_min_equals_max_accepted(self) -> None:
        config = TextFieldConfig(min_length=10, max_length=10)
        assert config.min_length == config.max_length == 10

    def test_placeholder_max_200_chars(self) -> None:
        config = TextFieldConfig(placeholder="x" * 200)
        assert len(config.placeholder) == 200

    def test_placeholder_exceeds_200_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TextFieldConfig(placeholder="x" * 201)

    def test_valid_regex_pattern(self) -> None:
        config = TextFieldConfig(regex_pattern=r"^\d{3}-\d{4}$")
        assert config.regex_pattern == r"^\d{3}-\d{4}$"

    def test_invalid_regex_pattern_rejected(self) -> None:
        with pytest.raises(ValidationError, match="not a valid regular expression"):
            TextFieldConfig(regex_pattern="[unclosed")

    def test_regex_pattern_max_500_chars(self) -> None:
        pattern = "a" * 500
        config = TextFieldConfig(regex_pattern=pattern)
        assert len(config.regex_pattern) == 500

    def test_regex_pattern_exceeds_500_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TextFieldConfig(regex_pattern="a" * 501)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TextFieldConfig(unknown_field="value")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# FloatFieldConfig Tests
# ---------------------------------------------------------------------------


class TestFloatFieldConfig:
    """Tests for FloatFieldConfig validation."""

    def test_valid_full_config(self) -> None:
        config = FloatFieldConfig(
            decimal_precision=2,
            min_value=0.0,
            max_value=14.0,
            unit_label="pH",
        )
        assert config.decimal_precision == 2
        assert config.min_value == 0.0
        assert config.max_value == 14.0
        assert config.unit_label == "pH"

    def test_all_optional_defaults(self) -> None:
        config = FloatFieldConfig()
        assert config.decimal_precision is None
        assert config.min_value is None
        assert config.max_value is None
        assert config.unit_label is None

    def test_precision_zero_valid(self) -> None:
        config = FloatFieldConfig(decimal_precision=0)
        assert config.decimal_precision == 0

    def test_precision_ten_valid(self) -> None:
        config = FloatFieldConfig(decimal_precision=10)
        assert config.decimal_precision == 10

    def test_precision_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FloatFieldConfig(decimal_precision=-1)

    def test_precision_eleven_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FloatFieldConfig(decimal_precision=11)

    def test_min_exceeds_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="min_value must not exceed max_value"):
            FloatFieldConfig(min_value=100.0, max_value=0.0)

    def test_min_equals_max_accepted(self) -> None:
        config = FloatFieldConfig(min_value=5.0, max_value=5.0)
        assert config.min_value == config.max_value == 5.0

    def test_negative_values_accepted(self) -> None:
        config = FloatFieldConfig(min_value=-100.5, max_value=-0.5)
        assert config.min_value == -100.5
        assert config.max_value == -0.5

    def test_unit_label_max_50_chars(self) -> None:
        config = FloatFieldConfig(unit_label="x" * 50)
        assert len(config.unit_label) == 50

    def test_unit_label_exceeds_50_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FloatFieldConfig(unit_label="x" * 51)


# ---------------------------------------------------------------------------
# IntegerFieldConfig Tests
# ---------------------------------------------------------------------------


class TestIntegerFieldConfig:
    """Tests for IntegerFieldConfig validation."""

    def test_valid_full_config(self) -> None:
        config = IntegerFieldConfig(
            min_value=0,
            max_value=1000,
            step_size=5,
            unit_label="mg",
        )
        assert config.min_value == 0
        assert config.max_value == 1000
        assert config.step_size == 5
        assert config.unit_label == "mg"

    def test_defaults(self) -> None:
        config = IntegerFieldConfig()
        assert config.min_value is None
        assert config.max_value is None
        assert config.step_size == 1
        assert config.unit_label is None

    def test_step_size_one_valid(self) -> None:
        config = IntegerFieldConfig(step_size=1)
        assert config.step_size == 1

    def test_step_size_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IntegerFieldConfig(step_size=0)

    def test_step_size_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IntegerFieldConfig(step_size=-1)

    def test_min_exceeds_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="min_value must not exceed max_value"):
            IntegerFieldConfig(min_value=100, max_value=0)

    def test_min_equals_max_accepted(self) -> None:
        config = IntegerFieldConfig(min_value=42, max_value=42)
        assert config.min_value == config.max_value == 42

    def test_negative_values_accepted(self) -> None:
        config = IntegerFieldConfig(min_value=-50, max_value=-10)
        assert config.min_value == -50
        assert config.max_value == -10

    def test_unit_label_max_50_chars(self) -> None:
        config = IntegerFieldConfig(unit_label="x" * 50)
        assert len(config.unit_label) == 50

    def test_unit_label_exceeds_50_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IntegerFieldConfig(unit_label="x" * 51)


# ---------------------------------------------------------------------------
# DateFieldConfig Tests
# ---------------------------------------------------------------------------


class TestDateFieldConfig:
    """Tests for DateFieldConfig validation."""

    def test_valid_full_config(self) -> None:
        config = DateFieldConfig(
            min_date="2024-01-01",
            max_date="2024-12-31",
            date_format="YYYY-MM-DD",
        )
        assert config.min_date == "2024-01-01"
        assert config.max_date == "2024-12-31"
        assert config.date_format == "YYYY-MM-DD"

    def test_all_optional_defaults(self) -> None:
        config = DateFieldConfig()
        assert config.min_date is None
        assert config.max_date is None
        assert config.date_format is None

    def test_valid_date_formats(self) -> None:
        for fmt in ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MMM-YYYY"]:
            config = DateFieldConfig(date_format=fmt)  # type: ignore[arg-type]
            assert config.date_format == fmt

    def test_invalid_date_format_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DateFieldConfig(date_format="INVALID")  # type: ignore[arg-type]

    def test_min_date_invalid_iso_rejected(self) -> None:
        with pytest.raises(ValidationError, match="valid ISO 8601 date"):
            DateFieldConfig(min_date="not-a-date")

    def test_max_date_invalid_iso_rejected(self) -> None:
        with pytest.raises(ValidationError, match="valid ISO 8601 date"):
            DateFieldConfig(max_date="31/12/2024")

    def test_min_later_than_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="min_date must not be later than max_date"):
            DateFieldConfig(min_date="2024-12-31", max_date="2024-01-01")

    def test_min_equals_max_accepted(self) -> None:
        config = DateFieldConfig(min_date="2024-06-15", max_date="2024-06-15")
        assert config.min_date == config.max_date

    def test_only_min_date_valid(self) -> None:
        config = DateFieldConfig(min_date="2024-01-01")
        assert config.min_date == "2024-01-01"
        assert config.max_date is None

    def test_only_max_date_valid(self) -> None:
        config = DateFieldConfig(max_date="2024-12-31")
        assert config.min_date is None
        assert config.max_date == "2024-12-31"

    def test_invalid_day_rejected(self) -> None:
        with pytest.raises(ValidationError, match="valid ISO 8601 date"):
            DateFieldConfig(min_date="2024-02-30")


# ---------------------------------------------------------------------------
# BooleanFieldConfig Tests
# ---------------------------------------------------------------------------


class TestBooleanFieldConfig:
    """Tests for BooleanFieldConfig validation."""

    def test_valid_custom_labels(self) -> None:
        config = BooleanFieldConfig(true_label="Pass", false_label="Fail")
        assert config.true_label == "Pass"
        assert config.false_label == "Fail"

    def test_defaults(self) -> None:
        config = BooleanFieldConfig()
        assert config.true_label == "True"
        assert config.false_label == "False"

    def test_empty_true_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BooleanFieldConfig(true_label="")

    def test_empty_false_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BooleanFieldConfig(false_label="")

    def test_true_label_max_50_chars(self) -> None:
        config = BooleanFieldConfig(true_label="x" * 50)
        assert len(config.true_label) == 50

    def test_true_label_exceeds_50_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BooleanFieldConfig(true_label="x" * 51)

    def test_false_label_max_50_chars(self) -> None:
        config = BooleanFieldConfig(false_label="x" * 50)
        assert len(config.false_label) == 50

    def test_false_label_exceeds_50_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BooleanFieldConfig(false_label="x" * 51)
