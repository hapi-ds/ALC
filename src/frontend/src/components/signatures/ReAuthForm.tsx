/**
 * ReAuthForm Component
 *
 * Re-authentication form shown as the first step in the Signature Dialog.
 * Collects the user's password for identity verification before signing,
 * as required by 21 CFR Part 11 for electronic signature operations.
 *
 * This component does NOT call backend APIs directly — it delegates to
 * signatureStore.reAuthenticate(password) which calls:
 *   POST /api/v1/auth/re-authenticate (verified in signatureStore.ts)
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9
 */

import { useEffect, useRef, useState } from "react";
import { Lock, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSignatureStore } from "@/stores/signatureStore";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ReAuthFormProps {
  onSuccess: () => void;
  isLocked: boolean;
  lockoutRemaining: number;
}

// ---------------------------------------------------------------------------
// ReAuthForm
// ---------------------------------------------------------------------------

export function ReAuthForm({
  onSuccess,
  isLocked,
  lockoutRemaining,
}: ReAuthFormProps) {
  const [password, setPassword] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const isReAuthenticating = useSignatureStore(
    (state) => state.isReAuthenticating
  );
  const reAuthError = useSignatureStore((state) => state.reAuthError);
  const signatureToken = useSignatureStore((state) => state.signatureToken);

  // Track previous signatureToken to detect transition from null → non-null
  const prevTokenRef = useRef<string | null>(signatureToken);

  useEffect(() => {
    if (prevTokenRef.current === null && signatureToken !== null) {
      onSuccess();
    }
    prevTokenRef.current = signatureToken;
  }, [signatureToken, onSuccess]);

  // Focus the password input on mount
  useEffect(() => {
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  }, []);

  // Re-focus password input when an auth error occurs (401)
  useEffect(() => {
    if (reAuthError && reAuthError.includes("Invalid password")) {
      setPassword("");
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [reAuthError]);

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------

  const isButtonDisabled =
    password.length === 0 || isLocked || isReAuthenticating;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleSubmit() {
    if (isButtonDisabled) return;
    await useSignatureStore.getState().reAuthenticate(password);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !isButtonDisabled) {
      e.preventDefault();
      handleSubmit();
    }
  }

  // ---------------------------------------------------------------------------
  // Error message rendering
  // ---------------------------------------------------------------------------

  function renderErrorMessage() {
    if (isLocked) {
      return (
        <p className="text-sm text-destructive" role="alert" aria-live="assertive">
          Account temporarily locked due to too many failed attempts. Please
          wait {lockoutRemaining} second{lockoutRemaining !== 1 ? "s" : ""}{" "}
          before trying again.
        </p>
      );
    }

    if (!reAuthError) return null;

    // Determine the appropriate message based on error content
    let message: string;

    if (
      reAuthError.includes("Invalid password") ||
      reAuthError.includes("401") ||
      reAuthError.includes("invalid") ||
      reAuthError.includes("credentials")
    ) {
      message = "Invalid password. Please try again.";
    } else if (
      reAuthError.includes("Network") ||
      reAuthError.includes("network") ||
      reAuthError.includes("Failed to fetch") ||
      reAuthError.includes("Unable to reach")
    ) {
      message =
        "Network error: Unable to reach the server. Please check your connection.";
    } else if (
      reAuthError.includes("500") ||
      reAuthError.includes("502") ||
      reAuthError.includes("503") ||
      reAuthError.includes("Server") ||
      reAuthError.includes("server error")
    ) {
      message =
        "A server error occurred. Please try again shortly.";
    } else {
      // Fallback: display the raw error
      message = reAuthError;
    }

    return (
      <p className="text-sm text-destructive" role="alert" aria-live="assertive">
        {message}
      </p>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Lock className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
        <h3 className="text-base font-semibold">Verify Your Identity</h3>
      </div>

      {/* Informational text */}
      <p className="text-sm text-muted-foreground" id="reauth-info">
        Re-authentication is required per 21 CFR Part 11 for electronic
        signature operations.
      </p>

      {/* Password input */}
      <div className="space-y-2">
        <label
          htmlFor="reauth-password"
          className="text-sm font-medium"
        >
          Password
        </label>
        <input
          ref={inputRef}
          id="reauth-password"
          type="password"
          maxLength={128}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isReAuthenticating || isLocked}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          placeholder="Enter your password"
          aria-required="true"
          aria-describedby="reauth-info"
          autoComplete="current-password"
        />

        {/* Error message */}
        {renderErrorMessage()}
      </div>

      {/* Verify Identity button */}
      <Button
        type="button"
        onClick={handleSubmit}
        disabled={isButtonDisabled}
        className="w-full"
      >
        {isReAuthenticating && (
          <Loader2
            className="h-4 w-4 animate-spin"
            aria-hidden="true"
          />
        )}
        {isReAuthenticating ? "Verifying..." : "Verify Identity"}
      </Button>
    </div>
  );
}
