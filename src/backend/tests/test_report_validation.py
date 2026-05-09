"""Property-based tests for backend type validation (Property 6).

Tests that validate_single_value correctly rejects invalid values and accepts
valid ones for all field types (Text, Float, Integer, Date, Boolean) across
both PDF and manual entry contexts.

**Validates: Requirements 11.4, 11.9**

References:
    - Design: .kiro/specs/Step_2-5_report-data-entry-pdf-extraction/design.md (Property 6)
    - Requirements: .kiro/specs/Step_2-5_report-data-entry-pdf-extraction/requirements.md
"""

from datetime import date

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.field_validator import (
    FieldValidationError,
    MANUAL_ENTRY_BOOLEAN_VALUES,
    PDF_BOOLEAN_VALUES,
    validate_single_value,
)


# ---------------------------------------------------------------------------
# Oracle — independently determine if a value is valid for a given type
# ---------------------------------------------------------------------------


def _is_valid_float(value: str) -> bool:
    """Check if value is parseable as float()."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def _is_valid_integer(value: str) -> bool:
    """Check if value is parseable as int()."""
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def _is_valid_date(value: str) -> bool:
    """Check if value is parseable as date.fromisoformat()."""
    try:
        date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _is_valid_boolean_manual(value: str) -> bool:
    """Check if value is in the manual entry boolean set (case-insensitive)."""
    return value.lower() in MANUAL_ENTRY_BOOLEAN_VALUES


def _is_valid_boolean_pdf(value: str) -> bool:
    """Check if value is in the PDF boolean set (case-sensitive)."""
    return value in PDF_BOOLEAN_VALUES


# ---------------------------------------------------------------------------
# Hypothesis Strategies — generate valid values for each type
# ---------------------------------------------------------------------------

st_valid_floats = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False).map(str),
    st.integers(min_value=-10000, max_value=10000).map(str),
    st.from_regex(r"-?\d+\.\d+", fullmatch=True),
)

st_valid_integers = st.integers(min_value=-100000, max_value=100000).map(str)

st_valid_dates = st.dates(
    min_value=date(1, 1, 1),
    max_value=date(9999, 12, 31),
).map(lambda d: d.isoformat())

st_valid_booleans_manual = st.sampled_from(
    ["true", "false", "True", "False", "TRUE", "FALSE"]
)

st_valid_booleans_pdf = st.sampled_from(list(PDF_BOOLEAN_VALUES))

st_valid_text = st.text(min_size=0, max_size=50)


# ---------------------------------------------------------------------------
# Hypothesis Strategies — generate invalid values for each type
# ---------------------------------------------------------------------------

st_invalid_floats = st.text(min_size=1, max_size=20).filter(
    lambda s: not _is_valid_float(s)
)

st_invalid_integers = st.text(min_size=1, max_size=20).filter(
    lambda s: not _is_valid_integer(s)
)

st_invalid_dates = st.text(min_size=1, max_size=20).filter(
    lambda s: not _is_valid_date(s)
)

st_invalid_booleans_manual = st.text(min_size=1, max_size=20).filter(
    lambda s: not _is_valid_boolean_manual(s)
)

st_invalid_booleans_pdf = st.text(min_size=1, max_size=20).filter(
    lambda s: not _is_valid_boolean_pdf(s)
)


# ---------------------------------------------------------------------------
# Property 6: Backend type validation rejects invalid values and accepts
# valid ones
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=st_valid_text)
def test_text_always_passes(value: str) -> None:
    """For any string value, Text type validation SHALL return None (valid).

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Text",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert result is None, (
        f"Text validation rejected '{value}' but should always pass"
    )


@settings(max_examples=100)
@given(value=st_valid_floats)
def test_float_accepts_valid_values(value: str) -> None:
    """For any string parseable as float(), Float validation SHALL return None.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Float",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert result is None, f"Float validation rejected valid value '{value}'"


@settings(max_examples=100)
@given(value=st_invalid_floats)
def test_float_rejects_invalid_values(value: str) -> None:
    """For any string NOT parseable as float(), Float validation SHALL return
    FieldValidationError.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Float",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert isinstance(result, FieldValidationError), (
        f"Float validation accepted invalid value '{value}'"
    )
    assert result.expected_type == "Float"
    assert result.actual_value == value


@settings(max_examples=100)
@given(value=st_valid_integers)
def test_integer_accepts_valid_values(value: str) -> None:
    """For any string parseable as int(), Integer validation SHALL return None.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Integer",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert result is None, f"Integer validation rejected valid value '{value}'"


@settings(max_examples=100)
@given(value=st_invalid_integers)
def test_integer_rejects_invalid_values(value: str) -> None:
    """For any string NOT parseable as int(), Integer validation SHALL return
    FieldValidationError.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Integer",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert isinstance(result, FieldValidationError), (
        f"Integer validation accepted invalid value '{value}'"
    )
    assert result.expected_type == "Integer"
    assert result.actual_value == value


