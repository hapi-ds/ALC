import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: auth-session-frontend, Property 10: Logout resets all application state regardless of API outcome
 *
 * Validates: Requirements 6.1, 6.3, 6.4, 6.5
 *
 * For any initial auth state (any user, any tokens, any tenant context) and any
 * logout API outcome (success, network error, server error), after logout completes:
 * the user SHALL be null, isAuthenticated SHALL be false, all tokens SHALL be cleared,
 * tenant context SHALL be null, and navigation SHALL be at the login page.
 */

// Mock apiClient before importing authStore
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

// Mock tokenStorage
vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(),
}));

import { useAuthStore } from "../authStore";
import { apiClient } from "@/lib/apiClient";
import { clearAccessToken } from "@/lib/tokenStorage";

describe("Feature: auth-session-frontend, Property 10: Logout resets all application state regardless of API outcome", () => {
  let originalLocation: PropertyDescriptor | undefined;

  beforeEach(() => {
    vi.resetAllMocks();
    // Mock window.location.href
    originalLocation = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", {
      writable: true,
      value: { href: "/" },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Restore window.location
    if (originalLocation) {
      Object.defineProperty(window, "location", originalLocation);
    }
    // Reset the store to initial state
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      sessionExpired: false,
      activeCompanyId: null,
      activeCompanySlug: null,
    });
  });

  // Generators
  const userArb = fc.record({
    id: fc.integer({ min: 1, max: 100000 }),
    username: fc.string({ minLength: 1, maxLength: 50 }),
    email: fc.string({ minLength: 1, maxLength: 100 }),
    full_name: fc.string({ minLength: 1, maxLength: 100 }),
    roles: fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 1, maxLength: 5 }),
  });

  const apiOutcomeArb = fc.oneof(
    fc.constant("success" as const),
    fc.constant("network_error" as const),
    fc.constant("server_error" as const)
  );

  const activeCompanyIdArb = fc.option(fc.integer({ min: 1, max: 100000 }));

  it("after logout, user is null, isAuthenticated is false, tokens cleared, and tenant context is null regardless of API outcome", async () => {
    await fc.assert(
      fc.asyncProperty(
        userArb,
        apiOutcomeArb,
        activeCompanyIdArb,
        async (user, apiOutcome, activeCompanyId) => {
          // Reset mocks for each iteration
          vi.mocked(apiClient.post).mockReset();
          vi.mocked(clearAccessToken).mockReset();
          (window.location as { href: string }).href = "/";

          // Set the store to the generated initial state (authenticated)
          useAuthStore.setState({
            user,
            isAuthenticated: true,
            isLoading: false,
            sessionExpired: false,
            activeCompanyId: activeCompanyId ?? null,
            activeCompanySlug: activeCompanyId ? `company-${activeCompanyId}` : null,
          });

          // Mock apiClient.post to simulate the generated API outcome
          switch (apiOutcome) {
            case "success":
              vi.mocked(apiClient.post).mockResolvedValueOnce({ message: "Logged out successfully" });
              break;
            case "network_error":
              vi.mocked(apiClient.post).mockRejectedValueOnce(new TypeError("Failed to fetch"));
              break;
            case "server_error":
              vi.mocked(apiClient.post).mockRejectedValueOnce(new Error("Internal Server Error"));
              break;
          }

          // Call logout
          await useAuthStore.getState().logout();

          // Assert: state is fully reset
          const state = useAuthStore.getState();
          expect(state.user).toBeNull();
          expect(state.isAuthenticated).toBe(false);
          expect(state.activeCompanyId).toBeNull();
          expect(state.activeCompanySlug).toBeNull();

          // Assert: clearAccessToken was called
          expect(clearAccessToken).toHaveBeenCalled();

          // Assert: navigation to login page
          expect(window.location.href).toBe("/login");
        }
      ),
      { numRuns: 100 }
    );
  });
});
