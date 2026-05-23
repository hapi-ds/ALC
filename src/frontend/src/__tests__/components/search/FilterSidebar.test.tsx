import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { FilterSidebar } from "@/components/search/FilterSidebar";
import type { SearchResult, SearchFilters } from "@/stores/searchStore";

/**
 * Unit tests for FilterSidebar component.
 *
 * Validates: Requirements 6.1, 6.2, 6.4, 6.6, 6.7
 */

// ---------------------------------------------------------------------------
// Test Fixtures
// ---------------------------------------------------------------------------

function createMockResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    document_uuid: "doc-001",
    title: "Test Document",
    version: "v1.0",
    excerpt: "Test excerpt",
    relevance_score: 0.9,
    document_type: "SOP",
    status: "Active",
    tags: ["GxP", "Safety"],
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-06-01T00:00:00Z",
    ...overrides,
  };
}

const emptyFilters: SearchFilters = {
  document_type: [],
  status: [],
  tags: [],
};

function renderSidebar(props: Partial<Parameters<typeof FilterSidebar>[0]> = {}) {
  const defaultProps = {
    results: [
      createMockResult({ document_type: "SOP", status: "Active", tags: ["GxP", "Safety"] }),
      createMockResult({ document_type: "Policy", status: "Draft", tags: ["Compliance"] }),
      createMockResult({ document_type: "SOP", status: "Draft", tags: ["GxP"] }),
    ],
    activeFilters: emptyFilters,
    onFilterToggle: vi.fn(),
    onClearAll: vi.fn(),
    disabled: false,
    ...props,
  };

  return { ...render(<FilterSidebar {...defaultProps} />), props: defaultProps };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("FilterSidebar", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Renders three collapsible sections
  // -------------------------------------------------------------------------

  describe("collapsible sections", () => {
    it("renders three collapsible sections: Document Type, Status, Tags", () => {
      renderSidebar();

      const buttons = screen.getAllByRole("button", { expanded: true });
      const sectionNames = buttons.map((btn) => btn.textContent);

      expect(sectionNames.some((name) => name?.includes("Document Type"))).toBe(true);
      expect(sectionNames.some((name) => name?.includes("Status"))).toBe(true);
      expect(sectionNames.some((name) => name?.includes("Tags"))).toBe(true);
    });

    it("collapses a section when its header is clicked", () => {
      renderSidebar();

      const docTypeButton = screen.getByRole("button", { name: /Document Type/i });
      expect(docTypeButton.getAttribute("aria-expanded")).toBe("true");

      fireEvent.click(docTypeButton);

      expect(docTypeButton.getAttribute("aria-expanded")).toBe("false");
    });
  });

  // -------------------------------------------------------------------------
  // Derives options from result metadata
  // -------------------------------------------------------------------------

  describe("derives options from result metadata", () => {
    it("shows distinct document_type values as checkboxes", () => {
      renderSidebar();

      // SOP and Policy are the distinct document types
      expect(screen.getByLabelText("Filter by Document Type: SOP")).toBeDefined();
      expect(screen.getByLabelText("Filter by Document Type: Policy")).toBeDefined();
    });

    it("shows distinct status values as checkboxes", () => {
      renderSidebar();

      expect(screen.getByLabelText("Filter by Status: Active")).toBeDefined();
      expect(screen.getByLabelText("Filter by Status: Draft")).toBeDefined();
    });

    it("shows distinct tag values as checkboxes", () => {
      renderSidebar();

      expect(screen.getByLabelText("Filter by Tags: Compliance")).toBeDefined();
      expect(screen.getByLabelText("Filter by Tags: GxP")).toBeDefined();
      expect(screen.getByLabelText("Filter by Tags: Safety")).toBeDefined();
    });

    it("does not show duplicate options for repeated metadata values", () => {
      renderSidebar();

      // SOP appears in 2 results but should only show once as an option
      const sopCheckboxes = screen.getAllByLabelText("Filter by Document Type: SOP");
      expect(sopCheckboxes.length).toBe(1);
    });
  });

  // -------------------------------------------------------------------------
  // Shows count badges for active selections
  // -------------------------------------------------------------------------

  describe("count badges for active selections", () => {
    it("shows count badge on section header when filters are active", () => {
      renderSidebar({
        activeFilters: {
          document_type: ["SOP", "Policy"],
          status: [],
          tags: ["GxP"],
        },
      });

      // Document Type section should show badge with "2"
      const docTypeButton = screen.getByRole("button", { name: /Document Type/i });
      expect(docTypeButton.textContent).toContain("2");

      // Tags section should show badge with "1"
      const tagsButton = screen.getByRole("button", { name: /Tags/i });
      expect(tagsButton.textContent).toContain("1");
    });

    it("does not show count badge when no filters are active in a section", () => {
      renderSidebar({
        activeFilters: emptyFilters,
      });

      const statusButton = screen.getByRole("button", { name: /Status/i });
      // Should not contain any number badge
      expect(statusButton.textContent).not.toMatch(/\d/);
    });
  });

  // -------------------------------------------------------------------------
  // Disabled state shows message
  // -------------------------------------------------------------------------

  describe("disabled state", () => {
    it("shows disabled message when disabled is true", () => {
      renderSidebar({ disabled: true });

      expect(
        screen.getByText("Perform a search to see available filters")
      ).toBeDefined();
    });

    it("does not render checkboxes when disabled", () => {
      renderSidebar({ disabled: true });

      expect(screen.queryAllByRole("checkbox").length).toBe(0);
    });

    it("does not render collapsible section buttons when disabled", () => {
      renderSidebar({ disabled: true });

      expect(screen.queryByRole("button", { name: /Document Type/i })).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Checkbox toggles call onFilterToggle
  // -------------------------------------------------------------------------

  describe("checkbox toggles", () => {
    it("calls onFilterToggle with correct category and value when checkbox is clicked", () => {
      const { props } = renderSidebar();

      const sopCheckbox = screen.getByLabelText("Filter by Document Type: SOP");
      fireEvent.click(sopCheckbox);

      expect(props.onFilterToggle).toHaveBeenCalledWith("document_type", "SOP");
    });

    it("calls onFilterToggle for status category", () => {
      const { props } = renderSidebar();

      const activeCheckbox = screen.getByLabelText("Filter by Status: Active");
      fireEvent.click(activeCheckbox);

      expect(props.onFilterToggle).toHaveBeenCalledWith("status", "Active");
    });

    it("calls onFilterToggle for tags category", () => {
      const { props } = renderSidebar();

      const gxpCheckbox = screen.getByLabelText("Filter by Tags: GxP");
      fireEvent.click(gxpCheckbox);

      expect(props.onFilterToggle).toHaveBeenCalledWith("tags", "GxP");
    });

    it("shows checkbox as checked when value is in activeFilters", () => {
      renderSidebar({
        activeFilters: {
          document_type: ["SOP"],
          status: [],
          tags: [],
        },
      });

      const sopCheckbox = screen.getByLabelText(
        "Filter by Document Type: SOP"
      ) as HTMLInputElement;
      expect(sopCheckbox.checked).toBe(true);

      const policyCheckbox = screen.getByLabelText(
        "Filter by Document Type: Policy"
      ) as HTMLInputElement;
      expect(policyCheckbox.checked).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // "Clear all filters" button calls onClearAll
  // -------------------------------------------------------------------------

  describe("clear all filters button", () => {
    it("shows 'Clear all filters' button when any filter is active", () => {
      renderSidebar({
        activeFilters: {
          document_type: ["SOP"],
          status: [],
          tags: [],
        },
      });

      expect(screen.getByRole("button", { name: /Clear all filters/i })).toBeDefined();
    });

    it("does not show 'Clear all filters' button when no filters are active", () => {
      renderSidebar({
        activeFilters: emptyFilters,
      });

      expect(screen.queryByRole("button", { name: /Clear all filters/i })).toBeNull();
    });

    it("calls onClearAll when 'Clear all filters' button is clicked", () => {
      const { props } = renderSidebar({
        activeFilters: {
          document_type: ["SOP"],
          status: ["Active"],
          tags: ["GxP"],
        },
      });

      const clearButton = screen.getByRole("button", { name: /Clear all filters/i });
      fireEvent.click(clearButton);

      expect(props.onClearAll).toHaveBeenCalledTimes(1);
    });
  });
});
