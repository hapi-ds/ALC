/**
 * Risk Framework Store (Zustand)
 *
 * Centralized state management for the AI Risk & Compliance Framework:
 * task types, active company risk profile, HITL checkpoints, operation logs,
 * and dashboard statistics.
 *
 * Uses granular loading/error states per resource to allow independent
 * fetching without UI flicker across unrelated sections.
 *
 * Requirements: 7.2, 7.3, 7.4, 7.5, 7.6
 */

import { create } from 'zustand';
import { ApiError } from '../lib/apiClient';
import {
  getTaskTypes,
  getActiveProfile,
  createProfile,
  updateProfile,
  getCheckpoints,
  reviewCheckpoint,
  getOperationLogs,
  getDashboardStats,
} from '../lib/riskFrameworkApi';
import type {
  PaginatedResult,
  AITaskTypeResponse,
  CompanyRiskProfileResponse,
  HITLCheckpointResponse,
  AIOperationLogResponse,
  DashboardStatsResponse,
  CreateProfileRequest,
  UpdateProfileRequest,
  ReviewCheckpointRequest,
  CheckpointFilters,
  PaginationParams,
  OperationLogParams,
} from '../lib/riskFrameworkApi';

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface RiskFrameworkLoadingState {
  taskTypes: boolean;
  profile: boolean;
  checkpoints: boolean;
  operationLogs: boolean;
  dashboardStats: boolean;
}

export interface RiskFrameworkErrorState {
  taskTypes: string | null;
  profile: string | null;
  checkpoints: string | null;
  operationLogs: string | null;
  dashboardStats: string | null;
}

export interface RiskFrameworkState {
  taskTypes: PaginatedResult<AITaskTypeResponse> | null;
  activeProfile: CompanyRiskProfileResponse | null;
  checkpoints: PaginatedResult<HITLCheckpointResponse> | null;
  operationLogs: PaginatedResult<AIOperationLogResponse> | null;
  dashboardStats: DashboardStatsResponse | null;
  loading: RiskFrameworkLoadingState;
  error: RiskFrameworkErrorState;

  // Actions
  fetchTaskTypes: (params?: PaginationParams) => Promise<void>;
  fetchProfile: () => Promise<void>;
  createProfile: (data: CreateProfileRequest, changeReason: string) => Promise<void>;
  updateProfile: (profileId: string, data: UpdateProfileRequest, changeReason: string) => Promise<void>;
  fetchCheckpoints: (params?: CheckpointFilters & PaginationParams) => Promise<void>;
  reviewCheckpoint: (checkpointId: string, data: ReviewCheckpointRequest, changeReason: string) => Promise<void>;
  fetchOperationLogs: (params?: OperationLogParams) => Promise<void>;
  fetchDashboardStats: () => Promise<void>;
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
  return 'An unexpected error occurred';
}

// ---------------------------------------------------------------------------
// Initial State
// ---------------------------------------------------------------------------

const initialLoadingState: RiskFrameworkLoadingState = {
  taskTypes: false,
  profile: false,
  checkpoints: false,
  operationLogs: false,
  dashboardStats: false,
};

