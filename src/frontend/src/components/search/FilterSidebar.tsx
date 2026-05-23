import { useState } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SearchResult, SearchFilters } from "@/stores/searchStore";

interface FilterSidebarProps {
  results: SearchResult[];
  activeFilters: SearchFilters;
  onFilterToggle: (category: keyof SearchFilters, value: string) => void;
  onClearAll: () => void;
  disabled: boolean;
}

interface FilterSectionProps {
  title: string;
  category: keyof SearchFilters;
  options: string[];
  activeValues: string[];
  onToggle: (category: keyof SearchFilters, value: string) => void;
  disabled: boolean;
}

/**
 * A collapsible filter section with checkboxes for each available value.
 */
function FilterSection({
  title,
  category,
  options,
  activeValues,
  onToggle,
  disabled,
}: FilterSectionProps) {
  const [isOpen, setIsOpen] = useState(true);
  const activeCount = activeValues.length;

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className="flex w-full items-center justify-between px-3 py-2.5 text-sm font-medium text-foreground hover:bg-accent/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        aria-expanded={isOpen}
      >
        <span className="flex items-center gap-2">
          {isOpen && !disabled ? (
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          )}
          {title}
          {activeCount > 0 && (
            <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              {activeCount}
            </span>
          )}
        </span>
      </button>

      {isOpen && !disabled && (
        <div className="px-3 pb-3 space-y-1.5">
          {options.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No options available</p>
          ) : (
            options.map((value) => (
              <label
                key={value}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm cursor-pointer hover:bg-accent/50 transition-colors"
              >
                <input
                  type="checkbox"
                  checked={activeValues.includes(value)}
                  onChange={() => onToggle(category, value)}
                  className="h-4 w-4 rounded border-input text-primary focus:ring-1 focus:ring-ring"
                  aria-label={`Filter by ${title}: ${value}`}
                />
                <span className="text-foreground">{value}</span>
              </label>
            ))
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Derives distinct filter options from the current search results.
 */
function deriveFilterOptions(results: SearchResult[]) {
  const documentTypes = new Set<string>();
  const statuses = new Set<string>();
  const tags = new Set<string>();

  for (const result of results) {
    if (result.document_type) {
      documentTypes.add(result.document_type);
    }
    if (result.status) {
      statuses.add(result.status);
    }
    for (const tag of result.tags) {
      tags.add(tag);
    }
  }

  return {
    document_type: Array.from(documentTypes).sort(),
    status: Array.from(statuses).sort(),
    tags: Array.from(tags).sort(),
  };
}

/**
 * FilterSidebar renders collapsible filter sections for Document Type, Status, and Tags.
 * Filter options are derived from distinct metadata values in the current result set.
 *
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.6, 6.7, 8.4
 */
export function FilterSidebar({
  results,
  activeFilters,
  onFilterToggle,
  onClearAll,
  disabled,
}: FilterSidebarProps) {
  const options = deriveFilterOptions(results);

  const hasActiveFilters =
    activeFilters.document_type.length > 0 ||
    activeFilters.status.length > 0 ||
    activeFilters.tags.length > 0;

  if (disabled) {
    return (
      <aside className="w-full rounded-lg border border-border bg-card" aria-label="Search filters">
        <div className="p-4">
          <h2 className="text-sm font-semibold text-foreground mb-3">Filters</h2>
          <p className="text-sm text-muted-foreground">
            Perform a search to see available filters
          </p>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-full rounded-lg border border-border bg-card" aria-label="Search filters">
      <div className="p-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Filters</h2>
        {hasActiveFilters && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClearAll}
            className="h-7 px-2 text-xs"
            aria-label="Clear all filters"
          >
            <X className="h-3 w-3 mr-1" aria-hidden="true" />
            Clear all filters
          </Button>
        )}
      </div>

      <div>
        <FilterSection
          title="Document Type"
          category="document_type"
          options={options.document_type}
          activeValues={activeFilters.document_type}
          onToggle={onFilterToggle}
          disabled={disabled}
        />
        <FilterSection
          title="Status"
          category="status"
          options={options.status}
          activeValues={activeFilters.status}
          onToggle={onFilterToggle}
          disabled={disabled}
        />
        <FilterSection
          title="Tags"
          category="tags"
          options={options.tags}
          activeValues={activeFilters.tags}
          onToggle={onFilterToggle}
          disabled={disabled}
        />
      </div>
    </aside>
  );
}
