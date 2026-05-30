import { describe, it, expect } from "vitest";
import * as fc from "fast-check";

/**
 * Property-based tests for the Audit Trail Viewer frontend logic.
 *
 * Tests pure utility functions used in the audit trail UI:
 * - Filter state management correctness (query param building)
 * - Event formatting/truncation logic
 * - Pagination cursor handling (no duplicates in accumulated results)
 * - Changed fields display (max 10 with "+N more" indicator)
 *
 * **Validates: Requirements 1.3, 2.4, 3.6, 10.2**
 */

// ---------------------------------------------------------------------------
// Pure logic under test (extracted from components/store)
// ---------------------------------------------------------------------------

import type { AuditTrailFilters, AuditEvent, SortConfig } from "../types/auditTrail";

/**
 * Build query string parameters from filter state.
 * Mirrors: useAuditTrailStore.buildQueryParams
 */
function buildQueryParams(
  filters: AuditTrailFilters,
  searchQuery: string,
  cursor: string | null,
  sort: SortConfig,
): string {
  const params = new URLSearchParams();

  params.set("page_size", "50");

  if (cursor) {
    params.set("cursor", cursor);
  }

  if (searchQuery.trim()) {
    params.set("search", searchQuery.trim());
  }

  if (filters.user_id !== undefined) {
    params.set("user_id", String(filters.user_id));
  }
  if (filters.date_start) {
    params.set("date_start", filters.date_start);
  }
  if (filters.date_end) {
    params.set("date_end", filters.date_end);
  }
  if (filters.record_type) {
    params.set("record_type", filters.record_type);
  }
  if (filters.operation_type) {
    params.set("operation_type", filters.operation_type);
  }

  if (sort.column) {
    params.set("sort_column", sort.column);
  }
  if (sort.direction) {
    params.set("sort_direction", sort.direction);
  }

  return params.toString();
}

/**
 * Truncate text to a max length, appending ellipsis if truncated.
 * Mirrors: AuditTrailTable.truncateText
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "…";
}

/**
 * Format changed fields for display: show max 10 fields, with "+N more" indicator.
 * Mirrors: AuditTrailTable.ChangedFieldsDisplay logic
 */
function formatChangedFields(
  changedFields: string[],
  totalChangedFields: number,
): { displayed: string[]; remaining: number } {
  const MAX_DISPLAYED_FIELDS = 10;
  const displayedFields = changedFields.slice(0, MAX_DISPLAYED_FIELDS);
  const remaining = totalChangedFields - displayedFields.length;
  return { displayed: displayedFields, remaining: Math.max(0, remaining) };
}

/**
 * Accumulate paginated events, ensuring no duplicates by composite key.
 * Mirrors: useAuditTrailStore.fetchNextPage append logic
 */
function accumulateEvents(
  existing: AuditEvent[],
  newPage: AuditEvent[],
): AuditEvent[] {
  const seen = new Set(
    existing.map((e) => `${e.record_type}-${e.record_id}-${e.transaction_id}`),
  );
  const deduped = newPage.filter(
    (e) => !seen.has(`${e.record_type}-${e.record_id}-${e.transaction_id}`),
  );
  return [...existing, ...deduped];
}

// ---------------------------------------------------------------------------
// Arbitrary generators
// ---------------------------------------------------------------------------

const arbOperationType = fc.constantFrom<"INSERT" | "UPDATE" | "DELETE">(
  "INSERT",
  "UPDATE",
  "DELETE",
);

const arbRecordType = fc.constantFrom(
  "documents",
  "templates",
  "reports",
  "workflows",
  "signatures",
  "training_tasks",
  "training_records",
);

const arbSortDirection = fc.constantFrom<"asc" | "desc">("asc", "desc");

const arbSortColumn = fc.constantFrom(
  "timestamp",
  "user",
  "record_type",
  "operation_type",
);

const arbSortConfig: fc.Arbitrary<SortConfig> = fc.record({
  column: arbSortColumn,
  direction: arbSortDirection,
});

/** Generate an ISO date string from a timestamp in a safe range. */
const arbIsoDateString = fc
  .integer({ min: 1577836800000, max: 1767225600000 }) // 2020-01-01 to 2025-12-31 in ms
  .map((ms) => new Date(ms).toISOString());

