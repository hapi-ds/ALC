# Requirements Document

## Introduction

This feature implements the Workflow Execution & State Transitions frontend for AlcoaBase, enabling users to view the current workflow state of a document, see available transitions, trigger state transitions with confirmation dialogs and change reasons, and review a chronological workflow history timeline. The feature integrates with the existing backend `POST /api/workflows/transition` and `GET /api/workflows/state/{document_uuid}` endpoints, and extends the backend with a workflow history endpoint. It builds upon Phase 3.1 (BPMN Workflow Visual Editor) which provides workflow definitions, and integrates into the document detail pages from Phase 2.1–2.3. Transition hooks for PAdES signatures (Phase 3.4) and training gates (Phase 3.3) are surfaced as blocking indicators with appropriate messaging.

## Glossary

- **Workflow_State_Panel**: The React component displayed on the document detail page showing the current workflow state, workflow name, and available transitions for the document.
- **Transition_Confirmation_Dialog**: A modal dialog presented to the user before executing a state transition, requiring a change reason and displaying any gate requirements (signature, training).
- **Workflow_History_Timeline**: A chronological list component showing all state transitions that have occurred on a document, including timestamps, users, previous/new states, and change reasons.
- **Workflow_Execution_Store**: The Zustand state store managing document workflow state, transition execution, and workflow history data.
- **Document_State_API**: The backend endpoint at `GET /api/workflows/state/{document_uuid}` returning the current workflow state and valid transitions for a document.
- **Transition_API**: The backend endpoint at `POST /api/workflows/transition` that validates and executes a state transition for a document.
- **Workflow_History_API**: The backend endpoint at `GET /api/workflows/state/{document_uuid}/history` returning the chronological list of all state transitions for a document.
- **Transition_Gate**: A pre-condition on a transition that must be satisfied before the transition can complete, specifically PAdES signature requirement (Phase 3.4) or training completion requirement (Phase 3.3).
- **Change_Reason**: A mandatory text field provided by the user when triggering a transition, stored in the audit trail and sent via the `X-Change-Reason` header.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and the X-Change-Reason audit header.
- **WorkflowTransitionAudit**: The backend model recording every state transition with document_id, user_id, previous_state, new_state, timestamp, and change_reason.

## Requirements

### Requirement 1: Document Workflow State Display

**User Story:** As a user viewing a document, I want to see the current workflow state of the document, so that I understand where the document is in its lifecycle and what actions are available.

#### Acceptance Criteria

1. WHEN the user views a document detail page for a document that has an assigned workflow, THE Workflow_State_Panel SHALL fetch the document state from `GET /api/workflows/state/{document_uuid}` and display the current state name, workflow name, and last updated timestamp formatted in the user's locale (date and time with timezone offset).
2. THE Workflow_State_Panel SHALL display the current state using a color-coded badge (Draft: gray, Review: blue, Approved: green, Rejected: red, other states: default neutral color).
3. IF the document state includes one or more valid transitions, THEN THE Workflow_State_Panel SHALL display each valid transition as an action button labeled with the target state name.
4. IF the document state includes zero valid transitions, THEN THE Workflow_State_Panel SHALL display a text indication that no transitions are currently available for this document state.
5. WHILE the document state is loading, THE Workflow_State_Panel SHALL display a loading skeleton placeholder.
6. IF the document state request returns a 404 (no workflow state exists), THEN THE Workflow_State_Panel SHALL display a message indicating no workflow is assigned to the document.
7. IF the document state request fails due to a network or server error, THEN THE Workflow_State_Panel SHALL display an error message with a retry button that re-invokes the `GET /api/workflows/state/{document_uuid}` request when clicked.
8. THE Workflow_State_Panel SHALL be positioned within the document detail page below the document metadata section and above the version history panel.

### Requirement 2: Transition Execution with Confirmation

**User Story:** As a user, I want to trigger a workflow state transition with a confirmation step, so that I can advance a document through its lifecycle while providing an audit-compliant change reason.

#### Acceptance Criteria

