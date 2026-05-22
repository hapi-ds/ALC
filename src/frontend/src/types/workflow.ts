/**
 * TypeScript types for workflow execution and state transitions.
 *
 * These types mirror the backend Pydantic schemas defined in
 * src/backend/src/alcoabase/schemas/workflow.py and are used by
 * the workflowExecutionStore and workflow UI components.
 */

/** Risk level classification for workflow definitions. */
export type RiskLevel = "low" | "medium" | "high" | "critical";

/** Response from GET /api/workflows/state/{document_uuid} */
export interface DocumentStateResponse {
  document_uuid: string;
  current_state: string;
  workflow_name: string;
  valid_transitions: string[];
  updated_at: string | null;
}

/** Response from POST /api/workflows/transition */
export interface TransitionResponse {
  success: boolean;
  previous_state: string;
  new_state: string;
  requires_signature: boolean;
  triggers_training: boolean;
}

/** A single entry from GET /api/workflows/state/{document_uuid}/history */
export interface TransitionHistoryEntry {
  id: number;
  document_id: number;
  user_id: number;
  previous_state: string;
  new_state: string;
  timestamp: string;
  change_reason: string | null;
}

/** Subset of workflow definition data needed for gate indicator display. */
export interface WorkflowGateInfo {
  signature_required_transitions: string[];
  training_trigger_transitions: string[];
  risk_level: RiskLevel;
}
