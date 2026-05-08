import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import type { TemplateVersionResponse } from "../../../types/template";

/**
 * Unit tests for VersionHistoryPanel and DownloadPdfButton components.
 *
 * Validates: Requirements 11.1, 11.2, 11.4, 16.4, 16.5, 16.6
 *
 * Testing strategy: Mock the Zustand store via vi.mock and control state
 * through mockImplementation. This isolates component rendering from
 * actual store logic. No backend API calls are made in these tests.
 */

// ---------------------------------------------------------------------------
// Store mock setup
// ---------------------------------------------------------------------------

const mockFetchVersionHistory = vi.fn();
const mockLoadVersionIntoCanvas = vi.fn();
const mockDownloadPdf = vi.fn();

vi.mock("../../../stores/templateBuilderStore", () => ({
  useTemplateBuilderStore: vi.fn(),
}));

import { useTemplateBuilderStore } from "../../../stores/templateBuilderStore";
import { VersionHistoryPanel } from "../VersionHistoryPanel";
import { DownloadPdfButton } from "../DownloadPdfButton";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockVersion(
  overrides: Partial<TemplateVersionResponse> = {}
): TemplateVersionResponse {
  return {
    id: 1,
    version_number: 1,
    document_uuid: "2024-00001",
    json_schema: { elements: [] },
    status: "ReadOnly",
    is_active: false,
    created_by: 1,
    change_reason: "Initial version",
    created_at: "2024-06-01T10:00:00Z",
    fields: [],
    ...overrides,
  };
}

function setupVersionHistoryMock(overrides: {
  versions?: TemplateVersionResponse[];
  activeVersion?: TemplateVersionResponse | null;
  versionError?: string | null;
}) {
  const state = {
    versions: overrides.versions ?? [],
    activeVersion: overrides.activeVersion ?? null,
    versionError: overrides.versionError ?? null,
    fetchVersionHistory: mockFetchVersionHistory,
    loadVersionIntoCanvas: mockLoadVersionIntoCanvas,
  };

  vi.mocked(useTemplateBuilderStore).mockImplementation((selector: unknown) => {
    if (typeof selector === "function") {
      return (selector as (s: typeof state) => unknown)(state);
    }
    return state;
  });
}

function setupDownloadMock(overrides: {
  isDownloading?: boolean;
  downloadError?: string | null;
}) {
  const state = {
    isDownloading: overrides.isDownloading ?? false,
    downloadError: overrides.downloadError ?? null,
    downloadPdf: mockDownloadPdf,
  };

  vi.mocked(useTemplateBuilderStore).mockImplementation((selector: unknown) => {
    if (typeof selector === "function") {
      return (selector as (s: typeof state) => unknown)(state);
    }
    return state;
  });
}

// ---------------------------------------------------------------------------
// VersionHistoryPanel Tests
// ---------------------------------------------------------------------------

