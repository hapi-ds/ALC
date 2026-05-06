import { useCallback, useEffect, useRef, useState } from 'react';
import { getTokenExpiry } from '@/lib/tokenStorage';
import { useAuthStore } from '@/stores/authStore';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SessionTimerConfig {
  inactivityTimeoutMs: number;
  warningBeforeMs: number;
  refreshBeforeExpiryMs: number;
}

interface UseSessionTimerReturn {
  showInactivityWarning: boolean;
  showExpiryWarning: boolean;
  remainingSeconds: number;
  dismissWarning(): void;
  extendSession(): void;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: SessionTimerConfig = {
  inactivityTimeoutMs: 30 * 60 * 1000, // 30 minutes
  warningBeforeMs: 60 * 1000, // 60 seconds before logout
  refreshBeforeExpiryMs: 60 * 1000, // 60 seconds before token expiry
};

// Activity events to track for inactivity detection
const ACTIVITY_EVENTS: Array<keyof DocumentEventMap> = [
  'mousemove',
  'keydown',
  'touchstart',
];

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSessionTimer(
  config: Partial<SessionTimerConfig> = {},
): UseSessionTimerReturn {
  const {
    inactivityTimeoutMs,
    warningBeforeMs,
    refreshBeforeExpiryMs,
  } = { ...DEFAULT_CONFIG, ...config };

  const refreshToken = useAuthStore((state) => state.refreshToken);
  const logout = useAuthStore((state) => state.logout);

  // State
  const [showInactivityWarning, setShowInactivityWarning] = useState(false);
  const [showExpiryWarning, setShowExpiryWarning] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(0);

  // Refs for timers and tracking
  const tokenCheckIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inactivityTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastActivityRef = useRef<number>(Date.now());
  const isRefreshingRef = useRef(false);
  const showInactivityWarningRef = useRef(false);

  // Keep ref in sync with state for use in event handlers
  showInactivityWarningRef.current = showInactivityWarning;

  // -------------------------------------------------------------------------
  // Inactivity timer management
  // -------------------------------------------------------------------------

  const clearInactivityTimers = useCallback(() => {
    if (inactivityTimerRef.current !== null) {
      clearTimeout(inactivityTimerRef.current);
      inactivityTimerRef.current = null;
    }
    if (warningTimerRef.current !== null) {
      clearTimeout(warningTimerRef.current);
      warningTimerRef.current = null;
    }
    if (countdownIntervalRef.current !== null) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
  }, []);

  const startInactivityCountdown = useCallback((secondsLeft: number) => {
    setRemainingSeconds(secondsLeft);
    countdownIntervalRef.current = setInterval(() => {
      setRemainingSeconds((prev) => {
        if (prev <= 1) {
          if (countdownIntervalRef.current !== null) {
            clearInterval(countdownIntervalRef.current);
            countdownIntervalRef.current = null;
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  const resetInactivityTimer = useCallback(() => {
    clearInactivityTimers();
    setShowInactivityWarning(false);
    lastActivityRef.current = Date.now();

    // Set warning timer (fires warningBeforeMs before logout)
    const warningDelay = inactivityTimeoutMs - warningBeforeMs;
    warningTimerRef.current = setTimeout(() => {
      setShowInactivityWarning(true);
      startInactivityCountdown(Math.round(warningBeforeMs / 1000));
    }, warningDelay);

    // Set logout timer (fires at full inactivity timeout)
    inactivityTimerRef.current = setTimeout(() => {
      void logout();
    }, inactivityTimeoutMs);
  }, [clearInactivityTimers, inactivityTimeoutMs, warningBeforeMs, startInactivityCountdown, logout]);

  // -------------------------------------------------------------------------
  // Token expiry check
  // -------------------------------------------------------------------------

  const checkTokenExpiry = useCallback(() => {
    const expiry = getTokenExpiry();
    if (expiry === null) {
      return;
    }

    const nowSeconds = Math.floor(Date.now() / 1000);
    const secondsUntilExpiry = expiry - nowSeconds;
    const refreshThresholdSeconds = Math.round(refreshBeforeExpiryMs / 1000);

    if (secondsUntilExpiry <= refreshThresholdSeconds && secondsUntilExpiry > 0) {
      if (!isRefreshingRef.current) {
        isRefreshingRef.current = true;
        void refreshToken().then((success) => {
          isRefreshingRef.current = false;
          if (!success) {
            setShowExpiryWarning(true);
            setRemainingSeconds(secondsUntilExpiry);
          }
        });
      }
    } else if (secondsUntilExpiry <= 0) {
      // Token already expired
      setShowExpiryWarning(true);
      setRemainingSeconds(0);
    }
  }, [refreshBeforeExpiryMs, refreshToken]);

  // -------------------------------------------------------------------------
  // Public actions
  // -------------------------------------------------------------------------

  const dismissWarning = useCallback(() => {
    setShowInactivityWarning(false);
    setShowExpiryWarning(false);
    if (countdownIntervalRef.current !== null) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
  }, []);

  const extendSession = useCallback(() => {
    setShowInactivityWarning(false);
    setShowExpiryWarning(false);
    if (countdownIntervalRef.current !== null) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
    resetInactivityTimer();
  }, [resetInactivityTimer]);

  // -------------------------------------------------------------------------
  // Setup and cleanup
  // -------------------------------------------------------------------------

  // Token expiry check interval
  useEffect(() => {
    tokenCheckIntervalRef.current = setInterval(checkTokenExpiry, 1000);

    return () => {
      if (tokenCheckIntervalRef.current !== null) {
        clearInterval(tokenCheckIntervalRef.current);
        tokenCheckIntervalRef.current = null;
      }
    };
  }, [checkTokenExpiry]);

  // Inactivity timer setup
  useEffect(() => {
    resetInactivityTimer();

    return () => {
      clearInactivityTimers();
    };
  }, [resetInactivityTimer, clearInactivityTimers]);

  // Activity event listeners
  useEffect(() => {
    const handleActivity = () => {
      // Only reset if no warning is currently showing
      if (!showInactivityWarningRef.current) {
        lastActivityRef.current = Date.now();
        resetInactivityTimer();
      }
    };

    ACTIVITY_EVENTS.forEach((event) => {
      document.addEventListener(event, handleActivity);
    });

    return () => {
      ACTIVITY_EVENTS.forEach((event) => {
        document.removeEventListener(event, handleActivity);
      });
    };
  }, [resetInactivityTimer]);

  return {
    showInactivityWarning,
    showExpiryWarning,
    remainingSeconds,
    dismissWarning,
    extendSession,
  };
}
