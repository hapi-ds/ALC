# Requirements Document

## Introduction

This feature implements the frontend Report Data Entry and PDF Extraction workflow for AlcoaBase. It enables users to create reports by filling out dynamic forms rendered from template JSON schemas, submit field values to the backend, upload completed offline PDFs to trigger the existing Dual-UUID extraction pipeline, and view a comparison between manually entered data and PDF-extracted data. The feature also includes a report list view for browsing all reports within a tenant. This builds upon the existing backend infrastructure (Report model, ReportFieldValue model, PDFExtractor service, upload-pdf endpoint) and the frontend template system (template schemas with typed fields, template stores, apiClient).

## Glossary

- **Report_Data_Entry_Page**: The React page component that renders a dynamic form from a template's JSON schema, allowing users to enter field values for report creation.
- **Report_Store**: The Zustand state store managing report list state, report creation, PDF upload, and comparison data.
- **Report_List_Page**: The React page component displaying all reports for the current tenant with filtering and status indicators.
- **Report_Detail_Page**: The React page component displaying a single report's extracted or entered field values and metadata.
- **Comparison_View**: A UI component that displays extracted PDF field values side-by-side with manually entered field values, highlighting discrepancies for data integrity verification.
- **Template_Schema**: The JSON schema stored on a template containing an `elements` array with field definitions (type, label, config, required, help_text, default_value) and content blocks.
- **Field_UUID**: A unique identifier in FLD-XXXXXXXX format assigned by the backend to each field upon template creation, used as the AcroForm field name in PDFs.
- **Document_UUID**: A unique identifier in YYYY-NNNNN format assigned by the backend to the template, embedded as `__DOC_UUID__` in generated PDFs.
- **Report_API**: The FastAPI router at `/api/reports` providing PDF upload and report CRUD endpoints.
- **Template_API**: The FastAPI router at `/api/templates` providing template retrieval and PDF download endpoints.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and file uploads.
- **PDF_Extractor**: The backend service at `src/backend/src/alcoabase/services/pdf_extractor.py` that reads AcroForm fields from uploaded PDFs using PyMuPDF.
- **Report_Field_Value**: A database record linking a report to a specific Field_UUID and its extracted or entered string value.
- **Discrepancy**: A difference between a manually entered field value and the corresponding PDF-extracted value for the same Field_UUID within a report.

## Requirements

### Requirement 1: Report List Page

**User Story:** As a lab analyst, I want to view all reports for my company, so that I can track submitted data and review extraction results.

#### Acceptance Criteria

1. WHEN the user navigates to the reports route, THE Report_List_Page SHALL fetch reports for the current tenant from `GET /api/reports` and display them in a table sorted by upload timestamp descending (newest first), showing up to 50 reports per page with pagination controls to access additional pages.
2. THE Report_List_Page SHALL display for each report: report ID, source template name, Document_UUID, status (Extracted, Validated, Draft), uploaded-by user, and upload timestamp formatted as a locale-aware relative time (e.g., "2 hours ago") with the full ISO 8601 datetime visible on hover.
3. WHEN the user clicks on a report row, THE Report_List_Page SHALL navigate to the Report_Detail_Page for that report.
4. WHILE the report list is loading, THE Report_List_Page SHALL display a loading indicator.
5. IF the report list request fails, THEN THE Report_List_Page SHALL display an error message with the failure reason and a retry button that re-fetches the report list when clicked.
6. IF the report list response contains zero reports, THEN THE Report_List_Page SHALL display an empty state message indicating no reports exist, along with the "New Report" button.
7. THE Report_List_Page SHALL display a "New Report" button that navigates to a template selection step for report creation.

### Requirement 2: Template Selection for Report Creation

**User Story:** As a lab analyst, I want to select a template before creating a report, so that the correct form schema is loaded for data entry.

#### Acceptance Criteria

