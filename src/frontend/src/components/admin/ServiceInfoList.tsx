import { useEffect } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Server,
  Clock,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { ServiceInfo } from "@/types/systemConfig";

/**
 * ServiceInfoList — displays all Docker services with container name, state,
 * version, uptime, and per-service resource utilization (CPU %, memory MB, memory limit).
 *
 * Shows a memory warning indicator when usage exceeds 90% of the container limit.
 *
 * Requirements: 12.1–12.5, 13.4
 */
export function ServiceInfoList() {
  const { services = [], loading = {}, errors = {}, fetchServices } = useSystemConfigStore();

  useEffect(() => {
    fetchServices();
  }, [fetchServices]);

  const isLoading = loading["services"];
  const fetchError = errors["services"];

  if (isLoading && services.length === 0) {
    return (
      <div className="space-y-3 animate-pulse" aria-label="Loading services">
        <div className="h-6 w-1/4 rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
        <div className="h-16 w-full rounded bg-muted" />
      </div>
    );
  }

  if (fetchError && services.length === 0) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          <p className="text-sm font-medium text-red-800">
            Failed to load service information
          </p>
        </div>
        <p className="mt-1 text-sm text-red-700">{fetchError}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => fetchServices()}
        >
          Retry
        </Button>
      </div>
    );
  }

  if (services.length === 0) {
    return (
      <div className="rounded-md border border-border p-6 text-center">
        <Server className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="mt-2 text-sm text-muted-foreground">
          No service information available.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-foreground">Docker Services</h4>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm" aria-label="Docker services table">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Service
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Container
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                State
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Version
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Uptime
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                CPU %
              </th>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                Memory
              </th>
            </tr>
          </thead>
          <tbody>
            {services.map((service) => (
              <ServiceRow key={service.container_name} service={service} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ServiceRow
// ---------------------------------------------------------------------------

interface ServiceRowProps {
  service: ServiceInfo;
}

function ServiceRow({ service }: ServiceRowProps) {
  const memoryWarning = isMemoryWarning(service.memory_used_mb, service.memory_limit_mb);

  return (
    <tr
      className={`border-b border-border last:border-b-0 ${
        memoryWarning ? "bg-amber-50/50" : ""
      }`}
    >
      <td className="px-4 py-2 font-medium text-foreground whitespace-nowrap">
        {service.service_name}
      </td>
      <td className="px-4 py-2 text-muted-foreground whitespace-nowrap font-mono text-xs">
        {service.container_name}
      </td>
      <td className="px-4 py-2">
        <StateBadge state={service.running_state} />
      </td>
      <td className="px-4 py-2 text-foreground whitespace-nowrap text-xs">
        {service.version || "—"}
      </td>
      <td className="px-4 py-2 text-foreground whitespace-nowrap">
        <span className="inline-flex items-center gap-1 text-xs">
          <Clock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
          {service.uptime || "—"}
        </span>
      </td>
      <td className="px-4 py-2 text-foreground whitespace-nowrap">
        {service.cpu_percent !== null && service.cpu_percent !== undefined
          ? `${service.cpu_percent.toFixed(1)}%`
          : "—"}
      </td>
      <td className="px-4 py-2 whitespace-nowrap">
        <MemoryCell
          usedMb={service.memory_used_mb}
          limitMb={service.memory_limit_mb}
          warning={memoryWarning}
        />
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// StateBadge
// ---------------------------------------------------------------------------

function StateBadge({ state }: { state: string }) {
  const normalized = state.toLowerCase();

  if (normalized === "running") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        Running
      </span>
    );
  }

  if (normalized === "restarting") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
        Restarting
      </span>
    );
  }

  if (normalized === "exited" || normalized === "stopped") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
        <XCircle className="h-3 w-3" aria-hidden="true" />
        {state}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
      {state}
    </span>
  );
}

// ---------------------------------------------------------------------------
// MemoryCell
// ---------------------------------------------------------------------------

interface MemoryCellProps {
  usedMb: number;
  limitMb: number | null;
  warning: boolean;
}

function MemoryCell({ usedMb, limitMb, warning }: MemoryCellProps) {
  if (usedMb === null || usedMb === undefined) {
    return <span className="text-muted-foreground">—</span>;
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className={`text-xs ${warning ? "text-amber-700 font-medium" : "text-foreground"}`}>
        {usedMb.toFixed(0)} MB
        {limitMb !== null && limitMb > 0 && (
          <span className="text-muted-foreground"> / {limitMb.toFixed(0)} MB</span>
        )}
      </span>
      {warning && (
        <span
          className="inline-flex items-center gap-0.5 text-amber-600"
          aria-label="Memory usage exceeds 90% of limit"
          title="Memory usage exceeds 90% of container limit"
        >
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Returns true when memory usage exceeds 90% of the container limit.
 * Property 14: Memory Utilization Warning Threshold.
 */
function isMemoryWarning(usedMb: number, limitMb: number | null): boolean {
  if (limitMb === null || limitMb <= 0) return false;
  return usedMb / limitMb > 0.9;
}
