// src/frontend/src/types/traceability.ts

// ---------------------------------------------------------------------------
// String literal union types for constrained fields
// ---------------------------------------------------------------------------

/** Detection method used to establish a traceability link */
export type LinkMethod = "exact_id_match" | "cross_reference" | "semantic_match";

/** Verification status of a traceability link */
export type VerificationStatus = "verified" | "unverified" | "failed";

/** Terminal status of a traceability matrix generation job */
export type MatrixStatus = "completed" | "partial_success" | "failed";

/** Severity classification for orphan requirements */
export type OrphanSeverity = "critical" | "major" | "minor";

/** Risk level classification for orphan test cases */
export type RiskLevel = "high" | "medium" | "low";

/** Suggested action for orphan requirements */
export type OrphanRequirementAction =
  | "create_test_case"
  | "review_requirement"
  | "link_existing_test";

/** Suggested action for orphan test cases */
export type OrphanTestCaseAction =
  | "link_to_requirement"
  | "create_requirement"
  | "remove_test_case";

/** Alert severity classification */
export type AlertSeverity = "critical" | "major" | "minor";

/** Resolution action for traceability alerts */
export type ResolutionAction =
  | "matrix_regenerated"
  | "links_verified"
  | "no_action_needed";

/** Current status of a traceability job */
export type JobStatusValue =
  | "processing"
  | "completed"
  | "partial_success"
  | "failed";

/** Current phase of the traceability matrix generation pipeline */
export type GenerationPhase =
  | "validating"
  | "extracting_requirements"
  | "extracting_test_cases"
  | "establishing_links"
  | "detecting_orphans"
  | "computing_metrics"
  | "persisting_matrix";

// ---------------------------------------------------------------------------
// Core data structures (matching backend JSONB schemas)
// ---------------------------------------------------------------------------

/** A single mapping between one requirement and one test case */
export interface TraceabilityLink {
  /** Extracted requirement identifier (e.g., "REQ-001") */
  requirement_id: string;
  /** First 500 characters of the requirement statement */
  requirement_text: string;
  /** UUID of the source document containing the requirement */
  source_document_uuid: string;
  /** Section heading and paragraph index in the source document */
  source_section: string;
  /** UUID of the target document containing the test case */
  target_document_uuid: string;
  /** Section heading and paragraph index in the target document */
  target_section: string;
  /** Extracted test case identifier (e.g., "TC-001") */
  test_case_id: string;
  /** First 500 characters of the test case description */
  test_case_text: string;
  /** Confidence score between 0.0 and 1.0 */
  link_confidence: number;
  /** Primary detection method that established this link */
  link_method: LinkMethod;
  /** All detection methods that identified this link */
  link_methods: string[];
  /** Current verification status of the link */
  verification_status: VerificationStatus;
}

/** A requirement with no corresponding test case */
export interface OrphanRequirement {
  /** Extracted requirement identifier */
  requirement_id: string;
  /** First 500 characters of the requirement statement */
  requirement_text: string;
  /** UUID of the source document */
  source_document_uuid: string;
  /** Section heading and paragraph index */
  source_section: string;
  /** Classified severity based on keyword analysis */
  severity: OrphanSeverity;
  /** Recommended remediation action */
  suggested_action: OrphanRequirementAction;
}

/** A test case that does not trace back to any requirement */
export interface OrphanTestCase {
  /** Extracted test case identifier */
  test_case_id: string;
  /** First 500 characters of the test case description */
  test_case_text: string;
  /** UUID of the target document */
  target_document_uuid: string;
  /** Section heading and paragraph index */
  target_section: string;
  /** Classified risk level based on test case content */
  risk_level: RiskLevel;
  /** Recommended remediation action */
  suggested_action: OrphanTestCaseAction;
}

/** Quantitative measures of traceability completeness */
export interface CoverageMetric {
  /** Count of all requirements extracted from source documents */
  total_requirements: number;
  /** Count of requirements with at least one link >= 0.5 */
  covered_requirements: number;
  /** total_requirements - covered_requirements */
  orphan_requirements_count: number;
  /** covered/total * 100, rounded to two decimal places */
  coverage_percentage: number;
  /** Count of all test cases extracted from target documents */
  total_test_cases: number;
  /** Count of test cases with at least one link */
  linked_test_cases: number;
  /** total_test_cases - linked_test_cases */
  orphan_test_cases_count: number;
  /** Mean of all link confidence values (0.00 if none) */
  average_link_confidence: number;
  /** Weighted composite score clamped to [0.0, 100.0] */
  compliance_readiness_score: number;
}

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

