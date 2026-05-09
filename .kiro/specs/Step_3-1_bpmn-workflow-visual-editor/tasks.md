# Implementation Plan: BPMN Workflow Visual Editor

## Overview

This plan implements a visual BPMN workflow editor for AlcoaBase. The implementation proceeds in layers: backend model extensions and migration first, then API endpoint additions, followed by frontend state management, and finally the UI components with bpmn-js integration. Each task builds incrementally on the previous, ensuring no orphaned code.

## Tasks

- [x] 1. Backend model extensions and database migration
  - [x] 1.1 Add `risk_level`, `auto_assignment_config`, and `current_version` columns to WorkflowDefinition model
    - Add `risk_level: Mapped[str] = mapped_column(String(20), default="low")` with CHECK constraint for "low"|"medium"|"high"|"critical"
    - Add `auto_assignment_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)`
    - Add `current_version: Mapped[int] = mapped_column(default=1)`
    - File: `src/backend/src/alcoabase/models/workflow.py`
    - _Requirements: 13.1, 13.2, 9.1_

  - [x] 1.2 Create WorkflowVersion model
    - Create `WorkflowVersion` class in `src/backend/src/alcoabase/models/workflow.py`
    - Include columns: id, workflow_id (FK), version_number, bpmn_xml (Text), name (String 200), document_tag (String 100), risk_level (String 20), signature_required_transitions (JSON), training_trigger_transitions (JSON), auto_assignment_config (JSON nullable), created_by (FK to users), created_at (DateTime with timezone, server_default=func.now()), change_reason (String 500), company_id (FK to companies)
    - Add UniqueConstraint on (workflow_id, version_number)
    - Register model in `src/backend/src/alcoabase/models/__init__.py`
    - _Requirements: 13.3, 13.4_

  - [x] 1.3 Create Alembic migration for model changes
    - Generate migration with `uv run alembic revision --autogenerate -m "add_workflow_versioning_and_risk_level"`
    - Migration adds `risk_level` and `auto_assignment_config` columns to `workflow_definitions` table
    - Migration creates `workflow_versions` table with unique constraint
    - Migration backfills existing workflows: creates version 1 record for each existing WorkflowDefinition
    - File: `src/backend/alembic/versions/` (new migration file)
    - _Requirements: 13.5, 13.6_

- [x] 2. Backend API schema extensions
  - [x] 2.1 Extend workflow Pydantic schemas
    - Add `risk_level` (str, default "low", constrained) and `auto_assignment_config` (dict | None) to `WorkflowCreateRequest`
    - Add `risk_level` (str | None) and `auto_assignment_config` (dict | None) to `WorkflowUpdateRequest`
    - Add `risk_level` (str), `auto_assignment_config` (dict | None), and `current_version_number` (int) to `WorkflowResponse`
    - Create `WorkflowVersionSummary` schema (version_number, created_by, created_at, change_reason)
    - Create `WorkflowVersionDetail` schema (version_number, bpmn_xml, name, document_tag, risk_level, signature_required_transitions, training_trigger_transitions, auto_assignment_config, created_by, created_at, change_reason)
    - File: `src/backend/src/alcoabase/schemas/workflow.py`
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

