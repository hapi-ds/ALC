/**
 * Unit tests for VideoAlignmentActions component.
 *
 * Tests cover:
 * - Action buttons display when no report exists
 * - Triggering API calls for each action
 * - Job progress tracking with polling
 * - Auto-render results on completion
 * - Error handling (network, 5xx, timeout)
 * - Retry button functionality
 *
 * Requirements: 11.6, 11.7, 11.8
 */

import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent, waitFor, act } from "@testing-library/react";
import { VideoAlignmentActions } from "../VideoAlignmentActions";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/apiClient", () => {
  class MockApiError extends Error {
    status: number;
    body: string;
    url: string;
    constructor(status: number, body: string, url: string) {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  }

  return {
    apiClient: {
      get: (...args: unknown[]) => mockGet(...args),
      post: (...args: unknown[]) => mockPost(...args),
    },
    ApiError: MockApiError,
  };
});

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VideoAlignmentActions", () => {
  const defaultProps = {
    documentUuid: "2024-00001",
    onReportReady: vi.fn(),
  };

  // -------------------------------------------------------------------------
  // 1. Action buttons display
  // -------------------------------------------------------------------------

  describe("Action Buttons (no report exists)", () => {
    it("renders all three action buttons in sequence", () => {
      render(<VideoAlignmentActions {...defaultProps} />);

      expect(screen.getByLabelText("Extract Frames")).toBeInTheDocument();
      expect(screen.getByLabelText("Analyze Frames")).toBeInTheDocument();
      expect(screen.getByLabelText("Align with SOP")).toBeInTheDocument();
    });

    it("displays instructional text about running steps in sequence", () => {
      render(<VideoAlignmentActions {...defaultProps} />);

      expect(
        screen.getByText(/No alignment report exists for this video/i)
      ).toBeInTheDocument();
    });

    it("renders numbered step indicators", () => {
      render(<VideoAlignmentActions {...defaultProps} />);

      expect(screen.getByText("1")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("3")).toBeInTheDocument();
    });

    it("renders as a region with proper aria label", () => {
      render(<VideoAlignmentActions {...defaultProps} />);

      expect(
        screen.getByRole("region", { name: "Video alignment actions" })
      ).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 2. Triggering API calls
  // -------------------------------------------------------------------------

  describe("Triggering Actions", () => {
    it("calls POST extract-frames when Extract Frames is clicked", async () => {
      mockPost.mockResolvedValueOnce({
        job_id: "job-123",
        status: "processing",
        estimated_duration_seconds: 60,
      });
      // Mock the polling response
      mockGet.mockResolvedValue({
        job_id: "job-123",
        status: "processing",
        started_at: new Date().toISOString(),
        completed_at: null,
        progress_percent: 10,
        result_reference: null,
        error_message: null,
      });

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      expect(mockPost).toHaveBeenCalledWith(
        "/api/knowledge/videos/2024-00001/extract-frames",
        undefined,
        expect.objectContaining({ changeReason: expect.any(String) })
      );
    });

    it("calls POST analyze-frames when Analyze Frames is clicked", async () => {
      mockPost.mockResolvedValueOnce({
        job_id: "job-456",
        status: "processing",
        estimated_duration_seconds: 300,
      });
      mockGet.mockResolvedValue({
        job_id: "job-456",
        status: "processing",
        started_at: new Date().toISOString(),
        completed_at: null,
        progress_percent: 5,
        result_reference: null,
        error_message: null,
      });

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Analyze Frames"));
      });

      expect(mockPost).toHaveBeenCalledWith(
        "/api/knowledge/videos/2024-00001/analyze-frames",
        undefined,
        expect.objectContaining({ changeReason: expect.any(String) })
      );
    });

    it("calls POST align when Align with SOP is clicked", async () => {
      mockPost.mockResolvedValueOnce({
        job_id: "job-789",
        status: "processing",
        estimated_duration_seconds: 180,
      });
      mockGet.mockResolvedValue({
        job_id: "job-789",
        status: "processing",
        started_at: new Date().toISOString(),
        completed_at: null,
        progress_percent: 0,
        result_reference: null,
        error_message: null,
      });

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Align with SOP"));
      });

      expect(mockPost).toHaveBeenCalledWith(
        "/api/knowledge/videos/2024-00001/align",
        undefined,
        expect.objectContaining({ changeReason: expect.any(String) })
      );
    });
  });

  // -------------------------------------------------------------------------
  // 3. Progress tracking
  // -------------------------------------------------------------------------

  describe("Job Progress Tracking", () => {
    it("shows progress bar after triggering an action", async () => {
      mockPost.mockResolvedValueOnce({
        job_id: "job-123",
        status: "processing",
        estimated_duration_seconds: 60,
      });
      mockGet.mockResolvedValue({
        job_id: "job-123",
        status: "processing",
        started_at: new Date().toISOString(),
        completed_at: null,
        progress_percent: 45,
        result_reference: null,
        error_message: null,
      });

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByRole("progressbar")).toBeInTheDocument();
      });

      expect(screen.getByLabelText("Progress: 45%")).toBeInTheDocument();
    });

    it("displays the action label during processing", async () => {
      mockPost.mockResolvedValueOnce({
        job_id: "job-123",
        status: "processing",
        estimated_duration_seconds: 60,
      });
      mockGet.mockResolvedValue({
        job_id: "job-123",
        status: "processing",
        started_at: new Date().toISOString(),
        completed_at: null,
        progress_percent: 20,
        result_reference: null,
        error_message: null,
      });

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByText("Extract Frames")).toBeInTheDocument();
        expect(screen.getByRole("progressbar")).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // 4. Error handling
  // -------------------------------------------------------------------------

  describe("Error Handling", () => {
    it("shows error message on network failure when triggering action", async () => {
      mockPost.mockRejectedValueOnce(new TypeError("Failed to fetch"));

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });

    it("shows error message on 5xx server error", async () => {
      const { ApiError: MockApiError } = await import("@/lib/apiClient");
      mockPost.mockRejectedValueOnce(
        new MockApiError(500, "Internal Server Error", "/api/test")
      );

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });
      expect(screen.getByText(/Server error/i)).toBeInTheDocument();
    });

    it("shows retry button on error", async () => {
      mockPost.mockRejectedValueOnce(new TypeError("Failed to fetch"));

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByLabelText("Retry operation")).toBeInTheDocument();
      });
    });

    it("shows error when job status is failed", async () => {
      mockPost.mockResolvedValueOnce({
        job_id: "job-fail",
        status: "processing",
        estimated_duration_seconds: 60,
      });
      mockGet.mockResolvedValue({
        job_id: "job-fail",
        status: "failed",
        started_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        progress_percent: 30,
        result_reference: null,
        error_message: "Frame extraction failed: corrupt video file",
      });

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeInTheDocument();
      });
      expect(
        screen.getByText(/Frame extraction failed: corrupt video file/i)
      ).toBeInTheDocument();
    });

    it("shows 409 conflict error message", async () => {
      const { ApiError: MockApiError } = await import("@/lib/apiClient");
      mockPost.mockRejectedValueOnce(
        new MockApiError(409, "Frame extraction is already in progress", "/api/test")
      );

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByText(/already in progress/i)).toBeInTheDocument();
      });
    });
  });

  // -------------------------------------------------------------------------
  // 5. Retry functionality
  // -------------------------------------------------------------------------

  describe("Retry", () => {
    it("retries the action when retry button is clicked after trigger error", async () => {
      mockPost
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce({
          job_id: "job-retry",
          status: "processing",
          estimated_duration_seconds: 60,
        });
      mockGet.mockResolvedValue({
        job_id: "job-retry",
        status: "processing",
        started_at: new Date().toISOString(),
        completed_at: null,
        progress_percent: 10,
        result_reference: null,
        error_message: null,
      });

      render(<VideoAlignmentActions {...defaultProps} />);

      // First attempt fails
      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByLabelText("Retry operation")).toBeInTheDocument();
      });

      // Retry succeeds
      await act(async () => {
        fireEvent.click(screen.getByLabelText("Retry operation"));
      });

      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledTimes(2);
      });
    });

    it("dismiss button clears error and shows action buttons again", async () => {
      mockPost.mockRejectedValueOnce(new TypeError("Failed to fetch"));

      render(<VideoAlignmentActions {...defaultProps} />);

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Extract Frames"));
      });

      await waitFor(() => {
        expect(screen.getByText("Dismiss")).toBeInTheDocument();
      });

      await act(async () => {
        fireEvent.click(screen.getByText("Dismiss"));
      });

      // Should show action buttons again
      expect(screen.getByLabelText("Extract Frames")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 6. Auto-render on completion
  // -------------------------------------------------------------------------

  describe("Auto-render on Completion", () => {
    it("fetches report and calls onReportReady when job completes", async () => {
      const onReportReady = vi.fn();
      const mockReport = {
        alignment_score: 0.85,
        matched_steps: [],
        missing_steps: [],
        extra_steps: [],
        order_mismatches: [],
        total_video_steps: 5,
        total_sop_steps: 5,
        generated_at: "2024-06-15T14:00:00Z",
        requires_review: false,
      };

      mockPost.mockResolvedValueOnce({
        job_id: "job-done",
        status: "processing",
        estimated_duration_seconds: 60,
      });
      // First call to polling returns completed
      mockGet.mockImplementation((url: string) => {
        if (url.includes("/jobs/")) {
          return Promise.resolve({
            job_id: "job-done",
            status: "completed",
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            progress_percent: 100,
            result_reference: null,
            error_message: null,
          });
        }
        if (url.includes("/report")) {
          return Promise.resolve(mockReport);
        }
        return Promise.reject(new Error("Unknown URL"));
      });

      render(
        <VideoAlignmentActions
          documentUuid="2024-00001"
          onReportReady={onReportReady}
        />
      );

      await act(async () => {
        fireEvent.click(screen.getByLabelText("Align with SOP"));
      });

      await waitFor(() => {
        expect(onReportReady).toHaveBeenCalledWith(mockReport);
      });
    });
  });
});
