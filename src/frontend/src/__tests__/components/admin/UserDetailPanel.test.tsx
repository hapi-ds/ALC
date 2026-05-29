import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Tests for UserDetailPanel rendering, action buttons, self-deactivation prevention.
 *
 * Validates: Requirements 8.1–8.6, 9.3
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    url: string;
    constructor(status: number, body: string, url: string = "/api/admin/users") {
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

const mockAuthUser = { id: 1, username: "admin", email: "admin@test.com", full_name: "Admin User", roles: ["admin"] };

vi.mock("../../../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (state: unknown) => unknown) => {
      const state = {
        user: mockAuthUser,
        isAuthenticated: true,
        activeCompanyId: 1,
      };
      if (selector) return selector(state);
      return state;
    }),
    { getState: () => ({ user: mockAuthUser, activeCompanyId: 1 }) }
  ),
}));

import { useAdminStore } from "../../../stores/adminStore";
import { UserDetailPanel } from "../../../components/admin/UserDetailPanel";
import type { UserDetail, UserHistoryEntry } from "../../../types/admin";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockUserDetail: UserDetail = {
  id: 5,
  username: "john.doe",
  email: "john@example.com",
  full_name: "John Doe",
  is_active: true,
  created_at: "2024-01-15T10:00:00Z",
  memberships: [
    {
      id: 1,
      company_id: 1,
      company_name: "Acme Corp",
      role: "member",
      created_at: "2024-01-15T10:00:00Z",
      revoked_at: null,
    },
    {
      id: 2,
      company_id: 2,
      company_name: "Beta Inc",
      role: "viewer",
      created_at: "2024-02-01T10:00:00Z",
      revoked_at: "2024-03-01T10:00:00Z",
    },
  ],
};

const mockHistory: UserHistoryEntry[] = [
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
// Helpers
// ---------------------------------------------------------------------------

function resetStore(overrides: Partial<ReturnType<typeof useAdminStore.getState>> = {}) {
  useAdminStore.setState({
    users: [],
    totalUsers: 0,
    currentUser: null,
    userHistory: [],
    roles: [],
    currentRole: null,
    permissionTemplates: [],
    currentTemplate: null,
    isLoading: false,
    error: null,
    searchQuery: "",
    sortField: "created_at",
    sortDirection: "desc",
    page: 1,
    pageSize: 20,
    // Override fetch actions to be no-ops so useEffect doesn't trigger loading
    fetchUserDetail: vi.fn().mockResolvedValue(undefined),
    fetchUserHistory: vi.fn().mockResolvedValue(undefined),
    deactivateUser: vi.fn().mockResolvedValue(undefined),
    reactivateUser: vi.fn().mockResolvedValue(undefined),
    resetPassword: vi.fn().mockResolvedValue("TempPass123"),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useAdminStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UserDetailPanel", () => {
  beforeEach(() => {
    resetStore({ currentUser: mockUserDetail, userHistory: mockHistory });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders the panel with user detail heading", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("User Details")).toBeDefined();
    });

    it("displays user full name and username", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("John Doe")).toBeDefined();
      expect(screen.getByText("@john.doe")).toBeDefined();
    });

    it("displays user email", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("john@example.com")).toBeDefined();
    });

    it("displays active status for active user", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      // The user info section shows "Active" status
      const activeTexts = screen.getAllByText("Active");
      expect(activeTexts.length).toBeGreaterThan(0);
    });

    it("displays deactivated status for inactive user", () => {
      resetStore({
        currentUser: { ...mockUserDetail, is_active: false },
        userHistory: mockHistory,
      });

      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("Deactivated")).toBeDefined();
    });

    it("displays company memberships", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("Acme Corp")).toBeDefined();
      expect(screen.getByText("Beta Inc")).toBeDefined();
    });

    it("shows revoked status for revoked memberships", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      // Active membership
      const activeLabels = screen.getAllByText("Active");
      expect(activeLabels.length).toBeGreaterThan(0);

      // Revoked membership shows revoked date
      expect(screen.getByText(/Revoked:/)).toBeDefined();
    });

    it("shows loading skeleton when loading and no user", () => {
      resetStore({ currentUser: null, isLoading: true });

      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByLabelText("User detail panel")).toBeDefined();
    });
  });

  describe("Action buttons", () => {
    it("renders Edit button", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("Edit")).toBeDefined();
    });

    it("renders Deactivate button for active user", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("Deactivate")).toBeDefined();
    });

    it("renders Reactivate button for inactive user", () => {
      resetStore({
        currentUser: { ...mockUserDetail, is_active: false },
        userHistory: mockHistory,
      });

      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("Reactivate")).toBeDefined();
    });

    it("renders Reset Password button", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("Reset Password")).toBeDefined();
    });

    it("calls onEdit when Edit button is clicked", () => {
      const onEdit = vi.fn();
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={onEdit} />);

      fireEvent.click(screen.getByText("Edit"));
      expect(onEdit).toHaveBeenCalledWith(mockUserDetail);
    });

    it("calls onClose when close button is clicked", () => {
      const onClose = vi.fn();
      render(<UserDetailPanel userId={5} onClose={onClose} onEdit={vi.fn()} />);

      fireEvent.click(screen.getByLabelText("Close panel"));
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("Self-deactivation prevention (Requirement 8.6)", () => {
    it("disables Deactivate button when viewing own account", () => {
      // Set currentUser to have same id as auth user (id: 1)
      resetStore({
        currentUser: { ...mockUserDetail, id: 1 },
        userHistory: mockHistory,
      });

      render(<UserDetailPanel userId={1} onClose={vi.fn()} onEdit={vi.fn()} />);

      const deactivateButton = screen.getByText("Deactivate").closest("button");
      expect(deactivateButton?.hasAttribute("disabled")).toBe(true);
    });

    it("shows self-deactivation warning message", () => {
      resetStore({
        currentUser: { ...mockUserDetail, id: 1 },
        userHistory: mockHistory,
      });

      render(<UserDetailPanel userId={1} onClose={vi.fn()} onEdit={vi.fn()} />);

      expect(screen.getByText("You cannot deactivate your own account.")).toBeDefined();
    });

    it("enables Deactivate button when viewing another user", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      const deactivateButton = screen.getByText("Deactivate").closest("button");
      expect(deactivateButton?.hasAttribute("disabled")).toBe(false);
    });
  });

  describe("Action dialogs", () => {
    it("opens reason dialog when Deactivate is clicked", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      fireEvent.click(screen.getByText("Deactivate"));

      expect(screen.getByText("Deactivate User")).toBeDefined();
      expect(screen.getByLabelText("Reason")).toBeDefined();
    });

    it("opens reason dialog when Reset Password is clicked", () => {
      render(<UserDetailPanel userId={5} onClose={vi.fn()} onEdit={vi.fn()} />);

      fireEvent.click(screen.getByText("Reset Password"));

      // The reason dialog should appear with a title
      expect(screen.getByLabelText("Reason")).toBeDefined();
    });
  });
});