- [x] 3. Backend API endpoint additions and tenant scoping fixes
  - [x] 3.1 Add GET /api/workflows/{workflow_id} endpoint
    - Return single workflow by ID, scoped to tenant via `X-Company-Id`
    - Return 404 if not found or belongs to different tenant (indistinguishable responses)
    - Include `risk_level`, `auto_assignment_config`, `current_version_number` in response
    - File: `src/backend/src/alcoabase/api/workflows.py`
    - _Requirements: 8.7, 16.4_

  - [x] 3.2 Add DELETE /api/workflows/{workflow_id} endpoint
    - Accept integer path parameter `workflow_id`
    - Scope to tenant via `X-Company-Id` header
    - Check for active DocumentState records referencing the workflow; return 409 if in use
    - Delete all associated WorkflowVersion records, then delete the workflow
    - Return 204 on success, 404 if not found or wrong tenant
    - Require `X-Change-Reason` header (enforced by AuditMiddleware)
    - File: `src/backend/src/alcoabase/api/workflows.py`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [x] 3.3 Add GET /api/workflows/{workflow_id}/versions endpoint
    - Return JSON array of WorkflowVersionSummary records ordered by version_number descending
    - Scope to tenant via `X-Company-Id`; return 404 if workflow not found or wrong tenant
    - File: `src/backend/src/alcoabase/api/workflows.py`
    - _Requirements: 11.1, 11.2, 11.6_

  - [x] 3.4 Add GET /api/workflows/{workflow_id}/versions/{version_id} endpoint
    - Return single WorkflowVersionDetail with all fields including bpmn_xml
    - Return 404 if version not found or does not belong to specified workflow
    - Scope to tenant
    - File: `src/backend/src/alcoabase/api/workflows.py`
    - _Requirements: 11.3, 11.4, 11.5_

  - [x] 3.5 Add POST /api/workflows/validate endpoint
    - Accept JSON body with `bpmn_xml` (required) and `signature_required_transitions` (optional array)
    - Return 200 with `{is_valid: true, errors: []}` or `{is_valid: false, errors: [...]}`
    - Return 422 if bpmn_xml is empty or missing
    - Require `X-Change-Reason` header
    - File: `src/backend/src/alcoabase/api/workflows.py`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 3.6 Fix tenant scoping on existing endpoints (POST, PUT, GET list)
    - POST: Set `company_id=tenant.company_id` and `created_by=tenant.user_id` on created workflow; create WorkflowVersion record (version 1)
    - PUT: Add tenant scoping filter (`company_id == tenant.company_id`); create new WorkflowVersion on structural changes (bpmn_xml, transitions); increment `current_version`
    - GET list: Add `.where(WorkflowDefinition.company_id == tenant.company_id)` filter
    - Update all response constructions to include `risk_level`, `auto_assignment_config`, `current_version_number`
    - File: `src/backend/src/alcoabase/api/workflows.py`
    - _Requirements: 8.1, 8.2, 5.1, 5.2, 9.3, 9.4_

- [x] 4. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Frontend: Install bpmn-js and create workflow store
  - [x] 5.1 Install bpmn-js dependency
    - Add `bpmn-js` package to `src/frontend/package.json` dependencies
    - Add `@types/bpmn-js` if available, or create local type declarations
    - _Requirements: 2.1_

  - [x] 5.2 Create workflowStore (Zustand)
    - Create `src/frontend/src/stores/workflowStore.ts`
    - Implement state: workflows array, currentWorkflow, bpmnXml, workflowName, documentTag, riskLevel, signatureRequiredTransitions, trainingTriggerTransitions, autoAssignmentConfig, isDirty, loading flags (isLoadingList, isLoadingDetail, isSaving, isValidating, isDeleting, isLoadingVersions), error states, validationResult, versions array, selectedVersion
    - Implement actions: fetchWorkflowList, fetchWorkflowDetail, createWorkflow, updateWorkflow, deleteWorkflow, validateWorkflow, fetchVersionHistory, fetchVersion, setBpmnXml, setWorkflowName, setDocumentTag, setRiskLevel, setSignatureTransitions, setTrainingTransitions, setAutoAssignmentConfig, clearValidation, resetEditor, restoreVersion
    - Use `apiClient` for all API calls with proper `X-Change-Reason` headers
    - Track dirty state by comparing current values against last-saved values
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9_

  - [x] 5.3 Write property tests for workflowStore
    - **Property 5: Store dirty flag and validation clearing**
    - **Property 11: Version restore sets editor state**
    - Use fast-check to generate arbitrary XML strings, workflow names, transitions
    - Verify setBpmnXml sets isDirty=true and clears validationErrors
    - Verify restoreVersion sets bpmnXml, transitions, and isDirty=true
    - File: `src/frontend/src/stores/__tests__/workflowStore.property.test.ts`
    - **Validates: Requirements 14.8, 14.9**

- [x] 6. Frontend: BpmnEditor component
  - [x] 6.1 Create custom palette provider module
    - Create `src/frontend/src/components/workflows/customPalette.ts`
    - Restrict palette to: Start Event, End Event, Task, Sequence Flow (connect tool), Space tool, Lasso tool
    - Export as bpmn-js additional module
    - _Requirements: 2.1, 2.3_

  - [x] 6.2 Create BPMN moddle extension definition
    - Create `src/frontend/src/components/workflows/alcoaExtension.json`
    - Define `alcoa:RiskLevel` and `alcoa:AutoAssignment` extension element types
    - URI: `http://alcoa.io/bpmn/extensions`
    - _Requirements: 9.1, 4.1_

  - [x] 6.3 Implement BpmnEditor component
    - Create `src/frontend/src/components/workflows/BpmnEditor.tsx`
    - Props: `initialXml`, `onXmlChange`, `onTransitionsChange`, `readOnly`
    - Mount bpmn-js Modeler (or Viewer if readOnly) on a div ref
    - Configure custom palette provider and alcoa moddle extension
    - Register `commandStack.changed` listener to export XML and extract transitions
    - Extract transitions as `"SourceTaskName→TargetTaskName"` strings from sequence flows between tasks
    - Handle `importXML` on mount and when `initialXml` prop changes
    - Provide zoom controls (zoom in, zoom out, fit to viewport)
    - Clean up bpmn-js instance on unmount
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [x] 6.4 Write property tests for BPMN validation utilities
    - **Property 4: Client-side BPMN pre-validation**
    - Create `src/frontend/src/lib/bpmnValidation.ts` with client-side pre-validation function
    - Create `src/frontend/src/lib/__tests__/bpmnValidation.property.test.ts`
    - Use fast-check to generate BPMN XML variants missing Start Event, End Event, or Task
    - Verify correct error messages for each missing element type
    - **Validates: Requirements 6.1, 6.4**

