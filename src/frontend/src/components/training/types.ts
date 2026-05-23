/**
 * Training Management UI - Type Definitions
 *
 * These types model the training task lifecycle, content structure,
 * and supporting data shapes used across the training management feature.
 */

/** Training task from API response (GET /api/training/tasks) */
export interface TrainingTask {
  id: number;
  sop_document_uuid: string;
  sop_version: string;
  assigned_user_id: number;
  task_title: string;
  is_completed: boolean;
  completed_at: string | null;
  created_at: string;
}

/** Training status from API response (GET /api/training/status/{sop_uuid}/{version}) */
export interface TrainingStatus {
  sop_document_uuid: string;
  sop_version: string;
  total_tasks: number;
  completed_tasks: number;
  is_complete: boolean;
}

/** Training content from API response (GET /api/training/content/{content_id}) */
export interface TrainingContent {
  content_id: string;
  sop_document_uuid: string;
  sop_version: string;
  summary: string;
  quiz_questions: QuizQuestion[];
  procedural_steps: ProceduralStep[];
  safety_points: string[];
  status: "draft" | "pending_review" | "approved" | "rejected";
  generated_at: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
  review_notes: string;
}

/** Quiz question within training content */
export interface QuizQuestion {
  question_id: string;
  question: string;
  correct_answer: string;
  distractors: string[];
  sop_section_ref: string;
}

/** Procedural step within training content */
export interface ProceduralStep {
  step_number: number;
  description: string;
  is_safety_critical: boolean;
  safety_note: string;
}

/** Filter type for task list */
export type TaskFilter = "all" | "pending" | "completed";

/** Training statistics (computed client-side from tasks) */
export interface TrainingStatistics {
  pending: number;
  completed: number;
  total: number;
  completionPercentage: number | null; // null when total is 0
}

/** Gate cache mapping sop_document_uuid+version to completion boolean */
export type GateCache = Record<string, boolean>;

/** Quiz submission result from POST /api/training/quiz/submit */
export interface QuizAttemptResult {
  attempt_id: number;
  score: number;
  total_questions: number;
  passed: boolean;
  passing_score_threshold: number;
  correct_answers: Record<string, string>;
  attempted_at: string;
}

/** Quiz pass check from GET /api/training/quiz/passed/{content_id} */
export interface QuizPassStatus {
  content_id: string;
  user_id: number;
  has_passed: boolean;
  best_score: number | null;
}

/** Quiz results from GET /api/training/quiz/results/{content_id} */
export interface QuizResultsResponse {
  results: QuizAttemptHistoryEntry[];
  has_passed: boolean;
}

/** Single quiz attempt entry in results history */
export interface QuizAttemptHistoryEntry {
  attempt_id: number;
  score: number;
  total_questions: number;
  passed: boolean;
  attempted_at: string;
  answers: Record<string, string>;
}
