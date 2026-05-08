# Requirements Document

## Introduction

This feature enhances the existing Template Builder frontend with rich field configuration options, non-editable text/markup blocks, template versioning for ALCOA+ compliance, live PDF preview, and PDF download integration. These enhancements transform the basic drag-and-drop builder into a production-ready template authoring tool suitable for GxP-regulated pharmaceutical environments. The enhancements build upon the existing template-builder-frontend spec (5 field types, drag-and-drop canvas, basic label/type configuration, save to backend, and template list view).

## Glossary

- **Template_Builder**: The main React page component hosting the three-panel drag-and-drop form builder interface, enhanced with rich configuration and preview capabilities.
- **Configuration_Panel**: The right panel component displaying detailed, type-specific configuration options for the currently selected Canvas_Field or Content_Block.
- **Canvas_Field**: A field instance placed on the Builder_Canvas, containing a client-side temporary ID, label, type, display order, and type-specific configuration properties.
- **Content_Block**: A non-editable static content element (section header, paragraph text, or horizontal divider) placed on the Builder_Canvas that appears in the generated PDF but does not collect data.
- **Field_Configuration**: The set of type-specific properties for a Canvas_Field (e.g., max_length for Text, decimal_precision for Float, min_value/max_value for numeric types).
- **Template_Version**: A numbered revision of a template (v1, v2, v3...) where each version contains a complete, immutable snapshot of the template schema at the time of creation.
- **Active_Version**: The most recently created version of a template, used for new data collection and PDF generation.
- **Version_History**: The chronological list of all versions for a given template, accessible for audit trail purposes.
- **PDF_Preview**: A live-updating side panel or modal rendering a visual approximation of the generated PDF, reflecting the current builder state.
- **PDF_Generator**: The backend ReportLab-based service at `src/backend/src/alcoabase/services/pdf_generator.py` that produces fillable AcroForm PDFs from template schemas.
- **Template_API**: The FastAPI router at `/api/templates` providing template CRUD, versioning, and PDF download endpoints.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, and tenant headers.
- **Template_Store**: The Zustand state store managing template builder state, field list, configuration, and API interactions.
- **ALCOA_Plus**: Data integrity principles (Attributable, Legible, Contemporaneous, Original, Accurate, plus Complete, Consistent, Enduring, Available) required in GxP environments.
- **Document_UUID**: A unique identifier in YYYY-NNNNN format assigned by the backend to the template upon creation.
- **Field_UUID**: A unique identifier in FLD-XXXXXXXX format assigned by the backend to each field upon template creation.

## Requirements

### Requirement 1: Rich Field Configuration — Common Properties

**User Story:** As a template author, I want to configure common properties (required/optional, help text, default value) on any field type, so that I can define data collection expectations for each field.

#### Acceptance Criteria

1. WHEN the user selects a Canvas_Field on the Builder_Canvas, THE Configuration_Panel SHALL display a "Required" toggle defaulting to off (optional), a "Help Text" text input (max 500 characters), and a "Default Value" input appropriate to the field type.
2. WHEN the user toggles the "Required" property, THE Template_Store SHALL update the corresponding Canvas_Field required property to the new boolean value.
3. WHEN the user enters text in the "Help Text" input, THE Template_Store SHALL update the corresponding Canvas_Field help_text property on each input change event.
4. IF the "Help Text" input value exceeds 500 characters, THEN THE Configuration_Panel SHALL display a validation error indicating the maximum length has been exceeded.
5. WHEN the user enters a value in the "Default Value" input, THE Template_Store SHALL validate the value against the field type constraints (e.g., numeric for Integer/Float, valid date format for Date, boolean for Boolean) before storing the value.
6. IF the "Default Value" does not conform to the field type constraints, THEN THE Configuration_Panel SHALL display a validation error indicating the value is invalid for the selected field type.
7. THE Template_Store SHALL include the required, help_text, and default_value properties in the serialized Template_Schema sent to the backend.

### Requirement 2: Rich Field Configuration — Text Field Properties

