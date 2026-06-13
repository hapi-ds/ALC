import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Save, Settings, AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import { ApiError } from "@/lib/apiClient";
import type { HealthCheckConfig } from "@/types/systemConfig";

/**
 * HealthConfigForm — form for editing health check parameters.
 *
 * Allows administrators to configure:
 * - Polling interval (10–300 seconds)
 * - Degraded threshold (1–30 seconds)
 * - Unreachable timeout (5–60 seconds)
 *
 * Changes are applied on the next health check cycle without requiring a service restart.
 * Requires X-Change-Reason for audit compliance.
 *
 * Requirements: 15.1–15.5
 */
export function HealthConfigForm() {
  const {
    healthConfig,
    loading,
    errors,
    fetchHealthConfig,
    updateHealthConfig,
  } = useSystemConfigStore();

  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [reason, setReason] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors: formErrors, isDirty },
  } = useForm<HealthCheckConfig>();

  useEffect(() => {
    fetchHealthConfig();
  }, [fetchHealthConfig]);

  useEffect(() => {
    if (healthConfig) {
      reset(healthConfig);
    }
  }, [healthConfig, reset]);

  const onFormSubmit = () => {
    setShowReasonDialog(true);
  };

  const handleConfirm = async (data: HealthCheckConfig) => {
    if (reason.trim().length < 1) return;

    setSubmitError(null);
    try {
      await updateHealthConfig(data, reason.trim());
      setShowReasonDialog(false);
      setReason("");
    } catch (err) {
      let message = "Failed to update health check configuration";
      if (err instanceof ApiError) {
        try {
          const body = JSON.parse(err.body);
          message = body.detail || message;
        } catch {
          // body wasn't JSON
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setSubmitError(message);
      setShowReasonDialog(false);
      setReason("");
    }
  };

  const isLoading = loading["healthConfig"];
  const fetchError = errors["healthConfig"];

  if (isLoading && !healthConfig) {
    return (
      <div className="space-y-4 animate-pulse" aria-label="Loading health configuration">
        <div className="h-6 w-1/3 rounded bg-muted" />
        <div className="h-4 w-2/3 rounded bg-muted" />
        <div className="h-4 w-1/2 rounded bg-muted" />
      </div>
    );
  }

  if (fetchError && !healthConfig) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load health check configuration
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{fetchError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchHealthConfig()}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Current config display */}
      {healthConfig && (
        <div className="rounded-md border border-border p-4">
          <div className="flex items-center gap-2 mb-3">
            <Settings className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <h4 className="text-sm font-semibold text-foreground">Current Configuration</h4>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <span className="block text-xs font-medium text-muted-foreground">
                Polling Interval
              </span>
              <p className="mt-0.5 text-sm text-foreground">
                {healthConfig.polling_interval_seconds}s
              </p>
            </div>
            <div>
              <span className="block text-xs font-medium text-muted-foreground">
                Degraded Threshold
              </span>
              <p className="mt-0.5 text-sm text-foreground">
                {healthConfig.degraded_threshold_seconds}s
              </p>
            </div>
            <div>
              <span className="block text-xs font-medium text-muted-foreground">
                Unreachable Timeout
              </span>
              <p className="mt-0.5 text-sm text-foreground">
                {healthConfig.unreachable_timeout_seconds}s
              </p>
            </div>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Changes are applied on the next health check cycle without requiring a service restart.
          </p>
        </div>
      )}

      {/* Edit form */}
      <form
        onSubmit={handleSubmit(onFormSubmit)}
        className="space-y-4"
        aria-label="Edit health check configuration form"
      >
        <fieldset className="space-y-4 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Edit Health Check Parameters
          </legend>

          {/* Polling interval */}
          <div>
            <label
              htmlFor="polling_interval_seconds"
              className="block text-sm font-medium text-foreground"
            >
              Polling Interval (seconds)
            </label>
            <input
              id="polling_interval_seconds"
              type="number"
              {...register("polling_interval_seconds", {
                valueAsNumber: true,
                required: "Polling interval is required",
                min: { value: 10, message: "Minimum polling interval is 10 seconds" },
                max: { value: 300, message: "Maximum polling interval is 300 seconds" },
              })}
              className="mt-1 block w-full max-w-xs rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {formErrors.polling_interval_seconds && (
              <p className="mt-1 text-xs text-red-600" role="alert">
                {formErrors.polling_interval_seconds.message}
              </p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              How often health checks are performed (10–300 seconds).
            </p>
          </div>

          {/* Degraded threshold */}
          <div>
            <label
              htmlFor="degraded_threshold_seconds"
              className="block text-sm font-medium text-foreground"
            >
              Degraded Threshold (seconds)
            </label>
            <input
              id="degraded_threshold_seconds"
              type="number"
              {...register("degraded_threshold_seconds", {
                valueAsNumber: true,
                required: "Degraded threshold is required",
                min: { value: 1, message: "Minimum degraded threshold is 1 second" },
                max: { value: 30, message: "Maximum degraded threshold is 30 seconds" },
              })}
              className="mt-1 block w-full max-w-xs rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {formErrors.degraded_threshold_seconds && (
              <p className="mt-1 text-xs text-red-600" role="alert">
                {formErrors.degraded_threshold_seconds.message}
              </p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Response time above this marks a service as degraded (1–30 seconds).
            </p>
          </div>

          {/* Unreachable timeout */}
          <div>
            <label
              htmlFor="unreachable_timeout_seconds"
              className="block text-sm font-medium text-foreground"
            >
              Unreachable Timeout (seconds)
            </label>
            <input
              id="unreachable_timeout_seconds"
              type="number"
              {...register("unreachable_timeout_seconds", {
                valueAsNumber: true,
                required: "Unreachable timeout is required",
                min: { value: 5, message: "Minimum unreachable timeout is 5 seconds" },
                max: { value: 60, message: "Maximum unreachable timeout is 60 seconds" },
              })}
              className="mt-1 block w-full max-w-xs rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {formErrors.unreachable_timeout_seconds && (
              <p className="mt-1 text-xs text-red-600" role="alert">
                {formErrors.unreachable_timeout_seconds.message}
              </p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              No response within this time marks a service as unreachable (5–60 seconds).
            </p>
          </div>

          {/* Submit button */}
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={!isDirty || isLoading}>
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Save className="h-4 w-4" aria-hidden="true" />
              )}
              Update Configuration
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
            aria-labelledby="health-config-reason-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2
              id="health-config-reason-title"
              className="text-lg font-semibold text-foreground"
            >
              Update Health Check Configuration
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Provide a reason for changing the health check parameters. This will be
              recorded in the audit trail.
            </p>
            <div className="mt-4">
              <label
                htmlFor="health-config-reason-input"
                className="block text-sm font-medium text-foreground"
              >
                Change Reason
              </label>
              <textarea
                id="health-config-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why the health check configuration is being changed..."
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
                onClick={() => handleSubmit((data) => handleConfirm(data))()}
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
