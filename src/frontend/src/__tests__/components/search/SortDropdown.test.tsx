import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { SortDropdown } from "@/components/search/SortDropdown";

/**
 * Unit tests for SortDropdown component.
 *
 * Validates: Requirements 10.1, 10.3
 */

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function renderSortDropdown(
  props: Partial<Parameters<typeof SortDropdown>[0]> = {}
) {
  const defaultProps = {
    value: "relevance" as const,
    onChange: vi.fn(),
    ...props,
  };

  return { ...render(<SortDropdown {...defaultProps} />), props: defaultProps };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SortDropdown", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Renders both options
  // -------------------------------------------------------------------------

  describe("renders both options", () => {
    it("renders a select element with combobox role", () => {
      renderSortDropdown();

      const select = screen.getByRole("combobox");
      expect(select).toBeDefined();
    });

    it("renders 'Most Relevant' option with value 'relevance'", () => {
      renderSortDropdown();

      const option = screen.getByRole("option", { name: "Most Relevant" });
      expect(option).toBeDefined();
      expect(option.getAttribute("value")).toBe("relevance");
    });

    it("renders 'Most Recent' option with value 'date'", () => {
      renderSortDropdown();

      const option = screen.getByRole("option", { name: "Most Recent" });
      expect(option).toBeDefined();
      expect(option.getAttribute("value")).toBe("date");
    });

    it("renders exactly two options", () => {
      renderSortDropdown();

      const options = screen.getAllByRole("option");
      expect(options).toHaveLength(2);
    });
  });

  // -------------------------------------------------------------------------
  // Visually indicates active option
  // -------------------------------------------------------------------------

  describe("visually indicates active option", () => {
    it("shows 'relevance' as selected when value is 'relevance'", () => {
      renderSortDropdown({ value: "relevance" });

      const select = screen.getByRole("combobox") as HTMLSelectElement;
      expect(select.value).toBe("relevance");
    });

    it("shows 'date' as selected when value is 'date'", () => {
      renderSortDropdown({ value: "date" });

      const select = screen.getByRole("combobox") as HTMLSelectElement;
      expect(select.value).toBe("date");
    });

    it("the selected option reflects the value prop", () => {
      const { rerender } = render(
        <SortDropdown value="relevance" onChange={vi.fn()} />
      );

      const select = screen.getByRole("combobox") as HTMLSelectElement;
      expect(select.value).toBe("relevance");

      rerender(<SortDropdown value="date" onChange={vi.fn()} />);
      expect(select.value).toBe("date");
    });
  });

  // -------------------------------------------------------------------------
  // Calls onChange on selection
  // -------------------------------------------------------------------------

  describe("calls onChange on selection", () => {
    it("calls onChange with 'date' when user selects 'Most Recent'", () => {
      const { props } = renderSortDropdown({ value: "relevance" });

      const select = screen.getByRole("combobox");
      fireEvent.change(select, { target: { value: "date" } });

      expect(props.onChange).toHaveBeenCalledTimes(1);
      expect(props.onChange).toHaveBeenCalledWith("date");
    });

    it("calls onChange with 'relevance' when user selects 'Most Relevant'", () => {
      const { props } = renderSortDropdown({ value: "date" });

      const select = screen.getByRole("combobox");
      fireEvent.change(select, { target: { value: "relevance" } });

      expect(props.onChange).toHaveBeenCalledTimes(1);
      expect(props.onChange).toHaveBeenCalledWith("relevance");
    });
  });
});
