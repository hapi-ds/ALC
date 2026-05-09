# Implementation Plan: Report Data Entry & PDF Extraction

## Overview

This plan implements the complete report lifecycle: backend CRUD endpoints for manual report submission, listing, and comparison; frontend pages for report list, data entry, detail view, and comparison; a Zustand store for state management; client-side validation; and PDF upload/download integration. Tasks are ordered so each builds on prior work, starting with shared types and backend endpoints, then frontend store, validation, components, pages, and routing.

## Tasks

- [x] 1. Backend schemas and shared validation utility
  - [x] 1.1 Add request/response schemas for report endpoints
    - Add `ReportFieldValueInput`, `ReportCreateRequest`, `ComparisonFieldRow`, and `ComparisonResponse` to `src/backend/src/alcoabase/schemas/report.py`
    - _Requirements: 11.1, 13.1_

  - [x] 1.2 Extract shared type validation utility from PDFExtractor
    - Create `src/backend/src/alcoabase/services/field_validator.py` with a `validate_single_value` function extracted from `PDFExtractor._validate_single_value`
    - Update `PDFExtractor._validate_single_value` to delegate to the shared utility
    - The shared function must accept `"true"/"false"` (case-insensitive) for Boolean in manual entry context
    - _Requirements: 11.4, 11.9_

  - [x] 1.3 Write property tests for backend type validation (Property 6)
    - **Property 6: Backend type validation rejects invalid values and accepts valid ones**
    - **Validates: Requirements 11.4, 11.9**
    - Use `hypothesis` with `@settings(max_examples=100)`
    - Test file: `src/backend/tests/test_report_validation.py`

- [x] 2. Backend report endpoints
  - [x] 2.1 Implement POST /api/reports endpoint
    - Add `create_report` handler to `src/backend/src/alcoabase/api/reports.py`
    - Validate document_uuid belongs to tenant, field_uuids exist in template, type validation per field
    - Create Report with status "Draft" + ReportFieldValues atomically
    - Return 201 with ReportResponse; return 400 for validation failures
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 11.11_

  - [x] 2.2 Implement GET /api/reports endpoint
    - Add `list_reports` handler to `src/backend/src/alcoabase/api/reports.py`
    - Filter by company_id, order by uploaded_at descending, eagerly load field_values
    - Return 200 with list of ReportResponse
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 2.3 Implement GET /api/reports/{report_id} endpoint
    - Add `get_report` handler to `src/backend/src/alcoabase/api/reports.py`
    - Scope to tenant; return 404 for not-found and cross-tenant access (indistinguishable)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 2.4 Implement GET /api/reports/{report_id}/compare endpoint
    - Add `compare_report` handler to `src/backend/src/alcoabase/api/reports.py`
    - Load source report (must be "Extracted"), find matching "Draft" report with same document_uuid
    - Align fields by field_uuid, exact string comparison, return ComparisonResponse
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [x] 2.5 Write property tests for backend report list tenant isolation (Property 7)
    - **Property 7: Backend report list is tenant-isolated and ordered**
    - **Validates: Requirements 12.1, 12.3, 12.4**
    - Use `hypothesis` with `@settings(max_examples=100)`
    - Test file: `src/backend/tests/test_reports_api.py`

  - [x] 2.6 Write property tests for backend report detail tenant isolation (Property 8)
    - **Property 8: Backend report detail enforces tenant isolation**
    - **Validates: Requirements 13.2, 13.4**
    - Test file: `src/backend/tests/test_reports_api.py`

  - [x] 2.7 Write property tests for submission response completeness (Property 9)
    - **Property 9: Backend submission response contains all submitted field values**
    - **Validates: Requirements 11.6**
    - Test file: `src/backend/tests/test_reports_api.py`

