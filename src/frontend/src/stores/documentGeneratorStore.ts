/**
 * Document Generator Store (Zustand)
 *
 * Centralized state management for the AI Document Generator (Template-Based)
 * feature. Manages template registration, generation jobs, generated document
 * review, provenance, cross-references, and async job polling.
 *
 * API endpoints (from backend routers):
 *   POST /api/documents/templates/register          - register template
 *   GET  /api/documents/templates                   - list templates
 *   GET  /api/documents/templates/{template_id}     - get template with analysis
 *   POST /api/documents/generate-from-template      - start generation
 *   GET  /api/documents/generate-from-template/{job_id}/status - poll job status
 *   POST /api/documents/{document_id}/review        - approve/reject
 *   GET  /api/documents/generated                   - list generated documents
 *   GET  /api/documents/{document_id}/provenance    - get provenance
 *   GET  /api/documents/{document_id}/cross-references - get cross-references
 *
 * Requirements: 7.3
 */

import { create } from "zustand";
import { apiClient } from "../lib/apiClient";
import type {
  DocumentTemplate,
  TemplateAnalysis,
  GenerationJob,
  GeneratedDocument,
  ProvenanceData,
  CrossReference,
  TemplateRegisterRequest,
  GenerateFromTemplateRequest,
  DocumentReviewRequest,
  GeneratedDocFilters,
} from "../types/documentGenerator";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5_000;

// ---------------------------------------------------------------------------
// Response types (API list wrappers)
// ---------------------------------------------------------------------------

interface TemplateListResponse {
  items: DocumentTemplate[];
  total: number;
}

interface GeneratedDocumentListResponse {
  items: GeneratedDocument[];
  total: number;
}

interface CrossReferenceListResponse {
  items: CrossReference[];
  total: number;
}

interface JobAcceptedResponse {
  job_id: string;
  status: string;
}

