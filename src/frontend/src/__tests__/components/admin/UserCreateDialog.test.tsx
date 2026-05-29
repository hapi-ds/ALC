import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";

/**
 * Tests for UserCreateDialog form validation, submit, success display with temp password, error handling.
 *
 * Validates: Requirements 6.1–6.6
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
import { UserCreateDialog } from "../../../components/admin/UserCreateDialog";

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

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

describe("UserCreateDialog", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders nothing when open is false", () => {
      render(<UserCreateDialog open={false} onOpenChange={vi.fn()} />);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("renders dialog when open is true", () => {
      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);
      expect(screen.getByRole("dialog")).toBeDefined();
    });

    it("displays Create New User title", () => {
      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);
      expect(screen.getByText("Create New User")).toBeDefined();
    });

    it("renders all form fields", () => {
      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByLabelText(/Username/)).toBeDefined();
      expect(screen.getByLabelText(/Email/)).toBeDefined();
      expect(screen.getByLabelText(/Full Name/)).toBeDefined();
      expect(screen.getByLabelText(/Role/)).toBeDefined();
    });

    it("renders Create User and Cancel buttons", () => {
      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByText("Create User")).toBeDefined();
      expect(screen.getByText("Cancel")).toBeDefined();
    });
  });

  describe("Form validation", () => {
    it("shows error when username is empty on submit", async () => {
      // Mock window.prompt to return a reason
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      // Fill email and full_name but leave username empty
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "test@example.com" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "Test User" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Username is required.")).toBeDefined();
      });
    });

    it("shows error when username is too short", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "ab" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "test@example.com" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "Test User" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Username must be at least 3 characters.")).toBeDefined();
      });
    });

    it("shows error when username has invalid characters", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "user name!" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "test@example.com" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "Test User" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Username may only contain letters, numbers, underscores, dots, and hyphens.")).toBeDefined();
      });
    });

    it("shows error when email is invalid", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "validuser" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "not-an-email" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "Test User" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Please enter a valid email address.")).toBeDefined();
      });
    });

    it("shows error when full name is empty", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "validuser" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "test@example.com" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Full name is required.")).toBeDefined();
      });
    });
  });

  describe("Successful submission (Requirement 6.6)", () => {
    it("displays temporary password on successful creation", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Created new user");

      mockedPost.mockResolvedValueOnce({
        id: 10,
        username: "newuser",
        email: "new@example.com",
        full_name: "New User",
        role: "member",
        is_active: true,
        created_at: "2024-03-01T10:00:00Z",
        temporary_password: "TempPass123!",
      });

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "newuser" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "new@example.com" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "New User" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("User Created Successfully")).toBeDefined();
      });

      expect(screen.getByText("TempPass123!")).toBeDefined();
      expect(screen.getByText(/has been created/)).toBeDefined();
    });

    it("shows copy password button in success state", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Created new user");

      mockedPost.mockResolvedValueOnce({
        id: 10,
        username: "newuser",
        email: "new@example.com",
        full_name: "New User",
        role: "member",
        is_active: true,
        created_at: "2024-03-01T10:00:00Z",
        temporary_password: "TempPass123!",
      });

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "newuser" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "new@example.com" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "New User" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByLabelText("Copy password to clipboard")).toBeDefined();
      });
    });
  });

  describe("Error handling", () => {
    it("shows error when change reason is cancelled", async () => {
      vi.spyOn(window, "prompt").mockReturnValue(null);

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "newuser" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "new@example.com" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "New User" } });

      const submitButton = screen.getByText("Create User");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("A change reason is required for audit compliance.")).toBeDefined();
      });
    });

    it("shows duplicate error on 409 conflict", async () => {
      vi.spyOn(window, "prompt").mockReturnValue("Test reason");

      mockedPost.mockRejectedValueOnce(
        new (ApiError as unknown as new (s: number, b: string, u: string) => Error)(
          409,
          JSON.stringify({ detail: "Username already exists" }),
          "/api/admin/users"
        )
      );

      render(<UserCreateDialog open={true} onOpenChange={vi.fn()} />);

      fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "existing" } });
      fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "new@example.com" } });
      fireEvent.change(screen.getByLabelText(/Full Name/), { target: { value: "New User" } });

      const submitButton = screen.getByText("Create User");
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
      render(<UserCreateDialog open={true} onOpenChange={onOpenChange} />);

      fireEvent.click(screen.getByText("Cancel"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it("calls onOpenChange(false) when close button is clicked", () => {
      const onOpenChange = vi.fn();
      render(<UserCreateDialog open={true} onOpenChange={onOpenChange} />);

      fireEvent.click(screen.getByLabelText("Close dialog"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
