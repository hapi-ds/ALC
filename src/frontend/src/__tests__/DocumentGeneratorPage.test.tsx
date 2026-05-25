import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";

/**
 * Frontend tests for DocumentGeneratorPage and sub-components.
 *
 * Validates: Requirements 1.1, 2.1, 6.2, 7.3
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock react-router-dom (DocumentGeneratorPage uses useSearchParams)
const mockSetSearchParams = vi.fn();
vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(), mockSetSearchParams],
}));

// Mock apiClient
vi.mock("../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

// Mock lucide-react icons to avoid rendering issues
vi.mock("lucide-react", () => ({
  Loader2: () => <span data-testid="loader-icon">Loading</span>,
  ChevronLeft: () => <span>←</span>,
  ChevronRight: () => <span>→</span>,
  Check: () => <span>✓</span>,
  X: () => <span>✗</span>,
  FileText: () => <span>📄</span>,
  RefreshCw: () => <span>🔄</span>,
  Eye: () => <span>👁</span>,
  AlertCircle: () => <span>⚠</span>,
  Hash: () => <span>#</span>,
  Layout: () => <span>⊞</span>,
  Type: () => <span>T</span>,
}));

// Import after mocks
import { apiClient } from "../lib/apiClient";
import { useDocumentGeneratorStore } from "../stores/documentGeneratorStore";
import { DocumentGeneratorPage } from "../pages/DocumentGeneratorPage";
import { TemplateRegistrationPanel } from "../components/document-generator/TemplateRegistrationPanel";
import { GenerationSetupPanel } from "../components/document-generator/GenerationSetupPanel";
import { JobProgressMonitor } from "../components/document-generator/JobProgressMonitor";
import { ReviewWorkflowPanel } from "../components/document-generator/ReviewWorkflowPanel";
import type {
  DocumentTemplate,
  GenerationJob,
  GeneratedDocument,
} from "../types/documentGenerator";

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockTemplate: DocumentTemplate = {
  id: 1,
  document_id: 10,
  document_version_id: 20,
  template_name: "URS Master Template v2",
  document_type_target: "URS",
  status: "ready",
  registered_by: 42,
  registered_at: "2024-06-01T10:00:00Z",
  template_analysis: null,
};

const mockTemplate2: DocumentTemplate = {
  id: 2,
  document_id: 11,
  document_version_id: 21,
  template_name: "SOP Template",
  document_type_target: "SOP",
  status: "ready",
  registered_by: 42,
  registered_at: "2024-06-02T10:00:00Z",
  template_analysis: null,
};

const mockProcessingJob: GenerationJob = {
  job_id: "job-abc-123",
  status: "processing",
  progress_percent: 45,
  current_section: "Section 2: Scope",
  sections_completed: 2,
  sections_total: 5,
  estimated_time_remaining_seconds: 120,
  error_message: null,
  result_document_id: null,
  result_document_uuid: null,
  result_storage_key: null,
  file_size_bytes: null,
  generation_duration_ms: null,
};

const mockCompletedJob: GenerationJob = {
  job_id: "job-def-456",
  status: "completed",
  progress_percent: 100,
  current_section: null,
  sections_completed: 5,
  sections_total: 5,
  estimated_time_remaining_seconds: null,
  error_message: null,
  result_document_id: 99,
  result_document_uuid: "doc-uuid-999",
  result_storage_key: "generated/doc-99.docx",
  file_size_bytes: 1024000,
  generation_duration_ms: 45000,
};

const mockFailedJob: GenerationJob = {
  job_id: "job-fail-789",
  status: "failed",
  progress_percent: 30,
  current_section: null,
  sections_completed: 1,
  sections_total: 5,
  estimated_time_remaining_seconds: null,
  error_message: "Generation timeout exceeded",
  result_document_id: null,
  result_document_uuid: null,
  result_storage_key: null,
  file_size_bytes: null,
  generation_duration_ms: null,
};

const mockGeneratedDoc: GeneratedDocument = {
  id: 100,
  document_uuid: "gen-doc-uuid-100",
  title: "User Requirements Specification — Module X",
  document_type: "URS",
  current_status: "Draft",
  content_status: "pending_review",
  template_name: "URS Master Template v2",
  generated_at: "2024-06-15T14:00:00Z",
  generation_duration_ms: 45000,
};

const mockApprovedDoc: GeneratedDocument = {
  id: 101,
  document_uuid: "gen-doc-uuid-101",
  title: "SOP — Lab Equipment Maintenance",
  document_type: "SOP",
  current_status: "Review",
  content_status: "approved",
  template_name: "SOP Template",
  generated_at: "2024-06-10T09:00:00Z",
  generation_duration_ms: 30000,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
  useDocumentGeneratorStore.setState({
    templates: [],
    selectedTemplate: null,
    templateAnalysis: null,
    templatesTotal: 0,
    activeJobs: [],
    generatedDocuments: [],
    generatedDocumentsTotal: 0,
    currentProvenance: null,
    crossReferences: [],
    isRegistering: false,
    isGenerating: false,
    isLoading: false,
    error: null,
    pollingIntervalId: null,
  });
}

// ---------------------------------------------------------------------------
// Tests: TemplateRegistrationPanel
// ---------------------------------------------------------------------------

describe("TemplateRegistrationPanel", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    mockedGet.mockResolvedValue({ items: [], total: 0 });
    mockedPost.mockResolvedValue({ job_id: "new-job-123", status: "pending" });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the registration form with all required fields", () => {
    render(<TemplateRegistrationPanel />);

    expect(screen.getByLabelText("Document ID")).toBeDefined();
    expect(screen.getByLabelText("Document Version ID")).toBeDefined();
    expect(screen.getByLabelText("Template Name")).toBeDefined();
    expect(screen.getByLabelText("Document Type Target")).toBeDefined();
    expect(screen.getByRole("button", { name: /register template/i })).toBeDefined();
  });

  it("submit button is disabled when required fields are empty", () => {
    render(<TemplateRegistrationPanel />);

    const submitBtn = screen.getByRole("button", { name: /register template/i });
    expect(submitBtn).toHaveProperty("disabled", true);
  });

  it("submit button is enabled when all required fields are filled", () => {
    render(<TemplateRegistrationPanel />);

    fireEvent.change(screen.getByLabelText("Document ID"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Document Version ID"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Template Name"), { target: { value: "My Template" } });

    const submitBtn = screen.getByRole("button", { name: /register template/i });
    expect(submitBtn).toHaveProperty("disabled", false);
  });

  it("calls registerTemplate store action on form submit", async () => {
    render(<TemplateRegistrationPanel />);

    fireEvent.change(screen.getByLabelText("Document ID"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Document Version ID"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Template Name"), { target: { value: "URS Template" } });

    const form = screen.getByRole("form", { name: /template registration form/i });
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/api/documents/templates/register",
        {
          document_id: 10,
          document_version_id: 20,
          template_name: "URS Template",
          document_type_target: "URS",
        },
        { changeReason: "Register new document template for AI generation" },
      );
    });
  });

  it("shows success message after successful registration", async () => {
    render(<TemplateRegistrationPanel />);

    fireEvent.change(screen.getByLabelText("Document ID"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Document Version ID"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Template Name"), { target: { value: "URS Template" } });

    const form = screen.getByRole("form", { name: /template registration form/i });
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(screen.getByRole("status")).toBeDefined();
      expect(screen.getByText(/template registration started/i)).toBeDefined();
    });
  });

  it("shows error message when registration fails", async () => {
    mockedPost.mockRejectedValueOnce(new Error("Network error"));

    render(<TemplateRegistrationPanel />);

    fireEvent.change(screen.getByLabelText("Document ID"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Document Version ID"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Template Name"), { target: { value: "URS Template" } });

    const form = screen.getByRole("form", { name: /template registration form/i });
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: GenerationSetupPanel
// ---------------------------------------------------------------------------

describe("GenerationSetupPanel", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    // Provide templates for the selector
    mockedGet.mockResolvedValue({ items: [mockTemplate, mockTemplate2], total: 2 });
    mockedPost.mockResolvedValue({ job_id: "gen-job-001", status: "pending" });
    useDocumentGeneratorStore.setState({
      templates: [mockTemplate, mockTemplate2],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the generation form with all fields", () => {
    render(<GenerationSetupPanel />);

    expect(screen.getByLabelText(/template/i)).toBeDefined();
    expect(screen.getByLabelText(/document title/i)).toBeDefined();
    expect(screen.getByLabelText(/generation instructions/i)).toBeDefined();
    expect(screen.getByLabelText(/reference document ids/i)).toBeDefined();
    expect(screen.getByLabelText(/output folder path/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /generate document/i })).toBeDefined();
  });

  it("shows validation errors when submitting with empty required fields", async () => {
    render(<GenerationSetupPanel />);

    const form = screen.getByRole("form", { name: /generation setup form/i });
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(screen.getByText("Please select a template")).toBeDefined();
      expect(screen.getByText("Title is required")).toBeDefined();
      expect(screen.getByText("Generation instructions are required")).toBeDefined();
      expect(screen.getByText("Output folder path is required")).toBeDefined();
    });
  });

  it("calls startGeneration with correct payload on valid submission", async () => {
    render(<GenerationSetupPanel />);

    // Fill in the form
    fireEvent.change(screen.getByLabelText(/template/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/document title/i), {
      target: { value: "My URS Document" },
    });
    fireEvent.change(screen.getByLabelText(/generation instructions/i), {
      target: { value: "Generate a comprehensive URS for Module X" },
    });
    fireEvent.change(screen.getByLabelText(/output folder path/i), {
      target: { value: "/documents/generated/urs" },
    });

    const form = screen.getByRole("form", { name: /generation setup form/i });
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/api/documents/generate-from-template",
        {
          template_id: 1,
          title: "My URS Document",
          generation_instructions: "Generate a comprehensive URS for Module X",
          output_folder_path: "/documents/generated/urs",
        },
        { changeReason: "Template-based document generation initiated" },
      );
    });
  });

  it("includes reference_document_ids when provided", async () => {
    render(<GenerationSetupPanel />);

    fireEvent.change(screen.getByLabelText(/template/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/document title/i), {
      target: { value: "My URS" },
    });
    fireEvent.change(screen.getByLabelText(/generation instructions/i), {
      target: { value: "Generate URS content" },
    });
    fireEvent.change(screen.getByLabelText(/reference document ids/i), {
      target: { value: "12, 34, 56" },
    });
    fireEvent.change(screen.getByLabelText(/output folder path/i), {
      target: { value: "/output" },
    });

    const form = screen.getByRole("form", { name: /generation setup form/i });
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/api/documents/generate-from-template",
        expect.objectContaining({
          reference_document_ids: [12, 34, 56],
        }),
        expect.any(Object),
      );
    });
  });

  it("shows validation error for invalid reference document IDs", async () => {
    render(<GenerationSetupPanel />);

    fireEvent.change(screen.getByLabelText(/template/i), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText(/document title/i), {
      target: { value: "My URS" },
    });
    fireEvent.change(screen.getByLabelText(/generation instructions/i), {
      target: { value: "Generate content" },
    });
    fireEvent.change(screen.getByLabelText(/reference document ids/i), {
      target: { value: "abc, xyz" },
    });
    fireEvent.change(screen.getByLabelText(/output folder path/i), {
      target: { value: "/output" },
    });

    const form = screen.getByRole("form", { name: /generation setup form/i });
    await act(async () => {
      fireEvent.submit(form);
    });

    await waitFor(() => {
      expect(
        screen.getByText(/reference document ids must be positive integers/i),
      ).toBeDefined();
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: JobProgressMonitor
// ---------------------------------------------------------------------------

describe("JobProgressMonitor", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    mockedGet.mockResolvedValue(mockProcessingJob);
  });

  afterEach(() => {
    cleanup();
  });

  it("shows empty state when no active jobs", () => {
    render(<JobProgressMonitor />);

    expect(screen.getByText(/no active generation jobs/i)).toBeDefined();
  });

  it("renders progress bar with correct percentage for processing job", () => {
    useDocumentGeneratorStore.setState({ activeJobs: [mockProcessingJob] });

    render(<JobProgressMonitor />);

    const progressBar = screen.getByRole("progressbar");
    expect(progressBar.getAttribute("aria-valuenow")).toBe("45");
    expect(progressBar.getAttribute("aria-valuemin")).toBe("0");
    expect(progressBar.getAttribute("aria-valuemax")).toBe("100");
  });

  it("displays status badge for processing job", () => {
    useDocumentGeneratorStore.setState({ activeJobs: [mockProcessingJob] });

    render(<JobProgressMonitor />);

    expect(screen.getByText("Processing")).toBeDefined();
  });

  it("displays current section name", () => {
    useDocumentGeneratorStore.setState({ activeJobs: [mockProcessingJob] });

    render(<JobProgressMonitor />);

    expect(screen.getByText("Section 2: Scope")).toBeDefined();
  });

  it("displays sections completed / total", () => {
    useDocumentGeneratorStore.setState({ activeJobs: [mockProcessingJob] });

    render(<JobProgressMonitor />);

    expect(screen.getByText("2 / 5")).toBeDefined();
  });

  it("displays estimated time remaining for processing job", () => {
    useDocumentGeneratorStore.setState({ activeJobs: [mockProcessingJob] });

    render(<JobProgressMonitor />);

    expect(screen.getByText("2m")).toBeDefined();
  });

  it("shows completed status badge and document ID for completed job", () => {
    useDocumentGeneratorStore.setState({ activeJobs: [mockCompletedJob] });

    render(<JobProgressMonitor />);

    expect(screen.getByText("Completed")).toBeDefined();
    expect(screen.getByText(/document generated successfully.*id: 99/i)).toBeDefined();
  });

  it("shows error message for failed job", () => {
    useDocumentGeneratorStore.setState({ activeJobs: [mockFailedJob] });

    render(<JobProgressMonitor />);

    expect(screen.getByText("Failed")).toBeDefined();
    expect(screen.getByText("Generation timeout exceeded")).toBeDefined();
  });

  it("renders multiple jobs simultaneously", () => {
    useDocumentGeneratorStore.setState({
      activeJobs: [mockProcessingJob, mockCompletedJob, mockFailedJob],
    });

    render(<JobProgressMonitor />);

    const progressBars = screen.getAllByRole("progressbar");
    expect(progressBars.length).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// Tests: ReviewWorkflowPanel
// ---------------------------------------------------------------------------

describe("ReviewWorkflowPanel", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    mockedGet.mockResolvedValue({ items: [mockGeneratedDoc, mockApprovedDoc], total: 2 });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the review workflow heading and filter controls", async () => {
    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    expect(screen.getByText("Review Workflow")).toBeDefined();
    expect(screen.getByLabelText("Status")).toBeDefined();
    expect(screen.getByLabelText("Document Type")).toBeDefined();
    expect(screen.getByLabelText("From Date")).toBeDefined();
    expect(screen.getByLabelText("To Date")).toBeDefined();
  });

  it("fetches generated documents on mount", async () => {
    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        expect.stringContaining("/api/documents/generated"),
      );
    });
  });

  it("renders document list with titles and status badges", async () => {
    mockedGet.mockResolvedValue({ items: [mockGeneratedDoc, mockApprovedDoc], total: 2 });

    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    await waitFor(() => {
      expect(screen.getByText(/User Requirements Specification/)).toBeDefined();
      expect(screen.getByText(/Lab Equipment Maintenance/)).toBeDefined();
      // Status badges (use aria-label to distinguish from filter options)
      expect(screen.getByLabelText("Status: Pending Review")).toBeDefined();
      expect(screen.getByLabelText("Status: Approved")).toBeDefined();
    });
  });

  it("shows Review button only for pending_review documents", async () => {
    mockedGet.mockResolvedValue({ items: [mockGeneratedDoc, mockApprovedDoc], total: 2 });

    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    await waitFor(() => {
      // Only one Review button for the pending_review document
      const reviewButtons = screen.getAllByRole("button", { name: /review/i });
      expect(reviewButtons.length).toBe(1);
    });
  });

  it("clicking Review shows approve/reject actions with comment textarea", async () => {
    mockedGet.mockResolvedValue({ items: [mockGeneratedDoc], total: 1 });

    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /review/i })).toBeDefined();
    });

    const reviewBtn = screen.getByRole("button", { name: /review/i });
    fireEvent.click(reviewBtn);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /approve/i })).toBeDefined();
      expect(screen.getByRole("button", { name: /reject/i })).toBeDefined();
      expect(screen.getByPlaceholderText(/enter review comments/i)).toBeDefined();
    });
  });

  it("calls reviewDocument with approve action", async () => {
    mockedGet.mockResolvedValue({ items: [mockGeneratedDoc], total: 1 });

    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /review/i })).toBeDefined();
    });

    // Open review actions
    const reviewBtn = screen.getByRole("button", { name: /review/i });
    fireEvent.click(reviewBtn);

    // Click approve
    const approveBtn = await screen.findByRole("button", { name: /approve/i });

    mockedPost.mockResolvedValueOnce({
      document_id: 100,
      current_status: "Review",
      content_status: "approved",
    });

    await act(async () => {
      fireEvent.click(approveBtn);
    });

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/api/documents/100/review",
        { action: "approve", reviewer_comments: undefined },
        expect.objectContaining({ changeReason: expect.stringContaining("Approved") }),
      );
    });
  });

  it("calls reviewDocument with reject action and comment", async () => {
    mockedGet.mockResolvedValue({ items: [mockGeneratedDoc], total: 1 });

    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /review/i })).toBeDefined();
    });

    // Open review actions
    const reviewBtn = screen.getByRole("button", { name: /review/i });
    fireEvent.click(reviewBtn);

    // Enter comment
    const textarea = await screen.findByPlaceholderText(/enter review comments/i);
    fireEvent.change(textarea, { target: { value: "Needs more detail in Section 3" } });

    // Click reject
    const rejectBtn = screen.getByRole("button", { name: /reject/i });

    mockedPost.mockResolvedValueOnce({
      document_id: 100,
      current_status: "Draft",
      content_status: "rejected",
    });

    await act(async () => {
      fireEvent.click(rejectBtn);
    });

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/api/documents/100/review",
        { action: "reject", reviewer_comments: "Needs more detail in Section 3" },
        expect.objectContaining({ changeReason: expect.stringContaining("Rejected") }),
      );
    });
  });

  it("shows error when rejecting without a comment", async () => {
    mockedGet.mockResolvedValue({ items: [mockGeneratedDoc], total: 1 });

    await act(async () => {
      render(<ReviewWorkflowPanel />);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /review/i })).toBeDefined();
    });

    // Open review actions
    const reviewBtn = screen.getByRole("button", { name: /review/i });
    fireEvent.click(reviewBtn);

    // Click reject without entering a comment
    const rejectBtn = await screen.findByRole("button", { name: /reject/i });
    await act(async () => {
      fireEvent.click(rejectBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/comment is required when rejecting/i)).toBeDefined();
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: DocumentGeneratorPage (integration)
// ---------------------------------------------------------------------------

describe("DocumentGeneratorPage", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    mockedGet.mockResolvedValue({ items: [], total: 0 });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders with page heading and description", () => {
    render(<DocumentGeneratorPage />);

    expect(screen.getByText("AI Document Generator")).toBeDefined();
    expect(
      screen.getByText(/generate regulatory documents from master templates/i),
    ).toBeDefined();
  });

  it("renders tab navigation with all four tabs", () => {
    render(<DocumentGeneratorPage />);

    const tablist = screen.getByRole("tablist", { name: /document generator sections/i });
    expect(tablist).toBeDefined();

    expect(screen.getByRole("tab", { name: "Templates" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "Generate" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "Review" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "Provenance" })).toBeDefined();
  });

  it("Templates tab is selected by default", () => {
    render(<DocumentGeneratorPage />);

    const templatesTab = screen.getByRole("tab", { name: "Templates" });
    expect(templatesTab.getAttribute("aria-selected")).toBe("true");
  });

  it("clicking Generate tab switches to generation panel", () => {
    render(<DocumentGeneratorPage />);

    const generateTab = screen.getByRole("tab", { name: "Generate" });
    fireEvent.click(generateTab);

    expect(generateTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("New Generation")).toBeDefined();
  });

  it("clicking Review tab switches to review panel", () => {
    render(<DocumentGeneratorPage />);

    const reviewTab = screen.getByRole("tab", { name: "Review" });
    fireEvent.click(reviewTab);

    expect(reviewTab.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Review Workflow")).toBeDefined();
  });
});