1. WHEN the user clicks "New Report" on the Report_List_Page, THE Report_Data_Entry_Page SHALL fetch the template list from `GET /api/templates` and display a template selector showing only templates with status "ReadOnly".
2. THE template selector SHALL display for each template: template name, Document_UUID, and the count of field elements (elements with element_type "field") from the template's fields array.
3. WHILE the template list is loading, THE Report_Data_Entry_Page SHALL display a loading indicator in the template selector area.
4. WHEN the user selects a template, THE Report_Data_Entry_Page SHALL fetch the full template details from `GET /api/templates/{document_uuid}` and render the dynamic form from the template's JSON schema.
5. WHILE the template detail is loading after selection, THE Report_Data_Entry_Page SHALL display a loading indicator in the form area and disable the template selector.
6. IF the template list request fails, THEN THE Report_Data_Entry_Page SHALL display an error message with the failure reason and a retry button to re-fetch the template list.
7. IF the template detail request fails, THEN THE Report_Data_Entry_Page SHALL display an error message with the failure reason, re-enable the template selector, and allow the user to select a different template or retry.
8. IF no ReadOnly templates exist, THEN THE Report_Data_Entry_Page SHALL display a message indicating that no templates are available for report creation.

### Requirement 3: Dynamic Form Rendering from Template Schema

**User Story:** As a lab analyst, I want the report form to render input fields matching the template schema, so that I can enter data in the correct format for each field type.

#### Acceptance Criteria

1. WHEN a template is selected, THE Report_Data_Entry_Page SHALL render one input control for each field element (element_type "field") in the template's JSON schema `elements` array, ordered by their position in the array, displaying the field's label above the input control.
2. THE Report_Data_Entry_Page SHALL render Text fields as text input controls with the maximum character length set to the field's configured max_length when present.
3. THE Report_Data_Entry_Page SHALL render Float fields as numeric input controls accepting decimal values, constrained to the number of decimal places specified by the field's decimal_precision config when present.
4. THE Report_Data_Entry_Page SHALL render Integer fields as numeric input controls accepting only whole numbers, using the field's configured step_size (default 1) as the input step increment.
5. WHEN a Date field has a date_format configured, THE Report_Data_Entry_Page SHALL render the field as a date picker control using that format. IF no date_format is configured, THEN THE Report_Data_Entry_Page SHALL default to YYYY-MM-DD format.
6. THE Report_Data_Entry_Page SHALL render Boolean fields as checkbox or toggle controls using the configured true_label and false_label as the option labels, defaulting to "True" and "False" when not configured.
7. THE Report_Data_Entry_Page SHALL render content block elements as non-interactive visual elements: heading_h1 as a top-level heading, heading_h2 as a second-level heading, heading_h3 as a third-level heading, paragraph as body text displaying the element's text_content, and divider as a horizontal separator line.
8. WHEN a field has the required property set to true, THE Report_Data_Entry_Page SHALL display a required indicator (asterisk) next to the field label.
9. WHEN a field has help_text configured, THE Report_Data_Entry_Page SHALL display the help text below the field input as assistive text associated with the input control.
10. WHEN a field has a default_value configured, THE Report_Data_Entry_Page SHALL pre-populate the input control with the default value on initial render.
11. WHEN a numeric field (Float or Integer) has a unit_label configured, THE Report_Data_Entry_Page SHALL display the unit_label adjacent to the input control.

### Requirement 4: Client-Side Field Validation

**User Story:** As a lab analyst, I want immediate feedback when I enter invalid data, so that I can correct errors before submission.

#### Acceptance Criteria

1. WHEN the user moves focus away from a Float field that contains a value that is not a valid decimal number, THE Report_Data_Entry_Page SHALL display a validation error message adjacent to that field within 200 milliseconds.
2. WHEN the user moves focus away from an Integer field that contains a value that is not a valid whole number, THE Report_Data_Entry_Page SHALL display a validation error message adjacent to that field within 200 milliseconds.
3. WHEN the user moves focus away from a Date field that contains a value that is not a valid date in the configured format, THE Report_Data_Entry_Page SHALL display a validation error message adjacent to that field within 200 milliseconds.
4. WHEN a field has min_value and max_value configured and the user moves focus away from the field with a value outside that range, THE Report_Data_Entry_Page SHALL display a validation error message indicating the allowed minimum and maximum values.
5. WHEN a field has min_length or max_length configured and the user moves focus away from the field with text length violating the constraint, THE Report_Data_Entry_Page SHALL display a validation error message indicating the required minimum or maximum length.
6. WHEN the user attempts to submit the form with empty required fields, THE Report_Data_Entry_Page SHALL display validation errors on all empty required fields and prevent submission.
7. IF any field has a validation error, THEN THE Report_Data_Entry_Page SHALL disable the submit button.
8. WHEN the user corrects a field value so that it passes all validation rules for that field, THE Report_Data_Entry_Page SHALL remove the validation error message from that field and re-enable the submit button if no other validation errors remain.
9. THE Report_Data_Entry_Page SHALL NOT display validation errors on fields the user has not yet interacted with, except when the user attempts to submit the form.

