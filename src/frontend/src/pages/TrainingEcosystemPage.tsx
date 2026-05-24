/**
 * TrainingEcosystemPage
 *
 * Main page for the AI-Enhanced Training Ecosystem. Provides tabbed navigation
 * between schedule, materials, assessments, and role-play sub-panels.
 *
 * Route: /training/ecosystem
 * Requirements: 10.1, 10.2, 10.9
 */

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { useTrainingEcosystemStore } from "@/stores/trainingEcosystemStore";
import { useAuthStore } from "@/stores/authStore";
import { TrainingSchedulePanel } from "@/components/training/TrainingSchedulePanel";
import { SkillGapAlert } from "@/components/training/SkillGapAlert";
import { TrainingMaterialViewer } from "@/components/training/TrainingMaterialViewer";
import { VirtualAuditInterface } from "@/components/training/VirtualAuditInterface";
import { DynamicFeedbackPanel } from "@/components/training/DynamicFeedbackPanel";
import { JobMonitor } from "@/components/training/JobMonitor";
import type { TrainingItem } from "@/components/training/TrainingSchedulePanel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TabId = "schedule" | "materials" | "assessments" | "roleplay";

interface TabDefinition {
  id: TabId;
  label: string;
}

const TABS: TabDefinition[] = [
  { id: "schedule", label: "Schedule" },
  { id: "materials", label: "Materials" },
  { id: "assessments", label: "Assessments" },
  { id: "roleplay", label: "Virtual Audit" },
];

// ---------------------------------------------------------------------------
// TrainingEcosystemPage
// ---------------------------------------------------------------------------

export function TrainingEcosystemPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get("view") as TabId | null;
  const [activeTab, setActiveTab] = useState<TabId>(
    viewParam && TABS.some((t) => t.id === viewParam) ? viewParam : "schedule"
  );

  // Selected document for materials/assessments
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);

  const user = useAuthStore((s) => s.user);

  const {
    schedule,
    skillGaps,
    materials,
    pendingJobs,
    isLoadingSchedule,
    isLoadingGaps,
    isLoadingMaterials,
    scheduleError,
    fetchSchedule,
    fetchGaps,
    fetchMaterials,
    startPolling,
    stopPolling,
  } = useTrainingEcosystemStore();

  // Fetch schedule and gaps on mount
  useEffect(() => {
    if (user?.id) {
      fetchSchedule(user.id);
      fetchGaps(user.id);
    }
  }, [user?.id, fetchSchedule, fetchGaps]);

  // Start polling if there are pending jobs
  useEffect(() => {
    if (pendingJobs.length > 0) {
      startPolling();
    }
    return () => {
      stopPolling();
    };
  }, [pendingJobs.length, startPolling, stopPolling]);

  // Sync tab with URL search params
  const handleTabChange = useCallback(
    (tab: TabId) => {
      setActiveTab(tab);
      setSearchParams({ view: tab });
    },
    [setSearchParams]
  );

  // Handle starting training from schedule item
  const handleStartTraining = useCallback(
    (item: TrainingItem) => {
      setSelectedDocumentId(item.document_id);
      setActiveTab("materials");
      setSearchParams({ view: "materials" });
      fetchMaterials(item.document_id);
    },
    [setSearchParams, fetchMaterials]
  );

  const handleRetrySchedule = useCallback(() => {
    if (user?.id) fetchSchedule(user.id);
  }, [user?.id, fetchSchedule]);

  // Determine if critical/high gaps exist for alert
  const hasCriticalGaps = skillGaps.some(
    (gap) =>
      gap.priority.toLowerCase() === "critical" ||
      gap.priority.toLowerCase() === "high"
  );

  return (
    <main role="main" aria-label="AI Training Ecosystem" className="space-y-6">
      {/* Live region for loading announcements */}
      <div aria-live="polite" className="sr-only">
        {isLoadingSchedule ? "Loading training schedule..." : ""}
      </div>

      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold">AI Training Ecosystem</h2>
        <p className="text-sm text-muted-foreground">
          Personalized training schedule, AI-generated materials, and interactive assessments
        </p>
      </div>

      {/* Skill Gap Alert */}
      {hasCriticalGaps && !isLoadingGaps && (
        <SkillGapAlert
          gaps={skillGaps}
          onViewGaps={() => handleTabChange("schedule")}
        />
      )}

      {/* Job Monitor */}
      {pendingJobs.length > 0 && <JobMonitor jobs={pendingJobs} />}

      {/* Tab Navigation */}
      <div role="tablist" aria-label="Training ecosystem sections" className="flex border-b">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            id={`ecosystem-tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`ecosystem-tabpanel-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
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
        id={`ecosystem-tabpanel-${activeTab}`}
        aria-labelledby={`ecosystem-tab-${activeTab}`}
      >
        {activeTab === "schedule" && (
          <TrainingSchedulePanel
            schedule={schedule}
            isLoading={isLoadingSchedule}
            error={scheduleError}
            onStartTraining={handleStartTraining}
            onRetry={handleRetrySchedule}
          />
        )}

        {activeTab === "materials" && (
          <TrainingMaterialViewer
            materials={selectedDocumentId ? materials[selectedDocumentId] ?? [] : []}
            isLoading={isLoadingMaterials}
            documentId={selectedDocumentId}
          />
        )}

        {activeTab === "assessments" && (
          <DynamicFeedbackPanel />
        )}

        {activeTab === "roleplay" && (
          <VirtualAuditInterface />
        )}
      </div>
    </main>
  );
}
