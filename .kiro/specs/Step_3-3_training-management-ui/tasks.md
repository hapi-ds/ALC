# Implementation Plan: Training Management UI

## Overview

This plan implements the Training Management UI for AlcoaBase, replacing the placeholder `TrainingPage.tsx` with a fully functional training dashboard. The implementation follows an incremental approach: first establishing the Zustand store and pure utility functions, then building components bottom-up (cards → lists → page), and finally wiring in the Training Gate Guard and Document Detail integration.

All code is TypeScript/React using Zustand, Tailwind CSS, Lucide icons, and the existing `apiClient` for API calls.

## Tasks

- [ ] 1. Create TypeScript types and pure utility functions
  - [ ] 1.1 Create training type definitions and utility functions
    - Create `src/frontend/src/components/training/types.ts` with interfaces: `TrainingTask`, `TrainingStatus`, `TrainingContent`, `QuizQuestion`, `ProceduralStep`, `TaskFilter`, `TrainingStatistics`, `GateCache`
    - Create `src/frontend/src/components/training/utils.ts` with pure functions: `computeStatistics`, `truncateTitle`, `filterTasks`, `sortTasks`, `validateInputLength`, `deriveContentId`, `shouldRenderSection`, `shuffleAnswerOptions`, `determineRecordValidity`, `sortRecords`, `groupRecordsBySop`, `deriveUniqueSopPairs`, `shouldEnforceGate`, `checkGateFromTasks`, `extractErrorMessage`, `formatAriaLabel`
    - _Requirements: 1.1, 1.5, 2.1, 2.3, 2.4, 3.2, 4.1, 4.2, 4.4, 5.3, 5.4, 5.6, 6.7, 8.7, 9.5, 9.7, 11.3_

  - [ ] 1.2 Write property tests for statistics computation (Property 1)
    - **Property 1: Statistics computation is correct**
    - **Validates: Requirements 1.1, 1.5**

  - [ ] 1.3 Write property tests for title truncation (Property 2)
    - **Property 2: Title truncation preserves content within bounds**
    - **Validates: Requirements 2.1**

  - [ ] 1.4 Write property tests for client-side filtering (Property 3)
    - **Property 3: Client-side filtering returns correct subset**
    - **Validates: Requirements 2.3, 5.2**

  - [ ] 1.5 Write property tests for task sorting (Property 4)
    - **Property 4: Task sorting maintains ordering invariants**
    - **Validates: Requirements 2.4**

  - [ ] 1.6 Write property tests for bounded-length input validation (Property 5)
    - **Property 5: Bounded-length input validation**
    - **Validates: Requirements 3.2, 7.4**

  - [ ] 1.7 Write property tests for content ID derivation (Property 6)
    - **Property 6: Content ID derivation is deterministic**
    - **Validates: Requirements 4.1**

  - [ ] 1.8 Write property tests for section rendering logic (Property 7)
    - **Property 7: Content sections render only when non-empty**
    - **Validates: Requirements 4.2**

  - [ ] 1.9 Write property tests for quiz answer options (Property 8)
    - **Property 8: Quiz answer options preserve the complete answer set**
    - **Validates: Requirements 4.4**

  - [ ] 1.10 Write property tests for record validity determination (Property 9)
    - **Property 9: Training record validity determination**
    - **Validates: Requirements 5.3**

  - [ ] 1.11 Write property tests for records sorting (Property 10)
    - **Property 10: Records sorting maintains order for each sort key**
    - **Validates: Requirements 5.4**

  - [ ] 1.12 Write property tests for records grouping (Property 11)
    - **Property 11: Records grouping produces correct partitions**
    - **Validates: Requirements 5.6**

  - [ ] 1.13 Write property tests for SOP selector uniqueness (Property 12)
    - **Property 12: SOP selector contains unique pairs**
    - **Validates: Requirements 6.7**

  - [ ] 1.14 Write property tests for gate enforcement scope (Property 13)
    - **Property 13: Training gate enforcement scope**
    - **Validates: Requirements 8.1, 8.7**

  - [ ] 1.15 Write property tests for gate check with caching (Property 14)
    - **Property 14: Training gate check with caching**
    - **Validates: Requirements 8.4, 9.5**

  - [ ] 1.16 Write property tests for gate cache invalidation (Property 15)
    - **Property 15: Gate cache invalidation on task completion**
    - **Validates: Requirements 9.4**

  - [ ] 1.17 Write property tests for error message extraction (Property 16)
    - **Property 16: Error message extraction from API errors**
    - **Validates: Requirements 9.7**

  - [ ] 1.18 Write property tests for aria-label format (Property 18)
    - **Property 18: Task card aria-label format**
    - **Validates: Requirements 11.3**

