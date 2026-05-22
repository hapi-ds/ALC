/**
 * Workflow Execution Store (Zustand)
 *
 * Centralized state management for workflow execution operations on documents:
 * fetching document workflow state, executing transitions, retrieving history,
 * and loading gate information from workflow definitions.
 *
 * Separate from workflowStore (which manages workflow definitions/editor) to
 * maintain single-responsibility.
 *
 * API endpoints (verified against src/backend/src/alcoabase/api/workflows.py):
 *   GET  /api/workflows/state/{document_uuid}          - get document workflow state
 *   POST /api/workflows/transition                     - execute state transition
 *   GET  /api/workflows/state/{document_uuid}/history  - get transition history
 *   GET  /api/workflows                                - list workflows (for gate info)
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 9.1, 9.2, 10.1, 10.2, 10.3, 10.5
 */

import { create } from "zustand";
import { apiClient, ApiError } from "../lib/apiClient";
import { isSignatureRequired } from "../lib/signatureUtils";
import { useSignatureStore } from "./signatureStore";
import type {
  DocumentStateResponse,
  TransitionResponse,
  TransitionHistoryEntry,
  RiskLevel,
} from "../types/workflow";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Workflow definition response shape (subset needed from GET /api/workflows) */
interface WorkflowListItem {
  id: number;
  name: string;
  signature_required_transitions: string[];
  training_trigger_transitions: string[];
  risk_level: string;
}

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface WorkflowExecutionState {
  // Document workflow state
  documentUuid: string | null;
  currentState: string | null;
  workflowName: string | null;
  validTransitions: string[];
  updatedAt: string | null;
  isLoadingState: boolean;
  stateError: string | null;

  // Transition execution
  isTransitioning: boolean;
  transitionError: string | null;
  lastTransitionResult: {
    success: boolean;
    previous_state: string;
    new_state: string;
    requires_signature: boolean;
    triggers_training: boolean;
  } | null;

  // Workflow history
  history: TransitionHistoryEntry[];
  isLoadingHistory: boolean;
  historyError: string | null;

  // Gate status (from workflow definition)
  signatureRequiredTransitions: string[];
  trainingTriggerTransitions: string[];
  riskLevel: RiskLevel;
  isLoadingGateInfo: boolean;

  // Actions
  fetchDocumentState: (documentUuid: string) => Promise<void>;
  executeTransition: (
    documentUuid: string,
    targetState: string,
    changeReason: string,
    skipSignatureCheck?: boolean
  ) => Promise<boolean>;
  fetchTransitionHistory: (documentUuid: string) => Promise<void>;
  fetchWorkflowGateInfo: (workflowName: string) => Promise<void>;
  clearTransitionState: () => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Helper: extract error message
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

export const useWorkflowExecutionStore = create<WorkflowExecutionState>(
  (set, get) => ({
    // Document workflow state
    documentUuid: null,
    currentState: null,
    workflowName: null,
    validTransitions: [],
    updatedAt: null,
    isLoadingState: false,
    stateError: null,

    // Transition execution
    isTransitioning: false,
    transitionError: null,
    lastTransitionResult: null,

    // Workflow history
    history: [],
    isLoadingHistory: false,
    historyError: null,

    // Gate status
    signatureRequiredTransitions: [],
    trainingTriggerTransitions: [],
    riskLevel: "low",
    isLoadingGateInfo: false,

    // -----------------------------------------------------------------------
    // Actions
    // -----------------------------------------------------------------------

    fetchDocumentState: async (documentUuid: string) => {
      set({ isLoadingState: true, stateError: null });

      try {
        const response = await apiClient.get<DocumentStateResponse>(
          `/api/workflows/state/${documentUuid}`
        );

        set({
          documentUuid,
          currentState: response.current_state,
          workflowName: response.workflow_name,
          validTransitions: response.valid_transitions,
          updatedAt: response.updated_at,
          isLoadingState: false,
        });
      } catch (error) {
        set({
          stateError: extractErrorMessage(error),
          isLoadingState: false,
        });
      }
    },

    executeTransition: async (
      documentUuid: string,
      targetState: string,
      changeReason: string,
      skipSignatureCheck?: boolean
    ): Promise<boolean> => {
      // If skipSignatureCheck is not true, check if this transition requires a signature
      if (!skipSignatureCheck) {
        const { currentState, signatureRequiredTransitions } = get();

        if (
          currentState &&
          isSignatureRequired(
            currentState,
            targetState,
            signatureRequiredTransitions
          )
        ) {
          // Open the signature dialog instead of executing the transition directly
          const { openSignatureDialog } = useSignatureStore.getState();
          openSignatureDialog({
            document_uuid: documentUuid,
            document_version_id: 0, // Will be resolved from document state by SignatureDialog
            transition: `${currentState}\u2192${targetState}`,
            documentTitle: documentUuid, // Best available; UI can enhance later
          });
          // Return false \u2014 the transition will be completed by the SignatureDialog after signing
          return false;
        }
      }

      set({ isTransitioning: true, transitionError: null });

      try {
        const response = await apiClient.post<TransitionResponse>(
          "/api/workflows/transition",
          {
            document_uuid: documentUuid,
            target_state: targetState,
          },
          { changeReason }
        );

        set({
          lastTransitionResult: response,
          isTransitioning: false,
        });

        // Re-fetch state and history after successful transition
        const { fetchDocumentState, fetchTransitionHistory } = get();
        await Promise.all([
          fetchDocumentState(documentUuid),
          fetchTransitionHistory(documentUuid),
        ]);

        return true;
      } catch (error) {
        set({
          transitionError: extractErrorMessage(error),
          isTransitioning: false,
        });
        return false;
      }
    },

    fetchTransitionHistory: async (documentUuid: string) => {
      set({ isLoadingHistory: true, historyError: null });

      try {
        const response = await apiClient.get<TransitionHistoryEntry[]>(
          `/api/workflows/state/${documentUuid}/history`
        );

        set({
          history: response,
          isLoadingHistory: false,
        });
      } catch (error) {
        set({
          historyError: extractErrorMessage(error),
          isLoadingHistory: false,
        });
      }
    },

    fetchWorkflowGateInfo: async (workflowName: string) => {
      set({ isLoadingGateInfo: true });

      try {
        const workflows =
          await apiClient.get<WorkflowListItem[]>("/api/workflows");

        const match = workflows.find((w) => w.name === workflowName);

        if (match) {
          set({
            signatureRequiredTransitions:
              match.signature_required_transitions ?? [],
            trainingTriggerTransitions:
              match.training_trigger_transitions ?? [],
            riskLevel: (match.risk_level as RiskLevel) || "low",
            isLoadingGateInfo: false,
          });
        } else {
          set({ isLoadingGateInfo: false });
        }
      } catch {
        // Gate info failure is non-blocking \u2014 render buttons without indicators
        set({ isLoadingGateInfo: false });
      }
    },

    clearTransitionState: () => {
      set({
        transitionError: null,
        lastTransitionResult: null,
      });
    },

    reset: () => {
      set({
        documentUuid: null,
        currentState: null,
        workflowName: null,
        validTransitions: [],
        updatedAt: null,
        isLoadingState: false,
        stateError: null,
        isTransitioning: false,
        transitionError: null,
        lastTransitionResult: null,
        history: [],
        isLoadingHistory: false,
        historyError: null,
        signatureRequiredTransitions: [],
        trainingTriggerTransitions: [],
        riskLevel: "low",
        isLoadingGateInfo: false,
      });
    },
  })
);
