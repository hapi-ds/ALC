/**
 * AuditTrailFilters — Filter bar for the Audit Trail Viewer.
 *
 * Provides user selection (searchable), date range pickers, record type
 * dropdown, operation type dropdown, search input, and a clear-all button.
 * All filter changes update the Zustand store which triggers a refetch.
 *
 * Validates: Requirements 3.6, 5.4, 10.6
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { Search, X, Calendar, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuditTrailStore } from "@/stores/useAuditTrailStore";
import { apiClient } from "@/lib/apiClient";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RECORD_TYPES = [
  { value: "documents", label: "Documents" },
  { value: "templates", label: "Templates" },
  { value: "reports", label: "Reports" },
  { value: "workflows", label: "Workflows" },
  { value: "signatures", label: "Signatures" },
  { value: "training_tasks", label: "Training Tasks" },
  { value: "training_records", label: "Training Records" },
] as const;

const OPERATION_TYPES = [
  { value: "INSERT", label: "INSERT" },
  { value: "UPDATE", label: "UPDATE" },
  { value: "DELETE", label: "DELETE" },
] as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserOption {
  id: number;
  display_name: string;
  username: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AuditTrailFilters() {
  const { filters, searchQuery, setFilters, setSearchQuery, resetFilters } =
    useAuditTrailStore();

  // Local state for search input (submit-on-enter)
  const [localSearch, setLocalSearch] = useState(searchQuery);

  // User dropdown state
  const [users, setUsers] = useState<UserOption[]>([]);
  const [userSearchTerm, setUserSearchTerm] = useState("");
  const [isUserDropdownOpen, setIsUserDropdownOpen] = useState(false);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const userDropdownRef = useRef<HTMLDivElement>(null);

  // Fetch users for the dropdown
  const fetchUsers = useCallback(async (search: string) => {
    setIsLoadingUsers(true);
    try {
      const params = new URLSearchParams();
      if (search.trim()) {
        params.set("search", search.trim());
      }
      params.set("page_size", "20");
      const url = `/api/admin/users?${params.toString()}`;
      const response = await apiClient.get<{ users: UserOption[] }>(url);
      setUsers(response.users ?? []);
    } catch {
      setUsers([]);
    } finally {
      setIsLoadingUsers(false);
    }
  }, []);

  // Fetch users when dropdown opens or search term changes
  useEffect(() => {
    if (isUserDropdownOpen) {
      const timer = setTimeout(() => {
        fetchUsers(userSearchTerm);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [isUserDropdownOpen, userSearchTerm, fetchUsers]);

  // Close user dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        userDropdownRef.current &&
        !userDropdownRef.current.contains(event.target as Node)
      ) {
        setIsUserDropdownOpen(false);
      }
    }

    if (isUserDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isUserDropdownOpen]);

  // Handlers
  function handleUserSelect(user: UserOption) {
    setFilters({ ...filters, user_id: user.id });
    setIsUserDropdownOpen(false);
    setUserSearchTerm("");
  }

  function handleClearUser() {
    const { user_id: _user_id, ...rest } = filters;
    void _user_id;
    setFilters(rest);
  }

  function handleDateStartChange(value: string) {
    if (value) {
      setFilters({ ...filters, date_start: value });
    } else {
      const { date_start: _date_start, ...rest } = filters;
      void _date_start;
      setFilters(rest);
    }
  }

  function handleDateEndChange(value: string) {
    if (value) {
      setFilters({ ...filters, date_end: value });
    } else {
      const { date_end: _date_end, ...rest } = filters;
      void _date_end;
      setFilters(rest);
    }
  }

  function handleRecordTypeChange(value: string) {
    if (value) {
      setFilters({ ...filters, record_type: value });
    } else {
      const { record_type: _record_type, ...rest } = filters;
      void _record_type;
      setFilters(rest);
    }
  }

  function handleOperationTypeChange(value: string) {
    if (value) {
      setFilters({
        ...filters,
        operation_type: value as "INSERT" | "UPDATE" | "DELETE",
      });
    } else {
      const { operation_type: _operation_type, ...rest } = filters;
      void _operation_type;
      setFilters(rest);
    }
  }

  function handleSearchKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      setSearchQuery(localSearch);
    }
  }

  function handleClearAll() {
    setLocalSearch("");
    setUserSearchTerm("");
    resetFilters();
  }

  const hasActiveFilters =
    filters.user_id !== undefined ||
    filters.date_start !== undefined ||
    filters.date_end !== undefined ||
    filters.record_type !== undefined ||
    filters.operation_type !== undefined ||
    searchQuery.trim().length > 0;

  // Find selected user display name
  const selectedUserLabel = filters.user_id
    ? users.find((u) => u.id === filters.user_id)?.display_name ??
      users.find((u) => u.id === filters.user_id)?.username ??
      `User #${filters.user_id}`
    : null;

  return (
    <div
      className="flex flex-wrap items-end gap-3"
      role="search"
      aria-label="Audit trail filters"
    >
      {/* User selection dropdown (searchable) */}
      <div className="relative min-w-[180px]" ref={userDropdownRef}>
        <label
          htmlFor="filter-user"
          className="mb-1 block text-xs font-medium text-muted-foreground"
        >
          User
        </label>
        <button
          id="filter-user"
          type="button"
          onClick={() => setIsUserDropdownOpen(!isUserDropdownOpen)}
          className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-expanded={isUserDropdownOpen}
          aria-haspopup="listbox"
        >
          <span className={selectedUserLabel ? "text-foreground" : "text-muted-foreground"}>
            {selectedUserLabel ?? "All users"}
          </span>
          <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        </button>

        {isUserDropdownOpen && (
          <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-card shadow-lg">
            <div className="p-2">
              <input
                type="text"
                value={userSearchTerm}
                onChange={(e) => setUserSearchTerm(e.target.value)}
                placeholder="Search users..."
                className="flex h-8 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                autoFocus
                aria-label="Search users"
              />
            </div>
            <ul
              role="listbox"
              className="max-h-48 overflow-y-auto px-1 pb-1"
              aria-label="User options"
            >
              {filters.user_id !== undefined && (
                <li
                  role="option"
                  aria-selected={false}
                  className="cursor-pointer rounded-sm px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent"
                  onClick={() => handleClearUser()}
                >
                  All users
                </li>
              )}
              {isLoadingUsers ? (
                <li className="px-2 py-1.5 text-sm text-muted-foreground italic">
                  Loading...
                </li>
              ) : users.length === 0 ? (
                <li className="px-2 py-1.5 text-sm text-muted-foreground italic">
                  No users found
                </li>
              ) : (
                users.map((user) => (
                  <li
                    key={user.id}
                    role="option"
                    aria-selected={filters.user_id === user.id}
                    className={`cursor-pointer rounded-sm px-2 py-1.5 text-sm hover:bg-accent ${
                      filters.user_id === user.id
                        ? "bg-accent font-medium"
                        : ""
                    }`}
                    onClick={() => handleUserSelect(user)}
                  >
                    {user.display_name || user.username}
                  </li>
                ))
              )}
            </ul>
          </div>
        )}
      </div>

      {/* Date range: start */}
      <div className="min-w-[150px]">
        <label
          htmlFor="filter-date-start"
          className="mb-1 block text-xs font-medium text-muted-foreground"
        >
          <Calendar className="inline h-3 w-3 mr-1" aria-hidden="true" />
          From
        </label>
        <input
          id="filter-date-start"
          type="date"
          value={filters.date_start ?? ""}
          onChange={(e) => handleDateStartChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="Filter start date"
        />
      </div>

      {/* Date range: end */}
      <div className="min-w-[150px]">
        <label
          htmlFor="filter-date-end"
          className="mb-1 block text-xs font-medium text-muted-foreground"
        >
          <Calendar className="inline h-3 w-3 mr-1" aria-hidden="true" />
          To
        </label>
        <input
          id="filter-date-end"
          type="date"
          value={filters.date_end ?? ""}
          onChange={(e) => handleDateEndChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="Filter end date"
        />
      </div>

      {/* Record type dropdown */}
      <div className="min-w-[160px]">
        <label
          htmlFor="filter-record-type"
          className="mb-1 block text-xs font-medium text-muted-foreground"
        >
          Record Type
        </label>
        <select
          id="filter-record-type"
          value={filters.record_type ?? ""}
          onChange={(e) => handleRecordTypeChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="Filter by record type"
        >
          <option value="">All types</option>
          {RECORD_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
      </div>

      {/* Operation type dropdown */}
      <div className="min-w-[130px]">
        <label
          htmlFor="filter-operation-type"
          className="mb-1 block text-xs font-medium text-muted-foreground"
        >
          Operation
        </label>
        <select
          id="filter-operation-type"
          value={filters.operation_type ?? ""}
          onChange={(e) => handleOperationTypeChange(e.target.value)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="Filter by operation type"
        >
          <option value="">All operations</option>
          {OPERATION_TYPES.map((op) => (
            <option key={op.value} value={op.value}>
              {op.label}
            </option>
          ))}
        </select>
      </div>

      {/* Search input (submit-on-enter) */}
      <div className="flex-1 min-w-[200px]">
        <label
          htmlFor="filter-search"
          className="mb-1 block text-xs font-medium text-muted-foreground"
        >
          Search
        </label>
        <div className="relative">
          <Search
            className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            id="filter-search"
            type="text"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search change reasons, users, records..."
            className="flex h-9 w-full rounded-md border border-input bg-transparent pl-9 pr-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            aria-label="Search audit events"
          />
        </div>
      </div>

      {/* Clear filters button */}
      {hasActiveFilters && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleClearAll}
          aria-label="Clear all filters"
          className="h-9"
        >
          <X className="h-4 w-4 mr-1" aria-hidden="true" />
          Clear filters
        </Button>
      )}
    </div>
  );
}
