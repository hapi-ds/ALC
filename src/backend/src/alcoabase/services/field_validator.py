"""Shared field value type validation utility.

Extracted from PDFExtractor._validate_single_value to enable reuse
across both PDF extraction and manual report entry paths.

References:
    - Requirements 11.4: Type validation for manual entry
    - Requirements 11.9: Validation error reporting
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class FieldValidationError:
    """A single field validation error.

    Attributes:
        field_uuid: The Field-UUID that failed validation.
        field_label: Human-readable label for the field.
        expected_type: The expected data type.
        actual_value: The value that failed validation.
        message: Descriptive error message.
    """

    field_uuid: str
    field_label: str
    expected_type: str
    actual_value: str | None
    message: str


# Boolean values accepted from PDF AcroForm checkbox widgets
PDF_BOOLEAN_VALUES = {"Yes", "Off", "True", "False", "On", "0", "1"}

# Boolean values accepted from manual entry (case-insensitive)
MANUAL_ENTRY_BOOLEAN_VALUES = {"true", "false"}


def validate_single_value(
    value: str,
    field_type: str,
    field_uuid: str,
    field_label: str,
    context: str = "pdf",
) -> FieldValidationError | None:
    """Validate a single field value against its expected type.

    Supports both PDF extraction context (broader boolean acceptance)
    and manual entry context (only "true"/"false" case-insensitive).

    Args:
        value: The string value to validate.
        field_type: Expected type (Text, Float, Integer, Date, Boolean).
        field_uuid: The Field-UUID for error reporting.
        field_label: Human-readable label for error reporting.
        context: Validation context - "pdf" for PDF extraction,
            "manual" for manual data entry. Affects Boolean validation.

    Returns:
        A FieldValidationError if validation fails, None if valid.
    """
    if field_type == "Text":
        return None

    elif field_type == "Float":
        try:
            float(value)
            return None
        except (ValueError, TypeError):
            return FieldValidationError(
                field_uuid=field_uuid,
                field_label=field_label,
                expected_type="Float",
                actual_value=value,
                message=f"Value '{value}' is not a valid float number.",
            )

    elif field_type == "Integer":
        try:
            int(value)
            return None
        except (ValueError, TypeError):
            return FieldValidationError(
                field_uuid=field_uuid,
                field_label=field_label,
                expected_type="Integer",
                actual_value=value,
                message=f"Value '{value}' is not a valid integer.",
            )

    elif field_type == "Date":
        try:
            date.fromisoformat(value)
            return None
        except (ValueError, TypeError):
            return FieldValidationError(
                field_uuid=field_uuid,
                field_label=field_label,
                expected_type="Date",
                actual_value=value,
                message=f"Value '{value}' is not a valid date (expected YYYY-MM-DD).",
            )

    elif field_type == "Boolean":
        if context == "manual":
            if value.lower() in MANUAL_ENTRY_BOOLEAN_VALUES:
                return None
            return FieldValidationError(
                field_uuid=field_uuid,
                field_label=field_label,
                expected_type="Boolean",
                actual_value=value,
                message=f"Value '{value}' is not a valid boolean (expected true/false).",
            )
        else:
            # PDF context: accept broader set of checkbox values
            if value in PDF_BOOLEAN_VALUES:
                return None
            return FieldValidationError(
                field_uuid=field_uuid,
                field_label=field_label,
                expected_type="Boolean",
                actual_value=value,
                message=(
                    f"Value '{value}' is not a valid boolean "
                    f"(expected Yes/Off/True/False/On/0/1)."
                ),
            )

    # Unknown field type — treat as valid (defensive)
    return None
