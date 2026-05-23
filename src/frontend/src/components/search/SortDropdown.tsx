import { ArrowUpDown } from "lucide-react";

export interface SortDropdownProps {
  value: "relevance" | "date";
  onChange: (sortBy: "relevance" | "date") => void;
}

/**
 * SortDropdown renders a select dropdown for choosing the search result sort order.
 * Options: "Most Relevant" (relevance) and "Most Recent" (date).
 *
 * Validates: Requirements 10.1, 10.3
 */
export function SortDropdown({ value, onChange }: SortDropdownProps) {
  return (
    <div className="flex items-center gap-2">
      <ArrowUpDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      <label htmlFor="sort-dropdown" className="text-sm text-muted-foreground whitespace-nowrap">
        Sort by:
      </label>
      <select
        id="sort-dropdown"
        value={value}
        onChange={(e) => onChange(e.target.value as "relevance" | "date")}
        className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm text-foreground shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
        aria-label="Sort search results"
      >
        <option value="relevance">Most Relevant</option>
        <option value="date">Most Recent</option>
      </select>
    </div>
  );
}
