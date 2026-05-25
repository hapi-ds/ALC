/**
 * TypeScript types for the AI Document Generator (Template-Based) feature.
 *
 * These types mirror the backend Pydantic schemas defined in
 * src/backend/src/alcoabase/schemas/document_generation.py and are used by
 * the documentGeneratorStore and document generation UI components.
 *
 * Requirements: 1.1, 2.1, 6.2, 7.3
 */

// ---------------------------------------------------------------------------
// Template Analysis Types
// ---------------------------------------------------------------------------

/** A single section extracted from the template hierarchy. */
export interface TemplateSection {
  heading: string;
  level: number;
  position: number;
  has_placeholder: boolean;
  placeholder_markers: string[];
  has_table: boolean;
  table_columns: string[] | null;
}

/** Complete structural analysis of a template document. */
export interface TemplateAnalysis {
  section_hierarchy: TemplateSection[];
  numbering_scheme: string;
  paragraph_styles: string[];
  table_structures: Array<Record<string, unknown>>;
  header_footer_patterns: Record<string, string>;
  placeholder_markers: Array<Record<string, string>>;
  total_sections: number;
  has_toc: boolean;
  page_layout: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Template Types
// ---------------------------------------------------------------------------

/** A registered document template with optional analysis data. */
export interface DocumentTemplate {
  id: number;
  document_id: number;
  document_version_id: number;
  template_name: string;
  document_type_target: string;
  status: string;
  registered_by: number;
  registered_at: string;
  template_analysis: TemplateAnalysis | null;
}

// ---------------------------------------------------------------------------
// Generation Job Types
// ---------------------------------------------------------------------------

/** Possible states for a generation job. */
export type GenerationJobStatus = "pending" | "processing" | "completed" | "failed";

/** Generation job status and progress tracking. */
export interface GenerationJob {
  job_id: string;
  status: GenerationJobStatus;
  progress_percent: number;
  current_section: string | null;
  sections_completed: number;
  sections_total: number;
  estimated_time_remaining_seconds: number | null;
  error_message: string | null;
  result_document_id: number | null;
  result_document_uuid: string | null;
  result_storage_key: string | null;
  file_size_bytes: number | null;
  generation_duration_ms: number | null;
}

// ---------------------------------------------------------------------------
// Generated Document Types
// ---------------------------------------------------------------------------

/** An AI-generated document in listing views. */
export interface GeneratedDocument {
  id: number;
  document_uuid: string;
  title: string;
  document_type: string;
  current_status: string;
  content_status: string;
  template_name: string;
  generated_at: string;
  generation_duration_ms: number | null;
}

// ---------------------------------------------------------------------------
// Provenance Types
// ---------------------------------------------------------------------------

/** Generation provenance audit trail data. */
export interface ProvenanceData {
  generation_id: string;
  template_id: number;
  template_document_uuid: string;
  source_document_uuids: string[];
  reference_document_ids: number[];
  agent_archetype: string;
  generation_parameters: Record<string, unknown>;
  requesting_user_id: number;
  total_inference_duration_ms: number;
  total_token_count: number;
  section_provenance: Array<Record<string, unknown>>;
  unverified_references: Array<Record<string, unknown>>;
  generation_timestamp: string;
  previous_generation_id: string | null;
}

// ---------------------------------------------------------------------------
// Cross-Reference Types
// ---------------------------------------------------------------------------

/** A single cross-reference entry linking generated content to source documents. */
export interface CrossReference {
  source_document_id: number;
  source_document_title: string;
  reference_type: string;
  reference_identifier: string;
  reference_text: string | null;
  location_in_output: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Request Types
// ---------------------------------------------------------------------------

/** Request payload for registering a .docx file as a Master Template. */
export interface TemplateRegisterRequest {
  document_id: number;
  document_version_id: number;
  template_name: string;
  document_type_target: string;
}

/** Request payload for starting a template-based document generation job. */
export interface GenerateFromTemplateRequest {
  template_id: number;
  title: string;
  generation_instructions: string;
  reference_document_ids?: number[];
  output_folder_path: string;
}

/** Request payload for approving or rejecting an AI-generated document. */
export interface DocumentReviewRequest {
  action: "approve" | "reject";
  reviewer_comments?: string;
}

// ---------------------------------------------------------------------------
// Filter Types
// ---------------------------------------------------------------------------

/** Filter parameters for listing AI-generated documents. */
export interface GeneratedDocFilters {
  content_status?: string;
  document_type?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}
