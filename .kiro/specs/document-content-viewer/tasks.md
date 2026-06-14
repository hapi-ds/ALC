# Implementation Plan: Document Content Viewer

## Overview

This plan implements document content viewing and downloading across AlcoaBase. The approach starts with the database migration and backend utilities, builds up the API endpoints, then moves to frontend components and integration. Each task builds incrementally on previous work so there is no orphaned code.

## Tasks

- [ ] 1. Database migration and content type utilities
  - [ ] 1.1 Create Alembic migration to add `content_type` column to `document_versions`
    - Generate a new Alembic migration file in `src/backend/alembic/versions/`
    - Add nullable `sa.Column("content_type", sa.String(200), nullable=True)` to the `document_versions` table
    - Include a downgrade operation that drops the column
    - _Requirements: 5.1_

  - [ ] 1.2 Create `services/content_type_utils.py` with pure utility functions
    - Implement `resolve_content_type(stored_content_type: str | None, storage_key: str) -> str` with extension-to-MIME mapping and `application/octet-stream` fallback
    - Implement `is_previewable(content_type: str) -> bool` checking against the `PREVIEWABLE_TYPES` set (PDF, markdown, plain text, images)
    - Implement `build_content_disposition(disposition: str, filename: str) -> str` with RFC 6266 UTF-8 filename encoding
    - Add type hints and docstrings per project conventions
    - _Requirements: 5.1, 5.2, 2.4_

  - [ ]* 1.3 Write property tests for content type utilities (Property 4: Content-Type Resolution)
    - **Property 4: Content-Type Resolution**
    - **Validates: Requirements 5.1, 5.2**
    - Create `src/backend/tests/properties/test_content_type_resolution.py`
    - Use Hypothesis to generate random `(stored_type, storage_key)` pairs and verify resolution logic: stored value takes priority, then extension mapping, then octet-stream fallback

  - [ ]* 1.4 Write property tests for disposition classification (Property 2: Content-Type Disposition Classification)
    - **Property 2: Content-Type Disposition Classification**
    - **Validates: Requirements 2.4**
    - Create `src/backend/tests/properties/test_content_type_disposition.py`
    - Use Hypothesis to generate random MIME type strings and verify `is_previewable()` correctly classifies them as inline vs. attachment

  - [ ]* 1.5 Write property tests for response header construction (Property 1: Response Header Correctness)
    - **Property 1: Response Header Correctness**
    - **Validates: Requirements 1.1, 2.1, 5.3**
    - Create `src/backend/tests/properties/test_response_header_correctness.py`
    - Use Hypothesis to generate random titles (unicode, special chars, long strings) and content types, verify `build_content_disposition()` produces valid RFC 6266 headers

- [ ] 2. Backend audit access logger
  - [ ] 2.1 Extend `services/audit_access_logger.py` with document access logging
    - Add `log_document_access(session, user_id, document_uuid, major_version, minor_version, action)` async function
    - `action` parameter accepts `"download"` or `"content_preview"`
    - Record event to the audit trail including user ID, document UUID, version, and timestamp
    - _Requirements: 6.4_

- [ ] 3. Backend download and content endpoints
  - [ ] 3.1 Implement download endpoint in `api/documents.py`
    - Add `GET /{document_uuid}/versions/{major_version}/{minor_version}/download` route
    - Look up `DocumentVersion` by UUID + version, return 404 if not found
    - Call `DocumentService.check_document_access()` for RBAC enforcement, return 401/403 as appropriate
    - Retrieve file bytes via `StorageService.download_file(storage_key)`
    - Return `StreamingResponse` with `Content-Type` from `resolve_content_type()`, `Content-Disposition: attachment`, and `Content-Length` header
    - Call `log_document_access()` after successful retrieval
    - Return 502 if StorageService raises an exception
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.3, 6.1, 6.2, 6.3, 6.4_

  - [ ] 3.2 Implement content preview endpoint in `api/documents.py`
    - Add `GET /{document_uuid}/versions/{major_version}/{minor_version}/content` route
    - Same RBAC and version lookup logic as download endpoint
    - Use `is_previewable()` to determine disposition: `inline` for previewable types, `attachment` fallback for others
    - For `text/markdown`, set `Content-Type: text/markdown; charset=utf-8`
    - Call `log_document_access()` with action `"content_preview"`
    - Return 502 on storage errors
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.1, 6.2, 6.3, 6.4_

  - [ ]* 3.3 Write unit tests for download and content endpoints
    - Create `src/backend/tests/unit/test_document_content_endpoints.py`
    - Mock `DocumentService` and `StorageService`
    - Test 404 for missing version, 403 for unauthorized user, 502 for storage failure
    - Verify correct `Content-Type`, `Content-Disposition`, and `Content-Length` headers
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.4, 2.5_

  - [ ]* 3.4 Write property test for RBAC enforcement consistency (Property 3: RBAC Enforcement Consistency)
    - **Property 3: RBAC Enforcement Consistency**
    - **Validates: Requirements 1.4, 6.2, 6.3**
    - Create `src/backend/tests/properties/test_document_download_rbac.py`
    - Use Hypothesis to generate user/document combinations and verify access is granted iff `check_document_access` returns True

