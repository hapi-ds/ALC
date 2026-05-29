// TypeScript types for admin user management, roles, permission templates, and memberships.
// Mirrors backend Pydantic schemas in src/backend/src/alcoabase/schemas/admin_*.py

// --- User Management ---

export interface UserListItem {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface MembershipInfo {
  id: number;
  company_id: number;
  company_name: string;
  role: string;
  created_at: string;
  revoked_at: string | null;
}

export interface UserDetail {
  id: number;
  username: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  memberships: MembershipInfo[];
}

export interface UserCreatePayload {
  username: string;
  email: string;
  full_name: string;
  role: "system_admin" | "doc_admin" | "it_admin" | "member" | "viewer";
}

export interface UserUpdatePayload {
  full_name?: string;
  email?: string;
  role?: "system_admin" | "doc_admin" | "it_admin" | "member" | "viewer";
}

export interface CreateUserResponse {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  temporary_password: string;
}

export interface UserHistoryEntry {
  version_id: number;
  changed_at: string;
  changed_by: number;
  changed_by_username: string;
  change_reason: string;
  changes: Record<string, { old: unknown; new: unknown }>;
}

// --- Roles ---

export interface PermissionEntry {
  resource: string;
  actions: ("create" | "read" | "update" | "delete" | "approve")[];
}

export interface RoleWithCount {
  id: number;
  name: string;
  description: string | null;
  is_system: boolean;
  user_count: number;
}

export interface RoleDetail {
  id: number;
  name: string;
  description: string | null;
  is_system: boolean;
  permissions: Record<string, string[]>;
  user_count: number;
}

// --- Permission Templates ---

export interface RoleActionMapping {
  role: "system_admin" | "doc_admin" | "it_admin" | "member" | "viewer";
  actions: ("read" | "write" | "approve")[];
}

export interface PermissionTemplate {
  id: number;
  name: string;
  description: string | null;
  document_type: string;
  role_permissions: Record<string, string[]>;
  is_default: boolean;
  created_by: number;
  created_at: string;
  active_document_count: number;
}

export interface PermissionTemplateDetail {
  id: number;
  name: string;
  description: string | null;
  document_type: string;
  role_permissions: Record<string, string[]>;
  is_default: boolean;
  created_by: number;
  created_at: string;
  active_document_count: number;
}

export interface CreateTemplatePayload {
  name: string;
  description?: string | null;
  document_type: string;
  role_permissions: RoleActionMapping[];
}

export interface UpdateTemplatePayload {
  name?: string;
  description?: string | null;
  role_permissions?: RoleActionMapping[];
}

// --- Memberships ---

export interface AssignMembershipPayload {
  user_id: number;
  company_id: number;
  role: "system_admin" | "doc_admin" | "it_admin" | "member" | "viewer";
}

export interface MembershipDetail {
  id: number;
  user_id: number;
  user_username: string;
  user_full_name: string;
  company_id: number;
  company_name: string;
  role: string;
  created_at: string;
  revoked_at: string | null;
}

// --- Filter/Pagination ---

export interface UserListParams {
  search?: string;
  sort_by?: "full_name" | "username" | "role" | "is_active" | "created_at";
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
  is_active?: boolean;
}

export interface PaginatedResponse<T> {
  users: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
