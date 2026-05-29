import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Tests for VLLMStatusCard status display and restart flow.
 *
 * Validates: Requirements 4.1–4.5
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

import { useSystemConfigStore } from "../../../stores/useSystemConfigStore";
import { VLLMStatusCard } from "../../../components/admin/VLLMStatusCard";
import type { VLLMStatus } from "../../../types/systemConfig";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore(overrides: Partial<ReturnType<typeof useSystemConfigStore.getState>> = {}) {
  useSystemConfigStore.setState({
    vllmStatus: null,
    loading: {},
    errors: {},
    fetchVLLMStatus: vi.fn().mockResolvedValue(undefined),
    restartVLLM: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useSystemConfigStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VLLMStatusCard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  describe("Status display", () => {
    it("displays Running status when vLLM is running", () => {
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      expect(screen.getByText("Running")).toBeDefined();
      expect(screen.getByRole("status", { name: "vLLM service status" })).toBeDefined();
    });

    it("displays Restarting status with elapsed time", () => {
      resetStore({
        vllmStatus: { status: "restarting", elapsed_time: 15, error: null },
      });

      render(<VLLMStatusCard />);

      expect(screen.getByText("Restarting")).toBeDefined();
    });

    it("displays Error status with error message", () => {
      resetStore({
        vllmStatus: { status: "error", elapsed_time: null, error: "OOM killed" },
      });

      render(<VLLMStatusCard />);

      expect(screen.getByText("Error")).toBeDefined();
      expect(screen.getByText("OOM killed")).toBeDefined();
    });

    it("displays Unreachable status", () => {
      resetStore({
        vllmStatus: { status: "unreachable", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      expect(screen.getByText("Unreachable")).toBeDefined();
    });

    it("shows vLLM Service heading", () => {
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      expect(screen.getByText("vLLM Service")).toBeDefined();
    });
  });

  describe("Loading state", () => {
    it("shows loading skeleton when loading and no status", () => {
      resetStore({ vllmStatus: null, loading: { vllmStatus: true } });

      render(<VLLMStatusCard />);

      expect(screen.getByLabelText("Loading vLLM status")).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("shows error alert when fetch fails", () => {
      resetStore({
        vllmStatus: null,
        errors: { vllmStatus: "Connection refused" },
      });

      render(<VLLMStatusCard />);

      expect(screen.getByText("Failed to load vLLM status")).toBeDefined();
      expect(screen.getByText("Connection refused")).toBeDefined();
    });

    it("shows Retry button on fetch error", () => {
      resetStore({
        vllmStatus: null,
        errors: { vllmStatus: "Connection refused" },
      });

      render(<VLLMStatusCard />);

      expect(screen.getByText("Retry")).toBeDefined();
    });
  });

  describe("Restart flow", () => {
    it("renders Restart vLLM button", () => {
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      expect(
        screen.getByRole("button", { name: "Restart vLLM service" })
      ).toBeDefined();
    });

    it("disables restart button while restarting", () => {
      resetStore({
        vllmStatus: { status: "restarting", elapsed_time: 5, error: null },
      });

      render(<VLLMStatusCard />);

      const btn = screen.getByRole("button", { name: "Restart vLLM service" });
      expect(btn.hasAttribute("disabled")).toBe(true);
    });

    it("opens reason dialog when restart button is clicked", () => {
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      fireEvent.click(screen.getByRole("button", { name: "Restart vLLM service" }));

      expect(screen.getByText("Restart vLLM Service")).toBeDefined();
      expect(screen.getByLabelText("Change Reason")).toBeDefined();
    });

    it("shows 180 second timeout warning in dialog", () => {
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      fireEvent.click(screen.getByRole("button", { name: "Restart vLLM service" }));

      expect(
        screen.getByText(/up to 180 seconds/)
      ).toBeDefined();
    });

    it("disables Confirm Restart button when reason is empty", () => {
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      fireEvent.click(screen.getByRole("button", { name: "Restart vLLM service" }));

      const confirmBtn = screen.getByText("Confirm Restart").closest("button");
      expect(confirmBtn?.hasAttribute("disabled")).toBe(true);
    });

    it("calls restartVLLM with reason when confirmed", async () => {
      vi.useRealTimers(); // Use real timers for this async test
      const mockRestart = vi.fn().mockResolvedValue(undefined);
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
        restartVLLM: mockRestart,
      });

      render(<VLLMStatusCard />);

      fireEvent.click(screen.getByRole("button", { name: "Restart vLLM service" }));

      const reasonInput = screen.getByLabelText("Change Reason");
      fireEvent.change(reasonInput, { target: { value: "Applying new model config" } });
      fireEvent.click(screen.getByText("Confirm Restart"));

      await waitFor(() => {
        expect(mockRestart).toHaveBeenCalledWith("Applying new model config");
      });
    });

    it("closes dialog when Cancel is clicked", () => {
      resetStore({
        vllmStatus: { status: "running", elapsed_time: null, error: null },
      });

      render(<VLLMStatusCard />);

      fireEvent.click(screen.getByRole("button", { name: "Restart vLLM service" }));
      expect(screen.getByText("Restart vLLM Service")).toBeDefined();

      fireEvent.click(screen.getByText("Cancel"));

      expect(screen.queryByText("Restart vLLM Service")).toBeNull();
    });
  });
});
