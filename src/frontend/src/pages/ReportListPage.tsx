import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, FileText, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReportStore } from "@/stores/reportStore";

/**
 * Report list page displaying all reports for the current tenant.
 * Fetches reports via the report store (GET /api/reports), displays
 * in a table sorted by upload timestamp descending.
 */
export function ReportListPage() {
  const navigate = useNavigate();
  const { reports, isLoadingList, listError, fetchReportList } =
    useReportStore();

  useEffect(() => {
    fetchReportList();
  }, [fetchReportList]);

  function formatRelativeTime(isoDate: string | null): string {
    if (!isoDate) return "—";
    const date = new Date(isoDate);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins} min ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? "s" : ""} ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} day${diffDays > 1 ? "s" : ""} ago`;
  }

  function getStatusBadgeClass(status: string): string {
    switch (status) {
      case "Extracted":
        return "bg-blue-100 text-blue-700";
      case "Validated":
        return "bg-green-100 text-green-700";
      case "Draft":
        return "bg-gray-100 text-gray-700";
      default:
        return "bg-gray-100 text-gray-700";
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Reports</h2>
        <Button onClick={() => navigate("/reports/new")}>
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          New Report
        </Button>
      </div>

      {listError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{listError}</p>
          <Button variant="outline" size="sm" onClick={fetchReportList}>
            <RefreshCw className="h-3 w-3 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      )}

      {isLoadingList && (
        <div className="flex items-center justify-center py-8" role="status">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">Loading reports</span>
        </div>
      )}

      {!isLoadingList && !listError && reports.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
          <p className="text-lg font-medium">No reports yet</p>
          <p className="text-sm mt-1">Create your first report to get started</p>
          <Button className="mt-4" onClick={() => navigate("/reports/new")}>
            <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
            New Report
          </Button>
        </div>
      )}

      {!isLoadingList && reports.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">ID</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Document UUID</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Uploaded</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {reports.map((report) => (
                <tr
                  key={report.id}
                  onClick={() => navigate(`/reports/${report.id}`)}
                  className="cursor-pointer hover:bg-muted/30 transition-colors"
                  role="link"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") navigate(`/reports/${report.id}`);
                  }}
                >
                  <td className="px-4 py-3 font-mono text-xs">{report.id}</td>
                  <td className="px-4 py-3 font-mono text-xs">{report.document_uuid}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${getStatusBadgeClass(report.status)}`}
                    >
                      {report.status}
                    </span>
                  </td>
                  <td
                    className="px-4 py-3 text-muted-foreground"
                    title={report.uploaded_at ?? undefined}
                  >
                    {formatRelativeTime(report.uploaded_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
