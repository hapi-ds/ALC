"""Unit tests for traceability Pydantic schemas.

Tests validation rules for TraceabilityLinkSchema, OrphanRequirementSchema,
OrphanTestCaseSchema, CoverageMetricSchema, and GenerateMatrixRequest.

References:
    - Requirements 1.4: Request validation (source max 10, target max 20)
    - Requirements 1.5: Document count limits
    - Requirements 4.1: Matrix persistence structure
    - Requirements 5.1: Matrix API response structure
    - Requirements 10.8: Schema-level range enforcement
"""

import pytest
from pydantic import ValidationError

from alcoabase.schemas.traceability import (
    CoverageMetricSchema,
    GenerateMatrixRequest,
    OrphanRequirementSchema,
    OrphanTestCaseSchema,
    TraceabilityLinkSchema,
)


# ---------------------------------------------------------------------------
# TraceabilityLinkSchema Tests
# ---------------------------------------------------------------------------


class TestTraceabilityLinkSchema:
    """Tests for TraceabilityLinkSchema validation."""

    @pytest.fixture
    def valid_link_data(self) -> dict:
        """Minimal valid data for TraceabilityLinkSchema."""
        return {
            "requirement_id": "REQ-001",
            "requirement_text": "The system shall validate inputs.",
            "source_document_uuid": "DOC-SRC-001",
            "source_section": "Section 3.1",
            "target_document_uuid": "DOC-TGT-001",
            "target_section": "Section 4.2",
            "test_case_id": "TC-001",
            "test_case_text": "Verify input validation works.",
            "link_confidence": 0.85,
            "link_method": "exact_id_match",
            "link_methods": ["exact_id_match", "semantic_match"],
            "verification_status": "verified",
        }

    def test_valid_full_data(self, valid_link_data: dict) -> None:
        link = TraceabilityLinkSchema(**valid_link_data)
        assert link.requirement_id == "REQ-001"
        assert link.link_confidence == 0.85
        assert link.link_method == "exact_id_match"
        assert link.verification_status == "verified"
        assert link.link_methods == ["exact_id_match", "semantic_match"]

    def test_requirement_id_at_max_length(self, valid_link_data: dict) -> None:
        valid_link_data["requirement_id"] = "R" * 100
        link = TraceabilityLinkSchema(**valid_link_data)
        assert len(link.requirement_id) == 100

    def test_requirement_id_exceeds_max_length_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["requirement_id"] = "R" * 101
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_requirement_text_at_max_length(self, valid_link_data: dict) -> None:
        valid_link_data["requirement_text"] = "x" * 500
        link = TraceabilityLinkSchema(**valid_link_data)
        assert len(link.requirement_text) == 500

    def test_requirement_text_exceeds_max_length_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["requirement_text"] = "x" * 501
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_source_document_uuid_at_max_length(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["source_document_uuid"] = "D" * 12
        link = TraceabilityLinkSchema(**valid_link_data)
        assert len(link.source_document_uuid) == 12

    def test_source_document_uuid_exceeds_max_length_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["source_document_uuid"] = "D" * 13
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_target_document_uuid_exceeds_max_length_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["target_document_uuid"] = "T" * 13
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_test_case_id_at_max_length(self, valid_link_data: dict) -> None:
        valid_link_data["test_case_id"] = "T" * 100
        link = TraceabilityLinkSchema(**valid_link_data)
        assert len(link.test_case_id) == 100

    def test_test_case_id_exceeds_max_length_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["test_case_id"] = "T" * 101
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_test_case_text_at_max_length(self, valid_link_data: dict) -> None:
        valid_link_data["test_case_text"] = "t" * 500
        link = TraceabilityLinkSchema(**valid_link_data)
        assert len(link.test_case_text) == 500

    def test_test_case_text_exceeds_max_length_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["test_case_text"] = "t" * 501
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_link_confidence_at_zero(self, valid_link_data: dict) -> None:
        valid_link_data["link_confidence"] = 0.0
        link = TraceabilityLinkSchema(**valid_link_data)
        assert link.link_confidence == 0.0

    def test_link_confidence_at_one(self, valid_link_data: dict) -> None:
        valid_link_data["link_confidence"] = 1.0
        link = TraceabilityLinkSchema(**valid_link_data)
        assert link.link_confidence == 1.0

    def test_link_confidence_below_zero_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["link_confidence"] = -0.01
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_link_confidence_above_one_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["link_confidence"] = 1.01
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_valid_link_method_values(self, valid_link_data: dict) -> None:
        for method in ("exact_id_match", "cross_reference", "semantic_match"):
            valid_link_data["link_method"] = method
            link = TraceabilityLinkSchema(**valid_link_data)
            assert link.link_method == method

    def test_invalid_link_method_rejected(self, valid_link_data: dict) -> None:
        valid_link_data["link_method"] = "manual_match"
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_valid_verification_status_values(
        self, valid_link_data: dict
    ) -> None:
        for status in ("verified", "unverified", "failed"):
            valid_link_data["verification_status"] = status
            link = TraceabilityLinkSchema(**valid_link_data)
            assert link.verification_status == status

    def test_invalid_verification_status_rejected(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data["verification_status"] = "pending"
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(**valid_link_data)

    def test_link_methods_defaults_to_empty_list(
        self, valid_link_data: dict
    ) -> None:
        valid_link_data.pop("link_methods")
        link = TraceabilityLinkSchema(**valid_link_data)
        assert link.link_methods == []

    def test_required_field_missing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TraceabilityLinkSchema(
                requirement_id="REQ-001",
                # missing other required fields
            )

    def test_serialization_roundtrip(self, valid_link_data: dict) -> None:
        link = TraceabilityLinkSchema(**valid_link_data)
        serialized = link.model_dump()
        restored = TraceabilityLinkSchema(**serialized)
        assert restored == link


# ---------------------------------------------------------------------------
# OrphanRequirementSchema Tests
# ---------------------------------------------------------------------------


class TestOrphanRequirementSchema:
    """Tests for OrphanRequirementSchema validation."""

    @pytest.fixture
    def valid_orphan_req_data(self) -> dict:
        """Minimal valid data for OrphanRequirementSchema."""
        return {
            "requirement_id": "REQ-042",
            "requirement_text": "The system shall ensure sterility.",
            "source_document_uuid": "DOC-SRC-002",
            "source_section": "Section 5.3",
            "severity": "critical",
            "suggested_action": "create_test_case",
        }

    def test_valid_full_data(self, valid_orphan_req_data: dict) -> None:
        orphan = OrphanRequirementSchema(**valid_orphan_req_data)
        assert orphan.requirement_id == "REQ-042"
        assert orphan.severity == "critical"
        assert orphan.suggested_action == "create_test_case"

    def test_requirement_id_at_max_length(
        self, valid_orphan_req_data: dict
    ) -> None:
        valid_orphan_req_data["requirement_id"] = "R" * 100
        orphan = OrphanRequirementSchema(**valid_orphan_req_data)
        assert len(orphan.requirement_id) == 100

    def test_requirement_id_exceeds_max_length_rejected(
        self, valid_orphan_req_data: dict
    ) -> None:
        valid_orphan_req_data["requirement_id"] = "R" * 101
        with pytest.raises(ValidationError):
            OrphanRequirementSchema(**valid_orphan_req_data)

    def test_requirement_text_at_max_length(
        self, valid_orphan_req_data: dict
    ) -> None:
        valid_orphan_req_data["requirement_text"] = "x" * 500
        orphan = OrphanRequirementSchema(**valid_orphan_req_data)
        assert len(orphan.requirement_text) == 500

    def test_requirement_text_exceeds_max_length_rejected(
        self, valid_orphan_req_data: dict
    ) -> None:
        valid_orphan_req_data["requirement_text"] = "x" * 501
        with pytest.raises(ValidationError):
            OrphanRequirementSchema(**valid_orphan_req_data)

    def test_source_document_uuid_exceeds_max_length_rejected(
        self, valid_orphan_req_data: dict
    ) -> None:
        valid_orphan_req_data["source_document_uuid"] = "D" * 13
        with pytest.raises(ValidationError):
            OrphanRequirementSchema(**valid_orphan_req_data)

    def test_valid_severity_values(self, valid_orphan_req_data: dict) -> None:
        for severity in ("critical", "major", "minor"):
            valid_orphan_req_data["severity"] = severity
            orphan = OrphanRequirementSchema(**valid_orphan_req_data)
            assert orphan.severity == severity

    def test_invalid_severity_rejected(
        self, valid_orphan_req_data: dict
    ) -> None:
        valid_orphan_req_data["severity"] = "high"
        with pytest.raises(ValidationError):
            OrphanRequirementSchema(**valid_orphan_req_data)

    def test_valid_suggested_action_values(
        self, valid_orphan_req_data: dict
    ) -> None:
        for action in (
            "create_test_case",
            "review_requirement",
            "link_existing_test",
        ):
            valid_orphan_req_data["suggested_action"] = action
            orphan = OrphanRequirementSchema(**valid_orphan_req_data)
            assert orphan.suggested_action == action

    def test_invalid_suggested_action_rejected(
        self, valid_orphan_req_data: dict
    ) -> None:
        valid_orphan_req_data["suggested_action"] = "delete_requirement"
        with pytest.raises(ValidationError):
            OrphanRequirementSchema(**valid_orphan_req_data)

    def test_required_field_missing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OrphanRequirementSchema(
                requirement_id="REQ-001",
                # missing other required fields
            )

    def test_serialization_roundtrip(
        self, valid_orphan_req_data: dict
    ) -> None:
        orphan = OrphanRequirementSchema(**valid_orphan_req_data)
        serialized = orphan.model_dump()
        restored = OrphanRequirementSchema(**serialized)
        assert restored == orphan


# ---------------------------------------------------------------------------
# OrphanTestCaseSchema Tests
# ---------------------------------------------------------------------------


class TestOrphanTestCaseSchema:
    """Tests for OrphanTestCaseSchema validation."""

    @pytest.fixture
    def valid_orphan_tc_data(self) -> dict:
        """Minimal valid data for OrphanTestCaseSchema."""
        return {
            "test_case_id": "TC-099",
            "test_case_text": "Verify alarm triggers on threshold.",
            "target_document_uuid": "DOC-TGT-003",
            "target_section": "Section 7.1",
            "risk_level": "high",
            "suggested_action": "link_to_requirement",
        }

    def test_valid_full_data(self, valid_orphan_tc_data: dict) -> None:
        orphan = OrphanTestCaseSchema(**valid_orphan_tc_data)
        assert orphan.test_case_id == "TC-099"
        assert orphan.risk_level == "high"
        assert orphan.suggested_action == "link_to_requirement"

    def test_test_case_id_at_max_length(
        self, valid_orphan_tc_data: dict
    ) -> None:
        valid_orphan_tc_data["test_case_id"] = "T" * 100
        orphan = OrphanTestCaseSchema(**valid_orphan_tc_data)
        assert len(orphan.test_case_id) == 100

    def test_test_case_id_exceeds_max_length_rejected(
        self, valid_orphan_tc_data: dict
    ) -> None:
        valid_orphan_tc_data["test_case_id"] = "T" * 101
        with pytest.raises(ValidationError):
            OrphanTestCaseSchema(**valid_orphan_tc_data)

    def test_test_case_text_at_max_length(
        self, valid_orphan_tc_data: dict
    ) -> None:
        valid_orphan_tc_data["test_case_text"] = "t" * 500
        orphan = OrphanTestCaseSchema(**valid_orphan_tc_data)
        assert len(orphan.test_case_text) == 500

    def test_test_case_text_exceeds_max_length_rejected(
        self, valid_orphan_tc_data: dict
    ) -> None:
        valid_orphan_tc_data["test_case_text"] = "t" * 501
        with pytest.raises(ValidationError):
            OrphanTestCaseSchema(**valid_orphan_tc_data)

    def test_target_document_uuid_exceeds_max_length_rejected(
        self, valid_orphan_tc_data: dict
    ) -> None:
        valid_orphan_tc_data["target_document_uuid"] = "D" * 13
        with pytest.raises(ValidationError):
            OrphanTestCaseSchema(**valid_orphan_tc_data)

    def test_valid_risk_level_values(
        self, valid_orphan_tc_data: dict
    ) -> None:
        for level in ("high", "medium", "low"):
            valid_orphan_tc_data["risk_level"] = level
            orphan = OrphanTestCaseSchema(**valid_orphan_tc_data)
            assert orphan.risk_level == level

    def test_invalid_risk_level_rejected(
        self, valid_orphan_tc_data: dict
    ) -> None:
        valid_orphan_tc_data["risk_level"] = "critical"
        with pytest.raises(ValidationError):
            OrphanTestCaseSchema(**valid_orphan_tc_data)

    def test_valid_suggested_action_values(
        self, valid_orphan_tc_data: dict
    ) -> None:
        for action in (
            "link_to_requirement",
            "create_requirement",
            "remove_test_case",
        ):
            valid_orphan_tc_data["suggested_action"] = action
            orphan = OrphanTestCaseSchema(**valid_orphan_tc_data)
            assert orphan.suggested_action == action

    def test_invalid_suggested_action_rejected(
        self, valid_orphan_tc_data: dict
    ) -> None:
        valid_orphan_tc_data["suggested_action"] = "ignore"
        with pytest.raises(ValidationError):
            OrphanTestCaseSchema(**valid_orphan_tc_data)

    def test_required_field_missing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OrphanTestCaseSchema(
                test_case_id="TC-001",
                # missing other required fields
            )

    def test_serialization_roundtrip(
        self, valid_orphan_tc_data: dict
    ) -> None:
        orphan = OrphanTestCaseSchema(**valid_orphan_tc_data)
        serialized = orphan.model_dump()
        restored = OrphanTestCaseSchema(**serialized)
        assert restored == orphan


# ---------------------------------------------------------------------------
# CoverageMetricSchema Tests
# ---------------------------------------------------------------------------


class TestCoverageMetricSchema:
    """Tests for CoverageMetricSchema validation."""

    @pytest.fixture
    def valid_coverage_data(self) -> dict:
        """Minimal valid data for CoverageMetricSchema."""
        return {
            "total_requirements": 50,
            "covered_requirements": 45,
            "orphan_requirements_count": 5,
            "coverage_percentage": 90.0,
            "total_test_cases": 60,
            "linked_test_cases": 55,
            "orphan_test_cases_count": 5,
            "average_link_confidence": 0.82,
            "compliance_readiness_score": 75.5,
        }

    def test_valid_full_data(self, valid_coverage_data: dict) -> None:
        metric = CoverageMetricSchema(**valid_coverage_data)
        assert metric.total_requirements == 50
        assert metric.covered_requirements == 45
        assert metric.coverage_percentage == 90.0
        assert metric.average_link_confidence == 0.82
        assert metric.compliance_readiness_score == 75.5

    def test_all_zero_values_accepted(self) -> None:
        metric = CoverageMetricSchema(
            total_requirements=0,
            covered_requirements=0,
            orphan_requirements_count=0,
            coverage_percentage=0.0,
            total_test_cases=0,
            linked_test_cases=0,
            orphan_test_cases_count=0,
            average_link_confidence=0.0,
            compliance_readiness_score=0.0,
        )
        assert metric.total_requirements == 0
        assert metric.coverage_percentage == 0.0

    def test_coverage_percentage_at_max(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["coverage_percentage"] = 100.0
        metric = CoverageMetricSchema(**valid_coverage_data)
        assert metric.coverage_percentage == 100.0

    def test_coverage_percentage_above_max_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["coverage_percentage"] = 100.01
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_coverage_percentage_below_zero_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["coverage_percentage"] = -0.01
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_average_link_confidence_at_max(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["average_link_confidence"] = 1.0
        metric = CoverageMetricSchema(**valid_coverage_data)
        assert metric.average_link_confidence == 1.0

    def test_average_link_confidence_above_max_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["average_link_confidence"] = 1.01
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_average_link_confidence_below_zero_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["average_link_confidence"] = -0.01
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_compliance_readiness_score_at_max(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["compliance_readiness_score"] = 100.0
        metric = CoverageMetricSchema(**valid_coverage_data)
        assert metric.compliance_readiness_score == 100.0

    def test_compliance_readiness_score_above_max_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["compliance_readiness_score"] = 100.01
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_compliance_readiness_score_below_zero_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["compliance_readiness_score"] = -0.01
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_negative_integer_field_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["total_requirements"] = -1
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_negative_covered_requirements_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["covered_requirements"] = -1
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_negative_total_test_cases_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["total_test_cases"] = -1
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_negative_linked_test_cases_rejected(
        self, valid_coverage_data: dict
    ) -> None:
        valid_coverage_data["linked_test_cases"] = -1
        with pytest.raises(ValidationError):
            CoverageMetricSchema(**valid_coverage_data)

    def test_required_field_missing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CoverageMetricSchema(
                total_requirements=10,
                # missing other required fields
            )

    def test_serialization_roundtrip(self, valid_coverage_data: dict) -> None:
        metric = CoverageMetricSchema(**valid_coverage_data)
        serialized = metric.model_dump()
        restored = CoverageMetricSchema(**serialized)
        assert restored == metric


# ---------------------------------------------------------------------------
# GenerateMatrixRequest Tests
# ---------------------------------------------------------------------------


class TestGenerateMatrixRequest:
    """Tests for GenerateMatrixRequest validation."""

    @pytest.fixture
    def valid_request_data(self) -> dict:
        """Minimal valid data for GenerateMatrixRequest."""
        return {
            "source_document_ids": [1, 2, 3],
            "target_document_ids": [10, 11, 12, 13],
            "matrix_name": "URS to IQ Traceability",
            "description": "Maps URS requirements to IQ test cases.",
        }

    def test_valid_full_data(self, valid_request_data: dict) -> None:
        req = GenerateMatrixRequest(**valid_request_data)
        assert req.source_document_ids == [1, 2, 3]
        assert req.target_document_ids == [10, 11, 12, 13]
        assert req.matrix_name == "URS to IQ Traceability"
        assert req.description == "Maps URS requirements to IQ test cases."

    def test_description_is_optional(self, valid_request_data: dict) -> None:
        valid_request_data.pop("description")
        req = GenerateMatrixRequest(**valid_request_data)
        assert req.description is None

    def test_description_none_accepted(self, valid_request_data: dict) -> None:
        valid_request_data["description"] = None
        req = GenerateMatrixRequest(**valid_request_data)
        assert req.description is None

    def test_source_document_ids_min_one_required(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["source_document_ids"] = []
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(**valid_request_data)

    def test_source_document_ids_at_max_ten(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["source_document_ids"] = list(range(1, 11))
        req = GenerateMatrixRequest(**valid_request_data)
        assert len(req.source_document_ids) == 10

    def test_source_document_ids_exceeds_max_ten_rejected(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["source_document_ids"] = list(range(1, 12))
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(**valid_request_data)

    def test_target_document_ids_min_one_required(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["target_document_ids"] = []
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(**valid_request_data)

    def test_target_document_ids_at_max_twenty(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["target_document_ids"] = list(range(1, 21))
        req = GenerateMatrixRequest(**valid_request_data)
        assert len(req.target_document_ids) == 20

    def test_target_document_ids_exceeds_max_twenty_rejected(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["target_document_ids"] = list(range(1, 22))
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(**valid_request_data)

    def test_matrix_name_min_one_char(self, valid_request_data: dict) -> None:
        valid_request_data["matrix_name"] = "A"
        req = GenerateMatrixRequest(**valid_request_data)
        assert req.matrix_name == "A"

    def test_matrix_name_empty_rejected(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["matrix_name"] = ""
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(**valid_request_data)

    def test_matrix_name_at_max_200_chars(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["matrix_name"] = "N" * 200
        req = GenerateMatrixRequest(**valid_request_data)
        assert len(req.matrix_name) == 200

    def test_matrix_name_exceeds_max_200_rejected(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["matrix_name"] = "N" * 201
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(**valid_request_data)

    def test_description_at_max_1000_chars(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["description"] = "D" * 1000
        req = GenerateMatrixRequest(**valid_request_data)
        assert len(req.description) == 1000

    def test_description_exceeds_max_1000_rejected(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["description"] = "D" * 1001
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(**valid_request_data)

    def test_single_source_document_accepted(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["source_document_ids"] = [1]
        req = GenerateMatrixRequest(**valid_request_data)
        assert len(req.source_document_ids) == 1

    def test_single_target_document_accepted(
        self, valid_request_data: dict
    ) -> None:
        valid_request_data["target_document_ids"] = [1]
        req = GenerateMatrixRequest(**valid_request_data)
        assert len(req.target_document_ids) == 1

    def test_required_field_missing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GenerateMatrixRequest(
                source_document_ids=[1],
                # missing target_document_ids and matrix_name
            )

    def test_serialization_roundtrip(self, valid_request_data: dict) -> None:
        req = GenerateMatrixRequest(**valid_request_data)
        serialized = req.model_dump()
        restored = GenerateMatrixRequest(**serialized)
        assert restored == req
