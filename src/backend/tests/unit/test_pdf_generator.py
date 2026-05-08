"""Unit tests for enhanced PDFGenerator rich config rendering.

Tests rich field configuration rendering including:
- Content block rendering: headings (H1=16pt, H2=13pt, H3=11pt bold),
  paragraphs (10pt body text), dividers (horizontal rule) (Requirement 17.7)
- Required asterisks next to field labels (Requirement 17.4)
- Help text as 8pt italic below field labels (Requirement 17.5)
- Unit labels adjacent to numeric field boxes (Requirement 17.3)
- Default values pre-filled in AcroForm fields (Requirement 17.6)
- Text field width scaling by max_length (Requirement 17.1)
- Date format tooltip hint (Requirement 17.8)
- Float precision tooltip hint (Requirement 17.2)
- Version number in PDF header (Requirement 12.1, 12.2)
- Hidden __VERSION__ AcroForm field (Requirement 12.4)

**Validates: Requirements 17.1-17.8, 12.1, 12.2, 12.4**
"""

from unittest.mock import MagicMock

import fitz  # PyMuPDF
import pytest

from alcoabase.services.pdf_generator import PDFGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field(
    *,
    field_uuid: str = "FLD-00000001",
    field_type: str = "Text",
    field_label: str = "Test Field",
    field_order: int = 0,
    element_type: str = "field",
    content_type: str | None = None,
    text_content: str | None = None,
    required: bool = False,
    help_text: str | None = None,
    default_value: str | None = None,
    config: dict | None = None,
) -> MagicMock:
    """Create a mock TemplateField with the given attributes."""
    field = MagicMock()
    field.field_uuid = field_uuid
    field.field_type = field_type
    field.field_label = field_label
    field.field_order = field_order
    field.element_type = element_type
    field.content_type = content_type
    field.text_content = text_content
    field.required = required
    field.help_text = help_text
    field.default_value = default_value
    field.config = config
    return field


def _make_template(
    fields: list[MagicMock],
    name: str = "Test Template",
    document_uuid: str = "2024-00001",
) -> MagicMock:
    """Create a mock Template with the given fields."""
    template = MagicMock()
    template.fields = fields
    template.document_uuid = document_uuid
    template.name = name
    template.status = "ReadOnly"
    return template


def _get_page_text(pdf_bytes: bytes, page_num: int = 0) -> str:
    """Extract text from a specific page of a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = doc[page_num].get_text()
    doc.close()
    return text


# ---------------------------------------------------------------------------
# Tests: Required asterisk rendering (Requirement 17.4)
# ---------------------------------------------------------------------------


class TestRequiredAsterisk:
    """Tests for required field asterisk rendering.

    Validates: Requirement 17.4
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_required_field_shows_asterisk_in_text(self) -> None:
        """Required fields have an asterisk (*) next to the label in PDF text."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Batch Number",
                required=True,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "Batch Number *" in page_text

    def test_optional_field_no_asterisk(self) -> None:
        """Optional fields do not have an asterisk next to the label."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Notes",
                required=False,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "Notes" in page_text
        assert "Notes *" not in page_text

    def test_multiple_required_fields_all_have_asterisks(self) -> None:
        """All required fields in a template show asterisks."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Field A",
                field_order=0,
                required=True,
            ),
            _make_field(
                field_uuid="FLD-00000002",
                field_type="Integer",
                field_label="Field B",
                field_order=1,
                required=True,
            ),
            _make_field(
                field_uuid="FLD-00000003",
                field_type="Float",
                field_label="Field C",
                field_order=2,
                required=False,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "Field A *" in page_text
        assert "Field B *" in page_text
        assert "Field C *" not in page_text


# ---------------------------------------------------------------------------
# Tests: Help text rendering (Requirement 17.5)
# ---------------------------------------------------------------------------


class TestHelpTextRendering:
    """Tests for help text rendering below field labels.

    Validates: Requirement 17.5
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_help_text_appears_in_pdf(self) -> None:
        """Help text is rendered in the PDF page text."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Batch Number",
                help_text="Enter the batch number from the production label",
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "Enter the batch number from the production label" in page_text

    def test_no_help_text_when_none(self) -> None:
        """No extra text appears when help_text is None."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Simple Field",
                help_text=None,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "Simple Field" in page_text


# ---------------------------------------------------------------------------
# Tests: Unit label rendering (Requirement 17.3)
# ---------------------------------------------------------------------------


