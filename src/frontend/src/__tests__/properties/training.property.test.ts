import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { computeStatistics, truncateTitle, filterTasks, sortTasks, validateInputLength, deriveContentId, shouldRenderSection, shuffleAnswerOptions, determineRecordValidity, sortRecords, groupRecordsBySop, deriveUniqueSopPairs, shouldEnforceGate, checkGateFromTasks, invalidateGateCacheEntry, buildGateCacheKey, extractErrorMessage, formatAriaLabel } from "../../components/training/utils";
import type { TrainingRecord, RecordSortKey, SopVersionPair } from "../../components/training/utils";
import type { TrainingTask, QuizQuestion, GateCache } from "../../components/training/types";

// ---------------------------------------------------------------------------
// Arbitrary generators for training domain types
// ---------------------------------------------------------------------------

/**
 * Generator for a valid TrainingTask object.
 */
const arbTrainingTask: fc.Arbitrary<TrainingTask> = fc.record({
  id: fc.integer({ min: 1, max: 100000 }),
  sop_document_uuid: fc.uuid(),
  sop_version: fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
  assigned_user_id: fc.integer({ min: 1, max: 10000 }),
  task_title: fc.string({ minLength: 1, maxLength: 200 }),
  is_completed: fc.boolean(),
  completed_at: fc.oneof(
    fc.constant(null),
    fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString())
  ),
  created_at: fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString()),
});

