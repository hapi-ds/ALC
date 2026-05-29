import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Tests for AIHardwareForm rendering and form submission.
 *
 * Validates: Requirements 2.1–2.7, 3.1–3.6
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
import { AIHardwareForm } from "../../../components/admin/AIHardwareForm";
import type { AIHardwareConfig } from "../../../types/systemConfig";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockAIHardware: AIHardwareConfig = {
  model_chat_name: "gemma-4-e4b-it",
  model_chat_path: "/models/gemma-4-e4b-it",
  model_chat_max_gpu_memory_gb: 24,
  model_embedding_name: "bge-large-en-v1.5",
  model_embedding_path: "/models/bge-large-en-v1.5",
  model_embedding_dimension: 1024,
  model_ocr_name: "gemma-4-e4b-it",
  model_ocr_path: "/models/gemma-4-e4b-it",
  inference_mode: "gpu",
  gpu_device_id: 0,
  vllm_chat_url: "http://vllm-chat:8000",
  vllm_embedding_url: "http://vllm-embed:8001",
  vllm_chat_status: "reachable",
  vllm_embedding_status: "reachable",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore(overrides: Partial<ReturnType<typeof useSystemConfigStore.getState>> = {}) {
  useSystemConfigStore.setState({
    aiHardware: null,
    vllmStatus: null,
    loading: {},
    errors: {},
    fetchAIHardware: vi.fn().mockResolvedValue(undefined),
    updateAIHardware: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useSystemConfigStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AIHardwareForm", () => {
  beforeEach(() => {
    resetStore({ aiHardware: mockAIHardware });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders the form with correct aria-label", () => {
      render(<AIHardwareForm />);

      expect(
        screen.getByRole("form", { name: "AI hardware configuration form" })
      ).toBeDefined();
    });

    it("displays chat model fields", () => {
      render(<AIHardwareForm />);

      // Multiple "Model Name" labels exist; use getAllByLabelText
      const modelNames = screen.getAllByLabelText("Model Name");
      expect(modelNames.length).toBeGreaterThanOrEqual(2);
      expect(screen.getByLabelText("Max GPU Memory (GB)")).toBeDefined();
    });

    it("displays embedding model fields", () => {
      render(<AIHardwareForm />);

      expect(screen.getByLabelText("Vector Dimension")).toBeDefined();
    });

    it("displays inference mode selector", () => {
      render(<AIHardwareForm />);

      expect(screen.getByLabelText("Inference Mode")).toBeDefined();
    });

    it("displays GPU device ID field", () => {
      render(<AIHardwareForm />);

      expect(screen.getByLabelText("GPU Device ID")).toBeDefined();
    });

    it("displays vLLM connection URLs", () => {
      render(<AIHardwareForm />);

      expect(screen.getByText("http://vllm-chat:8000")).toBeDefined();
      expect(screen.getByText("http://vllm-embed:8001")).toBeDefined();
    });

    it("displays vLLM chat status as reachable", () => {
      render(<AIHardwareForm />);

      const reachableTexts = screen.getAllByText("Reachable");
      expect(reachableTexts.length).toBe(2);
    });

    it("displays vLLM status as unreachable when service is down", () => {
      resetStore({
        aiHardware: {
          ...mockAIHardware,
          vllm_chat_status: "unreachable",
          vllm_embedding_status: "unreachable",
        },
      });

      render(<AIHardwareForm />);

      const unreachableTexts = screen.getAllByText("Unreachable");
      expect(unreachableTexts.length).toBe(2);
    });

    it("renders Save Changes button", () => {
      render(<AIHardwareForm />);

      expect(screen.getByText("Save Changes")).toBeDefined();
    });

    it("renders fieldset legends for each section", () => {
      render(<AIHardwareForm />);

      expect(screen.getByText("Chat Model")).toBeDefined();
      expect(screen.getByText("Embedding Model")).toBeDefined();
      expect(screen.getByText("OCR / Vision Model")).toBeDefined();
      expect(screen.getByText("Inference Settings")).toBeDefined();
      expect(screen.getByText("vLLM Connection")).toBeDefined();
    });
  });

  describe("Loading state", () => {
    it("shows loading skeleton when loading and no data", () => {
      resetStore({ aiHardware: null, loading: { aiHardware: true } });

      render(<AIHardwareForm />);

      expect(
        screen.getByLabelText("Loading AI hardware configuration")
      ).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("shows error alert when fetch fails", () => {
      resetStore({
        aiHardware: null,
        errors: { aiHardware: "Network error: connection refused" },
      });

      render(<AIHardwareForm />);

      expect(
        screen.getByText("Failed to load AI hardware configuration")
      ).toBeDefined();
      expect(
        screen.getByText("Network error: connection refused")
      ).toBeDefined();
    });

    it("shows Retry button on error", () => {
      resetStore({
        aiHardware: null,
        errors: { aiHardware: "Network error" },
      });

      render(<AIHardwareForm />);

      expect(screen.getByText("Retry")).toBeDefined();
    });

    it("calls fetchAIHardware when Retry is clicked", () => {
      const mockFetch = vi.fn().mockResolvedValue(undefined);
      resetStore({
        aiHardware: null,
        errors: { aiHardware: "Network error" },
        fetchAIHardware: mockFetch,
      });

      render(<AIHardwareForm />);
      fireEvent.click(screen.getByText("Retry"));

      expect(mockFetch).toHaveBeenCalled();
    });
  });

  describe("Form submission", () => {
    it("opens reason dialog when form is submitted", async () => {
      render(<AIHardwareForm />);

      // Change a field to make form dirty
      const gpuMemoryInput = screen.getByLabelText("Max GPU Memory (GB)");
      fireEvent.change(gpuMemoryInput, { target: { value: "32" } });

      // Submit the form
      fireEvent.click(screen.getByText("Save Changes"));

      await waitFor(() => {
        expect(screen.getByText("Reason for Change")).toBeDefined();
      });
    });

    it("shows character counter in reason dialog", async () => {
      render(<AIHardwareForm />);

      const gpuMemoryInput = screen.getByLabelText("Max GPU Memory (GB)");
      fireEvent.change(gpuMemoryInput, { target: { value: "32" } });
      fireEvent.click(screen.getByText("Save Changes"));

      await waitFor(() => {
        expect(screen.getByText("0/500 characters")).toBeDefined();
      });
    });

    it("disables Confirm button when reason is empty", async () => {
      render(<AIHardwareForm />);

      const gpuMemoryInput = screen.getByLabelText("Max GPU Memory (GB)");
      fireEvent.change(gpuMemoryInput, { target: { value: "32" } });
      fireEvent.click(screen.getByText("Save Changes"));

      await waitFor(() => {
        const confirmBtn = screen.getByText("Confirm").closest("button");
        expect(confirmBtn?.hasAttribute("disabled")).toBe(true);
      });
    });

    it("shows restart required banner after successful update", async () => {
      const mockUpdate = vi.fn().mockResolvedValue(undefined);
      resetStore({
        aiHardware: mockAIHardware,
        updateAIHardware: mockUpdate,
      });

      render(<AIHardwareForm />);

      // Make form dirty and submit
      const gpuMemoryInput = screen.getByLabelText("Max GPU Memory (GB)");
      fireEvent.change(gpuMemoryInput, { target: { value: "32" } });
      fireEvent.click(screen.getByText("Save Changes"));

      // Fill reason and confirm
      await waitFor(() => {
        expect(screen.getByLabelText("Change Reason")).toBeDefined();
      });

      const reasonInput = screen.getByLabelText("Change Reason");
      fireEvent.change(reasonInput, { target: { value: "Upgrading GPU memory" } });
      fireEvent.click(screen.getByText("Confirm"));

      await waitFor(() => {
        expect(
          screen.getByText(
            "Configuration updated. A vLLM service restart is required for changes to take effect."
          )
        ).toBeDefined();
      });
    });
  });
});
