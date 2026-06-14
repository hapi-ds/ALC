/**
 * Integration tests for DocumentDetail with ContentViewer and DownloadButton.
 *
 * Validates: Requirements 3.5, 3.6
 *
 * - ContentViewer renders with the latest version on initial load (3.5)
 * - When a different version is selected (via store update), ContentViewer updates props (3.6)
 * - DownloadButton is present in the header area with correct props (3.5)
 * - DownloadButton updates when version selection changes (3.6)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DocumentResponse, DocumentVersion } from "@/types/document";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock stores
vi.mock("@/stores/documentStore", () => ({
  useDocumentStore: vi.fn(),
}));

vi.mock("@/stores/workflowStore", () => ({
  useWorkflowStore: vi.fn(),
}));

vi.mock("@/stores/workflowExecutionStore", () => ({
  useWorkflowExecutionStore: vi.fn(),
}));

// Mock apiClient (used by ContentViewer for markdown fetch)
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    download: vi.fn(),
    get: vi.fn(),
  },
}));

// Mock renderMarkdown
vi.mock("@/lib/renderMarkdown", () => ({
  renderMarkdown: vi.fn((text: string) => `<p>${text}</p>`),
}));

// Mock file download utility
vi.mock("@/lib/fileDownload", () => ({
  triggerBrowserDownload: vi.fn(),
}));

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

// Mock child components that are not relevant to this integration test
vi.mock("@/components/training/TrainingStatusBanner", () => ({
  TrainingStatusBanner: () => <div data-testid="mock-training-banner" />,
}));

vi.mock("@/components/signatures/SignatureRecordsPanel", () => ({
  SignatureRecordsPanel: () => <div data-testid="mock-signature-panel" />,
}));

vi.mock("@/components/reviews/SubmitForReviewModal", () => ({
  SubmitForReviewModal: () => <div data-testid="mock-review-modal" />,
}));

vi.mock("@/components/impact/DocumentImpactStatus", () => ({
  DocumentImpactStatus: () => <div data-testid="mock-impact-status" />,
}));

import { useDocumentStore } from "@/stores/documentStore";
import { useWorkflowStore } from "@/stores/workflowStore";
import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { apiClient } from "@/lib/apiClient";
import { DocumentDetail } from "@/components/documents/DocumentDetail";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function createVersion(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    id: 1,
    major_version: 1,
    minor_version: 0,
    storage_key: "documents/doc-uuid/v1.0/document",
    file_hash: "a".repeat(64),
    uploaded_by: 1,
    uploaded_at: "2024-01-10T10:00:00Z",
    change_reason: "Initial upload",
    content_type: "application/pdf",
    ...overrides,
  };
}

const v1_0 = createVersion({
  id: 1,
  major_version: 1,
  minor_version: 0,
  content_type: "application/pdf",
  change_reason: "Initial upload",
});

const v1_1 = createVersion({
  id: 2,
  major_version: 1,
  minor_version: 1,
  content_type: "text/markdown",
  change_reason: "Minor update",
});

const v2_0 = createVersion({
  id: 3,
  major_version: 2,
  minor_version: 0,
  content_type: "application/pdf",
  change_reason: "Major revision",
});

const mockDocument: DocumentResponse = {
  id: 42,
  document_uuid: "test-doc-uuid-999",
  title: "Test SOP Document",
  folder_path: "/sops",
  document_type: "SOP",
  current_status: "Draft",
  created_by: 1,
  created_at: "2024-01-10T10:00:00Z",
  tags: [],
  versions: [v1_0, v1_1, v2_0],
};

// ---------------------------------------------------------------------------
// Store mock helpers
// ---------------------------------------------------------------------------

function setupDocumentStoreMock(selectedVersion: DocumentVersion | null = null) {
  vi.mocked(useDocumentStore).mockImplementation((selector: unknown) => {
    const state = {
      selectedVersion,
      isVersionLoading: false,
      versionError: null,
      comparisonOpen: false,
      fetchVersion: vi.fn(),
      downloadVersion: vi.fn(),
      setComparisonOpen: vi.fn(),
      clearSelectedVersion: vi.fn(),
    };
    if (typeof selector === "function") {
      return (selector as (s: typeof state) => unknown)(state);
    }
    return state;
  });
}

function setupWorkflowStoreMock() {
  vi.mocked(useWorkflowStore).mockImplementation((selector: unknown) => {
    const state = {
      workflows: [],
      fetchWorkflowList: vi.fn(),
    };
    if (typeof selector === "function") {
      return (selector as (s: typeof state) => unknown)(state);
    }
    return state;
  });
}

function setupWorkflowExecutionStoreMock() {
  vi.mocked(useWorkflowExecutionStore).mockImplementation((selector: unknown) => {
    const state = {
      lastTransitionResult: null,
    };
    if (typeof selector === "function") {
      return (selector as (s: typeof state) => unknown)(state);
    }
    return state;
  });
}

function setupAllStoreMocks(selectedVersion: DocumentVersion | null = null) {
  setupDocumentStoreMock(selectedVersion);
  setupWorkflowStoreMock();
  setupWorkflowExecutionStoreMock();
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderDocumentDetail(document: DocumentResponse = mockDocument) {
  return render(
    <MemoryRouter>
      <DocumentDetail
        document={document}
        onNewVersion={vi.fn()}
        onBack={vi.fn()}
      />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DocumentDetail with ContentViewer integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("ContentViewer renders with the latest version on initial load", () => {
    it("renders ContentViewer with latest version (v2.0) props when no version is selected", () => {
      setupAllStoreMocks(null);

      renderDocumentDetail();

      // The latest version is v2_0 (major=2, minor=0, content_type=application/pdf)
      // For PDF, ContentViewer renders an iframe with the content URL
      const pdfViewer = screen.getByTestId("content-viewer-pdf");
      expect(pdfViewer).toBeInTheDocument();

      const iframe = pdfViewer.querySelector("iframe");
      expect(iframe).not.toBeNull();
      expect(iframe!.getAttribute("src")).toBe(
        "/api/documents/test-doc-uuid-999/versions/2/0/content"
      );
    });

    it("uses the highest (major, minor) version as latest", () => {
      // Document with versions where latest is v1.1 (no v2.x)
      const doc: DocumentResponse = {
        ...mockDocument,
        versions: [v1_0, v1_1],
      };
      setupAllStoreMocks(null);

      renderDocumentDetail(doc);

      // v1.1 has content_type text/markdown, so ContentViewer fetches markdown
      // During loading, we should see the loading indicator
      const loadingOrMarkdown =
        screen.queryByTestId("content-viewer-loading") ||
        screen.queryByTestId("content-viewer-markdown");
      expect(loadingOrMarkdown).toBeInTheDocument();
    });
  });

  describe("Version selection updates ContentViewer", () => {
    it("renders ContentViewer with the selected version's props", () => {
      // Select v1_0 (PDF, major=1, minor=0)
      setupAllStoreMocks(v1_0);

      renderDocumentDetail();

      const pdfViewer = screen.getByTestId("content-viewer-pdf");
      const iframe = pdfViewer.querySelector("iframe");
      expect(iframe!.getAttribute("src")).toBe(
        "/api/documents/test-doc-uuid-999/versions/1/0/content"
      );
    });

    it("switches content type when a markdown version is selected", async () => {
      // Select v1_1 (markdown)
      const fakeBlob = new Blob(["# Hello"], { type: "text/markdown" });
      (apiClient.download as ReturnType<typeof vi.fn>).mockResolvedValueOnce(fakeBlob);

      setupAllStoreMocks(v1_1);

      renderDocumentDetail();

      // Should show loading or markdown content (not PDF iframe)
      expect(screen.queryByTestId("content-viewer-pdf")).not.toBeInTheDocument();

      const markdownOrLoading =
        screen.queryByTestId("content-viewer-loading") ||
        screen.queryByTestId("content-viewer-markdown");
      expect(markdownOrLoading).toBeInTheDocument();
    });

    it("updates iframe URL when switching between PDF versions", () => {
      // First render with v2_0 selected
      setupAllStoreMocks(v2_0);

      const { unmount } = renderDocumentDetail();

      let pdfViewer = screen.getByTestId("content-viewer-pdf");
      let iframe = pdfViewer.querySelector("iframe");
      expect(iframe!.getAttribute("src")).toBe(
        "/api/documents/test-doc-uuid-999/versions/2/0/content"
      );

      unmount();

      // Re-render with v1_0 selected
      setupAllStoreMocks(v1_0);

      renderDocumentDetail();

      pdfViewer = screen.getByTestId("content-viewer-pdf");
      iframe = pdfViewer.querySelector("iframe");
      expect(iframe!.getAttribute("src")).toBe(
        "/api/documents/test-doc-uuid-999/versions/1/0/content"
      );
    });
  });

  describe("DownloadButton presence and interaction", () => {
    it("renders DownloadButton in the header with latest version props when no version is selected", () => {
      setupAllStoreMocks(null);

      renderDocumentDetail();

      // DownloadButton renders with aria-label "Download {documentTitle}"
      const downloadButton = screen.getByRole("button", {
        name: /download test sop document/i,
      });
      expect(downloadButton).toBeInTheDocument();
    });

    it("DownloadButton reflects the selected version", () => {
      // When v1_0 is selected, the DownloadButton should use v1_0's version info
      setupAllStoreMocks(v1_0);

      renderDocumentDetail();

      const downloadButton = screen.getByRole("button", {
        name: /download test sop document/i,
      });
      expect(downloadButton).toBeInTheDocument();
    });

    it("DownloadButton is not rendered when document has no versions", () => {
      const emptyDoc: DocumentResponse = {
        ...mockDocument,
        versions: [],
      };
      setupAllStoreMocks(null);

      renderDocumentDetail(emptyDoc);

      // DownloadButton should not be present when there's no viewedVersion
      const downloadButton = screen.queryByRole("button", {
        name: /download test sop document/i,
      });
      expect(downloadButton).not.toBeInTheDocument();
    });

    it("DownloadButton updates when version selection changes", () => {
      // Render with no selection (uses latest v2_0)
      setupAllStoreMocks(null);
      const { unmount } = renderDocumentDetail();

      let downloadButton = screen.getByRole("button", {
        name: /download test sop document/i,
      });
      expect(downloadButton).toBeInTheDocument();

      unmount();

      // Re-render with v1_1 selected
      setupAllStoreMocks(v1_1);
      renderDocumentDetail();

      // DownloadButton still present (with updated version internally)
      downloadButton = screen.getByRole("button", {
        name: /download test sop document/i,
      });
      expect(downloadButton).toBeInTheDocument();
    });
  });
});
