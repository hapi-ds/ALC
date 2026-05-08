import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import React from "react";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";

/**
 * Integration tests for the full Template Builder flow.
 *
 * Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 9.1, 9.2, 9.4, 11.2, 11.4, 11.5
 */

// Mock apiClient — the store calls apiClient.post("/api/templates", payload, { changeReason })
// which internally sets the X-Change-Reason header. We verify the store passes correct args.
vi.mock("../../lib/apiClient", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    url: string;
    constructor(status: number, body: string, url: string = "/api/templates") {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

// Mock authStore to provide a user with id=42
vi.mock("../../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn(() => ({
      user: { id: 42, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["admin"] },
      isAuthenticated: true,
    })),
    {
      getState: () => ({
        user: { id: 42, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["admin"] },
        isAuthenticated: true,
        activeCompanyId: 1,
        activeCompanySlug: "test-company",
      }),
    }
  ),
}));

// Import after mocks
import { apiClient, ApiError } from "../../lib/apiClient";
import { TemplateBuilderPage } from "../../pages/TemplateBuilderPage";
import { UnsavedChangesDialog } from "../../components/templates/UnsavedChangesDialog";

const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

function resetStore() {
  useTemplateBuilderStore.setState({
    fields: [],
    selectedFieldId: null,
    fieldErrors: {},
    templateName: "",
    isSaving: false,
    saveError: null,
    saveSuccess: false,
    savedTemplate: null,
    isDirty: false,
    nameError: null,
  });
}

// ---------------------------------------------------------------------------
// Store-level integration tests (no rendering needed)
// ---------------------------------------------------------------------------

describe("Template Builder Integration - Store-level save flow", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  it("full save flow: add fields, set labels/types, set name, save, verify API call", async () => {
    const store = useTemplateBuilderStore.getState();

    // Add fields via store
    store.addField("Text", 0);
    store.addField("Integer", 1);
    store.addField("Date", 2);

    // Configure labels
    const fields = useTemplateBuilderStore.getState().fields;
    useTemplateBuilderStore.getState().updateFieldLabel(fields[0].id, "Patient Name");
    useTemplateBuilderStore.getState().updateFieldLabel(fields[1].id, "Age");
    useTemplateBuilderStore.getState().updateFieldLabel(fields[2].id, "Visit Date");

    // Change type of second field
    useTemplateBuilderStore.getState().updateFieldType(fields[1].id, "Float");

    // Set template name
    useTemplateBuilderStore.getState().setTemplateName("Clinical Trial Form");

    // Mock successful API response
    mockedPost.mockResolvedValueOnce({
      id: 1,
      document_uuid: "2025-00001",
      name: "Clinical Trial Form",
      json_schema: {},
      status: "ReadOnly",
      created_by: 42,
      fields: [],
    });

    // Save
    await useTemplateBuilderStore.getState().saveTemplate();

    // Verify apiClient.post was called with correct URL, payload, and options
    expect(mockedPost).toHaveBeenCalledTimes(1);
    expect(mockedPost).toHaveBeenCalledWith(
      "/api/templates",
      {
        name: "Clinical Trial Form",
        json_schema: {
          elements: [
            { element_type: "field", label: "Patient Name", type: "Text", required: false, help_text: null, default_value: null, config: {} },
            { element_type: "field", label: "Age", type: "Float", required: false, help_text: null, default_value: null, config: {} },
            { element_type: "field", label: "Visit Date", type: "Date", required: false, help_text: null, default_value: null, config: { date_format: "YYYY-MM-DD" } },
          ],
        },
        user_id: 42,
      },
      { changeReason: "Template created via builder" }
    );

    // Verify success state
    const finalState = useTemplateBuilderStore.getState();
    expect(finalState.saveSuccess).toBe(true);
    expect(finalState.isDirty).toBe(false);
    expect(finalState.isSaving).toBe(false);
    expect(finalState.savedTemplate).not.toBeNull();
    expect(finalState.savedTemplate?.document_uuid).toBe("2025-00001");
  });

  it("400 error handling: parses detail message from response body", async () => {
    const store = useTemplateBuilderStore.getState();

    // Set up valid state for save
    store.addField("Text", 0);
    useTemplateBuilderStore.getState().updateFieldLabel(
      useTemplateBuilderStore.getState().fields[0].id,
      "Field A"
    );
    useTemplateBuilderStore.getState().setTemplateName("Duplicate Template");

    // Mock 400 error with detail in body
    const error = new ApiError(
      400,
      JSON.stringify({ detail: "Template name already exists" }),
      "/api/templates"
    );
    mockedPost.mockRejectedValueOnce(error);

    // Save
    await useTemplateBuilderStore.getState().saveTemplate();

    // Verify error state contains the parsed detail message
    const finalState = useTemplateBuilderStore.getState();
    expect(finalState.saveError).toBe("Template name already exists");
    expect(finalState.isSaving).toBe(false);
    expect(finalState.saveSuccess).toBe(false);
  });

  it("network error handling: displays generic error message", async () => {
    const store = useTemplateBuilderStore.getState();

    // Set up valid state for save
    store.addField("Text", 0);
    useTemplateBuilderStore.getState().updateFieldLabel(
      useTemplateBuilderStore.getState().fields[0].id,
      "Field A"
    );
    useTemplateBuilderStore.getState().setTemplateName("My Template");

    // Mock generic network error (not an ApiError)
    mockedPost.mockRejectedValueOnce(new Error("Network request failed"));

    // Save
    await useTemplateBuilderStore.getState().saveTemplate();

    // Verify generic error message
    const finalState = useTemplateBuilderStore.getState();
    expect(finalState.saveError).toBe("Failed to save template. Please try again.");
    expect(finalState.isSaving).toBe(false);
    expect(finalState.saveSuccess).toBe(false);
  });

  it("serialization correctness: fields ordered by fieldOrder with only label and type", async () => {
    const store = useTemplateBuilderStore.getState();

    // Add fields in specific order
    store.addField("Boolean", 0);
    store.addField("Float", 1);
    store.addField("Date", 2);
    store.addField("Text", 3);

    // Configure labels
    const fields = useTemplateBuilderStore.getState().fields;
    useTemplateBuilderStore.getState().updateFieldLabel(fields[0].id, "Is Active");
    useTemplateBuilderStore.getState().updateFieldLabel(fields[1].id, "Temperature");
    useTemplateBuilderStore.getState().updateFieldLabel(fields[2].id, "Start Date");
    useTemplateBuilderStore.getState().updateFieldLabel(fields[3].id, "Notes");

    // Reorder: move field at index 3 to index 1
    useTemplateBuilderStore.getState().reorderField(3, 1);

    // Set template name
    useTemplateBuilderStore.getState().setTemplateName("Reordered Template");

    // Mock successful response
    mockedPost.mockResolvedValueOnce({
      id: 2,
      document_uuid: "2025-00002",
      name: "Reordered Template",
      json_schema: {},
      status: "ReadOnly",
      created_by: 42,
      fields: [],
    });

    // Save
    await useTemplateBuilderStore.getState().saveTemplate();

    // Verify the payload has fields in fieldOrder order
    const callArgs = mockedPost.mock.calls[0];
    const payload = callArgs[1];

    // After reorder: [Is Active, Notes, Temperature, Start Date]
    expect(payload.json_schema.elements).toEqual([
      { element_type: "field", label: "Is Active", type: "Boolean", required: false, help_text: null, default_value: null, config: { true_label: "True", false_label: "False" } },
      { element_type: "field", label: "Notes", type: "Text", required: false, help_text: null, default_value: null, config: {} },
      { element_type: "field", label: "Temperature", type: "Float", required: false, help_text: null, default_value: null, config: {} },
      { element_type: "field", label: "Start Date", type: "Date", required: false, help_text: null, default_value: null, config: { date_format: "YYYY-MM-DD" } },
    ]);

    // Verify each element has element_type discriminator
    for (const element of payload.json_schema.elements) {
      expect(element.element_type).toBe("field");
    }

    // Verify array length matches canvas fields
    expect(payload.json_schema.elements.length).toBe(4);
  });
});

