import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import React from "react";

/**
 * Feature: auth-session-frontend, Property 2: Login form validation rejects empty fields
 *
 * Validates: Requirements 1.2
 *
 * For any pair of (username, password) inputs where at least one is empty,
 * submitting the login form SHALL produce a validation error for the empty field(s)
 * and SHALL NOT trigger an API request. Conversely, for any pair where both are
 * non-empty strings, no client-side validation error SHALL be produced.
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

describe("Feature: auth-session-frontend, Property 2: Login form validation rejects empty fields", () => {
  beforeEach(() => {
    mockLogin.mockReset();
    mockNavigate.mockReset();
    mockLogin.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  // Generator for field values: empty string, or non-empty alphanumeric string
  // We use alphanumeric to avoid special characters that userEvent.type interprets
  // (e.g., `[`, `{` are keyboard descriptors in userEvent)
  const nonEmptyStringArb = fc.stringMatching(/^[a-zA-Z0-9]+$/u, {
    minLength: 1,
    maxLength: 20,
  });

  const fieldValueArb = fc.oneof(
    fc.constant(""),
    nonEmptyStringArb
  );

  it("shows validation error when either field is empty, no error when both non-empty", { timeout: 60000 }, async () => {
    await fc.assert(
      fc.asyncProperty(fieldValueArb, fieldValueArb, async (username, password) => {
        // Clean up any previous render
        cleanup();
        mockLogin.mockReset();
        mockNavigate.mockReset();
        mockLogin.mockResolvedValue(undefined);

        const user = userEvent.setup();

        render(
          <MemoryRouter>
            <LoginPage />
          </MemoryRouter>
        );

        const usernameInput = screen.getByLabelText("Username");
        const passwordInput = screen.getByLabelText("Password");
        const submitButton = screen.getByRole("button", { name: /sign in/i });

        // Type values into fields (only if non-empty, since typing "" does nothing)
        if (username !== "") {
          await user.type(usernameInput, username);
        }
        if (password !== "") {
          await user.type(passwordInput, password);
        }

        // Submit the form
        await user.click(submitButton);

        const usernameEmpty = username === "";
        const passwordEmpty = password === "";

        if (usernameEmpty || passwordEmpty) {
          // At least one field is empty: expect validation error, no API call
          await waitFor(() => {
            const errors = screen.queryAllByRole("alert");
            const fieldErrors = errors.filter(
              (el) =>
                el.textContent === "Username is required" ||
                el.textContent === "Password is required"
            );
            expect(fieldErrors.length).toBeGreaterThan(0);
          });
          expect(mockLogin).not.toHaveBeenCalled();
        } else {
          // Both fields non-empty: no validation error, login should be called
          await waitFor(() => {
            expect(mockLogin).toHaveBeenCalledWith(username, password);
          });
          const validationErrors = screen.queryAllByRole("alert");
          const fieldErrors = validationErrors.filter(
            (el) =>
              el.textContent === "Username is required" ||
              el.textContent === "Password is required"
          );
          expect(fieldErrors.length).toBe(0);
        }
      }),
      { numRuns: 30 }
    );
  });
});
