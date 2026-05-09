# Requirements Document

## Introduction

This feature implements a BPMN Workflow Visual Editor for AlcoaBase, enabling administrators to design, manage, and version document lifecycle workflows using a visual BPMN 2.0 editor (bpmn-js). The editor provides full CRUD operations for workflow definitions with version history tracking, risk-level metadata for risk-based pathing, and auto-assignment preparation fields for future AI-driven reviewer suggestions. The feature builds upon the existing backend WorkflowDefinition model, WorkflowEngine service, and workflow API endpoints, extending them with DELETE capability, versioning, risk metadata, and auto-assignment fields. The frontend replaces the current placeholder WorkflowsPage with a fully functional workflow management interface featuring an embedded bpmn-js canvas.

## Glossary

- **BPMN_Editor**: The bpmn-js library component embedded in the frontend that provides a visual canvas for designing BPMN 2.0 workflow diagrams with drag-and-drop elements, connection routing, and property editing.
- **Workflow_Store**: The Zustand state store managing workflow list state, CRUD operations, version history, and editor state for the workflow management interface.
- **Workflow_List_Page**: The React page component displaying all workflow definitions for the current tenant with status indicators, filtering, and navigation to the editor.
- **Workflow_Editor_Page**: The React page component containing the embedded BPMN_Editor canvas, workflow metadata form, and save/validate controls.
- **Workflow_API**: The FastAPI router at `/api/workflows` providing CRUD endpoints for workflow definitions, versioning, and validation.
- **WorkflowDefinition**: The SQLAlchemy model storing workflow metadata, BPMN XML, transition hooks, risk level, and auto-assignment configuration.
- **WorkflowDefinitionVersion**: The SQLAlchemy model storing historical versions of workflow definitions with version numbers, timestamps, and change reasons.
- **BPMN_XML**: A BPMN 2.0 compliant XML string defining workflow states (tasks), transitions (sequence flows), start events, and end events.
- **Risk_Level**: A classification (low, medium, high, critical) assigned to a workflow definition that determines the strictness of the review path for documents bound to that workflow.
- **Auto_Assignment_Config**: A JSON configuration on a workflow definition specifying rules for AI-driven reviewer/approver suggestions, referencing agent roles from the Agent Registry (Phase 5.1).
- **Version_History**: A chronological record of all changes to a workflow definition, including the BPMN XML, metadata changes, version number, author, and change reason.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and the X-Change-Reason audit header.
- **Transition_Hook**: A configured trigger on a specific state transition that requires either a PAdES signature (Phase 3.4) or training completion (Phase 3.3) before the transition is allowed.

## Requirements

### Requirement 1: Workflow List Page

**User Story:** As an administrator, I want to view all workflow definitions for my company, so that I can manage document lifecycle configurations and identify which workflows are active.

#### Acceptance Criteria

1. WHEN the user navigates to the workflows route, THE Workflow_List_Page SHALL fetch workflow definitions from `GET /api/workflows` and display them in a table sorted by name ascending, showing the workflow name, document tag, risk level, active status, and version number.
2. THE Workflow_List_Page SHALL display a "New Workflow" button that navigates to the Workflow_Editor_Page in creation mode.
3. WHEN the user clicks on a workflow row, THE Workflow_List_Page SHALL navigate to the Workflow_Editor_Page in edit mode with the selected workflow loaded.
4. WHILE the workflow list is loading, THE Workflow_List_Page SHALL display a loading indicator.
5. IF the workflow list request fails, THEN THE Workflow_List_Page SHALL display an error message with the failure reason and a retry button.
6. IF the workflow list response contains zero workflows, THEN THE Workflow_List_Page SHALL display an empty state message with a prompt to create the first workflow and the "New Workflow" button.
7. THE Workflow_List_Page SHALL display a visual indicator distinguishing active workflows from inactive workflows using distinct badge colors.
8. THE Workflow_List_Page SHALL display the risk level for each workflow using a color-coded badge (low: green, medium: yellow, high: orange, critical: red).

### Requirement 2: BPMN Visual Editor Integration

**User Story:** As an administrator, I want to design workflow diagrams visually using a BPMN editor, so that I can define document lifecycle states and transitions without writing XML manually.

#### Acceptance Criteria

