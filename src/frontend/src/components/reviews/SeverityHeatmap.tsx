/**
 * SeverityHeatmap — Grid visualization of finding density by chapter and severity.
 *
 * Renders a heatmap where:
 *   - Y-axis: document chapters/sections
 *   - X-axis: severity levels (Critical, Major, Minor, Informational)
 *   - Cell color intensity: number of findings for that (chapter, severity) pair
 *
 * Colors follow the spec convention:
 *   - Critical: red
 *   - Major: orange
 *   - Minor: yellow
 *   - Informational: blue
 *
 * Validates: Requirements 11.4, 5.3
 */

import { useMemo } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A single finding entry used to build the heatmap. */
export interface HeatmapFinding {
  severity: "Critical" | "Major" | "Minor" | "Informational";
  chapter: string;
}

export interface SeverityHeatmapProps {
  /** Array of findings from agent reports to visualize. */
  findings: HeatmapFinding[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Ordered severity levels for the X-axis. */
const SEVERITY_LEVELS = ["Critical", "Major", "Minor", "Informational"] as const;

type SeverityLevel = (typeof SEVERITY_LEVELS)[number];

/** Header text color per severity level. */
const SEVERITY_HEADER_COLORS: Record<SeverityLevel, string> = {
  Critical: "text-red-700",
  Major: "text-orange-700",
  Minor: "text-yellow-700",
  Informational: "text-blue-700",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Get the Tailwind background color class for a severity at a given intensity.
 * Uses fixed color shades with opacity for intensity variation.
 */
function getCellColorClass(severity: SeverityLevel, count: number, maxCount: number): string {
  if (count === 0) return "bg-gray-50";

  const colorMap: Record<SeverityLevel, string[]> = {
    Critical: ["bg-red-100", "bg-red-200", "bg-red-400", "bg-red-600"],
    Major: ["bg-orange-100", "bg-orange-200", "bg-orange-400", "bg-orange-600"],
    Minor: ["bg-yellow-100", "bg-yellow-200", "bg-yellow-400", "bg-yellow-600"],
    Informational: ["bg-blue-100", "bg-blue-200", "bg-blue-400", "bg-blue-600"],
  };

  if (maxCount === 0) return colorMap[severity][0];
  const ratio = count / maxCount;
  if (ratio <= 0.25) return colorMap[severity][0];
  if (ratio <= 0.5) return colorMap[severity][1];
  if (ratio <= 0.75) return colorMap[severity][2];
  return colorMap[severity][3];
}

/**
 * Get appropriate text color for contrast against the cell background.
 */
function getCellTextClass(severity: SeverityLevel, count: number, maxCount: number): string {
  if (count === 0) return "text-gray-400";
  if (maxCount === 0) return "text-gray-700";
  const ratio = count / maxCount;
  if (ratio > 0.5) return "text-white";
  return "text-gray-700";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SeverityHeatmap({ findings }: SeverityHeatmapProps) {
  /** Build the heatmap data: count findings per (chapter, severity) pair. */
  const { chapters, grid, maxCount } = useMemo(() => {
    const countMap = new Map<string, Record<SeverityLevel, number>>();

    for (const finding of findings) {
      const chapter = finding.chapter || "Unknown";
      if (!countMap.has(chapter)) {
        countMap.set(chapter, { Critical: 0, Major: 0, Minor: 0, Informational: 0 });
      }
      const row = countMap.get(chapter)!;
      if (SEVERITY_LEVELS.includes(finding.severity)) {
        row[finding.severity]++;
      }
    }

    // Sort chapters alphabetically for consistent display
    const sortedChapters = [...countMap.keys()].sort();

    // Find the maximum count for intensity scaling
    let max = 0;
    for (const row of countMap.values()) {
      for (const count of Object.values(row)) {
        if (count > max) max = count;
      }
    }

    return { chapters: sortedChapters, grid: countMap, maxCount: max };
  }, [findings]);

  // Empty state
  if (findings.length === 0 || chapters.length === 0) {
    return (
      <div
        className="rounded-lg border border-border p-6 text-center text-muted-foreground"
        role="region"
        aria-label="Severity heatmap"
      >
        <p>No findings to display</p>
      </div>
    );
  }

  return (
    <div role="region" aria-label="Severity heatmap" className="space-y-3">
      <h3 className="text-sm font-medium text-foreground">Finding Severity Heatmap</h3>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-sm" aria-label="Severity heatmap grid">
          <thead>
            <tr>
              <th
                className="border-b border-r border-border bg-muted/50 px-3 py-2 text-left text-xs font-medium text-muted-foreground"
                scope="col"
              >
                Chapter / Section
              </th>
              {SEVERITY_LEVELS.map((severity) => (
                <th
                  key={severity}
                  className={`border-b border-border bg-muted/50 px-3 py-2 text-center text-xs font-medium ${SEVERITY_HEADER_COLORS[severity]}`}
                  scope="col"
                >
                  {severity}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {chapters.map((chapter) => {
              const row = grid.get(chapter)!;
              return (
                <tr key={chapter} className="border-b border-border last:border-b-0">
                  <td
                    className="border-r border-border px-3 py-2 text-xs font-medium text-foreground"
                    title={chapter}
                  >
                    <span className="block max-w-[200px] truncate">{chapter}</span>
                  </td>
                  {SEVERITY_LEVELS.map((severity) => {
                    const count = row[severity];
                    const colorClass = getCellColorClass(severity, count, maxCount);
                    const textClass = getCellTextClass(severity, count, maxCount);
                    return (
                      <td
                        key={severity}
                        className={`px-3 py-2 text-center text-xs font-medium transition-colors ${colorClass} ${textClass}`}
                        title={`${chapter}: ${count} ${severity.toLowerCase()} finding${count !== 1 ? "s" : ""}`}
                        aria-label={`${chapter}, ${severity}: ${count} finding${count !== 1 ? "s" : ""}`}
                      >
                        {count > 0 ? count : "—"}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground" aria-label="Heatmap legend">
        <span className="font-medium">Intensity:</span>
        <div className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm bg-gray-50 border border-border" />
          <span>None</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm bg-gray-200" />
          <span>Low</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm bg-gray-400" />
          <span>Medium</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm bg-gray-600" />
          <span>High</span>
        </div>
      </div>
    </div>
  );
}
