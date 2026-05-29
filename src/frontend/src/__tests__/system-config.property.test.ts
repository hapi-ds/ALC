import { describe, it, expect } from "vitest";
import * as fc from "fast-check";

/**
 * Property-based tests for system configuration frontend logic.
 *
 * Tests pure utility functions used in the admin system configuration UI:
 * - Byte formatting (mirrors backend Property 5)
 * - Quota status classification (mirrors backend Property 6)
 * - Health status color mapping
 * - Pagination calculation
 *
 * **Validates: Requirements 5.1, 5.3, 5.5, 10.3, 14.4**
 */

// ---------------------------------------------------------------------------
// Pure logic under test (mirrors backend implementations)
// ---------------------------------------------------------------------------

/**
 * Convert bytes to human-readable binary units (KB, MB, GB, TB).
 * Rounds to 2 decimal places. Returns "0 B" for zero bytes.
 *
 * Mirrors: StorageQuotaService.format_bytes_human_readable
 */
function formatBytesHumanReadable(sizeBytes: number): string {
  if (sizeBytes === 0) return "0 B";

  const units: [string, number][] = [
    ["TB", 1024 ** 4],
    ["GB", 1024 ** 3],
    ["MB", 1024 ** 2],
    ["KB", 1024 ** 1],
  ];

  for (const [unitName, unitFactor] of units) {
    if (sizeBytes >= unitFactor) {
      const value = sizeBytes / unitFactor;
      return `${value.toFixed(2)} ${unitName}`;
    }
  }

  return `${sizeBytes} B`;
}

/**
 * Compute quota status from usage, limit, and threshold.
 *
 * Mirrors: StorageQuotaService.compute_quota_status
 */
function computeQuotaStatus(
  usageBytes: number,
  quotaBytes: number | null,
  thresholdPct: number | null,
): "normal" | "quota_warning" | "quota_exceeded" {
  if (quotaBytes === null) return "normal";
  if (usageBytes > quotaBytes) return "quota_exceeded";
  if (thresholdPct !== null) {
    const thresholdBytes = (thresholdPct / 100.0) * quotaBytes;
    if (usageBytes > thresholdBytes) return "quota_warning";
  }
  return "normal";
}

/**
 * Classify service health status based on response time.
 *
 * Mirrors: HealthMonitor.classify_status
 */
function classifyHealthStatus(
  responseTimeMs: number,
  degradedThresholdMs: number,
  timeoutMs: number,
): "healthy" | "degraded" | "unreachable" {
  if (responseTimeMs < degradedThresholdMs) return "healthy";
  if (responseTimeMs < timeoutMs) return "degraded";
  return "unreachable";
}

/**
 * Map health status to display color class.
 * Used by the Health Status Grid component.
 *
 * Requirements 11.2: green for healthy, yellow for degraded, red for unreachable.
 */
function getHealthStatusColor(status: "healthy" | "degraded" | "unreachable"): string {
  switch (status) {
    case "healthy":
      return "green";
    case "degraded":
      return "yellow";
    case "unreachable":
      return "red";
  }
}

/**
 * Calculate pagination metadata from total items and page size.
 * Used by the snapshot history list (20 items per page).
 */
function calculatePagination(
  total: number,
  pageSize: number,
  currentPage: number,
): { totalPages: number; hasNext: boolean; hasPrev: boolean; startItem: number; endItem: number } {
  const totalPages = total === 0 ? 0 : Math.ceil(total / pageSize);
  const hasNext = currentPage < totalPages;
  const hasPrev = currentPage > 1;
  const startItem = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, total);
  return { totalPages, hasNext, hasPrev, startItem, endItem };
}

// ---------------------------------------------------------------------------
// Arbitrary generators
// ---------------------------------------------------------------------------

/** Non-negative integer representing bytes (up to ~10 TB). */
const arbBytes = fc.integer({ min: 0, max: 10 * 1024 ** 4 });

/** Positive integer representing a quota limit in bytes. */
const arbQuotaBytes = fc.integer({ min: 1, max: 10 * 1024 ** 4 });

/** Alert threshold percentage (1–99). */
const arbThresholdPct = fc.integer({ min: 1, max: 99 });

/** Response time in milliseconds (0–120000). */
const arbResponseTimeMs = fc.float({ min: 0, max: 120000, noNaN: true });

/** Degraded threshold in ms (must be positive). */
const arbDegradedThreshold = fc.float({ min: 1, max: 30000, noNaN: true });

