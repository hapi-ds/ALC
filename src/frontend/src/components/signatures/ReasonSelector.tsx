/**
 * ReasonSelector Component
 *
 * Provides the reason category dropdown and signature note input for
 * 21 CFR Part 11 compliance. The user must select a reason category
 * (Author, Review, or Approval) and provide a descriptive note (3–200
 * characters) explaining the specific reason for signing.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4
 */

import { useState } from "react";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ReasonSelectorProps {
  reasonCategory: string;
  signatureNote: string;
  onReasonCategoryChange: (category: string) => void;
  onSignatureNoteChange: (note: string) => void;
  disabled: boolean;
}

// ---------------------------------------------------------------------------
// ReasonSelector
// ---------------------------------------------------------------------------

export function ReasonSelector({
  reasonCategory,
  signatureNote,
  onReasonCategoryChange,
  onSignatureNoteChange,
  disabled,
}: ReasonSelectorProps) {
  const [noteTouched, setNoteTouched] = useState(false);

  // Validation: trimmed length must be at least 3 characters
  const trimmedLength = signatureNote.trim().length;
  const showNoteError = noteTouched && trimmedLength < 3;

  // Character counter: raw (untrimmed) character count
  const rawLength = signatureNote.length;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleNoteBlur() {
    setNoteTouched(true);
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Reason Category Dropdown */}
      <div className="space-y-2">
        <label
          htmlFor="reason-category"
          className="text-sm font-medium"
        >
          Reason for Signature
        </label>
        <select
          id="reason-category"
          value={reasonCategory}
          onChange={(e) => onReasonCategoryChange(e.target.value)}
          disabled={disabled}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          aria-required="true"
        >
          <option value="" disabled>
            Select a reason...
          </option>
          <option value="Author">Author</option>
          <option value="Review">Review</option>
          <option value="Approval">Approval</option>
        </select>
      </div>

      {/* Signature Note Input */}
      <div className="space-y-2">
        <label
          htmlFor="signature-note"
          className="text-sm font-medium"
        >
          Signature Note
        </label>
        <input
          id="signature-note"
          type="text"
          value={signatureNote}
          onChange={(e) => onSignatureNoteChange(e.target.value)}
          onBlur={handleNoteBlur}
          disabled={disabled}
          maxLength={200}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          placeholder="e.g., Approved by QA Manager after final review"
          aria-required="true"
          aria-describedby={showNoteError ? "signature-note-error" : undefined}
        />

        {/* Character counter and validation */}
        <div className="flex items-center justify-between">
          {showNoteError ? (
            <p
              id="signature-note-error"
              className="text-sm text-destructive"
              role="alert"
            >
              Signature note must contain at least 3 characters
            </p>
          ) : (
            <span />
          )}
          <span className="text-xs text-muted-foreground">
            {rawLength}/200
          </span>
        </div>
      </div>
    </div>
  );
}
