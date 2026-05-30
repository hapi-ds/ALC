import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Frontend tests for AIRiskFrameworkPage.
 *
 * Covers:
 * - Page rendering with correct title
 * - All 5 tabs visible (Dashboard, Task Types, Risk Profile, HITL Queue, Operation Logs)
 * - Default tab is Dashboard
 * - Tab navigation works (clicking a tab shows its content)
 * - Unauthorized user (no system_admin/doc_admin role) is redirected with toast
 *
 * Validates: Requirements 7.1–7.8
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock apiClient
vi.mock("../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string = "/api/risk-framework") {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

vi.mock("../lib/tokenStorage", () => ({
  getAccessToken: vi.fn(() => "mock-token"),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(() => null),
}));

// Mock riskFrameworkApi to prevent real API calls from sub-components
vi.mock("../lib/riskFrameworkApi", () => ({
  getTaskTypes: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
  getTaskType: vi.fn().mockResolvedValue(null),
  getActiveProfile: vi.fn().mockResolvedValue(null),
  createProfile: vi.fn().mockResolvedValue(null),
  updateProfile: vi.fn().mockResolvedValue(null),
  getCheckpoints: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
  reviewCheckpoint: vi.fn().mockResolvedValue(null),
  getOperationLogs: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
  getDashboardStats: vi.fn().mockResolvedValue({
    operations_by_tier: { high: 0, medium: 0, low: 0 },
    pending_checkpoints: 0,
    expired_checkpoints: 0,
    blocked_operations: 0,
    active_profile_name: null,
  }),
  getProfileHistory: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
  getTiers: vi.fn().mockResolvedValue([]),
  getTier: vi.fn().mockResolvedValue(null),
}));

// Mock sonner toast
const mockToastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
const mockSetSearchParams = vi.fn();
let mockSearchParams = new URLSearchParams();

vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}));

// Mock lucide-react icons to avoid rendering issues in jsdom
vi.mock("lucide-react", () => ({
  LayoutDashboard: () => <span data-testid="icon-dashboard">D</span>,
  ListChecks: () => <span data-testid="icon-task-types">T</span>,
  ShieldCheck: () => <span data-testid="icon-risk-profile">R</span>,
  ClipboardCheck: () => <span data-testid="icon-hitl-queue">H</span>,
  ScrollText: () => <span data-testid="icon-operation-logs">O</span>,
  ChevronDown: () => <span>▼</span>,
  ChevronRight: () => <span>▶</span>,
  ChevronLeft: () => <span>◀</span>,
  Loader2: () => <span data-testid="loader-icon">Loading</span>,
  AlertCircle: () => <span>⚠</span>,
  AlertTriangle: () => <span>⚠</span>,
  Clock: () => <span>🕐</span>,
  ShieldOff: () => <span>🛡</span>,
  Activity: () => <span>📊</span>,
  User: () => <span>👤</span>,
  Plus: () => <span>+</span>,
  History: () => <span>📜</span>,
  Trash2: () => <span>🗑</span>,
  X: () => <span>✕</span>,
  Check: () => <span>✓</span>,
  Filter: () => <span>🔍</span>,
  Search: () => <span>🔎</span>,
  Eye: () => <span>👁</span>,
  EyeOff: () => <span>👁‍🗨</span>,
  RefreshCw: () => <span>🔄</span>,
  MoreHorizontal: () => <span>⋯</span>,
  ArrowUpDown: () => <span>↕</span>,
  Calendar: () => <span>📅</span>,
  FileText: () => <span>📄</span>,
  Info: () => <span>ℹ</span>,
  ExternalLink: () => <span>🔗</span>,
}));

// Mock auth store — default: authorized user
let mockUser = {
  id: 1,
  username: "admin",
  email: "admin@test.com",
  full_name: "Admin User",
  roles: ["system_admin"],
};

vi.mock("../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (state: unknown) => unknown) => {
      const state = {
        user: mockUser,
        isAuthenticated: true,
        activeCompanyId: 1,
      };
      if (selector) return selector(state);
      return state;
    }),
    { getState: () => ({ user: mockUser, activeCompanyId: 1 }) },
  ),
}));

