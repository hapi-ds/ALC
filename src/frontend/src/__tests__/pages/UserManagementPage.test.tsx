import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Tests for UserManagementPage rendering, pagination, search, sort, empty states, loading skeletons.
 *
 * Validates: Requirements 5.1–5.5
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

vi.mock("../../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (state: unknown) => unknown) => {
      const state = {
        user: { id: 1, username: "admin", email: "admin@test.com", full_name: "Admin User", roles: ["admin"] },
        isAuthenticated: true,
        activeCompanyId: 1,
        activeCompanySlug: "test-company",
      };
      if (selector) return selector(state);
      return state;
    }),
    { getState: () => ({ user: { id: 1 }, activeCompanyId: 1 }) }
  ),
}));

import { useAdminStore } from "../../stores/adminStore";
import { UserManagementPage } from "../../pages/UserManagementPage";
import type { UserListItem } from "../../types/admin";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockUsers: UserListItem[] = [
  {
    id: 1,
    username: "john.doe",
    email: "john@example.com",
    full_name: "John Doe",
    role: "system_admin",
    is_active: true,
    created_at: "2024-01-15T10:00:00Z",
  },
  {
    id: 2,
    username: "jane.smith",
    email: "jane@example.com",
    full_name: "Jane Smith",
    role: "doc_admin",
    is_active: true,
    created_at: "2024-02-20T14:30:00Z",
  },
  {
    id: 3,
    username: "bob.inactive",
    email: "bob@example.com",
    full_name: "Bob Inactive",
    role: "viewer",
    is_active: false,
    created_at: "2024-03-01T09:00:00Z",
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
    // Override fetchUsers to be a no-op so useEffect doesn't trigger loading
    fetchUsers: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useAdminStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UserManagementPage", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders the page heading and description", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      expect(screen.getByText("User Management")).toBeDefined();
      expect(screen.getByText("Create, edit, and manage user accounts")).toBeDefined();
    });

    it("renders the Create User button", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      expect(screen.getByText("Create User")).toBeDefined();
    });

    it("renders the search input with correct placeholder", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      const searchInput = screen.getByPlaceholderText("Search by username, email, or full name...");
      expect(searchInput).toBeDefined();
    });

    it("renders user table with correct columns when users exist", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      expect(screen.getByLabelText("Users table")).toBeDefined();
      expect(screen.getByText("Full Name")).toBeDefined();
      expect(screen.getByText("Username")).toBeDefined();
      expect(screen.getByText("Role")).toBeDefined();
      expect(screen.getByText("Status")).toBeDefined();
      expect(screen.getByText("Created")).toBeDefined();
      expect(screen.getByText("Email")).toBeDefined();
    });

    it("displays user data in table rows", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      expect(screen.getByText("John Doe")).toBeDefined();
      expect(screen.getByText("john.doe")).toBeDefined();
      expect(screen.getByText("john@example.com")).toBeDefined();
    });

    it("displays role badges with correct labels", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      expect(screen.getByText("System Admin")).toBeDefined();
      expect(screen.getByText("Doc Admin")).toBeDefined();
      expect(screen.getByText("Viewer")).toBeDefined();
    });

    it("displays active/inactive status indicators (Requirement 5.5)", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      const activeIndicators = screen.getAllByText("Active");
      expect(activeIndicators.length).toBe(2);
      expect(screen.getByText("Inactive")).toBeDefined();
    });
  });

  describe("Loading state", () => {
    it("shows loading skeleton when isLoading is true", () => {
      resetStore({ isLoading: true });
      render(<UserManagementPage />);

      expect(screen.getByLabelText("Loading users")).toBeDefined();
    });

    it("hides user table during loading", () => {
      resetStore({ isLoading: true, users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      // Table should not be visible during loading
      expect(screen.queryByLabelText("Users table")).toBeNull();
    });
  });

  describe("Empty state", () => {
    it("shows empty state when no users and no search query", () => {
      resetStore({ users: [], totalUsers: 0 });
      render(<UserManagementPage />);

      expect(screen.getByText("No users found")).toBeDefined();
      expect(screen.getByText("Create your first user to get started")).toBeDefined();
    });

    it("shows search-specific empty state when search query is active", () => {
      resetStore({ users: [], totalUsers: 0, searchQuery: "nonexistent" });
      render(<UserManagementPage />);

      expect(screen.getByText("No users found")).toBeDefined();
      expect(screen.getByText("Try adjusting your search query")).toBeDefined();
    });
  });

  describe("Error state", () => {
    it("displays error banner when error is set", () => {
      resetStore({ error: "Failed to fetch users" });
      render(<UserManagementPage />);

      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(screen.getByText("Failed to fetch users")).toBeDefined();
    });
  });

  describe("Pagination", () => {
    it("displays total user count", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 1, pageSize: 20 });
      render(<UserManagementPage />);

      expect(screen.getByText("50 users total")).toBeDefined();
    });

    it("displays current page info", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 2, pageSize: 20 });
      render(<UserManagementPage />);

      expect(screen.getByText("Page 2 of 3")).toBeDefined();
    });

    it("disables Previous button on first page", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 1, pageSize: 20 });
      render(<UserManagementPage />);

      const prevButton = screen.getByLabelText("Previous page");
      expect(prevButton.hasAttribute("disabled")).toBe(true);
    });

    it("disables Next button on last page", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 3, pageSize: 20 });
      render(<UserManagementPage />);

      const nextButton = screen.getByLabelText("Next page");
      expect(nextButton.hasAttribute("disabled")).toBe(true);
    });

    it("enables Next button when not on last page", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 1, pageSize: 20 });
      render(<UserManagementPage />);

      const nextButton = screen.getByLabelText("Next page");
      expect(nextButton.hasAttribute("disabled")).toBe(false);
    });

    it("clicking Next page calls setPage with incremented value", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 1, pageSize: 20 });
      render(<UserManagementPage />);

      const nextButton = screen.getByLabelText("Next page");
      fireEvent.click(nextButton);

      expect(useAdminStore.getState().page).toBe(2);
    });

    it("clicking Previous page calls setPage with decremented value", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 2, pageSize: 20 });
      render(<UserManagementPage />);

      const prevButton = screen.getByLabelText("Previous page");
      fireEvent.click(prevButton);

      expect(useAdminStore.getState().page).toBe(1);
    });

    it("renders page size selector with options", () => {
      resetStore({ users: mockUsers, totalUsers: 50, page: 1, pageSize: 20 });
      render(<UserManagementPage />);

      const select = screen.getByLabelText("Rows per page");
      expect(select).toBeDefined();
    });
  });

  describe("Search (Requirement 5.3)", () => {
    it("updates search input value on typing", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      const searchInput = screen.getByPlaceholderText("Search by username, email, or full name...");
      fireEvent.change(searchInput, { target: { value: "john" } });

      expect((searchInput as HTMLInputElement).value).toBe("john");
    });

    it("debounces search query update", async () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      const searchInput = screen.getByPlaceholderText("Search by username, email, or full name...");
      fireEvent.change(searchInput, { target: { value: "test" } });

      // Immediately after typing, store should not be updated yet
      expect(useAdminStore.getState().searchQuery).toBe("");

      // After debounce delay, store should be updated
      await waitFor(() => {
        expect(useAdminStore.getState().searchQuery).toBe("test");
      }, { timeout: 500 });
    });
  });

  describe("Sort (Requirement 5.4)", () => {
    it("renders sort buttons for each column", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      expect(screen.getByLabelText("Sort by Full Name")).toBeDefined();
      expect(screen.getByLabelText("Sort by Username")).toBeDefined();
      expect(screen.getByLabelText("Sort by Role")).toBeDefined();
      expect(screen.getByLabelText("Sort by Status")).toBeDefined();
      expect(screen.getByLabelText("Sort by Created")).toBeDefined();
    });

    it("clicking a sort button updates sort field", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      const sortButton = screen.getByLabelText("Sort by Full Name");
      fireEvent.click(sortButton);

      expect(useAdminStore.getState().sortField).toBe("full_name");
    });

    it("clicking same sort button toggles direction", () => {
      resetStore({ users: mockUsers, totalUsers: 3, sortField: "full_name", sortDirection: "asc" });
      render(<UserManagementPage />);

      const sortButton = screen.getByLabelText("Sort by Full Name");
      fireEvent.click(sortButton);

      expect(useAdminStore.getState().sortDirection).toBe("desc");
    });
  });

  describe("Row interaction", () => {
    it("clicking a user row opens the detail panel", () => {
      resetStore({ users: mockUsers, totalUsers: 3 });
      render(<UserManagementPage />);

      const row = screen.getByLabelText("View details for John Doe");
      fireEvent.click(row);

      // Detail panel should appear
      expect(screen.getByLabelText("User details for John Doe")).toBeDefined();
    });
  });
});
