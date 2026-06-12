import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";
import type { SavedSearch } from "@/types/literatureSearch";

/**
 * Collapsible sidebar panel listing the user's saved searches.
 * Loads saved searches on mount via loadSavedSearches(). Each entry
 * displays the search name, last execution date, and result count,
 * with buttons to re-execute or delete.
 */
export function SavedSearchesPanel() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const savedSearches = useLiteratureSearchStore(
    (state) => state.savedSearches
  );
  const savedSearchesLoading = useLiteratureSearchStore(
    (state) => state.savedSearchesLoading
  );
  const loadSavedSearches = useLiteratureSearchStore(
    (state) => state.loadSavedSearches
  );
  const executeSavedSearch = useLiteratureSearchStore(
    (state) => state.executeSavedSearch
  );
  const deleteSavedSearch = useLiteratureSearchStore(
    (state) => state.deleteSavedSearch
  );
  const isLoading = useLiteratureSearchStore((state) => state.isLoading);

  useEffect(() => {
    loadSavedSearches();
  }, [loadSavedSearches]);

  const handleExecute = async (id: number) => {
    await executeSavedSearch(id);
  };

  const handleDelete = async (id: number) => {
    await deleteSavedSearch(id);
  };

  return (
    <div className="flex flex-col border rounded-lg bg-background">
      <button
        type="button"
        className="flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-accent/50 transition-colors"
        onClick={() => setIsCollapsed(!isCollapsed)}
        aria-expanded={!isCollapsed}
        aria-controls="saved-searches-list"
      >
        <span>Saved Searches</span>
        <span className="text-muted-foreground text-xs">
          {isCollapsed ? "▶" : "▼"}
        </span>
      </button>

      {!isCollapsed && (
        <div id="saved-searches-list" className="border-t">
          {savedSearchesLoading ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              Loading saved searches...
            </div>
          ) : savedSearches.length === 0 ? (
            <div className="px-4 py-6 text-center text-sm text-muted-foreground">
              No saved searches yet.
            </div>
          ) : (
            <ScrollArea className="max-h-[400px]">
              <ul className="divide-y" role="list">
                {savedSearches.map((search) => (
                  <SavedSearchItem
                    key={search.id}
                    search={search}
                    onExecute={handleExecute}
                    onDelete={handleDelete}
                    isExecuting={isLoading}
                  />
                ))}
              </ul>
            </ScrollArea>
          )}
        </div>
      )}
    </div>
  );
}

interface SavedSearchItemProps {
  search: SavedSearch;
  onExecute: (id: number) => void;
  onDelete: (id: number) => void;
  isExecuting: boolean;
}

function SavedSearchItem({
  search,
  onExecute,
  onDelete,
  isExecuting,
}: SavedSearchItemProps) {
  return (
    <li className="px-4 py-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate" title={search.name}>
            {search.name}
          </p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
            {search.last_executed_at && (
              <span>{formatDate(search.last_executed_at)}</span>
            )}
            {search.last_result_count !== null && (
              <span>
                {search.last_result_count}{" "}
                {search.last_result_count === 1 ? "result" : "results"}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => onExecute(search.id)}
          disabled={isExecuting}
        >
          Re-execute
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-destructive hover:text-destructive"
          onClick={() => onDelete(search.id)}
          disabled={isExecuting}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}

/** Format an ISO date string as a relative or formatted date. */
function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
