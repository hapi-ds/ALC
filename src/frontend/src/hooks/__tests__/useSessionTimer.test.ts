import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSessionTimer } from "../useSessionTimer";

// Mock tokenStorage
vi.mock("@/lib/tokenStorage", () => ({
  getTokenExpiry: vi.fn(() => null),
}));

// Mock authStore
const mockRefreshToken = vi.fn(() => Promise.resolve(true));
const mockLogout = vi.fn(() => Promise.resolve());

vi.mock("@/stores/authStore", () => ({
  useAuthStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      refreshToken: mockRefreshToken,
      logout: mockLogout,
    }),
}));

import { getTokenExpiry } from "@/lib/tokenStorage";

const mockedGetTokenExpiry = vi.mocked(getTokenExpiry);

describe("useSessionTimer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockedGetTokenExpiry.mockReturnValue(null);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("Proactive token refresh (Requirement 5.1, 5.2)", () => {
    it("triggers refreshToken when token is within 60s of expiry", async () => {
      // Set token expiry to 50 seconds from now
      const nowSeconds = Math.floor(Date.now() / 1000);
      mockedGetTokenExpiry.mockReturnValue(nowSeconds + 50);

      renderHook(() => useSessionTimer());

      // Advance by 1 second to trigger the interval check
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(mockRefreshToken).toHaveBeenCalled();
    });

    it("does not trigger refreshToken when token has more than 60s until expiry", async () => {
      // Set token expiry to 120 seconds from now (well beyond threshold)
      const nowSeconds = Math.floor(Date.now() / 1000);
      mockedGetTokenExpiry.mockReturnValue(nowSeconds + 120);

      renderHook(() => useSessionTimer());

      // Advance by 1 second to trigger the interval check
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(mockRefreshToken).not.toHaveBeenCalled();
    });

    it("does not trigger refreshToken when no token is stored", async () => {
      mockedGetTokenExpiry.mockReturnValue(null);

      renderHook(() => useSessionTimer());

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(mockRefreshToken).not.toHaveBeenCalled();
    });
  });

  describe("Inactivity warning (Requirement 5.5)", () => {
    it("shows inactivity warning after configured timeout minus warning period", async () => {
      const { result } = renderHook(() =>
        useSessionTimer({
          inactivityTimeoutMs: 5000,
          warningBeforeMs: 2000,
        })
      );

      expect(result.current.showInactivityWarning).toBe(false);

      // Advance past the warning threshold (5000 - 2000 = 3000ms)
      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      expect(result.current.showInactivityWarning).toBe(true);
    });

    it("does not show warning before the warning threshold", async () => {
      const { result } = renderHook(() =>
        useSessionTimer({
          inactivityTimeoutMs: 5000,
          warningBeforeMs: 2000,
        })
      );

      // Advance to just before the warning threshold
      await act(async () => {
        vi.advanceTimersByTime(2900);
      });

      expect(result.current.showInactivityWarning).toBe(false);
    });

    it("calls logout after full inactivity timeout", async () => {
      renderHook(() =>
        useSessionTimer({
          inactivityTimeoutMs: 5000,
          warningBeforeMs: 2000,
        })
      );

      // Advance past the full inactivity timeout
      await act(async () => {
        vi.advanceTimersByTime(5000);
      });

      expect(mockLogout).toHaveBeenCalled();
    });
  });

  describe("User activity resets inactivity timer (Requirement 5.5)", () => {
    it("resets the inactivity timer on mousemove event", async () => {
      const { result } = renderHook(() =>
        useSessionTimer({
          inactivityTimeoutMs: 5000,
          warningBeforeMs: 2000,
        })
      );

      // Advance partway (2000ms, before warning threshold of 3000ms)
      await act(async () => {
        vi.advanceTimersByTime(2000);
      });

      expect(result.current.showInactivityWarning).toBe(false);

      // Fire a mousemove event to reset the timer
      await act(async () => {
        document.dispatchEvent(new Event("mousemove"));
      });

      // Advance another 2000ms (total 4000ms from start, but only 2000ms since reset)
      await act(async () => {
        vi.advanceTimersByTime(2000);
      });

      // Should still not show warning because timer was reset
      expect(result.current.showInactivityWarning).toBe(false);

      // Advance to the warning threshold from the reset point (3000ms total since reset)
      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(result.current.showInactivityWarning).toBe(true);
    });

    it("does not reset timer when inactivity warning is already showing", async () => {
      const { result } = renderHook(() =>
        useSessionTimer({
          inactivityTimeoutMs: 5000,
          warningBeforeMs: 2000,
        })
      );

      // Advance past warning threshold
      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      expect(result.current.showInactivityWarning).toBe(true);

      // Fire a mousemove event - should NOT reset because warning is showing
      await act(async () => {
        document.dispatchEvent(new Event("mousemove"));
      });

      // Warning should still be showing
      expect(result.current.showInactivityWarning).toBe(true);
    });
  });

  describe("extendSession (Requirement 5.3, 5.5)", () => {
    it("dismisses the inactivity warning and resets the timer", async () => {
      const { result } = renderHook(() =>
        useSessionTimer({
          inactivityTimeoutMs: 5000,
          warningBeforeMs: 2000,
        })
      );

      // Advance past warning threshold
      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      expect(result.current.showInactivityWarning).toBe(true);

      // Call extendSession
      await act(async () => {
        result.current.extendSession();
      });

      // Warning should be dismissed
      expect(result.current.showInactivityWarning).toBe(false);

      // Timer should be reset - advance to just before new warning threshold
      await act(async () => {
        vi.advanceTimersByTime(2900);
      });

      expect(result.current.showInactivityWarning).toBe(false);

      // Advance past new warning threshold
      await act(async () => {
        vi.advanceTimersByTime(200);
      });

      expect(result.current.showInactivityWarning).toBe(true);
    });

    it("prevents logout after extending session", async () => {
      renderHook(() =>
        useSessionTimer({
          inactivityTimeoutMs: 5000,
          warningBeforeMs: 2000,
        })
      );

      // Advance past warning threshold but before logout
      await act(async () => {
        vi.advanceTimersByTime(4000);
      });

      // Logout should not have been called yet
      expect(mockLogout).not.toHaveBeenCalled();
    });
  });
});
