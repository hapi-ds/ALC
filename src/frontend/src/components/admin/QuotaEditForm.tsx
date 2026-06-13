import { useState } from "react";
import { useForm } from "react-hook-form";
import { Save, Loader2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import { ApiError } from "@/lib/apiClient";
import type { CompanyStorageUsage, StorageQuotaUpdate } from "@/types/systemConfig";

/**
 * QuotaEditForm — form for setting quota limits and alert thresholds per company.
 *
 * Allows administrators to select a company and configure:
 * - Quota limit in bytes (or clear to remove quota)
 * - Alert threshold percentage (1–99)
 *
 * Requires X-Change-Reason for audit compliance.
 *
 * Requirements: 6.1–6.6
 */

interface QuotaEditFormProps {
  /** The company to edit quota for. If null, shows a prompt to select a company. */
  company: CompanyStorageUsage | null;
  /** Callback when the form is closed/cancelled. */
  onClose?: () => void;
}

interface QuotaFormValues {
  quota_limit_gb: number | null;
  alert_threshold_pct: number | null;
}

export function QuotaEditForm({ company, onClose }: QuotaEditFormProps) {
  const { loading, errors: storeErrors, updateQuota } = useSystemConfigStore();

  const [showReasonDialog, setShowReasonDialog] = useState(false);
  const [reason, setReason] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const currentQuotaGb = company?.quota_limit_bytes
    ? company.quota_limit_bytes / (1024 * 1024 * 1024)
    : null;

  const {
    register,
    handleSubmit,
    formState: { errors: formErrors, isDirty },
  } = useForm<QuotaFormValues>({
    defaultValues: {
      quota_limit_gb: currentQuotaGb,
      alert_threshold_pct: company?.alert_threshold_pct ?? null,
    },
  });

  if (!company) {
    return (
      <div className="rounded-md border border-border p-4">
        <p className="text-sm text-muted-foreground">
          Select a company from the usage list to configure its storage quota.
        </p>
      </div>
    );
  }

  const onFormSubmit = () => {
    setShowReasonDialog(true);
  };

  const handleConfirmSubmit = async (data: QuotaFormValues) => {
    if (reason.trim().length < 1) return;

    setSubmitError(null);
    setSubmitSuccess(false);

    const updateData: StorageQuotaUpdate = {};

    // Convert GB to bytes for the API
    if (data.quota_limit_gb !== null && data.quota_limit_gb !== undefined && data.quota_limit_gb > 0) {
      updateData.quota_limit_bytes = Math.round(data.quota_limit_gb * 1024 * 1024 * 1024);
    } else {
      updateData.quota_limit_bytes = null;
    }

    if (data.alert_threshold_pct !== null && data.alert_threshold_pct !== undefined) {
      updateData.alert_threshold_pct = data.alert_threshold_pct;
    } else {
      updateData.alert_threshold_pct = null;
    }

    try {
      await updateQuota(company.company_id, updateData, reason.trim());
      setSubmitSuccess(true);
      setShowReasonDialog(false);
      setReason("");
    } catch (err) {
      let message = "Failed to update quota";
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

  const isLoading = loading["quotas"];
  const quotaError = storeErrors["quotas"];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-foreground">
            Configure Quota: {company.company_name}
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            Current usage: {company.human_readable} ({company.usage_bytes.toLocaleString()} bytes)
          </p>
        </div>
        {onClose && (
          <Button variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        )}
      </div>

      {/* Success message */}
      {submitSuccess && (
        <div
          className="rounded-md border border-green-200 bg-green-50 px-4 py-3"
          role="alert"
        >
          <p className="text-sm font-medium text-green-800">
            Quota updated successfully.
          </p>
        </div>
      )}

      {/* Error messages */}
      {(submitError || quotaError) && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3" role="alert">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
            <p className="text-sm font-medium text-red-800">
              {submitError || quotaError}
            </p>
          </div>
        </div>
      )}

      {/* Form */}
      <form
        onSubmit={handleSubmit(onFormSubmit)}
        className="space-y-4"
        aria-label={`Quota configuration form for ${company.company_name}`}
      >
        <fieldset className="space-y-4 rounded-md border border-border p-4">
          <legend className="px-2 text-sm font-semibold text-foreground">
            Quota Settings
          </legend>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Quota limit */}
            <div>
              <label
                htmlFor="quota_limit_gb"
                className="block text-sm font-medium text-foreground"
              >
                Quota Limit (GB)
              </label>
              <input
                id="quota_limit_gb"
                type="number"
                step="0.01"
                placeholder="No limit"
                {...register("quota_limit_gb", {
                  valueAsNumber: true,
                  validate: (value) => {
                    if (value === null || value === undefined || isNaN(value)) return true;
                    if (value <= 0) return "Quota limit must be greater than 0";
                    return true;
                  },
                })}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {formErrors.quota_limit_gb && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {formErrors.quota_limit_gb.message}
                </p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                Leave empty to remove quota limit.
              </p>
            </div>

            {/* Alert threshold */}
            <div>
              <label
                htmlFor="alert_threshold_pct"
                className="block text-sm font-medium text-foreground"
              >
                Alert Threshold (%)
              </label>
              <input
                id="alert_threshold_pct"
                type="number"
                min={1}
                max={99}
                placeholder="e.g., 80"
                {...register("alert_threshold_pct", {
                  valueAsNumber: true,
                  validate: (value) => {
                    if (value === null || value === undefined || isNaN(value)) return true;
                    if (value < 1 || value > 99) return "Threshold must be between 1 and 99";
                    if (!Number.isInteger(value)) return "Threshold must be a whole number";
                    return true;
                  },
                })}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              {formErrors.alert_threshold_pct && (
                <p className="mt-1 text-xs text-red-600" role="alert">
                  {formErrors.alert_threshold_pct.message}
                </p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                Warning triggers when usage exceeds this percentage of the quota limit (1–99).
              </p>
            </div>
          </div>
        </fieldset>

        {/* Submit button */}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={!isDirty || isLoading}>
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Save className="h-4 w-4" aria-hidden="true" />
            )}
            Save Quota
          </Button>
          {isDirty && (
            <span className="text-xs text-muted-foreground">Unsaved changes</span>
          )}
        </div>
      </form>

      {/* X-Change-Reason dialog */}
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
            aria-labelledby="quota-reason-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2
              id="quota-reason-title"
              className="text-lg font-semibold text-foreground"
            >
              Reason for Change
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Provide a reason for this quota configuration change. This will be
              recorded in the audit trail.
            </p>
            <div className="mt-4">
              <label
                htmlFor="quota-change-reason-input"
                className="block text-sm font-medium text-foreground"
              >
                Change Reason
              </label>
              <textarea
                id="quota-change-reason-input"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe why this quota is being changed..."
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
                onClick={() => handleSubmit((data) => handleConfirmSubmit(data))()}
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
