/**
 * SkillGapAlert
 *
 * Dismissible banner displayed at the top of the training ecosystem page
 * when Critical or High priority skill gaps exist. Shows the gap count
 * and provides a link to view details.
 *
 * Requirements: 10.3
 */

import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SkillGap } from "@/types/training-ecosystem";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SkillGapAlertProps {
  gaps: SkillGap[];
  onViewGaps?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SkillGapAlert({ gaps, onViewGaps }: SkillGapAlertProps) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  // Filter to only critical and high priority gaps
  const criticalHighGaps = gaps.filter(
    (gap) =>
      gap.priority.toLowerCase() === "critical" ||
      gap.priority.toLowerCase() === "high"
  );

  if (criticalHighGaps.length === 0) return null;

  const criticalCount = criticalHighGaps.filter(
    (g) => g.priority.toLowerCase() === "critical"
  ).length;
  const highCount = criticalHighGaps.filter(
    (g) => g.priority.toLowerCase() === "high"
  ).length;

  // Build description text
  const parts: string[] = [];
  if (criticalCount > 0) {
    parts.push(`${criticalCount} critical`);
  }
  if (highCount > 0) {
    parts.push(`${highCount} high priority`);
  }
  const description = `You have ${parts.join(" and ")} skill gap${criticalHighGaps.length > 1 ? "s" : ""} requiring attention.`;

  return (
    <div
      role="alert"
      aria-label="Skill gap warning"
      className="relative rounded-lg border border-orange-200 bg-orange-50 p-4"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle
          className="h-5 w-5 shrink-0 text-orange-600 mt-0.5"
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-orange-800">
            Skill Gaps Detected
          </p>
          <p className="mt-1 text-sm text-orange-700">{description}</p>
          {onViewGaps && (
            <Button
              variant="link"
              size="sm"
              onClick={onViewGaps}
              className="mt-1 h-auto p-0 text-orange-800 underline"
            >
              View skill gaps
            </Button>
          )}
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss skill gap alert"
          className="shrink-0 rounded-md p-1 text-orange-600 hover:bg-orange-100 transition-colors"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
