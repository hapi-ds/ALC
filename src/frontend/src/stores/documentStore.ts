import { create } from "zustand";
import type {
  DocumentResponse,
  DocumentSearchResponse,
  DocumentVersion,
} from "../types/document";
import { apiClient, ApiError } from "../lib/apiClient";
import { getAccessToken } from "../lib/tokenStorage";

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

  // Version state
  selectedVersion: DocumentVersion | null;
  isVersionLoading: boolean;
  versionError: string | null;
  downloadingVersionId: number | null;
  comparisonOpen: boolean;

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

  // Version actions
  fetchVersion: (uuid: string, major: number, minor: number) => Promise<void>;
  selectVersionFromCache: (version: DocumentVersion) => void;
  clearSelectedVersion: () => void;
  downloadVersion: (
    documentUuid: string,
    version: DocumentVersion,
    documentTitle: string
  ) => Promise<void>;
  setComparisonOpen: (open: boolean) => void;
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

  // Version state
  selectedVersion: null,
  isVersionLoading: false,
  versionError: null,
  downloadingVersionId: null,
  comparisonOpen: false,

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

  // Version actions

  fetchVersion: async (uuid: string, major: number, minor: number) => {
    set({ isVersionLoading: true, versionError: null, selectedVersion: null });

    try {
      const response = await apiClient.get<DocumentVersion>(
        `/api/documents/${uuid}/versions/${major}/${minor}`
      );
      set({ selectedVersion: response, isVersionLoading: false });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        set({
          versionError: "Version not found",
          selectedVersion: null,
          isVersionLoading: false,
        });
      } else {
        const message =
          error instanceof Error ? error.message : "Failed to fetch version";
        set({
          versionError: message,
          selectedVersion: null,
          isVersionLoading: false,
        });
      }
    }
  },

  selectVersionFromCache: (version: DocumentVersion) => {
    set({ selectedVersion: version, versionError: null });
  },

  clearSelectedVersion: () => {
    set({ selectedVersion: null, versionError: null, isVersionLoading: false });
  },

  downloadVersion: async (
    documentUuid: string,
    version: DocumentVersion,
    documentTitle: string
  ) => {
    set({ downloadingVersionId: version.id });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30_000);

    try {
      const token = getAccessToken();
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(
        `/api/documents/${documentUuid}/versions/${version.major_version}/${version.minor_version}/download`,
        {
          headers,
          signal: controller.signal,
          credentials: "include",
        }
      );

      if (!response.ok) {
        throw new Error(`Download failed with status ${response.status}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);

      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${documentTitle}_v${version.major_version}.${version.minor_version}`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);

      URL.revokeObjectURL(url);
    } catch {
      // On error/timeout: silently clear state (don't throw)
    } finally {
      clearTimeout(timeoutId);
      set({ downloadingVersionId: null });
    }
  },

  setComparisonOpen: (open: boolean) => {
    set({ comparisonOpen: open });
  },
}));