1. WHEN the Workflow_Editor_Page loads in creation mode, THE BPMN_Editor SHALL render an empty BPMN canvas with a default start event and provide the BPMN element palette containing: start events, end events, tasks (user tasks, service tasks), gateways (exclusive, parallel), and sequence flows.
2. WHEN the Workflow_Editor_Page loads in edit mode, THE BPMN_Editor SHALL import and render the existing BPMN_XML from the loaded workflow definition onto the canvas within 3 seconds.
3. THE BPMN_Editor SHALL allow the user to add BPMN elements by dragging from the palette onto the canvas.
4. THE BPMN_Editor SHALL allow the user to connect elements by drawing sequence flows between them.
5. THE BPMN_Editor SHALL allow the user to select elements and edit their properties (name, id) via a properties panel or inline editing.
6. THE BPMN_Editor SHALL allow the user to delete selected elements from the canvas.
7. THE BPMN_Editor SHALL allow the user to move and reposition elements on the canvas using drag interactions.
8. WHEN the user modifies the diagram, THE BPMN_Editor SHALL export the current diagram state as valid BPMN 2.0 XML accessible to the Workflow_Store for saving.
9. THE BPMN_Editor SHALL provide zoom controls (zoom in, zoom out, fit to viewport) for navigating large diagrams.
10. THE BPMN_Editor SHALL provide an undo and redo capability for diagram modifications.

### Requirement 3: Workflow Metadata Form

**User Story:** As an administrator, I want to configure workflow metadata alongside the visual diagram, so that I can set the workflow name, document tag binding, risk level, and transition hooks in one interface.

#### Acceptance Criteria

1. THE Workflow_Editor_Page SHALL display a metadata form alongside the BPMN canvas containing fields for: workflow name (text input, required, max 200 characters), document tag (text input, required, max 100 characters), risk level (select dropdown with options: low, medium, high, critical), and active status (toggle).
2. WHEN the Workflow_Editor_Page loads in edit mode, THE metadata form SHALL pre-populate all fields with the current workflow definition values.
3. THE Workflow_Editor_Page SHALL display a "Signature Required Transitions" section listing all transitions extracted from the current BPMN diagram, each with a checkbox to mark it as requiring a PAdES signature.
4. THE Workflow_Editor_Page SHALL display a "Training Trigger Transitions" section listing all transitions extracted from the current BPMN diagram, each with a checkbox to mark it as triggering training assignment.
5. WHEN the BPMN diagram changes (elements added, removed, or renamed), THE transition lists in the Signature Required and Training Trigger sections SHALL update to reflect the current set of transitions in the diagram.
6. WHEN the user moves focus away from the workflow name field with an empty value, THE metadata form SHALL display a validation error indicating the name is required.
7. WHEN the user moves focus away from the document tag field with an empty value, THE metadata form SHALL display a validation error indicating the document tag is required.

### Requirement 4: Workflow Auto-Assignment Configuration

**User Story:** As an administrator, I want to configure auto-assignment rules on a workflow, so that the system can suggest appropriate reviewers and approvers based on document content when the Agent Registry (Phase 5.1) is available.

#### Acceptance Criteria

1. THE Workflow_Editor_Page SHALL display an "Auto-Assignment Configuration" section with a JSON editor field for defining assignment rules.
2. THE Auto-Assignment Configuration section SHALL display a descriptive label indicating that auto-assignment rules will be activated when the Agent Registry (Phase 5.1) is integrated.
3. WHEN the user enters JSON in the auto-assignment configuration field, THE Workflow_Editor_Page SHALL validate that the input is syntactically valid JSON before allowing save.
4. IF the auto-assignment configuration contains invalid JSON syntax, THEN THE Workflow_Editor_Page SHALL display a validation error indicating the JSON is malformed and prevent form submission.
5. THE Workflow_Editor_Page SHALL allow the auto-assignment configuration field to be empty (null), indicating no auto-assignment rules are configured.

### Requirement 5: Save Workflow (Create and Update)

**User Story:** As an administrator, I want to save my workflow design, so that the BPMN diagram and metadata are persisted and available for document lifecycle enforcement.

#### Acceptance Criteria

