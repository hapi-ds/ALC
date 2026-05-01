import { create } from "zustand";

interface Document {
  id: number;
  document_uuid: string;
  title: string;
  document_type: string;
  current_status: string;
  tags: string[];
  created_at: string;
}

interface DocumentVersion {
  id: number;
  major_version: number;
  minor_version: number;
  uploaded_at: string;
  change_reason: string;
}

interface DocumentState {
  documents: Document[];
  selectedDocument: Document | null;
  versions: DocumentVersion[];
  isLoading: boolean;
  fetchDocuments: (filters?: Record<string, string>) => Promise<void>;
  fetchDocument: (uuid: string) => Promise<void>;
  fetchVersions: (uuid: string) => Promise<void>;
  uploadDocument: (file: File, metadata: Record<string, string>) => Promise<void>;
  createVersion: (uuid: string, file: File, reason: string) => Promise<void>;
}

export const useDocumentStore = create<DocumentState>((set) => ({
  documents: [],
  selectedDocument: null,
  versions: [],
  isLoading: false,

  fetchDocuments: async (_filters) => {
    set({ isLoading: true });
    // Placeholder: GET /api/documents
    set({ documents: [], isLoading: false });
  },

  fetchDocument: async (_uuid) => {
    set({ isLoading: true });
    // Placeholder: GET /api/documents/{uuid}
    set({ selectedDocument: null, isLoading: false });
  },

  fetchVersions: async (_uuid) => {
    // Placeholder: GET /api/documents/{uuid}/versions
    set({ versions: [] });
  },

  uploadDocument: async (_file, _metadata) => {
    // Placeholder: POST /api/documents
  },

  createVersion: async (_uuid, _file, _reason) => {
    // Placeholder: POST /api/documents/{uuid}/versions
  },
}));
