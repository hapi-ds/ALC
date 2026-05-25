"""Unit tests for impact analysis Pydantic schemas.

Tests validation rules for AffectedItemSchema, GapFindingSchema,
ChangeDeltaSchema, and request/response/pagination schemas.

References:
    - Requirements 3.5: Affected item structure and constraints
    - Requirements 4.3: Gap finding structure and constraints
    - Requirements 5.1: Impact report structure
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from alcoabase.schemas.impact_analysis import (
    AffectedItemSchema,
    BuildGraphRequest,
    ChangeDeltaSchema,
    DependencyEdgeResponse,
    GapAnalysisResultResponse,
    GapFindingSchema,
    ImpactReportResponse,
    NotificationResponse,
    PaginationParams,
)


# ---------------------------------------------------------------------------
# AffectedItemSchema Tests
# ---------------------------------------------------------------------------


class TestAffectedItemSchema:
    """Tests for AffectedItemSchema validation."""

    @pytest.fixture
    def valid_affected_item_data(self) -> dict:
        """Minimal valid data for AffectedItemSchema."""
        return {
            "affected_document_uuid": "DOC-001",
            "affected_document_title": "Test SOP",
            "dependency_type": "validates",
            "impact_severity": "critical",
            "affected_sections": ["Section 1", "Section 2"],
            "change_summary": "Requirement updated",
            "recommended_action": "update_required",
            "inference_prompt_summary": "Prompt text",
            "model_response_summary": "Response text",
            "token_count": 150,
        }

    def test_valid_full_data(self, valid_affected_item_data: dict) -> None:
        item = AffectedItemSchema(**valid_affected_item_data)
        assert item.affected_document_uuid == "DOC-001"
        assert item.impact_severity == "critical"
        assert item.recommended_action == "update_required"
        assert item.token_count == 150

    def test_change_summary_at_max_length(self, valid_affected_item_data: dict) -> None:
        valid_affected_item_data["change_summary"] = "x" * 500
        item = AffectedItemSchema(**valid_affected_item_data)
        assert len(item.change_summary) == 500

    def test_change_summary_exceeds_max_length_rejected(
        self, valid_affected_item_data: dict
    ) -> None:
        valid_affected_item_data["change_summary"] = "x" * 501
        with pytest.raises(ValidationError):
            AffectedItemSchema(**valid_affected_item_data)

    def test_invalid_impact_severity_rejected(
        self, valid_affected_item_data: dict
    ) -> None:
        valid_affected_item_data["impact_severity"] = "high"
        with pytest.raises(ValidationError):
            AffectedItemSchema(**valid_affected_item_data)

    def test_valid_impact_severity_values(
        self, valid_affected_item_data: dict
    ) -> None:
        for severity in ("critical", "major", "minor", "unknown"):
            valid_affected_item_data["impact_severity"] = severity
            item = AffectedItemSchema(**valid_affected_item_data)
            assert item.impact_severity == severity

    def test_invalid_recommended_action_rejected(
        self, valid_affected_item_data: dict
    ) -> None:
        valid_affected_item_data["recommended_action"] = "delete_document"
        with pytest.raises(ValidationError):
            AffectedItemSchema(**valid_affected_item_data)

    def test_valid_recommended_action_values(
        self, valid_affected_item_data: dict
    ) -> None:
        for action in (
            "update_required",
            "review_recommended",
            "retraining_required",
            "manual_review_required",
        ):
            valid_affected_item_data["recommended_action"] = action
            item = AffectedItemSchema(**valid_affected_item_data)
            assert item.recommended_action == action

    def test_optional_fields_default_to_none(
        self, valid_affected_item_data: dict
    ) -> None:
        valid_affected_item_data.pop("affected_document_uuid")
        item = AffectedItemSchema(**valid_affected_item_data)
        assert item.affected_document_uuid is None
        assert item.training_task_id is None

    def test_training_task_id_accepted(self, valid_affected_item_data: dict) -> None:
        valid_affected_item_data["training_task_id"] = 42
        item = AffectedItemSchema(**valid_affected_item_data)
        assert item.training_task_id == 42

    def test_inference_prompt_summary_at_max_length(
        self, valid_affected_item_data: dict
    ) -> None:
        valid_affected_item_data["inference_prompt_summary"] = "p" * 500
        item = AffectedItemSchema(**valid_affected_item_data)
        assert len(item.inference_prompt_summary) == 500

    def test_inference_prompt_summary_exceeds_max_rejected(
        self, valid_affected_item_data: dict
    ) -> None:
        valid_affected_item_data["inference_prompt_summary"] = "p" * 501
        with pytest.raises(ValidationError):
            AffectedItemSchema(**valid_affected_item_data)

    def test_model_response_summary_exceeds_max_rejected(
        self, valid_affected_item_data: dict
    ) -> None:
        valid_affected_item_data["model_response_summary"] = "r" * 501
        with pytest.raises(ValidationError):
            AffectedItemSchema(**valid_affected_item_data)

    def test_required_field_missing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AffectedItemSchema(
                affected_document_title="Test",
                # missing dependency_type, impact_severity, etc.
            )


# ---------------------------------------------------------------------------
# GapFindingSchema Tests
# ---------------------------------------------------------------------------


class TestGapFindingSchema:
    """Tests for GapFindingSchema validation."""

    @pytest.fixture
    def valid_gap_finding_data(self) -> dict:
        """Minimal valid data for GapFindingSchema."""
        return {
            "source_section": "Section 3.1",
            "source_content_excerpt": "The process shall...",
            "target_section": "Section 4.2",
            "target_content_excerpt": "Current procedure states...",
            "gap_type": "missing",
            "severity": "major",
            "remediation_suggestion": "Add coverage for new requirement",
            "inference_prompt_summary": "Prompt text",
            "model_response_summary": "Response text",
            "token_count": 200,
        }

    def test_valid_full_data(self, valid_gap_finding_data: dict) -> None:
        finding = GapFindingSchema(**valid_gap_finding_data)
        assert finding.source_section == "Section 3.1"
        assert finding.gap_type == "missing"
        assert finding.severity == "major"

    def test_source_content_excerpt_at_max_length(
        self, valid_gap_finding_data: dict
    ) -> None:
        valid_gap_finding_data["source_content_excerpt"] = "s" * 300
        finding = GapFindingSchema(**valid_gap_finding_data)
        assert len(finding.source_content_excerpt) == 300

    def test_source_content_excerpt_exceeds_max_rejected(
        self, valid_gap_finding_data: dict
    ) -> None:
        valid_gap_finding_data["source_content_excerpt"] = "s" * 301
        with pytest.raises(ValidationError):
            GapFindingSchema(**valid_gap_finding_data)

    def test_target_content_excerpt_exceeds_max_rejected(
        self, valid_gap_finding_data: dict
    ) -> None:
        valid_gap_finding_data["target_content_excerpt"] = "t" * 301
        with pytest.raises(ValidationError):
            GapFindingSchema(**valid_gap_finding_data)

    def test_invalid_gap_type_rejected(self, valid_gap_finding_data: dict) -> None:
        valid_gap_finding_data["gap_type"] = "wrong"
        with pytest.raises(ValidationError):
            GapFindingSchema(**valid_gap_finding_data)

    def test_valid_gap_type_values(self, valid_gap_finding_data: dict) -> None:
        for gap_type in ("missing", "contradicts", "incomplete", "outdated"):
            valid_gap_finding_data["gap_type"] = gap_type
            finding = GapFindingSchema(**valid_gap_finding_data)
            assert finding.gap_type == gap_type

    def test_invalid_severity_rejected(self, valid_gap_finding_data: dict) -> None:
        valid_gap_finding_data["severity"] = "unknown"
        with pytest.raises(ValidationError):
            GapFindingSchema(**valid_gap_finding_data)

    def test_valid_severity_values(self, valid_gap_finding_data: dict) -> None:
        for severity in ("critical", "major", "minor"):
            valid_gap_finding_data["severity"] = severity
            finding = GapFindingSchema(**valid_gap_finding_data)
            assert finding.severity == severity

    def test_target_section_not_found_accepted(
        self, valid_gap_finding_data: dict
    ) -> None:
        valid_gap_finding_data["target_section"] = "not_found"
        finding = GapFindingSchema(**valid_gap_finding_data)
        assert finding.target_section == "not_found"

    def test_inference_prompt_summary_exceeds_max_rejected(
        self, valid_gap_finding_data: dict
    ) -> None:
        valid_gap_finding_data["inference_prompt_summary"] = "p" * 501
        with pytest.raises(ValidationError):
            GapFindingSchema(**valid_gap_finding_data)

    def test_model_response_summary_exceeds_max_rejected(
        self, valid_gap_finding_data: dict
    ) -> None:
        valid_gap_finding_data["model_response_summary"] = "r" * 501
        with pytest.raises(ValidationError):
            GapFindingSchema(**valid_gap_finding_data)


# ---------------------------------------------------------------------------
# ChangeDeltaSchema Tests
# ---------------------------------------------------------------------------


class TestChangeDeltaSchema:
    """Tests for ChangeDeltaSchema validation."""

    def test_valid_full_data(self) -> None:
        delta = ChangeDeltaSchema(
            sections_added=[{"heading": "New Section", "content": "Added content"}],
            sections_modified=[{"heading": "Section 2", "content": "Updated text"}],
            sections_deleted=[{"heading": "Old Section", "content": "Removed"}],
            significance_levels={"high": 1, "medium": 1, "low": 0},
        )
        assert len(delta.sections_added) == 1
        assert len(delta.sections_modified) == 1
        assert len(delta.sections_deleted) == 1
        assert delta.significance_levels["high"] == 1

    def test_empty_lists_accepted(self) -> None:
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[],
            sections_deleted=[],
            significance_levels={"high": 0, "medium": 0, "low": 0},
        )
        assert delta.sections_added == []
        assert delta.sections_modified == []
        assert delta.sections_deleted == []

    def test_metadata_defaults_to_empty_dict(self) -> None:
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[],
            sections_deleted=[],
            significance_levels={},
        )
        assert delta.metadata == {}

    def test_metadata_accepts_arbitrary_data(self) -> None:
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[],
            sections_deleted=[],
            significance_levels={},
            metadata={"fallback_used": True, "user_attribution_unavailable": True},
        )
        assert delta.metadata["fallback_used"] is True

    def test_serialization_roundtrip(self) -> None:
        data = {
            "sections_added": [{"heading": "A", "summary": "new"}],
            "sections_modified": [{"heading": "B", "change": "updated"}],
            "sections_deleted": [{"heading": "C", "reason": "obsolete"}],
            "significance_levels": {"high": 2, "medium": 1, "low": 3},
            "metadata": {"note": "test"},
        }
        delta = ChangeDeltaSchema(**data)
        serialized = delta.model_dump()
        restored = ChangeDeltaSchema(**serialized)
        assert restored == delta

    def test_required_fields_missing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChangeDeltaSchema(
                sections_added=[],
                # missing sections_modified, sections_deleted, significance_levels
            )


# ---------------------------------------------------------------------------
# PaginationParams Tests
# ---------------------------------------------------------------------------


class TestPaginationParams:
    """Tests for PaginationParams validation."""

    def test_defaults(self) -> None:
        params = PaginationParams()
        assert params.limit == 20
        assert params.offset == 0

    def test_limit_at_max(self) -> None:
        params = PaginationParams(limit=200)
        assert params.limit == 200

    def test_limit_exceeds_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginationParams(limit=201)

    def test_limit_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginationParams(limit=0)

    def test_limit_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginationParams(limit=-1)

    def test_limit_one_accepted(self) -> None:
        params = PaginationParams(limit=1)
        assert params.limit == 1

    def test_offset_zero_accepted(self) -> None:
        params = PaginationParams(offset=0)
        assert params.offset == 0

    def test_offset_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PaginationParams(offset=-1)

    def test_offset_large_value_accepted(self) -> None:
        params = PaginationParams(offset=10000)
        assert params.offset == 10000


# ---------------------------------------------------------------------------
# BuildGraphRequest Tests
# ---------------------------------------------------------------------------


class TestBuildGraphRequest:
    """Tests for BuildGraphRequest validation."""

    def test_defaults_to_incremental(self) -> None:
        req = BuildGraphRequest()
        assert req.scope == "incremental"

    def test_full_scope_accepted(self) -> None:
        req = BuildGraphRequest(scope="full")
        assert req.scope == "full"

    def test_incremental_scope_accepted(self) -> None:
        req = BuildGraphRequest(scope="incremental")
        assert req.scope == "incremental"

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BuildGraphRequest(scope="partial")


# ---------------------------------------------------------------------------
# Response Schemas with from_attributes Tests
# ---------------------------------------------------------------------------


class TestDependencyEdgeResponse:
    """Tests for DependencyEdgeResponse with from_attributes."""

    def test_valid_data(self) -> None:
        now = datetime.now(tz=timezone.utc)
        edge = DependencyEdgeResponse(
            id=1,
            source_document_uuid="DOC-001",
            target_document_uuid="DOC-002",
            dependency_type="validates",
            confidence_score=0.95,
            detected_references=["REQ-001", "REQ-002"],
            last_verified_at=now,
            created_at=now,
        )
        assert edge.confidence_score == 0.95
        assert edge.detected_references == ["REQ-001", "REQ-002"]

    def test_confidence_score_below_zero_rejected(self) -> None:
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(ValidationError):
            DependencyEdgeResponse(
                id=1,
                source_document_uuid="DOC-001",
                target_document_uuid="DOC-002",
                dependency_type="validates",
                confidence_score=-0.1,
                detected_references=[],
                last_verified_at=now,
                created_at=now,
            )

    def test_confidence_score_above_one_rejected(self) -> None:
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(ValidationError):
            DependencyEdgeResponse(
                id=1,
                source_document_uuid="DOC-001",
                target_document_uuid="DOC-002",
                dependency_type="validates",
                confidence_score=1.1,
                detected_references=[],
                last_verified_at=now,
                created_at=now,
            )

    def test_from_attributes_config(self) -> None:
        assert DependencyEdgeResponse.model_config.get("from_attributes") is True


class TestImpactReportResponse:
    """Tests for ImpactReportResponse with from_attributes."""

    def test_from_attributes_config(self) -> None:
        assert ImpactReportResponse.model_config.get("from_attributes") is True

    def test_valid_full_report(self) -> None:
        now = datetime.now(tz=timezone.utc)
        report = ImpactReportResponse(
            id=1,
            report_id="550e8400-e29b-41d4-a716-446655440000",
            triggering_document_uuid="DOC-001",
            triggering_version_id=5,
            change_delta_summary=ChangeDeltaSchema(
                sections_added=[],
                sections_modified=[{"heading": "Scope", "content": "Updated"}],
                sections_deleted=[],
                significance_levels={"high": 1, "medium": 0, "low": 0},
            ),
            affected_items=[],
            gap_findings=[],
            status="completed",
            analysis_timestamp=now,
            analysis_duration_ms=5000,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=1500,
            company_id=1,
            created_at=now,
        )
        assert report.status == "completed"
        assert report.total_token_count == 1500


class TestGapAnalysisResultResponse:
    """Tests for GapAnalysisResultResponse with from_attributes."""

    def test_from_attributes_config(self) -> None:
        assert GapAnalysisResultResponse.model_config.get("from_attributes") is True


class TestNotificationResponse:
    """Tests for NotificationResponse with from_attributes."""

    def test_from_attributes_config(self) -> None:
        assert NotificationResponse.model_config.get("from_attributes") is True

    def test_valid_notification(self) -> None:
        now = datetime.now(tz=timezone.utc)
        notif = NotificationResponse(
            id=1,
            report_id="550e8400-e29b-41d4-a716-446655440000",
            affected_document_uuid="DOC-002",
            notification_type="change_impact",
            impact_severity="critical",
            change_summary="Requirement REQ-001 was updated",
            target_user_id=10,
            is_acknowledged=False,
            company_id=1,
            created_at=now,
        )
        assert notif.is_acknowledged is False
        assert notif.acknowledged_at is None