- [x] 7. Frontend: Editor page panels
  - [x] 7.1 Create MetadataForm component
    - Create `src/frontend/src/components/workflows/MetadataForm.tsx`
    - Fields: workflow name (text, required, max 200), document tag (text, required, max 100), risk level (select: low/medium/high/critical), active status (toggle)
    - Pre-populate fields from store's currentWorkflow in edit mode
    - Validate required fields on blur with inline error messages
    - Connect to workflowStore actions (setWorkflowName, setDocumentTag, setRiskLevel)
    - _Requirements: 3.1, 3.2, 3.6, 3.7_

  - [x] 7.2 Create TransitionConfigPanel component
    - Create `src/frontend/src/components/workflows/TransitionConfigPanel.tsx`
    - Display list of transitions extracted from BPMN diagram
    - Each transition has checkboxes for "Signature Required" and "Training Trigger"
    - Update store's signatureRequiredTransitions and trainingTriggerTransitions on toggle
    - Auto-update when transitions change (via onTransitionsChange callback from BpmnEditor)
    - _Requirements: 3.3, 3.4, 3.5_

  - [x] 7.3 Write property tests for transition toggle logic
    - **Property 3: Transition toggle set membership**
    - Create `src/frontend/src/components/workflows/__tests__/transitionToggle.property.test.ts`
    - Use fast-check to generate arbitrary transition strings and initial arrays
    - Verify toggling on adds the transition, toggling off removes it, other elements unchanged
    - **Validates: Requirements 3.3, 3.4**

  - [x] 7.4 Create RiskConfigPanel component
    - Create `src/frontend/src/components/workflows/RiskConfigPanel.tsx`
    - Display visual warning when risk_level is "high" or "critical"
    - Display recommendation for at least two sequential review states before approval
    - _Requirements: 9.2, 9.6_

  - [x] 7.5 Create AutoAssignmentPanel component
    - Create `src/frontend/src/components/workflows/AutoAssignmentPanel.tsx`
    - JSON editor field for auto-assignment rules
    - Descriptive label about Phase 5.1 Agent Registry integration
    - Validate JSON syntax before allowing save; show error for malformed JSON
    - Allow empty/null value
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 7.6 Create VersionHistoryPanel component
    - Create `src/frontend/src/components/workflows/VersionHistoryPanel.tsx`
    - Display list of versions: version number, timestamp, author, change reason
    - Loading indicator while fetching
    - Error state with retry button
    - Click version to load into BpmnEditor in read-only preview mode
    - "Restore" button on historical versions that calls store's restoreVersion
    - _Requirements: 8.3, 8.4, 8.5, 8.8, 8.9_

