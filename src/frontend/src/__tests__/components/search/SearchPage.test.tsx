import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useSearchStore } from "@/stores/searchStore";
import type { SearchState } from "@/stores/searchStore";

/**
 * Unit tests for SearchPage integration.
 *
 * Validates: Requirements 4.1, 4.2, 4.3, 4.5, 4.6, 5.3, 5.4, 5.5, 5.7, 8.1, 8.2, 8.5, 9.1, 9.4
 */

// Mock apiClient to prevent actual API calls
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
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
import { SearchPage } from "@/pages/SearchPage";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSearchResponse(overrides: Record<string, unknown> = {}) {
  return {
    results: [
      {
        document_uuid: "doc-001",
        title: "SOP Document",
        version: "1.0",
        excerpt: "This is a test excerpt with search terms",
        relevance_score: 0.85,
        document_type: "SOP",
        status: "Active",
        tags: ["GxP"],
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-06-01T00:00:00Z",
      },
    ],
    total: 1,
    total_available: 1,
    query: "test",
    offset: 0,
    filters_applied: {},
    ...overrides,
  };
}

const defaultState: Partial<SearchState> = {
  query: "",
  results: [],
  isSearching: false,
  error: null,
  filters: { document_type: [], status: [], tags: [] },
  offset: 0,
  limit: 20,
  totalAvailable: 0,
  sortBy: "relevance",
};

