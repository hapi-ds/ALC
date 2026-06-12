import { create } from "zustand";
import { apiClient } from "../lib/apiClient";
import type {
  SearchMode,
  SearchFilters,
  LiteratureSearchResult,
  PaginationMeta,
  FacetCounts,
  SavedSearch,
  SearchHistoryEntry,
} from "../types/literatureSearch";

// ---------------------------------------------------------------------------
// API Response Types
// ---------------------------------------------------------------------------

interface SearchResponse {
  results: LiteratureSearchResult[];
  pagination: PaginationMeta;
  facets: FacetCounts;
  search_execution_id: number;
}

interface SavedSearchesResponse {
  items: SavedSearch[];
  total: number;
}

interface SearchHistoryResponse {
  items: SearchHistoryEntry[];
  total: number;
}

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface LiteratureSearchState {
  // Query state
  queryText: string;
  searchMode: SearchMode;
  includeInternal: boolean;
  filters: SearchFilters;

  // Results state
  results: LiteratureSearchResult[];
  pagination: PaginationMeta | null;
  facetCounts: FacetCounts | null;
  isLoading: boolean;
  error: string | null;
  searchExecutionId: number | null;

  // Saved searches
  savedSearches: SavedSearch[];
  savedSearchesLoading: boolean;

  // Search history
  searchHistory: SearchHistoryEntry[];

  // Actions
  setQueryText: (text: string) => void;
  setSearchMode: (mode: SearchMode) => void;
  setIncludeInternal: (include: boolean) => void;
  setFilters: (filters: Partial<SearchFilters>) => void;
  executeSearch: (page?: number) => Promise<void>;
  loadSavedSearches: () => Promise<void>;
  saveCurrentSearch: (name: string, description?: string) => Promise<void>;
  executeSavedSearch: (id: number) => Promise<void>;
  deleteSavedSearch: (id: number) => Promise<void>;
  loadSearchHistory: () => Promise<void>;
  resetSearch: () => void;
}

// ---------------------------------------------------------------------------
// Default State Values
// ---------------------------------------------------------------------------

const DEFAULT_FILTERS: SearchFilters = {
  date_from: null,
  date_to: null,
  journals: [],
  sources: [],
  publication_types: [],
  mesh_terms: [],
  device_class: [],
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useLiteratureSearchStore = create<LiteratureSearchState>(
  (set, get) => ({
    // Query state
    queryText: "",
    searchMode: "hybrid",
    includeInternal: false,
    filters: { ...DEFAULT_FILTERS },

    // Results state
    results: [],
    pagination: null,
    facetCounts: null,
    isLoading: false,
    error: null,
    searchExecutionId: null,

    // Saved searches
    savedSearches: [],
    savedSearchesLoading: false,

    // Search history
    searchHistory: [],

    // --- Actions ---

    setQueryText: (text: string) => set({ queryText: text }),

    setSearchMode: (mode: SearchMode) => set({ searchMode: mode }),

    setIncludeInternal: (include: boolean) => set({ includeInternal: include }),

    setFilters: (filters: Partial<SearchFilters>) => {
      const current = get().filters;
      set({ filters: { ...current, ...filters } });
    },

    executeSearch: async (page = 1) => {
      const state = get();

      // Guard against concurrent calls
      if (state.isLoading) {
        return;
      }

      // Reject whitespace-only queries
      if (!state.queryText.trim()) {
        return;
      }

      set({ isLoading: true, error: null });

      try {
        const body = {
          query_text: state.queryText.trim(),
          filters: state.filters,
          search_mode: state.searchMode,
          include_internal: state.includeInternal,
          page,
          page_size: 20,
        };

        const response = await apiClient.post<SearchResponse>(
          "/api/literature-search/query",
          body,
          { changeReason: "Literature search query execution" },
        );

        set({
          results: response.results,
          pagination: response.pagination,
          facetCounts: response.facets,
          searchExecutionId: response.search_execution_id,
          isLoading: false,
        });
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Search failed. Please try again.";

        set({
          results: [],
          pagination: null,
          facetCounts: null,
          searchExecutionId: null,
          isLoading: false,
          error: message,
        });
      }
    },

    loadSavedSearches: async () => {
      set({ savedSearchesLoading: true });

      try {
        const response = await apiClient.get<SavedSearchesResponse>(
          "/api/literature-search/saved-searches",
        );

        set({
          savedSearches: response.items,
          savedSearchesLoading: false,
        });
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to load saved searches.";

        set({
          savedSearchesLoading: false,
          error: message,
        });
      }
    },

    saveCurrentSearch: async (name: string, description?: string) => {
      const state = get();

      try {
        const body = {
          name,
          description: description ?? null,
          query_text: state.queryText.trim(),
          filters: state.filters,
          search_mode: state.searchMode,
          include_internal: state.includeInternal,
        };

        await apiClient.post<SavedSearch>(
          "/api/literature-search/saved-searches",
          body,
          { changeReason: "Save literature search configuration" },
        );

        // Reload saved searches to reflect the new entry
        await get().loadSavedSearches();
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to save search.";

        set({ error: message });
      }
    },

    executeSavedSearch: async (id: number) => {
      const state = get();

      if (state.isLoading) {
        return;
      }

      set({ isLoading: true, error: null });

      try {
        const response = await apiClient.post<SearchResponse>(
          `/api/literature-search/saved-searches/${id}/execute`,
          undefined,
          { changeReason: "Execute saved literature search" },
        );

        set({
          results: response.results,
          pagination: response.pagination,
          facetCounts: response.facets,
          searchExecutionId: response.search_execution_id,
          isLoading: false,
        });
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to execute saved search.";

        set({
          results: [],
          pagination: null,
          facetCounts: null,
          searchExecutionId: null,
          isLoading: false,
          error: message,
        });
      }
    },

    deleteSavedSearch: async (id: number) => {
      try {
        await apiClient.delete(
          `/api/literature-search/saved-searches/${id}`,
          { changeReason: "Delete saved literature search" },
        );

        // Remove from local state
        const current = get().savedSearches;
        set({ savedSearches: current.filter((s) => s.id !== id) });
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to delete saved search.";

        set({ error: message });
      }
    },

    loadSearchHistory: async () => {
      try {
        const response = await apiClient.get<SearchHistoryResponse>(
          "/api/literature-search/history",
        );

        set({ searchHistory: response.items });
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to load search history.";

        set({ error: message });
      }
    },

    resetSearch: () =>
      set({
        queryText: "",
        searchMode: "hybrid",
        includeInternal: false,
        filters: { ...DEFAULT_FILTERS },
        results: [],
        pagination: null,
        facetCounts: null,
        searchExecutionId: null,
        isLoading: false,
        error: null,
      }),
  }),
);
