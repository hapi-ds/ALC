import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { VersionDetailView } from "@/components/documents/VersionDetailView";
import type { DocumentVersion } from "@/types/document";

/**
 * Helper to create a mock DocumentVersion object.
 */
function createMockVersion(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    id: 1,
    major_version: 2,
    minor_version: 3,
    storage_key: "documents/abc123/v2.3/report.pdf",
    file_hash: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
    uploaded_by: 42,
    uploaded_at: "2024-06-15T10:30:00Z",
    change_reason: "Updated compliance section with new regulations",
    ...overrides,
  };
}

describe("VersionDetailView", () => {
  const mockOnRetry = vi.fn();
  const mockOnDownload = vi.fn();
  const mockOnClose = vi.fn();

  beforeEach(() => {
    mockOnRetry.mockReset();
    mockOnDownload.mockReset();
    mockOnClose.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe("Loading state", () => {
    it("shows spinner and loading text when isLoading is true", () => {
      render(
        <VersionDetailView
          version={null}
          isLoading={true}
          error={null}
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      const loadingContainer = screen.getByLabelText("Loading version details");
      expect(loadingContainer).toBeInTheDocument();
      expect(screen.getByText("Loading version details…")).toBeInTheDocument();
    });
  });

  describe("Error state", () => {
    it("shows error message and retry button", () => {
      render(
        <VersionDetailView
          version={null}
          isLoading={false}
          error="Version not found"
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      expect(screen.getByText("Version not found")).toBeInTheDocument();

      const retryButton = screen.getByRole("button", { name: /retry/i });
      expect(retryButton).toBeInTheDocument();

      fireEvent.click(retryButton);
      expect(mockOnRetry).toHaveBeenCalledTimes(1);
    });
  });

  describe("Success state", () => {
    it("displays all metadata fields", () => {
      const version = createMockVersion();

      render(
        <VersionDetailView
          version={version}
          isLoading={false}
          error={null}
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      // Version number
      expect(screen.getByText("2.3")).toBeInTheDocument();

      // Storage key
      expect(screen.getByText("documents/abc123/v2.3/report.pdf")).toBeInTheDocument();

      // Full file hash (monospace)
      expect(
        screen.getByText(
          "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
        )
      ).toBeInTheDocument();

      // Uploaded by
      expect(screen.getByText("42")).toBeInTheDocument();

      // Uploaded at (locale formatted)
      const formattedDate = new Date("2024-06-15T10:30:00Z").toLocaleString();
      expect(screen.getByText(formattedDate)).toBeInTheDocument();

      // Change reason
      expect(
        screen.getByText("Updated compliance section with new regulations")
      ).toBeInTheDocument();
    });
  });

  describe("Copy button behavior", () => {
    it("calls navigator.clipboard.writeText with the file hash when clicked", async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      const version = createMockVersion();

      render(
        <VersionDetailView
          version={version}
          isLoading={false}
          error={null}
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      const copyButton = screen.getByRole("button", { name: /copy file hash/i });
      fireEvent.click(copyButton);

      await waitFor(() => {
        expect(writeTextMock).toHaveBeenCalledWith(
          "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
        );
      });
    });

    it("shows confirmation indicator after successful copy", async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      const version = createMockVersion();

      render(
        <VersionDetailView
          version={version}
          isLoading={false}
          error={null}
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      const copyButton = screen.getByRole("button", { name: /copy file hash/i });
      fireEvent.click(copyButton);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /copied/i })).toBeInTheDocument();
      });
    });
  });

  describe("Null change_reason", () => {
    it('shows "No reason provided" placeholder text when change_reason is null', () => {
      const version = createMockVersion({ change_reason: null });

      render(
        <VersionDetailView
          version={version}
          isLoading={false}
          error={null}
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      expect(screen.getByText("No reason provided")).toBeInTheDocument();
    });
  });

  describe("Close button", () => {
    it("calls onClose when clicked", () => {
      const version = createMockVersion();

      render(
        <VersionDetailView
          version={version}
          isLoading={false}
          error={null}
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      const closeButton = screen.getByRole("button", { name: /close version detail/i });
      fireEvent.click(closeButton);

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("Download button", () => {
    it("calls onDownload with the version when clicked", () => {
      const version = createMockVersion();

      render(
        <VersionDetailView
          version={version}
          isLoading={false}
          error={null}
          onRetry={mockOnRetry}
          onDownload={mockOnDownload}
          onClose={mockOnClose}
        />
      );

      const downloadButton = screen.getByRole("button", { name: /download/i });
      fireEvent.click(downloadButton);

      expect(mockOnDownload).toHaveBeenCalledTimes(1);
      expect(mockOnDownload).toHaveBeenCalledWith(version);
    });
  });
});
