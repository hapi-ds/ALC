/**
 * DocumentGeneratorPage
 *
 * Main page for the AI Document Generator (Template-Based) feature.
 * Provides tabbed navigation between Template Registration, Generation,
 * Review, and Provenance views.
 *
 * Route: /document-generator
 * Requirements: 1.1, 2.1, 6.2, 7.3
 */

import { useEffect, useCallback, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";
import { ReviewWorkflowPanel } from "@/components/document-generator/ReviewWorkflowPanel";
import { ProvenanceViewer } from "@/components/document-generator/ProvenanceViewer";
import { TemplateRegistrationPanel } from "@/components/document-generator/TemplateRegistrationPanel";
import { TemplateListPanel } from "@/components/document-generator/TemplateListPanel";
import { GenerationSetupPanel, JobProgressMonitor } from "@/components/document-generator";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TabId = "templates" | "generate" | "review" | "provenance";

interface TabDefinition {
  id: TabId;
  label: string;
}

const TABS: TabDefinition[] = [
  { id: "templates", label: "Templates" },
  { id: "generate", label: "Generate" },
  { id: "review", label: "Review" },
  { id: "provenance", label: "Provenance" },
];

// ---------------------------------------------------------------------------
// Placeholder Panels (to be replaced by tasks 15.2–15.4)
// ---------------------------------------------------------------------------

function TemplatesPanel() {
  return (
    <div className="space-y-6">
      <TemplateRegistrationPanel />
      <TemplateListPanel />
    </div>
  );
}

function GeneratePanel() {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border p-6">
        <h3 className="text-lg font-semibold mb-4">New Generation</h3>
        <GenerationSetupPanel />
      </div>
      <div className="rounded-lg border p-6">
        <h3 className="text-lg font-semibold mb-4">Job Progress</h3>
        <JobProgressMonitor />
      </div>
    </div>
  );
}

function ReviewPanel() {
  return <ReviewWorkflowPanel />;
}

function ProvenancePanel() {
  return <ProvenanceViewer />;
}

// ---------------------------------------------------------------------------
// DocumentGeneratorPage
// ---------------------------------------------------------------------------

export function DocumentGeneratorPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get("view") as TabId | null;
  const [activeTab, setActiveTab] = useState<TabId>(
    viewParam && TABS.some((t) => t.id === viewParam) ? viewParam : "templates",
  );

  const { activeJobs, startPolling, stopPolling } = useDocumentGeneratorStore();

  // Start polling if there are active jobs
  useEffect(() => {
    const pendingJobs = activeJobs.filter(
      (job) => job.status === "pending" || job.status === "processing",
    );
    if (pendingJobs.length > 0) {
      startPolling();
    }
    return () => {
      stopPolling();
    };
  }, [activeJobs, startPolling, stopPolling]);

  // Sync tab with URL search params
  const handleTabChange = useCallback(
    (tab: TabId) => {
      setActiveTab(tab);
      setSearchParams({ view: tab });
    },
    [setSearchParams],
  );

  return (
    <main role="main" aria-label="AI Document Generator" className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold">AI Document Generator</h2>
        <p className="text-sm text-muted-foreground">
          Generate regulatory documents from Master Templates using AI-powered content synthesis
        </p>
      </div>

      {/* Tab Navigation */}
      <div role="tablist" aria-label="Document generator sections" className="flex border-b">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            id={`docgen-tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`docgen-tabpanel-${tab.id}`}
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
        id={`docgen-tabpanel-${activeTab}`}
        aria-labelledby={`docgen-tab-${activeTab}`}
      >
        {activeTab === "templates" && <TemplatesPanel />}
        {activeTab === "generate" && <GeneratePanel />}
        {activeTab === "review" && <ReviewPanel />}
        {activeTab === "provenance" && <ProvenancePanel />}
      </div>
    </main>
  );
}
