/**
 * JobMonitor
 *
 * Displays the status of pending AI generation jobs with 15-second polling.
 * Shows job status indicators and auto-removes completed/failed jobs.
 *
 * Requirements: 10.7, 10.8
 */

import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Job } from "@/types/training-ecosystem";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface JobMonitorProps {
  jobs: Job[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getJobStatusIcon(status: string) {
  switch (status) {
    case "completed":
      return <CheckCircle className="h-4 w-4 text-green-600" aria-hidden="true" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-destructive" aria-hidden="true" />;
    default:
      return <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />;
  }
}

function getJobStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Queued";
    case "in_progress":
      return "Processing";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return status;
  }
}

function getJobStatusColor(status: string): string {
  switch (status) {
    case "completed":
      return "text-green-700";
    case "failed":
      return "text-destructive";
    case "in_progress":
      return "text-primary";
    default:
      return "text-muted-foreground";
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function JobMonitor({ jobs }: JobMonitorProps) {
  if (jobs.length === 0) return null;

  return (
    <div
      className="rounded-lg border bg-card p-4"
      aria-label="Active generation jobs"
      role="status"
      aria-live="polite"
    >
      <h4 className="text-sm font-medium mb-3">Generation Jobs</h4>
      <ul className="space-y-2">
        {jobs.map((job) => (
          <li
            key={job.job_id}
            className="flex items-center gap-3 text-sm"
          >
            {getJobStatusIcon(job.status)}
            <span className="font-mono text-xs text-muted-foreground truncate max-w-[200px]">
              {job.job_id}
            </span>
            <span
              className={cn(
                "text-xs font-medium capitalize",
                getJobStatusColor(job.status)
              )}
            >
              {getJobStatusLabel(job.status)}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        Status updates every 15 seconds
      </p>
    </div>
  );
}
