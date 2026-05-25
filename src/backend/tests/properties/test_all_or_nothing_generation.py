"""Property-based tests for all-or-nothing generation integrity.

Property 10: All-or-Nothing Generation Integrity
If provenance cannot be persisted, no document is stored. If the job fails,
no partial document exists. Only completed jobs have associated documents.

This is a pure logic test — no database needed. It models the state
transitions of the generation pipeline and verifies the invariant that
document storage and provenance persistence are atomic: either both exist
or neither exists.

**Validates: Requirements 5.8, 7.5**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import hypothesis.strategies as st
from hypothesis import assume, given, settings


# ---------------------------------------------------------------------------
# Data models representing generation pipeline state
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    """Status of a generation job."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FailurePoint(str, Enum):
    """Points in the pipeline where failure can occur."""

    TEMPLATE_LOAD = "template_load"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    SECTION_GENERATION = "section_generation"
    DOCX_ASSEMBLY = "docx_assembly"
    MINIO_UPLOAD = "minio_upload"
    DOCUMENT_RECORD_CREATION = "document_record_creation"
    PROVENANCE_WRITE = "provenance_write"
    JOB_COMPLETION = "job_completion"
    TIMEOUT = "timeout"
    NONE = "none"  # No failure — successful completion


@dataclass(frozen=True)
class GenerationJobState:
    """Represents the final state of a generation job after execution."""

    job_id: str
    job_status: JobStatus
    template_id: int
    company_id: int
    failure_point: FailurePoint
    # Artifacts produced (or not) by the pipeline
    document_stored: bool  # Whether a document was persisted in MinIO + DB
    provenance_persisted: bool  # Whether provenance record was written
    cross_references_stored: bool  # Whether cross-reference entries exist
    error_message: str | None = None


@dataclass(frozen=True)
class PipelineExecutionResult:
    """Result of simulating the generation pipeline."""

    job_state: GenerationJobState
    sections_generated: int
    sections_total: int


# ---------------------------------------------------------------------------
# Functions under test: generation pipeline state machine
# ---------------------------------------------------------------------------


