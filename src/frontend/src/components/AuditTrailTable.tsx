/**
 * AuditTrailTable Component
 *
 * Displays audit trail events in a sortable data table with pagination,
 * loading/empty states, operation type badges, and row click to open detail.
 *
 * Uses shadcn/ui-style table markup with Tailwind CSS styling.
 * Connects to useAuditTrailStore for data, sorting, pagination, and detail fetching.
 *
 * Requirements: 2.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
 */

import { useCallback, useMemo } from "react";
import { ArrowUpDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuditTrailStore } from "@/stores/useAuditTrailStore";
import type { AuditEvent, SortConfig } from "@/types/auditTrail";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SORTABLE_COLUMNS: Record<string, string> = {
  timestamp: "Timestamp",
  user: "User",
  record_type: "Record Type",
  operation_type: "Operation",
};

const MAX_CHANGE_REASON_LENGTH = 80;
const MAX_DISPLAYED_FIELDS = 10;
const SKELETON_ROW_COUNT = 8;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format an ISO timestamp to a human-readable locale string.
 */
function formatTimestamp(isoString: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(isoString));
}

/**
 * Truncate text to a max length, appending ellipsis if truncated.
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "…";
}

/**
 * Get badge color classes for an operation type.
 */
function getOperationBadgeClasses(
  operationType: "INSERT" | "UPDATE" | "DELETE"
): string {
  switch (operationType) {
    case "INSERT":
      return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300";
    case "UPDATE":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300";
    case "DELETE":
      return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300";
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SortableHeaderProps {
  column: string;
  label: string;
  sort: SortConfig;
  onSort: (sort: SortConfig) => void;
}

function SortableHeader({ column, label, sort, onSort }: SortableHeaderProps) {
  const isActive = sort.column === column;
  const nextDirection =
    isActive && sort.direction === "desc" ? "asc" : "desc";

  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 text-left font-medium text-muted-foreground hover:text-foreground transition-colors"
      onClick={() => onSort({ column, direction: nextDirection })}
      aria-label={`Sort by ${label} ${nextDirection === "asc" ? "ascending" : "descending"}`}
    >
      {label}
      <ArrowUpDown
        className={cn(
          "h-3.5 w-3.5",
          isActive ? "text-foreground" : "text-muted-foreground/50"
        )}
        aria-hidden="true"
      />
    </button>
  );
}

interface OperationBadgeProps {
  operationType: "INSERT" | "UPDATE" | "DELETE";
}

function OperationBadge({ operationType }: OperationBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        getOperationBadgeClasses(operationType)
      )}
    >
      {operationType}
    </span>
  );
}

interface ChangedFieldsDisplayProps {
  changedFields: string[];
  totalChangedFields: number;
}

function ChangedFieldsDisplay({
  changedFields,
  totalChangedFields,
}: ChangedFieldsDisplayProps) {
  if (changedFields.length === 0) return <span className="text-muted-foreground">—</span>;

  const displayedFields = changedFields.slice(0, MAX_DISPLAYED_FIELDS);
  const remaining = totalChangedFields - displayedFields.length;

  return (
    <span className="text-xs text-muted-foreground">
      {displayedFields.join(", ")}
      {remaining > 0 && (
        <span className="ml-1 text-xs font-medium text-muted-foreground/70">
          +{remaining} more
        </span>
      )}
    </span>
  );
}

interface TransactionBadgeProps {
  transactionId: number;
  events: AuditEvent[];
}

