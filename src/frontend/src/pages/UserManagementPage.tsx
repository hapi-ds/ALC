import { useEffect, useState, useCallback } from "react";
import {
  Search,
  UserPlus,
  Users,
  AlertCircle,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAdminStore } from "@/stores/adminStore";
import type { UserListItem } from "@/types/admin";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortField = "full_name" | "username" | "role" | "is_active" | "created_at";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

const ROLE_BADGE_COLORS: Record<string, string> = {
  system_admin: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
  doc_admin: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  it_admin: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
  member: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  viewer: "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300",
};

const ROLE_LABELS: Record<string, string> = {
  system_admin: "System Admin",
  doc_admin: "Doc Admin",
  it_admin: "IT Admin",
  member: "Member",
  viewer: "Viewer",
};

// ---------------------------------------------------------------------------
// Helper Components
// ---------------------------------------------------------------------------

function RoleBadge({ role }: { role: string }) {
  const colorClass = ROLE_BADGE_COLORS[role] ?? "bg-gray-100 text-gray-800";
  const label = ROLE_LABELS[role] ?? role;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${colorClass}`}
    >
      {label}
    </span>
  );
}

function ActiveStatusIndicator({ isActive }: { isActive: boolean }) {
  if (isActive) {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-green-700 dark:text-green-400">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        <span>Active</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-sm text-red-600 dark:text-red-400">
      <XCircle className="h-4 w-4" aria-hidden="true" />
      <span>Inactive</span>
    </span>
  );
}

function SortIcon({
  field,
  currentField,
  direction,
}: {
  field: SortField;
  currentField: string;
  direction: "asc" | "desc";
}) {
  if (field !== currentField) {
    return <ArrowUpDown className="h-3.5 w-3.5 opacity-50" aria-hidden="true" />;
  }
  if (direction === "asc") {
    return <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />;
  }
  return <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />;
}

function TableSkeleton() {
  return (
    <div className="space-y-3" aria-label="Loading users">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 rounded-md border border-border p-4 animate-pulse"
        >
          <div className="h-4 w-32 rounded bg-muted" />
          <div className="h-4 w-24 rounded bg-muted" />
          <div className="h-4 w-40 rounded bg-muted" />
          <div className="h-5 w-20 rounded-full bg-muted" />
          <div className="h-4 w-16 rounded bg-muted" />
          <div className="h-4 w-24 rounded bg-muted" />
        </div>
      ))}
      <span className="sr-only">Loading users</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function UserManagementPage() {
  const {
    users,
    totalUsers,
    isLoading,
    error,
    searchQuery,
    sortField,
    sortDirection,
    page,
    pageSize,
    fetchUsers,
    setSearchQuery,
    setSortField,
    setSortDirection,
    setPage,
    setPageSize,
  } = useAdminStore();

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<UserListItem | null>(null);

  // Fetch users on mount and when pagination/sort/search state changes
  useEffect(() => {
    fetchUsers();
  }, [fetchUsers, searchQuery, sortField, sortDirection, page, pageSize]);

  // Debounced search handler
  const [searchInput, setSearchInput] = useState(searchQuery);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchQuery(searchInput);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput, setSearchQuery]);

  const handleSort = useCallback(
    (field: SortField) => {
      if (sortField === field) {
        setSortDirection(sortDirection === "asc" ? "desc" : "asc");
      } else {
        setSortField(field);
        setSortDirection("asc");
      }
    },
    [sortField, sortDirection, setSortField, setSortDirection],
  );

  const handleRowClick = useCallback((user: UserListItem) => {
    setSelectedUser(user);
  }, []);

  const handlePageSizeChange = useCallback(
    (newSize: number) => {
      setPageSize(newSize);
    },
    [setPageSize],
  );

  const totalPages = Math.ceil(totalUsers / pageSize) || 1;
  const isPrevDisabled = page <= 1;
  const isNextDisabled = page >= totalPages;

  // Column definitions for the sortable header
  const columns: { key: SortField; label: string }[] = [
    { key: "full_name", label: "Full Name" },
    { key: "username", label: "Username" },
    { key: "role", label: "Role" },
    { key: "is_active", label: "Status" },
    { key: "created_at", label: "Created" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">User Management</h2>
          <p className="text-sm text-muted-foreground">
            Create, edit, and manage user accounts
          </p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <UserPlus className="h-4 w-4 mr-2" aria-hidden="true" />
          Create User
        </Button>
      </div>

      {/* Search bar */}
      <div className="relative" role="search" aria-label="Search users">
        <label htmlFor="user-search" className="sr-only">
          Search by username, email, or full name
        </label>
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          id="user-search"
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search by username, email, or full name..."
          className="flex h-9 w-full rounded-md border border-input bg-transparent pl-9 pr-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{error}</p>
        </div>
      )}

      {/* Loading state */}
      {isLoading && <TableSkeleton />}

      {/* Empty state */}
      {!isLoading && !error && users.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <Users className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
          <p className="text-lg font-medium">No users found</p>
          <p className="text-sm mt-1">
            {searchQuery
              ? "Try adjusting your search query"
              : "Create your first user to get started"}
          </p>
        </div>
      )}

      {/* User table */}
      {!isLoading && users.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm" aria-label="Users table">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    className="px-4 py-3 text-left font-medium text-muted-foreground"
                  >
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
                      onClick={() => handleSort(col.key)}
                      aria-label={`Sort by ${col.label}`}
                    >
                      {col.label}
                      <SortIcon
                        field={col.key}
                        currentField={sortField}
                        direction={sortDirection}
                      />
                    </button>
                  </th>
                ))}
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  Email
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((user) => (
                <tr
                  key={user.id}
                  className="hover:bg-muted/50 cursor-pointer transition-colors"
                  onClick={() => handleRowClick(user)}
                  role="button"
                  tabIndex={0}
                  aria-label={`View details for ${user.full_name}`}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleRowClick(user);
                    }
                  }}
                >
                  <td className="px-4 py-3 font-medium">{user.full_name}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {user.username}
                  </td>
                  <td className="px-4 py-3">
                    <RoleBadge role={user.role} />
                  </td>
                  <td className="px-4 py-3">
                    <ActiveStatusIndicator isActive={user.is_active} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {user.email}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination controls */}
      {!isLoading && users.length > 0 && (
        <div
          className="flex items-center justify-between py-2"
          role="navigation"
          aria-label="Pagination"
        >
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>
              {totalUsers} {totalUsers === 1 ? "user" : "users"} total
            </span>
            <span className="text-border">|</span>
            <label htmlFor="page-size-select" className="sr-only">
              Rows per page
            </label>
            <select
              id="page-size-select"
              value={pageSize}
              onChange={(e) => handlePageSizeChange(Number(e.target.value))}
              className="h-8 rounded-md border border-input bg-transparent px-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              aria-label="Rows per page"
            >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {size} per page
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage(page - 1)}
              disabled={isPrevDisabled}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Previous
            </Button>

            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage(page + 1)}
              disabled={isNextDisabled}
              aria-label="Next page"
            >
              Next
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      )}

      {/* UserCreateDialog placeholder — will be implemented in task 13.2 */}
      {createDialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          role="dialog"
          aria-modal="true"
          aria-label="Create User"
        >
          <div className="bg-background rounded-lg border border-border p-6 shadow-lg max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-2">Create User</h3>
            <p className="text-sm text-muted-foreground mb-4">
              User creation form will be implemented in a subsequent task.
            </p>
            <Button
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
            >
              Close
            </Button>
          </div>
        </div>
      )}

      {/* UserDetailPanel placeholder — will be implemented in task 13.4 */}
      {selectedUser && (
        <div
          className="fixed inset-y-0 right-0 z-50 w-full max-w-md border-l border-border bg-background shadow-lg"
          role="dialog"
          aria-modal="true"
          aria-label={`User details for ${selectedUser.full_name}`}
        >
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">{selectedUser.full_name}</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedUser(null)}
                aria-label="Close panel"
              >
                ✕
              </Button>
            </div>
            <div className="space-y-2 text-sm">
              <p>
                <span className="text-muted-foreground">Username:</span>{" "}
                {selectedUser.username}
              </p>
              <p>
                <span className="text-muted-foreground">Email:</span>{" "}
                {selectedUser.email}
              </p>
              <p>
                <span className="text-muted-foreground">Role:</span>{" "}
                <RoleBadge role={selectedUser.role} />
              </p>
              <p>
                <span className="text-muted-foreground">Status:</span>{" "}
                <ActiveStatusIndicator isActive={selectedUser.is_active} />
              </p>
              <p>
                <span className="text-muted-foreground">Created:</span>{" "}
                {new Date(selectedUser.created_at).toLocaleDateString()}
              </p>
            </div>
            <p className="text-xs text-muted-foreground italic">
              Full detail panel will be implemented in a subsequent task.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
