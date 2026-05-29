import { useState, useEffect, useCallback } from "react";
import {
  RotateCcw,
  AlertTriangle,
  Loader2,
  X,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type {
  ConfigurationSnapshot,
  ConfigDiffItem,
  RollbackConfirmation,
} from "@/types/systemConfig";

/**
 * RollbackDialog — confirmation dialog for rolling back to a configuration snapshot.
 *
 * Shows a diff preview between the snapshot and current state, requires an
 * X-Change-Reason input, and displays the rollback result (changed categories,
 * services requiring restart). Handles validation failure gracefully.
 *
 * Requirements: 14.2, 14.3, 14.5, 14.6
 */

interface RollbackDialogProps {
  snapshot: ConfigurationSnapshot;
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

type DialogState = "preview" | "confirming" | "success" | "error";

export function RollbackDialog({ snapshot, open, onClose, onSuccess }: RollbackDialogProps) {
  const { fetchSnapshotDiff, rollbackToSnapshot, loading, errors } = useSystemConfigStore();

  const [state, setState] = useState<DialogState>("preview");
  const [diffItems, setDiffItems] = useState<ConfigDiffItem[]>([]);
  const [diffLoading, setDiffLoading] = useState(true);
  const [changeReason, setChangeReason] = useState("");
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [rollbackResult, setRollbackResult] = useState<RollbackConfirmation | null>(null);
  const [rollbackError, setRollbackError] = useState<string | null>(null);

  const isRollingBack = loading["rollback"];

  // Load diff on mount
  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setDiffLoading(true);

    fetchSnapshotDiff(snapshot.id)
      .then((diff) => {
        if (!cancelled) {
          setDiffItems(diff);
          setDiffLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDiffItems([]);
          setDiffLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open, snapshot.id, fetchSnapshotDiff]);

  const validateReason = useCallback((value: string): boolean => {
    const trimmed = value.trim();
    if (!trimmed) {
      setReasonError("Change reason is required");
      return false;
    }
    if (trimmed.length > 500) {
      setReasonError("Change reason must be 500 characters or fewer");
      return false;
    }
    setReasonError(null);
    return true;
  }, []);

  const handleConfirm = useCallback(async () => {
    if (!validateReason(changeReason)) return;

    setState("confirming");
    setRollbackError(null);

    try {
      const result = await rollbackToSnapshot(snapshot.id, changeReason.trim());
      setRollbackResult(result);
      setState("success");
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : errors["rollback"] || "Rollback failed. No changes were applied.";
      setRollbackError(message);
      setState("error");
    }
  }, [changeReason, snapshot.id, rollbackToSnapshot, validateReason, errors]);

  const handleClose = useCallback(() => {
    if (state === "success") {
      onSuccess();
    } else {
      onClose();
    }
  }, [state, onSuccess, onClose]);

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

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rollback-dialog-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50"
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Dialog panel */}
      <div className="relative z-50 w-full max-w-2xl max-h-[85vh] overflow-hidden rounded-lg border border-border bg-background shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5 text-amber-600" aria-hidden="true" />
            <h2 id="rollback-dialog-title" className="text-lg font-semibold text-foreground">
              Rollback Configuration
            </h2>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleClose}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-4 max-h-[calc(85vh-140px)] space-y-4">
          {/* Snapshot info */}
          <div className="rounded-md border border-border bg-muted/30 p-3 space-y-1">
            <p className="text-sm">
              <span className="font-medium">Target snapshot:</span>{" "}
              {formatTimestamp(snapshot.created_at)}
            </p>
            <p className="text-sm">
              <span className="font-medium">Created by:</span>{" "}
              {snapshot.created_by_name}
            </p>
            <p className="text-sm">
              <span className="font-medium">Original reason:</span>{" "}
              {snapshot.change_reason}
            </p>
          </div>

          {/* Preview state: show diff */}
          {(state === "preview" || state === "confirming") && (
            <>
              {/* Diff preview */}
              <div>
                <h3 className="text-sm font-semibold text-foreground mb-2">
                  Changes to be applied (diff between snapshot and current state)
                </h3>

                {diffLoading ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    Loading diff...
                  </div>
                ) : diffItems.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2">
                    No differences found. The current configuration matches this snapshot.
                  </p>
                ) : (
                  <div className="rounded-md border border-border overflow-hidden">
                    <table className="w-full text-sm" aria-label="Configuration diff preview">
                      <thead>
                        <tr className="border-b border-border bg-muted/50">
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground text-xs">
                            Key
                          </th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground text-xs">
                            Snapshot Value (will restore)
                          </th>
                          <th className="px-3 py-2 text-left font-medium text-muted-foreground text-xs">
                            Current Value
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {diffItems.map((item) => (
                          <tr
                            key={item.key}
                            className="border-b border-border/50 last:border-b-0"
                          >
                            <td className="px-3 py-2 font-mono text-xs text-foreground break-all">
                              {item.key}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-green-600 break-all">
                              {formatDiffValue(item.old_value)}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-red-600 break-all">
                              {formatDiffValue(item.new_value)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Change reason input */}
              <div>
                <label
                  htmlFor="rollback-change-reason"
                  className="block text-sm font-medium text-foreground mb-1"
                >
                  Change Reason <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="rollback-change-reason"
                  value={changeReason}
                  onChange={(e) => {
                    setChangeReason(e.target.value);
                    if (reasonError) validateReason(e.target.value);
                  }}
                  placeholder="Explain why you are rolling back this configuration..."
                  rows={3}
                  maxLength={500}
                  disabled={state === "confirming"}
                  className="block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
                  aria-describedby={reasonError ? "rollback-reason-error" : undefined}
                  aria-invalid={!!reasonError}
                />
                <div className="flex items-center justify-between mt-1">
                  {reasonError ? (
                    <p id="rollback-reason-error" className="text-xs text-red-600">
                      {reasonError}
                    </p>
                  ) : (
                    <span />
                  )}
                  <span className="text-xs text-muted-foreground">
                    {changeReason.length}/500
                  </span>
                </div>
              </div>

              {/* Warning */}
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3">
                <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" aria-hidden="true" />
                <p className="text-xs text-amber-800">
                  This action will restore all configuration values to the state captured in the
                  selected snapshot. Some services may require a restart after rollback. The rollback
                  is atomic — if any value fails validation, no changes will be applied.
                </p>
              </div>
            </>
          )}

          {/* Success state */}
          {state === "success" && rollbackResult && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 rounded-md border border-green-200 bg-green-50 p-4">
                <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" aria-hidden="true" />
                <div>
                  <p className="text-sm font-medium text-green-800">
                    Rollback completed successfully
                  </p>
                  <p className="text-xs text-green-700 mt-0.5">
                    Configuration restored to snapshot from{" "}
                    {formatTimestamp(rollbackResult.snapshot_timestamp)}
                  </p>
                </div>
              </div>

              {/* Changed categories */}
              {rollbackResult.changed_categories.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-foreground mb-1">
                    Changed categories:
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {rollbackResult.changed_categories.map((cat) => (
                      <span
                        key={cat}
                        className="inline-block rounded bg-muted px-2 py-0.5 text-xs font-medium text-foreground"
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Services requiring restart */}
              {rollbackResult.services_requiring_restart.length > 0 && (
                <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3">
                  <RefreshCw className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" aria-hidden="true" />
                  <div>
                    <p className="text-sm font-medium text-amber-800">
                      Services requiring restart:
                    </p>
                    <ul className="mt-1 list-disc list-inside text-xs text-amber-700">
                      {rollbackResult.services_requiring_restart.map((svc) => (
                        <li key={svc}>{svc}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Error state */}
          {state === "error" && (
            <div className="space-y-3">
              <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-4">
                <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5 shrink-0" aria-hidden="true" />
                <div>
                  <p className="text-sm font-medium text-red-800">
                    Rollback failed — no changes were applied
                  </p>
                  <p className="text-xs text-red-700 mt-1">
                    {rollbackError}
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setState("preview");
                  setRollbackError(null);
                }}
              >
                Try again
              </Button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
          {(state === "preview" || state === "confirming") && (
            <>
              <Button variant="outline" onClick={handleClose} disabled={isRollingBack}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleConfirm}
                disabled={isRollingBack || diffLoading || diffItems.length === 0}
              >
                {isRollingBack ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    Rolling back...
                  </>
                ) : (
                  <>
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    Confirm Rollback
                  </>
                )}
              </Button>
            </>
          )}
          {(state === "success" || state === "error") && (
            <Button onClick={handleClose}>
              Close
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