function renderSearchPage() {
  return render(
    <MemoryRouter>
      <SearchPage />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SearchPage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useSearchStore.setState(defaultState);
    vi.clearAllMocks();
    mockedApiClient.post.mockResolvedValue(makeSearchResponse());
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Renders search input with placeholder and icon
  // -------------------------------------------------------------------------

  describe("search input", () => {
    it("renders search input with placeholder and icon", () => {
      renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");
      expect(input).toBeDefined();
      expect(input.getAttribute("type")).toBe("search");
      expect(input.getAttribute("aria-label")).toBe("Search documents");

      // The form should have role="search"
      const form = screen.getByRole("search");
      expect(form).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Shows initial placeholder state
  // -------------------------------------------------------------------------

  describe("initial placeholder state", () => {
    it("shows initial placeholder state", () => {
      renderSearchPage();

      expect(
        screen.getByText("Enter a query to search across all documents")
      ).toBeDefined();
      expect(
        screen.getByText(
          "Results include Document-UUID, title, version, excerpt, and relevance score"
        )
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Debounce fires after 300ms
  // -------------------------------------------------------------------------

  describe("debounce", () => {
    it("fires search after 300ms debounce", async () => {
      renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: "test query" } });
      });

      // Should not have searched yet
      expect(mockedApiClient.post).not.toHaveBeenCalled();

      // Advance timers by 300ms
      await act(async () => {
        vi.advanceTimersByTime(300);
      });

      expect(mockedApiClient.post).toHaveBeenCalledTimes(1);
    });

    it("does not fire search before 300ms", async () => {
      renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: "test" } });
      });

      await act(async () => {
        vi.advanceTimersByTime(200);
      });

      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Enter key triggers immediate search
  // -------------------------------------------------------------------------

  describe("Enter key", () => {
    it("triggers immediate search on Enter", async () => {
      renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: "test query" } });
      });

      await act(async () => {
        fireEvent.keyDown(input, { key: "Enter" });
      });

      expect(mockedApiClient.post).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // Escape key clears input and results
  // -------------------------------------------------------------------------

  describe("Escape key", () => {
    it("clears input and results on Escape", async () => {
      useSearchStore.setState({
        ...defaultState,
        query: "test",
        results: makeSearchResponse().results,
        totalAvailable: 1,
      });

      renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: "test" } });
      });

      await act(async () => {
        fireEvent.keyDown(input, { key: "Escape" });
      });

      // Input should be cleared
      expect((input as HTMLInputElement).value).toBe("");

      // Store should be cleared
      const state = useSearchStore.getState();
      expect(state.query).toBe("");
      expect(state.results).toEqual([]);
    });
  });

  // -------------------------------------------------------------------------
  // Shows loading skeleton during search
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("shows loading skeleton during search", () => {
      useSearchStore.setState({
        ...defaultState,
        query: "test",
        isSearching: true,
      });

      const { container } = renderSearchPage();

      // Check for animate-pulse class (loading skeleton)
      const pulsingElements = container.querySelectorAll(".animate-pulse");
      expect(pulsingElements.length).toBeGreaterThan(0);
    });
  });

  // -------------------------------------------------------------------------
  // Shows empty state when no results
  // -------------------------------------------------------------------------

  describe("empty state", () => {
    it("shows empty state when no results after search", async () => {
      mockedApiClient.post.mockResolvedValue(
        makeSearchResponse({ results: [], total: 0, total_available: 0 })
      );

      renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: "nonexistent" } });
      });

      await act(async () => {
        fireEvent.keyDown(input, { key: "Enter" });
      });

      expect(screen.getByText(/No results found for/)).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Shows error alert with retry button
  // -------------------------------------------------------------------------

  describe("error state", () => {
    it("shows error alert with retry button", () => {
      useSearchStore.setState({
        ...defaultState,
        query: "test",
        error: "Search is temporarily unavailable. Please try again.",
      });

      renderSearchPage();

      expect(
        screen.getByText("Search is temporarily unavailable. Please try again.")
      ).toBeDefined();

      const retryButton = screen.getByRole("button", { name: "Retry" });
      expect(retryButton).toBeDefined();
    });

    it("retry button triggers search", async () => {
      useSearchStore.setState({
        ...defaultState,
        query: "test",
        error: "Search is temporarily unavailable. Please try again.",
      });

      renderSearchPage();

      const retryButton = screen.getByRole("button", { name: "Retry" });

      await act(async () => {
        fireEvent.click(retryButton);
      });

      expect(mockedApiClient.post).toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Shows inline validation error for 422
  // -------------------------------------------------------------------------

  describe("inline validation error", () => {
    it("shows inline validation error for 422", () => {
      useSearchStore.setState({
        ...defaultState,
        query: "test",
        error: "422: validation error - Query must be between 1 and 1000 characters",
      });

      renderSearchPage();

      // The 422 error should be displayed inline below the input
      expect(
        screen.getByText(
          "422: validation error - Query must be between 1 and 1000 characters"
        )
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Truncates long queries with notification
  // -------------------------------------------------------------------------

  describe("query truncation", () => {
    it("truncates long queries and shows notification", async () => {
      const longQuery = "a".repeat(1100);

      renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: longQuery } });
      });

      await act(async () => {
        fireEvent.keyDown(input, { key: "Enter" });
      });

      // Notification should appear
      expect(
        screen.getByText("Query truncated to 1000 characters")
      ).toBeDefined();

      // The API should have been called with truncated query
      const callArgs = mockedApiClient.post.mock.calls[0];
      const body = callArgs[1] as { query: string };
      expect(body.query).toHaveLength(1000);
    });
  });

  // -------------------------------------------------------------------------
  // aria-live region announces result count
  // -------------------------------------------------------------------------

  describe("aria-live region", () => {
    it("announces result count after search", async () => {
      mockedApiClient.post.mockResolvedValue(
        makeSearchResponse({ total_available: 5 })
      );

      const { container } = renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: "test" } });
      });

      await act(async () => {
        fireEvent.keyDown(input, { key: "Enter" });
      });

      const liveRegion = container.querySelector('[aria-live="polite"]');
      expect(liveRegion).not.toBeNull();
      expect(liveRegion!.textContent).toContain("results found");
    });

    it("announces no results when empty", async () => {
      mockedApiClient.post.mockResolvedValue(
        makeSearchResponse({ results: [], total: 0, total_available: 0 })
      );

      const { container } = renderSearchPage();

      const input = screen.getByPlaceholderText("Search documents...");

      await act(async () => {
        fireEvent.change(input, { target: { value: "nothing" } });
      });

      await act(async () => {
        fireEvent.keyDown(input, { key: "Enter" });
      });

      const liveRegion = container.querySelector('[aria-live="polite"]');
      expect(liveRegion).not.toBeNull();
      expect(liveRegion!.textContent).toContain("No results found");
    });
  });

  // -------------------------------------------------------------------------
  // aria-busy set during loading
  // -------------------------------------------------------------------------

  describe("aria-busy", () => {
    it("sets aria-busy during loading", () => {
      useSearchStore.setState({
        ...defaultState,
        query: "test",
        isSearching: true,
      });

      const { container } = renderSearchPage();

      const busyElement = container.querySelector('[aria-busy="true"]');
      expect(busyElement).not.toBeNull();
    });

    it("aria-busy is false when not loading", () => {
      useSearchStore.setState({
        ...defaultState,
        query: "test",
        isSearching: false,
      });

      const { container } = renderSearchPage();

      const busyElement = container.querySelector('[aria-busy="true"]');
      expect(busyElement).toBeNull();
    });
  });
});
