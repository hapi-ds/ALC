# Implementation Plan: Template Builder Frontend

## Overview

This plan implements a JSON-driven visual form builder with @hello-pangea/dnd drag-and-drop, Zustand state management, and a two-route architecture (`/templates` list and `/templates/new` builder). The implementation proceeds bottom-up: types → stores → components → routing → integration tests, ensuring each step builds on the previous with no orphaned code.

## Tasks

- [x] 1. Define TypeScript interfaces and types
  - [x] 1.1 Create template type definitions
    - Create `src/frontend/src/types/template.ts` with `FieldType`, `CanvasFieldData`, `TemplateCreatePayload`, `TemplateResponse`, and `TemplateFieldResponse` interfaces as specified in the design
    - Export all types for use across stores and components
    - _Requirements: 9.1, 2.1_

- [x] 2. Implement templateBuilderStore with core logic
  - [x] 2.1 Create templateBuilderStore with field management actions
    - Create `src/frontend/src/stores/templateBuilderStore.ts` with the full state interface
    - Implement `addField` action: generates UUID v4 id, sets default label as `"{Type} Field"`, assigns fieldOrder at drop index, shifts existing fields, enforces 50-field max
    - Implement `removeField` action: removes field by id, recalculates contiguous fieldOrder (0, 1, 2, ..., n-1)
    - Implement `reorderField` action: moves field from sourceIndex to destinationIndex, recalculates all fieldOrder values to maintain contiguous sequence
    - Implement `selectField` action: sets selectedFieldId, preserves selection across reorder
    - Implement `updateFieldLabel` and `updateFieldType` actions: update field properties in-place
    - Implement `setTemplateName` action with validation
    - Implement `isDirty` tracking: set true on any mutation, reset on `markClean`
    - Implement `canSave` derived logic: name valid, fields.length > 0, no empty labels, not saving
    - _Requirements: 2.1, 2.2, 3.1, 3.5, 3.6, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 6.2, 11.1, 11.6_

  - [x] 2.2 Write property test for field-order contiguous invariant
    - **Property 1: Field-order contiguous invariant**
    - Test that after any sequence of add/remove/reorder operations, fieldOrder values always form 0..n-1
    - **Validates: Requirements 2.2, 3.1, 5.2**

  - [x] 2.3 Write property test for add field correctness
    - **Property 2: Add field produces correct Canvas_Field**
    - Test that addField produces correct type, default label "{Type} Field", UUID v4 id, and fieldOrder at drop index
    - **Validates: Requirements 2.1**

  - [x] 2.4 Write property test for reorder idempotency
    - **Property 3: Reorder to same position is idempotent**
    - Test that reordering from index i to index i leaves all fieldOrder values and field identities unchanged
    - **Validates: Requirements 3.5**

  - [x] 2.5 Write property test for selection preserved across reorder
    - **Property 4: Selection preserved across reorder**
    - Test that selectedFieldId remains unchanged after any valid reorder operation
    - **Validates: Requirements 3.6**

  - [x] 2.6 Write property test for field property update propagation
    - **Property 5: Field property update propagation**
    - Test that updateFieldLabel/updateFieldType correctly updates the field and reading it back returns the new value
    - **Validates: Requirements 4.3, 4.4**

  - [x] 2.7 Write property test for field label validation
    - **Property 6: Field label validation**
    - Test that empty strings return error, strings > 200 chars return error, all others return no error
    - **Validates: Requirements 4.5**

  - [x] 2.8 Write property test for template name validation
    - **Property 7: Template name validation**
    - Test that empty/whitespace-only strings return error, strings > 500 chars return error, all others return no error
    - **Validates: Requirements 6.2**

  - [x] 2.9 Write property test for remove field correctness
    - **Property 8: Remove field correctness**
    - Test that removing a field decreases list length by 1 and the removed id no longer appears
    - **Validates: Requirements 5.1**

  - [x] 2.10 Write property test for selection consistency on removal
    - **Property 9: Selection consistency on removal**
    - Test that removing the selected field clears selection; removing a non-selected field preserves selection
    - **Validates: Requirements 5.3, 5.4**

  - [x] 2.11 Write property test for dirty state tracking
    - **Property 13: Dirty state tracking**
    - Test that any mutation sets isDirty to true, and markClean sets it to false
    - **Validates: Requirements 11.1, 11.6**

