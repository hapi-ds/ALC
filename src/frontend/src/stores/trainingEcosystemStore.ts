/**
 * Training Ecosystem Store (Zustand)
 *
 * Centralized state management for the AI-Enhanced Training Ecosystem.
 * Manages schedule, skill gaps, materials, questions, role-play sessions,
 * and async job polling.
 *
 * Requirements: 10.7, 10.8
 */

import { create } from "zustand";
import type {
  TrainingSchedule,
  SkillGap,
  TrainingMaterial,
  GeneratedQuestion,
  VirtualAuditSession,
  TurnEvaluation,
  Job,
} from "../types/training-ecosystem";
import {
  getSchedule,
  getUserGaps,
  generateMaterials as apiGenerateMaterials,
  generateQuestions as apiGenerateQuestions,
  getMaterials,
  getQuestions,
  startRolePlay as apiStartRolePlay,
  submitRolePlayResponse,
  getRolePlayHistory,
} from "../lib/training-ecosystem-api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 15_000;

// ---------------------------------------------------------------------------
// Store Interface
// ---------------------------------------------------------------------------

export interface TrainingEcosystemState {
  // Schedule
  schedule: TrainingSchedule | null;
  skillGaps: SkillGap[];

  // Materials (keyed by document_id)
  materials: Record<number, TrainingMaterial[]>;

  // Questions (keyed by document_id)
  questions: Record<number, GeneratedQuestion[]>;

  // Role-play
  activeSession: VirtualAuditSession | null;
  sessionHistory: VirtualAuditSession[];

  // Jobs
  pendingJobs: Job[];

  // Loading states
  isLoadingSchedule: boolean;
  isLoadingGaps: boolean;
  isLoadingMaterials: boolean;
  isLoadingQuestions: boolean;
  isLoadingSession: boolean;
  isSubmittingResponse: boolean;

  // Error states
  scheduleError: string | null;
  gapsError: string | null;
  materialsError: string | null;
  questionsError: string | null;
  sessionError: string | null;
  responseError: string | null;

  // Last turn evaluation (for UI display)
  lastEvaluation: TurnEvaluation | null;

  // Polling
  pollingIntervalId: ReturnType<typeof setInterval> | null;