interface DocumentReviewResponse {
  document_id: number;
  current_status: string;
  content_status: string;
}

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface DocumentGeneratorState {
  // Template state
  templates: DocumentTemplate[];
  selectedTemplate: DocumentTemplate | null;
  templateAnalysis: TemplateAnalysis | null;
  templatesTotal: number;

  // Generation jobs
  activeJobs: GenerationJob[];

  // Generated documents
  generatedDocuments: GeneratedDocument[];
  generatedDocumentsTotal: number;

  // Provenance & cross-references
  currentProvenance: ProvenanceData | null;
  crossReferences: CrossReference[];

  // UI state
  isRegistering: boolean;
  isGenerating: boolean;
  isLoading: boolean;
  error: string | null;

  // Polling
  pollingIntervalId: ReturnType<typeof setInterval> | null;

  // Actions
  fetchTemplates: (documentTypeTarget?: string, limit?: number, offset?: number) => Promise<void>;
  registerTemplate: (request: TemplateRegisterRequest, changeReason: string) => Promise<string | null>;
  getTemplateAnalysis: (templateId: number) => Promise<void>;
  startGeneration: (request: GenerateFromTemplateRequest, changeReason: string) => Promise<string | null>;
  pollJobStatus: (jobId: string) => Promise<GenerationJob | null>;
  reviewDocument: (documentId: number, request: DocumentReviewRequest, changeReason: string) => Promise<DocumentReviewResponse | null>;
  fetchGeneratedDocuments: (filters?: GeneratedDocFilters) => Promise<void>;
  fetchProvenance: (documentId: number) => Promise<void>;
  fetchCrossReferences: (documentId: number) => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred";
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useDocumentGeneratorStore = create<DocumentGeneratorState>(
  (set, get) => ({
    // Template state
    templates: [],
    selectedTemplate: null,
    templateAnalysis: null,
    templatesTotal: 0,

    // Generation jobs
    activeJobs: [],

    // Generated documents
    generatedDocuments: [],
    generatedDocumentsTotal: 0,

    // Provenance & cross-references
    currentProvenance: null,
    crossReferences: [],

    // UI state
    isRegistering: false,
    isGenerating: false,
    isLoading: false,
    error: null,

    // Polling
    pollingIntervalId: null,

    // -----------------------------------------------------------------------
    // Template Actions
    // -----------------------------------------------------------------------

    fetchTemplates: async (
      documentTypeTarget?: string,
      limit: number = 20,
      offset: number = 0,
    ) => {
      set({ isLoading: true, error: null });

      try {
        const params = new URLSearchParams();
        params.set("limit", String(limit));
        params.set("offset", String(offset));
        if (documentTypeTarget) {
          params.set("document_type_target", documentTypeTarget);
        }

        const response = await apiClient.get<TemplateListResponse>(
          `/api/documents/templates?${params.toString()}`,
        );

        set({
          templates: response.items,
          templatesTotal: response.total,
          isLoading: false,
        });
      } catch (error) {
        set({ error: extractErrorMessage(error), isLoading: false });
      }
    },

    registerTemplate: async (
      request: TemplateRegisterRequest,
      changeReason: string,
    ): Promise<string | null> => {
      set({ isRegistering: true, error: null });

      try {
        const response = await apiClient.post<JobAcceptedResponse>(
          "/api/documents/templates/register",
          request,
          { changeReason },
        );

        set({ isRegistering: false });
        return response.job_id;
      } catch (error) {
        set({ error: extractErrorMessage(error), isRegistering: false });
        return null;
      }
    },

    getTemplateAnalysis: async (templateId: number) => {
      set({ isLoading: true, error: null });

      try {
        const response = await apiClient.get<DocumentTemplate>(
          `/api/documents/templates/${templateId}`,
        );

        set({
          selectedTemplate: response,
          templateAnalysis: response.template_analysis,
          isLoading: false,
        });
      } catch (error) {
        set({ error: extractErrorMessage(error), isLoading: false });
      }
    },

    // -----------------------------------------------------------------------
    // Generation Actions
    // -----------------------------------------------------------------------

    startGeneration: async (
      request: GenerateFromTemplateRequest,
      changeReason: string,
    ): Promise<string | null> => {
      set({ isGenerating: true, error: null });

      try {
        const response = await apiClient.post<JobAcceptedResponse>(
          "/api/documents/generate-from-template",
          request,
          { changeReason },
        );

        // Add the new job to active jobs
        const newJob: GenerationJob = {
          job_id: response.job_id,
          status: "pending",
          progress_percent: 0,
          current_section: null,
          sections_completed: 0,
          sections_total: 0,
          estimated_time_remaining_seconds: null,
          error_message: null,
          result_document_id: null,
          result_document_uuid: null,
          result_storage_key: null,
          file_size_bytes: null,
          generation_duration_ms: null,
        };

        set((state) => ({
          activeJobs: [...state.activeJobs, newJob],
          isGenerating: false,
        }));

        // Start polling if not already active
        if (!get().pollingIntervalId) {
          get().startPolling();
        }

        return response.job_id;
      } catch (error) {
        set({ error: extractErrorMessage(error), isGenerating: false });
        return null;
      }
    },

    pollJobStatus: async (jobId: string): Promise<GenerationJob | null> => {
      try {
        const response = await apiClient.get<GenerationJob>(
          `/api/documents/generate-from-template/${jobId}/status`,
        );

        // Update the job in activeJobs
        set((state) => ({
          activeJobs: state.activeJobs.map((job) =>
            job.job_id === jobId ? response : job,
          ),
        }));

        return response;
      } catch (error) {
        set({ error: extractErrorMessage(error) });
        return null;
      }
    },

    // -----------------------------------------------------------------------
    // Review Actions
    // -----------------------------------------------------------------------

    reviewDocument: async (
      documentId: number,
      request: DocumentReviewRequest,
      changeReason: string,
    ): Promise<DocumentReviewResponse | null> => {
      set({ isLoading: true, error: null });

      try {
        const response = await apiClient.post<DocumentReviewResponse>(
          `/api/documents/${documentId}/review`,
          request,
          { changeReason },
        );

        set({ isLoading: false });
        return response;
      } catch (error) {
        set({ error: extractErrorMessage(error), isLoading: false });
        return null;
      }
    },

    fetchGeneratedDocuments: async (filters?: GeneratedDocFilters) => {
      set({ isLoading: true, error: null });

      try {
        const params = new URLSearchParams();
        if (filters?.content_status) {
          params.set("content_status", filters.content_status);
        }
        if (filters?.document_type) {
          params.set("document_type", filters.document_type);
        }
        if (filters?.date_from) {
          params.set("start_date", filters.date_from);
        }
        if (filters?.date_to) {
          params.set("end_date", filters.date_to);
        }
        const limit = filters?.page_size ?? 20;
        const offset = filters?.page ? (filters.page - 1) * limit : 0;
        params.set("limit", String(limit));
        params.set("offset", String(offset));

        const response = await apiClient.get<GeneratedDocumentListResponse>(
          `/api/documents/generated?${params.toString()}`,
        );

        set({
          generatedDocuments: response.items,
          generatedDocumentsTotal: response.total,
          isLoading: false,
        });
      } catch (error) {
        set({ error: extractErrorMessage(error), isLoading: false });
      }
    },

    // -----------------------------------------------------------------------
    // Provenance & Cross-Reference Actions
    // -----------------------------------------------------------------------

    fetchProvenance: async (documentId: number) => {
      set({ isLoading: true, error: null, currentProvenance: null });

      try {
        const response = await apiClient.get<ProvenanceData>(
          `/api/documents/${documentId}/provenance`,
        );

        set({ currentProvenance: response, isLoading: false });
      } catch (error) {
        set({ error: extractErrorMessage(error), isLoading: false });
      }
    },

    fetchCrossReferences: async (documentId: number) => {
      set({ isLoading: true, error: null, crossReferences: [] });

      try {
        const response = await apiClient.get<CrossReferenceListResponse>(
          `/api/documents/${documentId}/cross-references`,
        );

        set({ crossReferences: response.items, isLoading: false });
      } catch (error) {
        set({ error: extractErrorMessage(error), isLoading: false });
      }
    },

    // -----------------------------------------------------------------------
    // Polling Actions
    // -----------------------------------------------------------------------

    startPolling: () => {
      // Avoid duplicate intervals
      if (get().pollingIntervalId) return;

      const intervalId = setInterval(async () => {
        const { activeJobs } = get();

        // Only poll jobs that are still in progress
        const pendingJobs = activeJobs.filter(
          (job) => job.status === "pending" || job.status === "processing",
        );

        if (pendingJobs.length === 0) {
          get().stopPolling();
          return;
        }

        // Poll each active job
        for (const job of pendingJobs) {
          await get().pollJobStatus(job.job_id);
        }

        // Check if all jobs are now complete after polling
        const updatedJobs = get().activeJobs;
        const stillPending = updatedJobs.some(
          (job) => job.status === "pending" || job.status === "processing",
        );

        if (!stillPending) {
          get().stopPolling();
        }
      }, POLL_INTERVAL_MS);

      set({ pollingIntervalId: intervalId });
    },

    stopPolling: () => {
      const { pollingIntervalId } = get();
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
        set({ pollingIntervalId: null });
      }
    },

    // -----------------------------------------------------------------------
    // Reset
    // -----------------------------------------------------------------------

    reset: () => {
      const { pollingIntervalId } = get();
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
      }

      set({
        templates: [],
        selectedTemplate: null,
        templateAnalysis: null,
        templatesTotal: 0,
        activeJobs: [],
        generatedDocuments: [],
        generatedDocumentsTotal: 0,
        currentProvenance: null,
        crossReferences: [],
        isRegistering: false,
        isGenerating: false,
        isLoading: false,
        error: null,
        pollingIntervalId: null,
      });
    },
  }),
);
