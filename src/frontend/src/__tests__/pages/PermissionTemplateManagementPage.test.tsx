import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Tests for PermissionTemplateManagementPage rendering and delete guard UI.
 *
 * Validates: Requirements 4.1–4.5
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
    constructor(status: number, body: string, url: string = "/api/admin/permission-templates") {
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
import { PermissionTemplateManagementPage } from "../../pages/PermissionTemplateManagementPage";
import type { PermissionTemplate } from "../../types/admin";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockTemplates: PermissionTemplate[] = [
  {
    id: 1,
    name: "Internal SOP",
    description: "Standard operating procedures",
    document_type: "SOP",
    role_permissions: {
      system_admin: ["read", "write", "approve"],
      doc_admin: ["read", "write", "approve"],
      member: ["read"],
      viewer: ["read"],
    },
    is_default: true,
    created_by: 1,
    created_at: "2024-01-01T00:00:00Z",
    active_document_count: 5,
  },
  {
    id: 2,
    name: "External Supplier File",
    description: "Supplier documentation",
    document_type: "Supplier",
    role_permissions: {
      system_admin: ["read", "write", "approve"],
      doc_admin: ["read", "approve"],
    },
    is_default: true,
    created_by: 1,
    created_at: "2024-01-01T00:00:00Z",
    active_document_count: 0,
  },
  {
    id: 3,
    name: "Custom Protocol",
    description: "Custom protocol template",
    document_type: "Protocol",
    role_permissions: {
      system_admin: ["read", "write", "approve"],
      doc_admin: ["read", "write"],
      member: ["read"],
    },
    is_default: false,
    created_by: 1,
    created_at: "2024-02-15T00:00:00Z",
    active_document_count: 3,
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
    fetchPermissionTemplates: vi.fn().mockResolvedValue(undefined),
    deletePermissionTemplate: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useAdminStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PermissionTemplateManagementPage", () => {
  beforeEach(() => {
    resetStore({ permissionTemplates: mockTemplates });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders page heading and description", () => {
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByText("Permission Templates")).toBeDefined();
      expect(screen.getByText("Manage document-type permission templates for role-based access")).toBeDefined();
    });

    it("renders Create Template button", () => {
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByText("Create Template")).toBeDefined();
    });

    it("renders template table with all templates", () => {
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByText("Internal SOP")).toBeDefined();
      expect(screen.getByText("External Supplier File")).toBeDefined();
      expect(screen.getByText("Custom Protocol")).toBeDefined();
    });

    it("displays document type for each template", () => {
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByText("SOP")).toBeDefined();
      expect(screen.getByText("Supplier")).toBeDefined();
      expect(screen.getByText("Protocol")).toBeDefined();
    });

    it("displays active document count", () => {
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByText("5")).toBeDefined();
      expect(screen.getByText("0")).toBeDefined();
      expect(screen.getByText("3")).toBeDefined();
    });

    it("shows Default badge for default templates", () => {
      render(<PermissionTemplateManagementPage />);

      const defaultBadges = screen.getAllByText("Default");
      expect(defaultBadges.length).toBe(2);
    });

    it("renders edit buttons for each template", () => {
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByLabelText("Edit template Internal SOP")).toBeDefined();
      expect(screen.getByLabelText("Edit template External Supplier File")).toBeDefined();
      expect(screen.getByLabelText("Edit template Custom Protocol")).toBeDefined();
    });
  });

  describe("Delete guard UI (Requirement 4.4)", () => {
    it("disables delete button for templates with active documents", () => {
      render(<PermissionTemplateManagementPage />);

      // Internal SOP has 5 active documents — delete should be disabled
      const deleteButton = screen.getByLabelText(
        "Cannot delete template Internal SOP — it has active documents"
      );
      expect(deleteButton.hasAttribute("disabled")).toBe(true);
    });

    it("enables delete button for templates with no active documents", () => {
      render(<PermissionTemplateManagementPage />);

      // External Supplier File has 0 active documents — delete should be enabled
      const deleteButton = screen.getByLabelText("Delete template External Supplier File");
      expect(deleteButton.hasAttribute("disabled")).toBe(false);
    });

    it("disables delete for Custom Protocol with 3 active documents", () => {
      render(<PermissionTemplateManagementPage />);

      const deleteButton = screen.getByLabelText(
        "Cannot delete template Custom Protocol — it has active documents"
      );
      expect(deleteButton.hasAttribute("disabled")).toBe(true);
    });
  });

  describe("Empty state", () => {
    it("shows empty state when no templates exist", () => {
      resetStore({ permissionTemplates: [] });
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByText("No permission templates yet.")).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("shows error banner when error is set", () => {
      resetStore({ permissionTemplates: [], error: "Failed to fetch templates" });
      render(<PermissionTemplateManagementPage />);

      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText("Failed to fetch templates")).toBeDefined();
    });
  });

  describe("Dialog interaction", () => {
    it("opens create dialog when Create Template is clicked", () => {
      render(<PermissionTemplateManagementPage />);

      fireEvent.click(screen.getByText("Create Template"));

      expect(screen.getByRole("dialog")).toBeDefined();
      expect(screen.getByText("Create Permission Template")).toBeDefined();
    });

    it("opens edit dialog when edit button is clicked", () => {
      render(<PermissionTemplateManagementPage />);

      fireEvent.click(screen.getByLabelText("Edit template Internal SOP"));

      expect(screen.getByRole("dialog")).toBeDefined();
      expect(screen.getByText("Edit Permission Template")).toBeDefined();
    });
  });
});