1. WHEN the user clicks a transition action button, THE Workflow_State_Panel SHALL open the Transition_Confirmation_Dialog displaying the current state, target state, and a required text input for the change reason.
2. THE Transition_Confirmation_Dialog SHALL require the change reason field to contain between 3 and 500 characters before enabling the confirm button, and SHALL display a character counter showing the remaining characters.
3. WHEN the user confirms the transition, THE Workflow_Execution_Store SHALL send a POST request to `POST /api/workflows/transition` with the document_uuid and target_state in the request body, and the user-provided change reason in the `X-Change-Reason` header.
4. WHILE the transition request is in progress, THE Transition_Confirmation_Dialog SHALL display a loading indicator on the confirm button and disable both the confirm and cancel buttons to prevent duplicate submissions. IF the request does not complete within 30 seconds, THEN THE Transition_Confirmation_Dialog SHALL abort the request, display a timeout error message, and re-enable the buttons.
5. WHEN the backend returns a successful response with `success: true`, THE Workflow_State_Panel SHALL update the displayed current state to the new state, refresh the valid transitions list, and display a success notification that auto-dismisses after 5 seconds.
6. IF the backend returns a 400 error indicating an invalid transition, THEN THE Transition_Confirmation_Dialog SHALL display the error detail message from the response, retain the user-entered change reason text, and re-enable the buttons.
7. IF the transition request fails due to a network error, THEN THE Transition_Confirmation_Dialog SHALL display a network error message, retain the user-entered change reason text, and re-enable the buttons.
8. IF the backend returns a non-400 server error (403, 500, or other unexpected status), THEN THE Transition_Confirmation_Dialog SHALL display an error message indicating the transition could not be completed, retain the user-entered change reason text, and re-enable the buttons.
9. WHEN the user clicks cancel in the Transition_Confirmation_Dialog, THE dialog SHALL close without executing any transition.

### Requirement 3: Transition Gate Indicators

**User Story:** As a user, I want to see when a transition requires a signature or training completion, so that I understand what additional steps are needed before the transition can proceed.

#### Acceptance Criteria

1. WHEN the backend transition response includes `requires_signature: true`, THE Workflow_State_Panel SHALL display a signature-required indicator as an inline banner below the state badge, directing the user to complete the electronic signature (Phase 3.4).
2. WHEN the backend transition response includes `triggers_training: true`, THE Workflow_State_Panel SHALL display a training-required indicator as an inline banner below the state badge, indicating that training tasks have been assigned (Phase 3.3).
3. THE Workflow_State_Panel SHALL display gate indicators (lock icon for signature, book icon for training) on transition buttons that are known to require gates, based on the workflow definition's `signature_required_transitions` and `training_trigger_transitions` arrays.
4. WHEN a transition button has a signature gate indicator, THE Transition_Confirmation_Dialog SHALL display a warning message with yellow/amber styling stating that completing this transition will require an electronic signature.
5. WHEN a transition button has a training gate indicator, THE Transition_Confirmation_Dialog SHALL display an informational message with blue styling stating that completing this transition will trigger training assignment.
6. IF a transition has both a signature gate and a training gate, THEN THE transition button SHALL display both the lock icon and the book icon, and THE Transition_Confirmation_Dialog SHALL display both the signature warning and the training informational message.

### Requirement 4: Workflow History Timeline

**User Story:** As a user, I want to view the complete history of state transitions for a document, so that I can audit who changed the document state, when, and why.

#### Acceptance Criteria

1. THE Workflow_History_Timeline SHALL be displayed on the document detail page below the Workflow_State_Panel, showing all state transitions for the document in reverse chronological order (newest first).
2. WHEN the document detail page loads for a document with a workflow state, THE Workflow_Execution_Store SHALL fetch the transition history from `GET /api/workflows/state/{document_uuid}/history`.
3. Each entry in the Workflow_History_Timeline SHALL display: the previous state, the new state, the user who triggered the transition (display name when available, falling back to user ID if display name is not present), the timestamp formatted as an absolute date-time in the user's locale, and the change reason truncated to 120 characters with a "Show more" toggle to reveal the full text.
4. THE Workflow_History_Timeline SHALL display a directional arrow or visual connector between the previous state and new state for each entry.
5. WHILE the history is loading, THE Workflow_History_Timeline SHALL display a loading skeleton.
6. IF the history request fails, THEN THE Workflow_History_Timeline SHALL display an error message with a retry button that re-invokes fetchTransitionHistory for the same document_uuid when clicked.
7. IF the document has no transition history (only the initial state), THEN THE Workflow_History_Timeline SHALL display a message indicating no transitions have occurred yet.
8. THE Workflow_History_Timeline SHALL support collapsing and expanding to conserve vertical space on the document detail page, defaulting to expanded with the 5 most recent entries visible and a "Show all" button for documents with more than 5 transitions that expands the list inline to display all entries up to a maximum of 50, with a scrollable container if the total exceeds 50 entries.

