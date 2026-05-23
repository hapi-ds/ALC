import { describe, it, expect, beforeEach, vi } from "vitest";
import { useSearchStore } from "@/stores/searchStore";
import type { SearchState } from "@/stores/searchStore";

/**
 * Unit tests for searchStore actions.
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
 */

// Mock apiClient module
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
        tags: ["GxP", "Quality"],
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-02-01T00:00:00Z",
      },
    ],
    total: 1,
    total_available: 42,
    query: "test query",
    offset: 0,
    filters_applied: {},
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default state for reset between tests
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("searchStore", () => {
  beforeEach(() => {
    useSearchStore.setState(defaultState);
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Initial state
  // -------------------------------------------------------------------------

  describe("initial state", () => {
    it("has correct defaults", () => {
      useSearchStore.setState(defaultState);
      const state = useSearchStore.getState();

      expect(state.query).toBe("");
      expect(state.results).toEqual([]);
      expect(state.isSearching).toBe(false);
      expect(state.error).toBeNull();
      expect(state.filters).toEqual({ document_type: [], status: [], tags: [] });
      expect(state.offset).toBe(0);
      expect(state.limit).toBe(20);
      expect(state.totalAvailable).toBe(0);
      expect(state.sortBy).toBe("relevance");
    });
  });

  // -------------------------------------------------------------------------
  // search()
  // -------------------------------------------------------------------------

  describe("search()", () => {
    it("sends POST with correct body and changeReason option", async () => {
      useSearchStore.setState({ query: "test query", offset: 10, sortBy: "date" });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      await useSearchStore.getState().search();

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/search",
        {
          query: "test query",
          user_id: 1,
          limit: 20,
          filters: { document_type: [], status: [], tags: [] },
          offset: 10,
          sort_by: "date",
        },
        { changeReason: "Document search query" },
      );
    });

    it("sets isSearching to true during request", async () => {
      useSearchStore.setState({ query: "test" });

      mockedApiClient.post.mockImplementation(() => new Promise(() => {}));

      // Fire and don't await — we want to check intermediate state
      useSearchStore.getState().search();

      await vi.waitFor(() => {
        expect(useSearchStore.getState().isSearching).toBe(true);
      });
    });

    it("stores results on success", async () => {
      useSearchStore.setState({ query: "test" });
      const response = makeSearchResponse({ total_available: 50 });
      mockedApiClient.post.mockResolvedValue(response);

      await useSearchStore.getState().search();

      const state = useSearchStore.getState();
      expect(state.results).toEqual(response.results);
      expect(state.totalAvailable).toBe(50);
      expect(state.isSearching).toBe(false);
      expect(state.error).toBeNull();
    });

    it("handles error response (sets error, clears results)", async () => {
      useSearchStore.setState({
        query: "test",
        results: makeSearchResponse().results,
        totalAvailable: 10,
      });

      mockedApiClient.post.mockRejectedValue(new Error("Network failure"));

      await useSearchStore.getState().search();

      const state = useSearchStore.getState();
      expect(state.error).toBe("Network failure");
      expect(state.results).toEqual([]);
      expect(state.totalAvailable).toBe(0);
      expect(state.isSearching).toBe(false);
    });

    it("skips when isSearching is true (deduplication)", async () => {
      useSearchStore.setState({ query: "test", isSearching: true });

      await useSearchStore.getState().search();

      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });

    it("rejects whitespace-only queries", async () => {
      useSearchStore.setState({ query: "   \t\n  " });

      await useSearchStore.getState().search();

      expect(mockedApiClient.post).not.toHaveBeenCalled();
      const state = useSearchStore.getState();
      // clearResults should have been called, resetting state
      expect(state.query).toBe("");
      expect(state.results).toEqual([]);
      expect(state.totalAvailable).toBe(0);
    });

    it("truncates query > 1000 chars", async () => {
      const longQuery = "a".repeat(1500);
      useSearchStore.setState({ query: longQuery });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      await useSearchStore.getState().search();

      const callArgs = mockedApiClient.post.mock.calls[0];
      const body = callArgs[1] as { query: string };
      expect(body.query).toHaveLength(1000);
      expect(body.query).toBe("a".repeat(1000));
    });

    it("sets error with fallback message for non-Error exceptions", async () => {
      useSearchStore.setState({ query: "test" });
      mockedApiClient.post.mockRejectedValue("string error");

      await useSearchStore.getState().search();

      const state = useSearchStore.getState();
      expect(state.error).toBe("Search is temporarily unavailable. Please try again.");
      expect(state.results).toEqual([]);
      expect(state.isSearching).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // setFilter()
  // -------------------------------------------------------------------------

  describe("setFilter()", () => {
    it("adds a value to the filter category when not present", async () => {
      useSearchStore.setState({ query: "test" });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().setFilter("document_type", "SOP");

      await vi.waitFor(() => {
        expect(useSearchStore.getState().filters.document_type).toContain("SOP");
      });
    });

    it("removes a value from the filter category when already present", async () => {
      useSearchStore.setState({
        query: "test",
        filters: { document_type: ["SOP", "Policy"], status: [], tags: [] },
      });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().setFilter("document_type", "SOP");

      await vi.waitFor(() => {
        expect(useSearchStore.getState().filters.document_type).toEqual(["Policy"]);
      });
    });

    it("resets offset to 0 and triggers search", async () => {
      useSearchStore.setState({ query: "test", offset: 40 });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().setFilter("status", "Active");

      await vi.waitFor(() => {
        expect(useSearchStore.getState().offset).toBe(0);
        expect(mockedApiClient.post).toHaveBeenCalled();
      });
    });
  });

  // -------------------------------------------------------------------------
  // setSortBy()
  // -------------------------------------------------------------------------

  describe("setSortBy()", () => {
    it("updates sort and triggers search", async () => {
      useSearchStore.setState({ query: "test", sortBy: "relevance", offset: 20 });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().setSortBy("date");

      await vi.waitFor(() => {
        const state = useSearchStore.getState();
        expect(state.sortBy).toBe("date");
        expect(state.offset).toBe(0);
        expect(mockedApiClient.post).toHaveBeenCalled();
      });
    });
  });

  // -------------------------------------------------------------------------
  // setQuery()
  // -------------------------------------------------------------------------

  describe("setQuery()", () => {
    it("updates query without triggering search", () => {
      useSearchStore.getState().setQuery("new query");

      expect(useSearchStore.getState().query).toBe("new query");
      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // nextPage() / previousPage()
  // -------------------------------------------------------------------------

  describe("nextPage()", () => {
    it("increments offset by limit when more results available", async () => {
      useSearchStore.setState({ query: "test", offset: 0, limit: 20, totalAvailable: 50 });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().nextPage();

      await vi.waitFor(() => {
        expect(useSearchStore.getState().offset).toBe(20);
        expect(mockedApiClient.post).toHaveBeenCalled();
      });
    });

    it("does not increment offset when at last page", () => {
      useSearchStore.setState({ query: "test", offset: 40, limit: 20, totalAvailable: 50 });

      useSearchStore.getState().nextPage();

      expect(useSearchStore.getState().offset).toBe(40);
      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });

    it("does not increment offset when exactly at boundary", () => {
      useSearchStore.setState({ query: "test", offset: 40, limit: 20, totalAvailable: 60 });

      useSearchStore.getState().nextPage();

      // offset + limit = 60 which is NOT < totalAvailable (60), so no change
      expect(useSearchStore.getState().offset).toBe(40);
      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });
  });

  describe("previousPage()", () => {
    it("decrements offset by limit", async () => {
      useSearchStore.setState({ query: "test", offset: 40, limit: 20, totalAvailable: 100 });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().previousPage();

      await vi.waitFor(() => {
        expect(useSearchStore.getState().offset).toBe(20);
        expect(mockedApiClient.post).toHaveBeenCalled();
      });
    });

    it("does not go below 0", async () => {
      useSearchStore.setState({ query: "test", offset: 10, limit: 20, totalAvailable: 100 });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().previousPage();

      await vi.waitFor(() => {
        expect(useSearchStore.getState().offset).toBe(0);
      });
    });

    it("stays at 0 when already at first page", async () => {
      useSearchStore.setState({ query: "test", offset: 0, limit: 20, totalAvailable: 100 });
      mockedApiClient.post.mockResolvedValue(makeSearchResponse());

      useSearchStore.getState().previousPage();

      await vi.waitFor(() => {
        expect(useSearchStore.getState().offset).toBe(0);
      });
    });
  });

  // -------------------------------------------------------------------------
  // clearResults()
  // -------------------------------------------------------------------------

  describe("clearResults()", () => {
    it("resets all state to defaults", () => {
      useSearchStore.setState({
        query: "some query",
        results: makeSearchResponse().results,
        isSearching: false,
        error: "some error",
        filters: { document_type: ["SOP"], status: ["Active"], tags: ["GxP"] },
        offset: 40,
        totalAvailable: 100,
        sortBy: "date",
      });

      useSearchStore.getState().clearResults();

      const state = useSearchStore.getState();
      expect(state.query).toBe("");
      expect(state.results).toEqual([]);
      expect(state.isSearching).toBe(false);
      expect(state.error).toBeNull();
      expect(state.filters).toEqual({ document_type: [], status: [], tags: [] });
      expect(state.offset).toBe(0);
      expect(state.totalAvailable).toBe(0);
      expect(state.sortBy).toBe("relevance");
    });
  });
});
