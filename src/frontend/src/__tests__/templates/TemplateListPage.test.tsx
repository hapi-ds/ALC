import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import { render, screen, cleanup, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TemplateListPage } from "../../pages/TemplateListPage";
import { useTemplateListStore } from "../../stores/templateListStore";
import type { TemplateResponse } from "../../types/template";

/**
 * Unit tests for TemplateListPage component.
 *
 * Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
 */

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockTemplates: TemplateResponse[] = [
  {
    id: 1,
    document_uuid: "2024-00001",
    name: "Test Template A",
    json_schema: {},
    status: "ReadOnly",
    created_by: 1,
    fields: [
      {
        id: 1,
        field_uuid: "FLD-00000001",
        field_type: "Text",
        field_label: "Name",
        field_order: 0,
      },
      {
        id: 2,
        field_uuid: "FLD-00000002",
        field_type: "Date",
        field_label: "Date",
        field_order: 1,
      },
    ],
  },
  {
    id: 2,
    document_uuid: "2024-00002",
    name: "Test Template B",
    json_schema: {},
    status: "ReadOnly",
    created_by: 1,
    fields: [
      {
        id: 3,
        field_uuid: "FLD-00000003",
        field_type: "Float",
        field_label: "Amount",
        field_order: 0,
      },
    ],
  },
];

function resetStore() {
  useTemplateListStore.setState({
    templates: [],
    isLoading: false,
    error: null,
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <TemplateListPage />
    </MemoryRouter>
  );
}

describe("TemplateListPage", () => {
  beforeEach(() => {
    resetStore();
    mockNavigate.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("calls fetchTemplates on mount", () => {
    const fetchSpy = vi.fn();
    useTemplateListStore.setState({ fetchTemplates: fetchSpy });

    renderPage();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("shows loading indicator when isLoading is true after 200ms delay", () => {
    useTemplateListStore.setState({ isLoading: true });

    renderPage();

    // Loading indicator should NOT be visible immediately
    expect(screen.queryByLabelText("Loading templates")).toBeNull();

    // Advance timers past the 200ms delay
    act(() => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.getByLabelText("Loading templates")).toBeDefined();
  });

  it("renders template list items with document_uuid, name, status, and field count", () => {
    useTemplateListStore.setState({
      templates: mockTemplates,
      isLoading: false,
    });

    renderPage();

    // Check first template
    expect(screen.getByText("2024-00001")).toBeDefined();
    expect(screen.getByText("Test Template A")).toBeDefined();

    // Check second template
    expect(screen.getByText("2024-00002")).toBeDefined();
    expect(screen.getByText("Test Template B")).toBeDefined();

    // Check status badges
    const statusBadges = screen.getAllByText("ReadOnly");
    expect(statusBadges).toHaveLength(2);

    // Check field counts: Template A has 2 fields, Template B has 1 field
    expect(screen.getByText("2")).toBeDefined();
    expect(screen.getByText("1")).toBeDefined();
  });

  it("orders templates by document_uuid descending", () => {
    useTemplateListStore.setState({
      templates: mockTemplates,
      isLoading: false,
    });

    renderPage();

    const rows = screen.getAllByRole("row");
    // First row is the header, so data rows start at index 1
    const firstDataRow = rows[1];
    const secondDataRow = rows[2];

    // 2024-00002 should come first (descending order)
    expect(firstDataRow.textContent).toContain("2024-00002");
    expect(secondDataRow.textContent).toContain("2024-00001");
  });

  it('shows empty state message when templates array is empty', () => {
    useTemplateListStore.setState({
      templates: [],
      isLoading: false,
      error: null,
    });

    renderPage();

    expect(
      screen.getByText("No templates have been created yet.")
    ).toBeDefined();
  });

  it("shows error message when error is set", () => {
    useTemplateListStore.setState({
      templates: [],
      isLoading: false,
      error: "Failed to load templates",
    });

    renderPage();

    const alert = screen.getByRole("alert");
    expect(alert).toBeDefined();
    expect(alert.textContent).toContain("Failed to load templates");
  });

  it("shows timeout error message", () => {
    useTemplateListStore.setState({
      templates: [],
      isLoading: false,
      error: "Request timed out",
    });

    renderPage();

    const alert = screen.getByRole("alert");
    expect(alert).toBeDefined();
    expect(alert.textContent).toContain("Request timed out");
  });

  it('"New Template" button navigates to /templates/new', () => {
    renderPage();

    const newButton = screen.getByRole("button", { name: /new template/i });
    newButton.click();

    expect(mockNavigate).toHaveBeenCalledWith("/templates/new");
  });
});
