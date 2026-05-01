"""Property-based tests for PDF Generator service.

Validates that generated PDFs contain exactly one AcroForm field per
Field-UUID in the template, and that the hidden __DOC_UUID__ field
contains the correct Document-UUID.

**Validates: Requirements 4.1, 4.2, 4.3, 6.3**

References:
    - Design doc Section 4: PDF Generation (ReportLab)
    - Requirements 4: Offline PDF Generation from Templates
    - Requirements 6: PDF Round-Trip Integrity
"""

from unittest.mock import MagicMock

import fitz  # PyMuPDF
from hypothesis import given, settings
from hypothesis import strategies as st

from alcoabase.services.pdf_generator import PDFGenerator


# ---------------------------------------------------------------------------
# Strategies for generating template data
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
    # Generate a unique field UUID (FLD- prefix + 8 hex chars)
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
                whitelist_categories=("L", "N", "Z"),
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=1,
            max_size=50,
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
    """Generate a mock Template with random fields.

    Generates between 1 and 30 fields with unique Field-UUIDs.

    Args:
        draw: Hypothesis draw function.

    Returns:
        A MagicMock mimicking a Template instance with fields loaded.
    """
    num_fields = draw(st.integers(min_value=1, max_value=30))

    # Generate unique field UUIDs
    fields = []
    used_uuids: set[str] = set()
    for i in range(num_fields):
        while True:
            field = draw(field_strategy(order=i))
            if field.field_uuid not in used_uuids:
                used_uuids.add(field.field_uuid)
                fields.append(field)
                break

    # Generate document UUID in YYYY-NNNNN format
    year = draw(st.integers(min_value=2020, max_value=2030))
    seq = draw(st.integers(min_value=1, max_value=99999))
    document_uuid = f"{year}-{seq:05d}"

    name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=1,
            max_size=100,
        )
    )

    template = MagicMock()
    template.fields = fields
    template.document_uuid = document_uuid
    template.name = name
    template.status = "ReadOnly"
    return template


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


class TestPDFGeneratorProperties:
    """Property-based tests for PDFGenerator AcroForm field generation."""

    def setup_method(self) -> None:
        """Set up the PDF generator instance for each test."""
        self.generator = PDFGenerator()

    @given(template=template_strategy())
    @settings(max_examples=50, deadline=None)
    def test_every_field_uuid_has_exactly_one_acroform_field(
        self, template: MagicMock
    ) -> None:
        """Every Field-UUID in the template has exactly one AcroForm field.

        **Validates: Requirements 6.3**

        For all generated PDFs, every Field-UUID from the template must
        appear as exactly one AcroForm field name in the PDF.
        """
        pdf_bytes = self.generator.generate_offline_pdf(template)

        # Extract AcroForm field names using PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        # Every Field-UUID from the template must appear exactly once
        expected_uuids = {f.field_uuid for f in template.fields}
        field_name_counts: dict[str, int] = {}
        for name in field_names:
            if name.startswith("FLD-"):
                field_name_counts[name] = field_name_counts.get(name, 0) + 1

        # Check that every expected UUID is present exactly once
        for uuid in expected_uuids:
            assert uuid in field_name_counts, (
                f"Field-UUID '{uuid}' not found in PDF AcroForm fields. "
                f"Found fields: {list(field_name_counts.keys())}"
            )
            assert field_name_counts[uuid] == 1, (
                f"Field-UUID '{uuid}' appears {field_name_counts[uuid]} times "
                f"in PDF, expected exactly 1."
            )

        # No extra FLD- fields beyond what's in the template
        extra_fields = set(field_name_counts.keys()) - expected_uuids
        assert not extra_fields, (
            f"PDF contains unexpected FLD- fields: {extra_fields}"
        )

    @given(template=template_strategy())
    @settings(max_examples=50, deadline=None)
    def test_doc_uuid_hidden_field_contains_correct_value(
        self, template: MagicMock
    ) -> None:
        """The __DOC_UUID__ hidden field contains the correct Document-UUID.

        **Validates: Requirements 4.3**

        For all generated PDFs, the hidden __DOC_UUID__ AcroForm field
        must contain the template's Document-UUID value.
        """
        pdf_bytes = self.generator.generate_offline_pdf(template)

        # Extract the __DOC_UUID__ field value using PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        doc_uuid_value = None
        doc_uuid_count = 0

        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "__DOC_UUID__":
                    doc_uuid_value = widget.field_value
                    doc_uuid_count += 1
        doc.close()

        # The __DOC_UUID__ field must exist exactly once
        assert doc_uuid_count == 1, (
            f"Expected exactly 1 __DOC_UUID__ field, found {doc_uuid_count}"
        )

        # The value must match the template's Document-UUID
        assert doc_uuid_value == template.document_uuid, (
            f"__DOC_UUID__ field value '{doc_uuid_value}' does not match "
            f"template Document-UUID '{template.document_uuid}'"
        )