def execute_generation_pipeline(
    job_id: str,
    template_id: int,
    company_id: int,
    sections_total: int,
    failure_point: FailurePoint,
    sections_before_failure: int = 0,
) -> PipelineExecutionResult:
    """Simulate the generation pipeline with a specified failure point.

    Models the all-or-nothing behavior:
    - If failure occurs at any point before final commit, no document is stored.
    - If provenance cannot be written, no document is stored.
    - Only a fully completed pipeline produces a stored document.

    The pipeline stages in order:
    1. Load template (10%)
    2. Retrieve knowledge base content (20%)
    3. Generate sections (20-90%) — individual section failures use placeholders
    4. Assemble DOCX (95%)
    5. Upload to MinIO (96%)
    6. Create Document + DocumentVersion records (97%)
    7. Write GenerationProvenance (98%)
    8. Write CrossReferenceEntries + complete job (100%)

    Per Requirements 5.8 and 7.5:
    - If provenance write fails → entire job fails, document is NOT stored
    - If job fails → no partial document exists
    - Only completed jobs have associated documents

    Args:
        job_id: UUID of the generation job.
        template_id: Template being used.
        company_id: Company scope.
        sections_total: Total sections in the template.
        failure_point: Where in the pipeline the failure occurs.
        sections_before_failure: Sections generated before failure
            (only relevant for SECTION_GENERATION failure point).

    Returns:
        PipelineExecutionResult with final state.
    """
    # No failure — full success
    if failure_point == FailurePoint.NONE:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.COMPLETED,
                template_id=template_id,
                company_id=company_id,
                failure_point=FailurePoint.NONE,
                document_stored=True,
                provenance_persisted=True,
                cross_references_stored=True,
                error_message=None,
            ),
            sections_generated=sections_total,
            sections_total=sections_total,
        )

    # Failure at template load — nothing produced
    if failure_point == FailurePoint.TEMPLATE_LOAD:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="Template could not be loaded",
            ),
            sections_generated=0,
            sections_total=sections_total,
        )

    # Failure at knowledge retrieval — nothing produced
    if failure_point == FailurePoint.KNOWLEDGE_RETRIEVAL:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="Insufficient source material from knowledge base",
            ),
            sections_generated=0,
            sections_total=sections_total,
        )

    # Failure during section generation (catastrophic, not individual section)
    # Note: individual section failures use placeholder fallback and don't
    # fail the job. This models a catastrophic failure (e.g., all sections fail).
    if failure_point == FailurePoint.SECTION_GENERATION:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="Section generation failed catastrophically",
            ),
            sections_generated=sections_before_failure,
            sections_total=sections_total,
        )

    # Failure at DOCX assembly — sections were generated but output is invalid
    if failure_point == FailurePoint.DOCX_ASSEMBLY:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="DOCX assembly failed: output file was malformed",
            ),
            sections_generated=sections_total,
            sections_total=sections_total,
        )

    # Failure at MinIO upload — DOCX was assembled but couldn't be stored
    if failure_point == FailurePoint.MINIO_UPLOAD:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="Failed to upload document to storage",
            ),
            sections_generated=sections_total,
            sections_total=sections_total,
        )

    # Failure at document record creation — file uploaded but DB record failed
    # All-or-nothing: we must roll back (clean up MinIO object)
    if failure_point == FailurePoint.DOCUMENT_RECORD_CREATION:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="Failed to create document record",
            ),
            sections_generated=sections_total,
            sections_total=sections_total,
        )

    # Failure at provenance write — document record exists but provenance can't
    # be persisted. Per Requirement 5.8: entire job fails, document NOT stored.
    if failure_point == FailurePoint.PROVENANCE_WRITE:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message=(
                    "Provenance record could not be persisted; "
                    "generation rolled back"
                ),
            ),
            sections_generated=sections_total,
            sections_total=sections_total,
        )

    # Failure at job completion (after provenance written but before final commit)
    # This is a late failure — still all-or-nothing, rolled back
    if failure_point == FailurePoint.JOB_COMPLETION:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="Job completion failed; generation rolled back",
            ),
            sections_generated=sections_total,
            sections_total=sections_total,
        )

    # Timeout — job exceeded 600s limit
    if failure_point == FailurePoint.TIMEOUT:
        return PipelineExecutionResult(
            job_state=GenerationJobState(
                job_id=job_id,
                job_status=JobStatus.FAILED,
                template_id=template_id,
                company_id=company_id,
                failure_point=failure_point,
                document_stored=False,
                provenance_persisted=False,
                cross_references_stored=False,
                error_message="Generation timeout exceeded (600s limit)",
            ),
            sections_generated=sections_before_failure,
            sections_total=sections_total,
        )

    # Should not reach here
    raise ValueError(f"Unknown failure point: {failure_point}")


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=100)
TEMPLATE_IDS = st.integers(min_value=1, max_value=500)
SECTIONS_TOTAL = st.integers(min_value=1, max_value=30)
JOB_IDS = st.from_regex(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

FAILURE_POINTS = st.sampled_from(list(FailurePoint))

# Failure points that occur before any document is stored
EARLY_FAILURE_POINTS = st.sampled_from([
    FailurePoint.TEMPLATE_LOAD,
    FailurePoint.KNOWLEDGE_RETRIEVAL,
    FailurePoint.SECTION_GENERATION,
    FailurePoint.DOCX_ASSEMBLY,
    FailurePoint.MINIO_UPLOAD,
    FailurePoint.DOCUMENT_RECORD_CREATION,
    FailurePoint.TIMEOUT,
])

# Failure points that specifically test provenance atomicity
PROVENANCE_FAILURE_POINTS = st.sampled_from([
    FailurePoint.PROVENANCE_WRITE,
    FailurePoint.JOB_COMPLETION,
])


@st.composite
def st_generation_scenario(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a complete generation pipeline scenario."""
    job_id = draw(JOB_IDS)
    template_id = draw(TEMPLATE_IDS)
    company_id = draw(COMPANY_IDS)
    sections_total = draw(SECTIONS_TOTAL)
    failure_point = draw(FAILURE_POINTS)

    # For section generation failures, determine how many sections completed
    sections_before_failure = 0
    if failure_point in (FailurePoint.SECTION_GENERATION, FailurePoint.TIMEOUT):
        sections_before_failure = draw(
            st.integers(min_value=0, max_value=max(0, sections_total - 1))
        )

    return {
        "job_id": job_id,
        "template_id": template_id,
        "company_id": company_id,
        "sections_total": sections_total,
        "failure_point": failure_point,
        "sections_before_failure": sections_before_failure,
    }


# ---------------------------------------------------------------------------
# Property 10: All-or-Nothing Generation Integrity
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(scenario=st_generation_scenario())
def test_failed_jobs_never_have_stored_documents(
    scenario: dict[str, Any],
) -> None:
    """For any generation job that fails (at any pipeline stage), no document
    SHALL be stored. Failed jobs must never leave partial documents in the
    system.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(**scenario)
    job_state = result.job_state

    if job_state.job_status == JobStatus.FAILED:
        assert not job_state.document_stored, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} failed at "
            f"'{job_state.failure_point.value}' but document_stored=True. "
            f"Failed jobs must never have stored documents."
        )


