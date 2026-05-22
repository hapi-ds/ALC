import { useEffect, useRef, useState, useCallback } from "react";
import { Lock, BookOpen, AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { isValidChangeReason } from "@/lib/workflowUtils";
import type { RiskLevel } from "@/types/workflow";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TransitionConfirmationDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback to control open state */
  onOpenChange: (open: boolean) => void;
  /** The current workflow state name */
  currentState: string;
  /** The target state for the transition */
  targetState: string;
  /** The document UUID for executing the transition */
  documentUuid: string;
  /** Whether this transition requires an electronic signature */
  requiresSignature: boolean;
  /** Whether this transition triggers training assignment */
  triggersTraining: boolean;
  /** The workflow risk level */
  riskLevel: RiskLevel;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIMEOUT_MS = 30_000;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TransitionConfirmationDialog({
  open,
  onOpenChange,
  currentState,
  targetState,
  documentUuid,
  requiresSignature,
  triggersTraining,
  riskLevel,
}: TransitionConfirmationDialogProps) {
  const executeTransition = useWorkflowExecutionStore(
    (s) => s.executeTransition
  );
  const isTransitioning = useWorkflowExecutionStore((s) => s.isTransitioning);
  const transitionError = useWorkflowExecutionStore((s) => s.transitionError);
  const clearTransitionState = useWorkflowExecutionStore(
    (s) => s.clearTransitionState
  );

  const [changeReason, setChangeReason] = useState("");
  const [timeoutError, setTimeoutError] = useState<string | null>(null);

  // Refs for focus management
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const firstFocusableRef = useRef<HTMLTextAreaElement>(null);
  const timeoutIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Capture the triggering element when dialog opens
  useEffect(() => {
    if (open) {
      triggerRef.current = document.activeElement as HTMLElement;
      setTimeoutError(null);
    }
  }, [open]);

  // Focus the textarea when dialog opens
  useEffect(() => {
    if (open && firstFocusableRef.current) {
      // Small delay to ensure DOM is ready
      requestAnimationFrame(() => {
        firstFocusableRef.current?.focus();
      });
    }
  }, [open]);

  // ---------------------------------------------------------------------------
  // Focus trapping
  // ---------------------------------------------------------------------------

  const handleClose = useCallback(() => {
    clearTransitionState();
    setChangeReason("");
    setTimeoutError(null);
    if (timeoutIdRef.current) {
      clearTimeout(timeoutIdRef.current);
      timeoutIdRef.current = null;
    }
    onOpenChange(false);

    // Return focus to triggering button
    requestAnimationFrame(() => {
      triggerRef.current?.focus();
    });
  }, [clearTransitionState, onOpenChange]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!open || !dialogRef.current) return;

      if (e.key === "Escape") {
        e.preventDefault();
        handleClose();
        return;
      }

      if (e.key === "Tab") {
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        const focusable = Array.from(focusableElements);

        if (focusable.length === 0) return;

        const firstElement = focusable[0];
        const lastElement = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    },
    [open, handleClose]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleConfirm() {
    setTimeoutError(null);

    // Start 30-second timeout
    const timeoutPromise = new Promise<"timeout">((resolve) => {
      timeoutIdRef.current = setTimeout(() => {
        resolve("timeout");
      }, TIMEOUT_MS);
    });

    const transitionPromise = executeTransition(
      documentUuid,
      targetState,
      changeReason
    );

    const result = await Promise.race([transitionPromise, timeoutPromise]);

    // Clear timeout if transition completed first
    if (timeoutIdRef.current) {
      clearTimeout(timeoutIdRef.current);
      timeoutIdRef.current = null;
    }

    if (result === "timeout") {
      setTimeoutError(
        "The transition request timed out after 30 seconds. Please try again."
      );
      return;
    }

    if (result === true) {
      // Success — close dialog and clear state
      setChangeReason("");
      setTimeoutError(null);
      clearTransitionState();
      onOpenChange(false);

      // Return focus to triggering button
      requestAnimationFrame(() => {
        triggerRef.current?.focus();
      });
    }
    // On failure (result === false), the store sets transitionError.
    // Dialog stays open with the error displayed and change reason retained.
  }

  // ---------------------------------------------------------------------------
  // Cleanup timeout on unmount
  // ---------------------------------------------------------------------------

  useEffect(() => {
    return () => {
      if (timeoutIdRef.current) {
        clearTimeout(timeoutIdRef.current);
      }
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!open) return null;

  const trimmedLength = changeReason.trim().length;
  const isValid = isValidChangeReason(changeReason);
  const showRiskWarning = riskLevel === "high" || riskLevel === "critical";
  const displayError = timeoutError || transitionError;
  const buttonsDisabled = isTransitioning;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isTransitioning) {
          handleClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="transition-dialog-title"
        aria-describedby="transition-dialog-description"
        className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4"
      >
        {/* Title */}
        <h2 id="transition-dialog-title" className="text-lg font-semibold">
          Confirm Transition
        </h2>

        {/* Transition summary */}
        <p
          id="transition-dialog-description"
          className="text-sm text-muted-foreground"
        >
          {currentState} &rarr; {targetState}
        </p>

        {/* Gate warnings */}
        {requiresSignature && (
          <div className="flex items-center gap-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800">
            <span title="Requires electronic signature">
              <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
            </span>
            <span>This transition requires an electronic signature.</span>
          </div>
        )}
        {triggersTraining && (
          <div className="flex items-center gap-2 rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-sm text-blue-800">
            <span title="Triggers training assignment">
              <BookOpen className="h-4 w-4 shrink-0" aria-hidden="true" />
            </span>
            <span>This transition will trigger training assignment.</span>
          </div>
        )}

        {/* Risk warning for high/critical */}
        {showRiskWarning && (
          <div
            className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
              riskLevel === "critical"
                ? "bg-red-50 text-red-800 border border-red-200"
                : "bg-orange-50 text-orange-800 border border-orange-200"
            }`}
          >
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>
              This document is under a <strong>{riskLevel}-risk</strong>{" "}
              workflow. Transitions are subject to enhanced review requirements.
            </span>
          </div>
        )}

        {/* Change reason input */}
        <div className="space-y-1">
          <label
            htmlFor="transition-change-reason"
            className="text-sm font-medium"
          >
            Change Reason
          </label>
          <textarea
            ref={firstFocusableRef}
            id="transition-change-reason"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            rows={3}
            placeholder="Provide a reason for this transition (3–500 characters)"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            disabled={buttonsDisabled}
            maxLength={500}
            aria-required="true"
            aria-invalid={trimmedLength > 0 && !isValid}
            aria-describedby="change-reason-counter"
          />
          <p
            id="change-reason-counter"
            className="text-xs text-muted-foreground text-right"
          >
            {trimmedLength}/500
          </p>
        </div>

        {/* Error display */}
        {displayError && (
          <p className="text-sm text-destructive" role="alert">
            {displayError}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleClose}
            disabled={buttonsDisabled}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleConfirm}
            disabled={!isValid || buttonsDisabled}
          >
            {isTransitioning && (
              <Loader2
                className="h-4 w-4 animate-spin"
                aria-hidden="true"
              />
            )}
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}
