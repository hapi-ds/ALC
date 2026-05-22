/**
 * Training Management UI - Pure Utility Functions
 *
 * All functions in this module are pure (no side effects, deterministic output
 * for given inputs) and operate on the training domain types.
 */

import type {
  TrainingTask,
  TrainingStatistics,
  TaskFilter,
  QuizQuestion,
  GateCache,
} from "./types";

/**
 * Training record with validity information, derived from completed tasks.
 */
export interface TrainingRecord {
  id: number;
  sop_document_uuid: string;
  sop_version: string;
  completed_at: string;
  is_valid: boolean;
}

/**
 * SOP document UUID + version pair for admin selector.
 */
export interface SopVersionPair {
  sop_document_uuid: string;
  sop_version: string;
}

/**
 * Sort key options for training records.
 */
export type RecordSortKey = "sop_document_uuid" | "completed_at" | "sop_version";

// ---------------------------------------------------------------------------
// Property 1: Statistics computation
// Validates: Requirements 1.1, 1.5
// ---------------------------------------------------------------------------

/**
 * Compute training statistics from an array of tasks.
 *
 * - pending = count of tasks where is_completed is false
 * - completed = count of tasks where is_completed is true
 * - total = array length
 * - completionPercentage = Math.round(completed / total * 100) when total > 0, null otherwise
 */
export function computeStatistics(tasks: TrainingTask[]): TrainingStatistics {
  const total = tasks.length;
  const completed = tasks.filter((t) => t.is_completed).length;
  const pending = total - completed;
  const completionPercentage =
    total > 0 ? Math.round((completed / total) * 100) : null;

  return { pending, completed, total, completionPercentage };
}

// ---------------------------------------------------------------------------
// Property 2: Title truncation
// Validates: Requirements 2.1
// ---------------------------------------------------------------------------

/**
 * Truncate a title to maxLength characters. If the title exceeds maxLength,
 * return the first maxLength characters followed by "\u2026" (ellipsis character).
 * Otherwise return the original string unchanged.
 */
export function truncateTitle(title: string, maxLength: number = 80): string {
  if (title.length <= maxLength) {
    return title;
  }
  return title.slice(0, maxLength) + "\u2026";
}

// ---------------------------------------------------------------------------
// Property 3: Client-side filtering
// Validates: Requirements 2.3, 5.2
// ---------------------------------------------------------------------------

/**
 * Filter tasks by status. Returns:
 * - all tasks when filter is "all"
 * - only tasks where is_completed is false when filter is "pending"
 * - only tasks where is_completed is true when filter is "completed"
 */
export function filterTasks(
  tasks: TrainingTask[],
  filter: TaskFilter
): TrainingTask[] {
  switch (filter) {
    case "all":
      return tasks;
    case "pending":
      return tasks.filter((t) => !t.is_completed);
    case "completed":
      return tasks.filter((t) => t.is_completed);
  }
}

// ---------------------------------------------------------------------------
// Property 4: Task sorting
// Validates: Requirements 2.4
// ---------------------------------------------------------------------------

/**
 * Sort tasks with pending tasks first (ordered by created_at ascending),
 * followed by completed tasks (ordered by completed_at descending).
 *
 * Returns a new sorted array (does not mutate input).
 */
export function sortTasks(tasks: TrainingTask[]): TrainingTask[] {
  return [...tasks].sort((a, b) => {
    // Pending before completed
    if (a.is_completed !== b.is_completed) {
      return a.is_completed ? 1 : -1;
    }

    if (!a.is_completed) {
      // Both pending: sort by created_at ascending
      return a.created_at.localeCompare(b.created_at);
    }

    // Both completed: sort by completed_at descending
    const aCompleted = a.completed_at ?? "";
    const bCompleted = b.completed_at ?? "";
    return bCompleted.localeCompare(aCompleted);
  });
}

// ---------------------------------------------------------------------------
// Property 5: Bounded-length input validation
// Validates: Requirements 3.2, 7.4
// ---------------------------------------------------------------------------

/**
 * Validate that a trimmed input string has length within [minLength, maxLength].
 * Returns true if valid, false otherwise.
 */
export function validateInputLength(
  input: string,
  minLength: number,
  maxLength: number
): boolean {
  const trimmed = input.trim();
  return trimmed.length >= minLength && trimmed.length <= maxLength;
}

// ---------------------------------------------------------------------------
// Property 6: Content ID derivation
// Validates: Requirements 4.1
// ---------------------------------------------------------------------------

