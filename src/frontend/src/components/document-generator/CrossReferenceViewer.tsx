/**
 * CrossReferenceViewer
 *
 * Displays cross-reference entries for a generated document, grouped by
 * reference_type (requirement, test_case, section). Each entry shows the
 * reference_identifier, reference_text, and source_document_title.
 *
 * Embedded within ProvenanceViewer.
 *
 * Requirements: 5.3, 6.5
 */

import { useEffect } from "react";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";
import type { CrossReference } from "@/types/documentGenerator";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function groupByReferenceType(
  refs: CrossReference[],
): Record<string, CrossReference[]> {
  const grouped: Record<string, CrossReference[]> = {};
  for (const ref of refs) {
    const key = ref.reference_type;
    if (!grouped[key]) {
      grouped[key] = [];
    }
    grouped[key].push(ref);
  }
  return grouped;
}

function formatReferenceType(type: string): string {
  switch (type) {
    case "requirement":
      return "Requirements";
    case "test_case":
      return "Test Cases";
    case "section":
      return "Sections";
    default:
      return type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, " ");
  }
}

// ---------------------------------------------------------------------------
// CrossReferenceViewer
// ---------------------------------------------------------------------------

interface CrossReferenceViewerProps {
  documentId: number;
}

export function CrossReferenceViewer({ documentId }: CrossReferenceViewerProps) {
  const { crossReferences, isLoading, error, fetchCrossReferences } =
    useDocumentGeneratorStore();

  useEffect(() => {
    fetchCrossReferences(documentId);
  }, [documentId, fetchCrossReferences]);

  if (isLoading) {
    return (
      <div className="py-4 text-sm text-muted-foreground" aria-live="polite">
        Loading cross-references…
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-4 text-sm text-destructive" role="alert">
        {error}
      </div>
    );
  }

  if (crossReferences.length === 0) {
    return (
      <div className="py-4 text-sm text-muted-foreground">
        No cross-references found for this document.
      </div>
    );
  }

  const grouped = groupByReferenceType(crossReferences);

  return (
    <section aria-label="Cross-references">
      <h4 className="text-base font-semibold mb-3">Cross-References</h4>

      <div className="space-y-4">
        {Object.entries(grouped).map(([type, refs]) => (
          <div key={type}>
            <h5 className="text-sm font-medium text-muted-foreground mb-2">
              {formatReferenceType(type)} ({refs.length})
            </h5>

            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm" aria-label={`${formatReferenceType(type)} cross-references`}>
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      Identifier
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      Text
                    </th>
                    <th scope="col" className="px-3 py-2 text-left font-medium">
                      Source Document
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {refs.map((ref, idx) => (
                    <tr
                      key={`${ref.reference_identifier}-${idx}`}
                      className="border-b last:border-b-0 hover:bg-muted/30"
                    >
                      <td className="px-3 py-2 font-mono text-xs">
                        {ref.reference_identifier}
                      </td>
                      <td className="px-3 py-2 max-w-xs truncate" title={ref.reference_text ?? ""}>
                        {ref.reference_text ?? "—"}
                      </td>
                      <td className="px-3 py-2">
                        {ref.source_document_title}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
