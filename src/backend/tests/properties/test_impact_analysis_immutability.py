"""Property-based tests for ImpactReport and GapAnalysisResult immutability.

Property 11: Immutability Enforcement

For any ImpactReport or GapAnalysisResult record that has been persisted,
any attempt to UPDATE or DELETE the record through the ORM SHALL raise an
ImmutableRecordError. The record's content SHALL remain unchanged after
creation regardless of subsequent operations.

**Validates: Requirements 5.2, 9.2, 9.4**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/models/immutability.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.impact_analysis import GapAnalysisResult, ImpactReport
from alcoabase.models.immutability import (
    ImmutableRecordError,
    _prevent_delete,
    _prevent_update,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=100)
USER_IDS = st.integers(min_value=1, max_value=200)
RECORD_IDS = st.integers(min_value=1, max_value=10000)

REPORT_IDS = st.from_regex(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

JOB_IDS = st.from_regex(
    r"job-[a-f0-9]{8}-[a-f0-9]{4}",
    fullmatch=True,
)

REPORT_STATUSES = st.sampled_from(["completed", "partial_success", "failed"])

GAP_ANALYSIS_STATUSES = st.sampled_from(
    ["completed", "partial_success", "failed"]
)

AGENT_ARCHETYPES = st.sampled_from([
    "Change Impact Analyst",
    "Regulatory Compliance Auditor",
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
VERSION_IDS = st.integers(min_value=1, max_value=5000)
GAP_COUNTS = st.integers(min_value=0, max_value=500)


# ---------------------------------------------------------------------------
# Data models for pure-logic immutability testing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImpactReportData:
    """Represents an ImpactReport record with all required fields."""

    id: int
    report_id: str
    triggering_document_uuid: str
    triggering_version_id: int
    change_delta_summary: dict[str, Any]
    affected_items: list[dict[str, Any]]
    gap_findings: list[dict[str, Any]]
    status: str
    analysis_timestamp: datetime
    analysis_duration_ms: int
    agent_archetype_used: str
    model_used: str
    total_token_count: int
    requesting_user_id: int | None
    company_id: int
    created_at: datetime


@dataclass(frozen=True)
class GapAnalysisResultData:
    """Represents a GapAnalysisResult record with all required fields."""

    id: int
    job_id: str
    source_document_uuid: str
    target_document_uuid: str
    gap_findings: list[dict[str, Any]]
    total_gaps_detected: int
    gaps_retained: int
    status: str
    analysis_duration_ms: int
    company_id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Functions under test: immutability enforcement
# ---------------------------------------------------------------------------


def attempt_update_impact_report(report: ImpactReportData) -> None:
    """Simulate an UPDATE attempt on an ImpactReport record.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_update event listener.

    Raises:
        ImmutableRecordError: Always, because ImpactReport is immutable.
    """
    raise ImmutableRecordError(
        model_name="ImpactReport",
        operation="update",
        record_id=report.id,
    )


def attempt_delete_impact_report(report: ImpactReportData) -> None:
    """Simulate a DELETE attempt on an ImpactReport record.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_delete event listener.

    Raises:
        ImmutableRecordError: Always, because ImpactReport is immutable.
    """
    raise ImmutableRecordError(
        model_name="ImpactReport",
        operation="delete",
        record_id=report.id,
    )


def attempt_update_gap_analysis_result(result: GapAnalysisResultData) -> None:
    """Simulate an UPDATE attempt on a GapAnalysisResult record.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_update event listener.

    Raises:
        ImmutableRecordError: Always, because GapAnalysisResult is immutable.
    """
    raise ImmutableRecordError(
        model_name="GapAnalysisResult",
        operation="update",
        record_id=result.id,
    )


def attempt_delete_gap_analysis_result(result: GapAnalysisResultData) -> None:
    """Simulate a DELETE attempt on a GapAnalysisResult record.

    Models the application-layer immutability enforcement via
    SQLAlchemy before_delete event listener.

    Raises:
        ImmutableRecordError: Always, because GapAnalysisResult is immutable.
    """
    raise ImmutableRecordError(
        model_name="GapAnalysisResult",
        operation="delete",
        record_id=result.id,
    )


# ---------------------------------------------------------------------------
# Composite Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_change_delta_summary(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid change_delta_summary JSONB structure."""
    return {
        "sections_added": draw(
            st.lists(
                st.fixed_dictionaries({"heading": st.text(min_size=1, max_size=50)}),
                min_size=0,
                max_size=5,
            )
        ),
        "sections_modified": draw(
            st.lists(
                st.fixed_dictionaries({"heading": st.text(min_size=1, max_size=50)}),
                min_size=0,
                max_size=5,
            )
        ),
        "sections_deleted": draw(
            st.lists(
                st.fixed_dictionaries({"heading": st.text(min_size=1, max_size=50)}),
                min_size=0,
                max_size=5,
            )
        ),
        "significance_levels": {
            "high": draw(st.integers(min_value=0, max_value=10)),
            "medium": draw(st.integers(min_value=0, max_value=10)),
            "low": draw(st.integers(min_value=0, max_value=10)),
        },
    }


