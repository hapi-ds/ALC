import { useMemo } from "react";
import { AlertTriangle, CheckCircle2, XCircle, Info } from "lucide-react";
import type {
  DiscrepancyReport,
  DiscrepancySeverity,
  MatchedStep,
  DiscrepancyStep,
  OrderMismatch,
} from "@/types/videoAlignment";

/**
 * Props for the VideoAlignment component.
 */
export interface VideoAlignmentProps {
  /** The discrepancy report data from the API */
  report: DiscrepancyReport;
}

// ---------------------------------------------------------------------------
// Severity color utilities
// ---------------------------------------------------------------------------

const SEVERITY_COLORS: Record<DiscrepancySeverity, { bg: string; text: string; border: string }> = {
  critical: {
    bg: "bg-red-50 dark:bg-red-950/30",
    text: "text-red-700 dark:text-red-400",
    border: "border-red-200 dark:border-red-800",
  },
  major: {
    bg: "bg-orange-50 dark:bg-orange-950/30",
    text: "text-orange-700 dark:text-orange-400",
    border: "border-orange-200 dark:border-orange-800",
  },
  minor: {
    bg: "bg-yellow-50 dark:bg-yellow-950/30",
    text: "text-yellow-700 dark:text-yellow-400",
    border: "border-yellow-200 dark:border-yellow-800",
  },
};

/**
 * Get the color class for the alignment score badge.
 * - Green: 80%+ (good alignment)
 * - Yellow: 50-79% (moderate alignment)
 * - Red: <50% (poor alignment, requires review)
 */
function getScoreBadgeClasses(score: number): string {
  const percentage = score * 100;
  if (percentage >= 80) {
    return "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300";
  }
  if (percentage >= 50) {
    return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300";
  }
  return "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300";
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

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Severity legend displayed at the top of the report */
function SeverityLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs" aria-label="Severity legend">
      <span className="font-medium text-muted-foreground">Severity:</span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 h-3 rounded-sm bg-red-500" aria-hidden="true" />
        <span>Critical</span>
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 h-3 rounded-sm bg-orange-500" aria-hidden="true" />
        <span>Major</span>
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 h-3 rounded-sm bg-yellow-500" aria-hidden="true" />
        <span>Minor</span>
      </span>
    </div>
  );
}