**User Story:** As a template author, I want to configure text-specific properties (min/max length, placeholder, regex pattern), so that I can enforce text input constraints in the generated PDF and during data validation.

#### Acceptance Criteria

1. WHEN the user selects a Canvas_Field of type Text, THE Configuration_Panel SHALL display inputs for: minimum character length (integer, min 0), maximum character length (integer, min 1), placeholder text (max 200 characters), and regex validation pattern (max 500 characters).
2. WHEN the user sets a minimum length value, THE Template_Store SHALL validate that the value is a non-negative integer and store it on the Canvas_Field.
3. WHEN the user sets a maximum length value, THE Template_Store SHALL validate that the value is a positive integer and store it on the Canvas_Field.
4. IF the minimum length exceeds the maximum length, THEN THE Configuration_Panel SHALL display a validation error indicating that minimum length must not exceed maximum length.
5. WHEN the user enters a regex pattern, THE Template_Store SHALL validate that the pattern is a syntactically valid regular expression before storing it.
6. IF the regex pattern is syntactically invalid, THEN THE Configuration_Panel SHALL display a validation error indicating the pattern is not a valid regular expression.
7. WHEN the user enters placeholder text exceeding 200 characters, THE Configuration_Panel SHALL display a validation error indicating the maximum length has been exceeded.
8. THE Template_Store SHALL include min_length, max_length, placeholder, and regex_pattern properties in the serialized field configuration sent to the backend.

### Requirement 3: Rich Field Configuration — Float Field Properties

**User Story:** As a template author, I want to configure float-specific properties (decimal precision, min/max value, unit label), so that I can define numeric precision and range constraints for measurement fields.

#### Acceptance Criteria

1. WHEN the user selects a Canvas_Field of type Float, THE Configuration_Panel SHALL display inputs for: decimal precision (integer 0–10), minimum value (float), maximum value (float), and unit label (max 50 characters).
2. WHEN the user sets a decimal precision value, THE Template_Store SHALL validate that the value is an integer between 0 and 10 inclusive and store it on the Canvas_Field.
3. IF the decimal precision value is outside the range 0–10, THEN THE Configuration_Panel SHALL display a validation error indicating the valid range.
4. WHEN the user sets minimum and maximum values, THE Template_Store SHALL validate that both are valid floating-point numbers.
5. IF the minimum value exceeds the maximum value, THEN THE Configuration_Panel SHALL display a validation error indicating that minimum value must not exceed maximum value.
6. WHEN the user enters a unit label exceeding 50 characters, THE Configuration_Panel SHALL display a validation error indicating the maximum length has been exceeded.
7. THE Template_Store SHALL include decimal_precision, min_value, max_value, and unit_label properties in the serialized field configuration sent to the backend.

### Requirement 4: Rich Field Configuration — Integer Field Properties

**User Story:** As a template author, I want to configure integer-specific properties (min/max value, step size, unit label), so that I can define range and increment constraints for count or quantity fields.

#### Acceptance Criteria

1. WHEN the user selects a Canvas_Field of type Integer, THE Configuration_Panel SHALL display inputs for: minimum value (integer), maximum value (integer), step size (positive integer, default 1), and unit label (max 50 characters).
2. WHEN the user sets a step size value, THE Template_Store SHALL validate that the value is a positive integer (greater than 0) and store it on the Canvas_Field.
3. IF the step size value is zero or negative, THEN THE Configuration_Panel SHALL display a validation error indicating that step size must be a positive integer.
4. IF the minimum value exceeds the maximum value, THEN THE Configuration_Panel SHALL display a validation error indicating that minimum value must not exceed maximum value.
5. WHEN the user enters a unit label exceeding 50 characters, THE Configuration_Panel SHALL display a validation error indicating the maximum length has been exceeded.
6. THE Template_Store SHALL include min_value, max_value, step_size, and unit_label properties in the serialized field configuration sent to the backend.

### Requirement 5: Rich Field Configuration — Date Field Properties

