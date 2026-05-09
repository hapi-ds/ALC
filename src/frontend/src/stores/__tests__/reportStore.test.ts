import { describe, it, expect, beforeEach, vi } from "vitest";
import { useReportStore } from "../reportStore";
import type { ReportResponse, ComparisonData } from "../../types/report";

// Mock apiClient module
vi.mock("../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    upload: vi.fn(),
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

// Mock tokenStorage and authStore (used by downloadBlankPdf)
vi.mock("../../lib/tokenStorage", () => ({
  getAccessToken: vi.fn(() => "mock-token"),
}));

vi.mock("../authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 1 },
      activeCompanyId: 100,
    }),
  },
}));

// Import mocked modules for assertions
import { apiClient, ApiError } from "../../lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  upload: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeReport(overrides: Partial<ReportResponse> = {}): ReportResponse {
  return {
    id: 1,
    document_uuid: "2024-00001",
    template_id: 10,
    uploaded_by: 1,
    uploaded_at: "2024-03-15T14:30:00Z",
    status: "Draft",
    field_values: [
      { field_uuid: "FLD-00000001", value: "test value", validated: false },
    ],
    ...overrides,
  };
}

function makeComparisonData(): ComparisonData {
  return {
    report_id: 1,
    compared_with_report_id: 2,
    total_fields: 3,
    matches: 2,
    discrepancies: 1,
    rows: [
      {
        field_uuid: "FLD-00000001",
        field_label: "Sample Name",
        extracted_value: "ABC",
        entered_value: "ABC",
        is_match: true,
      },
      {
        field_uuid: "FLD-00000002",
        field_label: "Weight",
        extracted_value: "10.5",
        entered_value: "10.5",
        is_match: true,
      },
      {
        field_uuid: "FLD-00000003",
        field_label: "Date",
        extracted_value: "2024-01-01",
        entered_value: "2024-01-02",
        is_match: false,
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("reportStore", () => {
  beforeEach(() => {
    // Reset store state
    useReportStore.setState({
      reports: [],
      isLoadingList: false,
      listError: null,
      currentReport: null,
      isLoadingDetail: false,
      detailError: null,
      isSubmitting: false,
      submitError: null,
      isUploading: false,
      uploadError: null,
      comparisonData: null,
      isLoadingComparison: false,
      comparisonError: null,
      isDownloadingPdf: false,
      downloadPdfError: null,
    });
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // fetchReportList
  // -------------------------------------------------------------------------

  describe("fetchReportList", () => {
    it("sets isLoadingList to true and clears listError on start", async () => {
      // Set a pre-existing error to verify it gets cleared
      useReportStore.setState({ listError: "previous error" });

      mockedApiClient.get.mockImplementation(
        () => new Promise(() => {}), // never resolves
      );

      // Don't await — just trigger the action
      useReportStore.getState().fetchReportList();

      // After the synchronous set(), loading should be true and error cleared
      await vi.waitFor(() => {
        const state = useReportStore.getState();
        expect(state.isLoadingList).toBe(true);
        expect(state.listError).toBeNull();
      });
    });

    it("sets reports and isLoadingList=false on success", async () => {
      const reports = [makeReport({ id: 1 }), makeReport({ id: 2 })];
      mockedApiClient.get.mockResolvedValue(reports);

      await useReportStore.getState().fetchReportList();

      const state = useReportStore.getState();
      expect(state.reports).toEqual(reports);
      expect(state.isLoadingList).toBe(false);
      expect(state.listError).toBeNull();
      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/reports");
    });

    it("sets listError and isLoadingList=false on ApiError", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(500, "Internal server error", "/api/reports"),
      );

      await useReportStore.getState().fetchReportList();

      const state = useReportStore.getState();
      expect(state.listError).toBe("Internal server error");
      expect(state.isLoadingList).toBe(false);
      expect(state.reports).toEqual([]);
    });

    it("sets generic error message for non-ApiError failures", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network failure"));

      await useReportStore.getState().fetchReportList();

      const state = useReportStore.getState();
      expect(state.listError).toBe("Failed to load reports");
      expect(state.isLoadingList).toBe(false);
    });

    it("clears previous error when a new request starts", async () => {
      // First call fails
      mockedApiClient.get.mockRejectedValueOnce(
        new ApiError(500, "Server error", "/api/reports"),
      );
      await useReportStore.getState().fetchReportList();
      expect(useReportStore.getState().listError).toBe("Server error");

      // Second call succeeds — error should be cleared
      mockedApiClient.get.mockResolvedValueOnce([makeReport()]);
      await useReportStore.getState().fetchReportList();

      const state = useReportStore.getState();
      expect(state.listError).toBeNull();
      expect(state.reports).toHaveLength(1);
    });
  });

  // -------------------------------------------------------------------------
  // fetchReportDetail
  // -------------------------------------------------------------------------

  describe("fetchReportDetail", () => {
    it("sets isLoadingDetail to true and clears detailError on start", async () => {
      useReportStore.setState({ detailError: "old error" });

      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));

      useReportStore.getState().fetchReportDetail(42);

      await vi.waitFor(() => {
        const state = useReportStore.getState();
        expect(state.isLoadingDetail).toBe(true);
        expect(state.detailError).toBeNull();
      });
    });

    it("sets currentReport and isLoadingDetail=false on success", async () => {
      const report = makeReport({ id: 42 });
      mockedApiClient.get.mockResolvedValue(report);

      await useReportStore.getState().fetchReportDetail(42);

      const state = useReportStore.getState();
      expect(state.currentReport).toEqual(report);
      expect(state.isLoadingDetail).toBe(false);
      expect(state.detailError).toBeNull();
      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/reports/42");
    });

    it("sets detailError and isLoadingDetail=false on failure", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(404, "Report not found", "/api/reports/99"),
      );

      await useReportStore.getState().fetchReportDetail(99);

      const state = useReportStore.getState();
      expect(state.detailError).toBe("Report not found");
      expect(state.isLoadingDetail).toBe(false);
      expect(state.currentReport).toBeNull();
    });

    it("clears previous detailError on new request", async () => {
      mockedApiClient.get.mockRejectedValueOnce(
        new ApiError(404, "Not found", "/api/reports/1"),
      );
      await useReportStore.getState().fetchReportDetail(1);
      expect(useReportStore.getState().detailError).toBe("Not found");

      mockedApiClient.get.mockResolvedValueOnce(makeReport({ id: 2 }));
      await useReportStore.getState().fetchReportDetail(2);

      expect(useReportStore.getState().detailError).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // submitReport
  // -------------------------------------------------------------------------

  describe("submitReport", () => {
    it("sets isSubmitting to true and clears submitError on start", async () => {
      useReportStore.setState({ submitError: "old submit error" });

      mockedApiClient.post.mockImplementation(() => new Promise(() => {}));

      useReportStore.getState().submitReport("2024-00001", [
        { field_uuid: "FLD-00000001", value: "test" },
      ]);

      await vi.waitFor(() => {
        const state = useReportStore.getState();
        expect(state.isSubmitting).toBe(true);
        expect(state.submitError).toBeNull();
      });
    });

    it("sets currentReport, isSubmitting=false, and returns report on success", async () => {
      const report = makeReport({ id: 5 });
      mockedApiClient.post.mockResolvedValue(report);

      const result = await useReportStore.getState().submitReport("2024-00001", [
        { field_uuid: "FLD-00000001", value: "test" },
      ]);

      const state = useReportStore.getState();
      expect(state.currentReport).toEqual(report);
      expect(state.isSubmitting).toBe(false);
      expect(state.submitError).toBeNull();
      expect(result).toEqual(report);
      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/reports",
        {
          document_uuid: "2024-00001",
          field_values: [{ field_uuid: "FLD-00000001", value: "test" }],
        },
        { changeReason: "Report created via manual data entry" },
      );
    });

    it("prepends new report to list when list was previously fetched", async () => {
      const existingReport = makeReport({ id: 1 });
      useReportStore.setState({ reports: [existingReport] });

      const newReport = makeReport({ id: 2 });
      mockedApiClient.post.mockResolvedValue(newReport);

      await useReportStore.getState().submitReport("2024-00001", [
        { field_uuid: "FLD-00000001", value: "val" },
      ]);

      const state = useReportStore.getState();
      expect(state.reports).toHaveLength(2);
      expect(state.reports[0]).toEqual(newReport);
      expect(state.reports[1]).toEqual(existingReport);
    });

    it("does not modify empty reports list on success", async () => {
      useReportStore.setState({ reports: [] });

      const newReport = makeReport({ id: 3 });
      mockedApiClient.post.mockResolvedValue(newReport);

      await useReportStore.getState().submitReport("2024-00001", [
        { field_uuid: "FLD-00000001", value: "val" },
      ]);

      const state = useReportStore.getState();
      expect(state.reports).toEqual([]);
    });

    it("sets submitError, isSubmitting=false, and throws on ApiError", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(400, "Validation failed", "/api/reports"),
      );

      await expect(
        useReportStore.getState().submitReport("2024-00001", [
          { field_uuid: "FLD-00000001", value: "bad" },
        ]),
      ).rejects.toThrow();

      const state = useReportStore.getState();
      expect(state.submitError).toBe("Validation failed");
      expect(state.isSubmitting).toBe(false);
    });

    it("sets generic error message for non-ApiError failures", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("Network timeout"));

      await expect(
        useReportStore.getState().submitReport("2024-00001", [
          { field_uuid: "FLD-00000001", value: "val" },
        ]),
      ).rejects.toThrow();

      const state = useReportStore.getState();
      expect(state.submitError).toBe("Failed to submit report");
    });

    it("clears previous submitError on new request", async () => {
      mockedApiClient.post.mockRejectedValueOnce(
        new ApiError(400, "Bad request", "/api/reports"),
      );
      await expect(
        useReportStore.getState().submitReport("2024-00001", [
          { field_uuid: "FLD-00000001", value: "x" },
        ]),
      ).rejects.toThrow();
      expect(useReportStore.getState().submitError).toBe("Bad request");

      mockedApiClient.post.mockResolvedValueOnce(makeReport());
      await useReportStore.getState().submitReport("2024-00001", [
        { field_uuid: "FLD-00000001", value: "y" },
      ]);

      expect(useReportStore.getState().submitError).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // uploadPdf
  // -------------------------------------------------------------------------

  describe("uploadPdf", () => {
    it("sets isUploading to true and clears uploadError on start", async () => {
      useReportStore.setState({ uploadError: "old upload error" });

      mockedApiClient.upload.mockImplementation(() => new Promise(() => {}));

      const file = new File(["pdf content"], "test.pdf", { type: "application/pdf" });
      useReportStore.getState().uploadPdf(file);

      await vi.waitFor(() => {
        const state = useReportStore.getState();
        expect(state.isUploading).toBe(true);
        expect(state.uploadError).toBeNull();
      });
    });

    it("sets currentReport, isUploading=false, and returns report on success", async () => {
      const report = makeReport({ id: 7, status: "Extracted" });
      mockedApiClient.upload.mockResolvedValue(report);

      const file = new File(["pdf content"], "test.pdf", { type: "application/pdf" });
      const result = await useReportStore.getState().uploadPdf(file);

      const state = useReportStore.getState();
      expect(state.currentReport).toEqual(report);
      expect(state.isUploading).toBe(false);
      expect(state.uploadError).toBeNull();
      expect(result).toEqual(report);

      // Verify upload was called with correct args
      expect(mockedApiClient.upload).toHaveBeenCalledWith(
        "/api/reports/upload-pdf",
        expect.any(FormData),
        undefined,
        "Report created via PDF extraction",
      );
    });

    it("prepends new report to list when list was previously fetched", async () => {
      const existingReport = makeReport({ id: 1 });
      useReportStore.setState({ reports: [existingReport] });

      const newReport = makeReport({ id: 8, status: "Extracted" });
      mockedApiClient.upload.mockResolvedValue(newReport);

      const file = new File(["pdf"], "report.pdf", { type: "application/pdf" });
      await useReportStore.getState().uploadPdf(file);

      const state = useReportStore.getState();
      expect(state.reports).toHaveLength(2);
      expect(state.reports[0]).toEqual(newReport);
      expect(state.reports[1]).toEqual(existingReport);
    });

    it("does not modify empty reports list on success", async () => {
      useReportStore.setState({ reports: [] });

      const newReport = makeReport({ id: 9, status: "Extracted" });
      mockedApiClient.upload.mockResolvedValue(newReport);

      const file = new File(["pdf"], "report.pdf", { type: "application/pdf" });
      await useReportStore.getState().uploadPdf(file);

      expect(useReportStore.getState().reports).toEqual([]);
    });

    it("sets uploadError, isUploading=false, and throws on ApiError", async () => {
      mockedApiClient.upload.mockRejectedValue(
        new ApiError(400, "Invalid PDF", "/api/reports/upload-pdf"),
      );

      const file = new File(["bad"], "bad.pdf", { type: "application/pdf" });
      await expect(useReportStore.getState().uploadPdf(file)).rejects.toThrow();

      const state = useReportStore.getState();
      expect(state.uploadError).toBe("Invalid PDF");
      expect(state.isUploading).toBe(false);
    });

    it("sets generic error message for non-ApiError failures", async () => {
      mockedApiClient.upload.mockRejectedValue(new Error("Connection lost"));

      const file = new File(["pdf"], "test.pdf", { type: "application/pdf" });
      await expect(useReportStore.getState().uploadPdf(file)).rejects.toThrow();

      expect(useReportStore.getState().uploadError).toBe("Failed to upload PDF");
    });

    it("clears previous uploadError on new request", async () => {
      mockedApiClient.upload.mockRejectedValueOnce(
        new ApiError(400, "Bad PDF", "/api/reports/upload-pdf"),
      );
      const file = new File(["bad"], "bad.pdf", { type: "application/pdf" });
      await expect(useReportStore.getState().uploadPdf(file)).rejects.toThrow();
      expect(useReportStore.getState().uploadError).toBe("Bad PDF");

      mockedApiClient.upload.mockResolvedValueOnce(makeReport({ id: 10 }));
      const goodFile = new File(["good"], "good.pdf", { type: "application/pdf" });
      await useReportStore.getState().uploadPdf(goodFile);

      expect(useReportStore.getState().uploadError).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // fetchComparisonData
  // -------------------------------------------------------------------------

  describe("fetchComparisonData", () => {
    it("sets isLoadingComparison to true and clears errors on start", async () => {
      useReportStore.setState({
        comparisonError: "old comparison error",
        comparisonData: makeComparisonData(),
      });

      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));

      useReportStore.getState().fetchComparisonData(1);

      await vi.waitFor(() => {
        const state = useReportStore.getState();
        expect(state.isLoadingComparison).toBe(true);
        expect(state.comparisonError).toBeNull();
        expect(state.comparisonData).toBeNull();
      });
    });

    it("sets comparisonData and isLoadingComparison=false on success", async () => {
      const data = makeComparisonData();
      mockedApiClient.get.mockResolvedValue(data);

      await useReportStore.getState().fetchComparisonData(1);

      const state = useReportStore.getState();
      expect(state.comparisonData).toEqual(data);
      expect(state.isLoadingComparison).toBe(false);
      expect(state.comparisonError).toBeNull();
      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/reports/1/compare");
    });

    it("sets comparisonError and clears comparisonData on failure", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(400, "No matching report", "/api/reports/1/compare"),
      );

      await useReportStore.getState().fetchComparisonData(1);

      const state = useReportStore.getState();
      expect(state.comparisonError).toBe("No matching report");
      expect(state.isLoadingComparison).toBe(false);
      expect(state.comparisonData).toBeNull();
    });

    it("sets generic error message for non-ApiError failures", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network error"));

      await useReportStore.getState().fetchComparisonData(1);

      expect(useReportStore.getState().comparisonError).toBe("Failed to load comparison");
    });

    it("clears previous comparisonError on new request", async () => {
      mockedApiClient.get.mockRejectedValueOnce(
        new ApiError(500, "Server error", "/api/reports/1/compare"),
      );
      await useReportStore.getState().fetchComparisonData(1);
      expect(useReportStore.getState().comparisonError).toBe("Server error");

      mockedApiClient.get.mockResolvedValueOnce(makeComparisonData());
      await useReportStore.getState().fetchComparisonData(1);

      expect(useReportStore.getState().comparisonError).toBeNull();
    });
  });
});