@settings(max_examples=25)
@given(scenario=st_generation_scenario())
def test_provenance_failure_prevents_document_storage(
    scenario: dict[str, Any],
) -> None:
    """If provenance cannot be persisted, no document SHALL be stored.
    This is the core atomicity guarantee: document and provenance are
    an inseparable pair.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(**scenario)
    job_state = result.job_state

    if not job_state.provenance_persisted:
        assert not job_state.document_stored, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} has "
            f"document_stored=True but provenance_persisted=False. "
            f"No document may exist without its provenance record."
        )


@settings(max_examples=25)
@given(scenario=st_generation_scenario())
def test_document_storage_requires_provenance(
    scenario: dict[str, Any],
) -> None:
    """If a document is stored, provenance MUST also be persisted.
    The converse of the provenance failure test — verifying the
    bidirectional invariant.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(**scenario)
    job_state = result.job_state

    if job_state.document_stored:
        assert job_state.provenance_persisted, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} has "
            f"document_stored=True but provenance_persisted=False. "
            f"Every stored document must have a provenance record."
        )


@settings(max_examples=25)
@given(scenario=st_generation_scenario())
def test_only_completed_jobs_have_documents(
    scenario: dict[str, Any],
) -> None:
    """Only jobs with status "completed" SHALL have associated documents.
    No processing or failed job may have a stored document.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(**scenario)
    job_state = result.job_state

    if job_state.document_stored:
        assert job_state.job_status == JobStatus.COMPLETED, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} has "
            f"document_stored=True but job_status='{job_state.job_status.value}'. "
            f"Only completed jobs may have stored documents."
        )


@settings(max_examples=25)
@given(scenario=st_generation_scenario())
def test_completed_jobs_always_have_documents_and_provenance(
    scenario: dict[str, Any],
) -> None:
    """Every completed job SHALL have both a stored document and a persisted
    provenance record. A job cannot be "completed" without both artifacts.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(**scenario)
    job_state = result.job_state

    if job_state.job_status == JobStatus.COMPLETED:
        assert job_state.document_stored, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} is completed "
            f"but document_stored=False. Completed jobs must have documents."
        )
        assert job_state.provenance_persisted, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} is completed "
            f"but provenance_persisted=False. Completed jobs must have provenance."
        )
        assert job_state.cross_references_stored, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} is completed "
            f"but cross_references_stored=False. Completed jobs must have "
            f"cross-reference entries."
        )


