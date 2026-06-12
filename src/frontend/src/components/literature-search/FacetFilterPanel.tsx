import { useState, type KeyboardEvent } from "react";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Device classification options from Phase 9.5 enum. */
const DEVICE_CLASSES = ["Class I", "Class IIa", "Class IIb", "Class III"];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface MultiSelectSectionProps {
  title: string;
  options: { value: string; count: number }[];
  selected: string[];
  onChange: (values: string[]) => void;
}

/** Checkbox-based multi-select section with count badges. */
function MultiSelectSection({
  title,
  options,
  selected,
  onChange,
}: MultiSelectSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const displayOptions = expanded ? options : options.slice(0, 5);

  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-foreground">{title}</h4>
      {options.length === 0 ? (
        <p className="text-xs text-muted-foreground">No options available</p>
      ) : (
        <>
          <div className="space-y-1">
            {displayOptions.map((opt) => (
              <label
                key={opt.value}
                className="flex items-center gap-2 cursor-pointer text-sm"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(opt.value)}
                  onChange={() => toggle(opt.value)}
                  className="rounded border-input"
                />
                <span className="flex-1 truncate">{opt.value}</span>
                <Badge variant="secondary" className="text-xs px-1.5 py-0">
                  {opt.count}
                </Badge>
              </label>
            ))}
          </div>
          {options.length > 5 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs px-2"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Show less" : `Show all (${options.length})`}
            </Button>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Static multi-select (no facet counts, e.g. device class)
// ---------------------------------------------------------------------------

interface StaticMultiSelectProps {
  title: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}

function StaticMultiSelect({
  title,
  options,
  selected,
  onChange,
}: StaticMultiSelectProps) {
  const toggle = (value: string) => {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  };

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-foreground">{title}</h4>
      <div className="space-y-1">
        {options.map((opt) => (
          <label
            key={opt}
            className="flex items-center gap-2 cursor-pointer text-sm"
          >
            <input
              type="checkbox"
              checked={selected.includes(opt)}
              onChange={() => toggle(opt)}
              className="rounded border-input"
            />
            <span className="flex-1">{opt}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MeSH Tag Input
// ---------------------------------------------------------------------------

interface TagInputProps {
  title: string;
  tags: string[];
  onChange: (tags: string[]) => void;
}

function TagInput({ title, tags, onChange }: TagInputProps) {
  const [inputValue, setInputValue] = useState("");

  const addTag = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
    }
    setInputValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag();
    }
  };

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag));
  };

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-foreground">{title}</h4>
      <Input
        placeholder="Type and press Enter…"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className="h-8 text-sm"
      />
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map((tag) => (
            <Badge
              key={tag}
              variant="secondary"
              className="text-xs cursor-pointer hover:bg-destructive/20"
              onClick={() => removeTag(tag)}
            >
              {tag} ×
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FacetFilterPanel
// ---------------------------------------------------------------------------

export default function FacetFilterPanel() {
  const filters = useLiteratureSearchStore((s) => s.filters);
  const setFilters = useLiteratureSearchStore((s) => s.setFilters);
  const facetCounts = useLiteratureSearchStore((s) => s.facetCounts);

  return (
    <aside className="flex flex-col gap-5 p-4 border-r border-border min-w-[240px] max-w-[300px] overflow-y-auto">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Filters
      </h3>

      {/* Date Range */}
      <div className="space-y-2">
        <h4 className="text-sm font-medium text-foreground">Date Range</h4>
        <div className="flex flex-col gap-1.5">
          <Input
            type="date"
            value={filters.date_from ?? ""}
            onChange={(e) =>
              setFilters({ date_from: e.target.value || null })
            }
            className="h-8 text-sm"
            aria-label="Date from"
          />
          <Input
            type="date"
            value={filters.date_to ?? ""}
            onChange={(e) =>
              setFilters({ date_to: e.target.value || null })
            }
            className="h-8 text-sm"
            aria-label="Date to"
          />
        </div>
      </div>

      {/* Journals */}
      <MultiSelectSection
        title="Journals"
        options={facetCounts?.journals ?? []}
        selected={filters.journals}
        onChange={(journals) => setFilters({ journals })}
      />

      {/* Sources */}
      <MultiSelectSection
        title="Sources"
        options={facetCounts?.sources ?? []}
        selected={filters.sources}
        onChange={(sources) => setFilters({ sources })}
      />

      {/* Publication Types */}
      <MultiSelectSection
        title="Publication Type"
        options={facetCounts?.publication_types ?? []}
        selected={filters.publication_types}
        onChange={(publication_types) => setFilters({ publication_types })}
      />

      {/* MeSH Terms */}
      <TagInput
        title="MeSH Terms"
        tags={filters.mesh_terms}
        onChange={(mesh_terms) => setFilters({ mesh_terms })}
      />

      {/* Device Class */}
      <StaticMultiSelect
        title="Device Class"
        options={DEVICE_CLASSES}
        selected={filters.device_class}
        onChange={(device_class) => setFilters({ device_class })}
      />

      {/* Reset Filters */}
      <Button
        variant="outline"
        size="sm"
        className="w-full"
        onClick={() =>
          setFilters({
            date_from: null,
            date_to: null,
            journals: [],
            sources: [],
            publication_types: [],
            mesh_terms: [],
            device_class: [],
          })
        }
      >
        Clear All Filters
      </Button>
    </aside>
  );
}