**User Story:** As a template author, I want to configure date-specific properties (min/max date, display format), so that I can constrain date ranges and control how dates appear in the PDF.

#### Acceptance Criteria

1. WHEN the user selects a Canvas_Field of type Date, THE Configuration_Panel SHALL display inputs for: minimum date (date picker or ISO 8601 input), maximum date (date picker or ISO 8601 input), and date format display (dropdown with options: "YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MMM-YYYY").
2. WHEN the user sets a minimum date, THE Template_Store SHALL validate that the value is a valid ISO 8601 date string and store it on the Canvas_Field.
3. WHEN the user sets a maximum date, THE Template_Store SHALL validate that the value is a valid ISO 8601 date string and store it on the Canvas_Field.
4. IF the minimum date is later than the maximum date, THEN THE Configuration_Panel SHALL display a validation error indicating that minimum date must not be later than maximum date.
5. THE date format display selection SHALL default to "YYYY-MM-DD" when no format is explicitly chosen.
6. THE Template_Store SHALL include min_date, max_date, and date_format properties in the serialized field configuration sent to the backend.

### Requirement 6: Rich Field Configuration — Boolean Field Properties

**User Story:** As a template author, I want to configure custom true/false labels for boolean fields, so that the PDF displays domain-appropriate labels (e.g., "Pass/Fail", "Yes/No", "Compliant/Non-Compliant").

#### Acceptance Criteria

1. WHEN the user selects a Canvas_Field of type Boolean, THE Configuration_Panel SHALL display inputs for: custom true label (max 50 characters, default "True") and custom false label (max 50 characters, default "False").
2. WHEN the user modifies the true label or false label, THE Template_Store SHALL update the corresponding Canvas_Field property on each input change event.
3. IF the true label or false label is empty, THEN THE Configuration_Panel SHALL display a validation error indicating that a label is required.
4. IF the true label or false label exceeds 50 characters, THEN THE Configuration_Panel SHALL display a validation error indicating the maximum length has been exceeded.
5. THE Template_Store SHALL include true_label and false_label properties in the serialized field configuration sent to the backend.

### Requirement 7: Non-Editable Content Blocks — Section Headers

**User Story:** As a template author, I want to add section headers (H1, H2, H3) to the template, so that the generated PDF has clear visual structure and organization for data collectors.

#### Acceptance Criteria

1. THE Field_Palette SHALL display a "Content" section containing draggable items for: "Section Header (H1)", "Section Header (H2)", and "Section Header (H3)".
2. WHEN the user drags a section header item from the Field_Palette and drops it onto the Builder_Canvas, THE Template_Store SHALL add a new Content_Block with the selected heading level, a default text of "Section Title", and a field_order equal to the 0-based drop position index.
3. WHEN the user selects a section header Content_Block, THE Configuration_Panel SHALL display an editable text input for the header text (max 200 characters) and a dropdown to change the heading level (H1, H2, H3).
4. IF the header text is empty, THEN THE Configuration_Panel SHALL display a validation error indicating that header text is required.
5. IF the header text exceeds 200 characters, THEN THE Configuration_Panel SHALL display a validation error indicating the maximum length has been exceeded.
6. THE Builder_Canvas SHALL render section header Content_Blocks with visually distinct styling corresponding to their heading level (H1 largest, H3 smallest).
7. THE Template_Store SHALL serialize Content_Blocks as part of the template schema with a distinct element_type property value of "content_block" and a content_type of "heading_h1", "heading_h2", or "heading_h3".

### Requirement 8: Non-Editable Content Blocks — Paragraph Text

**User Story:** As a template author, I want to add paragraph text blocks (instructions, descriptions) to the template, so that data collectors see contextual guidance in the printed PDF.

#### Acceptance Criteria

