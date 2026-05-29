import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Unit tests and property-based tests for traceabilityStore.
 *
 * Tests state transitions, action sequences, error handling, polling logic.
 * Tests 409 handling on generate, polling timeout behavior.
 * Uses fast-check for property-based testing of state invariants.
 *
 * **Validates: Requirements 8.9**
 */

// Mock apiClient module
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
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

import { useTraceabilityStore } from "@/stores/traceabilityStore";
import { apiClient, ApiError } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeMatrix(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    matrix_id: "mat-001",
    matrix_name: "Test Matrix",
    description: null,
    source_document_uuids: ["doc-001"],
    target_document_uuids: ["doc-002"],
    source_document_versions: [{ document_uuid: "doc-001", version_id: 1 }],
    target_document_versions: [{ document_uuid: "doc-002", version_id: 1 }],
    traceability_links: [],
    orphan_requirements: [],
    orphan_test_cases: [],
    coverage_metrics: {
      total_requirements: 10,
      covered_requirements: 8,
      orphan_requirements_count: 2,
      coverage_percentage: 80.0,
      total_test_cases: 12,
      linked_test_cases: 10,
      orphan_test_cases_count: 2,
      average_link_confidence: 0.85,
      compliance_readiness_score: 75.0,
    },
    status: "completed",
    parent_matrix_id: null,
    generation_timestamp: "2024-01-15T10:00:00Z",
    generation_duration_ms: 45000,
    agent_archetype_used: "Traceability Analyst",
    model_used: "gemma-4-e4b-it",
    total_token_count: 5000,
    requesting_user_id: 1,
    company_id: 1,
    deleted_at: null,
    created_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeLink(overrides: Record<string, unknown> = {}) {
  return {
    requirement_id: "REQ-001",
    requirement_text: "The system shall...",
    source_document_uuid: "doc-001",
    source_section: "Section 4.1",
    target_document_uuid: "doc-002",
    target_section: "Section 2.3",
    test_case_id: "TC-001",
    test_case_text: "Verify that...",
    link_confidence: 0.95,
    link_method: "exact_id_match",
    link_methods: ["exact_id_match"],
    verification_status: "unverified",
    ...overrides,
  };
}

function makeOrphanRequirement(overrides: Record<string, unknown> = {}) {
  return {
    requirement_id: "REQ-010",
    requirement_text: "The system shall comply with FDA...",
    source_document_uuid: "doc-001",
    source_section: "Section 5.1",
    severity: "critical",
    suggested_action: "create_test_case",
    ...overrides,
  };
}

function makeOrphanTestCase(overrides: Record<string, unknown> = {}) {
  return {
    test_case_id: "TC-020",
    test_case_text: "Verify label formatting...",
    target_document_uuid: "doc-002",
    target_section: "Section 3.2",
    risk_level: "low",
    suggested_action: "link_to_requirement",
    ...overrides,
  };
}

function makeJobStatus(overrides: Record<string, unknown> = {}) {
  return {
    job_id: "job-001",
    status: "processing",
    progress_percent: 50,
    current_phase: "establishing_links",
    requirements_extracted: 10,
    test_cases_extracted: 12,
    links_established: 5,
    orphans_detected: 0,
    error_message: null,
    matrix_id: null,
    total_requirements: null,
    total_test_cases: null,
    total_links: null,
    coverage_percentage: null,
    orphan_requirements_count: null,
    orphan_test_cases_count: null,
    compliance_readiness_score: null,
    generation_duration_ms: null,
    summary_sentence: null,
    ...overrides,
  };
}

function makeAlert(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    alert_id: "alert-001",
    triggering_report_id: "report-001",
    affected_matrix_ids: ["mat-001"],
    affected_link_count: 3,
    alert_severity: "major",
    is_resolved: false,
    resolved_at: null,
    resolved_by: null,
    resolution_action: null,
    resolution_note: null,
    company_id: 1,
    created_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeCoverageSummary(overrides: Record<string, unknown> = {}) {
  return {
    total_matrices_generated: 5,
    latest_matrix_date: "2024-01-15T10:00:00Z",
    average_coverage_percentage: 82.5,
    total_orphan_requirements: 4,
    total_orphan_test_cases: 2,
    average_compliance_readiness_score: 78.0,
    breakdown: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("traceabilityStore", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useTraceabilityStore.getState().reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    useTraceabilityStore.getState().stopPolling();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Initial state
  // -------------------------------------------------------------------------

  describe("initial state", () => {
    it("has correct defaults", () => {
      const state = useTraceabilityStore.getState();
      expect(state.matrices).toEqual([]);
      expect(state.currentMatrix).toBeNull();
      expect(state.links).toEqual([]);
      expect(state.orphanRequirements).toEqual([]);
      expect(state.orphanTestCases).toEqual([]);
      expect(state.coverageSummary).toBeNull();
      expect(state.coverageHistory).toEqual([]);
      expect(state.alerts).toEqual([]);
      expect(state.activeJob).toBeNull();
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.pollingIntervalId).toBeNull();
      expect(state.pollingStartTime).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // fetchMatrices()
  // -------------------------------------------------------------------------

  describe("fetchMatrices()", () => {
    it("sets isLoading to true during request", async () => {
      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));
      useTraceabilityStore.getState().fetchMatrices();
      await vi.waitFor(() => {
        expect(useTraceabilityStore.getState().isLoading).toBe(true);
      });
    });

    it("populates matrices on success", async () => {
      const matrices = [makeMatrix(), makeMatrix({ id: 2, matrix_id: "mat-002" })];
      mockedApiClient.get.mockResolvedValue({ matrices, total_count: 2 });

      await useTraceabilityStore.getState().fetchMatrices();

      const state = useTraceabilityStore.getState();
      expect(state.matrices).toEqual(matrices);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });

    it("handles errors: sets error state, clears isLoading", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network failure"));

      await useTraceabilityStore.getState().fetchMatrices();

      const state = useTraceabilityStore.getState();
      expect(state.error).toBe("Network failure");
      expect(state.isLoading).toBe(false);
    });

    it("passes filter params as query string", async () => {
      mockedApiClient.get.mockResolvedValue({ matrices: [], total_count: 0 });

      await useTraceabilityStore.getState().fetchMatrices({
        source_document_uuid: "doc-001",
        status: "completed",
        limit: 50,
        offset: 10,
      });

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("source_document_uuid=doc-001"),
      );
      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("status=completed"),
      );
      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("limit=50"),
      );
    });
  });

  // -------------------------------------------------------------------------
  // fetchMatrix()
  // -------------------------------------------------------------------------

  describe("fetchMatrix()", () => {
    it("populates currentMatrix on success", async () => {
      const matrix = makeMatrix();
      mockedApiClient.get.mockResolvedValue(matrix);

      await useTraceabilityStore.getState().fetchMatrix("mat-001");

      const state = useTraceabilityStore.getState();
      expect(state.currentMatrix).toEqual(matrix);
      expect(state.isLoading).toBe(false);
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(404, JSON.stringify({ detail: "Matrix not found" }), "/api/traceability/matrices/bad-id"),
      );

      await useTraceabilityStore.getState().fetchMatrix("bad-id");

      const state = useTraceabilityStore.getState();
      expect(state.error).toBe("Matrix not found");
      expect(state.isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // fetchLinks()
  // -------------------------------------------------------------------------

  describe("fetchLinks()", () => {
    it("populates links on success", async () => {
      const links = [makeLink(), makeLink({ test_case_id: "TC-002" })];
      mockedApiClient.get.mockResolvedValue({ links, total_count: 2 });

      await useTraceabilityStore.getState().fetchLinks("mat-001");

      const state = useTraceabilityStore.getState();
      expect(state.links).toEqual(links);
      expect(state.isLoading).toBe(false);
    });

    it("passes filter params", async () => {
      mockedApiClient.get.mockResolvedValue({ links: [], total_count: 0 });

      await useTraceabilityStore.getState().fetchLinks("mat-001", {
        link_confidence_min: 0.8,
        link_method: "exact_id_match",
      });

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("link_confidence_min=0.8"),
      );
      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("link_method=exact_id_match"),
      );
    });
  });

  // -------------------------------------------------------------------------
  // fetchOrphanRequirements()
  // -------------------------------------------------------------------------

  describe("fetchOrphanRequirements()", () => {
    it("populates orphanRequirements on success", async () => {
      const orphans = [makeOrphanRequirement()];
      mockedApiClient.get.mockResolvedValue({ orphan_requirements: orphans, total_count: 1 });

      await useTraceabilityStore.getState().fetchOrphanRequirements("mat-001");

      const state = useTraceabilityStore.getState();
      expect(state.orphanRequirements).toEqual(orphans);
      expect(state.isLoading).toBe(false);
    });

    it("handles errors", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Server error"));

      await useTraceabilityStore.getState().fetchOrphanRequirements("mat-001");

      expect(useTraceabilityStore.getState().error).toBe("Server error");
    });
  });

  // -------------------------------------------------------------------------
  // fetchOrphanTestCases()
  // -------------------------------------------------------------------------

  describe("fetchOrphanTestCases()", () => {
    it("populates orphanTestCases on success", async () => {
      const orphans = [makeOrphanTestCase()];
      mockedApiClient.get.mockResolvedValue({ orphan_test_cases: orphans, total_count: 1 });

      await useTraceabilityStore.getState().fetchOrphanTestCases("mat-001");

      const state = useTraceabilityStore.getState();
      expect(state.orphanTestCases).toEqual(orphans);
      expect(state.isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // generateMatrix()
  // -------------------------------------------------------------------------

  describe("generateMatrix()", () => {
    it("returns job_id on success and starts polling", async () => {
      mockedApiClient.post.mockResolvedValue({ job_id: "new-job-123" });
      mockedApiClient.get.mockResolvedValue(
        makeJobStatus({ job_id: "new-job-123", status: "completed" }),
      );

      const jobId = await useTraceabilityStore.getState().generateMatrix(
        {
          source_document_ids: [1, 2],
          target_document_ids: [3, 4, 5],
          matrix_name: "Test Matrix",
        },
        "Initial generation",
      );

      expect(jobId).toBe("new-job-123");
      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/traceability/matrices/generate",
        {
          source_document_ids: [1, 2],
          target_document_ids: [3, 4, 5],
          matrix_name: "Test Matrix",
        },
        { changeReason: "Initial generation" },
      );
    });

    it("handles 409 (concurrent job): sets error and polls existing job", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(
          409,
          JSON.stringify({ job_id: "existing-job-456" }),
          "/api/traceability/matrices/generate",
        ),
      );
      mockedApiClient.get.mockResolvedValue(
        makeJobStatus({ job_id: "existing-job-456", status: "completed" }),
      );

      const jobId = await useTraceabilityStore.getState().generateMatrix(
        {
          source_document_ids: [1],
          target_document_ids: [2],
          matrix_name: "Duplicate",
        },
        "Retry",
      );

      const state = useTraceabilityStore.getState();
      expect(state.error).toBe(
        "A matrix generation job is already in progress for these documents.",
      );
      expect(jobId).toBe("existing-job-456");
    });

    it("throws on non-409 errors", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(500, "Internal error", "/api/traceability/matrices/generate"),
      );

      await expect(
        useTraceabilityStore.getState().generateMatrix(
          { source_document_ids: [1], target_document_ids: [2], matrix_name: "X" },
          "Test",
        ),
      ).rejects.toThrow();

      const state = useTraceabilityStore.getState();
      expect(state.isLoading).toBe(false);
      expect(state.error).not.toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // deleteMatrix()
  // -------------------------------------------------------------------------

  describe("deleteMatrix()", () => {
    it("removes matrix from local list on success", async () => {
      useTraceabilityStore.setState({
        matrices: [
          makeMatrix({ matrix_id: "mat-001" }),
          makeMatrix({ id: 2, matrix_id: "mat-002" }),
        ],
      });
      mockedApiClient.delete.mockResolvedValue(undefined);

      await useTraceabilityStore.getState().deleteMatrix("mat-001", "No longer needed");

      const state = useTraceabilityStore.getState();
      expect(state.matrices).toHaveLength(1);
      expect(state.matrices[0].matrix_id).toBe("mat-002");
    });

    it("passes changeReason header", async () => {
      useTraceabilityStore.setState({ matrices: [makeMatrix()] });
      mockedApiClient.delete.mockResolvedValue(undefined);

      await useTraceabilityStore.getState().deleteMatrix("mat-001", "Obsolete");

      expect(mockedApiClient.delete).toHaveBeenCalledWith(
        "/api/traceability/matrices/mat-001",
        { changeReason: "Obsolete" },
      );
    });

    it("sets error on failure", async () => {
      useTraceabilityStore.setState({ matrices: [makeMatrix()] });
      mockedApiClient.delete.mockRejectedValue(
        new ApiError(404, JSON.stringify({ detail: "Not found" }), "/api/traceability/matrices/bad"),
      );

      await useTraceabilityStore.getState().deleteMatrix("bad", "Test");

      expect(useTraceabilityStore.getState().error).toBe("Not found");
    });
  });

  // -------------------------------------------------------------------------
  // fetchCoverageSummary()
  // -------------------------------------------------------------------------

  describe("fetchCoverageSummary()", () => {
    it("populates coverageSummary on success", async () => {
      const summary = makeCoverageSummary();
      mockedApiClient.get.mockResolvedValue(summary);

      await useTraceabilityStore.getState().fetchCoverageSummary();

      const state = useTraceabilityStore.getState();
      expect(state.coverageSummary).toEqual(summary);
      expect(state.isLoading).toBe(false);
    });

    it("handles errors", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Service unavailable"));

      await useTraceabilityStore.getState().fetchCoverageSummary();

      expect(useTraceabilityStore.getState().error).toBe("Service unavailable");
    });
  });

  // -------------------------------------------------------------------------
  // fetchCoverageHistory()
  // -------------------------------------------------------------------------

  describe("fetchCoverageHistory()", () => {
    it("populates coverageHistory on success", async () => {
      const snapshots = [
        { snapshot_date: "2024-01-15", matrix_id: "mat-001", source_document_uuid: "doc-001",
          coverage_percentage: 80, orphan_requirements_count: 2, orphan_test_cases_count: 1,
          compliance_readiness_score: 75, total_requirements: 10, covered_requirements: 8,
          total_test_cases: 12, linked_test_cases: 11 },
      ];
      mockedApiClient.get.mockResolvedValue({ snapshots, total_count: 1 });

      await useTraceabilityStore.getState().fetchCoverageHistory();

      expect(useTraceabilityStore.getState().coverageHistory).toEqual(snapshots);
    });
  });

  // -------------------------------------------------------------------------
  // fetchAlerts()
  // -------------------------------------------------------------------------

  describe("fetchAlerts()", () => {
    it("populates alerts on success", async () => {
      const alerts = [makeAlert(), makeAlert({ id: 2, alert_id: "alert-002" })];
      mockedApiClient.get.mockResolvedValue({ alerts, total_count: 2 });

      await useTraceabilityStore.getState().fetchAlerts();

      const state = useTraceabilityStore.getState();
      expect(state.alerts).toEqual(alerts);
      expect(state.isLoading).toBe(false);
    });

    it("handles errors", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Forbidden"));

      await useTraceabilityStore.getState().fetchAlerts();

      expect(useTraceabilityStore.getState().error).toBe("Forbidden");
    });
  });

  // -------------------------------------------------------------------------
  // resolveAlert()
  // -------------------------------------------------------------------------

  describe("resolveAlert()", () => {
    it("removes alert from local list on success", async () => {
      useTraceabilityStore.setState({
        alerts: [
          makeAlert({ alert_id: "alert-001" }),
          makeAlert({ id: 2, alert_id: "alert-002" }),
        ],
      });
      mockedApiClient.post.mockResolvedValue({});

      await useTraceabilityStore.getState().resolveAlert(
        "alert-001",
        { resolution_action: "links_verified", resolution_note: "Checked" },
        "Verified links are still valid",
      );

      const state = useTraceabilityStore.getState();
      expect(state.alerts).toHaveLength(1);
      expect(state.alerts[0].alert_id).toBe("alert-002");
    });

    it("passes changeReason header", async () => {
      useTraceabilityStore.setState({ alerts: [makeAlert()] });
      mockedApiClient.post.mockResolvedValue({});

      await useTraceabilityStore.getState().resolveAlert(
        "alert-001",
        { resolution_action: "matrix_regenerated" },
        "Regenerated matrix",
      );

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/traceability/alerts/alert-001/resolve",
        { resolution_action: "matrix_regenerated" },
        { changeReason: "Regenerated matrix" },
      );
    });

    it("sets error on failure", async () => {
      useTraceabilityStore.setState({ alerts: [makeAlert()] });
      mockedApiClient.post.mockRejectedValue(
        new ApiError(409, JSON.stringify({ detail: "Already resolved" }), "/api/traceability/alerts/alert-001/resolve"),
      );

      await useTraceabilityStore.getState().resolveAlert(
        "alert-001",
        { resolution_action: "no_action_needed" },
        "Test",
      );

      expect(useTraceabilityStore.getState().error).toBe("Already resolved");
    });
  });

  // -------------------------------------------------------------------------
  // pollJobStatus()
  // -------------------------------------------------------------------------

  describe("pollJobStatus()", () => {
    it("fetches initial status and sets activeJob", async () => {
      const jobStatus = makeJobStatus({ status: "completed" });
      mockedApiClient.get.mockResolvedValue(jobStatus);

      await useTraceabilityStore.getState().pollJobStatus("job-001");

      const state = useTraceabilityStore.getState();
      expect(state.activeJob).toEqual(jobStatus);
      // Should not start polling since status is terminal
      expect(state.pollingIntervalId).toBeNull();
    });

    it("starts polling when job is processing", async () => {
      const processingJob = makeJobStatus({ status: "processing" });
      mockedApiClient.get.mockResolvedValue(processingJob);

      await useTraceabilityStore.getState().pollJobStatus("job-001");

      const state = useTraceabilityStore.getState();
      expect(state.activeJob).toEqual(processingJob);
      expect(state.pollingIntervalId).not.toBeNull();
    });

    it("stops polling when job reaches terminal status", async () => {
      mockedApiClient.get
        .mockResolvedValueOnce(makeJobStatus({ status: "processing" }))
        .mockResolvedValueOnce(makeJobStatus({ status: "completed" }));

      await useTraceabilityStore.getState().pollJobStatus("job-001");
      expect(useTraceabilityStore.getState().pollingIntervalId).not.toBeNull();

      // Advance timer to trigger the interval
      await vi.advanceTimersByTimeAsync(5000);

      const state = useTraceabilityStore.getState();
      expect(state.activeJob?.status).toBe("completed");
      expect(state.pollingIntervalId).toBeNull();
    });

    it("sets error when initial fetch fails", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Job not found"));

      await useTraceabilityStore.getState().pollJobStatus("bad-job");

      const state = useTraceabilityStore.getState();
      expect(state.error).toBe("Job not found");
      expect(state.pollingIntervalId).toBeNull();
    });

    it("stops polling and sets error on timeout (10 minutes)", async () => {
      mockedApiClient.get.mockResolvedValue(makeJobStatus({ status: "processing" }));

      await useTraceabilityStore.getState().pollJobStatus("job-001");
      expect(useTraceabilityStore.getState().pollingIntervalId).not.toBeNull();

      // Advance time past the 10-minute timeout
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000);

      const state = useTraceabilityStore.getState();
      expect(state.pollingIntervalId).toBeNull();
      expect(state.error).toBe(
        "Matrix generation timed out after 10 minutes. You can retry the operation.",
      );
    });
  });

  // -------------------------------------------------------------------------
  // fetchDocumentCoverage()
  // -------------------------------------------------------------------------

  describe("fetchDocumentCoverage()", () => {
    it("returns document coverage on success", async () => {
      const coverage = {
        document_uuid: "doc-001",
        latest_matrix_id: "mat-001",
        latest_matrix_date: "2024-01-15T10:00:00Z",
        coverage_percentage: 80.0,
        orphan_requirement_count: 2,
        total_requirements: 10,
        compliance_readiness_score: 75.0,
      };
      mockedApiClient.get.mockResolvedValue(coverage);

      const result = await useTraceabilityStore.getState().fetchDocumentCoverage("doc-001");

      expect(result).toEqual(coverage);
      expect(useTraceabilityStore.getState().isLoading).toBe(false);
    });

    it("throws and sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Not found"));

      await expect(
        useTraceabilityStore.getState().fetchDocumentCoverage("bad-doc"),
      ).rejects.toThrow("Not found");

      expect(useTraceabilityStore.getState().error).toBe("Not found");
    });
  });

  // -------------------------------------------------------------------------
  // reset()
  // -------------------------------------------------------------------------

  describe("reset()", () => {
    it("resets all state to defaults", () => {
      useTraceabilityStore.setState({
        matrices: [makeMatrix()],
        currentMatrix: makeMatrix(),
        links: [makeLink()],
        orphanRequirements: [makeOrphanRequirement()],
        orphanTestCases: [makeOrphanTestCase()],
        coverageSummary: makeCoverageSummary(),
        coverageHistory: [],
        alerts: [makeAlert()],
        activeJob: makeJobStatus(),
        isLoading: true,
        error: "some error",
      });

      useTraceabilityStore.getState().reset();

      const state = useTraceabilityStore.getState();
      expect(state.matrices).toEqual([]);
      expect(state.currentMatrix).toBeNull();
      expect(state.links).toEqual([]);
      expect(state.orphanRequirements).toEqual([]);
      expect(state.orphanTestCases).toEqual([]);
      expect(state.coverageSummary).toBeNull();
      expect(state.coverageHistory).toEqual([]);
      expect(state.alerts).toEqual([]);
      expect(state.activeJob).toBeNull();
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.pollingIntervalId).toBeNull();
      expect(state.pollingStartTime).toBeNull();
    });
  });

  // =========================================================================
  // Property-Based Tests (fast-check)
  // =========================================================================

  describe("property: state invariants", () => {
    /**
     * Property: After any fetch action (success or failure),
     * isLoading is always false when the promise resolves.
     *
     * **Validates: Requirements 8.9**
     */
    it("isLoading is always false after fetchMatrices resolves", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.boolean(),
          fc.string({ minLength: 1, maxLength: 100 }),
          async (shouldSucceed, errorMsg) => {
            useTraceabilityStore.getState().reset();
            vi.clearAllMocks();

            if (shouldSucceed) {
              mockedApiClient.get.mockResolvedValue({
                matrices: [],
                total_count: 0,
              });
            } else {
              mockedApiClient.get.mockRejectedValue(new Error(errorMsg));
            }

            await useTraceabilityStore.getState().fetchMatrices();

            expect(useTraceabilityStore.getState().isLoading).toBe(false);
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: On success, error is always null. On failure, error is
     * always a non-empty string.
     *
     * **Validates: Requirements 8.9**
     */
    it("error is null on success, non-empty string on failure", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.boolean(),
          fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.trim().length > 0),
          async (shouldSucceed, errorMsg) => {
            useTraceabilityStore.getState().reset();
            vi.clearAllMocks();

            if (shouldSucceed) {
              mockedApiClient.get.mockResolvedValue({
                matrices: [],
                total_count: 0,
              });
            } else {
              mockedApiClient.get.mockRejectedValue(new Error(errorMsg));
            }

            await useTraceabilityStore.getState().fetchMatrices();

            const state = useTraceabilityStore.getState();
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
     * Property: resolveAlert always removes exactly the alert with
     * the given alert_id from the list (if it exists).
     *
     * **Validates: Requirements 8.9**
     */
    it("resolveAlert removes exactly the target alert", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.array(
            fc.string({ minLength: 5, maxLength: 20 }).filter((s) => /^[a-z0-9-]+$/.test(s)),
            { minLength: 1, maxLength: 10 },
          ),
          async (alertIds) => {
            const uniqueIds = [...new Set(alertIds)];
            if (uniqueIds.length === 0) return;

            useTraceabilityStore.getState().reset();
            vi.clearAllMocks();

            const alerts = uniqueIds.map((id, i) =>
              makeAlert({ id: i + 1, alert_id: id }),
            );
            useTraceabilityStore.setState({ alerts });
            mockedApiClient.post.mockResolvedValue({});

            const targetId = uniqueIds[0];
            await useTraceabilityStore.getState().resolveAlert(
              targetId,
              { resolution_action: "links_verified" },
              "Test reason",
            );

            const state = useTraceabilityStore.getState();
            expect(state.alerts.find((a) => a.alert_id === targetId)).toBeUndefined();
            expect(state.alerts).toHaveLength(uniqueIds.length - 1);
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: deleteMatrix always removes exactly the matrix with
     * the given matrix_id from the list.
     *
     * **Validates: Requirements 8.9**
     */
    it("deleteMatrix removes exactly the target matrix", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.array(
            fc.string({ minLength: 5, maxLength: 20 }).filter((s) => /^[a-z0-9-]+$/.test(s)),
            { minLength: 1, maxLength: 10 },
          ),
          async (matrixIds) => {
            const uniqueIds = [...new Set(matrixIds)];
            if (uniqueIds.length === 0) return;

            useTraceabilityStore.getState().reset();
            vi.clearAllMocks();

            const matrices = uniqueIds.map((id, i) =>
              makeMatrix({ id: i + 1, matrix_id: id }),
            );
            useTraceabilityStore.setState({ matrices });
            mockedApiClient.delete.mockResolvedValue(undefined);

            const targetId = uniqueIds[0];
            await useTraceabilityStore.getState().deleteMatrix(targetId, "Remove");

            const state = useTraceabilityStore.getState();
            expect(state.matrices.find((m) => m.matrix_id === targetId)).toBeUndefined();
            expect(state.matrices).toHaveLength(uniqueIds.length - 1);
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: reset() always returns the store to its initial state
     * regardless of what state it was in before.
     *
     * **Validates: Requirements 8.9**
     */
    it("reset() always returns to initial state regardless of current state", () => {
      fc.assert(
        fc.property(
          fc.boolean(),
          fc.string({ minLength: 0, maxLength: 100 }),
          fc.array(fc.integer({ min: 1, max: 100 }), { minLength: 0, maxLength: 5 }),
          (isLoading, errorStr, alertIds) => {
            useTraceabilityStore.setState({
              matrices: [makeMatrix()],
              currentMatrix: makeMatrix(),
              links: [makeLink()],
              orphanRequirements: [makeOrphanRequirement()],
              orphanTestCases: [makeOrphanTestCase()],
              alerts: alertIds.map((id) => makeAlert({ id, alert_id: `alert-${id}` })),
              isLoading,
              error: errorStr || null,
              activeJob: makeJobStatus(),
              coverageSummary: makeCoverageSummary(),
            });

            useTraceabilityStore.getState().reset();

            const state = useTraceabilityStore.getState();
            expect(state.matrices).toEqual([]);
            expect(state.currentMatrix).toBeNull();
            expect(state.links).toEqual([]);
            expect(state.orphanRequirements).toEqual([]);
            expect(state.orphanTestCases).toEqual([]);
            expect(state.coverageSummary).toBeNull();
            expect(state.coverageHistory).toEqual([]);
            expect(state.alerts).toEqual([]);
            expect(state.activeJob).toBeNull();
            expect(state.isLoading).toBe(false);
            expect(state.error).toBeNull();
            expect(state.pollingIntervalId).toBeNull();
            expect(state.pollingStartTime).toBeNull();
          },
        ),
        { numRuns: 50 },
      );
    });

    /**
     * Property: pollJobStatus does not start polling interval when
     * job status is terminal (completed, partial_success, failed).
     *
     * **Validates: Requirements 8.9**
     */
    it("pollJobStatus does not start interval for terminal statuses", async () => {
      const terminalStatus = fc.constantFrom("completed", "partial_success", "failed");

      await fc.assert(
        fc.asyncProperty(terminalStatus, async (status) => {
          useTraceabilityStore.getState().reset();
          vi.clearAllMocks();

          mockedApiClient.get.mockResolvedValue(makeJobStatus({ status }));

          await useTraceabilityStore.getState().pollJobStatus("job-x");

          const state = useTraceabilityStore.getState();
          expect(state.pollingIntervalId).toBeNull();
          expect(state.activeJob?.status).toBe(status);
        }),
        { numRuns: 20 },
      );
    });

    /**
     * Property: generateMatrix on 409 always sets the specific error message
     * and never throws, regardless of the response body content.
     *
     * **Validates: Requirements 8.9**
     */
    it("generateMatrix on 409 always sets error message without throwing", async () => {
      await fc.assert(
        fc.asyncProperty(
          fc.string({ minLength: 0, maxLength: 50 }),
          async (jobId) => {
            useTraceabilityStore.getState().reset();
            vi.clearAllMocks();

            const body = jobId ? JSON.stringify({ job_id: jobId }) : "{}";
            mockedApiClient.post.mockRejectedValue(
              new ApiError(409, body, "/api/traceability/matrices/generate"),
            );
            // Mock the polling call if job_id is present
            if (jobId) {
              mockedApiClient.get.mockResolvedValue(
                makeJobStatus({ job_id: jobId, status: "completed" }),
              );
            }

            const result = await useTraceabilityStore.getState().generateMatrix(
              { source_document_ids: [1], target_document_ids: [2], matrix_name: "T" },
              "Test",
            );

            const state = useTraceabilityStore.getState();
            expect(state.error).toBe(
              "A matrix generation job is already in progress for these documents.",
            );
            expect(state.isLoading).toBe(false);
            expect(result).toBe(jobId || "");
          },
        ),
        { numRuns: 30 },
      );
    });
  });
});
