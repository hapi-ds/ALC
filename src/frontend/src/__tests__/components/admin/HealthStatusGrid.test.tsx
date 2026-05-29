import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Tests for HealthStatusGrid color-coded indicators.
 *
 * Validates: Requirements 10.3, 11.1–11.6
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
import { HealthStatusGrid } from "../../../components/admin/HealthStatusGrid";
import type { ServiceHealthStatus } from "../../../types/systemConfig";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockHealthyService: ServiceHealthStatus = {
  service_name: "postgresql",
  status: "healthy",
  response_time_ms: 12.5,
  last_checked: "2024-06-15T10:30:00Z",
  uptime_pct_24h: 99.9,
  avg_response_time_5min: 15.2,
};

const mockDegradedService: ServiceHealthStatus = {
  service_name: "opensearch",
  status: "degraded",
  response_time_ms: 6500,
  last_checked: "2024-06-15T10:30:00Z",
  uptime_pct_24h: 95.5,
  avg_response_time_5min: 5800,
};

const mockUnreachableService: ServiceHealthStatus = {
  service_name: "vllm",
  status: "unreachable",
  response_time_ms: null,
  last_checked: "2024-06-15T10:30:00Z",
  uptime_pct_24h: 85.0,
  avg_response_time_5min: null,
};

const allServices: ServiceHealthStatus[] = [
  mockHealthyService,
  {
    service_name: "minio",
    status: "healthy",
    response_time_ms: 8.3,
    last_checked: "2024-06-15T10:30:00Z",
    uptime_pct_24h: 100.0,
    avg_response_time_5min: 9.1,
  },
  mockDegradedService,
  {
    service_name: "redis",
    status: "healthy",
    response_time_ms: 1.2,
    last_checked: "2024-06-15T10:30:00Z",
    uptime_pct_24h: 100.0,
    avg_response_time_5min: 1.5,
  },
  mockUnreachableService,
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore(overrides: Partial<ReturnType<typeof useSystemConfigStore.getState>> = {}) {
  useSystemConfigStore.setState({
    healthStatus: [],
    loading: {},
    errors: {},
    fetchHealthStatus: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useSystemConfigStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("HealthStatusGrid", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Loading state", () => {
    it("shows loading skeleton when loading and no data", () => {
      resetStore({ loading: { healthStatus: true } });

      render(<HealthStatusGrid />);

      expect(screen.getByLabelText("Loading health status")).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("shows error alert when fetch fails", () => {
      resetStore({
        errors: { healthStatus: "Health check service unavailable" },
      });

      render(<HealthStatusGrid />);

      expect(screen.getByText("Failed to load health status")).toBeDefined();
      expect(screen.getByText("Health check service unavailable")).toBeDefined();
    });

    it("shows Retry button on error", () => {
      resetStore({
        errors: { healthStatus: "Health check service unavailable" },
      });

      render(<HealthStatusGrid />);

      expect(screen.getByText("Retry")).toBeDefined();
    });

    it("calls fetchHealthStatus when Retry is clicked", () => {
      const mockFetch = vi.fn().mockResolvedValue(undefined);
      resetStore({
        errors: { healthStatus: "Health check service unavailable" },
        fetchHealthStatus: mockFetch,
      });

      render(<HealthStatusGrid />);
      fireEvent.click(screen.getByText("Retry"));

      expect(mockFetch).toHaveBeenCalled();
    });
  });

  describe("Empty state", () => {
    it("shows empty message when no health data", () => {
      resetStore({ healthStatus: [] });

      render(<HealthStatusGrid />);

      expect(screen.getByText("No health status data available.")).toBeDefined();
    });
  });

  describe("Grid rendering", () => {
    it("renders all service cards", () => {
      resetStore({ healthStatus: allServices });

      render(<HealthStatusGrid />);

      expect(screen.getByText("postgresql")).toBeDefined();
      expect(screen.getByText("minio")).toBeDefined();
      expect(screen.getByText("opensearch")).toBeDefined();
      expect(screen.getByText("redis")).toBeDefined();
      expect(screen.getByText("vllm")).toBeDefined();
    });

    it("renders grid with correct role and label", () => {
      resetStore({ healthStatus: allServices });

      render(<HealthStatusGrid />);

      expect(
        screen.getByRole("list", { name: "Service health status" })
      ).toBeDefined();
    });
  });

  describe("Color-coded status indicators", () => {
    it("shows Healthy badge for healthy services", () => {
      resetStore({ healthStatus: [mockHealthyService] });

      render(<HealthStatusGrid />);

      expect(screen.getByText("Healthy")).toBeDefined();
    });

    it("shows Degraded badge for degraded services", () => {
      resetStore({ healthStatus: [mockDegradedService] });

      render(<HealthStatusGrid />);

      expect(screen.getByText("Degraded")).toBeDefined();
    });

    it("shows Unreachable badge for unreachable services", () => {
      resetStore({ healthStatus: [mockUnreachableService] });

      render(<HealthStatusGrid />);

      expect(screen.getByText("Unreachable")).toBeDefined();
    });

    it("applies green border for healthy services", () => {
      resetStore({ healthStatus: [mockHealthyService] });

      render(<HealthStatusGrid />);

      const card = screen.getByLabelText("postgresql health status: healthy");
      expect(card.className).toContain("border-green-200");
    });

    it("applies yellow border for degraded services", () => {
      resetStore({ healthStatus: [mockDegradedService] });

      render(<HealthStatusGrid />);

      const card = screen.getByLabelText("opensearch health status: degraded");
      expect(card.className).toContain("border-yellow-200");
    });

    it("applies red border for unreachable services", () => {
      resetStore({ healthStatus: [mockUnreachableService] });

      render(<HealthStatusGrid />);

      const card = screen.getByLabelText("vllm health status: unreachable");
      expect(card.className).toContain("border-red-200");
    });
  });

  describe("Service metrics display", () => {
    it("displays uptime percentage", () => {
      resetStore({ healthStatus: [mockHealthyService] });

      render(<HealthStatusGrid />);

      expect(screen.getByText("99.9%")).toBeDefined();
      expect(screen.getByText("Uptime (24h)")).toBeDefined();
    });

    it("displays average response time", () => {
      resetStore({ healthStatus: [mockHealthyService] });

      render(<HealthStatusGrid />);

      expect(screen.getByText("15ms")).toBeDefined();
      expect(screen.getByText("Avg Response (5min)")).toBeDefined();
    });

    it("displays dash for null response time", () => {
      resetStore({ healthStatus: [mockUnreachableService] });

      render(<HealthStatusGrid />);

      // Unreachable service has null avg_response_time_5min
      expect(screen.getByText("—")).toBeDefined();
    });

    it("displays last checked timestamp", () => {
      resetStore({ healthStatus: [mockHealthyService] });

      render(<HealthStatusGrid />);

      expect(screen.getByText("Last Checked")).toBeDefined();
    });
  });
});
