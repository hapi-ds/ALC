import { create } from "zustand";
import type {
  VirtualFolderResponse,
  VirtualFolderUpdate,
  TagFilter,
} from "../types/virtualFolder";
import type { DocumentResponse } from "../types/document";
import { apiClient } from "../lib/apiClient";

export interface VirtualFolderState {
  // Data
  folders: VirtualFolderResponse[];
  selectedFolder: VirtualFolderResponse | null;
  selectedFolderDocuments: DocumentResponse[];

  // Pagination
  documentsOffset: number;
  documentsLimit: number;

  // UI state
  isFoldersLoading: boolean;
  foldersError: string | null;
  isDocumentsLoading: boolean;
  documentsError: string | null;

  // Cache
  lastFetchedAt: number | null;

  // Actions
  fetchFolders: () => Promise<void>;
  createFolder: (
    name: string,
    tag_filter: TagFilter,
    sort_order: string
  ) => Promise<void>;
  updateFolder: (id: number, updates: VirtualFolderUpdate) => Promise<void>;
  deleteFolder: (id: number, changeReason: string) => Promise<void>;
  fetchFolderDocuments: (folderId: number) => Promise<void>;
  selectFolder: (folder: VirtualFolderResponse | null) => void;
  nextDocumentsPage: () => void;
  prevDocumentsPage: () => void;
}

export const useVirtualFolderStore = create<VirtualFolderState>((set, get) => ({
  // Data
  folders: [],
  selectedFolder: null,
  selectedFolderDocuments: [],

  // Pagination
  documentsOffset: 0,
  documentsLimit: 20,

  // UI state
  isFoldersLoading: false,
  foldersError: null,
  isDocumentsLoading: false,
  documentsError: null,

  // Cache
  lastFetchedAt: null,

  fetchFolders: async () => {
    set({ isFoldersLoading: true, foldersError: null });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15_000);

    try {
      const response = await Promise.race([
        apiClient.get<VirtualFolderResponse[]>("/api/virtual-folders"),
        new Promise<never>((_, reject) => {
          controller.signal.addEventListener("abort", () => {
            reject(new Error("Request timed out"));
          });
        }),
      ]);

      set({
        folders: response,
        isFoldersLoading: false,
        lastFetchedAt: Date.now(),
      });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to fetch virtual folders";
      set({ foldersError: message, isFoldersLoading: false });
    } finally {
      clearTimeout(timeoutId);
    }
  },

  createFolder: async (
    name: string,
    tag_filter: TagFilter,
    sort_order: string
  ) => {
    set({ isFoldersLoading: true, foldersError: null });

    try {
      await apiClient.post<VirtualFolderResponse>(
        "/api/virtual-folders",
        { name, tag_filter, sort_order },
        { changeReason: `Created virtual folder: ${name}` }
      );

      await get().fetchFolders();
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to create virtual folder";
      set({ foldersError: message, isFoldersLoading: false });
      throw error;
    }
  },

  updateFolder: async (id: number, updates: VirtualFolderUpdate) => {
    set({ isFoldersLoading: true, foldersError: null });

    try {
      const name =
        updates.name ?? get().folders.find((f) => f.id === id)?.name ?? "folder";
      await apiClient.put<VirtualFolderResponse>(
        `/api/virtual-folders/${id}`,
        updates,
        { changeReason: `Updated virtual folder: ${name}` }
      );

      await get().fetchFolders();
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update virtual folder";
      set({ foldersError: message, isFoldersLoading: false });
      throw error;
    }
  },

  deleteFolder: async (id: number, changeReason: string) => {
    set({ isFoldersLoading: true, foldersError: null });

    try {
      await apiClient.delete(`/api/virtual-folders/${id}`, { changeReason });

      // Remove from local state immediately
      const { selectedFolder, folders } = get();
      set({
        folders: folders.filter((f) => f.id !== id),
      });

      // Clear selectedFolder if it was the deleted one
      if (selectedFolder?.id === id) {
        set({ selectedFolder: null, selectedFolderDocuments: [] });
      }

      await get().fetchFolders();
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to delete virtual folder";
      set({ foldersError: message, isFoldersLoading: false });
      throw error;
    }
  },

  fetchFolderDocuments: async (folderId: number) => {
    const { documentsOffset, documentsLimit } = get();
    set({ isDocumentsLoading: true, documentsError: null });

    try {
      const params = new URLSearchParams();
      params.set("offset", String(documentsOffset));
      params.set("limit", String(documentsLimit));

      const response = await apiClient.get<DocumentResponse[]>(
        `/api/virtual-folders/${folderId}/documents?${params.toString()}`
      );

      set({
        selectedFolderDocuments: response,
        isDocumentsLoading: false,
      });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to fetch folder documents";
      set({ documentsError: message, isDocumentsLoading: false });
    }
  },

  selectFolder: (folder: VirtualFolderResponse | null) => {
    set({
      selectedFolder: folder,
      documentsOffset: 0,
      selectedFolderDocuments: [],
    });

    if (folder) {
      get().fetchFolderDocuments(folder.id);
    }
  },

  nextDocumentsPage: () => {
    const { documentsOffset, documentsLimit, selectedFolder } = get();
    set({ documentsOffset: documentsOffset + documentsLimit });

    if (selectedFolder) {
      get().fetchFolderDocuments(selectedFolder.id);
    }
  },

  prevDocumentsPage: () => {
    const { documentsOffset, documentsLimit, selectedFolder } = get();
    set({ documentsOffset: Math.max(0, documentsOffset - documentsLimit) });

    if (selectedFolder) {
      get().fetchFolderDocuments(selectedFolder.id);
    }
  },
}));