@settings(max_examples=100)
@given(value=st_valid_dates)
def test_date_accepts_valid_values(value: str) -> None:
    """For any string parseable as date.fromisoformat(), Date validation SHALL
    return None.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Date",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert result is None, f"Date validation rejected valid value '{value}'"


@settings(max_examples=100)
@given(value=st_invalid_dates)
def test_date_rejects_invalid_values(value: str) -> None:
    """For any string NOT parseable as date.fromisoformat(), Date validation
    SHALL return FieldValidationError.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Date",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert isinstance(result, FieldValidationError), (
        f"Date validation accepted invalid value '{value}'"
    )
    assert result.expected_type == "Date"
    assert result.actual_value == value


@settings(max_examples=100)
@given(value=st_valid_booleans_manual)
def test_boolean_manual_accepts_valid_values(value: str) -> None:
    """For any value in the manual entry boolean set (case-insensitive
    true/false), Boolean validation with context='manual' SHALL return None.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Boolean",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert result is None, (
        f"Boolean (manual) validation rejected valid value '{value}'"
    )


@settings(max_examples=100)
@given(value=st_invalid_booleans_manual)
def test_boolean_manual_rejects_invalid_values(value: str) -> None:
    """For any value NOT in the manual entry boolean set, Boolean validation
    with context='manual' SHALL return FieldValidationError.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Boolean",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="manual",
    )
    assert isinstance(result, FieldValidationError), (
        f"Boolean (manual) validation accepted invalid value '{value}'"
    )
    assert result.expected_type == "Boolean"
    assert result.actual_value == value


@settings(max_examples=100)
@given(value=st_valid_booleans_pdf)
def test_boolean_pdf_accepts_valid_values(value: str) -> None:
    """For any value in the PDF boolean set (Yes/Off/True/False/On/0/1),
    Boolean validation with context='pdf' SHALL return None.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Boolean",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="pdf",
    )
    assert result is None, (
        f"Boolean (pdf) validation rejected valid value '{value}'"
    )


@settings(max_examples=100)
@given(value=st_invalid_booleans_pdf)
def test_boolean_pdf_rejects_invalid_values(value: str) -> None:
    """For any value NOT in the PDF boolean set, Boolean validation with
    context='pdf' SHALL return FieldValidationError.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type="Boolean",
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context="pdf",
    )
    assert isinstance(result, FieldValidationError), (
        f"Boolean (pdf) validation accepted invalid value '{value}'"
    )
    assert result.expected_type == "Boolean"
    assert result.actual_value == value


# ---------------------------------------------------------------------------
# Combined property: for any type and any value, the result is correct
# ---------------------------------------------------------------------------

st_field_types = st.sampled_from(["Text", "Float", "Integer", "Date", "Boolean"])
st_contexts = st.sampled_from(["pdf", "manual"])
st_arbitrary_values = st.text(min_size=0, max_size=30)


@settings(max_examples=100)
@given(value=st_arbitrary_values, field_type=st_field_types, context=st_contexts)
def test_validation_result_matches_oracle(
    value: str, field_type: str, context: str
) -> None:
    """For any field type and any string value, validate_single_value SHALL
    return FieldValidationError if and only if the value is invalid for that
    type.

    **Validates: Requirements 11.4, 11.9**
    """
    result = validate_single_value(
        value=value,
        field_type=field_type,
        field_uuid="FLD-TEST",
        field_label="Test Field",
        context=context,
    )

    # Compute expected validity using oracle
    if field_type == "Text":
        expected_valid = True
    elif field_type == "Float":
        expected_valid = _is_valid_float(value)
    elif field_type == "Integer":
        expected_valid = _is_valid_integer(value)
    elif field_type == "Date":
        expected_valid = _is_valid_date(value)
    elif field_type == "Boolean":
        if context == "manual":
            expected_valid = _is_valid_boolean_manual(value)
        else:
            expected_valid = _is_valid_boolean_pdf(value)
    else:
        expected_valid = True

    if expected_valid:
        assert result is None, (
            f"Type={field_type}, context={context}: "
            f"value '{value}' should be valid but got error: {result}"
        )
    else:
        assert isinstance(result, FieldValidationError), (
            f"Type={field_type}, context={context}: "
            f"value '{value}' should be invalid but was accepted"
        )
