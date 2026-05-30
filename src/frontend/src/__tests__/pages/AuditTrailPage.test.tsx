import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for Audit Trail Viewer frontend components.
 *
 * Covers:
 * - Component rendering (table, filters, detail panel, export button)
 * - Loading/empty/error states
 * - Column sorting interaction
 * - Export button behavior (sync vs async feedback)
 * - Route guard enforcement
 *
 * Validates: Requirements 2.4, 3.6, 5.4, 6.1–6.5, 7.7–7.9, 9.3, 10.1–10.6
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
    constructor(status: number, body: string, url: string = "/api/audit-trail") {
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

vi.mock("../../lib/tokenStorage", () => ({
  getAccessToken: vi.fn(() => "mock-token"),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(() => null),
}));

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock react-router-dom for AdminRouteGuard tests
const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  Navigate: ({ to, replace }: { to: string; replace?: boolean }) => {
    mockNavigate(to, replace);
    return <div data-testid="navigate-redirect">Redirected to {to}</div>;
  },
  useNavigate: () => mockNavigate,
}));

vi.mock("../../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (state: unknown) => unknown) => {
      const state = {
        user: {
          id: 1,
          username: "admin",
          email: "admin@test.com",
          full_name: "Admin User",
          roles: ["system_admin"],
        },
        isAuthenticated: true,
        activeCompanyId: 1,
      };
      if (selector) return selector(state);
      return state;
    }),
    { getState: () => ({ user: { id: 1, roles: ["system_admin"] }, activeCompanyId: 1 }) }
  ),
}));

import { useAuditTrailStore } from "../../stores/useAuditTrailStore";
import { AuditTrailTable } from "../../components/AuditTrailTable";
import { AuditTrailFilters } from "../../components/AuditTrailFilters";
import { AuditEventDetailPanel } from "../../components/AuditEventDetailPanel";
import { AuditExportButton } from "../../components/AuditExportButton";
import { AdminRouteGuard } from "../../components/auth/AdminRouteGuard";
import { useAuthStore } from "../../stores/authStore";
import type { AuditEvent, AuditEventDetail as AuditEventDetailType } from "../../types/auditTrail";

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockEvents: AuditEvent[] = [
  {
    transaction_id: 100,
    timestamp: "2024-06-15T10:30:00Z",
    user_id: 1,
    user_display_name: "Alice Johnson",
    record_type: "documents",
    record_id: 42,
    operation_type: "UPDATE",
    change_reason: "Updated document title for clarity",
    changed_fields: ["title", "description"],
    total_changed_fields: 2,
    company_id: 1,
  },
  {
    transaction_id: 101,
    timestamp: "2024-06-15T09:15:00Z",
    user_id: 2,
    user_display_name: "Bob Smith",
    record_type: "templates",
    record_id: 7,
    operation_type: "INSERT",
    change_reason: "Created new SOP template",
    changed_fields: ["name", "content", "version", "status"],
    total_changed_fields: 4,
    company_id: 1,
  },
  {
    transaction_id: 102,
    timestamp: "2024-06-14T16:45:00Z",
    user_id: 3,
    user_display_name: null,
    record_type: "workflows",
    record_id: 15,
    operation_type: "DELETE",
    change_reason: null,
    changed_fields: [],
    total_changed_fields: 0,
    company_id: 1,
  },
];

const mockEventWithManyFields: AuditEvent = {
  transaction_id: 200,
  timestamp: "2024-06-15T12:00:00Z",
  user_id: 1,
  user_display_name: "Alice Johnson",
  record_type: "reports",
  record_id: 99,
  operation_type: "UPDATE",
  change_reason: "Bulk update of report fields for compliance review",
  changed_fields: ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10"],
  total_changed_fields: 15,
  company_id: 1,
};

