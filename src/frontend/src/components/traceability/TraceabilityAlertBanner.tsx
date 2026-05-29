/**
 * TraceabilityAlertBanner
 *
 * Banner showing unresolved critical/major alerts with count and link to
 * the alerts section. Displays severity badges and a summary message.
 *
 * Fetches from the traceability store's alerts state.
 *
 * Requirements: 9.2
 */

import { AlertTriangle, ArrowRight } from "lucide-react";
import { useTraceabilityStore } from "@/stores/traceabilityStore";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TraceabilityAlertBanner() {
  const { alerts } = useTraceabilityStore();

  // Filter to unresolved critical and major alerts
  const unresolvedAlerts = alerts.filter(
    (a) => !a.is_resolved && (a.alert_severity === "critical" || a.alert_severity === "major"),
  );

  if (unresolvedAlerts.length === 0) {
    return null;
  }

  const criticalCount = unresolvedAlerts.filter((a) => a.alert_severity === "critical").length;
  const majorCount = unresolvedAlerts.filter((a) => a.alert_severity === "major").length;

  return (
    <div
      role="alert"
      className="flex items-center gap-3 p-3 border border-amber-200 bg-amber-50 rounded-lg"
    >
      <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" aria-hidden="true" />
      <div className="flex-1 flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium text-amber-900">
          {unresolvedAlerts.length} unresolved traceability{" "}
          {unresolvedAlerts.length === 1 ? "alert" : "alerts"}
        </span>
        {criticalCount > 0 && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-800 font-medium border border-red-200">
            {criticalCount} critical
          </span>
        )}
        {majorCount > 0 && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-800 font-medium border border-orange-200">
            {majorCount} major
          </span>
        )}
        <span className="text-xs text-amber-700">
          — Requirements may have changed since last matrix generation
        </span>
      </div>
      <a
        href="#alerts"
        className="flex items-center gap-1 text-xs font-medium text-amber-700 hover:text-amber-900 transition-colors whitespace-nowrap"
        aria-label="View traceability alerts"
      >
        View alerts
        <ArrowRight className="h-3 w-3" aria-hidden="true" />
      </a>
    </div>
  );
}