1. THE Field_Palette SHALL display a draggable item for "Paragraph Text" in the "Content" section.
2. WHEN the user drags a paragraph text item from the Field_Palette and drops it onto the Builder_Canvas, THE Template_Store SHALL add a new Content_Block with content_type "paragraph", a default text of "Enter instructions or description here", and a field_order equal to the 0-based drop position index.
3. WHEN the user selects a paragraph Content_Block, THE Configuration_Panel SHALL display a multi-line text area for the paragraph content (max 2000 characters).
4. IF the paragraph text is empty, THEN THE Configuration_Panel SHALL display a validation error indicating that paragraph text is required.
5. IF the paragraph text exceeds 2000 characters, THEN THE Configuration_Panel SHALL display a validation error indicating the maximum length has been exceeded.
6. THE Builder_Canvas SHALL render paragraph Content_Blocks with a distinct visual style (e.g., lighter background, text icon) to differentiate them from input fields.
7. THE Template_Store SHALL serialize paragraph Content_Blocks with element_type "content_block" and content_type "paragraph".

### Requirement 9: Non-Editable Content Blocks — Horizontal Dividers

**User Story:** As a template author, I want to add horizontal dividers between sections, so that the generated PDF has clear visual separation between logical groups of fields.

#### Acceptance Criteria

1. THE Field_Palette SHALL display a draggable item for "Divider" in the "Content" section.
2. WHEN the user drags a divider item from the Field_Palette and drops it onto the Builder_Canvas, THE Template_Store SHALL add a new Content_Block with content_type "divider" and a field_order equal to the 0-based drop position index.
3. THE Builder_Canvas SHALL render divider Content_Blocks as a horizontal line spanning the canvas width.
4. WHEN the user selects a divider Content_Block, THE Configuration_Panel SHALL display a message indicating that dividers have no configurable properties.
5. THE Template_Store SHALL serialize divider Content_Blocks with element_type "content_block" and content_type "divider".
6. Content_Blocks and Canvas_Fields SHALL share the same field_order sequence, allowing interleaving of input fields and content blocks in any order.

### Requirement 10: Template Versioning — Create New Version

**User Story:** As a template author, I want to create a new version of an existing template, so that I can update template designs while preserving previous versions for ALCOA+ audit trail compliance.

#### Acceptance Criteria

1. WHEN the user views a ReadOnly template detail page, THE Template_Builder SHALL display a "Create New Version" button.
2. WHEN the user clicks "Create New Version", THE Template_Builder SHALL load the Active_Version schema into the builder canvas in an editable state, pre-populating all fields, content blocks, and their configurations.
3. WHEN the user saves the new version, THE Template_Store SHALL send a POST request to the versioning endpoint with the updated schema and a reference to the parent template Document_UUID.
4. WHEN the backend returns a successful response, THE Template_Store SHALL store the new version with an incremented version number (parent version + 1).
5. THE Template_API SHALL assign the new version a version number that is exactly one greater than the highest existing version number for that template.
6. WHEN a new version is created, THE Template_API SHALL set the new version status to "ReadOnly" and mark the new version as the Active_Version.
7. WHEN a new version is created, THE Template_API SHALL retain all previous versions with their original status unchanged for audit trail purposes.
8. IF the user attempts to create a new version while another version creation is in progress for the same template, THEN THE Template_API SHALL reject the request with an appropriate error to prevent race conditions.

### Requirement 11: Template Versioning — Version History Display

**User Story:** As a template author or auditor, I want to view the version history of a template, so that I can review changes over time and satisfy ALCOA+ audit requirements.

#### Acceptance Criteria

1. WHEN the user navigates to a template detail page, THE Template_Builder SHALL display a version history panel listing all versions of the template in descending order (newest first).
2. THE version history panel SHALL display for each version: version number (e.g., "v1", "v2"), creation date and time, the user who created the version, and whether the version is the Active_Version.
3. WHEN the user selects a previous version from the version history, THE Template_Builder SHALL display the schema of that version in a read-only view showing all fields, content blocks, and their configurations.
4. THE Active_Version SHALL be visually distinguished in the version history list (e.g., badge, highlight, or label indicating "Active").
5. THE Template_Builder SHALL not allow editing of any version other than through the "Create New Version" workflow.
6. WHEN the user views a previous version, THE Template_Builder SHALL display a clear indicator that the version is historical and not the active version.