/**
 * Derive a content ID from a SOP document UUID and version.
 * Format: "{sop_document_uuid}_v{sop_version}"
 */
export function deriveContentId(
  sopDocumentUuid: string,
  sopVersion: string
): string {
  return `${sopDocumentUuid}_v${sopVersion}`;
}

// ---------------------------------------------------------------------------
// Property 7: Section rendering logic
// Validates: Requirements 4.2
// ---------------------------------------------------------------------------

/**
 * Determine whether a content section should be rendered.
 * A section renders only when its data array is non-empty.
 */
export function shouldRenderSection(data: unknown[]): boolean {
  return data.length > 0;
}

// ---------------------------------------------------------------------------
// Property 8: Quiz answer options
// Validates: Requirements 4.4
// ---------------------------------------------------------------------------

/**
 * Shuffle answer options for a quiz question. Combines the correct_answer
 * with distractors and returns them in a randomized order.
 *
 * The returned array contains exactly {correct_answer} union {distractors}
 * with no duplicates added and no options removed.
 *
 * Uses Fisher-Yates shuffle for uniform distribution.
 */
export function shuffleAnswerOptions(question: QuizQuestion): string[] {
  const options = [question.correct_answer, ...question.distractors];

  // Fisher-Yates shuffle
  for (let i = options.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [options[i], options[j]] = [options[j], options[i]];
  }

  return options;
}

// ---------------------------------------------------------------------------
// Property 9: Record validity determination
// Validates: Requirements 5.3
// ---------------------------------------------------------------------------

/**
 * Determine validity of training records from completed tasks.
 *
 * A record is "valid" if it has the highest sop_version (lexicographically)
 * among all completed tasks for the same sop_document_uuid.
 * All other records for the same SOP are marked "invalidated".
 *
 * Returns a map of task ID to validity boolean.
 */
export function determineRecordValidity(
  tasks: TrainingTask[]
): Record<number, boolean> {
  const completedTasks = tasks.filter((t) => t.is_completed);

  // Group by sop_document_uuid
  const grouped: Record<string, TrainingTask[]> = {};
  for (const task of completedTasks) {
    if (!grouped[task.sop_document_uuid]) {
      grouped[task.sop_document_uuid] = [];
    }
    grouped[task.sop_document_uuid].push(task);
  }

  // For each group, find the highest version
  const validityMap: Record<number, boolean> = {};
  for (const sopUuid of Object.keys(grouped)) {
    const sopTasks = grouped[sopUuid];
    // Find the highest version (lexicographic comparison)
    let highestVersion = sopTasks[0].sop_version;
    for (const task of sopTasks) {
      if (task.sop_version.localeCompare(highestVersion) > 0) {
        highestVersion = task.sop_version;
      }
    }

    // Mark validity
    for (const task of sopTasks) {
      validityMap[task.id] = task.sop_version === highestVersion;
    }
  }

  return validityMap;
}

// ---------------------------------------------------------------------------
// Property 10: Records sorting
// Validates: Requirements 5.4
// ---------------------------------------------------------------------------

/**
 * Sort training records by the specified key.
 * - sop_document_uuid: alphabetical ascending
 * - completed_at: newest first (descending)
 * - sop_version: descending
 *
 * Returns a new sorted array (does not mutate input).
 */
export function sortRecords(
  records: TrainingRecord[],
  key: RecordSortKey
): TrainingRecord[] {
  return [...records].sort((a, b) => {
    switch (key) {
      case "sop_document_uuid":
        return a.sop_document_uuid.localeCompare(b.sop_document_uuid);
      case "completed_at":
        return b.completed_at.localeCompare(a.completed_at);
      case "sop_version":
        return b.sop_version.localeCompare(a.sop_version);
    }
  });
}

// ---------------------------------------------------------------------------
// Property 11: Records grouping
// Validates: Requirements 5.6
// ---------------------------------------------------------------------------

/**
 * Group training records by sop_document_uuid.
 *
 * Every record within a group has the same sop_document_uuid.
 * No two groups share the same sop_document_uuid.
 * The union of all groups equals the original array.
 */
export function groupRecordsBySop(
  records: TrainingRecord[]
): Record<string, TrainingRecord[]> {
  const groups: Record<string, TrainingRecord[]> = {};
  for (const record of records) {
    if (!groups[record.sop_document_uuid]) {
      groups[record.sop_document_uuid] = [];
    }
    groups[record.sop_document_uuid].push(record);
  }
  return groups;
}