- [x] 8. Frontend: Page components and routing
  - [x] 8.1 Create WorkflowListPage component
    - Create `src/frontend/src/pages/WorkflowListPage.tsx`
    - Fetch workflows from store on mount; display in table sorted by name ascending
    - Columns: name, document_tag, risk level (color-coded badge), active status (badge), version number
    - "New Workflow" button navigating to `/workflows/new`
    - Click row navigates to `/workflows/:workflowId/edit`
    - Loading indicator, error state with retry, empty state with prompt
    - Risk level filter dropdown
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 9.5_

  - [x] 8.2 Create WorkflowEditorPage component
    - Create `src/frontend/src/pages/WorkflowEditorPage.tsx`
    - Accept mode prop ("create" | "edit") or derive from route params
    - Compose: MetadataForm, BpmnEditor, TransitionConfigPanel, RiskConfigPanel, AutoAssignmentPanel, VersionHistoryPanel (hidden in create mode)
    - Save button: calls createWorkflow or updateWorkflow from store; shows loading state; disables during save
    - Validate button: calls validateWorkflow; shows results
    - Delete button (edit mode only): confirmation dialog, calls deleteWorkflow, navigates to list on success
    - Handle 400, 404, 409 error responses with appropriate messages
    - Transition from create to edit mode on successful creation
    - Unsaved changes protection: useBlocker + beforeunload event
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 8.3 Update App.tsx routing
    - Replace single `/workflows` route with:
      - `/workflows` → WorkflowListPage
      - `/workflows/new` → WorkflowEditorPage (mode="create")
      - `/workflows/:workflowId/edit` → WorkflowEditorPage (mode="edit")
    - Ensure `/workflows/new` is ordered before `:workflowId` to prevent "new" matching as param
    - Remove old WorkflowsPage import
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 9. Checkpoint - Frontend integration complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Backend property-based tests
  - [x] 10.1 Write property test for BPMN XML parsing consistency
    - **Property 1: BPMN XML state and transition extraction consistency**
    - Use hypothesis to generate valid BPMN XML with varying numbers of tasks and sequence flows
    - Verify parse_bpmn_xml extracts same states/transitions regardless of element ordering
    - File: `src/backend/tests/properties/test_workflow_engine_property.py`
    - **Validates: Requirements 16.1**

  - [x] 10.2 Write property test for backend validation rejects invalid workflows
    - **Property 8: Backend validation rejects invalid workflows**
    - Use hypothesis to generate BPMN XML with unreachable states
    - Verify validate_bpmn_workflow returns is_valid=False with "unreachable" error
    - Generate invalid signature_required_transitions referencing non-existent transitions
    - Verify validation returns is_valid=False with appropriate error
    - File: `src/backend/tests/properties/test_workflow_engine_property.py`
    - **Validates: Requirements 12.2, 12.3**

  - [x] 10.3 Write property test for version increment on structural changes only
    - **Property 10: Version increment on structural changes only**
    - Use hypothesis to generate update payloads with/without structural changes
    - Verify version increments only when bpmn_xml or transitions change
    - Verify metadata-only changes (name, is_active) do not create new versions
    - File: `src/backend/tests/properties/test_workflow_versioning_property.py`
    - **Validates: Requirements 8.1, 8.2**

  - [x] 10.4 Write property test for tenant isolation
    - **Property 9: Tenant isolation**
    - Use hypothesis to generate workflow queries with different company_ids
    - Verify queries only return workflows matching the requesting tenant's company_id
    - Verify cross-tenant access returns 404
    - File: `src/backend/tests/properties/test_workflow_tenant_property.py`
    - **Validates: Requirements 10.4, 11.6**

- [x] 11. Frontend property-based tests (remaining)
  - [x] 11.1 Write property test for BPMN XML round-trip
    - **Property 7: BPMN XML workflow structure round-trip**
    - Use fast-check to generate BPMN XML with tasks and sequence flows
    - Verify parsing produces consistent BPMNWorkflow (same states, transitions, initial_state, terminal_states)
    - File: `src/frontend/src/lib/__tests__/bpmnRoundTrip.property.test.ts`
    - **Validates: Requirements 16.1, 16.2, 16.3**

  - [x] 11.2 Write property test for metadata field validation
    - **Property 2: Metadata field validation**
    - Use fast-check to generate arbitrary strings for document_tag
    - Verify validation accepts only `^[a-zA-Z0-9_-]+$` pattern
    - Verify empty/whitespace-only strings are rejected for name and document_tag
    - File: `src/frontend/src/lib/__tests__/metadataValidation.property.test.ts`
    - **Validates: Requirements 3.6, 3.7**

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Python (FastAPI, SQLAlchemy, Alembic, hypothesis for PBT)
- The frontend uses TypeScript (React 19, Vite, Zustand, bpmn-js, fast-check for PBT)
- All mutating API calls require the `X-Change-Reason` header per AuditMiddleware
- All tenant-scoped queries filter by `company_id` from `X-Company-Id` header

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1", "6.2"] },
    { "id": 5, "tasks": ["5.3", "6.3", "6.4"] },
    { "id": 6, "tasks": ["7.1", "7.2", "7.3", "7.4", "7.5", "7.6"] },
    { "id": 7, "tasks": ["8.1", "8.2"] },
    { "id": 8, "tasks": ["8.3"] },
    { "id": 9, "tasks": ["10.1", "10.2", "10.3", "10.4", "11.1", "11.2"] }
  ]
}
```
