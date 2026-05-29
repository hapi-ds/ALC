import { useEffect } from "react";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  AlertTriangle,
  Database,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { BackupRecord } from "@/types/systemConfig";

/**
 * BackupHistoryTable — displays backup history with status, size, duration, and type.
 *
 * Shows a table of all backup records ordered by most recent first.
 * Each row displays timestamp, size, duration, type (scheduled/manual), and status.
 * Active backups (queued/running) are highlighted with a progress indicator.
 */
export function BackupHistoryTable() {
  const { backupHistory, loading, errors, fetchBackupHistory } =
    useSystemConfigStore();

  useEffect(() => {
    fetchBackupHistory();
  }, [fetchBackupHistory]);

  const isLoading = loading["backupHistory"];
  const fetchError = errors["backupHistory"];

  const formatBytes = (bytes: number | null): string => {
    if (bytes === null || bytes === undefined) return "—";
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${units[i]}`;
  };

  const formatDuration = (seconds: number | null): string => {
    if (seconds === null || seconds === undefined) return "—";
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  const formatTimestamp = (timestamp: string | null): string => {
    if (!timestamp) return "—";
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

  const getStatusBadge = (status: BackupRecord["status"]) => {
    switch (status) {
      case "completed":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
            Completed
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
            <XCircle className="h-3 w-3" aria-hidden="true" />
            Failed
          </span>
        );
      case "running":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
            Running
          </span>
        );
      case "queued":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
            <Clock className="h-3 w-3" aria-hidden="true" />
            Queued
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
            Unknown
          </span>
        );
    }
  };

  const getTypeBadge = (type: BackupRecord["backup_type"]) => {
    switch (type) {
      case "scheduled":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-700">
            <Clock className="h-3 w-3" aria-hidden="true" />
            Scheduled
          </span>
        );
      case "manual":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
            <Database className="h-3 w-3" aria-hidden="true" />
            Manual
          </span>
        );
      default:
        return (
          <span className="text-xs text-muted-foreground">{type}</span>
        );
    }
  };

  if (isLoading && backupHistory.length === 0) {
    return (
      <div className="space-y-3 animate-pulse" aria-label="Loading backup history">
        <div className="h-6 w-1/4 rounded bg-muted" />
        <div className="h-10 w-full rounded bg-muted" />
        <div className="h-10 w-full rounded bg-muted" />
        <div className="h-10 w-full rounded bg-muted" />
      </div>
    );
  }

  if (fetchError && backupHistory.length === 0) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load backup history
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{fetchError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchBackupHistory()}
        >
          Retry
        </Button>
      </div>
    );
  }

  if (backupHistory.length === 0) {
    return (
      <div className="rounded-md border border-border p-6 text-center">
        <Database className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="mt-2 text-sm text-muted-foreground">
          No backup history available. Trigger a manual backup or wait for the next scheduled backup.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-foreground">Backup History</h4>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm" aria-label="Backup history table">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Timestamp
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Type
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Status
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Size
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Duration
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Error
              </th>
            </tr>
          </thead>
          <tbody>
            {backupHistory.map((backup) => (
              <tr
                key={backup.id}
                className={`border-b border-border last:border-b-0 ${
                  backup.status === "running" || backup.status === "queued"
                    ? "bg-blue-50/50"
                    : ""
                }`}
              >
                <td className="px-4 py-2 text-foreground whitespace-nowrap">
                  {formatTimestamp(backup.started_at || backup.completed_at)}
                </td>
                <td className="px-4 py-2">{getTypeBadge(backup.backup_type)}</td>
                <td className="px-4 py-2">{getStatusBadge(backup.status)}</td>
                <td className="px-4 py-2 text-foreground whitespace-nowrap">
                  {formatBytes(backup.file_size_bytes)}
                </td>
                <td className="px-4 py-2 text-foreground whitespace-nowrap">
                  {formatDuration(backup.duration_seconds)}
                </td>
                <td className="px-4 py-2 text-red-600 text-xs max-w-[200px] truncate">
                  {backup.error_message || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
