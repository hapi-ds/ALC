import { useEffect, useState, useCallback } from "react";
import {
  History,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Loader2,
  Eye,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { ConfigurationSnapshot, ConfigDiffItem } from "@/types/systemConfig";
import { RollbackDialog } from "./RollbackDialog";

/**
 * SnapshotHistoryList — paginated configuration change history (20 per page).
 *
 * Displays each snapshot with timestamp, user, change reason, rollback badge,
 * and changed keys. Supports inline diff view and rollback action.
 *
 * Requirements: 14.1–14.7
 */
export function SnapshotHistoryList() {
  const {
    snapshots,
    snapshotsPagination,
    loading,
    errors,
    fetchSnapshots,
    fetchSnapshotDiff,
  } = useSystemConfigStore();

  const [expandedSnapshotId, setExpandedSnapshotId] = useState<number | null>(null);
  const [diffData, setDiffData] = useState<ConfigDiffItem[]>([]);
  const [diffLoading, setDiffLoading] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<ConfigurationSnapshot | null>(null);

  const isLoading = loading?.["snapshots"] ?? false;
  const fetchError = errors?.["snapshots"] ?? null;
  const snapshotList = snapshots ?? [];

  useEffect(() => {
    fetchSnapshots(1);
  }, [fetchSnapshots]);

  const handlePageChange = useCallback(
    (page: number) => {
      fetchSnapshots(page);
      setExpandedSnapshotId(null);
      setDiffData([]);
    },
    [fetchSnapshots],
  );

  const handleViewDiff = useCallback(
    async (snapshot: ConfigurationSnapshot) => {
      if (expandedSnapshotId === snapshot.id) {
        // Collapse
        setExpandedSnapshotId(null);
        setDiffData([]);
        return;
      }

      setExpandedSnapshotId(snapshot.id);
      setDiffLoading(true);
      try {
        const diff = await fetchSnapshotDiff(snapshot.id);
        setDiffData(diff);
      } catch {
        setDiffData([]);
      } finally {
        setDiffLoading(false);
      }
    },
    [expandedSnapshotId, fetchSnapshotDiff],
  );

  const handleRollbackClick = useCallback((snapshot: ConfigurationSnapshot) => {
    setRollbackTarget(snapshot);
  }, []);

  const handleRollbackClose = useCallback(() => {
    setRollbackTarget(null);
  }, []);

  const handleRollbackSuccess = useCallback(() => {
    setRollbackTarget(null);
    // Refresh the snapshot list after rollback
    fetchSnapshots(snapshotsPagination?.page ?? 1);
  }, [fetchSnapshots, snapshotsPagination]);

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  const formatDiffValue = (value: unknown): string => {
    if (value === null || value === undefined) return "null";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  };

  // Loading skeleton
  if (isLoading && snapshotList.length === 0) {
    return (
      <div className="space-y-3 animate-pulse" aria-label="Loading configuration history">
        <div className="h-6 w-1/3 rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
      </div>
    );
  }

  // Error state
  if (fetchError && snapshotList.length === 0) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load configuration history
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{fetchError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchSnapshots(1)}
        >
          Retry
        </Button>
      </div>
    );
  }

  // Empty state
  if (snapshotList.length === 0) {
    return (
      <div className="rounded-md border border-border p-6 text-center">
        <History className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="mt-2 text-sm text-muted-foreground">
          No configuration changes recorded yet. Changes will appear here after the first configuration update.
        </p>
      </div>
    );
  }

  const { page, total_pages, total } = snapshotsPagination ?? { page: 1, total_pages: 0, total: 0 };

  return (
    <div className="space-y-4">
      {/* Header with count */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {total} configuration change{total !== 1 ? "s" : ""} recorded
        </p>
        {isLoading && (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Refreshing" />
        )}
      </div>

      {/* Snapshot list */}
      <div className="space-y-2" role="list" aria-label="Configuration snapshot history">
        {snapshotList.map((snapshot) => (
          <div
            key={snapshot.id}
            role="listitem"
            className="rounded-md border border-border bg-background"
          >
            {/* Snapshot row */}
            <div className="flex items-start justify-between gap-4 p-4">
              <div className="flex-1 min-w-0 space-y-1">
                {/* Timestamp and user */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-foreground">
                    {formatTimestamp(snapshot.created_at)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    by {snapshot.created_by_name}
                  </span>
                  {snapshot.is_rollback && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                      <RotateCcw className="h-3 w-3" aria-hidden="true" />
                      Rollback
                    </span>
                  )}
                </div>

                {/* Change reason */}
                <p className="text-sm text-muted-foreground truncate">
                  {snapshot.change_reason}
                </p>

                {/* Changed keys */}
                {snapshot.changed_keys.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {snapshot.changed_keys.map((key) => (
                      <span
                        key={key}
                        className="inline-block rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-muted-foreground"
                      >
                        {key}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleViewDiff(snapshot)}
                  aria-expanded={expandedSnapshotId === snapshot.id}
                  aria-label={`View diff for snapshot from ${formatTimestamp(snapshot.created_at)}`}
                >
                  {expandedSnapshotId === snapshot.id ? (
                    <ChevronUp className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <ChevronDown className="h-4 w-4" aria-hidden="true" />
                  )}
                  <Eye className="h-4 w-4" aria-hidden="true" />
                  <span className="sr-only sm:not-sr-only">Diff</span>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleRollbackClick(snapshot)}
                  aria-label={`Rollback to snapshot from ${formatTimestamp(snapshot.created_at)}`}
                >
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                  <span className="sr-only sm:not-sr-only">Rollback</span>
                </Button>
              </div>
            </div>

            {/* Inline diff view */}
            {expandedSnapshotId === snapshot.id && (
              <div className="border-t border-border bg-muted/30 p-4">
                {diffLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    Loading diff...
                  </div>
                ) : diffData.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No differences found between this snapshot and the current configuration.
                  </p>
                ) : (
                  <div className="space-y-2" role="table" aria-label="Configuration diff">
                    <div className="grid grid-cols-3 gap-2 text-xs font-medium text-muted-foreground border-b border-border pb-1">
                      <span>Key</span>
                      <span>Snapshot Value</span>
                      <span>Current Value</span>
                    </div>
                    {diffData.map((item) => (
                      <div
                        key={item.key}
                        className="grid grid-cols-3 gap-2 text-sm py-1 border-b border-border/50 last:border-b-0"
                        role="row"
                      >
                        <span className="font-mono text-xs text-foreground break-all">
                          {item.key}
                        </span>
                        <span className="font-mono text-xs text-red-600 break-all">
                          {formatDiffValue(item.old_value)}
                        </span>
                        <span className="font-mono text-xs text-green-600 break-all">
                          {formatDiffValue(item.new_value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Pagination controls */}
      {total_pages > 1 && (
        <nav
          className="flex items-center justify-between pt-2"
          aria-label="Snapshot history pagination"
        >
          <p className="text-sm text-muted-foreground">
            Page {page} of {total_pages}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => handlePageChange(page - 1)}
              disabled={page <= 1}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= total_pages}
              aria-label="Next page"
            >
              Next
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </nav>
      )}

      {/* Rollback dialog */}
      {rollbackTarget && (
        <RollbackDialog
          snapshot={rollbackTarget}
          open={!!rollbackTarget}
          onClose={handleRollbackClose}
          onSuccess={handleRollbackSuccess}
        />
      )}
    </div>
  );
}