### Requirement 5: Report Submission

**User Story:** As a lab analyst, I want to submit my entered field values to create a report, so that the data is persisted in the system for review and audit.

#### Acceptance Criteria

1. WHEN the user clicks the submit button with all fields valid, THE Report_Store SHALL send a POST request to `POST /api/reports` with a JSON body containing the template's Document_UUID and a field_values array mapping each Field_UUID to its entered string value.
2. WHEN the Report_Store sends the submission request, THE Report_Store SHALL include the `X-Change-Reason` header with the value "Report created via manual data entry" on the request.
3. WHILE the submission request is in progress, THE Report_Data_Entry_Page SHALL display a loading indicator on the submit button, disable the submit button, and disable all form inputs to prevent duplicate submissions.
4. WHEN the backend returns a successful response (201), THE Report_Data_Entry_Page SHALL navigate to the Report_Detail_Page for the newly created report and display a success notification that auto-dismisses after 5 seconds.
5. IF the backend returns a 400 error with validation_errors, THEN THE Report_Data_Entry_Page SHALL display the server-side validation errors mapped to their corresponding fields by Field_UUID, re-enable the form inputs, and preserve all entered values.
6. IF the backend returns a 403 error, THEN THE Report_Data_Entry_Page SHALL display an error message indicating insufficient permissions and re-enable the form inputs.
7. IF the submission fails due to a network error or request timeout, THEN THE Report_Data_Entry_Page SHALL display an error notification, re-enable the form inputs, and preserve all entered values.
8. IF the backend returns an unexpected error (5xx or any status not otherwise handled), THEN THE Report_Data_Entry_Page SHALL display a generic error notification indicating the submission failed, re-enable the form inputs, and preserve all entered values.

### Requirement 6: PDF Upload for Extraction

**User Story:** As a lab analyst, I want to upload a completed offline PDF, so that the system extracts field values automatically using the Dual-UUID mechanism.

#### Acceptance Criteria

1. THE Report_Data_Entry_Page SHALL display a "Upload Completed PDF" section with a file input accepting only PDF files (`.pdf` MIME type) with a maximum file size of 20 MB.
2. WHEN the user selects a PDF file, THE Report_Data_Entry_Page SHALL display the filename, file size in human-readable format (KB or MB), and a "Change File" option allowing re-selection before upload.
3. WHEN the user confirms the upload, THE Report_Store SHALL send the PDF file as a multipart POST request to `POST /api/reports/upload-pdf` using the API_Client upload method.
4. THE Report_Store SHALL include the `X-Change-Reason` header with the value "Report created via PDF extraction" on the upload request.
5. WHILE the upload and extraction is in progress, THE Report_Data_Entry_Page SHALL display a progress indicator and disable the upload button.
6. WHEN the backend returns a successful response (201) with the extracted report data, THE Report_Data_Entry_Page SHALL navigate to the Report_Detail_Page displaying the extracted field values.
7. IF the backend returns a 400 error indicating the PDF does not contain a valid `__DOC_UUID__` field, THEN THE Report_Data_Entry_Page SHALL display an error message: "This PDF was not generated by AlcoaBase. Only PDFs downloaded from the template system can be uploaded for extraction."
8. IF the backend returns a 400 error with validation_errors (type mismatches), THEN THE Report_Data_Entry_Page SHALL display each validation error with the field label, expected type, and actual value.
9. IF the backend returns a 400 error indicating an unknown Document_UUID, THEN THE Report_Data_Entry_Page SHALL display an error message indicating no matching template was found.
10. IF the upload fails due to a network error or a response is not received within 60 seconds, THEN THE Report_Data_Entry_Page SHALL display an error notification and re-enable the upload button.
11. IF the user selects a PDF file exceeding 20 MB, THEN THE Report_Data_Entry_Page SHALL display an error message indicating the file exceeds the maximum allowed size and SHALL NOT initiate the upload request.

