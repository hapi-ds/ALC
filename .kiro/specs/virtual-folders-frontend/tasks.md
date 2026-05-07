# Implementation Plan: Virtual Folders Frontend

## Overview

This plan implements the frontend integration for virtual folders, connecting the existing static page to the live FastAPI backend. The implementation follows an incremental approach: types and utilities first, then the store, then components, then wiring and integration. Property-based tests validate correctness properties from the design document using fast-check.

## Tasks

- [ ] 1. Define TypeScript types and pure utility functions
  - [ ] 1.1 Create virtual folder TypeScript types
    - Create `src/frontend/src/types/virtualFolder.ts`
    - Define `TagFilter`, `VirtualFolderResponse`, `VirtualFolderCreate`, `VirtualFolderUpdate` interfaces
    - _Requirements: 9.1, 9.2_

  - [ ] 1.2 Implement pure utility functions
    - Create `src/frontend/src/lib/virtualFolderUtils.ts`
    - Implement `formatTagFilter(filter: TagFilter): string` — converts tag_filter to display text
    - Implement `validateFolderName(name: string): { valid: boolean; error?: string }` — validates 1–200 chars, rejects whitespace-only
    - Implement `computeFolderDiff(original, edited): VirtualFolderUpdate` — returns only changed fields
    - Implement `buildTagFilter(selectedTags: string[], selectedStatus: string | null): TagFilter` — constructs TagFilter from selections
    - _Requirements: 1.3, 2.2, 3.2, 3.5, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 1.3 Write property test for formatTagFilter (Property 1)
    - **Property 1: Tag filter display text derivation**
    - **Validates: Requirements 1.3**
    - Create `src/frontend/src/__tests__/virtual-folders/formatTagFilter.property.test.ts`
    - Generate random TagFilter objects with 0–20 tags and optional status
    - Assert: result contains every tag name and status when present; returns "No filter" only when both absent

  - [ ]* 1.4 Write property test for validateFolderName (Property 2)
    - **Property 2: Folder name validation rejects whitespace-only input**
    - **Validates: Requirements 2.2, 3.2**
    - Create `src/frontend/src/__tests__/virtual-folders/validateFolderName.property.test.ts`
    - Generate random whitespace-only strings → assert rejected
    - Generate random 1–200 char strings with at least one non-whitespace → assert accepted

  - [ ]* 1.5 Write property test for computeFolderDiff (Property 3)
    - **Property 3: Update payload contains only changed fields**
    - **Validates: Requirements 3.5**
    - Create `src/frontend/src/__tests__/virtual-folders/computeFolderDiff.property.test.ts`
    - Generate random original folder + random edits
    - Assert: diff contains only fields that differ; empty object when nothing changed

  - [ ]* 1.6 Write property test for buildTagFilter (Property 7)
    - **Property 7: Filter builder produces correct TagFilter structure**
    - **Validates: Requirements 8.3, 8.4, 8.5, 8.6, 8.9**
    - Create `src/frontend/src/__tests__/virtual-folders/buildTagFilter.property.test.ts`
    - Generate random tag arrays (0–20) + optional status from valid set
    - Assert: tags field present iff non-empty array; status field present iff non-null; empty object when neither