- [x] 3. Implement serialization and save logic
  - [x] 3.1 Add saveTemplate and serialization to templateBuilderStore
    - Implement `serializeTemplate` helper that transforms CanvasFieldData[] into TemplateCreatePayload format: sorts by fieldOrder ascending, maps to {label, type} only, excludes id/field_uuid/field_order
    - Implement `saveTemplate` async action: validates canSave, sets isSaving, calls `apiClient.post("/api/templates", payload, { changeReason: "Template created via builder" })`, handles 201 success (stores response, sets ReadOnly status, calls markClean), handles 400 (extracts detail from response body), handles network/other errors
    - Implement `resetBuilder` action to clear all state
    - Backend endpoint: `POST /api/templates` (prefix `/api` + router prefix `/templates` + path `""`) returns 201 with `TemplateResponse`
    - Required header: `X-Change-Reason: "Template created via builder"` (enforced by AuditMiddleware)
    - Request body format: `{ name: string, json_schema: { fields: [{ label, type }] }, user_id: number }`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 9.1, 9.2, 9.4, 9.5_

  - [x] 3.2 Write property test for serialization correctness
    - **Property 10: Serialization correctness**
    - Test that serializeTemplate produces correct name, fields ordered by fieldOrder, only label+type per entry, correct array length
    - **Validates: Requirements 7.1, 9.1, 9.2, 9.4**

  - [x] 3.3 Write property test for serialization round-trip
    - **Property 11: Serialization round-trip preserves field data**
    - Test that serializing and mapping back preserves each field's label and type in the same order
    - **Validates: Requirements 9.3**

  - [x] 3.4 Write property test for submission guard
    - **Property 12: Submission guard**
    - Test that canSave is false when fields empty, any label empty, or name empty/whitespace-only
    - **Validates: Requirements 9.5**

- [x] 4. Implement templateListStore
  - [x] 4.1 Create templateListStore with fetch logic
    - Create `src/frontend/src/stores/templateListStore.ts` with `templates`, `isLoading`, `error` state
    - Implement `fetchTemplates` action: calls `apiClient.get("/api/templates")`, handles success, error, and 30-second timeout via AbortController
    - Backend endpoint: `GET /api/templates` (prefix `/api` + router prefix `/templates` + path `""`) returns `list[TemplateResponse]`
    - Required headers: Authorization, X-User-Id, X-Company-Id (handled automatically by apiClient)
    - _Requirements: 8.1, 8.5, 8.6_

- [x] 5. Checkpoint - Verify stores and types
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement builder UI components
  - [x] 6.1 Create FieldPalette component
    - Create `src/frontend/src/components/templates/FieldPalette.tsx`
    - Render 5 draggable items (Text, Float, Integer, Date, Boolean) inside a `Droppable` with `isDropDisabled={true}`
    - Each item uses `draggableId` format `palette-{Type}` and is keyboard-focusable via Tab in visual order
    - Display drag handle icon on each item
    - _Requirements: 1.2, 2.4, 10.1_

  - [x] 6.2 Create CanvasField component
    - Create `src/frontend/src/components/templates/CanvasField.tsx`
    - Render a `Draggable` item showing label, type badge, drag handle, and remove button
    - Accept props: `field: CanvasFieldData`, `index: number`, `isSelected: boolean`
    - Apply selection highlight (distinct border/background) when `isSelected` is true
    - Apply keyboard focus indicator with minimum 3:1 contrast ratio and 2px thickness
    - Remove button accessible via keyboard (Enter or Delete key on the remove control)
    - _Requirements: 3.3, 4.1, 5.1, 10.2, 10.4, 10.6_

  - [x] 6.3 Create BuilderCanvas component
    - Create `src/frontend/src/components/templates/BuilderCanvas.tsx`
    - Render a `Droppable` zone with id `builder-canvas`
    - When fields array is empty, display drop zone placeholder message
    - Render CanvasField items in ascending fieldOrder sequence
    - Show visual placeholder at target drop position during drag
    - _Requirements: 1.3, 2.3, 3.2, 3.4, 5.5_

  - [x] 6.4 Create ConfigurationPanel component
    - Create `src/frontend/src/components/templates/ConfigurationPanel.tsx`
    - When no field selected, display empty state message
    - When field selected, display editable label text input and type dropdown (Text, Float, Integer, Date, Boolean)
    - Label input validates on each change: show error if empty or > 200 chars
    - Type dropdown updates store on change
    - Form inputs reachable via keyboard Tab navigation
    - _Requirements: 1.4, 1.6, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 10.3_

  - [x] 6.5 Create TemplateNameInput component
    - Create `src/frontend/src/components/templates/TemplateNameInput.tsx`
    - Controlled text input for template name, reads/writes from templateBuilderStore
    - Inline validation: error if empty, whitespace-only, or > 500 chars
    - Display validation error adjacent to input field
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 6.6 Create SaveButton component
    - Create `src/frontend/src/components/templates/SaveButton.tsx`
    - Disabled when `canSave` is false or `isSaving` is true
    - Shows loading indicator while save is in progress
    - Triggers `saveTemplate` action on click
    - Displays validation messages for zero fields or blank name
    - _Requirements: 7.3, 7.7, 7.8, 7.9_

  - [x] 6.7 Create TemplateBuilder orchestrator component
    - Create `src/frontend/src/components/templates/TemplateBuilder.tsx`
    - Wraps children in `DragDropContext` with `onDragEnd` handler
    - `onDragEnd` distinguishes palette→canvas (addField) vs canvas→canvas (reorderField)
    - Renders three-panel layout: FieldPalette (left), BuilderCanvas (center), ConfigurationPanel (right)
    - Renders TemplateNameInput above canvas and SaveButton below
    - Displays success notification (auto-dismiss 5s) and error notifications
    - Enforces 50-field max with validation message
    - Maintains logical tab order: name input → palette → canvas → config panel → save button
    - _Requirements: 1.1, 1.5, 2.1, 2.5, 2.6, 7.4, 7.5, 7.6, 10.5, 10.7, 10.8_

  - [x] 6.8 Create UnsavedChangesDialog component
    - Create `src/frontend/src/components/templates/UnsavedChangesDialog.tsx`
    - Modal dialog with confirm and cancel options
    - Props: `open: boolean`, `onConfirm: () => void`, `onCancel: () => void`
    - Accessible: focus trapped in dialog, keyboard operable
    - _Requirements: 11.2, 11.4, 11.5_

