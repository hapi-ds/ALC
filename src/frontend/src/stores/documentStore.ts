import { create } from "zustand";
import type { DocumentResponse, DocumentSearchResponse } from "../types/document";
import { apiClient } from "../lib/apiClient";

export interface DocumentState {
  // Data
  documents: DocumentResponse[];
  selectedDocument: DocumentResponse | null;
  total: number;

  // Pagination
  offset: number;
  limit: number;

  // Filters
  tagFilter: string | null;
  folderPathFilter: string | null;

  // UI state
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchDocuments: () => Promise<void>;
  fetchDocument: (uuid: string) => Promise<void>;
  uploadDocument: (formData: FormData) => Promise<void>;
  createVersion: (uuid: string, formData: FormData) => Promise<void>;
  setPage: (page: number) => void;
  nextPage: () => void;
  prevPage: () => void;
  setTagFilter: (tag: string | null) => void;
  setFolderPathFilter: (path: string | null) => void;
  clearFilters: () => void;
}

export const useDocumentStore = create<DocumentState>((set, get) => ({
  // Data
  documents: [],
  selectedDocument: null,
  total: 0,

  // Pagination
  offset: 0,
  limit: 20,

  // Filters
  tagFilter: null,
  folderPathFilter: null,

  // UI state
  isLoading: false,
  error: null,

  fetchDocuments: async () => {
    const { offset, limit, tagFilter, folderPathFilter } = get();
    set({ isLoading: true, error: null });

    try {
      const params = new URLSearchParams();
      params.set("offset", String(offset));
      params.set("limit", String(limit));
      if (tagFilter) {
        params.set("tag", tagFilter);
      }
      if (folderPathFilter) {
        params.set("folder_path", folderPathFilter);
      }

      const response = await apiClient.get<DocumentSearchResponse>(
        `/api/documents?${params.toString()}`
      );

      set({
        documents: response.items,
        total: response.total,
        isLoading: false,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch documents";
      set({ error: message, isLoading: false });
    }
  },

  fetchDocument: async (uuid: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiClient.get<DocumentResponse>(
        `/api/documents/${uuid}`
      );
      set({ selectedDocument: response, isLoading: false });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch document";
      set({ error: message, isLoading: false });
    }
  },

  uploadDocument: async (formData: FormData) => {
    set({ isLoading: true, error: null });

    try {
      await apiClient.upload<DocumentResponse>(
        "/api/documents",
        formData,
        undefined,
        "Document upload"
      );
      set({ isLoading: false });
      // Refresh the document list after successful upload
      await get().fetchDocuments();
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  createVersion: async (uuid: string, formData: FormData) => {
    set({ isLoading: true, error: null });

    try {
      await apiClient.upload<DocumentResponse>(
        `/api/documents/${uuid}/versions`,
        formData,
        undefined,
        "New document version"
      );
      set({ isLoading: false });
      // Refresh the document detail after successful version creation
      await get().fetchDocument(uuid);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to create document version";
      set({ error: message, isLoading: false });
      throw error;
    }
  },

  setPage: (page: number) => {
    const { limit } = get();
    const offset = (page - 1) * limit;
    set({ offset: Math.max(0, offset) });
  },

  nextPage: () => {
    const { offset, limit } = get();
    set({ offset: offset + limit });
  },

  prevPage: () => {
    const { offset, limit } = get();
    set({ offset: Math.max(0, offset - limit) });
  },

  setTagFilter: (tag: string | null) => {
    set({ tagFilter: tag, offset: 0 });
  },

  setFolderPathFilter: (path: string | null) => {
    set({ folderPathFilter: path, offset: 0 });
  },

  clearFilters: () => {
    set({ tagFilter: null, folderPathFilter: null, offset: 0 });
  },
}));
