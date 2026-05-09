/**
 * Workflow Store (Zustand)
 *
 * Centralized state management for workflow CRUD operations, BPMN editor state,
 * validation, version history, and dirty tracking. Uses apiClient for all API
 * calls with proper X-Change-Reason headers for ALCOA+ audit compliance.
 *
 * API endpoints verified against src/backend/src/alcoabase/api/workflows.py:
 *   GET  /api/workflows                          - list workflows (tenant-scoped)
 *   GET  /api/workflows/{id}                     - get single workflow
 *   POST /api/workflows                          - create workflow
 *   PUT  /api/workflows/{id}                     - update workflow
 *   DELETE /api/workflows/{id}                   - delete workflow
 *   POST /api/workflows/validate                 - validate BPMN XML
 *   GET  /api/workflows/{id}/versions            - list versions
 *   GET  /api/workflows/{id}/versions/{versionId} - get version detail
 *
 * All mutating requests (POST, PUT, DELETE) require X-Change-Reason header,
 * which is passed via apiClient's `changeReason` option.
 *
 * Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9
 */

import { create } from "zustand";
import { apiClient, ApiError } from "../lib/apiClient";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface WorkflowResponse {
  id: number;
  name: string;
  document_tag: string;
  bpmn_xml: string;
  signature_required_transitions: string[];
  training_trigger_transitions: string[];
  is_active: boolean;
  risk_level: string;
  auto_assignment_config: Record<string, unknown> | null;
  current_version_number: number;
}

export interface WorkflowVersionSummary {
  version_number: number;
  created_by: number;
  created_at: string;
  change_reason: string;
}

export interface WorkflowVersionDetail {
  version_number: number;
  bpmn_xml: string;
  name: string;
  document_tag: string;
  risk_level: string;
  signature_required_transitions: string[];
  training_trigger_transitions: string[];
  auto_assignment_config: Record<string, unknown> | null;
  created_by: number;
  created_at: string;
  change_reason: string;
}

export interface ValidationResult {
  is_valid: boolean;
  errors: string[];
}

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface WorkflowStoreState {
  // List state
  workflows: WorkflowResponse[];
  isLoadingList: boolean;
  listError: string | null;

  // Detail state
  currentWorkflow: WorkflowResponse | null;
  isLoadingDetail: boolean;
  detailError: string | null;

  // Editor state
  bpmnXml: string;
  workflowName: string;
  documentTag: string;
  riskLevel: RiskLevel;
  signatureRequiredTransitions: string[];
  trainingTriggerTransitions: string[];
  autoAssignmentConfig: Record<string, unknown> | null;

  // Dirty tracking
  isDirty: boolean;

  // Save state
  isSaving: boolean;
  saveError: string | null;

  // Validation state
  isValidating: boolean;
  validateError: string | null;
  validationResult: ValidationResult | null;

  // Delete state
  isDeleting: boolean;
  deleteError: string | null;

  // Version state
  versions: WorkflowVersionSummary[];
  selectedVersion: WorkflowVersionDetail | null;
  isLoadingVersions: boolean;
  versionsError: string | null;

  // Actions
  fetchWorkflowList: () => Promise<void>;
  fetchWorkflowDetail: (id: number) => Promise<void>;
  createWorkflow: () => Promise<WorkflowResponse | null>;
  updateWorkflow: (id: number) => Promise<WorkflowResponse | null>;
  deleteWorkflow: (id: number) => Promise<boolean>;
  validateWorkflow: () => Promise<void>;
  fetchVersionHistory: (workflowId: number) => Promise<void>;
  fetchVersion: (workflowId: number, versionNumber: number) => Promise<void>;
  setBpmnXml: (xml: string) => void;
  setWorkflowName: (name: string) => void;
  setDocumentTag: (tag: string) => void;
  setRiskLevel: (level: RiskLevel) => void;
  setSignatureTransitions: (transitions: string[]) => void;
  setTrainingTransitions: (transitions: string[]) => void;
  setAutoAssignmentConfig: (config: Record<string, unknown> | null) => void;
  clearValidation: () => void;
  resetEditor: () => void;
  restoreVersion: (version: WorkflowVersionDetail) => void;
}

