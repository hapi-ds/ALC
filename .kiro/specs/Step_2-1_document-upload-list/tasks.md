# Implementation Plan: Document Upload & List

## Overview

This plan implements the full document upload and listing feature across two deliverables: (1) Frontend integration wiring the React Documents page to the real FastAPI backend with pagination, filtering, upload dialogs, and detail views; (2) A Python CLI tool for bulk-uploading directory trees. Tasks are ordered so each step builds on the previous, with property-based tests placed close to the code they validate.

## Tasks

- [x] 1. Define TypeScript types and extend the API client
  - [x] 1.1 Create document type definitions in `src/frontend/src/types/document.ts`
    - Define `DocumentTag`, `DocumentVersion`, `DocumentResponse`, `DocumentSearchResponse`, `UploadFormData`, and `VersionUploadFormData` interfaces
    - Match the shapes specified in the design Data Models section
    - _Requirements: 1.3, 5.2, 5.4_

  - [x] 1.2 Add `upload()` method to `src/frontend/src/lib/apiClient.ts`
    - Add a new `upload<T>(url: string, formData: FormData, options?: ApiClientOptions): Promise<T>` method
    - Must NOT set `Content-Type` header (browser sets multipart boundary automatically)
    - Must attach Bearer token, `X-Company-Id`, and `X-User-Id` headers
    - Must support 401 retry with token refresh (reuse existing refresh logic)
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 1.3 Write property test for API client upload headers (Property 8)
    - **Property 8: API client upload method sets correct headers**
    - For any access token, userId, and companyId, verify Authorization is `Bearer {token}`, X-Company-Id and X-User-Id are set, and Content-Type is NOT `application/json`
    - Place test in `src/frontend/src/__tests__/documents/apiClient.upload.property.test.ts`
    - **Validates: Requirements 9.1, 9.2, 9.3**

- [x] 2. Rewrite the document store with real API integration
  - [x] 2.1 Rewrite `src/frontend/src/stores/documentStore.ts` with full state and actions
    - Implement `DocumentState` interface from design: documents, selectedDocument, total, offset, limit, tagFilter, folderPathFilter, isLoading, error
    - Implement `fetchDocuments()` calling `GET /api/v1/documents` with offset, limit, tag, folder_path query params
    - Implement `fetchDocument(uuid)` calling `GET /api/v1/documents/{uuid}`
    - Implement `uploadDocument(formData)` calling `apiClient.upload()` to `POST /api/v1/documents`
    - Implement `createVersion(uuid, formData)` calling `apiClient.upload()` to `POST /api/v1/documents/{uuid}/versions`
    - Implement pagination actions: `setPage`, `nextPage`, `prevPage`
    - Implement filter actions: `setTagFilter`, `setFolderPathFilter`, `clearFilters`
    - Filters must reset offset to 0 when applied
    - _Requirements: 1.1, 2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 4.5, 6.3_

  - [x] 2.2 Write property test for pagination arithmetic (Property 2)
    - **Property 2: Pagination arithmetic is consistent**
    - For any valid offset, limit, total: verify currentPage = floor(offset/limit)+1, totalPages = ceil(total/limit), nextPage increments offset by limit, prevPage decrements (min 0), prev disabled iff offset=0, next disabled iff offset+limit>=total
    - Place test in `src/frontend/src/__tests__/documents/pagination.property.test.ts`
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

  - [x] 2.3 Write property test for filter resets pagination (Property 3)
    - **Property 3: Applying a filter resets pagination to first page**
    - For any offset > 0, applying tag or folder_path filter resets offset to 0
    - Place test in `src/frontend/src/__tests__/documents/filters.property.test.ts`
    - **Validates: Requirements 3.3**

  - [x] 2.4 Write property test for filters mapping to query params (Property 4)
    - **Property 4: Active filters map to API query parameters**
    - For any non-null tag/folder_path in store, the API request URL contains corresponding query params
    - Place test in `src/frontend/src/__tests__/documents/filters.property.test.ts`
    - **Validates: Requirements 3.1, 3.2**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement the UploadDialog component
  - [x] 4.1 Create `src/frontend/src/components/documents/UploadDialog.tsx`
    - Modal dialog with file picker supporting click and drag-and-drop
    - Form fields: title (required, max 500 chars), folder_path (required, max 1000 chars), document_type (required), tags (comma-separated, optional)
    - Client-side validation with inline error messages on invalid fields
    - Submit constructs FormData and calls `documentStore.uploadDocument()`
    - Show progress indicator and disable submit button while uploading
    - On success: close dialog, store refreshes document list
    - On failure: display error message from API response
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 10.1, 10.2, 10.3, 10.4_

  - [x] 4.2 Write property test for upload form validation (Property 5)
    - **Property 5: Upload form field validation**
    - For any title string: valid iff trimmed length 1–500. For any folder_path: valid iff trimmed length 1–1000. Submission blocked if file is null, title invalid, or folder_path invalid
    - Place test in `src/frontend/src/__tests__/documents/uploadValidation.property.test.ts`
    - **Validates: Requirements 4.3, 10.1, 10.2, 10.3**

  - [x] 4.3 Write property test for FormData construction (Property 6)
    - **Property 6: Multipart FormData construction preserves all fields**
    - For any valid upload form data, the constructed FormData contains entries for file, title, folder_path, document_type, tags with matching values
    - Place test in `src/frontend/src/__tests__/documents/formData.property.test.ts`
    - **Validates: Requirements 4.5, 6.3**

