import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import React from "react";

/**
 * Feature: auth-session-frontend, Property 3: Post-login redirect preserves requested URL
 *
 * Validates: Requirements 1.4
 *
 * For any valid URL path stored as a `redirect` query parameter on the login page,
 * a successful login SHALL navigate the user to that exact path. When no redirect
 * parameter is present, navigation SHALL go to the default landing page ("/").
 */

// Mock the auth store
const mockLogin = vi.fn();
vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn(() => ({
    isAuthenticated: false,
    login: mockLogin,
  })),
}));

// Mock react-router-dom navigation with a mutable search params holder
const mockNavigate = vi.fn();
const searchParamsHolder = { current: new URLSearchParams() };

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [searchParamsHolder.current, vi.fn()],
  };
});

import { LoginPage } from "../LoginPage";

describe("Feature: auth-session-frontend, Property 3: Post-login redirect preserves requested URL", () => {
  beforeEach(() => {
    mockLogin.mockReset();
    mockNavigate.mockReset();
    mockLogin.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  // Generator for valid URL paths: starts with "/" followed by path segments
  const urlPathArb = fc
    .array(
      fc.stringMatching(/^[a-zA-Z0-9_-]+$/u, { minLength: 1, maxLength: 12 }),
      { minLength: 1, maxLength: 4 }
    )
    .map((segments) => "/" + segments.join("/"));

  it("navigates to the redirect param value after successful login", async () => {
    await fc.assert(
      fc.asyncProperty(urlPathArb, async (redirectPath) => {
        cleanup();
        mockLogin.mockReset();
        mockNavigate.mockReset();
        mockLogin.mockResolvedValue(undefined);

        // Set up search params with the redirect value
        searchParamsHolder.current = new URLSearchParams(`redirect=${redirectPath}`);

        const user = userEvent.setup();

        render(
          <MemoryRouter>
            <LoginPage />
          </MemoryRouter>
        );

        const usernameInput = screen.getByLabelText("Username");
        const passwordInput = screen.getByLabelText("Password");
        const submitButton = screen.getByRole("button", { name: /sign in/i });

        // Fill in both fields with valid values
        await user.type(usernameInput, "testuser");
        await user.type(passwordInput, "testpass123");

        // Submit the form
        await user.click(submitButton);

        // Wait for login to resolve and navigation to occur
        await waitFor(() => {
          expect(mockLogin).toHaveBeenCalledWith("testuser", "testpass123");
        });

        await waitFor(() => {
          expect(mockNavigate).toHaveBeenCalledWith(redirectPath, { replace: true });
        });
      }),
      { numRuns: 100 }
    );
  }, 60000);

  it("navigates to '/' when no redirect param is present", async () => {
    await fc.assert(
      fc.asyncProperty(fc.constant(null), async () => {
        cleanup();
        mockLogin.mockReset();
        mockNavigate.mockReset();
        mockLogin.mockResolvedValue(undefined);

        // No redirect param
        searchParamsHolder.current = new URLSearchParams();

        const user = userEvent.setup();

        render(
          <MemoryRouter>
            <LoginPage />
          </MemoryRouter>
        );

        const usernameInput = screen.getByLabelText("Username");
        const passwordInput = screen.getByLabelText("Password");
        const submitButton = screen.getByRole("button", { name: /sign in/i });

        // Fill in both fields with valid values
        await user.type(usernameInput, "testuser");
        await user.type(passwordInput, "testpass123");

        // Submit the form
        await user.click(submitButton);

        // Wait for login to resolve and navigation to occur
        await waitFor(() => {
          expect(mockLogin).toHaveBeenCalledWith("testuser", "testpass123");
        });

        await waitFor(() => {
          expect(mockNavigate).toHaveBeenCalledWith("/", { replace: true });
        });
      }),
      { numRuns: 10 }
    );
  }, 30000);
});
