import { create } from "zustand";
import { apiClient } from "../lib/apiClient";

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

export interface SearchFilters {
  document_type: string[];
  status: string[];
  tags: string[];
}

export interface SearchResult {
  document_uuid: string;
  title: string;
  version: string;
  excerpt: string;
  relevance_score: number;
  document_type: string | null;
  status: string | null;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
}

interface SearchResponse {
  results: SearchResult[];
  total: number;
  total_available: number;
  query: string;
  offset: number;
  filters_applied: Record<string, string[]>;
}

export interface SearchState {
  query: string;
  results: SearchResult[];
  isSearching: boolean;
  error: string | null;
  filters: SearchFilters;
  offset: number;
  limit: number;
  totalAvailable: number;
  sortBy: "relevance" | "date";

  setQuery: (query: string) => void;
  search: () => Promise<void>;
  setFilter: (category: keyof SearchFilters, value: string) => void;
  setSortBy: (sortBy: "relevance" | "date") => void;
  nextPage: () => void;
  previousPage: () => void;
  clearResults: () => void;
}

// ---------------------------------------------------------------------------
// Default state values
// ---------------------------------------------------------------------------

const DEFAULT_FILTERS: SearchFilters = {
  document_type: [],
  status: [],
  tags: [],
};

const DEFAULT_LIMIT = 20;

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useSearchStore = create<SearchState>((set, get) => ({
  query: "",
  results: [],
  isSearching: false,
  error: null,
  filters: { ...DEFAULT_FILTERS },
  offset: 0,
  limit: DEFAULT_LIMIT,
  totalAvailable: 0,
  sortBy: "relevance",

  setQuery: (query) => set({ query }),

  search: async () => {
    const state = get();

    // Guard against concurrent calls
    if (state.isSearching) {
      return;
    }

    // Reject whitespace-only queries
    if (!state.query.trim()) {
      get().clearResults();
      return;
    }

    // Truncate query to 1000 characters
    const truncatedQuery = state.query.slice(0, 1000);

    set({ isSearching: true, error: null });

    try {
      const body = {
        query: truncatedQuery,
        user_id: 1, // Placeholder until auth integration
        limit: state.limit,
        filters: state.filters,
        offset: state.offset,
        sort_by: state.sortBy,
      };

      const response = await apiClient.post<SearchResponse>(
        "/api/search",
        body,
        { changeReason: "Document search query" }
      );

      set({
        results: response.results,
        totalAvailable: response.total_available,
        isSearching: false,
      });
    } catch (error: unknown) {
      const message =
        error instanceof Error
          ? error.message
          : "Search is temporarily unavailable. Please try again.";

      set({
        error: message,
        results: [],
        totalAvailable: 0,
        isSearching: false,
      });
    }
  },

  setFilter: (category, value) => {
    const state = get();
    const currentValues = [...state.filters[category]];
    const index = currentValues.indexOf(value);

    if (index === -1) {
      currentValues.push(value);
    } else {
      currentValues.splice(index, 1);
    }

    set({
      filters: { ...state.filters, [category]: currentValues },
      offset: 0,
    });

    get().search();
  },

  setSortBy: (sortBy) => {
    set({ sortBy, offset: 0 });
    get().search();
  },

  nextPage: () => {
    const state = get();
    if (state.offset + state.limit < state.totalAvailable) {
      set({ offset: state.offset + state.limit });
      get().search();
    }
  },

  previousPage: () => {
    const state = get();
    const newOffset = Math.max(0, state.offset - state.limit);
    set({ offset: newOffset });
    get().search();
  },

  clearResults: () =>
    set({
      query: "",
      results: [],
      isSearching: false,
      error: null,
      filters: { document_type: [], status: [], tags: [] },
      offset: 0,
      totalAvailable: 0,
      sortBy: "relevance",
    }),
}));