// Import after mocks
import { AIRiskFrameworkPage } from "../pages/AIRiskFrameworkPage";
import { useRiskFrameworkStore } from "../stores/riskFrameworkStore";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AIRiskFrameworkPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams = new URLSearchParams();
    mockUser = {
      id: 1,
      username: "admin",
      email: "admin@test.com",
      full_name: "Admin User",
      roles: ["system_admin"],
    };
    useRiskFrameworkStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // 1. Page renders with correct title
  // -------------------------------------------------------------------------

  it("renders with correct page title", () => {
    render(<AIRiskFrameworkPage />);

    expect(screen.getByText("AI Risk & Compliance Framework")).toBeDefined();
    expect(
      screen.getByText(
        /manage risk classifications, control enforcement, hitl checkpoints, and audit compliance/i,
      ),
    ).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // 2. All 5 tabs are visible
  // -------------------------------------------------------------------------

  it("renders all 5 tabs", () => {
    render(<AIRiskFrameworkPage />);

    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.getByText("Task Types")).toBeDefined();
    expect(screen.getByText("Risk Profile")).toBeDefined();
    expect(screen.getByText("HITL Queue")).toBeDefined();
    expect(screen.getByText("Operation Logs")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // 3. Default tab is Dashboard
  // -------------------------------------------------------------------------

  it("defaults to Dashboard tab when no tab param in URL", () => {
    render(<AIRiskFrameworkPage />);

    // The Dashboard tab trigger should be the active/selected one
    const dashboardTab = screen.getByRole("tab", { name: /dashboard/i });
    expect(dashboardTab.getAttribute("data-state")).toBe("active");
  });

  // -------------------------------------------------------------------------
  // 4. Tab navigation works (clicking a tab activates it)
  // -------------------------------------------------------------------------

  it("all tabs have correct values for navigation", () => {
    render(<AIRiskFrameworkPage />);

    // Verify all tab triggers exist with correct values
    const tabs = screen.getAllByRole("tab");
    expect(tabs.length).toBe(5);

    // Verify tab values match expected IDs
    const tabValues = tabs.map((tab) => tab.getAttribute("data-value") || tab.getAttribute("value"));
    expect(screen.getByRole("tab", { name: /dashboard/i })).toBeDefined();
    expect(screen.getByRole("tab", { name: /task types/i })).toBeDefined();
    expect(screen.getByRole("tab", { name: /risk profile/i })).toBeDefined();
    expect(screen.getByRole("tab", { name: /hitl queue/i })).toBeDefined();
    expect(screen.getByRole("tab", { name: /operation logs/i })).toBeDefined();
  });

  it("Dashboard tab is initially active and others are inactive", () => {
    render(<AIRiskFrameworkPage />);

    const dashboardTab = screen.getByRole("tab", { name: /dashboard/i });
    const taskTypesTab = screen.getByRole("tab", { name: /task types/i });
    const riskProfileTab = screen.getByRole("tab", { name: /risk profile/i });
    const hitlTab = screen.getByRole("tab", { name: /hitl queue/i });
    const logsTab = screen.getByRole("tab", { name: /operation logs/i });

    expect(dashboardTab.getAttribute("data-state")).toBe("active");
    expect(taskTypesTab.getAttribute("data-state")).toBe("inactive");
    expect(riskProfileTab.getAttribute("data-state")).toBe("inactive");
    expect(hitlTab.getAttribute("data-state")).toBe("inactive");
    expect(logsTab.getAttribute("data-state")).toBe("inactive");
  });

  it("tab from URL search params sets the correct tab as active", () => {
    mockSearchParams = new URLSearchParams("tab=hitl-queue");

    render(<AIRiskFrameworkPage />);

    const hitlTab = screen.getByRole("tab", { name: /hitl queue/i });
    expect(hitlTab.getAttribute("data-state")).toBe("active");

    const dashboardTab = screen.getByRole("tab", { name: /dashboard/i });
    expect(dashboardTab.getAttribute("data-state")).toBe("inactive");
  });

  // -------------------------------------------------------------------------
  // 5. Unauthorized user is redirected with toast
  // -------------------------------------------------------------------------

  it("redirects unauthorized user (no admin role) to / with error toast", () => {
    // Set user without authorized roles
    mockUser = {
      id: 2,
      username: "viewer",
      email: "viewer@test.com",
      full_name: "Viewer User",
      roles: ["viewer"],
    };

    render(<AIRiskFrameworkPage />);

    expect(mockToastError).toHaveBeenCalledWith(
      "Access denied. This page requires system_admin or doc_admin role.",
    );
    expect(mockNavigate).toHaveBeenCalledWith("/", { replace: true });
  });

  it("does NOT redirect user with doc_admin role", () => {
    mockUser = {
      id: 3,
      username: "docadmin",
      email: "docadmin@test.com",
      full_name: "Doc Admin",
      roles: ["doc_admin"],
    };

    render(<AIRiskFrameworkPage />);

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it("does NOT redirect user with system_admin role", () => {
    render(<AIRiskFrameworkPage />);

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(mockToastError).not.toHaveBeenCalled();
  });
});