// ---------------------------------------------------------------------------
// Component-level integration test for unsaved changes dialog
// ---------------------------------------------------------------------------

describe("Template Builder Integration - Unsaved changes dialog", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("UnsavedChangesDialog renders when open is true", () => {
    render(
      <UnsavedChangesDialog open={true} onConfirm={() => {}} onCancel={() => {}} />
    );

    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByText("Unsaved Changes")).toBeDefined();
    expect(screen.getByText(/You have unsaved changes/)).toBeDefined();
    expect(screen.getByText("Leave")).toBeDefined();
    expect(screen.getByText("Stay")).toBeDefined();
  });

  it("UnsavedChangesDialog does not render when open is false", () => {
    render(
      <UnsavedChangesDialog open={false} onConfirm={() => {}} onCancel={() => {}} />
    );

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("clicking Stay calls onCancel", () => {
    const onCancel = vi.fn();
    render(
      <UnsavedChangesDialog open={true} onConfirm={() => {}} onCancel={onCancel} />
    );

    fireEvent.click(screen.getByText("Stay"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("clicking Leave calls onConfirm", () => {
    const onConfirm = vi.fn();
    render(
      <UnsavedChangesDialog open={true} onConfirm={onConfirm} onCancel={() => {}} />
    );

    fireEvent.click(screen.getByText("Leave"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("beforeunload listener is added when isDirty is true", () => {
    const addEventSpy = vi.spyOn(window, "addEventListener");

    // Render the page in a MemoryRouter
    render(
      <MemoryRouter initialEntries={["/templates/new"]}>
        <TemplateBuilderPage />
      </MemoryRouter>
    );

    // Make dirty
    act(() => {
      useTemplateBuilderStore.getState().addField("Text", 0);
    });

    expect(addEventSpy).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    addEventSpy.mockRestore();
  });

  it("beforeunload listener is not added when state is clean", () => {
    const addEventSpy = vi.spyOn(window, "addEventListener");

    render(
      <MemoryRouter initialEntries={["/templates/new"]}>
        <TemplateBuilderPage />
      </MemoryRouter>
    );

    // State is clean — beforeunload should not be registered
    const beforeUnloadCalls = addEventSpy.mock.calls.filter(
      (call) => call[0] === "beforeunload"
    );
    expect(beforeUnloadCalls).toHaveLength(0);
    addEventSpy.mockRestore();
  });
});
