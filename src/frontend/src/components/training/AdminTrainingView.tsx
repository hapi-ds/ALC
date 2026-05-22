import { useState, useMemo, useEffect, useCallback } from "react";
import {
  AlertCircle,
  Award,
  BarChart3,
  FileText,
} from "lucide-react";
import type { TrainingTask, TrainingContent } from "./types";
import { deriveUniqueSopPairs } from "./utils";
import type { SopVersionPair } from "./utils";
import { useTrainingStore } from "../../stores/trainingStore";
import { TrainingContentViewer } from "./TrainingContentViewer";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AdminTrainingViewProps {
  tasks: TrainingTask[];
  isAdmin: boolean;
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function StatusSkeleton() {
  return (
    <div className="animate-pulse space-y-6" aria-busy="true" aria-label="Loading training status">
      {/* Progress bar skeleton */}
      <div className="space-y-2">
        <div className="h-4 w-48 rounded bg-muted" />
        <div className="h-6 w-full rounded bg-muted" />
      </div>
      {/* Stats skeleton */}
      <div className="grid grid-cols-3 gap-4">
        <div className="h-16 rounded-lg bg-muted" />
        <div className="h-16 rounded-lg bg-muted" />
        <div className="h-16 rounded-lg bg-muted" />
      </div>
      {/* Table skeleton */}
      <div className="space-y-2">
        <div className="h-4 w-40 rounded bg-muted" />
        <div className="h-10 w-full rounded bg-muted" />
        <div className="h-10 w-full rounded bg-muted" />
        <div className="h-10 w-full rounded bg-muted" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error Panel
// ---------------------------------------------------------------------------

function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4"
    >
      <AlertCircle
        className="h-5 w-5 shrink-0 text-destructive"
        aria-hidden="true"
      />
      <p className="flex-1 text-sm text-destructive">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        aria-label="Retry loading"
        className="shrink-0 rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors"
      >
        Retry
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty State
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <FileText
        className="h-10 w-10 text-muted-foreground/50"
        aria-hidden="true"
      />
      <p className="mt-3 text-sm text-muted-foreground">
        No training tasks have been assigned for the selected SOP version.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress Bar
// ---------------------------------------------------------------------------

function ProgressBar({ percentage }: { percentage: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <span className="text-sm font-medium text-foreground">Completion Progress</span>
        </div>
        <span className="text-sm font-medium text-foreground">{percentage}%</span>
      </div>
      <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all duration-300"
          style={{ width: `${percentage}%` }}
          role="progressbar"
          aria-valuenow={percentage}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Training completion: ${percentage}%`}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Training Complete Badge
// ---------------------------------------------------------------------------

function TrainingCompleteBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800">
      <Award className="h-4 w-4" aria-hidden="true" />
      Training Complete
    </span>
  );
}

// ---------------------------------------------------------------------------
// User Breakdown Table
// ---------------------------------------------------------------------------

function UserBreakdownTable({ tasks }: { tasks: TrainingTask[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="px-4 py-2 text-left font-medium text-muted-foreground">User ID</th>
            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Status</th>
            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Completed At</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id} className="border-b last:border-b-0">
              <td className="px-4 py-2 text-foreground">{task.assigned_user_id}</td>
              <td className="px-4 py-2">
                {task.is_completed ? (
                  <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                    Completed
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                    Pending
                  </span>
                )}
              </td>
              <td className="px-4 py-2 text-muted-foreground">
                {task.completed_at
                  ? new Date(task.completed_at).toLocaleDateString()
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Content Review Section
// ---------------------------------------------------------------------------

function ContentReviewSection() {
  const {
    pendingReviewItems,
    isReviewing,
    reviewError,
    approveContent,
    rejectContent,
  } = useTrainingStore();

  const [selectedItem, setSelectedItem] = useState<TrainingContent | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  const handleApprove = useCallback(async () => {
    if (!selectedItem) return;
    // Use a default reviewer ID of 0 — the backend will use the authenticated user
    const success = await approveContent(selectedItem.content_id, 0, "");
    if (success) {
      setNotification("Content approved successfully.");
      setSelectedItem(null);
      setTimeout(() => setNotification(null), 5000);
    }
  }, [selectedItem, approveContent]);

  const handleReject = useCallback(async () => {
    if (!selectedItem) return;
    const success = await rejectContent(selectedItem.content_id, 0, "Content rejected by reviewer");
    if (success) {
      setNotification("Content rejected successfully.");
      setSelectedItem(null);
      setTimeout(() => setNotification(null), 5000);
    }
  }, [selectedItem, rejectContent]);

  return (
    <section className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground">Content Review</h3>

      {/* Notification */}
      {notification && (
        <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-800">
          {notification}
        </div>
      )}

      {/* Review error */}
      {reviewError && (
        <div role="alert" className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          {reviewError}
        </div>
      )}

      {/* Empty state */}
      {pendingReviewItems.length === 0 && !selectedItem && (
        <p className="text-sm text-muted-foreground">
          No content items are awaiting review.
        </p>
      )}

      {/* Pending review items list */}
      {pendingReviewItems.length > 0 && !selectedItem && (
        <div className="space-y-2">
          {pendingReviewItems.map((item) => (
            <button
              key={item.content_id}
              type="button"
              onClick={() => setSelectedItem(item)}
              className="w-full rounded-lg border p-3 text-left hover:bg-muted/50 transition-colors"
            >
              <p className="text-sm font-medium text-foreground">
                {item.sop_document_uuid} v{item.sop_version}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Generated: {new Date(item.generated_at).toLocaleDateString()}
              </p>
            </button>
          ))}
        </div>
      )}

      {/* Selected item viewer */}
      {selectedItem && (
        <div className="space-y-3">
          <button
            type="button"
            onClick={() => setSelectedItem(null)}
            className="text-xs text-primary hover:text-primary/80 transition-colors"
          >
            ← Back to review queue
          </button>
          <TrainingContentViewer
            content={selectedItem}
            isLoading={false}
            error={null}
            mode="review"
            onApprove={isReviewing ? undefined : handleApprove}
            onReject={isReviewing ? undefined : handleReject}
          />
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// AdminTrainingView
// ---------------------------------------------------------------------------

export function AdminTrainingView({ tasks, isAdmin }: AdminTrainingViewProps) {
  // If not admin, render nothing
  if (!isAdmin) {
    return null;
  }

  return <AdminTrainingViewContent tasks={tasks} />;
}

// ---------------------------------------------------------------------------
// AdminTrainingViewContent (inner component to avoid conditional hooks)
// ---------------------------------------------------------------------------

function AdminTrainingViewContent({ tasks }: { tasks: TrainingTask[] }) {
  const {
    sopStatus,
    isLoadingStatus,
    statusError,
    fetchTrainingStatus,
  } = useTrainingStore();

  // Derive unique SOP pairs from tasks
  const sopPairs = useMemo(() => deriveUniqueSopPairs(tasks), [tasks]);

  // Selected SOP pair state
  const [selectedIndex, setSelectedIndex] = useState(0);

  const selectedPair: SopVersionPair | undefined = sopPairs[selectedIndex];

  // Fetch status when selected pair changes
  useEffect(() => {
    if (selectedPair) {
      fetchTrainingStatus(selectedPair.sop_document_uuid, selectedPair.sop_version);
    }
  }, [selectedPair, fetchTrainingStatus]);

  // Derive user-level breakdown from tasks matching selected SOP
  const userTasks = useMemo(() => {
    if (!selectedPair) return [];
    return tasks.filter(
      (t) =>
        t.sop_document_uuid === selectedPair.sop_document_uuid &&
        t.sop_version === selectedPair.sop_version
    );
  }, [tasks, selectedPair]);

  // Handle SOP selector change
  const handleSopChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      setSelectedIndex(Number(e.target.value));
    },
    []
  );

  // Handle retry
  const handleRetry = useCallback(() => {
    if (selectedPair) {
      fetchTrainingStatus(selectedPair.sop_document_uuid, selectedPair.sop_version);
    }
  }, [selectedPair, fetchTrainingStatus]);

  // Compute completion percentage
  const completionPercentage = useMemo(() => {
    if (!sopStatus || sopStatus.total_tasks === 0) return 0;
    return Math.floor((sopStatus.completed_tasks / sopStatus.total_tasks) * 100);
  }, [sopStatus]);

  // No SOP pairs available
  if (sopPairs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <FileText className="h-10 w-10 text-muted-foreground/50" aria-hidden="true" />
        <p className="mt-3 text-sm text-muted-foreground">
          No SOP training data available.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* SOP Selector */}
      <div className="flex items-center gap-3">
        <label htmlFor="sop-selector" className="text-sm font-medium text-foreground">
          Select SOP:
        </label>
        <select
          id="sop-selector"
          value={selectedIndex}
          onChange={handleSopChange}
          className="rounded-md border bg-background px-3 py-1.5 text-sm text-foreground"
        >
          {sopPairs.map((pair, idx) => (
            <option key={`${pair.sop_document_uuid}_${pair.sop_version}`} value={idx}>
              {pair.sop_document_uuid} (v{pair.sop_version})
            </option>
          ))}
        </select>
      </div>

      {/* Loading state */}
      {isLoadingStatus && <StatusSkeleton />}

      {/* Error state */}
      {statusError && !isLoadingStatus && (
        <ErrorPanel message={statusError} onRetry={handleRetry} />
      )}

      {/* Status display */}
      {sopStatus && !isLoadingStatus && !statusError && (
        <>
          {/* Empty state when total_tasks is 0 */}
          {sopStatus.total_tasks === 0 ? (
            <EmptyState />
          ) : (
            <div className="space-y-6">
              {/* Training Complete Badge */}
              {sopStatus.is_complete && (
                <div className="flex items-center">
                  <TrainingCompleteBadge />
                </div>
              )}

              {/* Progress Bar */}
              <ProgressBar percentage={completionPercentage} />

              {/* Stats Summary */}
              <div className="grid grid-cols-3 gap-4">
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold text-foreground">{sopStatus.total_tasks}</p>
                  <p className="text-xs text-muted-foreground">Total Tasks</p>
                </div>
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold text-green-600">{sopStatus.completed_tasks}</p>
                  <p className="text-xs text-muted-foreground">Completed</p>
                </div>
                <div className="rounded-lg border p-4 text-center">
                  <p className="text-2xl font-bold text-amber-600">
                    {sopStatus.total_tasks - sopStatus.completed_tasks}
                  </p>
                  <p className="text-xs text-muted-foreground">Pending</p>
                </div>
              </div>

              {/* User Breakdown Table */}
              <section>
                <h3 className="text-sm font-semibold text-foreground mb-3">User Breakdown</h3>
                <div className="rounded-lg border">
                  <UserBreakdownTable tasks={userTasks} />
                </div>
              </section>
            </div>
          )}
        </>
      )}

      {/* Content Review Section */}
      <div className="border-t pt-6">
        <ContentReviewSection />
      </div>
    </div>
  );
}