### Requirement 12: Template Versioning — Version Number in PDF

**User Story:** As a data collector, I want the version number printed on the generated PDF, so that I can identify which template version was used for data collection (ALCOA+ traceability).

#### Acceptance Criteria

1. WHEN the PDF_Generator generates a PDF from a template version, THE PDF_Generator SHALL render the version number (e.g., "v1", "v2") in the PDF header area alongside the template name and Document_UUID.
2. THE version number in the PDF SHALL match exactly the version number stored in the database for that template version.
3. WHEN the user downloads a PDF for a specific version, THE PDF filename SHALL include the version number (e.g., "Template_Name_DOC-UUID_v2.pdf").
4. THE PDF SHALL include the version number as a hidden AcroForm field named "__VERSION__" to enable automated version identification during PDF upload and extraction.

### Requirement 13: Template Versioning — Active Version Enforcement

**User Story:** As a system administrator, I want only the latest version to be active for new data collection, so that data collectors always use the current approved template.

#### Acceptance Criteria

1. THE Template_API SHALL return only the Active_Version when a client requests a template for data collection purposes (PDF download for new data entry).
2. WHEN the user requests a PDF download from the template list view, THE Template_API SHALL generate the PDF from the Active_Version of the template.
3. WHEN a new version is created, THE Template_API SHALL automatically deactivate the previous Active_Version by updating its is_active flag to false.
4. THE Template_API SHALL ensure that exactly one version per template has is_active set to true at any given time.
5. IF a request attempts to download a PDF from a non-active version, THEN THE Template_API SHALL allow the download but include a visible watermark or annotation indicating "Historical Version — Not for Active Data Collection".

### Requirement 14: PDF Preview — Live Preview Panel

**User Story:** As a template author, I want a live preview of the PDF while editing the template, so that I can see how the final printed document will look before saving.

#### Acceptance Criteria

1. THE Template_Builder SHALL display a "Preview" button that opens a PDF preview panel (side panel or modal).
2. WHEN the PDF_Preview panel is open, THE PDF_Preview SHALL render a visual representation of the template as it would appear in the generated PDF, including: template name, version number (or "Draft" for unsaved templates), all Canvas_Fields with their labels and type-appropriate input representations, all Content_Blocks in their configured positions, and field configuration hints (e.g., character limits shown as field widths, unit labels adjacent to numeric fields).
3. WHEN the user modifies the template while the PDF_Preview panel is open, THE PDF_Preview SHALL update within 500 milliseconds to reflect the current builder state.
4. THE PDF_Preview SHALL render Canvas_Fields marked as required with a visual indicator (e.g., asterisk or "Required" label).
5. THE PDF_Preview SHALL render help text as a tooltip or subtitle beneath the corresponding field.
6. THE PDF_Preview SHALL render Content_Blocks (headers, paragraphs, dividers) with styling that approximates the final PDF output.
7. WHEN the user closes the PDF_Preview panel, THE Template_Builder SHALL preserve all builder state unchanged.

### Requirement 15: PDF Preview — Field Configuration Visualization

**User Story:** As a template author, I want the PDF preview to reflect field configurations (character limits, precision, units), so that I can verify the template will produce a usable data collection form.

#### Acceptance Criteria

1. WHEN a Text field has a max_length configured, THE PDF_Preview SHALL render the field input area with a size proportional to the character limit and display the limit as a hint (e.g., "max 100 chars").
2. WHEN a Float field has decimal_precision configured, THE PDF_Preview SHALL display the precision hint adjacent to the field (e.g., "2 decimal places").
3. WHEN a numeric field (Float or Integer) has a unit_label configured, THE PDF_Preview SHALL display the unit label adjacent to the field input area (e.g., "mg/L", "°C").
4. WHEN a numeric field has min_value and max_value configured, THE PDF_Preview SHALL display the range as a hint (e.g., "Range: 0–100").
5. WHEN a Date field has a date_format configured, THE PDF_Preview SHALL display the format as a placeholder or hint in the field area (e.g., "DD/MM/YYYY").
6. WHEN a Boolean field has custom true/false labels, THE PDF_Preview SHALL display the custom labels instead of generic "True/False" (e.g., "Pass / Fail").

