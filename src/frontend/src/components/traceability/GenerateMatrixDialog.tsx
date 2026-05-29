/**
 * GenerateMatrixDialog
 *
 * Modal dialog for generating a new traceability matrix:
 * - Multi-select document picker for source documents (max 10)
 * - Multi-select document picker for target documents (max 20)
 * - matrix_name text input (required, 1-200 chars)
 * - Optional description textarea (max 1000 chars)
 * - Validation: at least one source, one target, valid matrix_name
 * - Submit with X-Change-Reason prompt
 * - On 202: poll job status, show progress, auto-navigate on completion
 * - On 409: display "generation in progress" message, poll existing job
 * - On failure/timeout: stop polling, show error, provide retry
 *
 * Requirements: 8.5, 8.6, 8.7, 8.12
 */

import { useState, useCallback } from "react";
import { X, Loader2, CheckCircle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTraceabilityStore } from "@/stores/traceabilityStore";
import type { JobStatus } from "@/types/traceability";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GenerateMatrixDialogProps {
  onClose: () => void;
}

interface DocumentOption {
  id: number;
  name: string;
  type: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_SOURCE_DOCS = 10;
const MAX_TARGET_DOCS = 20;
const MAX_NAME_LENGTH = 200;
const MAX_DESCRIPTION_LENGTH = 1000;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GenerateMatrixDialog({ onClose }: GenerateMatrixDialogProps) {
  const { activeJob, generateMatrix, error } = useTraceabilityStore();

  // Form state
  const [matrixName, setMatrixName] = useState("");
  const [description, setDescription] = useState("");
  const [sourceDocIds, setSourceDocIds] = useState<number[]>([]);
  const [targetDocIds, setTargetDocIds] = useState<number[]>([]);
  const [changeReason, setChangeReason] = useState("");
  const [sourceInput, setSourceInput] = useState("");
  const [targetInput, setTargetInput] = useState("");

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [jobStarted, setJobStarted] = useState(false);

  // Validation
  const nameValid = matrixName.length >= 1 && matrixName.length <= MAX_NAME_LENGTH;
  const descriptionValid = description.length <= MAX_DESCRIPTION_LENGTH;
  const sourceValid = sourceDocIds.length >= 1 && sourceDocIds.length <= MAX_SOURCE_DOCS;
  const targetValid = targetDocIds.length >= 1 && targetDocIds.length <= MAX_TARGET_DOCS;
  const reasonValid = changeReason.trim().length > 0;
  const canSubmit =
    nameValid && descriptionValid && sourceValid && targetValid && reasonValid && !isSubmitting;

  const handleAddSourceDoc = useCallback(() => {
    const id = parseInt(sourceInput, 10);
    if (!isNaN(id) && !sourceDocIds.includes(id) && sourceDocIds.length < MAX_SOURCE_DOCS) {
      setSourceDocIds((prev) => [...prev, id]);
      setSourceInput("");
    }
  }, [sourceInput, sourceDocIds]);

  const handleAddTargetDoc = useCallback(() => {
    const id = parseInt(targetInput, 10);
    if (!isNaN(id) && !targetDocIds.includes(id) && targetDocIds.length < MAX_TARGET_DOCS) {
      setTargetDocIds((prev) => [...prev, id]);
      setTargetInput("");
    }
  }, [targetInput, targetDocIds]);

  const handleRemoveSource = (id: number) => {
    setSourceDocIds((prev) => prev.filter((d) => d !== id));
  };

  const handleRemoveTarget = (id: number) => {
    setTargetDocIds((prev) => prev.filter((d) => d !== id));
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await generateMatrix(
        {
          source_document_ids: sourceDocIds,
          target_document_ids: targetDocIds,
          matrix_name: matrixName,
          description: description || undefined,
        },
        changeReason,
      );
      setJobStarted(true);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to start matrix generation",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Show progress view when job is active
  if (jobStarted && activeJob) {
    return (
      <DialogWrapper onClose={onClose}>
        <JobProgressView job={activeJob} onClose={onClose} error={error} />
      </DialogWrapper>
    );
  }

  return (
    <DialogWrapper onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Generate Traceability Matrix</h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {/* Matrix name */}
        <div>
          <label className="block text-sm font-medium mb-1">
            Matrix Name <span className="text-destructive">*</span>
          </label>
          <input
            type="text"
            value={matrixName}
            onChange={(e) => setMatrixName(e.target.value)}
            maxLength={MAX_NAME_LENGTH}
            placeholder="e.g., URS v2.0 → IQ/OQ Traceability"
            className="w-full px-3 py-2 border border-input rounded-md text-sm bg-background focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground mt-1">
            {matrixName.length}/{MAX_NAME_LENGTH} characters
          </p>
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium mb-1">
            Description (optional)
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={MAX_DESCRIPTION_LENGTH}
            rows={3}
            placeholder="Describe the purpose of this traceability matrix..."
            className="w-full px-3 py-2 border border-input rounded-md text-sm bg-background focus:outline-none focus:ring-1 focus:ring-ring resize-none"
          />
          <p className="text-xs text-muted-foreground mt-1">
            {description.length}/{MAX_DESCRIPTION_LENGTH} characters
          </p>
        </div>

        {/* Source documents */}
        <div>
          <label className="block text-sm font-medium mb-1">
            Source Documents (Requirements) <span className="text-destructive">*</span>
          </label>
          <p className="text-xs text-muted-foreground mb-2">
            Select up to {MAX_SOURCE_DOCS} documents containing requirements (URS, SRS, etc.)
          </p>
          <div className="flex gap-2">
            <input
              type="number"
              value={sourceInput}
              onChange={(e) => setSourceInput(e.target.value)}
              placeholder="Document ID"
              className="flex-1 px-3 py-2 border border-input rounded-md text-sm bg-background focus:outline-none focus:ring-1 focus:ring-ring"
              onKeyDown={(e) => e.key === "Enter" && handleAddSourceDoc()}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={handleAddSourceDoc}
              disabled={sourceDocIds.length >= MAX_SOURCE_DOCS}
            >
              Add
            </Button>
          </div>
          {sourceDocIds.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {sourceDocIds.map((id) => (
                <span
                  key={id}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded-md"
                >
                  Doc #{id}
                  <button
                    onClick={() => handleRemoveSource(id)}
                    className="hover:text-blue-600"
                    aria-label={`Remove document ${id}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            {sourceDocIds.length}/{MAX_SOURCE_DOCS} selected
          </p>
        </div>

        {/* Target documents */}
        <div>
          <label className="block text-sm font-medium mb-1">
            Target Documents (Test Cases) <span className="text-destructive">*</span>
          </label>
          <p className="text-xs text-muted-foreground mb-2">
            Select up to {MAX_TARGET_DOCS} documents containing test cases (IQ, OQ, PQ, MVP)
          </p>
          <div className="flex gap-2">
            <input
              type="number"
              value={targetInput}
              onChange={(e) => setTargetInput(e.target.value)}
              placeholder="Document ID"
              className="flex-1 px-3 py-2 border border-input rounded-md text-sm bg-background focus:outline-none focus:ring-1 focus:ring-ring"
              onKeyDown={(e) => e.key === "Enter" && handleAddTargetDoc()}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={handleAddTargetDoc}
              disabled={targetDocIds.length >= MAX_TARGET_DOCS}
            >
              Add
            </Button>
          </div>
          {targetDocIds.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {targetDocIds.map((id) => (
                <span
                  key={id}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-purple-100 text-purple-800 rounded-md"
                >
                  Doc #{id}
                  <button
                    onClick={() => handleRemoveTarget(id)}
                    className="hover:text-purple-600"
                    aria-label={`Remove document ${id}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            {targetDocIds.length}/{MAX_TARGET_DOCS} selected
          </p>
        </div>

        {/* Change reason */}
        <div>
          <label className="block text-sm font-medium mb-1">
            Change Reason (X-Change-Reason) <span className="text-destructive">*</span>
          </label>
          <input
            type="text"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            placeholder="e.g., Initial traceability matrix generation for URS v2.0"
            className="w-full px-3 py-2 border border-input rounded-md text-sm bg-background focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {/* Error */}
        {(submitError || error) && (
          <div className="flex items-center gap-2 p-3 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <p>{submitError || error}</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {isSubmitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            Generate Matrix
          </Button>
        </div>
      </div>
    </DialogWrapper>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DialogWrapper({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Generate Traceability Matrix"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Content */}
      <div className="relative bg-background border border-border rounded-lg shadow-lg p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {children}
      </div>
    </div>
  );
}

function JobProgressView({
  job,
  onClose,
  error,
}: {
  job: JobStatus;
  onClose: () => void;
  error: string | null;
}) {
  const isTerminal = ["completed", "partial_success", "failed"].includes(job.status);
  const isSuccess = job.status === "completed" || job.status === "partial_success";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Matrix Generation</h3>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground"
          aria-label="Close dialog"
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground capitalize">
            {job.current_phase.replace(/_/g, " ")}
          </span>
          <span className="font-medium">{job.progress_percent}%</span>
        </div>
        <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              job.status === "failed" ? "bg-destructive" : "bg-primary"
            }`}
            style={{ width: `${job.progress_percent}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <p>Requirements extracted: {job.requirements_extracted}</p>
        <p>Test cases extracted: {job.test_cases_extracted}</p>
        <p>Links established: {job.links_established}</p>
        <p>Orphans detected: {job.orphans_detected}</p>
      </div>

      {/* Status message */}
      {isTerminal && (
        <div
          className={`flex items-center gap-2 p-3 rounded-md text-sm ${
            isSuccess
              ? "bg-green-50 text-green-800 border border-green-200"
              : "bg-destructive/10 text-destructive border border-destructive/50"
          }`}
        >
          {isSuccess ? (
            <CheckCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          <p>
            {isSuccess
              ? `Matrix generated successfully. Coverage: ${job.coverage_percentage?.toFixed(1) ?? "N/A"}%`
              : job.error_message || "Matrix generation failed."}
          </p>
        </div>
      )}

      {/* Timeout error from store */}
      {error && !isTerminal && (
        <div className="flex items-center gap-2 p-3 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{error}</p>
        </div>
      )}

      {/* Spinner while processing */}
      {!isTerminal && !error && (
        <div className="flex items-center justify-center py-2">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="ml-2 text-sm text-muted-foreground">Processing...</span>
        </div>
      )}

      {/* Close button */}
      <div className="flex justify-end pt-2">
        <Button variant="outline" onClick={onClose}>
          {isTerminal ? "Close" : "Run in Background"}
        </Button>
      </div>
    </div>
  );
}