// ---------------------------------------------------------------------------
// Property 1: Statistics computation is correct
// Validates: Requirements 1.1, 1.5
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 1: Statistics computation is correct", () => {
  /**
   * **Validates: Requirements 1.1, 1.5**
   *
   * For any array of TrainingTask objects, pending + completed === total.
   */
  it("pending + completed === total", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const stats = computeStatistics(tasks);
          expect(stats.pending + stats.completed).toBe(stats.total);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 1.1, 1.5**
   *
   * For any array of TrainingTask objects, total === input array length.
   */
  it("total === input array length", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const stats = computeStatistics(tasks);
          expect(stats.total).toBe(tasks.length);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 1.1, 1.5**
   *
   * When total is 0, completionPercentage is null.
   */
  it("completionPercentage is null when total is 0", () => {
    const stats = computeStatistics([]);
    expect(stats.completionPercentage).toBeNull();
  });

  /**
   * **Validates: Requirements 1.1, 1.5**
   *
   * For any non-empty array of TrainingTask objects,
   * completionPercentage === Math.round(completed / total * 100).
   */
  it("completionPercentage is Math.round(completed/total * 100) when total > 0", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 1, maxLength: 50 }),
        (tasks) => {
          const stats = computeStatistics(tasks);
          const expected = Math.round((stats.completed / stats.total) * 100);
          expect(stats.completionPercentage).toBe(expected);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 1.1, 1.5**
   *
   * pending === count of tasks where is_completed is false.
   */
  it("pending === count of tasks where is_completed is false", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const stats = computeStatistics(tasks);
          const expectedPending = tasks.filter((t) => !t.is_completed).length;
          expect(stats.pending).toBe(expectedPending);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 1.1, 1.5**
   *
   * completed === count of tasks where is_completed is true.
   */
  it("completed === count of tasks where is_completed is true", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const stats = computeStatistics(tasks);
          const expectedCompleted = tasks.filter((t) => t.is_completed).length;
          expect(stats.completed).toBe(expectedCompleted);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Title truncation preserves content within bounds
// Validates: Requirements 2.1
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 2: Title truncation preserves content within bounds", () => {
  /**
   * **Validates: Requirements 2.1**
   *
   * Output length is always <= maxLength + 1 (accounting for ellipsis character).
   */
  it("output length is always <= maxLength + 1", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 300 }),
        fc.integer({ min: 1, max: 200 }),
        (title, maxLength) => {
          const result = truncateTitle(title, maxLength);
          expect(result.length).toBeLessThanOrEqual(maxLength + 1);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.1**
   *
   * When input length <= maxLength, output === input (unchanged).
   */
  it("when input length <= maxLength, output === input", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 300 }),
        fc.integer({ min: 1, max: 200 }),
        (title, maxLength) => {
          fc.pre(title.length <= maxLength);
          const result = truncateTitle(title, maxLength);
          expect(result).toBe(title);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.1**
   *
   * When input length > maxLength, output ends with "\u2026" (ellipsis).
   */
  it("when input length > maxLength, output ends with ellipsis", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 2, maxLength: 300 }),
        fc.integer({ min: 1, max: 200 }),
        (title, maxLength) => {
          fc.pre(title.length > maxLength);
          const result = truncateTitle(title, maxLength);
          expect(result.endsWith("\u2026")).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.1**
   *
   * When input length > maxLength, output length === maxLength + 1.
   */
  it("when input length > maxLength, output length === maxLength + 1", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 2, maxLength: 300 }),
        fc.integer({ min: 1, max: 200 }),
        (title, maxLength) => {
          fc.pre(title.length > maxLength);
          const result = truncateTitle(title, maxLength);
          expect(result.length).toBe(maxLength + 1);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.1**
   *
   * The non-ellipsis prefix of a truncated result equals the first maxLength chars of input.
   */
  it("truncated prefix equals first maxLength chars of input", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 2, maxLength: 300 }),
        fc.integer({ min: 1, max: 200 }),
        (title, maxLength) => {
          fc.pre(title.length > maxLength);
          const result = truncateTitle(title, maxLength);
          const prefix = result.slice(0, -1); // Remove the trailing ellipsis
          expect(prefix).toBe(title.slice(0, maxLength));
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 3: Client-side filtering returns correct subset
// Validates: Requirements 2.3, 5.2
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 3: Client-side filtering returns correct subset", () => {
  /**
   * **Validates: Requirements 2.3, 5.2**
   *
   * filter "all" returns the same array (same length, same elements).
   */
  it("filter 'all' returns the same array", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const result = filterTasks(tasks, "all");
          expect(result.length).toBe(tasks.length);
          expect(result).toEqual(tasks);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.3, 5.2**
   *
   * filter "pending" returns only tasks where is_completed is false.
   */
  it("filter 'pending' returns only tasks where is_completed is false", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const result = filterTasks(tasks, "pending");
          for (const task of result) {
            expect(task.is_completed).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.3, 5.2**
   *
   * filter "completed" returns only tasks where is_completed is true.
   */
  it("filter 'completed' returns only tasks where is_completed is true", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const result = filterTasks(tasks, "completed");
          for (const task of result) {
            expect(task.is_completed).toBe(true);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.3, 5.2**
   *
   * Filtered result is always a subset of the input (every element in output exists in input).
   */
  it("filtered result is always a subset of the input", () => {
    const arbFilter = fc.constantFrom<"all" | "pending" | "completed">("all", "pending", "completed");

    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        arbFilter,
        (tasks, filter) => {
          const result = filterTasks(tasks, filter);
          for (const task of result) {
            expect(tasks).toContain(task);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.3, 5.2**
   *
   * pending count + completed count === total count (partition property).
   */
  it("pending count + completed count === total count", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const pendingResult = filterTasks(tasks, "pending");
          const completedResult = filterTasks(tasks, "completed");
          expect(pendingResult.length + completedResult.length).toBe(tasks.length);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4: Task sorting maintains ordering invariants
// Validates: Requirements 2.4
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 4: Task sorting maintains ordering invariants", () => {
  /**
   * Generator for a pending TrainingTask with a valid created_at timestamp.
   */
  const arbPendingTask: fc.Arbitrary<TrainingTask> = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    sop_document_uuid: fc.uuid(),
    sop_version: fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
    assigned_user_id: fc.integer({ min: 1, max: 10000 }),
    task_title: fc.string({ minLength: 1, maxLength: 200 }),
    is_completed: fc.constant(false),
    completed_at: fc.constant(null),
    created_at: fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString()),
  });

  /**
   * Generator for a completed TrainingTask with valid created_at and completed_at timestamps.
   */
  const arbCompletedTask: fc.Arbitrary<TrainingTask> = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    sop_document_uuid: fc.uuid(),
    sop_version: fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
    assigned_user_id: fc.integer({ min: 1, max: 10000 }),
    task_title: fc.string({ minLength: 1, maxLength: 200 }),
    is_completed: fc.constant(true),
    completed_at: fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString()),
    created_at: fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString()),
  });

  /**
   * **Validates: Requirements 2.4**
   *
   * All pending tasks appear before all completed tasks in the sorted result.
   */
  it("all pending tasks appear before all completed tasks", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const sorted = sortTasks(tasks);
          const firstCompletedIndex = sorted.findIndex((t) => t.is_completed);
          if (firstCompletedIndex === -1) {
            // No completed tasks — all are pending, which is fine
            return;
          }
          // Every task after the first completed task must also be completed
          for (let i = firstCompletedIndex; i < sorted.length; i++) {
            expect(sorted[i].is_completed).toBe(true);
          }
          // Every task before the first completed task must be pending
          for (let i = 0; i < firstCompletedIndex; i++) {
            expect(sorted[i].is_completed).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.4**
   *
   * Among pending tasks, they are sorted by created_at ascending (earlier dates first).
   */
  it("pending tasks are sorted by created_at ascending", () => {
    fc.assert(
      fc.property(
        fc.array(arbPendingTask, { minLength: 2, maxLength: 50 }),
        (tasks) => {
          const sorted = sortTasks(tasks);
          const pendingTasks = sorted.filter((t) => !t.is_completed);
          for (let i = 0; i < pendingTasks.length - 1; i++) {
            expect(pendingTasks[i].created_at.localeCompare(pendingTasks[i + 1].created_at)).toBeLessThanOrEqual(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.4**
   *
   * Among completed tasks, they are sorted by completed_at descending (most recent first).
   */
  it("completed tasks are sorted by completed_at descending", () => {
    fc.assert(
      fc.property(
        fc.array(arbCompletedTask, { minLength: 2, maxLength: 50 }),
        (tasks) => {
          const sorted = sortTasks(tasks);
          const completedTasks = sorted.filter((t) => t.is_completed);
          for (let i = 0; i < completedTasks.length - 1; i++) {
            const a = completedTasks[i].completed_at ?? "";
            const b = completedTasks[i + 1].completed_at ?? "";
            expect(b.localeCompare(a)).toBeLessThanOrEqual(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.4**
   *
   * The output has the same length as the input (no elements lost or added).
   */
  it("output has the same length as the input", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const sorted = sortTasks(tasks);
          expect(sorted.length).toBe(tasks.length);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 2.4**
   *
   * The output is a permutation of the input (same elements, different order).
   */
  it("output is a permutation of the input", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const sorted = sortTasks(tasks);
          // Every element in sorted exists in tasks (by reference)
          for (const task of sorted) {
            expect(tasks).toContain(task);
          }
          // Every element in tasks exists in sorted (by reference)
          for (const task of tasks) {
            expect(sorted).toContain(task);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 5: Bounded-length input validation
// Validates: Requirements 3.2, 7.4
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 5: Bounded-length input validation", () => {
  /**
   * **Validates: Requirements 3.2, 7.4**
   *
   * For any string whose trimmed length is within [minLength, maxLength],
   * validateInputLength returns true.
   */
  it("returns true when trimmed input length is within [minLength, maxLength]", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 50 }),
        fc.integer({ min: 0, max: 100 }),
        (minLength, extraRange) => {
          const maxLength = minLength + extraRange;
          // Generate a string whose trimmed length is within bounds
          const targetLength = minLength + Math.floor(Math.random() * (extraRange + 1));
          const content = "a".repeat(targetLength);
          expect(validateInputLength(content, minLength, maxLength)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.2, 7.4**
   *
   * For any string whose trimmed length is less than minLength,
   * validateInputLength returns false.
   */
  it("returns false when trimmed input length is less than minLength", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 100 }),
        fc.integer({ min: 0, max: 200 }),
        (minLength, maxLength) => {
          fc.pre(maxLength >= minLength);
          // Generate a string shorter than minLength
          const shortLength = Math.max(0, minLength - 1 - Math.floor(Math.random() * minLength));
          const content = "b".repeat(shortLength);
          fc.pre(content.trim().length < minLength);
          expect(validateInputLength(content, minLength, maxLength)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.2, 7.4**
   *
   * For any string whose trimmed length exceeds maxLength,
   * validateInputLength returns false.
   */
  it("returns false when trimmed input length exceeds maxLength", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 50 }),
        fc.integer({ min: 0, max: 100 }),
        fc.integer({ min: 1, max: 50 }),
        (minLength, maxLength, excess) => {
          fc.pre(maxLength >= minLength);
          const content = "c".repeat(maxLength + excess);
          expect(validateInputLength(content, minLength, maxLength)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.2, 7.4**
   *
   * Leading/trailing whitespace is ignored (trimmed before validation).
   * A string with whitespace padding that has valid trimmed length returns true.
   */
  it("leading/trailing whitespace is ignored (trimmed before validation)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 50 }),
        fc.integer({ min: 0, max: 50 }),
        fc.integer({ min: 1, max: 20 }),
        fc.integer({ min: 1, max: 20 }),
        (minLength, extraRange, leadingSpaces, trailingSpaces) => {
          const maxLength = minLength + extraRange;
          const content = "x".repeat(minLength);
          const padded = " ".repeat(leadingSpaces) + content + " ".repeat(trailingSpaces);
          // The trimmed length equals minLength, which is within [minLength, maxLength]
          expect(validateInputLength(padded, minLength, maxLength)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.2, 7.4**
   *
   * Empty string (after trim) returns false when minLength > 0.
   */
  it("empty string (after trim) returns false when minLength > 0", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 500 }),
        fc.integer({ min: 0, max: 500 }),
        fc.constantFrom("", "   ", "\t", "\n", "  \t\n  "),
        (minLength, extraRange, whitespaceOnly) => {
          const maxLength = minLength + extraRange;
          expect(validateInputLength(whitespaceOnly, minLength, maxLength)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 6: Content ID derivation is deterministic
// Validates: Requirements 4.1
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 6: Content ID derivation is deterministic", () => {
  /**
   * **Validates: Requirements 4.1**
   *
   * Output format is always "{uuid}_v{version}".
   */
  it("output format is always '{uuid}_v{version}'", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.stringMatching(/^[0-9]+(\.[0-9]+)*$/),
        (uuid, version) => {
          const result = deriveContentId(uuid, version);
          expect(result).toBe(`${uuid}_v${version}`);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.1**
   *
   * Same inputs always produce the same output (deterministic).
   */
  it("same inputs always produce the same output (deterministic)", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.stringMatching(/^[0-9]+(\.[0-9]+)*$/),
        (uuid, version) => {
          const result1 = deriveContentId(uuid, version);
          const result2 = deriveContentId(uuid, version);
          expect(result1).toBe(result2);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.1**
   *
   * Different inputs produce different outputs (no collisions for distinct uuid/version pairs).
   */
  it("different inputs produce different outputs", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.stringMatching(/^[0-9]+(\.[0-9]+)*$/),
        fc.uuid(),
        fc.stringMatching(/^[0-9]+(\.[0-9]+)*$/),
        (uuid1, version1, uuid2, version2) => {
          fc.pre(uuid1 !== uuid2 || version1 !== version2);
          const result1 = deriveContentId(uuid1, version1);
          const result2 = deriveContentId(uuid2, version2);
          expect(result1).not.toBe(result2);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.1**
   *
   * Output contains the input uuid and version as substrings.
   */
  it("output contains the input uuid and version as substrings", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.stringMatching(/^[0-9]+(\.[0-9]+)*$/),
        (uuid, version) => {
          const result = deriveContentId(uuid, version);
          expect(result).toContain(uuid);
          expect(result).toContain(version);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 7: Content sections render only when non-empty
// Validates: Requirements 4.2
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 7: Content sections render only when non-empty", () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * shouldRenderSection returns false for empty arrays.
   */
  it("returns false for empty arrays", () => {
    expect(shouldRenderSection([])).toBe(false);
  });

  /**
   * **Validates: Requirements 4.2**
   *
   * shouldRenderSection returns true for any non-empty array.
   */
  it("returns true for non-empty arrays", () => {
    fc.assert(
      fc.property(
        fc.array(fc.anything(), { minLength: 1, maxLength: 50 }),
        (data) => {
          expect(shouldRenderSection(data)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.2**
   *
   * Result is equivalent to checking array.length > 0 for any array.
   */
  it("result is equivalent to array.length > 0", () => {
    fc.assert(
      fc.property(
        fc.array(fc.anything(), { minLength: 0, maxLength: 50 }),
        (data) => {
          expect(shouldRenderSection(data)).toBe(data.length > 0);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Property 8: Quiz answer options preserve the complete answer set
// Validates: Requirements 4.4
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 8: Quiz answer options preserve the complete answer set", () => {
  /**
   * Generator for a valid QuizQuestion object with unique answer options.
   */
  const arbQuizQuestion: fc.Arbitrary<QuizQuestion> = fc
    .record({
      question_id: fc.uuid(),
      question: fc.string({ minLength: 1, maxLength: 200 }),
      correct_answer: fc.string({ minLength: 1, maxLength: 100 }),
      distractors: fc.array(fc.string({ minLength: 1, maxLength: 100 }), {
        minLength: 1,
        maxLength: 5,
      }),
      sop_section_ref: fc.string({ minLength: 1, maxLength: 50 }),
    })
    .filter((q) => {
      // Ensure correct_answer is not in distractors for cleaner tests
      return !q.distractors.includes(q.correct_answer);
    });

  /**
   * **Validates: Requirements 4.4**
   *
   * Output contains exactly the same elements as [correct_answer, ...distractors] (same multiset).
   */
  it("output contains exactly the same elements as [correct_answer, ...distractors]", () => {
    fc.assert(
      fc.property(arbQuizQuestion, (question) => {
        const result = shuffleAnswerOptions(question);
        const expected = [question.correct_answer, ...question.distractors];
        expect([...result].sort()).toEqual([...expected].sort());
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.4**
   *
   * Output length equals 1 + distractors.length.
   */
  it("output length equals 1 + distractors.length", () => {
    fc.assert(
      fc.property(arbQuizQuestion, (question) => {
        const result = shuffleAnswerOptions(question);
        expect(result.length).toBe(1 + question.distractors.length);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.4**
   *
   * The correct_answer is always present in the output.
   */
  it("the correct_answer is always present in the output", () => {
    fc.assert(
      fc.property(arbQuizQuestion, (question) => {
        const result = shuffleAnswerOptions(question);
        expect(result).toContain(question.correct_answer);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.4**
   *
   * All distractors are present in the output.
   */
  it("all distractors are present in the output", () => {
    fc.assert(
      fc.property(arbQuizQuestion, (question) => {
        const result = shuffleAnswerOptions(question);
        for (const distractor of question.distractors) {
          expect(result).toContain(distractor);
        }
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.4**
   *
   * No new elements are introduced (output is a subset of the original set).
   */
  it("no new elements are introduced (output is a subset of the original set)", () => {
    fc.assert(
      fc.property(arbQuizQuestion, (question) => {
        const result = shuffleAnswerOptions(question);
        const originalSet = new Set([question.correct_answer, ...question.distractors]);
        for (const option of result) {
          expect(originalSet.has(option)).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Property 9: Training record validity determination
// Validates: Requirements 5.3
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 9: Training record validity determination", () => {
  /**
   * Generator for a non-completed (pending) TrainingTask.
   */
  const arbPendingTask: fc.Arbitrary<TrainingTask> = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    sop_document_uuid: fc.uuid(),
    sop_version: fc
      .array(
        fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."),
        { minLength: 1, maxLength: 10 }
      )
      .map((chars) => chars.join("")),
    assigned_user_id: fc.integer({ min: 1, max: 10000 }),
    task_title: fc.string({ minLength: 1, maxLength: 200 }),
    is_completed: fc.constant(false),
    completed_at: fc.constant(null),
    created_at: fc
      .integer({ min: 946684800000, max: 1924905600000 })
      .map((ts) => new Date(ts).toISOString()),
  });

  /**
   * **Validates: Requirements 5.3**
   *
   * Only completed tasks appear in the output validity map.
   * Non-completed tasks never have entries in the map.
   */
  it("only completed tasks appear in the output validity map", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const validityMap = determineRecordValidity(tasks);
          const completedIds = new Set(
            tasks.filter((t) => t.is_completed).map((t) => t.id)
          );
          // Every key in the map must be a completed task's ID
          for (const idStr of Object.keys(validityMap)) {
            expect(completedIds.has(Number(idStr))).toBe(true);
          }
          // Every completed task must have an entry in the map
          for (const id of completedIds) {
            expect(id in validityMap).toBe(true);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.3**
   *
   * Non-completed tasks never appear in the validity map.
   */
  it("non-completed tasks never appear in the validity map", () => {
    fc.assert(
      fc.property(
        fc.array(arbPendingTask, { minLength: 1, maxLength: 20 }),
        (pendingTasks) => {
          const validityMap = determineRecordValidity(pendingTasks);
          expect(Object.keys(validityMap).length).toBe(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.3**
   *
   * For each sop_document_uuid group, exactly the task(s) with the highest
   * version (lexicographically) are marked valid (true).
   */
  it("tasks with the highest version in each SOP group are marked valid", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(
          fc.constantFrom("1.0", "1.1", "2.0", "2.1", "3.0"),
          { minLength: 2, maxLength: 5 }
        ),
        fc.array(fc.integer({ min: 1, max: 100000 }), {
          minLength: 5,
          maxLength: 5,
        }),
        (sopUuid, versions, ids) => {
          // Ensure unique IDs
          const uniqueIds = [...new Set(ids)];
          fc.pre(uniqueIds.length >= versions.length);

          const tasks: TrainingTask[] = versions.map((version, i) => ({
            id: uniqueIds[i],
            sop_document_uuid: sopUuid,
            sop_version: version,
            assigned_user_id: 1,
            task_title: `Task ${i}`,
            is_completed: true,
            completed_at: new Date().toISOString(),
            created_at: new Date().toISOString(),
          }));

          const validityMap = determineRecordValidity(tasks);

          // Find the highest version lexicographically
          const highestVersion = versions.reduce((max, v) =>
            v.localeCompare(max) > 0 ? v : max
          );

          // Tasks with highest version should be valid
          for (const task of tasks) {
            if (task.sop_version === highestVersion) {
              expect(validityMap[task.id]).toBe(true);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.3**
   *
   * Tasks with lower versions in the same SOP group are marked invalid (false).
   */
  it("tasks with lower versions in the same SOP group are marked invalid", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(
          fc.constantFrom("1.0", "1.1", "2.0", "2.1", "3.0"),
          { minLength: 2, maxLength: 5 }
        ),
        fc.array(fc.integer({ min: 1, max: 100000 }), {
          minLength: 5,
          maxLength: 5,
        }),
        (sopUuid, versions, ids) => {
          // Ensure unique IDs
          const uniqueIds = [...new Set(ids)];
          fc.pre(uniqueIds.length >= versions.length);
          // Ensure at least two distinct versions
          const distinctVersions = new Set(versions);
          fc.pre(distinctVersions.size >= 2);

          const tasks: TrainingTask[] = versions.map((version, i) => ({
            id: uniqueIds[i],
            sop_document_uuid: sopUuid,
            sop_version: version,
            assigned_user_id: 1,
            task_title: `Task ${i}`,
            is_completed: true,
            completed_at: new Date().toISOString(),
            created_at: new Date().toISOString(),
          }));

          const validityMap = determineRecordValidity(tasks);

          // Find the highest version lexicographically
          const highestVersion = versions.reduce((max, v) =>
            v.localeCompare(max) > 0 ? v : max
          );

          // Tasks with lower versions should be invalid
          for (const task of tasks) {
            if (task.sop_version !== highestVersion) {
              expect(validityMap[task.id]).toBe(false);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.3**
   *
   * A single completed task for a given SOP is always valid.
   */
  it("a single completed task for a given SOP is always valid", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.stringMatching(/^[0-9]+(\.[0-9]+)*$/),
        fc.integer({ min: 1, max: 100000 }),
        (sopUuid, version, taskId) => {
          const tasks: TrainingTask[] = [
            {
              id: taskId,
              sop_document_uuid: sopUuid,
              sop_version: version,
              assigned_user_id: 1,
              task_title: "Single task",
              is_completed: true,
              completed_at: new Date().toISOString(),
              created_at: new Date().toISOString(),
            },
          ];

          const validityMap = determineRecordValidity(tasks);
          expect(validityMap[taskId]).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.3**
   *
   * Mixed completed and non-completed tasks: only completed tasks appear in the map,
   * and validity is determined correctly within the completed subset.
   */
  it("mixed tasks: validity determined only from completed tasks", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.integer({ min: 1, max: 50000 }),
        fc.integer({ min: 50001, max: 100000 }),
        fc.integer({ min: 100001, max: 150000 }),
        (sopUuid, id1, id2, id3) => {
          const tasks: TrainingTask[] = [
            {
              id: id1,
              sop_document_uuid: sopUuid,
              sop_version: "1.0",
              assigned_user_id: 1,
              task_title: "Completed old",
              is_completed: true,
              completed_at: new Date().toISOString(),
              created_at: new Date().toISOString(),
            },
            {
              id: id2,
              sop_document_uuid: sopUuid,
              sop_version: "2.0",
              assigned_user_id: 1,
              task_title: "Completed new",
              is_completed: true,
              completed_at: new Date().toISOString(),
              created_at: new Date().toISOString(),
            },
            {
              id: id3,
              sop_document_uuid: sopUuid,
              sop_version: "3.0",
              assigned_user_id: 1,
              task_title: "Pending newest",
              is_completed: false,
              completed_at: null,
              created_at: new Date().toISOString(),
            },
          ];

          const validityMap = determineRecordValidity(tasks);

          // Pending task (id3) should NOT be in the map
          expect(id3 in validityMap).toBe(false);

          // Among completed tasks, version "2.0" > "1.0" lexicographically
          expect(validityMap[id1]).toBe(false); // lower version
          expect(validityMap[id2]).toBe(true); // highest completed version
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 10: Records sorting maintains order for each sort key
// Validates: Requirements 5.4
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 10: Records sorting maintains order for each sort key", () => {
  /**
   * Generator for a valid TrainingRecord object.
   */
  const arbTrainingRecord: fc.Arbitrary<TrainingRecord> = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    sop_document_uuid: fc.uuid(),
    sop_version: fc
      .array(
        fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."),
        { minLength: 1, maxLength: 10 }
      )
      .map((chars) => chars.join("")),
    completed_at: fc
      .integer({ min: 946684800000, max: 1924905600000 })
      .map((ts) => new Date(ts).toISOString()),
    is_valid: fc.boolean(),
  });

  /**
   * **Validates: Requirements 5.4**
   *
   * When sorting by "sop_document_uuid", records are in alphabetical ascending order.
   */
  it("sorting by sop_document_uuid produces alphabetical ascending order", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 2, maxLength: 50 }),
        (records) => {
          const sorted = sortRecords(records, "sop_document_uuid");
          for (let i = 0; i < sorted.length - 1; i++) {
            expect(
              sorted[i].sop_document_uuid.localeCompare(sorted[i + 1].sop_document_uuid)
            ).toBeLessThanOrEqual(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.4**
   *
   * When sorting by "completed_at", records are in descending order (newest first).
   */
  it("sorting by completed_at produces descending order (newest first)", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 2, maxLength: 50 }),
        (records) => {
          const sorted = sortRecords(records, "completed_at");
          for (let i = 0; i < sorted.length - 1; i++) {
            expect(
              sorted[i].completed_at.localeCompare(sorted[i + 1].completed_at)
            ).toBeGreaterThanOrEqual(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.4**
   *
   * When sorting by "sop_version", records are in descending order.
   */
  it("sorting by sop_version produces descending order", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 2, maxLength: 50 }),
        (records) => {
          const sorted = sortRecords(records, "sop_version");
          for (let i = 0; i < sorted.length - 1; i++) {
            expect(
              sorted[i].sop_version.localeCompare(sorted[i + 1].sop_version)
            ).toBeGreaterThanOrEqual(0);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.4**
   *
   * Output has the same length as input (no elements lost).
   */
  it("output has the same length as input", () => {
    const arbSortKey: fc.Arbitrary<RecordSortKey> = fc.constantFrom(
      "sop_document_uuid",
      "completed_at",
      "sop_version"
    );

    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 0, maxLength: 50 }),
        arbSortKey,
        (records, key) => {
          const sorted = sortRecords(records, key);
          expect(sorted.length).toBe(records.length);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.4**
   *
   * Output is a permutation of the input (same elements).
   */
  it("output is a permutation of the input", () => {
    const arbSortKey: fc.Arbitrary<RecordSortKey> = fc.constantFrom(
      "sop_document_uuid",
      "completed_at",
      "sop_version"
    );

    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 0, maxLength: 50 }),
        arbSortKey,
        (records, key) => {
          const sorted = sortRecords(records, key);
          // Every element in sorted exists in records (by reference)
          for (const record of sorted) {
            expect(records).toContain(record);
          }
          // Every element in records exists in sorted (by reference)
          for (const record of records) {
            expect(sorted).toContain(record);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 11: Records grouping produces correct partitions
// Validates: Requirements 5.6
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 11: Records grouping produces correct partitions", () => {
  /**
   * Generator for a valid TrainingRecord object.
   */
  const arbTrainingRecord: fc.Arbitrary<TrainingRecord> = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    sop_document_uuid: fc.uuid(),
    sop_version: fc
      .array(
        fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."),
        { minLength: 1, maxLength: 10 }
      )
      .map((chars) => chars.join("")),
    completed_at: fc
      .integer({ min: 946684800000, max: 1924905600000 })
      .map((ts) => new Date(ts).toISOString()),
    is_valid: fc.boolean(),
  });

  /**
   * **Validates: Requirements 5.6**
   *
   * Every record within a group has the same sop_document_uuid.
   */
  it("every record within a group has the same sop_document_uuid", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 0, maxLength: 50 }),
        (records) => {
          const groups = groupRecordsBySop(records);
          for (const [sopUuid, groupRecords] of Object.entries(groups)) {
            for (const record of groupRecords) {
              expect(record.sop_document_uuid).toBe(sopUuid);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.6**
   *
   * No two groups share the same sop_document_uuid (keys are unique).
   * This is inherent in the Record<string, ...> type, but we verify
   * that the number of keys equals the number of distinct sop_document_uuids.
   */
  it("no two groups share the same sop_document_uuid (keys are unique)", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 0, maxLength: 50 }),
        (records) => {
          const groups = groupRecordsBySop(records);
          const keys = Object.keys(groups);
          const uniqueKeys = new Set(keys);
          expect(keys.length).toBe(uniqueKeys.size);

          // Also verify the keys match the distinct sop_document_uuids in input
          const distinctUuids = new Set(records.map((r) => r.sop_document_uuid));
          expect(keys.length).toBe(distinctUuids.size);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.6**
   *
   * The union of all groups equals the original array (no records lost).
   */
  it("the union of all groups equals the original array (no records lost)", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 0, maxLength: 50 }),
        (records) => {
          const groups = groupRecordsBySop(records);
          const allGroupedRecords: TrainingRecord[] = [];
          for (const groupRecords of Object.values(groups)) {
            allGroupedRecords.push(...groupRecords);
          }
          // Same length
          expect(allGroupedRecords.length).toBe(records.length);
          // Every record in the input appears in the grouped output
          for (const record of records) {
            expect(allGroupedRecords).toContain(record);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.6**
   *
   * The total count of records across all groups equals the input length.
   */
  it("total count of records across all groups equals the input length", () => {
    fc.assert(
      fc.property(
        fc.array(arbTrainingRecord, { minLength: 0, maxLength: 50 }),
        (records) => {
          const groups = groupRecordsBySop(records);
          let totalCount = 0;
          for (const groupRecords of Object.values(groups)) {
            totalCount += groupRecords.length;
          }
          expect(totalCount).toBe(records.length);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 5.6**
   *
   * Empty input produces empty output.
   */
  it("empty input produces empty output", () => {
    const groups = groupRecordsBySop([]);
    expect(Object.keys(groups).length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Property 12: SOP selector contains unique pairs
// Validates: Requirements 6.7
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 12: SOP selector contains unique pairs", () => {
  /**
   * Generator for a valid TrainingTask object (reused from above scope).
   */
  const arbTask: fc.Arbitrary<TrainingTask> = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    sop_document_uuid: fc.uuid(),
    sop_version: fc
      .array(
        fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."),
        { minLength: 1, maxLength: 10 }
      )
      .map((chars) => chars.join("")),
    assigned_user_id: fc.integer({ min: 1, max: 10000 }),
    task_title: fc.string({ minLength: 1, maxLength: 200 }),
    is_completed: fc.boolean(),
    completed_at: fc.oneof(
      fc.constant(null),
      fc
        .integer({ min: 946684800000, max: 1924905600000 })
        .map((ts) => new Date(ts).toISOString())
    ),
    created_at: fc
      .integer({ min: 946684800000, max: 1924905600000 })
      .map((ts) => new Date(ts).toISOString()),
  });

  /**
   * **Validates: Requirements 6.7**
   *
   * No duplicates in the output: each (sop_document_uuid, sop_version) pair appears at most once.
   */
  it("no duplicates in the output (each pair appears at most once)", () => {
    fc.assert(
      fc.property(
        fc.array(arbTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const pairs = deriveUniqueSopPairs(tasks);
          const keys = pairs.map(
            (p) => `${p.sop_document_uuid}_${p.sop_version}`
          );
          const uniqueKeys = new Set(keys);
          expect(keys.length).toBe(uniqueKeys.size);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 6.7**
   *
   * Every unique (sop_document_uuid, sop_version) pair from the input appears in the output.
   */
  it("every unique pair from the input appears in the output", () => {
    fc.assert(
      fc.property(
        fc.array(arbTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const pairs = deriveUniqueSopPairs(tasks);
          const outputKeys = new Set(
            pairs.map((p) => `${p.sop_document_uuid}_${p.sop_version}`)
          );
          // Every unique pair in the input must be in the output
          for (const task of tasks) {
            const key = `${task.sop_document_uuid}_${task.sop_version}`;
            expect(outputKeys.has(key)).toBe(true);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 6.7**
   *
   * Output length <= input length.
   */
  it("output length <= input length", () => {
    fc.assert(
      fc.property(
        fc.array(arbTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const pairs = deriveUniqueSopPairs(tasks);
          expect(pairs.length).toBeLessThanOrEqual(tasks.length);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 6.7**
   *
   * Output length equals the number of distinct (sop_document_uuid, sop_version) pairs in the input.
   */
  it("output length equals the number of distinct pairs in the input", () => {
    fc.assert(
      fc.property(
        fc.array(arbTask, { minLength: 0, maxLength: 50 }),
        (tasks) => {
          const pairs = deriveUniqueSopPairs(tasks);
          const distinctPairs = new Set(
            tasks.map((t) => `${t.sop_document_uuid}_${t.sop_version}`)
          );
          expect(pairs.length).toBe(distinctPairs.size);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 6.7**
   *
   * Empty input produces empty output.
   */
  it("empty input produces empty output", () => {
    const pairs = deriveUniqueSopPairs([]);
    expect(pairs.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Property 13: Training gate enforcement scope
// Validates: Requirements 8.1, 8.7
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 13: Training gate enforcement scope", () => {
  /**
   * **Validates: Requirements 8.1, 8.7**
   *
   * shouldEnforceGate returns true only when status is exactly "InTraining".
   */
  it("returns true only when status is exactly 'InTraining'", () => {
    expect(shouldEnforceGate("InTraining")).toBe(true);
  });

  /**
   * **Validates: Requirements 8.1, 8.7**
   *
   * shouldEnforceGate returns false for any status string that is not "InTraining".
   */
  it("returns false for any status string that is not 'InTraining'", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 100 }).filter((s) => s !== "InTraining"),
        (status) => {
          expect(shouldEnforceGate(status)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 8.1, 8.7**
   *
   * shouldEnforceGate returns false for empty string.
   */
  it("returns false for empty string", () => {
    expect(shouldEnforceGate("")).toBe(false);
  });

  /**
   * **Validates: Requirements 8.1, 8.7**
   *
   * shouldEnforceGate returns false for similar but different strings
   * (case variations, extra whitespace, underscores).
   */
  it("returns false for similar but different strings", () => {
    const similarStrings = [
      "intraining",
      "IN_TRAINING",
      "InTraining ",
      " InTraining",
      "inTraining",
      "INTRAINING",
      "In Training",
      "in_training",
      "In_Training",
      "intraining ",
    ];

    for (const status of similarStrings) {
      expect(shouldEnforceGate(status)).toBe(false);
    }
  });

  /**
   * **Validates: Requirements 8.1, 8.7**
   *
   * shouldEnforceGate returns false for common SOP statuses other than "InTraining".
   */
  it("returns false for common SOP statuses other than 'InTraining'", () => {
    const otherStatuses = ["Active", "Draft", "Retired", "Archived", "PendingReview", "Approved"];

    for (const status of otherStatuses) {
      expect(shouldEnforceGate(status)).toBe(false);
    }
  });

  /**
   * **Validates: Requirements 8.1, 8.7**
   *
   * For any arbitrary string, shouldEnforceGate returns a boolean
   * equivalent to strict equality with "InTraining".
   */
  it("result is equivalent to strict equality check with 'InTraining'", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 200 }),
        (status) => {
          expect(shouldEnforceGate(status)).toBe(status === "InTraining");
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Property 14: Training gate check with caching
// Validates: Requirements 8.4, 9.5
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 14: Training gate check with caching", () => {
  /**
   * **Validates: Requirements 8.4, 9.5**
   *
   * Returns true when there exists at least one completed task matching the uuid AND version.
   */
  it("returns true when there exists at least one completed task matching uuid AND version", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 20 }),
        fc.integer({ min: 1, max: 100000 }),
        (targetUuid, targetVersion, otherTasks, taskId) => {
          // Create a completed task that matches the target uuid and version
          const matchingTask: TrainingTask = {
            id: taskId,
            sop_document_uuid: targetUuid,
            sop_version: targetVersion,
            assigned_user_id: 1,
            task_title: "Matching completed task",
            is_completed: true,
            completed_at: new Date().toISOString(),
            created_at: new Date().toISOString(),
          };

          const tasks = [...otherTasks, matchingTask];
          expect(checkGateFromTasks(tasks, targetUuid, targetVersion)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 8.4, 9.5**
   *
   * Returns false when no completed task matches the uuid AND version.
   */
  it("returns false when no completed task matches the uuid AND version", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
        fc.array(arbTrainingTask, { minLength: 0, maxLength: 20 }),
        (targetUuid, targetVersion, tasks) => {
          // Filter out any tasks that happen to match both uuid AND version AND are completed
          const filteredTasks = tasks.filter(
            (t) => !(t.sop_document_uuid === targetUuid && t.sop_version === targetVersion && t.is_completed)
          );
          expect(checkGateFromTasks(filteredTasks, targetUuid, targetVersion)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 8.4, 9.5**
   *
   * Returns false for empty tasks array.
   */
  it("returns false for empty tasks array", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
        (uuid, version) => {
          expect(checkGateFromTasks([], uuid, version)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 8.4, 9.5**
   *
   * Returns false when uuid matches but version doesn't.
   */
  it("returns false when uuid matches but version doesn't", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
        fc.integer({ min: 1, max: 100000 }),
        (targetUuid, targetVersion, differentVersion, taskId) => {
          fc.pre(targetVersion !== differentVersion);

          const tasks: TrainingTask[] = [
            {
              id: taskId,
              sop_document_uuid: targetUuid,
              sop_version: differentVersion, // UUID matches, version doesn't
              assigned_user_id: 1,
              task_title: "Mismatched version task",
              is_completed: true,
              completed_at: new Date().toISOString(),
              created_at: new Date().toISOString(),
            },
          ];

          expect(checkGateFromTasks(tasks, targetUuid, targetVersion)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 8.4, 9.5**
   *
   * Returns false when version matches but uuid doesn't.
   */
  it("returns false when version matches but uuid doesn't", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
        fc.integer({ min: 1, max: 100000 }),
        (targetUuid, differentUuid, targetVersion, taskId) => {
          fc.pre(targetUuid !== differentUuid);

          const tasks: TrainingTask[] = [
            {
              id: taskId,
              sop_document_uuid: differentUuid, // Version matches, UUID doesn't
              sop_version: targetVersion,
              assigned_user_id: 1,
              task_title: "Mismatched uuid task",
              is_completed: true,
              completed_at: new Date().toISOString(),
              created_at: new Date().toISOString(),
            },
          ];

          expect(checkGateFromTasks(tasks, targetUuid, targetVersion)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 8.4, 9.5**
   *
   * Returns false when task matches uuid and version but is not completed.
   */
  it("returns false when task matches uuid and version but is not completed", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
        fc.integer({ min: 1, max: 100000 }),
        (targetUuid, targetVersion, taskId) => {
          const tasks: TrainingTask[] = [
            {
              id: taskId,
              sop_document_uuid: targetUuid,
              sop_version: targetVersion,
              assigned_user_id: 1,
              task_title: "Pending matching task",
              is_completed: false, // Not completed
              completed_at: null,
              created_at: new Date().toISOString(),
            },
          ];

          expect(checkGateFromTasks(tasks, targetUuid, targetVersion)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 15: Gate cache invalidation on task completion
// Validates: Requirements 9.4
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 15: Gate cache invalidation on task completion", () => {
  /**
   * Generator for a gate cache with random entries.
   */
  const arbGateCache: fc.Arbitrary<GateCache> = fc
    .array(
      fc.tuple(
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 5 }).map((chars) => chars.join("")),
        fc.boolean()
      ),
      { minLength: 0, maxLength: 10 }
    )
    .map((entries) => {
      const cache: GateCache = {};
      for (const [uuid, version, value] of entries) {
        cache[buildGateCacheKey(uuid, version)] = value;
      }
      return cache;
    });

  /**
   * **Validates: Requirements 9.4**
   *
   * After invalidation, the specified key is no longer in the cache.
   */
  it("after invalidation, the specified key is no longer in the cache", () => {
    fc.assert(
      fc.property(
        arbGateCache,
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 5 }).map((chars) => chars.join("")),
        (cache, uuid, version) => {
          // Ensure the key exists in the cache before invalidation
          const key = buildGateCacheKey(uuid, version);
          const cacheWithKey = { ...cache, [key]: true };

          const result = invalidateGateCacheEntry(cacheWithKey, uuid, version);
          expect(result).not.toHaveProperty(key);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.4**
   *
   * All other entries in the cache remain unchanged after invalidation.
   */
  it("all other entries in the cache remain unchanged", () => {
    fc.assert(
      fc.property(
        arbGateCache,
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 5 }).map((chars) => chars.join("")),
        (cache, uuid, version) => {
          const key = buildGateCacheKey(uuid, version);
          const result = invalidateGateCacheEntry(cache, uuid, version);

          // All keys other than the invalidated one should remain unchanged
          for (const existingKey of Object.keys(cache)) {
            if (existingKey !== key) {
              expect(result[existingKey]).toBe(cache[existingKey]);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.4**
   *
   * Invalidating a key that doesn't exist returns the same cache contents (no error).
   */
  it("invalidating a key that doesn't exist returns the same cache contents (no error)", () => {
    fc.assert(
      fc.property(
        arbGateCache,
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 5 }).map((chars) => chars.join("")),
        (cache, uuid, version) => {
          const key = buildGateCacheKey(uuid, version);
          // Ensure the key does NOT exist in the cache
          const cacheWithoutKey = { ...cache };
          delete cacheWithoutKey[key];

          const result = invalidateGateCacheEntry(cacheWithoutKey, uuid, version);

          // Result should have the same entries as the input cache (without the key)
          expect(Object.keys(result).sort()).toEqual(Object.keys(cacheWithoutKey).sort());
          for (const existingKey of Object.keys(cacheWithoutKey)) {
            expect(result[existingKey]).toBe(cacheWithoutKey[existingKey]);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.4**
   *
   * The returned cache is a new object (not the same reference as the input).
   */
  it("the returned cache is a new object (not the same reference)", () => {
    fc.assert(
      fc.property(
        arbGateCache,
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 5 }).map((chars) => chars.join("")),
        (cache, uuid, version) => {
          const result = invalidateGateCacheEntry(cache, uuid, version);
          expect(result).not.toBe(cache);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.4**
   *
   * buildGateCacheKey produces consistent keys from uuid+version.
   */
  it("buildGateCacheKey produces consistent keys from uuid+version", () => {
    fc.assert(
      fc.property(
        fc.uuid(),
        fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 5 }).map((chars) => chars.join("")),
        (uuid, version) => {
          const key1 = buildGateCacheKey(uuid, version);
          const key2 = buildGateCacheKey(uuid, version);
          expect(key1).toBe(key2);
          expect(key1).toBe(`${uuid}_${version}`);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 16: Error message extraction from API errors
// Validates: Requirements 9.7
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 16: Error message extraction from API errors", () => {
  /**
   * **Validates: Requirements 9.7**
   *
   * Returns `detail` field from parsed JSON body when present.
   */
  it("returns detail field from parsed JSON body when present", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        (detailMessage) => {
          const error = {
            body: JSON.stringify({ detail: detailMessage }),
            message: "fallback message",
          };
          expect(extractErrorMessage(error)).toBe(detailMessage);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.7**
   *
   * Returns `message` field from parsed JSON body when detail is absent.
   */
  it("returns message field from parsed JSON body when detail is absent", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        (messageText) => {
          const error = {
            body: JSON.stringify({ message: messageText }),
            message: "fallback message",
          };
          expect(extractErrorMessage(error)).toBe(messageText);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.7**
   *
   * Returns raw body string when JSON parsing fails.
   */
  it("returns raw body string when JSON parsing fails", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }).filter((s) => {
          try {
            JSON.parse(s);
            return false; // Skip strings that are valid JSON
          } catch {
            return true; // Keep strings that fail JSON parsing
          }
        }),
        (rawBody) => {
          const error = {
            body: rawBody,
            message: "fallback message",
          };
          expect(extractErrorMessage(error)).toBe(rawBody);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.7**
   *
   * Returns error.message when body is absent/empty.
   */
  it("returns error.message when body is absent or empty", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        fc.constantFrom(undefined, "", null),
        (errorMessage, body) => {
          const error: Record<string, unknown> = { message: errorMessage };
          if (body !== undefined) {
            error.body = body;
          }
          expect(extractErrorMessage(error)).toBe(errorMessage);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.7**
   *
   * Returns "An unexpected error occurred" as final fallback for non-object/non-Error inputs.
   */
  it("returns 'An unexpected error occurred' as final fallback for non-object/non-Error inputs", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(null),
          fc.constant(undefined),
          fc.integer(),
          fc.boolean(),
          fc.constant("")
        ),
        (input) => {
          expect(extractErrorMessage(input)).toBe("An unexpected error occurred");
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.7**
   *
   * Always returns a non-empty string regardless of input.
   */
  it("always returns a non-empty string", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(null),
          fc.constant(undefined),
          fc.integer(),
          fc.boolean(),
          fc.string(),
          fc.record({
            body: fc.oneof(fc.string(), fc.constant(undefined)),
            message: fc.oneof(fc.string(), fc.constant(undefined)),
          }),
          fc.record({
            body: fc.oneof(
              fc.constant(JSON.stringify({ detail: "some error" })),
              fc.constant(JSON.stringify({ message: "some msg" })),
              fc.constant("raw body text"),
              fc.constant("")
            ),
            message: fc.oneof(fc.string({ minLength: 1 }), fc.constant("")),
          })
        ),
        (input) => {
          const result = extractErrorMessage(input);
          expect(typeof result).toBe("string");
          expect(result.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 18: Task card aria-label format
// Validates: Requirements 11.3
// ---------------------------------------------------------------------------

describe("Feature: training-management-ui, Property 18: Task card aria-label format", () => {
  /**
   * Generator for a valid TrainingTask object.
   */
  const arbTask: fc.Arbitrary<TrainingTask> = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    sop_document_uuid: fc.uuid(),
    sop_version: fc.array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), { minLength: 1, maxLength: 10 }).map((chars) => chars.join("")),
    assigned_user_id: fc.integer({ min: 1, max: 10000 }),
    task_title: fc.string({ minLength: 1, maxLength: 200 }),
    is_completed: fc.boolean(),
    completed_at: fc.oneof(
      fc.constant(null),
      fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString())
    ),
    created_at: fc.integer({ min: 946684800000, max: 1924905600000 }).map((ts) => new Date(ts).toISOString()),
  });

  /**
   * **Validates: Requirements 11.3**
   *
   * Output format is always "{task_title} - {status}" where status is "Pending" or "Completed".
   */
  it("output format is always '{task_title} - {status}'", () => {
    fc.assert(
      fc.property(arbTask, (task) => {
        const result = formatAriaLabel(task);
        const expectedStatus = task.is_completed ? "Completed" : "Pending";
        expect(result).toBe(`${task.task_title} - ${expectedStatus}`);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 11.3**
   *
   * When task.is_completed is true, status part is "Completed".
   */
  it("when task.is_completed is true, status part is 'Completed'", () => {
    fc.assert(
      fc.property(
        arbTask.filter((t) => t.is_completed),
        (task) => {
          const result = formatAriaLabel(task);
          expect(result.endsWith(" - Completed")).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 11.3**
   *
   * When task.is_completed is false, status part is "Pending".
   */
  it("when task.is_completed is false, status part is 'Pending'", () => {
    fc.assert(
      fc.property(
        arbTask.filter((t) => !t.is_completed),
        (task) => {
          const result = formatAriaLabel(task);
          expect(result.endsWith(" - Pending")).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 11.3**
   *
   * Output always contains the task_title as a prefix.
   */
  it("output always contains the task_title as a prefix", () => {
    fc.assert(
      fc.property(arbTask, (task) => {
        const result = formatAriaLabel(task);
        expect(result.startsWith(task.task_title)).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 11.3**
   *
   * Output always contains " - " separator.
   */
  it("output always contains ' - ' separator", () => {
    fc.assert(
      fc.property(arbTask, (task) => {
        const result = formatAriaLabel(task);
        expect(result).toContain(" - ");
      }),
      { numRuns: 100 }
    );
  });
});