- [x] 5. Implement DocumentDetail and VersionUploadDialog components
  - [x] 5.1 Create `src/frontend/src/components/documents/DocumentDetail.tsx`
    - Display full document metadata: title, document_uuid, folder_path, document_type, current_status, created_by, created_at
    - Render tags as visual badges
    - Render version history showing major_version, minor_version, uploaded_at, change_reason for each version
    - Include a "New Version" action button
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1_

  - [x] 5.2 Create `src/frontend/src/components/documents/VersionUploadDialog.tsx`
    - Modal with file picker, version type selector (major/minor), and change reason text field
    - Submit constructs FormData and calls `documentStore.createVersion(uuid, formData)`
    - Show progress indicator during upload; display error on failure; refresh detail on success
    - _Requirements: 6.2, 6.3, 6.4, 6.5_

  - [x] 5.3 Write property test for document detail rendering (Property 7)
    - **Property 7: Document detail renders all metadata, tags, and versions**
    - For any valid DocumentResponse with N tags and M versions, verify all metadata fields, N tag badges, and M version entries are rendered
    - Place test in `src/frontend/src/__tests__/documents/documentDetail.property.test.ts`
    - **Validates: Requirements 5.2, 5.3, 5.4**

- [x] 6. Implement FilterBar and Pagination components
  - [x] 6.1 Create `src/frontend/src/components/documents/FilterBar.tsx`
    - Tag filter dropdown/input and folder path text input
    - On change, call `documentStore.setTagFilter()` / `setFolderPathFilter()`
    - Clear button calls `documentStore.clearFilters()`
    - _Requirements: 3.1, 3.2, 3.4_

  - [x] 6.2 Create `src/frontend/src/components/documents/Pagination.tsx`
    - Display total document count and current page position (e.g., "Page 1 of 5")
    - Previous/Next buttons wired to `documentStore.prevPage()` / `nextPage()`
    - Disable Previous when on first page (offset === 0)
    - Disable Next when on last page (offset + limit >= total)
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [x] 7. Rewrite DocumentsPage to orchestrate all components
  - [x] 7.1 Rewrite `src/frontend/src/pages/DocumentsPage.tsx`
    - On mount: call `documentStore.fetchDocuments()`
    - Display company name from auth context
    - Show loading indicator while `isLoading` is true
    - Show error banner when `error` is set
    - Show empty state when documents array is empty and not loading
    - Render `FilterBar`, `DocumentList`, `Pagination` for the list view
    - Render `DocumentDetail` when a document is selected (fetch on click)
    - Upload button opens `UploadDialog`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 4.1, 5.1_

  - [x] 7.2 Update `src/frontend/src/components/documents/DocumentList.tsx`
    - Accept `DocumentResponse[]` and render document_uuid, title, document_type, current_status, tags (as badges), and created_at
    - Make each row clickable to select a document
    - _Requirements: 1.3_

  - [x] 7.3 Write property test for document list field rendering (Property 1)
    - **Property 1: Document list renders all required fields**
    - For any array of valid DocumentResponse objects, rendered output contains each document's document_uuid, title, document_type, current_status, at least one tag, and created_at
    - Place test in `src/frontend/src/__tests__/documents/documentList.property.test.ts`
    - **Validates: Requirements 1.3**

  - [x] 7.4 Write unit tests for DocumentsPage integration
    - Test mount triggers fetchDocuments
    - Test loading state shows spinner
    - Test empty state message
    - Test error state displays error
    - Test upload button opens dialog
    - Test document click fetches detail
    - Place tests in `src/frontend/src/__tests__/documents/DocumentsPage.test.ts`
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 4.1, 5.1_

