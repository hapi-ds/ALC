import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { sortVersionsDescending, truncateText, validateFileSize, isCurrentVersion, computeVersionDiff, computeTimeDelta, validateChangeReason, formatFileSize } from "@/lib/versionUtils";
import type { DocumentVersion } from "@/types/document";

const MAX_FILE_SIZE = 524_288_000;

/**
 * Helper to create a mock File object with a given size.
 */
function createMockFile(size: number): File {
  return { size } as File;
}

describe("Feature: document-versioning-ui, Property 7: File validation rejects invalid sizes", () => {
  /**
   * **Validates: Requirements 7.1**
   *
   * For any file with size <= 0, validateFileSize SHALL return { valid: false }
   * with an error message.
   */
  it("rejects files with size <= 0", () => {
    fc.assert(
      fc.property(
        fc.integer({ max: 0 }),
        (size) => {
          const result = validateFileSize(createMockFile(size));
          expect(result.valid).toBe(false);
          expect(result.error).toBeDefined();
          expect(typeof result.error).toBe("string");
          expect(result.error!.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 7.1**
   *
   * For any file with size > 524,288,000, validateFileSize SHALL return { valid: false }
   * with an error message.
   */
  it("rejects files with size > 524,288,000", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: MAX_FILE_SIZE + 1, max: Number.MAX_SAFE_INTEGER }),
        (size) => {
          const result = validateFileSize(createMockFile(size));
          expect(result.valid).toBe(false);
          expect(result.error).toBeDefined();
          expect(typeof result.error).toBe("string");
          expect(result.error!.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 7.1**
   *
   * For any file with 0 < size <= 524,288,000, validateFileSize SHALL return { valid: true }.
   */
  it("accepts files with 0 < size <= 524,288,000", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: MAX_FILE_SIZE }),
        (size) => {
          const result = validateFileSize(createMockFile(size));
          expect(result.valid).toBe(true);
          expect(result.error).toBeUndefined();
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe("Feature: document-versioning-ui, Property 5: Time delta computation is non-negative and reversible", () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * For any two valid ISO date strings, computeTimeDelta returns a TimeDelta
   * where all fields are non-negative integers, and the total minutes represented
   * equals the absolute difference in minutes between the two timestamps
   * (within 1-minute tolerance due to flooring).
   */
  it("all fields (days, hours, minutes) are non-negative integers and total minutes equals absolute difference within 1-minute tolerance", () => {
    const safeDate = fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts));
    fc.assert(
      fc.property(safeDate, safeDate, (dateA, dateB) => {
        const isoA = dateA.toISOString();
        const isoB = dateB.toISOString();

        const result = computeTimeDelta(isoA, isoB);

        // All fields are non-negative
        expect(result.days).toBeGreaterThanOrEqual(0);
        expect(result.hours).toBeGreaterThanOrEqual(0);
        expect(result.minutes).toBeGreaterThanOrEqual(0);

        // All fields are integers
        expect(Number.isInteger(result.days)).toBe(true);
        expect(Number.isInteger(result.hours)).toBe(true);
        expect(Number.isInteger(result.minutes)).toBe(true);

        // Total minutes equals absolute difference within 1-minute tolerance
        const expectedTotalMinutes = Math.floor(
          Math.abs(dateA.getTime() - dateB.getTime()) / 60000
        );
        const actualTotalMinutes =
          result.days * 24 * 60 + result.hours * 60 + result.minutes;

        expect(Math.abs(actualTotalMinutes - expectedTotalMinutes)).toBeLessThanOrEqual(1);
      }),
      { numRuns: 100 }
    );
  });
});


describe("Feature: document-versioning-ui, Property 8: Change reason validation enforces length bounds", () => {
  /**
   * **Validates: Requirements 7.2**
   *
   * For any string `reason`, `validateChangeReason(reason)` SHALL return
   * `{ valid: true }` if and only if `reason.trim().length >= 1 AND reason.trim().length <= 2000`.
   * Otherwise it SHALL return `{ valid: false }` with an error message.
   */
  it("returns valid: true iff reason.trim().length is between 1 and 2000 inclusive", () => {
    fc.assert(
      fc.property(fc.string(), (reason) => {
        const trimmedLength = reason.trim().length;
        const result = validateChangeReason(reason);

        if (trimmedLength >= 1 && trimmedLength <= 2000) {
          expect(result.valid).toBe(true);
          expect(result.error).toBeUndefined();
        } else {
          expect(result.valid).toBe(false);
          expect(result.error).toBeDefined();
          expect(typeof result.error).toBe("string");
        }
      }),
      { numRuns: 100 }
    );
  });

  it("rejects empty or whitespace-only strings", () => {
    const whitespaceChars = [" ", "\t", "\n", "\r"];
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(...whitespaceChars), { minLength: 0, maxLength: 50 }),
        (chars) => {
          const whitespace = chars.join("");
          const result = validateChangeReason(whitespace);
          expect(result.valid).toBe(false);
          expect(result.error).toBeDefined();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("rejects strings with trimmed length exceeding 2000", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 2001, maxLength: 3000 }),
        (longReason) => {
          // Ensure trimmed length actually exceeds 2000
          // by prepending a non-whitespace char if needed
          const reason = "x" + longReason;
          const trimmedLength = reason.trim().length;
          if (trimmedLength > 2000) {
            const result = validateChangeReason(reason);
            expect(result.valid).toBe(false);
            expect(result.error).toBeDefined();
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("accepts strings with trimmed length between 1 and 2000", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 2000 }).filter(
          (s) => s.trim().length >= 1 && s.trim().length <= 2000
        ),
        (validReason) => {
          const result = validateChangeReason(validReason);
          expect(result.valid).toBe(true);
          expect(result.error).toBeUndefined();
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe("Feature: document-versioning-ui, Property 4: File size formatting is consistent with threshold", () => {
  const MB_THRESHOLD = 1_048_576;

  /**
   * **Validates: Requirements 7.3**
   *
   * For any non-negative integer bytes < 1,048,576, formatFileSize(bytes)
   * SHALL return a string containing "KB" and the numeric value SHALL be
   * mathematically correct (Math.round(bytes / 1024)).
   */
  it("returns a string containing 'KB' for bytes < 1,048,576 with correct numeric value", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: MB_THRESHOLD - 1 }),
        (bytes) => {
          const result = formatFileSize(bytes);

          // Must contain "KB"
          expect(result).toContain("KB");
          expect(result).not.toContain("MB");

          // Numeric value is mathematically correct (bytes/1024 rounded)
          const expectedKB = Math.round(bytes / 1024);
          expect(result).toBe(`${expectedKB} KB`);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 7.3**
   *
   * For any non-negative integer bytes >= 1,048,576, formatFileSize(bytes)
   * SHALL return a string containing "MB" and the numeric value SHALL be
   * mathematically correct (bytes / 1,048,576 with 1 decimal place).
   */
  it("returns a string containing 'MB' for bytes >= 1,048,576 with correct numeric value", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: MB_THRESHOLD, max: 10_737_418_240 }),
        (bytes) => {
          const result = formatFileSize(bytes);

          // Must contain "MB"
          expect(result).toContain("MB");
          expect(result).not.toContain("KB");

          // Numeric value is mathematically correct (bytes/1048576 with 1 decimal)
          const expectedMB = (bytes / MB_THRESHOLD).toFixed(1);
          expect(result).toBe(`${expectedMB} MB`);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Arbitrary generator for a DocumentVersion with specified major/minor.
 */
function arbitraryDocumentVersion(
  major: number,
  minor: number
): fc.Arbitrary<DocumentVersion> {
  return fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    major_version: fc.constant(major),
    minor_version: fc.constant(minor),
    storage_key: fc.string({ minLength: 1, maxLength: 50 }),
    file_hash: fc.stringMatching(/^[0-9a-f]{64}$/),
    uploaded_by: fc.integer({ min: 1, max: 1000 }),
    uploaded_at: fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString()),
    change_reason: fc.oneof(
      fc.string({ minLength: 1, maxLength: 200 }),
      fc.constant(null)
    ),
  });
}

/**
 * Generates a non-empty array of DocumentVersion objects with distinct (major, minor) tuples.
 */
function arbitraryDistinctVersions(): fc.Arbitrary<DocumentVersion[]> {
  return fc
    .uniqueArray(
      fc.record({
        major: fc.integer({ min: 0, max: 100 }),
        minor: fc.integer({ min: 0, max: 100 }),
      }),
      {
        minLength: 1,
        maxLength: 20,
        comparator: (a, b) => a.major === b.major && a.minor === b.minor,
      }
    )
    .chain((tuples) =>
      fc.tuple(...tuples.map((t) => arbitraryDocumentVersion(t.major, t.minor)))
    )
    .map((versions) => [...versions]);
}

describe("Feature: document-versioning-ui, Property 1: Version sorting is stable descending", () => {
  /**
   * **Validates: Requirements 1.1**
   *
   * For any array of DocumentVersion objects with distinct (major, minor) tuples,
   * sortVersionsDescending SHALL return them ordered such that for every adjacent pair
   * (versions[i], versions[i+1]), versions[i] has a strictly greater (major, minor) tuple
   * than versions[i+1].
   */
  it("every adjacent pair satisfies versions[i] > versions[i+1] lexicographically by (major, minor)", () => {
    fc.assert(
      fc.property(arbitraryDistinctVersions(), (versions) => {
        const sorted = sortVersionsDescending(versions);

        for (let i = 0; i < sorted.length - 1; i++) {
          const current = sorted[i];
          const next = sorted[i + 1];

          const isStrictlyGreater =
            current.major_version > next.major_version ||
            (current.major_version === next.major_version &&
              current.minor_version > next.minor_version);

          expect(isStrictlyGreater).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });
});

describe("Feature: document-versioning-ui, Property 2: Current version identification is unique and maximal", () => {
  /**
   * **Validates: Requirements 2.1, 2.2**
   *
   * For any non-empty array of DocumentVersion objects with distinct (major, minor) tuples,
   * exactly one version is identified as "current" by isCurrentVersion,
   * and that version has the maximum (major, minor) tuple.
   */
  it("exactly one version is identified as current and it has the maximum (major, minor) tuple", () => {
    fc.assert(
      fc.property(arbitraryDistinctVersions(), (versions) => {
        // Count how many versions are identified as current
        const currentVersions = versions.filter((v) =>
          isCurrentVersion(v, versions)
        );

        // Exactly one version should be current
        expect(currentVersions).toHaveLength(1);

        const current = currentVersions[0];

        // The current version should have the maximum (major, minor) tuple
        for (const v of versions) {
          if (v === current) continue;
          const currentIsGreater =
            current.major_version > v.major_version ||
            (current.major_version === v.major_version &&
              current.minor_version > v.minor_version);
          expect(currentIsGreater).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });
});

/**
 * Arbitrary generator for DocumentVersion objects with random major/minor.
 */
function arbitraryFullDocumentVersion(): fc.Arbitrary<DocumentVersion> {
  return fc.record({
    id: fc.integer({ min: 1, max: 100_000 }),
    major_version: fc.integer({ min: 0, max: 100 }),
    minor_version: fc.integer({ min: 0, max: 100 }),
    storage_key: fc.string({ minLength: 1, maxLength: 100 }),
    file_hash: fc.stringMatching(/^[0-9a-f]{64}$/),
    uploaded_by: fc.integer({ min: 1, max: 10_000 }),
    uploaded_at: fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString()),
    change_reason: fc.oneof(
      fc.constant(null),
      fc.string({ minLength: 1, maxLength: 200 })
    ),
  });
}

describe("Feature: document-versioning-ui, Property 6: Version diff detects all field changes correctly", () => {
  /**
   * **Validates: Requirements 4.1, 4.3, 4.4**
   *
   * For any two DocumentVersion objects left and right:
   * - hashChanged equals (left.file_hash !== right.file_hash)
   * - uploaderChanged equals (left.uploaded_by !== right.uploaded_by)
   * - changeReasonChanged equals (left.change_reason !== right.change_reason)
   */
  it("hashChanged equals (left.file_hash !== right.file_hash)", () => {
    fc.assert(
      fc.property(
        arbitraryFullDocumentVersion(),
        arbitraryFullDocumentVersion(),
        (left, right) => {
          const diff = computeVersionDiff(left, right);
          expect(diff.hashChanged).toBe(left.file_hash !== right.file_hash);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("uploaderChanged equals (left.uploaded_by !== right.uploaded_by)", () => {
    fc.assert(
      fc.property(
        arbitraryFullDocumentVersion(),
        arbitraryFullDocumentVersion(),
        (left, right) => {
          const diff = computeVersionDiff(left, right);
          expect(diff.uploaderChanged).toBe(left.uploaded_by !== right.uploaded_by);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("changeReasonChanged equals (left.change_reason !== right.change_reason)", () => {
    fc.assert(
      fc.property(
        arbitraryFullDocumentVersion(),
        arbitraryFullDocumentVersion(),
        (left, right) => {
          const diff = computeVersionDiff(left, right);
          expect(diff.changeReasonChanged).toBe(left.change_reason !== right.change_reason);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe("Feature: document-versioning-ui, Property 3: Text truncation preserves content within limit", () => {
  /**
   * **Validates: Requirements 1.2, 1.3**
   *
   * For any string and positive maxLength, truncateText(text, maxLength) returns a string
   * whose length is at most maxLength + 1 (accounting for the ellipsis character).
   * If text.length <= maxLength, the output equals the input exactly.
   * If text.length > maxLength, the output ends with "…" and the prefix is a prefix of the original.
   */

  it("output length is at most maxLength + 1 for any string and positive maxLength", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 500 }),
        fc.integer({ min: 1, max: 300 }),
        (text, maxLength) => {
          const result = truncateText(text, maxLength);
          expect(result.length).toBeLessThanOrEqual(maxLength + 1);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("if input length <= maxLength, output equals input exactly", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 200 }),
        fc.integer({ min: 1, max: 300 }),
        (text, maxLength) => {
          fc.pre(text.length <= maxLength);
          const result = truncateText(text, maxLength);
          expect(result).toBe(text);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("if input length > maxLength, output ends with '…' and prefix is a prefix of original", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 2, maxLength: 500 }),
        fc.integer({ min: 1, max: 300 }),
        (text, maxLength) => {
          fc.pre(text.length > maxLength);
          const result = truncateText(text, maxLength);

          // Output ends with ellipsis
          expect(result.endsWith("\u2026")).toBe(true);

          // The non-ellipsis prefix is a prefix of the original text
          const prefix = result.slice(0, -1);
          expect(text.startsWith(prefix)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});