### Requirement 7: Report Detail View

**User Story:** As a lab analyst, I want to view a report's extracted or entered field values, so that I can review the data before validation.

#### Acceptance Criteria

1. WHEN the user navigates to a report detail route, THE Report_Detail_Page SHALL fetch the report from `GET /api/reports/{report_id}` and display all field values within 3 seconds of navigation.
2. THE Report_Detail_Page SHALL display for each field value: the field label (resolved from the template schema), the Field_UUID, the stored value, and the validation status.
3. THE Report_Detail_Page SHALL display report metadata: report ID, Document_UUID, template name, status, uploaded-by user, and upload timestamp formatted as locale-appropriate date and time with timezone (e.g., "2024-03-15 14:30 UTC").
4. WHEN a field value has validated set to true, THE Report_Detail_Page SHALL display a checkmark indicator next to that field.
5. WHEN a field value has validated set to false, THE Report_Detail_Page SHALL display a warning indicator next to that field.
6. WHEN a field value has no validation status (validated is null or undefined), THE Report_Detail_Page SHALL display no validation indicator next to that field.
7. WHILE the report detail is loading, THE Report_Detail_Page SHALL display a loading indicator.
8. IF the report is not found (404), THEN THE Report_Detail_Page SHALL display a "Report not found" message with a link back to the report list.
9. IF the report detail request fails due to a network error or non-404 server error, THEN THE Report_Detail_Page SHALL display an error message with the failure reason and a retry button.

### Requirement 8: Extracted vs. Entered Data Comparison

**User Story:** As a QA reviewer, I want to compare PDF-extracted values against manually entered values for the same template, so that I can verify data integrity and identify transcription errors.

#### Acceptance Criteria

1. WHEN a report has status "Extracted" and the user clicks "Compare with Manual Entry", THE Comparison_View SHALL fetch comparison data via the Report_Store fetchComparisonData action and display a two-column layout with "Extracted (PDF)" values on the left and "Manual Entry" values on the right, where the manual entry report is identified by matching the same Document_UUID.
2. THE Comparison_View SHALL align fields by Field_UUID, displaying the field label, extracted value, and entered value in the same row, using exact string comparison (case-sensitive, no whitespace trimming) to determine match or discrepancy.
3. WHEN an extracted value differs from the entered value for the same Field_UUID (per exact string comparison), THE Comparison_View SHALL highlight the row with a visual discrepancy indicator distinguishable from match rows.
4. WHEN an extracted value matches the entered value for the same Field_UUID (per exact string comparison), THE Comparison_View SHALL display the row with a match indicator.
5. IF a Field_UUID exists in one report but has no corresponding value in the other report, THEN THE Comparison_View SHALL display the row with a "missing value" indicator showing the available value and an empty placeholder for the missing side, and count it as a discrepancy.
6. THE Comparison_View SHALL display a summary showing: total fields compared, number of matches, and number of discrepancies.
7. WHEN all fields match between extracted and entered values with zero discrepancies, THE Comparison_View SHALL display a confirmation message indicating data integrity is verified.
8. IF one of the two reports (extracted or entered) does not exist for comparison for the same Document_UUID, THEN THE Comparison_View SHALL display a message indicating that comparison requires both an extracted report and a manually entered report for the same template.
9. WHILE the comparison data is loading, THE Comparison_View SHALL display a loading indicator.
10. IF the comparison data request fails, THEN THE Comparison_View SHALL display an error message with the failure reason and a retry button.

### Requirement 9: Report Store State Management

**User Story:** As a developer, I want a centralized state store for report operations, so that report data flows consistently across all report-related components.

#### Acceptance Criteria

