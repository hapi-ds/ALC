import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import React from "react";

// Mock the document store
vi.mock("@/stores/documentStore", () => ({
  useDocumentStore: vi.fn(),
}));

// Mock createPortal to render children inline instead of into document.body
vi.mock("react-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-dom")>();
  return {
    ...actual,
    createPortal: (children: React.ReactNode) => children,
  };
});

import { VersionUploadDialog } from "@/components/documents/VersionUploadDialog";
import { useDocumentStore } from "@/stores/documentStore";

const mockCreateVersion = vi.fn();

function setupStoreMock(overrides: Partial<ReturnType<typeof useDocumentStore>> = {}) {
  vi.mocked(useDocumentStore).mockReturnValue({
    createVersion: mockCreateVersion,
    isLoading: false,
    ...overrides,
  } as unknown as ReturnType<typeof useDocumentStore>);
}

/**
 * Helper to create a mock File with a specific size.
 */
function createMockFile(name: string, sizeInBytes: number): File {
  const buffer = new ArrayBuffer(sizeInBytes);
  const blob = new Blob([buffer], { type: "application/octet-stream" });
  return new File([blob], name, { type: "application/octet-stream" });
}

describe("VersionUploadDialog validation", () => {
  beforeEach(() => {
    setupStoreMock();
    mockCreateVersion.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });


  describe("File size validation", () => {
    it("shows error when file exceeds 500 MB", async () => {
      render(
        <VersionUploadDialog open={true} onOpenChange={vi.fn()} documentUuid="test-uuid" />
      );

      // Create a file > 500 MB (524,288,001 bytes)
      const largeFile = createMockFile("large.pdf", 524_288_001);

      // Simulate file selection via the hidden input
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [largeFile] } });

      // Fill other required fields to isolate file validation
      const select = screen.getByLabelText(/version type/i);
      fireEvent.change(select, { target: { value: "minor" } });

      const textarea = screen.getByPlaceholderText(/describe what changed/i);
      fireEvent.change(textarea, { target: { value: "Some change reason" } });

      // Submit the form
      const submitButton = screen.getByRole("button", { name: /upload version/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("File must not exceed 500 MB.")).toBeInTheDocument();
      });
    });

    it("shows error when file is 0 bytes (empty)", async () => {
      render(
        <VersionUploadDialog open={true} onOpenChange={vi.fn()} documentUuid="test-uuid" />
      );

      // Create a 0-byte file
      const emptyFile = createMockFile("empty.pdf", 0);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [emptyFile] } });

      // Fill other required fields
      const select = screen.getByLabelText(/version type/i);
      fireEvent.change(select, { target: { value: "major" } });

      const textarea = screen.getByPlaceholderText(/describe what changed/i);
      fireEvent.change(textarea, { target: { value: "Some change reason" } });

      // Submit
      const submitButton = screen.getByRole("button", { name: /upload version/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("File must not be empty.")).toBeInTheDocument();
      });
    });
  });

  describe("Change reason validation", () => {
    it("shows error when change reason is empty", async () => {
      render(
        <VersionUploadDialog open={true} onOpenChange={vi.fn()} documentUuid="test-uuid" />
      );

      // Select a valid file
      const validFile = createMockFile("doc.pdf", 1024);
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [validFile] } });

      // Select version type
      const select = screen.getByLabelText(/version type/i);
      fireEvent.change(select, { target: { value: "minor" } });

      // Leave change reason empty and submit
      const submitButton = screen.getByRole("button", { name: /upload version/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Change reason is required.")).toBeInTheDocument();
      });
    });

    it("shows error when change reason exceeds 2000 characters", async () => {
      render(
        <VersionUploadDialog open={true} onOpenChange={vi.fn()} documentUuid="test-uuid" />
      );

      // Select a valid file
      const validFile = createMockFile("doc.pdf", 1024);
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [validFile] } });

      // Select version type
      const select = screen.getByLabelText(/version type/i);
      fireEvent.change(select, { target: { value: "major" } });

      // Enter a change reason > 2000 characters
      const longReason = "a".repeat(2001);
      const textarea = screen.getByPlaceholderText(/describe what changed/i);
      fireEvent.change(textarea, { target: { value: longReason } });

      // Submit
      const submitButton = screen.getByRole("button", { name: /upload version/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText("Change reason must not exceed 2000 characters.")
        ).toBeInTheDocument();
      });
    });
  });

  describe("File size display formatting", () => {
    it("displays file size in KB for files under 1 MB", async () => {
      render(
        <VersionUploadDialog open={true} onOpenChange={vi.fn()} documentUuid="test-uuid" />
      );

      // 512 KB = 524,288 bytes (under 1 MB threshold of 1,048,576)
      const smallFile = createMockFile("small.pdf", 524_288);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [smallFile] } });

      // 524288 / 1024 = 512 KB
      await waitFor(() => {
        expect(screen.getByText("(512 KB)")).toBeInTheDocument();
      });
    });

    it("displays file size in MB for files 1 MB and above", async () => {
      render(
        <VersionUploadDialog open={true} onOpenChange={vi.fn()} documentUuid="test-uuid" />
      );

      // 2.5 MB = 2,621,440 bytes (>= 1,048,576 threshold)
      const largeFile = createMockFile("large.pdf", 2_621_440);

      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [largeFile] } });

      // 2621440 / 1048576 = 2.5 MB
      await waitFor(() => {
        expect(screen.getByText("(2.5 MB)")).toBeInTheDocument();
      });
    });
  });
});
