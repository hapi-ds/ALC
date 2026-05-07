import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import React from "react";
import type { DocumentVersion } from "@/types/document";

// Mock the document store
vi.mock("@/stores/documentStore", () => ({
  useDocumentStore: vi.fn(() => null),
}));

import { useDocumentStore } from "@/stores/documentStore";
import { VersionHistoryPanel } from "@/components/documents/VersionHistoryPanel";
import { VersionStatusBadge } from "@/components/documents/VersionStatusBadge";

function setupStoreMock() {
  vi.mocked(useDocumentStore).mockImplementation((selector: unknown) => {
    const state = { downloadingVersionId: null };
    if (typeof selector === "function") {
      return (selector as (s: typeof state) => unknown)(state);
    }
    return state;
  });
}

/**
 * Helper to create a mock DocumentVersion.
 */
function createMockVersion(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    id: 1,
    major_version: 1,
    minor_version: 0,
    storage_key: "storage/doc/v1.0",
    file_hash: "abc123def456789012345678901234567890123456789012345678901234abcd",
    uploaded_by: 42,
    uploaded_at: "2024-01-15T10:30:00Z",
    change_reason: "Initial upload",
    ...overrides,
  };
}

describe("VersionHistoryPanel", () => {
  const defaultProps = {
    documentTitle: "Test Document",
    onSelectVersion: vi.fn(),
    onDownload: vi.fn(),
    onCompare: vi.fn(),
  };

  beforeEach(() => {
    setupStoreMock();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders correct number of version entries for a given array", () => {
    const versions: DocumentVersion[] = [
      createMockVersion({ id: 1, major_version: 1, minor_version: 0 }),
      createMockVersion({ id: 2, major_version: 1, minor_version: 1 }),
      createMockVersion({ id: 3, major_version: 2, minor_version: 0 }),
    ];

    render(<VersionHistoryPanel {...defaultProps} versions={versions} />);

    // Each version entry has an aria-label like "Version X.Y"
    const entries = screen.getAllByRole("button", { name: /^Version \d+\.\d+$/ });
    expect(entries).toHaveLength(3);
  });

  it("shows empty state message when versions array is empty", () => {
    render(<VersionHistoryPanel {...defaultProps} versions={[]} />);

    expect(
      screen.getByText("No versions available for this document.")
    ).toBeInTheDocument();
  });

  it("disables Compare Versions button when fewer than 2 versions", () => {
    const versions: DocumentVersion[] = [
      createMockVersion({ id: 1, major_version: 1, minor_version: 0 }),
    ];

    render(<VersionHistoryPanel {...defaultProps} versions={versions} />);

    const compareButton = screen.getByRole("button", { name: /compare versions/i });
    expect(compareButton).toBeDisabled();
  });

  it("enables Compare Versions button when 2 or more versions exist", () => {
    const versions: DocumentVersion[] = [
      createMockVersion({ id: 1, major_version: 1, minor_version: 0 }),
      createMockVersion({ id: 2, major_version: 1, minor_version: 1 }),
    ];

    render(<VersionHistoryPanel {...defaultProps} versions={versions} />);

    const compareButton = screen.getByRole("button", { name: /compare versions/i });
    expect(compareButton).not.toBeDisabled();
  });
});

describe("VersionStatusBadge", () => {
  afterEach(() => {
    cleanup();
  });

  it('shows "Current" with aria-label="Current version" for the latest version', () => {
    render(<VersionStatusBadge isCurrent={true} />);

    const badge = screen.getByText("Current");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("aria-label", "Current version");
  });

  it('shows "Previous" with aria-label="Previous version" for older versions', () => {
    render(<VersionStatusBadge isCurrent={false} />);

    const badge = screen.getByText("Previous");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("aria-label", "Previous version");
  });

  it("applies primary styling for current version badge", () => {
    render(<VersionStatusBadge isCurrent={true} />);

    const badge = screen.getByText("Current");
    expect(badge.className).toContain("bg-primary/15");
    expect(badge.className).toContain("text-primary");
  });

  it("applies muted styling for previous version badge", () => {
    render(<VersionStatusBadge isCurrent={false} />);

    const badge = screen.getByText("Previous");
    expect(badge.className).toContain("bg-muted");
    expect(badge.className).toContain("text-muted-foreground");
  });
});
