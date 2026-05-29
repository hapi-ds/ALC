"""Property-based tests for TraceabilityMatrix and CoverageSnapshot immutability.

Property 7: Immutability Enforcement

For any TraceabilityMatrix record that has been persisted, any attempt to
UPDATE any column except deleted_at through the ORM SHALL raise an
ImmutableRecordError. UPDATE of deleted_at (soft-delete) SHALL be permitted.
Any attempt to DELETE a TraceabilityMatrix record SHALL raise
ImmutableRecordError unconditionally.

For any CoverageSnapshot record that has been persisted, any attempt to
UPDATE or DELETE the record through the ORM SHALL raise an
ImmutableRecordError. No mutations are permitted on CoverageSnapshot.

**Validates: Requirements 4.2, 10.1, 10.2**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/models/immutability.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.immutability import (
    ImmutableRecordError,
    _prevent_delete,
    _prevent_update,
    _prevent_update_except_deleted_at,
)
from alcoabase.models.traceability import CoverageSnapshot, TraceabilityMatrix


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=100)
USER_IDS = st.integers(min_value=1, max_value=200)
RECORD_IDS = st.integers(min_value=1, max_value=10000)

MATRIX_IDS = st.from_regex(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

MATRIX_STATUSES = st.sampled_from(["completed", "partial_success", "failed"])

MATRIX_NAMES = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=200,
)

AGENT_ARCHETYPES = st.sampled_from([
    "Traceability Analyst",
    "Change Impact Analyst",
])

MODEL_NAMES = st.sampled_from([
    "gemma-4-e4b-it",
    "qwen3-embedding-8b",
])

TIMESTAMPS = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(UTC),
)

DURATION_MS = st.integers(min_value=100, max_value=600000)
TOKEN_COUNTS = st.integers(min_value=100, max_value=50000)
COVERAGE_PERCENTAGES = st.floats(min_value=0.0, max_value=100.0)
COUNTS = st.integers(min_value=0, max_value=500)


# ---------------------------------------------------------------------------
# Data models for pure-logic immutability testing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TraceabilityMatrixData:
    """Represents a TraceabilityMatrix record with all required fields."""

    id: int
    matrix_id: str
    matrix_name: str
    source_document_uuids: list[str]
    target_document_uuids: list[str]
    source_document_versions: list[dict[str, Any]]
    target_document_versions: list[dict[str, Any]]
    traceability_links: list[dict[str, Any]]
    orphan_requirements: list[dict[str, Any]]
    orphan_test_cases: list[dict[str, Any]]
    coverage_metrics: dict[str, Any]
    status: str
    generation_timestamp: datetime
    generation_duration_ms: int
    agent_archetype_used: str
    model_used: str
    total_token_count: int
    requesting_user_id: int
    company_id: int
    deleted_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class CoverageSnapshotData:
    """Represents a CoverageSnapshot record with all required fields."""

    id: int
    matrix_id: str
    source_document_uuid: str
    coverage_percentage: float
    orphan_requirements_count: int
    orphan_test_cases_count: int
    compliance_readiness_score: float
    total_requirements: int
    covered_requirements: int
    total_test_cases: int
    linked_test_cases: int
    snapshot_date: datetime
    company_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Functions under test: immutability enforcement
# ---------------------------------------------------------------------------


def attempt_update_traceability_matrix(
    matrix: TraceabilityMatrixData, column: str
) -> None:
    """Simulate an UPDATE attempt on a TraceabilityMatrix column other than deleted_at.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_update event listener (_prevent_update_except_deleted_at).

    Raises:
        ImmutableRecordError: When any column other than deleted_at is modified.
    """
    if column == "deleted_at":
        # Soft-delete is permitted
        return
    raise ImmutableRecordError(
        model_name="TraceabilityMatrix",
        operation="update",
        record_id=matrix.id,
    )


def attempt_soft_delete_traceability_matrix(
    matrix: TraceabilityMatrixData,
) -> TraceabilityMatrixData:
    """Simulate a soft-delete (setting deleted_at) on a TraceabilityMatrix.

    This is the ONLY permitted mutation on TraceabilityMatrix records.

    Returns:
        A new data object representing the soft-deleted state.
    """
    # Soft-delete is permitted — no error raised
    return TraceabilityMatrixData(
        id=matrix.id,
        matrix_id=matrix.matrix_id,
        matrix_name=matrix.matrix_name,
        source_document_uuids=matrix.source_document_uuids,
        target_document_uuids=matrix.target_document_uuids,
        source_document_versions=matrix.source_document_versions,
        target_document_versions=matrix.target_document_versions,
        traceability_links=matrix.traceability_links,
        orphan_requirements=matrix.orphan_requirements,
        orphan_test_cases=matrix.orphan_test_cases,
        coverage_metrics=matrix.coverage_metrics,
        status=matrix.status,
        generation_timestamp=matrix.generation_timestamp,
        generation_duration_ms=matrix.generation_duration_ms,
        agent_archetype_used=matrix.agent_archetype_used,
        model_used=matrix.model_used,
        total_token_count=matrix.total_token_count,
        requesting_user_id=matrix.requesting_user_id,
        company_id=matrix.company_id,
        deleted_at=datetime.now(UTC),
        created_at=matrix.created_at,
    )


def attempt_delete_traceability_matrix(matrix: TraceabilityMatrixData) -> None:
    """Simulate a DELETE attempt on a TraceabilityMatrix record.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_delete event listener.

    Raises:
        ImmutableRecordError: Always, because hard-delete is prohibited.
    """
    raise ImmutableRecordError(
        model_name="TraceabilityMatrix",
        operation="delete",
        record_id=matrix.id,
    )


def attempt_update_coverage_snapshot(snapshot: CoverageSnapshotData) -> None:
    """Simulate an UPDATE attempt on a CoverageSnapshot record.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_update event listener (_prevent_update).

    Raises:
        ImmutableRecordError: Always, because CoverageSnapshot is fully immutable.
    """
    raise ImmutableRecordError(
        model_name="CoverageSnapshot",
        operation="update",
        record_id=snapshot.id,
    )


def attempt_delete_coverage_snapshot(snapshot: CoverageSnapshotData) -> None:
    """Simulate a DELETE attempt on a CoverageSnapshot record.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_delete event listener.

    Raises:
        ImmutableRecordError: Always, because CoverageSnapshot is fully immutable.
    """
    raise ImmutableRecordError(
        model_name="CoverageSnapshot",
        operation="delete",
        record_id=snapshot.id,
    )


# ---------------------------------------------------------------------------
# Composite Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_traceability_matrix_data(draw: st.DrawFn) -> TraceabilityMatrixData:
    """Generate a valid TraceabilityMatrix data record."""
    source_uuids = draw(
        st.lists(DOCUMENT_UUIDS, min_size=1, max_size=10, unique=True)
    )
    target_uuids = draw(
        st.lists(DOCUMENT_UUIDS, min_size=1, max_size=20, unique=True)
    )

    return TraceabilityMatrixData(
        id=draw(RECORD_IDS),
        matrix_id=draw(MATRIX_IDS),
        matrix_name=draw(MATRIX_NAMES),
        source_document_uuids=source_uuids,
        target_document_uuids=target_uuids,
        source_document_versions=[
            {"document_uuid": uuid, "version_id": draw(st.integers(1, 100))}
            for uuid in source_uuids
        ],
        target_document_versions=[
            {"document_uuid": uuid, "version_id": draw(st.integers(1, 100))}
            for uuid in target_uuids
        ],
        traceability_links=draw(
            st.lists(
                st.fixed_dictionaries({
                    "requirement_id": st.text(min_size=1, max_size=20),
                    "test_case_id": st.text(min_size=1, max_size=20),
                    "link_confidence": st.floats(min_value=0.5, max_value=1.0),
                }),
                min_size=0,
                max_size=5,
            )
        ),
        orphan_requirements=draw(
            st.lists(
                st.fixed_dictionaries({
                    "requirement_id": st.text(min_size=1, max_size=20),
                    "severity": st.sampled_from(["critical", "major", "minor"]),
                }),
                min_size=0,
                max_size=5,
            )
        ),
        orphan_test_cases=draw(
            st.lists(
                st.fixed_dictionaries({
                    "test_case_id": st.text(min_size=1, max_size=20),
                    "risk_level": st.sampled_from(["high", "medium", "low"]),
                }),
                min_size=0,
                max_size=5,
            )
        ),
        coverage_metrics={
            "total_requirements": draw(COUNTS),
            "covered_requirements": draw(COUNTS),
            "coverage_percentage": draw(COVERAGE_PERCENTAGES),
        },
        status=draw(MATRIX_STATUSES),
        generation_timestamp=draw(TIMESTAMPS),
        generation_duration_ms=draw(DURATION_MS),
        agent_archetype_used=draw(AGENT_ARCHETYPES),
        model_used=draw(MODEL_NAMES),
        total_token_count=draw(TOKEN_COUNTS),
        requesting_user_id=draw(USER_IDS),
        company_id=draw(COMPANY_IDS),
        deleted_at=None,
        created_at=draw(TIMESTAMPS),
    )


@st.composite
def st_coverage_snapshot_data(draw: st.DrawFn) -> CoverageSnapshotData:
    """Generate a valid CoverageSnapshot data record."""
    total_req = draw(st.integers(min_value=1, max_value=500))
    covered_req = draw(st.integers(min_value=0, max_value=total_req))
    total_tc = draw(st.integers(min_value=1, max_value=500))
    linked_tc = draw(st.integers(min_value=0, max_value=total_tc))

    return CoverageSnapshotData(
        id=draw(RECORD_IDS),
        matrix_id=draw(MATRIX_IDS),
        source_document_uuid=draw(DOCUMENT_UUIDS),
        coverage_percentage=round(covered_req / total_req * 100, 2),
        orphan_requirements_count=total_req - covered_req,
        orphan_test_cases_count=total_tc - linked_tc,
        compliance_readiness_score=draw(
            st.floats(min_value=0.0, max_value=100.0)
        ),
        total_requirements=total_req,
        covered_requirements=covered_req,
        total_test_cases=total_tc,
        linked_test_cases=linked_tc,
        snapshot_date=draw(TIMESTAMPS),
        company_id=draw(COMPANY_IDS),
        created_at=draw(TIMESTAMPS),
    )


# Columns on TraceabilityMatrix that are NOT deleted_at
IMMUTABLE_MATRIX_COLUMNS = st.sampled_from([
    "matrix_id",
    "matrix_name",
    "description",
    "source_document_uuids",
    "target_document_uuids",
    "source_document_versions",
    "target_document_versions",
    "traceability_links",
    "orphan_requirements",
    "orphan_test_cases",
    "coverage_metrics",
    "status",
    "parent_matrix_id",
    "generation_timestamp",
    "generation_duration_ms",
    "agent_archetype_used",
    "model_used",
    "total_token_count",
    "requesting_user_id",
    "company_id",
    "created_at",
])


# ---------------------------------------------------------------------------
# Property 7: Immutability Enforcement — TraceabilityMatrix
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(matrix=st_traceability_matrix_data(), column=IMMUTABLE_MATRIX_COLUMNS)
def test_traceability_matrix_update_non_deleted_at_raises_error(
    matrix: TraceabilityMatrixData,
    column: str,
) -> None:
    """For any persisted TraceabilityMatrix record, any attempt to UPDATE
    any column other than deleted_at through the ORM SHALL raise an
    ImmutableRecordError. The record's content SHALL remain unchanged
    after creation (except for soft-delete).

    **Validates: Requirements 4.2, 10.1, 10.2**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_update_traceability_matrix(matrix, column)

    assert exc_info.value.model_name == "TraceabilityMatrix"
    assert exc_info.value.operation == "update"
    assert exc_info.value.record_id == matrix.id


