/**
 * ReviewSessionDetailPage
 *
 * Route-level page for /reviews/:sessionId that fetches the session detail
 * and renders the ReviewSessionDetail component.
 *
 * Requirements: 11.1, 11.2
 */

import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ReviewSessionDetail } from "@/components/reviews/ReviewSessionDetail";
import { useReviewStore } from "@/stores/reviewStore";

export function ReviewSessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const {
    currentSession,
    isLoadingDetail,
    detailError,
    isApproving,
    approveError,
    fetchSessionDetail,
    approveSession,
    rejectSession,
    stopPolling,
  } = useReviewStore();

  const numericSessionId = sessionId ? Number(sessionId) : null;

  useEffect(() => {
    if (numericSessionId != null && !isNaN(numericSessionId)) {
      fetchSessionDetail(numericSessionId);
    }

    return () => {
      stopPolling();
    };
  }, [numericSessionId, fetchSessionDetail, stopPolling]);

  function handleApprove(changeReason: string) {
    if (numericSessionId != null) {
      approveSession(numericSessionId, changeReason);
    }
  }

  function handleReject(changeReason: string) {
    if (numericSessionId != null) {
      rejectSession(numericSessionId, changeReason);
    }
  }

  // Invalid session ID
  if (numericSessionId == null || isNaN(numericSessionId)) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/reviews")}>
          <ArrowLeft className="h-4 w-4 mr-2" aria-hidden="true" />
          Back to Reviews
        </Button>
        <div className="border border-destructive/50 bg-destructive/10 rounded-md p-6 text-center">
          <AlertCircle className="h-8 w-8 mx-auto mb-2 text-destructive" aria-hidden="true" />
          <p className="text-destructive font-medium">Invalid session ID</p>
        </div>
      </div>
    );
  }

  // Loading state
  if (isLoadingDetail) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/reviews")}>
          <ArrowLeft className="h-4 w-4 mr-2" aria-hidden="true" />
          Back to Reviews
        </Button>
        <div className="flex items-center justify-center py-12" role="status" aria-label="Loading session detail">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">Loading session detail</span>
        </div>
      </div>
    );
  }

  // Error state
  if (detailError) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/reviews")}>
          <ArrowLeft className="h-4 w-4 mr-2" aria-hidden="true" />
          Back to Reviews
        </Button>
        <div
          role="alert"
          className="flex flex-col items-center gap-3 p-6 border border-destructive/50 bg-destructive/10 rounded-md text-center"
        >
          <AlertCircle className="h-8 w-8 text-destructive" aria-hidden="true" />
          <p className="text-destructive font-medium">{detailError}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchSessionDetail(numericSessionId)}
          >
            <RefreshCw className="h-3 w-3 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // No session found
  if (!currentSession) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/reviews")}>
          <ArrowLeft className="h-4 w-4 mr-2" aria-hidden="true" />
          Back to Reviews
        </Button>
        <div className="border border-border rounded-md p-6 text-center text-muted-foreground">
          <p>Session not found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Button variant="ghost" onClick={() => navigate("/reviews")}>
        <ArrowLeft className="h-4 w-4 mr-2" aria-hidden="true" />
        Back to Reviews
      </Button>
      <ReviewSessionDetail
        session={currentSession}
        isApproving={isApproving}
        approveError={approveError}
        onApprove={handleApprove}
        onReject={handleReject}
      />
    </div>
  );
}
