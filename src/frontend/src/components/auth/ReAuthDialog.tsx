import { useState, useEffect, useRef, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/authStore";

export interface ReAuthDialogProps {
  open: boolean;
  onSuccess: (signatureToken: string) => void;
  onCancel: () => void;
}

const MAX_ATTEMPTS = 5;

export function ReAuthDialog({ open, onSuccess, onCancel }: ReAuthDialogProps) {
  const navigate = useNavigate();
  const { user, reAuthenticate, clearSession } = useAuthStore();

  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedAttempts, setFailedAttempts] = useState(0);

  const passwordInputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setPassword("");
      setError(null);
      setFailedAttempts(0);
      setIsSubmitting(false);
    }
  }, [open]);

  // Focus trap: focus the password input when dialog opens
  useEffect(() => {
    if (open) {
      // Small delay to ensure the DOM is rendered
      const timer = setTimeout(() => {
        passwordInputRef.current?.focus();
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // Trap focus within the dialog
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onCancel();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'input, button, [tabindex]:not([tabindex="-1"])'
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
  }, [open, onCancel]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!password.trim()) {
      setError("Password is required");
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      const result = await reAuthenticate(password);

      if (result.verified && result.signatureToken) {
        onSuccess(result.signatureToken);
      } else {
        // Authentication failed — increment failure count
        const newAttempts = failedAttempts + 1;
        setFailedAttempts(newAttempts);

        if (newAttempts >= MAX_ATTEMPTS) {
          clearSession("locked");
          navigate("/login", { replace: true });
        } else {
          setError(
            `Incorrect password. ${MAX_ATTEMPTS - newAttempts} attempt${MAX_ATTEMPTS - newAttempts === 1 ? "" : "s"} remaining.`
          );
        }
      }
    } catch {
      // Network errors (thrown by the store) do NOT count toward the attempt limit
      setError("Connection error. Please try again.");
    } finally {
      setIsSubmitting(false);
      setPassword("");
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      aria-hidden="true"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reauth-dialog-title"
        aria-describedby="reauth-dialog-description"
        className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        <h2
          id="reauth-dialog-title"
          className="text-lg font-semibold text-foreground"
        >
          Re-Authentication Required
        </h2>
        <p
          id="reauth-dialog-description"
          className="mt-1 text-sm text-muted-foreground"
        >
          Please enter your password to confirm your identity for this action.
        </p>

        <form onSubmit={handleSubmit} className="mt-4" noValidate>
          {/* Error message */}
          <div aria-live="polite" aria-atomic="true" className="mb-4">
            {error && (
              <p
                id="reauth-error"
                className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
                role="alert"
              >
                {error}
              </p>
            )}
          </div>

          {/* Username (read-only) */}
          <div className="mb-4">
            <label
              htmlFor="reauth-username"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Username
            </label>
            <input
              id="reauth-username"
              type="text"
              value={user?.username ?? ""}
              readOnly
              tabIndex={-1}
              className="flex h-9 w-full rounded-md border border-input bg-muted px-3 py-1 text-sm text-muted-foreground shadow-sm"
            />
          </div>

          {/* Password field */}
          <div className="mb-6">
            <label
              htmlFor="reauth-password"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Password
            </label>
            <input
              ref={passwordInputRef}
              id="reauth-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={error ? "reauth-error" : undefined}
              aria-invalid={error ? "true" : undefined}
              disabled={isSubmitting}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            />
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
              {isSubmitting ? "Verifying…" : "Confirm"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
