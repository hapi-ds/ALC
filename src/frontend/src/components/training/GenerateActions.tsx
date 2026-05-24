/**
 * GenerateActions
 *
 * Action buttons for "Generate Materials" and "Generate Quiz" operations.
 * Visible only to coordinator/admin roles. Buttons are disabled when a
 * generation job is pending or in progress, showing current job status.
 *
 * Requirements: 10.7, 10.8
 */

import { Loader2, FileText, HelpCircle } from "lucide-react";
import { useCallback } from "react";
import { Button } from "@/components/ui/button";
import { useTrainingEcosystemStore } from "@/stores/trainingEcosystemStore";
import { useAuthStore } from "@/stores/authStore";
import type { Job } from "@/types/training-ecosystem";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface GenerateActionsProps {
  documentId: number;
  documentVersionId: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function hasActiveJob(jobs: Job[]): boolean {
  return jobs.some(
    (job) => job.status === "pending" || job.status === "in_progress"
  );
}

function isCoordinatorOrAdmin(roles: string[] | undefined): boolean {
  if (!roles) return false;
  return roles.some(
    (role) =>
      role === "admin" || role === "coordinator" || role === "company_admin"
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GenerateActions({
  documentId,
  documentVersionId,
}: GenerateActionsProps) {
  const user = useAuthStore((s) => s.user);
  const {
    pendingJobs,
    generateMaterials,
    generateQuestions,
    materialsError,
    questionsError,
  } = useTrainingEcosystemStore();

  // Only show for coordinator/admin roles
  if (!isCoordinatorOrAdmin(user?.roles)) {
    return null;
  }

  const jobsActive = hasActiveJob(pendingJobs);

  const handleGenerateMaterials = useCallback(() => {
    generateMaterials(documentId, documentVersionId);
  }, [documentId, documentVersionId, generateMaterials]);

  const handleGenerateQuiz = useCallback(() => {
    generateQuestions(documentId, documentVersionId);
  }, [documentId, documentVersionId, generateQuestions]);

  return (
    <div className="flex flex-wrap items-center gap-3" aria-label="Generation actions">
      {/* Generate Materials button */}
      <Button
        variant="outline"
        size="sm"
        onClick={handleGenerateMaterials}
        disabled={jobsActive}
        aria-label="Generate training materials for this document"
      >
        {jobsActive ? (
          <Loader2 className="h-4 w-4 animate-spin mr-1" aria-hidden="true" />
        ) : (
          <FileText className="h-4 w-4 mr-1" aria-hidden="true" />
        )}
        Generate Materials
      </Button>

      {/* Generate Quiz button */}
      <Button
        variant="outline"
        size="sm"
        onClick={handleGenerateQuiz}
        disabled={jobsActive}
        aria-label="Generate quiz questions for this document"
      >
        {jobsActive ? (
          <Loader2 className="h-4 w-4 animate-spin mr-1" aria-hidden="true" />
        ) : (
          <HelpCircle className="h-4 w-4 mr-1" aria-hidden="true" />
        )}
        Generate Quiz
      </Button>

      {/* Status indicator when jobs are active */}
      {jobsActive && (
        <span className="text-xs text-muted-foreground">
          Generation in progress...
        </span>
      )}

      {/* Error messages */}
      {materialsError && (
        <span className="text-xs text-destructive">{materialsError}</span>
      )}
      {questionsError && (
        <span className="text-xs text-destructive">{questionsError}</span>
      )}
    </div>
  );
}