  // Actions
  fetchSchedule: (userId: number) => Promise<void>;
  fetchGaps: (userId: number) => Promise<void>;
  generateMaterials: (documentId: number, versionId: number, materialTypes?: string[]) => Promise<void>;
  generateQuestions: (documentId: number, versionId: number, questionCount?: number) => Promise<void>;
  fetchMaterials: (documentId: number) => Promise<void>;
  fetchQuestions: (documentId: number) => Promise<void>;
  startRolePlay: (documentId: number, versionId: number, userId: number) => Promise<void>;
  submitResponse: (sessionId: number, text: string) => Promise<void>;
  fetchSessionHistory: (userId: number) => Promise<void>;
  pollJobs: () => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

// ---------------------------------------------------------------------------
// Initial State
// ---------------------------------------------------------------------------

const initialState = {
  schedule: null,
  skillGaps: [],
  materials: {},
  questions: {},
  activeSession: null,
  sessionHistory: [],
  pendingJobs: [],
  isLoadingSchedule: false,
  isLoadingGaps: false,
  isLoadingMaterials: false,
  isLoadingQuestions: false,
  isLoadingSession: false,
  isSubmittingResponse: false,
  scheduleError: null,
  gapsError: null,
  materialsError: null,
  questionsError: null,
  sessionError: null,
  responseError: null,
  lastEvaluation: null,
  pollingIntervalId: null,
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useTrainingEcosystemStore = create<TrainingEcosystemState>(
  (set, get) => ({
    ...initialState,

    // -------------------------------------------------------------------------
    // Schedule
    // -------------------------------------------------------------------------

    fetchSchedule: async (userId: number) => {
      if (get().isLoadingSchedule) return;
      set({ isLoadingSchedule: true, scheduleError: null });

      try {
        const schedule = await getSchedule(userId);
        set({ schedule, isLoadingSchedule: false });
      } catch (error) {
        set({
          scheduleError: extractErrorMessage(error),
          isLoadingSchedule: false,
        });
      }
    },

    // -------------------------------------------------------------------------
    // Skill Gaps
    // -------------------------------------------------------------------------

    fetchGaps: async (userId: number) => {
      if (get().isLoadingGaps) return;
      set({ isLoadingGaps: true, gapsError: null });

      try {
        const skillGaps = await getUserGaps(userId);
        set({ skillGaps, isLoadingGaps: false });
      } catch (error) {
        set({
          gapsError: extractErrorMessage(error),
          isLoadingGaps: false,
        });
      }
    },

    // -------------------------------------------------------------------------
    // Materials
    // -------------------------------------------------------------------------

    generateMaterials: async (
      documentId: number,
      versionId: number,
      materialTypes?: string[]
    ) => {
      set({ materialsError: null });

      try {
        const job = await apiGenerateMaterials(
          { document_id: documentId, document_version_id: versionId, material_types: materialTypes ?? null },
          "Generate training materials",
        );
        const pendingJobs = [...get().pendingJobs, job];
        set({ pendingJobs });

        // Start polling if not already active
        if (!get().pollingIntervalId) {
          get().startPolling();
        }
      } catch (error) {
        set({ materialsError: extractErrorMessage(error) });
      }
    },

    fetchMaterials: async (documentId: number) => {
      if (get().isLoadingMaterials) return;
      set({ isLoadingMaterials: true, materialsError: null });

      try {
        const result = await getMaterials(documentId);
        const materials = { ...get().materials, [documentId]: result.items };
        set({ materials, isLoadingMaterials: false });
      } catch (error) {
        set({
          materialsError: extractErrorMessage(error),
          isLoadingMaterials: false,
        });
      }
    },

    // -------------------------------------------------------------------------
    // Questions
    // -------------------------------------------------------------------------

    generateQuestions: async (
      documentId: number,
      versionId: number,
      questionCount?: number
    ) => {
      set({ questionsError: null });

      try {
        const job = await apiGenerateQuestions(
          { document_id: documentId, document_version_id: versionId, question_count: questionCount },
          "Generate training questions",
        );
        const pendingJobs = [...get().pendingJobs, job];
        set({ pendingJobs });

        // Start polling if not already active
        if (!get().pollingIntervalId) {
          get().startPolling();
        }
      } catch (error) {
        set({ questionsError: extractErrorMessage(error) });
      }
    },

    fetchQuestions: async (documentId: number) => {
      if (get().isLoadingQuestions) return;
      set({ isLoadingQuestions: true, questionsError: null });

      try {
        const result = await getQuestions(documentId);
        const questions = { ...get().questions, [documentId]: result.items };
        set({ questions, isLoadingQuestions: false });
      } catch (error) {
        set({
          questionsError: extractErrorMessage(error),
          isLoadingQuestions: false,
        });
      }
    },

    // -------------------------------------------------------------------------
    // Role-Play
    // -------------------------------------------------------------------------

    startRolePlay: async (
      documentId: number,
      versionId: number,
      userId: number
    ) => {
      if (get().isLoadingSession) return;
      set({ isLoadingSession: true, sessionError: null, lastEvaluation: null });

      try {
        const response = await apiStartRolePlay(
          { document_id: documentId, document_version_id: versionId, user_id: userId },
          "Start virtual audit session",
        );
        set({
          activeSession: {
            id: response.session_id,
            user_id: userId,
            document_id: documentId,
            status: "in_progress",
            overall_score: null,
            passed: null,
            turns_completed: 0,
            total_turns: response.total_turns,
            session_data: { first_question: response.first_question, turns: [] },
            summary_data: null,
            started_at: new Date().toISOString(),
            completed_at: null,
          },
          isLoadingSession: false,
        });
      } catch (error) {
        set({
          sessionError: extractErrorMessage(error),
          isLoadingSession: false,
        });
      }
    },

    submitResponse: async (sessionId: number, text: string) => {
      if (get().isSubmittingResponse) return;
      set({ isSubmittingResponse: true, responseError: null });

      try {
        const evaluation = await submitRolePlayResponse(
          sessionId,
          { response_text: text },
          "Submit virtual audit response",
        );
        const updates: Partial<TrainingEcosystemState> = {
          lastEvaluation: evaluation,
          isSubmittingResponse: false,
        };

        // Update active session turn count
        const activeSession = get().activeSession;
        if (activeSession && activeSession.id === sessionId) {
          updates.activeSession = {
            ...activeSession,
            turns_completed: activeSession.turns_completed + 1,
            status: evaluation.session_complete ? "completed" : activeSession.status,
            overall_score: evaluation.current_score,
            passed: evaluation.session_complete
              ? evaluation.current_score >= 0.7
              : activeSession.passed,
          };
        }

        set(updates as TrainingEcosystemState);
      } catch (error) {
        set({
          responseError: extractErrorMessage(error),
          isSubmittingResponse: false,
        });
      }
    },

    fetchSessionHistory: async (userId: number) => {
      try {
        const result = await getRolePlayHistory(userId);
        set({ sessionHistory: result.items });
      } catch {
        // Silently fail for history fetch — non-critical
      }
    },

    // -------------------------------------------------------------------------
    // Job Polling
    // -------------------------------------------------------------------------

    pollJobs: async () => {
      const { pendingJobs } = get();
      if (pendingJobs.length === 0) {
        get().stopPolling();
        return;
      }

      // Check each pending job status via the existing job tracker endpoint
      const updatedJobs: Job[] = [];

      for (const job of pendingJobs) {
        try {
          const response = await fetch(`/api/jobs/${job.job_id}`, {
            credentials: "include",
          });
          if (response.ok) {
            const data = (await response.json()) as { status: string };
            if (data.status === "completed" || data.status === "failed") {
              // Job finished — remove from pending
              continue;
            }
            updatedJobs.push({ ...job, status: data.status });
          } else {
            // Keep the job in pending if we can't check status
            updatedJobs.push(job);
          }
        } catch {
          updatedJobs.push(job);
        }
      }

      set({ pendingJobs: updatedJobs });

      // Stop polling if no more pending jobs
      if (updatedJobs.length === 0) {
        get().stopPolling();
      }
    },

    startPolling: () => {
      // Avoid duplicate intervals
      if (get().pollingIntervalId) return;

      const intervalId = setInterval(() => {
        get().pollJobs();
      }, POLL_INTERVAL_MS);

      set({ pollingIntervalId: intervalId });
    },

    stopPolling: () => {
      const { pollingIntervalId } = get();
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
        set({ pollingIntervalId: null });
      }
    },

    // -------------------------------------------------------------------------
    // Reset
    // -------------------------------------------------------------------------

    reset: () => {
      const { pollingIntervalId } = get();
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
      }
      set(initialState);
    },
  })
);
