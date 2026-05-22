# Requirements Document

## Introduction

This feature implements the Training Management UI for AlcoaBase, providing a frontend interface for managing SOP training tasks, viewing training records, completing training assignments, and enforcing training-gated access in frontend routing. The UI integrates with the existing backend training service endpoints (`GET /api/training/tasks`, `POST /api/training/tasks/{task_id}/complete`, `GET /api/training/status/{sop_uuid}/{version}`, `GET /api/training/content/{content_id}`, `POST /api/training/content/{content_id}/approve`, `POST /api/training/content/{content_id}/reject`) and replaces the current placeholder `TrainingPage.tsx` with a fully functional training dashboard. The feature supports the GxP training execution gate (REQ-TRN-02) by blocking frontend navigation to documents requiring uncompleted training, and integrates with Phase 3.2 (Workflow Execution) transition gate indicators and Phase 3.5 (Training-Gated Access Control) for hard enforcement.

## Glossary

- **Training_Dashboard**: The main React page component at route `/training` displaying training statistics, task lists, and training content for the authenticated user.
- **Training_Task_List**: The filterable list component displaying training tasks assigned to the current user, supporting filter states: pending, completed, and all.
- **Training_Task_Card**: An individual list item component representing a single training task with SOP name, version, status, and action controls.
- **Task_Completion_Dialog**: A modal dialog presented when a user initiates task completion, requiring confirmation and a change reason for ALCOA+ audit compliance.
- **Training_Content_Viewer**: A component that renders training content including summary, quiz questions, procedural steps, and safety points for a selected training task.
- **Training_Records_Panel**: A component displaying training completion records, filterable by user or by document/SOP, showing validity status and completion timestamps.
- **Training_Status_Overview**: A statistics dashboard section showing aggregate training metrics: pending tasks, completed tasks, total tasks, and completion percentage.
- **Training_Store**: The Zustand state store managing training tasks, records, content, statistics, and API interactions for the training management feature.
- **Training_Gate_Guard**: A React Router wrapper component that checks training status before allowing navigation to training-gated document routes, blocking access with an informational message when training is incomplete.
- **Admin_Training_View**: A component accessible to administrators showing per-SOP training status across all assigned users, with completion tracking and progress indicators.
- **Training_Tasks_API**: The backend endpoint at `GET /api/training/tasks?user_id={id}` returning training tasks assigned to a user.
- **Task_Complete_API**: The backend endpoint at `POST /api/training/tasks/{task_id}/complete?user_id={id}` marking a training task as completed.
- **Training_Status_API**: The backend endpoint at `GET /api/training/status/{sop_uuid}/{version}` returning training progress for an SOP version.
- **Training_Content_API**: The backend endpoint at `GET /api/training/content/{content_id}` returning training content (quiz, steps, safety points).
- **Content_Approve_API**: The backend endpoint at `POST /api/training/content/{content_id}/approve` approving training content after coordinator review.
- **Content_Reject_API**: The backend endpoint at `POST /api/training/content/{content_id}/reject` rejecting training content after coordinator review.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and the X-Change-Reason audit header.
- **Change_Reason**: A mandatory text field provided by the user when completing a training task, stored in the audit trail and sent via the `X-Change-Reason` header.

## Requirements

### Requirement 1: Training Dashboard Statistics Display

**User Story:** As a user, I want to see an overview of my training status at a glance, so that I understand how many tasks are pending, completed, and my overall training progress.

#### Acceptance Criteria

1. WHEN the user navigates to the `/training` route, THE Training_Dashboard SHALL fetch training tasks from `GET /api/training/tasks?user_id={current_user_id}` and compute statistics: total tasks, pending tasks (where `is_completed` is false), completed tasks (where `is_completed` is true), and completion percentage (completed divided by total, rounded to the nearest whole number using standard rounding).
2. THE Training_Status_Overview SHALL display three statistics cards: "Pending" with a clock icon showing the count of incomplete tasks, "Completed" with a check-circle icon showing the count of completed tasks, and "Total Tasks" with a graduation-cap icon showing the total task count. THE Training_Status_Overview SHALL also display the completion percentage as a separate text element positioned below or adjacent to the statistics cards, formatted as "{value}%".
3. WHILE the training tasks are loading, THE Training_Status_Overview SHALL display skeleton placeholders for each statistics card and for the completion percentage element.
4. IF the training tasks request fails due to a network or server error, THEN THE Training_Dashboard SHALL display an error message with a retry button that re-invokes the fetch when clicked.
5. IF the user has zero training tasks assigned, THEN THE Training_Status_Overview SHALL display all statistics cards with a value of "0" and the completion percentage element as "N/A".