### Requirement 5: Backend Workflow History Endpoint

**User Story:** As a frontend developer, I want a backend endpoint to retrieve the transition history for a document, so that the workflow history timeline can display all past state changes.

#### Acceptance Criteria

1. THE Workflow_History_API SHALL expose a `GET /api/workflows/state/{document_uuid}/history` endpoint returning a JSON array of WorkflowTransitionAudit records for the specified document, ordered by timestamp descending, returning a maximum of 1000 records per response.
2. Each record in the response SHALL include: id, document_id, user_id, previous_state, new_state, timestamp (as ISO 8601 datetime with timezone), and change_reason.
3. IF the `document_uuid` does not correspond to any document with a workflow state within the tenant, THEN THE Workflow_History_API SHALL return a 404 response with a detail message indicating that no workflow state was found for the specified document.
4. IF the document has no transition history, THEN THE Workflow_History_API SHALL return a 200 response with an empty JSON array.
5. THE Workflow_History_API SHALL scope results to documents belonging to the tenant identified by the `X-Company-Id` header.
6. IF the `document_uuid` path parameter is not a valid UUID format, THEN THE Workflow_History_API SHALL return a 422 response with a validation error message.

### Requirement 6: Backend Transition Audit Enhancement

**User Story:** As a developer, I want the transition audit trail to capture the change reason from the request header, so that the workflow history timeline can display why each transition occurred.

#### Acceptance Criteria

1. WHEN a state transition is executed via `POST /api/workflows/transition`, THE WorkflowEngine SHALL extract the value of the `X-Change-Reason` header from the request and store it in the WorkflowTransitionAudit record's `change_reason` field.
2. IF the `X-Change-Reason` header value exceeds 500 characters, THEN THE WorkflowEngine SHALL truncate the value to 500 characters before storing it in the `change_reason` field.
3. IF the `X-Change-Reason` header value is empty or contains only whitespace, THEN THE WorkflowEngine SHALL store null in the `change_reason` field.
4. THE WorkflowTransitionAudit model SHALL include a `change_reason` column of type String(500), nullable, to store the audit reason for each transition.
5. THE database migration SHALL add the `change_reason` column to the existing `workflow_transition_audits` table without data loss, defaulting to null for existing records.

### Requirement 7: Workflow Execution State Store

**User Story:** As a developer, I want a centralized state store for workflow execution operations, so that document state, transitions, and history data flow consistently across components.

#### Acceptance Criteria

1. THE Workflow_Execution_Store SHALL maintain state for: document workflow state (current_state, workflow_name, valid_transitions, updated_at, isLoadingState, stateError), transition execution (isTransitioning, transitionError, lastTransitionResult), workflow history (history array, isLoadingHistory, historyError), and gate status (requires_signature, triggers_training from last transition, signature_required_transitions, training_trigger_transitions, risk_level).
2. THE Workflow_Execution_Store SHALL expose actions for: fetchDocumentState(documentUuid), executeTransition(documentUuid, targetState, changeReason), fetchTransitionHistory(documentUuid), fetchWorkflowGateInfo(workflowName), and clearTransitionState().
3. WHEN fetchDocumentState is called, THE Workflow_Execution_Store SHALL set isLoadingState to true, clear stateError, send a GET request to `/api/workflows/state/{document_uuid}`, store the response in state on success, and set isLoadingState to false. IF the request fails, THEN THE store SHALL set stateError to the error message and set isLoadingState to false.
4. WHEN executeTransition is called, THE Workflow_Execution_Store SHALL set isTransitioning to true, clear transitionError, send a POST request to `/api/workflows/transition` with the document_uuid and target_state in the body and the changeReason in the `X-Change-Reason` header via apiClient's changeReason option, then update the document state on success and set isTransitioning to false.
5. WHEN executeTransition succeeds, THE Workflow_Execution_Store SHALL automatically re-fetch the document state and transition history to reflect the new state.
6. WHEN clearTransitionState is called, THE Workflow_Execution_Store SHALL reset transitionError to null, lastTransitionResult to null, requires_signature to false, and triggers_training to false.
7. IF any API request initiated by the Workflow_Execution_Store fails, THEN THE Workflow_Execution_Store SHALL store the error message in the corresponding error state property and set the corresponding loading flag to false.

