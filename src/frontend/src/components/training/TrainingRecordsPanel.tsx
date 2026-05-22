import { useState, useMemo } from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  XCircle,
  FileText,
} from "lucide-react";
import type { TrainingTask } from "./types";
import {
  determineRecordValidity,
  sortRecords,
  groupRecordsBySop,
} from "./utils";
import type { TrainingRecord, RecordSortKey } from "./utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TrainingRecordsPanelProps {
  tasks: TrainingTask[];
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SORT_OPTIONS: { value: RecordSortKey; label: string }[] = [
  { value: "completed_at", label: "Completion Date" },
  { value: "sop_document_uuid", label: "SOP UUID" },
  { value: "sop_version", label: "Version" },
];

const EMPTY_STATE_MESSAGE =
  "No training records found. Complete training tasks to build your training history.";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Derive TrainingRecord[] from completed tasks with validity information.
 */
function deriveRecords(tasks: TrainingTask[]): TrainingRecord[] {
  const completedTasks = tasks.filter(
    (t) => t.is_completed && t.completed_at !== null
  );
  const validityMap = determineRecordValidity(tasks);

  return completedTasks.map((task) => ({
    id: task.id,
    sop_document_uuid: task.sop_document_uuid,
    sop_version: task.sop_version,
    completed_at: task.completed_at!,
    is_valid: validityMap[task.id] ?? false,
  }));
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div
      className="space-y-3"
      aria-busy="true"
      aria-label="Loading training records"
    >
      {[1, 2, 3].map((i) => (
        <div key={i} className="animate-pulse rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 rounded bg-muted" />
            <div className="min-w-0 flex-1 space-y-2">
              <div className="h-4 w-2/3 rounded bg-muted" />
              <div className="h-3 w-1/3 rounded bg-muted" />
            </div>
            <div className="h-5 w-16 rounded-full bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error Panel
// ---------------------------------------------------------------------------

function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4"
    >
      <AlertCircle
        className="h-5 w-5 shrink-0 text-destructive"
        aria-hidden="true"
      />
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

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <FileText
        className="h-10 w-10 text-muted-foreground/50"
        aria-hidden="true"
      />
      <p className="mt-3 text-sm text-muted-foreground">
        {EMPTY_STATE_MESSAGE}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Validity Badge
// ---------------------------------------------------------------------------

function ValidityBadge({ isValid }: { isValid: boolean }) {
  if (isValid) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
        <CheckCircle className="h-3 w-3" aria-hidden="true" />
        Valid
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
      <XCircle className="h-3 w-3" aria-hidden="true" />
      Invalidated
    </span>
  );
}

// ---------------------------------------------------------------------------
// Record Row
// ---------------------------------------------------------------------------

function RecordRow({ record }: { record: TrainingRecord }) {
  const formattedDate = new Date(record.completed_at).toLocaleDateString();

  return (
    <div className="flex items-center justify-between gap-4 rounded-md border px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">
          {record.sop_document_uuid}
        </p>
        <p className="text-xs text-muted-foreground">
          Version {record.sop_version} &middot; Completed {formattedDate}
        </p>
      </div>
      <ValidityBadge isValid={record.is_valid} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Record Group (collapsible)
// ---------------------------------------------------------------------------

function RecordGroup({
  sopUuid,
  records,
}: {
  sopUuid: string;
  records: TrainingRecord[];
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Sort records within group by completed_at descending (most recent first)
  const sortedRecords = useMemo(
    () => sortRecords(records, "completed_at"),
    [records]
  );

  const mostRecent = sortedRecords[0];
  const historicalRecords = sortedRecords.slice(1);
  const hasHistory = historicalRecords.length > 0;

  return (
    <div className="rounded-lg border">
      {/* Group header with most recent record */}
      <div className="flex items-center gap-2 p-3">
        {hasHistory ? (
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            aria-expanded={isExpanded}
            aria-label={`Toggle history for ${sopUuid}`}
            className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground transition-colors"
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        ) : (
          <span className="inline-block h-4 w-5 shrink-0" aria-hidden="true" />
        )}
        <div className="min-w-0 flex-1">
          <RecordRow record={mostRecent} />
        </div>
      </div>

      {/* Historical records (collapsed by default) */}
      {isExpanded && hasHistory && (
        <div className="border-t bg-muted/30 px-3 pb-3 pt-2 space-y-2">
          <p className="text-xs font-medium text-muted-foreground px-4">
            Previous versions
          </p>
          {historicalRecords.map((record) => (
            <div key={record.id} className="pl-7">
              <RecordRow record={record} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TrainingRecordsPanel
// ---------------------------------------------------------------------------

export function TrainingRecordsPanel({
  tasks,
  isLoading,
  error,
  onRetry,
}: TrainingRecordsPanelProps) {
  const [sortKey, setSortKey] = useState<RecordSortKey>("completed_at");

  // Derive records from completed tasks
  const records = useMemo(() => deriveRecords(tasks), [tasks]);

  // Sort records
  const sortedRecords = useMemo(
    () => sortRecords(records, sortKey),
    [records, sortKey]
  );

  // Group records by SOP UUID
  const groupedRecords = useMemo(
    () => groupRecordsBySop(sortedRecords),
    [sortedRecords]
  );

  const sopUuids = Object.keys(groupedRecords);

  // Loading state
  if (isLoading) {
    return <LoadingSkeleton />;
  }

  // Error state
  if (error) {
    return <ErrorPanel message={error} onRetry={onRetry} />;
  }

  // Empty state
  if (records.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="space-y-4">
      {/* Sort Controls */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">
          Training Records ({records.length})
        </h3>
        <div className="flex items-center gap-2">
          <label
            htmlFor="records-sort"
            className="text-xs text-muted-foreground"
          >
            Sort by:
          </label>
          <select
            id="records-sort"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as RecordSortKey)}
            className="rounded-md border bg-background px-2 py-1 text-xs text-foreground"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Grouped Records */}
      <div className="space-y-3">
        {sopUuids.map((sopUuid) => (
          <RecordGroup
            key={sopUuid}
            sopUuid={sopUuid}
            records={groupedRecords[sopUuid]}
          />
        ))}
      </div>
    </div>
  );
}
