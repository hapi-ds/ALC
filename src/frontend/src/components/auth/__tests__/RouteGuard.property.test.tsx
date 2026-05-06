import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import React from "react";

/**
 * Feature: auth-session-frontend, Property 8: Route guard redirects unauthenticated users with URL preservation
 *
 * Validates: Requirements 4.1, 4.2
 *
 * For any protected route path, when the auth state is unauthenticated (and not loading),
 * the Route Guard SHALL redirect to `/login?redirect=<encoded_path>` preserving the
 * originally requested URL.
 */

// Mock the auth store
vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn(),
}));

// Track Navigate calls
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    Navigate: (props: { to: string; replace?: boolean }) => {
      mockNavigate(props);
      return null;
    },
  };
});

import { RouteGuard } from "../RouteGuard";
import { useAuthStore } from "@/stores/authStore";

describe("Feature: auth-session-frontend, Property 8: Route guard redirects unauthenticated users with URL preservation", () => {
  beforeEach(() => {
    vi.mocked(useAuthStore).mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
    } as ReturnType<typeof useAuthStore>);
    mockNavigate.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // Generator for valid URL paths: starts with "/" followed by path segments
  const urlPathArb = fc
    .array(
      fc.stringMatching(/^[a-zA-Z0-9._~:@!$&'()*+,;=-]+$/u, {
        minLength: 1,
        maxLength: 20,
      }),
      { minLength: 1, maxLength: 5 }
    )
    .map((segments) => "/" + segments.join("/"));

  it("redirects unauthenticated users to /login?redirect=<encoded_path> for any path", () => {
    fc.assert(
      fc.property(urlPathArb, (path) => {
        mockNavigate.mockReset();

        render(
          <MemoryRouter initialEntries={[path]}>
            <RouteGuard>
              <div>Protected Content</div>
            </RouteGuard>
          </MemoryRouter>
        );

        // Navigate should have been called
        expect(mockNavigate).toHaveBeenCalledTimes(1);

        const navigateProps = mockNavigate.mock.calls[0][0];
        const expectedRedirect = `/login?redirect=${encodeURIComponent(path)}`;

        expect(navigateProps.to).toBe(expectedRedirect);
        expect(navigateProps.replace).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  // Generator for paths with query strings
  const urlPathWithQueryArb = fc
    .tuple(
      fc
        .array(
          fc.stringMatching(/^[a-zA-Z0-9._~-]+$/u, {
            minLength: 1,
            maxLength: 15,
          }),
          { minLength: 1, maxLength: 4 }
        )
        .map((segments) => "/" + segments.join("/")),
      fc
        .array(
          fc.tuple(
            fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9]*$/u, {
              minLength: 1,
              maxLength: 10,
            }),
            fc.stringMatching(/^[a-zA-Z0-9]+$/u, {
              minLength: 1,
              maxLength: 10,
            })
          ),
          { minLength: 1, maxLength: 3 }
        )
        .map(
          (params) =>
            "?" + params.map(([k, v]) => `${k}=${v}`).join("&")
        )
    )
    .map(([path, query]) => path + query);

  it("preserves query parameters in the redirect URL", () => {
    fc.assert(
      fc.property(urlPathWithQueryArb, (fullPath) => {
        mockNavigate.mockReset();

        render(
          <MemoryRouter initialEntries={[fullPath]}>
            <RouteGuard>
              <div>Protected Content</div>
            </RouteGuard>
          </MemoryRouter>
        );

        expect(mockNavigate).toHaveBeenCalledTimes(1);

        const navigateProps = mockNavigate.mock.calls[0][0];
        const expectedRedirect = `/login?redirect=${encodeURIComponent(fullPath)}`;

        expect(navigateProps.to).toBe(expectedRedirect);
        expect(navigateProps.replace).toBe(true);
      }),
      { numRuns: 100 }
    );
  });
});
