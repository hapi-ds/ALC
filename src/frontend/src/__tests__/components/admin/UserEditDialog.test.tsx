import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";

/**
 * Tests for UserEditDialog pre-population, submit, error handling.
 *
 * Validates: Requirements 7.1–7.4
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

vi.mock("../../../stores/authStore", () => ({
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

import { apiClient, ApiError } from "../../../lib/apiClient";
import { useAdminStore } from "../../../stores/adminStore";
import { UserEditDialog } from "../../../components/admin/UserEditDialog";
import type { UserListItem } from "../../../types/admin";

const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockUser: UserListItem = {
  id: 5,
  username: "john.doe",
  email: "john@example.com",
  full_name: "John Doe",
  role: "member",
  is_active: true,
  created_at: "2024-01-15T10:00:00Z",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
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
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UserEditDialog", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders nothing when open is false", () => {
      render(<UserEditDialog open={false} user={mockUser} onOpenChange={vi.fn()} />);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("renders nothing when user is null", () => {
      render(<UserEditDialog open={true} user={null} onOpenChange={vi.fn()} />);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("renders dialog when open and user provided", () => {
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);
      expect(screen.getByRole("dialog")).toBeDefined();
    });

    it("displays Edit User title", () => {
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);
      expect(screen.getByText("Edit User")).toBeDefined();
    });
  });

  describe("Pre-population (Requirement 7.1)", () => {
    it("pre-populates full name field with current value", () => {
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);

      const input = screen.getByLabelText(/Full Name/) as HTMLInputElement;
      expect(input.value).toBe("John Doe");
    });

    it("pre-populates email field with current value", () => {
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);

      const input = screen.getByLabelText(/Email/) as HTMLInputElement;
      expect(input.value).toBe("john@example.com");
    });

    it("pre-populates role field with current value", () => {
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);

      const select = screen.getByLabelText(/Role/) as HTMLSelectElement;
      expect(select.value).toBe("member");
    });
  });

  describe("Form validation", () => {
    it("shows error when full name is cleared", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);

      const input = screen.getByLabelText(/Full Name/);
      fireEvent.change(input, { target: { value: "" } });

      const submitButton = screen.getByText("Save Changes");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Full name is required.")).toBeDefined();
      });
    });

    it("shows error when email is invalid", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);

      const input = screen.getByLabelText(/Email/);
      fireEvent.change(input, { target: { value: "not-valid" } });

      const submitButton = screen.getByText("Save Changes");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Please enter a valid email address.")).toBeDefined();
      });
    });
  });

  describe("Submit behavior", () => {
    it("shows error when change reason is cancelled", async () => {
      vi.spyOn(window, "prompt").mockReturnValue(null);

      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);

      // Change a field to make form dirty
      const input = screen.getByLabelText(/Full Name/);
      fireEvent.change(input, { target: { value: "Updated Name" } });

      const submitButton = screen.getByText("Save Changes");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("A change reason is required for audit compliance.")).toBeDefined();
      });
    });

    it("calls onOpenChange(false) on successful submit", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Updated profile");
      mockedPatch.mockResolvedValueOnce({});

      const onOpenChange = vi.fn();
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={onOpenChange} />);

      const input = screen.getByLabelText(/Full Name/);
      fireEvent.change(input, { target: { value: "Updated Name" } });

      const submitButton = screen.getByText("Save Changes");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(onOpenChange).toHaveBeenCalledWith(false);
      });
    });
  });

  describe("Error handling", () => {
    it("shows duplicate email error on 409 conflict (Requirement 7.3)", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Changed email");

      mockedPatch.mockRejectedValueOnce(
        new (ApiError as unknown as new (s: number, b: string, u: string) => Error)(
          409,
          JSON.stringify({ detail: "This email address is already in use by another account." }),
          "/api/admin/users/5"
        )
      );

      render(<UserEditDialog open={true} user={mockUser} onOpenChange={vi.fn()} />);

      const input = screen.getByLabelText(/Email/);
      fireEvent.change(input, { target: { value: "taken@example.com" } });

      const submitButton = screen.getByText("Save Changes");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeDefined();
      });
    });
  });

  describe("Dialog controls", () => {
    it("calls onOpenChange(false) when Cancel is clicked", () => {
      const onOpenChange = vi.fn();
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={onOpenChange} />);

      fireEvent.click(screen.getByText("Cancel"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it("calls onOpenChange(false) when close button is clicked", () => {
      const onOpenChange = vi.fn();
      render(<UserEditDialog open={true} user={mockUser} onOpenChange={onOpenChange} />);

      fireEvent.click(screen.getByLabelText("Close dialog"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
