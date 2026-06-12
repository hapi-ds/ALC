import { useState, useCallback } from "react";
import { toast } from "sonner";
import { apiClient, ApiError } from "@/lib/apiClient";
import type {
  InternalizationRequest,
  CitationCollection,
  CitationCollectionDetail,
  CollectionPurpose,
  TraceabilityLink,
  TraceabilityTargetType,
  ExportRequest,
} from "@/types/literatureSearch";

// ─── Shared Types ───────────────────────────────────────────────────────────

interface MutationState {
  loading: boolean;
  error: string | null;
}

// ─── useInternalize ─────────────────────────────────────────────────────────

interface InternalizedDocumentResponse {
  document_id: number;
  title: string;
  status: string;
}

interface UseInternalizeReturn extends MutationState {
  internalize: (request: InternalizationRequest) => Promise<InternalizedDocumentResponse | null>;
}

/**
 * Hook for one-click internalization of a literature record into a managed Document.
 * POST /api/literature-search/internalize
 *
 * Handles 409 (duplicate internalization) as a special case with informative message.
 */
export function useInternalize(): UseInternalizeReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const internalize = useCallback(
    async (request: InternalizationRequest): Promise<InternalizedDocumentResponse | null> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.post<InternalizedDocumentResponse>(
          "/api/literature-search/internalize",
          request,
          { changeReason: "Internalize literature record into managed document" }
        );
        toast.success("Document internalized successfully.");
        return response;
      } catch (err: unknown) {
        let message: string;

        if (err instanceof ApiError && err.status === 409) {
          message = "This record has already been internalized. A document already exists for this literature entry.";
        } else if (err instanceof ApiError) {
          message = `Internalization failed (${err.status}): ${err.body}`;
        } else {
          message = "An unexpected error occurred during internalization.";
        }

        setError(message);
        toast.error(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { loading, error, internalize };
}


// ─── useCitationCollections ─────────────────────────────────────────────────

interface CreateCollectionParams {
  name: string;
  description?: string | null;
  purpose: CollectionPurpose;
}

interface UpdateCollectionParams {
  name?: string;
  description?: string | null;
  purpose?: CollectionPurpose;
}

interface UseCitationCollectionsReturn extends MutationState {
  create: (params: CreateCollectionParams) => Promise<CitationCollection | null>;
  list: () => Promise<CitationCollection[]>;
  get: (id: number) => Promise<CitationCollectionDetail | null>;
  update: (id: number, params: UpdateCollectionParams) => Promise<CitationCollection | null>;
  remove: (id: number) => Promise<boolean>;
  addDocuments: (collectionId: number, documentIds: number[]) => Promise<CitationCollectionDetail | null>;
  removeDocument: (collectionId: number, documentId: number) => Promise<boolean>;
}

/**
 * Hook for CRUD operations on citation collections.
 * Endpoints under /api/literature-search/citation-collections
 */
export function useCitationCollections(): UseCitationCollectionsReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = useCallback(
    async (params: CreateCollectionParams): Promise<CitationCollection | null> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.post<CitationCollection>(
          "/api/literature-search/citation-collections",
          params,
          { changeReason: "Create citation collection" }
        );
        toast.success("Citation collection created.");
        return response;
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? `Failed to create collection (${err.status}): ${err.body}`
            : "An unexpected error occurred.";
        setError(message);
        toast.error(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const list = useCallback(async (): Promise<CitationCollection[]> => {
    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.get<CitationCollection[]>(
        "/api/literature-search/citation-collections"
      );
      return response;
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? `Failed to list collections (${err.status}): ${err.body}`
          : "An unexpected error occurred.";
      setError(message);
      toast.error(message);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  const get = useCallback(
    async (id: number): Promise<CitationCollectionDetail | null> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.get<CitationCollectionDetail>(
          `/api/literature-search/citation-collections/${id}`
        );
        return response;
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? `Failed to get collection (${err.status}): ${err.body}`
            : "An unexpected error occurred.";
        setError(message);
        toast.error(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const update = useCallback(
    async (id: number, params: UpdateCollectionParams): Promise<CitationCollection | null> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.put<CitationCollection>(
          `/api/literature-search/citation-collections/${id}`,
          params,
          { changeReason: "Update citation collection" }
        );
        toast.success("Citation collection updated.");
        return response;
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? `Failed to update collection (${err.status}): ${err.body}`
            : "An unexpected error occurred.";
        setError(message);
        toast.error(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const remove = useCallback(async (id: number): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await apiClient.delete<void>(
        `/api/literature-search/citation-collections/${id}`,
        { changeReason: "Archive citation collection" }
      );
      toast.success("Citation collection archived.");
      return true;
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? `Failed to archive collection (${err.status}): ${err.body}`
          : "An unexpected error occurred.";
      setError(message);
      toast.error(message);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const addDocuments = useCallback(
    async (collectionId: number, documentIds: number[]): Promise<CitationCollectionDetail | null> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.post<CitationCollectionDetail>(
          `/api/literature-search/citation-collections/${collectionId}/documents`,
          { document_ids: documentIds },
          { changeReason: "Add documents to citation collection" }
        );
        toast.success("Documents added to collection.");
        return response;
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? `Failed to add documents (${err.status}): ${err.body}`
            : "An unexpected error occurred.";
        setError(message);
        toast.error(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const removeDocument = useCallback(
    async (collectionId: number, documentId: number): Promise<boolean> => {
      setLoading(true);
      setError(null);

      try {
        await apiClient.delete<void>(
          `/api/literature-search/citation-collections/${collectionId}/documents/${documentId}`,
          { changeReason: "Remove document from citation collection" }
        );
        toast.success("Document removed from collection.");
        return true;
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? `Failed to remove document (${err.status}): ${err.body}`
            : "An unexpected error occurred.";
        setError(message);
        toast.error(message);
        return false;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { loading, error, create, list, get, update, remove, addDocuments, removeDocument };
}


// ─── useTraceabilityLinks ───────────────────────────────────────────────────

interface CreateTraceabilityLinkParams {
  document_id: number;
  target_type: TraceabilityTargetType;
  target_id: number;
  rationale?: string | null;
}

interface UseTraceabilityLinksReturn extends MutationState {
  create: (params: CreateTraceabilityLinkParams) => Promise<TraceabilityLink | null>;
  list: (filters?: { document_id?: number; target_id?: number }) => Promise<TraceabilityLink[]>;
  remove: (linkId: number) => Promise<boolean>;
}

/**
 * Hook for creating, listing, and deleting traceability links
 * between internalized documents and requirements/test cases.
 * Endpoints under /api/literature-search/traceability-links
 */
export function useTraceabilityLinks(): UseTraceabilityLinksReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = useCallback(
    async (params: CreateTraceabilityLinkParams): Promise<TraceabilityLink | null> => {
      setLoading(true);
      setError(null);

      try {
        const response = await apiClient.post<TraceabilityLink>(
          "/api/literature-search/traceability-links",
          params,
          { changeReason: "Create traceability link" }
        );
        toast.success("Traceability link created.");
        return response;
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? `Failed to create traceability link (${err.status}): ${err.body}`
            : "An unexpected error occurred.";
        setError(message);
        toast.error(message);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const list = useCallback(
    async (filters?: { document_id?: number; target_id?: number }): Promise<TraceabilityLink[]> => {
      setLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams();
        if (filters?.document_id != null) {
          params.set("document_id", String(filters.document_id));
        }
        if (filters?.target_id != null) {
          params.set("target_id", String(filters.target_id));
        }

        const queryString = params.toString();
        const url = `/api/literature-search/traceability-links${queryString ? `?${queryString}` : ""}`;

        const response = await apiClient.get<TraceabilityLink[]>(url);
        return response;
      } catch (err: unknown) {
        const message =
          err instanceof ApiError
            ? `Failed to list traceability links (${err.status}): ${err.body}`
            : "An unexpected error occurred.";
        setError(message);
        toast.error(message);
        return [];
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const remove = useCallback(async (linkId: number): Promise<boolean> => {
    setLoading(true);
    setError(null);

    try {
      await apiClient.delete<void>(
        `/api/literature-search/traceability-links/${linkId}`,
        { changeReason: "Delete traceability link" }
      );
      toast.success("Traceability link deleted.");
      return true;
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? `Failed to delete traceability link (${err.status}): ${err.body}`
          : "An unexpected error occurred.";
      setError(message);
      toast.error(message);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  return { loading, error, create, list, remove };
}


// ─── useExport ──────────────────────────────────────────────────────────────

interface UseExportReturn extends MutationState {
  exportResults: (request: ExportRequest) => Promise<boolean>;
}

/**
 * Hook for exporting search results as CSV or PDF.
 * POST /api/literature-search/export
 *
 * Triggers a file download by fetching a blob response and creating
 * a temporary download link programmatically.
 */
export function useExport(): UseExportReturn {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const exportResults = useCallback(
    async (request: ExportRequest): Promise<boolean> => {
      setLoading(true);
      setError(null);

      try {
        // Use raw fetch for blob download since apiClient returns JSON
        const response = await fetch("/api/literature-search/export", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Change-Reason": "Export search results",
          },
          credentials: "include",
          body: JSON.stringify(request),
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Export failed (${response.status}): ${errorText}`);
        }

        const blob = await response.blob();

        // Determine file extension from format
        const extension = request.format === "pdf" ? "pdf" : "csv";
        const mimeType = request.format === "pdf" ? "application/pdf" : "text/csv";

        // Create download link
        const url = URL.createObjectURL(new Blob([blob], { type: mimeType }));
        const link = document.createElement("a");
        link.href = url;
        link.download = `literature-search-export.${extension}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        toast.success(`Export downloaded as ${extension.toUpperCase()}.`);
        return true;
      } catch (err: unknown) {
        const message =
          err instanceof Error
            ? err.message
            : "An unexpected error occurred during export.";
        setError(message);
        toast.error(message);
        return false;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { loading, error, exportResults };
}
