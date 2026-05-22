import { useEffect, useRef, useState, useCallback } from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TrainingTask } from "./types";
import { validateInputLength } from "./utils";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MIN_LENGTH = 3;
const MAX_LENGTH = 500;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TaskCompletionDialogProps {
  task: TrainingTask;
  isSubmitting: boolean;
  error: string | null;
  onConfirm: (changeReason: string) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// TaskCompletionDialog
// ---------------------------------------------------------------------------

export function TaskCompletionDialog({
  task,
  isSubmitting,
  error,
  onConfirm,
  onClose,
}: TaskCompletionDialogProps) {
  const [changeReason, setChangeReason] = useState("");

  // Refs for focus management
  const dialogRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  // Capture the triggering element on mount
  useEffect(() => {
    triggerRef.current = document.activeElement as HTMLElement;
  }, []);

  // Focus the input on mount
  useEffect(() => {
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  }, []);

  // Focus error message when error appears
  useEffect(() => {
    if (error && errorRef.current) {
      errorRef.current.focus();
    }
  }, [error]);

  // ---------------------------------------------------------------------------
  // Validation
  // ---------------------------------------------------------------------------

  const trimmedLength = changeReason.trim().length;
  const isValid = validateInputLength(changeReason, MIN_LENGTH, MAX_LENGTH);
  const remainingChars = MAX_LENGTH - changeReason.length;

  // ---------------------------------------------------------------------------
  // Focus trapping
  // ---------------------------------------------------------------------------

  const handleClose = useCallback(() => {
    onClose();

    // Return focus to triggering button
    requestAnimationFrame(() => {
      triggerRef.current?.focus();
    });
  }, [onClose]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!dialogRef.current) return;

      if (e.key === "Escape") {
        e.preventDefault();
        if (!isSubmitting) {
          handleClose();
        }
        return;
      }

      if (e.key === "Tab") {
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
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
    [handleClose, isSubmitting]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleConfirm() {
    if (!isValid || isSubmitting) return;
    onConfirm(changeReason.trim());
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          handleClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-completion-dialog-title"
        aria-describedby="task-completion-dialog-description"
        className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4"
      >
        {/* Header with close button */}
        <div className="flex items-start justify-between">
          <h2
            id="task-completion-dialog-title"
            className="text-lg font-semibold"
          >
            Complete Training Task
          </h2>
          <button
            type="button"
            onClick={handleClose}
            disabled={isSubmitting}
            className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* Task details */}
        <div id="task-completion-dialog-description" className="space-y-1">
          <p className="text-sm font-medium">{task.task_title}</p>
          <p className="text-xs text-muted-foreground">
            SOP: {task.sop_document_uuid}
          </p>
          <p className="text-xs text-muted-foreground">
            Version: {task.sop_version}
          </p>
        </div>

        {/* Change reason input */}
        <div className="space-y-1">
          <label
            htmlFor="task-completion-change-reason"
            className="text-sm font-medium"
          >
            Change Reason <span className="text-destructive">*</span>
          </label>
          <textarea
            ref={inputRef}
            id="task-completion-change-reason"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            rows={3}
            placeholder="Provide a reason for completing this task (3–500 characters)"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            disabled={isSubmitting}
            maxLength={MAX_LENGTH}
            aria-required="true"
            aria-invalid={trimmedLength > 0 && !isValid}
            aria-describedby="change-reason-counter change-reason-hint"
          />
          <div className="flex items-center justify-between">
            <p
              id="change-reason-hint"
              className="text-xs text-muted-foreground"
            >
              {trimmedLength < MIN_LENGTH && trimmedLength > 0
                ? `Minimum ${MIN_LENGTH} characters required`
                : ""}
            </p>
            <p
              id="change-reason-counter"
              className={`text-xs ${
                remainingChars < 50
                  ? "text-amber-600"
                  : "text-muted-foreground"
              }`}
            >
              {remainingChars} characters remaining
            </p>
          </div>
        </div>

        {/* Error display */}
        {error && (
          <p
            ref={errorRef}
            className="text-sm text-destructive"
            role="alert"
            aria-live="assertive"
            tabIndex={-1}
          >
            {error}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleClose}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleConfirm}
            disabled={!isValid || isSubmitting}
          >
            {isSubmitting && (
              <Loader2
                className="h-4 w-4 animate-spin"
                aria-hidden="true"
              />
            )}
            {isSubmitting ? "Completing..." : "Confirm"}
          </Button>
        </div>
      </div>
    </div>
  );
}
