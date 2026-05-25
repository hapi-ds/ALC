/**
 * ProvenanceViewer
 *
 * Displays generation provenance for a selected AI-generated document:
 * - Document selector (pick a generated document to view its provenance)
 * - Sources table: lists source_document_uuids with their titles
 * - Per-section provenance breakdown: section heading, KB query used,
 *   chunks retrieved, token count, inference duration
 * - Generation metadata: agent archetype, parameters, total tokens,
 *   total duration, timestamp
 * - Previous generation link (if regeneration)
 * - Embedded CrossReferenceViewer
 *
 * Requirements: 5.3, 6.5
 */

import { useEffect, useState, useCallback } from "react";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";
import { CrossReferenceViewer } from "./CrossReferenceViewer";
import type { GeneratedDocument, ProvenanceData } from "@/types/documentGenerator";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = (ms / 1000).toFixed(1);
  return `${seconds}s`;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Sources Table
// ---------------------------------------------------------------------------

interface SourcesTableProps {
  sourceUuids: string[];
}

function SourcesTable({ sourceUuids }: SourcesTableProps) {
  if (sourceUuids.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No source documents recorded.</p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm" aria-label="Source documents">
        <thead>
          <tr className="border-b bg-muted/50">
            <th scope="col" className="px-3 py-2 text-left font-medium w-12">
              #
            </th>
            <th scope="col" className="px-3 py-2 text-left font-medium">
              Document UUID
            </th>
          </tr>
        </thead>
        <tbody>
          {sourceUuids.map((uuid, idx) => (
            <tr key={uuid} className="border-b last:border-b-0 hover:bg-muted/30">
              <td className="px-3 py-2 text-muted-foreground">{idx + 1}</td>
              <td className="px-3 py-2 font-mono text-xs">{uuid}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section Provenance Breakdown
// ---------------------------------------------------------------------------

interface SectionProvenanceProps {
  sections: Array<Record<string, unknown>>;
}

function SectionProvenanceBreakdown({ sections }: SectionProvenanceProps) {
  if (sections.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No per-section provenance data available.</p>
    );
  }

  return (
    <div className="space-y-2">
      {sections.map((section, idx) => (
        <details
          key={idx}
          className="rounded-md border"
        >
          <summary className="px-3 py-2 cursor-pointer text-sm font-medium hover:bg-muted/30">
            {(section.section_heading as string) ?? `Section ${idx + 1}`}
            <span className="ml-2 text-xs text-muted-foreground font-normal">
              {section.token_count_for_section != null &&
                `${section.token_count_for_section} tokens`}
              {section.inference_duration_ms_for_section != null &&
                ` · ${formatDuration(section.inference_duration_ms_for_section as number)}`}
            </span>
          </summary>
          <div className="px-3 py-2 border-t bg-muted/10 space-y-2 text-xs">
            {section.knowledge_base_query_used && (
              <div>
                <span className="font-medium">KB Query:</span>{" "}
                <span className="text-muted-foreground">
                  {section.knowledge_base_query_used as string}
                </span>
              </div>
            )}
            {Array.isArray(section.source_chunks_retrieved) && (
              <div>
                <span className="font-medium">
                  Chunks Retrieved: {(section.source_chunks_retrieved as unknown[]).length}
                </span>
                <ul className="mt-1 space-y-1 pl-4 list-disc text-muted-foreground">
                  {(section.source_chunks_retrieved as Array<Record<string, unknown>>).map(
                    (chunk, cIdx) => (
                      <li key={cIdx} className="truncate max-w-lg" title={chunk.chunk_text as string}>
                        <span className="font-mono">{(chunk.document_uuid as string)?.slice(0, 8)}…</span>
                        {" — "}
                        {(chunk.chunk_text as string)?.slice(0, 100)}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            )}
            {section.token_count_for_section != null && (
              <div>
                <span className="font-medium">Token Count:</span>{" "}
                {section.token_count_for_section as number}
              </div>
            )}
            {section.inference_duration_ms_for_section != null && (
              <div>
                <span className="font-medium">Inference Duration:</span>{" "}
                {formatDuration(section.inference_duration_ms_for_section as number)}
              </div>
            )}
          </div>
        </details>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generation Metadata
// ---------------------------------------------------------------------------

interface GenerationMetadataProps {
  provenance: ProvenanceData;
}

function GenerationMetadata({ provenance }: GenerationMetadataProps) {
  return (
    <div className="rounded-md border p-4 space-y-2 text-sm">
      <h5 className="font-medium">Generation Metadata</h5>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-xs">
        <div>
          <dt className="font-medium text-muted-foreground">Agent Archetype</dt>
          <dd>{provenance.agent_archetype}</dd>
        </div>
        <div>
          <dt className="font-medium text-muted-foreground">Generation ID</dt>
          <dd className="font-mono">{provenance.generation_id}</dd>
        </div>
        <div>
          <dt className="font-medium text-muted-foreground">Total Tokens</dt>
          <dd>{provenance.total_token_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="font-medium text-muted-foreground">Total Duration</dt>
          <dd>{formatDuration(provenance.total_inference_duration_ms)}</dd>
        </div>
        <div>
          <dt className="font-medium text-muted-foreground">Timestamp</dt>
          <dd>{formatTimestamp(provenance.generation_timestamp)}</dd>
        </div>
        <div>
          <dt className="font-medium text-muted-foreground">Requesting User ID</dt>
          <dd>{provenance.requesting_user_id}</dd>
        </div>
        {provenance.generation_parameters && (
          <div className="sm:col-span-2">
            <dt className="font-medium text-muted-foreground">Parameters</dt>
            <dd className="font-mono text-xs mt-1 bg-muted/30 rounded p-2 overflow-x-auto">
              {JSON.stringify(provenance.generation_parameters, null, 2)}
            </dd>
          </div>
        )}
        {provenance.previous_generation_id && (
          <div className="sm:col-span-2">
            <dt className="font-medium text-muted-foreground">Previous Generation</dt>
            <dd className="font-mono">{provenance.previous_generation_id}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProvenanceViewer
// ---------------------------------------------------------------------------

export function ProvenanceViewer() {
  const {
    generatedDocuments,
    generatedDocumentsTotal,
    currentProvenance,
    isLoading,
    error,
    fetchGeneratedDocuments,
    fetchProvenance,
  } = useDocumentGeneratorStore();

  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);

  // Fetch generated documents for the selector on mount
  useEffect(() => {
    if (generatedDocumentsTotal === 0) {
      fetchGeneratedDocuments({ page_size: 100 });
    }
  }, [generatedDocumentsTotal, fetchGeneratedDocuments]);

  const handleDocumentSelect = useCallback(
    (docId: number) => {
      setSelectedDocumentId(docId);
      fetchProvenance(docId);
    },
    [fetchProvenance],
  );

  return (
    <section aria-label="Generation provenance" className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Generation Provenance</h3>
        <p className="text-sm text-muted-foreground">
          View audit trails, source attribution, and cross-references for AI-generated documents.
        </p>
      </div>

      {/* Document Selector */}
      <div className="max-w-md">
        <label htmlFor="provenance-document-select" className="text-sm font-medium block mb-1">
          Select Document
        </label>
        <select
          id="provenance-document-select"
          value={selectedDocumentId ?? ""}
          onChange={(e) => {
            const val = e.target.value;
            if (val) {
              handleDocumentSelect(Number(val));
            } else {
              setSelectedDocumentId(null);
            }
          }}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-describedby="provenance-doc-hint"
        >
          <option value="">— Choose a generated document —</option>
          {generatedDocuments.map((doc: GeneratedDocument) => (
            <option key={doc.id} value={doc.id}>
              {doc.title} ({doc.document_type})
            </option>
          ))}
        </select>
        <p id="provenance-doc-hint" className="text-xs text-muted-foreground mt-1">
          Select a document to view its generation provenance and cross-references.
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="text-sm text-destructive" role="alert">
          {error}
        </div>
      )}

      {/* Loading */}
      {isLoading && selectedDocumentId && (
        <div className="py-4 text-sm text-muted-foreground" aria-live="polite">
          Loading provenance data…
        </div>
      )}

      {/* Provenance Content */}
      {!isLoading && currentProvenance && selectedDocumentId && (
        <div className="space-y-6">
          {/* Generation Metadata */}
          <GenerationMetadata provenance={currentProvenance} />

          {/* Sources Table */}
          <div>
            <h4 className="text-base font-semibold mb-2">Source Documents</h4>
            <SourcesTable sourceUuids={currentProvenance.source_document_uuids} />
          </div>

          {/* Per-Section Provenance */}
          <div>
            <h4 className="text-base font-semibold mb-2">Per-Section Provenance</h4>
            <SectionProvenanceBreakdown sections={currentProvenance.section_provenance} />
          </div>

          {/* Unverified References */}
          {currentProvenance.unverified_references.length > 0 && (
            <div>
              <h4 className="text-base font-semibold mb-2 text-yellow-700">
                Unverified References ({currentProvenance.unverified_references.length})
              </h4>
              <div className="overflow-x-auto rounded-md border border-yellow-200">
                <table className="w-full text-sm" aria-label="Unverified references">
                  <thead>
                    <tr className="border-b bg-yellow-50">
                      <th scope="col" className="px-3 py-2 text-left font-medium">
                        Reference
                      </th>
                      <th scope="col" className="px-3 py-2 text-left font-medium">
                        Location
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentProvenance.unverified_references.map((ref, idx) => (
                      <tr key={idx} className="border-b last:border-b-0">
                        <td className="px-3 py-2 font-mono text-xs">
                          {(ref.reference as string) ?? JSON.stringify(ref)}
                        </td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">
                          {ref.section_number != null && `Section ${ref.section_number}`}
                          {ref.paragraph_index != null && `, Para ${ref.paragraph_index}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Cross-Reference Viewer */}
          <CrossReferenceViewer documentId={selectedDocumentId} />
        </div>
      )}

      {/* No provenance state */}
      {!isLoading && !currentProvenance && selectedDocumentId && (
        <div className="py-4 text-sm text-muted-foreground">
          No provenance data found for this document. It may not be AI-generated.
        </div>
      )}
    </section>
  );
}
