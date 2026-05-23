import { useEffect } from "react";
import { CheckCircle, Clock, Loader2, AlertCircle, RotateCcw } from "lucide-react";
import type { TrainingTask } from "./types";
import { truncateTitle, formatAriaLabel, deriveContentId } from "./utils";
import { useTrainingStore } from "@/stores/trainingStore";
import { useAuthStore } from "@/stores/authStore";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TrainingTaskCardProps {
  task: TrainingTask;
  isSelected?: boolean;
  onSelect?: (task: TrainingTask) => void;
  onMarkComplete: (task: TrainingTask) => void;
}

// ---------------------------------------------------------------------------
// TrainingTaskCard
// ---------------------------------------------------------------------------

export function TrainingTaskCard({ task, isSelected, onSelect, onMarkComplete }: TrainingTaskCardProps) {
  const ariaLabel = formatAriaLabel(task);
  const displayTitle = truncateTitle(task.task_title);
  const formattedCompletedAt = task.completed_at
    ? new Date(task.completed_at).toLocaleString()
    : null;

  // Quiz pass guard state
  const user = useAuthStore((state) => state.user);
  const { quizPassCache, isCheckingQuizPass, quizPassError, checkQuizPassed } =
    useTrainingStore();

  const contentId = deriveContentId(task.sop_document_uuid, task.sop_version);
  const quizPassStatus = quizPassCache[contentId];
  const hasPassedQuiz = quizPassStatus?.has_passed ?? false;

  // Check quiz pass status on mount for pending tasks
  useEffect(() => {
    if (!task.is_completed && user?.id) {
      checkQuizPassed(contentId, user.id);
    }
  }, [task.is_completed, contentId, user?.id, checkQuizPassed]);

  const handleRetryQuizCheck = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (user?.id) {
      // Clear the cached error state and re-check
      checkQuizPassed(contentId, user.id);
    }
  };

  // Determine the Mark Complete button state
  const renderMarkCompleteButton = () => {
    // Loading state: quiz pass check is in-flight
    if (isCheckingQuizPass && quizPassStatus === undefined) {
      return (
        <span className="inline-flex items-center gap-1 rounded-md bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          Checking…
        </span>
      );
    }

    // Error state: quiz pass check failed
    if (quizPassError && quizPassStatus === undefined) {
      return (
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-md bg-destructive/10 px-2.5 py-1.5 text-xs font-medium text-destructive">
            <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
            Error
          </span>
          <button
            type="button"
            onClick={handleRetryQuizCheck}
            aria-label="Retry quiz pass check"
            className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/80 transition-colors"
          >
            <RotateCcw className="h-3 w-3" aria-hidden="true" />
            Retry
          </button>
        </span>
      );
    }

    // Quiz not passed: disabled button with tooltip
    if (!hasPassedQuiz) {
      return (
        <button
          type="button"
          disabled
          title="Pass the quiz to enable task completion"
          aria-label="Mark Complete (disabled: pass the quiz first)"
          className="inline-flex items-center gap-1 rounded-md bg-primary/50 px-3 py-1.5 text-xs font-medium text-primary-foreground/70 cursor-not-allowed"
        >
          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
          Mark Complete
        </button>
      );
    }

    // Quiz passed: enabled button
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onMarkComplete(task);
        }}
        className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
        Mark Complete
      </button>
    );
  };

  return (
    <article
      role="article"
      aria-label={ariaLabel}
      className={`rounded-lg border p-4 transition-colors hover:bg-muted/50 cursor-pointer ${
        isSelected ? "ring-2 ring-primary border-primary" : ""
      }`}
      onClick={() => onSelect?.(task)}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium leading-tight" title={task.task_title}>
            {displayTitle}
          </h3>
          <div className="mt-1 space-y-0.5">
            <p className="text-xs text-muted-foreground">
              SOP: {task.sop_document_uuid}
            </p>
            <p className="text-xs text-muted-foreground">
              Version: {task.sop_version}
            </p>
            {task.is_completed && formattedCompletedAt && (
              <p className="text-xs text-muted-foreground">
                Completed: {formattedCompletedAt}
              </p>
            )}
          </div>
        </div>

        <div className="shrink-0">
          {task.is_completed ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700">
              <CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />
              Completed
            </span>
          ) : (
            renderMarkCompleteButton()
          )}
        </div>
      </div>
    </article>
  );
}
