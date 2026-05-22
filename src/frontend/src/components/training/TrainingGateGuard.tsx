import { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { Shield, Loader2, AlertTriangle } from "lucide-react";
import { useTrainingStore } from "@/stores/trainingStore";
import { useAuthStore } from "@/stores/authStore";
import { shouldEnforceGate } from "./utils";

interface TrainingGateGuardProps {
  sopDocumentUuid: string;
  sopVersion: string;
  sopStatus: string;
  children: React.ReactNode;
}

/**
 * TrainingGateGuard - Route wrapper that blocks navigation to documents
 * requiring uncompleted training when the SOP is in "InTraining" status.
 *
 * Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 11.10
 */
export function TrainingGateGuard({
  sopDocumentUuid,
  sopVersion,
  sopStatus,
  children,
}: TrainingGateGuardProps) {
  const { checkTrainingGate, fetchTrainingTasks, hasFetchedTasks } =
    useTrainingStore();
  const user = useAuthStore((state) => state.user);

  const [isTimedOut, setIsTimedOut] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const userId = user?.id ?? null;

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

  const handleRetry = useCallback(() => {
    if (userId === null) return;

    setIsTimedOut(false);
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

  // Check training gate
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

  // Training complete - allow navigation
  if (gateResult === true) {
    return <>{children}</>;
  }

  // Training incomplete - block navigation
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
