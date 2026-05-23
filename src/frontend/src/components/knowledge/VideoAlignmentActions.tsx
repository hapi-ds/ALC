import { useCallback, useEffect, useRef, useState } from "react";
import {
  Play,
  Eye,
  GitCompare,
  Loader2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { apiClient, ApiError } from "@/lib/apiClient";
import { useJobPolling } from "@/hooks/useJobPolling";
import type {
  DiscrepancyReport,
  JobStatusResponse,
} from "@/types/videoAlignment";

/**
 * Props for the VideoAlignmentActions component.
 */
export interface VideoAlignmentActionsProps {
  /** UUID of the Video_Document */
  documentUuid: string;
  /** Callback when alignment completes and a report is available */
  onReportReady: (report: DiscrepancyReport) => void;
}

/** The sequential actions available for video alignment */
type AlignmentAction = "extract-frames" | "analyze-frames" | "align";

interface ActionConfig {
  id: AlignmentAction;
  label: string;
  description: string;
  icon: typeof Play;
  changeReason: string;
}

const ACTIONS: ActionConfig[] = [
  {
    id: "extract-frames",
    label: "Extract Frames",
    description: "Extract key frames from the video at regular intervals",
    icon: Play,
    changeReason: "Extract frames for video alignment analysis",
  },
  {
    id: "analyze-frames",
    label: "Analyze Frames",
    description: "Analyze extracted frames using the vision model",
    icon: Eye,
    changeReason: "Analyze video frames for step extraction",
  },
  {
    id: "align",
    label: "Align with SOP",
    description: "Compare video steps against linked SOP procedures",
    icon: GitCompare,
    changeReason: "Run video-to-SOP alignment",
  },
];

/**
 * Format estimated time remaining into a human-readable string.
 */
function formatEstimatedTime(seconds: number): string {
  if (seconds <= 0) return "almost done";
  if (seconds < 60) return `~${seconds}s remaining`;
  const mins = Math.ceil(seconds / 60);
  return `~${mins}min remaining`;
}

/**
 * VideoAlignmentActions displays action buttons and job progress tracking
 * for the video alignment workflow.
 *
 * When no report exists:
 * - Shows action buttons in sequence (Extract Frames → Analyze Frames → Align)
 * - Each button triggers the corresponding API call
 *
 * While processing:
 * - Polls GET /api/knowledge/videos/jobs/{job_id} every 5 seconds
 * - Shows progress bar with percentage and estimated time remaining
 * - Auto-renders results on completion
 * - Shows error message on failure
 *
 * Error handling:
 * - Network errors: show error message with retry button
 * - 5xx errors: show error message with retry button
 * - Timeout (15s): show timeout message with retry button
 *
 * Validates: Requirements 11.6, 11.7, 11.8
 */
export function VideoAlignmentActions({
  documentUuid,
  onReportReady,
}: VideoAlignmentActionsProps) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<AlignmentAction | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);

  const {
    isPolling,
    jobStatus,
    error: pollingError,
    startPolling,
    stopPolling,
    retry: retryPolling,
  } = useJobPolling();

  // Track whether we've already handled the completion to avoid re-triggering
  const completionHandledRef = useRef(false);

  // When job completes, fetch the report
  const handleJobComplete = useCallback(async () => {
    try {
      const report = await apiClient.get<DiscrepancyReport>(
        `/api/knowledge/videos/${documentUuid}/report`
      );
      onReportReady(report);
    } catch (err: unknown) {
      let message = "Failed to load the alignment report.";
      if (err instanceof ApiError) {
        message = `Failed to load report (${err.status}).`;
      }
      setActionError(message);
    }
  }, [documentUuid, onReportReady]);

  // Detect job completion via useEffect to avoid infinite re-renders
  useEffect(() => {
    if (
      jobStatus?.status === "completed" &&
      !isPolling &&
      !completionHandledRef.current
    ) {
      completionHandledRef.current = true;
      setActiveAction(null);
      void handleJobComplete();
    }
  }, [jobStatus, isPolling, handleJobComplete]);

  const triggerAction = useCallback(
    async (action: AlignmentAction) => {
      setActionError(null);
      setActiveAction(action);
      setIsTriggering(true);
      completionHandledRef.current = false;

      const url = `/api/knowledge/videos/${documentUuid}/${action}`;

      try {
        const response = await apiClient.post<JobStatusResponse>(url, undefined, {
          changeReason: ACTIONS.find((a) => a.id === action)?.changeReason ?? "Video alignment operation",
        });

        setIsTriggering(false);
        startPolling(response.job_id);
      } catch (err: unknown) {
        setIsTriggering(false);

        let errorMessage: string;
        if (err instanceof ApiError) {
          if (err.status >= 500) {
            errorMessage = `Server error (${err.status}). Please try again later.`;
          } else if (err.status === 409) {
            errorMessage = "This operation is already in progress.";
          } else if (err.status === 422) {
            errorMessage = `Precondition not met: ${err.body}`;
          } else {
            errorMessage = `Request failed (${err.status}): ${err.body}`;
          }
        } else if (err instanceof TypeError) {
          errorMessage = "Network error. Please check your connection and try again.";
        } else {
          errorMessage = "An unexpected error occurred. Please try again.";
        }

        setActionError(errorMessage);
      }
    },
    [documentUuid, startPolling]
  );

  const handleRetry = useCallback(() => {
    if (pollingError) {
      retryPolling();
    } else if (actionError && activeAction) {
      setActionError(null);
      void triggerAction(activeAction);
    }
  }, [pollingError, retryPolling, actionError, activeAction, triggerAction]);

  const handleDismissError = useCallback(() => {
    setActionError(null);
    setActiveAction(null);
    stopPolling();
  }, [stopPolling]);

  // Determine the current error to display
  const displayError = pollingError || actionError;
  const jobFailed = jobStatus?.status === "failed";

  // ---------------------------------------------------------------------------
  // Render: Error state
  // ---------------------------------------------------------------------------

  if (displayError || jobFailed) {
    const errorMessage = jobFailed
      ? jobStatus?.error_message || "The operation failed. Please try again."
      : displayError;

    return (
      <div
        className="space-y-4"
        aria-label="Video alignment actions"
        role="region"
      >
        <div
          role="alert"
          className="flex items-start gap-3 p-4 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800"
        >
          <AlertCircle
            className="h-5 w-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5"
            aria-hidden="true"
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              {jobFailed ? "Operation Failed" : "Error"}
            </p>
            <p className="text-sm text-red-700 dark:text-red-400 mt-1">
              {errorMessage}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleRetry}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            aria-label="Retry operation"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Retry
          </button>
          <button
            type="button"
            onClick={handleDismissError}
            className="inline-flex items-center px-3 py-2 text-sm font-medium rounded-md border border-border hover:bg-muted transition-colors"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Polling / Progress state
  // ---------------------------------------------------------------------------

  if (isPolling || isTriggering) {
    const progressPercent = jobStatus?.progress_percent ?? 0;
    const actionLabel = ACTIONS.find((a) => a.id === activeAction)?.label ?? "Processing";

    // Estimate remaining time based on progress and elapsed time
    let estimatedRemaining = "";
    if (jobStatus?.started_at && progressPercent > 0 && progressPercent < 100) {
      const elapsed = (Date.now() - new Date(jobStatus.started_at).getTime()) / 1000;
      const totalEstimated = elapsed / (progressPercent / 100);
      const remaining = Math.max(0, Math.round(totalEstimated - elapsed));
      estimatedRemaining = formatEstimatedTime(remaining);
    } else if (isTriggering) {
      estimatedRemaining = "starting...";
    }

    return (
      <div
        className="space-y-4"
        aria-label="Video alignment progress"
        role="region"
      >
        <div className="flex items-center gap-3">
          <Loader2
            className="h-5 w-5 text-primary animate-spin"
            aria-hidden="true"
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">{actionLabel}</p>
            {estimatedRemaining && (
              <p className="text-xs text-muted-foreground">{estimatedRemaining}</p>
            )}
          </div>
          <span
            className="text-sm font-semibold text-primary"
            aria-label={`Progress: ${progressPercent}%`}
          >
            {progressPercent}%
          </span>
        </div>

        {/* Progress bar */}
        <div
          className="w-full h-2 bg-muted rounded-full overflow-hidden"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${actionLabel} progress`}
        >
          <div
            className="h-full bg-primary rounded-full transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Action buttons (no report exists)
  // ---------------------------------------------------------------------------

  return (
    <div
      className="space-y-4"
      aria-label="Video alignment actions"
      role="region"
    >
      <div className="p-4 rounded-md bg-muted/50 border border-border">
        <p className="text-sm text-muted-foreground mb-4">
          No alignment report exists for this video. Run the following steps in
          sequence to generate a discrepancy report:
        </p>
        <div className="flex flex-wrap gap-2">
          {ACTIONS.map((action, index) => {
            const Icon = action.icon;
            return (
              <button
                key={action.id}
                type="button"
                onClick={() => void triggerAction(action.id)}
                className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                title={action.description}
                aria-label={action.label}
              >
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary-foreground/20 text-xs font-bold">
                  {index + 1}
                </span>
                <Icon className="h-4 w-4" aria-hidden="true" />
                {action.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
