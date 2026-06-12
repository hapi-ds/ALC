import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";
import { SearchInput } from "@/components/literature-search/SearchInput";
import { SearchModeSelector } from "@/components/literature-search/SearchModeSelector";
import FacetFilterPanel from "@/components/literature-search/FacetFilterPanel";
import { SearchResultsList } from "@/components/literature-search/SearchResultsList";
import PaginationControls from "@/components/literature-search/PaginationControls";
import { SavedSearchesPanel } from "@/components/literature-search/SavedSearchesPanel";
import { SearchHistoryPanel } from "@/components/literature-search/SearchHistoryPanel";
import { ExportMenu } from "@/components/literature-search/ExportMenu";
import { SaveSearchDialog } from "@/components/literature-search/SaveSearchDialog";
import { InternalizationDialog } from "@/components/literature-search/InternalizationDialog";
import type { LiteratureSearchResult } from "@/types/literatureSearch";

/**
 * LiteratureSearchPage is the main dashboard page for executing faceted
 * literature searches, managing saved searches, viewing search history,
 * and internalizing external literature records.
 *
 * Layout:
 *  - Left sidebar: FacetFilterPanel
 *  - Center: Search bar, mode selector, results list, pagination
 *  - Right sidebar: Saved searches + search history (tabs)
 *  - Top-right: Export menu + Save Search button
 *
 * On mount: loads saved searches and search history.
 * Error states are shown via toast notifications.
 *
 * Validates: Requirements 9.1, 9.11, 9.12
 */
export default function LiteratureSearchPage() {
  const {
    error,
    searchExecutionId,
    loadSavedSearches,
    loadSearchHistory,
  } = useLiteratureSearchStore();

  // Save search dialog state
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);

  // Internalization dialog state
  const [internalizingResult, setInternalizingResult] =
    useState<LiteratureSearchResult | null>(null);

  // Load saved searches and history on mount
  useEffect(() => {
    loadSavedSearches();
    loadSearchHistory();
  }, [loadSavedSearches, loadSearchHistory]);

  // Display error toasts when the store error state changes
  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  const handleInternalize = useCallback(
    (result: LiteratureSearchResult) => {
      setInternalizingResult(result);
    },
    [],
  );

  const handleInternalizationClose = useCallback((open: boolean) => {
    if (!open) {
      setInternalizingResult(null);
    }
  }, []);

  return (
    <div className="flex h-full gap-6">
      {/* Left Sidebar — Facet Filters */}
      <aside className="hidden w-64 shrink-0 lg:block">
        <FacetFilterPanel />
      </aside>

      {/* Main Content */}
      <main className="flex min-w-0 flex-1 flex-col gap-4">
        {/* Top bar: Search + Mode + Actions */}
        <div className="flex flex-col gap-3">
          <div className="flex items-start gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <SearchInput />
              <SearchModeSelector />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="outline"
                onClick={() => setSaveDialogOpen(true)}
                aria-label="Save current search"
              >
                <Save className="h-4 w-4" aria-hidden="true" />
                Save
              </Button>
              <ExportMenu searchExecutionId={searchExecutionId} />
            </div>
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto">
          <SearchResultsList
            canInternalize
            onInternalize={handleInternalize}
          />
        </div>

        {/* Pagination */}
        <PaginationControls />
      </main>

      {/* Right Sidebar — Saved Searches & History */}
      <aside className="hidden w-72 shrink-0 xl:block">
        <Tabs defaultValue="saved" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="saved" className="flex-1">
              Saved
            </TabsTrigger>
            <TabsTrigger value="history" className="flex-1">
              History
            </TabsTrigger>
          </TabsList>
          <TabsContent value="saved" className="mt-3">
            <SavedSearchesPanel />
          </TabsContent>
          <TabsContent value="history" className="mt-3">
            <SearchHistoryPanel />
          </TabsContent>
        </Tabs>
      </aside>

      {/* Save Search Dialog */}
      <SaveSearchDialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen} />

      {/* Internalization Dialog */}
      {internalizingResult && (
        <InternalizationDialog
          open={!!internalizingResult}
          onOpenChange={handleInternalizationClose}
          ingestionRecordId={internalizingResult.id}
          defaultTitle={internalizingResult.title}
        />
      )}
    </div>
  );
}
