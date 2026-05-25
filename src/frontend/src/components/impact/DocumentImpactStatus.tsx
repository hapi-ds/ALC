/**
 * DocumentImpactStatus
 *
 * Inline widget displaying a document's impact analysis status:
 * last_analysis_date, outstanding critical/major counts, and is_up_to_date badge.
 *
 * Requirements: 10.6, 10.10
 */

import { useEffect } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  Clock,
  Loader2,
} from "lucide-react";
import { useImpactAnalysisStore } from "@/stores/impactAnalysisStore";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(isoDate: string | null): string {
  if (!isoDate) return "Never analyzed";
  const date = new Date(isoDate);
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface DocumentImpactStatusProps {
  documentUuid: string;
}

export function DocumentImpactStatus({
  documentUuid,
}: DocumentImpactStatusProps) {
  const { documentStatus, fetchDocumentStatus, isLoading } =
    useImpactAnalysisStore();

  useEffect(() => {
    fetchDocumentStatus(documentUuid);
  }, [documentUuid, fetchDocumentStatus]);

  const status = documentStatus[documentUuid];

  if (isLoading && !status) {
    return (
      <div
        className="flex items-center gap-1.5 text-xs text-muted-foreground"
        role="status"
        aria-label="Loading impact status"
      >
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
        <span>Loading status…</span>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Clock className="h-3 w-3" aria-hidden="true" />
        <span>No impact data available</span>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-3 text-xs"
      aria-label="Document impact status"
    >
      {/* Up-to-date badge */}
      {status.is_up_to_date ? (
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 bg-green-100 text-green-800 font-medium">
          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
          Up to date
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 bg-red-100 text-red-800 font-medium">
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          Needs review
        </span>
      )}

      {/* Outstanding counts */}
      {(status.outstanding_critical_count > 0 ||
        status.outstanding_major_count > 0) && (
        <span className="text-muted-foreground">
          {status.outstanding_critical_count > 0 && (
            <span className="text-red-600 font-medium mr-1.5">
              {status.outstanding_critical_count} critical
            </span>
          )}
          {status.outstanding_major_count > 0 && (
            <span className="text-orange-600 font-medium">
              {status.outstanding_major_count} major
            </span>
          )}
        </span>
      )}

      {/* Last analysis date */}
      <span className="text-muted-foreground">
        {formatDate(status.last_analysis_date)}
      </span>
    </div>
  );
}
