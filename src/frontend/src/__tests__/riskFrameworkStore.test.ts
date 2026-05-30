import { describe, it, expect, beforeEach, vi } from "vitest";

/**
 * Unit tests for riskFrameworkStore (Zustand).
 *
 * Covers:
 * - Initial state has null values and loading=false
 * - fetchTaskTypes sets loading, then updates taskTypes state
 * - fetchProfile handles 404 as null (not error)
 * - createProfile updates activeProfile on success
 * - fetchDashboardStats updates dashboardStats state
 * - Error handling sets error state correctly
 * - reset() clears all state
 *
 * Validates: Requirements 7.1–7.8
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string = "/api/risk-framework") {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

vi.mock("../lib/tokenStorage", () => ({
  getAccessToken: vi.fn(() => "mock-token"),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(() => null),
}));

// Mock the riskFrameworkApi module functions
const mockGetTaskTypes = vi.fn();
const mockGetActiveProfile = vi.fn();
const mockCreateProfile = vi.fn();
const mockUpdateProfile = vi.fn();
const mockGetCheckpoints = vi.fn();
const mockReviewCheckpoint = vi.fn();
const mockGetOperationLogs = vi.fn();
const mockGetDashboardStats = vi.fn();

vi.mock("../lib/riskFrameworkApi", () => ({
  getTaskTypes: (...args: unknown[]) => mockGetTaskTypes(...args),
  getActiveProfile: (...args: unknown[]) => mockGetActiveProfile(...args),
  createProfile: (...args: unknown[]) => mockCreateProfile(...args),
  updateProfile: (...args: unknown[]) => mockUpdateProfile(...args),
  getCheckpoints: (...args: unknown[]) => mockGetCheckpoints(...args),
  reviewCheckpoint: (...args: unknown[]) => mockReviewCheckpoint(...args),
  getOperationLogs: (...args: unknown[]) => mockGetOperationLogs(...args),
  getDashboardStats: (...args: unknown[]) => mockGetDashboardStats(...args),
}));

import { useRiskFrameworkStore } from "../stores/riskFrameworkStore";
import { ApiError } from "../lib/apiClient";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeTaskTypesResult() {
  return {
    items: [
      {
        id: "uuid-1",
        task_type_id: "document_generation",
        display_name: "Document Generation",
        module_reference: "document_generator",
        default_risk_tier: "high" as const,
        company_tier: null,
        is_active: true,
        is_system_defined: true,
      },
      {
        id: "uuid-2",
        task_type_id: "rag_knowledge_query",
        display_name: "RAG Knowledge Query",
        module_reference: "knowledge_search",
        default_risk_tier: "low" as const,
        company_tier: null,
        is_active: true,
        is_system_defined: true,
      },
    ],
    total: 2,
    limit: 20,
    offset: 0,
  };
}

function makeProfile() {
  return {
    id: "profile-uuid-1",
    company_id: 1,
    profile_name: "GMP Compliance Profile",
    description: "Profile for GMP-regulated operations",
    regulatory_frameworks: ["FDA 21 CFR Part 11", "EU GMP Annex 11"],
    is_active: true,
    overrides: [],
    created_by: 1,
    created_at: "2024-06-01T10:00:00Z",
    updated_at: null,
  };
}

function makeDashboardStats() {
  return {
    operations_by_tier: { high: 5, medium: 12, low: 30 },
    pending_checkpoints: 3,
    expired_checkpoints: 1,
    blocked_operations: 2,
    active_profile_name: "GMP Compliance Profile",
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("riskFrameworkStore", () => {
  beforeEach(() => {
    useRiskFrameworkStore.getState().reset();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Initial state has null values and loading=false
  // -------------------------------------------------------------------------

  describe("initial state", () => {
    it("has null values and loading=false", () => {
      const state = useRiskFrameworkStore.getState();

      expect(state.taskTypes).toBeNull();
      expect(state.activeProfile).toBeNull();
      expect(state.checkpoints).toBeNull();
      expect(state.operationLogs).toBeNull();
      expect(state.dashboardStats).toBeNull();

      expect(state.loading.taskTypes).toBe(false);
      expect(state.loading.profile).toBe(false);
      expect(state.loading.checkpoints).toBe(false);
      expect(state.loading.operationLogs).toBe(false);
      expect(state.loading.dashboardStats).toBe(false);

      expect(state.error.taskTypes).toBeNull();
      expect(state.error.profile).toBeNull();
      expect(state.error.checkpoints).toBeNull();
      expect(state.error.operationLogs).toBeNull();
      expect(state.error.dashboardStats).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // 2. fetchTaskTypes sets loading, then updates taskTypes state
  // -------------------------------------------------------------------------

  describe("fetchTaskTypes()", () => {
    it("sets loading to true during request", async () => {
      mockGetTaskTypes.mockImplementation(() => new Promise(() => {}));
      useRiskFrameworkStore.getState().fetchTaskTypes();

      // Check loading was set (may already be resolved in microtask)
      const state = useRiskFrameworkStore.getState();
      expect(state.loading.taskTypes).toBe(true);
    });

    it("updates taskTypes state on success", async () => {
      const result = makeTaskTypesResult();
      mockGetTaskTypes.mockResolvedValue(result);

      await useRiskFrameworkStore.getState().fetchTaskTypes();

      const state = useRiskFrameworkStore.getState();
      expect(state.taskTypes).toEqual(result);
      expect(state.loading.taskTypes).toBe(false);
      expect(state.error.taskTypes).toBeNull();
    });

    it("passes pagination params to API", async () => {
      mockGetTaskTypes.mockResolvedValue(makeTaskTypesResult());

      await useRiskFrameworkStore.getState().fetchTaskTypes({ limit: 10, offset: 20 });

      expect(mockGetTaskTypes).toHaveBeenCalledWith({ limit: 10, offset: 20 });
    });
  });

  // -------------------------------------------------------------------------
  // 3. fetchProfile handles 404 as null (not error)
  // -------------------------------------------------------------------------

  describe("fetchProfile()", () => {
    it("sets activeProfile on success", async () => {
      const profile = makeProfile();
      mockGetActiveProfile.mockResolvedValue(profile);

      await useRiskFrameworkStore.getState().fetchProfile();

      const state = useRiskFrameworkStore.getState();
      expect(state.activeProfile).toEqual(profile);
      expect(state.loading.profile).toBe(false);
      expect(state.error.profile).toBeNull();
    });

    it("handles 404 as null (not error)", async () => {
      mockGetActiveProfile.mockRejectedValue(
        new ApiError(404, "Not Found", "/api/risk-framework/profiles"),
      );

      await useRiskFrameworkStore.getState().fetchProfile();

      const state = useRiskFrameworkStore.getState();
      expect(state.activeProfile).toBeNull();
      expect(state.loading.profile).toBe(false);
      expect(state.error.profile).toBeNull();
    });

    it("sets error for non-404 errors", async () => {
      mockGetActiveProfile.mockRejectedValue(
        new ApiError(500, JSON.stringify({ detail: "Internal server error" }), "/api/risk-framework/profiles"),
      );

      await useRiskFrameworkStore.getState().fetchProfile();

      const state = useRiskFrameworkStore.getState();
      expect(state.activeProfile).toBeNull();
      expect(state.loading.profile).toBe(false);
      expect(state.error.profile).not.toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // 4. createProfile updates activeProfile on success
  // -------------------------------------------------------------------------

  describe("createProfile()", () => {
    it("updates activeProfile on success", async () => {
      const profile = makeProfile();
      mockCreateProfile.mockResolvedValue(profile);

      await useRiskFrameworkStore.getState().createProfile(
        {
          profile_name: "GMP Compliance Profile",
          regulatory_frameworks: ["FDA 21 CFR Part 11"],
          overrides: [],
        },
        "Creating new risk profile",
      );

      const state = useRiskFrameworkStore.getState();
      expect(state.activeProfile).toEqual(profile);
      expect(state.loading.profile).toBe(false);
      expect(state.error.profile).toBeNull();
    });

    it("sets error on failure", async () => {
      mockCreateProfile.mockRejectedValue(new Error("Validation failed"));

      await useRiskFrameworkStore.getState().createProfile(
        {
          profile_name: "Bad",
          regulatory_frameworks: [],
          overrides: [],
        },
        "Test",
      );

      const state = useRiskFrameworkStore.getState();
      expect(state.activeProfile).toBeNull();
      expect(state.loading.profile).toBe(false);
      expect(state.error.profile).toBe("Validation failed");
    });
  });

  // -------------------------------------------------------------------------
  // 5. fetchDashboardStats updates dashboardStats state
  // -------------------------------------------------------------------------

  describe("fetchDashboardStats()", () => {
    it("updates dashboardStats state on success", async () => {
      const stats = makeDashboardStats();
      mockGetDashboardStats.mockResolvedValue(stats);

      await useRiskFrameworkStore.getState().fetchDashboardStats();

      const state = useRiskFrameworkStore.getState();
      expect(state.dashboardStats).toEqual(stats);
      expect(state.loading.dashboardStats).toBe(false);
      expect(state.error.dashboardStats).toBeNull();
    });

    it("sets loading to true during request", async () => {
      mockGetDashboardStats.mockImplementation(() => new Promise(() => {}));
      useRiskFrameworkStore.getState().fetchDashboardStats();

      const state = useRiskFrameworkStore.getState();
      expect(state.loading.dashboardStats).toBe(true);
    });
  });

  // -------------------------------------------------------------------------
  // 6. Error handling sets error state correctly
  // -------------------------------------------------------------------------

  describe("error handling", () => {
    it("sets taskTypes error on fetch failure", async () => {
      mockGetTaskTypes.mockRejectedValue(new Error("Network failure"));

      await useRiskFrameworkStore.getState().fetchTaskTypes();

      const state = useRiskFrameworkStore.getState();
      expect(state.error.taskTypes).toBe("Network failure");
      expect(state.loading.taskTypes).toBe(false);
    });

    it("sets dashboardStats error on fetch failure", async () => {
      mockGetDashboardStats.mockRejectedValue(new Error("Service unavailable"));

      await useRiskFrameworkStore.getState().fetchDashboardStats();

      const state = useRiskFrameworkStore.getState();
      expect(state.error.dashboardStats).toBe("Service unavailable");
      expect(state.loading.dashboardStats).toBe(false);
    });

    it("extracts detail from ApiError JSON body", async () => {
      mockGetTaskTypes.mockRejectedValue(
        new ApiError(422, JSON.stringify({ detail: "Invalid pagination params" }), "/api/risk-framework/task-types"),
      );

      await useRiskFrameworkStore.getState().fetchTaskTypes();

      const state = useRiskFrameworkStore.getState();
      expect(state.error.taskTypes).toBe("Invalid pagination params");
    });

    it("uses ApiError body as fallback when not JSON", async () => {
      mockGetTaskTypes.mockRejectedValue(
        new ApiError(500, "Internal Server Error", "/api/risk-framework/task-types"),
      );

      await useRiskFrameworkStore.getState().fetchTaskTypes();

      const state = useRiskFrameworkStore.getState();
      expect(state.error.taskTypes).toBe("Internal Server Error");
    });

    it("clears previous error on new fetch", async () => {
      // First: set an error
      mockGetTaskTypes.mockRejectedValue(new Error("First error"));
      await useRiskFrameworkStore.getState().fetchTaskTypes();
      expect(useRiskFrameworkStore.getState().error.taskTypes).toBe("First error");

      // Second: successful fetch clears error
      mockGetTaskTypes.mockResolvedValue(makeTaskTypesResult());
      await useRiskFrameworkStore.getState().fetchTaskTypes();
      expect(useRiskFrameworkStore.getState().error.taskTypes).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // 7. reset() clears all state
  // -------------------------------------------------------------------------

  describe("reset()", () => {
    it("clears all state to initial values", async () => {
      // Populate state
      mockGetTaskTypes.mockResolvedValue(makeTaskTypesResult());
      mockGetActiveProfile.mockResolvedValue(makeProfile());
      mockGetDashboardStats.mockResolvedValue(makeDashboardStats());

      await useRiskFrameworkStore.getState().fetchTaskTypes();
      await useRiskFrameworkStore.getState().fetchProfile();
      await useRiskFrameworkStore.getState().fetchDashboardStats();

      // Verify state is populated
      let state = useRiskFrameworkStore.getState();
      expect(state.taskTypes).not.toBeNull();
      expect(state.activeProfile).not.toBeNull();
      expect(state.dashboardStats).not.toBeNull();

      // Reset
      useRiskFrameworkStore.getState().reset();

      // Verify all cleared
      state = useRiskFrameworkStore.getState();
      expect(state.taskTypes).toBeNull();
      expect(state.activeProfile).toBeNull();
      expect(state.checkpoints).toBeNull();
      expect(state.operationLogs).toBeNull();
      expect(state.dashboardStats).toBeNull();

      expect(state.loading.taskTypes).toBe(false);
      expect(state.loading.profile).toBe(false);
      expect(state.loading.checkpoints).toBe(false);
      expect(state.loading.operationLogs).toBe(false);
      expect(state.loading.dashboardStats).toBe(false);

      expect(state.error.taskTypes).toBeNull();
      expect(state.error.profile).toBeNull();
      expect(state.error.checkpoints).toBeNull();
      expect(state.error.operationLogs).toBeNull();
      expect(state.error.dashboardStats).toBeNull();
    });
  });
});
