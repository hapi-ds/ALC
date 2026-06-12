import { useEffect, useCallback } from "react";
import { Clock, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";

/**
 * SearchHistoryPanel displays the last 20 search executions with query text,
 * timestamp, and result count. Clicking a history entry sets the query text
 * in the store and re-executes the search.
 *
 * Validates: Requirements 9.6
 */
export function SearchHistoryPanel() {
  const {
    searchHistory,
    loadSearchHistory,
    setQueryText,
    executeSearch,
    isLoading,
  } = useLiteratureSearchStore();

  useEffect(() => {
    loadSearchHistory();
  }, [loadSearchHistory]);

  const handleReExecute = useCallback(
    (queryText: string) => {
      if (isLoading) return;
      setQueryText(queryText);
      executeSearch();
    },
    [isLoading, setQueryText, executeSearch],
  );

  const recentHistory = searchHistory.slice(0, 20);

  if (recentHistory.length === 0) {
    return (
      <div className="rounded-md border p-4">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-medium">
          <Clock className="h-4 w-4" aria-hidden="true" />
          Search History
        </h3>
        <p className="text-sm text-muted-foreground">
          No search history yet. Execute a search to see it here.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-medium">
        <Clock className="h-4 w-4" aria-hidden="true" />
        Search History
      </h3>
      <ul className="space-y-2" aria-label="Search history entries">
        {recentHistory.map((entry) => (
          <li
            key={entry.id}
            className="flex items-center justify-between gap-2 rounded-sm border px-3 py-2 text-sm"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium" title={entry.query_text}>
                {entry.query_text}
              </p>
              <p className="text-xs text-muted-foreground">
                {formatTimestamp(entry.executed_at)} &middot;{" "}
                {entry.total_results} result
                {entry.total_results !== 1 ? "s" : ""}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleReExecute(entry.query_text)}
              disabled={isLoading}
              aria-label={`Re-execute search: ${entry.query_text}`}
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Format an ISO timestamp for display. */
function formatTimestamp(iso: string): string {
  try {
    const date = new Date(iso);
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
