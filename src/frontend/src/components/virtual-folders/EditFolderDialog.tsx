import { useState, useEffect, useRef, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FilterBuilder } from "@/components/virtual-folders/FilterBuilder";
import { useVirtualFolderStore } from "@/stores/virtualFolderStore";
import { validateFolderName, computeFolderDiff } from "@/lib/virtualFolderUtils";
import type { VirtualFolderResponse, TagFilter } from "@/types/virtualFolder";

export interface EditFolderDialogProps {
  open: boolean;
  onClose: () => void;
  folder: VirtualFolderResponse;
}

const SORT_ORDER_OPTIONS = [
  { value: "created_at_desc", label: "Created (newest first)" },
  { value: "created_at_asc", label: "Created (oldest first)" },
  { value: "name_asc", label: "Name (A–Z)" },
  { value: "name_desc", label: "Name (Z–A)" },
] as const;

/**
 * EditFolderDialog is a modal for editing an existing virtual folder's
 * name, tag filter, and sort order. It pre-populates with the current
 * folder values and only sends changed fields on submit.
 *
 * API interaction is handled via useVirtualFolderStore.updateFolder which
 * calls PUT /api/virtual-folders/{id} with X-Change-Reason header.
 */
export function EditFolderDialog({ open, onClose, folder }: EditFolderDialogProps) {
  const updateFolder = useVirtualFolderStore((s) => s.updateFolder);

  const [name, setName] = useState(folder.name);
  const [tagFilter, setTagFilter] = useState<TagFilter>(folder.tag_filter);
  const [sortOrder, setSortOrder] = useState(folder.sort_order);
  const [nameError, setNameError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const dialogRef = useRef<HTMLDivElement>(null);

  // Reset form state when dialog opens or folder changes
  useEffect(() => {
    if (open) {
      setName(folder.name);
      setTagFilter(folder.tag_filter);
      setSortOrder(folder.sort_order);
      setNameError(undefined);
      setSubmitError(null);
      setIsSubmitting(false);
    }
  }, [open, folder]);

  // Focus trap and escape key handling
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
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
  }, [open, onClose]);

  function handleNameChange(value: string) {
    setName(value);
    // Clear name error on change
    if (nameError) {
      setNameError(undefined);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // Validate name
    const validation = validateFolderName(name);
    if (!validation.valid) {
      setNameError(validation.error);
      return;
    }

    // Compute diff — only send changed fields
    const diff = computeFolderDiff(folder, {
      name: name.trim(),
      tag_filter: tagFilter,
      sort_order: sortOrder,
    });

    // If nothing changed, just close
    if (Object.keys(diff).length === 0) {
      onClose();
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await updateFolder(folder.id, diff);
      onClose();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to update folder.";

      // Check for duplicate name error
      if (message.toLowerCase().includes("already exists")) {
        setNameError("A folder with this name already exists.");
      } else {
        setSubmitError(message);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-folder-dialog-title"
        className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg max-h-[90vh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="edit-folder-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Edit Folder
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Submit error */}
        {submitError && (
          <div
            className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
            aria-live="polite"
          >
            {submitError}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          {/* Folder Name */}
          <div className="mb-4">
            <label
              htmlFor="edit-folder-name"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Folder Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="edit-folder-name"
              type="text"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              maxLength={200}
              disabled={isSubmitting}
              aria-invalid={nameError ? "true" : undefined}
              aria-describedby={nameError ? "edit-folder-name-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                nameError ? "border-destructive" : "border-input"
              }`}
              placeholder="Enter folder name"
            />
            {nameError && (
              <p id="edit-folder-name-error" className="mt-1 text-sm text-destructive" role="alert">
                {nameError}
              </p>
            )}
          </div>

          {/* Tag Filter */}
          <div className="mb-4">
            <FilterBuilder value={tagFilter} onChange={setTagFilter} />
          </div>

          {/* Sort Order */}
          <div className="mb-6">
            <label
              htmlFor="edit-folder-sort-order"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Sort Order
            </label>
            <select
              id="edit-folder-sort-order"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              disabled={isSubmitting}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {SORT_ORDER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <Button
              type="submit"
              className="flex-1"
              disabled={isSubmitting}
            >
              {isSubmitting && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isSubmitting ? "Saving…" : "Save Changes"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={onClose}
              disabled={isSubmitting}
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
