/**
 * DependencyGraphView
 *
 * Interactive SVG-based dependency graph visualization. Renders documents
 * as nodes and dependencies as directed edges. Color-coded by severity.
 * Supports filtering by dependency_type, zooming/panning.
 * Limited to 200 nodes max with truncation message.
 *
 * Requirements: 10.2, 10.3
 */

import { useState, useMemo, useRef, useCallback } from "react";
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DependencyEdge, DependencyType } from "@/types/impactAnalysis";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_NODES = 200;
const NODE_RADIUS = 24;
const GRAPH_WIDTH = 900;
const GRAPH_HEIGHT = 600;

const DEPENDENCY_TYPE_OPTIONS: DependencyType[] = [
  "validates",
  "references",
  "implements",
  "trains_on",
  "derived_from",
];

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ef4444", // red
  major: "#f97316", // orange
  minor: "#eab308", // yellow
  none: "#22c55e", // green
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GraphNode {
  id: string;
  x: number;
  y: number;
  severity: string;
}

interface GraphEdge {
  source: string;
  target: string;
  type: DependencyType;
}

// ---------------------------------------------------------------------------
// Layout helpers
// ---------------------------------------------------------------------------

function computeLayout(
  edges: DependencyEdge[],
  severityMap: Record<string, string>,
): { nodes: GraphNode[]; graphEdges: GraphEdge[] } {
  // Collect unique node IDs
  const nodeIds = new Set<string>();
  for (const edge of edges) {
    nodeIds.add(edge.source_document_uuid);
    nodeIds.add(edge.target_document_uuid);
  }

  // Limit to MAX_NODES
  const nodeArray = Array.from(nodeIds).slice(0, MAX_NODES);

  // Simple circular layout
  const nodes: GraphNode[] = nodeArray.map((id, i) => {
    const angle = (2 * Math.PI * i) / nodeArray.length;
    const radiusX = (GRAPH_WIDTH - 100) / 2.5;
    const radiusY = (GRAPH_HEIGHT - 100) / 2.5;
    return {
      id,
      x: GRAPH_WIDTH / 2 + radiusX * Math.cos(angle),
      y: GRAPH_HEIGHT / 2 + radiusY * Math.sin(angle),
      severity: severityMap[id] || "none",
    };
  });

  const graphEdges: GraphEdge[] = edges
    .filter(
      (e) =>
        nodeArray.includes(e.source_document_uuid) &&
        nodeArray.includes(e.target_document_uuid),
    )
    .map((e) => ({
      source: e.source_document_uuid,
      target: e.target_document_uuid,
      type: e.dependency_type,
    }));

  return { nodes, graphEdges };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface DependencyGraphViewProps {
  edges: DependencyEdge[];
  /** Map of document_uuid → highest severity for color-coding */
  severityMap?: Record<string, string>;
}

export function DependencyGraphView({
  edges,
  severityMap = {},
}: DependencyGraphViewProps) {
  const [filterType, setFilterType] = useState<DependencyType | "">("");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const svgRef = useRef<SVGSVGElement>(null);

  // Filter edges by type
  const filteredEdges = useMemo(() => {
    if (!filterType) return edges;
    return edges.filter((e) => e.dependency_type === filterType);
  }, [edges, filterType]);

  // Compute layout
  const { nodes, graphEdges } = useMemo(
    () => computeLayout(filteredEdges, severityMap),
    [filteredEdges, severityMap],
  );

  // Total unique nodes (before truncation)
  const totalNodes = useMemo(() => {
    const ids = new Set<string>();
    for (const edge of filteredEdges) {
      ids.add(edge.source_document_uuid);
      ids.add(edge.target_document_uuid);
    }
    return ids.size;
  }, [filteredEdges]);

  const isTruncated = totalNodes > MAX_NODES;

  // Node position lookup
  const nodeMap = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const node of nodes) {
      map.set(node.id, node);
    }
    return map;
  }, [nodes]);

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    setZoom((z) => Math.min(z + 0.2, 3));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((z) => Math.max(z - 0.2, 0.4));
  }, []);

  const handleReset = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  // Pan handlers
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      setIsPanning(true);
      setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    },
    [pan],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isPanning) return;
      setPan({ x: e.clientX - panStart.x, y: e.clientY - panStart.y });
    },
    [isPanning, panStart],
  );

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  if (edges.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 text-center text-muted-foreground">
        <p className="text-sm font-medium">No dependency graph data</p>
        <p className="text-xs mt-1">
          Build the dependency graph to visualize document relationships.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Controls */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {/* Filter */}
        <div className="flex items-center gap-2">
          <label
            htmlFor="graph-filter-type"
            className="text-xs font-medium text-muted-foreground"
          >
            Filter by type:
          </label>
          <select
            id="graph-filter-type"
            value={filterType}
            onChange={(e) =>
              setFilterType(e.target.value as DependencyType | "")
            }
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
          >
            <option value="">All types</option>
            {DEPENDENCY_TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ))}
          </select>
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={handleZoomOut}
            aria-label="Zoom out"
          >
            <ZoomOut className="h-3 w-3" aria-hidden="true" />
          </Button>
          <span className="text-xs text-muted-foreground w-10 text-center">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={handleZoomIn}
            aria-label="Zoom in"
          >
            <ZoomIn className="h-3 w-3" aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={handleReset}
            aria-label="Reset view"
          >
            <Maximize2 className="h-3 w-3" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {/* Truncation warning */}
      {isTruncated && (
        <div className="flex items-center gap-1.5 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-md px-3 py-1.5">
          <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span>
            Showing {MAX_NODES} of {totalNodes} nodes. Apply filters to reduce
            the graph size.
          </span>
        </div>
      )}

      {/* SVG Graph */}
      <div className="border border-border rounded-lg overflow-hidden bg-muted/10">
        <svg
          ref={svgRef}
          width="100%"
          height={GRAPH_HEIGHT}
          viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
          className="select-none"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{ cursor: isPanning ? "grabbing" : "grab" }}
          role="img"
          aria-label="Document dependency graph"
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="8"
              markerHeight="6"
              refX="8"
              refY="3"
              orient="auto"
            >
              <polygon
                points="0 0, 8 3, 0 6"
                fill="currentColor"
                className="text-muted-foreground"
              />
            </marker>
          </defs>

          <g
            transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}
          >
            {/* Edges */}
            {graphEdges.map((edge, i) => {
              const source = nodeMap.get(edge.source);
              const target = nodeMap.get(edge.target);
              if (!source || !target) return null;

              // Compute edge endpoint offset to stop at node boundary
              const dx = target.x - source.x;
              const dy = target.y - source.y;
              const dist = Math.sqrt(dx * dx + dy * dy);
              if (dist === 0) return null;

              const offsetX = (dx / dist) * NODE_RADIUS;
              const offsetY = (dy / dist) * NODE_RADIUS;

              return (
                <line
                  key={`edge-${i}`}
                  x1={source.x + offsetX}
                  y1={source.y + offsetY}
                  x2={target.x - offsetX}
                  y2={target.y - offsetY}
                  stroke="currentColor"
                  className="text-muted-foreground/50"
                  strokeWidth={1}
                  markerEnd="url(#arrowhead)"
                />
              );
            })}

            {/* Nodes */}
            {nodes.map((node) => (
              <g key={node.id}>
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={NODE_RADIUS}
                  fill={SEVERITY_COLORS[node.severity] || SEVERITY_COLORS.none}
                  opacity={0.8}
                  stroke="white"
                  strokeWidth={2}
                />
                <title>{node.id}</title>
                <text
                  x={node.x}
                  y={node.y + 1}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="fill-white text-[8px] font-mono pointer-events-none"
                >
                  {node.id.slice(0, 6)}
                </text>
              </g>
            ))}
          </g>
        </svg>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="font-medium">Severity:</span>
        <span className="flex items-center gap-1">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: SEVERITY_COLORS.critical }}
          />
          Critical
        </span>
        <span className="flex items-center gap-1">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: SEVERITY_COLORS.major }}
          />
          Major
        </span>
        <span className="flex items-center gap-1">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: SEVERITY_COLORS.minor }}
          />
          Minor
        </span>
        <span className="flex items-center gap-1">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: SEVERITY_COLORS.none }}
          />
          No findings
        </span>
      </div>
    </div>
  );
}
