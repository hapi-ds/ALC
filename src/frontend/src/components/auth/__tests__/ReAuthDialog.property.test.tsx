import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import * as fc from "fast-check";
import { render, waitFor, within, cleanup, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import React from "react";

/**
 * Feature: auth-session-frontend, Property 11: Re-auth lockout after 5 consecutive failures
 *
 * Validates: Requirements 7.6
 *
 * For any sequence of N consecutive failed re-authentication attempts where N >= 5,
 * the system SHALL lock the session and redirect to the login page on the 5th failure.
 * For N < 5, the dialog SHALL remain open and allow retry.
 */

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock the auth store
const mockReAuthenticate = vi.fn();
const mockClearSession = vi.fn();

vi.mock("@/stores/authStore", () => ({
  useAuthStore: () => ({
    user: { id: 1, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["user"] },
    reAuthenticate: mockReAuthenticate,
    clearSession: mockClearSession,
  }),
}));

import { ReAuthDialog } from "../ReAuthDialog";

describe("Feature: auth-session-frontend, Property 11: Re-auth lockout after 5 consecutive failures", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockReAuthenticate.mockResolvedValue({ verified: false });
  });

  it("locks session and redirects on N >= 5 failures, keeps dialog open for N < 5", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 10 }),
        async (n) => {
          cleanup();
          mockNavigate.mockReset();
          mockClearSession.mockReset();
          mockReAuthenticate.mockReset();
          mockReAuthenticate.mockResolvedValue({ verified: false });

          const onSuccess = vi.fn();
          const onCancel = vi.fn();

          const { container, unmount } = render(
            <MemoryRouter>
              <ReAuthDialog open={true} onSuccess={onSuccess} onCancel={onCancel} />
            </MemoryRouter>
          );

          const dialog = within(container);
          const attemptsToMake = Math.min(n, 5);

          for (let i = 0; i < attemptsToMake; i++) {
            const passwordInput = dialog.getByLabelText("Password");

            // Use fireEvent for speed (avoids character-by-character typing)
            fireEvent.change(passwordInput, { target: { value: "wrongpassword" } });

            const form = container.querySelector("form")!;
            fireEvent.submit(form);

            // Wait for the async reAuthenticate call to resolve
            await waitFor(() => {
              expect(mockReAuthenticate).toHaveBeenCalledTimes(i + 1);
            });

            // After the 5th failure, the component locks and navigates away
            if (i + 1 >= 5) {
              break;
            }
          }

          if (n >= 5) {
            // Session should be locked and navigate to /login
            await waitFor(() => {
              expect(mockClearSession).toHaveBeenCalledWith("locked");
            });
            expect(mockNavigate).toHaveBeenCalledWith("/login", { replace: true });
          } else {
            // Dialog should remain open, no lockout
            expect(mockClearSession).not.toHaveBeenCalled();
            expect(mockNavigate).not.toHaveBeenCalled();
            // Dialog is still visible
            expect(dialog.getByRole("dialog", { hidden: true })).toBeInTheDocument();
          }

          // onSuccess should never be called for failed attempts
          expect(onSuccess).not.toHaveBeenCalled();

          unmount();
        }
      ),
      { numRuns: 30 }
    );
  }, 30000);
});