### Requirement 2: Training Task List with Filtering

**User Story:** As a user, I want to view my training tasks with the ability to filter by status, so that I can focus on pending tasks or review completed ones.

#### Acceptance Criteria

1. THE Training_Task_List SHALL display training tasks in a vertical list, with each Training_Task_Card showing: the task title (truncated with an ellipsis after 80 characters), SOP document UUID, SOP version, completion status (pending or completed), and completion timestamp (for completed tasks, formatted in the user's locale).
2. THE Training_Task_List SHALL provide filter controls with three options: "All" (default, showing all tasks), "Pending" (showing only tasks where `is_completed` is false), and "Completed" (showing only tasks where `is_completed` is true). THE currently active filter option SHALL be visually distinguished from inactive options.
3. WHEN the user selects a filter option, THE Training_Task_List SHALL update the displayed tasks to match the selected filter within the same render cycle without making an additional API request.
4. THE Training_Task_List SHALL sort tasks with pending tasks first (ordered by `created_at` ascending, oldest first) followed by completed tasks (ordered by `completed_at` descending, newest first). WHEN a single-status filter is active ("Pending" or "Completed"), THE Training_Task_List SHALL apply only the sort order for that status (ascending `created_at` for pending, descending `completed_at` for completed).
5. IF the filtered task list is empty, THEN THE Training_Task_List SHALL display a contextual empty state message: "No pending training tasks" for the Pending filter, "No completed training tasks" for the Completed filter, or "No training tasks assigned" for the All filter.
6. WHILE a training task has `is_completed` equal to false, THE Training_Task_Card SHALL display a "Mark Complete" action button.
7. WHILE a training task has `is_completed` equal to true, THE Training_Task_Card SHALL display a "Completed" badge with the completion date formatted in the user's locale and SHALL NOT display any action button.

### Requirement 3: Training Task Completion Flow

**User Story:** As a user, I want to mark a training task as completed with a confirmation step, so that I can acknowledge my training while providing an audit-compliant change reason.

#### Acceptance Criteria

1. WHEN the user clicks the "Mark Complete" button on a Training_Task_Card, THE Training_Task_List SHALL open the Task_Completion_Dialog displaying the task title, SOP document UUID, SOP version, and a required text input for the change reason with an empty initial value.
2. THE Task_Completion_Dialog SHALL require the change reason field to contain between 3 and 500 non-whitespace-trimmed characters (leading and trailing whitespace removed before length validation) before enabling the confirm button, and SHALL display a character counter showing the remaining characters out of 500 based on the current input length.
3. WHEN the user confirms the completion, THE Training_Store SHALL send a POST request to `POST /api/training/tasks/{task_id}/complete?user_id={current_user_id}` with the trimmed change reason in the `X-Change-Reason` header via apiClient's changeReason option.
4. WHILE the completion request is in progress, THE Task_Completion_Dialog SHALL display a loading indicator on the confirm button and disable both the confirm and cancel buttons to prevent duplicate submissions.
5. WHEN the backend returns a successful response, THE Training_Store SHALL update the task's `is_completed` status to true, update the `completed_at` timestamp from the response, recompute the statistics counters locally from the updated tasks array (pending count, completed count, completion percentage), close the dialog, and display a success notification that auto-dismisses after 5 seconds.
6. IF the backend returns a 400 error (task not found, not assigned to user, or already completed), THEN THE Task_Completion_Dialog SHALL display the error detail message from the response body below the change reason input, retain the user-entered change reason text, and re-enable the confirm and cancel buttons.
7. IF the completion request fails due to a network error (no response received), THEN THE Task_Completion_Dialog SHALL display the message "Network error: Unable to reach the server. Please check your connection." below the change reason input, retain the user-entered change reason text, and re-enable the confirm and cancel buttons.
8. WHEN the user clicks cancel or presses the Escape key in the Task_Completion_Dialog, THE dialog SHALL close without executing any completion action, and the change reason text SHALL NOT be persisted (the next dialog open starts with an empty change reason field).

### Requirement 4: Training Content Viewer

**User Story:** As a user, I want to view training content associated with a task including summaries, quiz questions, procedural steps, and safety points, so that I can learn the required material before marking the task as complete.

#### Acceptance Criteria

1. WHEN the user clicks on a Training_Task_Card (anywhere except the "Mark Complete" button), THE Training_Content_Viewer SHALL fetch training content from `GET /api/training/content/{content_id}` where `content_id` is derived from the task's `sop_document_uuid` and `sop_version` (formatted as `{sop_document_uuid}_v{sop_version}`).
2. WHEN the training content is successfully fetched with a status of "approved", THE Training_Content_Viewer SHALL display the content in organized sections: a summary section at the top, followed by procedural steps (if any exist), then safety points highlighted with warning styling (if any exist), and finally quiz questions (if any exist). Sections with no content SHALL be omitted from the display.
3. THE Training_Content_Viewer SHALL render procedural steps as a numbered list ordered by `step_number`, with safety-critical steps (where `is_safety_critical` is true) visually distinguished using a red/amber border and a safety icon, and displaying the `safety_note` below the step description.
4. THE Training_Content_Viewer SHALL render quiz questions with the question text, answer options (the `correct_answer` mixed with `distractors` in an order randomized once when the content is loaded), and a "Reveal Answer" toggle that, when activated, shows the correct answer text and the `sop_section_ref` value.
5. THE Training_Content_Viewer SHALL render safety points as a bulleted list within a visually distinct warning panel with an alert icon.
6. WHILE the training content is loading, THE Training_Content_Viewer SHALL display a loading skeleton matching the layout of the content sections.
7. IF the training content request returns a 404 (content not yet generated), THEN THE Training_Content_Viewer SHALL display a message indicating that training content is not yet available for this task, with an explanation that content will be generated by the training coordinator, and SHALL NOT display any content sections.
8. IF the training content has a status of "rejected", THEN THE Training_Content_Viewer SHALL display a notice indicating that the content is under revision and not currently available for training, and SHALL NOT display any content sections.
9. IF the training content has a status of "pending_review" or "draft", THEN THE Training_Content_Viewer SHALL display a notice indicating that the content is awaiting coordinator review and is not yet available for training, and SHALL NOT display any content sections.
10. IF the training content request fails due to a network or server error (HTTP 500 or above, or no response received), THEN THE Training_Content_Viewer SHALL display an error message with a retry button that re-invokes the content fetch when clicked.
11. WHEN the user clicks on a different Training_Task_Card or navigates away from the Training_Dashboard, THE Training_Content_Viewer SHALL dismiss the current content and, if a new task was selected, fetch and display content for the newly selected task.

### Requirement 5: Training Records View

**User Story:** As a user, I want to view my training records showing which SOPs I am trained on and the validity of each record, so that I can verify my training compliance status.

#### Acceptance Criteria

1. THE Training_Records_Panel SHALL be accessible as a tab or section within the Training_Dashboard, displaying training records for the current user.
2. WHEN the Training_Records_Panel is displayed, THE Training_Store SHALL fetch training tasks from the existing `GET /api/training/tasks?user_id={current_user_id}` endpoint and derive training records from completed tasks (tasks where `is_completed` is true represent valid training records).
3. Each training record entry SHALL display: the SOP document UUID, SOP version, completion date formatted in the user's locale, and a validity indicator where a record is "valid" (green badge) if it is the most recent completed task for that SOP document UUID and the SOP version matches the current version, and "invalidated" (red badge) if a newer SOP version exists for which the user has a completed training task or if the record is not for the latest trained version of that SOP.
4. THE Training_Records_Panel SHALL support sorting by: SOP document UUID (alphabetical), completion date (newest first, default), and SOP version (descending).
5. IF the user has no training records, THEN THE Training_Records_Panel SHALL display an empty state message: "No training records found. Complete training tasks to build your training history."
6. THE Training_Records_Panel SHALL group records by SOP document UUID, showing the most recent training record for each SOP as the default visible row in the collapsed group, and allowing expansion via a toggle control to reveal historical records for the same SOP listed in reverse chronological order.
7. WHILE the Training_Records_Panel is loading training records, THE Training_Records_Panel SHALL display skeleton placeholders matching the layout of the records list.
8. IF the training records fetch fails due to a network or server error, THEN THE Training_Records_Panel SHALL display an error message with a retry button that re-invokes the fetch when clicked.

### Requirement 6: Admin Training Status View

**User Story:** As an administrator, I want to view training status per SOP showing which users have completed training and which have not, so that I can monitor compliance and follow up with untrained personnel.

#### Acceptance Criteria

1. THE Admin_Training_View SHALL be accessible within the Training_Dashboard when the current user has an administrator role, displayed as an additional tab labeled "Admin: SOP Training Status".
2. WHEN the administrator selects an SOP and version from the SOP selector, THE Admin_Training_View SHALL fetch training status from `GET /api/training/status/{sop_uuid}/{version}` and display: total assigned tasks (integer), completed tasks (integer), completion percentage (completed divided by total, displayed as a whole number percentage rounded down, or "N/A" if total is zero), and whether training is fully complete (the `is_complete` boolean from the response).
3. THE Admin_Training_View SHALL display a user-level breakdown showing each assigned user's name (or user ID as fallback), their task completion status (pending or completed), and completion timestamp formatted in the user's locale for completed tasks. The user-level data SHALL be derived from the training tasks fetched via `GET /api/training/tasks` for the selected SOP and version.
4. THE Admin_Training_View SHALL provide a visual progress bar representing the completion percentage (completed tasks divided by total tasks) for the selected SOP version, with the percentage value displayed as text adjacent to the bar.
5. IF all users have completed training for the selected SOP version (`is_complete` is true in the status response), THEN THE Admin_Training_View SHALL display a "Training Complete" badge with green styling indicating the SOP is ready to transition from InTraining to Active.
6. IF the training status request fails due to a network or server error, THEN THE Admin_Training_View SHALL display an error message and a retry button that re-invokes the fetch for the currently selected SOP and version when clicked.
7. THE Admin_Training_View SHALL provide an SOP selector dropdown populated from the training tasks data available to the administrator, listing unique SOP document UUIDs paired with their versions, with the first entry selected by default upon tab activation.
8. WHILE the training status request is in progress, THE Admin_Training_View SHALL display a loading skeleton matching the layout of the status summary and user-level breakdown sections.
9. IF the selected SOP version has zero assigned tasks (total_tasks is 0), THEN THE Admin_Training_View SHALL display an empty state message indicating no training tasks have been assigned for the selected SOP version.

### Requirement 7: Training Content Review (Admin)

**User Story:** As a training coordinator, I want to approve or reject AI-generated training content, so that I can ensure training materials are accurate and appropriate before they are presented to trainees.

#### Acceptance Criteria

1. THE Admin_Training_View SHALL include a "Content Review" section showing training content items with status "pending_review", accessible to users with administrator or coordinator roles. IF no content items have status "pending_review", THEN THE "Content Review" section SHALL display an empty state message indicating no items are awaiting review.
2. WHEN the coordinator selects a content item for review, THE Training_Content_Viewer SHALL display the full content (summary, quiz questions, procedural steps, safety points) with approve and reject action buttons.
3. WHEN the coordinator clicks "Approve", THE Training_Store SHALL send a POST request to `POST /api/training/content/{content_id}/approve` with the reviewer_id and optional notes (maximum 1000 characters) in the request body, and the change reason "Training content approved" in the `X-Change-Reason` header.
4. WHEN the coordinator clicks "Reject", THE Training_Store SHALL open a rejection dialog requiring a rejection reason (minimum 10 characters, maximum 1000 characters) with a character counter, then send a POST request to `POST /api/training/content/{content_id}/reject` with the reviewer_id and rejection notes in the request body, and the change reason "Training content rejected" in the `X-Change-Reason` header.
5. WHILE an approve or reject request is in progress, THE Training_Content_Viewer SHALL display a loading indicator on the activated action button and disable both the approve and reject buttons to prevent duplicate submissions.
6. WHEN the approve or reject request succeeds, THE Admin_Training_View SHALL update the content status in the list, display a success notification that auto-dismisses after 5 seconds, and remove the item from the pending review queue.
7. IF the approve or reject request returns a 400 error (content not in reviewable state), THEN THE Training_Store SHALL display the error detail message to the coordinator and re-enable the action buttons.
8. IF the approve or reject request returns a 404 error (content not found), THEN THE Training_Store SHALL display an error message and remove the stale item from the pending review list.
9. IF the approve or reject request fails due to a network error, THEN THE Training_Content_Viewer SHALL display an error message indicating the request could not be completed, retain the reviewer's notes, and re-enable the action buttons.

### Requirement 8: Training-Gated Access Enforcement in Frontend Routing

**User Story:** As a system, I want to block navigation to documents that require uncompleted training, so that untrained users cannot interact with regulated documents before completing their training.

#### Acceptance Criteria

1. WHEN a user attempts to navigate to a document detail page for a document whose SOP is in "InTraining" status, THE Training_Gate_Guard SHALL check the user's training completion status by querying the Training_Store for a completed task matching the document's `sop_document_uuid` and current `sop_version`. IF the Training_Store has not yet loaded training tasks (tasks array is empty and no prior fetch has completed), THEN THE Training_Gate_Guard SHALL trigger a fetchTrainingTasks call and display the loading indicator until the fetch completes before evaluating the gate.
2. IF the user has not completed training for the document's current SOP version, THEN THE Training_Gate_Guard SHALL block navigation, display a full-page informational message stating "Action denied: Valid training record for {SOP_Name} Version {version} is missing.", and provide a link to the Training_Dashboard to complete the pending task.
3. IF the user has completed training for the document's current SOP version (a completed task exists for the matching sop_document_uuid and sop_version), THEN THE Training_Gate_Guard SHALL allow navigation to proceed normally.
4. THE Training_Gate_Guard SHALL cache the user's training status in the Training_Store to avoid redundant API calls on repeated navigation attempts within the same browser session (until page refresh or user logout), invalidating the cache entry for the specific sop_document_uuid and sop_version when a training task matching those values is completed.
5. WHILE the training status check is in progress (including any required task fetch), THE Training_Gate_Guard SHALL display a loading indicator instead of the document content. IF the loading state persists for more than 10 seconds without a response, THEN THE Training_Gate_Guard SHALL treat the check as failed and display the network error state with a retry button.
6. IF the training status check fails due to a network error, THEN THE Training_Gate_Guard SHALL display an error message with a retry button, and SHALL NOT allow navigation to the document until the check succeeds. Each click of the retry button SHALL re-initiate the training status check from the beginning.
7. THE Training_Gate_Guard SHALL only enforce gating for documents whose associated SOP has a current status of "InTraining"; documents with SOPs in "Active", "Draft", or any other status SHALL pass through the guard without a training check.

### Requirement 9: Training Store (Zustand State Management)

**User Story:** As a developer, I want a centralized state store for training operations, so that training tasks, records, content, and gate status flow consistently across components.

#### Acceptance Criteria

1. THE Training_Store SHALL maintain state for: training tasks (tasks array, isLoadingTasks, tasksError, filter), task completion (isCompleting, completionError), training content (currentContent, isLoadingContent, contentError), statistics (pending count, completed count, total count, completion percentage), admin status (sopStatus, isLoadingStatus, statusError), content review (pendingReviewItems, isReviewing, reviewError), and gate status (gateCache mapping sop_document_uuid+version to boolean, isCheckingGate).
2. THE Training_Store SHALL expose actions for: fetchTrainingTasks(userId), completeTrainingTask(taskId, userId, changeReason), fetchTrainingContent(contentId), fetchTrainingStatus(sopUuid, version), approveContent(contentId, reviewerId, notes), rejectContent(contentId, reviewerId, notes), setFilter(filter), checkTrainingGate(sopDocumentUuid, sopVersion, userId), and clearGateCache().
3. WHEN fetchTrainingTasks is called, THE Training_Store SHALL set isLoadingTasks to true, clear tasksError, send a GET request to `/api/training/tasks?user_id={userId}`, store the response in the tasks array on success, compute statistics from the response, and set isLoadingTasks to false. IF the request fails, THEN THE store SHALL extract the error message from the ApiError body (parsed as JSON `detail` field, falling back to the error message string) and set tasksError to that value, then set isLoadingTasks to false.
4. WHEN completeTrainingTask is called, THE Training_Store SHALL set isCompleting to true, clear completionError, send a POST request to `/api/training/tasks/{taskId}/complete?user_id={userId}` with the changeReason in the `X-Change-Reason` header via apiClient's changeReason option, update the matching task in the local tasks array (setting `is_completed` to true and `completed_at` to the response value) on success, recompute statistics, invalidate the gate cache for the task's sop_document_uuid and sop_version, and set isCompleting to false.
5. WHEN checkTrainingGate is called, THE Training_Store SHALL first check the gateCache for an existing entry matching the sop_document_uuid and sop_version. IF a cached entry exists, THEN THE store SHALL return the cached value. IF no cached entry exists, THEN THE store SHALL check the local tasks array for a completed task matching the sop_document_uuid and sop_version, cache the result, and return it.
6. WHEN clearGateCache is called, THE Training_Store SHALL reset the gateCache to an empty mapping.
7. IF any API request initiated by the Training_Store fails, THEN THE Training_Store SHALL extract the error message from the ApiError body (parsed as JSON `detail` field, falling back to the error message string) and store it in the corresponding error state property, then set the corresponding loading flag to false.
8. WHEN fetchTrainingContent is called, THE Training_Store SHALL set isLoadingContent to true, clear contentError, send a GET request to `/api/training/content/{contentId}`, store the response in currentContent on success, and set isLoadingContent to false. IF the request fails, THEN THE store SHALL set contentError to the extracted error message and set isLoadingContent to false.
9. WHEN fetchTrainingStatus is called, THE Training_Store SHALL set isLoadingStatus to true, clear statusError, send a GET request to `/api/training/status/{sopUuid}/{version}`, store the response in sopStatus on success, and set isLoadingStatus to false. IF the request fails, THEN THE store SHALL set statusError to the extracted error message and set isLoadingStatus to false.
10. WHEN approveContent or rejectContent is called, THE Training_Store SHALL set isReviewing to true, clear reviewError, send the appropriate POST request with the reviewer_id and notes in the body and the change reason in the `X-Change-Reason` header, remove the content item from pendingReviewItems on success, and set isReviewing to false. IF the request fails, THEN THE store SHALL set reviewError to the extracted error message and set isReviewing to false.

### Requirement 10: Integration with Document Detail Page

**User Story:** As a user viewing a document, I want to see the training status for the document's SOP, so that I understand whether training is required or completed for this document.

#### Acceptance Criteria

1. WHEN the document detail page loads for a document whose SOP is in "InTraining" status, THE DocumentDetail component SHALL query the Training_Store for the user's training tasks matching the document's `sop_document_uuid` and `sop_version`, and display a training status banner below the document metadata showing: the SOP name, version requiring training, the user's personal completion status (completed or pending), and a "View Training" link navigating to the `/training` route.
2. IF the user has not completed training for the document's SOP version, THEN THE training status banner SHALL display with amber/warning styling and the text "Training required: You have not completed training for {SOP_Name} v{version}. Complete training to gain full access."
3. IF the user has completed training for the document's SOP version, THEN THE training status banner SHALL display with green/success styling and the text "Training complete: You have completed training for {SOP_Name} v{version}." followed by the completion date formatted in the user's locale.
4. IF the document's SOP is not in "InTraining" status, THEN THE document detail page SHALL NOT display the training status banner.
5. WHILE the Training_Store is loading training tasks needed to determine the banner state, THE DocumentDetail component SHALL display a skeleton placeholder in the banner area below the document metadata.
6. IF the training tasks fetch fails due to a network or server error, THEN THE training status banner area SHALL display an inline error message "Unable to load training status" with a retry button that re-invokes the Training_Store fetch.

### Requirement 11: Accessibility and Keyboard Navigation

**User Story:** As a user relying on assistive technology, I want the training management interface to be fully accessible, so that I can manage training tasks using keyboard navigation and screen readers.

#### Acceptance Criteria

1. THE Training_Dashboard SHALL use an ARIA landmark role of "main" with an accessible label "Training Management", and all interactive elements SHALL be reachable via the Tab key in a logical order (statistics cards, filter controls, task list, content viewer).
2. THE Training_Task_List filter controls SHALL be implemented as a radio group with role "radiogroup" and an accessible label "Filter training tasks by status", with each filter option having role "radio" and appropriate aria-checked state.
3. EACH Training_Task_Card SHALL have role "article" with an aria-label in the format "{task_title} - {status}" where status is "Pending" or "Completed", and the "Mark Complete" button SHALL have an aria-label "Mark training task complete: {task_title}".
4. WHILE the Task_Completion_Dialog is open, THE dialog SHALL trap focus so that Tab and Shift+Tab cycle only through focusable elements within the dialog. WHEN the dialog is closed, THE focus SHALL return to the "Mark Complete" button that triggered the dialog.
5. WHEN the user presses the Escape key while the Task_Completion_Dialog is open, THE dialog SHALL close without executing any completion action and return focus to the triggering button.
6. ALL loading states within the Training_Dashboard SHALL use aria-live regions with politeness level "polite" to announce status changes to screen readers: announcing "Loading {section_name}" when a request begins and "{section_name} loaded" when the request completes, where section_name corresponds to the component (e.g., "training tasks", "training content", "training statistics").
7. ALL focusable elements within the Training_Dashboard and Task_Completion_Dialog SHALL display a visible focus indicator with a minimum thickness of 2px that meets a minimum contrast ratio of 3:1 against adjacent colors.
8. THE Task_Completion_Dialog SHALL assign the dialog role with an aria-labelledby attribute referencing the dialog title and aria-describedby referencing the dialog content, and the change reason input SHALL have an associated label element.
9. THE Training_Content_Viewer quiz questions SHALL use fieldset and legend elements to group each question with its answer options, and each answer option SHALL be a labeled radio input.
10. THE Training_Gate_Guard blocking message SHALL use role "alert" to immediately announce the access denial to screen readers.
11. IF an error occurs within the Task_Completion_Dialog (validation failure, network error, or server error), THEN THE dialog SHALL announce the error message to screen readers using an aria-live region with politeness level "assertive", and focus SHALL move to the error message element.
12. ALL interactive elements within the Training_Content_Viewer (including "Reveal Answer" toggles and expandable sections) SHALL be operable via the Enter or Space key, and each toggle SHALL convey its expanded or collapsed state using aria-expanded.

### Requirement 12: Error Handling, Loading States, and Retry Patterns

**User Story:** As a user, I want consistent error handling and loading feedback across the training interface, so that I understand the system state and can recover from failures.

#### Acceptance Criteria

1. WHILE any API request is in progress within the Training_Dashboard, THE corresponding component SHALL display a loading skeleton that matches the layout of the expected content (task cards for task list, stats cards for statistics, content sections for content viewer).
2. IF an API request fails with a network error (no response received) or a request timeout (no response within 30 seconds), THEN THE corresponding component SHALL display an error message "Network error: Unable to reach the server. Please check your connection." with a retry button.
3. IF an API request fails with a server error (HTTP 500 or above), THEN THE corresponding component SHALL display an error message "Server error: Something went wrong. Please try again later." with a retry button.
4. IF an API request fails with a 403 error, THEN THE corresponding component SHALL display an error message "Access denied: You do not have permission to perform this action." without a retry button.
5. WHEN the user clicks a retry button, THE component SHALL clear the displayed error state, re-invoke the failed API request, and display the loading skeleton again.
6. THE Training_Store SHALL implement request deduplication: IF a fetch action is called while the same fetch is already in progress (isLoading flag is true), THEN THE store SHALL NOT initiate a duplicate request.
7. WHEN a success notification is displayed (after task completion, content approval, or content rejection), THE notification SHALL auto-dismiss after 5 seconds and SHALL include a manual dismiss button.
8. IF the `X-Change-Reason` header is rejected by the backend (HTTP 400 with "X-Change-Reason header is required"), THEN THE Training_Store SHALL display an inline error message within the originating dialog or component indicating that a change reason is required for this action, and SHALL retain any user-entered form data.
9. IF an API request fails with a 401 error after the API_Client token refresh attempt has been exhausted, THEN THE Training_Dashboard SHALL redirect the user to the login page.
