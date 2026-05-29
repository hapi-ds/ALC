/**
 * OrphanAlertsPanel
 *
 * Two tabs: "Orphan Requirements" and "Orphan Test Cases"
 * - Orphan Requirements: severity badges (red=critical, orange=major, yellow=minor),
 *   suggested_action chips
 * - Orphan Test Cases: risk_level badges (red=high, orange=medium, green=low),
 *   suggested_action chips
 *
 * Fetches from GET /api/traceability/matrices/{matrix_id}/orphan-requirements
 * and orphan-test-cases.
 *
 * Requirements: 8.4
 */

import { useEffect, useState } from "react";
import { AlertTriangle, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTraceabilityStore } from "@/stores/traceabilityStore";
import type { OrphanRequirement, OrphanTestCase } from "@/types/traceability";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface OrphanAlertsPanelProps {
  matrixId: string;
}

type Tab = "requirements" | "test-cases";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getSeverityBadgeClass(severity: string): string {
  switch (severity) {
    case "critical":
      return "bg-red-100 text-red-800 border-red-200";
    case "major":
      return "bg-orange-100 text-orange-800 border-orange-200";
    case "minor":
      return "bg-yellow-100 text-yellow-800 border-yellow-200";
    default:
      return "bg-gray-100 text-gray-800 border-gray-200";
  }
}

function getRiskLevelBadgeClass(riskLevel: string): string {
  switch (riskLevel) {
    case "high":
      return "bg-red-100 text-red-800 border-red-200";
    case "medium":
      return "bg-orange-100 text-orange-800 border-orange-200";
    case "low":
      return "bg-green-100 text-green-800 border-green-200";
    default:
      return "bg-gray-100 text-gray-800 border-gray-200";
  }
}

function formatAction(action: string): string {
  return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function OrphanAlertsPanel({ matrixId }: OrphanAlertsPanelProps) {
  const {
    orphanRequirements,
    orphanTestCases,
    isLoading,
    fetchOrphanRequirements,
    fetchOrphanTestCases,
  } = useTraceabilityStore();

  const [activeTab, setActiveTab] = useState<Tab>("requirements");

  useEffect(() => {
    fetchOrphanRequirements(matrixId);
    fetchOrphanTestCases(matrixId);
  }, [matrixId, fetchOrphanRequirements, fetchOrphanTestCases]);

  return (
    <div className="space-y-4">
      {/* Tab buttons */}
      <div className="flex border-b border-border">
        <TabButton
          active={activeTab === "requirements"}
          onClick={() => setActiveTab("requirements")}
          icon={AlertTriangle}
          label="Orphan Requirements"
          count={orphanRequirements.length}
        />
        <TabButton
          active={activeTab === "test-cases"}
          onClick={() => setActiveTab("test-cases")}
          icon={FlaskConical}
          label="Orphan Test Cases"
          count={orphanTestCases.length}
        />
      </div>

      {/* Tab content */}
      {isLoading ? (
        <div className="text-center py-6 text-muted-foreground text-sm">
          Loading orphan data...
        </div>
      ) : activeTab === "requirements" ? (
        <OrphanRequirementsList orphans={orphanRequirements} />
      ) : (
        <OrphanTestCasesList orphans={orphanTestCases} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  count: number;
}

function TabButton({ active, onClick, icon: Icon, label, count }: TabButtonProps) {
  return (
    <button
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-primary text-primary"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
      onClick={onClick}
      role="tab"
      aria-selected={active}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
      {count > 0 && (
        <span className="text-xs bg-muted px-1.5 py-0.5 rounded-full">
          {count}
        </span>
      )}
    </button>
  );
}

function OrphanRequirementsList({ orphans }: { orphans: OrphanRequirement[] }) {
  if (orphans.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground text-sm">
        No orphan requirements found. All requirements have test coverage.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {orphans.map((orphan) => (
        <div
          key={`${orphan.requirement_id}-${orphan.source_document_uuid}`}
          className="border border-border rounded-lg p-3"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-medium">
                  {orphan.requirement_id}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium border ${getSeverityBadgeClass(orphan.severity)}`}
                >
                  {orphan.severity}
                </span>
              </div>
              <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                {orphan.requirement_text}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Source: {orphan.source_document_uuid} · {orphan.source_section}
              </p>
            </div>
            <span className="text-xs px-2 py-1 bg-muted rounded-md whitespace-nowrap">
              {formatAction(orphan.suggested_action)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function OrphanTestCasesList({ orphans }: { orphans: OrphanTestCase[] }) {
  if (orphans.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground text-sm">
        No orphan test cases found. All test cases trace to requirements.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {orphans.map((orphan) => (
        <div
          key={`${orphan.test_case_id}-${orphan.target_document_uuid}`}
          className="border border-border rounded-lg p-3"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-medium">
                  {orphan.test_case_id}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium border ${getRiskLevelBadgeClass(orphan.risk_level)}`}
                >
                  {orphan.risk_level}
                </span>
              </div>
              <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                {orphan.test_case_text}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Target: {orphan.target_document_uuid} · {orphan.target_section}
              </p>
            </div>
            <span className="text-xs px-2 py-1 bg-muted rounded-md whitespace-nowrap">
              {formatAction(orphan.suggested_action)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
