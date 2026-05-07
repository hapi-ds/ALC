import { create } from "zustand";
import type { TemplateResponse } from "../types/template";
import { apiClient } from "../lib/apiClient";

interface TemplateListState {
  templates: TemplateResponse[];
  isLoading: boolean;
  error: string | null;

  fetchTemplates: () => Promise<void>;
}

/** Timeout duration for template list fetch (ms) */
const FETCH_TIMEOUT_MS = 30_000;

export const useTemplateListStore = create<TemplateListState>((set) => ({
  templates: [],
  isLoading: false,
  error: null,

  fetchTemplates: async () => {
    set({ isLoading: true, error: null });

    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    try {
      const response = await Promise.race([
        apiClient.get<TemplateResponse[]>("/api/templates"),
        new Promise<never>((_, reject) => {
          timeoutId = setTimeout(() => {
            reject(new DOMException("The operation timed out.", "AbortError"));
          }, FETCH_TIMEOUT_MS);
        }),
      ]);

      set({ templates: response, isLoading: false });
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        set({ error: "Request timed out", isLoading: false });
      } else {
        set({ error: "Failed to load templates", isLoading: false });
      }
    } finally {
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    }
  },
}));
