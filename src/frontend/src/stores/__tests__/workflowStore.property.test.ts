import { describe, it, expect, beforeEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: bpmn-workflow-visual-editor
 *
 * Property 5: Store dirty flag and validation clearing
 * Property 11: Version restore sets editor state
 *
 * Validates: Requirements 14.8, 14.9
 */

// Mock apiClient and auth dependencies (no actual API calls in these tests)
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    constructor(status: number, body: string) {
      super(body);
      this.status = status;
      this.body = body;
    }
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(),
}));

vi.mock("../authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 1 },
      activeCompanyId: 1,
    }),
    setState: vi.fn(),
  },
}));

import { useWorkflowStore } from "../workflowStore";
import type { WorkflowVersionDetail } from "../workflowStore";

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Arbitrary non-empty XML string */
const xmlStringArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 200 })
  .filter((s) => s.trim().length > 0);

/** Arbitrary workflow name */
const workflowNameArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 200 })
  .filter((s) => s.trim().length > 0);

/** Arbitrary document tag */
const documentTagArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 100 })
  .filter((s) => s.trim().length > 0);

/** Arbitrary transition string (e.g., "Draft→Review") */
const transitionArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 50 })
  .filter((s) => s.trim().length > 0);

/** Arbitrary array of transitions */
const transitionsArrayArb: fc.Arbitrary<string[]> = fc.array(transitionArb, {
  minLength: 0,
  maxLength: 10,
});

/** Arbitrary risk level */
const riskLevelArb: fc.Arbitrary<string> = fc.constantFrom(
  "low",
  "medium",
  "high",
  "critical"
);

/** Arbitrary WorkflowVersionDetail */
const workflowVersionDetailArb: fc.Arbitrary<WorkflowVersionDetail> = fc.record({
  version_number: fc.integer({ min: 1, max: 1000 }),
  bpmn_xml: xmlStringArb,
  name: workflowNameArb,
  document_tag: documentTagArb,
  risk_level: riskLevelArb,
  signature_required_transitions: transitionsArrayArb,
  training_trigger_transitions: transitionsArrayArb,
  auto_assignment_config: fc.constantFrom(null, { role: "reviewer" }, { agent: "ai-1" }),
  created_by: fc.integer({ min: 1, max: 100 }),
  created_at: fc.integer({ min: 946684800000, max: 4102444799000 }).map((ts) => new Date(ts).toISOString()),
  change_reason: fc.string({ minLength: 1, maxLength: 100 }),
});

// ---------------------------------------------------------------------------
// Property 5: Store dirty flag and validation clearing
// ---------------------------------------------------------------------------

describe("Feature: bpmn-workflow-visual-editor, Property 5: Store dirty flag and validation clearing", () => {
  beforeEach(() => {
    useWorkflowStore.getState().resetEditor();
  });

  it("setBpmnXml sets isDirty=true and clears validationResult", () => {
    fc.assert(
      fc.property(xmlStringArb, (xml) => {
        useWorkflowStore.getState().resetEditor();

        // Set up a non-null validationResult to verify it gets cleared
        useWorkflowStore.setState({
          validationResult: { is_valid: false, errors: ["some error"] },
          isDirty: false,
        });

        // Act
        useWorkflowStore.getState().setBpmnXml(xml);

        // Assert
        const state = useWorkflowStore.getState();
        expect(state.isDirty).toBe(true);
        expect(state.validationResult).toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("setWorkflowName sets isDirty=true", () => {
    fc.assert(
      fc.property(workflowNameArb, (name) => {
        useWorkflowStore.getState().resetEditor();

        // Act
        useWorkflowStore.getState().setWorkflowName(name);

        // Assert
        const state = useWorkflowStore.getState();
        expect(state.isDirty).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it("setDocumentTag sets isDirty=true", () => {
    fc.assert(
      fc.property(documentTagArb, (tag) => {
        useWorkflowStore.getState().resetEditor();

        // Act
        useWorkflowStore.getState().setDocumentTag(tag);

        // Assert
        const state = useWorkflowStore.getState();
        expect(state.isDirty).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it("setSignatureTransitions sets isDirty=true", () => {
    fc.assert(
      fc.property(
        transitionsArrayArb.filter((arr) => arr.length > 0),
        (transitions) => {
          useWorkflowStore.getState().resetEditor();

          // Act
          useWorkflowStore.getState().setSignatureTransitions(transitions);

          // Assert
          const state = useWorkflowStore.getState();
          expect(state.isDirty).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("setTrainingTransitions sets isDirty=true", () => {
    fc.assert(
      fc.property(
        transitionsArrayArb.filter((arr) => arr.length > 0),
        (transitions) => {
          useWorkflowStore.getState().resetEditor();

          // Act
          useWorkflowStore.getState().setTrainingTransitions(transitions);

          // Assert
          const state = useWorkflowStore.getState();
          expect(state.isDirty).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 11: Version restore sets editor state
// ---------------------------------------------------------------------------

describe("Feature: bpmn-workflow-visual-editor, Property 11: Version restore sets editor state", () => {
  beforeEach(() => {
    useWorkflowStore.getState().resetEditor();
  });

  it("restoreVersion sets bpmnXml, transitions, and isDirty=true", () => {
    fc.assert(
      fc.property(workflowVersionDetailArb, (version) => {
        useWorkflowStore.getState().resetEditor();

        // Act
        useWorkflowStore.getState().restoreVersion(version);

        // Assert
        const state = useWorkflowStore.getState();
        expect(state.bpmnXml).toBe(version.bpmn_xml);
        expect(state.signatureRequiredTransitions).toEqual(
          version.signature_required_transitions
        );
        expect(state.trainingTriggerTransitions).toEqual(
          version.training_trigger_transitions
        );
        expect(state.isDirty).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it("restoreVersion also sets workflowName, documentTag, and riskLevel from version", () => {
    fc.assert(
      fc.property(workflowVersionDetailArb, (version) => {
        useWorkflowStore.getState().resetEditor();

        // Act
        useWorkflowStore.getState().restoreVersion(version);

        // Assert
        const state = useWorkflowStore.getState();
        expect(state.workflowName).toBe(version.name);
        expect(state.documentTag).toBe(version.document_tag);
        expect(state.riskLevel).toBe(version.risk_level);
        expect(state.autoAssignmentConfig).toEqual(
          version.auto_assignment_config
        );
      }),
      { numRuns: 100 }
    );
  });

  it("restoreVersion clears selectedVersion", () => {
    fc.assert(
      fc.property(workflowVersionDetailArb, (version) => {
        useWorkflowStore.getState().resetEditor();

        // Set a selectedVersion first
        useWorkflowStore.setState({ selectedVersion: version });

        // Act
        useWorkflowStore.getState().restoreVersion(version);

        // Assert
        const state = useWorkflowStore.getState();
        expect(state.selectedVersion).toBeNull();
      }),
      { numRuns: 100 }
    );
  });
});
