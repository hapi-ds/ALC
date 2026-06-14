import { Link } from "react-router-dom";
import type { SearchResult } from "@/stores/searchStore";
import { DownloadButton } from "@/components/documents";

interface SearchResultCardProps {
  result: SearchResult;
  query: string;
}

/**
 * Highlights occurrences of the query string within the text using <mark> elements.
 * Performs case-insensitive matching by splitting on the query and wrapping matches.
 */
function HighlightedExcerpt({ text, query }: { text: string; query: string }) {
  if (!query.trim()) {
    return <>{text}</>;
  }

  // Escape special regex characters in the query
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escaped})`, "gi"));

  return (
    <>
      {parts.map((part, index) => {
        const isMatch = part.toLowerCase() === query.toLowerCase();
        return isMatch ? (
          <mark key={index} className="bg-yellow-200 text-foreground rounded-sm px-0.5">
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        );
      })}
    </>
  );
}

/**
 * Parses a version string like "1.0" into major and minor version numbers.
 * Returns undefined if parsing fails.
 */
function parseVersion(version: string): { major_version: number; minor_version: number } | undefined {
  const parts = version.split(".");
  const major = Number(parts[0]);
  const minor = Number(parts[1] ?? 0);
  if (Number.isNaN(major) || Number.isNaN(minor)) return undefined;
  return { major_version: major, minor_version: minor };
}

/**
 * SearchResultCard renders a single search result with title link, version badge,
 * relevance score meter, highlighted excerpt, and metadata badges.
 *
 * Validates: Requirements 5.1, 5.2, 8.6, 9.5
 */
export function SearchResultCard({ result, query }: SearchResultCardProps) {
  const clampedScore = Math.max(0, Math.min(1, result.relevance_score));
  const percentage = Math.round(clampedScore * 100);
  const parsedVersion = parseVersion(result.version);

  return (
    <div className="border border-border rounded-lg p-4 space-y-3 hover:bg-accent/50 transition-colors">
      {/* Title and version */}
      <div className="flex items-center gap-2 flex-wrap">
        <Link
          to={`/documents/${result.document_uuid}`}
          className="text-sm font-medium text-primary hover:underline"
        >
          {result.title}
        </Link>
        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
          {result.version}
        </span>
        <div className="ml-auto">
          <DownloadButton
            documentUuid={result.document_uuid}
            documentTitle={result.title}
            version={parsedVersion}
            variant="icon"
          />
        </div>
      </div>

      {/* Relevance score bar */}
      <div className="space-y-1">
        <div
          role="meter"
          aria-valuenow={percentage}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Relevance score: ${percentage}%`}
          className="h-2 w-full bg-muted rounded-full overflow-hidden"
        >
          <div
            className="h-full bg-primary rounded-full transition-all"
            style={{ width: `${clampedScore * 100}%` }}
          />
        </div>
        <span className="text-xs text-muted-foreground">{percentage}% relevance</span>
      </div>

      {/* Excerpt with highlighted query terms */}
      <p className="text-sm text-muted-foreground leading-relaxed">
        <HighlightedExcerpt text={result.excerpt} query={query} />
      </p>

      {/* Metadata badges */}
      <div className="flex items-center gap-2 flex-wrap">
        {result.document_type && (
          <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-primary/10 text-primary">
            {result.document_type}
          </span>
        )}
        {result.status && (
          <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
            {result.status}
          </span>
        )}
      </div>
    </div>
  );
}
