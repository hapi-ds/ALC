import { describe, it, expect, beforeEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: template-builder-enhancements, Property 5: Field Order Contiguous Invariant
 *
 * Validates: Requirements 9.6, 7.2, 8.2, 9.2
 *
 * For any canvas state after any sequence of add, remove, and reorder operations
 * on a mix of fields and content blocks, the fieldOrder values SHALL form a
 * contiguous 0-based sequence (0, 1, 2, ..., n-1) with no gaps or duplicates.
 */

// Mock apiClient and auth dependencies (no actual API calls are made in this test)
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    constructor(status: number, body: string) {
      super(body);
      this.status = status;
      this.body = body;
    }
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(),
}));

vi.mock("../authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 1 },
      activeCompanyId: 1,
    }),
    setState: vi.fn(),
  },
}));

import { useTemplateBuilderStore } from "../templateBuilderStore";
import type { FieldType, ContentBlockType } from "../../types/template";

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

/**
 * Represents a single canvas operation.
 */
type CanvasOperation =
  | { type: "addField"; fieldType: FieldType; dropIndex: number }
  | { type: "addContentBlock"; contentType: ContentBlockType; dropIndex: number }
  | { type: "removeItem"; itemIndex: number }
  | { type: "reorderItem"; sourceIndex: number; destinationIndex: number };

/**
 * Generates a random canvas operation. The dropIndex/itemIndex/sourceIndex/destinationIndex
 * are generated as natural numbers and will be clamped to valid ranges during execution.
 */
const canvasOperationArb: fc.Arbitrary<CanvasOperation> = fc.oneof(
  fc.record({
    type: fc.constant("addField" as const),
    fieldType: fieldTypeArb,
    dropIndex: fc.nat({ max: 60 }),
  }),
  fc.record({
    type: fc.constant("addContentBlock" as const),
    contentType: contentBlockTypeArb,
    dropIndex: fc.nat({ max: 60 }),
  }),
  fc.record({
    type: fc.constant("removeItem" as const),
    itemIndex: fc.nat({ max: 60 }),
  }),
  fc.record({
    type: fc.constant("reorderItem" as const),
    sourceIndex: fc.nat({ max: 60 }),
    destinationIndex: fc.nat({ max: 60 }),
  })
);

/**
 * Generate a sequence of operations with a bias toward adds to ensure
 * the canvas has items to remove/reorder.
 */
const operationSequenceArb: fc.Arbitrary<CanvasOperation[]> = fc.array(
  canvasOperationArb,
  { minLength: 1, maxLength: 30 }
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Verifies that the fieldOrder values of all items form a contiguous 0-based sequence.
 */
function assertContiguousFieldOrder(items: { fieldOrder: number }[]): void {
  const fieldOrders = items.map((item) => item.fieldOrder);
  const sorted = [...fieldOrders].sort((a, b) => a - b);

  // Should be 0, 1, 2, ..., n-1
  for (let i = 0; i < sorted.length; i++) {
    expect(sorted[i]).toBe(i);
  }

  // No duplicates
  const unique = new Set(fieldOrders);
  expect(unique.size).toBe(items.length);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Feature: template-builder-enhancements, Property 5: Field Order Contiguous Invariant", () => {
  beforeEach(() => {
    // Reset the store to initial state before each test
    useTemplateBuilderStore.getState().resetBuilder();
  });

  it("fieldOrder values always form a contiguous 0-based sequence after any sequence of add/remove/reorder operations", () => {
    fc.assert(
      fc.property(operationSequenceArb, (operations) => {
        // Reset store for each property run
        useTemplateBuilderStore.getState().resetBuilder();

        for (const op of operations) {
          const state = useTemplateBuilderStore.getState();
          const currentItems = state.items;
          const itemCount = currentItems.length;

          switch (op.type) {
            case "addField": {
              state.addField(op.fieldType, op.dropIndex);
              break;
            }
            case "addContentBlock": {
              state.addContentBlock(op.contentType, op.dropIndex);
              break;
            }
            case "removeItem": {
              if (itemCount > 0) {
                // Pick a valid item to remove
                const validIndex = op.itemIndex % itemCount;
                const itemId = currentItems[validIndex].id;
                state.removeItem(itemId);
              }
              // If no items, skip this operation (no-op)
              break;
            }
            case "reorderItem": {
              if (itemCount > 1) {
                // Clamp indices to valid range
                const source = op.sourceIndex % itemCount;
                const dest = op.destinationIndex % itemCount;
                state.reorderItem(source, dest);
              }
              // If 0 or 1 items, skip (no-op)
              break;
            }
          }

          // After every operation, verify the contiguous invariant holds
          const updatedItems = useTemplateBuilderStore.getState().items;
          assertContiguousFieldOrder(updatedItems);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("fieldOrder is contiguous after interleaved adds of fields and content blocks", () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.record({
              type: fc.constant("addField" as const),
              fieldType: fieldTypeArb,
              dropIndex: fc.nat({ max: 30 }),
            }),
            fc.record({
              type: fc.constant("addContentBlock" as const),
              contentType: contentBlockTypeArb,
              dropIndex: fc.nat({ max: 30 }),
            })
          ),
          { minLength: 2, maxLength: 20 }
        ),
        (addOps) => {
          useTemplateBuilderStore.getState().resetBuilder();

          for (const op of addOps) {
            const state = useTemplateBuilderStore.getState();
            if (op.type === "addField") {
              state.addField(op.fieldType, op.dropIndex);
            } else {
              state.addContentBlock(op.contentType, op.dropIndex);
            }
          }

          const items = useTemplateBuilderStore.getState().items;
          assertContiguousFieldOrder(items);

          // Also verify the count matches the number of add operations
          // (no items lost, accounting for the 50-field max on field elements)
          const fieldAdds = addOps.filter((op) => op.type === "addField").length;
          const contentAdds = addOps.filter((op) => op.type === "addContentBlock").length;
          const expectedFields = Math.min(fieldAdds, 50);
          const actualFields = items.filter((i) => i.element_type === "field").length;
          const actualContentBlocks = items.filter((i) => i.element_type === "content_block").length;

          expect(actualFields).toBe(expectedFields);
          expect(actualContentBlocks).toBe(contentAdds);
        }
      ),
      { numRuns: 100 }
    );
  });
});
