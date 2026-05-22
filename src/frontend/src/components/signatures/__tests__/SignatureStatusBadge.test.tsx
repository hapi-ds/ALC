/**
 * Unit tests for SignatureStatusBadge
 *
 * Tests cover:
 * - Returns null (renders nothing) when signatureCount is 0
 * - Renders pen-tool icon and count when signatureCount > 0
 * - Displays "99+" when signatureCount > 99
 * - Has correct aria-label (e.g., "2 signatures applied")
 * - Shows tooltip content on hover/focus when latestSigner is provided
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4
 *
 * NOTE: This test file does NOT make any real backend API calls.
 * All API interactions are fully mocked via vi.mock("@/lib/apiClient").
 */

import { describe, it, expect, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { SignatureStatusBadge } from "../SignatureStatusBadge";

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
// Tests
// ---------------------------------------------------------------------------

describe("SignatureStatusBadge", () => {
  afterEach(() => {
    cleanup();
  });

  it("returns null (renders nothing) when signatureCount is 0", () => {
    const { container } = render(
      <SignatureStatusBadge documentUuid="doc-123" signatureCount={0} />
    );

    expect(container.innerHTML).toBe("");
  });

  it("renders pen-tool icon and count when signatureCount > 0", () => {
    render(
      <SignatureStatusBadge documentUuid="doc-123" signatureCount={3} />
    );

    // The badge should be rendered with the count text
    expect(screen.getByText("3")).toBeInTheDocument();

    // The pen-tool icon is rendered (aria-hidden SVG)
    const badge = screen.getByLabelText("3 signatures applied");
    expect(badge).toBeInTheDocument();
  });

  it('displays "99+" when signatureCount > 99', () => {
    render(
      <SignatureStatusBadge documentUuid="doc-123" signatureCount={150} />
    );

    expect(screen.getByText("99+")).toBeInTheDocument();
  });

  it('has correct aria-label (e.g., "2 signatures applied")', () => {
    render(
      <SignatureStatusBadge documentUuid="doc-123" signatureCount={2} />
    );

    expect(screen.getByLabelText("2 signatures applied")).toBeInTheDocument();
  });

  it("has correct aria-label for singular signature", () => {
    render(
      <SignatureStatusBadge documentUuid="doc-123" signatureCount={1} />
    );

    expect(screen.getByLabelText("1 signature applied")).toBeInTheDocument();
  });

  it("has correct aria-label when count > 99", () => {
    render(
      <SignatureStatusBadge documentUuid="doc-123" signatureCount={200} />
    );

    expect(screen.getByLabelText("99+ signatures applied")).toBeInTheDocument();
  });

  it("shows tooltip content on hover/focus when latestSigner is provided", () => {
    render(
      <SignatureStatusBadge
        documentUuid="doc-123"
        signatureCount={2}
        latestSigner={{
          displayName: "Jane Smith",
          transition: "Review\u2192Approved",
          signedAt: "2024-06-15T14:00:00Z",
        }}
      />
    );

    // Tooltip should exist in the DOM (hidden by CSS until hover/focus)
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();

    // Tooltip content should contain signer name and transition
    expect(tooltip.textContent).toContain("Jane Smith");
    expect(tooltip.textContent).toContain("Review\u2192Approved");
  });

  it("does not render tooltip when latestSigner is not provided", () => {
    render(
      <SignatureStatusBadge documentUuid="doc-123" signatureCount={5} />
    );

    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