- [ ] 2. Extend apiClient and create virtualFolderStore
  - [ ] 2.1 Extend apiClient with changeReason support
    - Add `changeReason?: string` to `ApiClientOptions` interface in `src/frontend/src/lib/apiClient.ts`
    - Update `buildHeaders` to add `X-Change-Reason` header when `options.changeReason` is provided and method is not GET
    - Ensure backward compatibility — existing callers unaffected
    - _Requirements: 9.7_

  - [ ] 2.2 Create virtualFolderStore
    - Create `src/frontend/src/stores/virtualFolderStore.ts`
    - Follow the existing `documentStore` pattern using Zustand `create`
    - Implement state: `folders`, `selectedFolder`, `selectedFolderDocuments`, `documentsOffset`, `documentsLimit`, `isFoldersLoading`, `foldersError`, `isDocumentsLoading`, `documentsError`, `lastFetchedAt`
    - Implement actions: `fetchFolders` (with 15s AbortController timeout), `createFolder`, `updateFolder`, `deleteFolder`, `fetchFolderDocuments`, `selectFolder`, `nextDocumentsPage`, `prevDocumentsPage`
    - All mutating actions include `changeReason` in apiClient options
    - On mutation success, auto-call `fetchFolders` to refresh
    - On error, set corresponding error property and loading to false
    - API paths: `GET /api/virtual-folders`, `POST /api/virtual-folders`, `PUT /api/virtual-folders/{id}`, `DELETE /api/virtual-folders/{id}`, `GET /api/virtual-folders/{id}/documents?offset=N&limit=M`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 1.7, 7.1, 7.2, 7.3_

  - [ ]* 2.3 Write property test for pagination offset calculation (Property 6)
    - **Property 6: Pagination offset calculation**
    - **Validates: Requirements 7.2, 7.3**
    - Create `src/frontend/src/__tests__/virtual-folders/pagination.property.test.ts`
    - Generate random offset (0–1000) and limit (1–100)
    - Assert: nextDocumentsPage produces offset + limit; prevDocumentsPage produces max(0, offset - limit)

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement FilterBuilder and dialog components
  - [ ] 4.1 Implement FilterBuilder component
    - Create `src/frontend/src/components/virtual-folders/FilterBuilder.tsx`
    - Render multi-select for tags (SOP, Protocol, Report, General, Policy, Form)
    - Render dropdown for status (Draft, Active, Approved, InTraining, Retired)
    - Display live JSON preview of resulting TagFilter
    - Call `onChange` prop whenever selection changes
    - Use `buildTagFilter` utility for constructing the filter
    - Disable confirmation action when filter is empty
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_

  - [ ] 4.2 Implement CreateFolderDialog component
    - Create `src/frontend/src/components/virtual-folders/CreateFolderDialog.tsx`
    - Modal with name input (validated via `validateFolderName`), FilterBuilder, sort order dropdown
    - Sort order options: "created_at_desc" (default), "created_at_asc", "name_asc", "name_desc"
    - Disable submit until name is valid and filter is non-empty
    - Show loading indicator while request in progress
    - Handle 400 duplicate name error with inline validation message
    - Handle network/server errors with generic error message, preserve user data
    - On success: close dialog, store refreshes folder list
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [ ] 4.3 Implement EditFolderDialog component
    - Create `src/frontend/src/components/virtual-folders/EditFolderDialog.tsx`
    - Modal pre-populated with current folder name, tag_filter, sort_order
    - Use `validateFolderName` for name validation
    - Use `computeFolderDiff` to send only changed fields on submit
    - Handle 400 duplicate name error, network errors
    - Show loading indicator while request in progress
    - Cancel closes without sending request
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

  - [ ] 4.4 Implement DeleteConfirmDialog component
    - Create `src/frontend/src/components/virtual-folders/DeleteConfirmDialog.tsx`
    - Confirmation modal with text input for change reason
    - Disable confirm button while request in progress, show loading indicator
    - Pass user-entered change reason to store's `deleteFolder` action
    - Handle 404 (folder not found) and 400 (system default) errors
    - Cancel closes dialog without action
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [ ] 5. Implement folder list and document view components
  - [ ] 5.1 Implement FolderListItem component
    - Create `src/frontend/src/components/virtual-folders/FolderListItem.tsx`
    - Display folder name, filter summary (via `formatTagFilter`), "System" badge for system defaults
    - Use distinct icon for system default vs user-created folders
    - Show edit/delete action menu only for non-system-default folders
    - _Requirements: 1.3, 1.4, 5.1, 5.2, 5.3, 5.4_

  - [ ]* 5.2 Write property test for system default folder protection (Property 4)
    - **Property 4: System default folder protection in rendering**
    - **Validates: Requirements 4.8, 5.1, 5.2, 5.3**
    - Create `src/frontend/src/__tests__/virtual-folders/folderListItem.property.test.ts`
    - Generate random VirtualFolderResponse with `is_system_default: true`
    - Assert: rendered output shows "System" badge AND does NOT render edit/delete controls

  - [ ] 5.3 Implement FolderListView component
    - Create `src/frontend/src/components/virtual-folders/FolderListView.tsx`
    - Render header with "Create Folder" button
    - Render folder list using FolderListItem components
    - Handle loading state (loading indicator), error state (error message + retry button), empty state
    - System default folders displayed before user-created folders (API sort order preserved)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ] 5.4 Implement FolderDocumentRow component
    - Create `src/frontend/src/components/virtual-folders/FolderDocumentRow.tsx`
    - Display document_uuid, title, document_type, current_status, tag names, created_at
    - _Requirements: 6.3_

  - [ ]* 5.5 Write property test for document row rendering (Property 5)
    - **Property 5: Document row renders all required fields**
    - **Validates: Requirements 6.3**
    - Create `src/frontend/src/__tests__/virtual-folders/folderDocumentRow.property.test.ts`
    - Generate random DocumentResponse objects
    - Assert: rendered output contains title, document_type, current_status, tag names, created_at

  - [ ] 5.6 Implement FolderPagination component
    - Create `src/frontend/src/components/virtual-folders/FolderPagination.tsx`
    - Prev/next buttons calling store's `prevDocumentsPage`/`nextDocumentsPage`
    - Disable prev when offset is 0
    - Disable next when returned documents count < limit
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

  - [ ] 5.7 Implement FolderDocumentView component
    - Create `src/frontend/src/components/virtual-folders/FolderDocumentView.tsx`
    - Display folder name as heading with back navigation link
    - Render document rows using FolderDocumentRow
    - Include FolderPagination component
    - Handle loading, error, and empty states
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Wire VirtualFoldersPage and route configuration
  - [ ] 7.1 Update route configuration in App.tsx
    - Add `<Route path="folders/:folderId" element={<VirtualFoldersPage />} />` alongside existing `/folders` route
    - _Requirements: 10.2, 10.5_

  - [ ] 7.2 Rewrite VirtualFoldersPage to integrate all components
    - Update `src/frontend/src/pages/VirtualFoldersPage.tsx`
    - Read `folderId` from `useParams()` — if present, render FolderDocumentView; if absent, render FolderListView
    - On mount: call `fetchFolders()` from store (with 300s cache staleness check)
    - Wire CreateFolderDialog, EditFolderDialog, DeleteConfirmDialog with open/close state
    - Handle folder click → navigate to `/folders/:folderId`
    - Handle back navigation → return to folder list with cached data
    - Handle invalid folderId in URL → show folder list with error message
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 1.1, 6.1_

  - [ ] 7.3 Create barrel export for virtual-folders components
    - Create `src/frontend/src/components/virtual-folders/index.ts`
    - Export all virtual folder components for clean imports
    - _Requirements: N/A (code organization)_

