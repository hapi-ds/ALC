/**
 * Unit tests for DownloadButton component.
 *
 * Validates: Requirements 4.1, 4.4
 *
 * - Click triggers apiClient.download with correct URL then triggerBrowserDownload (4.1)
 * - Shows loading indicator while download is in progress (4.4)
 * - On error, shows toast.error with error message (4.4)
 * - Button is disabled while downloading (4.4)
 * - Icon variant renders an icon-only button (4.1)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, act, cleanup } from "@testing-library/react";
import { DownloadButton } from "@/components/documents/DownloadButton";

// Mock apiClient
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    download: vi.fn(),
  },
}));

// Mock triggerBrowserDownload
vi.mock("@/lib/fileDownload", () => ({
  triggerBrowserDownload: vi.fn(),
}));

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
  },
}));

import { apiClient } from "@/lib/apiClient";
import { triggerBrowserDownload } from "@/lib/fileDownload";
import { toast } from "sonner";

describe("DownloadButton", () => {
  const defaultProps = {
    documentUuid: "abc-123",
    version: { major_version: 2, minor_version: 1 },
    documentTitle: "Test Document.pdf",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("triggers apiClient.download with the correct URL and then calls triggerBrowserDownload", async () => {
    const fakeBlob = new Blob(["pdf bytes"], { type: "application/pdf" });
    (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);

    render(<DownloadButton {...defaultProps} />);

    const button = screen.getByRole("button", { name: /download test document\.pdf/i });
    await act(async () => {
      fireEvent.click(button);
    });

    await waitFor(() => {
      expect(apiClient.download).toHaveBeenCalledWith(
        "/api/documents/abc-123/versions/2/1/download"
      );
    });

    expect(triggerBrowserDownload).toHaveBeenCalledWith(fakeBlob, "Test Document.pdf");
  });

  it("shows loading indicator while download is in progress", async () => {
    let resolveDownload: (value: Blob) => void;
    const downloadPromise = new Promise<Blob>((resolve) => {
      resolveDownload = resolve;
    });
    (apiClient.download as ReturnType<typeof vi.fn>).mockReturnValueOnce(downloadPromise);

    render(<DownloadButton {...defaultProps} />);

    const button = screen.getByRole("button", { name: /download test document\.pdf/i });

    await act(async () => {
      fireEvent.click(button);
    });

    // While downloading, the button should show "Downloading…" text and aria-label
    expect(screen.getByRole("button", { name: "Downloading…" })).toBeInTheDocument();
    expect(screen.getByText("Downloading…")).toBeInTheDocument();

    // Resolve the download
    await act(async () => {
      resolveDownload!(new Blob(["data"]));
    });

    // After downloading, should be back to normal
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /download test document\.pdf/i })).toBeInTheDocument();
    });
  });

  it("shows toast.error with error message when download fails", async () => {
    const error = new Error("Network timeout");
    (apiClient.download as ReturnType<typeof vi.fn>).mockRejectedValueOnce(error);

    render(<DownloadButton {...defaultProps} />);

    const button = screen.getByRole("button", { name: /download test document\.pdf/i });
    await act(async () => {
      fireEvent.click(button);
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Download failed", {
        description: "Network timeout",
      });
    });
  });

  it("button is disabled while downloading", async () => {
    let resolveDownload: (value: Blob) => void;
    const downloadPromise = new Promise<Blob>((resolve) => {
      resolveDownload = resolve;
    });
    (apiClient.download as ReturnType<typeof vi.fn>).mockReturnValueOnce(downloadPromise);

    render(<DownloadButton {...defaultProps} />);

    const button = screen.getByRole("button", { name: /download test document\.pdf/i });

    await act(async () => {
      fireEvent.click(button);
    });

    // Button should be disabled while downloading
    const downloadingButton = screen.getByRole("button", { name: "Downloading…" });
    expect(downloadingButton).toBeDisabled();

    // Resolve the download
    await act(async () => {
      resolveDownload!(new Blob(["data"]));
    });

    // After completing, button should be enabled again
    await waitFor(() => {
      const finalButton = screen.getByRole("button", { name: /download test document\.pdf/i });
      expect(finalButton).not.toBeDisabled();
    });
  });

  it("icon variant renders an icon-only button without text label", async () => {
    const fakeBlob = new Blob(["data"], { type: "application/pdf" });
    (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);

    render(<DownloadButton {...defaultProps} variant="icon" />);

    const button = screen.getByRole("button", { name: /download test document\.pdf/i });
    expect(button).toBeInTheDocument();

    // Icon variant should NOT have visible text "Download"
    expect(screen.queryByText("Download")).not.toBeInTheDocument();

    // Still functional
    await act(async () => {
      fireEvent.click(button);
    });

    await waitFor(() => {
      expect(apiClient.download).toHaveBeenCalledWith(
        "/api/documents/abc-123/versions/2/1/download"
      );
    });
  });

  it("shows toast.error when version is not provided", async () => {
    render(
      <DownloadButton
        documentUuid="abc-123"
        documentTitle="Test Document.pdf"
      />
    );

    const button = screen.getByRole("button", { name: /download test document\.pdf/i });
    await act(async () => {
      fireEvent.click(button);
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Download unavailable", {
        description: "No version information available for this document.",
      });
    });

    // Should not have called apiClient.download
    expect(apiClient.download).not.toHaveBeenCalled();
  });
});
