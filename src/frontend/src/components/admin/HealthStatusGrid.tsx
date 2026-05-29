import { useEffect } from "react";
import { AlertTriangle, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { ServiceHealthStatus } from "@/types/systemConfig";

/**
 * HealthStatusGrid — displays color-coded health status cards for all monitored services.
 *
 * Shows a grid of service health cards with:
 * - Green indicator for healthy services
 * - Yellow indicator for degraded services
 * - Red indicator for unreachable services
 * - Uptime percentage (24h) and average response time (5min)
 * - Last checked timestamp
 *
 * Requirements: 10.3, 11.1–11.6
 */
export function HealthStatusGrid() {
  const { healthStatus, loading, errors, fetchHealthStatus } =
    useSystemConfigStore();

  useEffect(() => {
    fetchHealthStatus();
  }, [fetchHealthStatus]);

  const isLoading = loading["healthStatus"];
  const fetchError = errors["healthStatus"];

  if (isLoading && healthStatus.length === 0) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 animate-pulse" aria-label="Loading health status">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-32 rounded-md border border-border bg-muted" />
        ))}
      </div>
    );
  }

  if (fetchError && healthStatus.length === 0) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load health status
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{fetchError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchHealthStatus()}
        >
          Retry
        </Button>
      </div>
    );
  }

  if (healthStatus.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No health status data available.</p>
    );
  }

  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      role="list"
      aria-label="Service health status"
    >
      {healthStatus.map((service) => (
        <HealthStatusCard key={service.service_name} service={service} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HealthStatusCard
// ---------------------------------------------------------------------------

interface HealthStatusCardProps {
  service: ServiceHealthStatus;
}

function HealthStatusCard({ service }: HealthStatusCardProps) {
  const statusConfig = getStatusConfig(service.status);

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  return (
    <div
      role="listitem"
      className={`rounded-md border p-4 ${statusConfig.borderClass}`}
      aria-label={`${service.service_name} health status: ${service.status}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {statusConfig.icon}
          <h4 className="text-sm font-semibold text-foreground capitalize">
            {service.service_name}
          </h4>
        </div>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusConfig.badgeClass}`}
        >
          {statusConfig.label}
        </span>
      </div>

      <div className="mt-3 space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Uptime (24h)</span>
          <span className="font-medium text-foreground">
            {service.uptime_pct_24h.toFixed(1)}%
          </span>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Avg Response (5min)</span>
          <span className="font-medium text-foreground">
            {service.avg_response_time_5min !== null
              ? `${service.avg_response_time_5min.toFixed(0)}ms`
              : "—"}
          </span>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Last Checked</span>
          <span className="font-medium text-foreground">
            {formatTimestamp(service.last_checked)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStatusConfig(status: ServiceHealthStatus["status"]): {
  label: string;
  borderClass: string;
  badgeClass: string;
  icon: React.ReactNode;
} {
  switch (status) {
    case "healthy":
      return {
        label: "Healthy",
        borderClass: "border-green-200 bg-green-50/30",
        badgeClass: "bg-green-100 text-green-700",
        icon: <CheckCircle2 className="h-4 w-4 text-green-500" aria-hidden="true" />,
      };
    case "degraded":
      return {
        label: "Degraded",
        borderClass: "border-yellow-200 bg-yellow-50/30",
        badgeClass: "bg-yellow-100 text-yellow-700",
        icon: <AlertCircle className="h-4 w-4 text-yellow-500" aria-hidden="true" />,
      };
    case "unreachable":
      return {
        label: "Unreachable",
        borderClass: "border-red-200 bg-red-50/30",
        badgeClass: "bg-red-100 text-red-700",
        icon: <AlertTriangle className="h-4 w-4 text-red-500" aria-hidden="true" />,
      };
    default:
      return {
        label: "Unknown",
        borderClass: "border-border",
        badgeClass: "bg-muted text-muted-foreground",
        icon: null,
      };
  }
}