- [ ] 2. Checkpoint - Ensure all property tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Implement the Training Store (Zustand)
  - [ ] 3.1 Create the trainingStore with all state and actions
    - Create `src/frontend/src/stores/trainingStore.ts` implementing the `TrainingStoreState` interface
    - Implement `fetchTrainingTasks`, `completeTrainingTask`, `fetchTrainingContent`, `fetchTrainingStatus`, `approveContent`, `rejectContent`, `setFilter`, `checkTrainingGate`, `clearGateCache`
    - Use `apiClient.get()` and `apiClient.post()` with proper `changeReason` option for mutations
    - Implement request deduplication (check isLoading flags before initiating requests)
    - Implement `extractErrorMessage` for consistent error handling across all actions
    - Implement gate cache invalidation in `completeTrainingTask`
    - Export store from `src/frontend/src/stores/index.ts`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 12.6_

  - [ ] 3.2 Write unit tests for trainingStore actions
    - Test fetchTrainingTasks success and error paths with mocked apiClient
    - Test completeTrainingTask with success, 400 error, and network error
    - Test fetchTrainingContent with success, 404, and network error
    - Test fetchTrainingStatus success and error
    - Test approveContent and rejectContent success and error paths
    - Test request deduplication (calling fetch while isLoading is true)
    - Test gate cache behavior (cache hit, cache miss, invalidation)
    - _Requirements: 9.1–9.10, 12.6_

- [ ] 4. Implement base UI components
  - [ ] 4.1 Create TrainingStatusOverview component
    - Create `src/frontend/src/components/training/TrainingStatusOverview.tsx`
    - Render three stat cards: Pending (Clock icon), Completed (CheckCircle icon), Total Tasks (GraduationCap icon)
    - Display completion percentage below/adjacent to stat cards
    - Show skeleton placeholders when `isLoading` is true
    - Show "0" values and "N/A" percentage when total is 0
    - _Requirements: 1.1, 1.2, 1.3, 1.5_

  - [ ] 4.2 Create TrainingTaskCard component
    - Create `src/frontend/src/components/training/TrainingTaskCard.tsx`
    - Display task title (truncated at 80 chars with ellipsis), SOP UUID, version, status, completion timestamp
    - Show "Mark Complete" button for pending tasks, "Completed" badge for completed tasks
    - Implement aria-label format: "{task_title} - {status}"
    - Use role="article" with proper ARIA attributes
    - _Requirements: 2.1, 2.6, 2.7, 11.3_

  - [ ] 4.3 Create TaskCompletionDialog component
    - Create `src/frontend/src/components/training/TaskCompletionDialog.tsx`
    - Display task title, SOP UUID, version, and required change reason input (3–500 chars trimmed)
    - Show character counter for remaining characters
    - Disable confirm button until validation passes
    - Show loading indicator on confirm button during submission
    - Disable both buttons during submission
    - Display inline error messages below input on failure
    - Retain user input on error
    - Implement focus trap (Tab/Shift+Tab cycle within dialog)
    - Return focus to triggering button on close
    - Close on Escape key press
    - Use dialog role with aria-labelledby and aria-describedby
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8, 11.4, 11.5, 11.8, 11.11_

  - [ ] 4.4 Create TrainingTaskList component with filtering
    - Create `src/frontend/src/components/training/TrainingTaskList.tsx`
    - Render filter controls (All, Pending, Completed) as radio group with ARIA
    - Apply client-side filtering without additional API calls
    - Sort tasks: pending first (created_at ascending), then completed (completed_at descending)
    - Show contextual empty state messages per filter
    - Show loading skeleton when isLoading is true
    - Show error panel with retry button on error
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 11.2, 12.1_

  - [ ] 4.5 Write unit tests for TrainingStatusOverview, TrainingTaskCard, TaskCompletionDialog, TrainingTaskList
    - Test rendering in loading, error, empty, and populated states
    - Test filter interactions and sort order
    - Test dialog focus trap and keyboard navigation
    - Test accessibility attributes (ARIA roles, labels, live regions)
    - _Requirements: 1.1–1.5, 2.1–2.7, 3.1–3.8, 11.2–11.5, 11.8_

