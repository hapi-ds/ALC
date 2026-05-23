import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { SourceCitation } from "@/stores/knowledgeStore";

interface CitationListProps {
  citations: SourceCitation[];
  defaultExpanded?: boolean;
  onCitationClick?: (documentUuid: string) => void;
}

/**
 * CitationList renders a collapsible list of source citations.
 *
 * - Displays a summary label with citation count (e.g., "3 sources"), collapsed by default
 * - Expands on click to show the full citation list
 * - Each citation shows: title as a link to /documents/{document_uuid}, version badge, page_or_section
 * - Maximum 50 citations displayed
 *
 * Validates: Requirements 4.1, 4.2, 4.3, 4.5, 4.6, 9.7
 */
export function CitationList({
  citations,
  defaultExpanded,
  onCitationClick,
}: CitationListProps) {
  const [expanded, setExpanded] = useState(defaultExpanded ?? false);

  if (citations.length === 0) return null;

  const displayedCitations = citations.slice(0, 50);
  const count = citations.length;
  const label = `${count} ${count === 1 ? "source" : "sources"}`;

  return (
    <div className="mt-2 border-t border-gray-200 dark:border-gray-700 pt-2">
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        aria-controls="citation-list"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        )}
        <span>{label}</span>
      </button>

      {expanded && (
        <ul id="citation-list" className="mt-1.5 space-y-1.5">
          {displayedCitations.map((citation) => (
            <li
              key={`${citation.document_uuid}-${citation.page_or_section}`}
              className="flex items-center gap-2 text-xs"
            >
              <Link
                to={`/documents/${citation.document_uuid}`}
                aria-label={`Open document: ${citation.title} version ${citation.version}`}
                className="text-blue-600 dark:text-blue-400 hover:underline truncate"
                onClick={() => onCitationClick?.(citation.document_uuid)}
              >
                {citation.title}
              </Link>
              <span className="bg-gray-200 dark:bg-gray-700 rounded-full px-2 py-0.5 text-xs text-muted-foreground whitespace-nowrap">
                v{citation.version}
              </span>
              {citation.page_or_section && (
                <span className="text-muted-foreground truncate">
                  {citation.page_or_section}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
