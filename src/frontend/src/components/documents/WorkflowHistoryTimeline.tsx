import { useEffect, useState } from "react";
import {
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { getStateBadgeColor, truncateText } from "@/lib/workflowUtils";

// ---------------------------------------------------------------------------
// Badge color mapping (Tailwind classes)
// ---------------------------------------------------------------------------

const STATE_BADGE_CLASSES: Record<string, string> = {
  gray: "bg-gray-100 text-gray-800",
  blue: "bg-blue-100 text-blue-800",
  green: "bg-green-100 text-green-800",
  red: "bg-red-100 text-red-800",
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COLLAPSED_LIMIT = 5;
const MAX_INLINE_ENTRIES = 50;
const REASON_TRUNCATE_LENGTH = 120;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface WorkflowHistoryTimelineProps {
  /** The document's UUID for API calls */
  documentUuid: string;
  /** Whether the timeline should start expanded (default: false) */
  defaultExpanded?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function WorkflowHistoryTimeline({
  documentUuid,
  defaultExpanded = false,
}: WorkflowHistoryTimelineProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [showAll, setShowAll] = useState(false);
  const [expandedReasons, setExpandedReasons] = useState<Set<number>>(
    new Set()
  );

  // Store state
  const history = useWorkflowExecutionStore((s) => s.history);
  const isLoadingHistory = useWorkflowExecutionStore(
    (s) => s.isLoadingHistory
  );
  const historyError = useWorkflowExecutionStore((s) => s.historyError);

  // Store actions
  const fetchTransitionHistory = useWorkflowExecutionStore(
    (s) => s.fetchTransitionHistory
  );

  // Fetch history on mount / documentUuid change
  useEffect(() => {
    fetchTransitionHistory(documentUuid);
  }, [documentUuid, fetchTransitionHistory]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleRetry() {
    fetchTransitionHistory(documentUuid);
  }

  function toggleReasonExpanded(entryId: number) {
    setExpandedReasons((prev) => {
      const next = new Set(prev);
      if (next.has(entryId)) {
        next.delete(entryId);
      } else {
        next.add(entryId);
      }
      return next;
    });
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function getBadgeClasses(state: string): string {
    const color = getStateBadgeColor(state);
    return STATE_BADGE_CLASSES[color] || STATE_BADGE_CLASSES.gray;
  }

  // Determine visible entries based on expand/showAll state
  function getVisibleEntries() {
    if (!expanded) return [];
    if (showAll) {
      return history.slice(0, MAX_INLINE_ENTRIES);
    }
    return history.slice(0, COLLAPSED_LIMIT);
  }

  // ---------------------------------------------------------------------------
  // Render: Loading skeleton
  // ---------------------------------------------------------------------------

  if (isLoadingHistory) {
    return (
      <div
        className="rounded-lg border p-6"
        role="region"
        aria-label="Workflow Transition History"
      >
        <div aria-live="polite" className="sr-only">
          Loading transition history...
        </div>
        <div className="animate-pulse space-y-4">
          <div className="h-5 w-48 bg-muted rounded" />
          <div className="space-y-3">
            <div className="h-12 bg-muted rounded" />
            <div className="h-12 bg-muted rounded" />
            <div className="h-12 bg-muted rounded" />
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Error state
  // ---------------------------------------------------------------------------

  if (historyError) {
    return (
      <div
        className="rounded-lg border p-6"
        role="region"
        aria-label="Workflow Transition History"
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Transition History</h3>
        </div>
        <div className="mt-4 flex items-center gap-3 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{historyError}</span>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRetry}
            className="ml-auto gap-1"
            aria-label="Retry loading transition history"
          >
            <RefreshCw className="h-3 w-3" aria-hidden="true" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Main panel
  // ---------------------------------------------------------------------------

  const visibleEntries = getVisibleEntries();
  const hasMoreThanLimit = history.length > COLLAPSED_LIMIT;
  const needsScrollContainer =
    showAll && history.length > MAX_INLINE_ENTRIES;

  return (
    <div
      className="rounded-lg border p-6"
      role="region"
      aria-label="Workflow Transition History"
    >
      {/* Panel header with collapse toggle */}
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls="workflow-history-content"
      >
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold">Transition History</h3>
          {history.length > 0 && (
            <span className="text-sm text-muted-foreground">
              ({history.length} {history.length === 1 ? "entry" : "entries"})
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        )}
      </button>

      {/* Collapsible content */}
      {expanded && (
        <div id="workflow-history-content" className="mt-4">
          {/* Empty state */}
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No transition history available for this document.
            </p>
          ) : (
            <>
              {/* Timeline list */}
              <div
                className={
                  needsScrollContainer
                    ? "max-h-[600px] overflow-y-auto"
                    : undefined
                }
              >
                <ol className="relative ml-3 space-y-0">
                  {/* Vertical timeline line */}
                  <div className="absolute left-0 top-0 bottom-0 w-px bg-border" />

                  {visibleEntries.map((entry) => {
                    const reasonIsLong =
                      entry.change_reason !== null &&
                      entry.change_reason.length > REASON_TRUNCATE_LENGTH;
                    const isReasonExpanded = expandedReasons.has(entry.id);

                    return (
                      <li key={entry.id} className="relative pl-6 pb-4">
                        {/* Timeline dot */}
                        <div className="absolute left-0 top-2 -translate-x-1/2 h-3 w-3 rounded-full border-2 bg-background border-muted-foreground" />

                        <div className="rounded-md border p-3">
                          {/* State transition */}
                          <div className="flex items-center gap-2 flex-wrap">
                            <span
                              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${getBadgeClasses(entry.previous_state)}`}
                            >
                              {entry.previous_state}
                            </span>
                            <ArrowRight
                              className="h-3.5 w-3.5 text-muted-foreground shrink-0"
                              aria-hidden="true"
                            />
                            <span
                              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${getBadgeClasses(entry.new_state)}`}
                            >
                              {entry.new_state}
                            </span>
                          </div>

                          {/* Metadata */}
                          <div className="mt-1.5 text-xs text-muted-foreground space-y-0.5">
                            <p>
                              {new Date(entry.timestamp).toLocaleString()} —
                              User #{entry.user_id}
                            </p>

                            {/* Change reason */}
                            {entry.change_reason && (
                              <div>
                                <p className="text-foreground/80">
                                  {reasonIsLong && !isReasonExpanded
                                    ? truncateText(
                                        entry.change_reason,
                                        REASON_TRUNCATE_LENGTH
                                      )
                                    : entry.change_reason}
                                </p>
                                {reasonIsLong && (
                                  <button
                                    type="button"
                                    className="text-primary text-xs hover:underline mt-0.5"
                                    onClick={() =>
                                      toggleReasonExpanded(entry.id)
                                    }
                                    aria-label={
                                      isReasonExpanded
                                        ? "Show less of change reason"
                                        : "Show more of change reason"
                                    }
                                  >
                                    {isReasonExpanded
                                      ? "Show less"
                                      : "Show more"}
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </div>

              {/* Show all button */}
              {hasMoreThanLimit && !showAll && (
                <div className="mt-3 text-center">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowAll(true)}
                    aria-label={`Show all ${history.length} transition history entries`}
                  >
                    Show all ({history.length})
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Aria live region for loading announcements */}
      <div aria-live="polite" className="sr-only">
        {isLoadingHistory
          ? "Loading transition history..."
          : "Transition history loaded."}
      </div>
    </div>
  );
}