- [x] 8. Checkpoint - Ensure all frontend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement the Bulk Upload CLI tool
  - [x] 9.1 Create `src/backend/scripts/bulk_upload.py` with argparse CLI interface
    - Accept required args: `--directory`, `--api-url`, `--company-id`, `--user-id`
    - Accept optional args: `--token` (or `ALCOABASE_TOKEN` env var), `--document-type` (default "General"), `--tags`, `--dry-run`
    - Validate root directory exists and is readable before starting
    - Exit with code 1 and descriptive error if directory invalid
    - _Requirements: 7.1, 8.1, 8.4, 8.5, 8.6, 8.7_

  - [x] 9.2 Implement directory walk and metadata derivation
    - Recursively walk directory tree using `pathlib.Path.rglob("*")` to find all regular files
    - Derive `title` from filename stem (without extension)
    - Derive `folder_path` from relative parent path within root directory
    - _Requirements: 7.2, 7.3, 7.4_

  - [x] 9.3 Implement upload loop with httpx multipart POST
    - For each file: construct multipart form with file, title, folder_path, document_type, tags, user_id
    - Set `Authorization: Bearer {token}` and `X-Company-Id: {company_id}` headers
    - Display progress: "Uploading file X of Y: {filename}"
    - On individual failure: log error with file path and status, continue to next file
    - On `--dry-run`: list files that would be uploaded without sending requests
    - _Requirements: 7.5, 7.6, 7.7, 8.2, 8.3, 8.6_

  - [x] 9.4 Implement summary reporting
    - After all files processed, print summary: total files, successful uploads, failed uploads
    - _Requirements: 7.8_

  - [x] 9.5 Write property test for path-to-metadata derivation (Property 9)
    - **Property 9: CLI path-to-metadata derivation**
    - For any root path and descendant file path, derived folder_path equals relative directory portion, derived title equals filename stem
    - Place test in `src/backend/tests/properties/test_bulk_upload_properties.py`
    - **Validates: Requirements 7.3, 7.4**

  - [x] 9.6 Write property test for directory walk completeness (Property 10)
    - **Property 10: CLI directory walk discovers all files**
    - For any directory tree structure, walk returns exactly all regular files with no duplicates or omissions
    - Place test in `src/backend/tests/properties/test_bulk_upload_properties.py`
    - **Validates: Requirements 7.2**

  - [x] 9.7 Write property test for request construction (Property 11)
    - **Property 11: CLI request construction includes all required fields and headers**
    - For any valid metadata and config, the constructed request includes Authorization, X-Company-Id, multipart encoding, and all form fields
    - Place test in `src/backend/tests/properties/test_bulk_upload_properties.py`
    - **Validates: Requirements 7.5, 8.2, 8.3, 8.4, 8.5**

  - [x] 9.8 Write property test for summary counts (Property 12)
    - **Property 12: CLI summary counts are arithmetically correct**
    - For any sequence of N uploads with S successes and F failures, summary reports total=N, successful=S, failed=F, and N=S+F
    - Place test in `src/backend/tests/properties/test_bulk_upload_properties.py`
    - **Validates: Requirements 7.8**

  - [x] 9.9 Write unit tests for CLI tool
    - Test token from env var fallback
    - Test dry-run lists files without HTTP calls
    - Test non-existent directory exits with error code 1
    - Test single file failure doesn't stop processing
    - Place tests in `src/backend/tests/unit/test_bulk_upload.py`
    - _Requirements: 7.7, 8.1, 8.6, 8.7_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–12)
- Unit tests validate specific examples and edge cases
- Frontend tests use vitest + fast-check (already in devDependencies)
- Backend CLI tests use pytest + hypothesis (already in dev dependencies)
- All frontend test files go in `src/frontend/src/__tests__/documents/`
- All backend CLI test files go in `src/backend/tests/properties/` and `src/backend/tests/unit/`
