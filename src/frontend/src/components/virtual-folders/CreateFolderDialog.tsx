import { useState, useEffect, useRef, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FilterBuilder } from "./FilterBuilder";
import { validateFolderName } from "@/lib/virtualFolderUtils";
import { useVirtualFolderStore } from "@/stores/virtualFolderStore";
import type { TagFilter } from "@/types/virtualFolder";

export interface CreateFolderDialogProps {
  open: boolean;
  onClose: () => void;
}

const SORT_ORDER_OPTIONS = [
  { value: "created_at_desc", label: "Created (newest first)" },
  { value: "created_at_asc", label: "Created (oldest first)" },
  { value: "name_asc", label: "Name (A–Z)" },
  { value: "name_desc", label: "Name (Z–A)" },
] as const;

/**
 * CreateFolderDialog provides a modal for creating a new virtual folder.
 *
 * Features:
 * - Name input validated via validateFolderName (1–200 chars, no whitespace-only)
 * - FilterBuilder for tag filter construction
 * - Sort order dropdown (created_at_desc default)
 * - Submit disabled until name valid and filter non-empty
 * - Loading indicator while request in progress
 * - Handles 400 duplicate name error with inline validation
 * - Handles network/server errors with generic message, preserves user data
 * - On success: closes dialog, store refreshes folder list
 *
 * The store's createFolder action handles the API call to POST /api/virtual-folders
 * with the X-Change-Reason header for ALCOA+ audit compliance.
 */
export function CreateFolderDialog({ open, onClose }: CreateFolderDialogProps) {
  const createFolder = useVirtualFolderStore((s) => s.createFolder);

  const [name, setName] = useState("");
  const [tagFilter, setTagFilter] = useState<TagFilter>({});
  const [sortOrder, setSortOrder] = useState("created_at_desc");
  const [nameError, setNameError] = useState<string | undefined>(undefined);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const dialogRef = useRef<HTMLDivElement>(null);

  // Reset form state when dialog opens
  useEffect(() => {
    if (open) {
      setName("");
      setTagFilter({});
      setSortOrder("created_at_desc");
      setNameError(undefined);
      setSubmitError(null);
      setIsSubmitting(false);
    }
  }, [open]);

  // Focus trap and escape key handling
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !isSubmitting) {
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
  }, [open, onClose, isSubmitting]);

  // Validate name on change
  function handleNameChange(value: string) {
    setName(value);
    // Clear duplicate name error when user edits
    if (nameError === "A folder with this name already exists.") {
      setNameError(undefined);
    }
    // Only show validation error if user has typed something
    if (value.length > 0) {
      const result = validateFolderName(value);
      setNameError(result.valid ? undefined : result.error);
    } else {
      setNameError(undefined);
    }
  }

  // Determine if filter is non-empty
  const isFilterEmpty =
    (!tagFilter.tags || tagFilter.tags.length === 0) && !tagFilter.status;

  // Determine if submit should be disabled
  const nameValidation = validateFolderName(name);
  const isSubmitDisabled =
    isSubmitting || !nameValidation.valid || isFilterEmpty;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // Final validation
    const validation = validateFolderName(name);
    if (!validation.valid) {
      setNameError(validation.error);
      return;
    }

    if (isFilterEmpty) {
      return;
    }

    setSubmitError(null);
    setIsSubmitting(true);

    try {
      await createFolder(name.trim(), tagFilter, sortOrder);
      onClose();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : String(error);

      if (message.includes("already exists")) {
        setNameError("A folder with this name already exists.");
      } else {
        setSubmitError("Something went wrong. Please try again.");
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
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-folder-dialog-title"
        className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="create-folder-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Create Folder
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

        {/* Generic submit error */}
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
              htmlFor="create-folder-name"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Folder Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="create-folder-name"
              type="text"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              maxLength={200}
              disabled={isSubmitting}
              aria-invalid={nameError ? "true" : undefined}
              aria-describedby={nameError ? "create-folder-name-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                nameError ? "border-destructive" : "border-input"
              }`}
              placeholder="Enter folder name"
            />
            {nameError && (
              <p
                id="create-folder-name-error"
                className="mt-1 text-sm text-destructive"
                role="alert"
              >
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
              htmlFor="create-folder-sort-order"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Sort Order
            </label>
            <select
              id="create-folder-sort-order"
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
              disabled={isSubmitDisabled}
            >
              {isSubmitting && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isSubmitting ? "Creating…" : "Create Folder"}
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
