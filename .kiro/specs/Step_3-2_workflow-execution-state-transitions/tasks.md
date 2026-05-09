# Implementation Plan: Workflow Execution & State Transitions (Frontend)

## Overview

This plan implements the workflow execution layer for AlcoaBase documents, covering backend enhancements (Alembic migration, history endpoint, change reason capture), frontend utility functions, a Zustand execution store, three new UI components (WorkflowStatePanel, TransitionConfirmationDialog, WorkflowHistoryTimeline), and integration into the existing DocumentDetail page. Tasks are ordered so backend changes land first, followed by frontend types/utilities, store, components, integration, and tests.

## Tasks

- [ ] 1. Backend: Database migration and model changes
  - [ ] 1.1 Create Alembic migration to add `change_reason` column to `workflow_transition_audits`
    - Generate a new migration file in `src/backend/alembic/versions/` following the existing naming convention (hex prefix + descriptive slug)
    - Add `change_reason` column: `sa.Column("change_reason", sa.String(500), nullable=True)`
    - Implement `downgrade()` to drop the column
    - _Requirements: 6.4, 6.5_

  - [ ] 1.2 Add `change_reason` field to `WorkflowTransitionAudit` model in `src/backend/src/alcoabase/services/workflow_engine.py`
    - Add `change_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)`
    - _Requirements: 6.4_

  - [ ] 1.3 Modify `WorkflowEngine._record_transition_audit` to accept and normalize `change_reason`
    - Accept `change_reason: str | None = None` parameter
    - Normalize: strip whitespace, store `None` for empty/whitespace-only, truncate to 500 chars
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ] 1.4 Modify `POST /api/workflows/transition` endpoint to extract `X-Change-Reason` header and pass to engine
    - Add `request: Request` parameter to the route handler (rename existing `request: TransitionRequest` to `body: TransitionRequest`)
    - Extract `request.headers.get("x-change-reason")` from the HTTP request
    - Pass `change_reason` to `engine.request_transition()`
    - Update `WorkflowEngine.request_transition` signature to accept `change_reason: str | None = None`
    - _Requirements: 6.1_

- [ ] 2. Backend: Workflow history endpoint and schema
  - [ ] 2.1 Create `TransitionHistoryResponse` schema in `src/backend/src/alcoabase/schemas/workflow.py`
    - Define Pydantic model with fields: `id`, `document_id`, `user_id`, `previous_state`, `new_state`, `timestamp` (datetime), `change_reason` (str | None)
    - _Requirements: 5.2_

  - [ ] 2.2 Implement `GET /api/workflows/state/{document_uuid}/history` endpoint in `src/backend/src/alcoabase/api/workflows.py`
    - Query `WorkflowTransitionAudit` records for the document, ordered by timestamp descending, limit 1000
    - Scope to tenant via `X-Company-Id` header (use `get_tenant_context` dependency)
    - Return 404 if no workflow state found for the document (same pattern as `get_document_state`)
    - Return 422 for invalid UUID format (FastAPI path validation)
    - Return 200 with empty array if no history exists
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 3. Checkpoint - Backend changes
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Frontend: TypeScript types and utility functions
  - [ ] 4.1 Create workflow execution types in `src/frontend/src/types/workflow.ts`
    - Define `DocumentStateResponse`, `TransitionResponse`, `TransitionHistoryEntry`, `WorkflowGateInfo`, `RiskLevel` types
    - _Requirements: 7.1_

  - [ ] 4.2 Create `src/frontend/src/lib/workflowUtils.ts` with pure utility functions
    - Implement `getStateBadgeColor(state: string): string` — Draft=gray, Review=blue, Approved=green, Rejected=red, default=neutral
    - Implement `getRiskLevelColor(riskLevel: string): string` — low=gray, medium=blue, high=orange, critical=red, default=gray
    - Implement `isValidChangeReason(reason: string): boolean` — trimmed length 3–500 inclusive
    - Implement `truncateText(text: string, maxLength: number): string` — append "…" if truncated
    - Implement `formatTransitionString(currentState: string, targetState: string): string` — "Current→Target" (U+2192)
    - Implement `hasGate(currentState: string, targetState: string, gateTransitions: string[]): boolean`
    - _Requirements: 1.2, 2.2, 3.3, 4.3, 9.3, 10.1, 10.3_