const mockEventDetail: AuditEventDetailType = {
  transaction_id: 100,
  timestamp: "2024-06-15T10:30:00Z",
  user_id: 1,
  user_display_name: "Alice Johnson",
  record_type: "documents",
  record_id: 42,
  operation_type: "UPDATE",
  change_reason: "Updated document title for clarity",
  field_changes: [
    { field_name: "title", old_value: "Old Title", new_value: "New Title" },
    { field_name: "description", old_value: "Old desc", new_value: "New desc" },
  ],
  company_id: 1,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetAuditStore(overrides: Partial<ReturnType<typeof useAuditTrailStore.getState>> = {}) {
  useAuditTrailStore.setState({
    events: [],
    filters: {},
    searchQuery: "",
    cursor: null,
    totalCount: 0,
    isLoading: false,
    selectedEvent: null,
    exportStatus: null,
    sort: { column: "timestamp", direction: "desc" },
    warnings: [],
    fetchEvents: vi.fn().mockResolvedValue(undefined),
    fetchNextPage: vi.fn().mockResolvedValue(undefined),
    fetchEventDetail: vi.fn().mockResolvedValue(undefined),
    setFilters: vi.fn(),
    setSearchQuery: vi.fn(),
    setSort: vi.fn(),
    triggerExport: vi.fn().mockResolvedValue(undefined),
    checkExportStatus: vi.fn().mockResolvedValue(undefined),
    clearSelectedEvent: vi.fn(),
    resetFilters: vi.fn(),
    ...overrides,
  } as unknown as Partial<ReturnType<typeof useAuditTrailStore.getState>>);
}

// ---------------------------------------------------------------------------
// Tests: AuditTrailTable
// ---------------------------------------------------------------------------

describe("AuditTrailTable", () => {
  beforeEach(() => {
    resetAuditStore({ events: mockEvents, totalCount: 3 });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering (Requirement 10.2)", () => {
    it("renders table with correct column headers", () => {
      render(<AuditTrailTable />);

      expect(screen.getByText("Timestamp")).toBeDefined();
      expect(screen.getByText("User")).toBeDefined();
      expect(screen.getByText("Record Type")).toBeDefined();
      expect(screen.getByText("Record ID")).toBeDefined();
      expect(screen.getByText("Operation")).toBeDefined();
      expect(screen.getByText("Change Reason")).toBeDefined();
      expect(screen.getByText("Changed Fields")).toBeDefined();
    });

    it("renders event rows with correct data", () => {
      render(<AuditTrailTable />);

      expect(screen.getByText("Alice Johnson")).toBeDefined();
      expect(screen.getByText("Bob Smith")).toBeDefined();
      // User with null display_name shows fallback
      expect(screen.getByText("User #3")).toBeDefined();
    });

    it("renders operation type badges", () => {
      render(<AuditTrailTable />);

      expect(screen.getByText("UPDATE")).toBeDefined();
      expect(screen.getByText("INSERT")).toBeDefined();
      expect(screen.getByText("DELETE")).toBeDefined();
    });

    it("renders record types", () => {
      render(<AuditTrailTable />);

      expect(screen.getByText("documents")).toBeDefined();
      expect(screen.getByText("templates")).toBeDefined();
      expect(screen.getByText("workflows")).toBeDefined();
    });

    it("displays total count indicator", () => {
      render(<AuditTrailTable />);

      // "Showing X of Y events" appears (may appear twice: top and bottom)
      const countTexts = screen.getAllByText("Showing 3 of 3 events");
      expect(countTexts.length).toBeGreaterThanOrEqual(1);
    });

    it("shows dash for null change_reason", () => {
      render(<AuditTrailTable />);

      // The DELETE event has null change_reason, should show "—"
      const dashes = screen.getAllByText("—");
      expect(dashes.length).toBeGreaterThanOrEqual(1);
    });

    it("shows +N more indicator when total_changed_fields exceeds displayed", () => {
      resetAuditStore({ events: [mockEventWithManyFields], totalCount: 1 });
      render(<AuditTrailTable />);

      expect(screen.getByText("+5 more")).toBeDefined();
    });
  });

  describe("Loading state (Requirement 10.4)", () => {
    it("renders skeleton rows when loading with no events", () => {
      resetAuditStore({ isLoading: true, events: [], totalCount: 0 });
      render(<AuditTrailTable />);

      const table = screen.getByLabelText("Audit trail events loading");
      expect(table).toBeDefined();
    });
  });

  describe("Empty state (Requirement 10.5)", () => {
    it("shows empty state message when no events match filters", () => {
      resetAuditStore({ isLoading: false, events: [], totalCount: 0 });
      render(<AuditTrailTable />);

      expect(
        screen.getByText("No audit events match the current filters.")
      ).toBeDefined();
    });
  });

  describe("Column sorting (Requirement 10.3)", () => {
    it("calls setSort when clicking a sortable column header", () => {
      const mockSetSort = vi.fn();
      resetAuditStore({ events: mockEvents, totalCount: 3, setSort: mockSetSort });
      render(<AuditTrailTable />);

      // Click on "User" header to sort
      const userSortButton = screen.getByLabelText(/Sort by User/);
      fireEvent.click(userSortButton);

      expect(mockSetSort).toHaveBeenCalledWith({ column: "user", direction: "desc" });
    });

    it("toggles sort direction when clicking the active column", () => {
      const mockSetSort = vi.fn();
      resetAuditStore({
        events: mockEvents,
        totalCount: 3,
        sort: { column: "timestamp", direction: "desc" },
        setSort: mockSetSort,
      });
      render(<AuditTrailTable />);

      // Click on "Timestamp" header (already active, desc → asc)
      const timestampSortButton = screen.getByLabelText(/Sort by Timestamp/);
      fireEvent.click(timestampSortButton);

      expect(mockSetSort).toHaveBeenCalledWith({ column: "timestamp", direction: "asc" });
    });
  });

  describe("Pagination", () => {
    it("shows Load more button when cursor is available", () => {
      resetAuditStore({ events: mockEvents, totalCount: 100, cursor: "next-cursor-abc" });
      render(<AuditTrailTable />);

      expect(screen.getByText("Load more")).toBeDefined();
    });

    it("does not show Load more button when cursor is null", () => {
      resetAuditStore({ events: mockEvents, totalCount: 3, cursor: null });
      render(<AuditTrailTable />);

      expect(screen.queryByText("Load more")).toBeNull();
    });

    it("calls fetchNextPage when Load more is clicked", () => {
      const mockFetchNextPage = vi.fn().mockResolvedValue(undefined);
      resetAuditStore({
        events: mockEvents,
        totalCount: 100,
        cursor: "next-cursor-abc",
        fetchNextPage: mockFetchNextPage,
      });
      render(<AuditTrailTable />);

      fireEvent.click(screen.getByText("Load more"));
      expect(mockFetchNextPage).toHaveBeenCalled();
    });
  });

  describe("Row click opens detail", () => {
    it("calls fetchEventDetail when a row is clicked", () => {
      const mockFetchEventDetail = vi.fn().mockResolvedValue(undefined);
      resetAuditStore({
        events: mockEvents,
        totalCount: 3,
        fetchEventDetail: mockFetchEventDetail,
      });
      render(<AuditTrailTable />);

      // Click on the first row (Alice Johnson's UPDATE event)
      const row = screen.getByLabelText(
        "UPDATE on documents 42 by Alice Johnson"
      );
      fireEvent.click(row);

      expect(mockFetchEventDetail).toHaveBeenCalledWith("documents", 42, 100);
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: AuditTrailFilters
// ---------------------------------------------------------------------------

describe("AuditTrailFilters", () => {
  beforeEach(() => {
    resetAuditStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering (Requirement 3.6)", () => {
    it("renders filter controls", () => {
      render(<AuditTrailFilters />);

      expect(screen.getByLabelText("Filter by record type")).toBeDefined();
      expect(screen.getByLabelText("Filter by operation type")).toBeDefined();
      expect(screen.getByLabelText("Filter start date")).toBeDefined();
      expect(screen.getByLabelText("Filter end date")).toBeDefined();
      expect(screen.getByLabelText("Search audit events")).toBeDefined();
    });

    it("renders record type dropdown with all options", () => {
      render(<AuditTrailFilters />);

      const select = screen.getByLabelText("Filter by record type") as HTMLSelectElement;
      expect(select.options.length).toBe(8); // "All types" + 7 record types
    });

    it("renders operation type dropdown with all options", () => {
      render(<AuditTrailFilters />);

      const select = screen.getByLabelText("Filter by operation type") as HTMLSelectElement;
      expect(select.options.length).toBe(4); // "All operations" + INSERT, UPDATE, DELETE
    });
  });

  describe("Filter interactions", () => {
    it("calls setFilters when record type is changed", () => {
      const mockSetFilters = vi.fn();
      resetAuditStore({ setFilters: mockSetFilters });
      render(<AuditTrailFilters />);

      const select = screen.getByLabelText("Filter by record type");
      fireEvent.change(select, { target: { value: "documents" } });

      expect(mockSetFilters).toHaveBeenCalledWith({ record_type: "documents" });
    });

    it("calls setFilters when operation type is changed", () => {
      const mockSetFilters = vi.fn();
      resetAuditStore({ setFilters: mockSetFilters });
      render(<AuditTrailFilters />);

      const select = screen.getByLabelText("Filter by operation type");
      fireEvent.change(select, { target: { value: "DELETE" } });

      expect(mockSetFilters).toHaveBeenCalledWith({ operation_type: "DELETE" });
    });

    it("calls setSearchQuery on Enter key in search input", () => {
      const mockSetSearchQuery = vi.fn();
      resetAuditStore({ setSearchQuery: mockSetSearchQuery });
      render(<AuditTrailFilters />);

      const searchInput = screen.getByLabelText("Search audit events");
      fireEvent.change(searchInput, { target: { value: "compliance" } });
      fireEvent.keyDown(searchInput, { key: "Enter" });

      expect(mockSetSearchQuery).toHaveBeenCalledWith("compliance");
    });

    it("shows Clear filters button when filters are active", () => {
      resetAuditStore({ filters: { record_type: "documents" } });
      render(<AuditTrailFilters />);

      expect(screen.getByLabelText("Clear all filters")).toBeDefined();
    });

    it("does not show Clear filters button when no filters are active", () => {
      resetAuditStore({ filters: {}, searchQuery: "" });
      render(<AuditTrailFilters />);

      expect(screen.queryByLabelText("Clear all filters")).toBeNull();
    });

    it("calls resetFilters when Clear filters is clicked", () => {
      const mockResetFilters = vi.fn();
      resetAuditStore({
        filters: { record_type: "documents" },
        resetFilters: mockResetFilters,
      });
      render(<AuditTrailFilters />);

      fireEvent.click(screen.getByLabelText("Clear all filters"));
      expect(mockResetFilters).toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: AuditEventDetailPanel
// ---------------------------------------------------------------------------

describe("AuditEventDetailPanel", () => {
  beforeEach(() => {
    resetAuditStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering (Requirement 6.1–6.5)", () => {
    it("renders panel title and description when open", () => {
      resetAuditStore({ selectedEvent: mockEventDetail, isLoading: false });
      render(<AuditEventDetailPanel open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByText("Audit Event Detail")).toBeDefined();
      expect(
        screen.getByText("Full change details for the selected audit event.")
      ).toBeDefined();
    });

    it("displays event metadata when event is selected", () => {
      resetAuditStore({ selectedEvent: mockEventDetail, isLoading: false });
      render(<AuditEventDetailPanel open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByText("Alice Johnson")).toBeDefined();
      expect(screen.getByText("documents")).toBeDefined();
      expect(screen.getByText("42")).toBeDefined();
      expect(screen.getByText("UPDATE")).toBeDefined();
      expect(screen.getByText("Updated document title for clarity")).toBeDefined();
    });

    it("displays field changes table for UPDATE operation", () => {
      resetAuditStore({ selectedEvent: mockEventDetail, isLoading: false });
      render(<AuditEventDetailPanel open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByText("Previous Value")).toBeDefined();
      expect(screen.getByText("New Value")).toBeDefined();
      expect(screen.getByText("title")).toBeDefined();
      expect(screen.getByText(/"Old Title"/)).toBeDefined();
      expect(screen.getByText(/"New Title"/)).toBeDefined();
    });

    it("displays Initial Value column for INSERT operation", () => {
      const insertDetail: AuditEventDetailType = {
        ...mockEventDetail,
        operation_type: "INSERT",
        field_changes: [
          { field_name: "name", old_value: null, new_value: "New Document" },
        ],
      };
      resetAuditStore({ selectedEvent: insertDetail, isLoading: false });
      render(<AuditEventDetailPanel open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByText("Initial Value")).toBeDefined();
    });

    it("displays Final Value column for DELETE operation", () => {
      const deleteDetail: AuditEventDetailType = {
        ...mockEventDetail,
        operation_type: "DELETE",
        field_changes: [
          { field_name: "name", old_value: "Deleted Doc", new_value: null },
        ],
      };
      resetAuditStore({ selectedEvent: deleteDetail, isLoading: false });
      render(<AuditEventDetailPanel open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByText("Final Value")).toBeDefined();
    });

    it("shows loading skeleton when isLoading is true", () => {
      resetAuditStore({ selectedEvent: null, isLoading: true });
      render(<AuditEventDetailPanel open={true} onOpenChange={vi.fn()} />);

      // Skeleton should be present (animated pulse divs)
      expect(screen.queryByText("Alice Johnson")).toBeNull();
    });

    it("shows 'No event selected' when no event and not loading", () => {
      resetAuditStore({ selectedEvent: null, isLoading: false });
      render(<AuditEventDetailPanel open={true} onOpenChange={vi.fn()} />);

      expect(screen.getByText("No event selected.")).toBeDefined();
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: AuditExportButton
// ---------------------------------------------------------------------------

describe("AuditExportButton", () => {
  beforeEach(() => {
    resetAuditStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Rendering (Requirement 7.7)", () => {
    it("renders Export to PDF button", () => {
      resetAuditStore({ totalCount: 10 });
      render(<AuditExportButton />);

      expect(screen.getByText("Export to PDF")).toBeDefined();
    });

    it("button is disabled when totalCount is 0", () => {
      resetAuditStore({ totalCount: 0 });
      render(<AuditExportButton />);

      const button = screen.getByRole("button", { name: /Export to PDF/i });
      expect(button.hasAttribute("disabled")).toBe(true);
    });

    it("button is enabled when totalCount > 0", () => {
      resetAuditStore({ totalCount: 50 });
      render(<AuditExportButton />);

      const button = screen.getByRole("button", { name: /Export to PDF/i });
      expect(button.hasAttribute("disabled")).toBe(false);
    });
  });

  describe("Export behavior (Requirement 7.8, 7.9)", () => {
    it("calls triggerExport when clicked", () => {
      const mockTriggerExport = vi.fn().mockResolvedValue(undefined);
      resetAuditStore({ totalCount: 50, triggerExport: mockTriggerExport });
      render(<AuditExportButton />);

      const button = screen.getByRole("button", { name: /Export to PDF/i });
      fireEvent.click(button);

      expect(mockTriggerExport).toHaveBeenCalled();
    });

    it("shows Exporting… text when export is pending", () => {
      resetAuditStore({
        totalCount: 50,
        exportStatus: { job_id: "job-123", status: "pending" },
      });
      render(<AuditExportButton />);

      expect(screen.getByText("Exporting…")).toBeDefined();
    });

    it("shows Exporting… text when export is processing", () => {
      resetAuditStore({
        totalCount: 50,
        exportStatus: { job_id: "job-123", status: "processing" },
      });
      render(<AuditExportButton />);

      expect(screen.getByText("Exporting…")).toBeDefined();
    });

    it("button is disabled during export", () => {
      resetAuditStore({
        totalCount: 50,
        exportStatus: { job_id: "job-123", status: "pending" },
      });
      render(<AuditExportButton />);

      const button = screen.getByRole("button");
      expect(button.hasAttribute("disabled")).toBe(true);
    });
  });

  describe("Tooltip when disabled (Requirement 7.8)", () => {
    it("wraps disabled button in tooltip trigger for accessibility", () => {
      resetAuditStore({ totalCount: 0 });
      render(<AuditExportButton />);

      // When disabled, the button is wrapped in a span with tabIndex for tooltip trigger
      const wrapper = screen.getByRole("button", { name: /Export to PDF/i }).closest("span");
      expect(wrapper).toBeDefined();
      expect(wrapper?.getAttribute("tabindex")).toBe("0");
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: AdminRouteGuard
// ---------------------------------------------------------------------------

describe("AdminRouteGuard", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  describe("Route guard enforcement (Requirement 9.3)", () => {
    it("renders children when user has system_admin role", () => {
      (useAuthStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
        (selector?: (state: unknown) => unknown) => {
          const state = {
            user: { id: 1, roles: ["system_admin"] },
          };
          if (selector) return selector(state);
          return state;
        }
      );

      render(
        <AdminRouteGuard>
          <div data-testid="protected-content">Protected Content</div>
        </AdminRouteGuard>
      );

      expect(screen.getByTestId("protected-content")).toBeDefined();
    });

    it("renders children when user has doc_admin role", () => {
      (useAuthStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
        (selector?: (state: unknown) => unknown) => {
          const state = {
            user: { id: 2, roles: ["doc_admin"] },
          };
          if (selector) return selector(state);
          return state;
        }
      );

      render(
        <AdminRouteGuard>
          <div data-testid="protected-content">Protected Content</div>
        </AdminRouteGuard>
      );

      expect(screen.getByTestId("protected-content")).toBeDefined();
    });

    it("renders children when user has it_admin role", () => {
      (useAuthStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
        (selector?: (state: unknown) => unknown) => {
          const state = {
            user: { id: 3, roles: ["it_admin"] },
          };
          if (selector) return selector(state);
          return state;
        }
      );

      render(
        <AdminRouteGuard>
          <div data-testid="protected-content">Protected Content</div>
        </AdminRouteGuard>
      );

      expect(screen.getByTestId("protected-content")).toBeDefined();
    });

    it("redirects to / when user has only member role", () => {
      (useAuthStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
        (selector?: (state: unknown) => unknown) => {
          const state = {
            user: { id: 4, roles: ["member"] },
          };
          if (selector) return selector(state);
          return state;
        }
      );

      render(
        <AdminRouteGuard>
          <div data-testid="protected-content">Protected Content</div>
        </AdminRouteGuard>
      );

      expect(screen.queryByTestId("protected-content")).toBeNull();
      expect(screen.getByTestId("navigate-redirect")).toBeDefined();
    });

    it("redirects to / when user has no roles", () => {
      (useAuthStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
        (selector?: (state: unknown) => unknown) => {
          const state = {
            user: { id: 5, roles: [] },
          };
          if (selector) return selector(state);
          return state;
        }
      );

      render(
        <AdminRouteGuard>
          <div data-testid="protected-content">Protected Content</div>
        </AdminRouteGuard>
      );

      expect(screen.queryByTestId("protected-content")).toBeNull();
      expect(screen.getByTestId("navigate-redirect")).toBeDefined();
    });

    it("redirects to / when user is null", () => {
      (useAuthStore as unknown as ReturnType<typeof vi.fn>).mockImplementation(
        (selector?: (state: unknown) => unknown) => {
          const state = {
            user: null,
          };
          if (selector) return selector(state);
          return state;
        }
      );

      render(
        <AdminRouteGuard>
          <div data-testid="protected-content">Protected Content</div>
        </AdminRouteGuard>
      );

      expect(screen.queryByTestId("protected-content")).toBeNull();
      expect(screen.getByTestId("navigate-redirect")).toBeDefined();
    });
  });
});