### Requirement 16: PDF Download Integration

**User Story:** As a template author, I want to download the generated PDF from the frontend, so that I can distribute printed templates for offline data collection.

#### Acceptance Criteria

1. WHEN the user views the template list, THE Template_Builder SHALL display a "Download PDF" action for each template that has at least one ReadOnly version.
2. WHEN the user views a template detail page, THE Template_Builder SHALL display a "Download PDF" button for the Active_Version.
3. WHEN the user clicks "Download PDF", THE Template_Store SHALL send a POST request to `POST /api/templates/{document_uuid}/download-pdf` with the `X-Change-Reason` header set to "PDF downloaded for offline data collection".
4. WHILE the PDF download request is in progress, THE Template_Builder SHALL display a loading indicator on the download button and disable the button to prevent duplicate requests.
5. WHEN the Template_API returns a successful response with PDF content, THE Template_Builder SHALL trigger a browser file download with the filename provided in the Content-Disposition response header.
6. IF the Template_API returns a 404 error, THEN THE Template_Builder SHALL display an error message indicating the template was not found.
7. IF the Template_API returns a 400 error, THEN THE Template_Builder SHALL display an error message indicating the template is not in a downloadable state.
8. IF the request fails due to a network error or timeout, THEN THE Template_Builder SHALL display an error notification indicating the download failed and re-enable the download button.

### Requirement 17: PDF Generation — Rich Configuration Rendering

**User Story:** As a data collector, I want the generated PDF to reflect all field configurations (character limits as field sizes, precision in number fields, unit labels, required indicators), so that I know the expected input format when filling out the form offline.

#### Acceptance Criteria

1. WHEN the PDF_Generator generates a PDF containing a Text field with max_length configured, THE PDF_Generator SHALL size the AcroForm text field proportionally to the character limit (longer fields for higher limits).
2. WHEN the PDF_Generator generates a PDF containing a Float field with decimal_precision configured, THE PDF_Generator SHALL include the precision hint in the field tooltip (e.g., "Enter value with 2 decimal places").
3. WHEN the PDF_Generator generates a PDF containing a numeric field with unit_label configured, THE PDF_Generator SHALL render the unit label text adjacent to the AcroForm field.
4. WHEN the PDF_Generator generates a PDF containing a field marked as required, THE PDF_Generator SHALL render an asterisk (*) next to the field label.
5. WHEN the PDF_Generator generates a PDF containing a field with help_text configured, THE PDF_Generator SHALL render the help text as a smaller font line below the field label.
6. WHEN the PDF_Generator generates a PDF containing a field with a default_value configured, THE PDF_Generator SHALL pre-fill the AcroForm field with the default value.
7. WHEN the PDF_Generator generates a PDF containing Content_Blocks, THE PDF_Generator SHALL render section headers with appropriate font sizes (H1 largest, H3 smallest), paragraph text as body text, and dividers as horizontal rules.
8. WHEN the PDF_Generator generates a PDF containing a Date field with date_format configured, THE PDF_Generator SHALL include the date format as a tooltip hint on the AcroForm field (e.g., "Format: DD/MM/YYYY").

### Requirement 18: Template Schema Serialization — Enhanced Format

**User Story:** As a developer, I want the enhanced template schema to serialize all field configurations and content blocks correctly to the backend-expected JSON format, so that templates are persisted without data loss.

#### Acceptance Criteria

