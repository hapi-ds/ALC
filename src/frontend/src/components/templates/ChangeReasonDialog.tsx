import { useState, useEffect, useRef, useCallback } from "react";

interface ChangeReasonDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (reason: string) => void;
  title?: string;
}

const MIN_REASON_LENGTH = 10;

/**
 * Modal dialog for collecting a change reason before mutating version actions.
 * Requires at least 10 characters to ensure meaningful audit documentation.
 * Implements focus trap, Escape to close, and aria-labelledby for accessibility.
 */
export function ChangeReasonDialog({
  isOpen,
  onClose,
  onSubmit,
  title = "Change Reason",
}: ChangeReasonDialogProps) {
  const [reason, setReason] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const submitButtonRef = useRef<HTMLButtonElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const isValid = reason.trim().length >= MIN_REASON_LENGTH;

  // Reset reason when dialog opens
  useEffect(() => {
    if (isOpen) {
      setReason("");
      requestAnimationFrame(() => {
        textareaRef.current?.focus();
      });
    }
  }, [isOpen]);

  // Handle keyboard events: Escape to close, Tab to trap focus
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === "Tab") {
        const focusableElements = [
          textareaRef.current,
          cancelButtonRef.current,
          submitButtonRef.current,
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
    [isOpen, onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [isOpen, handleKeyDown]);

  const handleSubmit = () => {
    if (isValid) {
      onSubmit(reason.trim());
    }
  };

  if (!isOpen) return null;

  const charCount = reason.trim().length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      aria-hidden={!isOpen}
    >
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-black/50"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-reason-title"
        className="relative z-10 w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <h2
          id="change-reason-title"
          className="text-lg font-semibold text-gray-900"
        >
          {title}
        </h2>

        <p className="mt-2 text-sm text-gray-600">
          Please provide a reason for this change. This will be recorded in the
          audit trail for ALCOA+ compliance.
        </p>

        <div className="mt-4">
          <label
            htmlFor="change-reason-input"
            className="block text-sm font-medium text-gray-700"
          >
            Reason
          </label>
          <textarea
            ref={textareaRef}
            id="change-reason-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe the reason for this change..."
            rows={4}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <p
            className={`mt-1 text-xs ${
              charCount >= MIN_REASON_LENGTH
                ? "text-green-600"
                : "text-gray-500"
            }`}
          >
            {charCount}/{MIN_REASON_LENGTH} characters minimum
          </p>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onClose}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          >
            Cancel
          </button>
          <button
            ref={submitButtonRef}
            type="button"
            onClick={handleSubmit}
            disabled={!isValid}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}
