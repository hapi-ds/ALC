/**
 * TraceabilityPage
 *
 * Main dashboard for AI-Powered Traceability & Gap Discovery. Displays:
 * - Summary cards: overall coverage %, compliance readiness score, orphan counts
 * - Paginated matrix list (20 per page, newest first) with status badges
 * - "Generate Matrix" button
 * - Coverage trend chart component
 * - Loading skeletons and empty states with descriptive messages
 * - Inline error messages with "Retry" button on API failures
 *
 * Requirements: 8.1, 8.10, 8.11
 */

import { useEffect, useState, useCallback } from "react";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  FileSearch,
  Loader2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Target,
  AlertTriangle,
  FlaskConical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTraceabilityStore } from "@/stores/traceabilityStore";
import { CoverageTrendChart } from "@/components/traceability/CoverageTrendChart";
import { TraceabilityAlertBanner } from "@/components/traceability/TraceabilityAlertBanner";
import { GenerateMatrixDialog } from "@/components/traceability/GenerateMatrixDialog";
import type { TraceabilityMatrix } from "@/types/traceability";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TraceabilityPage() {
  const {
    matrices,
    coverageSummary,
    isLoading,
    error,
    fetchMatrices,
    fetchCoverageSummary,
    fetchCoverageHistory,
    fetchAlerts,
  } = useTraceabilityStore();

  const [page, setPage] = useState(0);
  const [showGenerateDialog, setShowGenerateDialog] = useState(false);

  const loadData = useCallback(() => {
    fetchMatrices({ limit: 100 });
    fetchCoverageSummary();
    fetchCoverageHistory();
    fetchAlerts();
  }, [fetchMatrices, fetchCoverageSummary, fetchCoverageHistory, fetchAlerts]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Pagination (client-side, newest first)
  const sortedMatrices = [...matrices].sort(
    (a, b) =>
      new Date(b.generation_timestamp).getTime() -
      new Date(a.generation_timestamp).getTime(),
  );
  const totalPages = Math.max(1, Math.ceil(sortedMatrices.length / PAGE_SIZE));
  const paginatedMatrices = sortedMatrices.slice(
    page * PAGE_SIZE,
    (page + 1) * PAGE_SIZE,
  );
  const canPrev = page > 0;
  const canNext = page < totalPages - 1;

  // Summary values
  const coveragePercent = coverageSummary?.average_coverage_percentage ?? 0;
  const complianceScore = coverageSummary?.average_compliance_readiness_score ?? 0;
  const orphanReqCount = coverageSummary?.total_orphan_requirements ?? 0;
  const orphanTcCount = coverageSummary?.total_orphan_test_cases ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Traceability</h2>
          <p className="text-sm text-muted-foreground">
            AI-powered requirement-to-test traceability and gap discovery
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setShowGenerateDialog(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Generate Matrix
          </Button>
        </div>
      </div>

      {/* Alert banner */}
      <TraceabilityAlertBanner />

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          label="Coverage"
          value={`${coveragePercent.toFixed(1)}%`}
          icon={Target}
          colorClass="text-blue-600"
          bgClass="bg-blue-50"
        />
        <SummaryCard
          label="Compliance Score"
          value={complianceScore.toFixed(0)}
          icon={ShieldCheck}
          colorClass="text-green-600"
          bgClass="bg-green-50"
        />
        <SummaryCard
          label="Orphan Requirements"
          value={String(orphanReqCount)}
          icon={AlertTriangle}
          colorClass="text-orange-600"
          bgClass="bg-orange-50"
        />
        <SummaryCard
          label="Orphan Test Cases"
          value={String(orphanTcCount)}
          icon={FlaskConical}
          colorClass="text-purple-600"
          bgClass="bg-purple-50"
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

      {/* Coverage trend chart */}
      <CoverageTrendChart />

      {/* Loading skeleton */}
      {isLoading && matrices.length === 0 && <LoadingSkeleton />}

      {/* Empty state */}
      {!isLoading && !error && matrices.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FileSearch
            className="h-12 w-12 mx-auto mb-4 opacity-50"
            aria-hidden="true"
          />
          <p className="text-lg font-medium">No traceability matrices yet</p>
          <p className="text-sm mt-1">
            Generate your first traceability matrix to map requirements to test
            cases and discover coverage gaps.
          </p>
          <Button
            className="mt-4"
            size="sm"
            onClick={() => setShowGenerateDialog(true)}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            Generate Matrix
          </Button>
        </div>
      )}

      {/* Matrix list */}
      {!isLoading && paginatedMatrices.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">
            Traceability Matrices ({sortedMatrices.length})
          </h3>
          <div className="space-y-2">
            {paginatedMatrices.map((matrix) => (
              <MatrixCard key={matrix.matrix_id} matrix={matrix} />
            ))}
          </div>
        </div>
      )}

      {/* Pagination */}
      {!isLoading && sortedMatrices.length > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {page * PAGE_SIZE + 1}–
            {Math.min((page + 1) * PAGE_SIZE, sortedMatrices.length)} of{" "}
            {sortedMatrices.length} matrices
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

      {/* Generate Matrix Dialog */}
      {showGenerateDialog && (
        <GenerateMatrixDialog onClose={() => setShowGenerateDialog(false)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SummaryCardProps {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  colorClass: string;
  bgClass: string;
}

function SummaryCard({ label, value, icon: Icon, colorClass, bgClass }: SummaryCardProps) {
  return (
    <div className={`border border-border rounded-lg p-4 ${bgClass}`}>
      <div className="flex items-center gap-3">
        <Icon className={`h-5 w-5 ${colorClass}`} aria-hidden="true" />
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={`text-2xl font-bold ${colorClass}`}>{value}</p>
        </div>
      </div>
    </div>
  );
}

function MatrixCard({ matrix }: { matrix: TraceabilityMatrix }) {
  const statusColors: Record<string, string> = {
    completed: "bg-green-100 text-green-800",
    partial_success: "bg-yellow-100 text-yellow-800",
    failed: "bg-red-100 text-red-800",
  };

  const coverage = matrix.coverage_metrics?.coverage_percentage ?? 0;
  const date = new Date(matrix.generation_timestamp).toLocaleDateString();

  return (
    <div className="border border-border rounded-lg p-4 hover:bg-accent/50 transition-colors">
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-medium truncate">{matrix.matrix_name}</p>
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColors[matrix.status] || "bg-gray-100 text-gray-800"}`}
            >
              {matrix.status.replace("_", " ")}
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {matrix.source_document_uuids.length} source docs →{" "}
            {matrix.target_document_uuids.length} target docs · {date}
          </p>
        </div>
        <div className="text-right ml-4">
          <p className="text-sm font-medium">{coverage.toFixed(1)}%</p>
          <p className="text-xs text-muted-foreground">coverage</p>
        </div>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading traceability data">
      <Loader2
        className="h-5 w-5 animate-spin text-muted-foreground mx-auto"
        aria-hidden="true"
      />
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="border border-border rounded-lg p-4 animate-pulse"
          >
            <div className="flex items-center gap-3">
              <div className="h-5 w-16 bg-muted rounded" />
              <div className="flex-1">
                <div className="h-3 w-48 bg-muted rounded mb-2" />
                <div className="h-3 w-32 bg-muted rounded" />
              </div>
              <div className="h-4 w-12 bg-muted rounded" />
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">Loading traceability data</span>
    </div>
  );
}