- [ ] 5. Frontend: Workflow Execution Store
  - [ ] 5.1 Create `src/frontend/src/stores/workflowExecutionStore.ts` with Zustand
    - Define state shape: document state fields, transition execution fields, history fields, gate status fields
    - Implement `fetchDocumentState(documentUuid)` — GET `/api/workflows/state/{uuid}`, manage loading/error states
    - Implement `executeTransition(documentUuid, targetState, changeReason)` — POST `/api/workflows/transition` with body `{ document_uuid, target_state }` and `X-Change-Reason` header via apiClient's changeReason option, auto-refresh state and history on success
    - Implement `fetchTransitionHistory(documentUuid)` — GET `/api/workflows/state/{uuid}/history`, manage loading/error states
    - Implement `fetchWorkflowGateInfo(workflowName)` — GET `/api/workflows` to list workflows, find by name, extract `signature_required_transitions`, `training_trigger_transitions`, and `risk_level`
    - Implement `clearTransitionState()` and `reset()` actions
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 9.1, 9.2, 10.5_

  - [ ] 5.2 Export store from `src/frontend/src/stores/index.ts`
    - Add export for `workflowExecutionStore`
    - _Requirements: 7.1_

- [ ] 6. Frontend: WorkflowStatePanel component
  - [ ] 6.1 Create `src/frontend/src/components/documents/WorkflowStatePanel.tsx`
    - Render panel header with workflow name, risk level badge (color-coded), state badge (color-coded), and updated_at timestamp in user locale
    - Render transition buttons with target state labels, gate icons (lock for signature, book for training), and tooltips
    - Handle loading skeleton, error state with retry button, and "no workflow assigned" state
    - Implement collapsible section behavior (default expanded)
    - Use ARIA region role with label "Document Workflow State", aria-labels on buttons including gate info
    - Display gate indicator banners after successful transition (signature-required, training-triggered)
    - Display risk warning badge for high/critical workflows
    - Call `fetchWorkflowGateInfo` when valid transitions are available
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 3.1, 3.2, 3.3, 9.1, 9.3, 9.4, 9.5, 9.6, 9.7, 10.1, 10.2, 10.3, 10.4, 11.1, 11.2, 11.6, 11.7_

- [ ] 7. Frontend: TransitionConfirmationDialog component
  - [ ] 7.1 Create `src/frontend/src/components/documents/TransitionConfirmationDialog.tsx`
    - Render modal with state transition summary (current → target)
    - Render change reason textarea with character counter (3–500 chars), validation, and associated label element
    - Render gate warning messages (signature: yellow/amber, training: blue) when applicable
    - Render risk warning for high/critical workflows with icon and corresponding color (orange/red)
    - Implement confirm/cancel buttons with loading state, disable both during transition
    - Implement 30-second timeout with AbortController, display timeout error, re-enable buttons
    - Display backend error messages inline, retain change reason text on error
    - Implement focus trapping (Tab/Shift+Tab cycle within dialog), Escape to close
    - Set dialog role, aria-labelledby, aria-describedby attributes
    - Return focus to triggering button on close
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.4, 3.5, 3.6, 10.2, 11.3, 11.5, 11.7, 11.8_

- [ ] 8. Frontend: WorkflowHistoryTimeline component
  - [ ] 8.1 Create `src/frontend/src/components/documents/WorkflowHistoryTimeline.tsx`
    - Render ordered list (ol/li) of history entries in reverse chronological order
    - Each entry: previous state → new state (with directional arrow), user display name (fallback to user ID), locale-formatted absolute timestamp, change reason truncated to 120 chars with "Show more" toggle
    - Implement collapse/expand behavior (default collapsed), show 5 most recent when expanded, "Show all" button when > 5 entries expanding inline up to 50, scrollable container if > 50
    - Handle loading skeleton, error state with retry button, empty state message
    - Use aria-live regions with "polite" for loading announcements
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 11.4, 11.6_

