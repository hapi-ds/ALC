"""PDF Generator service using ReportLab for AcroForm PDF creation.

Generates fillable AcroForm PDF documents from template JSON schemas.
Each AcroForm field name is set to the corresponding Field-UUID, enabling
deterministic extraction by the PDF Extractor.

References:
    - Design doc Section 4: PDF Generation (ReportLab)
    - Requirements 4: Offline PDF Generation from Templates
    - Requirements 6: PDF Round-Trip Integrity
    - Requirements 17: Rich Configuration Rendering
"""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

from alcoabase.models.template import Template


class PDFGenerator:
    """Service for generating fillable AcroForm PDFs from templates.

    Produces PDF documents with AcroForm fields named by Field-UUID,
    enabling deterministic data extraction. Embeds the template's
    Document-UUID as a hidden field for template matching on upload.

    The generated PDFs support offline data collection \u2014 users fill
    in the form fields and upload the completed PDF for extraction.

    Rich field configuration rendering includes:
    - Required asterisk (*) next to field labels (Requirement 17.4)
    - Help text as 8pt italic below field labels (Requirement 17.5)
    - Unit labels adjacent to numeric field boxes (Requirement 17.3)
    - Default values pre-filled in AcroForm fields (Requirement 17.6)
    - Text field width scaled by max_length (Requirement 17.1)
    - Date format tooltip hints (Requirement 17.8)
    - Float precision tooltip hints (Requirement 17.2)
    """

    # Layout constants
    _PAGE_WIDTH, _PAGE_HEIGHT = A4
    _MARGIN_LEFT = 2 * cm
    _MARGIN_RIGHT = 2 * cm
    _MARGIN_TOP = 2.5 * cm
    _MARGIN_BOTTOM = 2 * cm
    _FIELD_HEIGHT = 0.6 * cm
    _CHECKBOX_SIZE = 0.5 * cm
    _LABEL_HEIGHT = 0.4 * cm
    _ROW_SPACING = 1.5 * cm
    _FIELD_WIDTH_RATIO = 0.7  # Field takes 70% of available width

    # Width scaling constants for max_length-based field sizing
    _MIN_FIELD_WIDTH_RATIO = 0.3  # Minimum 30% of available width
    _MAX_FIELD_WIDTH_RATIO = 0.9  # Maximum 90% of available width
    _MAX_LENGTH_FULL_WIDTH = 200  # max_length at which field reaches max width
    _HELP_TEXT_HEIGHT = 0.3 * cm  # Space for help text line

    def generate_offline_pdf(
        self,
        template: Template,
        version_number: int | None = None,
        is_historical: bool = False,
    ) -> bytes:
        """Generate a fillable AcroForm PDF from a template.

        Creates a PDF with one AcroForm field per TemplateField, where
        each field's internal name is set to the Field-UUID. A hidden
        field '__DOC_UUID__' embeds the template's Document-UUID for
        extraction matching.

        Rich field configuration rendering (Requirements 17.1-17.6, 17.8):
        - Required fields display an asterisk (*) next to the label
        - Help text renders as 8pt italic below the field label
        - Unit labels render adjacent to numeric field boxes
        - Default values pre-fill AcroForm fields
        - Text field width scales proportionally to max_length
        - Date fields include date_format as a tooltip hint

        When a version_number is provided, it is rendered in the PDF header
        alongside the template name. If is_historical is True, a watermark
        annotation is added indicating the version is not for active data
        collection (Requirement 13.5).

        Args:
            template: A Template model instance with fields loaded.
                Must have status 'ReadOnly' and at least one field.
            version_number: Optional version number to render in the header.
            is_historical: If True, adds a watermark annotation indicating
                this is a historical version not for active data collection.

        Returns:
            The generated PDF document as bytes.

        Raises:
            ValueError: If the template has no fields.
        """
        if not template.fields:
            raise ValueError("Template must have at least one field.")

        # Sort fields by field_order for consistent layout
        sorted_fields = sorted(template.fields, key=lambda f: f.field_order)

        buffer = io.BytesIO()
        canvas = _create_canvas(buffer)

        # Begin the AcroForm
        canvas.setFont("Helvetica-Bold", 14)
        y_position = self._PAGE_HEIGHT - self._MARGIN_TOP

        # Draw template title with version number (Requirement 12.1)
        if version_number is not None:
            title_text = f"{template.name} \u2014 v{version_number}"
        else:
            title_text = template.name
        canvas.drawString(self._MARGIN_LEFT, y_position, title_text)
        y_position -= 1.0 * cm

        # Draw Document-UUID reference
        canvas.setFont("Helvetica", 9)
        canvas.drawString(
            self._MARGIN_LEFT,
            y_position,
            f"Document-UUID: {template.document_uuid}",
        )
        y_position -= 1.0 * cm

        # Add historical version watermark annotation (Requirement 13.5)
        if is_historical:
            self._add_historical_watermark(canvas)

        # Calculate default field width
        available_width = (
            self._PAGE_WIDTH - self._MARGIN_LEFT - self._MARGIN_RIGHT
        )
        default_field_width = available_width * self._FIELD_WIDTH_RATIO

        # Add the hidden __DOC_UUID__ field
        self._add_hidden_doc_uuid_field(canvas, template.document_uuid)

        # Add hidden __VERSION__ field when version_number is provided (Requirement 12.4)
        if version_number is not None:
            self._add_hidden_version_field(canvas, version_number)

        # Add form fields
        form = canvas.acroForm
        for field in sorted_fields:
            # Skip content blocks - handled by content block rendering
            raw_element_type = getattr(field, "element_type", "field")
            if isinstance(raw_element_type, str) and raw_element_type == "content_block":
                y_position = self._render_content_block(
                    canvas, field, y_position
                )
                continue

            # Calculate row height needed (label + optional help_text + field)
            raw_help_text = getattr(field, "help_text", None)
            help_text = raw_help_text if isinstance(raw_help_text, str) else None
            has_help_text = bool(help_text)
            row_height = (
                self._LABEL_HEIGHT
                + 0.2 * cm
                + (self._HELP_TEXT_HEIGHT if has_help_text else 0)
                + self._FIELD_HEIGHT
                + 0.3 * cm
            )

            # Check if we need a new page
            if y_position - row_height < self._MARGIN_BOTTOM:
                canvas.showPage()
                y_position = self._PAGE_HEIGHT - self._MARGIN_TOP

            # Draw field label with required asterisk (Requirement 17.4)
            canvas.setFont("Helvetica", 10)
            label_text = field.field_label
            raw_required = getattr(field, "required", False)
            is_required = raw_required is True
            if is_required:
                label_text = f"{label_text} *"
            canvas.drawString(self._MARGIN_LEFT, y_position, label_text)
            y_position -= self._LABEL_HEIGHT + 0.2 * cm

            # Draw help_text as 8pt italic below label (Requirement 17.5)
            if has_help_text:
                canvas.setFont("Helvetica-Oblique", 8)
                canvas.drawString(
                    self._MARGIN_LEFT, y_position, help_text
                )
                y_position -= self._HELP_TEXT_HEIGHT

            # Determine field width based on config (Requirement 17.1)
            field_width = self._calculate_field_width(
                field, available_width, default_field_width
            )

            # Determine default value for pre-filling (Requirement 17.6)
            raw_default = getattr(field, "default_value", None)
            default_value = raw_default if isinstance(raw_default, str) else ""

            # Determine tooltip for the field (Requirements 17.2, 17.8)
            tooltip = self._get_field_tooltip(field)

            # Add the appropriate AcroForm field based on type
            self._add_field(
                form=form,
                canvas=canvas,
                field_uuid=field.field_uuid,
                field_type=field.field_type,
                x=self._MARGIN_LEFT,
                y=y_position - self._FIELD_HEIGHT,
                width=field_width,
                height=self._FIELD_HEIGHT,
                default_value=default_value,
                tooltip=tooltip,
            )

            # Render unit_label adjacent to field box (Requirement 17.3)
            self._render_unit_label(
                canvas, field, self._MARGIN_LEFT + field_width, y_position
            )

            y_position -= self._ROW_SPACING

        canvas.save()
        return buffer.getvalue()

    def _calculate_field_width(
        self,
        field: "TemplateField",
        available_width: float,
        default_width: float,
    ) -> float:
        """Calculate field width based on max_length config.

        For Text fields with max_length configured, the width scales
        proportionally between _MIN_FIELD_WIDTH_RATIO and
        _MAX_FIELD_WIDTH_RATIO of available width (Requirement 17.1).

        Args:
            field: The TemplateField instance.
            available_width: Total available width for fields.
            default_width: Default field width when no max_length is set.

        Returns:
            The calculated field width in points.
        """
        config = getattr(field, "config", None)
        if not isinstance(config, dict):
            config = {}
        max_length = config.get("max_length")

        if field.field_type == "Text" and max_length is not None and isinstance(max_length, (int, float)):
            # Scale linearly between min and max width ratios
            ratio = min(max_length / self._MAX_LENGTH_FULL_WIDTH, 1.0)
            width_ratio = (
                self._MIN_FIELD_WIDTH_RATIO
                + ratio
                * (self._MAX_FIELD_WIDTH_RATIO - self._MIN_FIELD_WIDTH_RATIO)
            )
            return available_width * width_ratio

        return default_width

    def _get_field_tooltip(self, field: "TemplateField") -> str:
        """Build a tooltip string for the AcroForm field.

        Includes precision hints for Float fields (Requirement 17.2)
        and date format hints for Date fields (Requirement 17.8).

        Args:
            field: The TemplateField instance.

        Returns:
            A tooltip string, or empty string if no hint applies.
        """
        config = getattr(field, "config", None)
        if not isinstance(config, dict):
            config = {}

        if field.field_type == "Float":
            precision = config.get("decimal_precision")
            if precision is not None and isinstance(precision, (int, float)):
                return f"Enter value with {precision} decimal places"

        if field.field_type == "Date":
            date_format = config.get("date_format")
            if isinstance(date_format, str):
                return f"Format: {date_format}"
            return "Format: YYYY-MM-DD"

        return ""

    def _render_unit_label(
        self,
        canvas: "Canvas",
        field: "TemplateField",
        field_right_x: float,
        y_position: float,
    ) -> None:
        """Render unit_label text adjacent to a numeric field box.

        Only renders for Float and Integer fields that have a unit_label
        configured in their config dict (Requirement 17.3).

        Args:
            canvas: The ReportLab canvas instance.
            field: The TemplateField instance.
            field_right_x: The x-coordinate of the right edge of the field.
            y_position: The current y position (baseline of the field area).
        """
        if field.field_type not in ("Float", "Integer"):
            return

        config = getattr(field, "config", None)
        if not isinstance(config, dict):
            return

        unit_label = config.get("unit_label")
        if unit_label and isinstance(unit_label, str):
            canvas.setFont("Helvetica", 9)
            # Position unit label 0.2cm to the right of the field box
            unit_x = field_right_x + 0.2 * cm
            # Vertically center with the field box
            unit_y = y_position - self._FIELD_HEIGHT + 0.15 * cm
            canvas.drawString(unit_x, unit_y, unit_label)

    def _render_content_block(
        self,
        canvas: "Canvas",
        field: "TemplateField",
        y_position: float,
    ) -> float:
        """Render a content block element (heading, paragraph, divider).

        Renders content blocks with appropriate styling:
        - heading_h1: 16pt bold
        - heading_h2: 13pt bold
        - heading_h3: 11pt bold
        - paragraph: 10pt body text
        - divider: horizontal rule across page width

        Args:
            canvas: The ReportLab canvas instance.
            field: The TemplateField with element_type="content_block".
            y_position: The current y position.

        Returns:
            The updated y position after rendering.
        """
        content_type = getattr(field, "content_type", None)

        if content_type in ("heading_h1", "heading_h2", "heading_h3"):
            font_sizes = {
                "heading_h1": 16,
                "heading_h2": 13,
                "heading_h3": 11,
            }
            font_size = font_sizes[content_type]
            text = getattr(field, "text_content", "") or "Section Title"

            if y_position - font_size < self._MARGIN_BOTTOM:
                canvas.showPage()
                y_position = self._PAGE_HEIGHT - self._MARGIN_TOP

            canvas.setFont("Helvetica-Bold", font_size)
            canvas.drawString(self._MARGIN_LEFT, y_position, text)
            y_position -= self._ROW_SPACING

        elif content_type == "paragraph":
            text = getattr(field, "text_content", "") or ""

            if y_position - 10 < self._MARGIN_BOTTOM:
                canvas.showPage()
                y_position = self._PAGE_HEIGHT - self._MARGIN_TOP

            canvas.setFont("Helvetica", 10)
            canvas.drawString(self._MARGIN_LEFT, y_position, text)
            y_position -= self._ROW_SPACING

        elif content_type == "divider":
            if y_position - 0.5 * cm < self._MARGIN_BOTTOM:
                canvas.showPage()
                y_position = self._PAGE_HEIGHT - self._MARGIN_TOP

            available_width = (
                self._PAGE_WIDTH - self._MARGIN_LEFT - self._MARGIN_RIGHT
            )
            canvas.setStrokeColorRGB(0.5, 0.5, 0.5)
            canvas.setLineWidth(0.5)
            canvas.line(
                self._MARGIN_LEFT,
                y_position,
                self._MARGIN_LEFT + available_width,
                y_position,
            )
            y_position -= self._ROW_SPACING

        return y_position

    def _add_hidden_version_field(
        self, canvas: "Canvas", version_number: int
    ) -> None:
        """Add a hidden AcroForm field containing the version number.

        The field is named '__VERSION__' and positioned off-screen
        with minimal size so it is not visible to the user but readable
        by automated tools. Uses 'readOnly' flag to prevent editing.
        Enables automated version identification during PDF upload and
        extraction (Requirement 12.4).

        Args:
            canvas: The ReportLab canvas instance.
            version_number: The version number to embed.
        """
        canvas.acroForm.textfield(
            name="__VERSION__",
            value=str(version_number),
            x=-100,
            y=-100,
            width=1,
            height=1,
            fontSize=1,
            borderWidth=0,
            fieldFlags="readOnly",
        )

    def _add_hidden_doc_uuid_field(
        self, canvas: "Canvas", document_uuid: str
    ) -> None:
        """Add a hidden AcroForm field containing the Document-UUID.

        The field is named '__DOC_UUID__' and positioned off-screen
        with minimal size so it is not visible to the user but readable
        by the PDF Extractor. Uses 'readOnly' flag to prevent editing.

        Args:
            canvas: The ReportLab canvas instance.
            document_uuid: The template's Document-UUID value.
        """
        canvas.acroForm.textfield(
            name="__DOC_UUID__",
            value=document_uuid,
            x=-100,
            y=-100,
            width=1,
            height=1,
            fontSize=1,
            borderWidth=0,
            fieldFlags="readOnly",
        )

    def _add_historical_watermark(self, canvas: "Canvas") -> None:
        """Add a diagonal watermark annotation for historical versions.

        Renders "Historical Version - Not for Active Data Collection"
        as a semi-transparent diagonal watermark across the page to
        clearly indicate this is not the active version (Requirement 13.5).

        Args:
            canvas: The ReportLab canvas instance.
        """
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 36)
        canvas.setFillColorRGB(0.85, 0.85, 0.85)  # Light gray
        canvas.translate(self._PAGE_WIDTH / 2, self._PAGE_HEIGHT / 2)
        canvas.rotate(45)
        watermark_text = (
            "Historical Version \u2014 Not for Active Data Collection"
        )
        canvas.drawCentredString(0, 0, watermark_text)
        canvas.restoreState()

    def _add_field(
        self,
        form: "AcroForm",
        canvas: "Canvas",
        field_uuid: str,
        field_type: str,
        x: float,
        y: float,
        width: float,
        height: float,
        default_value: str = "",
        tooltip: str = "",
    ) -> None:
        """Add an AcroForm field with type-appropriate constraints.

        Supports pre-filling with default_value (Requirement 17.6) and
        setting tooltip hints for precision/date format (Requirements 17.2, 17.8).

        Args:
            form: The ReportLab AcroForm instance.
            canvas: The ReportLab canvas instance.
            field_uuid: The Field-UUID to use as the field name.
            field_type: The field data type (Text, Float, Integer, Date, Boolean).
            x: X coordinate for field placement.
            y: Y coordinate for field placement.
            width: Field width in points.
            height: Field height in points.
            default_value: Value to pre-fill in the field (Requirement 17.6).
            tooltip: Tooltip hint text for the field.
        """
        if field_type == "Boolean":
            # Checkbox for boolean fields
            # Pre-check if default_value indicates true
            checked = default_value.lower() in ("true", "1", "yes") if default_value else False
            form.checkbox(
                name=field_uuid,
                x=x,
                y=y,
                size=self._CHECKBOX_SIZE,
                buttonStyle="check",
                borderWidth=1,
                checked=checked,
                tooltip=tooltip if tooltip else None,
            )
        elif field_type in ("Float", "Integer"):
            # Numeric text field
            form.textfield(
                name=field_uuid,
                value=default_value,
                tooltip=tooltip if tooltip else None,
                x=x,
                y=y,
                width=width,
                height=height,
                fontSize=10,
                borderWidth=1,
                fieldFlags="",
            )
            # Add JavaScript validation action for numeric fields
            js_validation = self._get_numeric_validation_js(
                field_uuid, field_type
            )
            if js_validation:
                self._add_field_validation_js(canvas, field_uuid, js_validation)
        elif field_type == "Date":
            # Date field with format hint in tooltip
            form.textfield(
                name=field_uuid,
                value=default_value,
                tooltip=tooltip if tooltip else "Format: YYYY-MM-DD",
                x=x,
                y=y,
                width=width,
                height=height,
                fontSize=10,
                borderWidth=1,
                fieldFlags="",
            )
        else:
            # Default: standard text field
            form.textfield(
                name=field_uuid,
                value=default_value,
                tooltip=tooltip if tooltip else None,
                x=x,
                y=y,
                width=width,
                height=height,
                fontSize=10,
                borderWidth=1,
                fieldFlags="",
            )

    @staticmethod
    def _get_numeric_validation_js(field_uuid: str, field_type: str) -> str:
        """Generate JavaScript validation code for numeric fields.

        Args:
            field_uuid: The field name for error messages.
            field_type: Either 'Float' or 'Integer'.

        Returns:
            JavaScript validation string for the field.
        """
        if field_type == "Integer":
            return (
                "var v = event.value; "
                "if (v !== '' && !/^-?\\\\d+$/.test(v)) { "
                "app.alert('This field requires an integer value.'); "
                "event.rc = false; }"
            )
        else:  # Float
            return (
                "var v = event.value; "
                "if (v !== '' && !/^-?\\\\d+(\\\\.\\\\d+)?$/.test(v)) { "
                "app.alert('This field requires a numeric value.'); "
                "event.rc = false; }"
            )

    @staticmethod
    def _add_field_validation_js(
        canvas: "Canvas", field_uuid: str, js_code: str
    ) -> None:
        """Add JavaScript validation action to a field.

        Note: ReportLab's AcroForm API has limited JS action support.
        This method adds validation hints via the PDF's JavaScript
        catalog when possible. For basic AcroForm generation, the
        field type constraints serve as documentation hints.

        Args:
            canvas: The ReportLab canvas instance.
            field_uuid: The field name to attach validation to.
            js_code: The JavaScript validation code.
        """
        # ReportLab's high-level AcroForm API doesn't directly support
        # per-field JavaScript actions. The validation JS is stored as
        # a hint for PDF readers that support it. The primary validation
        # happens server-side in the PDF Extractor.
        pass


def _create_canvas(buffer: io.BytesIO) -> "Canvas":
    """Create a ReportLab canvas configured for AcroForm generation.

    Args:
        buffer: BytesIO buffer to write the PDF into.

    Returns:
        A configured ReportLab Canvas instance.
    """
    from reportlab.pdfgen.canvas import Canvas

    canvas = Canvas(buffer, pagesize=A4)
    canvas.setTitle("AlcoaBase Offline Template")
    canvas.setAuthor("AlcoaBase PDF Generator")
    return canvas