const arbFilters: fc.Arbitrary<AuditTrailFilters> = fc.record(
  {
    user_id: fc.integer({ min: 1, max: 10000 }),
    date_start: arbIsoDateString,
    date_end: arbIsoDateString,
    record_type: arbRecordType,
    operation_type: arbOperationType,
  },
  { requiredKeys: [] },
);

const arbSearchQuery = fc.oneof(
  fc.constant(""),
  fc.string({ minLength: 1, maxLength: 100 }),
);

const arbCursor = fc.oneof(
  fc.constant(null),
  fc.string({ minLength: 5, maxLength: 50 }).map((s) => btoa(s)),
);

/** Generate a valid AuditEvent for testing. */
const arbAuditEvent: fc.Arbitrary<AuditEvent> = fc.record({
  transaction_id: fc.integer({ min: 1, max: 100000 }),
  timestamp: arbIsoDateString,
  user_id: fc.integer({ min: 1, max: 10000 }),
  user_display_name: fc.oneof(
    fc.constant(null),
    fc.string({ minLength: 1, maxLength: 50 }),
  ),
  record_type: arbRecordType,
  record_id: fc.integer({ min: 1, max: 100000 }),
  operation_type: arbOperationType,
  change_reason: fc.oneof(
    fc.constant(null),
    fc.string({ minLength: 0, maxLength: 1000 }),
  ),
  changed_fields: fc.array(fc.string({ minLength: 1, maxLength: 30 }), {
    minLength: 0,
    maxLength: 50,
  }),
  total_changed_fields: fc.integer({ min: 0, max: 50 }),
  company_id: fc.integer({ min: 1, max: 100 }),
});

// ---------------------------------------------------------------------------
// Property: Filter state management correctness
// ---------------------------------------------------------------------------

