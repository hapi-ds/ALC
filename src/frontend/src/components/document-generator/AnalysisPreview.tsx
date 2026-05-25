/**
 * AnalysisPreview
 *
 * Displays the structural analysis of a registered template, including
 * section hierarchy, detected placeholder markers, paragraph styles,
 * and page layout information.
 *
 * Requirements: 1.6
 */

import { FileText, Hash, Layout, Type } from "lucide-react";
import type { TemplateAnalysis } from "@/types/documentGenerator";

interface AnalysisPreviewProps {
  analysis: TemplateAnalysis;
}

export function AnalysisPreview({ analysis }: AnalysisPreviewProps) {
  return (
    <div className="space-y-4" aria-label="Template analysis details">
      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-md border p-3 text-center">
          <p className="text-2xl font-bold">{analysis.total_sections}</p>
          <p className="text-xs text-muted-foreground">Sections</p>
        </div>
        <div className="rounded-md border p-3 text-center">
          <p className="text-2xl font-bold">{analysis.placeholder_markers.length}</p>
          <p className="text-xs text-muted-foreground">Placeholders</p>
        </div>
        <div className="rounded-md border p-3 text-center">
          <p className="text-2xl font-bold">{analysis.paragraph_styles.length}</p>
          <p className="text-xs text-muted-foreground">Styles</p>
        </div>
        <div className="rounded-md border p-3 text-center">
          <p className="text-2xl font-bold">{analysis.table_structures.length}</p>
          <p className="text-xs text-muted-foreground">Tables</p>
        </div>
      </div>

      {/* Section Hierarchy */}
      <details className="rounded-md border" open>
        <summary className="flex cursor-pointer items-center gap-2 p-3 text-sm font-medium hover:bg-accent/50">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Section Hierarchy
        </summary>
        <div className="border-t px-3 py-2">
          {analysis.section_hierarchy.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">No sections detected.</p>
          ) : (
            <ul className="space-y-1" aria-label="Section hierarchy list">
              {analysis.section_hierarchy.map((section, idx) => (
                <li
                  key={idx}
                  className="flex items-center gap-2 text-sm py-1"
                  style={{ paddingLeft: `${(section.level - 1) * 16}px` }}
                >
                  <span className="text-xs text-muted-foreground font-mono w-6 shrink-0">
                    H{section.level}
                  </span>
                  <span className="truncate">{section.heading}</span>
                  {section.has_placeholder && (
                    <span className="text-xs px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded shrink-0">
                      placeholder
                    </span>
                  )}
                  {section.has_table && (
                    <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-800 rounded shrink-0">
                      table
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>

      {/* Placeholder Markers */}
      <details className="rounded-md border">
        <summary className="flex cursor-pointer items-center gap-2 p-3 text-sm font-medium hover:bg-accent/50">
          <Hash className="h-4 w-4" aria-hidden="true" />
          Placeholder Markers ({analysis.placeholder_markers.length})
        </summary>
        <div className="border-t px-3 py-2">
          {analysis.placeholder_markers.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">No placeholders detected.</p>
          ) : (
            <ul className="space-y-1" aria-label="Placeholder markers list">
              {analysis.placeholder_markers.map((marker, idx) => (
                <li key={idx} className="flex items-center gap-2 text-sm py-1">
                  <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">
                    {marker.marker || marker.identifier || JSON.stringify(marker)}
                  </code>
                  {marker.parameter && (
                    <span className="text-xs text-muted-foreground">
                      param: {marker.parameter}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>

      {/* Paragraph Styles */}
      <details className="rounded-md border">
        <summary className="flex cursor-pointer items-center gap-2 p-3 text-sm font-medium hover:bg-accent/50">
          <Type className="h-4 w-4" aria-hidden="true" />
          Paragraph Styles ({analysis.paragraph_styles.length})
        </summary>
        <div className="border-t px-3 py-2">
          {analysis.paragraph_styles.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">No styles detected.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5 py-1">
              {analysis.paragraph_styles.map((style, idx) => (
                <span
                  key={idx}
                  className="text-xs px-2 py-1 bg-muted rounded"
                >
                  {style}
                </span>
              ))}
            </div>
          )}
        </div>
      </details>

      {/* Page Layout */}
      <details className="rounded-md border">
        <summary className="flex cursor-pointer items-center gap-2 p-3 text-sm font-medium hover:bg-accent/50">
          <Layout className="h-4 w-4" aria-hidden="true" />
          Page Layout
        </summary>
        <div className="border-t px-3 py-2">
          {Object.keys(analysis.page_layout).length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">No layout info available.</p>
          ) : (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm py-1">
              {Object.entries(analysis.page_layout).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-muted-foreground capitalize">
                    {key.replace(/_/g, " ")}
                  </dt>
                  <dd className="font-mono text-xs">
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </details>

      {/* Numbering Scheme & TOC */}
      <div className="flex items-center gap-4 text-sm text-muted-foreground">
        <span>
          Numbering: <span className="font-mono">{analysis.numbering_scheme || "none"}</span>
        </span>
        <span>
          TOC: {analysis.has_toc ? "Yes" : "No"}
        </span>
      </div>
    </div>
  );
}
