import { useCallback } from "react";
import type { TagFilter } from "@/types/virtualFolder";
import { buildTagFilter } from "@/lib/virtualFolderUtils";

export interface FilterBuilderProps {
  value: TagFilter;
  onChange: (filter: TagFilter) => void;
}

const AVAILABLE_TAGS = ["SOP", "Protocol", "Report", "General", "Policy", "Form"] as const;
const STATUS_OPTIONS = ["Draft", "Active", "Approved", "InTraining", "Retired"] as const;

/**
 * FilterBuilder provides a visual interface for constructing TagFilter expressions.
 *
 * - Multi-select checkbox list for tags
 * - Dropdown for status selection
 * - Live JSON preview of the resulting TagFilter
 * - Calls onChange whenever selection changes
 */
export function FilterBuilder({ value, onChange }: FilterBuilderProps) {
  const selectedTags = value.tags ?? [];
  const selectedStatus = value.status ?? null;

  const isEmpty = selectedTags.length === 0 && !selectedStatus;

  const handleTagToggle = useCallback(
    (tag: string) => {
      const newTags = selectedTags.includes(tag)
        ? selectedTags.filter((t) => t !== tag)
        : [...selectedTags, tag];
      onChange(buildTagFilter(newTags, selectedStatus));
    },
    [selectedTags, selectedStatus, onChange],
  );

  const handleStatusChange = useCallback(
    (status: string) => {
      const newStatus = status === "" ? null : status;
      onChange(buildTagFilter(selectedTags, newStatus));
    },
    [selectedTags, onChange],
  );

  return (
    <div className="space-y-4">
      {/* Tag multi-select */}
      <fieldset>
        <legend className="mb-1.5 block text-sm font-medium text-foreground">
          Tags
        </legend>
        <div className="grid grid-cols-2 gap-2" role="group" aria-label="Tag selection">
          {AVAILABLE_TAGS.map((tag) => (
            <label
              key={tag}
              className="flex items-center gap-2 rounded-md border border-input px-3 py-2 text-sm cursor-pointer hover:bg-accent/50 transition-colors has-[:checked]:border-primary has-[:checked]:bg-primary/5"
            >
              <input
                type="checkbox"
                checked={selectedTags.includes(tag)}
                onChange={() => handleTagToggle(tag)}
                className="h-4 w-4 rounded border-input text-primary focus:ring-1 focus:ring-ring"
                aria-label={`Select tag: ${tag}`}
              />
              <span>{tag}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {/* Status dropdown */}
      <div>
        <label
          htmlFor="filter-status"
          className="mb-1.5 block text-sm font-medium text-foreground"
        >
          Status
        </label>
        <select
          id="filter-status"
          value={selectedStatus ?? ""}
          onChange={(e) => handleStatusChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <option value="">No status filter</option>
          {STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </div>

      {/* Live JSON preview */}
      <div>
        <label className="mb-1.5 block text-sm font-medium text-foreground">
          Filter Preview
        </label>
        <pre
          className="rounded-md border border-input bg-muted/50 px-3 py-2 text-xs font-mono text-muted-foreground overflow-x-auto"
          aria-live="polite"
          aria-label="Tag filter JSON preview"
        >
          {JSON.stringify(value, null, 2)}
        </pre>
        {isEmpty && (
          <p className="mt-1 text-xs text-muted-foreground">
            Select at least one tag or status to create a filter.
          </p>
        )}
      </div>
    </div>
  );
}
