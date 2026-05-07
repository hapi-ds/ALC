import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import React from "react";
import type { DocumentResponse, DocumentVersion } from "@/types/document";

// Mock createPortal to render children inline instead of into document.body
vi.mock("react-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-dom")>();
  return {
    ...actual,
    createPortal: (children: React.ReactNode) => children,
  };
});

// Mock the document store with a functional mock that tracks state changes
const mockFetchVersion = vi.fn();
const mockDownloadVersion = vi.fn();
const mockSetComparisonOpen = vi.fn();
const mockClearSelectedVersion = vi.fn();

let storeState = {
  selectedVersion: null as DocumentVersion | null,
  isVersionLoading: false,
  versionError: null as string | null,
  downloadingVersionId: null as number | null,
  comparisonOpen: false,
  fetchVersion: mockFetchVersion,
  downloadVersion: mockDownloadVersion,
  setComparisonOpen: mockSetComparisonOpen,
  clearSelectedVersion: mockClearSelectedVersion,
};

vi.mock("@/stores/documentStore", () => ({
  useDocumentStore: vi.fn((selector: unknown) => {
    if (typeof selector === "function") {
      return (selector as (s: typeof storeState) => unknown)(storeState);
    }
    return storeState;
  }),
}));

import { DocumentDetail } from "@/components/documents/DocumentDetail";

/**
 * Helper to create a mock DocumentVersion.
 */
function createMockVersion(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    id: 1,
    major_version: 1,
    minor_version: 0,
    storage_key: "storage/doc/v1.0/report.pdf",
    file_hash: "abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
    uploaded_by: 1,
    uploaded_at: "2024-01-15T10:00:00Z",
    change_reason: "Initial upload",
    ...overrides,
  };
}

/**
 * Helper to create a full DocumentResponse mock with multiple versions.
 */
function createMockDocument(overrides: Partial<DocumentResponse> = {}): DocumentResponse {
  return {
    id: 1,
    document_uuid: "doc-uuid-123",
    title: "Test Protocol Document",
    folder_path: "/protocols/phase-1",
    document_type: "SOP",
    current_status: "approved",
    created_by: 1,
    created_at: "2024-01-01T08:00:00Z",
    tags: [
      { id: 1, tag: "compliance" },
      { id: 2, tag: "phase-1" },
    ],
    versions: [
      createMockVersion({
        id: 1,
        major_version: 1,
        minor_version: 0,
        uploaded_at: "2024-01-15T10:00:00Z",
        change_reason: "Initial upload of protocol document",
        file_hash: "hash_v1_0_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        uploaded_by: 1,
        storage_key: "storage/doc/v1.0/report.pdf",
      }),
      createMockVersion({
        id: 2,
        major_version: 1,
        minor_version: 1,
        uploaded_at: "2024-02-10T14:30:00Z",
        change_reason: "Minor corrections to section 3",
        file_hash: "hash_v1_1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        uploaded_by: 2,
        storage_key: "storage/doc/v1.1/report.pdf",
      }),
      createMockVersion({
        id: 3,
        major_version: 2,
        minor_version: 0,
        uploaded_at: "2024-03-20T09:15:00Z",
        change_reason: "Major revision incorporating regulatory feedback",
        file_hash: "hash_v2_0_cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        uploaded_by: 1,
        storage_key: "storage/doc/v2.0/report.pdf",
      }),
    ],
    ...overrides,
  };
}

