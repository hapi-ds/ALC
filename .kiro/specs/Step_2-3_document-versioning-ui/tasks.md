# Implementation Plan: Document Versioning UI

## Overview

This plan implements the frontend document versioning UI feature for AlcoaBase. The backend is already complete — this is purely React/TypeScript work covering: pure utility functions, Zustand store extensions, new components (VersionHistoryPanel, VersionDetailView, VersionComparisonView, DiffMetadataView), enhancement of the existing VersionUploadDialog, and integration into DocumentDetail. All code uses the existing stack: React 19, Zustand v5, Tailwind CSS v4, shadcn/ui patterns, Lucide icons, Vitest, and fast-check.

## Tasks

- [x] 1. Create utility functions and types
  - [x] 1.1 Create `src/frontend/src/lib/versionUtils.ts` with all pure utility functions
    - Implement `sortVersionsDescending`, `isCurrentVersion`, `truncateText`, `formatFileSize`, `computeTimeDelta`, `formatTimeDelta`, `computeVersionDiff`, `validateFileSize`, `validateChangeReason`
    - Export the `TimeDelta` and `VersionDiff` interfaces
    - Use the `DocumentVersion` type from `src/frontend/src/types/document.ts`
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 4.1, 4.2, 4.3, 7.1, 7.2, 7.3_

  - [x] 1.2 Write property test: version sorting is stable descending (Property 1)
    - **Property 1: Version sorting is stable descending**
    - **Validates: Requirements 1.1**
    - Create test file `src/frontend/src/__tests__/versioning/versionUtils.property.test.ts`
    - Generate arbitrary arrays of DocumentVersion with distinct (major, minor) tuples
    - Assert every adjacent pair satisfies versions[i] > versions[i+1] lexicographically

  - [x] 1.3 Write property test: current version identification is unique and maximal (Property 2)
    - **Property 2: Current version identification is unique and maximal**
    - **Validates: Requirements 2.1, 2.2**
    - For any non-empty array with distinct (major, minor), exactly one version is identified as current
    - That version has the maximum (major, minor) tuple

  - [x] 1.4 Write property test: text truncation preserves content within limit (Property 3)
    - **Property 3: Text truncation preserves content within limit**
    - **Validates: Requirements 1.2, 1.3**
    - For any string and positive maxLength, output length ≤ maxLength + 1
    - If input ≤ maxLength, output equals input exactly
    - If input > maxLength, output ends with "…" and prefix is a prefix of original

  - [x] 1.5 Write property test: file size formatting is consistent with threshold (Property 4)
    - **Property 4: File size formatting is consistent with threshold**
    - **Validates: Requirements 7.3**
    - For bytes < 1,048,576 output contains "KB"; for bytes ≥ 1,048,576 output contains "MB"
    - Numeric value is mathematically correct

  - [x] 1.6 Write property test: time delta computation is non-negative and reversible (Property 5)
    - **Property 5: Time delta computation is non-negative and reversible**
    - **Validates: Requirements 4.2**
    - All fields (days, hours, minutes) are non-negative integers
    - Total minutes equals absolute difference within 1-minute tolerance

  - [x] 1.7 Write property test: version diff detects all field changes correctly (Property 6)
    - **Property 6: Version diff detects all field changes correctly**
    - **Validates: Requirements 4.1, 4.3, 4.4**
    - hashChanged equals (left.file_hash !== right.file_hash)
    - uploaderChanged equals (left.uploaded_by !== right.uploaded_by)
    - changeReasonChanged equals (left.change_reason !== right.change_reason)

  - [x] 1.8 Write property test: file validation rejects invalid sizes (Property 7)
    - **Property 7: File validation rejects invalid sizes**
    - **Validates: Requirements 7.1**
    - Files with size ≤ 0 or > 524,288,000 return { valid: false }
    - Files with 0 < size ≤ 524,288,000 return { valid: true }

  - [x] 1.9 Write property test: change reason validation enforces length bounds (Property 8)
    - **Property 8: Change reason validation enforces length bounds**
    - **Validates: Requirements 7.2**
    - Valid iff reason.trim().length >= 1 AND reason.trim().length <= 2000