1. WHEN the user clicks "Save" on a new workflow with all required fields valid, THE Workflow_Store SHALL send a POST request to `POST /api/workflows` with the workflow name, document tag, BPMN XML exported from the editor, risk level, signature required transitions, training trigger transitions, and auto-assignment configuration, including the `X-Change-Reason` header with the value "Workflow created: {workflow_name}".
2. WHEN the user clicks "Save" on an existing workflow with modifications, THE Workflow_Store SHALL send a PUT request to `PUT /api/workflows/{workflow_id}` with the updated fields, including the `X-Change-Reason` header with the value "Workflow updated: {workflow_name}".
3. WHILE the save request is in progress, THE Workflow_Editor_Page SHALL display a loading indicator on the save button and disable the save button to prevent duplicate submissions.
4. WHEN the backend returns a successful response (201 for create, 200 for update), THE Workflow_Editor_Page SHALL display a success notification and update the local state with the response data.
5. IF the backend returns a 400 error with validation errors (invalid BPMN, duplicate document tag, invalid transitions), THEN THE Workflow_Editor_Page SHALL display the validation error messages returned by the backend and re-enable the save button.
6. IF the save request fails due to a network error, THEN THE Workflow_Editor_Page SHALL display an error notification and re-enable the save button.
7. WHEN creating a new workflow successfully, THE Workflow_Editor_Page SHALL transition from creation mode to edit mode with the newly assigned workflow ID.

### Requirement 6: Validate Workflow

**User Story:** As an administrator, I want to validate my BPMN diagram before saving, so that I can identify structural issues like unreachable states or missing terminal states early.

#### Acceptance Criteria

1. THE Workflow_Editor_Page SHALL display a "Validate" button that triggers client-side and server-side validation of the current BPMN diagram.
2. WHEN the user clicks "Validate", THE Workflow_Store SHALL send a POST request to `POST /api/workflows/validate` with the current BPMN XML and signature required transitions, including the `X-Change-Reason` header with the value "Workflow validation requested".
3. WHEN the backend returns a validation response with is_valid set to true, THE Workflow_Editor_Page SHALL display a success message indicating the workflow is valid.
4. WHEN the backend returns a validation response with is_valid set to false, THE Workflow_Editor_Page SHALL display each validation error message from the errors array in a visible error list.
5. WHILE the validation request is in progress, THE Workflow_Editor_Page SHALL display a loading indicator on the validate button.
6. IF the validation request fails due to a network error, THEN THE Workflow_Editor_Page SHALL display an error notification indicating validation could not be completed.

### Requirement 7: Delete Workflow

**User Story:** As an administrator, I want to delete a workflow definition that is no longer needed, so that obsolete workflows do not clutter the management interface.

#### Acceptance Criteria

1. THE Workflow_Editor_Page SHALL display a "Delete" button when in edit mode for an existing workflow.
2. WHEN the user clicks "Delete", THE Workflow_Editor_Page SHALL display a confirmation dialog stating the workflow name and warning that deletion is permanent.
3. WHEN the user confirms deletion, THE Workflow_Store SHALL send a DELETE request to `DELETE /api/workflows/{workflow_id}` with the `X-Change-Reason` header set to "Workflow deleted: {workflow_name}".
4. WHEN the backend returns a successful response (204), THE Workflow_Editor_Page SHALL display a success notification and navigate back to the Workflow_List_Page.
5. IF the backend returns a 409 error indicating the workflow has active document states, THEN THE Workflow_Editor_Page SHALL display an error message indicating the workflow cannot be deleted because documents are currently using it.
6. IF the backend returns a 404 error, THEN THE Workflow_Editor_Page SHALL display an error message indicating the workflow was not found and navigate back to the Workflow_List_Page.
7. IF the delete request fails due to a network error, THEN THE Workflow_Editor_Page SHALL display an error notification and close the confirmation dialog.
8. THE Workflow_List_Page SHALL NOT display a delete action; deletion is only available from within the Workflow_Editor_Page to prevent accidental bulk deletions.

### Requirement 8: Workflow Versioning

**User Story:** As an administrator, I want to track all changes to workflow definitions over time, so that I can review the history of modifications and restore previous versions if needed.

#### Acceptance Criteria

