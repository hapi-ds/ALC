import { CheckCircle, FileText } from "lucide-react";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { LiteratureSearchResult } from "@/types/literatureSearch";

/**
 * Props for SearchResultCard component.
 */
export interface SearchResultCardProps {
  /** The literature search result to display. */
  result: LiteratureSearchResult;
  /** Whether the current user has permission to internalize (document_admin or system_admin). */
  canInternalize?: boolean;
  /** Callback triggered when the user clicks the "Internalize" button. */
  onInternalize?: (result: LiteratureSearchResult) => void;
}

/**
 * Formats authors for display: shows first 3 and "+N more" if there are additional.
 */
function formatAuthors(authors: string[]): string {
  if (authors.length === 0) return "Unknown authors";
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")} +${authors.length - 3} more`;
}

/**
 * Extracts the publication year from a date string.
 */
function getPublicationYear(date: string | null): string {
  if (!date) return "N/A";
  const year = new Date(date).getFullYear();
  return isNaN(year) ? "N/A" : String(year);
}

/**
 * SearchResultCard displays a single literature search result as a card with
 * metadata, relevance scoring, provenance indicator, and internalization controls.
 *
 * Validates: Requirements 9.4
 */
export function SearchResultCard({
  result,
  canInternalize = false,
  onInternalize,
}: SearchResultCardProps) {
  const relevancePercent = Math.round(result.relevance_score * 100);
  const publicationYear = getPublicationYear(result.publication_date);

  return (
    <Card className="relative">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <a
              href={result.doi ? `https://doi.org/${result.doi}` : "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="text-base font-semibold leading-tight text-primary hover:underline line-clamp-2"
              aria-label={`View details for: ${result.title}`}
            >
              {result.title}
            </a>
            <p className="mt-1 text-sm text-muted-foreground">
              {formatAuthors(result.authors)}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {result.is_internalized && (
              <CheckCircle
                className="h-5 w-5 text-green-600"
                aria-label="Already internalized"
              />
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Metadata row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span>{publicationYear}</span>
          {result.journal && <span>{result.journal}</span>}
          <span className="capitalize">{result.source}</span>
        </div>

        {/* Badges and indicators */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Provenance badge */}
          <Badge
            className={
              result.provenance === "external"
                ? "bg-blue-100 text-blue-800 border-blue-200"
                : "bg-green-100 text-green-800 border-green-200"
            }
          >
            {result.provenance === "external" ? "External" : "Internal"}
          </Badge>

          {/* Full-text indicator */}
          {result.full_text_available && (
            <Badge variant="secondary" className="gap-1">
              <FileText className="h-3 w-3" aria-hidden="true" />
              Full Text
            </Badge>
          )}
        </div>

        {/* Relevance score bar */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            Relevance
          </span>
          <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${relevancePercent}%` }}
              role="progressbar"
              aria-valuenow={relevancePercent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Relevance score: ${relevancePercent}%`}
            />
          </div>
          <span className="text-xs font-medium tabular-nums">
            {relevancePercent}%
          </span>
        </div>

        {/* Internalize button */}
        {canInternalize && !result.is_internalized && onInternalize && (
          <div className="pt-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onInternalize(result)}
              aria-label={`Internalize: ${result.title}`}
            >
              Internalize
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
