import { useEffect, useState } from "react";
import { AlertTriangle, BarChart3, Cpu, MemoryStick } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { ResourceMetrics, ServiceInfo } from "@/types/systemConfig";

/**
 * ResourceUtilizationCharts — displays CPU and memory utilization trends
 * for each Docker service over the last 60 minutes.
 *
 * Uses a simple inline SVG sparkline chart for each service showing
 * CPU % and memory MB trends. Includes a memory warning indicator
 * when usage exceeds 90% of the container limit.
 *
 * Requirements: 13.1–13.5
 */
export function ResourceUtilizationCharts() {
  const { services = [], resourceMetrics = {}, loading = {}, errors = {}, fetchServices, fetchResourceMetrics } =
    useSystemConfigStore();

  const [selectedService, setSelectedService] = useState<string | null>(null);

  useEffect(() => {
    if (services.length === 0) {
      fetchServices();
    }
  }, [services.length, fetchServices]);

  // Fetch metrics for selected service (or first service by default)
  useEffect(() => {
    const target = selectedService ?? services[0]?.service_name;
    if (target) {
      fetchResourceMetrics(target);
    }
  }, [selectedService, services, fetchResourceMetrics]);

  const isLoading = loading["resourceMetrics"];
  const fetchError = errors["resourceMetrics"];

  const activeService = selectedService ?? services[0]?.service_name ?? null;
  const metrics = activeService ? resourceMetrics[activeService] ?? [] : [];
  const serviceInfo = services.find((s) => s.service_name === activeService);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground">
          Resource Utilization (Last 60 min)
        </h4>
        {isLoading && (
          <span className="text-xs text-muted-foreground animate-pulse">Updating…</span>
        )}
      </div>

      {/* Service selector */}
      {services.length > 0 && (
        <div>
          <label
            htmlFor="service-metrics-select"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Select service
          </label>
          <select
            id="service-metrics-select"
            value={activeService ?? ""}
            onChange={(e) => setSelectedService(e.target.value || null)}
            className="block w-full max-w-xs rounded-md border border-border bg-background px-3 py-1.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          >
            {services.map((s) => (
              <option key={s.service_name} value={s.service_name}>
                {s.service_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Error state */}
      {fetchError && metrics.length === 0 && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4" role="alert">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
            <p className="text-sm font-medium text-red-800">
              Failed to load resource metrics
            </p>
          </div>
          <p className="mt-1 text-sm text-red-700">{fetchError}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => activeService && fetchResourceMetrics(activeService)}
          >
            Retry
          </Button>
        </div>
      )}

      {/* Empty state */}
      {!fetchError && metrics.length === 0 && !isLoading && (
        <div className="rounded-md border border-border p-6 text-center">
          <BarChart3 className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="mt-2 text-sm text-muted-foreground">
            No resource metrics available for this service yet.
          </p>
        </div>
      )}

      {/* Charts */}
      {metrics.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* CPU Chart */}
          <div className="rounded-md border border-border p-4">
            <div className="flex items-center gap-2 mb-3">
              <Cpu className="h-4 w-4 text-blue-600" aria-hidden="true" />
              <span className="text-sm font-medium text-foreground">CPU Usage</span>
              <span className="ml-auto text-xs text-muted-foreground">
                Current: {getLatestValue(metrics, "cpu_percent").toFixed(1)}%
              </span>
            </div>
            <SparklineChart
              data={metrics.map((m) => m.cpu_percent)}
              timestamps={metrics.map((m) => m.recorded_at)}
              maxValue={100}
              unit="%"
              color="rgb(37, 99, 235)"
              fillColor="rgba(37, 99, 235, 0.1)"
              label="CPU usage over time"
            />
          </div>

          {/* Memory Chart */}
          <div className="rounded-md border border-border p-4">
            <div className="flex items-center gap-2 mb-3">
              <MemoryStick className="h-4 w-4 text-purple-600" aria-hidden="true" />
              <span className="text-sm font-medium text-foreground">Memory Usage</span>
              <span className="ml-auto text-xs text-muted-foreground">
                Current: {getLatestValue(metrics, "memory_used_mb").toFixed(0)} MB
                {serviceInfo?.memory_limit_mb && (
                  <span> / {serviceInfo.memory_limit_mb.toFixed(0)} MB</span>
                )}
              </span>
              {/* Memory warning */}
              {serviceInfo && isMemoryWarning(serviceInfo.memory_used_mb, serviceInfo.memory_limit_mb) && (
                <span
                  className="inline-flex items-center gap-0.5 text-amber-600"
                  aria-label="Memory usage exceeds 90% of limit"
                  title="Memory usage exceeds 90% of container limit"
                >
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                </span>
              )}
            </div>
            <SparklineChart
              data={metrics.map((m) => m.memory_used_mb)}
              timestamps={metrics.map((m) => m.recorded_at)}
              maxValue={getMemoryChartMax(metrics, serviceInfo)}
              unit=" MB"
              color="rgb(147, 51, 234)"
              fillColor="rgba(147, 51, 234, 0.1)"
              label="Memory usage over time"
              limitLine={serviceInfo?.memory_limit_mb ?? undefined}
            />
            {/* Memory limit reference line label */}
            {serviceInfo?.memory_limit_mb && (
              <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                <span className="inline-block h-0.5 w-4 bg-red-400" aria-hidden="true" />
                <span>Container limit ({serviceInfo.memory_limit_mb.toFixed(0)} MB)</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SparklineChart — simple SVG-based time-series chart
// ---------------------------------------------------------------------------

interface SparklineChartProps {
  data: number[];
  timestamps: string[];
  maxValue: number;
  unit: string;
  color: string;
  fillColor: string;
  label: string;
  limitLine?: number;
}

function SparklineChart({
  data,
  timestamps,
  maxValue,
  unit,
  color,
  fillColor,
  label,
  limitLine,
}: SparklineChartProps) {
  if (data.length === 0) return null;

  const width = 400;
  const height = 120;
  const padding = { top: 10, right: 10, bottom: 24, left: 40 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const effectiveMax = Math.max(maxValue, ...data) * 1.05;

  // Build path points
  const points = data.map((value, i) => {
    const x = padding.left + (i / Math.max(data.length - 1, 1)) * chartWidth;
    const y = padding.top + chartHeight - (value / effectiveMax) * chartHeight;
    return { x, y };
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");

  // Fill area path (closed polygon)
  const areaPath =
    linePath +
    ` L ${points[points.length - 1].x} ${padding.top + chartHeight}` +
    ` L ${points[0].x} ${padding.top + chartHeight} Z`;

  // Y-axis labels
  const yLabels = [0, effectiveMax * 0.5, effectiveMax].map((v) => ({
    value: v,
    y: padding.top + chartHeight - (v / effectiveMax) * chartHeight,
  }));

  // X-axis labels (first and last timestamp)
  const firstTime = timestamps[0] ? formatTime(timestamps[0]) : "";
  const lastTime = timestamps[timestamps.length - 1]
    ? formatTime(timestamps[timestamps.length - 1])
    : "";

  // Limit line position
  const limitY =
    limitLine !== undefined
      ? padding.top + chartHeight - (limitLine / effectiveMax) * chartHeight
      : null;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto"
      role="img"
      aria-label={label}
    >
      {/* Grid lines */}
      {yLabels.map((yl, i) => (
        <line
          key={i}
          x1={padding.left}
          y1={yl.y}
          x2={width - padding.right}
          y2={yl.y}
          stroke="currentColor"
          strokeOpacity={0.1}
          strokeDasharray="2 2"
        />
      ))}

      {/* Y-axis labels */}
      {yLabels.map((yl, i) => (
        <text
          key={i}
          x={padding.left - 4}
          y={yl.y + 3}
          textAnchor="end"
          className="fill-muted-foreground"
          fontSize={9}
        >
          {yl.value.toFixed(0)}{unit}
        </text>
      ))}

      {/* X-axis labels */}
      <text
        x={padding.left}
        y={height - 4}
        textAnchor="start"
        className="fill-muted-foreground"
        fontSize={9}
      >
        {firstTime}
      </text>
      <text
        x={width - padding.right}
        y={height - 4}
        textAnchor="end"
        className="fill-muted-foreground"
        fontSize={9}
      >
        {lastTime}
      </text>

      {/* Limit line */}
      {limitY !== null && (
        <line
          x1={padding.left}
          y1={limitY}
          x2={width - padding.right}
          y2={limitY}
          stroke="rgb(248, 113, 113)"
          strokeWidth={1}
          strokeDasharray="4 2"
        />
      )}

      {/* Area fill */}
      <path d={areaPath} fill={fillColor} />

      {/* Line */}
      <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getLatestValue(metrics: ResourceMetrics[], key: keyof ResourceMetrics): number {
  if (metrics.length === 0) return 0;
  const value = metrics[metrics.length - 1][key];
  return typeof value === "number" ? value : 0;
}

function getMemoryChartMax(metrics: ResourceMetrics[], serviceInfo?: ServiceInfo): number {
  const maxUsed = Math.max(...metrics.map((m) => m.memory_used_mb), 0);
  const limit = serviceInfo?.memory_limit_mb ?? null;
  if (limit !== null && limit > 0) {
    return Math.max(maxUsed, limit);
  }
  return maxUsed > 0 ? maxUsed : 512;
}

/**
 * Returns true when memory usage exceeds 90% of the container limit.
 * Property 14: Memory Utilization Warning Threshold.
 */
function isMemoryWarning(usedMb: number, limitMb: number | null): boolean {
  if (limitMb === null || limitMb <= 0) return false;
  return usedMb / limitMb > 0.9;
}

/**
 * Format ISO timestamp to short time string (HH:MM).
 */
function formatTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
