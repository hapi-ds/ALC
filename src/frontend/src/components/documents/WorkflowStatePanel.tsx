import { useEffect, useState } from "react";
import {
  Lock,
  BookOpen,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import {
  getStateBadgeColor,
  getRiskLevelColor,
  hasGate,
} from "@/lib/workflowUtils";
import { TransitionConfirmationDialog } from "./TransitionConfirmationDialog";

// ---------------------------------------------------------------------------
// Badge color mapping (Tailwind classes)
// ---------------------------------------------------------------------------

const STATE_BADGE_CLASSES: Record<string, string> = {
  gray: "bg-gray-100 text-gray-800",
  blue: "bg-blue-100 text-blue-800",
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
};

const RISK_BADGE_CLASSES: Record<string, string> = {
  gray: "bg-gray-100 text-gray-700",
  blue: "bg-blue-100 text-blue-700",
  orange: "bg-orange-100 text-orange-700",
  red: "bg-red-100 text-red-700",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface WorkflowStatePanelProps {
  /** The document's UUID for API calls */
  documentUuid: string;
  /** Whether the panel should start expanded (default: true) */
  defaultExpanded?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function WorkflowStatePanel({
  documentUuid,
  defaultExpanded = true,
}: WorkflowStatePanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedTargetState, setSelectedTargetState] = useState<string | null>(
    null
  );

  // Store state
  const currentState = useWorkflowExecutionStore((s) => s.currentState);
  const workflowName = useWorkflowExecutionStore((s) => s.workflowName);
  const validTransitions = useWorkflowExecutionStore(
    (s) => s.validTransitions
  );
  const updatedAt = useWorkflowExecutionStore((s) => s.updatedAt);
  const isLoadingState = useWorkflowExecutionStore((s) => s.isLoadingState);
  const stateError = useWorkflowExecutionStore((s) => s.stateError);
  const riskLevel = useWorkflowExecutionStore((s) => s.riskLevel);
  const signatureRequiredTransitions = useWorkflowExecutionStore(
    (s) => s.signatureRequiredTransitions
  );
  const trainingTriggerTransitions = useWorkflowExecutionStore(
    (s) => s.trainingTriggerTransitions
  );
  const lastTransitionResult = useWorkflowExecutionStore(
    (s) => s.lastTransitionResult
  );

  // Store actions
  const fetchDocumentState = useWorkflowExecutionStore(
    (s) => s.fetchDocumentState
  );
  const fetchWorkflowGateInfo = useWorkflowExecutionStore(
    (s) => s.fetchWorkflowGateInfo
  );

  // Fetch document state on mount / documentUuid change
  useEffect(() => {
    fetchDocumentState(documentUuid);
  }, [documentUuid, fetchDocumentState]);

  // Fetch gate info when workflow name is available and transitions exist
  useEffect(() => {
    if (workflowName && validTransitions.length > 0) {
      fetchWorkflowGateInfo(workflowName);
    }
  }, [workflowName, validTransitions.length, fetchWorkflowGateInfo]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleTransitionClick(targetState: string) {
    setSelectedTargetState(targetState);
    setDialogOpen(true);
  }

  function handleRetry() {
    fetchDocumentState(documentUuid);
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function getAriaLabelForTransition(targetState: string): string {
    const parts: string[] = [`Transition to ${targetState}`];
    if (
      currentState &&
      hasGate(currentState, targetState, signatureRequiredTransitions)
    ) {
      parts.push("requires electronic signature");
    }
    if (
      currentState &&
      hasGate(currentState, targetState, trainingTriggerTransitions)
    ) {
      parts.push("triggers training assignment");
    }
    return parts.join(", ");
  }

  // ---------------------------------------------------------------------------
  // Render: Loading skeleton
  // ---------------------------------------------------------------------------

  if (isLoadingState) {
    return (
      <div
        className="rounded-lg border p-6"
        role="region"
        aria-label="Document Workflow State"
      >
        <div aria-live="polite" className="sr-only">
          Loading workflow state...
        </div>
        <div className="animate-pulse space-y-4">
          <div className="flex items-center gap-3">
            <div className="h-5 w-32 bg-muted rounded" />
            <div className="h-5 w-16 bg-muted rounded-full" />
          </div>
          <div className="flex gap-2">
            <div className="h-9 w-24 bg-muted rounded-md" />
            <div className="h-9 w-24 bg-muted rounded-md" />
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Error state
  // ---------------------------------------------------------------------------

  if (stateError) {
    return (
      <div
        className="rounded-lg border p-6"
        role="region"
        aria-label="Document Workflow State"
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Workflow State</h3>
        </div>
        <div className="mt-4 flex items-center gap-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{stateError}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRetry}
            className="ml-auto gap-1"
            aria-label="Retry loading workflow state"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: No workflow assigned (404 case — currentState is null after load)
  // ---------------------------------------------------------------------------

  if (!currentState) {
    return (
      <div
        className="rounded-lg border p-6"
        role="region"
        aria-label="Document Workflow State"
      >
        <h3 className="text-lg font-semibold">Workflow State</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          No workflow is assigned to this document.
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Main panel
  // ---------------------------------------------------------------------------

  const stateBadgeColor = getStateBadgeColor(currentState);
  const stateBadgeClasses =
    STATE_BADGE_CLASSES[stateBadgeColor] || STATE_BADGE_CLASSES.gray;

  const riskColor = getRiskLevelColor(riskLevel);
  const riskBadgeClasses =
    RISK_BADGE_CLASSES[riskColor] || RISK_BADGE_CLASSES.gray;

  const showRiskWarning = riskLevel === "high" || riskLevel === "critical";

  return (
    <div
      className="rounded-lg border p-6"
      role="region"
      aria-label="Document Workflow State"
    >
      {/* Panel header with collapse toggle */}
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls="workflow-state-content"
      >
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold">Workflow State</h3>
          {workflowName && (
            <span className="text-sm text-muted-foreground">
              {workflowName}
            </span>
          )}
          {/* Risk level badge */}
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${riskBadgeClasses}`}
          >
            {riskLevel}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* State badge (always visible in header) */}
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${stateBadgeClasses}`}
          >
            {currentState}
          </span>
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          )}
        </div>
      </button>

      {/* Collapsible content */}
      {expanded && (
        <div id="workflow-state-content" className="mt-4 space-y-4">
          {/* Updated at timestamp */}
          {updatedAt && (
            <p className="text-xs text-muted-foreground">
              Last updated: {new Date(updatedAt).toLocaleString()}
            </p>
          )}

          {/* Risk warning banner for high/critical */}
          {showRiskWarning && (
            <div
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
                riskLevel === "critical"
                  ? "bg-red-50 text-red-800 border border-red-200"
                  : "bg-orange-50 text-orange-800 border border-orange-200"
              }`}
              role="alert"
            >
              <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                This document is under a{" "}
                <strong>{riskLevel}-risk</strong> workflow. Transitions are
                subject to enhanced review requirements.
              </span>
            </div>
          )}

          {/* Gate indicator banners (post-transition) */}
          {lastTransitionResult?.requires_signature && (
            <div
              className="flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800"
              role="status"
            >
              <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                Electronic signature required. Please complete the signature
                process to finalize this transition.
              </span>
            </div>
          )}
          {lastTransitionResult?.triggers_training && (
            <div
              className="flex items-center gap-2 rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-sm text-blue-800"
              role="status"
            >
              <BookOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                Training tasks have been assigned as a result of this
                transition.
              </span>
            </div>
          )}

          {/* Transition buttons */}
          {validTransitions.length > 0 ? (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Available transitions">
              {validTransitions.map((targetState) => {
                const requiresSignature = hasGate(
                  currentState,
                  targetState,
                  signatureRequiredTransitions
                );
                const triggersTraining = hasGate(
                  currentState,
                  targetState,
                  trainingTriggerTransitions
                );

                return (
                  <Button
                    key={targetState}
                    variant="outline"
                    size="sm"
                    onClick={() => handleTransitionClick(targetState)}
                    aria-label={getAriaLabelForTransition(targetState)}
                    className="gap-1.5"
                  >
                    {requiresSignature && (
                      <span title="Requires electronic signature">
                        <Lock
                          className="h-3.5 w-3.5 text-amber-600"
                          aria-hidden="true"
                        />
                      </span>
                    )}
                    {triggersTraining && (
                      <span title="Triggers training assignment">
                        <BookOpen
                          className="h-3.5 w-3.5 text-blue-600"
                          aria-hidden="true"
                        />
                      </span>
                    )}
                    {targetState}
                  </Button>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No transitions are currently available for this document state.
            </p>
          )}
        </div>
      )}

      {/* Aria live region for loading announcements */}
      <div aria-live="polite" className="sr-only">
        {isLoadingState ? "Loading workflow state..." : "Workflow state loaded."}
      </div>

      {/* TransitionConfirmationDialog */}
      {dialogOpen && selectedTargetState && currentState && (
        <TransitionConfirmationDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          currentState={currentState}
          targetState={selectedTargetState}
          documentUuid={documentUuid}
          requiresSignature={hasGate(
            currentState,
            selectedTargetState,
            signatureRequiredTransitions
          )}
          triggersTraining={hasGate(
            currentState,
            selectedTargetState,
            trainingTriggerTransitions
          )}
          riskLevel={riskLevel}
        />
      )}
    </div>
  );
}
