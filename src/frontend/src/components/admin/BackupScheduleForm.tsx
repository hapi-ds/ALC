import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Save, Clock, Calendar, AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";

/**
 * BackupScheduleForm — displays and edits the backup cron schedule and retention policy.
 *
 * Shows the current schedule in both cron and human-readable format,
 * the retention policy (days + backup count), and allows editing the
 * cron expression with X-Change-Reason audit dialog.
 */
export function BackupScheduleForm() {
  const {
    backupSchedule,
    retentionPolicy,
    loading,
    errors,
    fetchBackupSchedule,
    updateBackupSchedule,
    fetchRetentionPolicy,
    updateRetentionPolicy,
  } = useSystemConfigStore();

  const [showScheduleReasonDialog, setShowScheduleReasonDialog] = useState(false);
  const [showRetentionReasonDialog, setShowRetentionReasonDialog] = useState(false);
  const [reason, setReason] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register: registerSchedule,
    handleSubmit: handleScheduleSubmit,
    reset: resetSchedule,
    formState: { errors: scheduleErrors, isDirty: isScheduleDirty },
  } = useForm<{ cron_expression: string }>();

  const {
    register: registerRetention,
    handleSubmit: handleRetentionSubmit,
    reset: resetRetention,
    formState: { errors: retentionErrors, isDirty: isRetentionDirty },
  } = useForm<{ retention_days: number }>();

  useEffect(() => {
    fetchBackupSchedule();
    fetchRetentionPolicy();
  }, [fetchBackupSchedule, fetchRetentionPolicy]);

  useEffect(() => {
    if (backupSchedule) {
      resetSchedule({ cron_expression: backupSchedule.cron_expression });
    }
  }, [backupSchedule, resetSchedule]);

  useEffect(() => {
    if (retentionPolicy) {
      resetRetention({ retention_days: retentionPolicy.retention_days });
    }
  }, [retentionPolicy, resetRetention]);

  const onScheduleFormSubmit = () => {
    setShowScheduleReasonDialog(true);
  };

  const onRetentionFormSubmit = () => {
    setShowRetentionReasonDialog(true);
  };

  const handleConfirmSchedule = async (data: { cron_expression: string }) => {
    if (reason.trim().length < 1) return;

    setSubmitError(null);
    try {
      await updateBackupSchedule(data.cron_expression, reason.trim());
      setShowScheduleReasonDialog(false);
      setReason("");
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to update backup schedule"
      );
      setShowScheduleReasonDialog(false);
      setReason("");
    }
  };

  const handleConfirmRetention = async (data: { retention_days: number }) => {
    if (reason.trim().length < 1) return;

    setSubmitError(null);
    try {
      await updateRetentionPolicy(data.retention_days, reason.trim());
      setShowRetentionReasonDialog(false);
      setReason("");
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to update retention policy"
      );
      setShowRetentionReasonDialog(false);
      setReason("");
    }
  };

  const isLoadingSchedule = loading["backupSchedule"];
  const isLoadingRetention = loading["retentionPolicy"];
  const scheduleError = errors["backupSchedule"];
  const retentionError = errors["retentionPolicy"];

  if ((isLoadingSchedule && !backupSchedule) || (isLoadingRetention && !retentionPolicy)) {
    return (
      <div className="space-y-4 animate-pulse" aria-label="Loading backup configuration">
        <div className="h-6 w-1/3 rounded bg-muted" />
        <div className="h-4 w-2/3 rounded bg-muted" />
        <div className="h-4 w-1/2 rounded bg-muted" />
      </div>
    );
  }

  if ((scheduleError && !backupSchedule) || (retentionError && !retentionPolicy)) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load backup configuration
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">
          {scheduleError || retentionError}
        </p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => {
            fetchBackupSchedule();
            fetchRetentionPolicy();
          }}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Current Schedule Display */}
      {backupSchedule && (
        <div className="rounded-md border border-border p-4">
          <div className="flex items-center gap-2 mb-3">
            <Calendar className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <h4 className="text-sm font-semibold text-foreground">Current Schedule</h4>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <span className="block text-xs font-medium text-muted-foreground">
                Cron Expression
              </span>
              <p className="mt-0.5 text-sm font-mono text-foreground">
                {backupSchedule.cron_expression}
              </p>
            </div>
            <div>
              <span className="block text-xs font-medium text-muted-foreground">
                Human-Readable
              </span>
              <p className="mt-0.5 text-sm text-foreground">
                {backupSchedule.human_readable}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Retention Policy Display */}
      {retentionPolicy && (
        <div className="rounded-md border border-border p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <h4 className="text-sm font-semibold text-foreground">Retention Policy</h4>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <span className="block text-xs font-medium text-muted-foreground">
                Retention Period
              </span>
              <p className="mt-0.5 text-sm text-foreground">
                {retentionPolicy.retention_days} day{retentionPolicy.retention_days !== 1 ? "s" : ""}
              </p>
            </div>
            <div>
              <span className="block text-xs font-medium text-muted-foreground">
                Backups Stored
              </span>
              <p className="mt-0.5 text-sm text-foreground">
                {retentionPolicy.backup_count} backup{retentionPolicy.backup_count !== 1 ? "s" : ""}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Edit Schedule Form */}
      <form
        onSubmit={handleScheduleSubmit(onScheduleFormSubmit)}
        className="space-y-4"
        aria-label="Edit backup schedule form"
      >
        <fieldset className="space-y-3 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Edit Schedule
          </legend>
          <div>
            <label
              htmlFor="cron_expression"
              className="block text-sm font-medium text-foreground"
            >
              Cron Expression
            </label>
            <input
              id="cron_expression"
              type="text"
              placeholder="0 2 * * *"
              {...registerSchedule("cron_expression", {
                required: "Cron expression is required",
                minLength: { value: 9, message: "Cron expression must be at least 9 characters" },
                maxLength: { value: 100, message: "Cron expression must be at most 100 characters" },
              })}
              className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {scheduleErrors.cron_expression && (
              <p className="mt-1 text-xs text-red-600" role="alert">
                {scheduleErrors.cron_expression.message}
              </p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              5-field cron format: minute hour day-of-month month day-of-week
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={!isScheduleDirty || isLoadingSchedule}>
              {isLoadingSchedule ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Save className="h-4 w-4" aria-hidden="true" />
              )}
              Update Schedule
            </Button>
          </div>
        </fieldset>
      </form>

      {/* Edit Retention Form */}
      <form
        onSubmit={handleRetentionSubmit(onRetentionFormSubmit)}
        className="space-y-4"
        aria-label="Edit retention policy form"
      >
        <fieldset className="space-y-3 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Edit Retention Policy
          </legend>
          <div>
            <label
              htmlFor="retention_days"
              className="block text-sm font-medium text-foreground"
            >
              Retention Period (days)
            </label>
            <input
              id="retention_days"
              type="number"
              {...registerRetention("retention_days", {
                valueAsNumber: true,
                required: "Retention days is required",
                min: { value: 1, message: "Minimum retention is 1 day" },
                max: { value: 365, message: "Maximum retention is 365 days" },
              })}
              className="mt-1 block w-full max-w-xs rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {retentionErrors.retention_days && (
              <p className="mt-1 text-xs text-red-600" role="alert">
                {retentionErrors.retention_days.message}
              </p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Backups older than this will be automatically cleaned up (minimum 1 retained).
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={!isRetentionDirty || isLoadingRetention}>
              {isLoadingRetention ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Save className="h-4 w-4" aria-hidden="true" />
              )}
              Update Retention
            </Button>
          </div>
        </fieldset>
      </form>

      {/* Submit error */}
      {submitError && (
        <p className="text-sm text-red-600" role="alert">
          {submitError}
        </p>
      )}

      {/* X-Change-Reason dialog for schedule */}
      {showScheduleReasonDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="fixed inset-0 bg-black/50"
            aria-hidden="true"
            onClick={() => setShowScheduleReasonDialog(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="schedule-reason-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2
              id="schedule-reason-title"
              className="text-lg font-semibold text-foreground"
            >
              Update Backup Schedule
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Provide a reason for changing the backup schedule. This will be
              recorded in the audit trail.
            </p>
            <div className="mt-4">
              <label
                htmlFor="schedule-reason-input"
                className="block text-sm font-medium text-foreground"
              >
                Change Reason
              </label>
              <textarea
                id="schedule-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why the backup schedule is being changed..."
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
                  setShowScheduleReasonDialog(false);
                  setReason("");
                }}
              >
                Cancel
              </Button>
              <Button
                disabled={reason.trim().length < 1}
                onClick={() =>
                  handleScheduleSubmit((data) => handleConfirmSchedule(data))()
                }
              >
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* X-Change-Reason dialog for retention */}
      {showRetentionReasonDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="fixed inset-0 bg-black/50"
            aria-hidden="true"
            onClick={() => setShowRetentionReasonDialog(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="retention-reason-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2
              id="retention-reason-title"
              className="text-lg font-semibold text-foreground"
            >
              Update Retention Policy
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Provide a reason for changing the retention policy. This will be
              recorded in the audit trail.
            </p>
            <div className="mt-4">
              <label
                htmlFor="retention-reason-input"
                className="block text-sm font-medium text-foreground"
              >
                Change Reason
              </label>
              <textarea
                id="retention-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why the retention policy is being changed..."
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
                  setShowRetentionReasonDialog(false);
                  setReason("");
                }}
              >
                Cancel
              </Button>
              <Button
                disabled={reason.trim().length < 1}
                onClick={() =>
                  handleRetentionSubmit((data) => handleConfirmRetention(data))()
                }
              >
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
