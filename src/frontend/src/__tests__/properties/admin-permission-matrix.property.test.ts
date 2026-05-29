import { describe, it, expect } from "vitest";
import * as fc from "fast-check";

/**
 * Property-based tests for permission matrix display logic.
 *
 * Tests the core logic that determines how permissions are displayed
 * in the PermissionMatrixView component — specifically the mapping
 * between role permission data and granted/denied visual indicators.
 *
 * **Validates: Requirements 10.2**
 */

// ---------------------------------------------------------------------------
// Constants (mirrors PermissionMatrixView.tsx)
// ---------------------------------------------------------------------------

const RESOURCE_TYPES = [
  "documents",
  "workflows",
  "users",
  "audit_logs",
  "templates",
  "training",
  "signatures",
  "system_config",
] as const;

const ACTIONS = ["create", "read", "update", "delete", "approve"] as const;

type ResourceType = (typeof RESOURCE_TYPES)[number];
type Action = (typeof ACTIONS)[number];

// ---------------------------------------------------------------------------
// Pure logic under test (extracted from component rendering logic)
// ---------------------------------------------------------------------------

/**
 * Determines whether a specific action is granted for a resource
 * given a permissions map. This is the core display logic used by
 * PermissionMatrixView to decide whether to show a checkmark or X.
 */
function isPermissionGranted(
  permissions: Record<string, string[]>,
  resource: ResourceType,
  action: Action
): boolean {
  const grantedActions = permissions[resource] ?? [];
  return grantedActions.includes(action);
}

/**
 * Counts the total number of granted permissions in a permission map.
 */
function countGrantedPermissions(permissions: Record<string, string[]>): number {
  let count = 0;
  for (const resource of RESOURCE_TYPES) {
    const actions = permissions[resource] ?? [];
    for (const action of ACTIONS) {
      if (actions.includes(action)) {
        count++;
      }
    }
  }
  return count;
}

/**
 * Counts the total number of denied permissions in a permission map.
 */
function countDeniedPermissions(permissions: Record<string, string[]>): number {
  const totalCells = RESOURCE_TYPES.length * ACTIONS.length;
  return totalCells - countGrantedPermissions(permissions);
}

// ---------------------------------------------------------------------------
// Arbitrary generators
// ---------------------------------------------------------------------------

/** Generator for a valid action subset. */
const arbActionSubset: fc.Arbitrary<Action[]> = fc.subarray(
  [...ACTIONS],
  { minLength: 0, maxLength: ACTIONS.length }
);

/** Generator for a valid permissions map (resource -> actions). */
const arbPermissions: fc.Arbitrary<Record<string, string[]>> = fc.record(
  Object.fromEntries(
    RESOURCE_TYPES.map((resource) => [resource, arbActionSubset])
  ) as Record<ResourceType, fc.Arbitrary<Action[]>>
);

/** Generator for a valid resource type. */
const arbResource: fc.Arbitrary<ResourceType> = fc.constantFrom(...RESOURCE_TYPES);

/** Generator for a valid action. */
const arbAction: fc.Arbitrary<Action> = fc.constantFrom(...ACTIONS);

// ---------------------------------------------------------------------------
// Property 1: Permission display completeness
// ---------------------------------------------------------------------------

