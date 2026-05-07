import { describe, it, expect, vi, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import React from "react";

// Mock createPortal to render children inline instead of into document.body
vi.mock("react-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-dom")>();
  return {
    ...actual,
    createPortal: (children: React.ReactNode) => children,
  };
});

import { VersionComparisonView } from "@/components/documents/VersionComparisonView";
import { DiffMetadataView } from "@/components/documents/DiffMetadataView";
import type { DocumentVersion } from "@/types/document";

/**
 * Helper to create a mock DocumentVersion object.
 */
function createMockVersion(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    id: 1,
    major_version: 1,
    minor_version: 0,
    storage_key: "storage/doc-v1.0.pdf",
    file_hash: "abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
    uploaded_by: 1,
    uploaded_at: "2024-01-15T10:00:00Z",
    change_reason: "Initial upload",
    ...overrides,
  };
}

/** Three versions for testing default selection behavior */
const threeVersions: DocumentVersion[] = [
  createMockVersion({
    id: 1,
    major_version: 1,
    minor_version: 0,
    uploaded_at: "2024-01-01T10:00:00Z",
    change_reason: "Initial upload",
    file_hash: "hash_v1_0",
    uploaded_by: 1,
  }),
  createMockVersion({
    id: 2,
    major_version: 1,
    minor_version: 1,
    uploaded_at: "2024-02-01T10:00:00Z",
    change_reason: "Minor fix",
    file_hash: "hash_v1_1",
    uploaded_by: 1,
  }),
  createMockVersion({
    id: 3,
    major_version: 2,
    minor_version: 0,
    uploaded_at: "2024-03-01T10:00:00Z",
    change_reason: "Major revision",
    file_hash: "hash_v2_0",
    uploaded_by: 2,
  }),
];

describe("VersionComparisonView", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe("Default version selection", () => {
    it("defaults left to second-most-recent and right to most-recent when opened with 3+ versions", () => {
      render(
        <VersionComparisonView
          open={true}
          onOpenChange={vi.fn()}
          versions={threeVersions}
        />
      );

      // Most recent is v2.0 (id=3), second-most-recent is v1.1 (id=2)
      const leftSelect = screen.getByLabelText(/left version/i) as HTMLSelectElement;
      const rightSelect = screen.getByLabelText(/right version/i) as HTMLSelectElement;

      // Left should default to second-most-recent (v1.1, id=2)
      expect(leftSelect.value).toBe("2");
      // Right should default to most-recent (v2.0, id=3)
      expect(rightSelect.value).toBe("3");
    });
  });

  describe("Same-version notice", () => {
    it("shows notice when same version is selected on both sides", () => {
      render(
        <VersionComparisonView
          open={true}
          onOpenChange={vi.fn()}
          versions={threeVersions}
        />
      );

      // Change left selector to match right (most recent, id=3)
      const leftSelect = screen.getByLabelText(/left version/i);
      fireEvent.change(leftSelect, { target: { value: "3" } });

      expect(
        screen.getByText(
          "Both sides show the same version. Select different versions to see differences."
        )
      ).toBeInTheDocument();
    });

    it("does not show notice when different versions are selected", () => {
      render(
        <VersionComparisonView
          open={true}
          onOpenChange={vi.fn()}
          versions={threeVersions}
        />
      );

      // Default selection is different versions (v1.1 left, v2.0 right)
      expect(
        screen.queryByText(
          "Both sides show the same version. Select different versions to see differences."
        )
      ).not.toBeInTheDocument();
    });
  });

  describe("Field highlighting for differing values", () => {
    it("applies amber background class to rows where values differ", () => {
      render(
        <VersionComparisonView
          open={true}
          onOpenChange={vi.fn()}
          versions={threeVersions}
        />
      );

      // Default: left=v1.1 (id=2), right=v2.0 (id=3)
      // These differ in: version number, file_hash, uploaded_at, change_reason, uploaded_by, storage_key
      const allRows = document.querySelectorAll(".bg-amber-50");
      expect(allRows.length).toBeGreaterThan(0);
    });

    it("does not highlight rows when same version is selected on both sides", () => {
      render(
        <VersionComparisonView
          open={true}
          onOpenChange={vi.fn()}
          versions={threeVersions}
        />
      );

      // Select same version on both sides
      const leftSelect = screen.getByLabelText(/left version/i);
      fireEvent.change(leftSelect, { target: { value: "3" } });

      // No amber highlighting should be present
      const highlightedRows = document.querySelectorAll(".bg-amber-50");
      expect(highlightedRows.length).toBe(0);
    });
  });

  describe("Does not render when closed", () => {
    it("renders nothing when open is false", () => {
      const { container } = render(
        <VersionComparisonView
          open={false}
          onOpenChange={vi.fn()}
          versions={threeVersions}
        />
      );

      expect(container.innerHTML).toBe("");
    });
  });
});

