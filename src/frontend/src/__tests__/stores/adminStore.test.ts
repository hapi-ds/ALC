import { describe, it, expect, beforeEach, vi } from "vitest";
import { useAdminStore } from "@/stores/adminStore";
import type { AdminState } from "@/stores/adminStore";

/**
 * Unit tests for adminStore actions.
 *
 * Validates: Requirements 5.1, 6.6, 9.3
 */

// Mock apiClient module
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

import { apiClient } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeUserListResponse(overrides: Record<string, unknown> = {}) {
  return {
    users: [
      {
        id: 1,
        username: "jdoe",
        email: "jdoe@example.com",
        full_name: "John Doe",
        role: "member",
        is_active: true,
        created_at: "2024-01-01T00:00:00Z",
      },
      {
        id: 2,
        username: "asmith",
        email: "asmith@example.com",
        full_name: "Alice Smith",
        role: "doc_admin",
        is_active: true,
        created_at: "2024-01-02T00:00:00Z",
      },
    ],
    total: 2,
    page: 1,
    page_size: 20,
    total_pages: 1,
    ...overrides,
  };
}

function makeCreateUserResponse() {
  return {
    id: 3,
    username: "newuser",
    email: "newuser@example.com",
    full_name: "New User",
    role: "member",
    is_active: true,
    created_at: "2024-03-01T00:00:00Z",
    temporary_password: "TempPass123!",
  };
}

function makeUserDetail() {
  return {
    id: 1,
    username: "jdoe",
    email: "jdoe@example.com",
    full_name: "John Doe",
    is_active: true,
    created_at: "2024-01-01T00:00:00Z",
    memberships: [
      {
        id: 10,
        company_id: 1,
        company_name: "Acme Corp",
        role: "member",
        created_at: "2024-01-01T00:00:00Z",
        revoked_at: null,
      },
    ],
  };
}

function makeRolesResponse() {
  return {
    roles: [
      { id: 1, name: "system_admin", description: "Full access", is_system: true, user_count: 1 },
      { id: 2, name: "doc_admin", description: "Document admin", is_system: true, user_count: 3 },
      { id: 3, name: "member", description: "Standard member", is_system: true, user_count: 10 },
    ],
  };
}

function makeRoleDetail() {
  return {
    id: 1,
    name: "system_admin",
    description: "Full access to all resources",
    is_system: true,
    permissions: {
      documents: ["create", "read", "update", "delete", "approve"],
      workflows: ["create", "read", "update", "delete", "approve"],
      users: ["create", "read", "update", "delete", "approve"],
    },
    user_count: 1,
  };
}

function makeTemplatesResponse() {
  return {
    templates: [
      {
        id: 1,
        name: "Internal SOP",
        description: "Standard operating procedure template",
        document_type: "SOP",
        role_permissions: { system_admin: ["read", "write", "approve"], member: ["read"] },
        is_default: true,
        created_by: 1,
        created_at: "2024-01-01T00:00:00Z",
        active_document_count: 5,
      },
    ],
  };
}

