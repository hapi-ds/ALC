import { useState, useCallback, type KeyboardEvent, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";

/**
 * SearchInput provides a text input with a search button for executing
 * literature search queries. Dispatches executeSearch from the store on
 * submit and disables submission for empty/whitespace-only queries.
 *
 * Validates: Requirements 9.2
 */
export function SearchInput() {
  const { queryText, setQueryText, executeSearch, isLoading } =
    useLiteratureSearchStore();

  const [localQuery, setLocalQuery] = useState(queryText);

  const isQueryEmpty = !localQuery.trim();

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      if (isQueryEmpty || isLoading) return;
      setQueryText(localQuery.trim());
      executeSearch();
    },
    [localQuery, isQueryEmpty, isLoading, setQueryText, executeSearch],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (isQueryEmpty || isLoading) return;
        setQueryText(localQuery.trim());
        executeSearch();
      }
    },
    [localQuery, isQueryEmpty, isLoading, setQueryText, executeSearch],
  );

  return (
    <form onSubmit={handleSubmit} className="flex w-full gap-2">
      <Input
        type="text"
        placeholder="Search literature..."
        value={localQuery}
        onChange={(e) => setLocalQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-label="Literature search query"
        className="flex-1"
        disabled={isLoading}
      />
      <Button
        type="submit"
        disabled={isQueryEmpty || isLoading}
        aria-label="Execute search"
      >
        <Search className="h-4 w-4" aria-hidden="true" />
        Search
      </Button>
    </form>
  );
}
