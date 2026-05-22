import { CheckCircle, Clock } from "lucide-react";
import type { TrainingTask } from "./types";
import { truncateTitle, formatAriaLabel } from "./utils";

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
          )}
        </div>
      </div>
    </article>
  );
}