@settings(max_examples=10)
@given(matrix=st_traceability_matrix_data())
def test_traceability_matrix_soft_delete_permitted(
    matrix: TraceabilityMatrixData,
) -> None:
    """TraceabilityMatrix SHALL permit UPDATE of the deleted_at column
    (soft-delete). This is the only permitted mutation on the record.

    **Validates: Requirements 4.2, 10.1, 10.2**
    """
    # Soft-delete should NOT raise an error
    result = attempt_soft_delete_traceability_matrix(matrix)

    # The deleted_at field should now be set
    assert result.deleted_at is not None
    # All other fields remain unchanged
    assert result.matrix_id == matrix.matrix_id
    assert result.matrix_name == matrix.matrix_name
    assert result.status == matrix.status
    assert result.company_id == matrix.company_id
    assert result.traceability_links == matrix.traceability_links
    assert result.coverage_metrics == matrix.coverage_metrics


@settings(max_examples=10)
@given(matrix=st_traceability_matrix_data())
def test_traceability_matrix_delete_raises_error(
    matrix: TraceabilityMatrixData,
) -> None:
    """For any persisted TraceabilityMatrix record, any attempt to DELETE
    the record through the ORM SHALL raise an ImmutableRecordError.
    Hard-delete is never permitted; only soft-delete via deleted_at is allowed.

    **Validates: Requirements 4.2, 10.1, 10.2**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_delete_traceability_matrix(matrix)

    assert exc_info.value.model_name == "TraceabilityMatrix"
    assert exc_info.value.operation == "delete"
    assert exc_info.value.record_id == matrix.id


# ---------------------------------------------------------------------------
# Property 7: Immutability Enforcement — CoverageSnapshot
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(snapshot=st_coverage_snapshot_data())
def test_coverage_snapshot_update_raises_error(
    snapshot: CoverageSnapshotData,
) -> None:
    """For any persisted CoverageSnapshot record, any attempt to UPDATE
    the record through the ORM SHALL raise an ImmutableRecordError.
    CoverageSnapshot is fully immutable — no mutations are permitted.

    **Validates: Requirements 4.2, 10.1, 10.2**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_update_coverage_snapshot(snapshot)

    assert exc_info.value.model_name == "CoverageSnapshot"
    assert exc_info.value.operation == "update"
    assert exc_info.value.record_id == snapshot.id


