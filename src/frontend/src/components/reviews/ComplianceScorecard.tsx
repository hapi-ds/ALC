import { useEffect } from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useReviewStore } from "@/stores/reviewStore";
import type { ComplianceScorecard as ScorecardData } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Risk band configuration
// ---------------------------------------------------------------------------

interface RiskBandConfig {
  label: string;
  color: string;
  bgColor: string;
  gaugeColor: string;
}

const RISK_BANDS: Record<string, RiskBandConfig> = {
  Excellent: {
    label: "Excellent",
    color: "text-green-700",
    bgColor: "bg-green-100",
    gaugeColor: "#16a34a",
  },
  Good: {
    label: "Good",
    color: "text-blue-700",
    bgColor: "bg-blue-100",
    gaugeColor: "#2563eb",
  },
  "Needs Attention": {
    label: "Needs Attention",
    color: "text-yellow-700",
    bgColor: "bg-yellow-100",
    gaugeColor: "#ca8a04",
  },
  "At Risk": {
    label: "At Risk",
    color: "text-orange-700",
    bgColor: "bg-orange-100",
    gaugeColor: "#ea580c",
  },
  Critical: {
    label: "Critical",
    color: "text-red-700",
    bgColor: "bg-red-100",
    gaugeColor: "#dc2626",
  },
};

const DEFAULT_BAND: RiskBandConfig = {
  label: "Unknown",
  color: "text-gray-700",
  bgColor: "bg-gray-100",
  gaugeColor: "#6b7280",
};

// ---------------------------------------------------------------------------
// Gauge SVG component
// ---------------------------------------------------------------------------

interface GaugeProps {
  score: number;
  color: string;
}

