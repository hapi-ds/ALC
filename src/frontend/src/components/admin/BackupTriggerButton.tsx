import { useEffect, useRef, useState } from "react";
import { Database, Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import { ApiError } from "@/lib/apiClient";

/**
 * BackupTriggerButton — triggers a manual backup with progress indicator.
 *
 * Displays a button to trigger a manual backup. While a backup is active
 * (queued/running), shows a progress indicator with status. Handles 409
 * conflict errors when a concurrent backup is already in progress.
 */
export function BackupTriggerButton() {
  const {
    activeBackupTaskId,
    backupHistory,
    loading,
    errors,
    triggerBackup,
    pollBackupStatus,
    fetchBackupHistory,
  } = useSystemConfigStore();

  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [reason, setReason] = useState("");
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [concurrentError, setConcurrentError] = useState(false);
  const [backupComplete, setBackupComplete] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll for backup status while a backup is active
  useEffect(() => {
    if (activeBackupTaskId) {
      setBackupComplete(false);
      pollRef.current = setInterval(() => {
        pollBackupStatus(activeBackupTaskId);
      }, 3000);
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [activeBackupTaskId, pollBackupStatus]);

  // Detect when backup completes
  useEffect(() => {
    if (!activeBackupTaskId && backupHistory.length > 0) {
      const latest = backupHistory[0];
      if (latest && (latest.status === "completed" || latest.status === "failed")) {
        // Only show completion if we were previously tracking a backup
        if (pollRef.current === null && triggerError === null) {
          // Check if this was recently completed (within last 10 seconds)
          const completedAt = latest.completed_at ? new Date(latest.completed_at).getTime() : 0;
          const now = Date.now();
          if (now - completedAt < 10000) {
            setBackupComplete(true);
            setTimeout(() => setBackupComplete(false), 5000);
          }
        }
      }
    }
  }, [activeBackupTaskId, backupHistory, triggerError]);

  const handleTriggerClick = () => {
    setTriggerError(null);
    setConcurrentError(false);
    setShowReasonDialog(true);
  };

  const handleConfirmTrigger = async () => {
    if (reason.trim().length < 1) return;

    setTriggerError(null);
    setConcurrentError(false);
    try {
      await triggerBackup(reason.trim());
      setShowReasonDialog(false);
      setReason("");
      // Refresh history to show the new queued backup
      fetchBackupHistory();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConcurrentError(true);
        setTriggerError(null);
      } else {
        setTriggerError(
          err instanceof Error ? err.message : "Failed to trigger backup"
        );
      }
      setShowReasonDialog(false);
      setReason("");
    }
  };

  const isTriggering = loading["triggerBackup"];
  const isBackupActive = !!activeBackupTaskId;

  // Find the active backup record for status display
  const activeBackup = activeBackupTaskId
    ? backupHistory.find((b) => b.task_id === activeBackupTaskId)
    : null;

  return (
    <div className="space-y-3">
      {/* Trigger button */}
      <div className="flex items-center gap-3">
        <Button
          onClick={handleTriggerClick}
          disabled={isTriggering || isBackupActive}
          aria-label="Trigger manual backup"
        >
          {isTriggering ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Database className="h-4 w-4" aria-hidden="true" />
          )}
          Trigger Manual Backup
        </Button>

        {backupComplete && (
          <span className="inline-flex items-center gap-1 text-sm text-green-600">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Backup completed
          </span>
        )}
      </div>

      {/* Active backup progress indicator */}
      {isBackupActive && (
        <div
          className="flex items-center gap-3 rounded-md border border-blue-200 bg-blue-50 px-4 py-3"
          role="status"
          aria-label="Backup in progress"
        >
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium text-blue-800">
              Backup in progress
            </p>
            <p className="text-xs text-blue-600">
              Status: {activeBackup?.status === "running" ? "Running" : "Queued"}
              {activeBackup?.status === "running" && " — dumping database and uploading to storage"}
            </p>
          </div>
        </div>
      )}

      {/* Concurrent backup error (409) */}
      {concurrentError && (
        <div
          className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3"
          role="alert"
        >
          <AlertTriangle className="h-4 w-4 text-amber-600" aria-hidden="true" />
          <p className="text-sm text-amber-800">
            A backup is already in progress. Please wait for it to complete before triggering another.
          </p>
        </div>
      )}

      {/* General trigger error */}
      {triggerError && (
        <div
          className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-3"
          role="alert"
        >
          <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
          <p className="text-sm text-red-800">{triggerError}</p>
        </div>
      )}

      {/* X-Change-Reason dialog */}
      {showReasonDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="fixed inset-0 bg-black/50"
            aria-hidden="true"
            onClick={() => setShowReasonDialog(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="backup-reason-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2
              id="backup-reason-title"
              className="text-lg font-semibold text-foreground"
            >
              Trigger Manual Backup
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              This will start a full PostgreSQL database backup. The backup will
              be compressed and uploaded to MinIO storage. Provide a reason for
              the audit trail.
            </p>
            <div className="mt-4">
              <label
                htmlFor="backup-reason-input"
                className="block text-sm font-medium text-foreground"
              >
                Change Reason
              </label>
              <textarea
                id="backup-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why a manual backup is being triggered..."
                rows={3}
                maxLength={500}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                autoFocus
              />
              <p className="mt-1 text-xs text-muted-foreground">
                {reason.trim().length}/500 characters
              </p>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  setShowReasonDialog(false);
                  setReason("");
                }}
              >
                Cancel
              </Button>
              <Button
                disabled={reason.trim().length < 1 || isTriggering}
                onClick={handleConfirmTrigger}
              >
                {isTriggering ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : null}
                Start Backup
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
