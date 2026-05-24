import { useState, useEffect, useRef, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { Loader2, X, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { submitReview, listAuditProfiles } from "@/lib/reviews-api";
import type { AuditProfile } from "@/lib/reviews-api";

export interface SubmitForReviewModalProps {
  open: boolean;
  onClose: () => void;
  documentId: number;
  documentVersionId: number;
  documentTitle: string;
  /** Called after successful submission with the new session ID */
  onSubmitted?: (sessionId: number) => void;
}

/**
 * Modal for submitting a document for multi-agent review.
 *
 * Allows the user to select an audit profile (or use the company default)
 * and provide a change reason (required for ALCOA+ compliance).
 * Calls POST /api/reviews with X-Change-Reason header.
 *
 * Validates: Requirements 11.8
 */
export function SubmitForReviewModal({
  open,
  onClose,
  documentId,
  documentVersionId,
  documentTitle,
  onSubmitted,
}: SubmitForReviewModalProps) {
  const [profiles, setProfiles] = useState<AuditProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [profilesError, setProfilesError] = useState<string | null>(null);

  const [selectedProfileId, setSelectedProfileId] = useState<string>("");
  const [changeReason, setChangeReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement>(null);

  // Fetch audit profiles when modal opens
  useEffect(() => {
    if (!open) return;

    setSelectedProfileId("");
    setChangeReason("");
    setIsSubmitting(false);
    setError(null);
    setProfilesError(null);

    async function loadProfiles() {
      setProfilesLoading(true);
      try {
        const data = await listAuditProfiles();
        setProfiles(data);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setProfilesError(message);
        setProfiles([]);
      } finally {
        setProfilesLoading(false);
      }
    }

    loadProfiles();
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
  }, [open, onClose, isSubmitting]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    if (changeReason.trim().length === 0 || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const auditProfileId = selectedProfileId
        ? Number(selectedProfileId)
        : undefined;

      const session = await submitReview(
        {
          document_id: documentId,
          document_version_id: documentVersionId,
          audit_profile_id: auditProfileId ?? null,
        },
        changeReason.trim(),
      );

      onSubmitted?.(session.id);
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);

      if (message.includes("409")) {
        setError(
          "This document already has an active review session. Please wait for it to complete."
        );
      } else if (message.includes("422")) {
        setError(
          "No default audit profile configured. Please select a profile or configure a default."
        );
      } else if (message.includes("404")) {
        setError("Document not found.");
      } else {
        setError("Failed to submit review. Please try again.");
      }

      setIsSubmitting(false);
    }
  }

  if (!open) return null;

  const defaultProfile = profiles.find((p) => p.is_default);
  const isSubmitDisabled = changeReason.trim().length === 0 || isSubmitting;

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
        aria-labelledby="submit-review-dialog-title"
        className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="submit-review-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Submit for Review
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

        {/* Document info */}
        <p className="mb-4 text-sm text-muted-foreground">
          Submit{" "}
          <span className="font-medium text-foreground">
            "{documentTitle}"
          </span>{" "}
          for multi-agent compliance review.
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

        <form onSubmit={handleSubmit} noValidate>
          {/* Audit Profile Selection */}
          <div className="mb-4">
            <label
              htmlFor="audit-profile-select"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Audit Profile
            </label>
            {profilesLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Loading profiles…
              </div>
            ) : profilesError ? (
              <p className="text-sm text-destructive py-2">
                Failed to load profiles. The default profile will be used.
              </p>
            ) : (
              <>
                <select
                  id="audit-profile-select"
                  value={selectedProfileId}
                  onChange={(e) => setSelectedProfileId(e.target.value)}
                  disabled={isSubmitting}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <option value="">
                    {defaultProfile
                      ? `Use default (${defaultProfile.name})`
                      : "Use company default"}
                  </option>
                  {profiles
                    .filter((p) => p.is_active)
                    .map((profile) => (
                      <option key={profile.id} value={String(profile.id)}>
                        {profile.name}
                        {profile.is_default ? " (default)" : ""}
                      </option>
                    ))}
                </select>
                <p className="mt-1 text-xs text-muted-foreground">
                  {defaultProfile
                    ? `Default: ${defaultProfile.name} (${defaultProfile.quorum} agent quorum)`
                    : "Select a profile or leave blank to use the company default."}
                </p>
              </>
            )}
          </div>

          {/* Change Reason */}
          <div className="mb-6">
            <label
              htmlFor="review-change-reason"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Change Reason <span aria-hidden="true">*</span>
            </label>
            <input
              id="review-change-reason"
              type="text"
              value={changeReason}
              onChange={(e) => setChangeReason(e.target.value)}
              disabled={isSubmitting}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Reason for submitting this document for review"
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
              className="flex-1 gap-1"
              disabled={isSubmitDisabled}
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Send className="h-4 w-4" aria-hidden="true" />
              )}
              {isSubmitting ? "Submitting…" : "Submit for Review"}
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
    document.body,
  );
}
