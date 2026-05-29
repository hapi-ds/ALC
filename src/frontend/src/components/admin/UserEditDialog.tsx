/**
 * UserEditDialog — Dialog form for editing user profile and role assignment.
 *
 * Pre-populates form with current values (full_name, email, role).
 * Uses react-hook-form for validation. On submit, prompts for X-Change-Reason
 * and calls updateUser action. Handles 409 duplicate email errors.
 *
 * Validates: Requirements 7.1, 7.2, 7.3, 7.4
 */

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useForm } from "react-hook-form";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAdminStore } from "@/stores/adminStore";
import { ApiError } from "@/lib/apiClient";
import type { UserListItem } from "@/types/admin";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UserEditDialogProps {
  open: boolean;
  user: UserListItem | null;
  onOpenChange: (open: boolean) => void;
  /** Called after successful update so the parent can refresh the list */
  onSuccess?: () => void;
}

type RoleOption = "system_admin" | "doc_admin" | "it_admin" | "member" | "viewer";

interface EditUserFormValues {
  full_name: string;
  email: string;
  role: RoleOption;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ROLE_OPTIONS: { value: RoleOption; label: string }[] = [
  { value: "system_admin", label: "System Administrator" },
  { value: "doc_admin", label: "Document Administrator" },
  { value: "it_admin", label: "IT Administrator" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function UserEditDialog({ open, user, onOpenChange, onSuccess }: UserEditDialogProps) {
  const { updateUser, isLoading } = useAdminStore();

  const [submitError, setSubmitError] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<EditUserFormValues>();

  // Pre-populate form when user changes or dialog opens (Requirement 7.1)
  // react-hook-form's reset is not a React setState call, so it's safe in effects.
  useEffect(() => {
    if (!open || !user) return;

    reset({
      full_name: user.full_name,
      email: user.email,
      role: user.role as RoleOption,
    });
  }, [open, user, reset]);

  // Focus trap and escape key handling
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onOpenChange(false);
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
  }, [open, onOpenChange]);

  async function onSubmit(data: EditUserFormValues) {
    if (!user) return;

    setSubmitError(null);

    // Prompt for X-Change-Reason (audit compliance)
    const reason = window.prompt(
      "Change Reason (required for audit compliance):",
      `Updated user profile: ${user.username}`
    );

    if (!reason || reason.trim().length === 0) {
      setSubmitError("A change reason is required for audit compliance.");
      return;
    }

    // Build payload with only changed fields
    const payload: Record<string, string> = {};
    if (data.full_name.trim() !== user.full_name) payload.full_name = data.full_name.trim();
    if (data.email.trim() !== user.email) payload.email = data.email.trim();
    if (data.role !== user.role) payload.role = data.role;

    // Nothing changed — close without API call
    if (Object.keys(payload).length === 0) {
      onOpenChange(false);
      return;
    }

    try {
      await updateUser(user.id, payload, reason.trim());
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // Handle duplicate email conflict (Requirement 7.3)
        try {
          const body = JSON.parse(error.body);
          setSubmitError(body.detail ?? "This email address is already in use by another account.");
        } catch {
          setSubmitError("This email address is already in use by another account.");
        }
      } else {
        const message =
          error instanceof Error ? error.message : "Failed to update user. Please try again.";
        setSubmitError(message);
      }
    }
  }

  function handleClose() {
    setSubmitError(null);
    onOpenChange(false);
  }

  if (!open || !user) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isLoading) handleClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="user-edit-dialog-title"
        className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="user-edit-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Edit User
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={handleClose}
            disabled={isLoading}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <p className="mb-4 text-sm text-muted-foreground">
          Update profile information and role for <strong>{user.full_name}</strong>.
        </p>

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

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          {/* Full Name (Requirement 7.2) */}
          <div className="mb-4">
            <label
              htmlFor="edit-full-name"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Full Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="edit-full-name"
              type="text"
              autoComplete="off"
              disabled={isLoading}
              aria-invalid={errors.full_name ? "true" : undefined}
              aria-describedby={errors.full_name ? "edit-full-name-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                errors.full_name ? "border-destructive" : "border-input"
              }`}
              {...register("full_name", {
                required: "Full name is required.",
                minLength: { value: 1, message: "Full name is required." },
                maxLength: { value: 200, message: "Full name must be at most 200 characters." },
              })}
            />
            {errors.full_name && (
              <p id="edit-full-name-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.full_name.message}
              </p>
            )}
          </div>

          {/* Email (Requirement 7.2, 7.3) */}
          <div className="mb-4">
            <label
              htmlFor="edit-email"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Email <span aria-hidden="true">*</span>
            </label>
            <input
              id="edit-email"
              type="email"
              autoComplete="off"
              disabled={isLoading}
              aria-invalid={errors.email ? "true" : undefined}
              aria-describedby={errors.email ? "edit-email-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                errors.email ? "border-destructive" : "border-input"
              }`}
              {...register("email", {
                required: "Email is required.",
                pattern: {
                  value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                  message: "Please enter a valid email address.",
                },
              })}
            />
            {errors.email && (
              <p id="edit-email-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.email.message}
              </p>
            )}
          </div>

          {/* Role (Requirement 7.2, 7.4) */}
          <div className="mb-6">
            <label
              htmlFor="edit-role"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Role <span aria-hidden="true">*</span>
            </label>
            <select
              id="edit-role"
              disabled={isLoading}
              aria-invalid={errors.role ? "true" : undefined}
              aria-describedby={errors.role ? "edit-role-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                errors.role ? "border-destructive" : "border-input"
              }`}
              {...register("role", {
                required: "Role is required.",
              })}
            >
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {errors.role && (
              <p id="edit-role-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.role.message}
              </p>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <Button
              type="submit"
              className="flex-1"
              disabled={isLoading || !isDirty}
            >
              {isLoading && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isLoading ? "Saving…" : "Save Changes"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={handleClose}
              disabled={isLoading}
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
