"""Unit tests for PDFGenerator content block rendering.

Validates that content blocks (headings, paragraphs, dividers) are
rendered correctly in the generated PDF without creating AcroForm fields.

**Validates: Requirements 17.7**
"""

from unittest.mock import MagicMock

import fitz  # PyMuPDF
import pytest

from alcoabase.services.pdf_generator import PDFGenerator


def _make_field_mock(
    *,
    field_uuid: str,
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


def _make_template_mock(fields: list[MagicMock]) -> MagicMock:
    """Create a mock Template with the given fields."""
    template = MagicMock()
    template.fields = fields
    template.document_uuid = "2024-00001"
    template.name = "Test Template"
    template.status = "ReadOnly"
    return template


class TestContentBlockRendering:
    """Tests for content block rendering in PDFGenerator."""

    def setup_method(self) -> None:
        """Set up the PDF generator instance."""
        self.generator = PDFGenerator()

    def test_heading_h1_rendered_as_text_not_acroform(self) -> None:
        """heading_h1 content blocks render as text, not AcroForm fields."""
        fields = [
            _make_field_mock(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Section 1",
                field_order=0,
                element_type="content_block",
                content_type="heading_h1",
                text_content="Product Information",
            ),
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Batch Number",
                field_order=1,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Collect all AcroForm field names
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        # The content block UUID should NOT appear as an AcroForm field
        assert "CB-00000001" not in field_names
        # The regular field should still be present
        assert "FLD-00000001" in field_names

    def test_heading_h1_text_appears_in_pdf(self) -> None:
        """heading_h1 text content is rendered in the PDF page text."""
        fields = [
            _make_field_mock(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h1",
                text_content="Product Information",
            ),
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Name",
                field_order=1,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_text = doc[0].get_text()
        doc.close()

        assert "Product Information" in page_text

    def test_heading_h2_rendered_as_text(self) -> None:
        """heading_h2 content blocks render as text in the PDF."""
        fields = [
            _make_field_mock(
                field_uuid="CB-00000002",
                field_type="Text",
                field_label="Sub Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h2",
                text_content="Subsection Details",
            ),
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Value",
                field_order=1,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_text = doc[0].get_text()
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        assert "Subsection Details" in page_text
        assert "CB-00000002" not in field_names

    def test_heading_h3_rendered_as_text(self) -> None:
        """heading_h3 content blocks render as text in the PDF."""
        fields = [
            _make_field_mock(
                field_uuid="CB-00000003",
                field_type="Text",
                field_label="Minor Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h3",
                text_content="Minor Section",
            ),
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Data",
                field_order=1,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_text = doc[0].get_text()
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        assert "Minor Section" in page_text
        assert "CB-00000003" not in field_names

    def test_paragraph_rendered_as_body_text(self) -> None:
        """paragraph content blocks render as body text in the PDF."""
        fields = [
            _make_field_mock(
                field_uuid="CB-00000004",
                field_type="Text",
                field_label="Instructions",
                field_order=0,
                element_type="content_block",
                content_type="paragraph",
                text_content="Please fill in all required fields below.",
            ),
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Input",
                field_order=1,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_text = doc[0].get_text()
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        assert "Please fill in all required fields below." in page_text
        assert "CB-00000004" not in field_names

    def test_divider_does_not_create_acroform_field(self) -> None:
        """divider content blocks do not create AcroForm fields."""
        fields = [
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Before Divider",
                field_order=0,
                element_type="field",
            ),
            _make_field_mock(
                field_uuid="CB-00000005",
                field_type="Text",
                field_label="Divider",
                field_order=1,
                element_type="content_block",
                content_type="divider",
                text_content=None,
            ),
            _make_field_mock(
                field_uuid="FLD-00000002",
                field_type="Text",
                field_label="After Divider",
                field_order=2,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        # Divider should not create an AcroForm field
        assert "CB-00000005" not in field_names
        # Regular fields should still be present
        assert "FLD-00000001" in field_names
        assert "FLD-00000002" in field_names

    def test_mixed_content_blocks_and_fields(self) -> None:
        """Templates with interleaved content blocks and fields render correctly."""
        fields = [
            _make_field_mock(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Header",
                field_order=0,
                element_type="content_block",
                content_type="heading_h1",
                text_content="Section A",
            ),
            _make_field_mock(
                field_uuid="CB-00000002",
                field_type="Text",
                field_label="Instructions",
                field_order=1,
                element_type="content_block",
                content_type="paragraph",
                text_content="Complete the following fields.",
            ),
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Float",
                field_label="Temperature",
                field_order=2,
                element_type="field",
            ),
            _make_field_mock(
                field_uuid="CB-00000003",
                field_type="Text",
                field_label="Divider",
                field_order=3,
                element_type="content_block",
                content_type="divider",
                text_content=None,
            ),
            _make_field_mock(
                field_uuid="CB-00000004",
                field_type="Text",
                field_label="Sub Header",
                field_order=4,
                element_type="content_block",
                content_type="heading_h2",
                text_content="Section B",
            ),
            _make_field_mock(
                field_uuid="FLD-00000002",
                field_type="Integer",
                field_label="Count",
                field_order=5,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_text = doc[0].get_text()
        field_names = []
        for page in doc:
            for widget in page.widgets():
                if widget.field_name:
                    field_names.append(widget.field_name)
        doc.close()

        # Content block text should appear in the PDF
        assert "Section A" in page_text
        assert "Complete the following fields." in page_text
        assert "Section B" in page_text

        # Only actual fields should have AcroForm entries
        acroform_fld_names = [n for n in field_names if n.startswith("FLD-")]
        assert "FLD-00000001" in acroform_fld_names
        assert "FLD-00000002" in acroform_fld_names
        assert len(acroform_fld_names) == 2

        # Content block UUIDs should NOT be AcroForm fields
        cb_names = [n for n in field_names if n.startswith("CB-")]
        assert len(cb_names) == 0

    def test_divider_renders_line_drawing(self) -> None:
        """divider content blocks produce a line drawing on the page."""
        fields = [
            _make_field_mock(
                field_uuid="CB-00000001",
                field_type="Text",
                field_label="Divider",
                field_order=0,
                element_type="content_block",
                content_type="divider",
                text_content=None,
            ),
            _make_field_mock(
                field_uuid="FLD-00000001",
                field_type="Text",
                field_label="Field",
                field_order=1,
                element_type="field",
            ),
        ]
        template = _make_template_mock(fields)
        pdf_bytes = self.generator.generate_offline_pdf(template)

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        # Check that there are line drawings on the page
        drawings = page.get_drawings()
        doc.close()

        # A divider should produce at least one line drawing
        assert len(drawings) > 0
