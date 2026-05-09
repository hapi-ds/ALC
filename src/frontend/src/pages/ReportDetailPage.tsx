import { useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Loader2, AlertCircle, RefreshCw, Check, AlertTriangle, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReportStore } from "@/stores/reportStore";

/**
 * Report detail page displaying a single report's field values and metadata.
 * Fetches report via the report store (GET /api/reports/{report_id}).
 */
export function ReportDetailPage() {
  const { reportId } = useParams<{ reportId: string }>();
  const navigate = useNavigate();
  const { currentReport, isLoadingDetail, detailError, fetchReportDetail } =
    useReportStore();

  useEffect(() => {
    if (reportId) {
      fetchReportDetail(Number(reportId));
    }
  }, [reportId, fetchReportDetail]);

  if (isLoadingDetail) {
    return (
      <div className="flex items-center justify-center py-12" role="status">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading report</span>
      </div>
    );
  }

  if (detailError) {
    const is404 = detailError.includes("not found") || detailError.includes("404");
    if (is404) {
      return (
        <div className="text-center py-12">
          <p className="text-lg font-medium text-muted-foreground">Report not found</p>
          <Link to="/reports" className="text-sm text-blue-600 hover:underline mt-2 inline-block">
            ← Back to reports
          </Link>
        </div>
      );
    }

    return (
      <div
        role="alert"
        className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
      >
        <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
        <p className="flex-1">{detailError}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => reportId && fetchReportDetail(Number(reportId))}
        >
          <RefreshCw className="h-3 w-3 mr-1" aria-hidden="true" />
          Retry
        </Button>
      </div>
    );
  }

  if (!currentReport) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate("/reports")}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <div>
          <h2 className="text-2xl font-bold">Report #{currentReport.id}</h2>
          <p className="text-sm text-muted-foreground">
            {currentReport.document_uuid}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 rounded-lg border border-border p-4">
        <div>
          <p className="text-xs text-muted-foreground">Status</p>
          <p className="text-sm font-medium">{currentReport.status}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Template ID</p>
          <p className="text-sm font-medium">{currentReport.template_id}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Uploaded By</p>
          <p className="text-sm font-medium">User {currentReport.uploaded_by}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Uploaded At</p>
          <p className="text-sm font-medium">
            {currentReport.uploaded_at
              ? new Date(currentReport.uploaded_at).toLocaleString()
              : "—"}
          </p>
        </div>
      </div>

      {currentReport.status === "Extracted" && (
        <Button
          variant="outline"
          onClick={() => navigate(`/reports/${currentReport.id}/compare`)}
        >
          Compare with Manual Entry
        </Button>
      )}

      <div className="space-y-2">
        <h3 className="text-lg font-semibold">Field Values</h3>
        {currentReport.field_values.length === 0 ? (
          <p className="text-sm text-muted-foreground">No field values recorded.</p>
        ) : (
          <div className="border border-border rounded-lg divide-y divide-border">
            {currentReport.field_values.map((fv) => (
              <div
                key={fv.field_uuid}
                className="flex items-center justify-between px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-mono text-muted-foreground">
                    {fv.field_uuid}
                  </p>
                  <p className="text-sm text-foreground">
                    {fv.value ?? <span className="italic text-muted-foreground">empty</span>}
                  </p>
                </div>
                <div className="ml-3 shrink-0">
                  {fv.validated === true && (
                    <Check className="h-4 w-4 text-green-600" aria-label="Validated" />
                  )}
                  {fv.validated === false && (
                    <AlertTriangle className="h-4 w-4 text-amber-500" aria-label="Not validated" />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