- [x] 3. Checkpoint - Backend endpoints complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Frontend types and validation logic
  - [x] 4.1 Create frontend report types
    - Create `src/frontend/src/types/report.ts` with `ReportResponse`, `ReportFieldValueResponse`, `FieldValueEntry`, `ReportCreatePayload`, `ComparisonData`, `ComparisonFieldRow` interfaces
    - _Requirements: 9.1_

  - [x] 4.2 Implement client-side field validation module
    - Create `src/frontend/src/lib/reportValidation.ts` with `validateField` and `validateAllFields` functions
    - Support Text, Float, Integer, Date, Boolean types with range/length constraints
    - Respect `touchedFields` set for selective validation; `forceAll` flag for submit-time validation
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [x] 4.3 Write property tests for field type validation (Property 1)
    - **Property 1: Field type validation correctly accepts and rejects values**
    - **Validates: Requirements 4.1, 4.2, 4.3, 11.4**
    - Use `fast-check` with `{ numRuns: 100 }`
    - Test file: `src/frontend/src/lib/__tests__/reportValidation.test.ts`

  - [x] 4.4 Write property tests for range/length constraint validation (Property 2)
    - **Property 2: Range and length constraint validation**
    - **Validates: Requirements 4.4, 4.5**
    - Test file: `src/frontend/src/lib/__tests__/reportValidation.test.ts`

  - [x] 4.5 Write property tests for required field validation on submit (Property 3)
    - **Property 3: Required field validation on submit**
    - **Validates: Requirements 4.6, 4.9**
    - Test file: `src/frontend/src/lib/__tests__/reportValidation.test.ts`

  - [x] 4.6 Write property tests for untouched fields (Property 4)
    - **Property 4: Untouched fields produce no validation errors**
    - **Validates: Requirements 4.8, 4.9**
    - Test file: `src/frontend/src/lib/__tests__/reportValidation.test.ts`

- [x] 5. Frontend Report Store
  - [x] 5.1 Implement Report Store with Zustand
    - Create `src/frontend/src/stores/reportStore.ts` with state and actions as defined in design
    - Actions: `fetchReportList`, `fetchReportDetail`, `submitReport`, `uploadPdf`, `fetchComparisonData`, `downloadBlankPdf`
    - Loading flags, error states, error cleanup on new requests, list prepend on creation
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

  - [x] 5.2 Write unit tests for Report Store actions
    - Test state transitions for each action (loading -> success/error)
    - Test error cleanup and list prepend behavior
    - Mock apiClient
    - Test file: `src/frontend/src/stores/__tests__/reportStore.test.ts`
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 6. Frontend field components
  - [x] 6.1 Implement field input components
    - Create `src/frontend/src/components/reports/fields/TextField.tsx`
    - Create `src/frontend/src/components/reports/fields/FloatField.tsx`
    - Create `src/frontend/src/components/reports/fields/IntegerField.tsx`
    - Create `src/frontend/src/components/reports/fields/DateField.tsx`
    - Create `src/frontend/src/components/reports/fields/BooleanField.tsx`
    - Create `src/frontend/src/components/reports/fields/ContentBlock.tsx`
    - Create `src/frontend/src/components/reports/fields/index.ts` barrel export
    - Each field renders with label, required indicator, help text, error display, unit label (numeric)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

  - [x] 6.2 Implement DynamicForm component
    - Create `src/frontend/src/components/reports/DynamicForm.tsx`
    - Iterate template elements array, render typed field or content block per element
    - Manage internal form state, validate on blur, disable submit when errors exist
    - Map server-side errors to fields by field_uuid
    - _Requirements: 3.1, 4.7, 4.8, 4.9, 5.5_

  - [x] 6.3 Implement TemplateSelector component
    - Create `src/frontend/src/components/reports/TemplateSelector.tsx`
    - Fetch and display ReadOnly templates with name, Document_UUID, field count
    - Loading, error, and empty states
    - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.7, 2.8_

  - [x] 6.4 Write property test for template selector filtering (Property 10)
    - **Property 10: Template selector filters to ReadOnly status only**
    - **Validates: Requirements 2.1**
    - Test file: `src/frontend/src/components/reports/__tests__/TemplateSelector.test.ts`

  - [x] 6.5 Implement PdfUploadSection component
    - Create `src/frontend/src/components/reports/PdfUploadSection.tsx`
    - File input accepting `.pdf` only, 20MB max, filename/size preview, "Change File" option
    - Upload confirmation button, progress indicator, error display
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.10, 6.11_

  - [x] 6.6 Implement comparison components
    - Create `src/frontend/src/components/reports/ComparisonRow.tsx`
    - Create `src/frontend/src/components/reports/ComparisonSummary.tsx`
    - ComparisonRow: field label, extracted value, entered value, match/discrepancy/missing indicators
    - ComparisonSummary: total fields, matches, discrepancies count, "data integrity verified" message
    - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 6.7 Write property test for comparison field alignment (Property 5)
    - **Property 5: Comparison field alignment and exact string matching**
    - **Validates: Requirements 8.2, 8.3, 8.4, 8.5, 8.6**
    - Use `fast-check` with `{ numRuns: 100 }`
    - Test file: `src/frontend/src/lib/__tests__/comparison.test.ts`

