/**
 * Traceability Store (Zustand)
 *
 * Centralized state management for AI-Powered Traceability & Gap Discovery:
 * matrices, links, orphan requirements/test cases, coverage metrics,
 * alerts, and job tracking.
 *
 * Polling: refreshes active job status every 5 seconds when a job is processing.
 * Timeout: stops polling after 10 minutes and displays an error.
 *
 * Requirements: 8.6, 8.7, 8.9, 8.12
 */

import { create } from "zustand";
import { apiClient, ApiError } from "../lib/apiClient";
import type {
  TraceabilityMatrix,
  TraceabilityLink,
  OrphanRequirement,
  OrphanTestCase,
  CoverageSummary,
  CoverageSnapshot,
  TraceabilityAlert,
  JobStatus,
  DocumentCoverage,
  MatrixFilters,
  LinkFilters,
  OrphanFilters,
  AlertFilters,
  HistoryFilters,
  GenerateMatrixRequest,
  ResolveAlertRequest,
  TraceabilityMatrixListResponse,
  TraceabilityLinkListResponse,
  OrphanRequirementListResponse,
  OrphanTestCaseListResponse,
  CoverageHistoryResponse,
  AlertListResponse,
} from "../types/traceability";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5_000;
const POLL_TIMEOUT_MS = 10 * 60 * 1_000; // 10 minutes
const TERMINAL_STATUSES = ["completed", "partial_success", "failed"];

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface TraceabilityState {
  matrices: TraceabilityMatrix[];
  currentMatrix: TraceabilityMatrix | null;
  links: TraceabilityLink[];
  orphanRequirements: OrphanRequirement[];
  orphanTestCases: OrphanTestCase[];
  coverageSummary: CoverageSummary | null;
  coverageHistory: CoverageSnapshot[];
  alerts: TraceabilityAlert[];
  activeJob: JobStatus | null;
  isLoading: boolean;
  error: string | null;

  // Polling internals
  pollingIntervalId: ReturnType<typeof setInterval> | null;
  pollingStartTime: number | null;

  // Actions
  fetchMatrices: (params?: MatrixFilters) => Promise<void>;
  fetchMatrix: (matrixId: string) => Promise<void>;
  fetchLinks: (matrixId: string, params?: LinkFilters) => Promise<void>;
  fetchOrphanRequirements: (matrixId: string, params?: OrphanFilters) => Promise<void>;
  fetchOrphanTestCases: (matrixId: string, params?: OrphanFilters) => Promise<void>;
  generateMatrix: (request: GenerateMatrixRequest, reason: string) => Promise<string>;
  deleteMatrix: (matrixId: string, reason: string) => Promise<void>;
  fetchCoverageSummary: () => Promise<void>;
  fetchCoverageHistory: (params?: HistoryFilters) => Promise<void>;
  fetchAlerts: (params?: AlertFilters) => Promise<void>;
  resolveAlert: (alertId: string, resolution: ResolveAlertRequest, reason: string) => Promise<void>;
  pollJobStatus: (jobId: string) => Promise<void>;
  fetchDocumentCoverage: (documentUuid: string) => Promise<DocumentCoverage>;
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

function buildQueryString(params: Record<string, unknown> | object): string {
  const queryParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      queryParams.set(key, String(value));
    }
  }
  const qs = queryParams.toString();
  return qs ? `?${qs}` : "";
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useTraceabilityStore = create<TraceabilityState>((set, get) => ({
  matrices: [],
  currentMatrix: null,
  links: [],
  orphanRequirements: [],
  orphanTestCases: [],
  coverageSummary: null,
  coverageHistory: [],
  alerts: [],
  activeJob: null,
  isLoading: false,
  error: null,
  pollingIntervalId: null,
  pollingStartTime: null,

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  fetchMatrices: async (params?: MatrixFilters) => {
    set({ isLoading: true, error: null });

    try {
      const url = `/api/traceability/matrices${buildQueryString(params || {})}`;
      const response = await apiClient.get<TraceabilityMatrixListResponse>(url);
      set({ matrices: response.matrices, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchMatrix: async (matrixId: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiClient.get<TraceabilityMatrix>(
        `/api/traceability/matrices/${matrixId}`,
      );
      set({ currentMatrix: response, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchLinks: async (matrixId: string, params?: LinkFilters) => {
    set({ isLoading: true, error: null });

    try {
      const url = `/api/traceability/matrices/${matrixId}/links${buildQueryString(params || {})}`;
      const response = await apiClient.get<TraceabilityLinkListResponse>(url);
      set({ links: response.links, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchOrphanRequirements: async (matrixId: string, params?: OrphanFilters) => {
    set({ isLoading: true, error: null });

    try {
      const url = `/api/traceability/matrices/${matrixId}/orphan-requirements${buildQueryString(params || {})}`;
      const response = await apiClient.get<OrphanRequirementListResponse>(url);
      set({ orphanRequirements: response.orphan_requirements, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchOrphanTestCases: async (matrixId: string, params?: OrphanFilters) => {
    set({ isLoading: true, error: null });

    try {
      const url = `/api/traceability/matrices/${matrixId}/orphan-test-cases${buildQueryString(params || {})}`;
      const response = await apiClient.get<OrphanTestCaseListResponse>(url);
      set({ orphanTestCases: response.orphan_test_cases, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  generateMatrix: async (request: GenerateMatrixRequest, reason: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiClient.post<{ job_id: string }>(
        "/api/traceability/matrices/generate",
        request,
        { changeReason: reason },
      );
      set({ isLoading: false });

      // Start polling the new job
      get().pollJobStatus(response.job_id);

      return response.job_id;
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // Concurrent job — extract existing job_id from response and poll it
        let existingJobId = "";
        try {
          const parsed = JSON.parse(error.body);
          existingJobId = parsed.job_id || "";
        } catch {
          // If we can't parse, just set the error
        }
        set({
          error: "A matrix generation job is already in progress for these documents.",
          isLoading: false,
        });

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

  deleteMatrix: async (matrixId: string, reason: string) => {
    set({ isLoading: true, error: null });

    try {
      await apiClient.delete(`/api/traceability/matrices/${matrixId}`, {
        changeReason: reason,
      });
      // Remove from local list
      const { matrices } = get();
      set({
        matrices: matrices.filter((m) => m.matrix_id !== matrixId),
        isLoading: false,
      });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchCoverageSummary: async () => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiClient.get<CoverageSummary>(
        "/api/traceability/coverage/summary",
      );
      set({ coverageSummary: response, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchCoverageHistory: async (params?: HistoryFilters) => {
    set({ isLoading: true, error: null });

    try {
      const url = `/api/traceability/coverage/history${buildQueryString(params || {})}`;
      const response = await apiClient.get<CoverageHistoryResponse>(url);
      set({ coverageHistory: response.snapshots, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  fetchAlerts: async (params?: AlertFilters) => {
    set({ isLoading: true, error: null });

    try {
      const url = `/api/traceability/alerts${buildQueryString(params || {})}`;
      const response = await apiClient.get<AlertListResponse>(url);
      set({ alerts: response.alerts, isLoading: false });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  resolveAlert: async (alertId: string, resolution: ResolveAlertRequest, reason: string) => {
    set({ isLoading: true, error: null });

    try {
      await apiClient.post(
        `/api/traceability/alerts/${alertId}/resolve`,
        resolution,
        { changeReason: reason },
      );
      // Remove resolved alert from local list
      const { alerts } = get();
      set({
        alerts: alerts.filter((a) => a.alert_id !== alertId),
        isLoading: false,
      });
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
    }
  },

  pollJobStatus: async (jobId: string) => {
    // Stop any existing polling
    get().stopPolling();

    // Fetch initial status
    try {
      const status = await apiClient.get<JobStatus>(
        `/api/traceability/jobs/${jobId}/status`,
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

    // Start polling interval with timeout tracking
    const startTime = Date.now();
    set({ pollingStartTime: startTime });

    const intervalId = setInterval(async () => {
      // Check for polling timeout (10 minutes)
      const elapsed = Date.now() - startTime;
      if (elapsed >= POLL_TIMEOUT_MS) {
        get().stopPolling();
        set({
          error: "Matrix generation timed out after 10 minutes. You can retry the operation.",
        });
        return;
      }

      try {
        const status = await apiClient.get<JobStatus>(
          `/api/traceability/jobs/${jobId}/status`,
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

  fetchDocumentCoverage: async (documentUuid: string) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiClient.get<DocumentCoverage>(
        `/api/traceability/documents/${documentUuid}/coverage`,
      );
      set({ isLoading: false });
      return response;
    } catch (error) {
      set({ error: extractErrorMessage(error), isLoading: false });
      throw error;
    }
  },

  stopPolling: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId !== null) {
      clearInterval(pollingIntervalId);
      set({ pollingIntervalId: null, pollingStartTime: null });
    }
  },

  reset: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId !== null) {
      clearInterval(pollingIntervalId);
    }

    set({
      matrices: [],
      currentMatrix: null,
      links: [],
      orphanRequirements: [],
      orphanTestCases: [],
      coverageSummary: null,
      coverageHistory: [],
      alerts: [],
      activeJob: null,
      isLoading: false,
      error: null,
      pollingIntervalId: null,
      pollingStartTime: null,
    });
  },
}));
