import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTrainingEcosystemStore } from "@/stores/trainingEcosystemStore";
import type { TrainingSchedule, SkillGap, TurnEvaluation } from "@/types/training-ecosystem";

/**
 * Unit tests for trainingEcosystemStore actions and state management.
 *
 * Validates: Requirements 10.7, 10.8
 */

// Mock the training-ecosystem-api module
vi.mock("@/lib/training-ecosystem-api", () => ({
  getSchedule: vi.fn(),
  getUserGaps: vi.fn(),
  generateMaterials: vi.fn(),
  generateQuestions: vi.fn(),
  getMaterials: vi.fn(),
  getQuestions: vi.fn(),
  startRolePlay: vi.fn(),
  submitRolePlayResponse: vi.fn(),
  getSessionHistory: vi.fn(),
}));

import {
  getSchedule,
  getUserGaps,
  generateMaterials,
  generateQuestions,
  getMaterials,
  getQuestions,
  startRolePlay,
  submitRolePlayResponse,
} from "@/lib/training-ecosystem-api";

const mockedGetSchedule = getSchedule as ReturnType<typeof vi.fn>;
const mockedGetUserGaps = getUserGaps as ReturnType<typeof vi.fn>;
const mockedGenerateMaterials = generateMaterials as ReturnType<typeof vi.fn>;
const mockedGenerateQuestions = generateQuestions as ReturnType<typeof vi.fn>;
const mockedGetMaterials = getMaterials as ReturnType<typeof vi.fn>;
const mockedGetQuestions = getQuestions as ReturnType<typeof vi.fn>;
const mockedStartRolePlay = startRolePlay as ReturnType<typeof vi.fn>;
const mockedSubmitRolePlayResponse = submitRolePlayResponse as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const sampleSchedule: TrainingSchedule = {
  id: 1,
  user_id: 42,
  schedule_data: { items: [] },
  compliance_percentage: 75.0,
  total_items: 4,
  completed_items: 3,
  generated_at: "2024-01-15T10:00:00Z",
  last_recalculated_at: "2024-01-15T10:00:00Z",
};

const sampleGaps: SkillGap[] = [
  {
    id: 1,
    document_id: 10,
    document_title: "Chemical Handling SOP",
    gap_type: "missing_training",
    priority: "Critical",
    days_overdue: 5,
    blocks_access: true,
    identified_at: "2024-01-10T00:00:00Z",
  },
];

// ---------------------------------------------------------------------------
// Initial state for reset
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
// Tests
// ---------------------------------------------------------------------------

