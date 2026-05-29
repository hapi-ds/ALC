/**
 * UserCreateDialog — Dialog form for creating new users.
 *
 * Uses react-hook-form for validation and the admin Zustand store
 * for the createUser action. On success, displays the temporary
 * password for the administrator to communicate to the new user.
 *
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.6
 */

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useForm } from "react-hook-form";
import { Loader2, X, CheckCircle2, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAdminStore } from "@/stores/adminStore";
import { ApiError } from "@/lib/apiClient";
import type { UserCreatePayload } from "@/types/admin";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UserCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after successful user creation so the parent can refresh the list */
  onSuccess?: () => void;
}

type RoleOption = UserCreatePayload["role"];

interface UserCreateFormValues {
  username: string;
  email: string;
  full_name: string;
  role: RoleOption;
}

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

export function UserCreateDialog({ open, onOpenChange, onSuccess }: UserCreateDialogProps) {
  const { createUser, isLoading } = useAdminStore();

  const [submitError, setSubmitError] = useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [createdUsername, setCreatedUsername] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const dialogRef = useRef<HTMLDivElement>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UserCreateFormValues>({
    defaultValues: {
      username: "",
      email: "",
      full_name: "",
      role: "member",
    },
  });

  // Reset form state when dialog opens
  useEffect(() => {
    if (open) {
      reset();
      setSubmitError(null);
      setTemporaryPassword(null);
      setCreatedUsername(null);
      setCopied(false);
    }
  }, [open, reset]);

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

  async function onSubmit(data: UserCreateFormValues) {
    setSubmitError(null);

    // Prompt for X-Change-Reason
    const reason = window.prompt(
      "Change Reason (required for audit compliance):",
      `Created user account: ${data.username}`
    );

    if (!reason || reason.trim().length === 0) {
      setSubmitError("A change reason is required for audit compliance.");
      return;
    }

    const payload: UserCreatePayload = {
      username: data.username.trim(),
      email: data.email.trim(),
      full_name: data.full_name.trim(),
      role: data.role,
    };

    try {
      const response = await createUser(payload, reason.trim());
      setTemporaryPassword(response.temporary_password);
      setCreatedUsername(response.username);
      onSuccess?.();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // Parse the conflict error body for duplicate username/email
        try {
          const body = JSON.parse(error.body);
          setSubmitError(body.detail ?? "A user with this username or email already exists.");
        } catch {
          setSubmitError("A user with this username or email already exists.");
        }
      } else {
        const message =
          error instanceof Error ? error.message : "Failed to create user. Please try again.";
        setSubmitError(message);
      }
    }
  }

  function handleCopyPassword() {
    if (temporaryPassword) {
      navigator.clipboard.writeText(temporaryPassword);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function handleClose() {
    onOpenChange(false);
  }

  if (!open) return null;

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
        aria-labelledby="user-create-dialog-title"
        className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="user-create-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            {temporaryPassword ? "User Created Successfully" : "Create New User"}
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

        {/* Success state: show temporary password */}
        {temporaryPassword ? (
          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-md bg-green-50 p-4 dark:bg-green-950/20">
              <CheckCircle2 className="h-5 w-5 text-green-600 mt-0.5 shrink-0" aria-hidden="true" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-green-800 dark:text-green-200">
                  User &ldquo;{createdUsername}&rdquo; has been created.
                </p>
                <p className="text-sm text-green-700 dark:text-green-300">
                  Communicate the temporary password below securely to the new user.
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-foreground">
                Temporary Password
              </label>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded-md border border-border bg-muted px-3 py-2 text-sm font-mono">
                  {temporaryPassword}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={handleCopyPassword}
                  aria-label="Copy password to clipboard"
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              {copied && (
                <p className="text-xs text-green-600" aria-live="polite">
                  Copied to clipboard
                </p>
              )}
            </div>

            <div className="pt-2">
              <Button
                type="button"
                className="w-full"
                onClick={handleClose}
              >
                Done
              </Button>
            </div>
          </div>
        ) : (
          <>
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
              {/* Username */}
              <div className="mb-4">
                <label
                  htmlFor="create-username"
                  className="mb-1.5 block text-sm font-medium text-foreground"
                >
                  Username <span aria-hidden="true">*</span>
                </label>
                <input
                  id="create-username"
                  type="text"
                  autoComplete="off"
                  disabled={isLoading}
                  aria-invalid={errors.username ? "true" : undefined}
                  aria-describedby={errors.username ? "create-username-error" : "create-username-hint"}
                  className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                    errors.username ? "border-destructive" : "border-input"
                  }`}
                  placeholder="e.g. john.doe"
                  {...register("username", {
                    required: "Username is required.",
                    minLength: { value: 3, message: "Username must be at least 3 characters." },
                    maxLength: { value: 100, message: "Username must be at most 100 characters." },
                    pattern: {
                      value: /^[a-zA-Z0-9_.-]+$/,
                      message: "Username may only contain letters, numbers, underscores, dots, and hyphens.",
                    },
                  })}
                />
                {errors.username ? (
                  <p id="create-username-error" className="mt-1 text-sm text-destructive" role="alert">
                    {errors.username.message}
                  </p>
                ) : (
                  <p id="create-username-hint" className="mt-1 text-xs text-muted-foreground">
                    Letters, numbers, underscores, dots, and hyphens only.
                  </p>
                )}
              </div>

              {/* Email */}
              <div className="mb-4">
                <label
                  htmlFor="create-email"
                  className="mb-1.5 block text-sm font-medium text-foreground"
                >
                  Email <span aria-hidden="true">*</span>
                </label>
                <input
                  id="create-email"
                  type="email"
                  autoComplete="off"
                  disabled={isLoading}
                  aria-invalid={errors.email ? "true" : undefined}
                  aria-describedby={errors.email ? "create-email-error" : undefined}
                  className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                    errors.email ? "border-destructive" : "border-input"
                  }`}
                  placeholder="user@example.com"
                  {...register("email", {
                    required: "Email is required.",
                    pattern: {
                      value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                      message: "Please enter a valid email address.",
                    },
                  })}
                />
                {errors.email && (
                  <p id="create-email-error" className="mt-1 text-sm text-destructive" role="alert">
                    {errors.email.message}
                  </p>
                )}
              </div>

              {/* Full Name */}
              <div className="mb-4">
                <label
                  htmlFor="create-full-name"
                  className="mb-1.5 block text-sm font-medium text-foreground"
                >
                  Full Name <span aria-hidden="true">*</span>
                </label>
                <input
                  id="create-full-name"
                  type="text"
                  autoComplete="off"
                  disabled={isLoading}
                  aria-invalid={errors.full_name ? "true" : undefined}
                  aria-describedby={errors.full_name ? "create-full-name-error" : undefined}
                  className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                    errors.full_name ? "border-destructive" : "border-input"
                  }`}
                  placeholder="John Doe"
                  {...register("full_name", {
                    required: "Full name is required.",
                    minLength: { value: 1, message: "Full name is required." },
                    maxLength: { value: 200, message: "Full name must be at most 200 characters." },
                  })}
                />
                {errors.full_name && (
                  <p id="create-full-name-error" className="mt-1 text-sm text-destructive" role="alert">
                    {errors.full_name.message}
                  </p>
                )}
              </div>

              {/* Role */}
              <div className="mb-6">
                <label
                  htmlFor="create-role"
                  className="mb-1.5 block text-sm font-medium text-foreground"
                >
                  Role <span aria-hidden="true">*</span>
                </label>
                <select
                  id="create-role"
                  disabled={isLoading}
                  aria-invalid={errors.role ? "true" : undefined}
                  aria-describedby={errors.role ? "create-role-error" : undefined}
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
                  <p id="create-role-error" className="mt-1 text-sm text-destructive" role="alert">
                    {errors.role.message}
                  </p>
                )}
              </div>

              {/* Action buttons */}
              <div className="flex gap-3">
                <Button
                  type="submit"
                  className="flex-1"
                  disabled={isLoading}
                >
                  {isLoading && (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  )}
                  {isLoading ? "Creating…" : "Create User"}
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
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
