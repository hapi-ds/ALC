import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, ApiError } from "@/lib/apiClient";
import type { JobStatusDetail } from "@/types/videoAlignment";

/**
 * Polling interval in milliseconds (5 seconds as per requirement 11.7).
 */
const POLL_INTERVAL_MS = 5000;

/**
 * Request timeout in milliseconds (15 seconds as per requirement 11.8).
 */
const REQUEST_TIMEOUT_MS = 15000;

/**
 * State of the job polling hook.
 */
export interface JobPollingState {
  /** Whether polling is currently active */
  isPolling: boolean;
  /** Current job status detail from the last successful poll */
  jobStatus: JobStatusDetail | null;
  /** Error message if polling encountered an error */
  error: string | null;
}

/**
 * Return type for the useJobPolling hook.
 */
export interface UseJobPollingReturn extends JobPollingState {
  /** Start polling for a specific job */
  startPolling: (jobId: string) => void;
  /** Stop polling and reset state */
  stopPolling: () => void;
  /** Retry after an error */
  retry: () => void;
}

/**
 * Custom hook for polling job status with 5-second intervals.
 *
 * Polls `GET /api/knowledge/videos/jobs/{job_id}` every 5 seconds.
 * Automatically stops polling when job completes or fails.
 * Handles network errors, 5xx errors, and 15s timeouts with error state.
 *
 * Validates: Requirements 11.7, 11.8
 */
export function useJobPolling(): UseJobPollingReturn {
  const [state, setState] = useState<JobPollingState>({
    isPolling: false,
    jobStatus: null,
    error: null,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const clearPollingInterval = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const fetchJobStatus = useCallback(async (jobId: string): Promise<void> => {
    // Abort any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Set up timeout
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, REQUEST_TIMEOUT_MS);

    try {
      const response = await apiClient.get<JobStatusDetail>(
        `/api/knowledge/videos/jobs/${jobId}`
      );

      clearTimeout(timeoutId);

      setState((prev) => ({
        ...prev,
        jobStatus: response,
        error: null,
      }));

      // Stop polling if job is completed or failed
      if (response.status === "completed" || response.status === "failed") {
        clearPollingInterval();
        setState((prev) => ({ ...prev, isPolling: false }));
      }
    } catch (err: unknown) {
      clearTimeout(timeoutId);

      let errorMessage: string;

      if (err instanceof ApiError) {
        if (err.status >= 500) {
          errorMessage = `Server error (${err.status}). The server encountered an issue processing the request.`;
        } else {
          errorMessage = `Request failed with status ${err.status}.`;
        }
      } else if (err instanceof DOMException && err.name === "AbortError") {
        errorMessage = "Request timed out after 15 seconds. Please check your connection and try again.";
      } else if (err instanceof TypeError) {
        // Network errors (fetch throws TypeError for network failures)
        errorMessage = "Network error. Please check your connection and try again.";
      } else {
        errorMessage = "An unexpected error occurred. Please try again.";
      }

      clearPollingInterval();
      setState((prev) => ({
        ...prev,
        isPolling: false,
        error: errorMessage,
      }));
    }
  }, [clearPollingInterval]);

  const startPolling = useCallback(
    (jobId: string) => {
      // Clear any existing polling
      clearPollingInterval();
      jobIdRef.current = jobId;

      setState({
        isPolling: true,
        jobStatus: null,
        error: null,
      });

      // Fetch immediately, then poll every 5 seconds
      void fetchJobStatus(jobId);
      intervalRef.current = setInterval(() => {
        void fetchJobStatus(jobId);
      }, POLL_INTERVAL_MS);
    },
    [clearPollingInterval, fetchJobStatus]
  );

  const stopPolling = useCallback(() => {
    clearPollingInterval();
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    jobIdRef.current = null;
    setState({
      isPolling: false,
      jobStatus: null,
      error: null,
    });
  }, [clearPollingInterval]);

  const retry = useCallback(() => {
    if (jobIdRef.current) {
      startPolling(jobIdRef.current);
    }
  }, [startPolling]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearPollingInterval();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [clearPollingInterval]);

  return {
    ...state,
    startPolling,
    stopPolling,
    retry,
  };
}