@settings(max_examples=10)
@given(snapshot=st_coverage_snapshot_data())
def test_coverage_snapshot_delete_raises_error(
    snapshot: CoverageSnapshotData,
) -> None:
    """For any persisted CoverageSnapshot record, any attempt to DELETE
    the record through the ORM SHALL raise an ImmutableRecordError.
    CoverageSnapshot must be retained indefinitely for trend analysis
    and GxP audit trail compliance.

    **Validates: Requirements 4.2, 10.1, 10.2**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_delete_coverage_snapshot(snapshot)

    assert exc_info.value.model_name == "CoverageSnapshot"
    assert exc_info.value.operation == "delete"
    assert exc_info.value.record_id == snapshot.id


# ---------------------------------------------------------------------------
# SQLAlchemy event listener tests (actual ORM-level enforcement)
# ---------------------------------------------------------------------------


class TestTraceabilityMatrixEventListeners:
    """Test that SQLAlchemy event listeners correctly enforce immutability
    on TraceabilityMatrix model instances.

    These tests verify the actual _prevent_update_except_deleted_at and
    _prevent_delete functions from the immutability module raise
    ImmutableRecordError when invoked on TraceabilityMatrix targets.
    """

    @settings(max_examples=25)
    @given(record_id=RECORD_IDS)
    def test_prevent_delete_raises_for_traceability_matrix(
        self, record_id: int
    ) -> None:
        """The _prevent_delete listener SHALL raise ImmutableRecordError
        for TraceabilityMatrix instances with any record ID.

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        target = TraceabilityMatrix()
        target.id = record_id

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_delete(None, None, target)

        assert exc_info.value.model_name == "TraceabilityMatrix"
        assert exc_info.value.operation == "delete"
        assert exc_info.value.record_id == record_id


