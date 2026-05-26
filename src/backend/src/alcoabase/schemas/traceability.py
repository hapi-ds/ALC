"""Pydantic request/response schemas for traceability endpoints.

Provides validated schemas for traceability matrix generation, orphan detection,
coverage metrics, alerts, and job status tracking.

References:
    - Design doc: Pydantic Schemas (Key Structures)
    - Requirements: 1.1, 1.4, 1.5, 2.3, 3.3, 4.1, 5.1, 5.2, 5.3, 5.4, 5.5,
                    7.1, 7.2, 9.3, 11.3
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Core Data Structures (stored in JSONB) ---


class TraceabilityLinkSchema(BaseModel):
    """Structure stored in TraceabilityMatrix.traceability_links JSONB.

    Represents a single mapping between one requirement and one test case,
    including confidence scoring and detection method metadata.

    Attributes:
        requirement_id: Extracted requirement identifier (e.g., "REQ-001").
        requirement_text: First 500 characters of the requirement statement.
        source_document_uuid: UUID of the source document containing the requirement.
        source_section: Section heading and paragraph index in the source document.
        target_document_uuid: UUID of the target document containing the test case.
        target_section: Section heading and paragraph index in the target document.
        test_case_id: Extracted test case identifier (e.g., "TC-001").
        test_case_text: First 500 characters of the test case description.
        link_confidence: Confidence score between 0.0 and 1.0.
        link_method: Primary detection method that established this link.
        link_methods: All detection methods that identified this link.
        verification_status: Current verification status of the link.
    """

    requirement_id: str = Field(max_length=100)
    requirement_text: str = Field(max_length=500)
    source_document_uuid: str = Field(max_length=12)
    source_section: str
    target_document_uuid: str = Field(max_length=12)
    target_section: str
    test_case_id: str = Field(max_length=100)
    test_case_text: str = Field(max_length=500)
    link_confidence: float = Field(ge=0.0, le=1.0)
    link_method: Literal["exact_id_match", "cross_reference", "semantic_match"]
    link_methods: list[str] = []
    verification_status: Literal["verified", "unverified", "failed"]


class OrphanRequirementSchema(BaseModel):
    """Structure stored in TraceabilityMatrix.orphan_requirements JSONB.

    Represents a requirement with no corresponding test case or validation
    result, classified by severity for prioritization.

    Attributes:
        requirement_id: Extracted requirement identifier.
        requirement_text: First 500 characters of the requirement statement.
        source_document_uuid: UUID of the source document.
        source_section: Section heading and paragraph index.
        severity: Classified severity based on keyword analysis.
        suggested_action: Recommended remediation action.
    """

    requirement_id: str = Field(max_length=100)
    requirement_text: str = Field(max_length=500)
    source_document_uuid: str = Field(max_length=12)
    source_section: str
    severity: Literal["critical", "major", "minor"]
    suggested_action: Literal[
        "create_test_case", "review_requirement", "link_existing_test"
    ]


class OrphanTestCaseSchema(BaseModel):
    """Structure stored in TraceabilityMatrix.orphan_test_cases JSONB.

    Represents a test case that does not trace back to any requirement,
    classified by risk level for prioritization.

    Attributes:
        test_case_id: Extracted test case identifier.
        test_case_text: First 500 characters of the test case description.
        target_document_uuid: UUID of the target document.
        target_section: Section heading and paragraph index.
        risk_level: Classified risk level based on test case content.
        suggested_action: Recommended remediation action.
    """

    test_case_id: str = Field(max_length=100)
    test_case_text: str = Field(max_length=500)
    target_document_uuid: str = Field(max_length=12)
    target_section: str
    risk_level: Literal["high", "medium", "low"]
    suggested_action: Literal[
        "link_to_requirement", "create_requirement", "remove_test_case"
    ]


class CoverageMetricSchema(BaseModel):
    """Structure stored in TraceabilityMatrix.coverage_metrics JSONB.

    Quantitative measures of traceability completeness including coverage
    percentage, orphan counts, and compliance readiness scoring.

    Attributes:
        total_requirements: Count of all requirements extracted from source documents.
        covered_requirements: Count of requirements with at least one link >= 0.5.
        orphan_requirements_count: total_requirements - covered_requirements.
        coverage_percentage: covered/total * 100, rounded to two decimal places.
        total_test_cases: Count of all test cases extracted from target documents.
        linked_test_cases: Count of test cases with at least one link.
        orphan_test_cases_count: total_test_cases - linked_test_cases.
        average_link_confidence: Mean of all link confidence values (0.00 if none).
        compliance_readiness_score: Weighted composite score clamped to [0.0, 100.0].
    """

    total_requirements: int = Field(ge=0)
    covered_requirements: int = Field(ge=0)
    orphan_requirements_count: int = Field(ge=0)
    coverage_percentage: float = Field(ge=0.0, le=100.0)
    total_test_cases: int = Field(ge=0)
    linked_test_cases: int = Field(ge=0)
    orphan_test_cases_count: int = Field(ge=0)
    average_link_confidence: float = Field(ge=0.0, le=1.0)
    compliance_readiness_score: float = Field(ge=0.0, le=100.0)


# --- Request Schemas ---


class GenerateMatrixRequest(BaseModel):
    """Request body for POST /api/traceability/matrices/generate.

    Attributes:
        source_document_ids: Array of document IDs containing requirements (max 10).
        target_document_ids: Array of document IDs containing test cases (max 20).
        matrix_name: Name for the generated matrix (1-200 characters).
        description: Optional description (max 1000 characters).
    """

    source_document_ids: list[int] = Field(min_length=1, max_length=10)
    target_document_ids: list[int] = Field(min_length=1, max_length=20)
    matrix_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class ResolveAlertRequest(BaseModel):
    """Request body for POST /api/traceability/alerts/{alert_id}/resolve.

    Attributes:
        resolution_action: Action taken to resolve the alert.
        resolution_note: Optional note explaining the resolution (max 500 chars).
    """

    resolution_action: Literal[
        "matrix_regenerated", "links_verified", "no_action_needed"
    ]
    resolution_note: str | None = Field(default=None, max_length=500)


# --- Response Schemas ---


class TraceabilityMatrixResponse(BaseModel):
    """Response schema for a full traceability matrix.

    Attributes:
        id: Matrix primary key.
        matrix_id: UUID identifier for the matrix.
        matrix_name: Display name of the matrix.
        description: Optional description text.
        source_document_uuids: Array of source document UUIDs.
        target_document_uuids: Array of target document UUIDs.
        source_document_versions: Array of {document_uuid, version_id} pairs.
        target_document_versions: Array of {document_uuid, version_id} pairs.
        traceability_links: Array of traceability link structures.
        orphan_requirements: Array of orphan requirement structures.
        orphan_test_cases: Array of orphan test case structures.
        coverage_metrics: Coverage metric structure.
        status: Terminal status of the generation job.
        parent_matrix_id: UUID of the previous matrix for the same document set.
        generation_timestamp: When the matrix was generated.
        generation_duration_ms: Duration of generation in milliseconds.
        agent_archetype_used: Name of the agent archetype used.
        model_used: Name of the AI model used.
        total_token_count: Total tokens consumed during generation.
        requesting_user_id: ID of the user who requested generation.
        company_id: ID of the owning company.
        deleted_at: Soft-delete timestamp (null if active).
        created_at: When the record was created.
    """

    id: int
    matrix_id: str
    matrix_name: str
    description: str | None = None
    source_document_uuids: list[str]
    target_document_uuids: list[str]
    source_document_versions: list[dict]
    target_document_versions: list[dict]
    traceability_links: list[TraceabilityLinkSchema]
    orphan_requirements: list[OrphanRequirementSchema]
    orphan_test_cases: list[OrphanTestCaseSchema]
    coverage_metrics: CoverageMetricSchema
    status: Literal["completed", "partial_success", "failed"]
    parent_matrix_id: str | None = None
    generation_timestamp: datetime
    generation_duration_ms: int
    agent_archetype_used: str
    model_used: str
    total_token_count: int
    requesting_user_id: int
    company_id: int
    deleted_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TraceabilityMatrixListResponse(BaseModel):
    """Response schema for paginated list of traceability matrices.

    Attributes:
        matrices: List of matrices for the current page.
        total_count: Total number of matching matrices before pagination.
    """

    matrices: list[TraceabilityMatrixResponse]
    total_count: int


class TraceabilityLinkListResponse(BaseModel):
    """Response schema for paginated list of traceability links.

    Attributes:
        links: List of traceability links for the current page.
        total_count: Total number of matching links before pagination.
    """

    links: list[TraceabilityLinkSchema]
    total_count: int


class OrphanRequirementListResponse(BaseModel):
    """Response schema for paginated list of orphan requirements.

    Attributes:
        orphan_requirements: List of orphan requirements for the current page.
        total_count: Total number of matching orphan requirements before pagination.
    """

    orphan_requirements: list[OrphanRequirementSchema]
    total_count: int


class OrphanTestCaseListResponse(BaseModel):
    """Response schema for paginated list of orphan test cases.

    Attributes:
        orphan_test_cases: List of orphan test cases for the current page.
        total_count: Total number of matching orphan test cases before pagination.
    """

    orphan_test_cases: list[OrphanTestCaseSchema]
    total_count: int


class DocumentCoverageResponse(BaseModel):
    """Response schema for a document's coverage status.

    Returns the latest coverage information for a document across all matrices
    where it appears as a source.

    Attributes:
        document_uuid: UUID of the document.
        latest_matrix_id: Matrix ID of the most recent matrix (null if never analyzed).
        latest_matrix_date: Date of the most recent matrix (null if never analyzed).
        coverage_percentage: Percentage of requirements with traceability links (null if never).
        orphan_requirement_count: Number of orphan requirements in the latest matrix.
        total_requirements: Total requirements extracted in the latest matrix.
        compliance_readiness_score: Weighted compliance score (null if never analyzed).
    """

    document_uuid: str
    latest_matrix_id: str | None = None
    latest_matrix_date: datetime | None = None
    coverage_percentage: float | None = None
    orphan_requirement_count: int = 0
    total_requirements: int = 0
    compliance_readiness_score: float | None = None


class DocumentCoverageBreakdown(BaseModel):
    """Per-document coverage breakdown within the coverage summary.

    Attributes:
        document_uuid: UUID of the source document.
        document_name: Display name of the document.
        coverage_percentage: Coverage percentage for this document.
        orphan_count: Number of orphan requirements for this document.
    """

    document_uuid: str
    document_name: str
    coverage_percentage: float = Field(ge=0.0, le=100.0)
    orphan_count: int = Field(ge=0)


class CoverageSummaryResponse(BaseModel):
    """Response schema for aggregated coverage summary across all matrices.

    Attributes:
        total_matrices_generated: Total number of non-deleted matrices.
        latest_matrix_date: Date of the most recent matrix (null if none).
        average_coverage_percentage: Average coverage across completed matrices.
        total_orphan_requirements: Total orphan requirements across latest matrices.
        total_orphan_test_cases: Total orphan test cases across latest matrices.
        average_compliance_readiness_score: Average compliance score.
        breakdown: Per-document coverage breakdown (max 200 documents).
    """

    total_matrices_generated: int = Field(ge=0)
    latest_matrix_date: datetime | None = None
    average_coverage_percentage: float = Field(ge=0.0, le=100.0)
    total_orphan_requirements: int = Field(ge=0)
    total_orphan_test_cases: int = Field(ge=0)
    average_compliance_readiness_score: float = Field(ge=0.0, le=100.0)
    breakdown: list[DocumentCoverageBreakdown] = []


class CoverageSnapshotSchema(BaseModel):
    """Schema for a single coverage snapshot in history responses.

    Attributes:
        snapshot_date: When the snapshot was taken.
        matrix_id: UUID of the matrix that generated this snapshot.
        source_document_uuid: UUID of the source document.
        coverage_percentage: Coverage percentage at snapshot time.
        orphan_requirements_count: Orphan requirements at snapshot time.
        orphan_test_cases_count: Orphan test cases at snapshot time.
        compliance_readiness_score: Compliance score at snapshot time.
        total_requirements: Total requirements at snapshot time.
        covered_requirements: Covered requirements at snapshot time.
        total_test_cases: Total test cases at snapshot time.
        linked_test_cases: Linked test cases at snapshot time.
    """

    snapshot_date: datetime
    matrix_id: str
    source_document_uuid: str
    coverage_percentage: float = Field(ge=0.0, le=100.0)
    orphan_requirements_count: int = Field(ge=0)
    orphan_test_cases_count: int = Field(ge=0)
    compliance_readiness_score: float = Field(ge=0.0, le=100.0)
    total_requirements: int = Field(ge=0)
    covered_requirements: int = Field(ge=0)
    total_test_cases: int = Field(ge=0)
    linked_test_cases: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class CoverageHistoryResponse(BaseModel):
    """Response schema for paginated coverage history.

    Attributes:
        snapshots: List of coverage snapshots for the current page.
        total_count: Total number of matching snapshots before pagination.
    """

    snapshots: list[CoverageSnapshotSchema]
    total_count: int


class TraceabilityAlertResponse(BaseModel):
    """Response schema for a traceability alert.

    Attributes:
        id: Alert primary key.
        alert_id: UUID identifier for the alert.
        triggering_report_id: UUID of the impact report that triggered this alert.
        affected_matrix_ids: List of matrix UUIDs affected by the change.
        affected_link_count: Number of links affected across all matrices.
        alert_severity: Severity classification of the alert.
        is_resolved: Whether the alert has been resolved.
        resolved_at: When the alert was resolved (null if unresolved).
        resolved_by: ID of the user who resolved the alert (null if unresolved).
        resolution_action: Action taken to resolve (null if unresolved).
        resolution_note: Note explaining the resolution (null if unresolved).
        company_id: ID of the owning company.
        created_at: When the alert was created.
    """

    id: int
    alert_id: str
    triggering_report_id: str
    affected_matrix_ids: list[str]
    affected_link_count: int = Field(ge=0)
    alert_severity: Literal["critical", "major", "minor"]
    is_resolved: bool
    resolved_at: datetime | None = None
    resolved_by: int | None = None
    resolution_action: Literal[
        "matrix_regenerated", "links_verified", "no_action_needed"
    ] | None = None
    resolution_note: str | None = None
    company_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertListResponse(BaseModel):
    """Response schema for paginated list of traceability alerts.

    Attributes:
        alerts: List of alerts for the current page.
        total_count: Total number of matching alerts before pagination.
    """

    alerts: list[TraceabilityAlertResponse]
    total_count: int


class JobStatusResponse(BaseModel):
    """Response schema for traceability job status and progress tracking.

    Attributes:
        job_id: Unique job identifier.
        status: Current job status.
        progress_percent: Progress percentage (0-100).
        current_phase: Current phase of the generation pipeline.
        requirements_extracted: Number of requirements extracted so far.
        test_cases_extracted: Number of test cases extracted so far.
        links_established: Number of links established so far.
        orphans_detected: Number of orphans detected so far.
        error_message: Failure reason (null unless status is failed/partial_success).
        matrix_id: UUID of the generated matrix (present on completion).
        total_requirements: Total requirements in final matrix (present on completion).
        total_test_cases: Total test cases in final matrix (present on completion).
        total_links: Total links in final matrix (present on completion).
        coverage_percentage: Coverage percentage (present on completion).
        orphan_requirements_count: Orphan requirements count (present on completion).
        orphan_test_cases_count: Orphan test cases count (present on completion).
        compliance_readiness_score: Compliance score (present on completion).
        generation_duration_ms: Generation duration in ms (present on completion).
        summary_sentence: AI-generated summary (present on completion, max 200 chars).
    """

    job_id: str
    status: Literal["processing", "completed", "partial_success", "failed"]
    progress_percent: int = Field(ge=0, le=100)
    current_phase: Literal[
        "validating",
        "extracting_requirements",
        "extracting_test_cases",
        "establishing_links",
        "detecting_orphans",
        "computing_metrics",
        "persisting_matrix",
    ]
    requirements_extracted: int = Field(ge=0)
    test_cases_extracted: int = Field(ge=0)
    links_established: int = Field(ge=0)
    orphans_detected: int = Field(ge=0)
    error_message: str | None = Field(default=None, max_length=1000)
    # Completion fields (present when status is completed/partial_success)
    matrix_id: str | None = None
    total_requirements: int | None = None
    total_test_cases: int | None = None
    total_links: int | None = None
    coverage_percentage: float | None = None
    orphan_requirements_count: int | None = None
    orphan_test_cases_count: int | None = None
    compliance_readiness_score: float | None = None
    generation_duration_ms: int | None = None
    summary_sentence: str | None = Field(default=None, max_length=200)


# --- Filter and Pagination Schemas ---


class MatrixFilters(BaseModel):
    """Filter parameters for listing traceability matrices.

    Attributes:
        source_document_uuid: Filter by source document UUID.
        target_document_uuid: Filter by target document UUID.
        status: Filter by matrix status.
        start_date: Filter by generation_timestamp >= start_date (ISO 8601).
        end_date: Filter by generation_timestamp <= end_date (ISO 8601).
        limit: Maximum number of items to return (default 20, max 100).
        offset: Number of items to skip (default 0).
    """

    source_document_uuid: str | None = None
    target_document_uuid: str | None = None
    status: Literal["completed", "partial_success", "failed"] | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class LinkFilters(BaseModel):
    """Filter parameters for listing traceability links.

    Attributes:
        source_document_uuid: Filter by source document UUID.
        target_document_uuid: Filter by target document UUID.
        link_confidence_min: Minimum confidence score (0.0-1.0).
        link_method: Filter by detection method.
        limit: Maximum number of items to return (default 50, max 200).
        offset: Number of items to skip (default 0).
    """

    source_document_uuid: str | None = None
    target_document_uuid: str | None = None
    link_confidence_min: float | None = Field(default=None, ge=0.0, le=1.0)
    link_method: Literal[
        "exact_id_match", "cross_reference", "semantic_match"
    ] | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class OrphanFilters(BaseModel):
    """Filter parameters for listing orphan requirements or test cases.

    Attributes:
        severity: Filter orphan requirements by severity.
        risk_level: Filter orphan test cases by risk level.
        source_document_uuid: Filter by source document UUID (for requirements).
        target_document_uuid: Filter by target document UUID (for test cases).
        limit: Maximum number of items to return (default 20, max 100).
        offset: Number of items to skip (default 0).
    """

    severity: Literal["critical", "major", "minor"] | None = None
    risk_level: Literal["high", "medium", "low"] | None = None
    source_document_uuid: str | None = None
    target_document_uuid: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AlertFilters(BaseModel):
    """Filter parameters for listing traceability alerts.

    Attributes:
        alert_severity: Filter by alert severity.
        is_resolved: Filter by resolution status (default: unresolved only).
        limit: Maximum number of items to return (default 20, max 100).
        offset: Number of items to skip (default 0).
    """

    alert_severity: Literal["critical", "major", "minor"] | None = None
    is_resolved: bool | None = False
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class HistoryFilters(BaseModel):
    """Filter parameters for listing coverage history snapshots.

    Attributes:
        source_document_uuid: Filter by source document UUID.
        start_date: Filter by snapshot_date >= start_date (ISO 8601).
        end_date: Filter by snapshot_date <= end_date (ISO 8601).
        limit: Maximum number of items to return (default 20, max 100).
        offset: Number of items to skip (default 0).
    """

    source_document_uuid: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
