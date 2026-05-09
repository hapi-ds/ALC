import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { toggleTransition } from "../TransitionConfigPanel";

/**
 * Feature: bpmn-workflow-visual-editor
 * Property 3: Transition toggle set membership
 *
 * For any transition string and initial array of selected transitions,
 * toggling the transition "on" SHALL result in an array containing that
 * transition, and toggling it "off" SHALL result in an array not containing
 * that transition, with all other elements unchanged.
 *
 * **Validates: Requirements 3.3, 3.4**
 */

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Arbitrary transition string (e.g., "Draft→Review") */
const transitionArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 50 })
  .filter((s) => s.trim().length > 0);

/** Arbitrary array of unique transition strings */
const uniqueTransitionsArrayArb: fc.Arbitrary<string[]> = fc
  .array(transitionArb, { minLength: 0, maxLength: 20 })
  .map((arr) => [...new Set(arr)]);

// ---------------------------------------------------------------------------
// Property Tests
// ---------------------------------------------------------------------------

describe("Feature: bpmn-workflow-visual-editor, Property 3: Transition toggle set membership", () => {
  it("toggling on adds the transition to the array", () => {
    fc.assert(
      fc.property(
        uniqueTransitionsArrayArb,
        transitionArb,
        (initialTransitions, transition) => {
          // Ensure the transition is NOT in the initial array (toggle ON scenario)
          const withoutTransition = initialTransitions.filter(
            (t) => t !== transition
          );

          const result = toggleTransition(withoutTransition, transition);

          // The transition should now be in the result
          expect(result).toContain(transition);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("toggling off removes the transition from the array", () => {
    fc.assert(
      fc.property(
        uniqueTransitionsArrayArb,
        transitionArb,
        (initialTransitions, transition) => {
          // Ensure the transition IS in the initial array (toggle OFF scenario)
          const withTransition = initialTransitions.includes(transition)
            ? initialTransitions
            : [...initialTransitions, transition];

          const result = toggleTransition(withTransition, transition);

          // The transition should NOT be in the result
          expect(result).not.toContain(transition);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("toggling preserves all other elements unchanged", () => {
    fc.assert(
      fc.property(
        uniqueTransitionsArrayArb,
        transitionArb,
        (initialTransitions, transition) => {
          const result = toggleTransition(initialTransitions, transition);

          // All elements that are not the toggled transition should remain
          const otherElements = initialTransitions.filter(
            (t) => t !== transition
          );
          for (const element of otherElements) {
            expect(result).toContain(element);
          }

          // The order of other elements should be preserved
          const resultOthers = result.filter((t) => t !== transition);
          expect(resultOthers).toEqual(otherElements);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("toggling is idempotent: toggling on twice is same as toggling on once", () => {
    fc.assert(
      fc.property(
        uniqueTransitionsArrayArb,
        transitionArb,
        (initialTransitions, transition) => {
          // Start without the transition
          const withoutTransition = initialTransitions.filter(
            (t) => t !== transition
          );

          // Toggle on once
          const afterFirstToggle = toggleTransition(
            withoutTransition,
            transition
          );
          // Toggle off then on again
          const afterToggleOff = toggleTransition(afterFirstToggle, transition);
          const afterSecondToggleOn = toggleTransition(
            afterToggleOff,
            transition
          );

          // Both should contain the transition
          expect(afterFirstToggle).toContain(transition);
          expect(afterSecondToggleOn).toContain(transition);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("result array length changes by exactly 1", () => {
    fc.assert(
      fc.property(
        uniqueTransitionsArrayArb,
        transitionArb,
        (initialTransitions, transition) => {
          const result = toggleTransition(initialTransitions, transition);

          if (initialTransitions.includes(transition)) {
            // Toggling off: length decreases by 1
            expect(result.length).toBe(initialTransitions.length - 1);
          } else {
            // Toggling on: length increases by 1
            expect(result.length).toBe(initialTransitions.length + 1);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
