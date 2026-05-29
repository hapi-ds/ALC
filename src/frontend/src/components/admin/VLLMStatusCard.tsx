import { useEffect, useRef, useState } from "react";
import { RefreshCw, AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";

/**
 * VLLMStatusCard — displays vLLM service status with restart capability.
 *
 * Shows current vLLM status (running, restarting, error, unreachable),
 * a restart button with X-Change-Reason dialog, elapsed time counter
 * during restart, and timeout/error handling (180s timeout).
 */
export function VLLMStatusCard() {
  const { vllmStatus, loading, errors, fetchVLLMStatus, restartVLLM } =
    useSystemConfigStore();

  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [reason, setReason] = useState("");
  const [restartError, setRestartError] = useState<string | null>(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const RESTART_TIMEOUT_SECONDS = 180;

  useEffect(() => {
    fetchVLLMStatus();
  }, [fetchVLLMStatus]);

  // Elapsed time counter while restarting
  useEffect(() => {
    if (vllmStatus?.status === "restarting") {
      setElapsedTime(0);
      timerRef.current = setInterval(() => {
        setElapsedTime((prev) => prev + 1);
      }, 1000);

      // Poll for status updates every 5 seconds
      pollRef.current = setInterval(() => {
        fetchVLLMStatus();
      }, 5000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [vllmStatus?.status, fetchVLLMStatus]);

  // Timeout detection
  useEffect(() => {
    if (
      vllmStatus?.status === "restarting" &&
      elapsedTime >= RESTART_TIMEOUT_SECONDS
    ) {
      setRestartError(
        `vLLM service failed to restart within ${RESTART_TIMEOUT_SECONDS} seconds.`
      );
    }
  }, [elapsedTime, vllmStatus?.status]);

  const handleRestartClick = () => {
    setShowReasonDialog(true);
    setRestartError(null);
  };

  const handleConfirmRestart = async () => {
    if (reason.trim().length < 1) return;

    setRestartError(null);
    try {
      await restartVLLM(reason.trim());
      setShowReasonDialog(false);
      setReason("");
    } catch (err) {
      setRestartError(
        err instanceof Error ? err.message : "Failed to trigger vLLM restart"
      );
      setShowReasonDialog(false);
      setReason("");
    }
  };

  const isRestarting = vllmStatus?.status === "restarting";
  const isLoadingStatus = loading["vllmStatus"];
  const statusError = errors["vllmStatus"];

  const getStatusIcon = () => {
    if (!vllmStatus) return null;

    switch (vllmStatus.status) {
      case "running":
        return <CheckCircle2 className="h-5 w-5 text-green-500" aria-hidden="true" />;
      case "restarting":
        return <Loader2 className="h-5 w-5 animate-spin text-amber-500" aria-hidden="true" />;
      case "error":
        return <XCircle className="h-5 w-5 text-red-500" aria-hidden="true" />;
      case "unreachable":
        return <AlertTriangle className="h-5 w-5 text-red-500" aria-hidden="true" />;
      default:
        return null;
    }
  };

  const getStatusLabel = () => {
    if (!vllmStatus) return "Unknown";

    switch (vllmStatus.status) {
      case "running":
        return "Running";
      case "restarting":
        return "Restarting";
      case "error":
        return "Error";
      case "unreachable":
        return "Unreachable";
      default:
        return "Unknown";
    }
  };

  const getStatusColor = () => {
    if (!vllmStatus) return "border-border";

    switch (vllmStatus.status) {
      case "running":
        return "border-green-200 bg-green-50";
      case "restarting":
        return "border-amber-200 bg-amber-50";
      case "error":
        return "border-red-200 bg-red-50";
      case "unreachable":
        return "border-red-200 bg-red-50";
      default:
        return "border-border";
    }
  };

  const formatElapsed = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  };

  if (isLoadingStatus && !vllmStatus) {
    return (
      <div
        className="rounded-md border border-border p-4 animate-pulse"
        aria-label="Loading vLLM status"
      >
        <div className="h-5 w-1/3 rounded bg-muted" />
        <div className="mt-2 h-4 w-1/2 rounded bg-muted" />
      </div>
    );
  }

  if (statusError && !vllmStatus) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load vLLM status
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{statusError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchVLLMStatus()}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Status card */}
      <div
        className={`rounded-md border p-4 ${getStatusColor()}`}
        role="status"
        aria-label="vLLM service status"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {getStatusIcon()}
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                vLLM Service
              </h3>
              <p className="text-sm text-muted-foreground">
                Status:{" "}
                <span className="font-medium">{getStatusLabel()}</span>
              </p>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRestartClick}
            disabled={isRestarting || loading["vllmRestart"]}
            aria-label="Restart vLLM service"
          >
            {loading["vllmRestart"] ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            Restart vLLM
          </Button>
        </div>

        {/* Restarting indicator with elapsed time */}
        {isRestarting && (
          <div className="mt-3 flex items-center gap-2 text-sm text-amber-700">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span>
              Restarting... Elapsed: {formatElapsed(elapsedTime)}
            </span>
            {elapsedTime >= RESTART_TIMEOUT_SECONDS && (
              <span className="font-medium text-red-600">(Timeout)</span>
            )}
          </div>
        )}

        {/* Error display */}
        {vllmStatus?.status === "error" && vllmStatus.error && (
          <div className="mt-3 rounded border border-red-200 bg-red-100 px-3 py-2">
            <p className="text-xs font-medium text-red-800">Last error:</p>
            <p className="text-xs text-red-700">{vllmStatus.error}</p>
          </div>
        )}
      </div>

      {/* Restart error */}
      {restartError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3" role="alert">
          <div className="flex items-center gap-2">
            <XCircle className="h-4 w-4 text-red-600" aria-hidden="true" />
            <p className="text-sm text-red-800">{restartError}</p>
          </div>
        </div>
      )}

      {/* X-Change-Reason dialog for restart */}
      {showReasonDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          aria-hidden={!showReasonDialog}
        >
          <div
            className="fixed inset-0 bg-black/50"
            aria-hidden="true"
            onClick={() => setShowReasonDialog(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="restart-reason-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2
              id="restart-reason-title"
              className="text-lg font-semibold text-foreground"
            >
              Restart vLLM Service
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              This will restart the vLLM inference service. The service will be
              unavailable during the restart (up to 180 seconds). Provide a
              reason for the audit trail.
            </p>
            <div className="mt-4">
              <label
                htmlFor="restart-reason-input"
                className="block text-sm font-medium text-foreground"
              >
                Change Reason
              </label>
              <textarea
                id="restart-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why the vLLM service is being restarted..."
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
                disabled={reason.trim().length < 1}
                onClick={handleConfirmRestart}
              >
                Confirm Restart
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
