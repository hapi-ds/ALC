import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";

/**
 * Tests for PermissionTemplateDialog form validation and submit.
 *
 * Validates: Requirements 4.1, 4.2, 4.5
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

import { apiClient } from "../../../lib/apiClient";
import { useAdminStore } from "../../../stores/adminStore";
import { PermissionTemplateDialog } from "../../../components/admin/PermissionTemplateDialog";
import type { PermissionTemplate } from "../../../types/admin";

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;
const mockedPatch = apiClient.patch as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockTemplate: PermissionTemplate = {
  id: 1,
  name: "Internal SOP",
  description: "Standard operating procedures",
  document_type: "SOP",
  role_permissions: {
    system_admin: ["read", "write", "approve"],
    doc_admin: ["read", "write"],
    member: ["read"],
  },
  is_default: false,
  created_by: 1,
  created_at: "2024-01-01T00:00:00Z",
  active_document_count: 0,
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

describe("PermissionTemplateDialog", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering", () => {
    it("renders nothing when open is false", () => {
      render(<PermissionTemplateDialog open={false} onOpenChange={vi.fn()} template={null} />);
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("renders dialog in create mode when template is null", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={null} />);
      expect(screen.getByRole("dialog")).toBeDefined();
      expect(screen.getByText("Create Permission Template")).toBeDefined();
    });

    it("renders dialog in edit mode when template is provided", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={mockTemplate} />);
      expect(screen.getByText("Edit Permission Template")).toBeDefined();
    });

    it("renders all form fields", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={null} />);

      expect(screen.getByLabelText(/Name/)).toBeDefined();
      expect(screen.getByLabelText(/Description/)).toBeDefined();
      expect(screen.getByLabelText(/Document Type/)).toBeDefined();
      expect(screen.getByLabelText(/Change Reason/)).toBeDefined();
    });

    it("renders role permission checkboxes", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={null} />);

      expect(screen.getByLabelText("System Admin can read")).toBeDefined();
      expect(screen.getByLabelText("System Admin can write")).toBeDefined();
      expect(screen.getByLabelText("System Admin can approve")).toBeDefined();
      expect(screen.getByLabelText("Doc Admin can read")).toBeDefined();
      expect(screen.getByLabelText("Member can read")).toBeDefined();
      expect(screen.getByLabelText("Viewer can read")).toBeDefined();
    });
  });

  describe("Edit mode pre-population", () => {
    it("pre-populates name field", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={mockTemplate} />);

      const input = screen.getByLabelText(/Name/) as HTMLInputElement;
      expect(input.value).toBe("Internal SOP");
    });

    it("pre-populates document type field (disabled in edit mode)", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={mockTemplate} />);

      const input = screen.getByLabelText(/Document Type/) as HTMLInputElement;
      expect(input.value).toBe("SOP");
      expect(input.disabled).toBe(true);
    });

    it("pre-populates role permission checkboxes", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={mockTemplate} />);

      const sysAdminRead = screen.getByLabelText("System Admin can read") as HTMLInputElement;
      const sysAdminWrite = screen.getByLabelText("System Admin can write") as HTMLInputElement;
      const sysAdminApprove = screen.getByLabelText("System Admin can approve") as HTMLInputElement;
      const memberRead = screen.getByLabelText("Member can read") as HTMLInputElement;
      const viewerRead = screen.getByLabelText("Viewer can read") as HTMLInputElement;

      expect(sysAdminRead.checked).toBe(true);
      expect(sysAdminWrite.checked).toBe(true);
      expect(sysAdminApprove.checked).toBe(true);
      expect(memberRead.checked).toBe(true);
      expect(viewerRead.checked).toBe(false);
    });
  });

  describe("Form validation", () => {
    it("shows error when name is empty on submit", async () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={null} />);

      // Fill other required fields but leave name empty
      fireEvent.change(screen.getByLabelText(/Document Type/), { target: { value: "SOP" } });
      fireEvent.change(screen.getByLabelText(/Change Reason/), { target: { value: "Test" } });

      const submitButton = screen.getByText("Create Template");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Template name is required")).toBeDefined();
      });
    });

    it("shows error when document type is empty on submit", async () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={null} />);

      fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Test Template" } });
      fireEvent.change(screen.getByLabelText(/Change Reason/), { target: { value: "Test" } });

      const submitButton = screen.getByText("Create Template");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Document type is required")).toBeDefined();
      });
    });

    it("shows error when change reason is empty on submit", async () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={null} />);

      fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Test Template" } });
      fireEvent.change(screen.getByLabelText(/Document Type/), { target: { value: "SOP" } });

      const submitButton = screen.getByText("Create Template");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(screen.getByText("Change reason is required for audit compliance")).toBeDefined();
      });
    });
  });

  describe("Submit behavior", () => {
    it("calls createPermissionTemplate on create mode submit", async () => {
      mockedPost.mockResolvedValueOnce({});

      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={null} />);

      fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "New Template" } });
      fireEvent.change(screen.getByLabelText(/Document Type/), { target: { value: "Protocol" } });
      fireEvent.change(screen.getByLabelText(/Change Reason/), { target: { value: "Created new template" } });

      // Check at least one permission
      fireEvent.click(screen.getByLabelText("System Admin can read"));

      const submitButton = screen.getByText("Create Template");
      await act(async () => {
        fireEvent.click(submitButton);
      });

      await waitFor(() => {
        expect(mockedPost).toHaveBeenCalled();
      });
    });

    it("shows Save Changes button in edit mode", () => {
      render(<PermissionTemplateDialog open={true} onOpenChange={vi.fn()} template={mockTemplate} />);

      expect(screen.getByText("Save Changes")).toBeDefined();
    });
  });

  describe("Dialog controls", () => {
    it("calls onOpenChange(false) when Cancel is clicked", () => {
      const onOpenChange = vi.fn();
      render(<PermissionTemplateDialog open={true} onOpenChange={onOpenChange} template={null} />);

      fireEvent.click(screen.getByText("Cancel"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it("calls onOpenChange(false) when close button is clicked", () => {
      const onOpenChange = vi.fn();
      render(<PermissionTemplateDialog open={true} onOpenChange={onOpenChange} template={null} />);

      fireEvent.click(screen.getByLabelText("Close dialog"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