describe("Integration: Full Versioning Flow", () => {
  const mockOnNewVersion = vi.fn();
  const mockOnBack = vi.fn();

  beforeEach(() => {
    // Reset store state to defaults
    storeState = {
      selectedVersion: null,
      isVersionLoading: false,
      versionError: null,
      downloadingVersionId: null,
      comparisonOpen: false,
      fetchVersion: mockFetchVersion,
      downloadVersion: mockDownloadVersion,
      setComparisonOpen: mockSetComparisonOpen,
      clearSelectedVersion: mockClearSelectedVersion,
    };

    mockFetchVersion.mockReset();
    mockDownloadVersion.mockReset();
    mockSetComparisonOpen.mockReset();
    mockClearSelectedVersion.mockReset();
    mockOnNewVersion.mockReset();
    mockOnBack.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe("View history → click version → see detail", () => {
    it("renders VersionHistoryPanel with all versions and calls fetchVersion on click", () => {
      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      // Verify all 3 version entries are rendered in the history panel
      const versionEntries = screen.getAllByRole("button", { name: /^Version \d+\.\d+$/ });
      expect(versionEntries).toHaveLength(3);

      // Click on version 1.1 entry
      const v11Button = screen.getByRole("button", { name: "Version 1.1" });
      fireEvent.click(v11Button);

      // Verify fetchVersion is called with correct params
      expect(mockFetchVersion).toHaveBeenCalledTimes(1);
      expect(mockFetchVersion).toHaveBeenCalledWith("doc-uuid-123", 1, 1);
    });

    it("shows VersionDetailView when selectedVersion is set in store", () => {
      const selectedVersion = createMockVersion({
        id: 2,
        major_version: 1,
        minor_version: 1,
        uploaded_at: "2024-02-10T14:30:00Z",
        change_reason: "Minor corrections to section 3",
        file_hash: "hash_v1_1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        uploaded_by: 2,
        storage_key: "storage/doc/v1.1/report.pdf",
      });

      // Set store state to have a selected version
      storeState.selectedVersion = selectedVersion;

      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      // Verify VersionDetailView renders with version metadata
      // The storage key only appears in the detail view, not in the history panel
      expect(screen.getByText("storage/doc/v1.1/report.pdf")).toBeInTheDocument();
      // The close button is unique to VersionDetailView
      expect(screen.getByRole("button", { name: /close version detail/i })).toBeInTheDocument();
      // Change reason appears in both history and detail; use getAllByText to confirm it's present
      const changeReasonElements = screen.getAllByText("Minor corrections to section 3");
      expect(changeReasonElements.length).toBeGreaterThanOrEqual(2);
    });
  });

  describe("Open comparison → verify default selection", () => {
    it("calls setComparisonOpen when Compare Versions button is clicked", () => {
      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      const compareButton = screen.getByRole("button", { name: /compare versions/i });
      fireEvent.click(compareButton);

      expect(mockSetComparisonOpen).toHaveBeenCalledTimes(1);
      expect(mockSetComparisonOpen).toHaveBeenCalledWith(true);
    });

    it("renders VersionComparisonView dialog when comparisonOpen is true", () => {
      storeState.comparisonOpen = true;

      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      // The comparison dialog should be visible
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      // Use the heading element specifically to avoid conflict with the button text
      const dialogTitle = screen.getByRole("heading", { name: /compare versions/i });
      expect(dialogTitle).toBeInTheDocument();

      // Verify default selection: left = v1.1 (second-most-recent), right = v2.0 (most-recent)
      const leftSelect = screen.getByLabelText(/left version/i) as HTMLSelectElement;
      const rightSelect = screen.getByLabelText(/right version/i) as HTMLSelectElement;

      expect(leftSelect.value).toBe("2"); // v1.1, id=2
      expect(rightSelect.value).toBe("3"); // v2.0, id=3
    });
  });

  describe("Download version", () => {
    it("calls downloadVersion with correct params when download button is clicked", () => {
      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      // Click the download button for version 2.0 (the first entry since sorted descending)
      const downloadButtons = screen.getAllByRole("button", { name: /^Download version \d+\.\d+$/ });
      // Sorted descending: v2.0, v1.1, v1.0 — first download button is for v2.0
      fireEvent.click(downloadButtons[0]);

      expect(mockDownloadVersion).toHaveBeenCalledTimes(1);
      expect(mockDownloadVersion).toHaveBeenCalledWith(
        "doc-uuid-123",
        expect.objectContaining({
          id: 3,
          major_version: 2,
          minor_version: 0,
        }),
        "Test Protocol Document"
      );
    });
  });

  describe("Version detail close", () => {
    it("calls clearSelectedVersion when close button is clicked in VersionDetailView", () => {
      const selectedVersion = createMockVersion({
        id: 2,
        major_version: 1,
        minor_version: 1,
        uploaded_at: "2024-02-10T14:30:00Z",
        change_reason: "Minor corrections to section 3",
        file_hash: "hash_v1_1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        uploaded_by: 2,
        storage_key: "storage/doc/v1.1/report.pdf",
      });

      storeState.selectedVersion = selectedVersion;

      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      // Verify VersionDetailView is rendered
      expect(screen.getByRole("button", { name: /close version detail/i })).toBeInTheDocument();

      // Click close button
      const closeButton = screen.getByRole("button", { name: /close version detail/i });
      fireEvent.click(closeButton);

      expect(mockClearSelectedVersion).toHaveBeenCalledTimes(1);
    });

    it("shows loading state in VersionDetailView when isVersionLoading is true", () => {
      storeState.isVersionLoading = true;

      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      expect(screen.getByLabelText("Loading version details")).toBeInTheDocument();
    });

    it("shows error state with retry in VersionDetailView when versionError is set", () => {
      storeState.versionError = "Version not found";

      const doc = createMockDocument();

      render(
        <DocumentDetail
          document={doc}
          onNewVersion={mockOnNewVersion}
          onBack={mockOnBack}
        />
      );

      expect(screen.getByText("Version not found")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });
});
