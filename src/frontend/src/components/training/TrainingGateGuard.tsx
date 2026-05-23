import { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { Shield, Loader2, AlertTriangle } from "lucide-react";
import { useTrainingStore } from "@/stores/trainingStore";
import { useAuthStore } from "@/stores/authStore";
import { shouldEnforceGate, deriveContentId } from "./utils";

interface TrainingGateGuardProps {
  sopDocumentUuid: string;
  sopVersion: string;
  sopStatus: string;
  children: React.ReactNode;
}

/**
 * TrainingGateGuard - Route wrapper that blocks navigation to documents
 * requiring uncompleted training AND quiz pass when the SOP is in "InTraining" status.
 *
 * Dual verification:
 * 1. User must have a completed training task for the SOP version
 * 2. User must have passed the comprehension quiz for the corresponding content_id
 *
 * Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
 */
export function TrainingGateGuard({
  sopDocumentUuid,
  sopVersion,
  sopStatus,
  children,
}: TrainingGateGuardProps) {
  const {
    checkTrainingGate,
    fetchTrainingTasks,
    hasFetchedTasks,
    checkQuizPassed,
    quizPassCache,
    isCheckingQuizPass,
    quizPassError,
  } = useTrainingStore();
  const user = useAuthStore((state) => state.user);

  const [isTimedOut, setIsTimedOut] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [quizCheckError, setQuizCheckError] = useState<string | null>(null);
  const [quizCheckInitiated, setQuizCheckInitiated] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const userId = user?.id ?? null;
  const contentId = deriveContentId(sopDocumentUuid, sopVersion);

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  // Trigger fetch if tasks haven't been loaded yet
  useEffect(() => {
    if (!shouldEnforceGate(sopStatus)) return;
    if (hasFetchedTasks || userId === null) return;

    setIsLoading(true);
    setIsTimedOut(false);

    // Start 10-second timeout
    timeoutRef.current = setTimeout(() => {
      setIsTimedOut(true);
      setIsLoading(false);
    }, 10_000);

    fetchTrainingTasks(userId).finally(() => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      setIsLoading(false);
    });
  }, [sopStatus, hasFetchedTasks, userId, fetchTrainingTasks]);

  // Trigger quiz pass check once tasks are loaded and task is complete
  useEffect(() => {
    if (!shouldEnforceGate(sopStatus)) return;
    if (!hasFetchedTasks || userId === null) return;

    // Only check quiz pass if the training task is complete
    const taskComplete = checkTrainingGate(sopDocumentUuid, sopVersion, userId);
    if (taskComplete !== true) return;

    // If already cached, no need to fetch
    if (contentId in quizPassCache) return;

    // Initiate quiz pass check
    if (!quizCheckInitiated) {
      setQuizCheckInitiated(true);
      checkQuizPassed(contentId, userId).then((result) => {
        if (result === null) {
          setQuizCheckError(quizPassError || "Unable to verify quiz status");
        }
      });
    }
  }, [
    sopStatus,
    hasFetchedTasks,
    userId,
    sopDocumentUuid,
    sopVersion,
    contentId,
    checkTrainingGate,
    checkQuizPassed,
    quizPassCache,
    quizCheckInitiated,
    quizPassError,
  ]);

  // Sync quiz pass error from store
  useEffect(() => {
    if (quizPassError && quizCheckInitiated) {
      setQuizCheckError(quizPassError);
    }
  }, [quizPassError, quizCheckInitiated]);

  const handleRetry = useCallback(() => {
    if (userId === null) return;

    setIsTimedOut(false);
    setQuizCheckError(null);
    setQuizCheckInitiated(false);
    setIsLoading(true);

    timeoutRef.current = setTimeout(() => {
      setIsTimedOut(true);
      setIsLoading(false);
    }, 10_000);

    fetchTrainingTasks(userId).finally(() => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      setIsLoading(false);
    });
  }, [userId, fetchTrainingTasks]);

  const handleQuizRetry = useCallback(() => {
    if (userId === null) return;

    setQuizCheckError(null);
    setQuizCheckInitiated(true);

    checkQuizPassed(contentId, userId).then((result) => {
      if (result === null) {
        setQuizCheckError("Unable to verify quiz status");
      }
    });
  }, [userId, contentId, checkQuizPassed]);

  // If gate is not enforced, render children directly
  if (!shouldEnforceGate(sopStatus)) {
    return <>{children}</>;
  }

  // Timeout error state
  if (isTimedOut) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
        <AlertTriangle className="h-12 w-12 text-amber-500 mb-4" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Unable to verify training status
        </h2>
        <p className="text-gray-600 text-center mb-4">
          The training status check timed out. Please check your connection and try again.
        </p>
        <button
          onClick={handleRetry}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          aria-label="Retry training status check"
        >
          Retry
        </button>
      </div>
    );
  }

  // Loading state - tasks not yet fetched or currently fetching
  if (isLoading || !hasFetchedTasks) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin mb-4" aria-hidden="true" />
        <p className="text-gray-600">Verifying training status…</p>
      </div>
    );
  }

  // Check training gate (task completion)
  const gateResult =
    userId !== null
      ? checkTrainingGate(sopDocumentUuid, sopVersion, userId)
      : null;

  // Gate result is null - still loading (tasks being fetched)
  if (gateResult === null) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin mb-4" aria-hidden="true" />
        <p className="text-gray-600">Verifying training status…</p>
      </div>
    );
  }

  // Training task NOT complete - block with existing message
  if (gateResult === false) {
    return (
      <div
        role="alert"
        className="flex flex-col items-center justify-center min-h-[400px] p-8"
      >
        <Shield className="h-12 w-12 text-amber-500 mb-4" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Training Required
        </h2>
        <p className="text-gray-600 text-center mb-4">
          Action denied: Valid training record for this SOP Version {sopVersion} is
          missing. You must complete training before accessing this document.
        </p>
        <Link
          to="/training"
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Go to Training
        </Link>
      </div>
    );
  }

  // Task is complete — now check quiz pass status

  // Network error checking quiz pass (fail-closed)
  if (quizCheckError) {
    return (
      <div
        role="alert"
        className="flex flex-col items-center justify-center min-h-[400px] p-8"
      >
        <AlertTriangle className="h-12 w-12 text-red-500 mb-4" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Access Verification Failed
        </h2>
        <p className="text-gray-600 text-center mb-4">
          Access verification could not be completed due to a network error. Please try again.
        </p>
        <button
          onClick={handleQuizRetry}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          aria-label="Retry access verification"
        >
          Retry
        </button>
      </div>
    );
  }

  // Quiz pass check in progress
  if (isCheckingQuizPass || (quizCheckInitiated && !(contentId in quizPassCache))) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
        <Loader2 className="h-8 w-8 text-blue-600 animate-spin mb-4" aria-hidden="true" />
        <p className="text-gray-600">Verifying quiz completion status…</p>
      </div>
    );
  }

  // Check quiz pass from cache
  const quizPassStatus = quizPassCache[contentId];
  const quizPassed = quizPassStatus?.has_passed ?? false;

  // Task complete but quiz NOT passed - block with specific message
  if (!quizPassed) {
    return (
      <div
        role="alert"
        className="flex flex-col items-center justify-center min-h-[400px] p-8"
      >
        <Shield className="h-12 w-12 text-amber-500 mb-4" aria-hidden="true" />
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Quiz Completion Required
        </h2>
        <p className="text-gray-600 text-center mb-4">
          Training task completed but comprehension quiz has not been passed for this SOP version.
        </p>
        <Link
          to="/training"
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Go to Training
        </Link>
      </div>
    );
  }

  // Both conditions met: task complete AND quiz passed — allow navigation
  return <>{children}</>;
}
