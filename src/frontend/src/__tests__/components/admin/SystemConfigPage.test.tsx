import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import React from "react";

/**
 * Tests for SystemConfigPage tab navigation.
 *
 * Validates: Requirements 2.1, 5.1, 7.4, 9.2, 10.3, 11.1, 12.1, 14.4
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

const mockSetSearchParams = vi.fn();
let mockSearchParams = new URLSearchParams();

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}));

// Mock child components to isolate SystemConfigPage tests
vi.mock("../../../components/admin/BackupScheduleForm", () => ({
  BackupScheduleForm: () => <div data-testid="backup-schedule-form">BackupScheduleForm</div>,
}));

vi.mock("../../../components/admin/BackupHistoryTable", () => ({
  BackupHistoryTable: () => <div data-testid="backup-history-table">BackupHistoryTable</div>,
}));

vi.mock("../../../components/admin/BackupTriggerButton", () => ({
  BackupTriggerButton: () => <div data-testid="backup-trigger-button">BackupTriggerButton</div>,
}));

vi.mock("../../../components/admin/StorageUsageList", () => ({
  StorageUsageList: () => <div data-testid="storage-usage-list">StorageUsageList</div>,
}));

vi.mock("../../../components/admin/QuotaEditForm", () => ({
  QuotaEditForm: () => <div data-testid="quota-edit-form">QuotaEditForm</div>,
}));

vi.mock("../../../components/admin/HealthStatusGrid", () => ({
  HealthStatusGrid: () => <div data-testid="health-status-grid">HealthStatusGrid</div>,
}));

vi.mock("../../../components/admin/HealthConfigForm", () => ({
  HealthConfigForm: () => <div data-testid="health-config-form">HealthConfigForm</div>,
}));

vi.mock("../../../components/admin/ServiceInfoList", () => ({
  ServiceInfoList: () => <div data-testid="service-info-list">ServiceInfoList</div>,
}));

vi.mock("../../../components/admin/ResourceUtilizationCharts", () => ({
  ResourceUtilizationCharts: () => <div data-testid="resource-charts">ResourceUtilizationCharts</div>,
}));

vi.mock("../../../components/admin/SnapshotHistoryList", () => ({
  SnapshotHistoryList: () => <div data-testid="snapshot-history-list">SnapshotHistoryList</div>,
}));

import { useSystemConfigStore } from "../../../stores/useSystemConfigStore";
import { SystemConfigPage } from "../../../pages/admin/SystemConfigPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
  useSystemConfigStore.setState({
    storageUsage: [],
    storageTotals: null,
    loading: {},
    errors: {},
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SystemConfigPage", () => {
  beforeEach(() => {
    resetStore();
    mockSearchParams = new URLSearchParams();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Page rendering", () => {
    it("renders the page header", () => {
      render(<SystemConfigPage />);

      expect(screen.getByText("System Configuration")).toBeDefined();
      expect(
        screen.getByText(
          "Manage AI hardware, storage quotas, backups, health monitoring, and services"
        )
      ).toBeDefined();
    });

    it("renders the main landmark with correct aria-label", () => {
      render(<SystemConfigPage />);

      const main = screen.getByRole("main", { name: "System Configuration" });
      expect(main).toBeDefined();
    });
  });

  describe("Tab navigation", () => {
    it("renders all six tab triggers", () => {
      render(<SystemConfigPage />);

      expect(screen.getByText("AI Settings")).toBeDefined();
      expect(screen.getByText("Storage")).toBeDefined();
      expect(screen.getByText("Backups")).toBeDefined();
      expect(screen.getByText("Health")).toBeDefined();
      expect(screen.getByText("Services")).toBeDefined();
      expect(screen.getByText("History")).toBeDefined();
    });

    it("defaults to AI Settings tab when no tab param", () => {
      render(<SystemConfigPage />);

      expect(screen.getByText("AI Hardware Settings")).toBeDefined();
    });

    it("shows Storage tab content when tab=storage param is set", () => {
      mockSearchParams = new URLSearchParams("tab=storage");
      render(<SystemConfigPage />);

      expect(screen.getByText("Storage & Quotas")).toBeDefined();
    });

    it("shows Backups tab content when tab=backups param is set", () => {
      mockSearchParams = new URLSearchParams("tab=backups");
      render(<SystemConfigPage />);

      expect(screen.getByText("Backup Configuration")).toBeDefined();
    });

    it("shows Health tab content when tab=health param is set", () => {
      mockSearchParams = new URLSearchParams("tab=health");
      render(<SystemConfigPage />);

      expect(screen.getByText("System Health")).toBeDefined();
    });

    it("shows Services tab content when tab=services param is set", () => {
      mockSearchParams = new URLSearchParams("tab=services");
      render(<SystemConfigPage />);

      expect(screen.getByText("Service Status")).toBeDefined();
    });

    it("shows History tab content when tab=history param is set", () => {
      mockSearchParams = new URLSearchParams("tab=history");
      render(<SystemConfigPage />);

      expect(screen.getByText("Configuration History")).toBeDefined();
    });

    it("defaults to AI Settings for invalid tab param", () => {
      mockSearchParams = new URLSearchParams("tab=invalid-tab");
      render(<SystemConfigPage />);

      expect(screen.getByText("AI Hardware Settings")).toBeDefined();
    });
  });
});