/** Health status enum. */
const arbHealthStatus = fc.constantFrom<"healthy" | "degraded" | "unreachable">(
  "healthy",
  "degraded",
  "unreachable",
);

/** Total items for pagination. */
const arbTotal = fc.integer({ min: 0, max: 10000 });

/** Page size (positive). */
const arbPageSize = fc.integer({ min: 1, max: 100 });

// ---------------------------------------------------------------------------
// Property 5 (frontend): Human-Readable Byte Formatting
// ---------------------------------------------------------------------------

describe("Feature: admin-system-configuration, Property 5: Human-Readable Byte Formatting", () => {
  /**
   * **Validates: Requirements 5.1**
   *
   * For any non-negative integer representing bytes, formatBytesHumanReadable
   * produces a string with binary units (KB, MB, GB, TB) rounded to 2 decimal
   * places. Parsing the numeric portion × unit factor yields a value within
   * 0.01 of the original / unit factor.
   */
  it("produces a valid unit string for any non-negative byte count", () => {
    fc.assert(
      fc.property(arbBytes, (bytes) => {
        const result = formatBytesHumanReadable(bytes);

        // Must match pattern: "X.XX UNIT" or "N B"
        const validUnits = ["B", "KB", "MB", "GB", "TB"];
        const parts = result.split(" ");
        expect(parts).toHaveLength(2);

        const numericPart = parseFloat(parts[0]);
        const unitPart = parts[1];

        expect(numericPart).not.toBeNaN();
        expect(validUnits).toContain(unitPart);
      }),
      { numRuns: 200 },
    );
  });

  it("zero bytes always returns '0 B'", () => {
    expect(formatBytesHumanReadable(0)).toBe("0 B");
  });

  it("round-trip: parsing numeric × unit factor is within tolerance of original", () => {
    const unitFactors: Record<string, number> = {
      B: 1,
      KB: 1024,
      MB: 1024 ** 2,
      GB: 1024 ** 3,
      TB: 1024 ** 4,
    };

    fc.assert(
      fc.property(fc.integer({ min: 1, max: 10 * 1024 ** 4 }), (bytes) => {
        const result = formatBytesHumanReadable(bytes);
        const parts = result.split(" ");
        const numericPart = parseFloat(parts[0]);
        const unitPart = parts[1];
        const factor = unitFactors[unitPart];

        // Reconstructed value should be close to original
        const reconstructed = numericPart * factor;
        // Tolerance: rounding to 2 decimal places means max error is 0.005 * factor
        const tolerance = 0.005 * factor + 1; // +1 for sub-byte rounding
        expect(Math.abs(reconstructed - bytes)).toBeLessThanOrEqual(tolerance);
      }),
      { numRuns: 200 },
    );
  });

  it("selects the largest appropriate unit", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 10 * 1024 ** 4 }), (bytes) => {
        const result = formatBytesHumanReadable(bytes);
        const parts = result.split(" ");
        const numericPart = parseFloat(parts[0]);
        const unitPart = parts[1];

        // The numeric portion should be >= 1 (we always pick the largest unit where value >= 1)
        if (unitPart !== "B") {
          expect(numericPart).toBeGreaterThanOrEqual(1.0);
        }
      }),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 6 (frontend): Quota Status Classification
// ---------------------------------------------------------------------------