describe("Feature: Step_6-3_audit-trail-viewer, Property: Filter state management correctness", () => {
  /**
   * **Validates: Requirements 3.6**
   *
   * For any combination of filters, the built query string correctly reflects
   * all applied filter values. Each non-empty filter appears as a query param,
   * and empty/undefined filters are omitted.
   */
  it("includes all defined filter fields in query params", () => {
    fc.assert(
      fc.property(arbFilters, arbSearchQuery, arbCursor, arbSortConfig, (filters, search, cursor, sort) => {
        const queryString = buildQueryParams(filters, search, cursor, sort);
        const params = new URLSearchParams(queryString);

        // page_size is always present
        expect(params.get("page_size")).toBe("50");

        // Each defined filter should appear in params
        if (filters.user_id !== undefined) {
          expect(params.get("user_id")).toBe(String(filters.user_id));
        } else {
          expect(params.has("user_id")).toBe(false);
        }

        if (filters.date_start) {
          expect(params.get("date_start")).toBe(filters.date_start);
        } else {
          expect(params.has("date_start")).toBe(false);
        }

        if (filters.date_end) {
          expect(params.get("date_end")).toBe(filters.date_end);
        } else {
          expect(params.has("date_end")).toBe(false);
        }

        if (filters.record_type) {
          expect(params.get("record_type")).toBe(filters.record_type);
        } else {
          expect(params.has("record_type")).toBe(false);
        }

        if (filters.operation_type) {
          expect(params.get("operation_type")).toBe(filters.operation_type);
        } else {
          expect(params.has("operation_type")).toBe(false);
        }
      }),
      { numRuns: 100 },
    );
  });

  it("includes search query only when non-empty after trimming", () => {
    fc.assert(
      fc.property(arbFilters, arbSearchQuery, arbSortConfig, (filters, search, sort) => {
        const queryString = buildQueryParams(filters, search, null, sort);
        const params = new URLSearchParams(queryString);

        if (search.trim()) {
          expect(params.get("search")).toBe(search.trim());
        } else {
          expect(params.has("search")).toBe(false);
        }
      }),
      { numRuns: 100 },
    );
  });

  it("includes cursor only when non-null", () => {
    fc.assert(
      fc.property(arbFilters, arbCursor, arbSortConfig, (filters, cursor, sort) => {
        const queryString = buildQueryParams(filters, "", cursor, sort);
        const params = new URLSearchParams(queryString);

        if (cursor) {
          expect(params.get("cursor")).toBe(cursor);
        } else {
          expect(params.has("cursor")).toBe(false);
        }
      }),
      { numRuns: 100 },
    );
  });

  it("includes sort column and direction", () => {
    fc.assert(
      fc.property(arbSortConfig, (sort) => {
        const queryString = buildQueryParams({}, "", null, sort);
        const params = new URLSearchParams(queryString);

        expect(params.get("sort_column")).toBe(sort.column);
        expect(params.get("sort_direction")).toBe(sort.direction);
      }),
      { numRuns: 100 },
    );
  });

  it("empty filters produce only page_size and sort params", () => {
    fc.assert(
      fc.property(arbSortConfig, (sort) => {
        const queryString = buildQueryParams({}, "", null, sort);
        const params = new URLSearchParams(queryString);

        // Should only have page_size, sort_column, sort_direction
        const keys = Array.from(params.keys());
        expect(keys).toContain("page_size");
        expect(keys).toContain("sort_column");
        expect(keys).toContain("sort_direction");
        expect(keys).not.toContain("user_id");
        expect(keys).not.toContain("date_start");
        expect(keys).not.toContain("date_end");
        expect(keys).not.toContain("record_type");
        expect(keys).not.toContain("operation_type");
        expect(keys).not.toContain("search");
        expect(keys).not.toContain("cursor");
      }),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property: Event formatting/truncation logic
// ---------------------------------------------------------------------------

describe("Feature: Step_6-3_audit-trail-viewer, Property: Event formatting/truncation logic", () => {
  /**
   * **Validates: Requirements 1.3, 10.2**
   *
   * For any text and max length, truncateText either returns the original text
   * (if within limit) or returns exactly maxLength characters followed by an
   * ellipsis character.
   */
  it("returns original text when length <= maxLength", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 200 }),
        fc.integer({ min: 1, max: 500 }),
        (text, maxLength) => {
          fc.pre(text.length <= maxLength);
          const result = truncateText(text, maxLength);
          expect(result).toBe(text);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("truncates to maxLength chars + ellipsis when text exceeds maxLength", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 2, maxLength: 1000 }),
        fc.integer({ min: 1, max: 500 }),
        (text, maxLength) => {
          fc.pre(text.length > maxLength);
          const result = truncateText(text, maxLength);

          // Result should be maxLength chars + 1 ellipsis char
          expect(result.length).toBe(maxLength + 1);
          // Should end with ellipsis
          expect(result.endsWith("…")).toBe(true);
          // The prefix should match the original text
          expect(result.slice(0, maxLength)).toBe(text.slice(0, maxLength));
        },
      ),
      { numRuns: 100 },
    );
  });

  it("truncated result never exceeds maxLength + 1 (ellipsis char)", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 1000 }),
        fc.integer({ min: 1, max: 500 }),
        (text, maxLength) => {
          const result = truncateText(text, maxLength);
          expect(result.length).toBeLessThanOrEqual(maxLength + 1);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("truncation is idempotent for already-short text", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 50 }),
        (text) => {
          const maxLength = 80; // MAX_CHANGE_REASON_LENGTH in table
          const result = truncateText(text, maxLength);
          // Applying truncation again should yield the same result
          const resultAgain = truncateText(result, maxLength);
          expect(resultAgain).toBe(result);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property: Pagination cursor handling (no duplicates)
// ---------------------------------------------------------------------------

describe("Feature: Step_6-3_audit-trail-viewer, Property: Pagination cursor handling", () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * For any sequence of page fetches, accumulating events with deduplication
   * by composite key (record_type, record_id, transaction_id) yields no
   * duplicate entries.
   */
  it("accumulated events contain no duplicates by composite key", () => {
    fc.assert(
      fc.property(
        fc.array(arbAuditEvent, { minLength: 0, maxLength: 30 }),
        fc.array(arbAuditEvent, { minLength: 0, maxLength: 30 }),
        (page1, page2) => {
          const accumulated = accumulateEvents(page1, page2);

          // Check no duplicates by composite key
          const keys = accumulated.map(
            (e) => `${e.record_type}-${e.record_id}-${e.transaction_id}`,
          );
          const uniqueKeys = new Set(keys);
          expect(keys.length).toBe(uniqueKeys.size);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("all events from first page are preserved in accumulation", () => {
    fc.assert(
      fc.property(
        fc.array(arbAuditEvent, { minLength: 1, maxLength: 20 }),
        fc.array(arbAuditEvent, { minLength: 0, maxLength: 20 }),
        (page1, page2) => {
          const accumulated = accumulateEvents(page1, page2);

          // All page1 events should be in the result
          for (const event of page1) {
            const key = `${event.record_type}-${event.record_id}-${event.transaction_id}`;
            const found = accumulated.some(
              (e) => `${e.record_type}-${e.record_id}-${e.transaction_id}` === key,
            );
            expect(found).toBe(true);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it("accumulation is monotonically growing (length never decreases)", () => {
    fc.assert(
      fc.property(
        fc.array(arbAuditEvent, { minLength: 0, maxLength: 20 }),
        fc.array(arbAuditEvent, { minLength: 0, maxLength: 20 }),
        (page1, page2) => {
          const accumulated = accumulateEvents(page1, page2);
          expect(accumulated.length).toBeGreaterThanOrEqual(page1.length);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("accumulating with empty page returns original events unchanged", () => {
    fc.assert(
      fc.property(
        fc.array(arbAuditEvent, { minLength: 0, maxLength: 30 }),
        (page1) => {
          const accumulated = accumulateEvents(page1, []);
          expect(accumulated.length).toBe(page1.length);
          expect(accumulated).toEqual(page1);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property: Changed fields display (max 10 with "+N more" indicator)
// ---------------------------------------------------------------------------

describe("Feature: Step_6-3_audit-trail-viewer, Property: Changed fields display", () => {
  /**
   * **Validates: Requirements 1.3**
   *
   * For any event with N changed fields (0 ≤ N ≤ 50), the display logic
   * shows at most 10 field names and a "+N more" indicator when total > 10.
   */
  it("displays at most 10 fields regardless of input size", () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), {
          minLength: 0,
          maxLength: 50,
        }),
        (fields) => {
          const totalCount = fields.length;
          const { displayed } = formatChangedFields(fields, totalCount);
          expect(displayed.length).toBeLessThanOrEqual(10);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("remaining count is zero when total fields <= 10", () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), {
          minLength: 0,
          maxLength: 10,
        }),
        (fields) => {
          const totalCount = fields.length;
          const { displayed, remaining } = formatChangedFields(fields, totalCount);
          expect(remaining).toBe(0);
          expect(displayed.length).toBe(fields.length);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("remaining count equals totalChangedFields - displayed count when total > 10", () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), {
          minLength: 11,
          maxLength: 50,
        }),
        (fields) => {
          const totalCount = fields.length;
          const { displayed, remaining } = formatChangedFields(fields, totalCount);
          expect(displayed.length).toBe(10);
          expect(remaining).toBe(totalCount - 10);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("displayed fields are the first N fields from the input (preserves order)", () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), {
          minLength: 1,
          maxLength: 50,
        }),
        (fields) => {
          const totalCount = fields.length;
          const { displayed } = formatChangedFields(fields, totalCount);

          // Displayed fields should be the first slice of the input
          const expectedSlice = fields.slice(0, Math.min(10, fields.length));
          expect(displayed).toEqual(expectedSlice);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("handles totalChangedFields > changedFields.length (server truncation)", () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), {
          minLength: 0,
          maxLength: 10,
        }),
        fc.integer({ min: 11, max: 50 }),
        (fields, totalCount) => {
          // Server may send fewer fields than totalChangedFields indicates
          fc.pre(totalCount > fields.length);
          const { displayed, remaining } = formatChangedFields(fields, totalCount);

          expect(displayed.length).toBeLessThanOrEqual(10);
          expect(displayed.length).toBe(fields.length);
          expect(remaining).toBe(totalCount - displayed.length);
          expect(remaining).toBeGreaterThan(0);
        },
      ),
      { numRuns: 100 },
    );
  });
});