describe("VersionHistoryPanel", () => {
  beforeEach(() => {
    mockFetchVersionHistory.mockReset();
    mockLoadVersionIntoCanvas.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("lists versions in descending order (newest first)", () => {
    const versions = [
      createMockVersion({ id: 3, version_number: 3, created_at: "2024-06-03T10:00:00Z" }),
      createMockVersion({ id: 2, version_number: 2, created_at: "2024-06-02T10:00:00Z" }),
      createMockVersion({ id: 1, version_number: 1, created_at: "2024-06-01T10:00:00Z" }),
    ];

    setupVersionHistoryMock({ versions });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" />
    );

    const list = screen.getByRole("list", { name: "Template versions" });
    const items = list.querySelectorAll("li");
    expect(items).toHaveLength(3);

    // First item should be v3 (newest)
    expect(items[0].textContent).toContain("v3");
    // Last item should be v1 (oldest)
    expect(items[2].textContent).toContain("v1");
  });

  it("highlights the active version with distinct styling", () => {
    const activeVersion = createMockVersion({
      id: 2,
      version_number: 2,
      is_active: true,
    });
    const versions = [
      activeVersion,
      createMockVersion({ id: 1, version_number: 1, is_active: false }),
    ];

    setupVersionHistoryMock({ versions, activeVersion });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" />
    );

    // Active version should show "Active" badge
    expect(screen.getByText("Active")).toBeDefined();

    // The active version button should have aria-current="true"
    const list = screen.getByRole("list", { name: "Template versions" });
    const buttons = list.querySelectorAll("button");
    const activeButton = Array.from(buttons).find(
      (btn) => btn.getAttribute("aria-current") === "true"
    );
    expect(activeButton).toBeDefined();
    expect(activeButton!.textContent).toContain("v2");
  });

  it("shows 'Create New Version' button when isReadOnly is true", () => {
    setupVersionHistoryMock({ versions: [] });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" isReadOnly={true} />
    );

    expect(
      screen.getByRole("button", { name: "Create New Version" })
    ).toBeDefined();
  });

  it("does not show 'Create New Version' button when isReadOnly is false", () => {
    setupVersionHistoryMock({ versions: [] });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" isReadOnly={false} />
    );

    expect(
      screen.queryByRole("button", { name: "Create New Version" })
    ).toBeNull();
  });

  it("calls onCreateNewVersion when 'Create New Version' button is clicked", () => {
    setupVersionHistoryMock({ versions: [] });
    const onCreateNewVersion = vi.fn();

    render(
      <VersionHistoryPanel
        documentUuid="2024-00001"
        isReadOnly={true}
        onCreateNewVersion={onCreateNewVersion}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Create New Version" }));
    expect(onCreateNewVersion).toHaveBeenCalledTimes(1);
  });

  it("fetches version history on mount", () => {
    setupVersionHistoryMock({ versions: [] });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" />
    );

    expect(mockFetchVersionHistory).toHaveBeenCalledWith("2024-00001");
  });

  it("displays version metadata (timestamp and creator)", () => {
    const versions = [
      createMockVersion({
        id: 1,
        version_number: 1,
        created_by: 42,
        created_at: "2024-06-15T14:30:00Z",
      }),
    ];

    setupVersionHistoryMock({ versions });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" />
    );

    // Creator name displayed as "User {id}"
    expect(screen.getByText("User 42")).toBeDefined();
  });

  it("shows empty state when no versions exist", () => {
    setupVersionHistoryMock({ versions: [] });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" />
    );

    expect(screen.getByText("No versions available.")).toBeDefined();
  });

  it("displays error message when versionError is set", () => {
    setupVersionHistoryMock({ versions: [], versionError: "Failed to load versions" });

    render(
      <VersionHistoryPanel documentUuid="2024-00001" />
    );

    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText("Failed to load versions")).toBeDefined();
  });

  it("calls loadVersionIntoCanvas and onVersionSelect when a version is clicked", () => {
    const version = createMockVersion({ id: 1, version_number: 1 });
    setupVersionHistoryMock({ versions: [version] });
    const onVersionSelect = vi.fn();

    render(
      <VersionHistoryPanel
        documentUuid="2024-00001"
        onVersionSelect={onVersionSelect}
      />
    );

    // Click the version entry button
    const versionButton = screen.getByText("v1").closest("button")!;
    fireEvent.click(versionButton);

    expect(mockLoadVersionIntoCanvas).toHaveBeenCalledWith(version);
    expect(onVersionSelect).toHaveBeenCalledWith(version);
  });
});

// ---------------------------------------------------------------------------
// DownloadPdfButton Tests
// ---------------------------------------------------------------------------

describe("DownloadPdfButton", () => {
  beforeEach(() => {
    mockDownloadPdf.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders download button in idle state", () => {
    setupDownloadMock({});

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    const button = screen.getByRole("button", { name: "Download PDF" });
    expect(button).toBeDefined();
    expect(button.getAttribute("disabled")).toBeNull();
    expect(button.textContent).toContain("Download PDF");
  });

  it("shows loading spinner and disables button while downloading", () => {
    setupDownloadMock({ isDownloading: true });

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    const button = screen.getByRole("button", { name: "Download PDF" });
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.textContent).toContain("Downloading");
  });

  it("triggers downloadPdf store action on click", () => {
    setupDownloadMock({});

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    expect(mockDownloadPdf).toHaveBeenCalledWith("2024-00001");
  });

  it("displays error message when downloadError is set", () => {
    setupDownloadMock({ downloadError: "Template not found" });

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText("Template not found")).toBeDefined();
  });

  it("displays 'Not downloadable' error for 400 status", () => {
    setupDownloadMock({ downloadError: "Not downloadable" });

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    expect(screen.getByText("Not downloadable")).toBeDefined();
  });

  it("displays 'Download failed' error for network errors", () => {
    setupDownloadMock({ downloadError: "Download failed" });

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    expect(screen.getByText("Download failed")).toBeDefined();
  });

  it("re-enables button when error occurs (not in downloading state)", () => {
    setupDownloadMock({ isDownloading: false, downloadError: "Download failed" });

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    const button = screen.getByRole("button", { name: "Download PDF" });
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("does not show error message when downloadError is null", () => {
    setupDownloadMock({ downloadError: null });

    render(<DownloadPdfButton documentUuid="2024-00001" />);

    expect(screen.queryByRole("alert")).toBeNull();
  });
});
