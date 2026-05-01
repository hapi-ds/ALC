"""Property-based tests for PDF round-trip integrity.

Validates that the PDF Generator and Extractor form a correct
serializer/parser pair: extract(generate(template, data)) == data.

**Validates: Requirements 5.1, 5.2, 5.3, 5.6, 6.1, 6.2, 6.3**

References:
    - Design doc Section 4: PDF Generation + Extraction
    - Requirements 5: PDF Data Extraction and Database Mapping
    - Requirements 6: PDF Round-Trip Integrity
"""

import io
from unittest.mock import MagicMock

import fitz  # PyMuPDF
from hypothesis import given, settings
from hypothesis import strategies as st

from alcoabase.services.pdf_extractor import PDFExtractor
from alcoabase.services.pdf_generator import PDFGenerator


# ---------------------------------------------------------------------------
# Strategies for generating template and field value data
# ---------------------------------------------------------------------------

FIELD_TYPES = ["Text", "Float", "Integer", "Date", "Boolean"]


@st.composite
def field_strategy(draw: st.DrawFn, order: int) -> MagicMock:
    """Generate a mock TemplateField with random type and label.

    Args:
        draw: Hypothesis draw function.
        order: The field order index.

    Returns:
        A MagicMock mimicking a TemplateField instance.
    """
    field_type = draw(st.sampled_from(FIELD_TYPES))
    hex_part = draw(
        st.text(
            alphabet="0123456789ABCDEF",
            min_size=8,
            max_size=8,
        )
    )
    field_uuid = f"FLD-{hex_part}"
    label = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                min_codepoint=65,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=30,
        )
    )

    field = MagicMock()
    field.field_uuid = field_uuid
    field.field_type = field_type
    field.field_label = label
    field.field_order = order
    return field


@st.composite
def template_strategy(draw: st.DrawFn) -> MagicMock:
    """Generate a mock Template with unique Field-UUIDs.

    Args:
        draw: Hypothesis draw function.

    Returns:
        A MagicMock mimicking a Template instance with fields loaded.
    """
    num_fields = draw(st.integers(min_value=1, max_value=15))

    fields = []
    used_uuids: set[str] = set()
    for i in range(num_fields):
        while True:
            field = draw(field_strategy(order=i))
            if field.field_uuid not in used_uuids:
                used_uuids.add(field.field_uuid)
                fields.append(field)
                break

    year = draw(st.integers(min_value=2020, max_value=2030))
    seq = draw(st.integers(min_value=1, max_value=99999))
    document_uuid = f"{year}-{seq:05d}"

    name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                min_codepoint=65,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=50,
        )
    )

    template = MagicMock()
    template.fields = fields
    template.document_uuid = document_uuid
    template.name = name
    template.status = "ReadOnly"
    return template


def value_for_field_type(field_type: str) -> st.SearchStrategy[str]:
    """Generate a valid value string for the given field type.

    Args:
        field_type: One of Text, Float, Integer, Date, Boolean.

    Returns:
        A Hypothesis strategy producing valid string values.
    """
    if field_type == "Text":
        return st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=1,
            max_size=50,
        )
    elif field_type == "Float":
        return st.floats(
            min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
        ).map(lambda x: str(round(x, 4)))
    elif field_type == "Integer":
        return st.integers(min_value=-999999, max_value=999999).map(str)
    elif field_type == "Date":
        return st.dates(
            min_value=st.dates().wrapped_strategy.min_value,
            max_value=st.dates().wrapped_strategy.max_value,
        ).map(lambda d: d.isoformat())
    elif field_type == "Boolean":
        return st.sampled_from(["Yes", "Off"])
    else:
        return st.just("default")


@st.composite
def template_with_values_strategy(
    draw: st.DrawFn,
) -> tuple[MagicMock, dict[str, str]]:
    """Generate a template and a matching set of valid field values.

    Args:
        draw: Hypothesis draw function.

    Returns:
        Tuple of (template mock, field_values dict mapping field_uuid to value).
    """
    template = draw(template_strategy())
    values: dict[str, str] = {}

    for field in template.fields:
        value = draw(value_for_field_type(field.field_type))
        values[field.field_uuid] = value

    return template, values