1. WHEN the user triggers template creation or version creation, THE Template_Store SHALL serialize the canvas elements into the format: `{ "name": string, "json_schema": { "elements": [...] }, "user_id": number }` where each element contains either field data or content block data.
2. THE Template_Store SHALL serialize Canvas_Fields with the structure: `{ "element_type": "field", "label": string, "type": FieldType, "required": boolean, "help_text": string | null, "default_value": string | null, "config": { ...type-specific properties } }`.
3. THE Template_Store SHALL serialize Content_Blocks with the structure: `{ "element_type": "content_block", "content_type": "heading_h1" | "heading_h2" | "heading_h3" | "paragraph" | "divider", "text": string | null }`.
4. THE Template_Store SHALL order elements in the serialized array by their field_order value in ascending numeric order, preserving the interleaved order of fields and content blocks.
5. FOR ALL valid canvas states containing at least one element, serializing to the payload format and then mapping back to a canvas element list SHALL preserve each element's type, configuration, and relative order (round-trip property).
6. IF the canvas state contains zero elements (no fields and no content blocks), THEN THE Template_Store SHALL prevent submission and not send a request to the backend.
7. THE Template_Store SHALL validate that at least one Canvas_Field (element_type "field") exists before allowing submission, as a template with only Content_Blocks has no data collection capability.

### Requirement 19: Version-Aware Template List View

**User Story:** As a template author, I want the template list to show version information, so that I can quickly identify which templates have multiple versions and which version is active.

#### Acceptance Criteria

1. WHEN the Templates page loads, THE Templates page SHALL display for each template: template name, Document_UUID, active version number (e.g., "v3"), total version count, creation date of the active version, and field count of the active version.
2. WHEN a template has more than one version, THE Templates page SHALL display the version count as a badge or label (e.g., "3 versions").
3. WHEN the user clicks on a template in the list, THE Templates page SHALL navigate to the template detail page showing the Active_Version with access to version history.
4. THE Templates page SHALL sort templates by the creation date of their Active_Version in descending order (most recently updated first).

### Requirement 20: Configuration Validation — Cross-Field Constraints

**User Story:** As a template author, I want the builder to validate configuration constraints in real-time, so that I cannot save a template with invalid field configurations.

#### Acceptance Criteria

1. WHILE any Canvas_Field has a configuration validation error (e.g., min exceeds max, invalid regex, empty required label), THE Template_Builder SHALL disable the Save button and display a summary of validation errors.
2. WHEN the user modifies a field configuration value, THE Configuration_Panel SHALL validate the new value within 100 milliseconds and display any error inline adjacent to the input.
3. IF a Text field has both min_length and max_length configured, THEN THE Configuration_Panel SHALL validate that min_length is less than or equal to max_length.
4. IF a numeric field (Float or Integer) has both min_value and max_value configured, THEN THE Configuration_Panel SHALL validate that min_value is less than or equal to max_value.
5. IF a Date field has both min_date and max_date configured, THEN THE Configuration_Panel SHALL validate that min_date is not later than max_date.
6. THE Template_Store SHALL not include invalid configuration values in the serialized payload; only validated, conforming values SHALL be serialized.

### Requirement 21: ALCOA+ Compliance — Audit Trail for Versioning

**User Story:** As a quality assurance auditor, I want all version creation events to be logged in the audit trail, so that template changes are attributable and traceable per ALCOA+ requirements.

#### Acceptance Criteria

1. WHEN a new template version is created, THE Template_API SHALL log an audit trail entry containing: the user ID who created the version, the timestamp of creation, the version number, the parent version number, and the change reason from the X-Change-Reason header.
2. THE Template_API SHALL reject version creation requests that do not include the X-Change-Reason header with HTTP 400 status.
3. WHEN the user initiates a "Create New Version" action, THE Template_Builder SHALL prompt the user to enter a change reason before submitting the request.
4. THE change reason input SHALL require at least 10 characters to ensure meaningful audit documentation.
5. WHEN a previous version is accessed for viewing, THE Template_API SHALL log a read-access audit entry containing the user ID, timestamp, and version number accessed.
6. THE Template_API SHALL ensure that no version record can be deleted or modified after creation (immutability enforcement for ALCOA+ "Original" principle).