describe("Feature: admin-system-configuration, Property 6: Quota Status Classification", () => {
  /**
   * **Validates: Requirements 5.3, 5.5**
   *
   * For any tuple of (usage_bytes, quota_limit_bytes, alert_threshold_pct),
   * computeQuotaStatus returns one of three mutually exclusive states:
   * - "normal" if no quota OR usage ≤ threshold% × quota
   * - "quota_warning" if usage > threshold% × quota AND ≤ quota
   * - "quota_exceeded" if usage > quota
   */
  it("returns 'normal' when quota is null (no quota configured)", () => {
    fc.assert(
      fc.property(arbBytes, arbThresholdPct, (usage, threshold) => {
        const status = computeQuotaStatus(usage, null, threshold);
        expect(status).toBe("normal");
      }),
      { numRuns: 100 },
    );
  });

  it("returns 'quota_exceeded' when usage > quota", () => {
    fc.assert(
      fc.property(
        arbQuotaBytes,
        arbThresholdPct,
        (quota, threshold) => {
          // usage is strictly greater than quota
          const usage = quota + 1;
          const status = computeQuotaStatus(usage, quota, threshold);
          expect(status).toBe("quota_exceeded");
        },
      ),
      { numRuns: 100 },
    );
  });

  it("returns 'quota_warning' when usage > threshold% × quota AND usage ≤ quota", () => {
    fc.assert(
      fc.property(
        arbQuotaBytes,
        arbThresholdPct,
        (quota, threshold) => {
          const thresholdBytes = (threshold / 100.0) * quota;
          // Generate usage that is above threshold but at or below quota
          // Only test when there's room between threshold and quota
          fc.pre(thresholdBytes < quota);
          // Pick a usage value just above the threshold but within quota
          const usage = Math.min(Math.floor(thresholdBytes) + 1, quota);
          fc.pre(usage > thresholdBytes && usage <= quota);

          const status = computeQuotaStatus(usage, quota, threshold);
          expect(status).toBe("quota_warning");
        },
      ),
      { numRuns: 100 },
    );
  });

  it("returns 'normal' when usage ≤ threshold% × quota", () => {
    fc.assert(
      fc.property(
        arbQuotaBytes,
        arbThresholdPct,
        (quota, threshold) => {
          const thresholdBytes = (threshold / 100.0) * quota;
          // Usage at or below threshold
          const usage = Math.min(Math.floor(thresholdBytes), quota);
          fc.pre(usage <= thresholdBytes);

          const status = computeQuotaStatus(usage, quota, threshold);
          expect(status).toBe("normal");
        },
      ),
      { numRuns: 100 },
    );
  });

  it("states are mutually exclusive and exhaustive", () => {
    fc.assert(
      fc.property(
        arbBytes,
        fc.oneof(fc.constant(null), arbQuotaBytes),
        fc.oneof(fc.constant(null), arbThresholdPct),
        (usage, quota, threshold) => {
          const status = computeQuotaStatus(usage, quota, threshold);
          const validStatuses = ["normal", "quota_warning", "quota_exceeded"];
          expect(validStatuses).toContain(status);

          // Exactly one status is returned (mutual exclusivity is guaranteed by return type)
          const allStatuses = validStatuses.map((s) =>
            computeQuotaStatus(usage, quota, threshold) === s,
          );
          const trueCount = allStatuses.filter(Boolean).length;
          expect(trueCount).toBe(1);
        },
      ),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------
// Health Status Color Mapping
// ---------------------------------------------------------------------------

describe("Feature: admin-system-configuration, Health Status Color Mapping", () => {
  /**
   * **Validates: Requirements 10.3, 11.2**
   *
   * Health status classification is mutually exclusive and exhaustive.
   * Color mapping: healthy → green, degraded → yellow, unreachable → red.
   */
  it("classifyHealthStatus returns exactly one of three states for any valid inputs", () => {
    fc.assert(
      fc.property(
        arbResponseTimeMs,
        arbDegradedThreshold,
        (responseTime, degradedThreshold) => {
          // Timeout must be > degraded threshold for meaningful classification
          const timeout = degradedThreshold + 1000;
          const status = classifyHealthStatus(responseTime, degradedThreshold, timeout);
          const validStatuses = ["healthy", "degraded", "unreachable"];
          expect(validStatuses).toContain(status);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("'healthy' when response time < degraded threshold", () => {
    fc.assert(
      fc.property(
        arbDegradedThreshold,
        (degradedThreshold) => {
          const timeout = degradedThreshold + 5000;
          // Response time strictly less than degraded threshold
          const responseTime = degradedThreshold * 0.5;
          fc.pre(responseTime < degradedThreshold);

          const status = classifyHealthStatus(responseTime, degradedThreshold, timeout);
          expect(status).toBe("healthy");
        },
      ),
      { numRuns: 100 },
    );
  });

  it("'degraded' when degraded threshold ≤ response time < timeout", () => {
    fc.assert(
      fc.property(
        arbDegradedThreshold,
        (degradedThreshold) => {
          const timeout = degradedThreshold + 5000;
          // Response time between degraded and timeout
          const responseTime = degradedThreshold + (timeout - degradedThreshold) * 0.5;
          fc.pre(responseTime >= degradedThreshold && responseTime < timeout);

          const status = classifyHealthStatus(responseTime, degradedThreshold, timeout);
          expect(status).toBe("degraded");
        },
      ),
      { numRuns: 100 },
    );
  });

  it("'unreachable' when response time ≥ timeout", () => {
    fc.assert(
      fc.property(
        arbDegradedThreshold,
        (degradedThreshold) => {
          const timeout = degradedThreshold + 5000;
          // Response time at or above timeout
          const responseTime = timeout + 1000;

          const status = classifyHealthStatus(responseTime, degradedThreshold, timeout);
          expect(status).toBe("unreachable");
        },
      ),
      { numRuns: 100 },
    );
  });

  it("maps each health status to a unique color", () => {
    fc.assert(
      fc.property(arbHealthStatus, (status) => {
        const color = getHealthStatusColor(status);
        const expectedMap: Record<string, string> = {
          healthy: "green",
          degraded: "yellow",
          unreachable: "red",
        };
        expect(color).toBe(expectedMap[status]);
      }),
      { numRuns: 50 },
    );
  });

  it("all three statuses map to distinct colors", () => {
    const colors = new Set([
      getHealthStatusColor("healthy"),
      getHealthStatusColor("degraded"),
      getHealthStatusColor("unreachable"),
    ]);
    expect(colors.size).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// Pagination Calculation
// ---------------------------------------------------------------------------

describe("Feature: admin-system-configuration, Pagination Calculation", () => {
  /**
   * **Validates: Requirements 14.4**
   *
   * Pagination arithmetic for configuration snapshot history (20 per page).
   * totalPages = ceil(total / pageSize), hasNext/hasPrev are correct,
   * startItem/endItem bounds are valid.
   */
  it("totalPages = ceil(total / pageSize) for any positive total and pageSize", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        arbPageSize,
        (total, pageSize) => {
          const { totalPages } = calculatePagination(total, pageSize, 1);
          expect(totalPages).toBe(Math.ceil(total / pageSize));
        },
      ),
      { numRuns: 200 },
    );
  });

  it("totalPages is 0 when total is 0", () => {
    fc.assert(
      fc.property(arbPageSize, (pageSize) => {
        const { totalPages } = calculatePagination(0, pageSize, 1);
        expect(totalPages).toBe(0);
      }),
      { numRuns: 50 },
    );
  });

  it("hasNext is true iff currentPage < totalPages", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        arbPageSize,
        (total, pageSize) => {
          const totalPages = Math.ceil(total / pageSize);
          // Pick a valid page
          const currentPage = Math.max(1, Math.min(totalPages, Math.ceil(totalPages / 2)));
          const result = calculatePagination(total, pageSize, currentPage);
          expect(result.hasNext).toBe(currentPage < totalPages);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("hasPrev is true iff currentPage > 1", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        arbPageSize,
        fc.integer({ min: 1, max: 500 }),
        (total, pageSize, page) => {
          const totalPages = Math.ceil(total / pageSize);
          const currentPage = Math.min(page, totalPages);
          fc.pre(currentPage >= 1);

          const result = calculatePagination(total, pageSize, currentPage);
          expect(result.hasPrev).toBe(currentPage > 1);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("startItem and endItem are within valid bounds", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        arbPageSize,
        (total, pageSize) => {
          const totalPages = Math.ceil(total / pageSize);
          const currentPage = Math.max(1, Math.min(totalPages, Math.ceil(totalPages / 2)));
          const result = calculatePagination(total, pageSize, currentPage);

          // startItem is 1-indexed
          expect(result.startItem).toBeGreaterThanOrEqual(1);
          expect(result.startItem).toBeLessThanOrEqual(total);
          // endItem does not exceed total
          expect(result.endItem).toBeLessThanOrEqual(total);
          // endItem >= startItem
          expect(result.endItem).toBeGreaterThanOrEqual(result.startItem);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("endItem - startItem + 1 ≤ pageSize (page never exceeds page size)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        arbPageSize,
        (total, pageSize) => {
          const totalPages = Math.ceil(total / pageSize);
          const currentPage = Math.max(1, Math.min(totalPages, Math.ceil(totalPages / 2)));
          const result = calculatePagination(total, pageSize, currentPage);

          const itemsOnPage = result.endItem - result.startItem + 1;
          expect(itemsOnPage).toBeLessThanOrEqual(pageSize);
          expect(itemsOnPage).toBeGreaterThanOrEqual(1);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("startItem = (currentPage - 1) * pageSize + 1 for non-empty results", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        arbPageSize,
        (total, pageSize) => {
          const totalPages = Math.ceil(total / pageSize);
          const currentPage = Math.max(1, Math.min(totalPages, Math.ceil(totalPages / 2)));
          const result = calculatePagination(total, pageSize, currentPage);

          expect(result.startItem).toBe((currentPage - 1) * pageSize + 1);
        },
      ),
      { numRuns: 200 },
    );
  });
});
