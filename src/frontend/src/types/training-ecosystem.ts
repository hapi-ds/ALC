/**
 * TypeScript types for the AI-Enhanced Training Ecosystem.
 *
 * Mirrors the backend Pydantic response schemas defined in
 * `alcoabase/schemas/training_ecosystem.py`.
 */

// ---------------------------------------------------------------------------
// Training Schedule & Skill Gaps
// ---------------------------------------------------------------------------

export interface TrainingSchedule {
  id: number;
  user_id: number;
  schedule_data: Record<string, unknown>;
  compliance_percentage: number;
  total_items: number;
  completed_items: number;
  generated_at: string;
  last_recalculated_at: string;
}

export interface SkillGap {
  id: number;
  document_id: number;
  document_title: string;
  gap_type: string;
  priority: string;
  days_overdue: number | null;
  blocks_access: boolean;
  identified_at: string;
}

export interface CompanyGapReport {
  total_users_with_gaps: number;
  company_compliance_percentage: number;
  top_documents: Record<string, unknown>[];
  top_users: Record<string, unknown>[];
  by_framework: Record<string, number> | null;
  total: number;
}

// ---------------------------------------------------------------------------
// Training Materials
// ---------------------------------------------------------------------------

export interface TrainingMaterial {
  id: number;
  document_id: number;
  document_version_id: number;
  material_type: string;
  content_data: Record<string, unknown>;
  learning_objectives: string[];
  estimated_duration_minutes: number;
  status: string;
  generated_by_agent_id: string | null;
  inference_duration_ms: number | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Generated Questions
// ---------------------------------------------------------------------------

export interface GeneratedQuestion {
  id: number;
  question_text: string;
  question_type: string;
  correct_answer: string | null;
  distractors: string[] | null;
  explanation: string | null;
  difficulty_level: string;
  bloom_taxonomy_level: string;
  sop_section_ref: string;
  status: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Virtual Audit / Role-Play
// ---------------------------------------------------------------------------

export interface VirtualAuditSession {
  id: number;
  user_id: number;
  document_id: number;
  status: string;
  overall_score: number | null;
  passed: boolean | null;
  turns_completed: number;
  total_turns: number;
  session_data: Record<string, unknown> | null;
  summary_data: Record<string, unknown> | null;
  started_at: string;
  completed_at: string | null;
}

export interface TurnEvaluation {
  evaluation: Record<string, number>;
  next_question: string | null;
  session_complete: boolean;
  current_score: number;
}

// ---------------------------------------------------------------------------
// Dynamic Feedback
// ---------------------------------------------------------------------------

export interface DynamicFeedback {
  correct_answer: string;
  paragraph_text: string;
  section_reference: string;
  page_number: number | null;
  explanation: string;
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export interface Job {
  job_id: string;
  status: string;
}
