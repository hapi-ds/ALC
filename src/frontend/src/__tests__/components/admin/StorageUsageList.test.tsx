import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Tests for StorageUsageList rendering with different quota statuses.
 *
 * Validates: Requirements 5.1–5.6
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
import { StorageUsageList } from "../../../components/admin/StorageUsageList";
import type { CompanyStorageUsage, StorageTotals } from "../../../types/systemConfig";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockCompanies: CompanyStorageUsage[] = [
  {
    company_id: 1,
    company_name: "Acme Pharma",
    usage_bytes: 5368709120, // ~5 GB
    human_readable: "5.00 GB",
    quota_status: "normal",
    quota_limit_bytes: 10737418240, // 10 GB
    alert_threshold_pct: 80,
  },
  {
    company_id: 2,
    company_name: "Beta Biotech",
    usage_bytes: 9126805504, // ~8.5 GB
    human_readable: "8.50 GB",
    quota_status: "quota_warning",
    quota_limit_bytes: 10737418240, // 10 GB
    alert_threshold_pct: 80,
  },
  {
    company_id: 3,
    company_name: "Gamma Labs",
    usage_bytes: 11811160064, // ~11 GB
    human_readable: "11.00 GB",
    quota_status: "quota_exceeded",
    quota_limit_bytes: 10737418240, // 10 GB
    alert_threshold_pct: 80,
  },
  {
    company_id: 4,
    company_name: "Delta Research",
    usage_bytes: 1073741824, // 1 GB
    human_readable: "1.00 GB",
    quota_status: "normal",
    quota_limit_bytes: null,
    alert_threshold_pct: null,
  },
];

const mockTotals: StorageTotals = {
  total_used_bytes: 27380416512,
  total_capacity_bytes: 107374182400,
  human_readable_used: "25.50 GB",
  human_readable_capacity: "100.00 GB",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore(overrides: Partial<ReturnType<typeof useSystemConfigStore.getState>> = {}) {
  useSystemConfigStore.setState({
    storageUsage: [],
    storageTotals: null,
    loading: {},
    errors: {},
    fetchStorageUsage: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useSystemConfigStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("StorageUsageList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Loading state", () => {
    it("shows loading skeleton when loading and no data", () => {
      resetStore({ loading: { storageUsage: true } });

      render(<StorageUsageList />);

      expect(screen.getByLabelText("Loading storage usage")).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("shows error alert when fetch fails", () => {
      resetStore({
        errors: { storageUsage: "MinIO connection timeout" },
      });

      render(<StorageUsageList />);

      expect(screen.getByText("Failed to load storage usage data")).toBeDefined();
      expect(screen.getByText("MinIO connection timeout")).toBeDefined();
    });

    it("shows Retry button on error", () => {
      resetStore({
        errors: { storageUsage: "MinIO connection timeout" },
      });

      render(<StorageUsageList />);

      expect(screen.getByText("Retry")).toBeDefined();
    });

    it("calls fetchStorageUsage when Retry is clicked", () => {
      const mockFetch = vi.fn().mockResolvedValue(undefined);
      resetStore({
        errors: { storageUsage: "MinIO connection timeout" },
        fetchStorageUsage: mockFetch,
      });

      render(<StorageUsageList />);
      fireEvent.click(screen.getByText("Retry"));

      expect(mockFetch).toHaveBeenCalled();
    });
  });

  describe("Empty state", () => {
    it("shows empty message when no companies", () => {
      resetStore({ storageUsage: [] });

      render(<StorageUsageList />);

      expect(screen.getByText("No company storage data available.")).toBeDefined();
    });
  });

  describe("Storage totals", () => {
    it("displays total storage used and capacity", () => {
      resetStore({
        storageUsage: mockCompanies,
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(screen.getByText("Total Storage")).toBeDefined();
      expect(screen.getByText("25.50 GB")).toBeDefined();
      expect(screen.getByText("100.00 GB")).toBeDefined();
    });
  });

  describe("Company list rendering", () => {
    it("renders all companies in the list", () => {
      resetStore({
        storageUsage: mockCompanies,
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(screen.getByText("Acme Pharma")).toBeDefined();
      expect(screen.getByText("Beta Biotech")).toBeDefined();
      expect(screen.getByText("Gamma Labs")).toBeDefined();
      expect(screen.getByText("Delta Research")).toBeDefined();
    });

    it("displays human-readable usage for each company", () => {
      resetStore({
        storageUsage: mockCompanies,
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(screen.getByText("5.00 GB")).toBeDefined();
      expect(screen.getByText("8.50 GB")).toBeDefined();
      expect(screen.getByText("11.00 GB")).toBeDefined();
      expect(screen.getByText("1.00 GB")).toBeDefined();
    });

    it("renders list with correct role", () => {
      resetStore({
        storageUsage: mockCompanies,
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(
        screen.getByRole("list", { name: "Company storage usage" })
      ).toBeDefined();
    });
  });

  describe("Quota status indicators", () => {
    it("shows Normal badge for companies within quota", () => {
      resetStore({
        storageUsage: [mockCompanies[0]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(screen.getByText("Normal")).toBeDefined();
    });

    it("shows Warning badge and indicator for companies exceeding threshold", () => {
      resetStore({
        storageUsage: [mockCompanies[1]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      // The badge text "Warning" appears in the status badge
      const warningElements = screen.getAllByText("Warning");
      expect(warningElements.length).toBeGreaterThanOrEqual(1);
    });

    it("shows Exceeded badge and indicator for companies over quota", () => {
      resetStore({
        storageUsage: [mockCompanies[2]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      // The badge text "Exceeded" appears in the status badge
      const exceededElements = screen.getAllByText("Exceeded");
      expect(exceededElements.length).toBeGreaterThanOrEqual(1);
    });

    it("shows No Quota badge for companies without quota", () => {
      resetStore({
        storageUsage: [mockCompanies[3]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(screen.getByText("No Quota")).toBeDefined();
    });
  });

  describe("Progress bars", () => {
    it("renders progress bar with correct percentage for companies with quota", () => {
      resetStore({
        storageUsage: [mockCompanies[0]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      // 5 GB / 10 GB = 50%
      expect(screen.getByText("50.0% of quota used")).toBeDefined();
    });

    it("shows No quota configured for companies without quota", () => {
      resetStore({
        storageUsage: [mockCompanies[3]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(screen.getByText("No quota configured")).toBeDefined();
    });

    it("shows alert threshold percentage when configured", () => {
      resetStore({
        storageUsage: [mockCompanies[0]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      expect(screen.getByText("Alert threshold: 80%")).toBeDefined();
    });

    it("renders disabled progress bar for no-quota companies", () => {
      resetStore({
        storageUsage: [mockCompanies[3]],
        storageTotals: mockTotals,
      });

      render(<StorageUsageList />);

      const progressbar = screen.getByRole("progressbar", {
        name: "Delta Research storage: no quota configured",
      });
      expect(progressbar).toBeDefined();
      expect(progressbar.getAttribute("aria-disabled")).toBe("true");
    });
  });
});
