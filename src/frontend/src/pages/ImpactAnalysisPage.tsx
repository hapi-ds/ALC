/**
 * ImpactAnalysisPage
 *
 * Main dashboard for AI-Driven Change Impact Analysis. Displays:
 * - Summary card with total unresolved critical/major findings
 * - Paginated report list (20 per page, newest first)
 * - Notification badge with unacknowledged count
 * - Loading skeletons and empty states with descriptive messages
 * - Inline error messages with "Retry" button on API failures
 *
 * Requirements: 10.1, 10.8, 10.9
 */

import { useEffect, useState, useCallback } from "react";
import {
  AlertTriangle,
  Bell,
  Loader2,
  AlertCircle,
  RefreshCw,
  Activity,
  ChevronLeft,
  ChevronRight,
  FileSearch,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useImpactAnalysisStore } from "@/stores/impactAnalysisStore";
import { ImpactReportCard } from "@/components/impact/ImpactReportCard";
import { NotificationPanel } from "@/components/impact/NotificationPanel";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ImpactAnalysisPage() {
  const {
    reports,
    notifications,
    isLoading,
    error,
    fetchReports,
    fetchNotifications,
  } = useImpactAnalysisStore();

  const [page, setPage] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);

  // Fetch data on mount and page change
  const loadData = useCallback(() => {
    fetchReports();
    fetchNotifications();
  }, [fetchReports, fetchNotifications]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Compute summary stats from reports
  const summaryStats = computeSummaryStats();

  function computeSummaryStats() {
    let totalCritical = 0;
    let totalMajor = 0;

    for (const report of reports) {
      if (report.status === "failed") continue;
      for (const item of report.affected_items) {
        if (item.impact_severity === "critical") totalCritical++;
        if (item.impact_severity === "major") totalMajor++;
      }
    }

    return { totalCritical, totalMajor };
  }

  // Pagination (client-side since store fetches all)
  const sortedReports = [...reports].sort(
    (a, b) =>
      new Date(b.analysis_timestamp).getTime() -
      new Date(a.analysis_timestamp).getTime(),
  );
  const totalPages = Math.max(1, Math.ceil(sortedReports.length / PAGE_SIZE));
  const paginatedReports = sortedReports.slice(
    page * PAGE_SIZE,
    (page + 1) * PAGE_SIZE,
  );
  const canPrev = page > 0;
  const canNext = page < totalPages - 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Impact Analysis</h2>
          <p className="text-sm text-muted-foreground">
            AI-driven change impact analysis and dependency tracking
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Notification badge */}
          <Button
            variant={showNotifications ? "default" : "outline"}
            size="sm"
            onClick={() => setShowNotifications(!showNotifications)}
            aria-label={`Notifications (${notifications.length} unacknowledged)`}
            className="relative"
          >
            <Bell className="h-4 w-4" aria-hidden="true" />
            Notifications
            {notifications.length > 0 && (
              <span className="absolute -top-1 -right-1 h-4 min-w-4 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold px-1">
                {notifications.length}
              </span>
            )}
          </Button>
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Summary card */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard
          label="Critical Findings"
          count={summaryStats.totalCritical}
          icon={AlertTriangle}
          colorClass="text-red-600"
          bgClass="bg-red-50"
        />
        <SummaryCard
          label="Major Findings"
          count={summaryStats.totalMajor}
          icon={AlertTriangle}
          colorClass="text-orange-600"
          bgClass="bg-orange-50"
        />
        <SummaryCard
          label="Total Reports"
          count={reports.length}
          icon={Activity}
          colorClass="text-blue-600"
          bgClass="bg-blue-50"
        />
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{error}</p>
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="h-3 w-3 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      )}

      {/* Notification panel (collapsible) */}
      {showNotifications && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">
            Unacknowledged Notifications ({notifications.length})
          </h3>
          <NotificationPanel notifications={notifications} />
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && reports.length === 0 && (
        <LoadingSkeleton />
      )}

      {/* Empty state */}
      {!isLoading && !error && reports.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FileSearch
            className="h-12 w-12 mx-auto mb-4 opacity-50"
            aria-hidden="true"
          />
          <p className="text-lg font-medium">No impact reports yet</p>
          <p className="text-sm mt-1">
            Impact reports are generated automatically when documents are updated,
            or you can trigger an analysis manually from a document&apos;s detail page.
          </p>
        </div>
      )}

      {/* Report list */}
      {!isLoading && paginatedReports.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">
            Impact Reports ({sortedReports.length})
          </h3>
          <div className="space-y-2">
            {paginatedReports.map((report) => (
              <ImpactReportCard key={report.report_id} report={report} />
            ))}
          </div>
        </div>
      )}

      {/* Pagination */}
      {!isLoading && sortedReports.length > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {page * PAGE_SIZE + 1}–
            {Math.min((page + 1) * PAGE_SIZE, sortedReports.length)} of{" "}
            {sortedReports.length} reports
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!canPrev}
              onClick={() => setPage((p) => p - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page + 1} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={!canNext}
              onClick={() => setPage((p) => p + 1)}
              aria-label="Next page"
            >
              Next
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SummaryCardProps {
  label: string;
  count: number;
  icon: React.ComponentType<{ className?: string }>;
  colorClass: string;
  bgClass: string;
}

function SummaryCard({
  label,
  count,
  icon: Icon,
  colorClass,
  bgClass,
}: SummaryCardProps) {
  return (
    <div className={`border border-border rounded-lg p-4 ${bgClass}`}>
      <div className="flex items-center gap-3">
        <Icon className={`h-5 w-5 ${colorClass}`} aria-hidden="true" />
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={`text-2xl font-bold ${colorClass}`}>{count}</p>
        </div>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading impact analysis data">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mx-auto" aria-hidden="true" />
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="border border-border rounded-lg p-4 animate-pulse"
          >
            <div className="flex items-center gap-3">
              <div className="h-5 w-16 bg-muted rounded" />
              <div className="flex-1">
                <div className="h-3 w-32 bg-muted rounded mb-2" />
                <div className="h-3 w-24 bg-muted rounded" />
              </div>
              <div className="h-4 w-12 bg-muted rounded" />
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">Loading impact analysis data</span>
    </div>
  );
}