// ---------------------------------------------------------------------------
// Saved state snapshot for dirty tracking
// ---------------------------------------------------------------------------

interface SavedSnapshot {
  bpmnXml: string;
  workflowName: string;
  documentTag: string;
  riskLevel: RiskLevel;
  signatureRequiredTransitions: string[];
  trainingTriggerTransitions: string[];
  autoAssignmentConfig: Record<string, unknown> | null;
}

let lastSavedSnapshot: SavedSnapshot = {
  bpmnXml: "",
  workflowName: "",
  documentTag: "",
  riskLevel: "low",
  signatureRequiredTransitions: [],
  trainingTriggerTransitions: [],
  autoAssignmentConfig: null,
};

/**
 * Compares current editor values against the last-saved snapshot.
 */
function computeIsDirty(state: {
  bpmnXml: string;
  workflowName: string;
  documentTag: string;
  riskLevel: RiskLevel;
  signatureRequiredTransitions: string[];
  trainingTriggerTransitions: string[];
  autoAssignmentConfig: Record<string, unknown> | null;
}): boolean {
  if (state.bpmnXml !== lastSavedSnapshot.bpmnXml) return true;
  if (state.workflowName !== lastSavedSnapshot.workflowName) return true;
  if (state.documentTag !== lastSavedSnapshot.documentTag) return true;
  if (state.riskLevel !== lastSavedSnapshot.riskLevel) return true;
  if (
    JSON.stringify(state.signatureRequiredTransitions) !==
    JSON.stringify(lastSavedSnapshot.signatureRequiredTransitions)
  )
    return true;
  if (
    JSON.stringify(state.trainingTriggerTransitions) !==
    JSON.stringify(lastSavedSnapshot.trainingTriggerTransitions)
  )
    return true;
  if (
    JSON.stringify(state.autoAssignmentConfig) !==
    JSON.stringify(lastSavedSnapshot.autoAssignmentConfig)
  )
    return true;
  return false;
}

/**
 * Updates the saved snapshot from a workflow response.
 */
function updateSavedSnapshot(workflow: WorkflowResponse): void {
  lastSavedSnapshot = {
    bpmnXml: workflow.bpmn_xml,
    workflowName: workflow.name,
    documentTag: workflow.document_tag,
    riskLevel: workflow.risk_level as RiskLevel,
    signatureRequiredTransitions: [...workflow.signature_required_transitions],
    trainingTriggerTransitions: [...workflow.training_trigger_transitions],
    autoAssignmentConfig: workflow.auto_assignment_config
      ? { ...workflow.auto_assignment_config }
      : null,
  };
}

/**
 * Resets the saved snapshot to empty (for new workflow creation).
 */
function resetSavedSnapshot(): void {
  lastSavedSnapshot = {
    bpmnXml: "",
    workflowName: "",
    documentTag: "",
    riskLevel: "low",
    signatureRequiredTransitions: [],
    trainingTriggerTransitions: [],
    autoAssignmentConfig: null,
  };
}