- [ ] 8. Store integration tests
  - [ ]* 8.1 Write property test for mutating actions refresh (Property 8)
    - **Property 8: Mutating store actions refresh folder list on success**
    - **Validates: Requirements 9.5**
    - Create `src/frontend/src/__tests__/virtual-folders/storeRefresh.property.test.ts`
    - Mock API success for createFolder, updateFolder, deleteFolder
    - Assert: fetchFolders is called after each successful mutation

  - [ ]* 8.2 Write property test for failed actions error handling (Property 9)
    - **Property 9: Failed store actions set error and clear loading**
    - **Validates: Requirements 9.6**
    - Create `src/frontend/src/__tests__/virtual-folders/storeErrors.property.test.ts`
    - Mock API errors for each store action
    - Assert: corresponding error property is set to non-empty string, loading property is false

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend is already complete — this is frontend-only implementation
- All mutating API calls must include the `X-Change-Reason` header for ALCOA+ audit compliance
- The existing `documentStore` pattern should be followed for the new `virtualFolderStore`
- Test files go in `src/frontend/src/__tests__/virtual-folders/`
- API base path is `/api/virtual-folders` (NOT `/api/v1/virtual-folders`)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "1.5", "1.6", "2.2"] },
    { "id": 3, "tasks": ["2.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "5.1", "5.4", "5.6"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.5", "5.7"] },
    { "id": 6, "tasks": ["7.1", "7.3"] },
    { "id": 7, "tasks": ["7.2"] },
    { "id": 8, "tasks": ["8.1", "8.2"] }
  ]
}
```
