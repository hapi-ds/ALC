/**
 * TypeScript types for Video Alignment data structures.
 *
 * Mirrors the backend Pydantic schemas in video_alignment.py.
 * Used by the VideoAlignment component and related UI.
 */

/** Severity levels for discrepancies */
export type DiscrepancySeverity = "critical" | "major" | "minor";

/** A matched step in the discrepancy report */
export interface MatchedStep {
  video_step_description: string;
  sop_step_text: string;
  similarity_score: number;
  video_timestamp_start: number;
  video_timestamp_end: number;
}

/** A missing or extra step in the discrepancy report */
export interface DiscrepancyStep {
  step_description: string;
  source: "video" | "sop";
  severity: DiscrepancySeverity;
  recommendation: string;
}

/** An order mismatch in the discrepancy report */
export interface OrderMismatch {
  video_step_description: string;
  sop_step_text: string;
  video_position: number;
  sop_position: number;
  severity: DiscrepancySeverity;
}

/** Full discrepancy report response from the API */
export interface DiscrepancyReport {
  alignment_score: number;
  matched_steps: MatchedStep[];
  missing_steps: DiscrepancyStep[];
  extra_steps: DiscrepancyStep[];
  order_mismatches: OrderMismatch[];
  total_video_steps: number;
  total_sop_steps: number;
  generated_at: string;
  requires_review: boolean;
}

/** Job status values for async processing operations */
export type JobStatus = "processing" | "completed" | "failed";

/** Response from POST endpoints that trigger long-running operations (HTTP 202) */
export interface JobStatusResponse {
  job_id: string;
  status: string;
  estimated_duration_seconds: number;
}

/** Detailed job status from the polling endpoint */
export interface JobStatusDetail {
  job_id: string;
  status: JobStatus;
  started_at: string;
  completed_at: string | null;
  progress_percent: number;
  result_reference: string | null;
  error_message: string | null;
}

/** A video step with detail information for the step detail view */
export interface VideoStepInfo {
  /** Description of the step */
  description: string;
  /** Start timestamp in seconds */
  timestamp_start: number;
  /** End timestamp in seconds */
  timestamp_end: number;
  /** Audio transcript text for this step (if available) */
  audio_transcript?: string | null;
  /** Frame thumbnail URLs for this step's timestamp range */
  frame_thumbnails: string[];
}

/** Linked SOP document info for the summary panel */
export interface LinkedSOPInfo {
  /** UUID of the linked SOP document */
  document_uuid: string;
  /** Title of the SOP document */
  title: string;
  /** Version of the SOP at time of linking */
  version: string;
  /** URL/path to navigate to the SOP document */
  link: string;
}

/** Extended report with linked SOP info for the summary panel */
export interface DiscrepancyReportWithSOP extends DiscrepancyReport {
  /** Linked SOP document information */
  linked_sop?: LinkedSOPInfo;
}
