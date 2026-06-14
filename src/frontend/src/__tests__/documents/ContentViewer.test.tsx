/**
 * Unit tests for ContentViewer component.
 *
 * Validates: Requirements 3.2, 3.3, 3.4
 *
 * - PDF: renders iframe with correct src URL (3.2)
 * - Markdown: fetches and renders HTML content (3.3)
 * - Unsupported: shows fallback message and download button (3.4)
 * - Loading: shows loading spinner during markdown fetch
 * - Error: shows error message with retry button when fetch fails
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ContentViewer } from "@/components/documents/ContentViewer";

// Mock apiClient.download
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    download: vi.fn(),
  },
}));

// Mock renderMarkdown
vi.mock("@/lib/renderMarkdown", () => ({
  renderMarkdown: vi.fn(),
}));

// Mock fileDownload
vi.mock("@/lib/fileDownload", () => ({
  triggerBrowserDownload: vi.fn(),
}));

import { apiClient } from "@/lib/apiClient";
import { renderMarkdown } from "@/lib/renderMarkdown";

describe("ContentViewer", () => {
  const defaultProps = {
    documentUuid: "test-doc-uuid-123",
    majorVersion: 2,
    minorVersion: 1,
    contentType: "application/pdf",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe("PDF content type", () => {
    it("renders an iframe with the correct content endpoint URL", () => {
      render(<ContentViewer {...defaultProps} contentType="application/pdf" />);

      const container = screen.getByTestId("content-viewer-pdf");
      expect(container).toBeDefined();

      const iframe = container.querySelector("iframe");
      expect(iframe).not.toBeNull();
      expect(iframe!.getAttribute("src")).toBe(
        "/api/documents/test-doc-uuid-123/versions/2/1/content"
      );
    });

    it("sets appropriate title and aria-label on the iframe", () => {
      render(<ContentViewer {...defaultProps} contentType="application/pdf" />);

      const container = screen.getByTestId("content-viewer-pdf");
      const iframe = container.querySelector("iframe");
      expect(iframe!.getAttribute("title")).toBe("PDF document preview");
      expect(iframe!.getAttribute("aria-label")).toBe("PDF document preview");
    });
  });

  describe("Markdown content type", () => {
    it("renders HTML content after fetching markdown", async () => {
      const markdownText = "# Hello World\n\nSome content.";
      const renderedHtml = '<h1 class="text-xl font-bold mt-4 mb-2">Hello World</h1>';

      const fakeBlob = new Blob([markdownText], { type: "text/markdown" });
      (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);
      (renderMarkdown as ReturnType<typeof vi.fn>).mockReturnValueOnce(renderedHtml);

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      // Wait for the markdown content to render
      const markdownContainer = await screen.findByTestId("content-viewer-markdown");
      expect(markdownContainer).toBeDefined();
      expect(markdownContainer.innerHTML).toBe(renderedHtml);
    });

    it("calls apiClient.download with the correct content URL", async () => {
      const fakeBlob = new Blob(["content"], { type: "text/markdown" });
      (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);
      (renderMarkdown as ReturnType<typeof vi.fn>).mockReturnValueOnce("<p>content</p>");

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      await waitFor(() => {
        expect(apiClient.download).toHaveBeenCalledWith(
          "/api/documents/test-doc-uuid-123/versions/2/1/content"
        );
      });
    });

    it("passes fetched text to renderMarkdown", async () => {
      const markdownText = "## Test heading";
      const fakeBlob = new Blob([markdownText], { type: "text/markdown" });
      (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);
      (renderMarkdown as ReturnType<typeof vi.fn>).mockReturnValueOnce("<h2>Test heading</h2>");

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      await waitFor(() => {
        expect(renderMarkdown).toHaveBeenCalledWith(markdownText);
      });
    });

    it("also handles text/x-markdown content type", async () => {
      const fakeBlob = new Blob(["content"], { type: "text/x-markdown" });
      (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);
      (renderMarkdown as ReturnType<typeof vi.fn>).mockReturnValueOnce("<p>content</p>");

      render(<ContentViewer {...defaultProps} contentType="text/x-markdown" />);

      const markdownContainer = await screen.findByTestId("content-viewer-markdown");
      expect(markdownContainer).toBeDefined();
    });
  });

  describe("Unsupported content type", () => {
    it("shows fallback message for unsupported types", () => {
      render(
        <ContentViewer
          {...defaultProps}
          contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        />
      );

      const container = screen.getByTestId("content-viewer-unsupported");
      expect(container).toBeDefined();
      expect(container.textContent).toContain("cannot be previewed");
    });

    it("displays the content type in the fallback message", () => {
      render(
        <ContentViewer {...defaultProps} contentType="application/msword" />
      );

      const container = screen.getByTestId("content-viewer-unsupported");
      expect(container.textContent).toContain("application/msword");
    });

    it("renders a download button in the fallback view", () => {
      render(
        <ContentViewer {...defaultProps} contentType="application/msword" />
      );

      const container = screen.getByTestId("content-viewer-unsupported");
      const downloadButton = container.querySelector("button");
      expect(downloadButton).not.toBeNull();
      expect(downloadButton!.textContent).toContain("Download");
    });
  });

  describe("Loading state", () => {
    it("shows loading spinner during markdown fetch", () => {
      // Make the download promise never resolve to keep loading state
      (apiClient.download as ReturnType<typeof vi.fn>).mockReturnValueOnce(
        new Promise(() => {})
      );

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      const loadingContainer = screen.getByTestId("content-viewer-loading");
      expect(loadingContainer).toBeDefined();
      expect(loadingContainer.textContent).toContain("Loading");
    });

    it("has an accessible role and label during loading", () => {
      (apiClient.download as ReturnType<typeof vi.fn>).mockReturnValueOnce(
        new Promise(() => {})
      );

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      const loadingContainer = screen.getByTestId("content-viewer-loading");
      expect(loadingContainer.getAttribute("role")).toBe("status");
      expect(loadingContainer.getAttribute("aria-label")).toBe(
        "Loading document content"
      );
    });
  });

  describe("Error state", () => {
    it("shows error message when fetch fails", async () => {
      (apiClient.download as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error("Network error")
      );

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      const errorContainer = await screen.findByTestId("content-viewer-error");
      expect(errorContainer).toBeDefined();
      expect(errorContainer.textContent).toContain("Network error");
    });

    it("shows a retry button on error", async () => {
      (apiClient.download as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error("Failed to load content.")
      );

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      const errorContainer = await screen.findByTestId("content-viewer-error");
      const retryButton = errorContainer.querySelector("button");
      expect(retryButton).not.toBeNull();
      expect(retryButton!.textContent).toContain("Retry");
    });

    it("retries fetch when retry button is clicked", async () => {
      const user = userEvent.setup();

      // First call fails
      (apiClient.download as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error("Network error")
      );

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      const errorContainer = await screen.findByTestId("content-viewer-error");
      const retryButton = errorContainer.querySelector("button")!;

      // Second call succeeds
      const fakeBlob = new Blob(["# Recovered"], { type: "text/markdown" });
      (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);
      (renderMarkdown as ReturnType<typeof vi.fn>).mockReturnValueOnce("<h1>Recovered</h1>");

      await user.click(retryButton);

      const markdownContainer = await screen.findByTestId("content-viewer-markdown");
      expect(markdownContainer.innerHTML).toBe("<h1>Recovered</h1>");
      expect(apiClient.download).toHaveBeenCalledTimes(2);
    });

    it("has an accessible alert role on error", async () => {
      (apiClient.download as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error("Something went wrong")
      );

      render(<ContentViewer {...defaultProps} contentType="text/markdown" />);

      const errorContainer = await screen.findByTestId("content-viewer-error");
      expect(errorContainer.getAttribute("role")).toBe("alert");
    });
  });
});
