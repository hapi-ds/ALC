/**
 * Unit tests for SignaturesPage
 *
 * Tests cover:
 * - Empty state rendering when no records exist
 * - Records display with document UUID, signer, transition, reason, timestamp, truncated hash
 * - Pagination controls (Previous/Next buttons, page info, disabled states)
 * - Filter inputs (document UUID, transition dropdown, date range pickers)
 * - Sort indicators (clickable column headers for signed_at, signer_user_id, document_uuid)
 * - Loading state (skeleton placeholders when isLoadingRecords is true)
 * - Error state (error message with retry button)
 *
 * Requirements: 8.1, 8.3, 8.4, 8.5, 8.6, 8.7
 *
 * NOTE: This test file does NOT make any real backend API calls.
 * All API interactions are fully mocked via vi.mock("@/lib/apiClient").
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { SignaturesPage } from "../SignaturesPage";
import { useSignatureStore } from "@/stores/signatureStore";
import type { SignatureRecordResponse } from "@/types/signature";

// ---------------------------------------------------------------------------
// Mocks — no real API calls are made; all backend interactions are mocked.
// ---------------------------------------------------------------------------

vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string) {
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

vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(),
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 1 },
      activeCompanyId: 1,
    }),
    setState: vi.fn(),
  },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockRecords: SignatureRecordResponse[] = [
  {
    id: 1,
    document_uuid: "doc-aaa-111",
    signer_user_id: 42,
    transition: "Draft\u2192Review",
    reason: "Author: Initial submission",
    signed_at: "2024-06-10T08:30:00Z",
    signature_hash:
      "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
  },
  {
    id: 2,
    document_uuid: "doc-bbb-222",
    signer_user_id: 7,
    transition: "Review\u2192Approved",
    reason: "Approval: Final QA sign-off",
    signed_at: "2024-06-15T14:00:00Z",
    signature_hash:
      "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
  },
  {
    id: 3,
    document_uuid: "doc-ccc-333",
    signer_user_id: 15,
    transition: "Draft\u2192Review",
    reason: "Review: Peer review completed",
    signed_at: "2024-06-12T10:00:00Z",
    signature_hash:
      "ffffeeeeddddccccbbbbaaaa00009999888877776666555544443333222211110000",
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SignaturesPage", () => {
  beforeEach(() => {
    useSignatureStore.getState().reset();
    useSignatureStore.setState({
      fetchSignatureRecords: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Empty state
  // -------------------------------------------------------------------------

  it("renders empty state message when no records exist in the store", () => {
    useSignatureStore.setState({
      records: {},
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignaturesPage />);

    expect(
      screen.getByText("No electronic signatures found.")
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Signatures are created when workflow transitions require signing."
      )
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Records display
  // -------------------------------------------------------------------------

  it("renders records with document UUID, signer, transition, reason, timestamp, and truncated hash", () => {
    useSignatureStore.setState({
      records: { "doc-aaa-111": [mockRecords[0]], "doc-bbb-222": [mockRecords[1]] },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignaturesPage />);

    // Document UUIDs
    expect(screen.getByText("doc-aaa-111")).toBeInTheDocument();
    expect(screen.getByText("doc-bbb-222")).toBeInTheDocument();

    // Signer user IDs
    expect(screen.getByText("User #42")).toBeInTheDocument();
    expect(screen.getByText("User #7")).toBeInTheDocument();

    // Transitions (appear in both table cells and filter dropdown, so use getAllByText)
    expect(screen.getAllByText("Draft\u2192Review").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Review\u2192Approved").length).toBeGreaterThanOrEqual(1);

    // Reasons
    expect(screen.getByText("Author: Initial submission")).toBeInTheDocument();
    expect(screen.getByText("Approval: Final QA sign-off")).toBeInTheDocument();

    // Truncated hashes (first 16 chars + ellipsis)
    expect(screen.getByText("abcdef1234567890\u2026")).toBeInTheDocument();
    expect(screen.getByText("1111222233334444\u2026")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Pagination controls
  // -------------------------------------------------------------------------

  it('shows "Previous" and "Next" buttons and page info when records exist', () => {
    useSignatureStore.setState({
      records: { "doc-aaa-111": [mockRecords[0]] },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignaturesPage />);

    expect(screen.getByRole("button", { name: /previous/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /next/i })).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 1")).toBeInTheDocument();
  });

  it("disables Previous button on page 1", () => {
    useSignatureStore.setState({
      records: { "doc-aaa-111": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignaturesPage />);

    const prevButton = screen.getByRole("button", { name: /previous/i });
    expect(prevButton).toBeDisabled();
  });

  it("disables Next button on last page", () => {
    // With 3 records and page size 25, there's only 1 page
    useSignatureStore.setState({
      records: { "doc-aaa-111": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignaturesPage />);

    const nextButton = screen.getByRole("button", { name: /next/i });
    expect(nextButton).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // 4. Filter inputs
  // -------------------------------------------------------------------------

  it("renders document UUID input, transition dropdown, and date range pickers", () => {
    useSignatureStore.setState({
      records: { "doc-aaa-111": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignaturesPage />);

    // Document UUID text input (use role to disambiguate from sort button aria-label)
    const uuidInput = screen.getByRole("textbox", { name: /document uuid/i });
    expect(uuidInput).toBeInTheDocument();
    expect(uuidInput).toHaveAttribute("type", "text");

    // Transition dropdown (select element)
    const transitionSelect = screen.getByRole("combobox", { name: /transition/i });
    expect(transitionSelect).toBeInTheDocument();

    // Date range pickers (use exact label text to avoid matching "to" in other aria-labels)
    const fromInput = screen.getByLabelText("From");
    expect(fromInput).toBeInTheDocument();
    expect(fromInput).toHaveAttribute("type", "date");

    const toInput = screen.getByLabelText("To");
    expect(toInput).toBeInTheDocument();
    expect(toInput).toHaveAttribute("type", "date");
  });

  // -------------------------------------------------------------------------
  // 5. Sort indicators
  // -------------------------------------------------------------------------

  it("renders clickable column headers for signed_at, signer_user_id, and document_uuid", () => {
    useSignatureStore.setState({
      records: { "doc-aaa-111": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignaturesPage />);

    // Sort buttons in table headers
    const documentSortBtn = screen.getByRole("button", { name: /sort by document uuid/i });
    expect(documentSortBtn).toBeInTheDocument();

    const signerSortBtn = screen.getByRole("button", { name: /sort by signer/i });
    expect(signerSortBtn).toBeInTheDocument();

    const signedAtSortBtn = screen.getByRole("button", { name: /sort by signed date/i });
    expect(signedAtSortBtn).toBeInTheDocument();

    // Clicking a sort button should not throw
    fireEvent.click(documentSortBtn);
    fireEvent.click(signerSortBtn);
    fireEvent.click(signedAtSortBtn);
  });

  // -------------------------------------------------------------------------
  // 6. Loading state
  // -------------------------------------------------------------------------

  it("shows skeleton placeholders when isLoadingRecords is true and no records loaded", () => {
    useSignatureStore.setState({
      records: {},
      isLoadingRecords: true,
      recordsError: null,
    });

    render(<SignaturesPage />);

    expect(
      screen.getByLabelText("Loading signature records")
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Error state
  // -------------------------------------------------------------------------

  it("shows error message with retry button when recordsError is set", () => {
    useSignatureStore.setState({
      records: {},
      isLoadingRecords: false,
      recordsError: "Network error: Unable to reach the server.",
    });

    render(<SignaturesPage />);

    expect(
      screen.getByText("Unable to load signature records.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("clicking Retry button triggers re-fetch", () => {
    const mockFetch = vi.fn();
    useSignatureStore.setState({
      records: { "doc-aaa-111": [] },
      isLoadingRecords: false,
      recordsError: "Server error",
      fetchSignatureRecords: mockFetch,
    });

    render(<SignaturesPage />);

    const retryButton = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retryButton);

    expect(mockFetch).toHaveBeenCalledWith("doc-aaa-111");
  });
});
