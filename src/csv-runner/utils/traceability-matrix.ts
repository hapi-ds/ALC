/**
 * Traceability Matrix Builder - Maps URS REQ-IDs to Playwright test case IDs.
 *
 * Builds a traceability matrix that shows which requirements are covered
 * by which test files, and flags any untested requirements.
 */

import { readFileSync, readdirSync } from "node:fs";
import { resolve, basename } from "node:path";

/**
 * A single entry in the traceability matrix mapping a requirement
 * to its associated test cases.
 */
export interface TraceabilityEntry {
  /** The URS requirement identifier (e.g., REQ-DM-01) */
  reqId: string;
  /** Array of test file names that cover this requirement */
  testFiles: string[];
  /** Whether this requirement has at least one associated test */
  isTested: boolean;
}

/**
 * The complete traceability matrix with summary statistics.
 */
export interface TraceabilityMatrix {
  /** All requirement-to-test mappings */
  entries: TraceabilityEntry[];
  /** Requirements that have no associated test files */
  untestedRequirements: string[];
  /** Total number of requirements */
  totalRequirements: number;
  /** Number of requirements with at least one test */
  testedCount: number;
  /** Coverage percentage (0-100) */
  coveragePercent: number;
}

/**
 * Regex to extract REQ-ID tags from Playwright test file content.
 * Matches tags like @REQ-DM-01 or test descriptions containing REQ-DM-01.
 */
const REQ_TAG_PATTERN = /REQ-[A-Z]{2,4}-\d{2}/g;

/**
 * Build a traceability matrix mapping URS requirement IDs to Playwright test files.
 *
 * Scans test files for REQ-ID references (in test tags, descriptions, or comments)
 * and builds a mapping showing coverage status for each requirement.
 *
 * @param reqIds - Array of requirement identifiers from the URS.
 * @param testDir - Path to the directory containing Playwright test files.
 * @returns The complete traceability matrix with coverage statistics.
 */
export function buildTraceabilityMatrix(
  reqIds: string[],
  testDir: string
): TraceabilityMatrix {
  const resolvedDir = resolve(testDir);

  // Discover test files
  let testFiles: string[] = [];
  try {
    testFiles = readdirSync(resolvedDir).filter((f) => f.endsWith(".spec.ts"));
  } catch {
    // Directory may not exist yet during early development
    testFiles = [];
  }

  // Build a map of REQ-ID -> test files that reference it
  const reqToTests = new Map<string, string[]>();

  for (const reqId of reqIds) {
    reqToTests.set(reqId, []);
  }

  for (const testFile of testFiles) {
    const filePath = resolve(resolvedDir, testFile);
    const content = readFileSync(filePath, "utf-8");
    const matches = content.match(REQ_TAG_PATTERN);

    if (matches) {
      const uniqueMatches = [...new Set(matches)];
      for (const reqId of uniqueMatches) {
        if (reqToTests.has(reqId)) {
          reqToTests.get(reqId)!.push(testFile);
        }
      }
    }
  }

  // Build entries
  const entries: TraceabilityEntry[] = reqIds.map((reqId) => ({
    reqId,
    testFiles: reqToTests.get(reqId) || [],
    isTested: (reqToTests.get(reqId) || []).length > 0,
  }));

  const untestedRequirements = entries
    .filter((e) => !e.isTested)
    .map((e) => e.reqId);

  const testedCount = entries.filter((e) => e.isTested).length;
  const totalRequirements = reqIds.length;
  const coveragePercent =
    totalRequirements > 0
      ? Math.round((testedCount / totalRequirements) * 100)
      : 0;

  return {
    entries,
    untestedRequirements,
    totalRequirements,
    testedCount,
    coveragePercent,
  };
}