- [x] 7. Checkpoint - Components complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Frontend pages
  - [x] 8.1 Implement ReportListPage
    - Create `src/frontend/src/pages/ReportListPage.tsx`
    - Fetch reports via store, display table with ID, template name, Document_UUID, status badge, uploaded-by, relative timestamp (hover shows ISO 8601)
    - Pagination (50 per page), row click navigates to detail, "New Report" button
    - Loading, error with retry, empty state
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 8.2 Implement ReportDataEntryPage
    - Create `src/frontend/src/pages/ReportDataEntryPage.tsx`
    - Template selection (auto-select if `:documentUuid` param present)
    - Render DynamicForm after template selection
    - Submit button calls store.submitReport, navigates to detail on success
    - PDF upload section, "Download Blank PDF" button (visible after template selection)
    - Handle all error states (400 validation, 403, network, 5xx)
    - _Requirements: 2.1, 2.4, 2.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [x] 8.3 Write property test for Content-Disposition filename extraction (Property 11)
    - **Property 11: Content-Disposition filename extraction**
    - **Validates: Requirements 14.3**
    - Test file: `src/frontend/src/lib/__tests__/filenameExtraction.test.ts`

  - [x] 8.4 Implement ReportDetailPage
    - Create `src/frontend/src/pages/ReportDetailPage.tsx`
    - Fetch report via store, display metadata (ID, Document_UUID, template name, status, uploaded-by, formatted timestamp)
    - Display field values with labels, validation indicators (checkmark/warning/none)
    - "Compare with Manual Entry" button (visible when status is "Extracted")
    - Loading, 404, and error states
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [x] 8.5 Implement ComparisonViewPage
    - Create `src/frontend/src/pages/ComparisonViewPage.tsx`
    - Fetch comparison data via store, two-column layout with ComparisonRow and ComparisonSummary
    - Loading, error, and "requires both reports" states
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10_

- [x] 9. Frontend routing and navigation
  - [x] 9.1 Add report routes to App.tsx and sidebar navigation
    - Add routes: `/reports`, `/reports/new`, `/reports/new/:documentUuid`, `/reports/:reportId`, `/reports/:reportId/compare`
    - Ensure `/reports/new` is ordered before `/reports/:reportId`
    - Add "Reports" link to sidebar navigation in MainLayout
    - Add wildcard redirect for unmatched `/reports/*` paths to `/reports`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

- [x] 10. Final checkpoint - Full integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python (FastAPI + Pydantic + SQLAlchemy async), frontend uses TypeScript (React + Zustand + Vitest)
- The existing `PDFExtractor._validate_single_value` is extracted to a shared utility to avoid duplication between upload and manual entry paths
- All backend endpoints use the existing `TenantContext` dependency for multi-tenancy
- All mutating requests include `X-Change-Reason` header for ALCOA+ audit compliance

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "4.1"] },
    { "id": 1, "tasks": ["1.3", "2.1", "2.2", "2.3", "4.2"] },
    { "id": 2, "tasks": ["2.4", "2.5", "2.6", "2.7", "4.3", "4.4", "4.5", "4.6"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1", "6.3", "6.5", "6.6"] },
    { "id": 5, "tasks": ["6.2", "6.4", "6.7"] },
    { "id": 6, "tasks": ["8.1", "8.4", "8.5"] },
    { "id": 7, "tasks": ["8.2", "8.3"] },
    { "id": 8, "tasks": ["9.1"] }
  ]
}
```