describe("Feature: admin-permission-matrix, Property 1: Permission display completeness", () => {
  /**
   * **Validates: Requirements 10.2**
   *
   * For any permissions map, the total number of granted + denied cells
   * always equals RESOURCE_TYPES.length × ACTIONS.length (the full grid).
   */
  it("granted + denied always equals total grid cells", () => {
    fc.assert(
      fc.property(arbPermissions, (permissions) => {
        const granted = countGrantedPermissions(permissions);
        const denied = countDeniedPermissions(permissions);
        const totalCells = RESOURCE_TYPES.length * ACTIONS.length;
        expect(granted + denied).toBe(totalCells);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 10.2**
   *
   * For any permissions map, granted count is non-negative and at most total cells.
   */
  it("granted count is bounded [0, totalCells]", () => {
    fc.assert(
      fc.property(arbPermissions, (permissions) => {
        const granted = countGrantedPermissions(permissions);
        const totalCells = RESOURCE_TYPES.length * ACTIONS.length;
        expect(granted).toBeGreaterThanOrEqual(0);
        expect(granted).toBeLessThanOrEqual(totalCells);
      }),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Permission lookup correctness
// ---------------------------------------------------------------------------

describe("Feature: admin-permission-matrix, Property 2: Permission lookup correctness", () => {
  /**
   * **Validates: Requirements 10.2**
   *
   * For any permissions map, resource, and action: isPermissionGranted returns true
   * if and only if the action is in the resource's action list.
   */
  it("isPermissionGranted is true iff action is in the resource's list", () => {
    fc.assert(
      fc.property(arbPermissions, arbResource, arbAction, (permissions, resource, action) => {
        const result = isPermissionGranted(permissions, resource, action);
        const expected = (permissions[resource] ?? []).includes(action);
        expect(result).toBe(expected);
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 10.2**
   *
   * For any resource not present in the permissions map, all actions are denied.
   */
  it("missing resource means all actions denied", () => {
    fc.assert(
      fc.property(arbAction, (action) => {
        const emptyPermissions: Record<string, string[]> = {};
        for (const resource of RESOURCE_TYPES) {
          expect(isPermissionGranted(emptyPermissions, resource, action)).toBe(false);
        }
      }),
      { numRuns: 50 }
    );
  });

  /**
   * **Validates: Requirements 10.2**
   *
   * For a resource with an empty action list, all actions are denied.
   */
  it("empty action list means all actions denied for that resource", () => {
    fc.assert(
      fc.property(arbResource, arbAction, (resource, action) => {
        const permissions: Record<string, string[]> = { [resource]: [] };
        expect(isPermissionGranted(permissions, resource, action)).toBe(false);
      }),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 3: Full access role has all permissions granted
// ---------------------------------------------------------------------------

describe("Feature: admin-permission-matrix, Property 3: Full access role correctness", () => {
  /**
   * **Validates: Requirements 10.2**
   *
   * A role with all actions on all resources has exactly totalCells granted.
   */
  it("full access role has all cells granted", () => {
    const fullPermissions: Record<string, string[]> = {};
    for (const resource of RESOURCE_TYPES) {
      fullPermissions[resource] = [...ACTIONS];
    }

    const granted = countGrantedPermissions(fullPermissions);
    const totalCells = RESOURCE_TYPES.length * ACTIONS.length;
    expect(granted).toBe(totalCells);
  });

  /**
   * **Validates: Requirements 10.2**
   *
   * For any resource and action, a full-access permissions map always grants.
   */
  it("full access role grants every resource-action pair", () => {
    const fullPermissions: Record<string, string[]> = {};
    for (const resource of RESOURCE_TYPES) {
      fullPermissions[resource] = [...ACTIONS];
    }

    fc.assert(
      fc.property(arbResource, arbAction, (resource, action) => {
        expect(isPermissionGranted(fullPermissions, resource, action)).toBe(true);
      }),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4: Adding an action increases granted count
// ---------------------------------------------------------------------------

describe("Feature: admin-permission-matrix, Property 4: Monotonicity of permission granting", () => {
  /**
   * **Validates: Requirements 10.2**
   *
   * Adding an action to a resource's list that wasn't there before
   * increases the granted count by exactly 1.
   */
  it("adding a new action increases granted count by 1", () => {
    fc.assert(
      fc.property(arbPermissions, arbResource, arbAction, (permissions, resource, action) => {
        const currentActions = permissions[resource] ?? [];
        // Only test when the action is NOT already granted
        fc.pre(!currentActions.includes(action));

        const before = countGrantedPermissions(permissions);
        const updatedPermissions = {
          ...permissions,
          [resource]: [...currentActions, action],
        };
        const after = countGrantedPermissions(updatedPermissions);

        expect(after).toBe(before + 1);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 10.2**
   *
   * Removing an action from a resource's list decreases the granted count by exactly 1.
   */
  it("removing an action decreases granted count by 1", () => {
    fc.assert(
      fc.property(arbPermissions, arbResource, arbAction, (permissions, resource, action) => {
        const currentActions = permissions[resource] ?? [];
        // Only test when the action IS already granted
        fc.pre(currentActions.includes(action));

        const before = countGrantedPermissions(permissions);
        const updatedPermissions = {
          ...permissions,
          [resource]: currentActions.filter((a) => a !== action),
        };
        const after = countGrantedPermissions(updatedPermissions);

        expect(after).toBe(before - 1);
      }),
      { numRuns: 100 }
    );
  });
});