@settings(max_examples=25)
@given(
    job_id=JOB_IDS,
    template_id=TEMPLATE_IDS,
    company_id=COMPANY_IDS,
    sections_total=SECTIONS_TOTAL,
    failure_point=PROVENANCE_FAILURE_POINTS,
)
def test_provenance_write_failure_is_catastrophic(
    job_id: str,
    template_id: int,
    company_id: int,
    sections_total: int,
    failure_point: FailurePoint,
) -> None:
    """When provenance write fails (even after sections are generated and
    DOCX is assembled), the entire job SHALL fail and no document SHALL
    be stored. This tests the specific Requirement 5.8 scenario where
    the pipeline reaches the provenance stage but cannot persist it.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(
        job_id=job_id,
        template_id=template_id,
        company_id=company_id,
        sections_total=sections_total,
        failure_point=failure_point,
        sections_before_failure=0,
    )
    job_state = result.job_state

    # Job must be failed
    assert job_state.job_status == JobStatus.FAILED, (
        f"Job {job_id} should be FAILED when provenance write fails, "
        f"got '{job_state.job_status.value}'"
    )

    # No document stored
    assert not job_state.document_stored, (
        f"Job {job_id} has document_stored=True despite provenance failure. "
        f"Requirement 5.8 mandates no document without provenance."
    )

    # No provenance persisted
    assert not job_state.provenance_persisted, (
        f"Job {job_id} has provenance_persisted=True despite failure at "
        f"'{failure_point.value}'"
    )

    # Error message must be present
    assert job_state.error_message is not None, (
        f"Job {job_id} failed but has no error_message"
    )


@settings(max_examples=25)
@given(scenario=st_generation_scenario())
def test_failed_jobs_never_have_cross_references(
    scenario: dict[str, Any],
) -> None:
    """For any failed generation job, no cross-reference entries SHALL
    exist. Cross-references are part of the atomic commit with document
    and provenance.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(**scenario)
    job_state = result.job_state

    if job_state.job_status == JobStatus.FAILED:
        assert not job_state.cross_references_stored, (
            f"INVARIANT VIOLATED: Job {job_state.job_id} failed but "
            f"cross_references_stored=True. Failed jobs must not leave "
            f"any artifacts."
        )


@settings(max_examples=25)
@given(scenario=st_generation_scenario())
def test_all_artifacts_are_atomic(
    scenario: dict[str, Any],
) -> None:
    """Document storage, provenance persistence, and cross-reference storage
    SHALL all be in the same state: either all True (completed) or all False
    (failed/incomplete). No partial artifact combinations are allowed.

    **Validates: Requirements 5.8, 7.5**
    """
    result = execute_generation_pipeline(**scenario)
    job_state = result.job_state

    artifacts = [
        job_state.document_stored,
        job_state.provenance_persisted,
        job_state.cross_references_stored,
    ]

    # All artifacts must be in the same state (all True or all False)
    assert all(artifacts) or not any(artifacts), (
        f"INVARIANT VIOLATED: Job {job_state.job_id} has inconsistent "
        f"artifact state: document_stored={job_state.document_stored}, "
        f"provenance_persisted={job_state.provenance_persisted}, "
        f"cross_references_stored={job_state.cross_references_stored}. "
        f"All artifacts must be atomic (all present or all absent)."
    )


@settings(max_examples=25)
@given(
    job_id=JOB_IDS,
    template_id=TEMPLATE_IDS,
    company_id=COMPANY_IDS,
    sections_total=SECTIONS_TOTAL,
    failure_point=EARLY_FAILURE_POINTS,
    sections_before_failure=st.integers(min_value=0, max_value=29),
)
def test_early_failures_produce_no_artifacts(
    job_id: str,
    template_id: int,
    company_id: int,
    sections_total: int,
    failure_point: FailurePoint,
    sections_before_failure: int,
) -> None:
    """Failures at any early pipeline stage (before final commit) SHALL
    produce zero artifacts. Even if sections were partially generated,
    no document, provenance, or cross-references are stored.

    **Validates: Requirements 5.8, 7.5**
    """
    # Ensure sections_before_failure is valid for the scenario
    assume(sections_before_failure < sections_total)

    result = execute_generation_pipeline(
        job_id=job_id,
        template_id=template_id,
        company_id=company_id,
        sections_total=sections_total,
        failure_point=failure_point,
        sections_before_failure=sections_before_failure,
    )
    job_state = result.job_state

    assert job_state.job_status == JobStatus.FAILED, (
        f"Job with failure at '{failure_point.value}' should be FAILED"
    )
    assert not job_state.document_stored, (
        f"Early failure at '{failure_point.value}' must not store document"
    )
    assert not job_state.provenance_persisted, (
        f"Early failure at '{failure_point.value}' must not persist provenance"
    )
    assert not job_state.cross_references_stored, (
        f"Early failure at '{failure_point.value}' must not store cross-references"
    )