1. WHEN a workflow definition is created, THE Workflow_API SHALL create a corresponding WorkflowDefinitionVersion record with version number 1, the initial BPMN XML, metadata snapshot, creating user ID, and the change reason from the X-Change-Reason header.
2. WHEN a workflow definition is updated, THE Workflow_API SHALL create a new WorkflowDefinitionVersion record with an incremented version number, the updated BPMN XML, metadata snapshot, updating user ID, and the change reason from the X-Change-Reason header.
3. THE Workflow_Editor_Page SHALL display a "Version History" panel showing all versions of the current workflow, listing for each version: version number, timestamp, author (user who made the change), and change reason.
4. WHEN the user selects a version from the history panel, THE Workflow_Editor_Page SHALL load that version's BPMN XML into the BPMN_Editor canvas in a read-only preview mode, clearly indicating the user is viewing a historical version.
5. WHEN the user clicks "Restore" on a historical version, THE Workflow_Store SHALL send a PUT request to `PUT /api/workflows/{workflow_id}` with the historical version's BPMN XML and metadata, including the `X-Change-Reason` header set to "Restored to version {version_number}".
6. THE Workflow_API SHALL expose a `GET /api/workflows/{workflow_id}/versions` endpoint returning all versions for a workflow definition ordered by version number descending.
7. THE Workflow_API SHALL expose a `GET /api/workflows/{workflow_id}/versions/{version_id}` endpoint returning a single version's full data including the BPMN XML.
8. WHILE the version history is loading, THE Workflow_Editor_Page SHALL display a loading indicator in the version history panel.
9. IF the version history request fails, THEN THE Workflow_Editor_Page SHALL display an error message in the version history panel with a retry button.

### Requirement 9: Risk-Based Workflow Pathing

**User Story:** As an administrator, I want to assign risk levels to workflows, so that high-risk documents automatically trigger stricter review paths with additional review cycles.

#### Acceptance Criteria

1. THE WorkflowDefinition model SHALL include a risk_level field accepting values: "low", "medium", "high", or "critical", defaulting to "low".
2. WHEN a workflow has risk_level set to "high" or "critical", THE Workflow_Editor_Page SHALL display a visual warning indicator next to the risk level selector reminding the administrator that documents bound to this workflow will require additional review cycles.
3. THE Workflow_API SHALL accept and persist the risk_level field on create and update operations.
4. THE Workflow_API SHALL return the risk_level field in all workflow response payloads.
5. THE Workflow_List_Page SHALL allow filtering workflows by risk level using a dropdown filter.
6. WHEN the risk_level is set to "high" or "critical", THE Workflow_Editor_Page SHALL display a recommendation section suggesting that the workflow include at least two sequential review states before an approval state.

### Requirement 10: Backend Delete Endpoint

**User Story:** As a frontend developer, I want a backend endpoint to delete workflow definitions, so that administrators can remove obsolete workflows.

#### Acceptance Criteria

1. THE Workflow_API SHALL expose a `DELETE /api/workflows/{workflow_id}` endpoint that accepts an integer path parameter `workflow_id`.
2. WHEN the workflow exists and belongs to the tenant identified by the `X-Company-Id` header, THE Workflow_API SHALL delete the workflow definition and return a 204 response with no body.
3. IF the workflow does not exist, THEN THE Workflow_API SHALL return a 404 response with a detail message indicating the workflow was not found.
4. IF the workflow belongs to a different tenant than the one identified by the `X-Company-Id` header, THEN THE Workflow_API SHALL return a 404 response indistinguishable from the not-found response.
5. IF documents currently have active states referencing the workflow (DocumentState records with workflow_id matching the target), THEN THE Workflow_API SHALL return a 409 response with a detail message indicating the workflow cannot be deleted because it is in use.
6. WHEN a workflow is deleted, THE Workflow_API SHALL also delete all associated WorkflowDefinitionVersion records.
7. THE Workflow_API SHALL require the `X-Change-Reason` header on the DELETE request for audit compliance.

### Requirement 11: Backend Versioning Endpoints

**User Story:** As a frontend developer, I want backend endpoints to retrieve workflow version history, so that the version history panel can display and restore previous versions.

#### Acceptance Criteria