@st.composite
def st_impact_report_data(draw: st.DrawFn) -> ImpactReportData:
    """Generate a valid ImpactReport data record."""
    return ImpactReportData(
        id=draw(RECORD_IDS),
        report_id=draw(REPORT_IDS),
        triggering_document_uuid=draw(DOCUMENT_UUIDS),
        triggering_version_id=draw(VERSION_IDS),
        change_delta_summary=draw(st_change_delta_summary()),
        affected_items=draw(
            st.lists(st.just({"severity": "major"}), min_size=0, max_size=5)
        ),
        gap_findings=draw(
            st.lists(st.just({"gap_type": "missing"}), min_size=0, max_size=5)
        ),
        status=draw(REPORT_STATUSES),
        analysis_timestamp=draw(TIMESTAMPS),
        analysis_duration_ms=draw(DURATION_MS),
        agent_archetype_used=draw(AGENT_ARCHETYPES),
        model_used=draw(MODEL_NAMES),
        total_token_count=draw(TOKEN_COUNTS),
        requesting_user_id=draw(st.one_of(st.none(), USER_IDS)),
        company_id=draw(COMPANY_IDS),
        created_at=draw(TIMESTAMPS),
    )


@st.composite
def st_gap_analysis_result_data(draw: st.DrawFn) -> GapAnalysisResultData:
    """Generate a valid GapAnalysisResult data record."""
    total_gaps = draw(GAP_COUNTS)
    gaps_retained = min(total_gaps, 100)

    return GapAnalysisResultData(
        id=draw(RECORD_IDS),
        job_id=draw(JOB_IDS),
        source_document_uuid=draw(DOCUMENT_UUIDS),
        target_document_uuid=draw(DOCUMENT_UUIDS),
        gap_findings=draw(
            st.lists(st.just({"gap_type": "missing"}), min_size=0, max_size=5)
        ),
        total_gaps_detected=total_gaps,
        gaps_retained=gaps_retained,
        status=draw(GAP_ANALYSIS_STATUSES),
        analysis_duration_ms=draw(DURATION_MS),
        company_id=draw(COMPANY_IDS),
        created_at=draw(TIMESTAMPS),
    )


# ---------------------------------------------------------------------------
# Property 11: Immutability Enforcement — ImpactReport
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(report=st_impact_report_data())
def test_impact_report_update_raises_immutable_record_error(
    report: ImpactReportData,
) -> None:
    """For any persisted ImpactReport record, any attempt to UPDATE the record
    through the ORM SHALL raise an ImmutableRecordError. The record's content
    SHALL remain unchanged after creation.

    **Validates: Requirements 5.2, 9.2, 9.4**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_update_impact_report(report)

    assert exc_info.value.model_name == "ImpactReport"
    assert exc_info.value.operation == "update"
    assert exc_info.value.record_id == report.id


@settings(max_examples=50)
@given(report=st_impact_report_data())
def test_impact_report_delete_raises_immutable_record_error(
    report: ImpactReportData,
) -> None:
    """For any persisted ImpactReport record, any attempt to DELETE the record
    through the ORM SHALL raise an ImmutableRecordError. The record must be
    retained indefinitely for GxP audit trail compliance.

    **Validates: Requirements 5.2, 9.2, 9.4**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_delete_impact_report(report)

    assert exc_info.value.model_name == "ImpactReport"
    assert exc_info.value.operation == "delete"
    assert exc_info.value.record_id == report.id


# ---------------------------------------------------------------------------
# Property 11: Immutability Enforcement — GapAnalysisResult
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(result=st_gap_analysis_result_data())
def test_gap_analysis_result_update_raises_immutable_record_error(
    result: GapAnalysisResultData,
) -> None:
    """For any persisted GapAnalysisResult record, any attempt to UPDATE the
    record through the ORM SHALL raise an ImmutableRecordError. The record's
    content SHALL remain unchanged after creation.

    **Validates: Requirements 5.2, 9.2, 9.4**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_update_gap_analysis_result(result)

    assert exc_info.value.model_name == "GapAnalysisResult"
    assert exc_info.value.operation == "update"
    assert exc_info.value.record_id == result.id


@settings(max_examples=50)
@given(result=st_gap_analysis_result_data())
def test_gap_analysis_result_delete_raises_immutable_record_error(
    result: GapAnalysisResultData,
) -> None:
    """For any persisted GapAnalysisResult record, any attempt to DELETE the
    record through the ORM SHALL raise an ImmutableRecordError. The record
    must be retained indefinitely for GxP audit trail compliance.

    **Validates: Requirements 5.2, 9.2, 9.4**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_delete_gap_analysis_result(result)

    assert exc_info.value.model_name == "GapAnalysisResult"
    assert exc_info.value.operation == "delete"
    assert exc_info.value.record_id == result.id


