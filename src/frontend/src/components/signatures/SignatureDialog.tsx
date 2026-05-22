/**
 * SignatureDialog Component
 *
 * Main modal dialog orchestrating the full electronic signature flow:
 * re-auth → reason/sign → success → transition execution.
 *
 * Controlled by signatureStore.isDialogOpen — renders nothing when false.
 * Reads dialogContext for document info (document_uuid, document_version_id,
 * transition, documentTitle).
 *
 * This component does NOT call backend APIs directly — it delegates to:
 *   - signatureStore.reAuthenticate() → POST /api/v1/auth/re-authenticate
 *   - signatureStore.signDocument() → POST /api/signatures/sign
 *   - workflowExecutionStore.executeTransition() → POST /api/workflows/transition
 *
 * Requirements: 1.1–1.5, 3.4–3.6, 4.5–4.6, 5.1–5.7, 10.2
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { PenTool, X, Loader2, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSignatureStore } from "@/stores/signatureStore";
import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { ReAuthForm } from "./ReAuthForm";
import { TokenCountdown } from "./TokenCountdown";
import { ReasonSelector } from "./ReasonSelector";
import {
  isSignButtonEnabled,
  formatSignatureReason,
} from "@/lib/signatureUtils";
import type { SignatureReasonCategory } from "@/types/signature";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DialogStep = "reauth" | "sign" | "success" | "error";

// ---------------------------------------------------------------------------
// SignatureDialog
// ---------------------------------------------------------------------------

export function SignatureDialog() {
  // Store state
  const isDialogOpen = useSignatureStore((s) => s.isDialogOpen);
  const dialogContext = useSignatureStore((s) => s.dialogContext);
  const signatureToken = useSignatureStore((s) => s.signatureToken);
  const remainingSeconds = useSignatureStore((s) => s.remainingSeconds);
  const isSigning = useSignatureStore((s) => s.isSigning);
  const signError = useSignatureStore((s) => s.signError);
  const lastSignResult = useSignatureStore((s) => s.lastSignResult);
  const _password = useSignatureStore((s) => s._password);
  const closeSignatureDialog = useSignatureStore(
    (s) => s.closeSignatureDialog
  );
  const signDocument = useSignatureStore((s) => s.signDocument);
  const clearToken = useSignatureStore((s) => s.clearToken);

  const executeTransition = useWorkflowExecutionStore(
    (s) => s.executeTransition
  );

  // Local state
  const [step, setStep] = useState<DialogStep>("reauth");
  const [reasonCategory, setReasonCategory] = useState("");
  const [signatureNote, setSignatureNote] = useState("");
  const [isLocked, setIsLocked] = useState(false);
  const [lockoutRemaining, setLockoutRemaining] = useState(0);
  const [tokenExpiredMessage, setTokenExpiredMessage] = useState<string | null>(
    null
  );
  const [transitionError, setTransitionError] = useState<string | null>(null);

  // Refs
  const dialogRef = useRef<HTMLDivElement>(null);
  const lockoutIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null
  );
  const prevTokenRef = useRef<string | null>(signatureToken);

  // ---------------------------------------------------------------------------
  // Reset local state when dialog opens/closes
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (isDialogOpen) {
      setStep("reauth");
      setReasonCategory("");
      setSignatureNote("");
      setIsLocked(false);
      setLockoutRemaining(0);
      setTokenExpiredMessage(null);
      setTransitionError(null);
    }
  }, [isDialogOpen]);

  // ---------------------------------------------------------------------------
  // Token expiry handling: watch signatureToken
  // When token becomes null while on "sign" step, return to reauth
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (
      prevTokenRef.current !== null &&
      signatureToken === null &&
      step === "sign"
    ) {
      setStep("reauth");
      setTokenExpiredMessage(
        "Session expired. Please re-authenticate to continue."
      );
      // Preserve reasonCategory and signatureNote
    }
    prevTokenRef.current = signatureToken;
  }, [signatureToken, step]);

  // ---------------------------------------------------------------------------
  // Watch lastSignResult to advance to success step
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (lastSignResult && step === "sign") {
      setStep("success");
    }
  }, [lastSignResult, step]);

  // ---------------------------------------------------------------------------
  // Watch signError for 401 → return to reauth
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (signError && step === "sign") {
      if (
        signError.includes("401") ||
        signError.includes("expired") ||
        signError.includes("Authentication") ||
        signError.includes("Unauthorized")
      ) {
        clearToken();
        setStep("reauth");
        setTokenExpiredMessage("Authentication expired. Please re-authenticate.");
        // Preserve reasonCategory and signatureNote
      }
    }
  }, [signError, step, clearToken]);

  // ---------------------------------------------------------------------------
  // Lockout management (429 handling)
  // ---------------------------------------------------------------------------

  function handleLockout() {
    setIsLocked(true);
    setLockoutRemaining(60);

    if (lockoutIntervalRef.current) {
      clearInterval(lockoutIntervalRef.current);
    }

    lockoutIntervalRef.current = setInterval(() => {
      setLockoutRemaining((prev) => {
        if (prev <= 1) {
          if (lockoutIntervalRef.current) {
            clearInterval(lockoutIntervalRef.current);
            lockoutIntervalRef.current = null;
          }
          setIsLocked(false);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  // Cleanup lockout interval on unmount
  useEffect(() => {
    return () => {
      if (lockoutIntervalRef.current) {
        clearInterval(lockoutIntervalRef.current);
      }
    };
  }, []);

  // Watch for 429 errors from the store
  const reAuthError = useSignatureStore((s) => s.reAuthError);
  useEffect(() => {
    if (
      reAuthError &&
      (reAuthError.includes("429") ||
        reAuthError.includes("locked") ||
        reAuthError.includes("too many"))
    ) {
      handleLockout();
    }
  }, [reAuthError]);

  // ---------------------------------------------------------------------------
  // Escape key handling
  // ---------------------------------------------------------------------------

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!isDialogOpen) return;
      if (e.key === "Escape") {
        e.preventDefault();
        closeSignatureDialog();
      }
    },
    [isDialogOpen, closeSignatureDialog]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // ---------------------------------------------------------------------------
  // Focus trapping
  // ---------------------------------------------------------------------------

  const handleFocusTrap = useCallback(
    (e: KeyboardEvent) => {
      if (!isDialogOpen || !dialogRef.current || e.key !== "Tab") return;

      const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
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
    },
    [isDialogOpen]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleFocusTrap);
    return () => document.removeEventListener("keydown", handleFocusTrap);
  }, [handleFocusTrap]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleReAuthSuccess() {
    setStep("sign");
    setTokenExpiredMessage(null);
  }

  async function handleSign() {
    if (!dialogContext || !_password) return;

    const formattedReason = formatSignatureReason(
      reasonCategory as SignatureReasonCategory,
      signatureNote
    );

    await signDocument(
      dialogContext.document_uuid,
      dialogContext.document_version_id,
      dialogContext.transition,
      formattedReason,
      _password
    );
  }

  async function handleContinue() {
    if (!dialogContext) return;

    // Extract target state from transition (after "→")
    const separatorIdx = dialogContext.transition.indexOf("→");
    const targetState =
      separatorIdx !== -1
        ? dialogContext.transition.substring(separatorIdx + 1)
        : dialogContext.transition;

    // Format the change reason
    const changeReason = formatSignatureReason(
      reasonCategory as SignatureReasonCategory,
      signatureNote
    );

    closeSignatureDialog();

    // Execute the transition (skipSignatureCheck=true will be supported
    // once workflowExecutionStore is updated in a later task)
    const success = await executeTransition(
      dialogContext.document_uuid,
      targetState,
      changeReason
    );

    if (!success) {
      setTransitionError(
        "Transition failed despite signature being recorded. Please contact an administrator."
      );
      setStep("error");
    }
  }

  // ---------------------------------------------------------------------------
  // Derived values
  // ---------------------------------------------------------------------------

  if (!isDialogOpen || !dialogContext) return null;

  // Extract current state and target state from transition
  const separatorIndex = dialogContext.transition.indexOf("→");
  const currentState =
    separatorIndex !== -1
      ? dialogContext.transition.substring(0, separatorIndex)
      : "";
  const targetState =
    separatorIndex !== -1
      ? dialogContext.transition.substring(separatorIndex + 1)
      : dialogContext.transition;

  const signButtonEnabled =
    isSignButtonEnabled(reasonCategory, signatureNote) && !isSigning;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget && step !== "success") {
          closeSignatureDialog();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="signature-dialog-title"
        className="w-full max-w-md rounded-lg bg-background border shadow-lg p-6 space-y-4"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <PenTool className="h-5 w-5 text-primary" aria-hidden="true" />
            <h2
              id="signature-dialog-title"
              className="text-lg font-semibold"
            >
              Electronic Signature Required
            </h2>
          </div>
          {step !== "error" && (
            <button
              type="button"
              onClick={closeSignatureDialog}
              className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              aria-label="Close"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>

        {/* Document info */}
        <div className="rounded-md bg-muted/50 px-3 py-2 space-y-1">
          <p className="text-sm font-medium">{dialogContext.documentTitle}</p>
          <p className="text-xs text-muted-foreground">
            {currentState} → {targetState}
          </p>
          <p className="text-xs text-muted-foreground">
            Transition: {dialogContext.transition}
          </p>
        </div>

        {/* Token expired message */}
        {tokenExpiredMessage && step === "reauth" && (
          <p className="text-sm text-amber-600" role="alert">
            {tokenExpiredMessage}
          </p>
        )}

        {/* Step content */}
        {step === "reauth" && (
          <ReAuthForm
            onSuccess={handleReAuthSuccess}
            isLocked={isLocked}
            lockoutRemaining={lockoutRemaining}
          />
        )}

        {step === "sign" && (
          <div className="space-y-4">
            {/* Token countdown */}
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                Token validity:
              </span>
              <TokenCountdown remainingSeconds={remainingSeconds} />
            </div>

            {/* Reason selector */}
            <ReasonSelector
              reasonCategory={reasonCategory}
              signatureNote={signatureNote}
              onReasonCategoryChange={setReasonCategory}
              onSignatureNoteChange={setSignatureNote}
              disabled={isSigning}
            />

            {/* Signing progress message */}
            {isSigning && (
              <p className="text-sm text-muted-foreground flex items-center gap-2">
                <Loader2
                  className="h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
                Applying PAdES signature...
              </p>
            )}

            {/* Sign error (non-401) */}
            {signError &&
              !signError.includes("401") &&
              !signError.includes("expired") &&
              !signError.includes("Authentication") &&
              !signError.includes("Unauthorized") && (
                <p className="text-sm text-destructive" role="alert">
                  {signError}
                </p>
              )}

            {/* Action buttons */}
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={closeSignatureDialog}
                disabled={isSigning}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSign}
                disabled={!signButtonEnabled}
              >
                {isSigning && (
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                )}
                Sign Document
              </Button>
            </div>
          </div>
        )}

        {step === "success" && lastSignResult && (
          <div className="space-y-4">
            {/* Success icon */}
            <div className="flex items-center gap-2 text-green-600">
              <CheckCircle className="h-5 w-5" aria-hidden="true" />
              <span className="font-medium">Signature Applied Successfully</span>
            </div>

            {/* Signature details */}
            <div className="rounded-md bg-muted/50 px-3 py-2 space-y-1 text-sm">
              <p>
                <span className="text-muted-foreground">Signer:</span>{" "}
                {lastSignResult.stamp.signer_name}
              </p>
              <p>
                <span className="text-muted-foreground">Signed at:</span>{" "}
                {new Intl.DateTimeFormat(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(lastSignResult.stamp.signed_at))}
              </p>
              <p>
                <span className="text-muted-foreground">Reason:</span>{" "}
                {lastSignResult.stamp.reason}
              </p>
              <p>
                <span className="text-muted-foreground">Signature hash:</span>{" "}
                <code className="text-xs">
                  {lastSignResult.signature_hash.substring(0, 16)}…
                </code>
              </p>
            </div>

            {/* Continue button */}
            <div className="flex justify-end">
              <Button size="sm" onClick={handleContinue}>
                Continue
              </Button>
            </div>
          </div>
        )}

        {step === "error" && (
          <div className="space-y-4">
            <p className="text-sm text-destructive" role="alert">
              {transitionError ||
                "Transition failed despite signature being recorded. Please contact an administrator."}
            </p>

            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={closeSignatureDialog}
              >
                Close
              </Button>
            </div>
          </div>
        )}

        {/* Cancel button for reauth step */}
        {step === "reauth" && (
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={closeSignatureDialog}
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