1. THE Workflow_API SHALL expose a `GET /api/workflows/{workflow_id}/versions` endpoint returning a JSON array of all WorkflowDefinitionVersion records for the specified workflow, ordered by version number descending.
2. Each version record in the response SHALL include: id, version_number, bpmn_xml, name, document_tag, risk_level, signature_required_transitions, training_trigger_transitions, auto_assignment_config, created_by, created_at, and change_reason.
3. THE Workflow_API SHALL expose a `GET /api/workflows/{workflow_id}/versions/{version_id}` endpoint returning a single WorkflowDefinitionVersion record with all fields.
4. IF the workflow does not exist or belongs to a different tenant, THEN THE version endpoints SHALL return a 404 response.
5. IF the version does not exist or does not belong to the specified workflow, THEN THE single version endpoint SHALL return a 404 response.
6. THE version list endpoint SHALL scope results to the tenant identified by the `X-Company-Id` header.

### Requirement 12: Backend Validation Endpoint

**User Story:** As a frontend developer, I want a dedicated validation endpoint, so that the editor can validate BPMN diagrams without creating or updating a workflow.

#### Acceptance Criteria

1. THE Workflow_API SHALL expose a `POST /api/workflows/validate` endpoint accepting a JSON body with: bpmn_xml (string, required) and signature_required_transitions (array of strings, optional).
2. WHEN the BPMN XML is valid with no structural issues, THE validation endpoint SHALL return a 200 response with is_valid set to true and an empty errors array.
3. WHEN the BPMN XML has structural issues (unreachable states, no terminal states, no initial state, invalid transition references), THE validation endpoint SHALL return a 200 response with is_valid set to false and the errors array populated with descriptive messages.
4. IF the bpmn_xml field is empty or missing, THEN THE validation endpoint SHALL return a 422 response indicating a validation error.
5. THE validation endpoint SHALL require the `X-Change-Reason` header for audit compliance.

### Requirement 13: Backend Model Extensions

**User Story:** As a developer, I want the WorkflowDefinition model extended with risk level, auto-assignment config, and a version history table, so that the system supports risk-based pathing and change tracking.

#### Acceptance Criteria

1. THE WorkflowDefinition model SHALL include a `risk_level` column of type String(20) with a default value of "low" and a CHECK constraint limiting values to "low", "medium", "high", or "critical".
2. THE WorkflowDefinition model SHALL include an `auto_assignment_config` column of type JSON, nullable, defaulting to null.
3. THE WorkflowDefinitionVersion model SHALL include columns: id (primary key), workflow_id (foreign key to workflow_definitions), version_number (integer), bpmn_xml (text), name (string 200), document_tag (string 100), risk_level (string 20), signature_required_transitions (JSON), training_trigger_transitions (JSON), auto_assignment_config (JSON nullable), created_by (foreign key to users), created_at (datetime with timezone, server default now), and change_reason (string 500).
4. THE WorkflowDefinitionVersion model SHALL have a unique constraint on (workflow_id, version_number) to prevent duplicate version numbers within a workflow.
5. THE database migration SHALL add the risk_level and auto_assignment_config columns to the existing workflow_definitions table without data loss.
6. THE database migration SHALL create the workflow_definition_versions table.

### Requirement 14: Workflow Store State Management

**User Story:** As a developer, I want a centralized state store for workflow operations, so that workflow data flows consistently across the list page, editor page, and version history panel.

#### Acceptance Criteria

