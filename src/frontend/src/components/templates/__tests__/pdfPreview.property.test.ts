import { describe, it, expect, afterEach } from "vitest";
import * as fc from "fast-check";
import { render, cleanup } from "@testing-library/react";
import React from "react";
import { useTemplateBuilderStore } from "../../../stores/templateBuilderStore";
import { PdfPreviewPanel } from "../PdfPreviewPanel";
import type {
  CanvasItem,
  CanvasFieldElement,
  CanvasContentBlockElement,
  FieldType,
  ContentBlockType,
  TextFieldConfig,
  FloatFieldConfig,
  IntegerFieldConfig,
  DateFieldConfig,
  BooleanFieldConfig,
  FieldConfig,
} from "../../../types/template";

/**
 * Feature: template-builder-enhancements, Property 9: Preview Completeness
 *
 * Validates: Requirements 14.2, 14.4, 14.5, 14.6, 15.1–15.6
 *
 * For any valid canvas state, the PDF preview rendering function SHALL produce
 * output containing: (a) every field's label text, (b) an asterisk or "Required"
 * indicator for every field with required=true, (c) the help_text for every field
 * that has it configured, (d) the unit_label for every numeric field that has it
 * configured, (e) the text content of every heading and paragraph content block,
 * and (f) a divider element for every divider content block.
 */

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

const fieldTypeArb: fc.Arbitrary<FieldType> = fc.constantFrom(
  "Text",
  "Float",
  "Integer",
  "Date",
  "Boolean"
);

const contentBlockTypeArb: fc.Arbitrary<ContentBlockType> = fc.constantFrom(
  "heading_h1",
  "heading_h2",
  "heading_h3",
  "paragraph",
  "divider"
);