/** Alignment score badge */
function AlignmentScoreBadge({ score }: { score: number }) {
  const percentage = Math.round(score * 100);
  const badgeClasses = getScoreBadgeClasses(score);

  return (
    <div className="flex items-center gap-2">
      {getScoreIcon(score)}
      <span
        className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold ${badgeClasses}`}
        aria-label={`Alignment score: ${percentage}%`}
      >
        {percentage}%
      </span>
    </div>
  );
}

/** A single matched step row with visual connector */
function MatchedStepRow({ step, index }: { step: MatchedStep; index: number }) {
  return (
    <div
      className="grid grid-cols-[1fr_auto_1fr] gap-2 items-stretch border border-border rounded-md p-3"
      aria-label={`Matched pair ${index + 1}`}
    >
      {/* Video step (left) */}
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">Video Step</span>
        <p className="text-sm">{step.video_step_description}</p>
        <span className="text-xs text-muted-foreground">
          {formatTimestamp(step.video_timestamp_start)} – {formatTimestamp(step.video_timestamp_end)}
        </span>
      </div>

      {/* Visual connector (center) */}
      <div className="flex flex-col items-center justify-center px-2">
        <div className="w-px flex-1 bg-green-400 dark:bg-green-600" aria-hidden="true" />
        <span
          className="my-1 inline-flex items-center justify-center w-8 h-8 rounded-full bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300 text-xs font-medium"
          aria-label={`Similarity: ${Math.round(step.similarity_score * 100)}%`}
        >
          {Math.round(step.similarity_score * 100)}%
        </span>
        <div className="w-px flex-1 bg-green-400 dark:bg-green-600" aria-hidden="true" />
      </div>

      {/* SOP step (right) */}
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">SOP Step</span>
        <p className="text-sm">{step.sop_step_text}</p>
      </div>
    </div>
  );
}

/** A discrepancy step row (missing or extra) */
function DiscrepancyStepRow({ step, type }: { step: DiscrepancyStep; type: "missing" | "extra" }) {
  const colors = SEVERITY_COLORS[step.severity];
  const label = type === "missing" ? "Missing from SOP" : "Extra in SOP";

  return (
    <div
      className={`border rounded-md p-3 ${colors.bg} ${colors.border}`}
      aria-label={`${label}: ${step.step_description}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-semibold uppercase ${colors.text}`}>
              {step.severity}
            </span>
            <span className="text-xs text-muted-foreground">
              {label}
            </span>
          </div>
          <p className="text-sm">{step.step_description}</p>
          {step.recommendation && (
            <p className="text-xs text-muted-foreground mt-1 italic">
              {step.recommendation}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** An order mismatch row */
function OrderMismatchRow({ mismatch }: { mismatch: OrderMismatch }) {
  const colors = SEVERITY_COLORS[mismatch.severity];

  return (
    <div
      className={`grid grid-cols-[1fr_auto_1fr] gap-2 items-stretch border rounded-md p-3 ${colors.bg} ${colors.border}`}
      aria-label={`Order mismatch: video position ${mismatch.video_position}, SOP position ${mismatch.sop_position}`}
    >
      {/* Video step (left) */}
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          Video Step (position {mismatch.video_position})
        </span>
        <p className="text-sm">{mismatch.video_step_description}</p>
      </div>

      {/* Connector with mismatch indicator */}
      <div className="flex flex-col items-center justify-center px-2">
        <div className={`w-px flex-1 ${colors.border.replace("border-", "bg-")}`} aria-hidden="true" />
        <span
          className={`my-1 inline-flex items-center justify-center w-8 h-8 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}
          aria-label="Order mismatch"
        >
          ↕
        </span>
        <div className={`w-px flex-1 ${colors.border.replace("border-", "bg-")}`} aria-hidden="true" />
      </div>

      {/* SOP step (right) */}
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">
          SOP Step (position {mismatch.sop_position})
        </span>
        <p className="text-sm">{mismatch.sop_step_text}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format seconds to MM:SS */
function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * VideoAlignment displays the Video Alignment section for a Video_Document
 * detail view. Shows the latest Discrepancy_Report with:
 * - Alignment score percentage badge (green 80%+, yellow 50-79%, red <50%)
 * - Side-by-side comparison view (video steps left, SOP steps right)
 * - Visual connectors for matched pairs
 * - Color-coded discrepancies (red=critical, orange=major, yellow=minor)
 * - Severity legend
 *
 * Validates: Requirements 11.1, 11.2, 11.3
 */
export function VideoAlignment({ report }: VideoAlignmentProps) {
  const {
    alignment_score,
    matched_steps,
    missing_steps,
    extra_steps,
    order_mismatches,
    total_video_steps,
    total_sop_steps,
    generated_at,
    requires_review,
  } = report;

  const formattedDate = useMemo(() => {
    try {
      return new Date(generated_at).toLocaleString();
    } catch {
      return generated_at;
    }
  }, [generated_at]);

  const hasDiscrepancies = missing_steps.length > 0 || extra_steps.length > 0 || order_mismatches.length > 0;

  return (
    <section aria-labelledby="video-alignment-heading" className="space-y-6">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <h3 id="video-alignment-heading" className="text-lg font-semibold">
          Video Alignment
        </h3>
        <AlignmentScoreBadge score={alignment_score} />
      </div>

      {/* Requires review banner */}
      {requires_review && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 rounded-md bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400"
        >
          <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            This alignment requires review. The alignment score is below 50%, indicating significant discrepancies between the video and SOP.
          </span>
        </div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div className="border border-border rounded-md p-3">
          <p className="text-2xl font-bold">{total_video_steps}</p>
          <p className="text-xs text-muted-foreground">Video Steps</p>
        </div>
        <div className="border border-border rounded-md p-3">
          <p className="text-2xl font-bold">{total_sop_steps}</p>
          <p className="text-xs text-muted-foreground">SOP Steps</p>
        </div>
        <div className="border border-border rounded-md p-3">
          <p className="text-2xl font-bold">{matched_steps.length}</p>
          <p className="text-xs text-muted-foreground">Matched</p>
        </div>
        <div className="border border-border rounded-md p-3">
          <p className="text-2xl font-bold">
            {missing_steps.length + extra_steps.length + order_mismatches.length}
          </p>
          <p className="text-xs text-muted-foreground">Discrepancies</p>
        </div>
      </div>

      {/* Report generation date */}
      <p className="text-xs text-muted-foreground">
        Report generated: {formattedDate}
      </p>

      {/* Severity legend */}
      {hasDiscrepancies && <SeverityLegend />}

      {/* Matched steps - side-by-side comparison */}
      {matched_steps.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground">
            Matched Steps ({matched_steps.length})
          </h4>
          <div className="space-y-2">
            {matched_steps.map((step, idx) => (
              <MatchedStepRow key={`matched-${idx}`} step={step} index={idx} />
            ))}
          </div>
        </div>
      )}

      {/* Order mismatches - side-by-side with mismatch indicator */}
      {order_mismatches.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground">
            Order Mismatches ({order_mismatches.length})
          </h4>
          <div className="space-y-2">
            {order_mismatches.map((mismatch, idx) => (
              <OrderMismatchRow key={`mismatch-${idx}`} mismatch={mismatch} />
            ))}
          </div>
        </div>
      )}

      {/* Missing steps (in video but not SOP) */}
      {missing_steps.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground">
            Missing from SOP ({missing_steps.length})
          </h4>
          <div className="space-y-2">
            {missing_steps.map((step, idx) => (
              <DiscrepancyStepRow key={`missing-${idx}`} step={step} type="missing" />
            ))}
          </div>
        </div>
      )}

      {/* Extra steps (in SOP but not video) */}
      {extra_steps.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-medium text-muted-foreground">
            Extra in SOP ({extra_steps.length})
          </h4>
          <div className="space-y-2">
            {extra_steps.map((step, idx) => (
              <DiscrepancyStepRow key={`extra-${idx}`} step={step} type="extra" />
            ))}
          </div>
        </div>
      )}

      {/* No discrepancies message */}
      {!hasDiscrepancies && matched_steps.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground border border-border rounded-md">
          <CheckCircle2 className="h-6 w-6 mx-auto mb-2 text-green-500" aria-hidden="true" />
          <p>No discrepancies found. All video steps align with the SOP.</p>
        </div>
      )}
    </section>
  );
}
