import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import React from "react";
import { UserHistoryTimeline } from "../../../components/admin/UserHistoryTimeline";
import type { UserHistoryEntry } from "../../../types/admin";

/**
 * Tests for UserHistoryTimeline rendering and timeline entries.
 *
 * Validates: Requirements 14.3
 */

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockEntries: UserHistoryEntry[] = [
  {
    version_id: 3,
    changed_at: "2024-03-15T14:30:00Z",
    changed_by: 1,
    changed_by_username: "admin",
    change_reason: "Updated user role",
    changes: {
      role: { old: "member", new: "doc_admin" },
    },
  },
  {
    version_id: 2,
    changed_at: "2024-02-10T09:00:00Z",
    changed_by: 1,
    changed_by_username: "admin",
    change_reason: "Updated email address",
    changes: {
      email: { old: "old@example.com", new: "new@example.com" },
    },
  },
  {
    version_id: 1,
    changed_at: "2024-01-15T10:00:00Z",
    changed_by: 1,
    changed_by_username: "admin",
    change_reason: "Initial user creation",
    changes: {},
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UserHistoryTimeline", () => {
  afterEach(() => {
    cleanup();
  });

  describe("Empty state", () => {
    it("shows empty message when no entries", () => {
      render(<UserHistoryTimeline entries={[]} />);

      expect(screen.getByText("No change history available.")).toBeDefined();
    });
  });

  describe("Rendering entries", () => {
    it("renders timeline list with correct aria-label", () => {
      render(<UserHistoryTimeline entries={mockEntries} />);

      expect(screen.getByLabelText("User change history timeline")).toBeDefined();
    });

    it("renders all timeline entries", () => {
      render(<UserHistoryTimeline entries={mockEntries} />);

      expect(screen.getByText("Version 3")).toBeDefined();
      expect(screen.getByText("Version 2")).toBeDefined();
      expect(screen.getByText("Version 1")).toBeDefined();
    });

    it("displays change reasons in quotes", () => {
      render(<UserHistoryTimeline entries={mockEntries} />);

      expect(screen.getByText(/Updated user role/)).toBeDefined();
      expect(screen.getByText(/Updated email address/)).toBeDefined();
      expect(screen.getByText(/Initial user creation/)).toBeDefined();
    });

    it("displays changed_by_username for each entry", () => {
      render(<UserHistoryTimeline entries={mockEntries} />);

      const adminLabels = screen.getAllByText("admin");
      expect(adminLabels.length).toBe(3);
    });

    it("renders field changes table when changes exist", () => {
      render(<UserHistoryTimeline entries={mockEntries} />);

      // The role change entry should show field diff
      expect(screen.getByText("Role")).toBeDefined();
      expect(screen.getByText("member")).toBeDefined();
      expect(screen.getByText("doc_admin")).toBeDefined();
    });

    it("renders email change with old and new values", () => {
      render(<UserHistoryTimeline entries={mockEntries} />);

      expect(screen.getByText("old@example.com")).toBeDefined();
      expect(screen.getByText("new@example.com")).toBeDefined();
    });

    it("does not render field changes table when changes is empty", () => {
      render(<UserHistoryTimeline entries={[mockEntries[2]]} />);

      // Version 1 has no changes, so no table should be rendered
      expect(screen.queryByLabelText("Field changes")).toBeNull();
    });
  });

  describe("Formatting", () => {
    it("formats field names from snake_case to Title Case", () => {
      const entries: UserHistoryEntry[] = [
        {
          version_id: 1,
          changed_at: "2024-01-15T10:00:00Z",
          changed_by: 1,
          changed_by_username: "admin",
          change_reason: "Test",
          changes: {
            full_name: { old: "Old Name", new: "New Name" },
            is_active: { old: true, new: false },
          },
        },
      ];

      render(<UserHistoryTimeline entries={entries} />);

      expect(screen.getByText("Full Name")).toBeDefined();
      expect(screen.getByText("Is Active")).toBeDefined();
    });

    it("formats boolean values as Yes/No", () => {
      const entries: UserHistoryEntry[] = [
        {
          version_id: 1,
          changed_at: "2024-01-15T10:00:00Z",
          changed_by: 1,
          changed_by_username: "admin",
          change_reason: "Deactivated user",
          changes: {
            is_active: { old: true, new: false },
          },
        },
      ];

      render(<UserHistoryTimeline entries={entries} />);

      expect(screen.getByText("Yes")).toBeDefined();
      expect(screen.getByText("No")).toBeDefined();
    });

    it("formats null values as em dash", () => {
      const entries: UserHistoryEntry[] = [
        {
          version_id: 1,
          changed_at: "2024-01-15T10:00:00Z",
          changed_by: 1,
          changed_by_username: "admin",
          change_reason: "Test",
          changes: {
            revoked_at: { old: null, new: "2024-03-01T10:00:00Z" },
          },
        },
      ];

      render(<UserHistoryTimeline entries={entries} />);

      expect(screen.getByText("—")).toBeDefined();
    });
  });
});
