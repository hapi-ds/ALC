import { Skeleton } from "@/components/ui/skeleton";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";
import { SearchResultCard } from "./SearchResultCard";
import type { LiteratureSearchResult } from "@/types/literatureSearch";

/**
 * Props for SearchResultsList component.
 */
export interface SearchResultsListProps {
  /** Whether the current user has permission to internalize. */
  canInternalize?: boolean;
  /** Callback triggered when the user clicks "Internalize" on a result card. */
  onInternalize?: (result: LiteratureSearchResult) => void;
}

/**
 * Renders a loading skeleton placeholder for a search result card.
 */
function ResultSkeleton() {
  return (
    <div className="rounded-xl border bg-card p-6 space-y-3">
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-4 w-1/2" />
      <div className="flex gap-4">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-24" />
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-5 w-16 rounded-md" />
        <Skeleton className="h-5 w-20 rounded-md" />
      </div>
      <Skeleton className="h-2 w-full rounded-full" />
    </div>
  );
}

/**
 * SearchResultsList maps the store's results array to SearchResultCard components,
 * displays loading skeletons during search, and shows an empty state message
 * when no results are found.
 *
 * Validates: Requirements 9.4
 */
export function SearchResultsList({
  canInternalize = false,
  onInternalize,
}: SearchResultsListProps) {
  const { results, isLoading } = useLiteratureSearchStore();

  // Loading state — show skeleton placeholders
  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Loading search results">
        {Array.from({ length: 5 }).map((_, index) => (
          <ResultSkeleton key={index} />
        ))}
      </div>
    );
  }

  // Empty state — no results
  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <p className="text-muted-foreground text-sm">
          No results found. Try adjusting your search query or filters.
        </p>
      </div>
    );
  }

  // Results list
  return (
    <div className="space-y-4" aria-label="Search results">
      {results.map((result) => (
        <SearchResultCard
          key={result.id}
          result={result}
          canInternalize={canInternalize}
          onInternalize={onInternalize}
        />
      ))}
    </div>
  );
}