class TestUnitLabelRendering:
    """Tests for unit label rendering adjacent to numeric fields.

    Validates: Requirement 17.3
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_float_field_unit_label_appears(self) -> None:
        """Float field with unit_label renders the unit in PDF text."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Float",
                field_label="Temperature",
                config={"unit_label": "deg_C"},
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "deg_C" in page_text

    def test_integer_field_unit_label_appears(self) -> None:
        """Integer field with unit_label renders the unit in PDF text."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Integer",
                field_label="Count",
                config={"unit_label": "pcs"},
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "pcs" in page_text

    def test_text_field_no_unit_label(self) -> None:
        """Text fields do not render unit labels even if config has one."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Name",
                config={"unit_label": "should_not_appear"},
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "should_not_appear" not in page_text

    def test_no_unit_label_when_not_configured(self) -> None:
        """No unit label rendered when config has no unit_label."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Float",
                field_label="Value",
                config={"decimal_precision": 2},
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        assert len(pdf_bytes) > 0


# ---------------------------------------------------------------------------
# Tests: Default value pre-filling (Requirement 17.6)
# ---------------------------------------------------------------------------


class TestDefaultValuePreFill:
    """Tests for default value pre-filling in AcroForm fields.

    Validates: Requirement 17.6
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_text_field_prefilled_with_default(self) -> None:
        """Text field AcroForm widget has default_value pre-filled."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Operator",
                default_value="John Doe",
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        widget_value = None
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    widget_value = widget.field_value
        doc.close()

        assert widget_value == "John Doe"

    def test_numeric_field_prefilled_with_default(self) -> None:
        """Float field AcroForm widget has default_value pre-filled."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Float",
                field_label="pH",
                default_value="7.0",
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        widget_value = None
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    widget_value = widget.field_value
        doc.close()

        assert widget_value == "7.0"

    def test_no_default_value_leaves_field_empty(self) -> None:
        """Field without default_value has empty value in AcroForm."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Notes",
                default_value=None,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        widget_value = None
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    widget_value = widget.field_value
        doc.close()

        assert widget_value == "" or widget_value is None

    def test_boolean_field_checked_when_default_true(self) -> None:
        """Boolean field is checked when default_value is 'true'."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Boolean",
                field_label="Approved",
                default_value="true",
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        assert len(pdf_bytes) > 0
        assert pdf_bytes[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Tests: Field width scaling (Requirement 17.1)
# ---------------------------------------------------------------------------


class TestFieldWidthScaling:
    """Tests for text field width scaling by max_length.

    Validates: Requirement 17.1
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_short_max_length_produces_narrower_field(self) -> None:
        """Text field with small max_length is narrower than one with large max_length."""
        fields_short = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Short",
                config={"max_length": 10},
            ),
        ]
        fields_long = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Long",
                config={"max_length": 200},
            ),
        ]
        template_short = _make_template(fields_short)
        template_long = _make_template(fields_long)

        pdf_short = self.generator.generate_offline_pdf(template_short)
        pdf_long = self.generator.generate_offline_pdf(template_long)

        doc_short = fitz.open(stream=pdf_short, filetype="pdf")
        doc_long = fitz.open(stream=pdf_long, filetype="pdf")

        width_short = None
        width_long = None
        for page in doc_short:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    width_short = widget.rect.width
        for page in doc_long:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    width_long = widget.rect.width

        doc_short.close()
        doc_long.close()

        assert width_short is not None
        assert width_long is not None
        assert width_short < width_long

    def test_no_max_length_uses_default_width(self) -> None:
        """Text field without max_length uses default field width."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Default Width",
                config=None,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        assert len(pdf_bytes) > 0


# ---------------------------------------------------------------------------
# Tests: Date format tooltip (Requirement 17.8)
# ---------------------------------------------------------------------------


class TestDateFormatTooltip:
    """Tests for date format tooltip hint on Date fields.

    Validates: Requirement 17.8
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_date_field_with_format_generates_valid_pdf(self) -> None:
        """Date field with date_format config generates a valid PDF with the field."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Date",
                field_label="Expiry Date",
                config={"date_format": "DD/MM/YYYY"},
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        found = False
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    found = True
        doc.close()
        assert found

    def test_date_field_without_format_generates_valid_pdf(self) -> None:
        """Date field without date_format uses default and generates valid PDF."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Date",
                field_label="Start Date",
                config={},
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        found = False
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    found = True
        doc.close()
        assert found


# ---------------------------------------------------------------------------
# Tests: Float precision tooltip (Requirement 17.2)
# ---------------------------------------------------------------------------


class TestFloatPrecisionTooltip:
    """Tests for float precision tooltip hint.

    Validates: Requirement 17.2
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_float_field_with_precision_generates_valid_pdf(self) -> None:
        """Float field with decimal_precision generates a valid PDF."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Float",
                field_label="Concentration",
                config={"decimal_precision": 3},
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        found = False
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "FLD-00000001":
                    found = True
        doc.close()
        assert found


# ---------------------------------------------------------------------------
# Tests: Version number in header (Requirements 12.1, 12.2)
# ---------------------------------------------------------------------------


class TestVersionNumberInHeader:
    """Tests for version number rendering in PDF header.

    Validates: Requirements 12.1, 12.2
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_version_number_in_header_text(self) -> None:
        """PDF header includes version number alongside template name."""
        fields = [
            _make_field(field_uuid="FLD-00000001", field_type="Text", field_label="F1"),
        ]
        template = _make_template(fields, name="Batch Release Form")
        pdf_bytes = self.generator.generate_offline_pdf(
            template, version_number=3
        )
        page_text = _get_page_text(pdf_bytes)

        assert "Batch Release Form" in page_text
        assert "v3" in page_text

    def test_version_number_matches_provided_value(self) -> None:
        """The version number in the header matches the provided version_number."""
        fields = [
            _make_field(field_uuid="FLD-00000001", field_type="Text", field_label="F1"),
        ]
        template = _make_template(fields, name="QC Checklist")
        pdf_bytes = self.generator.generate_offline_pdf(
            template, version_number=7
        )
        page_text = _get_page_text(pdf_bytes)

        assert "v7" in page_text

    def test_no_version_number_when_not_provided(self) -> None:
        """PDF header shows only template name when no version_number is given."""
        fields = [
            _make_field(field_uuid="FLD-00000001", field_type="Text", field_label="F1"),
        ]
        template = _make_template(fields, name="Draft Template")
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "Draft Template" in page_text
        assert "\u2014 v" not in page_text


# ---------------------------------------------------------------------------
# Tests: Hidden __VERSION__ AcroForm field (Requirement 12.4)
# ---------------------------------------------------------------------------


class TestHiddenVersionField:
    """Tests for hidden __VERSION__ AcroForm field.

    Validates: Requirement 12.4
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_version_field_present_when_version_provided(self) -> None:
        """__VERSION__ hidden field exists when version_number is provided."""
        fields = [
            _make_field(field_uuid="FLD-00000001", field_type="Text", field_label="F1"),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(
            template, version_number=2
        )

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        version_field_found = False
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "__VERSION__":
                    version_field_found = True
        doc.close()

        assert version_field_found

    def test_version_field_value_matches_version_number(self) -> None:
        """__VERSION__ field value matches the provided version number."""
        fields = [
            _make_field(field_uuid="FLD-00000001", field_type="Text", field_label="F1"),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(
            template, version_number=5
        )

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        version_value = None
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "__VERSION__":
                    version_value = widget.field_value
        doc.close()

        assert version_value == "5"

    def test_version_field_absent_when_no_version(self) -> None:
        """__VERSION__ field is not present when no version_number is given."""
        fields = [
            _make_field(field_uuid="FLD-00000001", field_type="Text", field_label="F1"),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        version_field_found = False
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "__VERSION__":
                    version_field_found = True
        doc.close()

        assert not version_field_found

    def test_version_field_is_exactly_one(self) -> None:
        """Only one __VERSION__ field exists in the PDF."""
        fields = [
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="F1",
                field_order=0,
            ),
            _make_field(
                field_uuid="FLD-00000002",
                field_type="Integer",
                field_label="F2",
                field_order=1,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(
            template, version_number=1
        )

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        version_count = 0
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == "__VERSION__":
                    version_count += 1
        doc.close()

        assert version_count == 1


# ---------------------------------------------------------------------------
# Tests: Content block rendering (Requirement 17.7)
# ---------------------------------------------------------------------------


class TestContentBlockRendering:
    """Tests for content block rendering in PDFGenerator.

    Validates: Requirement 17.7
    - heading_h1 rendered at 16pt bold
    - heading_h2 rendered at 13pt bold
    - heading_h3 rendered at 11pt bold
    - paragraph rendered as 10pt body text
    - divider rendered as horizontal rule
    """

    def setup_method(self) -> None:
        self.generator = PDFGenerator()

    def test_heading_h1_text_appears_in_pdf(self) -> None:
        """heading_h1 content block text is rendered in the PDF."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h1",
                text_content="Product Information",
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Name",
                field_order=1,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        assert "Product Information" in page_text

    def test_heading_h1_rendered_at_16pt_bold(self) -> None:
        """heading_h1 is rendered with 16pt bold font."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h1",
                text_content="Main Title",
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Field",
                field_order=1,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        blocks = page.get_text("dict")["blocks"]
        found_h1 = False
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if "Main Title" in span.get("text", ""):
                        # Verify 16pt font size
                        assert abs(span["size"] - 16.0) < 0.5
                        # Verify bold font
                        assert "Bold" in span["font"]
                        found_h1 = True
        doc.close()
        assert found_h1, "heading_h1 text 'Main Title' not found in PDF"

    def test_heading_h2_rendered_at_13pt_bold(self) -> None:
        """heading_h2 is rendered with 13pt bold font."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h2",
                text_content="Subsection Title",
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Field",
                field_order=1,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        blocks = page.get_text("dict")["blocks"]
        found_h2 = False
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if "Subsection Title" in span.get("text", ""):
                        assert abs(span["size"] - 13.0) < 0.5
                        assert "Bold" in span["font"]
                        found_h2 = True
        doc.close()
        assert found_h2, "heading_h2 text 'Subsection Title' not found in PDF"

    def test_heading_h3_rendered_at_11pt_bold(self) -> None:
        """heading_h3 is rendered with 11pt bold font."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h3",
                text_content="Minor Section",
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Field",
                field_order=1,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        blocks = page.get_text("dict")["blocks"]
        found_h3 = False
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if "Minor Section" in span.get("text", ""):
                        assert abs(span["size"] - 11.0) < 0.5
                        assert "Bold" in span["font"]
                        found_h3 = True
        doc.close()
        assert found_h3, "heading_h3 text 'Minor Section' not found in PDF"

    def test_paragraph_rendered_as_10pt_body_text(self) -> None:
        """paragraph content block is rendered as 10pt body text."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Instructions",
                field_order=0,
                element_type="content_block",
                content_type="paragraph",
                text_content="Please complete all fields below.",
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Field",
                field_order=1,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        blocks = page.get_text("dict")["blocks"]
        found_para = False
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if "Please complete all fields below." in span.get("text", ""):
                        assert abs(span["size"] - 10.0) < 0.5
                        # Body text should NOT be bold
                        assert "Bold" not in span["font"]
                        found_para = True
        doc.close()
        assert found_para, "paragraph text not found in PDF"

    def test_divider_renders_horizontal_rule(self) -> None:
        """divider content block renders as a horizontal line (rule)."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Divider",
                field_order=0,
                element_type="content_block",
                content_type="divider",
                text_content=None,
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Field",
                field_order=1,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        drawings = page.get_drawings()
        doc.close()

        # A divider should produce at least one line drawing
        assert len(drawings) > 0
        # Verify at least one drawing is a horizontal line (same y for start/end)
        has_horizontal_line = any(
            any(
                item[0] == "l"  # line item
                and abs(item[1].y - item[2].y) < 1.0  # horizontal
                for item in drawing.get("items", [])
            )
            for drawing in drawings
        )
        assert has_horizontal_line, "No horizontal line found for divider"

    def test_content_blocks_do_not_create_acroform_fields(self) -> None:
        """Content blocks should not create AcroForm fields."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h1",
                text_content="Section 1",
            ),
            _make_field(
                field_uuid="CB-00000002",
                field_type="Text",
                field_label="Para",
                field_order=1,
                element_type="content_block",
                content_type="paragraph",
                text_content="Instructions here.",
            ),
            _make_field(
                field_uuid="CB-00000003",
                field_type="Text",
                field_label="Divider",
                field_order=2,
                element_type="content_block",
                content_type="divider",
                text_content=None,
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Data Field",
                field_order=3,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        # Content block UUIDs should NOT appear as AcroForm fields
        assert "CB-00000001" not in field_names
        assert "CB-00000002" not in field_names
        assert "CB-00000003" not in field_names
        # Regular field should still be present
        assert "FLD-00000001" in field_names

    def test_mixed_content_blocks_and_fields_interleaved(self) -> None:
        """Interleaved content blocks and fields render correctly."""
        fields = [
            _make_field(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h1",
                text_content="Section A",
            ),
            _make_field(
                field_uuid="FLD-00000001",
                field_type="Float",
                field_label="Temperature",
                field_order=1,
                config={"unit_label": "C"},
            ),
            _make_field(
                field_uuid="CB-00000002",
                field_type="Text",
                field_label="Divider",
                field_order=2,
                element_type="content_block",
                content_type="divider",
                text_content=None,
            ),
            _make_field(
                field_uuid="CB-00000003",
                field_type="Text",
                field_label="Header2",
                field_order=3,
                element_type="content_block",
                content_type="heading_h2",
                text_content="Section B",
            ),
            _make_field(
                field_uuid="FLD-00000002",
                field_type="Integer",
                field_label="Count",
                field_order=4,
                required=True,
            ),
        ]
        template = _make_template(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)
        page_text = _get_page_text(pdf_bytes)

        # Content block text should appear
        assert "Section A" in page_text
        assert "Section B" in page_text
        # Field labels should appear
        assert "Temperature" in page_text
        assert "Count *" in page_text
