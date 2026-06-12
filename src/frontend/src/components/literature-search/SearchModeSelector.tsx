import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";
import type { SearchMode } from "@/types/literatureSearch";

const MODE_OPTIONS: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Hybrid" },
  { value: "keyword", label: "Keyword" },
  { value: "semantic", label: "Semantic" },
];

/**
 * SearchModeSelector provides a segmented control for selecting the search
 * mode (hybrid/keyword/semantic) and a toggle for including internal documents.
 * Reads and writes to the literatureSearchStore.
 *
 * Validates: Requirements 9.2
 */
export function SearchModeSelector() {
  const { searchMode, setSearchMode, includeInternal, setIncludeInternal } =
    useLiteratureSearchStore();

  return (
    <div className="flex flex-wrap items-center gap-4">
      {/* Search mode segmented control */}
      <div
        role="radiogroup"
        aria-label="Search mode"
        className="flex gap-1 rounded-lg bg-muted p-1"
      >
        {MODE_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={searchMode === option.value}
            onClick={() => setSearchMode(option.value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              searchMode === option.value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Include Internal Documents toggle */}
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <button
          type="button"
          role="switch"
          aria-checked={includeInternal}
          onClick={() => setIncludeInternal(!includeInternal)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
            includeInternal ? "bg-primary" : "bg-muted-foreground/30"
          }`}
          aria-label="Include internal documents"
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
              includeInternal ? "translate-x-4.5" : "translate-x-0.5"
            }`}
          />
        </button>
        <span className="text-sm text-foreground">Include Internal Documents</span>
      </label>
    </div>
  );
}
