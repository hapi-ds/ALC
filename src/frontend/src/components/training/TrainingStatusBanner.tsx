import { useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle, AlertCircle } from "lucide-react";
import { useTrainingStore } from "@/stores/trainingStore";
import { useAuthStore } from "@/stores/authStore";
import { shouldEnforceGate, checkGateFromTasks } from "./utils";

interface TrainingStatusBannerProps {
  sopDocumentUuid: string;
  sopVersion: string;
  sopStatus: string;
  sopName?: string;
}

/**
 * TrainingStatusBanner - Displays training status inline on the document detail page.
 *
 * - Amber/warning banner when training is pending
 * - Green/success banner when training is complete
 * - Only displays when SOP status is "InTraining"
 *
 * Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
 */
export function TrainingStatusBanner({
  sopDocumentUuid,
  sopVersion,
  sopStatus,
  sopName,
}: TrainingStatusBannerProps) {
  const { tasks, isLoadingTasks, tasksError, hasFetchedTasks, fetchTrainingTasks } =
    useTrainingStore();
  const user = useAuthStore((state) => state.user);

  const userId = user?.id ?? null;
  const displayName = sopName || sopDocumentUuid;

  // Fetch tasks if not yet loaded and gate should be enforced
  useEffect(() => {
    if (!shouldEnforceGate(sopStatus)) return;
    if (hasFetchedTasks || userId === null) return;

    fetchTrainingTasks(userId);
  }, [sopStatus, hasFetchedTasks, userId, fetchTrainingTasks]);

  const handleRetry = useCallback(() => {
    if (userId === null) return;
    fetchTrainingTasks(userId);
  }, [userId, fetchTrainingTasks]);

  // Don't render if SOP is not in "InTraining" status
  if (!shouldEnforceGate(sopStatus)) {
    return null;
  }

  // Loading state - skeleton placeholder
  if (isLoadingTasks || !hasFetchedTasks) {
    return (
      <div
        className="border border-border rounded-md p-4 animate-pulse"
        aria-label="Loading training status"
      >
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 bg-muted rounded" />
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-muted rounded w-3/4" />
            <div className="h-3 bg-muted rounded w-1/4" />
          </div>
        </div>
      </div>
    );
  }

  // Error state with retry
  if (tasksError) {
    return (
      <div
        role="alert"
        className="flex items-center gap-3 border border-destructive/50 bg-destructive/10 rounded-md p-4"
      >
        <AlertCircle className="h-5 w-5 text-destructive shrink-0" aria-hidden="true" />
        <p className="text-sm text-destructive flex-1">Unable to load training status</p>
        <button
          onClick={handleRetry}
          className="text-sm font-medium text-destructive hover:underline focus:outline-none focus:ring-2 focus:ring-destructive focus:ring-offset-2 rounded px-2 py-1"
          aria-label="Retry loading training status"
        >
          Retry
        </button>
      </div>
    );
  }

  // Determine training completion status from local tasks
  const isComplete = checkGateFromTasks(tasks, sopDocumentUuid, sopVersion);

  // Find the completion date if training is complete
  const completedTask = isComplete
    ? tasks.find(
        (t) =>
          t.sop_document_uuid === sopDocumentUuid &&
          t.sop_version === sopVersion &&
          t.is_completed
      )
    : null;

  const completionDate = completedTask?.completed_at
    ? new Date(completedTask.completed_at).toLocaleDateString()
    : null;

  // Training complete - green/success banner
  if (isComplete) {
    return (
      <div className="flex items-center gap-3 border border-green-200 bg-green-50 rounded-md p-4">
        <CheckCircle className="h-5 w-5 text-green-600 shrink-0" aria-hidden="true" />
        <div className="flex-1">
          <p className="text-sm text-green-800">
            Training complete: You have completed training for {displayName} v{sopVersion}.
            {completionDate && (
              <span className="ml-1 text-green-600">Completed on {completionDate}.</span>
            )}
          </p>
        </div>
        <Link
          to="/training"
          className="text-sm font-medium text-green-700 hover:text-green-900 hover:underline focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 rounded px-2 py-1"
        >
          View Training
        </Link>
      </div>
    );
  }

  // Training pending - amber/warning banner
  return (
    <div className="flex items-center gap-3 border border-amber-200 bg-amber-50 rounded-md p-4">
      <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" aria-hidden="true" />
      <div className="flex-1">
        <p className="text-sm text-amber-800">
          Training required: You have not completed training for {displayName} v{sopVersion}.
          Complete training to gain full access.
        </p>
      </div>
      <Link
        to="/training"
        className="text-sm font-medium text-amber-700 hover:text-amber-900 hover:underline focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2 rounded px-2 py-1"
      >
        View Training
      </Link>
    </div>
  );
}
