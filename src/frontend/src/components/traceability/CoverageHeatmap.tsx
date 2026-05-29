/**
 * CoverageHeatmap
 *
 * Grid visualization of source × target document coverage percentages.
 * - Rows = source documents, Columns = target documents
 * - Cells = coverage percentage
 * - Color intensity: dark green (100%) → yellow (50%) → red (0%)
 * - Tooltip on hover: exact coverage percentage and orphan count
 *
 * Requirements: 8.3
 */

import { useMemo, useState } from "react";
import type { TraceabilityMatrix } from "@/types/traceability";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CoverageHeatmapProps {
  matrices: TraceabilityMatrix[];
}

interface CellData {
  coveragePercent: number;
  orphanCount: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Interpolate between red (0%) → yellow (50%) → green (100%)
 */
function getCellColor(percent: number): string {
  if (percent >= 80) return "bg-green-600";
  if (percent >= 60) return "bg-green-400";
  if (percent >= 40) return "bg-yellow-400";
  if (percent >= 20) return "bg-orange-400";
  return "bg-red-400";
}

function getCellTextColor(percent: number): string {
  if (percent >= 60) return "text-white";
  return "text-gray-900";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CoverageHeatmap({ matrices }: CoverageHeatmapProps) {
  const [hoveredCell, setHoveredCell] = useState<{
    row: string;
    col: string;
    data: CellData;
    x: number;
    y: number;
  } | null>(null);

  // Build the grid data from matrices
  const { sourceDocIds, targetDocIds, grid } = useMemo(() => {
    const sourceSet = new Set<string>();
    const targetSet = new Set<string>();
    const cellMap = new Map<string, CellData>();

    for (const matrix of matrices) {
      if (matrix.status === "failed") continue;

      for (const sourceUuid of matrix.source_document_uuids) {
        sourceSet.add(sourceUuid);
        for (const targetUuid of matrix.target_document_uuids) {
          targetSet.add(targetUuid);

          const key = `${sourceUuid}:${targetUuid}`;
          // Use the latest matrix data (matrices should be sorted newest first)
          if (!cellMap.has(key)) {
            // Compute per-pair coverage from links
            const pairLinks = matrix.traceability_links.filter(
              (l) =>
                l.source_document_uuid === sourceUuid &&
                l.target_document_uuid === targetUuid,
            );
            const pairOrphans = matrix.orphan_requirements.filter(
              (o) => o.source_document_uuid === sourceUuid,
            );

            const totalReqs = pairLinks.length + pairOrphans.length;
            const coverage = totalReqs > 0 ? (pairLinks.length / totalReqs) * 100 : 0;

            cellMap.set(key, {
              coveragePercent: Math.round(coverage * 100) / 100,
              orphanCount: pairOrphans.length,
            });
          }
        }
      }
    }

    return {
      sourceDocIds: Array.from(sourceSet).sort(),
      targetDocIds: Array.from(targetSet).sort(),
      grid: cellMap,
    };
  }, [matrices]);

  if (sourceDocIds.length === 0 || targetDocIds.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 text-center text-muted-foreground">
        <p className="text-sm">
          No coverage data available. Generate a traceability matrix to see the heatmap.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">Coverage Heatmap</h3>
      <div className="overflow-x-auto border border-border rounded-lg p-4">
        <div className="relative">
          <table className="text-xs">
            <thead>
              <tr>
                <th className="px-2 py-1 text-left text-muted-foreground font-medium">
                  Source \ Target
                </th>
                {targetDocIds.map((targetId) => (
                  <th
                    key={targetId}
                    className="px-2 py-1 text-center text-muted-foreground font-medium max-w-[60px] truncate"
                    title={targetId}
                  >
                    {targetId.slice(0, 6)}…
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sourceDocIds.map((sourceId) => (
                <tr key={sourceId}>
                  <td
                    className="px-2 py-1 font-medium text-muted-foreground max-w-[80px] truncate"
                    title={sourceId}
                  >
                    {sourceId.slice(0, 6)}…
                  </td>
                  {targetDocIds.map((targetId) => {
                    const key = `${sourceId}:${targetId}`;
                    const data = grid.get(key) || { coveragePercent: 0, orphanCount: 0 };
                    return (
                      <td
                        key={targetId}
                        className={`px-2 py-1 text-center cursor-pointer rounded ${getCellColor(data.coveragePercent)} ${getCellTextColor(data.coveragePercent)}`}
                        onMouseEnter={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();
                          setHoveredCell({
                            row: sourceId,
                            col: targetId,
                            data,
                            x: rect.left + rect.width / 2,
                            y: rect.top,
                          });
                        }}
                        onMouseLeave={() => setHoveredCell(null)}
                        aria-label={`Coverage ${data.coveragePercent.toFixed(1)}% for ${sourceId} → ${targetId}`}
                      >
                        {data.coveragePercent.toFixed(0)}%
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>

          {/* Tooltip */}
          {hoveredCell && (
            <div
              className="fixed z-50 bg-popover border border-border rounded-md shadow-md px-3 py-2 text-xs pointer-events-none"
              style={{
                left: hoveredCell.x,
                top: hoveredCell.y - 60,
                transform: "translateX(-50%)",
              }}
              role="tooltip"
            >
              <p className="font-medium">
                {hoveredCell.row} → {hoveredCell.col}
              </p>
              <p>Coverage: {hoveredCell.data.coveragePercent.toFixed(1)}%</p>
              <p>Orphan requirements: {hoveredCell.data.orphanCount}</p>
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-2 mt-4 text-xs text-muted-foreground">
          <span>0%</span>
          <div className="flex h-3">
            <div className="w-6 bg-red-400 rounded-l" />
            <div className="w-6 bg-orange-400" />
            <div className="w-6 bg-yellow-400" />
            <div className="w-6 bg-green-400" />
            <div className="w-6 bg-green-600 rounded-r" />
          </div>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}