describe("trainingEcosystemStore", () => {
  beforeEach(() => {
    useTrainingEcosystemStore.getState().reset();
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  // -------------------------------------------------------------------------
  // fetchSchedule
  // -------------------------------------------------------------------------

  describe("fetchSchedule", () => {
    it("sets isLoadingSchedule to true and clears error on start", async () => {
      useTrainingEcosystemStore.setState({ scheduleError: "previous error" });
      mockedGetSchedule.mockImplementation(() => new Promise(() => {}));

      useTrainingEcosystemStore.getState().fetchSchedule(42);

      await vi.waitFor(() => {
        const state = useTrainingEcosystemStore.getState();
        expect(state.isLoadingSchedule).toBe(true);
        expect(state.scheduleError).toBeNull();
      });
    });

    it("stores schedule and sets isLoadingSchedule=false on success", async () => {
      mockedGetSchedule.mockResolvedValue(sampleSchedule);

      await useTrainingEcosystemStore.getState().fetchSchedule(42);

      const state = useTrainingEcosystemStore.getState();
      expect(state.schedule).toEqual(sampleSchedule);
      expect(state.isLoadingSchedule).toBe(false);
      expect(state.scheduleError).toBeNull();
      expect(mockedGetSchedule).toHaveBeenCalledWith(42);
    });

    it("sets scheduleError on failure", async () => {
      mockedGetSchedule.mockRejectedValue(new Error("Network error"));

      await useTrainingEcosystemStore.getState().fetchSchedule(42);

      const state = useTrainingEcosystemStore.getState();
      expect(state.scheduleError).toBe("Network error");
      expect(state.isLoadingSchedule).toBe(false);
    });

    it("deduplicates concurrent requests", async () => {
      useTrainingEcosystemStore.setState({ isLoadingSchedule: true });

      await useTrainingEcosystemStore.getState().fetchSchedule(42);

      expect(mockedGetSchedule).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // fetchGaps
  // -------------------------------------------------------------------------

  describe("fetchGaps", () => {
    it("stores skill gaps on success", async () => {
      mockedGetUserGaps.mockResolvedValue(sampleGaps);

      await useTrainingEcosystemStore.getState().fetchGaps(42);

      const state = useTrainingEcosystemStore.getState();
      expect(state.skillGaps).toEqual(sampleGaps);
      expect(state.isLoadingGaps).toBe(false);
      expect(state.gapsError).toBeNull();
    });

    it("sets gapsError on failure", async () => {
      mockedGetUserGaps.mockRejectedValue(new Error("Server error"));

      await useTrainingEcosystemStore.getState().fetchGaps(42);

      const state = useTrainingEcosystemStore.getState();
      expect(state.gapsError).toBe("Server error");
      expect(state.isLoadingGaps).toBe(false);
    });

    it("deduplicates concurrent requests", async () => {
      useTrainingEcosystemStore.setState({ isLoadingGaps: true });

      await useTrainingEcosystemStore.getState().fetchGaps(42);

      expect(mockedGetUserGaps).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // generateMaterials
  // -------------------------------------------------------------------------

  describe("generateMaterials", () => {
    it("adds job to pendingJobs on success", async () => {
      mockedGenerateMaterials.mockResolvedValue({ job_id: "job-123", status: "pending" });

      await useTrainingEcosystemStore.getState().generateMaterials(10, 1);

      const state = useTrainingEcosystemStore.getState();
      expect(state.pendingJobs).toHaveLength(1);
      expect(state.pendingJobs[0].job_id).toBe("job-123");
    });

    it("sets materialsError on failure", async () => {
      mockedGenerateMaterials.mockRejectedValue(new Error("Generation failed"));

      await useTrainingEcosystemStore.getState().generateMaterials(10, 1);

      const state = useTrainingEcosystemStore.getState();
      expect(state.materialsError).toBe("Generation failed");
    });
  });

  // -------------------------------------------------------------------------
  // generateQuestions
  // -------------------------------------------------------------------------

  describe("generateQuestions", () => {
    it("adds job to pendingJobs on success", async () => {
      mockedGenerateQuestions.mockResolvedValue({ job_id: "job-456", status: "pending" });

      await useTrainingEcosystemStore.getState().generateQuestions(10, 1);

      const state = useTrainingEcosystemStore.getState();
      expect(state.pendingJobs).toHaveLength(1);
      expect(state.pendingJobs[0].job_id).toBe("job-456");
    });

    it("sets questionsError on failure", async () => {
      mockedGenerateQuestions.mockRejectedValue(new Error("Question generation failed"));

      await useTrainingEcosystemStore.getState().generateQuestions(10, 1);

      const state = useTrainingEcosystemStore.getState();
      expect(state.questionsError).toBe("Question generation failed");
    });
  });

  // -------------------------------------------------------------------------
  // fetchMaterials
  // -------------------------------------------------------------------------

  describe("fetchMaterials", () => {
    it("stores materials keyed by document_id on success", async () => {
      const materials = [
        { id: 1, document_id: 10, material_type: "executive_summary", status: "approved" },
      ];
      mockedGetMaterials.mockResolvedValue(materials);

      await useTrainingEcosystemStore.getState().fetchMaterials(10);

      const state = useTrainingEcosystemStore.getState();
      expect(state.materials[10]).toEqual(materials);
      expect(state.isLoadingMaterials).toBe(false);
    });

    it("sets materialsError on failure", async () => {
      mockedGetMaterials.mockRejectedValue(new Error("Fetch failed"));

      await useTrainingEcosystemStore.getState().fetchMaterials(10);

      const state = useTrainingEcosystemStore.getState();
      expect(state.materialsError).toBe("Fetch failed");
      expect(state.isLoadingMaterials).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // fetchQuestions
  // -------------------------------------------------------------------------

  describe("fetchQuestions", () => {
    it("stores questions keyed by document_id on success", async () => {
      const questions = [
        { id: 1, document_id: 10, question_type: "multiple_choice", status: "approved" },
      ];
      mockedGetQuestions.mockResolvedValue(questions);

      await useTrainingEcosystemStore.getState().fetchQuestions(10);

      const state = useTrainingEcosystemStore.getState();
      expect(state.questions[10]).toEqual(questions);
      expect(state.isLoadingQuestions).toBe(false);
    });

    it("sets questionsError on failure", async () => {
      mockedGetQuestions.mockRejectedValue(new Error("Fetch failed"));

      await useTrainingEcosystemStore.getState().fetchQuestions(10);

      const state = useTrainingEcosystemStore.getState();
      expect(state.questionsError).toBe("Fetch failed");
      expect(state.isLoadingQuestions).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // startRolePlay
  // -------------------------------------------------------------------------

  describe("startRolePlay", () => {
    it("sets activeSession on success", async () => {
      mockedStartRolePlay.mockResolvedValue({
        session_id: 1,
        first_question: "What is the purpose of this SOP?",
        total_turns: 7,
        id: 1,
        user_id: 42,
        document_id: 10,
        status: "in_progress",
        overall_score: null,
        passed: null,
        turns_completed: 0,
        total_turns: 7,
        session_data: { first_question: "What is the purpose of this SOP?" },
        summary_data: null,
        started_at: "2024-01-15T10:00:00Z",
        completed_at: null,
      });

      await useTrainingEcosystemStore.getState().startRolePlay(10, 1, 42);

      const state = useTrainingEcosystemStore.getState();
      expect(state.activeSession).not.toBeNull();
      expect(state.isLoadingSession).toBe(false);
      expect(state.sessionError).toBeNull();
    });

    it("sets sessionError on failure", async () => {
      mockedStartRolePlay.mockRejectedValue(new Error("Session start failed"));

      await useTrainingEcosystemStore.getState().startRolePlay(10, 1, 42);

      const state = useTrainingEcosystemStore.getState();
      expect(state.sessionError).toBe("Session start failed");
      expect(state.isLoadingSession).toBe(false);
    });

    it("deduplicates concurrent requests", async () => {
      useTrainingEcosystemStore.setState({ isLoadingSession: true });

      await useTrainingEcosystemStore.getState().startRolePlay(10, 1, 42);

      expect(mockedStartRolePlay).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // submitResponse
  // -------------------------------------------------------------------------

  describe("submitResponse", () => {
    it("stores lastEvaluation and updates session on success", async () => {
      const evaluation: TurnEvaluation = {
        evaluation: { factual_accuracy: 0.8, completeness: 0.7, document_reference_quality: 0.6 },
        next_question: "What PPE is required?",
        session_complete: false,
        current_score: 0.72,
      };
      mockedSubmitRolePlayResponse.mockResolvedValue(evaluation);

      useTrainingEcosystemStore.setState({
        activeSession: {
          id: 1,
          user_id: 42,
          document_id: 10,
          status: "in_progress",
          overall_score: null,
          passed: null,
          turns_completed: 1,
          total_turns: 7,
          session_data: null,
          summary_data: null,
          started_at: "2024-01-15T10:00:00Z",
          completed_at: null,
        },
      });

      await useTrainingEcosystemStore.getState().submitResponse(1, "My response");

      const state = useTrainingEcosystemStore.getState();
      expect(state.lastEvaluation).toEqual(evaluation);
      expect(state.isSubmittingResponse).toBe(false);
      expect(state.activeSession?.turns_completed).toBe(2);
      expect(state.activeSession?.overall_score).toBe(0.72);
    });

    it("marks session as completed when session_complete is true", async () => {
      const evaluation: TurnEvaluation = {
        evaluation: { factual_accuracy: 0.9, completeness: 0.8, document_reference_quality: 0.7 },
        next_question: null,
        session_complete: true,
        current_score: 0.82,
      };
      mockedSubmitRolePlayResponse.mockResolvedValue(evaluation);

      useTrainingEcosystemStore.setState({
        activeSession: {
          id: 1,
          user_id: 42,
          document_id: 10,
          status: "in_progress",
          overall_score: null,
          passed: null,
          turns_completed: 6,
          total_turns: 7,
          session_data: null,
          summary_data: null,
          started_at: "2024-01-15T10:00:00Z",
          completed_at: null,
        },
      });

      await useTrainingEcosystemStore.getState().submitResponse(1, "Final response");

      const state = useTrainingEcosystemStore.getState();
      expect(state.activeSession?.status).toBe("completed");
      expect(state.activeSession?.passed).toBe(true);
    });

    it("sets responseError on failure", async () => {
      mockedSubmitRolePlayResponse.mockRejectedValue(new Error("Submit failed"));

      useTrainingEcosystemStore.setState({
        activeSession: {
          id: 1,
          user_id: 42,
          document_id: 10,
          status: "in_progress",
          overall_score: null,
          passed: null,
          turns_completed: 1,
          total_turns: 7,
          session_data: null,
          summary_data: null,
          started_at: "2024-01-15T10:00:00Z",
          completed_at: null,
        },
      });

      await useTrainingEcosystemStore.getState().submitResponse(1, "My response");

      const state = useTrainingEcosystemStore.getState();
      expect(state.responseError).toBe("Submit failed");
      expect(state.isSubmittingResponse).toBe(false);
    });

    it("deduplicates concurrent requests", async () => {
      useTrainingEcosystemStore.setState({ isSubmittingResponse: true });

      await useTrainingEcosystemStore.getState().submitResponse(1, "My response");

      expect(mockedSubmitRolePlayResponse).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Polling
  // -------------------------------------------------------------------------

  describe("polling", () => {
    it("startPolling sets up interval", () => {
      useTrainingEcosystemStore.getState().startPolling();

      const state = useTrainingEcosystemStore.getState();
      expect(state.pollingIntervalId).not.toBeNull();
    });

    it("stopPolling clears interval", () => {
      useTrainingEcosystemStore.getState().startPolling();
      useTrainingEcosystemStore.getState().stopPolling();

      const state = useTrainingEcosystemStore.getState();
      expect(state.pollingIntervalId).toBeNull();
    });

    it("startPolling does not create duplicate intervals", () => {
      useTrainingEcosystemStore.getState().startPolling();
      const firstId = useTrainingEcosystemStore.getState().pollingIntervalId;

      useTrainingEcosystemStore.getState().startPolling();
      const secondId = useTrainingEcosystemStore.getState().pollingIntervalId;

      expect(firstId).toBe(secondId);
    });
  });

  // -------------------------------------------------------------------------
  // Reset
  // -------------------------------------------------------------------------

  describe("reset", () => {
    it("resets all state to initial values", () => {
      useTrainingEcosystemStore.setState({
        schedule: sampleSchedule,
        skillGaps: sampleGaps,
        isLoadingSchedule: true,
        scheduleError: "some error",
      });

      useTrainingEcosystemStore.getState().reset();

      const state = useTrainingEcosystemStore.getState();
      expect(state.schedule).toBeNull();
      expect(state.skillGaps).toEqual([]);
      expect(state.isLoadingSchedule).toBe(false);
      expect(state.scheduleError).toBeNull();
    });

    it("clears polling interval on reset", () => {
      useTrainingEcosystemStore.getState().startPolling();
      expect(useTrainingEcosystemStore.getState().pollingIntervalId).not.toBeNull();

      useTrainingEcosystemStore.getState().reset();

      expect(useTrainingEcosystemStore.getState().pollingIntervalId).toBeNull();
    });
  });
});
