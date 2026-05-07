import { useState, useEffect, useRef, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVirtualFolderStore } from "@/stores/virtualFolderStore";
import type { VirtualFolderResponse } from "@/types/virtualFolder";

export interface DeleteConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  folder: VirtualFolderResponse;
}

export function DeleteConfirmDialog({
  open,
  onClose,
  folder,
}: DeleteConfirmDialogProps) {
  const { deleteFolder } = useVirtualFolderStore();

  const [changeReason, setChangeReason] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement>(null);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setChangeReason("");
      setIsDeleting(false);
      setError(null);
    }
  }, [open]);

  // Focus trap and escape key handling
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !isDeleting) {
        onClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusableElements =
          dialogRef.current.querySelectorAll<HTMLElement>(
            'input, select, button, textarea, [tabindex]:not([tabindex="-1"])'
          );
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement?.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement?.focus();
          }
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose, isDeleting]);

  async function handleConfirm(e: FormEvent) {
    e.preventDefault();

    if (changeReason.trim().length === 0 || isDeleting) {
      return;
    }

    setIsDeleting(true);
    setError(null);

    try {
      await deleteFolder(folder.id, changeReason.trim());
      onClose();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : String(err);

      if (message.toLowerCase().includes("not found") || message.includes("404")) {
        setError("Folder not found.");
      } else if (message.toLowerCase().includes("system default")) {
        setError("System default folders cannot be deleted.");
      } else {
        setError("Something went wrong. Please try again.");
      }

      setIsDeleting(false);
    }
  }

  if (!open) return null;

  const isConfirmDisabled =
    changeReason.trim().length === 0 || isDeleting;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isDeleting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-confirm-dialog-title"
        className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="delete-confirm-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Delete Folder
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            disabled={isDeleting}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Warning message */}
        <p className="mb-4 text-sm text-muted-foreground">
          The folder <span className="font-medium text-foreground">"{folder.name}"</span> will
          be permanently removed. This action cannot be undone.
        </p>

        {/* Error message */}
        {error && (
          <div
            className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
            aria-live="polite"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleConfirm} noValidate>
          {/* Change reason input */}
          <div className="mb-6">
            <label
              htmlFor="delete-change-reason"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Change Reason <span aria-hidden="true">*</span>
            </label>
            <input
              id="delete-change-reason"
              type="text"
              value={changeReason}
              onChange={(e) => setChangeReason(e.target.value)}
              disabled={isDeleting}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Reason for deleting this folder"
              aria-required="true"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Required for ALCOA+ audit compliance.
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <Button
              type="submit"
              variant="destructive"
              className="flex-1"
              disabled={isConfirmDisabled}
            >
              {isDeleting && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isDeleting ? "Deleting…" : "Delete"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={onClose}
              disabled={isDeleting}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}
