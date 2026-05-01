import { create } from "zustand";

interface SearchResult {
  document_uuid: string;
  title: string;
  version: string;
  excerpt: string;
  relevance_score: number;
}

interface SearchState {
  query: string;
  results: SearchResult[];
  isSearching: boolean;
  setQuery: (query: string) => void;
  search: (query: string) => Promise<void>;
  clearResults: () => void;
}

export const useSearchStore = create<SearchState>((set) => ({
  query: "",
  results: [],
  isSearching: false,

  setQuery: (query) => set({ query }),

  search: async (_query) => {
    set({ isSearching: true });
    // Placeholder: POST /api/search
    set({ results: [], isSearching: false });
  },

  clearResults: () => set({ results: [], query: "" }),
}));
