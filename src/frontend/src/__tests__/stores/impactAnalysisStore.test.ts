import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Unit tests and property-based tests for impactAnalysisStore.
 *
 * Tests state transitions, action sequences, error handling, polling logic.
 * Uses fast-check for property-based testing of state invariants.
 *
 * Validates: Requirements 10.7
 */

// Mock apiClient module
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

import { useImpactAnalysisStore } from "@/stores/impactAnalysisStore";
import { apiClient, ApiError } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeReport(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    report_id: "550e8400-e29b-41d4-a716-446655440000",
    triggering_document_uuid: "doc-001",
    triggering_version_id: 2,
    change_delta_summary: {
      sections_added: [],
      sections_modified: [],
      sections_deleted: [],
      significance_levels: { high: 1, medium: 0, low: 0 },
      metadata: {},
    },
    affected_items: [],
    gap_findings: [],
    status: "completed",
    analysis_timestamp: "2024-01-15T10:00:00Z",
    analysis_duration_ms: 5000,
    agent_archetype_used: "Change Impact Analyst",
    model_used: "gemma-4-e4b-it",
    total_token_count: 1200,
    requesting_user_id: 1,
    company_id: 1,
    created_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeNotification(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    report_id: "550e8400-e29b-41d4-a716-446655440000",
    affected_document_uuid: "doc-002",
    notification_type: "change_impact",
    impact_severity: "critical",
    change_summary: "SOP section 4.2 contradicts updated URS requirement",
    target_user_id: 1,
    is_acknowledged: false,
    acknowledged_at: null,
    acknowledged_by: null,
    company_id: 1,
    created_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeJobStatus(overrides: Record<string, unknown> = {}) {
  return {
    job_id: "job-001",
    status: "processing",
    progress_percent: 50,
    current_phase: "assessing_impact",
    items_assessed: 3,
    items_total: 6,
    critical_findings_count: 1,
    major_findings_count: 2,
    minor_findings_count: 0,
    error_message: null,
    ...overrides,
  };
}

function makeDocumentStatus(overrides: Record<string, unknown> = {}) {
  return {
    document_uuid: "doc-001",
    last_analysis_date: "2024-01-15T10:00:00Z",
    last_analysis_report_id: "550e8400-e29b-41d4-a716-446655440000",
    outstanding_critical_count: 0,
    outstanding_major_count: 0,
    is_up_to_date: true,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("impactAnalysisStore", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useImpactAnalysisStore.getState().reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    useImpactAnalysisStore.getState().stopPolling();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Initial state
  // -------------------------------------------------------------------------

  describe("initial state", () => {
    it("has correct defaults", () => {
      const state = useImpactAnalysisStore.getState();
      expect(state.reports).toEqual([]);
      expect(state.notifications).toEqual([]);
      expect(state.dependencyGraph).toEqual([]);
      expect(state.activeJob).toBeNull();
      expect(state.documentStatus).toEqual({});
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.pollingIntervalId).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // fetchReports()
  // -------------------------------------------------------------------------

  describe("fetchReports()", () => {
    it("sets isLoading to true during request", async () => {
      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));
      useImpactAnalysisStore.getState().fetchReports();
      await vi.waitFor(() => {
        expect(useImpactAnalysisStore.getState().isLoading).toBe(true);
      });
    });

    it("populates reports on success", async () => {
      const reports = [makeReport(), makeReport({ id: 2 })];
      mockedApiClient.get.mockResolvedValue({ reports, total_count: 2 });

      await useImpactAnalysisStore.getState().fetchReports();

      const state = useImpactAnalysisStore.getState();
      expect(state.reports).toEqual(reports);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });

    it("handles errors: sets error state, clears isLoading", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network failure"));

      await useImpactAnalysisStore.getState().fetchReports();

      const state = useImpactAnalysisStore.getState();
      expect(state.error).toBe("Network failure");
      expect(state.isLoading).toBe(false);
    });

    it("passes filter params as query string", async () => {
      mockedApiClient.get.mockResolvedValue({ reports: [], total_count: 0 });

      await useImpactAnalysisStore.getState().fetchReports({
        triggering_document_uuid: "doc-001",
        severity: "critical",
        status: "completed",
      });

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("triggering_document_uuid=doc-001"),
      );
      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("severity=critical"),
      );
      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("status=completed"),
      );
    });
  });

  // -------------------------------------------------------------------------
  // fetchNotifications()
  // -------------------------------------------------------------------------

  describe("fetchNotifications()", () => {
    it("populates notifications on success", async () => {
      const notifications = [makeNotification(), makeNotification({ id: 2 })];
      mockedApiClient.get.mockResolvedValue({ notifications, total_count: 2 });

      await useImpactAnalysisStore.getState().fetchNotifications();

      const state = useImpactAnalysisStore.getState();
      expect(state.notifications).toEqual(notifications);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });

    it("handles errors", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Server error"));

      await useImpactAnalysisStore.getState().fetchNotifications();

      const state = useImpactAnalysisStore.getState();
      expect(state.error).toBe("Server error");
      expect(state.isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // triggerAnalysis()
  // -------------------------------------------------------------------------

  describe("triggerAnalysis()", () => {
    it("returns job_id on success", async () => {
      mockedApiClient.post.mockResolvedValue({ job_id: "new-job-123" });
      mockedApiClient.get.mockResolvedValue(
        makeJobStatus({ job_id: "new-job-123", status: "completed" }),
      );

      const jobId = await useImpactAnalysisStore
        .getState()
        .triggerAnalysis(1, "Manual re-analysis");

      expect(jobId).toBe("new-job-123");
      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/impact-analysis/trigger",
        { document_id: 1 },
        { changeReason: "Manual re-analysis" },
      );
    });

    it("handles 409 (concurrent job)", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(409, JSON.stringify({ job_id: "existing-job" }), "/api/impact-analysis/trigger"),
      );
      mockedApiClient.get.mockResolvedValue(
        makeJobStatus({ job_id: "existing-job", status: "completed" }),
      );

      const jobId = await useImpactAnalysisStore
        .getState()
        .triggerAnalysis(1, "Re-analysis");

      const state = useImpactAnalysisStore.getState();
      expect(state.error).toBe("An impact analysis job is already in progress.");
      expect(jobId).toBe("existing-job");
    });

    it("throws on non-409 errors", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(500, "Internal error", "/api/impact-analysis/trigger"),
      );

      await expect(
        useImpactAnalysisStore.getState().triggerAnalysis(1, "Test"),
      ).rejects.toThrow();

      const state = useImpactAnalysisStore.getState();
      expect(state.isLoading).toBe(false);
      expect(state.error).not.toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // acknowledgeNotification()
  // -------------------------------------------------------------------------

  describe("acknowledgeNotification()", () => {
    it("removes notification from unacknowledged list", async () => {
      useImpactAnalysisStore.setState({
        notifications: [
          makeNotification({ id: 1 }),
          makeNotification({ id: 2 }),
          makeNotification({ id: 3 }),
        ],
      });
      mockedApiClient.post.mockResolvedValue({});

      await useImpactAnalysisStore
        .getState()
        .acknowledgeNotification(2, "Reviewed and addressed");

      const state = useImpactAnalysisStore.getState();
      expect(state.notifications).toHaveLength(2);
      expect(state.notifications.map((n) => n.id)).toEqual([1, 3]);
    });

    it("passes changeReason header", async () => {
      useImpactAnalysisStore.setState({
        notifications: [makeNotification({ id: 5 })],
      });
      mockedApiClient.post.mockResolvedValue({});

      await useImpactAnalysisStore
        .getState()
        .acknowledgeNotification(5, "Acknowledged after review");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/impact-analysis/notifications/5/acknowledge",
        {},
        { changeReason: "Acknowledged after review" },
      );
    });

    it("sets error on failure", async () => {
      useImpactAnalysisStore.setState({
        notifications: [makeNotification({ id: 1 })],
      });
      mockedApiClient.post.mockRejectedValue(new Error("Not found"));

      await useImpactAnalysisStore
        .getState()
        .acknowledgeNotification(1, "Test");

      const state = useImpactAnalysisStore.getState();
      expect(state.error).toBe("Not found");
    });
  });

  // -------------------------------------------------------------------------
  // pollJobStatus()
  // -------------------------------------------------------------------------

  describe("pollJobStatus()", () => {
    it("fetches initial status and sets activeJob", async () => {
      const jobStatus = makeJobStatus({ status: "completed" });
      mockedApiClient.get.mockResolvedValue(jobStatus);

      await useImpactAnalysisStore.getState().pollJobStatus("job-001");

      const state = useImpactAnalysisStore.getState();
      expect(state.activeJob).toEqual(jobStatus);
      // Should not start polling since status is terminal
      expect(state.pollingIntervalId).toBeNull();
    });

    it("starts polling when job is processing", async () => {
      const processingJob = makeJobStatus({ status: "processing" });
      mockedApiClient.get.mockResolvedValue(processingJob);

      await useImpactAnalysisStore.getState().pollJobStatus("job-001");

      const state = useImpactAnalysisStore.getState();
      expect(state.activeJob).toEqual(processingJob);
      expect(state.pollingIntervalId).not.toBeNull();
    });

    it("stops polling when job reaches terminal status", async () => {
      // First call: processing
      mockedApiClient.get
        .mockResolvedValueOnce(makeJobStatus({ status: "processing" }))
        // Second call (from interval): completed
        .mockResolvedValueOnce(makeJobStatus({ status: "completed" }));

      await useImpactAnalysisStore.getState().pollJobStatus("job-001");
      expect(useImpactAnalysisStore.getState().pollingIntervalId).not.toBeNull();

      // Advance timer to trigger the interval
      await vi.advanceTimersByTimeAsync(5000);

      const state = useImpactAnalysisStore.getState();
      expect(state.activeJob?.status).toBe("completed");
      expect(state.pollingIntervalId).toBeNull();
    });

    it("sets error when initial fetch fails", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Job not found"));

      await useImpactAnalysisStore.getState().pollJobStatus("bad-job");

      const state = useImpactAnalysisStore.getState();
      expect(state.error).toBe("Job not found");
      expect(state.pollingIntervalId).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // fetchDocumentStatus()
  // -------------------------------------------------------------------------

  describe("fetchDocumentStatus()", () => {
    it("populates documentStatus for the given UUID", async () => {
      const status = makeDocumentStatus();
      mockedApiClient.get.mockResolvedValue(status);

      await useImpactAnalysisStore.getState().fetchDocumentStatus("doc-001");

      const state = useImpactAnalysisStore.getState();
      expect(state.documentStatus["doc-001"]).toEqual(status);
    });

    it("preserves existing document statuses", async () => {
      useImpactAnalysisStore.setState({
        documentStatus: { "doc-existing": makeDocumentStatus({ document_uuid: "doc-existing" }) },
      });
      const newStatus = makeDocumentStatus({ document_uuid: "doc-002" });
      mockedApiClient.get.mockResolvedValue(newStatus);

      await useImpactAnalysisStore.getState().fetchDocumentStatus("doc-002");

      const state = useImpactAnalysisStore.getState();
      expect(state.documentStatus["doc-existing"]).toBeDefined();
      expect(state.documentStatus["doc-002"]).toEqual(newStatus);
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Not found"));

      await useImpactAnalysisStore.getState().fetchDocumentStatus("bad-doc");

      expect(useImpactAnalysisStore.getState().error).toBe("Not found");
    });
  });

  // -------------------------------------------------------------------------
  // reset()
  // -------------------------------------------------------------------------

  describe("reset()", () => {
    it("resets all state to defaults", () => {
      useImpactAnalysisStore.setState({
        reports: [makeReport()],
        notifications: [makeNotification()],
        dependencyGraph: [],
        activeJob: makeJobStatus(),
        documentStatus: { "doc-001": makeDocumentStatus() },
        isLoading: true,
        error: "some error",
      });

      useImpactAnalysisStore.getState().reset();

      const state = useImpactAnalysisStore.getState();
      expect(state.reports).toEqual([]);
      expect(state.notifications).toEqual([]);
      expect(state.dependencyGraph).toEqual([]);
      expect(state.activeJob).toBeNull();
      expect(state.documentStatus).toEqual({});
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.pollingIntervalId).toBeNull();
    });
  });

  // =========================================================================
  // Property-Based Tests (fast-check)
  // =========================================================================

  describe("property: state invariants", () => {
    /**
     * Property: After any fetchReports call (success or failure),
     * isLoading is always false when the promise resolves.
     *
     * **Validates: Requirements 10.7**
     */
    it("isLoading is always false after fetchReports resolves", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.boolean(),
          fc.string({ minLength: 1, maxLength: 100 }),
          async (shouldSucceed, errorMsg) => {
            useImpactAnalysisStore.getState().reset();
            vi.clearAllMocks();

            if (shouldSucceed) {
              mockedApiClient.get.mockResolvedValue({
                reports: [],
                total_count: 0,
              });
            } else {
              mockedApiClient.get.mockRejectedValue(new Error(errorMsg));
            }

            await useImpactAnalysisStore.getState().fetchReports();

            expect(useImpactAnalysisStore.getState().isLoading).toBe(false);
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: After any fetchNotifications call (success or failure),
     * isLoading is always false when the promise resolves.
     *
     * **Validates: Requirements 10.7**
     */
    it("isLoading is always false after fetchNotifications resolves", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.boolean(),
          fc.string({ minLength: 1, maxLength: 100 }),
          async (shouldSucceed, errorMsg) => {
            useImpactAnalysisStore.getState().reset();
            vi.clearAllMocks();

            if (shouldSucceed) {
              mockedApiClient.get.mockResolvedValue({
                notifications: [],
                total_count: 0,
              });
            } else {
              mockedApiClient.get.mockRejectedValue(new Error(errorMsg));
            }

            await useImpactAnalysisStore.getState().fetchNotifications();

            expect(useImpactAnalysisStore.getState().isLoading).toBe(false);
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: On success, error is always null. On failure, error is
     * always a non-empty string.
     *
     * **Validates: Requirements 10.7**
     */
    it("error is null on success, non-empty string on failure", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.boolean(),
          fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.trim().length > 0),
          async (shouldSucceed, errorMsg) => {
            useImpactAnalysisStore.getState().reset();
            vi.clearAllMocks();

            if (shouldSucceed) {
              mockedApiClient.get.mockResolvedValue({
                reports: [],
                total_count: 0,
              });
            } else {
              mockedApiClient.get.mockRejectedValue(new Error(errorMsg));
            }

            await useImpactAnalysisStore.getState().fetchReports();

            const state = useImpactAnalysisStore.getState();
            if (shouldSucceed) {
              expect(state.error).toBeNull();
            } else {
              expect(state.error).not.toBeNull();
              expect(state.error!.length).toBeGreaterThan(0);
            }
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: acknowledgeNotification always removes exactly the
     * notification with the given ID from the list (if it exists).
     *
     * **Validates: Requirements 10.7**
     */
    it("acknowledgeNotification removes exactly the target notification", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.array(fc.integer({ min: 1, max: 1000 }), { minLength: 1, maxLength: 20 }),
          async (ids) => {
            // Deduplicate IDs
            const uniqueIds = [...new Set(ids)];
            useImpactAnalysisStore.getState().reset();
            vi.clearAllMocks();

            const notifications = uniqueIds.map((id) => makeNotification({ id }));
            useImpactAnalysisStore.setState({ notifications });
            mockedApiClient.post.mockResolvedValue({});

            // Pick a random ID to acknowledge
            const targetId = uniqueIds[0];
            await useImpactAnalysisStore
              .getState()
              .acknowledgeNotification(targetId, "Test reason");

            const state = useImpactAnalysisStore.getState();
            // Target should be removed
            expect(state.notifications.find((n) => n.id === targetId)).toBeUndefined();
            // All others should remain
            expect(state.notifications).toHaveLength(uniqueIds.length - 1);
            for (const n of state.notifications) {
              expect(uniqueIds).toContain(n.id);
              expect(n.id).not.toBe(targetId);
            }
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: reset() always returns the store to its initial state
     * regardless of what state it was in before.
     *
     * **Validates: Requirements 10.7**
     */
    it("reset() always returns to initial state regardless of current state", () => {
      fc.assert(
        fc.property(
          fc.boolean(),
          fc.string({ minLength: 0, maxLength: 100 }),
          fc.array(fc.integer({ min: 1, max: 100 }), { minLength: 0, maxLength: 5 }),
          (isLoading, errorStr, notifIds) => {
            useImpactAnalysisStore.setState({
              reports: [makeReport()],
              notifications: notifIds.map((id) => makeNotification({ id })),
              isLoading,
              error: errorStr || null,
              activeJob: makeJobStatus(),
              documentStatus: { "doc-x": makeDocumentStatus() },
            });

            useImpactAnalysisStore.getState().reset();

            const state = useImpactAnalysisStore.getState();
            expect(state.reports).toEqual([]);
            expect(state.notifications).toEqual([]);
            expect(state.dependencyGraph).toEqual([]);
            expect(state.activeJob).toBeNull();
            expect(state.documentStatus).toEqual({});
            expect(state.isLoading).toBe(false);
            expect(state.error).toBeNull();
            expect(state.pollingIntervalId).toBeNull();
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: pollJobStatus does not start polling interval when
     * job status is terminal (completed, partial_success, failed).
     *
     * **Validates: Requirements 10.7**
     */
    it("pollJobStatus does not start interval for terminal statuses", async () => {
      const terminalStatus = fc.constantFrom("completed", "partial_success", "failed");

      await fc.assert(
        fc.asyncProperty(terminalStatus, async (status) => {
          useImpactAnalysisStore.getState().reset();
          vi.clearAllMocks();

          mockedApiClient.get.mockResolvedValue(makeJobStatus({ status }));

          await useImpactAnalysisStore.getState().pollJobStatus("job-x");

          const state = useImpactAnalysisStore.getState();
          expect(state.pollingIntervalId).toBeNull();
          expect(state.activeJob?.status).toBe(status);
        }),
        { numRuns: 20 },
      );
    });

    /**
     * Property: fetchDocumentStatus always stores the result under
     * the correct document UUID key without affecting other entries.
     *
     * **Validates: Requirements 10.7**
     */
    it("fetchDocumentStatus stores result under correct key without side effects", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.string({ minLength: 1, maxLength: 12 }).filter((s) => s.trim().length > 0),
          fc.string({ minLength: 1, maxLength: 12 }).filter((s) => s.trim().length > 0),
          async (existingUuid, newUuid) => {
            // Ensure they're different
            if (existingUuid === newUuid) return;

            useImpactAnalysisStore.getState().reset();
            vi.clearAllMocks();

            // Pre-populate with an existing entry
            const existingStatus = makeDocumentStatus({ document_uuid: existingUuid });
            useImpactAnalysisStore.setState({
              documentStatus: { [existingUuid]: existingStatus },
            });

            const newStatus = makeDocumentStatus({ document_uuid: newUuid });
            mockedApiClient.get.mockResolvedValue(newStatus);

            await useImpactAnalysisStore.getState().fetchDocumentStatus(newUuid);

            const state = useImpactAnalysisStore.getState();
            // New entry stored correctly
            expect(state.documentStatus[newUuid]).toEqual(newStatus);
            // Existing entry unchanged
            expect(state.documentStatus[existingUuid]).toEqual(existingStatus);
          },
        ),
        { numRuns: 50 },
      );
    });
  });
});