- [ ] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement Training Content Viewer
  - [ ] 6.1 Create TrainingContentViewer component
    - Create `src/frontend/src/components/training/TrainingContentViewer.tsx`
    - Derive content_id from task's sop_document_uuid and sop_version as `{uuid}_v{version}`
    - Render sections conditionally: summary, procedural steps, safety points, quiz questions
    - Render procedural steps as numbered list with safety-critical step highlighting (red/amber border, safety icon, safety_note)
    - Render quiz questions with shuffled answer options, "Reveal Answer" toggle showing correct answer and sop_section_ref
    - Render safety points as bulleted list in warning panel with alert icon
    - Show loading skeleton while fetching
    - Show "content not available" message for 404 responses
    - Show "under revision" notice for rejected content
    - Show "awaiting review" notice for pending_review/draft content
    - Show error with retry button for network/server errors
    - Support 'review' mode with approve/reject buttons for admin
    - Use fieldset/legend for quiz question groups with radio inputs
    - Implement aria-expanded on toggles
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 7.2, 7.5, 11.9, 11.12_

  - [ ] 6.2 Write unit tests for TrainingContentViewer
    - Test rendering for each content status (approved, rejected, pending_review, draft)
    - Test conditional section rendering (empty arrays omitted)
    - Test quiz answer shuffling and reveal toggle
    - Test safety-critical step highlighting
    - Test loading and error states
    - Test approve/reject button interactions in review mode
    - _Requirements: 4.1–4.11, 7.2, 7.5_

- [ ] 7. Implement Training Records Panel
  - [ ] 7.1 Create TrainingRecordsPanel component
    - Create `src/frontend/src/components/training/TrainingRecordsPanel.tsx`
    - Derive training records from completed tasks
    - Display SOP UUID, version, completion date (locale-formatted), validity badge (green=valid, red=invalidated)
    - Determine validity: most recent completed task per SOP UUID is valid, others invalidated
    - Support sorting by SOP UUID (alphabetical), completion date (newest first, default), version (descending)
    - Group records by SOP UUID with collapsible groups (most recent visible by default)
    - Show empty state message when no records
    - Show loading skeleton and error with retry
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [ ] 7.2 Write unit tests for TrainingRecordsPanel
    - Test record derivation from completed tasks
    - Test validity determination logic
    - Test sorting by each key
    - Test grouping and collapse/expand behavior
    - Test empty state and error states
    - _Requirements: 5.1–5.8_