describe("DiffMetadataView", () => {
  afterEach(() => {
    cleanup();
  });

  describe("File content unchanged notice", () => {
    it("shows 'File content unchanged' when two versions have the same file_hash", () => {
      const left = createMockVersion({
        id: 1,
        major_version: 1,
        minor_version: 0,
        file_hash: "same_hash_value",
        uploaded_by: 1,
        uploaded_at: "2024-01-01T10:00:00Z",
      });
      const right = createMockVersion({
        id: 2,
        major_version: 1,
        minor_version: 1,
        file_hash: "same_hash_value",
        uploaded_by: 1,
        uploaded_at: "2024-01-02T10:00:00Z",
      });

      render(<DiffMetadataView left={left} right={right} />);

      expect(screen.getByText("File content unchanged")).toBeInTheDocument();
    });
  });

  describe("File hash changed notice", () => {
    it("shows 'File hash changed between versions' when hashes differ", () => {
      const left = createMockVersion({
        id: 1,
        major_version: 1,
        minor_version: 0,
        file_hash: "hash_aaa",
        uploaded_by: 1,
        uploaded_at: "2024-01-01T10:00:00Z",
      });
      const right = createMockVersion({
        id: 2,
        major_version: 1,
        minor_version: 1,
        file_hash: "hash_bbb",
        uploaded_by: 1,
        uploaded_at: "2024-01-02T10:00:00Z",
      });

      render(<DiffMetadataView left={left} right={right} />);

      expect(
        screen.getByText("File hash changed between versions")
      ).toBeInTheDocument();
    });
  });

  describe("Uploader change info", () => {
    it("shows uploader changed message when uploaders differ", () => {
      const left = createMockVersion({
        id: 1,
        major_version: 1,
        minor_version: 0,
        file_hash: "hash_aaa",
        uploaded_by: 5,
        uploaded_at: "2024-01-01T10:00:00Z",
      });
      const right = createMockVersion({
        id: 2,
        major_version: 1,
        minor_version: 1,
        file_hash: "hash_bbb",
        uploaded_by: 8,
        uploaded_at: "2024-01-02T10:00:00Z",
      });

      render(<DiffMetadataView left={left} right={right} />);

      // The component renders: "Uploader changed (User 5 → User 8)"
      expect(
        screen.getByText(/Uploader changed \(User 5 → User 8\)/)
      ).toBeInTheDocument();
    });

    it("shows same uploader message when uploaders are the same", () => {
      const left = createMockVersion({
        id: 1,
        major_version: 1,
        minor_version: 0,
        file_hash: "hash_aaa",
        uploaded_by: 3,
        uploaded_at: "2024-01-01T10:00:00Z",
      });
      const right = createMockVersion({
        id: 2,
        major_version: 1,
        minor_version: 1,
        file_hash: "hash_bbb",
        uploaded_by: 3,
        uploaded_at: "2024-01-02T10:00:00Z",
      });

      render(<DiffMetadataView left={left} right={right} />);

      expect(screen.getByText("Same uploader (User 3)")).toBeInTheDocument();
    });
  });

  describe("Highlighting for changed fields", () => {
    it("applies amber background to file content section when hash changed", () => {
      const left = createMockVersion({
        id: 1,
        file_hash: "hash_aaa",
        uploaded_by: 1,
      });
      const right = createMockVersion({
        id: 2,
        file_hash: "hash_bbb",
        uploaded_by: 1,
      });

      const { container } = render(<DiffMetadataView left={left} right={right} />);

      // The file content section should have amber background when hash changed
      const amberSections = container.querySelectorAll(".bg-amber-50");
      expect(amberSections.length).toBeGreaterThan(0);
    });

    it("applies amber background to uploader section when uploader changed", () => {
      const left = createMockVersion({
        id: 1,
        file_hash: "same_hash",
        uploaded_by: 1,
      });
      const right = createMockVersion({
        id: 2,
        file_hash: "same_hash",
        uploaded_by: 2,
      });

      const { container } = render(<DiffMetadataView left={left} right={right} />);

      // The uploader section should have amber background
      const amberSections = container.querySelectorAll(".bg-amber-50");
      expect(amberSections.length).toBeGreaterThan(0);
    });
  });
});
