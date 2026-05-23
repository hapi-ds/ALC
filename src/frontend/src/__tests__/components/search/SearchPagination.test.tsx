import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { SearchPagination } from "@/components/search/SearchPagination";

/**
 * Unit tests for SearchPagination component.
 *
 * Validates: Requirements 7.1, 7.4, 7.5, 7.6, 8.4
 */

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function renderPagination(
  props: Partial<Parameters<typeof SearchPagination>[0]> = {}
) {
  const defaultProps = {
    offset: 0,
    limit: 20,
    totalAvailable: 100,
    onNext: vi.fn(),
    onPrevious: vi.fn(),
    ...props,
  };

  return { ...render(<SearchPagination {...defaultProps} />), props: defaultProps };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SearchPagination", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Hidden when totalAvailable ≤ limit
  // -------------------------------------------------------------------------

  describe("hidden when totalAvailable ≤ limit", () => {
    it("returns null when totalAvailable equals limit", () => {
      const { container } = renderPagination({
        totalAvailable: 20,
        limit: 20,
      });

      expect(container.innerHTML).toBe("");
    });

    it("returns null when totalAvailable is less than limit", () => {
      const { container } = renderPagination({
        totalAvailable: 5,
        limit: 20,
      });

      expect(container.innerHTML).toBe("");
    });

    it("returns null when totalAvailable is 0", () => {
      const { container } = renderPagination({
        totalAvailable: 0,
        limit: 20,
      });

      expect(container.innerHTML).toBe("");
    });

    it("renders when totalAvailable exceeds limit", () => {
      const { container } = renderPagination({
        totalAvailable: 21,
        limit: 20,
      });

      expect(container.innerHTML).not.toBe("");
    });
  });

  // -------------------------------------------------------------------------
  // Disables Previous at offset=0
  // -------------------------------------------------------------------------

  describe("disables Previous at offset=0", () => {
    it("disables Previous button when offset is 0", () => {
      renderPagination({ offset: 0 });

      const prevButton = screen.getByRole("button", { name: "Go to previous page" });
      expect(prevButton).toHaveProperty("disabled", true);
    });

    it("enables Previous button when offset is greater than 0", () => {
      renderPagination({ offset: 20 });

      const prevButton = screen.getByRole("button", { name: "Go to previous page" });
      expect(prevButton).toHaveProperty("disabled", false);
    });

    it("calls onPrevious when Previous button is clicked and enabled", () => {
      const { props } = renderPagination({ offset: 20 });

      const prevButton = screen.getByRole("button", { name: "Go to previous page" });
      fireEvent.click(prevButton);

      expect(props.onPrevious).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // Disables Next at last page
  // -------------------------------------------------------------------------

  describe("disables Next at last page", () => {
    it("disables Next button when offset + limit >= totalAvailable", () => {
      renderPagination({ offset: 80, limit: 20, totalAvailable: 100 });

      const nextButton = screen.getByRole("button", { name: "Go to next page" });
      expect(nextButton).toHaveProperty("disabled", true);
    });

    it("disables Next button when offset + limit exceeds totalAvailable", () => {
      renderPagination({ offset: 90, limit: 20, totalAvailable: 100 });

      const nextButton = screen.getByRole("button", { name: "Go to next page" });
      expect(nextButton).toHaveProperty("disabled", true);
    });

    it("enables Next button when more pages are available", () => {
      renderPagination({ offset: 0, limit: 20, totalAvailable: 100 });

      const nextButton = screen.getByRole("button", { name: "Go to next page" });
      expect(nextButton).toHaveProperty("disabled", false);
    });

    it("calls onNext when Next button is clicked and enabled", () => {
      const { props } = renderPagination({ offset: 0, limit: 20, totalAvailable: 100 });

      const nextButton = screen.getByRole("button", { name: "Go to next page" });
      fireEvent.click(nextButton);

      expect(props.onNext).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // Shows correct page indicator
  // -------------------------------------------------------------------------

  describe("shows correct page indicator", () => {
    it("shows 'Page 1 of 5' when on first page with 100 results and limit 20", () => {
      renderPagination({ offset: 0, limit: 20, totalAvailable: 100 });

      expect(screen.getByText("Page 1 of 5")).toBeDefined();
    });

    it("shows 'Page 2 of 5' when offset is 20", () => {
      renderPagination({ offset: 20, limit: 20, totalAvailable: 100 });

      expect(screen.getByText("Page 2 of 5")).toBeDefined();
    });

    it("shows 'Page 5 of 5' when on last page", () => {
      renderPagination({ offset: 80, limit: 20, totalAvailable: 100 });

      expect(screen.getByText("Page 5 of 5")).toBeDefined();
    });

    it("handles non-even total (e.g., 45 results with limit 20 = 3 pages)", () => {
      renderPagination({ offset: 0, limit: 20, totalAvailable: 45 });

      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });

    it("shows 'Page 1 of 2' for minimal multi-page case", () => {
      renderPagination({ offset: 0, limit: 20, totalAvailable: 21 });

      expect(screen.getByText("Page 1 of 2")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Buttons have correct aria-labels
  // -------------------------------------------------------------------------

  describe("buttons have correct aria-labels", () => {
    it("Previous button has aria-label 'Go to previous page'", () => {
      renderPagination();

      const prevButton = screen.getByRole("button", { name: "Go to previous page" });
      expect(prevButton).toBeDefined();
      expect(prevButton.getAttribute("aria-label")).toBe("Go to previous page");
    });

    it("Next button has aria-label 'Go to next page'", () => {
      renderPagination();

      const nextButton = screen.getByRole("button", { name: "Go to next page" });
      expect(nextButton).toBeDefined();
      expect(nextButton.getAttribute("aria-label")).toBe("Go to next page");
    });

    it("pagination container has role='navigation' with aria-label", () => {
      renderPagination();

      const nav = screen.getByRole("navigation");
      expect(nav).toBeDefined();
      expect(nav.getAttribute("aria-label")).toBe("Search results pagination");
    });
  });
});