// ---------------------------------------------------------------------------
// Property 12: SOP selector uniqueness
// Validates: Requirements 6.7
// ---------------------------------------------------------------------------

/**
 * Derive unique (sop_document_uuid, sop_version) pairs from tasks.
 * No duplicates in the output, and every unique pair in the input appears.
 */
export function deriveUniqueSopPairs(tasks: TrainingTask[]): SopVersionPair[] {
  const seen = new Set<string>();
  const pairs: SopVersionPair[] = [];

  for (const task of tasks) {
    const key = `${task.sop_document_uuid}_${task.sop_version}`;
    if (!seen.has(key)) {
      seen.add(key);
      pairs.push({
        sop_document_uuid: task.sop_document_uuid,
        sop_version: task.sop_version,
      });
    }
  }

  return pairs;
}

// ---------------------------------------------------------------------------
// Property 13: Gate enforcement scope
// Validates: Requirements 8.1, 8.7
// ---------------------------------------------------------------------------

/**
 * Determine whether the training gate should be enforced for a given SOP status.
 * The gate is enforced only when the status is "InTraining".
 * All other statuses pass through without a training check.
 */
export function shouldEnforceGate(sopStatus: string): boolean {
  return sopStatus === "InTraining";
}

// ---------------------------------------------------------------------------
// Property 14: Gate check from tasks
// Validates: Requirements 8.4, 9.5
// ---------------------------------------------------------------------------

/**
 * Check whether a user has completed training for a specific SOP version
 * by examining the local tasks array.
 *
 * Returns true if there is at least one task where sop_document_uuid matches
 * AND sop_version matches AND is_completed is true.
 */
export function checkGateFromTasks(
  tasks: TrainingTask[],
  sopDocumentUuid: string,
  sopVersion: string
): boolean {
  return tasks.some(
    (t) =>
      t.sop_document_uuid === sopDocumentUuid &&
      t.sop_version === sopVersion &&
      t.is_completed
  );
}

// ---------------------------------------------------------------------------
// Property 15: Gate cache invalidation (helper)
// Validates: Requirements 9.4
// ---------------------------------------------------------------------------

/**
 * Build a gate cache key from sop_document_uuid and sop_version.
 */
export function buildGateCacheKey(
  sopDocumentUuid: string,
  sopVersion: string
): string {
  return `${sopDocumentUuid}_${sopVersion}`;
}

/**
 * Invalidate a specific entry in the gate cache.
 * Returns a new cache object with the specified key removed.
 * All other entries remain unchanged.
 */
export function invalidateGateCacheEntry(
  cache: GateCache,
  sopDocumentUuid: string,
  sopVersion: string
): GateCache {
  const key = buildGateCacheKey(sopDocumentUuid, sopVersion);
  const newCache = { ...cache };
  delete newCache[key];
  return newCache;
}

// ---------------------------------------------------------------------------
// Property 16: Error message extraction
// Validates: Requirements 9.7
// ---------------------------------------------------------------------------

/**
 * Extract a user-friendly error message from an API error.
 *
 * Strategy:
 * 1. If error has a `body` property, try to parse it as JSON and return `detail` field
 * 2. If `detail` is absent in parsed JSON, return `message` field from JSON
 * 3. If JSON parsing fails, return the raw body string
 * 4. If body is empty/absent, return the Error's message property
 * 5. Final fallback: "An unexpected error occurred"
 */
export function extractErrorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const err = error as Record<string, unknown>;

    // Try body-based extraction (ApiError pattern)
    if (typeof err.body === "string" && err.body.length > 0) {
      try {
        const parsed = JSON.parse(err.body);
        if (typeof parsed.detail === "string") {
          return parsed.detail;
        }
        if (typeof parsed.message === "string") {
          return parsed.message;
        }
      } catch {
        // JSON parse failed, return raw body
        return err.body;
      }
    }

    // Fallback to message property
    if (typeof err.message === "string" && err.message.length > 0) {
      return err.message;
    }
  }

  // Handle plain Error instances
  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred";
}

// ---------------------------------------------------------------------------
// Property 18: Aria-label format
// Validates: Requirements 11.3
// ---------------------------------------------------------------------------

/**
 * Format an aria-label for a training task card.
 * Format: "{task_title} - {status}" where status is "Pending" or "Completed".
 */
export function formatAriaLabel(task: TrainingTask): string {
  const status = task.is_completed ? "Completed" : "Pending";
  return `${task.task_title} - ${status}`;
}
