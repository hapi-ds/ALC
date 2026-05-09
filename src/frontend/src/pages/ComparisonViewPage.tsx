import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Loader2, AlertCircle, RefreshCw, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReportStore } from "@/stores/reportStore";
import { ComparisonRow } from "@/components/reports/ComparisonRow";
import { ComparisonSummary } from "@/components/reports/ComparisonSummary";

/**
 * Comparison view page displaying extracted vs. entered field values.
 * Fetches comparison data via the report store (GET /api/reports/{report_id}/compare).
 */
export function ComparisonViewPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const navigate = useNavigate();
  const {
    comparisonData,
    isLoadingComparison,
    comparisonError,
    fetchComparisonData,
  } = useReportStore();

  useEffect(() => {
    if (reportId) {
      fetchComparisonData(Number(reportId));
    }
  }, [reportId, fetchComparisonData]);

  if (isLoadingComparison) {
    return (
      <div className="flex items-center justify-center py-12" role="status">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading comparison</span>
      </div>
    );
  }

  if (comparisonError) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4 mr-1" aria-hidden="true" />
          Back
        </Button>
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{comparisonError}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => reportId && fetchComparisonData(Number(reportId))}
          >
            <RefreshCw className="h-3 w-3 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  if (!comparisonData) {
    return null;
  }

  if (comparisonData.compared_with_report_id === null) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4 mr-1" aria-hidden="true" />
          Back
        </Button>
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <p className="text-lg font-medium">Comparison not available</p>
          <p className="text-sm mt-1">
            Comparison requires both an extracted report and a manually entered
            report for the same template.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <div>
          <h2 className="text-2xl font-bold">Data Comparison</h2>
          <p className="text-sm text-muted-foreground">
            Report #{comparisonData.report_id} vs Report #
            {comparisonData.compared_with_report_id}
          </p>
        </div>
      </div>

      <ComparisonSummary
        totalFields={comparisonData.total_fields}
        matches={comparisonData.matches}
        discrepancies={comparisonData.discrepancies}
      />

      <div className="grid grid-cols-[1fr_2fr_2fr_auto] items-center gap-3 px-4 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        <span>Field</span>
        <span>Extracted (PDF)</span>
        <span>Manual Entry</span>
        <span>Status</span>
      </div>

      <div className="space-y-1" role="table" aria-label="Field comparison">
        {comparisonData.rows.map((row) => (
          <ComparisonRow key={row.field_uuid} row={row} />
        ))}
      </div>
    </div>
  );
}