- [x] 2. Extend the document store with version state
  - [x] 2.1 Add version slice to `src/frontend/src/stores/documentStore.ts`
    - Add state fields: `selectedVersion`, `isVersionLoading`, `versionError`, `downloadingVersionId`, `comparisonOpen`
    - Implement `fetchVersion` action that calls GET `/api/documents/{uuid}/versions/{major}/{minor}` with loading/error state management and 404 handling
    - Implement `selectVersionFromCache` action to set selectedVersion from existing data
    - Implement `clearSelectedVersion` action
    - Implement `downloadVersion` action with 30-second AbortController timeout, blob download via storage_key, and filename formatted as `{title}_v{major}.{minor}`
    - Implement `setComparisonOpen` action
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 6.2, 6.4, 6.5, 6.6_

  - [x] 2.2 Write unit tests for store version actions
    - Create test file `src/frontend/src/__tests__/versioning/documentStore.version.test.ts`
    - Mock `apiClient` and verify state transitions for `fetchVersion` (success, 404, error)
    - Verify `downloadVersion` creates blob URL and triggers download
    - Verify `clearSelectedVersion` resets state
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement version history and status components
  - [x] 4.1 Create `src/frontend/src/components/documents/VersionStatusBadge.tsx`
    - Render "Current" badge with `bg-primary/15 text-primary` and aria-label="Current version"
    - Render "Previous" badge with `bg-muted text-muted-foreground` and aria-label="Previous version"
    - Accept `isCurrent: boolean` prop
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 4.2 Create `src/frontend/src/components/documents/VersionHistoryPanel.tsx`
    - Accept props: versions, documentTitle, onSelectVersion, onDownload, onCompare
    - Sort versions descending using `sortVersionsDescending`
    - Render vertical timeline with left border + dot indicators
    - Display version number, locale-formatted date, uploader ID, truncated change reason (120 chars), truncated file hash (12 chars)
    - Show VersionStatusBadge per entry
    - Show download button per entry with loading state from store's `downloadingVersionId`
    - Disable "Compare Versions" button when fewer than 2 versions
    - Show empty state when no versions
    - Display "No reason provided" for null change_reason
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 4.6, 5.6, 6.1_

  - [x] 4.3 Write unit tests for VersionHistoryPanel and VersionStatusBadge
    - Create test file `src/frontend/src/__tests__/versioning/VersionHistoryPanel.test.tsx`
    - Test correct number of entries rendered
    - Test empty state display
    - Test disabled compare button with < 2 versions
    - Test VersionStatusBadge aria labels and styling
    - _Requirements: 1.4, 2.3, 2.5, 5.6_

- [x] 5. Implement version detail view
  - [x] 5.1 Create `src/frontend/src/components/documents/VersionDetailView.tsx`
    - Accept props: version, isLoading, error, onRetry, onDownload, onClose
    - Display all metadata fields: version number, storage key, full file hash (monospace), uploaded by, uploaded at (locale), change reason
    - Copy-to-clipboard button for file hash with 3-second confirmation
    - Download button
    - Loading state with spinner
    - Error state with retry button
    - "No reason provided" placeholder for null change_reason
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 6.3_

  - [x] 5.2 Write unit tests for VersionDetailView
    - Create test file `src/frontend/src/__tests__/versioning/VersionDetailView.test.tsx`
    - Test loading, error, and success states
    - Test copy button behavior
    - Test null change_reason placeholder
    - _Requirements: 3.2, 3.4, 3.5_