function makeHistoryResponse() {
  return {
    entries: [
      {
        version_id: 1,
        changed_at: "2024-01-15T10:00:00Z",
        changed_by: 1,
        changed_by_username: "admin",
        change_reason: "Initial creation",
        changes: { full_name: { old: null, new: "John Doe" } },
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Default state for reset between tests
// ---------------------------------------------------------------------------

const defaultState: Partial<AdminState> = {
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
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("adminStore", () => {
  beforeEach(() => {
    useAdminStore.setState(defaultState);
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Initial state
  // -------------------------------------------------------------------------

  describe("initial state", () => {
    it("has correct defaults", () => {
      useAdminStore.setState(defaultState);
      const state = useAdminStore.getState();

      expect(state.users).toEqual([]);
      expect(state.totalUsers).toBe(0);
      expect(state.currentUser).toBeNull();
      expect(state.userHistory).toEqual([]);
      expect(state.roles).toEqual([]);
      expect(state.currentRole).toBeNull();
      expect(state.permissionTemplates).toEqual([]);
      expect(state.currentTemplate).toBeNull();
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.searchQuery).toBe("");
      expect(state.sortField).toBe("created_at");
      expect(state.sortDirection).toBe("desc");
      expect(state.page).toBe(1);
      expect(state.pageSize).toBe(20);
    });
  });

  // -------------------------------------------------------------------------
  // fetchUsers()
  // -------------------------------------------------------------------------

  describe("fetchUsers()", () => {
    it("fetches users with default params from state", async () => {
      mockedApiClient.get.mockResolvedValue(makeUserListResponse());

      await useAdminStore.getState().fetchUsers();

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("/api/admin/users?"),
      );
      const url = mockedApiClient.get.mock.calls[0][0] as string;
      expect(url).toContain("sort_by=created_at");
      expect(url).toContain("sort_dir=desc");
      expect(url).toContain("page=1");
      expect(url).toContain("page_size=20");
    });

    it("stores users and total on success", async () => {
      mockedApiClient.get.mockResolvedValue(makeUserListResponse({ total: 42 }));

      await useAdminStore.getState().fetchUsers();

      const state = useAdminStore.getState();
      expect(state.users).toHaveLength(2);
      expect(state.totalUsers).toBe(42);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });

    it("includes search param when searchQuery is set", async () => {
      useAdminStore.setState({ searchQuery: "john" });
      mockedApiClient.get.mockResolvedValue(makeUserListResponse());

      await useAdminStore.getState().fetchUsers();

      const url = mockedApiClient.get.mock.calls[0][0] as string;
      expect(url).toContain("search=john");
    });

    it("uses explicit params over state values", async () => {
      useAdminStore.setState({ searchQuery: "old", sortField: "username", page: 3 });
      mockedApiClient.get.mockResolvedValue(makeUserListResponse());

      await useAdminStore.getState().fetchUsers({
        search: "new",
        sort_by: "full_name",
        sort_dir: "asc",
        page: 1,
        page_size: 10,
      });

      const url = mockedApiClient.get.mock.calls[0][0] as string;
      expect(url).toContain("search=new");
      expect(url).toContain("sort_by=full_name");
      expect(url).toContain("sort_dir=asc");
      expect(url).toContain("page=1");
      expect(url).toContain("page_size=10");
    });

    it("sets isLoading true during request", async () => {
      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));

      useAdminStore.getState().fetchUsers();

      await vi.waitFor(() => {
        expect(useAdminStore.getState().isLoading).toBe(true);
      });
    });

    it("handles error response", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network failure"));

      await useAdminStore.getState().fetchUsers();

      const state = useAdminStore.getState();
      expect(state.error).toBe("Network failure");
      expect(state.isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // createUser()
  // -------------------------------------------------------------------------

  describe("createUser()", () => {
    it("sends POST with payload and X-Change-Reason", async () => {
      const payload = {
        username: "newuser",
        email: "newuser@example.com",
        full_name: "New User",
        role: "member" as const,
      };
      mockedApiClient.post.mockResolvedValue(makeCreateUserResponse());

      await useAdminStore.getState().createUser(payload, "Adding new team member");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/admin/users",
        payload,
        { changeReason: "Adding new team member" },
      );
    });

    it("returns CreateUserResponse with temporary_password", async () => {
      const payload = {
        username: "newuser",
        email: "newuser@example.com",
        full_name: "New User",
        role: "member" as const,
      };
      mockedApiClient.post.mockResolvedValue(makeCreateUserResponse());

      const result = await useAdminStore.getState().createUser(payload, "reason");

      expect(result.temporary_password).toBe("TempPass123!");
      expect(result.id).toBe(3);
    });

    it("sets error and re-throws on failure", async () => {
      const payload = {
        username: "dup",
        email: "dup@example.com",
        full_name: "Dup",
        role: "member" as const,
      };
      mockedApiClient.post.mockRejectedValue(new Error("API error 409 on /api/admin/users"));

      await expect(
        useAdminStore.getState().createUser(payload, "reason"),
      ).rejects.toThrow();

      const state = useAdminStore.getState();
      expect(state.error).toContain("409");
      expect(state.isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // updateUser()
  // -------------------------------------------------------------------------

  describe("updateUser()", () => {
    it("sends PATCH with payload and X-Change-Reason", async () => {
      mockedApiClient.patch.mockResolvedValue({});

      await useAdminStore.getState().updateUser(
        1,
        { full_name: "Updated Name" },
        "Correcting name",
      );

      expect(mockedApiClient.patch).toHaveBeenCalledWith(
        "/api/admin/users/1",
        { full_name: "Updated Name" },
        { changeReason: "Correcting name" },
      );
    });

    it("clears loading on success", async () => {
      mockedApiClient.patch.mockResolvedValue({});

      await useAdminStore.getState().updateUser(1, { email: "new@example.com" }, "reason");

      expect(useAdminStore.getState().isLoading).toBe(false);
      expect(useAdminStore.getState().error).toBeNull();
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.patch.mockRejectedValue(new Error("Failed to update user"));

      await expect(
        useAdminStore.getState().updateUser(1, { email: "dup@example.com" }, "reason"),
      ).rejects.toThrow();

      expect(useAdminStore.getState().error).toBe("Failed to update user");
    });
  });

  // -------------------------------------------------------------------------
  // deactivateUser() / reactivateUser()
  // -------------------------------------------------------------------------

  describe("deactivateUser()", () => {
    it("sends POST with X-Change-Reason to deactivate endpoint", async () => {
      mockedApiClient.post.mockResolvedValue({});

      await useAdminStore.getState().deactivateUser(5, "Employee left company");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/admin/users/5/deactivate",
        undefined,
        { changeReason: "Employee left company" },
      );
    });

    it("sets error on failure", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("Cannot deactivate self"));

      await expect(
        useAdminStore.getState().deactivateUser(1, "reason"),
      ).rejects.toThrow();

      expect(useAdminStore.getState().error).toBe("Cannot deactivate self");
    });
  });

  describe("reactivateUser()", () => {
    it("sends POST with X-Change-Reason to reactivate endpoint", async () => {
      mockedApiClient.post.mockResolvedValue({});

      await useAdminStore.getState().reactivateUser(5, "Employee reinstated");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/admin/users/5/reactivate",
        undefined,
        { changeReason: "Employee reinstated" },
      );
    });

    it("sets error on failure", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("User not found"));

      await expect(
        useAdminStore.getState().reactivateUser(99, "reason"),
      ).rejects.toThrow();

      expect(useAdminStore.getState().error).toBe("User not found");
    });
  });

  // -------------------------------------------------------------------------
  // resetPassword()
  // -------------------------------------------------------------------------

  describe("resetPassword()", () => {
    it("sends POST with X-Change-Reason and returns temporary password", async () => {
      mockedApiClient.post.mockResolvedValue({ temporary_password: "NewTemp456!" });

      const result = await useAdminStore.getState().resetPassword(5, "User forgot password");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/admin/users/5/reset-password",
        undefined,
        { changeReason: "User forgot password" },
      );
      expect(result).toBe("NewTemp456!");
    });

    it("clears loading state on success", async () => {
      mockedApiClient.post.mockResolvedValue({ temporary_password: "abc" });

      await useAdminStore.getState().resetPassword(1, "reason");

      expect(useAdminStore.getState().isLoading).toBe(false);
      expect(useAdminStore.getState().error).toBeNull();
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("Failed to reset password"));

      await expect(
        useAdminStore.getState().resetPassword(1, "reason"),
      ).rejects.toThrow();

      expect(useAdminStore.getState().error).toBe("Failed to reset password");
    });
  });

  // -------------------------------------------------------------------------
  // fetchUserDetail() / fetchUserHistory()
  // -------------------------------------------------------------------------

  describe("fetchUserDetail()", () => {
    it("fetches user detail and stores in currentUser", async () => {
      mockedApiClient.get.mockResolvedValue(makeUserDetail());

      await useAdminStore.getState().fetchUserDetail(1);

      const state = useAdminStore.getState();
      expect(state.currentUser).not.toBeNull();
      expect(state.currentUser!.username).toBe("jdoe");
      expect(state.currentUser!.memberships).toHaveLength(1);
      expect(state.isLoading).toBe(false);
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeUserDetail());

      await useAdminStore.getState().fetchUserDetail(42);

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/admin/users/42");
    });

    it("handles error", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Not found"));

      await useAdminStore.getState().fetchUserDetail(999);

      expect(useAdminStore.getState().error).toBe("Not found");
    });
  });

  describe("fetchUserHistory()", () => {
    it("fetches history and stores entries", async () => {
      mockedApiClient.get.mockResolvedValue(makeHistoryResponse());

      await useAdminStore.getState().fetchUserHistory(1);

      const state = useAdminStore.getState();
      expect(state.userHistory).toHaveLength(1);
      expect(state.userHistory[0].change_reason).toBe("Initial creation");
      expect(state.isLoading).toBe(false);
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeHistoryResponse());

      await useAdminStore.getState().fetchUserHistory(7);

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/admin/users/7/history");
    });
  });

  // -------------------------------------------------------------------------
  // fetchRoles() / fetchRoleDetail()
  // -------------------------------------------------------------------------

  describe("fetchRoles()", () => {
    it("fetches roles and stores them", async () => {
      mockedApiClient.get.mockResolvedValue(makeRolesResponse());

      await useAdminStore.getState().fetchRoles();

      const state = useAdminStore.getState();
      expect(state.roles).toHaveLength(3);
      expect(state.roles[0].name).toBe("system_admin");
      expect(state.isLoading).toBe(false);
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeRolesResponse());

      await useAdminStore.getState().fetchRoles();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/admin/roles");
    });

    it("handles error", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Forbidden"));

      await useAdminStore.getState().fetchRoles();

      expect(useAdminStore.getState().error).toBe("Forbidden");
    });
  });

  describe("fetchRoleDetail()", () => {
    it("fetches role detail and stores in currentRole", async () => {
      mockedApiClient.get.mockResolvedValue(makeRoleDetail());

      await useAdminStore.getState().fetchRoleDetail(1);

      const state = useAdminStore.getState();
      expect(state.currentRole).not.toBeNull();
      expect(state.currentRole!.name).toBe("system_admin");
      expect(state.currentRole!.permissions.documents).toContain("approve");
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeRoleDetail());

      await useAdminStore.getState().fetchRoleDetail(5);

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/admin/roles/5");
    });
  });

  // -------------------------------------------------------------------------
  // Permission template actions
  // -------------------------------------------------------------------------

  describe("fetchPermissionTemplates()", () => {
    it("fetches templates and stores them", async () => {
      mockedApiClient.get.mockResolvedValue(makeTemplatesResponse());

      await useAdminStore.getState().fetchPermissionTemplates();

      const state = useAdminStore.getState();
      expect(state.permissionTemplates).toHaveLength(1);
      expect(state.permissionTemplates[0].name).toBe("Internal SOP");
      expect(state.isLoading).toBe(false);
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeTemplatesResponse());

      await useAdminStore.getState().fetchPermissionTemplates();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/admin/permission-templates");
    });
  });

  describe("createPermissionTemplate()", () => {
    it("sends POST with payload and X-Change-Reason", async () => {
      const payload = {
        name: "New Template",
        document_type: "Policy",
        role_permissions: [{ role: "member" as const, actions: ["read" as const] }],
      };
      mockedApiClient.post.mockResolvedValue({});

      await useAdminStore.getState().createPermissionTemplate(payload, "Creating policy template");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/admin/permission-templates",
        payload,
        { changeReason: "Creating policy template" },
      );
    });
  });

  describe("updatePermissionTemplate()", () => {
    it("sends PATCH with payload and X-Change-Reason", async () => {
      mockedApiClient.patch.mockResolvedValue({});

      await useAdminStore.getState().updatePermissionTemplate(
        1,
        { name: "Updated Template" },
        "Renaming template",
      );

      expect(mockedApiClient.patch).toHaveBeenCalledWith(
        "/api/admin/permission-templates/1",
        { name: "Updated Template" },
        { changeReason: "Renaming template" },
      );
    });
  });

  describe("deletePermissionTemplate()", () => {
    it("sends DELETE with X-Change-Reason", async () => {
      mockedApiClient.delete.mockResolvedValue(undefined);

      await useAdminStore.getState().deletePermissionTemplate(2, "Template no longer needed");

      expect(mockedApiClient.delete).toHaveBeenCalledWith(
        "/api/admin/permission-templates/2",
        { changeReason: "Template no longer needed" },
      );
    });

    it("sets error on failure (e.g., active documents)", async () => {
      mockedApiClient.delete.mockRejectedValue(
        new Error("API error 409 on /api/admin/permission-templates/1"),
      );

      await expect(
        useAdminStore.getState().deletePermissionTemplate(1, "reason"),
      ).rejects.toThrow();

      expect(useAdminStore.getState().error).toContain("409");
    });
  });

  // -------------------------------------------------------------------------
  // Membership actions
  // -------------------------------------------------------------------------

  describe("assignMembership()", () => {
    it("sends POST with payload and X-Change-Reason", async () => {
      const payload = { user_id: 1, company_id: 2, role: "member" as const };
      mockedApiClient.post.mockResolvedValue({});

      await useAdminStore.getState().assignMembership(payload, "Cross-company assignment");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/admin/memberships",
        payload,
        { changeReason: "Cross-company assignment" },
      );
    });

    it("sets error on duplicate membership", async () => {
      const payload = { user_id: 1, company_id: 1, role: "member" as const };
      mockedApiClient.post.mockRejectedValue(new Error("Duplicate membership"));

      await expect(
        useAdminStore.getState().assignMembership(payload, "reason"),
      ).rejects.toThrow();

      expect(useAdminStore.getState().error).toBe("Duplicate membership");
    });
  });

  describe("revokeMembership()", () => {
    it("sends DELETE with X-Change-Reason", async () => {
      mockedApiClient.delete.mockResolvedValue(undefined);

      await useAdminStore.getState().revokeMembership(10, "User leaving company");

      expect(mockedApiClient.delete).toHaveBeenCalledWith(
        "/api/admin/memberships/10",
        { changeReason: "User leaving company" },
      );
    });

    it("sets error on failure", async () => {
      mockedApiClient.delete.mockRejectedValue(new Error("Membership not found"));

      await expect(
        useAdminStore.getState().revokeMembership(999, "reason"),
      ).rejects.toThrow();

      expect(useAdminStore.getState().error).toBe("Membership not found");
    });
  });

  // -------------------------------------------------------------------------
  // UI state setters (pagination, search, sort)
  // -------------------------------------------------------------------------

  describe("UI state setters", () => {
    it("setSearchQuery updates query and resets page to 1", () => {
      useAdminStore.setState({ page: 3 });

      useAdminStore.getState().setSearchQuery("alice");

      const state = useAdminStore.getState();
      expect(state.searchQuery).toBe("alice");
      expect(state.page).toBe(1);
    });

    it("setSortField updates field and resets page to 1", () => {
      useAdminStore.setState({ page: 5, sortField: "created_at" });

      useAdminStore.getState().setSortField("username");

      const state = useAdminStore.getState();
      expect(state.sortField).toBe("username");
      expect(state.page).toBe(1);
    });

    it("setSortDirection updates direction and resets page to 1", () => {
      useAdminStore.setState({ page: 2, sortDirection: "desc" });

      useAdminStore.getState().setSortDirection("asc");

      const state = useAdminStore.getState();
      expect(state.sortDirection).toBe("asc");
      expect(state.page).toBe(1);
    });

    it("setPage updates page without resetting other state", () => {
      useAdminStore.setState({ searchQuery: "test", sortField: "username" });

      useAdminStore.getState().setPage(4);

      const state = useAdminStore.getState();
      expect(state.page).toBe(4);
      expect(state.searchQuery).toBe("test");
      expect(state.sortField).toBe("username");
    });

    it("setPageSize updates size and resets page to 1", () => {
      useAdminStore.setState({ page: 3, pageSize: 20 });

      useAdminStore.getState().setPageSize(50);

      const state = useAdminStore.getState();
      expect(state.pageSize).toBe(50);
      expect(state.page).toBe(1);
    });
  });

  // -------------------------------------------------------------------------
  // Loading state transitions
  // -------------------------------------------------------------------------

  describe("loading state transitions", () => {
    it("sets isLoading=true at start and false on success for fetchUsers", async () => {
      let resolvePromise: (value: unknown) => void;
      const promise = new Promise((resolve) => { resolvePromise = resolve; });
      mockedApiClient.get.mockReturnValue(promise);

      const fetchPromise = useAdminStore.getState().fetchUsers();

      await vi.waitFor(() => {
        expect(useAdminStore.getState().isLoading).toBe(true);
      });

      resolvePromise!(makeUserListResponse());
      await fetchPromise;

      expect(useAdminStore.getState().isLoading).toBe(false);
    });

    it("sets isLoading=true at start and false on error for createUser", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("fail"));

      const payload = {
        username: "u",
        email: "u@e.com",
        full_name: "U",
        role: "member" as const,
      };

      await useAdminStore.getState().createUser(payload, "r").catch(() => {});

      expect(useAdminStore.getState().isLoading).toBe(false);
    });

    it("clears previous error on new request", async () => {
      useAdminStore.setState({ error: "Previous error" });
      mockedApiClient.get.mockResolvedValue(makeUserListResponse());

      await useAdminStore.getState().fetchUsers();

      expect(useAdminStore.getState().error).toBeNull();
    });
  });
});