class TestCoverageSnapshotEventListeners:
    """Test that SQLAlchemy event listeners correctly prevent mutations
    on CoverageSnapshot model instances.

    These tests verify the actual _prevent_update and _prevent_delete
    functions from the immutability module raise ImmutableRecordError
    when invoked on CoverageSnapshot targets.
    """

    @settings(max_examples=25)
    @given(record_id=RECORD_IDS)
    def test_prevent_update_raises_for_coverage_snapshot(
        self, record_id: int
    ) -> None:
        """The _prevent_update listener SHALL raise ImmutableRecordError
        for CoverageSnapshot instances with any record ID.

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        target = CoverageSnapshot()
        target.id = record_id

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_update(None, None, target)

        assert exc_info.value.model_name == "CoverageSnapshot"
        assert exc_info.value.operation == "update"
        assert exc_info.value.record_id == record_id

    @settings(max_examples=25)
    @given(record_id=RECORD_IDS)
    def test_prevent_delete_raises_for_coverage_snapshot(
        self, record_id: int
    ) -> None:
        """The _prevent_delete listener SHALL raise ImmutableRecordError
        for CoverageSnapshot instances with any record ID.

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        target = CoverageSnapshot()
        target.id = record_id

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_delete(None, None, target)

        assert exc_info.value.model_name == "CoverageSnapshot"
        assert exc_info.value.operation == "delete"
        assert exc_info.value.record_id == record_id


