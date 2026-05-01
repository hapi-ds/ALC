/**
 * Failure Report Generator.
 *
 * When the validation test suite does not achieve a 100% pass rate,
 * this module generates a failure report listing all failed test REQ-IDs
 * with their error details.
 */

import type { TestResult, ValidationRunResults } from "./certificate-generator";

/**
 * A failure report entry for a single failed requirement test.
 */
export interface FailureEntry {
  /** The URS requirement identifier that failed */
  reqId: string;
  /** The error message from the test failure */
  errorMessage: string;
  /** Duration of the failed test in milliseconds */
  durationMs: number;
}

/**
 * The complete failure report generated when tests do not all pass.
 */
export interface FailureReport {
  /** Report title */
  title: string;
  /** ISO timestamp of report generation */
  generatedAt: string;
  /** Total number of tests executed */
  totalTests: number;
  /** Number of tests that passed */
  passedCount: number;
  /** Number of tests that failed */
  failedCount: number;
  /** Pass rate as a percentage (0-100) */
  passRate: number;
  /** Detailed failure entries */
  failures: FailureEntry[];
  /** Summary of failed REQ-IDs */
  failedReqIds: string[];
  /** Recommended actions */
  recommendations: string[];
}

/**
 * Generate a failure report from validation run results.
 *
 * This is called when the test suite does not achieve 100% pass rate.
 * The report details which requirements failed and provides context
 * for investigation and remediation.
 *
 * @param results - The validation run results containing test outcomes.
 * @returns The failure report with all failed REQ-IDs and details.
 */
export function generateFailureReport(
  results: ValidationRunResults
): FailureReport {
  const failedResults = results.testResults.filter((r) => !r.passed);
  const passedCount = results.testResults.filter((r) => r.passed).length;
  const failedCount = failedResults.length;
  const totalTests = results.testResults.length;
  const passRate =
    totalTests > 0 ? Math.round((passedCount / totalTests) * 100) : 0;

  const failures: FailureEntry[] = failedResults.map((r) => ({
    reqId: r.reqId,
    errorMessage: r.errorMessage || "Unknown error",
    durationMs: r.durationMs,
  }));

  const failedReqIds = failures.map((f) => f.reqId);

  const recommendations = [
    `Investigate ${failedCount} failed requirement(s): ${failedReqIds.join(", ")}`,
    "Review test logs for detailed error traces",
    "Verify system configuration matches expected test environment",
    "Re-run failed tests individually for detailed diagnostics",
    "Document root cause analysis for each failure before re-validation",
  ];

  return {
    title: "AlcoaBase Validation Failure Report",
    generatedAt: new Date().toISOString(),
    totalTests,
    passedCount,
    failedCount,
    passRate,
    failures,
    failedReqIds,
    recommendations,
  };
}

/**
 * Submit the failure report to the backend API for storage.
 *
 * @param report - The failure report to store.
 * @param baseUrl - The backend API base URL.
 * @returns The Document-UUID of the stored failure report.
 */
export async function submitFailureReport(
  report: FailureReport,
  baseUrl: string
): Promise<string> {
  const response = await fetch(`${baseUrl}/api/validation/failure-report`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSV-Test-User": "csv_validation_runner",
    },
    body: JSON.stringify(report),
  });

  if (!response.ok) {
    throw new Error(
      `Failed to submit failure report: ${response.status} ${response.statusText}`
    );
  }

  const data = (await response.json()) as { document_uuid: string };
  return data.document_uuid;
}
