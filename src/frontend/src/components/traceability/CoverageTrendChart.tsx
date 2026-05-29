/**
 * CoverageTrendChart
 *
 * Line chart of coverage_percentage over time with compliance_readiness_score
 * as a secondary axis. Uses the coverageHistory data from the traceability store.
 *
 * Renders a simple SVG-based chart (no external charting library dependency).
 * - Primary line (blue): coverage percentage (0-100%)
 * - Secondary line (green): compliance readiness score (0-100)
 * - X-axis: time (snapshot dates)
 * - Hover tooltip with exact values
 *
 * Requirements: 8.8
 */

import { useMemo, useState } from "react";
import { useTraceabilityStore } from "@/stores/traceabilityStore";
import type { CoverageSnapshot } from "@/types/traceability";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CHART_WIDTH = 700;
const CHART_HEIGHT = 200;
const PADDING = { top: 20, right: 60, bottom: 40, left: 50 };
const INNER_WIDTH = CHART_WIDTH - PADDING.left - PADDING.right;
const INNER_HEIGHT = CHART_HEIGHT - PADDING.top - PADDING.bottom;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CoverageTrendChart() {
  const { coverageHistory } = useTraceabilityStore();
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Sort snapshots by date ascending for charting
  const sortedSnapshots = useMemo(() => {
    return [...coverageHistory].sort(
      (a, b) =>
        new Date(a.snapshot_date).getTime() - new Date(b.snapshot_date).getTime(),
    );
  }, [coverageHistory]);

  if (sortedSnapshots.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 text-center text-muted-foreground">
        <p className="text-sm">
          No coverage history available yet. Generate matrices to see trends over time.
        </p>
      </div>
    );
  }

  // Compute scales
  const xScale = (index: number) =>
    PADDING.left + (index / Math.max(sortedSnapshots.length - 1, 1)) * INNER_WIDTH;
  const yScale = (value: number) =>
    PADDING.top + INNER_HEIGHT - (value / 100) * INNER_HEIGHT;

  // Build path strings
  const coveragePath = sortedSnapshots
    .map((s, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${yScale(s.coverage_percentage)}`)
    .join(" ");

  const compliancePath = sortedSnapshots
    .map((s, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${yScale(s.compliance_readiness_score)}`)
    .join(" ");

  // X-axis labels (show max 6 labels)
  const labelStep = Math.max(1, Math.floor(sortedSnapshots.length / 6));
  const xLabels = sortedSnapshots
    .map((s, i) => ({ index: i, label: formatDate(s.snapshot_date) }))
    .filter((_, i) => i % labelStep === 0 || i === sortedSnapshots.length - 1);

  return (
    <div className="border border-border rounded-lg p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Coverage Trend</h3>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-blue-500 inline-block rounded" />
            Coverage %
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-0.5 bg-green-500 inline-block rounded" />
            Compliance Score
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <svg
          width={CHART_WIDTH}
          height={CHART_HEIGHT}
          className="w-full max-w-full"
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
          role="img"
          aria-label="Coverage trend chart showing coverage percentage and compliance score over time"
        >
          {/* Grid lines */}
          {[0, 25, 50, 75, 100].map((val) => (
            <g key={val}>
              <line
                x1={PADDING.left}
                y1={yScale(val)}
                x2={CHART_WIDTH - PADDING.right}
                y2={yScale(val)}
                stroke="currentColor"
                strokeOpacity={0.1}
                strokeDasharray="4 2"
              />
              <text
                x={PADDING.left - 8}
                y={yScale(val) + 4}
                textAnchor="end"
                className="fill-muted-foreground"
                fontSize={10}
              >
                {val}%
              </text>
            </g>
          ))}

          {/* X-axis labels */}
          {xLabels.map(({ index, label }) => (
            <text
              key={index}
              x={xScale(index)}
              y={CHART_HEIGHT - 8}
              textAnchor="middle"
              className="fill-muted-foreground"
              fontSize={10}
            >
              {label}
            </text>
          ))}

          {/* Coverage line */}
          <path
            d={coveragePath}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Compliance line */}
          <path
            d={compliancePath}
            fill="none"
            stroke="#22c55e"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="6 3"
          />

          {/* Data points (coverage) */}
          {sortedSnapshots.map((s, i) => (
            <circle
              key={`cov-${i}`}
              cx={xScale(i)}
              cy={yScale(s.coverage_percentage)}
              r={hoveredIndex === i ? 5 : 3}
              fill="#3b82f6"
              className="cursor-pointer"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
            />
          ))}

          {/* Data points (compliance) */}
          {sortedSnapshots.map((s, i) => (
            <circle
              key={`comp-${i}`}
              cx={xScale(i)}
              cy={yScale(s.compliance_readiness_score)}
              r={hoveredIndex === i ? 5 : 3}
              fill="#22c55e"
              className="cursor-pointer"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
            />
          ))}

          {/* Hover tooltip */}
          {hoveredIndex !== null && sortedSnapshots[hoveredIndex] && (
            <g>
              {/* Vertical line */}
              <line
                x1={xScale(hoveredIndex)}
                y1={PADDING.top}
                x2={xScale(hoveredIndex)}
                y2={PADDING.top + INNER_HEIGHT}
                stroke="currentColor"
                strokeOpacity={0.3}
                strokeDasharray="2 2"
              />
              {/* Tooltip box */}
              <rect
                x={Math.min(xScale(hoveredIndex) + 10, CHART_WIDTH - 160)}
                y={PADDING.top}
                width={140}
                height={52}
                rx={4}
                className="fill-background stroke-border"
              />
              <text
                x={Math.min(xScale(hoveredIndex) + 18, CHART_WIDTH - 152)}
                y={PADDING.top + 16}
                fontSize={10}
                className="fill-foreground"
              >
                {formatDate(sortedSnapshots[hoveredIndex].snapshot_date)}
              </text>
              <text
                x={Math.min(xScale(hoveredIndex) + 18, CHART_WIDTH - 152)}
                y={PADDING.top + 30}
                fontSize={10}
                fill="#3b82f6"
              >
                Coverage: {sortedSnapshots[hoveredIndex].coverage_percentage.toFixed(1)}%
              </text>
              <text
                x={Math.min(xScale(hoveredIndex) + 18, CHART_WIDTH - 152)}
                y={PADDING.top + 44}
                fontSize={10}
                fill="#22c55e"
              >
                Compliance: {sortedSnapshots[hoveredIndex].compliance_readiness_score.toFixed(1)}
              </text>
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
