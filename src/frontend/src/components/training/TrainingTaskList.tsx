import { AlertCircle, Inbox } from "lucide-react";
import type { TrainingTask, TaskFilter } from "./types";
import { filterTasks, sortTasks } from "./utils";
import { TrainingTaskCard } from "./TrainingTaskCard";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TrainingTaskListProps {
  tasks: TrainingTask[];
  filter: TaskFilter;
  isLoading: boolean;
  error: string | null;
  selectedTaskId?: number | null;
  onFilterChange: (filter: TaskFilter) => void;
  onTaskSelect?: (task: TrainingTask) => void;
  onMarkComplete: (task: TrainingTask) => void;
  onRetry: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FILTER_OPTIONS: { value: TaskFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "completed", label: "Completed" },
];

const EMPTY_STATE_MESSAGES: Record<TaskFilter, string> = {
  all: "No training tasks assigned",
  pending: "No pending tasks — all caught up!",
  completed: "No completed tasks yet",
};

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading training tasks">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="animate-pulse rounded-lg border p-4"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1 space-y-2">
              <div className="h-4 w-3/4 rounded bg-muted" />
              <div className="h-3 w-1/2 rounded bg-muted" />
              <div className="h-3 w-1/3 rounded bg-muted" />
            </div>
            <div className="h-7 w-24 rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error Panel
// ---------------------------------------------------------------------------

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4"
    >
      <AlertCircle className="h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
      <p className="flex-1 text-sm text-destructive">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        aria-label="Retry loading"
        className="shrink-0 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors"
      >
        Retry
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------

function EmptyState({ filter }: { filter: TaskFilter }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Inbox className="h-10 w-10 text-muted-foreground/50" aria-hidden="true" />
      <p className="mt-3 text-sm text-muted-foreground">
        {EMPTY_STATE_MESSAGES[filter]}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TrainingTaskList
// ---------------------------------------------------------------------------

export function TrainingTaskList({
  tasks,
  filter,
  isLoading,
  error,
  selectedTaskId,
  onFilterChange,
  onTaskSelect,
  onMarkComplete,
  onRetry,
}: TrainingTaskListProps) {
  // Apply client-side filtering and sorting
  const filteredTasks = filterTasks(tasks, filter);
  const sortedTasks = sortTasks(filteredTasks);

  return (
    <div className="space-y-4">
      {/* Filter Controls */}
      <div
        role="radiogroup"
        aria-label="Filter training tasks"
        className="flex gap-1 rounded-lg bg-muted p-1"
      >
        {FILTER_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={filter === option.value}
            onClick={() => onFilterChange(option.value)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === option.value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Content Area */}
      {isLoading ? (
        <LoadingSkeleton />
      ) : error ? (
        <ErrorPanel message={error} onRetry={onRetry} />
      ) : sortedTasks.length === 0 ? (
        <EmptyState filter={filter} />
      ) : (
        <div className="space-y-2" aria-label="Training tasks">
          {sortedTasks.map((task) => (
            <TrainingTaskCard
              key={task.id}
              task={task}
              isSelected={selectedTaskId === task.id}
              onSelect={onTaskSelect}
              onMarkComplete={onMarkComplete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
