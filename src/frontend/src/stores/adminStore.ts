/**
 * Admin Store — Zustand state management for admin user management.
 *
 * Manages state for user CRUD, roles, permission templates, and memberships.
 * All mutation actions include X-Change-Reason header for ALCOA+ audit compliance.
 */

import { create } from "zustand";
import { apiClient } from "@/lib/apiClient";
import type {
  UserListItem,
  UserDetail,
  UserCreatePayload,
  UserUpdatePayload,
  CreateUserResponse,
  UserHistoryEntry,
  RoleWithCount,
  RoleDetail,
  PermissionTemplate,
  PermissionTemplateDetail,
  CreateTemplatePayload,
  UpdateTemplatePayload,
  AssignMembershipPayload,
  UserListParams,
  PaginatedResponse,
} from "@/types/admin";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AdminState {
  // User management
  users: UserListItem[];
  totalUsers: number;
  currentUser: UserDetail | null;
  userHistory: UserHistoryEntry[];

  // Roles
  roles: RoleWithCount[];
  currentRole: RoleDetail | null;

  // Permission templates
  permissionTemplates: PermissionTemplate[];
  currentTemplate: PermissionTemplateDetail | null;

  // UI state
  isLoading: boolean;
  error: string | null;
  searchQuery: string;
  sortField: string;
  sortDirection: "asc" | "desc";
  page: number;
  pageSize: number;

  // Actions
  fetchUsers: (params?: UserListParams) => Promise<void>;
  createUser: (payload: UserCreatePayload, reason: string) => Promise<CreateUserResponse>;
  updateUser: (userId: number, payload: UserUpdatePayload, reason: string) => Promise<void>;
  deactivateUser: (userId: number, reason: string) => Promise<void>;
  reactivateUser: (userId: number, reason: string) => Promise<void>;
  resetPassword: (userId: number, reason: string) => Promise<string>;
  fetchUserDetail: (userId: number) => Promise<void>;
  fetchUserHistory: (userId: number) => Promise<void>;

  fetchRoles: () => Promise<void>;
  fetchRoleDetail: (roleId: number) => Promise<void>;

  fetchPermissionTemplates: () => Promise<void>;
  createPermissionTemplate: (payload: CreateTemplatePayload, reason: string) => Promise<void>;
  updatePermissionTemplate: (id: number, payload: UpdateTemplatePayload, reason: string) => Promise<void>;
  deletePermissionTemplate: (id: number, reason: string) => Promise<void>;

  assignMembership: (payload: AssignMembershipPayload, reason: string) => Promise<void>;
  revokeMembership: (membershipId: number, reason: string) => Promise<void>;

  // UI state setters
  setSearchQuery: (query: string) => void;
  setSortField: (field: string) => void;
  setSortDirection: (direction: "asc" | "desc") => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useAdminStore = create<AdminState>((set, get) => ({
  // Initial state
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

  // ---------------------------------------------------------------------------
  // User actions
  // ---------------------------------------------------------------------------

  fetchUsers: async (params?: UserListParams) => {
    set({ isLoading: true, error: null });
    try {
      const state = get();
      const queryParams = new URLSearchParams();

      const search = params?.search ?? state.searchQuery;
      const sortBy = params?.sort_by ?? state.sortField;
      const sortDir = params?.sort_dir ?? state.sortDirection;
      const page = params?.page ?? state.page;
      const pageSize = params?.page_size ?? state.pageSize;

      if (search) queryParams.set("search", search);
      queryParams.set("sort_by", sortBy);
      queryParams.set("sort_dir", sortDir);
      queryParams.set("page", String(page));
      queryParams.set("page_size", String(pageSize));
      if (params?.is_active !== undefined) {
        queryParams.set("is_active", String(params.is_active));
      }

      const url = `/api/admin/users?${queryParams.toString()}`;
      const response = await apiClient.get<PaginatedResponse<UserListItem>>(url);

      set({
        users: response.users,
        totalUsers: response.total,
        page: response.page,
        pageSize: response.page_size,
        isLoading: false,
      });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to fetch users",
      });
    }
  },

  createUser: async (payload: UserCreatePayload, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.post<CreateUserResponse>(
        "/api/admin/users",
        payload,
        { changeReason: reason },
      );
      set({ isLoading: false });
      return response;
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to create user",
      });
      throw error;
    }
  },

  updateUser: async (userId: number, payload: UserUpdatePayload, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.patch(
        `/api/admin/users/${userId}`,
        payload,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to update user",
      });
      throw error;
    }
  },

  deactivateUser: async (userId: number, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.post(
        `/api/admin/users/${userId}/deactivate`,
        undefined,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to deactivate user",
      });
      throw error;
    }
  },

  reactivateUser: async (userId: number, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.post(
        `/api/admin/users/${userId}/reactivate`,
        undefined,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to reactivate user",
      });
      throw error;
    }
  },

  resetPassword: async (userId: number, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.post<{ temporary_password: string }>(
        `/api/admin/users/${userId}/reset-password`,
        undefined,
        { changeReason: reason },
      );
      set({ isLoading: false });
      return response.temporary_password;
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to reset password",
      });
      throw error;
    }
  },

  fetchUserDetail: async (userId: number) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.get<UserDetail>(`/api/admin/users/${userId}`);
      set({ currentUser: response, isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to fetch user detail",
      });
    }
  },

  fetchUserHistory: async (userId: number) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.get<{ entries: UserHistoryEntry[] }>(
        `/api/admin/users/${userId}/history`,
      );
      set({ userHistory: response.entries, isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to fetch user history",
      });
    }
  },

  // ---------------------------------------------------------------------------
  // Role actions
  // ---------------------------------------------------------------------------

  fetchRoles: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.get<{ roles: RoleWithCount[] }>("/api/admin/roles");
      set({ roles: response.roles, isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to fetch roles",
      });
    }
  },

  fetchRoleDetail: async (roleId: number) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.get<RoleDetail>(`/api/admin/roles/${roleId}`);
      set({ currentRole: response, isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to fetch role detail",
      });
    }
  },

  // ---------------------------------------------------------------------------
  // Permission template actions
  // ---------------------------------------------------------------------------

  fetchPermissionTemplates: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.get<{ templates: PermissionTemplate[] }>(
        "/api/admin/permission-templates",
      );
      set({ permissionTemplates: response.templates, isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to fetch permission templates",
      });
    }
  },

  createPermissionTemplate: async (payload: CreateTemplatePayload, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.post(
        "/api/admin/permission-templates",
        payload,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to create permission template",
      });
      throw error;
    }
  },

  updatePermissionTemplate: async (id: number, payload: UpdateTemplatePayload, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.patch(
        `/api/admin/permission-templates/${id}`,
        payload,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to update permission template",
      });
      throw error;
    }
  },

  deletePermissionTemplate: async (id: number, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.delete(
        `/api/admin/permission-templates/${id}`,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to delete permission template",
      });
      throw error;
    }
  },

  // ---------------------------------------------------------------------------
  // Membership actions
  // ---------------------------------------------------------------------------

  assignMembership: async (payload: AssignMembershipPayload, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.post(
        "/api/admin/memberships",
        payload,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to assign membership",
      });
      throw error;
    }
  },

  revokeMembership: async (membershipId: number, reason: string) => {
    set({ isLoading: true, error: null });
    try {
      await apiClient.delete(
        `/api/admin/memberships/${membershipId}`,
        { changeReason: reason },
      );
      set({ isLoading: false });
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : "Failed to revoke membership",
      });
      throw error;
    }
  },

  // ---------------------------------------------------------------------------
  // UI state setters
  // ---------------------------------------------------------------------------

  setSearchQuery: (query: string) => {
    set({ searchQuery: query, page: 1 });
  },

  setSortField: (field: string) => {
    set({ sortField: field, page: 1 });
  },

  setSortDirection: (direction: "asc" | "desc") => {
    set({ sortDirection: direction, page: 1 });
  },

  setPage: (page: number) => {
    set({ page });
  },

  setPageSize: (size: number) => {
    set({ pageSize: size, page: 1 });
  },
}));