/** Document version reference captured at matrix generation time */
export interface DocumentVersion {
  document_uuid: string;
  version_id: number;
}

/** Full traceability matrix record */
export interface TraceabilityMatrix {
  /** Matrix primary key */
  id: number;
  /** UUID identifier for the matrix */
  matrix_id: string;
  /** Display name of the matrix */
  matrix_name: string;
  /** Optional description text */
  description: string | null;
  /** Array of source document UUIDs */
  source_document_uuids: string[];
  /** Array of target document UUIDs */
  target_document_uuids: string[];
  /** Array of source document version references */
  source_document_versions: DocumentVersion[];
  /** Array of target document version references */
  target_document_versions: DocumentVersion[];
  /** Array of traceability link structures */
  traceability_links: TraceabilityLink[];
  /** Array of orphan requirement structures */
  orphan_requirements: OrphanRequirement[];
  /** Array of orphan test case structures */
  orphan_test_cases: OrphanTestCase[];
  /** Coverage metric structure */
  coverage_metrics: CoverageMetric;
  /** Terminal status of the generation job */
  status: MatrixStatus;
  /** UUID of the previous matrix for the same document set */
  parent_matrix_id: string | null;
  /** When the matrix was generated (ISO 8601) */
  generation_timestamp: string;
  /** Duration of generation in milliseconds */
  generation_duration_ms: number;
  /** Name of the agent archetype used */
  agent_archetype_used: string;
  /** Name of the AI model used */
  model_used: string;
  /** Total tokens consumed during generation */
  total_token_count: number;
  /** ID of the user who requested generation */
  requesting_user_id: number;
  /** ID of the owning company */
  company_id: number;
  /** Soft-delete timestamp (null if active, ISO 8601) */
  deleted_at: string | null;
  /** When the record was created (ISO 8601) */
  created_at: string;
}

/** Point-in-time coverage snapshot for trend analysis */
export interface CoverageSnapshot {
  /** When the snapshot was taken (ISO 8601) */
  snapshot_date: string;
  /** UUID of the matrix that generated this snapshot */
  matrix_id: string;
  /** UUID of the source document */
  source_document_uuid: string;
  /** Coverage percentage at snapshot time */
  coverage_percentage: number;
  /** Orphan requirements at snapshot time */
  orphan_requirements_count: number;
  /** Orphan test cases at snapshot time */
  orphan_test_cases_count: number;
  /** Compliance score at snapshot time */
  compliance_readiness_score: number;
  /** Total requirements at snapshot time */
  total_requirements: number;
  /** Covered requirements at snapshot time */
  covered_requirements: number;
  /** Total test cases at snapshot time */
  total_test_cases: number;
  /** Linked test cases at snapshot time */
  linked_test_cases: number;
}

/** Per-document coverage breakdown within the coverage summary */
export interface DocumentCoverageBreakdown {
  /** UUID of the source document */
  document_uuid: string;
  /** Display name of the document */
  document_name: string;
  /** Coverage percentage for this document */
  coverage_percentage: number;
  /** Number of orphan requirements for this document */
  orphan_count: number;
}

/** Aggregated coverage summary across all non-deleted matrices */
export interface CoverageSummary {
  /** Total number of non-deleted matrices */
  total_matrices_generated: number;
  /** Date of the most recent matrix (ISO 8601, null if none) */
  latest_matrix_date: string | null;
  /** Average coverage across completed matrices */
  average_coverage_percentage: number;
  /** Total orphan requirements across latest matrices */
  total_orphan_requirements: number;
  /** Total orphan test cases across latest matrices */
  total_orphan_test_cases: number;
  /** Average compliance score */
  average_compliance_readiness_score: number;
  /** Per-document coverage breakdown */
  breakdown: DocumentCoverageBreakdown[];
}

/** Coverage status for a specific document */
export interface DocumentCoverage {
  /** UUID of the document */
  document_uuid: string;
  /** Matrix ID of the most recent matrix (null if never analyzed) */
  latest_matrix_id: string | null;
  /** Date of the most recent matrix (ISO 8601, null if never analyzed) */
  latest_matrix_date: string | null;
  /** Percentage of requirements with traceability links (null if never) */
  coverage_percentage: number | null;
  /** Number of orphan requirements in the latest matrix */
  orphan_requirement_count: number;
  /** Total requirements extracted in the latest matrix */
  total_requirements: number;
  /** Weighted compliance score (null if never analyzed) */
  compliance_readiness_score: number | null;
}

