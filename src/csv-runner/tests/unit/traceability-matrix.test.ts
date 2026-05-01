/**
 * Unit tests for the traceability matrix builder.
 *
 * Tests that the builder correctly maps REQ-IDs to test files
 * and flags untested requirements.
 */

import { test, expect } from "@playwright/test";
import { buildTraceabilityMatrix } from "../../utils/traceability-matrix";
import { writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const TEST_DIR = join(tmpdir(), "traceability-test-" + Date.now());
const TESTS_DIR = join(TEST_DIR, "tests");

test.beforeAll(() => {
  mkdirSync(TESTS_DIR, { recursive: true });

  // Create mock test files
  writeFileSync(
    join(TESTS_DIR, "req-dm-01.spec.ts"),
    `test("should work @REQ-DM-01", async () => { expect(true).toBe(true); });`
  );
  writeFileSync(
    join(TESTS_DIR, "req-pdf-01.spec.ts"),
    `test("template UUIDs @REQ-PDF-01", async () => { expect(true).toBe(true); });`
  );
  writeFileSync(
    join(TESTS_DIR, "req-pdf-02.spec.ts"),
    `test("offline PDF @REQ-PDF-02", async () => { expect(true).toBe(true); });`
  );
});

test.afterAll(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
});

test.describe("Traceability Matrix Builder", () => {
  test("should map REQ-IDs to test files that reference them", () => {
    const reqIds = ["REQ-DM-01", "REQ-PDF-01", "REQ-PDF-02"];
    const matrix = buildTraceabilityMatrix(reqIds, TESTS_DIR);

    expect(matrix.entries).toHaveLength(3);
    expect(matrix.entries[0].reqId).toBe("REQ-DM-01");
    expect(matrix.entries[0].testFiles).toContain("req-dm-01.spec.ts");
    expect(matrix.entries[0].isTested).toBe(true);
  });

  test("should flag untested requirements", () => {
    const reqIds = ["REQ-DM-01", "REQ-WF-01", "REQ-SIG-01"];
    const matrix = buildTraceabilityMatrix(reqIds, TESTS_DIR);

    expect(matrix.untestedRequirements).toContain("REQ-WF-01");
    expect(matrix.untestedRequirements).toContain("REQ-SIG-01");
    expect(matrix.untestedRequirements).not.toContain("REQ-DM-01");
  });

  test("should calculate coverage percentage correctly", () => {
    const reqIds = ["REQ-DM-01", "REQ-PDF-01", "REQ-WF-01", "REQ-SIG-01"];
    const matrix = buildTraceabilityMatrix(reqIds, TESTS_DIR);

    // 2 out of 4 are tested (REQ-DM-01, REQ-PDF-01)
    expect(matrix.totalRequirements).toBe(4);
    expect(matrix.testedCount).toBe(2);
    expect(matrix.coveragePercent).toBe(50);
  });

  test("should handle empty test directory gracefully", () => {
    const emptyDir = join(TEST_DIR, "empty-tests");
    mkdirSync(emptyDir, { recursive: true });

    const reqIds = ["REQ-DM-01", "REQ-PDF-01"];
    const matrix = buildTraceabilityMatrix(reqIds, emptyDir);

    expect(matrix.totalRequirements).toBe(2);
    expect(matrix.testedCount).toBe(0);
    expect(matrix.coveragePercent).toBe(0);
    expect(matrix.untestedRequirements).toEqual(["REQ-DM-01", "REQ-PDF-01"]);
  });

  test("should handle non-existent directory gracefully", () => {
    const reqIds = ["REQ-DM-01"];
    const matrix = buildTraceabilityMatrix(reqIds, "/non/existent/path");

    expect(matrix.totalRequirements).toBe(1);
    expect(matrix.testedCount).toBe(0);
    expect(matrix.coveragePercent).toBe(0);
  });

  test("should handle empty reqIds array", () => {
    const matrix = buildTraceabilityMatrix([], TESTS_DIR);

    expect(matrix.totalRequirements).toBe(0);
    expect(matrix.testedCount).toBe(0);
    expect(matrix.coveragePercent).toBe(0);
    expect(matrix.entries).toHaveLength(0);
  });

  test("should work with the actual test files directory", () => {
    const reqIds = [
      "REQ-DM-01",
      "REQ-PDF-01",
      "REQ-PDF-02",
      "REQ-PDF-03",
      "REQ-WF-01",
      "REQ-SIG-01",
      "REQ-TRN-01",
      "REQ-TRN-02",
      "REQ-AUD-01",
      "REQ-CSV-01",
      "REQ-CSV-02",
    ];
    const matrix = buildTraceabilityMatrix(reqIds, "src/csv-runner/tests");

    // All REQ-IDs should be tested since we created spec files for each
    expect(matrix.totalRequirements).toBe(11);
    expect(matrix.testedCount).toBe(11);
    expect(matrix.coveragePercent).toBe(100);
    expect(matrix.untestedRequirements).toHaveLength(0);
  });
});