function TransactionBadge({ transactionId, events }: TransactionBadgeProps) {
  const sharedCount = events.filter(
    (e) => e.transaction_id === transactionId
  ).length;

  if (sharedCount <= 1) return null;

  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-muted text-muted-foreground"
      title={`Transaction ${transactionId} — ${sharedCount} related events`}
    >
      TXN {transactionId}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Skeleton Row
// ---------------------------------------------------------------------------

function SkeletonRow() {
  return (
    <tr className="animate-pulse border-b border-border">
      <td className="px-3 py-3"><div className="h-4 w-28 rounded bg-muted" /></td>
      <td className="px-3 py-3"><div className="h-4 w-24 rounded bg-muted" /></td>
      <td className="px-3 py-3"><div className="h-4 w-20 rounded bg-muted" /></td>
      <td className="px-3 py-3"><div className="h-4 w-12 rounded bg-muted" /></td>
      <td className="px-3 py-3"><div className="h-4 w-16 rounded bg-muted" /></td>
      <td className="px-3 py-3"><div className="h-4 w-32 rounded bg-muted" /></td>
      <td className="px-3 py-3"><div className="h-4 w-24 rounded bg-muted" /></td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// AuditTrailTable
// ---------------------------------------------------------------------------

export function AuditTrailTable() {
  const events = useAuditTrailStore((s) => s.events);
  const isLoading = useAuditTrailStore((s) => s.isLoading);
  const totalCount = useAuditTrailStore((s) => s.totalCount);
  const cursor = useAuditTrailStore((s) => s.cursor);
  const sort = useAuditTrailStore((s) => s.sort);
  const setSort = useAuditTrailStore((s) => s.setSort);
  const fetchNextPage = useAuditTrailStore((s) => s.fetchNextPage);
  const fetchEventDetail = useAuditTrailStore((s) => s.fetchEventDetail);

  // Memoize transaction ID counts for badge display
  const transactionCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const event of events) {
      counts.set(event.transaction_id, (counts.get(event.transaction_id) ?? 0) + 1);
    }
    return counts;
  }, [events]);

  const handleRowClick = useCallback(
    (event: AuditEvent) => {
      fetchEventDetail(event.record_type, event.record_id, event.transaction_id);
    },
    [fetchEventDetail]
  );

  const handleLoadMore = useCallback(() => {
    if (cursor && !isLoading) {
      fetchNextPage();
    }
  }, [cursor, isLoading, fetchNextPage]);

  // ---------------------------------------------------------------------------
  // Render: Loading state (initial load with no events)
  // ---------------------------------------------------------------------------

  if (isLoading && events.length === 0) {
    return (
      <div className="rounded-md border border-border overflow-hidden">
        <table className="w-full text-sm" aria-label="Audit trail events loading">
          <thead className="bg-muted/50">
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Timestamp</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">User</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Record Type</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Record ID</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Operation</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Change Reason</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">Changed Fields</th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: SKELETON_ROW_COUNT }, (_, i) => (
              <SkeletonRow key={i} />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Empty state
  // ---------------------------------------------------------------------------

  if (!isLoading && events.length === 0) {
    return (
      <div className="rounded-md border border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">
          No audit events match the current filters.
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Data table
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-3">
      {/* Count indicator */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Showing {events.length} of {totalCount} events
        </p>
      </div>

      {/* Table */}
      <div className="rounded-md border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" aria-label="Audit trail events">
            <thead className="bg-muted/50">
              <tr className="border-b border-border">
                <th className="px-3 py-2 text-left text-xs">
                  <SortableHeader
                    column="timestamp"
                    label={SORTABLE_COLUMNS.timestamp}
                    sort={sort}
                    onSort={setSort}
                  />
                </th>
                <th className="px-3 py-2 text-left text-xs">
                  <SortableHeader
                    column="user"
                    label={SORTABLE_COLUMNS.user}
                    sort={sort}
                    onSort={setSort}
                  />
                </th>
                <th className="px-3 py-2 text-left text-xs">
                  <SortableHeader
                    column="record_type"
                    label={SORTABLE_COLUMNS.record_type}
                    sort={sort}
                    onSort={setSort}
                  />
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
                  Record ID
                </th>
                <th className="px-3 py-2 text-left text-xs">
                  <SortableHeader
                    column="operation_type"
                    label={SORTABLE_COLUMNS.operation_type}
                    sort={sort}
                    onSort={setSort}
                  />
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
                  Change Reason
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
                  Changed Fields
                </th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => {
                const hasSharedTransaction =
                  (transactionCounts.get(event.transaction_id) ?? 0) > 1;

                return (
                  <tr
                    key={`${event.record_type}-${event.record_id}-${event.transaction_id}`}
                    className="border-b border-border hover:bg-muted/30 cursor-pointer transition-colors"
                    onClick={() => handleRowClick(event)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleRowClick(event);
                      }
                    }}
                    aria-label={`${event.operation_type} on ${event.record_type} ${event.record_id} by ${event.user_display_name ?? `User #${event.user_id}`}`}
                  >
                    {/* Timestamp */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <span className="text-sm">{formatTimestamp(event.timestamp)}</span>
                    </td>

                    {/* User */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <span className="text-sm">
                        {event.user_display_name ?? `User #${event.user_id}`}
                      </span>
                    </td>

                    {/* Record Type */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <span className="text-sm capitalize">
                        {event.record_type.replace(/_/g, " ")}
                      </span>
                    </td>

                    {/* Record ID */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <span className="text-sm font-mono text-muted-foreground">
                        {event.record_id}
                      </span>
                    </td>

                    {/* Operation Type Badge */}
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <OperationBadge operationType={event.operation_type} />
                        {hasSharedTransaction && (
                          <TransactionBadge
                            transactionId={event.transaction_id}
                            events={events}
                          />
                        )}
                      </div>
                    </td>

                    {/* Change Reason (truncated with tooltip) */}
                    <td className="px-3 py-2.5 max-w-[200px]">
                      {event.change_reason ? (
                        <span
                          className="text-sm block truncate"
                          title={
                            event.change_reason.length > MAX_CHANGE_REASON_LENGTH
                              ? event.change_reason
                              : undefined
                          }
                        >
                          {truncateText(event.change_reason, MAX_CHANGE_REASON_LENGTH)}
                        </span>
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </td>

                    {/* Changed Fields */}
                    <td className="px-3 py-2.5 max-w-[200px]">
                      <ChangedFieldsDisplay
                        changedFields={event.changed_fields}
                        totalChangedFields={event.total_changed_fields}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination controls */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Showing {events.length} of {totalCount} events
        </p>

        {cursor && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadMore}
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Loading…
              </>
            ) : (
              "Load more"
            )}
          </Button>
        )}
      </div>
    </div>
  );
}
