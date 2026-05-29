/**
 * MatrixDetailView
 *
 * Tabular view of TraceabilityLinks with columns:
 * - requirement_id, requirement_text (truncated 100 chars with tooltip)
 * - target_document, test_case_id, test_case_text (truncated 100 chars with tooltip)
 * - link_confidence (percentage badge: green >= 0.8, yellow >= 0.5, red < 0.5)
 * - link_method, is_stale indicator
 *
 * Supports sorting by any column and filtering by link_confidence_min.
 *
 * Requirements: 8.2
 */

import { useEffect, useState, useMemo } from "react";
import { ArrowUpDown, AlertTriangle, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTraceabilityStore } from "@/stores/traceabilityStore";
import type { TraceabilityLink, StaleLinkMarker } from "@/types/traceability";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortField =
  | "requirement_id"
  | "requirement_text"
  | "target_document_uuid"
  | "test_case_id"
  | "test_case_text"
  | "link_confidence"
  | "link_method";

type SortDirection = "asc" | "desc";

interface MatrixDetailViewProps {
  matrixId: string;
  staleMarkers?: StaleLinkMarker[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "…";
}

function getConfidenceBadgeClass(confidence: number): string {
  if (confidence >= 0.8) return "bg-green-100 text-green-800";
  if (confidence >= 0.5) return "bg-yellow-100 text-yellow-800";
  return "bg-red-100 text-red-800";
}

function formatMethod(method: string): string {
  return method.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MatrixDetailView({ matrixId, staleMarkers = [] }: MatrixDetailViewProps) {
  const { links, isLoading, fetchLinks } = useTraceabilityStore();

  const [sortField, setSortField] = useState<SortField>("link_confidence");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [confidenceMin, setConfidenceMin] = useState<number>(0);

  useEffect(() => {
    fetchLinks(matrixId, { link_confidence_min: confidenceMin > 0 ? confidenceMin : undefined });
  }, [matrixId, fetchLinks, confidenceMin]);

  // Build stale lookup set
  const staleReqIds = useMemo(() => {
    const set = new Set<string>();
    for (const marker of staleMarkers) {
      if (!marker.is_cleared) {
        set.add(marker.requirement_id);
      }
    }
    return set;
  }, [staleMarkers]);

  // Sort links
  const sortedLinks = useMemo(() => {
    const sorted = [...links];
    sorted.sort((a, b) => {
      let aVal: string | number = "";
      let bVal: string | number = "";

      switch (sortField) {
        case "requirement_id":
          aVal = a.requirement_id;
          bVal = b.requirement_id;
          break;
        case "requirement_text":
          aVal = a.requirement_text;
          bVal = b.requirement_text;
          break;
        case "target_document_uuid":
          aVal = a.target_document_uuid;
          bVal = b.target_document_uuid;
          break;
        case "test_case_id":
          aVal = a.test_case_id;
          bVal = b.test_case_id;
          break;
        case "test_case_text":
          aVal = a.test_case_text;
          bVal = b.test_case_text;
          break;
        case "link_confidence":
          aVal = a.link_confidence;
          bVal = b.link_confidence;
          break;
        case "link_method":
          aVal = a.link_method;
          bVal = b.link_method;
          break;
      }

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      }
      const cmp = String(aVal).localeCompare(String(bVal));
      return sortDirection === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [links, sortField, sortDirection]);

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  }

  function SortableHeader({ field, label }: { field: SortField; label: string }) {
    return (
      <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
        <button
          className="flex items-center gap-1 hover:text-foreground transition-colors"
          onClick={() => handleSort(field)}
          aria-label={`Sort by ${label}`}
        >
          {label}
          <ArrowUpDown className="h-3 w-3" aria-hidden="true" />
        </button>
      </th>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <Filter className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <label className="text-sm text-muted-foreground">
          Min confidence:
        </label>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={confidenceMin * 100}
          onChange={(e) => setConfidenceMin(Number(e.target.value) / 100)}
          className="w-32"
          aria-label="Minimum confidence filter"
        />
        <span className="text-sm font-medium w-12">
          {(confidenceMin * 100).toFixed(0)}%
        </span>
      </div>

      {/* Table */}
      {isLoading && links.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          Loading links...
        </div>
      ) : sortedLinks.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          No traceability links found matching the current filter.
        </div>
      ) : (
        <div className="overflow-x-auto border border-border rounded-lg">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <SortableHeader field="requirement_id" label="Req ID" />
                <SortableHeader field="requirement_text" label="Requirement" />
                <SortableHeader field="target_document_uuid" label="Target Doc" />
                <SortableHeader field="test_case_id" label="Test ID" />
                <SortableHeader field="test_case_text" label="Test Case" />
                <SortableHeader field="link_confidence" label="Confidence" />
                <SortableHeader field="link_method" label="Method" />
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  Stale
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sortedLinks.map((link, idx) => (
                <LinkRow
                  key={`${link.requirement_id}-${link.test_case_id}-${idx}`}
                  link={link}
                  isStale={staleReqIds.has(link.requirement_id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LinkRow({ link, isStale }: { link: TraceabilityLink; isStale: boolean }) {
  return (
    <tr className={`hover:bg-accent/30 ${isStale ? "bg-amber-50" : ""}`}>
      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
        {link.requirement_id}
      </td>
      <td className="px-3 py-2 max-w-[200px]" title={link.requirement_text}>
        {truncateText(link.requirement_text, 100)}
      </td>
      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
        {link.target_document_uuid}
      </td>
      <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
        {link.test_case_id}
      </td>
      <td className="px-3 py-2 max-w-[200px]" title={link.test_case_text}>
        {truncateText(link.test_case_text, 100)}
      </td>
      <td className="px-3 py-2 whitespace-nowrap">
        <span
          className={`text-xs px-2 py-0.5 rounded-full font-medium ${getConfidenceBadgeClass(link.link_confidence)}`}
        >
          {(link.link_confidence * 100).toFixed(0)}%
        </span>
      </td>
      <td className="px-3 py-2 text-xs whitespace-nowrap">
        {formatMethod(link.link_method)}
      </td>
      <td className="px-3 py-2">
        {isStale && (
          <span className="flex items-center gap-1 text-amber-600" title="Link may be stale due to requirement changes">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" />
            <span className="text-xs">Stale</span>
          </span>
        )}
      </td>
    </tr>
  );
}
