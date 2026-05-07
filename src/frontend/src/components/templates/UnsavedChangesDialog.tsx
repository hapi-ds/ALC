import { useEffect, useRef, useCallback } from "react";

interface UnsavedChangesDialogProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Modal confirmation dialog for navigating away with unsaved changes.
 * Focus is trapped within the dialog and keyboard navigation is fully supported.
 */
export function UnsavedChangesDialog({
  open,
  onConfirm,
  onCancel,
}: UnsavedChangesDialogProps) {
  const stayButtonRef = useRef<HTMLButtonElement>(null);
  const leaveButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Focus the "Stay" button when dialog opens (safer default)
  useEffect(() => {
    if (open) {
      // Use requestAnimationFrame to ensure the DOM has rendered
      requestAnimationFrame(() => {
        stayButtonRef.current?.focus();
      });
    }
  }, [open]);

  // Handle keyboard events: Escape to cancel, Tab to trap focus
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!open) return;

      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
        return;
      }

      if (e.key === "Tab") {
        const focusableElements = [
          leaveButtonRef.current,
          stayButtonRef.current,
        ].filter(Boolean) as HTMLElement[];

        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

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
    [open, onCancel]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown);
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      aria-hidden={!open}
    >
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-black/50"
        aria-hidden="true"
        onClick={onCancel}
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="unsaved-changes-title"
        aria-describedby="unsaved-changes-description"
        className="relative z-10 w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <h2
          id="unsaved-changes-title"
          className="text-lg font-semibold text-gray-900"
        >
          Unsaved Changes
        </h2>

        <p
          id="unsaved-changes-description"
          className="mt-2 text-sm text-gray-600"
        >
          You have unsaved changes. Are you sure you want to leave? Your changes
          will be lost.
        </p>

        <div className="mt-6 flex justify-end gap-3">
          <button
            ref={leaveButtonRef}
            type="button"
            onClick={onConfirm}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            Leave
          </button>
          <button
            ref={stayButtonRef}
            type="button"
            onClick={onCancel}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            Stay
          </button>
        </div>
      </div>
    </div>
  );
}