// ---------------------------------------------------------------------------
// Helper: extract error message from ApiError
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.body);
      return parsed.detail || parsed.message || error.message;
    } catch {
      return error.body || error.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred";
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useWorkflowStore = create<WorkflowStoreState>((set, get) => ({
  // List state
  workflows: [],
  isLoadingList: false,
  listError: null,

  // Detail state
  currentWorkflow: null,
  isLoadingDetail: false,
  detailError: null,

  // Editor state
  bpmnXml: "",
  workflowName: "",
  documentTag: "",
  riskLevel: "low",
  signatureRequiredTransitions: [],
  trainingTriggerTransitions: [],
  autoAssignmentConfig: null,

  // Dirty tracking
  isDirty: false,

  // Save state
  isSaving: false,
  saveError: null,

  // Validation state
  isValidating: false,
  validateError: null,
  validationResult: null,

  // Delete state
  isDeleting: false,
  deleteError: null,

  // Version state
  versions: [],
  selectedVersion: null,
  isLoadingVersions: false,
  versionsError: null,

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  fetchWorkflowList: async () => {
    set({ isLoadingList: true, listError: null });

    try {
      const response = await apiClient.get<WorkflowResponse[]>(
        "/api/workflows"
      );
      set({ workflows: response, isLoadingList: false });
    } catch (error) {
      set({
        listError: extractErrorMessage(error),
        isLoadingList: false,
      });
    }
  },

  fetchWorkflowDetail: async (id: number) => {
    set({ isLoadingDetail: true, detailError: null });

    try {
      const response = await apiClient.get<WorkflowResponse>(
        `/api/workflows/${id}`
      );

      // Update saved snapshot for dirty tracking
      updateSavedSnapshot(response);

      set({
        currentWorkflow: response,
        bpmnXml: response.bpmn_xml,
        workflowName: response.name,
        documentTag: response.document_tag,
        riskLevel: response.risk_level as RiskLevel,
        signatureRequiredTransitions: [
          ...response.signature_required_transitions,
        ],
        trainingTriggerTransitions: [...response.training_trigger_transitions],
        autoAssignmentConfig: response.auto_assignment_config,
        isDirty: false,
        isLoadingDetail: false,
      });
    } catch (error) {
      set({
        detailError: extractErrorMessage(error),
        isLoadingDetail: false,
      });
    }
  },

  createWorkflow: async () => {
    const {
      workflowName,
      documentTag,
      bpmnXml,
      riskLevel,
      signatureRequiredTransitions,
      trainingTriggerTransitions,
      autoAssignmentConfig,
    } = get();

    set({ isSaving: true, saveError: null });

    try {
      const response = await apiClient.post<WorkflowResponse>(
        "/api/workflows",
        {
          name: workflowName,
          document_tag: documentTag,
          bpmn_xml: bpmnXml,
          risk_level: riskLevel,
          signature_required_transitions: signatureRequiredTransitions,
          training_trigger_transitions: trainingTriggerTransitions,
          auto_assignment_config: autoAssignmentConfig,
        },
        { changeReason: `Workflow created: ${workflowName}` }
      );

      // Update saved snapshot
      updateSavedSnapshot(response);

      set({
        currentWorkflow: response,
        isDirty: false,
        isSaving: false,
      });

      return response;
    } catch (error) {
      set({
        saveError: extractErrorMessage(error),
        isSaving: false,
      });
      return null;
    }
  },

  updateWorkflow: async (id: number) => {
    const {
      workflowName,
      documentTag,
      bpmnXml,
      riskLevel,
      signatureRequiredTransitions,
      trainingTriggerTransitions,
      autoAssignmentConfig,
    } = get();

    set({ isSaving: true, saveError: null });

    try {
      const response = await apiClient.put<WorkflowResponse>(
        `/api/workflows/${id}`,
        {
          name: workflowName,
          document_tag: documentTag,
          bpmn_xml: bpmnXml,
          risk_level: riskLevel,
          signature_required_transitions: signatureRequiredTransitions,
          training_trigger_transitions: trainingTriggerTransitions,
          auto_assignment_config: autoAssignmentConfig,
        },
        { changeReason: `Workflow updated: ${workflowName}` }
      );

      // Update saved snapshot
      updateSavedSnapshot(response);

      set({
        currentWorkflow: response,
        isDirty: false,
        isSaving: false,
      });

      return response;
    } catch (error) {
      set({
        saveError: extractErrorMessage(error),
        isSaving: false,
      });
      return null;
    }
  },

  deleteWorkflow: async (id: number) => {
    const { workflowName } = get();

    set({ isDeleting: true, deleteError: null });

    try {
      await apiClient.delete(`/api/workflows/${id}`, {
        changeReason: `Workflow deleted: ${workflowName}`,
      });

      // Remove from list state
      const { workflows } = get();
      set({
        workflows: workflows.filter((w) => w.id !== id),
        currentWorkflow: null,
        isDeleting: false,
      });

      return true;
    } catch (error) {
      set({
        deleteError: extractErrorMessage(error),
        isDeleting: false,
      });
      return false;
    }
  },

  validateWorkflow: async () => {
    const { bpmnXml, signatureRequiredTransitions } = get();

    set({ isValidating: true, validateError: null, validationResult: null });

    try {
      const response = await apiClient.post<ValidationResult>(
        "/api/workflows/validate",
        {
          bpmn_xml: bpmnXml,
          signature_required_transitions: signatureRequiredTransitions,
        },
        { changeReason: "Workflow validation requested" }
      );

      set({
        validationResult: response,
        isValidating: false,
      });
    } catch (error) {
      set({
        validateError: extractErrorMessage(error),
        isValidating: false,
      });
    }
  },

  fetchVersionHistory: async (workflowId: number) => {
    set({ isLoadingVersions: true, versionsError: null });

    try {
      const response = await apiClient.get<WorkflowVersionSummary[]>(
        `/api/workflows/${workflowId}/versions`
      );
      set({ versions: response, isLoadingVersions: false });
    } catch (error) {
      set({
        versionsError: extractErrorMessage(error),
        isLoadingVersions: false,
      });
    }
  },

  fetchVersion: async (workflowId: number, versionNumber: number) => {
    set({ isLoadingVersions: true, versionsError: null });

    try {
      const response = await apiClient.get<WorkflowVersionDetail>(
        `/api/workflows/${workflowId}/versions/${versionNumber}`
      );
      set({ selectedVersion: response, isLoadingVersions: false });
    } catch (error) {
      set({
        versionsError: extractErrorMessage(error),
        isLoadingVersions: false,
      });
    }
  },

  setBpmnXml: (xml: string) => {
    const state = get();
    const newState = { ...state, bpmnXml: xml };
    set({
      bpmnXml: xml,
      isDirty: computeIsDirty(newState),
      validationResult: null,
    });
  },

  setWorkflowName: (name: string) => {
    const state = get();
    const newState = { ...state, workflowName: name };
    set({
      workflowName: name,
      isDirty: computeIsDirty(newState),
    });
  },

  setDocumentTag: (tag: string) => {
    const state = get();
    const newState = { ...state, documentTag: tag };
    set({
      documentTag: tag,
      isDirty: computeIsDirty(newState),
    });
  },

  setRiskLevel: (level: RiskLevel) => {
    const state = get();
    const newState = { ...state, riskLevel: level };
    set({
      riskLevel: level,
      isDirty: computeIsDirty(newState),
    });
  },

  setSignatureTransitions: (transitions: string[]) => {
    const state = get();
    const newState = { ...state, signatureRequiredTransitions: transitions };
    set({
      signatureRequiredTransitions: transitions,
      isDirty: computeIsDirty(newState),
    });
  },

  setTrainingTransitions: (transitions: string[]) => {
    const state = get();
    const newState = { ...state, trainingTriggerTransitions: transitions };
    set({
      trainingTriggerTransitions: transitions,
      isDirty: computeIsDirty(newState),
    });
  },

  setAutoAssignmentConfig: (config: Record<string, unknown> | null) => {
    const state = get();
    const newState = { ...state, autoAssignmentConfig: config };
    set({
      autoAssignmentConfig: config,
      isDirty: computeIsDirty(newState),
    });
  },

  clearValidation: () => {
    set({ validationResult: null, validateError: null });
  },

  resetEditor: () => {
    resetSavedSnapshot();
    set({
      currentWorkflow: null,
      bpmnXml: "",
      workflowName: "",
      documentTag: "",
      riskLevel: "low",
      signatureRequiredTransitions: [],
      trainingTriggerTransitions: [],
      autoAssignmentConfig: null,
      isDirty: false,
      saveError: null,
      deleteError: null,
      detailError: null,
      validationResult: null,
      validateError: null,
      versions: [],
      selectedVersion: null,
      versionsError: null,
    });
  },

  restoreVersion: (version: WorkflowVersionDetail) => {
    set({
      bpmnXml: version.bpmn_xml,
      workflowName: version.name,
      documentTag: version.document_tag,
      riskLevel: version.risk_level as RiskLevel,
      signatureRequiredTransitions: [...version.signature_required_transitions],
      trainingTriggerTransitions: [...version.training_trigger_transitions],
      autoAssignmentConfig: version.auto_assignment_config,
      isDirty: true,
      selectedVersion: null,
    });
  },
}));
