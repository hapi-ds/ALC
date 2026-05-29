import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Tests for RoleManagementPage rendering, role selection, system role distinction.
 *
 * Validates: Requirements 10.1–10.4
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../lib/apiClient", () => ({
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
    constructor(status: number, body: string, url: string = "/api/admin/roles") {
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

vi.mock("../../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (state: unknown) => unknown) => {
      const state = {
        user: { id: 1, username: "admin", email: "admin@test.com", full_name: "Admin User", roles: ["admin"] },
        isAuthenticated: true,
        activeCompanyId: 1,
      };
      if (selector) return selector(state);
      return state;
    }),
    { getState: () => ({ user: { id: 1 }, activeCompanyId: 1 }) }
  ),
}));

import { useAdminStore } from "../../stores/adminStore";
import { RoleManagementPage } from "../../pages/RoleManagementPage";
import type { RoleWithCount, RoleDetail } from "../../types/admin";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockRoles: RoleWithCount[] = [
  { id: 1, name: "system_admin", description: "Full system access", is_system: true, user_count: 2 },
  { id: 2, name: "doc_admin", description: "Document management", is_system: true, user_count: 5 },
  { id: 3, name: "it_admin", description: "IT infrastructure", is_system: true, user_count: 1 },
  { id: 4, name: "member", description: "Standard member", is_system: true, user_count: 15 },
  { id: 5, name: "viewer", description: "Read-only access", is_system: true, user_count: 8 },
];

const mockRoleDetail: RoleDetail = {
  id: 1,
  name: "system_admin",
  description: "Full system access",
  is_system: true,
  permissions: {
    documents: ["create", "read", "update", "delete", "approve"],
    workflows: ["create", "read", "update", "delete", "approve"],
    users: ["create", "read", "update", "delete", "approve"],
    audit_logs: ["create", "read", "update", "delete", "approve"],
    templates: ["create", "read", "update", "delete", "approve"],
    training: ["create", "read", "update", "delete", "approve"],
    signatures: ["create", "read", "update", "delete", "approve"],
    system_config: ["create", "read", "update", "delete", "approve"],
  },
  user_count: 2,
};

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
    fetchRoles: vi.fn().mockResolvedValue(undefined),
    fetchRoleDetail: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useAdminStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("RoleManagementPage", () => {
  beforeEach(() => {
    resetStore({ roles: mockRoles });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering (Requirement 10.1)", () => {
    it("renders page heading and description", () => {
      render(<RoleManagementPage />);

      expect(screen.getByText("Role Management")).toBeDefined();
      expect(screen.getByText("View roles and their permission assignments")).toBeDefined();
    });

    it("renders all roles with their labels", () => {
      render(<RoleManagementPage />);

      expect(screen.getByText("System Admin")).toBeDefined();
      expect(screen.getByText("Document Admin")).toBeDefined();
      expect(screen.getByText("IT Admin")).toBeDefined();
      expect(screen.getByText("Member")).toBeDefined();
      expect(screen.getByText("Viewer")).toBeDefined();
    });

    it("displays role descriptions", () => {
      render(<RoleManagementPage />);

      expect(screen.getByText("Full system access")).toBeDefined();
      expect(screen.getByText("Document management")).toBeDefined();
    });

    it("displays user count for each role (Requirement 10.3)", () => {
      render(<RoleManagementPage />);

      expect(screen.getByText("2 users")).toBeDefined();
      expect(screen.getByText("5 users")).toBeDefined();
      expect(screen.getByText("1 user")).toBeDefined();
      expect(screen.getByText("15 users")).toBeDefined();
      expect(screen.getByText("8 users")).toBeDefined();
    });
  });

  describe("System role distinction (Requirement 10.4)", () => {
    it("shows System badge for system-defined roles", () => {
      render(<RoleManagementPage />);

      const systemBadges = screen.getAllByText("System");
      expect(systemBadges.length).toBe(5);
    });
  });

  describe("Role selection (Requirement 10.2)", () => {
    it("shows placeholder when no role is selected", () => {
      render(<RoleManagementPage />);

      expect(screen.getByText("Select a role to view its permission matrix")).toBeDefined();
    });

    it("shows permission matrix when a role is selected", () => {
      resetStore({ roles: mockRoles, currentRole: mockRoleDetail });
      render(<RoleManagementPage />);

      // Click on System Admin role
      const roleButton = screen.getByLabelText("Select role System Admin");
      fireEvent.click(roleButton);

      // Permission matrix should be visible
      expect(screen.getByLabelText("Permission matrix for system_admin")).toBeDefined();
    });

    it("marks selected role with aria-pressed", () => {
      resetStore({ roles: mockRoles, currentRole: mockRoleDetail });
      render(<RoleManagementPage />);

      const roleButton = screen.getByLabelText("Select role System Admin");
      fireEvent.click(roleButton);

      expect(roleButton.getAttribute("aria-pressed")).toBe("true");
    });

    it("shows non-editable message for system roles", () => {
      resetStore({ roles: mockRoles, currentRole: mockRoleDetail });
      render(<RoleManagementPage />);

      const roleButton = screen.getByLabelText("Select role System Admin");
      fireEvent.click(roleButton);

      expect(screen.getByText(/permissions cannot be modified/)).toBeDefined();
    });
  });

  describe("Empty state", () => {
    it("shows empty state when no roles exist", () => {
      resetStore({ roles: [] });
      render(<RoleManagementPage />);

      expect(screen.getByText("No roles found.")).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("shows error banner when error is set", () => {
      resetStore({ roles: [], error: "Failed to fetch roles" });
      render(<RoleManagementPage />);

      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText("Failed to fetch roles")).toBeDefined();
    });
  });
});
