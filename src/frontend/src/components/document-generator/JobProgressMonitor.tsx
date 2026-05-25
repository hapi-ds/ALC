/**
 * JobProgressMonitor
 *
 * Displays active generation job progress including a progress bar,
 * current section name, sections completed/total, estimated time remaining,
 * status badge, and error messages. Auto-updates via store polling.
 *
 * Requirements: 7.1, 7.2, 7.3
 */

import { useEffect } from "react";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";
import type { GenerationJob, GenerationJobStatus } from "@/types/documentGenerator";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimeRemaining(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return "—";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
}

function getStatusConfig(status: GenerationJobStatus): {
  label: string;
  className: string;
} {
  switch (status) {
    case "pending":
      return { label: "Pending", className: "bg-yellow-100 text-yellow-800" };
    case "processing":
      return { label: "Processing", className: "bg-blue-100 text-blue-800" };
    case "completed":
      return { label: "Completed", className: "bg-green-100 text-green-800" };
    case "failed":
      return { label: "Failed", className: "bg-red-100 text-red-800" };
    default:
      return { label: String(status), className: "bg-gray-100 text-gray-800" };
  }
}

// ---------------------------------------------------------------------------
// JobCard
// ---------------------------------------------------------------------------

function JobCard({ job }: { job: GenerationJob }) {
  const statusConfig = getStatusConfig(job.status);
  const progressPercent = Math.min(Math.max(job.progress_percent, 0), 100);

  return (
    <div
      className="rounded-lg border p-4 space-y-3"
      aria-label={`Generation job ${job.job_id}`}
    >
      {/* Header: Job ID + Status Badge */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium truncate max-w-[60%]" title={job.job_id}>
          Job: {job.job_id.slice(0, 8)}…
        </span>
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusConfig.className}`}
          aria-label={`Status: ${statusConfig.label}`}
        >
          {statusConfig.label}
        </span>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Progress</span>
          <span>{progressPercent}%</span>
        </div>
        <div
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Generation progress: ${progressPercent}%`}
          className="h-2 w-full rounded-full bg-secondary overflow-hidden"
        >
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              job.status === "failed"
                ? "bg-destructive"
                : job.status === "completed"
                  ? "bg-green-500"
                  : "bg-primary"
            }`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Current Section */}
      {job.current_section && (
        <div className="text-xs">
          <span className="text-muted-foreground">Current section: </span>
          <span className="font-medium">{job.current_section}</span>
        </div>
      )}

      {/* Sections Completed / Total */}
      {job.sections_total > 0 && (
        <div className="text-xs">
          <span className="text-muted-foreground">Sections: </span>
          <span className="font-medium">
            {job.sections_completed} / {job.sections_total}
          </span>
        </div>
      )}

      {/* Estimated Time Remaining */}
      {(job.status === "pending" || job.status === "processing") && (
        <div className="text-xs">
          <span className="text-muted-foreground">Est. remaining: </span>
          <span className="font-medium">
            {formatTimeRemaining(job.estimated_time_remaining_seconds)}
          </span>
        </div>
      )}

      {/* Completion info */}
      {job.status === "completed" && job.result_document_id && (
        <div className="rounded-md bg-green-50 border border-green-200 p-2 text-xs text-green-800">
          Document generated successfully (ID: {job.result_document_id})
        </div>
      )}

      {/* Error Display */}
      {job.status === "failed" && job.error_message && (
        <div
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 p-2"
        >
          <p className="text-xs text-destructive font-medium">Error</p>
          <p className="text-xs text-destructive mt-0.5">{job.error_message}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// JobProgressMonitor
// ---------------------------------------------------------------------------

export function JobProgressMonitor() {
  const { activeJobs, startPolling, stopPolling } = useDocumentGeneratorStore();

  // Start/stop polling based on active jobs
  useEffect(() => {
    const pendingJobs = activeJobs.filter(
      (job) => job.status === "pending" || job.status === "processing",
    );

    if (pendingJobs.length > 0) {
      startPolling();
    }

    return () => {
      stopPolling();
    };
  }, [activeJobs, startPolling, stopPolling]);

  if (activeJobs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center">
        <p className="text-sm text-muted-foreground">
          No active generation jobs. Start a generation above to monitor progress.
        </p>
      </div>
    );
  }

  return (
    <section aria-label="Generation job progress" className="space-y-3">
      <h4 className="text-sm font-semibold">Active Jobs</h4>
      <div className="space-y-3">
        {activeJobs.map((job) => (
          <JobCard key={job.job_id} job={job} />
        ))}
      </div>
    </section>
  );
}
