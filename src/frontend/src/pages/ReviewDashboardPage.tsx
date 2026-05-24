/**
 * ReviewDashboardPage
 *
 * Displays a filterable list of multi-agent review sessions for the current
 * company. Each row shows document title, type, status (color-coded badge),
 * compliance score, findings by severity, submitted date, and actions.
 *
 * Filters: status, date range, document type, score range, audit profile.
 * Clicking a row navigates to the session detail view.
 *
 * Requirements: 11.1, 5.1, 5.5
 */

import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ClipboardCheck,
  Loader2,
  AlertCircle,
  RefreshCw,
  AlertTriangle,
  Info,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReviewStore } from "@/stores/reviewStore";
import { listAuditProfiles } from "@/lib/reviews-api";
import type { AuditProfile, ReviewListParams, ReviewSession } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

const STATUS_OPTIONS = [
  "Pending",
  "InProgress",
  "Completed",
  "Failed",
  "Approved",
  "Rejected",
] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case "Pending":
      return "bg-yellow-100 text-yellow-800";
    case "InProgress":
      return "bg-blue-100 text-blue-800";
    case "Completed":
      return "bg-green-100 text-green-800";
    case "Failed":
      return "bg-red-100 text-red-800";
    case "Approved":
      return "bg-emerald-100 text-emerald-800";
    case "Rejected":
      return "bg-rose-100 text-rose-800";
    default:
      return "bg-gray-100 text-gray-700";
  }
}

function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function countFindingsBySeverity(session: ReviewSession): Record<string, number> {
  const counts: Record<string, number> = {
    Critical: 0,
    Major: 0,
    Minor: 0,
    Informational: 0,
  };

  if (!session.agent_reviews) return counts;

  for (const review of session.agent_reviews) {
    if (review.status !== "Completed" || !review.report_data) continue;
    const findings = (review.report_data as { findings?: Array<{ severity?: string }> }).findings;
    if (!Array.isArray(findings)) continue;
    for (const finding of findings) {
      const severity = finding.severity;
      if (severity && severity in counts) {
        counts[severity]++;
      }
    }
  }

  return counts;
}

// ---------------------------------------------------------------------------
// Filter State
// ---------------------------------------------------------------------------

interface FilterState {
  status: string;
  dateFrom: string;
  dateTo: string;
  documentType: string;
  minScore: string;
  maxScore: string;
  auditProfileId: string;
}

