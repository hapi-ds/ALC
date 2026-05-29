import { useEffect } from "react";
import { AlertTriangle, HardDrive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { CompanyStorageUsage } from "@/types/systemConfig";

/**
 * StorageUsageList — displays per-company storage usage with progress bars.
 *
 * Shows company name, usage in bytes and human-readable format, quota status
 * (normal/warning/exceeded), and a visual progress bar for usage vs quota.
 * Displays a warning indicator when usage exceeds the alert threshold.
 * Shows a disabled state when no quota is configured.
 *
 * Requirements: 5.1–5.6
 */
export function StorageUsageList() {
  const { storageUsage, storageTotals, loading, errors, fetchStorageUsage } =
    useSystemConfigStore();

  useEffect(() => {
    fetchStorageUsage();
  }, [fetchStorageUsage]);

  const isLoading = loading["storageUsage"];
  const fetchError = errors["storageUsage"];

  if (isLoading && storageUsage.length === 0) {
    return (
      <div className="space-y-4 animate-pulse" aria-label="Loading storage usage">
        <div className="h-6 w-1/3 rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
      </div>
    );
  }

  if (fetchError && storageUsage.length === 0) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load storage usage data
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{fetchError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchStorageUsage()}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Storage totals summary */}
      {storageTotals && (
        <div className="rounded-md border border-border bg-muted/30 p-4">
          <div className="flex items-center gap-2 mb-2">
            <HardDrive className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <h4 className="text-sm font-semibold text-foreground">Total Storage</h4>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <div>
              <span className="text-xs text-muted-foreground">Used</span>
              <p className="text-sm font-medium text-foreground">
                {storageTotals.human_readable_used}
                <span className="ml-1 text-xs text-muted-foreground">
                  ({storageTotals.total_used_bytes.toLocaleString()} bytes)
                </span>
              </p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Capacity</span>
              <p className="text-sm font-medium text-foreground">
                {storageTotals.human_readable_capacity}
                <span className="ml-1 text-xs text-muted-foreground">
                  ({storageTotals.total_capacity_bytes.toLocaleString()} bytes)
                </span>
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Per-company usage list */}
      {storageUsage.length === 0 ? (
        <p className="text-sm text-muted-foreground">No company storage data available.</p>
      ) : (
        <div className="space-y-3" role="list" aria-label="Company storage usage">
          {storageUsage.map((company) => (
            <StorageUsageRow key={company.company_id} company={company} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// StorageUsageRow
// ---------------------------------------------------------------------------

interface StorageUsageRowProps {
  company: CompanyStorageUsage;
}

function StorageUsageRow({ company }: StorageUsageRowProps) {
  const hasQuota = company.quota_limit_bytes !== null && company.quota_limit_bytes > 0;
  const usagePercent = hasQuota
    ? Math.min((company.usage_bytes / company.quota_limit_bytes!) * 100, 100)
    : 0;

  const statusConfig = getStatusConfig(company.quota_status, hasQuota);

  return (
    <div
      role="listitem"
      className={`rounded-md border p-4 ${statusConfig.borderClass}`}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Company info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h5 className="text-sm font-medium text-foreground truncate">
              {company.company_name}
            </h5>
            {/* Status badge */}
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusConfig.badgeClass}`}
            >
              {statusConfig.label}
            </span>
          </div>

          {/* Usage details */}
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-sm text-foreground">{company.human_readable}</span>
            <span className="text-xs text-muted-foreground">
              ({company.usage_bytes.toLocaleString()} bytes)
            </span>
          </div>
        </div>

        {/* Warning indicator */}
        {company.quota_status === "quota_warning" && (
          <div
            className="flex items-center gap-1 text-amber-600"
            aria-label="Storage usage warning: exceeds alert threshold"
          >
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            <span className="text-xs font-medium">Warning</span>
          </div>
        )}
        {company.quota_status === "quota_exceeded" && (
          <div
            className="flex items-center gap-1 text-red-600"
            aria-label="Storage quota exceeded"
          >
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            <span className="text-xs font-medium">Exceeded</span>
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="mt-3">
        {hasQuota ? (
          <div>
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>{usagePercent.toFixed(1)}% of quota used</span>
              <span>
                {formatBytesCompact(company.quota_limit_bytes!)} limit
              </span>
            </div>
            <div
              className="h-2 w-full rounded-full bg-muted overflow-hidden"
              role="progressbar"
              aria-valuenow={Math.round(usagePercent)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${company.company_name} storage usage: ${usagePercent.toFixed(1)}% of quota`}
            >
              <div
                className={`h-full rounded-full transition-all ${statusConfig.barClass}`}
                style={{ width: `${Math.min(usagePercent, 100)}%` }}
              />
            </div>
            {/* Alert threshold marker */}
            {company.alert_threshold_pct !== null && (
              <p className="mt-1 text-xs text-muted-foreground">
                Alert threshold: {company.alert_threshold_pct}%
              </p>
            )}
          </div>
        ) : (
          <div className="opacity-50" aria-disabled="true">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>No quota configured</span>
            </div>
            <div
              className="h-2 w-full rounded-full bg-muted"
              role="progressbar"
              aria-valuenow={0}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`${company.company_name} storage: no quota configured`}
              aria-disabled="true"
            >
              <div className="h-full rounded-full bg-muted-foreground/20" style={{ width: "0%" }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStatusConfig(
  status: CompanyStorageUsage["quota_status"],
  hasQuota: boolean,
): {
  label: string;
  borderClass: string;
  badgeClass: string;
  barClass: string;
} {
  if (!hasQuota) {
    return {
      label: "No Quota",
      borderClass: "border-border",
      badgeClass: "bg-muted text-muted-foreground",
      barClass: "bg-muted-foreground/20",
    };
  }

  switch (status) {
    case "quota_exceeded":
      return {
        label: "Exceeded",
        borderClass: "border-red-200 bg-red-50/30",
        badgeClass: "bg-red-100 text-red-700",
        barClass: "bg-red-500",
      };
    case "quota_warning":
      return {
        label: "Warning",
        borderClass: "border-amber-200 bg-amber-50/30",
        badgeClass: "bg-amber-100 text-amber-700",
        barClass: "bg-amber-500",
      };
    case "normal":
    default:
      return {
        label: "Normal",
        borderClass: "border-border",
        badgeClass: "bg-green-100 text-green-700",
        barClass: "bg-green-500",
      };
  }
}

/**
 * Compact byte formatting for inline display (e.g., quota limit labels).
 */
function formatBytesCompact(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const value = bytes / Math.pow(k, i);
  return `${value.toFixed(value < 10 ? 2 : value < 100 ? 1 : 0)} ${units[i]}`;
}
