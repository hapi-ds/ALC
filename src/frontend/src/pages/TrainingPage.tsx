import { useEffect, useState, useCallback } from "react";
import { useTrainingStore } from "@/stores/trainingStore";
import { useAuthStore } from "@/stores/authStore";
import { TrainingStatusOverview } from "@/components/training/TrainingStatusOverview";
import { TrainingTaskList } from "@/components/training/TrainingTaskList";
import { TrainingContentViewer } from "@/components/training/TrainingContentViewer";
import { TrainingRecordsPanel } from "@/components/training/TrainingRecordsPanel";
import { AdminTrainingView } from "@/components/training/AdminTrainingView";
import { TaskCompletionDialog } from "@/components/training/TaskCompletionDialog";
import { deriveContentId } from "@/components/training/utils";
import type { TrainingTask, TaskFilter } from "@/components/training/types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

type TabId = "tasks" | "records" | "admin";

interface TabDefinition {
  id: TabId;
  label: string;
  adminOnly?: boolean;
}

const TABS: TabDefinition[] = [
  { id: "tasks", label: "My Tasks" },
  { id: "records", label: "Records" },
  { id: "admin", label: "Admin: SOP Training Status", adminOnly: true },
];

// ---------------------------------------------------------------------------
// TrainingPage
// ---------------------------------------------------------------------------

export function TrainingPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.roles?.includes("admin") ?? false;

  const {
    tasks,
    isLoadingTasks,
    tasksError,
    statistics,
    filter,
    currentContent,
    isLoadingContent,
    contentError,
    isCompleting,
    completionError,
    fetchTrainingTasks,
    fetchTrainingContent,
    completeTrainingTask,
    setFilter,
  } = useTrainingStore();

  // Local UI state
  const [activeTab, setActiveTab] = useState<TabId>("tasks");
  const [selectedTask, setSelectedTask] = useState<TrainingTask | null>(null);
  const [completingTask, setCompletingTask] = useState<TrainingTask | null>(null);

  // Fetch training tasks on mount
  useEffect(() => {
    if (user?.id) {
      fetchTrainingTasks(user.id);
    }
  }, [user?.id, fetchTrainingTasks]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleTaskSelect = useCallback(
    (task: TrainingTask) => {
      setSelectedTask(task);
      const contentId = deriveContentId(task.sop_document_uuid, task.sop_version);
      fetchTrainingContent(contentId);
    },
    [fetchTrainingContent]
  );

  const handleMarkComplete = useCallback((task: TrainingTask) => {
    setCompletingTask(task);
  }, []);

  const handleCompletionConfirm = useCallback(
    async (changeReason: string) => {
      if (!completingTask || !user?.id) return;
      const success = await completeTrainingTask(
        completingTask.id,
        user.id,
        changeReason
      );
      if (success) {
        setCompletingTask(null);
      }
    },
    [completingTask, user?.id, completeTrainingTask]
  );

  const handleCompletionClose = useCallback(() => {
    setCompletingTask(null);
  }, []);

  const handleFilterChange = useCallback(
    (newFilter: TaskFilter) => {
      setFilter(newFilter);
    },
    [setFilter]
  );

  const handleRetry = useCallback(() => {
    if (user?.id) {
      fetchTrainingTasks(user.id);
    }
  }, [user?.id, fetchTrainingTasks]);

  const handleContentRetry = useCallback(() => {
    if (selectedTask) {
      const contentId = deriveContentId(
        selectedTask.sop_document_uuid,
        selectedTask.sop_version
      );
      fetchTrainingContent(contentId);
    }
  }, [selectedTask, fetchTrainingContent]);

  // ---------------------------------------------------------------------------
  // Tab filtering (hide admin tab for non-admins)
  // ---------------------------------------------------------------------------

  const visibleTabs = TABS.filter((tab) => !tab.adminOnly || isAdmin);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <main role="main" aria-label="Training Management" className="space-y-6">
      {/* Loading state announcement */}
      <div aria-live="polite" className="sr-only">
        {isLoadingTasks ? "Loading training tasks..." : ""}
      </div>

      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold">Training Dashboard</h2>
        <p className="text-sm text-muted-foreground">
          Track training tasks, completion status, and view training content
        </p>
      </div>

      {/* Status Overview */}
      <TrainingStatusOverview
        statistics={statistics}
        isLoading={isLoadingTasks}
      />

      {/* Tab Navigation */}
      <div
        role="tablist"
        aria-label="Training sections"
        className="flex border-b"
      >
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`tabpanel-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Panels */}
      <div
        role="tabpanel"
        id={`tabpanel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
      >
        {activeTab === "tasks" && (
          <div className="space-y-6">
            <TrainingTaskList
              tasks={tasks}
              filter={filter}
              isLoading={isLoadingTasks}
              error={tasksError}
              selectedTaskId={selectedTask?.id ?? null}
              onFilterChange={handleFilterChange}
              onTaskSelect={handleTaskSelect}
              onMarkComplete={handleMarkComplete}
              onRetry={handleRetry}
            />

            {/* Content Viewer (shown when a task is selected) */}
            {selectedTask && (
              <section aria-label="Training content">
                <h3 className="text-lg font-semibold mb-3">Training Content</h3>
                <TrainingContentViewer
                  content={currentContent}
                  isLoading={isLoadingContent}
                  error={contentError}
                  mode="view"
                  onRetry={handleContentRetry}
                />
              </section>
            )}

            {!selectedTask && !isLoadingTasks && tasks.length > 0 && (
              <section aria-label="Training content">
                <h3 className="text-lg font-semibold mb-3">Training Content</h3>
                <p className="text-sm text-muted-foreground">
                  Select a training task to view its content, quiz, and key points
                </p>
              </section>
            )}
          </div>
        )}

        {activeTab === "records" && (
          <TrainingRecordsPanel
            tasks={tasks}
            isLoading={isLoadingTasks}
            error={tasksError}
            onRetry={handleRetry}
          />
        )}

        {activeTab === "admin" && isAdmin && (
          <AdminTrainingView tasks={tasks} isAdmin={isAdmin} />
        )}
      </div>

      {/* Task Completion Dialog */}
      {completingTask && (
        <TaskCompletionDialog
          task={completingTask}
          isSubmitting={isCompleting}
          error={completionError}
          onConfirm={handleCompletionConfirm}
          onClose={handleCompletionClose}
        />
      )}
    </main>
  );
}
