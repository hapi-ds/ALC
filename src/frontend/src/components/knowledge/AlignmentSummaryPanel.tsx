import { useMemo } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Calendar,
  FileText,
  ExternalLink,
} from "lucide-react";
import type { DiscrepancyReportWithSOP } from "@/types/videoAlignment";

/**
 * Props for the AlignmentSummaryPanel component.
 */
export interface AlignmentSummaryPanelProps {
  /** The discrepancy report data (extended with linked SOP info) */
  report: DiscrepancyReportWithSOP;
}

/**
 * Get the color classes for the alignment score display.
 */
function getScoreClasses(score: number): { bg: string; text: string } {
  const percentage = score * 100;
  if (percentage >= 80) {
    return {
      bg: "bg-green-100 dark:bg-green-900/40",
      text: "text-green-800 dark:text-green-300",
    };
  }
  if (percentage >= 50) {
    return {
      bg: "bg-yellow-100 dark:bg-yellow-900/40",
      text: "text-yellow-800 dark:text-yellow-300",
    };
  }
  return {
    bg: "bg-red-100 dark:bg-red-900/40",
    text: "text-red-800 dark:text-red-300",
  };
}

/**
 * Get the icon for the alignment score.
 */
function getScoreIcon(score: number) {
  const percentage = score * 100;
  if (percentage >= 80) {
    return <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" aria-hidden="true" />;
  }
  if (percentage >= 50) {
    return <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" aria-hidden="true" />;
  }
  return <XCircle className="h-5 w-5 text-red-600 dark:text-red-400" aria-hidden="true" />;
}

/**
 * AlignmentSummaryPanel displays a summary of the alignment report at the top
 * of the Video Alignment section.
 *
 * Shows:
 * - Alignment score (percentage)
 * - Total video steps count
 * - Total SOP steps count
 * - Matched steps count
 * - Missing steps count
 * - Extra steps count
 * - Reordered steps count
 * - Report generation date
 * - Linked SOP title with link to the SOP document
 *
 * Validates: Requirements 11.5
 */
export function AlignmentSummaryPanel({ report }: AlignmentSummaryPanelProps) {
  const {
    alignment_score,
    matched_steps,
    missing_steps,
    extra_steps,
    order_mismatches,
    total_video_steps,
    total_sop_steps,
    generated_at,
    linked_sop,
  } = report;

  const scorePercentage = Math.round(alignment_score * 100);
  const scoreClasses = getScoreClasses(alignment_score);

  const formattedDate = useMemo(() => {
    try {
      return new Date(generated_at).toLocaleString();
    } catch {
      return generated_at;
    }
  }, [generated_at]);

  return (
    <div
      className="border border-border rounded-lg p-4 space-y-4 bg-card"
      aria-label="Alignment summary"
    >
      {/* Score and SOP link row */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        {/* Alignment score */}
        <div className="flex items-center gap-2">
          {getScoreIcon(alignment_score)}
          <span
            className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${scoreClasses.bg} ${scoreClasses.text}`}
            aria-label={`Alignment score: ${scorePercentage}%`}
          >
            {scorePercentage}% Alignment
          </span>
        </div>

        {/* Linked SOP */}
        {linked_sop && (
          <a
            href={linked_sop.link}
            className="flex items-center gap-1.5 text-sm text-primary hover:underline"
            aria-label={`Linked SOP: ${linked_sop.title}`}
          >
            <FileText className="h-4 w-4" aria-hidden="true" />
            <span>{linked_sop.title} (v{linked_sop.version})</span>
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>

      {/* Step counts grid */}
      <div className="grid grid-cols-3 sm:grid-cols-7 gap-2 text-center">
        <div className="border border-border rounded-md p-2">
          <p className="text-lg font-bold" aria-label="Video steps count">{total_video_steps}</p>
          <p className="text-xs text-muted-foreground">Video Steps</p>
        </div>
        <div className="border border-border rounded-md p-2">
          <p className="text-lg font-bold" aria-label="SOP steps count">{total_sop_steps}</p>
          <p className="text-xs text-muted-foreground">SOP Steps</p>
        </div>
        <div className="border border-border rounded-md p-2">
          <p className="text-lg font-bold text-green-600 dark:text-green-400" aria-label="Matched steps count">
            {matched_steps.length}
          </p>
          <p className="text-xs text-muted-foreground">Matched</p>
        </div>
        <div className="border border-border rounded-md p-2">
          <p className="text-lg font-bold text-red-600 dark:text-red-400" aria-label="Missing steps count">
            {missing_steps.length}
          </p>
          <p className="text-xs text-muted-foreground">Missing</p>
        </div>
        <div className="border border-border rounded-md p-2">
          <p className="text-lg font-bold text-orange-600 dark:text-orange-400" aria-label="Extra steps count">
            {extra_steps.length}
          </p>
          <p className="text-xs text-muted-foreground">Extra</p>
        </div>
        <div className="border border-border rounded-md p-2">
          <p className="text-lg font-bold text-yellow-600 dark:text-yellow-400" aria-label="Reordered steps count">
            {order_mismatches.length}
          </p>
          <p className="text-xs text-muted-foreground">Reordered</p>
        </div>
        <div className="border border-border rounded-md p-2 col-span-3 sm:col-span-1">
          <div className="flex items-center justify-center gap-1">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          </div>
          <p className="text-xs text-muted-foreground mt-0.5" aria-label={`Generated on ${formattedDate}`}>
            {formattedDate}
          </p>
        </div>
      </div>
    </div>
  );
}
