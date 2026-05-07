import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { createElement } from "react";
import { useDocumentStore } from "@/stores/documentStore";
import { useAuthStore } from "@/stores/authStore";

/**
 * Unit tests for DocumentsPage integration.
 *
 * Validates: Requirements 1.1, 1.2, 1.5, 1.6, 4.1, 5.1
 */

// Mock child components to isolate DocumentsPage behavior
vi.mock("@/components/documents", () => ({
  DocumentDetail: ({ document, onBack, onNewVersion }: any) =>
    createElement("div", { "data-testid": "document-detail" },
      createElement("span", null, document.title),
      createElement("button", { onClick: onBack }, "Back"),
      createElement("button", { onClick: onNewVersion }, "New Version")
    ),
  DocumentList: ({ documents, onDocumentClick }: any) =>
    createElement("div", { "data-testid": "document-list" },
      documents.map((doc: any) =>
        createElement("button", {
          key: doc.document_uuid,
          onClick: () => onDocumentClick(doc.document_uuid),
          "data-testid": `doc-${doc.document_uuid}`,
        }, doc.title)
      )
    ),
  FilterBar: () => createElement("div", { "data-testid": "filter-bar" }),
  Pagination: () => createElement("div", { "data-testid": "pagination" }),
  UploadDialog: ({ open, onOpenChange }: any) =>
    open
      ? createElement("div", { "data-testid": "upload-dialog" },
          createElement("button", { onClick: () => onOpenChange(false) }, "Close")
        )
      : null,
  VersionUploadDialog: ({ open }: any) =>
    open ? createElement("div", { "data-testid": "version-dialog" }) : null,
}));

// We need to import DocumentsPage after mocks are set up
const { DocumentsPage } = await import("@/pages/DocumentsPage");

const mockFetchDocuments = vi.fn();
const mockFetchDocument = vi.fn();

function setDocumentStoreState(overrides: Record<string, unknown>) {
  useDocumentStore.setState({
    documents: [],
    selectedDocument: null,
    total: 0,
    offset: 0,
    limit: 20,
    tagFilter: null,
    folderPathFilter: null,
    isLoading: false,
    error: null,
    fetchDocuments: mockFetchDocuments,
    fetchDocument: mockFetchDocument,
    uploadDocument: vi.fn(),
    createVersion: vi.fn(),
    setPage: vi.fn(),
    nextPage: vi.fn(),
    prevPage: vi.fn(),
    setTagFilter: vi.fn(),
    setFolderPathFilter: vi.fn(),
    clearFilters: vi.fn(),
    ...overrides,
  });
}

function setAuthStoreState(overrides: Record<string, unknown>) {
  useAuthStore.setState({
    user: null,
    isAuthenticated: true,
    isLoading: false,
    sessionExpired: false,
    activeCompanyId: 1,
    activeCompanySlug: "test-company",
    login: vi.fn(),
    logout: vi.fn(),
    refreshToken: vi.fn(),
    initialize: vi.fn(),
    reAuthenticate: vi.fn(),
    clearSession: vi.fn(),
    ...overrides,
  } as any);
}

describe("DocumentsPage integration", () => {
  beforeEach(() => {
    mockFetchDocuments.mockReset();
    mockFetchDocument.mockReset();
    setAuthStoreState({});
  });

  afterEach(() => {
    cleanup();
  });

  describe("Requirement 1.1: Mount triggers fetchDocuments", () => {
    it("calls fetchDocuments on mount", () => {
      setDocumentStoreState({});
      render(createElement(DocumentsPage));
      expect(mockFetchDocuments).toHaveBeenCalledTimes(1);
    });
  });

  describe("Requirement 1.2: Loading state shows spinner", () => {
    it("displays a loading indicator when isLoading is true", () => {
      setDocumentStoreState({ isLoading: true });
      render(createElement(DocumentsPage));
      const loader = screen.getByLabelText("Loading documents");
      expect(loader).toBeDefined();
    });

    it("does not display loading indicator when isLoading is false", () => {
      setDocumentStoreState({ isLoading: false });
      render(createElement(DocumentsPage));
      const loader = screen.queryByLabelText("Loading documents");
      expect(loader).toBeNull();
    });
  });

  describe("Requirement 1.5: Empty state message", () => {
    it("shows 'No documents yet' when documents is empty and not loading", () => {
      setDocumentStoreState({ documents: [], isLoading: false, error: null });
      render(createElement(DocumentsPage));
      expect(screen.getByText("No documents yet")).toBeDefined();
    });

    it("does not show empty state when loading", () => {
      setDocumentStoreState({ documents: [], isLoading: true, error: null });
      render(createElement(DocumentsPage));
      expect(screen.queryByText("No documents yet")).toBeNull();
    });
  });

  describe("Requirement 1.6: Error state displays error", () => {
    it("displays error message in an alert role when error is set", () => {
      setDocumentStoreState({ error: "Network failure" });
      render(createElement(DocumentsPage));
      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(alert.textContent).toContain("Network failure");
    });

    it("does not display error banner when error is null", () => {
      setDocumentStoreState({ error: null });
      render(createElement(DocumentsPage));
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });

  describe("Requirement 4.1: Upload button opens dialog", () => {
    it("opens the UploadDialog when Upload Document button is clicked", () => {
      setDocumentStoreState({});
      render(createElement(DocumentsPage));

      // Dialog should not be visible initially
      expect(screen.queryByTestId("upload-dialog")).toBeNull();

      // Click the upload button
      const uploadButton = screen.getByText("Upload Document");
      fireEvent.click(uploadButton);

      // Dialog should now be visible
      expect(screen.getByTestId("upload-dialog")).toBeDefined();
    });
  });

  describe("Requirement 5.1: Document click fetches detail", () => {
    it("calls fetchDocument with the document uuid when a document is clicked", () => {
      const testDoc = {
        id: 1,
        document_uuid: "2024-00001",
        title: "Test Document",
        folder_path: "/quality",
        document_type: "SOP",
        current_status: "Draft",
        created_by: 1,
        created_at: "2024-01-01T00:00:00Z",
        tags: [],
        versions: [],
      };

      setDocumentStoreState({ documents: [testDoc] });
      render(createElement(DocumentsPage));

      const docButton = screen.getByTestId("doc-2024-00001");
      fireEvent.click(docButton);

      expect(mockFetchDocument).toHaveBeenCalledWith("2024-00001");
    });
  });
});