- [ ] 9. Frontend: Integration into DocumentDetail
  - [ ] 9.1 Modify `src/frontend/src/components/documents/DocumentDetail.tsx` to render WorkflowStatePanel and WorkflowHistoryTimeline
    - Conditionally render panels when document has a tag matching an active workflow definition's `document_tag`
    - Position below document metadata, above VersionHistoryPanel, using same bordered rounded container styling
    - Call `fetchDocumentState` on mount when workflow is applicable
    - Update document `current_status` badge text after successful transition
    - Handle `?tab=workflow` query parameter: auto-expand both panels, scroll WorkflowStatePanel into viewport within 500ms
    - Do not render panels or show errors if document has no matching workflow
    - Preserve `?tab=workflow` in URL after scroll completes
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ] 9.2 Update `src/frontend/src/components/documents/index.ts` to export new components
    - Export WorkflowStatePanel, TransitionConfirmationDialog, WorkflowHistoryTimeline
    - _Requirements: 8.1_

- [ ] 10. Checkpoint - Core implementation complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Testing: Utility function and store tests
  - [ ]* 11.1 Write property tests for `workflowUtils` in `src/frontend/src/lib/__tests__/workflowUtils.property.test.ts`
    - **Property 1: State badge and risk level color mapping** — verify correct color for all known states and arbitrary strings
    - **Validates: Requirements 1.2, 10.1, 10.3, 10.4**

  - [ ]* 11.2 Write property tests for change reason validation in `src/frontend/src/lib/__tests__/workflowUtils.property.test.ts`
    - **Property 2: Change reason validation** — isValidChangeReason returns true iff trimmed length is 3–500
    - **Validates: Requirements 2.2**

  - [ ]* 11.3 Write property tests for gate indicator matching in `src/frontend/src/lib/__tests__/workflowUtils.property.test.ts`
    - **Property 3: Gate indicator matching** — hasGate returns true iff formatted transition string is in the gate array
    - **Validates: Requirements 3.3, 9.3, 9.4, 9.5, 9.6**

  - [ ]* 11.4 Write property tests for text truncation in `src/frontend/src/lib/__tests__/workflowUtils.property.test.ts`
    - **Property 5: Change reason text truncation** — truncateText(text, 120) preserves strings ≤120 chars, truncates with "…" otherwise
    - **Validates: Requirements 4.3**

  - [ ]* 11.5 Write unit tests for `workflowUtils` in `src/frontend/src/lib/__tests__/workflowUtils.test.ts`
    - Test specific known inputs for all utility functions
    - Test edge cases: empty strings, boundary lengths (2, 3, 500, 501 chars), special characters, Unicode
    - _Requirements: 1.2, 2.2, 3.3, 4.3, 10.1, 10.3_

  - [ ]* 11.6 Write property tests for store state machine in `src/frontend/src/stores/__tests__/workflowExecutionStore.property.test.ts`
    - **Property 8: Store loading state machine** — isLoadingState transitions correctly, never remains true after completion/failure
    - **Validates: Requirements 7.3, 7.7**

  - [ ]* 11.7 Write property tests for executeTransition API construction in `src/frontend/src/stores/__tests__/workflowExecutionStore.property.test.ts`
    - **Property 9: executeTransition API call construction** — correct body `{ document_uuid, target_state }` and X-Change-Reason header for any valid inputs
    - **Validates: Requirements 2.3, 7.4**

  - [ ]* 11.8 Write property tests for successful transition refresh in `src/frontend/src/stores/__tests__/workflowExecutionStore.property.test.ts`
    - **Property 10: Successful transition triggers state and history refresh** — both fetchDocumentState and fetchTransitionHistory are called after success
    - **Validates: Requirements 2.5, 7.5**

  - [ ]* 11.9 Write unit tests for `workflowExecutionStore` in `src/frontend/src/stores/__tests__/workflowExecutionStore.test.ts`
    - Test fetchDocumentState success/failure, executeTransition success/failure, clearTransitionState, reset
    - Mock apiClient calls
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 12. Testing: Component tests
  - [ ]* 12.1 Write unit tests for WorkflowStatePanel in `src/frontend/src/components/documents/__tests__/WorkflowStatePanel.test.tsx`
    - Test renders state badge with correct color, transition buttons, loading/error/empty states
    - Test gate icons appear for gated transitions with correct tooltips
    - Test risk badge display for all risk levels
    - Test accessibility: ARIA region, button aria-labels with gate info, focus indicators
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 9.4, 9.5, 11.1, 11.2_

  - [ ]* 12.2 Write unit tests for TransitionConfirmationDialog in `src/frontend/src/components/documents/__tests__/TransitionConfirmationDialog.test.tsx`
    - Test opens/closes, validates change reason input (3–500 chars), shows character counter
    - Test gate warnings display (signature yellow, training blue)
    - Test risk warning display for high/critical
    - Test confirm button disabled when reason invalid, loading state during transition
    - Test error display and reason retention on failure
    - Test accessibility: focus trapping, Escape key, dialog role, aria-labelledby, aria-describedby
    - _Requirements: 2.1, 2.2, 2.4, 2.6, 2.9, 3.4, 3.5, 10.2, 11.3, 11.5, 11.8_

  - [ ]* 12.3 Write unit tests for WorkflowHistoryTimeline in `src/frontend/src/components/documents/__tests__/WorkflowHistoryTimeline.test.tsx`
    - Test renders entries with correct data (states, user, timestamp, reason)
    - Test collapse/expand behavior, "Show all" button appears when > 5 entries
    - Test "Show more" toggle for truncated change reasons
    - Test empty state, error state with retry button, loading skeleton
    - Test accessibility: ordered list structure (ol/li), aria-live regions
    - _Requirements: 4.1, 4.3, 4.5, 4.6, 4.7, 4.8, 11.4, 11.6_

