/**
 * ReviewSessionDetail Component
 *
 * Displays the full detail view of a review session including:
 * - Progress tracker showing agent completion status with elapsed time
 * - Individual agent reports in expandable cards with findings tables
 * - Master summary in a highlighted section
 * - Approve/Reject buttons with change reason modal
 *
 * References:
 *   - Design doc Section 8: Frontend Components
 *   - Requirements: 11.2, 5.2, 5.6, 5.7
 */

import { useState, useMemo } from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Info,
  Shield,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ReviewSession, AgentReview } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ReviewSessionDetailProps {
  session: ReviewSession;
  isApproving?: boolean;
  approveError?: string | null;
  onApprove: (changeReason: string) => void;
  onReject: (changeReason: string) => void;
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function ReviewSessionDetail({
  session,
  isApproving = false,
  approveError = null,
  onApprove,
  onReject,
}: ReviewSessionDetailProps) {
  const [changeReasonModalOpen, setChangeReasonModalOpen] = useState(false);
  const [changeReasonAction, setChangeReasonAction] = useState<"approve" | "reject">("approve");
  const [changeReason, setChangeReason] = useState("");

  const agentReviews = session.agent_reviews ?? [];

  const handleApproveClick = () => {
    setChangeReasonAction("approve");
    setChangeReason("");
    setChangeReasonModalOpen(true);
  };

  const handleRejectClick = () => {
    setChangeReasonAction("reject");
    setChangeReason("");
    setChangeReasonModalOpen(true);
  };

  const handleConfirmAction = () => {
    if (!changeReason.trim()) return;
    if (changeReasonAction === "approve") {
      onApprove(changeReason.trim());
    } else {
      onReject(changeReason.trim());
    }
    setChangeReasonModalOpen(false);
    setChangeReason("");
  };

  const handleCancelAction = () => {
    setChangeReasonModalOpen(false);
    setChangeReason("");
  };

  return (
    <div className="space-y-6">
      {/* Session header */}
      <SessionHeader session={session} />

      {/* Progress tracker */}
      <ProgressTracker agentReviews={agentReviews} />

      {/* Master summary (highlighted) */}
      {session.master_summary && (
        <MasterSummarySection summary={session.master_summary} />
      )}

      {/* Individual agent reports */}
      {agentReviews.length > 0 && (
        <AgentReportsSection agentReviews={agentReviews} />
      )}

      {/* Approve/Reject actions */}
      {session.status === "Completed" && (
        <div className="flex items-center gap-3 pt-2">
          <Button
            onClick={handleApproveClick}
            disabled={isApproving}
            className="gap-1"
          >
            {isApproving && changeReasonAction === "approve" ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            )}
            Approve
          </Button>
          <Button
            variant="destructive"
            onClick={handleRejectClick}
            disabled={isApproving}
            className="gap-1"
          >
            {isApproving && changeReasonAction === "reject" ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <XCircle className="h-4 w-4" aria-hidden="true" />
            )}
            Reject
          </Button>
          {approveError && (
            <span className="text-sm text-destructive">{approveError}</span>
          )}
        </div>
      )}

      {/* Change reason modal */}
      {changeReasonModalOpen && (
        <ChangeReasonModal
          action={changeReasonAction}
          changeReason={changeReason}
          onChangeReason={setChangeReason}
          onConfirm={handleConfirmAction}
          onCancel={handleCancelAction}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Session Header
// ---------------------------------------------------------------------------

function SessionHeader({ session }: { session: ReviewSession }) {
  return (
    <div className="border border-border rounded-md p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{session.document_title}</h2>
        <StatusBadge status={session.status} />
      </div>
      <dl className="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-2 text-sm">
        <div>
          <dt className="text-muted-foreground">Document Type</dt>
          <dd className="font-medium">{session.document_type}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Submitted</dt>
          <dd className="font-medium">
            {new Date(session.submitted_at).toLocaleString()}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Compliance Score</dt>
          <dd className="font-medium">
            {session.compliance_score != null
              ? `${session.compliance_score.toFixed(1)}%`
              : "—"}
          </dd>
        </div>
      </dl>
      {session.summary_failed && (
        <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 rounded px-3 py-2">
          <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          Master summary generation failed. Individual agent reports are still available.
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress Tracker
// ---------------------------------------------------------------------------

function ProgressTracker({ agentReviews }: { agentReviews: AgentReview[] }) {
  const completedCount = agentReviews.filter(
    (r) => r.status === "Completed" || r.status === "Failed"
  ).length;
  const totalCount = agentReviews.length;

  return (
    <section
      className="border border-border rounded-md p-4 space-y-3"
      aria-labelledby="progress-tracker-heading"
    >
      <div className="flex items-center justify-between">
        <h3
          id="progress-tracker-heading"
          className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
        >
          Agent Progress
        </h3>
        <span className="text-sm text-muted-foreground">
          {completedCount} / {totalCount} completed
        </span>
      </div>

      {/* Progress bar */}
      <div
        className="w-full h-2 bg-muted rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={completedCount}
        aria-valuemin={0}
        aria-valuemax={totalCount}
        aria-label={`${completedCount} of ${totalCount} agents completed`}
      >
        <div
          className="h-full bg-primary rounded-full transition-all duration-300"
          style={{
            width: totalCount > 0 ? `${(completedCount / totalCount) * 100}%` : "0%",
          }}
        />
      </div>

      {/* Agent status list */}
      <div className="space-y-2">
        {agentReviews.map((review) => (
          <AgentProgressRow key={review.id} review={review} />
        ))}
      </div>
    </section>
  );
}

function AgentProgressRow({ review }: { review: AgentReview }) {
  const elapsedTime = useMemo(() => {
    if (review.inference_duration_ms != null) {
      return formatDuration(review.inference_duration_ms);
    }
    if (review.started_at && !review.completed_at) {
      const elapsed = Date.now() - new Date(review.started_at).getTime();
      return formatDuration(elapsed);
    }
    return null;
  }, [review.inference_duration_ms, review.started_at, review.completed_at]);

  return (
    <div className="flex items-center justify-between text-sm py-1.5 px-2 rounded hover:bg-muted/50">
      <div className="flex items-center gap-2">
        <AgentStatusIcon status={review.status} />
        <span className="font-medium">{review.agent_name}</span>
        {review.agent_archetype && (
          <span className="text-xs text-muted-foreground">
            ({review.agent_archetype})
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {elapsedTime && (
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" aria-hidden="true" />
            {elapsedTime}
          </span>
        )}
        {review.error_reason && (
          <span className="text-xs text-destructive">{review.error_reason}</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Master Summary Section
// ---------------------------------------------------------------------------

interface MasterSummaryData {
  compliance_score: number;
  risk_assessment: string;
  executive_summary: string;
  consensus_findings: Record<string, unknown>[];
  contradictions: Record<string, unknown>[];
  prioritized_action_items: Record<string, unknown>[];
}

function MasterSummarySection({ summary }: { summary: MasterSummaryData }) {
  return (
    <section
      className="border-2 border-primary/30 bg-primary/5 rounded-md p-4 space-y-4"
      aria-labelledby="master-summary-heading"
    >
      <div className="flex items-center gap-2">
        <Shield className="h-5 w-5 text-primary" aria-hidden="true" />
        <h3
          id="master-summary-heading"
          className="text-sm font-semibold uppercase tracking-wide text-primary"
        >
          Master Auditor Summary
        </h3>
      </div>

      {/* Score and risk */}
      <div className="flex items-center gap-6">
        <div className="text-center">
          <div className="text-2xl font-bold">{summary.compliance_score.toFixed(1)}%</div>
          <div className="text-xs text-muted-foreground">Compliance Score</div>
        </div>
        <RiskBadge assessment={summary.risk_assessment} />
      </div>

      {/* Executive summary */}
      <div className="space-y-1">
        <h4 className="text-sm font-medium">Executive Summary</h4>
        <p className="text-sm text-muted-foreground whitespace-pre-wrap">
          {summary.executive_summary}
        </p>
      </div>

      {/* Consensus findings */}
      {summary.consensus_findings.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">
            Consensus Findings ({summary.consensus_findings.length})
          </h4>
          <div className="space-y-1">
            {summary.consensus_findings.map((finding, idx) => (
              <FindingRow key={idx} finding={finding} variant="consensus" />
            ))}
          </div>
        </div>
      )}

      {/* Contradictions */}
      {summary.contradictions.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-amber-700">
            Contradictions ({summary.contradictions.length})
          </h4>
          <div className="space-y-1">
            {summary.contradictions.map((item, idx) => (
              <FindingRow key={idx} finding={item} variant="contradiction" />
            ))}
          </div>
        </div>
      )}

      {/* Prioritized action items */}
      {summary.prioritized_action_items.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">
            Prioritized Action Items ({summary.prioritized_action_items.length})
          </h4>
          <ol className="space-y-1 list-decimal list-inside text-sm">
            {summary.prioritized_action_items.map((item, idx) => (
              <li key={idx} className="text-muted-foreground">
                {String((item as Record<string, unknown>).title || (item as Record<string, unknown>).description || JSON.stringify(item))}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Agent Reports Section
// ---------------------------------------------------------------------------

function AgentReportsSection({ agentReviews }: { agentReviews: AgentReview[] }) {
  const completedReviews = agentReviews.filter((r) => r.status === "Completed");

  if (completedReviews.length === 0) return null;

  return (
    <section
      className="space-y-3"
      aria-labelledby="agent-reports-heading"
    >
      <h3
        id="agent-reports-heading"
        className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Individual Agent Reports
      </h3>
      <div className="space-y-2">
        {completedReviews.map((review) => (
          <AgentReportCard key={review.id} review={review} />
        ))}
      </div>
    </section>
  );
}

function AgentReportCard({ review }: { review: AgentReview }) {
  const [expanded, setExpanded] = useState(false);
  const report = review.report_data as Record<string, unknown> | null;
  const findings = Array.isArray(report?.findings)
    ? (report.findings as Record<string, unknown>[])
    : [];

  return (
    <div className="border border-border rounded-md overflow-hidden">
      {/* Card header (clickable) */}
      <button
        type="button"
        className="w-full flex items-center justify-between p-3 text-left hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={`agent-report-${review.id}`}
      >
        <div className="flex items-center gap-2">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          )}
          <span className="font-medium text-sm">{review.agent_name}</span>
          {review.agent_archetype && (
            <span className="text-xs px-2 py-0.5 bg-secondary text-secondary-foreground rounded-full">
              {review.agent_archetype}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {findings.length > 0 && (
            <span>{findings.length} finding{findings.length !== 1 ? "s" : ""}</span>
          )}
          {review.inference_duration_ms != null && (
            <span>{formatDuration(review.inference_duration_ms)}</span>
          )}
        </div>
      </button>

      {/* Expandable content */}
      {expanded && (
        <div id={`agent-report-${review.id}`} className="border-t border-border p-3 space-y-3">
          {/* Summary */}
          {report?.summary ? (
            <div className="space-y-1">
              <h4 className="text-xs font-medium text-muted-foreground uppercase">Summary</h4>
              <p className="text-sm">{String(report.summary)}</p>
            </div>
          ) : null}

          {/* Overall status */}
          {report?.overall_status ? (
            <div className="text-sm">
              <span className="text-muted-foreground">Overall Status: </span>
              <span className="font-medium">{String(report.overall_status)}</span>
            </div>
          ) : null}

          {/* Findings table */}
          {findings.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-medium text-muted-foreground uppercase">Findings</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse" role="table">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-1.5 px-2 text-xs font-medium text-muted-foreground">Severity</th>
                      <th className="text-left py-1.5 px-2 text-xs font-medium text-muted-foreground">Chapter</th>
                      <th className="text-left py-1.5 px-2 text-xs font-medium text-muted-foreground">Description</th>
                      <th className="text-left py-1.5 px-2 text-xs font-medium text-muted-foreground">Recommendation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {findings.map((finding, idx) => (
                      <tr key={idx} className="border-b border-border/50 last:border-0">
                        <td className="py-1.5 px-2">
                          <SeverityBadge severity={String(finding.severity || "Unknown")} />
                        </td>
                        <td className="py-1.5 px-2 text-muted-foreground">
                          {String(finding.chapter || finding.section || "—")}
                        </td>
                        <td className="py-1.5 px-2">
                          {String(finding.description || "—")}
                        </td>
                        <td className="py-1.5 px-2 text-muted-foreground">
                          {String(finding.recommendation || "—")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Chapter results */}
          {Array.isArray(report?.chapter_results) && (report.chapter_results as Record<string, unknown>[]).length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-medium text-muted-foreground uppercase">Chapter Results</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(report.chapter_results as Record<string, unknown>[]).map((chapter, idx) => (
                  <div key={idx} className="border border-border/50 rounded p-2 text-xs">
                    <div className="font-medium">{String(chapter.chapter || chapter.name || `Chapter ${idx + 1}`)}</div>
                    <div className="text-muted-foreground">{String(chapter.status || chapter.result || "—")}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Change Reason Modal
// ---------------------------------------------------------------------------

interface ChangeReasonModalProps {
  action: "approve" | "reject";
  changeReason: string;
  onChangeReason: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

function ChangeReasonModal({
  action,
  changeReason,
  onChangeReason,
  onConfirm,
  onCancel,
}: ChangeReasonModalProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="change-reason-title"
    >
      <div className="bg-background border border-border rounded-lg shadow-lg w-full max-w-md p-6 space-y-4">
        <h3 id="change-reason-title" className="text-lg font-semibold">
          {action === "approve" ? "Approve Review" : "Reject Review"}
        </h3>
        <p className="text-sm text-muted-foreground">
          Please provide a reason for {action === "approve" ? "approving" : "rejecting"} this
          review session. This is required for audit compliance.
        </p>
        <div className="space-y-2">
          <label htmlFor="change-reason-input" className="text-sm font-medium">
            Change Reason
          </label>
          <textarea
            id="change-reason-input"
            className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background focus:outline-none focus:ring-1 focus:ring-ring resize-none"
            rows={3}
            value={changeReason}
            onChange={(e) => onChangeReason(e.target.value)}
            placeholder="Enter the reason for this action..."
            autoFocus
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant={action === "reject" ? "destructive" : "default"}
            onClick={onConfirm}
            disabled={!changeReason.trim()}
          >
            {action === "approve" ? "Confirm Approval" : "Confirm Rejection"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared UI Helpers
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    Pending: "bg-gray-100 text-gray-700",
    InProgress: "bg-blue-100 text-blue-700",
    Completed: "bg-green-100 text-green-700",
    Failed: "bg-red-100 text-red-700",
    Approved: "bg-emerald-100 text-emerald-700",
    Rejected: "bg-rose-100 text-rose-700",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center text-xs px-2 py-0.5 rounded-full font-medium",
        colorMap[status] || "bg-gray-100 text-gray-700"
      )}
    >
      {status}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const colorMap: Record<string, string> = {
    Critical: "bg-red-100 text-red-700",
    Major: "bg-orange-100 text-orange-700",
    Minor: "bg-yellow-100 text-yellow-700",
    Informational: "bg-blue-100 text-blue-700",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center text-xs px-1.5 py-0.5 rounded font-medium",
        colorMap[severity] || "bg-gray-100 text-gray-700"
      )}
    >
      {severity}
    </span>
  );
}

function RiskBadge({ assessment }: { assessment: string }) {
  const colorMap: Record<string, string> = {
    Excellent: "bg-emerald-100 text-emerald-700 border-emerald-200",
    Good: "bg-green-100 text-green-700 border-green-200",
    "Needs Attention": "bg-yellow-100 text-yellow-700 border-yellow-200",
    "At Risk": "bg-orange-100 text-orange-700 border-orange-200",
    Critical: "bg-red-100 text-red-700 border-red-200",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center text-sm px-3 py-1 rounded-full font-medium border",
        colorMap[assessment] || "bg-gray-100 text-gray-700 border-gray-200"
      )}
    >
      {assessment}
    </span>
  );
}

function AgentStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "Completed":
      return <CheckCircle2 className="h-4 w-4 text-green-600" aria-label="Completed" />;
    case "Failed":
      return <XCircle className="h-4 w-4 text-red-600" aria-label="Failed" />;
    case "InProgress":
      return <Loader2 className="h-4 w-4 text-blue-600 animate-spin" aria-label="In progress" />;
    case "Pending":
      return <Clock className="h-4 w-4 text-gray-400" aria-label="Pending" />;
    default:
      return <Info className="h-4 w-4 text-gray-400" aria-label={status} />;
  }
}

function FindingRow({
  finding,
  variant,
}: {
  finding: Record<string, unknown>;
  variant: "consensus" | "contradiction";
}) {
  const borderColor = variant === "consensus" ? "border-l-green-500" : "border-l-amber-500";

  return (
    <div className={cn("border-l-2 pl-3 py-1 text-sm", borderColor)}>
      <div className="flex items-center gap-2">
        {finding.severity ? <SeverityBadge severity={String(finding.severity)} /> : null}
        {finding.chapter ? (
          <span className="text-xs text-muted-foreground">
            {String(finding.chapter)}
          </span>
        ) : null}
      </div>
      {finding.description ? (
        <p className="text-muted-foreground text-xs mt-0.5">
          {String(finding.description)}
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/** Format milliseconds into a human-readable duration string. */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}
