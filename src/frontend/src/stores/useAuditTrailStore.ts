/**
 * Zustand store for the Audit Trail Viewer.
 *
 * Manages state for listing, filtering, searching, paginating, and exporting
 * audit events. Communicates with the backend audit trail API endpoints.
 *
 * References:
 *   - Design doc: Frontend Components > Audit Trail Store
 *   - Requirements 2.4, 3.6, 5.4, 7.7, 10.1–10.6
 */

import { create } from "zustand";
import { apiClient } from "../lib/apiClient";
import { getAccessToken } from "../lib/tokenStorage";
import type {
  AuditEvent,
  AuditEventDetail,
  AuditTrailFilters,
  AuditTrailPage,
  ExportStatus,
  SortConfig,
} from "../types/auditTrail";

// ---------------------------------------------------------------------------
// State interface
// ---------------------------------------------------------------------------

export interface AuditTrailState {
  // Data
  events: AuditEvent[];
  filters: AuditTrailFilters;
  searchQuery: string;
  cursor: string | null;
  totalCount: number;
  isLoading: boolean;
  selectedEvent: AuditEventDetail | null;
  exportStatus: ExportStatus | null;
  sort: SortConfig;
  warnings: string[];

  // Actions
  fetchEvents: () => Promise<void>;
  fetchNextPage: () => Promise<void>;
  fetchEventDetail: (
    record_type: string,
    record_id: number,
    transaction_id: number
  ) => Promise<void>;
  setFilters: (filters: AuditTrailFilters) => void;
  setSearchQuery: (query: string) => void;
  setSort: (sort: SortConfig) => void;
  triggerExport: () => Promise<void>;
  checkExportStatus: (job_id: string) => Promise<void>;
  clearSelectedEvent: () => void;
  resetFilters: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_PAGE_SIZE = 50;

const DEFAULT_SORT: SortConfig = {
  column: "timestamp",
  direction: "desc",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build query string parameters from current store state.
 */
function buildQueryParams(
  filters: AuditTrailFilters,
  searchQuery: string,
  cursor: string | null,
  sort: SortConfig
): string {
  const params = new URLSearchParams();

  params.set("page_size", String(DEFAULT_PAGE_SIZE));

  if (cursor) {
    params.set("cursor", cursor);
  }

  if (searchQuery.trim()) {
    params.set("search", searchQuery.trim());
  }

  if (filters.user_id !== undefined) {
    params.set("user_id", String(filters.user_id));
  }
  if (filters.date_start) {
    params.set("date_start", filters.date_start);
  }
  if (filters.date_end) {
    params.set("date_end", filters.date_end);
  }
  if (filters.record_type) {
    params.set("record_type", filters.record_type);
  }
  if (filters.operation_type) {
    params.set("operation_type", filters.operation_type);
  }

  // Sort params (backend uses ordering via query params if supported)
  if (sort.column) {
    params.set("sort_column", sort.column);
  }
  if (sort.direction) {
    params.set("sort_direction", sort.direction);
  }

  return params.toString();
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useAuditTrailStore = create<AuditTrailState>((set, get) => ({
  // Initial state
  events: [],
  filters: {},
  searchQuery: "",
  cursor: null,
  totalCount: 0,
  isLoading: false,
  selectedEvent: null,
  exportStatus: null,
  sort: DEFAULT_SORT,
  warnings: [],

  fetchEvents: async () => {
    const { filters, searchQuery, sort } = get();
    set({ isLoading: true });

    try {
      const queryString = buildQueryParams(filters, searchQuery, null, sort);
      const response = await apiClient.get<AuditTrailPage>(
        `/api/audit-trail?${queryString}`
      );

      set({
        events: response.events,
        cursor: response.next_cursor,
        totalCount: response.total_count,
        warnings: response.warnings ?? [],
        isLoading: false,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch audit events";
      set({
        events: [],
        cursor: null,
        totalCount: 0,
        warnings: [message],
        isLoading: false,
      });
    }
  },

  fetchNextPage: async () => {
    const { filters, searchQuery, cursor, sort } = get();

    if (!cursor) return;

    set({ isLoading: true });

    try {
      const queryString = buildQueryParams(filters, searchQuery, cursor, sort);
      const response = await apiClient.get<AuditTrailPage>(
        `/api/audit-trail?${queryString}`
      );

      set((state) => ({
        events: [...state.events, ...response.events],
        cursor: response.next_cursor,
        totalCount: response.total_count,
        warnings: response.warnings ?? [],
        isLoading: false,
      }));
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to fetch next page of audit events";
      set((state) => ({
        warnings: [...state.warnings, message],
        isLoading: false,
      }));
    }
  },

  fetchEventDetail: async (
    record_type: string,
    record_id: number,
    transaction_id: number
  ) => {
    set({ isLoading: true });

    try {
      const response = await apiClient.get<AuditEventDetail>(
        `/api/audit-trail/${record_type}/${record_id}/${transaction_id}`
      );

      set({ selectedEvent: response, isLoading: false });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to fetch event detail";
      set({ selectedEvent: null, warnings: [message], isLoading: false });
    }
  },

  setFilters: (filters: AuditTrailFilters) => {
    set({ filters, cursor: null });
    get().fetchEvents();
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query, cursor: null });
    get().fetchEvents();
  },

  setSort: (sort: SortConfig) => {
    set({ sort, cursor: null });
    get().fetchEvents();
  },

  triggerExport: async () => {
    const { filters, searchQuery } = get();

    try {
      const body = {
        filters: Object.keys(filters).length > 0 ? filters : null,
        search_query: searchQuery.trim() || null,
      };

      // Use raw fetch for export since the response may be a PDF binary
      const token = getAccessToken();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Change-Reason": "Audit trail PDF export",
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch("/api/audit-trail/export", {
        method: "POST",
        headers,
        credentials: "include",
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Export failed: ${response.status} - ${errorText}`
        );
      }

      const contentType = response.headers.get("Content-Type") ?? "";

      if (contentType.includes("application/pdf")) {
        // Synchronous PDF response — trigger browser download
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "audit-trail-export.pdf";
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);

        URL.revokeObjectURL(url);
        set({ exportStatus: null });
      } else {
        // Async response — set export status for polling
        const data: ExportStatus = await response.json();
        set({ exportStatus: data });
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Export failed";
      set({
        exportStatus: {
          job_id: "",
          status: "failed",
          error_message: message,
        },
      });
    }
  },

  checkExportStatus: async (job_id: string) => {
    try {
      const response = await apiClient.get<ExportStatus>(
        `/api/audit-trail/export/${job_id}`
      );

      set({ exportStatus: response });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to check export status";
      set({
        exportStatus: {
          job_id,
          status: "failed",
          error_message: message,
        },
      });
    }
  },

  clearSelectedEvent: () => {
    set({ selectedEvent: null });
  },

  resetFilters: () => {
    set({ filters: {}, searchQuery: "", cursor: null });
    get().fetchEvents();
  },
}));