- [x] 6. Implement comparison and diff components
  - [x] 6.1 Create `src/frontend/src/components/documents/DiffMetadataView.tsx`
    - Accept props: left (DocumentVersion), right (DocumentVersion)
    - Show whether file hash changed with "file content unchanged" notice if identical
    - Show time elapsed between uploads using `computeTimeDelta` and `formatTimeDelta`
    - Show whether uploader changed
    - Highlight changed fields with `bg-amber-50 dark:bg-amber-950/20`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 6.2 Create `src/frontend/src/components/documents/VersionComparisonView.tsx`
    - Portal-based dialog following same pattern as VersionUploadDialog
    - Accept props: open, onOpenChange, versions
    - Two dropdown selectors for left/right version
    - Default to two most recent versions (second-most-recent left, most-recent right)
    - Side-by-side metadata grid with row alignment
    - Highlight differing fields with distinct background color
    - Show notice when same version selected on both sides
    - Embed DiffMetadataView for summary
    - Focus trap and Escape key handling
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 6.3 Write unit tests for VersionComparisonView and DiffMetadataView
    - Create test file `src/frontend/src/__tests__/versioning/VersionComparisonView.test.tsx`
    - Test default version selection
    - Test same-version notice
    - Test field highlighting for differing values
    - Test "file content unchanged" notice
    - _Requirements: 4.5, 5.2, 5.4, 5.5_

- [x] 7. Enhance VersionUploadDialog
  - [x] 7.1 Update `src/frontend/src/components/documents/VersionUploadDialog.tsx` with enhanced validation
    - Add file size validation using `validateFileSize` (> 0 bytes AND ≤ 500 MB)
    - Add change reason length validation using `validateChangeReason` (trimmed 1–2000 chars)
    - Display selected file name + formatted size using `formatFileSize` (KB < 1MB, MB ≥ 1MB with 1 decimal)
    - Keep existing drag-and-drop, version type validation, and error display
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 7.2 Write unit tests for enhanced VersionUploadDialog validation
    - Create test file `src/frontend/src/__tests__/versioning/VersionUploadDialog.test.tsx`
    - Test file size validation error messages
    - Test change reason length validation
    - Test file size display formatting
    - _Requirements: 7.1, 7.2, 7.3_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Integrate components into DocumentDetail and wire everything together
  - [x] 9.1 Update `src/frontend/src/components/documents/DocumentDetail.tsx` to integrate versioning UI
    - Replace the existing inline version list with VersionHistoryPanel
    - Add VersionDetailView below the history panel (shown when selectedVersion is set)
    - Add VersionComparisonView (portal dialog, controlled by comparisonOpen state)
    - Wire onSelectVersion to store's fetchVersion action
    - Wire onDownload to store's downloadVersion action
    - Wire onCompare to store's setComparisonOpen action
    - Wire onClose/onRetry in VersionDetailView to clearSelectedVersion/fetchVersion
    - Ensure version status badges update after new version upload (requirement 2.4)
    - _Requirements: 1.1, 2.4, 3.1, 5.1, 6.1, 6.3_

  - [x] 9.2 Update `src/frontend/src/components/documents/index.ts` barrel exports
    - Export VersionHistoryPanel, VersionDetailView, VersionComparisonView, DiffMetadataView, VersionStatusBadge
    - _Requirements: (structural)_

  - [x] 9.3 Write integration tests for the full versioning flow
    - Create test file `src/frontend/src/__tests__/versioning/integration.test.tsx`
    - Test: select document → view history → click version → see detail → download
    - Test: open comparison → change selectors → verify diff highlights
    - Test: upload new version → history refreshes → status badges update
    - _Requirements: 1.1, 2.4, 3.1, 5.1, 6.1_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (8 properties total)
- Unit tests validate specific examples and edge cases
- The backend is already complete — no API changes needed
- All new components go in `src/frontend/src/components/documents/`
- All test files go in `src/frontend/src/__tests__/versioning/`
- Pure utility functions go in `src/frontend/src/lib/versionUtils.ts`
- No new dependencies are required — fast-check v4.7.0 is already installed
- Backend API endpoints confirmed: GET `/api/documents/{uuid}/versions/{major}/{minor}` and POST `/api/documents/{uuid}/versions` (multipart, X-Change-Reason required)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "2.1"] },
    { "id": 2, "tasks": ["2.2", "4.1", "7.1"] },
    { "id": 3, "tasks": ["4.2", "5.1", "6.1", "7.2"] },
    { "id": 4, "tasks": ["4.3", "5.2", "6.2"] },
    { "id": 5, "tasks": ["6.3", "9.1"] },
    { "id": 6, "tasks": ["9.2", "9.3"] }
  ]
}
```
