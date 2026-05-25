/**
 * GapAnalysisDetail
 *
 * Displays a side-by-side comparison of source section (left) and target
 * section (right) for gap analysis findings. Highlights misalignments and
 * shows AI remediation suggestion below each finding.
 *
 * Requirements: 10.4
 */

import {
  AlertTriangle,
  AlertCircle,
  Lightbulb,
} from "lucide-react";
import type { GapFinding } from "@/types/impactAnalysis";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getSeverityConfig(severity: string) {
  switch (severity) {
    case "critical":
      return {
        label: "Critical",
        className: "bg-red-100 text-red-800 border-red-200",
        borderColor: "border-l-red-500",
        icon: AlertTriangle,
      };
    case "major":
      return {
        label: "Major",
        className: "bg-orange-100 text-orange-800 border-orange-200",
        borderColor: "border-l-orange-500",
        icon: AlertTriangle,
      };
    case "minor":
      return {
        label: "Minor",
        className: "bg-yellow-100 text-yellow-800 border-yellow-200",
        borderColor: "border-l-yellow-500",
        icon: AlertCircle,
      };
    default:
      return {
        label: severity,
        className: "bg-gray-100 text-gray-700 border-gray-200",
        borderColor: "border-l-gray-400",
        icon: AlertCircle,
      };
  }
}

function getGapTypeLabel(gapType: string): string {
  switch (gapType) {
    case "missing":
      return "Missing Coverage";
    case "contradicts":
      return "Contradiction";
    case "incomplete":
      return "Incomplete";
    case "outdated":
      return "Outdated";
    default:
      return gapType;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface GapAnalysisDetailProps {
  findings: GapFinding[];
}

export function GapAnalysisDetail({ findings }: GapAnalysisDetailProps) {
  if (findings.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 text-center text-muted-foreground">
        <p className="text-sm font-medium">No gap findings</p>
        <p className="text-xs mt-1">
          The documents are aligned — no misalignments detected.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4" role="list" aria-label="Gap analysis findings">
      {findings.map((finding, index) => {
        const config = getSeverityConfig(finding.severity);
        const SeverityIcon = config.icon;

        return (
          <div
            key={index}
            className={`border border-border rounded-lg overflow-hidden border-l-4 ${config.borderColor}`}
            role="listitem"
          >
            {/* Header */}
            <div className="flex items-center gap-2 px-4 py-2 bg-muted/30 border-b border-border">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${config.className}`}
              >
                <SeverityIcon className="h-3 w-3" aria-hidden="true" />
                {config.label}
              </span>
              <span className="text-xs text-muted-foreground font-medium">
                {getGapTypeLabel(finding.gap_type)}
              </span>
            </div>

            {/* Side-by-side comparison */}
            <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border">
              {/* Source section (left) */}
              <div className="p-3">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Source Section
                </p>
                <p className="text-xs font-mono text-primary mb-1.5">
                  {finding.source_section}
                </p>
                <p className="text-sm text-foreground bg-green-50 rounded p-2 border border-green-100">
                  {finding.source_content_excerpt}
                </p>
              </div>

              {/* Target section (right) */}
              <div className="p-3">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Target Section
                </p>
                <p className="text-xs font-mono text-primary mb-1.5">
                  {finding.target_section === "not_found"
                    ? "Not found in target"
                    : finding.target_section}
                </p>
                {finding.target_section === "not_found" ? (
                  <p className="text-sm text-muted-foreground italic bg-red-50 rounded p-2 border border-red-100">
                    No corresponding section found in the target document.
                  </p>
                ) : (
                  <p className="text-sm text-foreground bg-red-50 rounded p-2 border border-red-100">
                    {finding.target_content_excerpt}
                  </p>
                )}
              </div>
            </div>

            {/* Remediation suggestion */}
            <div className="px-4 py-2 bg-blue-50/50 border-t border-border">
              <div className="flex items-start gap-1.5">
                <Lightbulb
                  className="h-3.5 w-3.5 text-blue-600 shrink-0 mt-0.5"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-xs font-medium text-blue-800 mb-0.5">
                    AI Remediation Suggestion
                  </p>
                  <p className="text-xs text-blue-700">
                    {finding.remediation_suggestion}
                  </p>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