### Requirement 8: Integration with Document Detail Page

**User Story:** As a user, I want the workflow state and transitions to appear naturally within the document detail view, so that I can manage document lifecycle without navigating to a separate page.

#### Acceptance Criteria

1. THE DocumentDetail component SHALL render the Workflow_State_Panel when the document has at least one tag that matches a workflow definition's `document_tag` where that workflow definition has an active status, as determined by fetching available workflow definitions from the Workflow_Execution_Store.
2. WHEN the document detail page mounts and the document has a matching active workflow definition, THE component SHALL call fetchDocumentState with the document's `document_uuid` to load the workflow state.
3. WHEN a transition is successfully executed, THE DocumentDetail component SHALL update the document's `current_status` badge text in the metadata section to display the new state name returned by the transition response.
4. THE Workflow_State_Panel and Workflow_History_Timeline SHALL be rendered as collapsible sections positioned below the document metadata section and above the VersionHistoryPanel, using the same container styling as VersionHistoryPanel (bordered rounded container with section heading), with the Workflow_State_Panel defaulting to expanded and the Workflow_History_Timeline defaulting to collapsed.
5. IF the document has no assigned workflow (no tag matches any active workflow definition's `document_tag`), THEN THE document detail page SHALL NOT render the Workflow_State_Panel or Workflow_History_Timeline.
6. WHEN the document detail page URL contains the query parameter `?tab=workflow`, THE DocumentDetail component SHALL auto-expand both the Workflow_State_Panel and Workflow_History_Timeline sections and scroll the Workflow_State_Panel into the viewport.

### Requirement 9: Transition Gate Information from Workflow Definition

**User Story:** As a user, I want to see which transitions require signatures or training before I attempt them, so that I can prepare accordingly.

#### Acceptance Criteria

1. WHEN the Workflow_Execution_Store successfully fetches the document state and valid transitions are available, THE Workflow_State_Panel SHALL call fetchWorkflowGateInfo with the workflow name to retrieve gate configuration before rendering transition button indicators.
2. THE Workflow_Execution_Store SHALL expose a fetchWorkflowGateInfo(workflowName) action that retrieves the workflow definition from the backend, extracts the `signature_required_transitions` and `training_trigger_transitions` arrays, and stores them in state for use by the Workflow_State_Panel.
3. THE Workflow_State_Panel SHALL check each valid transition string (formatted as "CurrentState→TargetState" using Unicode U+2192) against the `signature_required_transitions` and `training_trigger_transitions` arrays to determine which gate indicators to display on each transition button.
4. IF a transition exists in the `signature_required_transitions` array, THEN THE transition button SHALL display a lock icon and a tooltip with the text "Requires electronic signature".
5. IF a transition exists in the `training_trigger_transitions` array, THEN THE transition button SHALL display a book icon and a tooltip with the text "Triggers training assignment".
6. IF a transition exists in both the `signature_required_transitions` and `training_trigger_transitions` arrays, THEN THE transition button SHALL display both the lock icon and the book icon, with each icon retaining its respective tooltip.
7. IF the fetchWorkflowGateInfo request fails, THEN THE Workflow_State_Panel SHALL render the transition buttons without gate indicators and SHALL NOT block the user from attempting transitions.

### Requirement 10: Risk-Based Transition Enforcement Display

**User Story:** As a user, I want to see when a document is under a high-risk workflow, so that I understand the additional scrutiny applied to state transitions.

#### Acceptance Criteria

1. WHEN the document's workflow has a risk_level of "high" or "critical", THE Workflow_State_Panel SHALL display a risk indicator badge showing the risk level text with color coding: "high" in orange and "critical" in red.
2. WHEN the document's workflow has a risk_level of "high" or "critical", THE Transition_Confirmation_Dialog SHALL display a warning message indicating that the document is under a high-risk workflow and that transitions are subject to enhanced review requirements, visually distinguished with a warning icon and the corresponding risk-level color (orange for high, red for critical).
3. THE Workflow_State_Panel SHALL display the workflow risk level alongside the workflow name in the panel header for all risk levels, using the following color coding: "low" in gray, "medium" in blue, "high" in orange, and "critical" in red.
4. IF the workflow definition does not include a risk_level value, THEN THE Workflow_State_Panel SHALL treat the workflow as "low" risk and display "low" in gray.
5. THE Workflow_Execution_Store SHALL obtain the workflow risk_level from the workflow definition data retrieved by the fetchWorkflowGateInfo action, and expose it as part of the document workflow state.

### Requirement 11: Accessibility and Keyboard Navigation

**User Story:** As a user relying on assistive technology, I want the workflow state panel and transition dialogs to be fully accessible, so that I can manage document workflows using keyboard navigation and screen readers.

#### Acceptance Criteria

1. THE Workflow_State_Panel SHALL use an ARIA region role with an accessible label "Document Workflow State", and all interactive elements within the panel SHALL be reachable via the Tab key in a logical order (state display, then transition buttons left-to-right).
2. THE transition action buttons SHALL have aria-labels in the format "Transition to {target_state}" and, when a gate icon (lock or book) is present on the button, SHALL include an aria-label in the format "Transition to {target_state}, requires electronic signature" or "Transition to {target_state}, triggers training assignment" respectively.
3. WHILE the Transition_Confirmation_Dialog is open, THE dialog SHALL trap focus so that Tab and Shift+Tab cycle only through focusable elements within the dialog. WHEN the dialog is closed, THE focus SHALL return to the transition button that triggered the dialog.
4. THE Workflow_History_Timeline entries SHALL be rendered as an ordered list (ol element) with each entry as a list item (li element) for screen reader navigation.
5. WHEN the user presses the Escape key while the Transition_Confirmation_Dialog is open, THE dialog SHALL close without executing any transition and return focus to the triggering button.
6. ALL loading states within the Workflow_State_Panel and Workflow_History_Timeline SHALL use aria-live regions with politeness level "polite" to announce loading start and completion messages to screen readers.
7. ALL focusable elements within the Workflow_State_Panel and Transition_Confirmation_Dialog SHALL display a visible focus indicator that meets a minimum contrast ratio of 3:1 against adjacent colors.
8. THE Transition_Confirmation_Dialog SHALL assign the dialog role with an aria-labelledby attribute referencing the dialog title and aria-describedby referencing the dialog content, and the change reason input SHALL have an associated label element.

### Requirement 12: Frontend Routing for Workflow State

**User Story:** As a user, I want to access a document's workflow state via a direct URL, so that I can share links to specific document workflow views.

#### Acceptance Criteria

1. WHEN the document detail page loads with the query parameter `?tab=workflow` present, THE page SHALL scroll the Workflow_State_Panel into the visible viewport and expand it if collapsed, within 500 milliseconds of the page content rendering.
2. WHEN a transition is successfully executed, THE browser URL SHALL NOT change; the workflow state panel updates in place within the document detail page.
3. THE Workflow_State_Panel SHALL be accessible without any additional route registration, as it is embedded within the existing document detail view.
4. WHILE the `?tab=workflow` query parameter is present in the URL, THE page SHALL preserve the parameter in the browser address bar so that the URL remains shareable after scrolling completes.
5. IF the query parameter `?tab=workflow` is present but the document has no assigned workflow, THEN THE document detail page SHALL render without scrolling and SHALL NOT display an error related to the query parameter.
