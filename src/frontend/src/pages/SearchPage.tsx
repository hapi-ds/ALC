import { useCallback, useEffect, useRef, useState } from "react";
import { Search, X, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSearchStore } from "@/stores/searchStore";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import { FilterSidebar } from "@/components/search/FilterSidebar";
import { SearchPagination } from "@/components/search/SearchPagination";
import { SortDropdown } from "@/components/search/SortDropdown";
import type { SearchFilters } from "@/stores/searchStore";

const DEBOUNCE_MS = 300;
const MAX_QUERY_LENGTH = 1000;

/**
 * Loading skeleton with pulsing placeholder cards.
 */
function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="border border-border rounded-lg p-4 space-y-3 animate-pulse">
          <div className="flex items-center gap-2">
            <div className="h-4 w-48 bg-muted rounded" />
            <div className="h-5 w-12 bg-muted rounded-full" />
          </div>
          <div className="space-y-1">
            <div className="h-2 w-full bg-muted rounded-full" />
          </div>
          <div className="space-y-1">
            <div className="h-3 w-full bg-muted rounded" />
            <div className="h-3 w-3/4 bg-muted rounded" />
          </div>
          <div className="flex items-center gap-2">
            <div className="h-5 w-16 bg-muted rounded-full" />
            <div className="h-5 w-14 bg-muted rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SearchPage() {
  const {
    query,
    results,
    isSearching,
    error,
    filters,
    offset,
    limit,
    totalAvailable,
    sortBy,
    setQuery,
    search,
    setFilter,
    setSortBy,
    nextPage,
    previousPage,
    clearResults,
  } = useSearchStore();

  const [inputValue, setInputValue] = useState(query);
  const [truncationNotice, setTruncationNotice] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Sync input value when store query changes externally (e.g., clearResults)
  useEffect(() => {
    setInputValue(query);
  }, [query]);

  const cancelDebounce = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
  }, []);

  const triggerSearch = useCallback((value: string) => {
    cancelDebounce();

    // Reject whitespace-only queries
    if (!value.trim()) {
      clearResults();
      setHasSearched(false);
      return;
    }

    // Truncate query > 1000 chars and show notification
    let searchQuery = value;
    if (value.length > MAX_QUERY_LENGTH) {
      searchQuery = value.slice(0, MAX_QUERY_LENGTH);
      setTruncationNotice(true);
      setTimeout(() => setTruncationNotice(false), 4000);
    }

    setQuery(searchQuery);
    setHasSearched(true);
    search();
  }, [cancelDebounce, clearResults, setQuery, search]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInputValue(value);
    setQuery(value);

    cancelDebounce();

    debounceRef.current = setTimeout(() => {
      triggerSearch(value);
    }, DEBOUNCE_MS);
  }, [cancelDebounce, setQuery, triggerSearch]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      triggerSearch(inputValue);
    } else if (e.key === "Escape") {
      cancelDebounce();
      setInputValue("");
      clearResults();
      setHasSearched(false);
      (e.target as HTMLInputElement).focus();
    }
  }, [cancelDebounce, clearResults, inputValue, triggerSearch]);

  const handleSearchClick = useCallback(() => {
    triggerSearch(inputValue);
  }, [inputValue, triggerSearch]);

  const handleFilterToggle = useCallback((category: keyof SearchFilters, value: string) => {
    setFilter(category, value);
  }, [setFilter]);

  const handleClearAllFilters = useCallback(() => {
    // Clear all filters and re-search
    for (const category of ["document_type", "status", "tags"] as const) {
      for (const value of filters[category]) {
        setFilter(category, value);
      }
    }
  }, [filters, setFilter]);

  const handleNextPage = useCallback(() => {
    nextPage();
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [nextPage]);

  const handlePreviousPage = useCallback(() => {
    previousPage();
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [previousPage]);

  const handleRetry = useCallback(() => {
    search();
  }, [search]);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      cancelDebounce();
    };
  }, [cancelDebounce]);

  // Determine active filter chips
  const activeFilterChips: { category: keyof SearchFilters; value: string }[] = [];
  for (const category of ["document_type", "status", "tags"] as const) {
    for (const value of filters[category]) {
      activeFilterChips.push({ category, value });
    }
  }

  // Determine if error is a 422 validation error
  const is422Error = error?.includes("422") || error?.includes("validation");

  // Determine display state
  const showInitialState = !hasSearched && !isSearching && results.length === 0 && !error;
  const showEmptyState = hasSearched && !isSearching && results.length === 0 && !error;
  const showResults = results.length > 0 && !error;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Search</h2>
        <p className="text-sm text-muted-foreground">
          Hybrid search combining BM25 lexical and semantic kNN search
        </p>
      </div>

      {/* Search input form */}
      <form role="search" onSubmit={(e) => e.preventDefault()}>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <input
              type="search"
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Search documents..."
              className="w-full pl-10 pr-4 py-2 border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              aria-label="Search documents"
            />
          </div>
          <Button
            type="button"
            onClick={handleSearchClick}
            disabled={isSearching}
          >
            Search
          </Button>
        </div>

        {/* Inline validation error for HTTP 422 */}
        {is422Error && error && (
          <p className="mt-2 text-sm text-destructive flex items-center gap-1">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            {error}
          </p>
        )}
      </form>

      {/* Truncation notification */}
      {truncationNotice && (
        <div className="rounded-md bg-yellow-50 border border-yellow-200 p-3 text-sm text-yellow-800" role="alert">
          Query truncated to 1000 characters
        </div>
      )}

      {/* Sort dropdown - only show when results exist */}
      {showResults && (
        <div className="flex justify-end">
          <SortDropdown value={sortBy} onChange={setSortBy} />
        </div>
      )}

      {/* Two-column layout: FilterSidebar + Results */}
      <div className="flex gap-6">
        {/* Filter sidebar */}
        <div className="w-64 shrink-0">
          <FilterSidebar
            results={results}
            activeFilters={filters}
            onFilterToggle={handleFilterToggle}
            onClearAll={handleClearAllFilters}
            disabled={!hasSearched || results.length === 0}
          />
        </div>

        {/* Results area */}
        <div className="flex-1 min-w-0" ref={resultsRef}>
          {/* Active filter chips */}
          {activeFilterChips.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {activeFilterChips.map(({ category, value }) => (
                <span
                  key={`${category}-${value}`}
                  className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
                >
                  {value}
                  <button
                    type="button"
                    onClick={() => setFilter(category, value)}
                    className="ml-1 rounded-full p-0.5 hover:bg-primary/20 transition-colors"
                    aria-label={`Remove filter: ${value}`}
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* aria-live region for result count announcements */}
          <div aria-live="polite" className="sr-only">
            {hasSearched && !isSearching && (
              totalAvailable > 0
                ? `${totalAvailable} results found`
                : "No results found"
            )}
          </div>

          {/* Result count */}
          {showResults && (
            <p className="text-sm text-muted-foreground mb-4">
              {totalAvailable} results found for &apos;{query}&apos;
            </p>
          )}

          {/* Results container with aria-busy */}
          <div aria-busy={isSearching}>
            {/* Loading skeleton */}
            {isSearching && <LoadingSkeleton />}

            {/* Error state (non-422) */}
            {error && !is422Error && (
              <div className="border border-destructive/50 bg-destructive/10 rounded-lg p-6 text-center">
                <AlertCircle className="h-8 w-8 mx-auto mb-2 text-destructive" aria-hidden="true" />
                <p className="text-sm text-destructive font-medium mb-3">{error}</p>
                <Button type="button" variant="outline" onClick={handleRetry}>
                  Retry
                </Button>
              </div>
            )}

            {/* Initial placeholder state */}
            {showInitialState && (
              <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
                <Search className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
                <p>Enter a query to search across all documents</p>
                <p className="text-xs mt-1">
                  Results include Document-UUID, title, version, excerpt, and relevance score
                </p>
              </div>
            )}

            {/* Empty state */}
            {showEmptyState && (
              <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
                <Search className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
                <p>No results found for &apos;{query}&apos;</p>
                <p className="text-xs mt-1">
                  Try different keywords or adjust your filters
                </p>
              </div>
            )}

            {/* Results list */}
            {showResults && !isSearching && (
              <div className="space-y-4">
                {results.map((result) => (
                  <SearchResultCard
                    key={result.document_uuid}
                    result={result}
                    query={query}
                  />
                ))}
              </div>
            )}

            {/* Pagination */}
            {showResults && !isSearching && (
              <SearchPagination
                offset={offset}
                limit={limit}
                totalAvailable={totalAvailable}
                onNext={handleNextPage}
                onPrevious={handlePreviousPage}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