/** A traceability alert triggered by an impact report */
export interface TraceabilityAlert {
  /** Alert primary key */
  id: number;
  /** UUID identifier for the alert */
  alert_id: string;
  /** UUID of the impact report that triggered this alert */
  triggering_report_id: string;
  /** List of matrix UUIDs affected by the change */
  affected_matrix_ids: string[];
  /** Number of links affected across all matrices */
  affected_link_count: number;
  /** Severity classification of the alert */
  alert_severity: AlertSeverity;
  /** Whether the alert has been resolved */
  is_resolved: boolean;
  /** When the alert was resolved (ISO 8601, null if unresolved) */
  resolved_at: string | null;
  /** ID of the user who resolved the alert (null if unresolved) */
  resolved_by: number | null;
  /** Action taken to resolve (null if unresolved) */
  resolution_action: ResolutionAction | null;
  /** Note explaining the resolution (null if unresolved) */
  resolution_note: string | null;
  /** ID of the owning company */
  company_id: number;
  /** When the alert was created (ISO 8601) */
  created_at: string;
}

/** Tracks stale traceability links when requirements change */
export interface StaleLinkMarker {
  /** Matrix UUID this marker belongs to */
  matrix_id: string;
  /** Extracted requirement identifier (e.g., "REQ-001") */
  requirement_id: string;
  /** When the link became stale (ISO 8601) */
  stale_since: string;
  /** Reason the link is stale (max 500 chars) */
  stale_reason: string;
  /** UUID of the impact report that triggered staleness */
  triggering_report_id: string;
  /** Whether the stale marker has been cleared */
  is_cleared: boolean;
  /** When the marker was cleared (ISO 8601, null if not cleared) */
  cleared_at: string | null;
  /** ID of the owning company */
  company_id: number;
  /** When the marker was created (ISO 8601) */
  created_at: string;
}

/** Job status and progress tracking for matrix generation */
export interface JobStatus {
  /** Unique job identifier */
  job_id: string;
  /** Current job status */
  status: JobStatusValue;
  /** Progress percentage (0-100) */
  progress_percent: number;
  /** Current phase of the generation pipeline */
  current_phase: GenerationPhase;
  /** Number of requirements extracted so far */
  requirements_extracted: number;
  /** Number of test cases extracted so far */
  test_cases_extracted: number;
  /** Number of links established so far */
  links_established: number;
  /** Number of orphans detected so far */
  orphans_detected: number;
  /** Failure reason (null unless status is failed/partial_success) */
  error_message: string | null;
  /** UUID of the generated matrix (present on completion) */
  matrix_id: string | null;
  /** Total requirements in final matrix (present on completion) */
  total_requirements: number | null;
  /** Total test cases in final matrix (present on completion) */
  total_test_cases: number | null;
  /** Total links in final matrix (present on completion) */
  total_links: number | null;
  /** Coverage percentage (present on completion) */
  coverage_percentage: number | null;
  /** Orphan requirements count (present on completion) */
  orphan_requirements_count: number | null;
  /** Orphan test cases count (present on completion) */
  orphan_test_cases_count: number | null;
  /** Compliance score (present on completion) */
  compliance_readiness_score: number | null;
  /** Generation duration in ms (present on completion) */
  generation_duration_ms: number | null;
  /** AI-generated summary (present on completion, max 200 chars) */
  summary_sentence: string | null;
}

// ---------------------------------------------------------------------------
// Filter and pagination types
// ---------------------------------------------------------------------------

/** Filter parameters for listing traceability matrices */
export interface MatrixFilters {
  /** Filter by source document UUID */
  source_document_uuid?: string;
  /** Filter by target document UUID */
  target_document_uuid?: string;
  /** Filter by matrix status */
  status?: MatrixStatus;
  /** Filter by generation_timestamp >= start_date (ISO 8601) */
  start_date?: string;
  /** Filter by generation_timestamp <= end_date (ISO 8601) */
  end_date?: string;
  /** Maximum number of items to return (1-100, default 20) */
  limit?: number;
  /** Number of items to skip (default 0) */
  offset?: number;
}