- [ ] 13. Testing: Backend tests
  - [ ]* 13.1 Write unit tests for workflow history endpoint in `src/backend/tests/test_workflow_transition_history.py`
    - Test 404 for missing document, empty array for no history, tenant scoping
    - Test correct ordering (newest first), limit of 1000 records
    - Test 422 for invalid UUID format
    - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 13.2 Write unit tests for change reason storage in `src/backend/tests/test_workflow_change_reason.py`
    - Test change_reason stored correctly from X-Change-Reason header
    - Test null stored for whitespace-only header value
    - Test truncation at 500 characters
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 13.3 Write property tests for change reason normalization in `src/backend/tests/test_workflow_change_reason_property.py`
    - **Property 7: Change reason normalization** — verify null for empty/whitespace, truncation at exactly 500, pass-through for trimmed 1–500 chars
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [ ]* 13.4 Write property tests for history ordering in `src/backend/tests/test_workflow_transition_history.py`
    - **Property 4: Transition history reverse chronological ordering** — verify descending timestamp order and max 1000 records
    - **Validates: Requirements 4.1, 5.1**

  - [ ]* 13.5 Write property tests for history response schema in `src/backend/tests/test_workflow_transition_history.py`
    - **Property 11: Transition history response schema completeness** — verify all required fields present in serialized response
    - **Validates: Requirements 5.2**

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–11)
- Unit tests validate specific examples and edge cases
- Backend tasks (1–2) must complete before frontend integration tasks (4–9) since the API contract must be stable
- The existing `workflowStore.ts` manages workflow definitions/editor (Phase 3.1) — the new `workflowExecutionStore.ts` is separate by design
- Frontend property tests use `fast-check`; backend property tests use `hypothesis`
- The `apiClient` already handles auth headers (`Authorization`, `X-User-Id`, `X-Company-Id`) automatically — the `X-Change-Reason` header is passed via the `changeReason` option on POST calls
- The existing `POST /api/workflows/transition` handler parameter `request: TransitionRequest` must be renamed to `body: TransitionRequest` to avoid conflict with the FastAPI `Request` object needed for header extraction

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["1.4", "2.2", "4.2"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1", "8.1"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["9.1", "9.2"] },
    { "id": 7, "tasks": ["11.1", "11.2", "11.3", "11.4", "11.5", "13.1", "13.2"] },
    { "id": 8, "tasks": ["11.6", "11.7", "11.8", "11.9", "13.3", "13.4", "13.5"] },
    { "id": 9, "tasks": ["12.1", "12.2", "12.3"] }
  ]
}
```
