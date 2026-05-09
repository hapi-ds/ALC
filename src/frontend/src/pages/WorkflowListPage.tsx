import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  GitBranch,
  Loader2,
  AlertCircle,
  RefreshCw,
  Filter,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWorkflowStore } from "@/stores/workflowStore";
import type { RiskLevel, WorkflowResponse } from "@/stores/workflowStore";

const RISK_LEVEL_BADGE_CLASSES: Record<RiskLevel, string> = {
  low: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

export function WorkflowListPage() {
  const {
    workflows,
    isLoadingList,
    listError,
    fetchWorkflowList,
  } = useWorkflowStore();
  const navigate = useNavigate();

  const [showLoading, setShowLoading] = useState(false);
  const [riskFilter, setRiskFilter] = useState<RiskLevel | "all">("all");

  useEffect(() => {
    fetchWorkflowList();
  }, [fetchWorkflowList]);

  // 200ms delay before showing loading indicator to avoid flash for fast responses
  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    if (isLoadingList) {
      timeoutId = setTimeout(() => {
        setShowLoading(true);
      }, 200);
    } else {
      setShowLoading(false);
    }

    return () => {
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    };
  }, [isLoadingList]);

  // Filter by risk level, then sort by name ascending
  const filteredAndSortedWorkflows = [...workflows]
    .filter((w) => riskFilter === "all" || w.risk_level === riskFilter)
    .sort((a, b) => a.name.localeCompare(b.name));

  const handleRowClick = (workflow: WorkflowResponse) => {
    navigate(`/workflows/${workflow.id}/edit`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Workflows</h2>
          <p className="text-sm text-muted-foreground">
            Manage document lifecycle workflow definitions
          </p>
        </div>
        <Button onClick={() => navigate("/workflows/new")}>
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          New Workflow
        </Button>
      </div>

      {/* Risk level filter */}
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <label htmlFor="risk-filter" className="text-sm text-muted-foreground">
          Risk Level:
        </label>
        <select
          id="risk-filter"
          value={riskFilter}
          onChange={(e) => setRiskFilter(e.target.value as RiskLevel | "all")}
          className="border border-border rounded-md px-2 py-1 text-sm bg-background"
        >
          <option value="all">All</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
      </div>

      {/* Error state with retry */}
      {listError && (
        <div
          role="alert"
          className="flex items-center justify-between p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <p>{listError}</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchWorkflowList()}
          >
            <RefreshCw className="h-3 w-3 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      )}

      {/* Loading indicator (shown after 200ms delay) */}
      {showLoading && (
        <div
          className="flex items-center justify-center py-8"
          aria-label="Loading workflows"
        >
          <Loader2
            className="h-6 w-6 animate-spin text-muted-foreground"
            aria-hidden="true"
          />
          <span className="sr-only">Loading workflows</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoadingList && !listError && workflows.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <GitBranch
            className="h-12 w-12 mx-auto mb-4 opacity-50"
            aria-hidden="true"
          />
          <p className="text-lg font-medium">No workflows yet</p>
          <p className="text-sm mt-1">
            Create your first workflow to define document lifecycle states and
            transitions.
          </p>
          <Button className="mt-4" onClick={() => navigate("/workflows/new")}>
            <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
            New Workflow
          </Button>
        </div>
      )}

      {/* Empty filter result */}
      {!isLoadingList &&
        !listError &&
        workflows.length > 0 &&
        filteredAndSortedWorkflows.length === 0 && (
          <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
            <Filter
              className="h-12 w-12 mx-auto mb-4 opacity-50"
              aria-hidden="true"
            />
            <p className="text-lg font-medium">No matching workflows</p>
            <p className="text-sm mt-1">
              No workflows match the selected risk level filter.
            </p>
          </div>
        )}

      {/* Workflow table */}
      {!isLoadingList &&
        !listError &&
        filteredAndSortedWorkflows.length > 0 && (
          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left p-3 font-medium">Name</th>
                  <th className="text-left p-3 font-medium">Document Tag</th>
                  <th className="text-left p-3 font-medium">Risk Level</th>
                  <th className="text-left p-3 font-medium">Status</th>
                  <th className="text-left p-3 font-medium">Version</th>
                </tr>
              </thead>
              <tbody>
                {filteredAndSortedWorkflows.map((workflow) => (
                  <tr
                    key={workflow.id}
                    className="border-b border-border last:border-b-0 hover:bg-accent/50 cursor-pointer"
                    onClick={() => handleRowClick(workflow)}
                    role="link"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleRowClick(workflow);
                      }
                    }}
                  >
                    <td className="p-3 font-medium">{workflow.name}</td>
                    <td className="p-3 font-mono text-xs">
                      {workflow.document_tag}
                    </td>
                    <td className="p-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          RISK_LEVEL_BADGE_CLASSES[
                            workflow.risk_level as RiskLevel
                          ] || RISK_LEVEL_BADGE_CLASSES.low
                        }`}
                      >
                        {workflow.risk_level}
                      </span>
                    </td>
                    <td className="p-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          workflow.is_active
                            ? "bg-green-100 text-green-800"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {workflow.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-primary/10 text-primary">
                        v{workflow.current_version_number}
                      </span>
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