const INITIAL_FILTERS: FilterState = {
  status: "",
  dateFrom: "",
  dateTo: "",
  documentType: "",
  minScore: "",
  maxScore: "",
  auditProfileId: "",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ReviewDashboardPage() {
  const navigate = useNavigate();
  const {
    sessions,
    sessionsTotal,
    isLoadingSessions,
    sessionsError,
    fetchSessions,
  } = useReviewStore();

  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [page, setPage] = useState(0);
  const [auditProfiles, setAuditProfiles] = useState<AuditProfile[]>([]);

  // Fetch audit profiles for the filter dropdown
  useEffect(() => {
    listAuditProfiles()
      .then(setAuditProfiles)
      .catch(() => {
        // Non-blocking: filter dropdown will just be empty
      });
  }, []);

  // Build params and fetch sessions
  const loadSessions = useCallback(
    (currentPage: number, currentFilters: FilterState) => {
      const params: ReviewListParams = {
        limit: PAGE_SIZE,
        offset: currentPage * PAGE_SIZE,
      };
      if (currentFilters.status) params.status = currentFilters.status;
      if (currentFilters.dateFrom) params.date_from = currentFilters.dateFrom;
      if (currentFilters.dateTo) params.date_to = currentFilters.dateTo;
      if (currentFilters.documentType) params.document_type = currentFilters.documentType;
      if (currentFilters.minScore) params.min_score = Number(currentFilters.minScore);
      if (currentFilters.maxScore) params.max_score = Number(currentFilters.maxScore);
      fetchSessions(params);
    },
    [fetchSessions],
  );

  // Initial load and reload on filter/page change
  useEffect(() => {
    loadSessions(page, filters);
  }, [page, filters, loadSessions]);

  // Filter change handler — resets to page 0
  function handleFilterChange(key: keyof FilterState, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(0);
  }

  // Pagination
  const totalPages = Math.max(1, Math.ceil(sessionsTotal / PAGE_SIZE));
  const canPrev = page > 0;
  const canNext = page < totalPages - 1;

  // Row click → navigate to session detail
  function handleRowClick(sessionId: number) {
    navigate(`/reviews/${sessionId}`);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Review Dashboard</h2>
          <p className="text-sm text-muted-foreground">
            Multi-agent document review sessions
          </p>
        </div>
        <Button onClick={() => loadSessions(page, filters)}>
          <RefreshCw className="h-4 w-4 mr-2" aria-hidden="true" />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 p-4 border border-border rounded-lg bg-muted/20"
        role="search"
        aria-label="Review session filters"
      >
        {/* Status filter */}
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-status" className="text-xs font-medium text-muted-foreground">
            Status
          </label>
          <select
            id="filter-status"
            value={filters.status}
            onChange={(e) => handleFilterChange("status", e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        {/* Document type filter */}
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-doc-type" className="text-xs font-medium text-muted-foreground">
            Document Type
          </label>
          <input
            id="filter-doc-type"
            type="text"
            placeholder="e.g. SOP, Protocol"
            value={filters.documentType}
            onChange={(e) => handleFilterChange("documentType", e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>

        {/* Date from */}
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-date-from" className="text-xs font-medium text-muted-foreground">
            From Date
          </label>
          <input
            id="filter-date-from"
            type="date"
            value={filters.dateFrom}
            onChange={(e) => handleFilterChange("dateFrom", e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>

        {/* Date to */}
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-date-to" className="text-xs font-medium text-muted-foreground">
            To Date
          </label>
          <input
            id="filter-date-to"
            type="date"
            value={filters.dateTo}
            onChange={(e) => handleFilterChange("dateTo", e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>

        {/* Min score */}
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-min-score" className="text-xs font-medium text-muted-foreground">
            Min Score
          </label>
          <input
            id="filter-min-score"
            type="number"
            min="0"
            max="100"
            step="1"
            placeholder="0"
            value={filters.minScore}
            onChange={(e) => handleFilterChange("minScore", e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>

        {/* Max score */}
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-max-score" className="text-xs font-medium text-muted-foreground">
            Max Score
          </label>
          <input
            id="filter-max-score"
            type="number"
            min="0"
            max="100"
            step="1"
            placeholder="100"
            value={filters.maxScore}
            onChange={(e) => handleFilterChange("maxScore", e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>

        {/* Audit profile filter */}
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-audit-profile" className="text-xs font-medium text-muted-foreground">
            Audit Profile
          </label>
          <select
            id="filter-audit-profile"
            value={filters.auditProfileId}
            onChange={(e) => handleFilterChange("auditProfileId", e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">All profiles</option>
            {auditProfiles.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Error banner */}
      {sessionsError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{sessionsError}</p>
          <Button variant="outline" size="sm" onClick={() => loadSessions(page, filters)}>
            <RefreshCw className="h-3 w-3 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      )}

      {/* Loading */}
      {isLoadingSessions && (
        <div className="flex items-center justify-center py-8" role="status" aria-label="Loading review sessions">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">Loading review sessions</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoadingSessions && !sessionsError && sessions.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <ClipboardCheck className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
          <p className="text-lg font-medium">No review sessions found</p>
          <p className="text-sm mt-1">
            Submit a document for review to see results here
          </p>
        </div>
      )}

      {/* Sessions table */}
      {!isLoadingSessions && sessions.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm" aria-label="Review sessions">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Document</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Type</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Score</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Findings</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Submitted</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sessions.map((session) => {
                const findings = countFindingsBySeverity(session);
                return (
                  <tr
                    key={session.id}
                    onClick={() => handleRowClick(session.id)}
                    className="cursor-pointer hover:bg-muted/30 transition-colors"
                    role="link"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleRowClick(session.id);
                    }}
                    aria-label={`Review session for ${session.document_title}`}
                  >
                    <td className="px-4 py-3 font-medium max-w-[200px] truncate">
                      {session.document_title}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {session.document_type}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${getStatusBadgeClass(session.status)}`}
                      >
                        {session.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {session.compliance_score != null ? (
                        <span className="font-mono text-sm">
                          {session.compliance_score.toFixed(1)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 text-xs">
                        {findings.Critical > 0 && (
                          <span className="flex items-center gap-0.5 text-red-600" title="Critical findings">
                            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                            {findings.Critical}
                          </span>
                        )}
                        {findings.Major > 0 && (
                          <span className="flex items-center gap-0.5 text-orange-600" title="Major findings">
                            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                            {findings.Major}
                          </span>
                        )}
                        {findings.Minor > 0 && (
                          <span className="flex items-center gap-0.5 text-yellow-600" title="Minor findings">
                            <Info className="h-3 w-3" aria-hidden="true" />
                            {findings.Minor}
                          </span>
                        )}
                        {findings.Informational > 0 && (
                          <span className="flex items-center gap-0.5 text-blue-600" title="Informational findings">
                            <Info className="h-3 w-3" aria-hidden="true" />
                            {findings.Informational}
                          </span>
                        )}
                        {findings.Critical === 0 &&
                          findings.Major === 0 &&
                          findings.Minor === 0 &&
                          findings.Informational === 0 && (
                            <span className="text-muted-foreground">—</span>
                          )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDate(session.submitted_at)}
                    </td>
                    <td className="px-4 py-3">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRowClick(session.id);
                        }}
                      >
                        View
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {!isLoadingSessions && sessions.length > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, sessionsTotal)} of{" "}
            {sessionsTotal} sessions
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