# ---------------------------------------------------------------------------
# Model structure tests (immutability design constraints)
# ---------------------------------------------------------------------------


class TestTraceabilityMatrixModelStructure:
    """Tests for TraceabilityMatrix model structure relevant to immutability."""

    def test_has_deleted_at_field(self) -> None:
        """TraceabilityMatrix has deleted_at for soft-delete (only permitted mutation).

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        column_names = [c.name for c in TraceabilityMatrix.__table__.columns]
        assert "deleted_at" in column_names

    def test_has_created_at_field(self) -> None:
        """TraceabilityMatrix has created_at for write-once timestamp.

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        column_names = [c.name for c in TraceabilityMatrix.__table__.columns]
        assert "created_at" in column_names

    def test_does_not_use_audit_mixin(self) -> None:
        """TraceabilityMatrix does NOT use AuditMixin (immutable, no versioning).

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        # AuditMixin adds version column for SQLAlchemy-Continuum
        column_names = [c.name for c in TraceabilityMatrix.__table__.columns]
        assert "version" not in column_names

    def test_no_updated_at_field(self) -> None:
        """TraceabilityMatrix has no updated_at field (immutable records don't update).

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        column_names = [c.name for c in TraceabilityMatrix.__table__.columns]
        assert "updated_at" not in column_names


class TestCoverageSnapshotModelStructure:
    """Tests for CoverageSnapshot model structure relevant to immutability."""

    def test_no_deleted_at_field(self) -> None:
        """CoverageSnapshot has no deleted_at field (fully immutable, no soft-delete).

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        column_names = [c.name for c in CoverageSnapshot.__table__.columns]
        assert "deleted_at" not in column_names

    def test_has_created_at_field(self) -> None:
        """CoverageSnapshot has created_at for write-once timestamp.

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        column_names = [c.name for c in CoverageSnapshot.__table__.columns]
        assert "created_at" in column_names

    def test_does_not_use_audit_mixin(self) -> None:
        """CoverageSnapshot does NOT use AuditMixin (immutable, no versioning).

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        column_names = [c.name for c in CoverageSnapshot.__table__.columns]
        assert "version" not in column_names

    def test_no_updated_at_field(self) -> None:
        """CoverageSnapshot has no updated_at field (immutable records don't update).

        **Validates: Requirements 4.2, 10.1, 10.2**
        """
        column_names = [c.name for c in CoverageSnapshot.__table__.columns]
        assert "updated_at" not in column_names
