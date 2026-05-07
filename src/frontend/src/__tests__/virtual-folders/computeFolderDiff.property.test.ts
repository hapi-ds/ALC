import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { computeFolderDiff } from "../../lib/virtualFolderUtils";
import type { TagFilter, VirtualFolderResponse } from "../../types/virtualFolder";

/**
 * Feature: virtual-folders-frontend, Property 3: Update payload contains only changed fields
 *
 * Validates: Requirements 3.5
 *
 * For any original VirtualFolderResponse and any set of edited values (name, tag_filter, sort_order),
 * the computeFolderDiff function SHALL produce an update object containing only the fields whose
 * values differ from the original, and SHALL produce an empty object when no values have changed.
 */

// Generators
const tagFilterArb: fc.Arbitrary<TagFilter> = fc.record(
  {
    tags: fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 10 }),
    status: fc.constantFrom("Draft", "Active", "Approved", "InTraining", "Retired"),
  },
  { requiredKeys: [] },
);

const virtualFolderResponseArb: fc.Arbitrary<VirtualFolderResponse> = fc.record({
  id: fc.integer({ min: 1, max: 10000 }),
  name: fc.string({ minLength: 1, maxLength: 200 }),
  tag_filter: tagFilterArb,
  sort_order: fc.constantFrom("created_at_desc", "created_at_asc", "name_asc", "name_desc"),
  is_system_default: fc.boolean(),
  created_by: fc.integer({ min: 1, max: 1000 }),
  created_at: fc.option(fc.integer({ min: 946684800000, max: 4102444800000 }).map((ts) => new Date(ts).toISOString()), { nil: null }),
});

const editedValuesArb = fc.record({
  name: fc.string({ minLength: 1, maxLength: 200 }),
  tag_filter: tagFilterArb,
  sort_order: fc.constantFrom("created_at_desc", "created_at_asc", "name_asc", "name_desc"),
});

describe("Feature: virtual-folders-frontend, Property 3: Update payload contains only changed fields", () => {
  it("diff does NOT contain 'name' when edited.name === original.name", () => {
    fc.assert(
      fc.property(virtualFolderResponseArb, editedValuesArb, (original, edited) => {
        const sameNameEdited = { ...edited, name: original.name };
        const diff = computeFolderDiff(original, sameNameEdited);
        expect(diff).not.toHaveProperty("name");
      }),
      { numRuns: 100 },
    );
  });

  it("diff does NOT contain 'tag_filter' when edited.tag_filter deep-equals original.tag_filter", () => {
    fc.assert(
      fc.property(virtualFolderResponseArb, editedValuesArb, (original, edited) => {
        const sameFilterEdited = { ...edited, tag_filter: JSON.parse(JSON.stringify(original.tag_filter)) };
        const diff = computeFolderDiff(original, sameFilterEdited);
        expect(diff).not.toHaveProperty("tag_filter");
      }),
      { numRuns: 100 },
    );
  });

  it("diff does NOT contain 'sort_order' when edited.sort_order === original.sort_order", () => {
    fc.assert(
      fc.property(virtualFolderResponseArb, editedValuesArb, (original, edited) => {
        const sameSortEdited = { ...edited, sort_order: original.sort_order };
        const diff = computeFolderDiff(original, sameSortEdited);
        expect(diff).not.toHaveProperty("sort_order");
      }),
      { numRuns: 100 },
    );
  });

  it("diff is empty object when all fields are the same", () => {
    fc.assert(
      fc.property(virtualFolderResponseArb, (original) => {
        const identicalEdited = {
          name: original.name,
          tag_filter: JSON.parse(JSON.stringify(original.tag_filter)),
          sort_order: original.sort_order,
        };
        const diff = computeFolderDiff(original, identicalEdited);
        expect(diff).toEqual({});
      }),
      { numRuns: 100 },
    );
  });

  it("diff contains 'name' with edited value when name differs", () => {
    fc.assert(
      fc.property(
        virtualFolderResponseArb,
        editedValuesArb.filter((e) => e.name.length > 0),
        (original, edited) => {
          // Ensure name actually differs
          const differentName = edited.name === original.name ? edited.name + "_changed" : edited.name;
          const diffEdited = { ...edited, name: differentName };
          const diff = computeFolderDiff(original, diffEdited);
          expect(diff.name).toBe(differentName);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("diff contains 'tag_filter' with edited value when tag_filter differs", () => {
    fc.assert(
      fc.property(virtualFolderResponseArb, (original) => {
        // Create a tag_filter that is guaranteed to differ
        const differentFilter: TagFilter = {
          tags: ["__unique_test_tag__"],
          status: original.tag_filter.status === "Draft" ? "Active" : "Draft",
        };
        const edited = {
          name: original.name,
          tag_filter: differentFilter,
          sort_order: original.sort_order,
        };
        const diff = computeFolderDiff(original, edited);
        expect(diff.tag_filter).toEqual(differentFilter);
      }),
      { numRuns: 100 },
    );
  });

  it("diff contains 'sort_order' with edited value when sort_order differs", () => {
    fc.assert(
      fc.property(virtualFolderResponseArb, (original) => {
        // Pick a sort_order that differs from original
        const options = ["created_at_desc", "created_at_asc", "name_asc", "name_desc"];
        const differentSort = options.find((o) => o !== original.sort_order) ?? "name_desc";
        const edited = {
          name: original.name,
          tag_filter: JSON.parse(JSON.stringify(original.tag_filter)),
          sort_order: differentSort,
        };
        const diff = computeFolderDiff(original, edited);
        expect(diff.sort_order).toBe(differentSort);
      }),
      { numRuns: 100 },
    );
  });
});