- [x] 7. Checkpoint - Verify component rendering
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement pages and routing
  - [x] 8.1 Create TemplateBuilderPage with navigation guards
    - Create `src/frontend/src/pages/TemplateBuilderPage.tsx`
    - Wraps `TemplateBuilder` component
    - Implements `beforeunload` listener when isDirty is true
    - Integrates with react-router-dom navigation blocking (useBlocker or equivalent) to show UnsavedChangesDialog on in-app navigation
    - _Requirements: 11.2, 11.3, 11.4, 11.5_

  - [x] 8.2 Create TemplateListPage component
    - Create `src/frontend/src/pages/TemplateListPage.tsx`
    - Calls `fetchTemplates` on mount via templateListStore
    - Shows loading indicator within 200ms of fetch initiation
    - Renders template list items showing Document_UUID, name, status, and field count, ordered by Document_UUID descending
    - Shows empty state message when no templates exist
    - Shows error message on API error (4xx/5xx)
    - Shows timeout error message if no response within 30 seconds
    - "New Template" button navigates to `/templates/new`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 8.3 Update App.tsx routing for template routes
    - Replace single `/templates` route with nested routes: `/templates` → TemplateListPage, `/templates/new` → TemplateBuilderPage
    - Add imports for new page components
    - Update `src/frontend/src/pages/index.ts` exports
    - _Requirements: 8.7_

- [x] 9. Checkpoint - Verify full integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Write unit and integration tests
  - [x] 10.1 Write unit tests for TemplateBuilder and DnD interactions
    - Create `src/frontend/src/__tests__/templates/TemplateBuilder.test.tsx`
    - Test three-panel rendering, onDragEnd handler logic (palette→canvas, canvas→canvas, drop outside)
    - Test 50-field max validation message display
    - Test success/error notification display and auto-dismiss
    - _Requirements: 1.1, 1.5, 2.1, 2.5, 2.6, 7.4, 7.5, 7.6_

  - [x] 10.2 Write unit tests for FieldPalette
    - Create `src/frontend/src/__tests__/templates/FieldPalette.test.tsx`
    - Test renders 5 field type items, items remain after drag, keyboard focusable
    - _Requirements: 1.2, 2.4, 10.1_

  - [x] 10.3 Write unit tests for BuilderCanvas and ConfigurationPanel
    - Create `src/frontend/src/__tests__/templates/BuilderCanvas.test.tsx`
    - Create `src/frontend/src/__tests__/templates/ConfigurationPanel.test.tsx`
    - Test empty placeholder, field rendering in order, selection highlight, label/type editing, validation errors
    - _Requirements: 1.3, 1.4, 3.2, 4.1, 4.2, 4.5, 4.6, 4.7, 5.5_

  - [x] 10.4 Write unit tests for TemplateListPage
    - Create `src/frontend/src/__tests__/templates/TemplateListPage.test.tsx`
    - Test loading state, successful list rendering (document_uuid, name, status, field count), empty state, error state, timeout, navigation to builder
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 10.5 Write integration tests for full builder flow
    - Create `src/frontend/src/__tests__/templates/TemplateBuilderIntegration.test.tsx`
    - Test full flow: add fields → configure labels/types → set name → save → verify API call with correct payload format, URL `/api/templates`, and `X-Change-Reason` header
    - Test 400 error handling with detail parsing, network error display
    - Test unsaved changes dialog: dirty state → navigate → dialog → confirm/cancel
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 9.1, 9.2, 9.4, 11.2, 11.4, 11.5_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design's 13 correctness properties
- Unit tests validate specific examples and edge cases
- The existing `templateStore.ts` will be superseded by the new `templateBuilderStore.ts` and `templateListStore.ts`
- The existing placeholder `TemplatesPage.tsx` will be replaced by `TemplateListPage.tsx`
- All API calls use the existing `apiClient.ts` which handles auth headers (Authorization, X-User-Id, X-Company-Id) and token refresh automatically
- The `X-Change-Reason` header is required for `POST /api/templates` per AuditMiddleware
- Backend endpoints verified: `POST ""` on `/api/templates` router (status 201), `GET ""` on `/api/templates` router (returns list)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.4", "6.5", "6.6", "6.8"] },
    { "id": 5, "tasks": ["6.3", "6.7"] },
    { "id": 6, "tasks": ["8.1", "8.2"] },
    { "id": 7, "tasks": ["8.3"] },
    { "id": 8, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5"] }
  ]
}
```
