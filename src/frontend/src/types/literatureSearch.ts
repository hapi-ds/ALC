/**
 * TypeScript type definitions for the Literature Search, Citation UI,
 * and Audit Trail Mapping feature (Phase 9.6).
 *
 * These interfaces mirror the backend Pydantic schemas defined in:
 * src/backend/src/alcoabase/literature/search/schemas/
 */

// ─── Enums / Literal Unions ─────────────────────────────────────────────────

/** Search execution mode determining which retrieval strategies to use. */
export type SearchMode = "hybrid" | "keyword" | "semantic";

/** Origin indicator for search results. */
export type Provenance = "external" | "internal";

/** Purpose classification for citation collections. */
export type CollectionPurpose =
  | "clinical_evaluation"
  | "post_market_surveillance"
  | "systematic_literature_review"
  | "risk_assessment"
  | "other";

/** Output format for search results export. */
export type ExportFormat = "csv" | "pdf";

/** Target entity type for traceability link creation. */
export type TraceabilityTargetType = "requirement" | "test_case";

/** Status for saved searches and citation collections. */
export type EntityStatus = "active" | "archived";

// ─── Filter & Query Types ───────────────────────────────────────────────────

/**
 * Faceted filter constraints for narrowing literature search results.
 * All fields are optional; when provided, they act as post-filter
 * constraints without affecting relevance scoring.
 */
export interface SearchFilters {
  date_from: string | null;
  date_to: string | null;
  journals: string[];
  sources: string[];
  publication_types: string[];
  mesh_terms: string[];
  device_class: string[];
}

// ─── Search Result Types ────────────────────────────────────────────────────

/**
 * A single literature search result with metadata and scoring.
 * Represents one item from a hybrid search result set, including
 * provenance information and internalization status.
 */
export interface LiteratureSearchResult {
  id: number;
  title: string;
  authors: string[];
  abstract: string | null;
  publication_date: string | null;
  journal: string;
  source: string;
  publication_type: string;
  mesh_terms: string[];
  doi: string | null;
  relevance_score: number;
  provenance: Provenance;
  full_text_available: boolean;
  is_internalized: boolean;
}

/** Pagination metadata for paginated responses. */
export interface PaginationMeta {
  total_results: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** A single facet value with its associated result count. */
export interface FacetValue {
  value: string;
  count: number;
}

/** Aggregated facet counts for filter dimensions. */
export interface FacetCounts {
  journals: FacetValue[];
  sources: FacetValue[];
  publication_types: FacetValue[];
}

// ─── Saved Searches ─────────────────────────────────────────────────────────

/**
 * A persisted search query configuration for later re-execution.
 * Enables reproducible search methodology documentation for
 * systematic literature reviews and clinical evaluations.
 */
export interface SavedSearch {
  id: number;
  name: string;
  description: string | null;
  query_text: string;
  filters: SearchFilters;
  search_mode: SearchMode;
  include_internal: boolean;
  last_executed_at: string | null;
  last_result_count: number | null;
  status: EntityStatus;
  created_at: string;
}

// ─── Citation Collections ───────────────────────────────────────────────────

/**
 * A named grouping of internalized documents organized for a
 * specific regulatory purpose (e.g., clinical evaluation, PMS report).
 */
export interface CitationCollection {
  id: number;
  name: string;
  description: string | null;
  purpose: CollectionPurpose;
  status: EntityStatus;
  document_count: number;
  created_at: string;
  updated_at: string;
}

/** Reference to a document within a citation collection. */
export interface CitationCollectionDocumentRef {
  document_id: number;
  title: string;
  authors: string[];
  publication_year: number | null;
  doi: string | null;
  position: number;
  added_at: string;
}

/**
 * Detailed citation collection response including the ordered
 * list of document references.
 */
export interface CitationCollectionDetail extends CitationCollection {
  documents: CitationCollectionDocumentRef[];
}

// ─── Traceability Links ─────────────────────────────────────────────────────

/**
 * A link between an internalized document and a requirement or
 * test case in the Traceability Matrix, providing regulatory
 * evidence chains.
 */
export interface TraceabilityLink {
  id: number;
  document_id: number;
  target_type: TraceabilityTargetType;
  target_id: number;
  rationale: string | null;
  created_at: string;
}

// ─── Search History ─────────────────────────────────────────────────────────

/** An entry in the search execution history log. */
export interface SearchHistoryEntry {
  id: number;
  query_text: string;
  search_mode: SearchMode;
  total_results: number;
  executed_at: string;
}

// ─── Internalization ────────────────────────────────────────────────────────

/** Input for a traceability link during internalization. */
export interface TraceabilityLinkInput {
  target_type: TraceabilityTargetType;
  target_id: number;
}

/**
 * Request body for one-click internalization of a literature
 * record into a managed internal Document entity.
 */
export interface InternalizationRequest {
  ingestion_record_id: number;
  document_name: string | null;
  document_type: string;
  tags: string[];
  citation_collection_id: number | null;
  traceability_links: TraceabilityLinkInput[];
}

// ─── Export ─────────────────────────────────────────────────────────────────

/**
 * Request body for generating a CSV or PDF export of search results
 * with optional PRISMA flow diagram inclusion.
 */
export interface ExportRequest {
  search_execution_id: number | null;
  saved_search_id: number | null;
  format: ExportFormat;
  include_prisma_flow: boolean;
}
