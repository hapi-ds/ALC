/**
 * Unit tests for SignatureRecordsPanel
 *
 * Tests cover:
 * - Empty state rendering with correct heading
 * - Records rendering (signer, transition, reason, timestamp, truncated hash)
 * - Loading skeleton placeholders
 * - Error state with "Retry" button
 * - Retry button calls fetchSignatureRecords
 * - Default expanded when records exist
 * - Default collapsed when records are empty
 *
 * Requirements: 6.1, 6.2, 6.4, 6.5, 6.6
 *
 * NOTE: This test file does NOT make any real backend API calls.
 * All API interactions are fully mocked via vi.mock("@/lib/apiClient").
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { SignatureRecordsPanel } from "../SignatureRecordsPanel";
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

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockRecords: SignatureRecordResponse[] = [
  {
    id: 1,
    document_uuid: "doc-123",
    signer_user_id: 42,
    transition: "Draft\u2192Review",
    reason: "Author: Initial submission",
    signed_at: "2024-06-10T08:30:00Z",
    signature_hash:
      "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
  },
  {
    id: 2,
    document_uuid: "doc-123",
    signer_user_id: 7,
    transition: "Review\u2192Approved",
    reason: "Approval: Final QA sign-off",
    signed_at: "2024-06-15T14:00:00Z",
    signature_hash:
      "1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SignatureRecordsPanel", () => {
  beforeEach(() => {
    useSignatureStore.getState().reset();
    // Mock fetchSignatureRecords to prevent real API calls
    useSignatureStore.setState({
      fetchSignatureRecords: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders "Electronic Signatures (0)" with empty state message when no records exist', () => {
    useSignatureStore.setState({
      records: { "doc-123": [] },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    expect(screen.getByText("Electronic Signatures (0)")).toBeInTheDocument();

    // Expand the section to see the empty state message
    const headerButton = screen.getByRole("button", {
      name: /electronic signatures/i,
    });
    fireEvent.click(headerButton);

    expect(
      screen.getByText(
        "No electronic signatures have been applied to this document."
      )
    ).toBeInTheDocument();
  });

  it("renders records correctly with signer, transition, reason, timestamp, and truncated hash", () => {
    useSignatureStore.setState({
      records: { "doc-123": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    // Records should be visible (section auto-expands when records exist)
    expect(screen.getByText("Electronic Signatures (2)")).toBeInTheDocument();

    // Signer user IDs (fallback format)
    expect(screen.getByText("User #42")).toBeInTheDocument();
    expect(screen.getByText("User #7")).toBeInTheDocument();

    // Transitions
    expect(screen.getByText("Draft\u2192Review")).toBeInTheDocument();
    expect(screen.getByText("Review\u2192Approved")).toBeInTheDocument();

    // Reasons
    expect(screen.getByText("Author: Initial submission")).toBeInTheDocument();
    expect(screen.getByText("Approval: Final QA sign-off")).toBeInTheDocument();

    // Truncated hashes (first 16 chars + ellipsis)
    expect(screen.getByText("abcdef1234567890\u2026")).toBeInTheDocument();
    expect(screen.getByText("1111222233334444\u2026")).toBeInTheDocument();
  });

  it("shows loading skeletons while isLoadingRecords is true", () => {
    useSignatureStore.setState({
      records: {},
      isLoadingRecords: true,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    // Expand the section (collapsed by default when no records loaded yet)
    const headerButton = screen.getByRole("button", {
      name: /electronic signatures/i,
    });
    fireEvent.click(headerButton);

    // Skeleton placeholders should be visible
    expect(
      screen.getByLabelText("Loading signature records")
    ).toBeInTheDocument();
  });

  it('shows error state with "Retry" button when recordsError is set', () => {
    useSignatureStore.setState({
      records: { "doc-123": [] },
      isLoadingRecords: false,
      recordsError: "Failed to fetch records",
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    // Expand the section
    const headerButton = screen.getByRole("button", {
      name: /electronic signatures/i,
    });
    fireEvent.click(headerButton);

    expect(
      screen.getByText("Unable to load signature records.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it('clicking "Retry" calls fetchSignatureRecords', () => {
    const mockFetch = vi.fn();
    useSignatureStore.setState({
      records: { "doc-123": [] },
      isLoadingRecords: false,
      recordsError: "Network error",
      fetchSignatureRecords: mockFetch,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    // Expand the section
    const headerButton = screen.getByRole("button", {
      name: /electronic signatures/i,
    });
    fireEvent.click(headerButton);

    const retryButton = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retryButton);

    expect(mockFetch).toHaveBeenCalledWith("doc-123");
  });

  it("section is expanded by default when records exist", () => {
    useSignatureStore.setState({
      records: { "doc-123": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    // The content should be visible without clicking
    expect(screen.getByText("User #42")).toBeInTheDocument();
  });

  it("section is collapsed by default when records are empty", () => {
    useSignatureStore.setState({
      records: { "doc-123": [] },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    // The empty state message should NOT be visible until expanded
    expect(
      screen.queryByText(
        "No electronic signatures have been applied to this document."
      )
    ).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Verification UI tests (Requirements: 12.1, 12.3, 12.4, 11.12)
  // -------------------------------------------------------------------------

  it('"Verify" button is visible when records exist (recordCount > 0)', () => {
    useSignatureStore.setState({
      records: { "doc-123": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    expect(screen.getByRole("button", { name: /verify/i })).toBeInTheDocument();
  });

  it('"Verify" button is NOT visible when records are empty (recordCount === 0)', () => {
    useSignatureStore.setState({
      records: { "doc-123": [] },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    expect(screen.queryByRole("button", { name: /verify/i })).not.toBeInTheDocument();
  });

  it('renders green "All signatures valid" banner when verifyResult.is_valid === true', () => {
    useSignatureStore.setState({
      records: { "doc-123": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
      verifyResult: {
        is_valid: true,
        signature_count: 2,
        signatures: [],
        tampered_from_index: -1,
      },
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    expect(screen.getByText("All signatures valid")).toBeInTheDocument();
  });

  it('renders red "Document integrity compromised" banner when verifyResult.is_valid === false', () => {
    useSignatureStore.setState({
      records: { "doc-123": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
      verifyResult: {
        is_valid: false,
        signature_count: 2,
        signatures: [],
        tampered_from_index: 1,
      },
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    expect(screen.getByText("Document integrity compromised")).toBeInTheDocument();
  });

  it('shows "Invalid" badge on tampered records when verifyResult.tampered_from_index >= 0', () => {
    // tampered_from_index = 1 means the second record (in ascending order) is tampered.
    // mockRecords[0] signed_at = "2024-06-10T08:30:00Z" (index 0 ascending — valid)
    // mockRecords[1] signed_at = "2024-06-15T14:00:00Z" (index 1 ascending — tampered)
    useSignatureStore.setState({
      records: { "doc-123": mockRecords },
      isLoadingRecords: false,
      recordsError: null,
      verifyResult: {
        is_valid: false,
        signature_count: 2,
        signatures: [],
        tampered_from_index: 1,
      },
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    // Only one record should have the "Invalid" badge (the one at ascending index >= 1)
    const invalidBadges = screen.getAllByText("Invalid");
    expect(invalidBadges).toHaveLength(1);
  });

  it("displays certificate subject when record has certificate_subject set", () => {
    const recordsWithCert: SignatureRecordResponse[] = [
      {
        id: 3,
        document_uuid: "doc-123",
        signer_user_id: 10,
        transition: "Draft\u2192Review",
        reason: "Author: Cert test",
        signed_at: "2024-07-01T10:00:00Z",
        signature_hash:
          "ccccddddeeeeffffccccddddeeeeffffccccddddeeeeffffccccddddeeeefffff",
        certificate_subject: "CN=John Doe, O=Acme Corp",
      },
    ];

    useSignatureStore.setState({
      records: { "doc-123": recordsWithCert },
      isLoadingRecords: false,
      recordsError: null,
    });

    render(<SignatureRecordsPanel documentUuid="doc-123" />);

    expect(screen.getByText("Certificate:")).toBeInTheDocument();
    expect(screen.getByText("CN=John Doe, O=Acme Corp")).toBeInTheDocument();
  });
});