1. THE Report_Store SHALL maintain state for: report list (array of reports), current report (single report detail), loading flags (isLoadingList, isLoadingDetail, isSubmitting, isUploading), error state (listError, detailError, submitError, uploadError), and comparison data.
2. THE Report_Store SHALL expose actions for: fetchReportList, fetchReportDetail, submitReport, uploadPdf, and fetchComparisonData.
3. WHEN fetchReportList is called, THE Report_Store SHALL set isLoadingList to true, clear listError, send a GET request to `/api/reports`, replace the report list state with the response array on success, and set isLoadingList to false.
4. WHEN submitReport is called with field values and a Document_UUID, THE Report_Store SHALL set isSubmitting to true, clear submitError, send a POST request to `/api/reports` with the field values payload and the `X-Change-Reason` header, set the current report state to the response on success, and set isSubmitting to false.
5. WHEN uploadPdf is called with a File object, THE Report_Store SHALL set isUploading to true, clear uploadError, send a multipart POST request to `/api/reports/upload-pdf` using the API_Client upload method with the `X-Change-Reason` header, set the current report state to the response on success, and set isUploading to false.
6. IF any API request initiated by the Report_Store fails, THEN THE Report_Store SHALL store the error message string from the ApiError in the corresponding error state property (listError, detailError, submitError, or uploadError) and set the corresponding loading flag to false.
7. THE Report_Store SHALL clear the corresponding error state property when a new request of the same type is initiated.
8. WHEN fetchReportDetail is called with a report ID, THE Report_Store SHALL set isLoadingDetail to true, clear detailError, send a GET request to `/api/reports/{report_id}`, set the current report state to the response on success, and set isLoadingDetail to false.
9. WHEN fetchComparisonData is called with a report ID, THE Report_Store SHALL send a GET request to `/api/reports/{report_id}/compare`, set the comparison data state to the response on success, and clear comparison data on failure.
10. WHEN submitReport or uploadPdf succeeds, THE Report_Store SHALL prepend the newly created report to the report list array if the list has been previously fetched.

### Requirement 10: Frontend Routing Integration

**User Story:** As a user, I want to navigate to report pages using standard URL routes, so that I can bookmark and share links to specific reports.

#### Acceptance Criteria

1. THE application router SHALL register the route `/reports` within the authenticated route guard, rendering the Report_List_Page.
2. THE application router SHALL register the route `/reports/new` rendering the Report_Data_Entry_Page with template selection.
3. THE application router SHALL register the route `/reports/new/:documentUuid` rendering the Report_Data_Entry_Page with the specified template pre-selected based on the Document_UUID path parameter.
4. THE application router SHALL register the route `/reports/:reportId` rendering the Report_Detail_Page, ordered after the `/reports/new` route to prevent "new" from matching as a reportId parameter.
5. THE application router SHALL register the route `/reports/:reportId/compare` rendering the Comparison_View.
6. THE navigation sidebar SHALL include a "Reports" link pointing to the `/reports` route, displayed as a navigation item consistent with the existing sidebar link pattern.
7. WHEN the user navigates directly to a report route via URL (bookmark or shared link), THE application router SHALL render the corresponding page component with the route parameters extracted from the URL.
8. IF the user navigates to an unmatched path under `/reports/*`, THEN THE application router SHALL redirect to the `/reports` route.

### Requirement 11: Backend Report Submission Endpoint

**User Story:** As a frontend developer, I want a backend endpoint to submit manually entered report field values, so that reports can be created without PDF upload.

#### Acceptance Criteria

1. THE Report_API SHALL expose a `POST /api/reports` endpoint accepting a JSON body with: document_uuid (string, max 12 characters), field_values (array of objects with field_uuid (string, max 40 characters) and value (string or null, max 10,000 characters) properties).
2. WHEN a POST request is received at `/api/reports`, THE Report_API SHALL validate that the document_uuid matches an existing template belonging to the tenant identified by the `X-Company-Id` header.
3. WHEN a POST request is received at `/api/reports`, THE Report_API SHALL validate that each field_uuid in the submission exists in the matched template's field list.
4. WHEN a POST request is received at `/api/reports`, THE Report_API SHALL validate each field value against its template field type: Text accepts any string, Float accepts strings parseable as decimal numbers, Integer accepts strings parseable as whole numbers without decimals, Date accepts strings in ISO 8601 format (YYYY-MM-DD), and Boolean accepts only the strings "true" or "false" (case-insensitive).
5. WHEN all validations pass, THE Report_API SHALL create a Report record with status "Draft" and persist all ReportFieldValue records atomically (all-or-nothing within a single database transaction).
6. WHEN the report is created successfully, THE Report_API SHALL return a 201 response with the full ReportResponse including field_values.
7. IF the document_uuid does not match any template, THEN THE Report_API SHALL return a 400 error with a message indicating no template was found for the given document_uuid.
8. IF any field_uuid does not exist in the template, THEN THE Report_API SHALL return a 400 error listing all invalid field UUIDs that were not found in the template.
9. IF any field value fails type validation, THEN THE Report_API SHALL return a 400 error with validation_errors detailing each failure (field_uuid, field_label, expected_type, actual_value, message) and no data SHALL be persisted.
10. THE Report_API SHALL scope the created report to the tenant identified by the `X-Company-Id` header by setting the report's company_id to the tenant's company ID.
11. IF the field_values array is empty (zero items), THEN THE Report_API SHALL return a 400 error with a message indicating that at least one field value is required.

