import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchResultCard } from "@/components/search/SearchResultCard";
import type { SearchResult } from "@/stores/searchStore";

/**
 * Unit tests for SearchResultCard component.
 *
 * Validates: Requirements 5.1, 5.2, 8.6, 9.5
 */

// ---------------------------------------------------------------------------
// Test Fixtures
// ---------------------------------------------------------------------------

function createMockResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    document_uuid: "abc-123-def-456",
    title: "Standard Operating Procedure",
    version: "v2.1",
    excerpt: "This document describes the procedure for handling chemicals safely.",
    relevance_score: 0.82,
    document_type: "SOP",
    status: "Active",
    tags: ["GxP", "Safety"],
    created_at: "2024-01-10T08:00:00Z",
    updated_at: "2024-06-15T14:30:00Z",
    ...overrides,
  };
}

function renderCard(result: SearchResult, query = "procedure") {
  return render(
    <MemoryRouter>
      <SearchResultCard result={result} query={query} />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SearchResultCard", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Title as link
  // -------------------------------------------------------------------------

  describe("title link", () => {
    it("renders title as a link to /documents/{uuid}", () => {
      const result = createMockResult();
      renderCard(result);

      const link = screen.getByRole("link", { name: "Standard Operating Procedure" });
      expect(link).toBeDefined();
      expect(link.getAttribute("href")).toBe("/documents/abc-123-def-456");
    });

    it("navigates to correct document page on click", () => {
      const result = createMockResult({ document_uuid: "xyz-789" });
      renderCard(result);

      const link = screen.getByRole("link", { name: "Standard Operating Procedure" });
      expect(link.getAttribute("href")).toBe("/documents/xyz-789");
    });
  });

  // -------------------------------------------------------------------------
  // Version badge
  // -------------------------------------------------------------------------

  describe("version badge", () => {
    it("renders the version badge", () => {
      const result = createMockResult({ version: "v3.0" });
      renderCard(result);

      expect(screen.getByText("v3.0")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Relevance bar with ARIA attributes
  // -------------------------------------------------------------------------

  describe("relevance bar", () => {
    it("renders relevance bar with correct ARIA attributes", () => {
      const result = createMockResult({ relevance_score: 0.82 });
      renderCard(result);

      const meter = screen.getByRole("meter");
      expect(meter).toBeDefined();
      expect(meter.getAttribute("aria-valuenow")).toBe("82");
      expect(meter.getAttribute("aria-valuemin")).toBe("0");
      expect(meter.getAttribute("aria-valuemax")).toBe("100");
      expect(meter.getAttribute("aria-label")).toBe("Relevance score: 82%");
    });

    it("clamps relevance score above 1 to 100%", () => {
      const result = createMockResult({ relevance_score: 1.5 });
      renderCard(result);

      const meter = screen.getByRole("meter");
      expect(meter.getAttribute("aria-valuenow")).toBe("100");
      expect(meter.getAttribute("aria-label")).toBe("Relevance score: 100%");
    });

    it("clamps relevance score below 0 to 0%", () => {
      const result = createMockResult({ relevance_score: -0.3 });
      renderCard(result);

      const meter = screen.getByRole("meter");
      expect(meter.getAttribute("aria-valuenow")).toBe("0");
      expect(meter.getAttribute("aria-label")).toBe("Relevance score: 0%");
    });

    it("handles relevance score of exactly 0", () => {
      const result = createMockResult({ relevance_score: 0 });
      renderCard(result);

      const meter = screen.getByRole("meter");
      expect(meter.getAttribute("aria-valuenow")).toBe("0");
    });

    it("handles relevance score of exactly 1", () => {
      const result = createMockResult({ relevance_score: 1 });
      renderCard(result);

      const meter = screen.getByRole("meter");
      expect(meter.getAttribute("aria-valuenow")).toBe("100");
    });
  });

  // -------------------------------------------------------------------------
  // Excerpt highlighting
  // -------------------------------------------------------------------------

  describe("excerpt highlighting", () => {
    it("highlights query terms in excerpt with <mark> elements", () => {
      const result = createMockResult({
        excerpt: "This procedure is the standard procedure for safety.",
      });
      renderCard(result, "procedure");

      const marks = screen.getAllByText("procedure");
      // The query "procedure" appears twice in the excerpt
      const markElements = marks.filter((el) => el.tagName === "MARK");
      expect(markElements.length).toBe(2);
    });

    it("performs case-insensitive highlighting", () => {
      const result = createMockResult({
        excerpt: "The SOP document describes SOP procedures.",
      });
      renderCard(result, "sop");

      const marks = screen.getAllByText(/^SOP$/i);
      const markElements = marks.filter((el) => el.tagName === "MARK");
      expect(markElements.length).toBe(2);
    });

    it("renders excerpt without marks when query is empty", () => {
      const result = createMockResult({
        excerpt: "Some text without highlights.",
      });
      renderCard(result, "");

      expect(screen.getByText("Some text without highlights.")).toBeDefined();
      // No <mark> elements should exist
      const container = screen.getByText("Some text without highlights.");
      expect(container.querySelector("mark")).toBeNull();
    });

    it("renders excerpt without marks when query has no match", () => {
      const result = createMockResult({
        excerpt: "This is a document about safety.",
      });
      renderCard(result, "nonexistent");

      expect(screen.getByText("This is a document about safety.")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Metadata badges
  // -------------------------------------------------------------------------

  describe("metadata badges", () => {
    it("renders document_type badge", () => {
      const result = createMockResult({ document_type: "SOP" });
      renderCard(result);

      expect(screen.getByText("SOP")).toBeDefined();
    });

    it("renders status badge", () => {
      const result = createMockResult({ status: "Active" });
      renderCard(result);

      expect(screen.getByText("Active")).toBeDefined();
    });

    it("does not render document_type badge when null", () => {
      const result = createMockResult({ document_type: null });
      renderCard(result);

      // Should not find a badge for document_type
      expect(screen.queryByText("SOP")).toBeNull();
    });

    it("does not render status badge when null", () => {
      const result = createMockResult({ status: null });
      renderCard(result);

      expect(screen.queryByText("Active")).toBeNull();
    });

    it("renders both document_type and status badges together", () => {
      const result = createMockResult({ document_type: "Policy", status: "Draft" });
      renderCard(result);

      expect(screen.getByText("Policy")).toBeDefined();
      expect(screen.getByText("Draft")).toBeDefined();
    });
  });
});