const textFieldConfigArb: fc.Arbitrary<TextFieldConfig> = fc.record(
  {
    min_length: fc.option(fc.integer({ min: 0, max: 500 }), { nil: undefined }),
    max_length: fc.option(fc.integer({ min: 1, max: 2000 }), { nil: undefined }),
    placeholder: fc.option(
      fc.string({ minLength: 1, maxLength: 50 }),
      { nil: undefined }
    ),
    regex_pattern: fc.option(
      fc.constantFrom("^[a-z]+$", "\\d{3}", "[A-Z]{2,5}"),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

const floatFieldConfigArb: fc.Arbitrary<FloatFieldConfig> = fc.record(
  {
    decimal_precision: fc.option(fc.integer({ min: 0, max: 10 }), { nil: undefined }),
    min_value: fc.option(fc.double({ min: -1000, max: 1000, noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
    max_value: fc.option(fc.double({ min: -1000, max: 1000, noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
    unit_label: fc.option(
      fc.stringMatching(/^[a-zA-Z/%°]+$/u, { minLength: 1, maxLength: 20 }),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

const integerFieldConfigArb: fc.Arbitrary<IntegerFieldConfig> = fc.record(
  {
    min_value: fc.option(fc.integer({ min: -10000, max: 10000 }), { nil: undefined }),
    max_value: fc.option(fc.integer({ min: -10000, max: 10000 }), { nil: undefined }),
    step_size: fc.option(fc.integer({ min: 1, max: 100 }), { nil: undefined }),
    unit_label: fc.option(
      fc.stringMatching(/^[a-zA-Z/%°]+$/u, { minLength: 1, maxLength: 20 }),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

const dateFieldConfigArb: fc.Arbitrary<DateFieldConfig> = fc.record(
  {
    min_date: fc.option(
      fc.constantFrom("2020-01-01", "2023-06-15", "2024-12-31"),
      { nil: undefined }
    ),
    max_date: fc.option(
      fc.constantFrom("2025-01-01", "2030-12-31", "2028-06-30"),
      { nil: undefined }
    ),
    date_format: fc.option(
      fc.constantFrom(
        "YYYY-MM-DD" as const,
        "DD/MM/YYYY" as const,
        "MM/DD/YYYY" as const,
        "DD-MMM-YYYY" as const
      ),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

const booleanFieldConfigArb: fc.Arbitrary<BooleanFieldConfig> = fc.record(
  {
    true_label: fc.option(
      fc.stringMatching(/^[a-zA-Z ]+$/u, { minLength: 1, maxLength: 20 }),
      { nil: undefined }
    ),
    false_label: fc.option(
      fc.stringMatching(/^[a-zA-Z ]+$/u, { minLength: 1, maxLength: 20 }),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

function fieldConfigForType(type: FieldType): fc.Arbitrary<FieldConfig> {
  switch (type) {
    case "Text":
      return textFieldConfigArb;
    case "Float":
      return floatFieldConfigArb;
    case "Integer":
      return integerFieldConfigArb;
    case "Date":
      return dateFieldConfigArb;
    case "Boolean":
      return booleanFieldConfigArb;
  }
}

/**
 * Generate a label that is safe for text matching in the DOM.
 * Uses alphanumeric characters to avoid regex/HTML issues.
 */
const safeLabelArb = fc.stringMatching(/^[A-Z][a-zA-Z0-9 ]{0,29}$/u, {
  minLength: 1,
  maxLength: 30,
});

/**
 * Generate help text that is safe for text matching.
 */
const safeHelpTextArb = fc.stringMatching(/^[a-zA-Z0-9 ]{5,40}$/u, {
  minLength: 5,
  maxLength: 40,
});

const canvasFieldElementArb: fc.Arbitrary<CanvasFieldElement> = fieldTypeArb.chain(
  (type) =>
    fc.record({
      id: fc.uuid(),
      element_type: fc.constant("field" as const),
      label: safeLabelArb,
      type: fc.constant(type),
      fieldOrder: fc.constant(0), // Will be recalculated
      required: fc.boolean(),
      help_text: fc.option(safeHelpTextArb, { nil: null }),
      default_value: fc.option(
        fc.stringMatching(/^[a-zA-Z0-9.]+$/u, { minLength: 1, maxLength: 20 }),
        { nil: null }
      ),
      config: fieldConfigForType(type),
    })
);

/**
 * Generate content block text that is safe for text matching.
 */
const safeContentTextArb = fc.stringMatching(/^[A-Z][a-zA-Z0-9 ]{4,39}$/u, {
  minLength: 5,
  maxLength: 40,
});

const canvasContentBlockElementArb: fc.Arbitrary<CanvasContentBlockElement> =
  contentBlockTypeArb.chain((contentType) =>
    fc.record({
      id: fc.uuid(),
      element_type: fc.constant("content_block" as const),
      content_type: fc.constant(contentType),
      text:
        contentType === "divider"
          ? fc.constant(null)
          : safeContentTextArb,
      fieldOrder: fc.constant(0), // Will be recalculated
    })
  );

const canvasItemArb: fc.Arbitrary<CanvasItem> = fc.oneof(
  { weight: 3, arbitrary: canvasFieldElementArb },
  { weight: 2, arbitrary: canvasContentBlockElementArb }
);

/**
 * Generates a valid CanvasItem[] array with at least one field element
 * and contiguous fieldOrder values.
 */
const canvasItemsArb: fc.Arbitrary<CanvasItem[]> = fc
  .tuple(
    // Ensure at least one field element
    canvasFieldElementArb,
    fc.array(canvasItemArb, { minLength: 0, maxLength: 8 })
  )
  .map(([requiredField, rest]) => {
    const items = [requiredField, ...rest];
    // Assign contiguous fieldOrder values
    return items.map((item, index) => ({ ...item, fieldOrder: index }));
  });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
  useTemplateBuilderStore.setState({
    items: [],
    templateName: "",
    selectedFieldId: null,
    activeVersion: null,
  });
}

// ---------------------------------------------------------------------------
// Property Test
// ---------------------------------------------------------------------------

describe("Feature: template-builder-enhancements, Property 9: Preview Completeness", () => {
  afterEach(() => {
    cleanup();
    resetStore();
  });

  it("preview output contains all required elements for any valid canvas state", { timeout: 120000 }, () => {
    fc.assert(
      fc.property(canvasItemsArb, (items) => {
        // Clean up previous render
        cleanup();

        // Set up store with generated items
        useTemplateBuilderStore.setState({
          items,
          templateName: "Test Template",
          activeVersion: null,
        });

        // Render the preview panel in open state
        const { container } = render(
          React.createElement(PdfPreviewPanel, {
            isOpen: true,
            onClose: () => {},
          })
        );

        const html = container.innerHTML;

        // Count expected dividers for assertion
        let expectedDividerCount = 0;

        // Verify each item is represented in the preview output
        for (const item of items) {
          if (item.element_type === "field") {
            const field = item as CanvasFieldElement;

            // (a) Every field's label text must be present
            expect(html).toContain(field.label);

            // (b) Required indicator (*) for fields with required=true
            if (field.required) {
              // The component renders a span with aria-label="required" containing "*"
              const requiredIndicators = container.querySelectorAll(
                '[aria-label="required"]'
              );
              expect(requiredIndicators.length).toBeGreaterThan(0);
            }

            // (c) Help text for every field that has it configured
            if (field.help_text) {
              expect(html).toContain(field.help_text);
            }

            // (d) Unit label for numeric fields that have it configured
            if (field.type === "Float") {
              const config = field.config as FloatFieldConfig;
              if (config.unit_label) {
                expect(html).toContain(config.unit_label);
              }
            }
            if (field.type === "Integer") {
              const config = field.config as IntegerFieldConfig;
              if (config.unit_label) {
                expect(html).toContain(config.unit_label);
              }
            }
          } else if (item.element_type === "content_block") {
            const block = item as CanvasContentBlockElement;

            if (block.content_type === "divider") {
              // (f) Count dividers for batch assertion
              expectedDividerCount++;
            } else {
              // (e) Text content of every heading and paragraph content block
              if (block.text) {
                expect(html).toContain(block.text);
              }
            }
          }
        }

        // (f) Verify the correct number of divider elements (hr tags)
        if (expectedDividerCount > 0) {
          const dividers = container.querySelectorAll("hr");
          expect(dividers.length).toBe(expectedDividerCount);
        }
      }),
      { numRuns: 100 }
    );
  });
});