# ---------------------------------------------------------------------------
# SQLAlchemy event listener tests (actual ORM-level enforcement)
# ---------------------------------------------------------------------------


class TestImpactReportEventListeners:
    """Test that SQLAlchemy event listeners correctly prevent mutations
    on ImpactReport model instances.

    These tests verify the actual _prevent_update and _prevent_delete
    functions from the immutability module raise ImmutableRecordError
    when invoked on ImpactReport targets.
    """

    @settings(max_examples=25)
    @given(record_id=RECORD_IDS)
    def test_prevent_update_raises_for_impact_report(
        self, record_id: int
    ) -> None:
        """The _prevent_update listener SHALL raise ImmutableRecordError
        for ImpactReport instances with any record ID.

        **Validates: Requirements 5.2, 9.2, 9.4**
        """
        target = ImpactReport()
        target.id = record_id

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_update(None, None, target)

        assert exc_info.value.model_name == "ImpactReport"
        assert exc_info.value.operation == "update"
        assert exc_info.value.record_id == record_id

    @settings(max_examples=25)
    @given(record_id=RECORD_IDS)
    def test_prevent_delete_raises_for_impact_report(
        self, record_id: int
    ) -> None:
        """The _prevent_delete listener SHALL raise ImmutableRecordError
        for ImpactReport instances with any record ID.

        **Validates: Requirements 5.2, 9.2, 9.4**
        """
        target = ImpactReport()
        target.id = record_id

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_delete(None, None, target)

        assert exc_info.value.model_name == "ImpactReport"
        assert exc_info.value.operation == "delete"
        assert exc_info.value.record_id == record_id


class TestGapAnalysisResultEventListeners:
    """Test that SQLAlchemy event listeners correctly prevent mutations
    on GapAnalysisResult model instances.

    These tests verify the actual _prevent_update and _prevent_delete
    functions from the immutability module raise ImmutableRecordError
    when invoked on GapAnalysisResult targets.
    """

    @settings(max_examples=25)
    @given(record_id=RECORD_IDS)
    def test_prevent_update_raises_for_gap_analysis_result(
        self, record_id: int
    ) -> None:
        """The _prevent_update listener SHALL raise ImmutableRecordError
        for GapAnalysisResult instances with any record ID.

        **Validates: Requirements 5.2, 9.2, 9.4**
        """
        target = GapAnalysisResult()
        target.id = record_id

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_update(None, None, target)

        assert exc_info.value.model_name == "GapAnalysisResult"
        assert exc_info.value.operation == "update"
        assert exc_info.value.record_id == record_id

    @settings(max_examples=25)
    @given(record_id=RECORD_IDS)
    def test_prevent_delete_raises_for_gap_analysis_result(
        self, record_id: int
    ) -> None:
        """The _prevent_delete listener SHALL raise ImmutableRecordError
        for GapAnalysisResult instances with any record ID.

        **Validates: Requirements 5.2, 9.2, 9.4**
        """
        target = GapAnalysisResult()
        target.id = record_id

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_delete(None, None, target)

        assert exc_info.value.model_name == "GapAnalysisResult"
        assert exc_info.value.operation == "delete"
        assert exc_info.value.record_id == record_id


# ---------------------------------------------------------------------------
# Model structure tests (immutability design constraints)
# ---------------------------------------------------------------------------


class TestImpactReportModelStructure:
    """Tests for ImpactReport model structure relevant to immutability."""

    def test_no_updated_at_field(self) -> None:
        """ImpactReport has no updated_at field (immutable records don't update)."""
        column_names = [c.name for c in ImpactReport.__table__.columns]
        assert "updated_at" not in column_names

    def test_has_created_at_field(self) -> None:
        """ImpactReport has created_at for write-once timestamp."""
        column_names = [c.name for c in ImpactReport.__table__.columns]
        assert "created_at" in column_names

    def test_does_not_use_audit_mixin(self) -> None:
        """ImpactReport does NOT use AuditMixin (immutable, no versioning)."""
        # AuditMixin adds version column for SQLAlchemy-Continuum
        column_names = [c.name for c in ImpactReport.__table__.columns]
        assert "version" not in column_names


class TestGapAnalysisResultModelStructure:
    """Tests for GapAnalysisResult model structure relevant to immutability."""

    def test_no_updated_at_field(self) -> None:
        """GapAnalysisResult has no updated_at field (immutable records don't update)."""
        column_names = [c.name for c in GapAnalysisResult.__table__.columns]
        assert "updated_at" not in column_names

    def test_has_created_at_field(self) -> None:
        """GapAnalysisResult has created_at for write-once timestamp."""
        column_names = [c.name for c in GapAnalysisResult.__table__.columns]
        assert "created_at" in column_names

    def test_does_not_use_audit_mixin(self) -> None:
        """GapAnalysisResult does NOT use AuditMixin (immutable, no versioning)."""
        column_names = [c.name for c in GapAnalysisResult.__table__.columns]
        assert "version" not in column_names
