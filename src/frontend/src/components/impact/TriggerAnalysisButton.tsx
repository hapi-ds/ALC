/**
 * TriggerAnalysisButton
 *
 * Button that triggers a manual impact analysis via POST /api/impact-analysis/trigger.
 * On 202: polls job status every 5s, shows progress indicator (current_phase, progress_percent).
 * On 409: displays "analysis in progress" message, polls existing job_id.
 * Auto-refreshes results on completion/partial_success.
 *
 * Requirements: 10.6, 10.10
 */

import { useState, useCallback } from "react";
import { Play, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useImpactAnalysisStore } from "@/stores/impactAnalysisStore";
import type { JobStatus } from "@/types/impactAnalysis";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getPhaseLabel(phase: string): string {
  switch (phase) {
    case "computing_delta":
      return "Computing changes…";
    case "querying_dependencies":
      return "Querying dependencies…";
    case "assessing_impact":
      return "Assessing impact…";
    case "analyzing_gaps":
      return "Analyzing gaps…";
    case "persisting_report":
      return "Saving report…";
    default:
      return "Processing…";
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface TriggerAnalysisButtonProps {
  documentId: number;
  onComplete?: () => void;
}

export function TriggerAnalysisButton({
  documentId,
  onComplete,
}: TriggerAnalysisButtonProps) {
  const { triggerAnalysis, activeJob, fetchReports } = useImpactAnalysisStore();
  const [isTriggering, setIsTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleTrigger = useCallback(async () => {
    setIsTriggering(true);
    setError(null);

    try {
      await triggerAnalysis(documentId, "Manual impact analysis trigger");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to trigger analysis",
      );
    } finally {
      setIsTriggering(false);
    }
  }, [documentId, triggerAnalysis]);

  // Determine if a job is actively running for display
  const isJobActive =
    activeJob !== null &&
    activeJob.status === "processing";

  const isJobTerminal =
    activeJob !== null &&
    (activeJob.status === "completed" ||
      activeJob.status === "partial_success" ||
      activeJob.status === "failed");

  // Auto-refresh on completion
  if (isJobTerminal && activeJob) {
    if (
      activeJob.status === "completed" ||
      activeJob.status === "partial_success"
    ) {
      // Trigger refresh of reports
      fetchReports();
      if (onComplete) onComplete();
    }
  }

  return (
    <div className="space-y-2">
      {/* Trigger button */}
      <Button
        onClick={handleTrigger}
        disabled={isTriggering || isJobActive}
        aria-label="Trigger impact analysis"
      >
        {isTriggering || isJobActive ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Play className="h-4 w-4" aria-hidden="true" />
        )}
        {isJobActive ? "Analysis Running…" : "Run Impact Analysis"}
      </Button>

      {/* Progress indicator */}
      {isJobActive && activeJob && (
        <ProgressIndicator job={activeJob} />
      )}

      {/* Terminal status */}
      {isJobTerminal && activeJob && (
        <TerminalStatus job={activeJob} />
      )}

      {/* Error message */}
      {error && (
        <div className="flex items-center gap-1.5 text-xs text-destructive">
          <AlertCircle className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProgressIndicator({ job }: { job: JobStatus }) {
  return (
    <div
      className="border border-border rounded-md p-3 bg-muted/20"
      role="status"
      aria-label="Analysis progress"
    >
      <div className="flex items-center justify-between text-xs mb-1.5">
        <span className="text-muted-foreground">
          {getPhaseLabel(job.current_phase)}
        </span>
        <span className="font-mono font-medium">{job.progress_percent}%</span>
      </div>
      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-all duration-300"
          style={{ width: `${job.progress_percent}%` }}
        />
      </div>
      {job.items_total > 0 && (
        <p className="text-xs text-muted-foreground mt-1">
          {job.items_assessed} / {job.items_total} items assessed
        </p>
      )}
    </div>
  );
}

function TerminalStatus({ job }: { job: JobStatus }) {
  if (job.status === "completed") {
    return (
      <div className="flex items-center gap-1.5 text-xs text-green-600">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        <span>Analysis completed successfully</span>
      </div>
    );
  }

  if (job.status === "partial_success") {
    return (
      <div className="flex items-center gap-1.5 text-xs text-yellow-600">
        <AlertCircle className="h-3 w-3" aria-hidden="true" />
        <span>Analysis completed with partial results</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 text-xs text-destructive">
      <AlertCircle className="h-3 w-3" aria-hidden="true" />
      <span>{job.error_message || "Analysis failed"}</span>
    </div>
  );
}