- [ ] 4. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Frontend API client and download utility
  - [ ] 5.1 Add `download` method to `lib/apiClient.ts`
    - Extend the existing `apiClient` with a `download(url: string, options?: ApiClientOptions): Promise<Blob>` method
    - Perform authenticated GET request with `Authorization: Bearer` header
    - Return response as `Blob` object
    - Propagate HTTP error responses (401, 403, 404) as `ApiError` consistent with existing patterns
    - _Requirements: 7.1, 7.3_

  - [ ] 5.2 Create `lib/fileDownload.ts` utility
    - Implement `triggerBrowserDownload(blob: Blob, filename: string): void`
    - Create a temporary object URL, trigger browser-native save dialog via hidden anchor element click, then revoke the URL
    - _Requirements: 7.2_

  - [ ]* 5.3 Write unit tests for apiClient.download and fileDownload
    - Create `src/frontend/src/__tests__/documents/apiClientDownload.test.ts`
    - Test `apiClient.download()` returns Blob on success
    - Test `apiClient.download()` throws ApiError on 401/403/404
    - Test `triggerBrowserDownload` creates and clicks an anchor element
    - _Requirements: 7.1, 7.2, 7.3_

- [ ] 6. Frontend ContentViewer component
  - [ ] 6.1 Create `components/documents/ContentViewer.tsx`
    - Accept props: `documentUuid`, `majorVersion`, `minorVersion`, `contentType`
    - For `application/pdf`: render an `<iframe>` pointing to the content endpoint URL
    - For `text/markdown`: fetch raw markdown via `apiClient.download()`, render as HTML using the existing `renderMarkdown` utility from `lib/renderMarkdown.ts`
    - For unsupported types: display informational message with download fallback button
    - Handle loading state, error state with retry button, and 30-second timeout
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 6.2 Write unit tests for ContentViewer
    - Create `src/frontend/src/__tests__/documents/ContentViewer.test.tsx`
    - Test iframe rendering for PDF content type
    - Test markdown rendered as HTML
    - Test fallback message for unsupported types
    - Test loading and error states
    - _Requirements: 3.2, 3.3, 3.4_

  - [ ]* 6.3 Write property test for latest version resolution (Property 5: Latest Version Resolution)
    - **Property 5: Latest Version Resolution**
    - **Validates: Requirements 4.3**
    - Create `src/frontend/src/__tests__/properties/latestVersionResolution.property.test.ts`
    - Use fast-check to generate random arrays of `{major_version, minor_version}` tuples and verify the selected latest version has the maximum `(major, minor)` tuple

  - [ ]* 6.4 Write property test for markdown rendering (Property 6: Markdown Rendering Produces Valid HTML Structure)
    - **Property 6: Markdown Rendering Produces Valid HTML Structure**
    - **Validates: Requirements 3.3**
    - Create `src/frontend/src/__tests__/properties/markdownRendering.property.test.ts`
    - Use fast-check to generate random markdown strings with headers and links, verify rendered HTML contains corresponding `<h1>`–`<h6>` and `<a>` elements

- [ ] 7. Frontend DownloadButton component
  - [ ] 7.1 Create `components/documents/DownloadButton.tsx`
    - Accept props: `documentUuid`, `version` (optional, defaults to latest), `documentTitle`, `variant` (`"icon"` | `"button"`)
    - On click: call `apiClient.download()` with the download endpoint URL, then `triggerBrowserDownload()` with the blob and document title
    - Show loading indicator while download is in progress
    - Handle errors with toast notification
    - _Requirements: 4.1, 4.3, 4.4_

  - [ ]* 7.2 Write unit tests for DownloadButton
    - Create `src/frontend/src/__tests__/documents/DownloadButton.test.tsx`
    - Test download flow triggers on click
    - Test loading indicator during download
    - Test error handling shows toast
    - _Requirements: 4.1, 4.4_

- [ ] 8. Integration into existing pages
  - [ ] 8.1 Integrate ContentViewer and DownloadButton into DocumentDetail page
    - Import `ContentViewer` and `DownloadButton` into `components/documents/DocumentDetail.tsx`
    - Render `ContentViewer` below the metadata section showing the latest (or selected) version content
    - Add `DownloadButton` for the currently viewed version
    - When user selects a different version from `VersionHistoryPanel`, update `ContentViewer` props
    - _Requirements: 3.1, 3.5, 3.6_

  - [ ] 8.2 Add download button to search results
    - Locate the search result item component and add a `DownloadButton` with `variant="icon"` targeting latest version
    - _Requirements: 4.1_

  - [ ] 8.3 Add download/view link to Knowledge Chat citations
    - In the Knowledge Chat citation component, add a clickable link that opens the document content endpoint in a new tab or triggers a download
    - _Requirements: 4.2_

  - [ ]* 8.4 Write integration tests for DocumentDetail with ContentViewer
    - Create `src/frontend/src/__tests__/documents/DocumentDetailViewer.test.tsx`
    - Test that version selection updates ContentViewer
    - Test DownloadButton presence and interaction
    - _Requirements: 3.5, 3.6_

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python (Hypothesis for property tests, pytest for unit tests)
- Frontend uses TypeScript (fast-check for property tests, Vitest + Testing Library for unit tests)
- The `audit_access_logger.py` file already exists — task 2.1 extends it with document-specific access logging

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "3.1", "3.2"] },
    { "id": 2, "tasks": ["3.3", "3.4", "5.1", "5.2"] },
    { "id": 3, "tasks": ["5.3", "6.1", "7.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "6.4", "7.2"] },
    { "id": 5, "tasks": ["8.1", "8.2", "8.3"] },
    { "id": 6, "tasks": ["8.4"] }
  ]
}
```
