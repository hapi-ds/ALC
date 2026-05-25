/**
 * Impact Analysis Store (Zustand)
 *
 * Centralized state management for AI-Driven Change Impact Analysis:
 * reports, notifications, dependency graph, job tracking, and document status.
 *
 * Polling: refreshes active job status every 5 seconds when a job is processing.
 *
 * Requirements: 10.1, 10.6, 10.7, 10.10
 */

import { create } from "zustand";
import { apiClient, ApiError } from "../lib/apiClient";
import type {
  ImpactReport,
  ImpactNotification,
  DependencyEdge,
  JobStatus,
  DocumentImpactStatus,
  ReportFilters,
} from "../types/impactAnalysis";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5_000;
const TERMINAL_STATUSES = ["completed", "partial_success", "failed"];

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface ImpactAnalysisState {
  reports: ImpactReport[];
  notifications: ImpactNotification[];
  dependencyGraph: DependencyEdge[];
  activeJob: JobStatus | null;
  documentStatus: Record<string, DocumentImpactStatus>;
  isLoading: boolean;
  error: string | null;

  // Polling
  pollingIntervalId: ReturnType<typeof setInterval> | null;

  // Actions
  fetchReports: (params?: ReportFilters) => Promise<void>;
  fetchNotifications: () => Promise<void>;
  fetchDependencyGraph: (documentUuid?: string) => Promise<void>;
  triggerAnalysis: (documentId: number, reason: string) => Promise<string>;
  acknowledgeNotification: (id: number, reason: string) => Promise<void>;
  pollJobStatus: (jobId: string) => Promise<void>;
  fetchDocumentStatus: (documentUuid: string) => Promise<void>;
  stopPolling: () => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.body);
      return parsed.detail || parsed.message || error.message;
    } catch {
      return error.body || error.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred";
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useImpactAnalysisStore = create<ImpactAnalysisState>((set, get) => ({
  reports: [],
  notifications: [],
  dependencyGraph: [],
  activeJob: null,
  documentStatus: {},
  isLoading: false,
  error: null,
  pollingIntervalId: null,

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  fetchReports: async (params?: ReportFilters) => {
    set({ isLoading: true, error: null });

    try {
      const queryParams = new URLSearchParams();
      if (params?.triggering_document_uuid) {
        queryParams.set("triggering_document_uuid", params.triggering_document_uuid);
      }
      if (params?.severity) {
        queryParams.set("severity", params.severity);
      }
      if (params?.start_date) {
        queryParams.set("start_date", params.start_date);
      }
      if (params?.end_date) {
        queryParams.set("end_date", params.end_date);
      }
      if (params?.status) {
        queryParams.set("status", params.status);
      }

      const queryString = queryParams.toString();
      const url = `/api/impact-analysis/reports${queryString ? `?${queryString}` : ""}`;

      const response = await apiClient.get<{ reports: ImpactReport[]; total_count: number }>(url);
      set({ reports: response.reports, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchNotifications: async () => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiClient.get<{
        notifications: ImpactNotification[];
        total_count: number;
      }>("/api/impact-analysis/notifications");
      set({ notifications: response.notifications, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchDependencyGraph: async (documentUuid?: string) => {
    set({ isLoading: true, error: null });

    try {
      if (documentUuid) {
        const response = await apiClient.get<{
          document_uuid: string;
          upstream: Record<string, DependencyEdge[]>;
          downstream: Record<string, DependencyEdge[]>;
        }>(`/api/impact-analysis/dependency-graph/${documentUuid}`);

        // Flatten upstream and downstream edges into a single array
        const edges: DependencyEdge[] = [];
        for (const edgeList of Object.values(response.upstream)) {
          edges.push(...edgeList);
        }
        for (const edgeList of Object.values(response.downstream)) {
          edges.push(...edgeList);
        }
        set({ dependencyGraph: edges, isLoading: false });
      } else {
        const response = await apiClient.get<{
          edges: DependencyEdge[];
          total_count: number;
        }>("/api/impact-analysis/dependency-graph");
        set({ dependencyGraph: response.edges, isLoading: false });
      }
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  triggerAnalysis: async (documentId: number, reason: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiClient.post<{ job_id: string }>(
        "/api/impact-analysis/trigger",
        { document_id: documentId },
        { changeReason: reason },
      );
      set({ isLoading: false });

      // Start polling the new job
      get().pollJobStatus(response.job_id);

      return response.job_id;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // Concurrent job — extract existing job_id from response
        let existingJobId = "";
        try {
          const parsed = JSON.parse(error.body);
          existingJobId = parsed.job_id || "";
        } catch {
          // If we can't parse, just set the error
        }
        set({ error: "An impact analysis job is already in progress.", isLoading: false });

        // Poll the existing job if we have its ID
        if (existingJobId) {
          get().pollJobStatus(existingJobId);
        }

        return existingJobId;
      }
      set({ error: extractErrorMessage(error), isLoading: false });
      throw error;
    }
  },

  acknowledgeNotification: async (id: number, reason: string) => {
    try {
      await apiClient.post(
        `/api/impact-analysis/notifications/${id}/acknowledge`,
        {},
        { changeReason: reason },
      );

      // Remove from unacknowledged list
      const { notifications } = get();
      set({
        notifications: notifications.filter((n) => n.id !== id),
      });
    } catch (error) {
      set({ error: extractErrorMessage(error) });
    }
  },

  pollJobStatus: async (jobId: string) => {
    // Stop any existing polling
    get().stopPolling();

    // Fetch initial status
    try {
      const status = await apiClient.get<JobStatus>(
        `/api/impact-analysis/jobs/${jobId}/status`,
      );
      set({ activeJob: status });

      // If already terminal, don't start polling
      if (TERMINAL_STATUSES.includes(status.status)) {
        return;
      }
    } catch (error) {
      set({ error: extractErrorMessage(error) });
      return;
    }

    // Start polling interval
    const intervalId = setInterval(async () => {
      try {
        const status = await apiClient.get<JobStatus>(
          `/api/impact-analysis/jobs/${jobId}/status`,
        );
        set({ activeJob: status });

        // Stop polling on terminal status
        if (TERMINAL_STATUSES.includes(status.status)) {
          get().stopPolling();
        }
      } catch {
        // Polling errors are non-blocking
      }
    }, POLL_INTERVAL_MS);

    set({ pollingIntervalId: intervalId });
  },

  fetchDocumentStatus: async (documentUuid: string) => {
    try {
      const status = await apiClient.get<DocumentImpactStatus>(
        `/api/impact-analysis/documents/${documentUuid}/status`,
      );
      const { documentStatus } = get();
      set({
        documentStatus: { ...documentStatus, [documentUuid]: status },
      });
    } catch (error) {
      set({ error: extractErrorMessage(error) });
    }
  },

  stopPolling: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId !== null) {
      clearInterval(pollingIntervalId);
      set({ pollingIntervalId: null });
    }
  },

  reset: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId !== null) {
      clearInterval(pollingIntervalId);
    }

    set({
      reports: [],
      notifications: [],
      dependencyGraph: [],
      activeJob: null,
      documentStatus: {},
      isLoading: false,
      error: null,
      pollingIntervalId: null,
    });
  },
}));