- [ ] 8. Implement Admin Training View
  - [ ] 8.1 Create AdminTrainingView component
    - Create `src/frontend/src/components/training/AdminTrainingView.tsx`
    - Show only when user has administrator role
    - Implement SOP selector dropdown from unique (sop_document_uuid, sop_version) pairs
    - Fetch training status via `GET /api/training/status/{sop_uuid}/{version}`
    - Display total tasks, completed tasks, completion percentage, is_complete status
    - Show progress bar with percentage text
    - Show user-level breakdown table (user name/ID, status, completion timestamp)
    - Show "Training Complete" badge when is_complete is true
    - Show empty state when total_tasks is 0
    - Show loading skeleton and error with retry
    - Implement Content Review section showing pending_review items
    - Wire approve/reject actions through TrainingContentViewer in review mode
    - Handle approve/reject success (remove from queue, show notification) and errors
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 7.1, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [ ] 8.2 Write unit tests for AdminTrainingView
    - Test admin-only visibility
    - Test SOP selector population and selection
    - Test progress bar and status display
    - Test user breakdown table rendering
    - Test content review approve/reject flows
    - Test loading, error, and empty states
    - _Requirements: 6.1–6.9, 7.1–7.9_

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Assemble TrainingPage and implement route integration
  - [ ] 10.1 Replace placeholder TrainingPage with full implementation
    - Replace `src/frontend/src/pages/TrainingPage.tsx` with the full training dashboard
    - Wire TrainingStatusOverview, TrainingTaskList, TrainingContentViewer, TrainingRecordsPanel, AdminTrainingView
    - Implement tab navigation: "My Tasks", "Records", "Admin: SOP Training Status" (admin-only)
    - Fetch training tasks on mount via trainingStore
    - Handle task selection to load content viewer
    - Handle "Mark Complete" to open TaskCompletionDialog
    - Use ARIA landmark role="main" with label "Training Management"
    - Implement aria-live regions for loading state announcements
    - _Requirements: 1.1, 1.4, 2.1, 4.11, 11.1, 11.6, 12.1_

  - [ ] 10.2 Create barrel export for training components
    - Create `src/frontend/src/components/training/index.ts` exporting all training components
    - _Requirements: N/A (project structure)_

  - [ ] 10.3 Write integration tests for TrainingPage
    - Test full page render with mocked store
    - Test tab navigation between My Tasks, Records, and Admin views
    - Test task selection → content viewer flow
    - Test task completion flow end-to-end
    - _Requirements: 1.1–1.5, 2.1–2.7, 4.11_

- [ ] 11. Implement Training Gate Guard and Document Detail integration
  - [ ] 11.1 Create TrainingGateGuard component
    - Create `src/frontend/src/components/training/TrainingGateGuard.tsx`
    - Only enforce gate when SOP status is "InTraining"
    - Check training completion via trainingStore.checkTrainingGate
    - If tasks not yet loaded (hasFetchedTasks is false), trigger fetchTrainingTasks and show loading
    - Block navigation with full-page message and link to /training when training incomplete
    - Allow navigation when training is complete
    - Implement 10-second timeout showing error state with retry
    - Show loading indicator during check
    - Use role="alert" for blocking message
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 11.10_

  - [ ] 11.2 Create TrainingStatusBanner component and integrate with DocumentDetail
    - Create `src/frontend/src/components/training/TrainingStatusBanner.tsx`
    - Show amber/warning banner when training is pending: "Training required: You have not completed training for {SOP_Name} v{version}. Complete training to gain full access."
    - Show green/success banner when training is complete with completion date
    - Only display when SOP status is "InTraining"
    - Include "View Training" link to /training
    - Show skeleton while loading, error with retry on failure
    - Integrate TrainingGateGuard into document detail routes in App.tsx
    - Integrate TrainingStatusBanner into DocumentDetail page
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ] 11.3 Write unit tests for TrainingGateGuard and TrainingStatusBanner
    - Test gate pass-through for non-InTraining statuses
    - Test gate blocking for incomplete training
    - Test gate allowing for complete training
    - Test timeout behavior (10 seconds)
    - Test banner rendering for pending and completed states
    - Test banner hidden for non-InTraining documents
    - _Requirements: 8.1–8.7, 10.1–10.6_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (18 properties)
- Unit tests validate specific examples, edge cases, and component interactions
- The design uses TypeScript explicitly — no language selection needed
- All API calls use `apiClient` with proper auth/tenant headers and `changeReason` for mutations
- The existing placeholder `TrainingPage.tsx` is replaced in task 10.1
- The `src/frontend/src/components/training/` directory exists with `.gitkeep` — ready for new files
- Property tests use `fast-check` library with Vitest, placed in `src/frontend/src/__tests__/properties/training.property.test.ts`

