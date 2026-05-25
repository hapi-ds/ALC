// src/frontend/src/types/impactAnalysis.ts

// ---------------------------------------------------------------------------
// String literal union types for constrained fields
// ---------------------------------------------------------------------------

/** Dependency relationship type between two documents */
export type DependencyType =
  | "validates"
  | "references"
  | "implements"
  | "trains_on"
  | "derived_from";

/** Assessed severity of a change's impact on a dependent document */
export type ImpactSeverity = "critical" | "major" | "minor" | "unknown";

/** Gap severity (excludes "unknown" since gaps are always classified) */
export type GapSeverity = "critical" | "major" | "minor";

/** Classification of a gap between source and target documents */
export type GapType = "missing" | "contradicts" | "incomplete" | "outdated";

/** Terminal status of an impact analysis or gap analysis job */
export type ReportStatus = "completed" | "partial_success" | "failed";

/** Current status of a running or completed job */
export type JobStatusValue = "processing" | "completed" | "partial_success" | "failed";

/** Current phase of the impact analysis pipeline */
export type AnalysisPhase =
  | "computing_delta"
  | "querying_dependencies"
  | "assessing_impact"
  | "analyzing_gaps"
  | "persisting_report";

/** Recommended remediation action for an affected item */
export type RecommendedAction =
  | "update_required"
  | "review_recommended"
  | "retraining_required"
  | "manual_review_required";

/** Notification type (currently only change_impact) */
export type NotificationType = "change_impact";

// ---------------------------------------------------------------------------
// Core data structures (matching backend JSONB schemas)
// ---------------------------------------------------------------------------

/** A document or training task identified as impacted by a change */
export interface AffectedItem {
  /** UUID of the affected document (null for training tasks) */
  affected_document_uuid: string | null;
  /** ID of the affected training task (null for documents) */
  training_task_id: number | null;
  /** Display title of the affected item */
  affected_document_title: string;
  /** Type of dependency relationship to the changed document */
  dependency_type: string;
  /** Assessed severity of the impact */
  impact_severity: ImpactSeverity;
  /** Section headings in the dependent document that are impacted */
  affected_sections: string[];
  /** One-sentence description of why the item is affected (max 500 chars) */
  change_summary: string;
  /** Recommended remediation action */
  recommended_action: RecommendedAction;
  /** First 500 characters of the prompt sent to the AI agent */
  inference_prompt_summary: string;
  /** First 500 characters of the AI response */
  model_response_summary: string;
  /** Token count for this individual assessment */
  token_count: number;
}

/** A specific mismatch identified between source and target documents */
export interface GapFinding {
  /** Section heading and paragraph index in the source document */
  source_section: string;
  /** First 300 characters of the relevant source text */
  source_content_excerpt: string;
  /** Section in the target document, or "not_found" */
  target_section: string;
  /** First 300 characters of the existing target text */
  target_content_excerpt: string;
  /** Classification of the gap */
  gap_type: GapType;
  /** Assessed severity of the gap */
  severity: GapSeverity;
  /** AI-generated recommendation for fixing the gap */
  remediation_suggestion: string;
  /** First 500 characters of the prompt sent to the AI agent */
  inference_prompt_summary: string;
  /** First 500 characters of the AI response */
  model_response_summary: string;
  /** Token count for this individual assessment */
  token_count: number;
}