/** Filter parameters for listing traceability links */
export interface LinkFilters {
  /** Filter by source document UUID */
  source_document_uuid?: string;
  /** Filter by target document UUID */
  target_document_uuid?: string;
  /** Minimum confidence score (0.0-1.0) */
  link_confidence_min?: number;
  /** Filter by detection method */
  link_method?: LinkMethod;
  /** Maximum number of items to return (1-200, default 50) */
  limit?: number;
  /** Number of items to skip (default 0) */
  offset?: number;
}

/** Filter parameters for listing orphan requirements or test cases */
export interface OrphanFilters {
  /** Filter orphan requirements by severity */
  severity?: OrphanSeverity;
  /** Filter orphan test cases by risk level */
  risk_level?: RiskLevel;
  /** Filter by source document UUID (for requirements) */
  source_document_uuid?: string;
  /** Filter by target document UUID (for test cases) */
  target_document_uuid?: string;
  /** Maximum number of items to return (1-100, default 20) */
  limit?: number;
  /** Number of items to skip (default 0) */
  offset?: number;
}

/** Filter parameters for listing traceability alerts */
export interface AlertFilters {
  /** Filter by alert severity */
  alert_severity?: AlertSeverity;
  /** Filter by resolution status (default: unresolved only) */
  is_resolved?: boolean;
  /** Maximum number of items to return (1-100, default 20) */
  limit?: number;
  /** Number of items to skip (default 0) */
  offset?: number;
}

/** Filter parameters for listing coverage history snapshots */
export interface HistoryFilters {
  /** Filter by source document UUID */
  source_document_uuid?: string;
  /** Filter by snapshot_date >= start_date (ISO 8601) */
  start_date?: string;
  /** Filter by snapshot_date <= end_date (ISO 8601) */
  end_date?: string;
  /** Maximum number of items to return (1-100, default 20) */
  limit?: number;
  /** Number of items to skip (default 0) */
  offset?: number;
}

// ---------------------------------------------------------------------------
// Request types
// ---------------------------------------------------------------------------

/** Request body for POST /api/traceability/matrices/generate */
export interface GenerateMatrixRequest {
  /** Array of document IDs containing requirements (max 10) */
  source_document_ids: number[];
  /** Array of document IDs containing test cases (max 20) */
  target_document_ids: number[];
  /** Name for the generated matrix (1-200 characters) */
  matrix_name: string;
  /** Optional description (max 1000 characters) */
  description?: string;
}

/** Request body for POST /api/traceability/alerts/{alert_id}/resolve */
export interface ResolveAlertRequest {
  /** Action taken to resolve the alert */
  resolution_action: ResolutionAction;
  /** Optional note explaining the resolution (max 500 chars) */
  resolution_note?: string;
}

// ---------------------------------------------------------------------------
// Paginated API response types
// ---------------------------------------------------------------------------

/** Paginated response for traceability matrices */
export interface TraceabilityMatrixListResponse {
  /** List of matrices for the current page */
  matrices: TraceabilityMatrix[];
  /** Total number of matching matrices before pagination */
  total_count: number;
}

/** Paginated response for traceability links */
export interface TraceabilityLinkListResponse {
  /** List of traceability links for the current page */
  links: TraceabilityLink[];
  /** Total number of matching links before pagination */
  total_count: number;
}

/** Paginated response for orphan requirements */
export interface OrphanRequirementListResponse {
  /** List of orphan requirements for the current page */
  orphan_requirements: OrphanRequirement[];
  /** Total number of matching orphan requirements before pagination */
  total_count: number;
}

/** Paginated response for orphan test cases */
export interface OrphanTestCaseListResponse {
  /** List of orphan test cases for the current page */
  orphan_test_cases: OrphanTestCase[];
  /** Total number of matching orphan test cases before pagination */
  total_count: number;
}

/** Paginated response for coverage history snapshots */
export interface CoverageHistoryResponse {
  /** List of coverage snapshots for the current page */
  snapshots: CoverageSnapshot[];
  /** Total number of matching snapshots before pagination */
  total_count: number;
}

/** Paginated response for traceability alerts */
export interface AlertListResponse {
  /** List of alerts for the current page */
  alerts: TraceabilityAlert[];
  /** Total number of matching alerts before pagination */
  total_count: number;
}
