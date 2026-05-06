import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import React from "react";

/**
 * Feature: auth-session-frontend, Property 12: Password visibility toggle state
 *
 * Validates: Requirements 9.2, 9.3
 *
 * For any number N of toggle activations on the password visibility control,
 * the password field type SHALL be "text" when N is odd and "password" when N
 * is even (including N=0 for the initial masked state).
 */

// Mock the auth store
const mockLogin = vi.fn();
vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn(() => ({
    isAuthenticated: false,
    login: mockLogin,
  })),
}));

// Mock react-router-dom navigation
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

import { LoginPage } from "../LoginPage";

describe("Feature: auth-session-frontend, Property 12: Password visibility toggle state", () => {
  beforeEach(() => {
    mockLogin.mockReset();
    mockNavigate.mockReset();
    mockLogin.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("password field type is 'text' when N is odd, 'password' when N is even", { timeout: 30000 }, () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 20 }), (n) => {

        cleanup();

        render(
          <MemoryRouter>
            <LoginPage />
          </MemoryRouter>
        );

        const passwordInput = screen.getByLabelText("Password");

        // Click the toggle button N times
        for (let i = 0; i < n; i++) {
          // The aria-label changes between "Show password" and "Hide password"
          const toggleButton = screen.getByRole("button", {
            name: /show password|hide password/i,
          });
          fireEvent.click(toggleButton);
        }

        // Assert: type is "text" when N is odd, "password" when N is even
        const expectedType = n % 2 === 1 ? "text" : "password";
        expect(passwordInput.getAttribute("type")).toBe(expectedType);
      }),
      { numRuns: 100 }
    );
  });
});