def _fill_pdf_fields(pdf_bytes: bytes, values: dict[str, str]) -> bytes:
    """Fill AcroForm fields in a PDF with the given values.

    Opens the PDF, sets each field value by name, and returns
    the modified PDF bytes.

    Args:
        pdf_bytes: The original PDF bytes with empty AcroForm fields.
        values: Mapping of field name to value to fill in.

    Returns:
        Modified PDF bytes with fields filled.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        for widget in page.widgets():
            if widget.field_name and widget.field_name in values:
                widget.field_value = values[widget.field_name]
                widget.update()
    result = doc.tobytes()
    doc.close()
    return result


# ---------------------------------------------------------------------------
# Property-based tests: PDF Round-Trip Integrity (Task 7.6)
# ---------------------------------------------------------------------------


class TestPDFRoundTripIntegrity:
    """Property-based tests verifying extract(generate(template, data)) == data.

    **Validates: Requirements 6.1**
    """

    def setup_method(self) -> None:
        """Set up generator and extractor instances."""
        self.generator = PDFGenerator()
        self.extractor = PDFExtractor()

    @given(data=template_with_values_strategy())
    @settings(max_examples=50, deadline=None)
    def test_round_trip_field_values(
        self, data: tuple[MagicMock, dict[str, str]]
    ) -> None:
        """Extracted field values equal the values filled into the generated PDF.

        **Validates: Requirements 6.1**

        For all valid templates and field values:
        extract(generate(template, data)) == data
        """
        template, values = data

        # Generate the PDF
        pdf_bytes = self.generator.generate_offline_pdf(template)

        # Fill in the field values
        filled_pdf = _fill_pdf_fields(pdf_bytes, values)

        # Extract the data
        extracted = self.extractor.extract_data(filled_pdf, template)

        # Verify round-trip integrity
        assert extracted.is_valid, (
            f"Extraction reported validation errors: {extracted.validation_errors}"
        )

        for field in template.fields:
            expected = values[field.field_uuid]
            actual = extracted.field_values.get(field.field_uuid)

            if field.field_type == "Float":
                # Float comparison: compare numeric values to handle
                # formatting differences (e.g., "1.0" vs "1.0000")
                assert actual is not None, (
                    f"Field {field.field_uuid} value is None, expected '{expected}'"
                )
                assert float(actual) == float(expected), (
                    f"Field {field.field_uuid}: "
                    f"expected float {float(expected)}, got {float(actual)}"
                )
            elif field.field_type == "Boolean":
                # Boolean checkbox values may normalize differently
                assert actual is not None, (
                    f"Field {field.field_uuid} value is None, expected '{expected}'"
                )
                # Both should be in the valid set
                assert actual == expected, (
                    f"Field {field.field_uuid}: "
                    f"expected '{expected}', got '{actual}'"
                )
            else:
                assert actual == expected, (
                    f"Field {field.field_uuid}: "
                    f"expected '{expected}', got '{actual}'"
                )


# ---------------------------------------------------------------------------
# Property-based tests: Document-UUID Round-Trip (Task 7.7)
# ---------------------------------------------------------------------------


class TestDocumentUUIDRoundTrip:
    """Property-based tests verifying Document-UUID round-trip integrity.

    **Validates: Requirements 6.2**
    """

    def setup_method(self) -> None:
        """Set up generator and extractor instances."""
        self.generator = PDFGenerator()
        self.extractor = PDFExtractor()

    @given(template=template_strategy())
    @settings(max_examples=50, deadline=None)
    def test_extracted_uuid_equals_embedded_uuid(
        self, template: MagicMock
    ) -> None:
        """Extracted Document-UUID equals the UUID embedded during generation.

        **Validates: Requirements 6.2**

        For all generated PDFs, the Document-UUID read by the extractor
        must exactly match the Document-UUID that was embedded by the
        generator.
        """
        # Generate the PDF
        pdf_bytes = self.generator.generate_offline_pdf(template)

        # Extract the Document-UUID
        extracted_uuid = self.extractor.read_document_uuid(pdf_bytes)

        assert extracted_uuid == template.document_uuid, (
            f"Document-UUID mismatch: embedded '{template.document_uuid}', "
            f"extracted '{extracted_uuid}'"
        )


# ---------------------------------------------------------------------------
# Property-based tests: Type Validation Rejection (Task 7.8)
# ---------------------------------------------------------------------------


def invalid_value_for_type(field_type: str) -> st.SearchStrategy[str]:
    """Generate an invalid value string for the given field type.

    Args:
        field_type: One of Float, Integer, Date, Boolean.

    Returns:
        A Hypothesis strategy producing invalid string values.
    """
    if field_type == "Float":
        # Non-numeric strings that cannot be parsed as float
        return st.sampled_from(["abc", "not_a_number", "12.34.56", "NaN_text", "$$"])
    elif field_type == "Integer":
        # Strings that are not valid integers (floats, text)
        return st.sampled_from(["3.14", "abc", "12.0", "not_int", "1e5"])
    elif field_type == "Date":
        # Invalid date formats
        return st.sampled_from(["not-a-date", "2024/01/01", "01-01-2024", "2024-13-01", "2024-01-32"])
    elif field_type == "Boolean":
        # Values not in the valid boolean set
        return st.sampled_from(["maybe", "true", "false", "2", "yes", "off"])
    else:
        # Text fields always pass — shouldn't reach here for invalid generation
        return st.just("any_text")


@st.composite
def template_with_one_invalid_field_strategy(
    draw: st.DrawFn,
) -> tuple[MagicMock, dict[str, str], str]:
    """Generate a template with values where at least one typed field is invalid.

    Ensures at least one non-Text field exists and has an invalid value.
    Only tests Float, Integer, and Date fields because Boolean checkbox
    widgets in PDF AcroForm normalize values to Yes/Off — you cannot
    store arbitrary invalid text in a checkbox widget.

    Args:
        draw: Hypothesis draw function.

    Returns:
        Tuple of (template, values dict, field_uuid of the invalid field).
    """
    # Only test types where invalid values can actually be stored in PDF
    # Boolean checkboxes normalize to Yes/Off at the PDF level
    typed_field_types = ["Float", "Integer", "Date"]
    invalid_type = draw(st.sampled_from(typed_field_types))

    # Create the invalid field
    hex_part = draw(
        st.text(alphabet="0123456789ABCDEF", min_size=8, max_size=8)
    )
    invalid_field_uuid = f"FLD-{hex_part}"

    invalid_field = MagicMock()
    invalid_field.field_uuid = invalid_field_uuid
    invalid_field.field_type = invalid_type
    invalid_field.field_label = f"Invalid {invalid_type} Field"
    invalid_field.field_order = 0

    # Optionally add some valid fields
    num_extra = draw(st.integers(min_value=0, max_value=5))
    fields = [invalid_field]
    used_uuids = {invalid_field_uuid}

    for i in range(num_extra):
        while True:
            field = draw(field_strategy(order=i + 1))
            if field.field_uuid not in used_uuids:
                used_uuids.add(field.field_uuid)
                fields.append(field)
                break

    year = draw(st.integers(min_value=2020, max_value=2030))
    seq = draw(st.integers(min_value=1, max_value=99999))
    document_uuid = f"{year}-{seq:05d}"

    template = MagicMock()
    template.fields = fields
    template.document_uuid = document_uuid
    template.name = "Test Template"
    template.status = "ReadOnly"

    # Generate values: valid for all fields except the invalid one
    values: dict[str, str] = {}
    for field in fields:
        if field.field_uuid == invalid_field_uuid:
            values[field.field_uuid] = draw(invalid_value_for_type(invalid_type))
        else:
            values[field.field_uuid] = draw(value_for_field_type(field.field_type))

    return template, values, invalid_field_uuid


class TestTypeValidationRejection:
    """Property-based tests verifying invalid values are rejected.

    **Validates: Requirements 5.3, 5.6**
    """

    def setup_method(self) -> None:
        """Set up generator and extractor instances."""
        self.generator = PDFGenerator()
        self.extractor = PDFExtractor()

    @given(data=template_with_one_invalid_field_strategy())
    @settings(max_examples=50, deadline=None)
    def test_invalid_typed_values_are_rejected(
        self, data: tuple[MagicMock, dict[str, str], str]
    ) -> None:
        """Invalid typed values cause extraction to report validation errors.

        **Validates: Requirements 5.3, 5.6**

        For all templates with at least one non-Text field containing an
        invalid value, the extractor must report is_valid=False and include
        the invalid field in validation_errors.
        """
        template, values, invalid_field_uuid = data

        # Generate the PDF
        pdf_bytes = self.generator.generate_offline_pdf(template)

        # Fill in the values (including the invalid one)
        filled_pdf = _fill_pdf_fields(pdf_bytes, values)

        # Extract the data
        extracted = self.extractor.extract_data(filled_pdf, template)

        # The extraction must report validation failure
        assert not extracted.is_valid, (
            f"Expected validation failure for field {invalid_field_uuid} "
            f"with value '{values[invalid_field_uuid]}', but extraction "
            f"reported is_valid=True"
        )

        # The invalid field must be in the validation errors
        error_uuids = {e.field_uuid for e in extracted.validation_errors}
        assert invalid_field_uuid in error_uuids, (
            f"Expected field {invalid_field_uuid} in validation errors, "
            f"but only found: {error_uuids}"
        )