const initialErrorState: RiskFrameworkErrorState = {
  taskTypes: null,
  profile: null,
  checkpoints: null,
  operationLogs: null,
  dashboardStats: null,
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useRiskFrameworkStore = create<RiskFrameworkState>((set, get) => ({
  taskTypes: null,
  activeProfile: null,
  checkpoints: null,
  operationLogs: null,
  dashboardStats: null,
  loading: { ...initialLoadingState },
  error: { ...initialErrorState },

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  fetchTaskTypes: async (params?: PaginationParams) => {
    set({ loading: { ...get().loading, taskTypes: true }, error: { ...get().error, taskTypes: null } });

    try {
      const result = await getTaskTypes(params);
      set({ taskTypes: result, loading: { ...get().loading, taskTypes: false } });
    } catch (error) {
      set({
        loading: { ...get().loading, taskTypes: false },
        error: { ...get().error, taskTypes: extractErrorMessage(error) },
      });
    }
  },

  fetchProfile: async () => {
    set({ loading: { ...get().loading, profile: true }, error: { ...get().error, profile: null } });

    try {
      const result = await getActiveProfile();
      set({ activeProfile: result, loading: { ...get().loading, profile: false } });
    } catch (error) {
      // 404 means no active profile — treat as null, not an error
      if (error instanceof ApiError && error.status === 404) {
        set({ activeProfile: null, loading: { ...get().loading, profile: false } });
        return;
      }
      set({
        loading: { ...get().loading, profile: false },
        error: { ...get().error, profile: extractErrorMessage(error) },
      });
    }
  },

  createProfile: async (data: CreateProfileRequest, changeReason: string) => {
    set({ loading: { ...get().loading, profile: true }, error: { ...get().error, profile: null } });

    try {
      const result = await createProfile(data, changeReason);
      set({ activeProfile: result, loading: { ...get().loading, profile: false } });
    } catch (error) {
      set({
        loading: { ...get().loading, profile: false },
        error: { ...get().error, profile: extractErrorMessage(error) },
      });
    }
  },

  updateProfile: async (profileId: string, data: UpdateProfileRequest, changeReason: string) => {
    set({ loading: { ...get().loading, profile: true }, error: { ...get().error, profile: null } });

    try {
      const result = await updateProfile(profileId, data, changeReason);
      set({ activeProfile: result, loading: { ...get().loading, profile: false } });
    } catch (error) {
      set({
        loading: { ...get().loading, profile: false },
        error: { ...get().error, profile: extractErrorMessage(error) },
      });
    }
  },

  fetchCheckpoints: async (params?: CheckpointFilters & PaginationParams) => {
    set({ loading: { ...get().loading, checkpoints: true }, error: { ...get().error, checkpoints: null } });

    try {
      const result = await getCheckpoints(params);
      set({ checkpoints: result, loading: { ...get().loading, checkpoints: false } });
    } catch (error) {
      set({
        loading: { ...get().loading, checkpoints: false },
        error: { ...get().error, checkpoints: extractErrorMessage(error) },
      });
    }
  },

  reviewCheckpoint: async (checkpointId: string, data: ReviewCheckpointRequest, changeReason: string) => {
    set({ loading: { ...get().loading, checkpoints: true }, error: { ...get().error, checkpoints: null } });

    try {
      await reviewCheckpoint(checkpointId, data, changeReason);
      // Refresh checkpoints list after successful review
      const { checkpoints } = get();
      const currentParams: PaginationParams = {
        limit: checkpoints?.limit ?? 20,
        offset: checkpoints?.offset ?? 0,
      };
      set({ loading: { ...get().loading, checkpoints: false } });
      await get().fetchCheckpoints(currentParams);
    } catch (error) {
      set({
        loading: { ...get().loading, checkpoints: false },
        error: { ...get().error, checkpoints: extractErrorMessage(error) },
      });
    }
  },

  fetchOperationLogs: async (params?: OperationLogParams) => {
    set({ loading: { ...get().loading, operationLogs: true }, error: { ...get().error, operationLogs: null } });

    try {
      const result = await getOperationLogs(params);
      set({ operationLogs: result, loading: { ...get().loading, operationLogs: false } });
    } catch (error) {
      set({
        loading: { ...get().loading, operationLogs: false },
        error: { ...get().error, operationLogs: extractErrorMessage(error) },
      });
    }
  },

  fetchDashboardStats: async () => {
    set({ loading: { ...get().loading, dashboardStats: true }, error: { ...get().error, dashboardStats: null } });

    try {
      const result = await getDashboardStats();
      set({ dashboardStats: result, loading: { ...get().loading, dashboardStats: false } });
    } catch (error) {
      set({
        loading: { ...get().loading, dashboardStats: false },
        error: { ...get().error, dashboardStats: extractErrorMessage(error) },
      });
    }
  },

  reset: () => {
    set({
      taskTypes: null,
      activeProfile: null,
      checkpoints: null,
      operationLogs: null,
      dashboardStats: null,
      loading: { ...initialLoadingState },
      error: { ...initialErrorState },
    });
  },
}));