### Requirement 12: Backend Report List Endpoint

**User Story:** As a frontend developer, I want a backend endpoint to list reports for the current tenant, so that the report list page can display all relevant reports.

#### Acceptance Criteria

1. WHEN a valid GET request is made to `/api/reports` with a valid `X-Company-Id` header, THE Report_API SHALL return a 200 response containing a JSON array of all reports belonging to the tenant identified by that header.
2. THE Report_API SHALL return each report with: id, document_uuid, template_id, uploaded_by, uploaded_at, status, and field_values array.
3. THE Report_API SHALL order reports by uploaded_at descending (newest first).
4. THE Report_API SHALL filter reports by company_id matching the resolved tenant, ensuring reports belonging to other tenants are never included in the response.
5. IF the tenant has no reports, THEN THE Report_API SHALL return a 200 response with an empty JSON array.
6. IF the `X-Company-Id` header is missing or the user is not a member of the specified company, THEN THE Report_API SHALL return an error response as defined by the TenantContext dependency (401 for missing user identity, 400 for missing company selection, 403 for unauthorized membership).

### Requirement 13: Backend Report Detail Endpoint

**User Story:** As a frontend developer, I want a backend endpoint to retrieve a single report with all field values, so that the report detail page can display complete report data.

#### Acceptance Criteria

1. THE Report_API SHALL expose a `GET /api/reports/{report_id}` endpoint that accepts an integer path parameter `report_id` and returns a ReportResponse containing: id, document_uuid, template_id, uploaded_by, uploaded_at, status, and a field_values array where each entry contains field_uuid, value, and validated.
2. WHEN the report exists and belongs to the tenant identified by the `X-Company-Id` header, THE Report_API SHALL return a 200 response with the ReportResponse.
3. IF the report does not exist, THEN THE Report_API SHALL return a 404 response with a JSON body containing a `detail` field indicating the report was not found.
4. IF the report belongs to a different tenant than the one identified by the `X-Company-Id` header, THEN THE Report_API SHALL return a 404 response with a JSON body indistinguishable from the not-found response to avoid information leakage.
5. IF the `report_id` path parameter is not a valid integer, THEN THE Report_API SHALL return a 422 response indicating a validation error.

### Requirement 14: Offline PDF Download from Report Page

**User Story:** As a lab analyst, I want to download a blank offline PDF from the report creation page, so that I can fill it out by hand and upload it later for extraction.

#### Acceptance Criteria

1. WHEN the user has selected a template on the Report_Data_Entry_Page, THE Report_Data_Entry_Page SHALL display a "Download Blank PDF" button.
2. WHEN the user clicks "Download Blank PDF", THE Report_Store SHALL send a POST request to `POST /api/templates/{document_uuid}/download-pdf` with the `X-Change-Reason` header set to "PDF downloaded for offline data collection from report page".
3. WHEN the backend returns a successful response with PDF content, THE Report_Data_Entry_Page SHALL trigger a browser file download with the filename from the Content-Disposition header, or a fallback filename of `{document_uuid}.pdf` if the header is missing or malformed.
4. WHILE the PDF download is in progress, THE Report_Data_Entry_Page SHALL display a loading indicator on the download button and disable the button to prevent duplicate requests.
5. IF the download request fails with a 404 response, THEN THE Report_Data_Entry_Page SHALL display an error notification indicating the template was not found and re-enable the download button.
6. IF the download request fails with a 400 response, THEN THE Report_Data_Entry_Page SHALL display an error notification indicating the template is not available for PDF download and re-enable the download button.
7. IF the download request fails due to a network error or non-400/404 server error, THEN THE Report_Data_Entry_Page SHALL display an error notification indicating the download failed and re-enable the download button.