function Gauge({ score, color }: GaugeProps) {
  // Semi-circle gauge: arc from 180° to 0° (left to right)
  const radius = 80;
  const strokeWidth = 14;
  const cx = 100;
  const cy = 95;

  // Arc path for the background track (full semi-circle)
  const startAngle = Math.PI;
  const endAngle = 0;
  const bgStartX = cx + radius * Math.cos(startAngle);
  const bgStartY = cy - radius * Math.sin(startAngle);
  const bgEndX = cx + radius * Math.cos(endAngle);
  const bgEndY = cy - radius * Math.sin(endAngle);
  const bgPath = `M ${bgStartX} ${bgStartY} A ${radius} ${radius} 0 0 1 ${bgEndX} ${bgEndY}`;

  // Arc path for the filled portion based on score (0-100)
  const clampedScore = Math.max(0, Math.min(100, score));
  const fillAngle = Math.PI - (clampedScore / 100) * Math.PI;
  const fillEndX = cx + radius * Math.cos(fillAngle);
  const fillEndY = cy - radius * Math.sin(fillAngle);
  const largeArc = clampedScore > 50 ? 1 : 0;
  const fillPath = `M ${bgStartX} ${bgStartY} A ${radius} ${radius} 0 ${largeArc} 1 ${fillEndX} ${fillEndY}`;

  return (
    <svg
      viewBox="0 0 200 110"
      className="w-full max-w-[240px] mx-auto"
      role="img"
      aria-label={`Compliance score gauge showing ${clampedScore.toFixed(1)} out of 100`}
    >
      {/* Background track */}
      <path
        d={bgPath}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      {/* Filled arc */}
      {clampedScore > 0 && (
        <path
          d={fillPath}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
      )}
      {/* Score text */}
      <text
        x={cx}
        y={cy - 10}
        textAnchor="middle"
        className="text-3xl font-bold"
        fill="currentColor"
        fontSize="28"
      >
        {clampedScore.toFixed(1)}
      </text>
      <text
        x={cx}
        y={cy + 12}
        textAnchor="middle"
        className="text-xs"
        fill="#6b7280"
        fontSize="12"
      >
        / 100
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Trend indicator component
// ---------------------------------------------------------------------------

interface TrendIndicatorProps {
  trend: ScorecardData["trend"];
}

function TrendIndicator({ trend }: TrendIndicatorProps) {
  switch (trend) {
    case "improving":
      return (
        <span className="inline-flex items-center gap-1 text-green-700" aria-label="Trend: improving">
          <TrendingUp className="h-4 w-4" aria-hidden="true" />
          <span className="text-sm font-medium">Improving</span>
        </span>
      );
    case "declining":
      return (
        <span className="inline-flex items-center gap-1 text-red-700" aria-label="Trend: declining">
          <TrendingDown className="h-4 w-4" aria-hidden="true" />
          <span className="text-sm font-medium">Declining</span>
        </span>
      );
    case "stable":
    default:
      return (
        <span className="inline-flex items-center gap-1 text-gray-500" aria-label="Trend: stable">
          <Minus className="h-4 w-4" aria-hidden="true" />
          <span className="text-sm font-medium">Stable</span>
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Bar chart for score by document type
// ---------------------------------------------------------------------------

interface DocumentTypeBarChartProps {
  data: Record<string, number>;
}

function DocumentTypeBarChart({ data }: DocumentTypeBarChartProps) {
  const entries = Object.entries(data);

  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">
        No document type data available
      </p>
    );
  }

  const maxScore = Math.max(...entries.map(([, score]) => score), 1);

  return (
    <div className="space-y-2" role="list" aria-label="Score by document type">
      {entries.map(([docType, score]) => {
        const widthPercent = (score / maxScore) * 100;
        const band = getRiskBandForScore(score);

        return (
          <div key={docType} role="listitem" className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="truncate font-medium">{docType}</span>
              <span className="text-muted-foreground ml-2 shrink-0">
                {score.toFixed(1)}
              </span>
            </div>
            <div className="h-2 w-full rounded-full bg-gray-100">
              <div
                className="h-2 rounded-full transition-all duration-300"
                style={{
                  width: `${widthPercent}%`,
                  backgroundColor: band.gaugeColor,
                }}
                role="progressbar"
                aria-valuenow={score}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`${docType}: ${score.toFixed(1)}`}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getRiskBandForScore(score: number): RiskBandConfig {
  if (score >= 90) return RISK_BANDS["Excellent"];
  if (score >= 75) return RISK_BANDS["Good"];
  if (score >= 50) return RISK_BANDS["Needs Attention"];
  if (score >= 25) return RISK_BANDS["At Risk"];
  return RISK_BANDS["Critical"];
}

// ---------------------------------------------------------------------------
// ComplianceScorecard component
// ---------------------------------------------------------------------------

export function ComplianceScorecard() {
  const { scorecard, isLoadingScorecard, scorecardError, fetchScorecard } = useReviewStore();

  useEffect(() => {
    fetchScorecard();
  }, [fetchScorecard]);

  // Loading state
  if (isLoadingScorecard) {
    return (
      <div
        className="rounded-lg border border-border p-6 text-center"
        aria-label="Compliance scorecard loading"
      >
        <div className="animate-pulse space-y-4">
          <div className="h-24 w-24 mx-auto rounded-full bg-gray-200" />
          <div className="h-4 w-32 mx-auto rounded bg-gray-200" />
          <div className="h-3 w-48 mx-auto rounded bg-gray-200" />
        </div>
      </div>
    );
  }

  // Error state
  if (scorecardError) {
    return (
      <div
        className="rounded-lg border border-border p-6 text-center"
        aria-label="Compliance scorecard error"
      >
        <p className="text-destructive text-sm">Error: {scorecardError}</p>
        <button
          type="button"
          onClick={() => fetchScorecard()}
          className="mt-2 text-sm underline hover:no-underline"
        >
          Retry
        </button>
      </div>
    );
  }

  // No data state
  if (!scorecard) {
    return (
      <div
        className="rounded-lg border border-border p-6 text-center"
        aria-label="Compliance scorecard empty"
      >
        <p className="text-muted-foreground text-sm">No scorecard data available</p>
      </div>
    );
  }

  const band = RISK_BANDS[scorecard.risk_band] ?? DEFAULT_BAND;

  return (
    <div
      className="rounded-lg border border-border p-6 space-y-6"
      aria-label="Compliance scorecard"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Audit Readiness</h3>
        <TrendIndicator trend={scorecard.trend} />
      </div>

      {/* Gauge */}
      <Gauge score={scorecard.overall_score} color={band.gaugeColor} />

      {/* Risk band badge */}
      <div className="text-center">
        <span
          className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium ${band.bgColor} ${band.color}`}
          aria-label={`Risk band: ${band.label}`}
        >
          {band.label}
        </span>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4 text-center border-t border-border pt-4">
        <div>
          <p className="text-2xl font-bold">{scorecard.total_documents_reviewed}</p>
          <p className="text-xs text-muted-foreground">Reviewed</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-red-600">
            {scorecard.documents_with_critical_findings}
          </p>
          <p className="text-xs text-muted-foreground">Critical</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-yellow-600">
            {scorecard.documents_with_open_action_items}
          </p>
          <p className="text-xs text-muted-foreground">Open Items</p>
        </div>
      </div>

      {/* Document type breakdown */}
      <div className="border-t border-border pt-4">
        <h4 className="text-sm font-medium mb-3">Score by Document Type</h4>
        <DocumentTypeBarChart data={scorecard.score_by_document_type} />
      </div>

      {/* Last updated */}
      <p className="text-xs text-muted-foreground text-center">
        Last updated: {new Date(scorecard.last_updated).toLocaleString()}
      </p>
    </div>
  );
}