/** Semantic difference between two versions of a document */
export interface ChangeDelta {
  /** Sections present in new version but absent in old */
  sections_added: Record<string, string>[];
  /** Sections present in both with different content */
  sections_modified: Record<string, string>[];
  /** Sections present in old version but absent in new */
  sections_deleted: Record<string, string>[];
  /** Count of changes by significance level */
  significance_levels: {
    high: number;
    medium: number;
    low: number;
  };
  /** Additional metadata (e.g., fallback_used, user_attribution_unavailable) */
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

/** A single directed edge in the document dependency graph */
export interface DependencyEdge {
  /** Edge primary key */
  id: number;
  /** UUID of the source document */
  source_document_uuid: string;
  /** UUID of the target document */
  target_document_uuid: string;
  /** Type of dependency relationship */
  dependency_type: DependencyType;
  /** Confidence score (0.0 to 1.0) */
  confidence_score: number;
  /** Array of reference identifiers linking the documents */
  detected_references: string[];
  /** When the edge was last verified (ISO 8601) */
  last_verified_at: string;
  /** When the edge was created (ISO 8601) */
  created_at: string;
  /** When the edge was last updated (ISO 8601, null if never updated) */
  updated_at: string | null;
}

/** Full impact analysis report */
export interface ImpactReport {
  /** Report primary key */
  id: number;
  /** UUID identifier for the report */
  report_id: string;
  /** UUID of the document that triggered the analysis */
  triggering_document_uuid: string;
  /** Version ID that triggered the analysis */
  triggering_version_id: number;
  /** Structured summary of what changed */
  change_delta_summary: ChangeDelta;
  /** List of affected items with severity and recommendations */
  affected_items: AffectedItem[];
  /** List of gap findings */
  gap_findings: GapFinding[];
  /** Terminal status of the analysis job */
  status: ReportStatus;
  /** When the analysis was performed (ISO 8601) */
  analysis_timestamp: string;
  /** Duration of the analysis in milliseconds */
  analysis_duration_ms: number;
  /** Name of the agent archetype used */
  agent_archetype_used: string;
  /** Name of the AI model used */
  model_used: string;
  /** Total tokens consumed across all assessments */
  total_token_count: number;
  /** ID of the user who requested the analysis (null for auto-triggered) */
  requesting_user_id: number | null;
  /** ID of the owning company */
  company_id: number;
  /** When the report record was created (ISO 8601) */
  created_at: string;
}

/** An impact notification for a document owner */
export interface ImpactNotification {
  /** Notification primary key */
  id: number;
  /** UUID of the associated impact report */
  report_id: string;
  /** UUID of the affected document */
  affected_document_uuid: string;
  /** Type of notification */
  notification_type: NotificationType;
  /** Severity of the impact */
  impact_severity: ImpactSeverity;
  /** Summary of the change that caused the notification (max 2000 chars) */
  change_summary: string;
  /** ID of the user targeted by the notification */
  target_user_id: number;
  /** Whether the notification has been acknowledged */
  is_acknowledged: boolean;
  /** When the notification was acknowledged (ISO 8601, null if not acknowledged) */
  acknowledged_at: string | null;
  /** ID of the user who acknowledged the notification (null if not acknowledged) */
  acknowledged_by: number | null;
  /** ID of the owning company */
  company_id: number;
  /** When the notification was created (ISO 8601) */
  created_at: string;
}

/** Job status and progress tracking */
export interface JobStatus {
  /** Unique job identifier */
  job_id: string;
  /** Current job status */
  status: JobStatusValue;
  /** Progress percentage (0-100) */
  progress_percent: number;
  /** Current phase of the analysis pipeline */
  current_phase: AnalysisPhase;
  /** Number of items assessed so far */
  items_assessed: number;
  /** Total number of items to assess */
  items_total: number;
  /** Number of critical findings discovered */
  critical_findings_count: number;
  /** Number of major findings discovered */
  major_findings_count: number;
  /** Number of minor findings discovered */
  minor_findings_count: number;
  /** Failure reason (null unless status is failed, max 1000 chars) */
  error_message: string | null;
}

/** Document impact analysis status */
export interface DocumentImpactStatus {
  /** UUID of the document */
  document_uuid: string;
  /** When the last analysis was performed (ISO 8601, null if never) */
  last_analysis_date: string | null;
  /** Report ID of the last analysis (null if never) */
  last_analysis_report_id: string | null;
  /** Number of unresolved critical findings */
  outstanding_critical_count: number;
  /** Number of unresolved major findings */
  outstanding_major_count: number;
  /** True if no unresolved critical or major findings exist */
  is_up_to_date: boolean;
}

// ---------------------------------------------------------------------------
// Paginated API response types
// ---------------------------------------------------------------------------

/** Paginated response for impact reports */
export interface ImpactReportListResponse {
  /** List of impact reports for the current page */
  reports: ImpactReport[];
  /** Total number of matching reports before pagination */
  total_count: number;
}

/** Paginated response for dependency graph edges */
export interface DependencyEdgeListResponse {
  /** List of dependency edges for the current page */
  edges: DependencyEdge[];
  /** Total number of matching edges before pagination */
  total_count: number;
}

/** Paginated response for gap analysis findings */
export interface GapAnalysisResultResponse {
  /** Result primary key */
  id: number;
  /** Job identifier for the gap analysis */
  job_id: string;
  /** UUID of the source document */
  source_document_uuid: string;
  /** UUID of the target document */
  target_document_uuid: string;
  /** List of gap findings */
  gap_findings: GapFinding[];
  /** Total number of gaps detected (before limiting) */
  total_gaps_detected: number;
  /** Number of gaps retained (after limiting to top 100) */
  gaps_retained: number;
  /** Terminal status of the gap analysis */
  status: ReportStatus;
  /** Duration of the analysis in milliseconds */
  analysis_duration_ms: number;
  /** ID of the owning company */
  company_id: number;
  /** When the result record was created (ISO 8601) */
  created_at: string;
}

/** Paginated response for notifications */
export interface NotificationListResponse {
  /** List of notifications for the current page */
  notifications: ImpactNotification[];
  /** Total number of matching notifications before pagination */
  total_count: number;
}

// ---------------------------------------------------------------------------
// Filter and pagination types
// ---------------------------------------------------------------------------

/** Filter parameters for listing impact reports */
export interface ReportFilters {
  /** Filter by triggering document UUID */
  triggering_document_uuid?: string;
  /** Filter by reports containing at least one finding of this severity */
  severity?: GapSeverity;
  /** Filter by analysis timestamp >= start_date (ISO 8601) */
  start_date?: string;
  /** Filter by analysis timestamp <= end_date (ISO 8601) */
  end_date?: string;
  /** Filter by report status */
  status?: ReportStatus;
}

/** Filter parameters for listing dependency graph edges */
export interface GraphFilters {
  /** Filter by source document UUID */
  source_document_uuid?: string;
  /** Filter by target document UUID */
  target_document_uuid?: string;
  /** Filter by dependency type */
  dependency_type?: DependencyType;
}

/** Pagination parameters for list endpoints */
export interface PaginationParams {
  /** Maximum number of items to return (1-200, default 20) */
  limit?: number;
  /** Number of items to skip (default 0) */
  offset?: number;
}
