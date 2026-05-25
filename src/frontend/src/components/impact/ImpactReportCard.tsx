/**
 * ImpactReportCard
 *
 * Summary card for a single impact analysis report showing status,
 * severity counts, timestamp, and triggering document UUID.
 *
 * Requirements: 10.1
 */

import {
  AlertTriangle,
  CheckCircle2,
  AlertCircle,
  Clock,
  FileText,
} from "lucide-react";
import type { ImpactReport } from "@/types/impactAnalysis";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStatusConfig(status: string) {
  switch (status) {
    case "completed":
      return {
        label: "Completed",
        className: "bg-green-100 text-green-800",
        icon: CheckCircle2,
      };
    case "partial_success":
      return {
        label: "Partial",
        className: "bg-yellow-100 text-yellow-800",
        icon: AlertCircle,
      };
    case "failed":
      return {
        label: "Failed",
        className: "bg-red-100 text-red-800",
        icon: AlertTriangle,
      };
    default:
      return {
        label: status,
        className: "bg-gray-100 text-gray-700",
        icon: AlertCircle,
      };
  }
}

function formatTimestamp(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function countSeverities(report: ImpactReport) {
  let critical = 0;
  let major = 0;
  let minor = 0;

  for (const item of report.affected_items) {
    switch (item.impact_severity) {
      case "critical":
        critical++;
        break;
      case "major":
        major++;
        break;
      case "minor":
        minor++;
        break;
    }
  }

  return { critical, major, minor };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ImpactReportCardProps {
  report: ImpactReport;
  onClick?: () => void;
}

export function ImpactReportCard({ report, onClick }: ImpactReportCardProps) {
  const statusConfig = getStatusConfig(report.status);
  const StatusIcon = statusConfig.icon;
  const severities = countSeverities(report);

  return (
    <div
      className="border border-border rounded-lg p-4 hover:bg-muted/30 transition-colors cursor-pointer"
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" && onClick) onClick();
      }}
      role="button"
      tabIndex={0}
      aria-label={`Impact report for document ${report.triggering_document_uuid}, status: ${statusConfig.label}`}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Left: status + document info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${statusConfig.className}`}
            >
              <StatusIcon className="h-3 w-3" aria-hidden="true" />
              {statusConfig.label}
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-sm text-muted-foreground mt-1">
            <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate font-mono text-xs">
              {report.triggering_document_uuid}
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-1">
            <Clock className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>{formatTimestamp(report.analysis_timestamp)}</span>
          </div>
        </div>

        {/* Right: severity counts */}
        <div className="flex items-center gap-2 text-xs shrink-0">
          {severities.critical > 0 && (
            <span
              className="flex items-center gap-0.5 text-red-600 font-medium"
              title="Critical findings"
            >
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              {severities.critical}
            </span>
          )}
          {severities.major > 0 && (
            <span
              className="flex items-center gap-0.5 text-orange-600 font-medium"
              title="Major findings"
            >
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              {severities.major}
            </span>
          )}
          {severities.minor > 0 && (
            <span
              className="flex items-center gap-0.5 text-yellow-600 font-medium"
              title="Minor findings"
            >
              <AlertCircle className="h-3 w-3" aria-hidden="true" />
              {severities.minor}
            </span>
          )}
          {severities.critical === 0 &&
            severities.major === 0 &&
            severities.minor === 0 && (
              <span className="text-muted-foreground">No findings</span>
            )}
        </div>
      </div>
    </div>
  );
}
