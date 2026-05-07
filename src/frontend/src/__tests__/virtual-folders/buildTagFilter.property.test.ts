import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { buildTagFilter } from "../../lib/virtualFolderUtils";

/**
 * Feature: virtual-folders-frontend, Property 7: Filter builder produces correct TagFilter structure
 *
 * Validates: Requirements 8.3, 8.4, 8.5, 8.6, 8.9
 *
 * For any combination of selected tags (0–20 strings) and optional status value
 * (one of "Draft", "Active", "Approved", "InTraining", "Retired", or none),
 * the buildTagFilter function SHALL produce a TagFilter where:
 * - if tags are non-empty, `tags` contains exactly those strings
 * - if status is non-null, `status` equals that value
 * - if both are present, both fields exist
 * - if neither is present, the result is an empty object `{}`
 */

const validStatuses = ["Draft", "Active", "Approved", "InTraining", "Retired"] as const;

const tagArb = fc.string({ minLength: 1, maxLength: 50 });
const tagsArrayArb = fc.array(tagArb, { minLength: 0, maxLength: 20 });
const statusArb = fc.option(fc.constantFrom(...validStatuses), { nil: null });

describe("Feature: virtual-folders-frontend, Property 7: Filter builder produces correct TagFilter structure", () => {
  it("includes tags field iff selectedTags is non-empty", () => {
    fc.assert(
      fc.property(tagsArrayArb, statusArb, (tags, status) => {
        const result = buildTagFilter(tags, status);

        if (tags.length > 0) {
          expect(result).toHaveProperty("tags");
          expect(result.tags).toEqual(tags);
        } else {
          expect(result).not.toHaveProperty("tags");
        }
      }),
      { numRuns: 100 }
    );
  });

  it("includes status field iff selectedStatus is non-null", () => {
    fc.assert(
      fc.property(tagsArrayArb, statusArb, (tags, status) => {
        const result = buildTagFilter(tags, status);

        if (status !== null) {
          expect(result).toHaveProperty("status");
          expect(result.status).toBe(status);
        } else {
          expect(result).not.toHaveProperty("status");
        }
      }),
      { numRuns: 100 }
    );
  });

  it("returns empty object when both tags are empty and status is null", () => {
    fc.assert(
      fc.property(fc.constant([]), fc.constant(null), (tags, status) => {
        const result = buildTagFilter(tags as string[], status);

        expect(result).toEqual({});
        expect(Object.keys(result)).toHaveLength(0);
      }),
      { numRuns: 100 }
    );
  });

  it("returns both fields when tags are non-empty and status is non-null", () => {
    fc.assert(
      fc.property(
        fc.array(tagArb, { minLength: 1, maxLength: 20 }),
        fc.constantFrom(...validStatuses),
        (tags, status) => {
          const result = buildTagFilter(tags, status);

          expect(result).toHaveProperty("tags");
          expect(result).toHaveProperty("status");
          expect(result.tags).toEqual(tags);
          expect(result.status).toBe(status);
        }
      ),
      { numRuns: 100 }
    );
  });
});
