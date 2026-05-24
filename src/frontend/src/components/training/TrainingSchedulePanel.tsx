/**
 * TrainingSchedulePanel
 *
 * Displays the user's AI-generated training schedule with items sorted by
 * priority (Critical first) then deadline (earliest first). Shows a progress
 * bar for overall completion and supports skeleton loading and empty states.
 *
 * Requirements: 10.1, 10.2, 10.9
 */

import { useMemo } from "react";
import { Clock, AlertTriangle, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { TrainingSchedule } from "@/types/training-ecosystem";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A single training item from the schedule_data JSON. */
export interface TrainingItem {
  document_id: number;
  document_title: string;
  priority: string;
  deadline: string | null;
  completed: boolean;
  blocks_access: boolean;
}

interface TrainingSchedulePanelProps {
  schedule: TrainingSchedule | null;
  isLoading: boolean;
  error: string | null;
  onStartTraining?: (item: TrainingItem) => void;
  onRetry?: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

const PRIORITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-200",
  high: "bg-orange-100 text-orange-800 border-orange-200",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-green-100 text-green-800 border-green-200",
};

const MAX_TITLE_LENGTH = 120;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncateTitle(title: string): string {
  if (title.length <= MAX_TITLE_LENGTH) return title;
  return title.slice(0, MAX_TITLE_LENGTH) + "…";
}

function sortItems(items: TrainingItem[]): TrainingItem[] {
  return [...items].sort((a, b) => {
    // Sort by priority first (Critical < High < Medium < Low)
    const priorityA = PRIORITY_ORDER[a.priority.toLowerCase()] ?? 4;
    const priorityB = PRIORITY_ORDER[b.priority.toLowerCase()] ?? 4;
    if (priorityA !== priorityB) return priorityA - priorityB;

    // Then by deadline (earliest first, null deadlines last)
    if (a.deadline && b.deadline) {
      return new Date(a.deadline).getTime() - new Date(b.deadline).getTime();
    }
    if (a.deadline && !b.deadline) return -1;
    if (!a.deadline && b.deadline) return 1;

    return 0;
  });
}

function extractItems(schedule: TrainingSchedule): TrainingItem[] {
  const data = schedule.schedule_data;
  if (Array.isArray(data)) return data as TrainingItem[];
  if (data && typeof data === "object" && "items" in data) {
    return (data as { items: TrainingItem[] }).items;
  }
  return [];
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function ScheduleSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading training schedule">
      {/* Progress bar skeleton */}
      <div className="h-4 w-full rounded bg-muted animate-pulse" />
      {/* Item skeletons */}
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-lg border p-4 space-y-2">
          <div className="h-4 w-3/4 rounded bg-muted animate-pulse" />
          <div className="flex gap-2">
            <div className="h-5 w-16 rounded bg-muted animate-pulse" />
            <div className="h-5 w-24 rounded bg-muted animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TrainingSchedulePanel({
  schedule,
  isLoading,
  error,
  onStartTraining,
  onRetry,
}: TrainingSchedulePanelProps) {
  const sortedItems = useMemo(() => {
    if (!schedule) return [];
    return sortItems(extractItems(schedule));
  }, [schedule]);

  // Loading state
  if (isLoading) {
    return (
      <section aria-label="Training schedule" className="space-y-4">
        <h3 className="text-lg font-semibold">Training Schedule</h3>
        <ScheduleSkeleton />
      </section>
    );
  }

  // Error state
  if (error) {
    return (
      <section aria-label="Training schedule" className="space-y-4">
        <h3 className="text-lg font-semibold">Training Schedule</h3>
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-4">
          <p className="text-sm text-destructive">{error}</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
              Retry
            </Button>
          )}
        </div>
      </section>
    );
  }

  // Empty state
  if (!schedule || sortedItems.length === 0) {
    return (
      <section aria-label="Training schedule" className="space-y-4">
        <h3 className="text-lg font-semibold">Training Schedule</h3>
        <div className="rounded-lg border border-dashed p-8 text-center">
          <BookOpen className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="mt-2 text-sm text-muted-foreground">
            No training items scheduled. Your schedule will appear here once generated.
          </p>
        </div>
      </section>
    );
  }

  // Compute progress
  const completedCount = sortedItems.filter((item) => item.completed).length;
  const totalCount = sortedItems.length;
  const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <section aria-label="Training schedule" className="space-y-4">
      <h3 className="text-lg font-semibold">Training Schedule</h3>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>
            {completedCount} of {totalCount} completed
          </span>
          <span>{progressPercent}%</span>
        </div>
        <div
          className="h-2 w-full rounded-full bg-muted overflow-hidden"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Training progress: ${progressPercent}% complete`}
        >
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Training items list */}
      <ul className="space-y-3" aria-label="Training items">
        {sortedItems.map((item) => (
          <li
            key={item.document_id}
            className={cn(
              "rounded-lg border p-4 transition-colors",
              item.completed && "opacity-60"
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p
                  className="text-sm font-medium leading-tight"
                  title={item.document_title}
                >
                  {truncateTitle(item.document_title)}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {/* Priority badge */}
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
                      PRIORITY_COLORS[item.priority.toLowerCase()] ??
                        "bg-gray-100 text-gray-800 border-gray-200"
                    )}
                  >
                    {item.priority}
                  </span>

                  {/* Deadline */}
                  {item.deadline && (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" aria-hidden="true" />
                      {new Date(item.deadline).toLocaleDateString()}
                    </span>
                  )}

                  {/* Blocks access indicator */}
                  {item.blocks_access && !item.completed && (
                    <span className="inline-flex items-center gap-1 text-xs text-orange-600">
                      <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                      Blocks access
                    </span>
                  )}
                </div>
              </div>

              {/* Action */}
              <div className="shrink-0">
                {item.completed ? (
                  <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700">
                    Completed
                  </span>
                ) : (
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => onStartTraining?.(item)}
                    aria-label={`Start training for ${item.document_title}`}
                  >
                    Start Training
                  </Button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