1. THE Workflow_Store SHALL maintain state for: workflow list (array of workflows), current workflow (single workflow detail), editor dirty state (boolean indicating unsaved changes), loading flags (isLoadingList, isLoadingDetail, isSaving, isValidating, isDeleting, isLoadingVersions), error state (listError, detailError, saveError, validateError, deleteError, versionsError), validation result, and version history (array of versions).
2. THE Workflow_Store SHALL expose actions for: fetchWorkflowList, fetchWorkflowDetail, createWorkflow, updateWorkflow, deleteWorkflow, validateWorkflow, fetchVersionHistory, and fetchVersion.
3. WHEN createWorkflow is called, THE Workflow_Store SHALL set isSaving to true, clear saveError, send a POST request to `/api/workflows` with the workflow payload and `X-Change-Reason` header, set the current workflow state to the response on success, and set isSaving to false.
4. WHEN updateWorkflow is called, THE Workflow_Store SHALL set isSaving to true, clear saveError, send a PUT request to `/api/workflows/{workflow_id}` with the updated payload and `X-Change-Reason` header, update the current workflow state with the response on success, and set isSaving to false.
5. WHEN deleteWorkflow is called, THE Workflow_Store SHALL set isDeleting to true, clear deleteError, send a DELETE request to `/api/workflows/{workflow_id}` with the `X-Change-Reason` header, remove the workflow from the list state on success, and set isDeleting to false.
6. WHEN validateWorkflow is called, THE Workflow_Store SHALL set isValidating to true, clear validateError, send a POST request to `/api/workflows/validate` with the BPMN XML and `X-Change-Reason` header, set the validation result state to the response, and set isValidating to false.
7. IF any API request initiated by the Workflow_Store fails, THEN THE Workflow_Store SHALL store the error message string from the ApiError in the corresponding error state property and set the corresponding loading flag to false.
8. THE Workflow_Store SHALL track editor dirty state by comparing the current BPMN XML and metadata against the last saved values, setting dirty to true when differences exist.
9. WHEN the user attempts to navigate away from the Workflow_Editor_Page with unsaved changes (dirty state is true), THE Workflow_Editor_Page SHALL display a confirmation dialog warning about unsaved changes.

### Requirement 15: Frontend Routing Integration

**User Story:** As a user, I want to navigate to workflow pages using standard URL routes, so that I can bookmark and share links to specific workflows.

#### Acceptance Criteria

1. THE application router SHALL register the route `/workflows` within the authenticated route guard, rendering the Workflow_List_Page.
2. THE application router SHALL register the route `/workflows/new` rendering the Workflow_Editor_Page in creation mode.
3. THE application router SHALL register the route `/workflows/:workflowId` rendering the Workflow_Editor_Page in edit mode, ordered after the `/workflows/new` route to prevent "new" from matching as a workflowId parameter.
4. THE application router SHALL register the route `/workflows/:workflowId/versions` rendering the Workflow_Editor_Page with the version history panel open.
5. THE existing navigation sidebar "Workflows" link SHALL point to the `/workflows` route.
6. WHEN the user navigates directly to a workflow route via URL, THE application router SHALL render the corresponding page component with the route parameters extracted from the URL.

### Requirement 16: BPMN XML Serialization Round-Trip

**User Story:** As a developer, I want BPMN XML to survive save and reload without data loss, so that workflow diagrams maintain their visual layout and structural integrity across sessions.

#### Acceptance Criteria

1. FOR ALL valid BPMN XML produced by the BPMN_Editor, saving to the backend via `POST /api/workflows` or `PUT /api/workflows/{workflow_id}` and then loading via `GET /api/workflows/{workflow_id}` SHALL return BPMN XML that, when parsed by the WorkflowEngine, produces an equivalent BPMNWorkflow (same states, same transitions, same initial state, same terminal states).
2. THE BPMN_Editor SHALL preserve diagram layout information (element positions, connection waypoints) in the exported BPMN XML using BPMN DI (Diagram Interchange) elements.
3. WHEN the BPMN_Editor imports previously saved BPMN XML, THE BPMN_Editor SHALL restore element positions and connection routing from the BPMN DI elements in the XML.
4. THE backend SHALL store and return BPMN XML without modification, transformation, or truncation.

### Requirement 17: Workflow Schema Extensions for API

**User Story:** As a frontend developer, I want the workflow API request and response schemas to include the new fields (risk level, auto-assignment config, version info), so that the frontend can read and write all workflow properties.

#### Acceptance Criteria

1. THE WorkflowCreateRequest schema SHALL include optional fields: risk_level (string, default "low", constrained to "low"|"medium"|"high"|"critical") and auto_assignment_config (JSON object or null).
2. THE WorkflowUpdateRequest schema SHALL include optional fields: risk_level (string or null) and auto_assignment_config (JSON object or null).
3. THE WorkflowResponse schema SHALL include fields: risk_level (string), auto_assignment_config (JSON object or null), and current_version_number (integer).
4. THE Workflow_API SHALL return a WorkflowVersionResponse schema for version endpoints containing: id, version_number, bpmn_xml, name, document_tag, risk_level, signature_required_transitions, training_trigger_transitions, auto_assignment_config, created_by, created_at, and change_reason.
