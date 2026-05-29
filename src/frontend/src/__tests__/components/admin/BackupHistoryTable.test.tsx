import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Tests for BackupHistoryTable rendering with various backup states.
 *
 * Validates: Requirements 9.2–9.5
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

import { useSystemConfigStore } from "../../../stores/useSystemConfigStore";
import { BackupHistoryTable } from "../../../components/admin/BackupHistoryTable";
import type { BackupRecord } from "../../../types/systemConfig";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockBackups: BackupRecord[] = [
  {
    id: 1,
    task_id: "task-001",
    backup_type: "manual",
    status: "completed",
    started_at: "2024-06-15T02:00:00Z",
    completed_at: "2024-06-15T02:05:30Z",
    file_size_bytes: 536870912, // ~512 MB
    duration_seconds: 330,
    error_message: null,
  },
  {
    id: 2,
    task_id: "task-002",
    backup_type: "scheduled",
    status: "completed",
    started_at: "2024-06-14T02:00:00Z",
    completed_at: "2024-06-14T02:03:15Z",
    file_size_bytes: 524288000, // ~500 MB
    duration_seconds: 195,
    error_message: null,
  },
  {
    id: 3,
    task_id: "task-003",
    backup_type: "manual",
    status: "failed",
    started_at: "2024-06-13T14:30:00Z",
    completed_at: null,
    file_size_bytes: null,
    duration_seconds: null,
    error_message: "pg_dump: connection refused",
  },
  {
    id: 4,
    task_id: "task-004",
    backup_type: "manual",
    status: "running",
    started_at: "2024-06-15T10:00:00Z",
    completed_at: null,
    file_size_bytes: null,
    duration_seconds: null,
    error_message: null,
  },
  {
    id: 5,
    task_id: "task-005",
    backup_type: "scheduled",
    status: "queued",
    started_at: null,
    completed_at: null,
    file_size_bytes: null,
    duration_seconds: null,
    error_message: null,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore(overrides: Partial<ReturnType<typeof useSystemConfigStore.getState>> = {}) {
  useSystemConfigStore.setState({
    backupHistory: [],
    loading: {},
    errors: {},
    fetchBackupHistory: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useSystemConfigStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BackupHistoryTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Loading state", () => {
    it("shows loading skeleton when loading and no data", () => {
      resetStore({ loading: { backupHistory: true } });

      render(<BackupHistoryTable />);

      expect(screen.getByLabelText("Loading backup history")).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("shows error alert when fetch fails", () => {
      resetStore({
        errors: { backupHistory: "Database connection error" },
      });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Failed to load backup history")).toBeDefined();
      expect(screen.getByText("Database connection error")).toBeDefined();
    });

    it("shows Retry button on error", () => {
      resetStore({
        errors: { backupHistory: "Database connection error" },
      });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Retry")).toBeDefined();
    });

    it("calls fetchBackupHistory when Retry is clicked", () => {
      const mockFetch = vi.fn().mockResolvedValue(undefined);
      resetStore({
        errors: { backupHistory: "Database connection error" },
        fetchBackupHistory: mockFetch,
      });

      render(<BackupHistoryTable />);
      fireEvent.click(screen.getByText("Retry"));

      expect(mockFetch).toHaveBeenCalled();
    });
  });

  describe("Empty state", () => {
    it("shows empty message when no backups exist", () => {
      resetStore({ backupHistory: [] });

      render(<BackupHistoryTable />);

      expect(
        screen.getByText(
          "No backup history available. Trigger a manual backup or wait for the next scheduled backup."
        )
      ).toBeDefined();
    });
  });

  describe("Table rendering", () => {
    it("renders the table with correct aria-label", () => {
      resetStore({ backupHistory: mockBackups });

      render(<BackupHistoryTable />);

      expect(
        screen.getByRole("table", { name: "Backup history table" })
      ).toBeDefined();
    });

    it("renders table headers", () => {
      resetStore({ backupHistory: mockBackups });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Timestamp")).toBeDefined();
      expect(screen.getByText("Type")).toBeDefined();
      expect(screen.getByText("Status")).toBeDefined();
      expect(screen.getByText("Size")).toBeDefined();
      expect(screen.getByText("Duration")).toBeDefined();
      expect(screen.getByText("Error")).toBeDefined();
    });

    it("renders Backup History heading", () => {
      resetStore({ backupHistory: mockBackups });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Backup History")).toBeDefined();
    });
  });

  describe("Status badges", () => {
    it("shows Completed badge for completed backups", () => {
      resetStore({ backupHistory: [mockBackups[0]] });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Completed")).toBeDefined();
    });

    it("shows Failed badge for failed backups", () => {
      resetStore({ backupHistory: [mockBackups[2]] });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Failed")).toBeDefined();
    });

    it("shows Running badge for active backups", () => {
      resetStore({ backupHistory: [mockBackups[3]] });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Running")).toBeDefined();
    });

    it("shows Queued badge for queued backups", () => {
      resetStore({ backupHistory: [mockBackups[4]] });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Queued")).toBeDefined();
    });
  });

  describe("Type badges", () => {
    it("shows Manual badge for manual backups", () => {
      resetStore({ backupHistory: [mockBackups[0]] });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Manual")).toBeDefined();
    });

    it("shows Scheduled badge for scheduled backups", () => {
      resetStore({ backupHistory: [mockBackups[1]] });

      render(<BackupHistoryTable />);

      expect(screen.getByText("Scheduled")).toBeDefined();
    });
  });

  describe("Data display", () => {
    it("displays file size for completed backups", () => {
      resetStore({ backupHistory: [mockBackups[0]] });

      render(<BackupHistoryTable />);

      // 536870912 bytes = 512 MB
      expect(screen.getByText("512.00 MB")).toBeDefined();
    });

    it("displays duration for completed backups", () => {
      resetStore({ backupHistory: [mockBackups[0]] });

      render(<BackupHistoryTable />);

      // 330 seconds = 5m 30s
      expect(screen.getByText("5m 30s")).toBeDefined();
    });

    it("displays dash for null file size", () => {
      resetStore({ backupHistory: [mockBackups[3]] });

      const { container } = render(<BackupHistoryTable />);

      // Running backup has null file_size_bytes
      const cells = container.querySelectorAll("td");
      const sizeCell = cells[3]; // Size column
      expect(sizeCell.textContent).toBe("—");
    });

    it("displays error message for failed backups", () => {
      resetStore({ backupHistory: [mockBackups[2]] });

      render(<BackupHistoryTable />);

      expect(screen.getByText("pg_dump: connection refused")).toBeDefined();
    });
  });
});
