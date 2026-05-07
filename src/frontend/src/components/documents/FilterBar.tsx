import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentStore } from "@/stores/documentStore";

export function FilterBar() {
  const { tagFilter, folderPathFilter, setTagFilter, setFolderPathFilter, clearFilters, fetchDocuments } =
    useDocumentStore();

  function handleTagChange(value: string) {
    const filter = value.trim() || null;
    setTagFilter(filter);
    fetchDocuments();
  }

  function handleFolderPathChange(value: string) {
    const filter = value.trim() || null;
    setFolderPathFilter(filter);
    fetchDocuments();
  }

  function handleClear() {
    clearFilters();
    fetchDocuments();
  }

  const hasActiveFilters = tagFilter !== null || folderPathFilter !== null;

  return (
    <div className="flex flex-wrap items-center gap-3" role="search" aria-label="Document filters">
      <div className="flex-1 min-w-[160px]">
        <label htmlFor="filter-tag" className="sr-only">
          Filter by tag
        </label>
        <input
          id="filter-tag"
          type="text"
          value={tagFilter ?? ""}
          onChange={(e) => handleTagChange(e.target.value)}
          placeholder="Filter by tag"
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </div>

      <div className="flex-1 min-w-[160px]">
        <label htmlFor="filter-folder-path" className="sr-only">
          Filter by folder path
        </label>
        <input
          id="filter-folder-path"
          type="text"
          value={folderPathFilter ?? ""}
          onChange={(e) => handleFolderPathChange(e.target.value)}
          placeholder="Filter by folder path"
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </div>

      {hasActiveFilters && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleClear}
          aria-label="Clear all filters"
        >
          <X className="h-4 w-4 mr-1" aria-hidden="true" />
          Clear
        </Button>
      )}
    </div>
  );
}
