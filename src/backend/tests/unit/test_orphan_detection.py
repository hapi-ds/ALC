"""Unit tests for OrphanDetectionService.

Tests orphan identification logic, severity classification, risk_level
classification, default assignment on agent timeout, and suggested_action
determination.

Requirements: 1.12, 2.1–2.7, 3.1–3.7
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.orphan_detection import (
    OrphanDetectionService,
    OrphanRequirement,
    OrphanTestCase,
    _CLASSIFICATION_TIMEOUT,
    _DEFAULT_RISK_LEVEL,
    _DEFAULT_SEVERITY,
    _DEFAULT_SUGGESTED_ACTION,
    _LINK_CONFIDENCE_THRESHOLD,
    _NEAR_MISS_CONFIDENCE_MAX,
    _NEAR_MISS_CONFIDENCE_MIN,
)
from alcoabase.services.traceability_matrix import (
    CandidateLink,
    ExtractedRequirement,
    ExtractedTestCase,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def mock_agent_registry():
    """Create a mock AgentRegistryService."""
    registry = MagicMock()
    registry.list_archetypes.return_value = [
        {
            "archetype": "Traceability Analyst",
            "system_prompt": "You are a Traceability Analyst.",
            "contextual_tuning": {
                "temperature": 0.15,
                "max_tokens": 4096,
            },
        }
    ]
    return registry


@pytest.fixture
def service(mock_inference_client, mock_agent_registry):
    """Create an OrphanDetectionService with mocked dependencies."""
    return OrphanDetectionService(
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
    )


@pytest.fixture
def service_no_inference():
    """Create an OrphanDetectionService without InferenceClient."""
    return OrphanDetectionService(
        inference_client=None,
        agent_registry=None,
    )


@pytest.fixture
def sample_requirements():
    """Sample extracted requirements."""
    return [
        ExtractedRequirement(
            requirement_id="REQ-001",
            requirement_text="The system shall ensure safety of the operator.",
            source_document_uuid="doc-src-001",
            source_section="1.1 Safety Requirements",
        ),
        ExtractedRequirement(
            requirement_id="REQ-002",
            requirement_text="The system shall perform data validation.",
            source_document_uuid="doc-src-001",
            source_section="2.1 Functional Requirements",
        ),
        ExtractedRequirement(
            requirement_id="REQ-003",
            requirement_text="The system should display a welcome message.",
            source_document_uuid="doc-src-002",
            source_section="3.1 UI Requirements",
        ),
    ]


@pytest.fixture
def sample_test_cases():
    """Sample extracted test cases."""
    return [
        ExtractedTestCase(
            test_case_id="TC-001",
            test_case_text="Verify alarm verification for safety interlock.",
            target_document_uuid="doc-tgt-001",
            target_section="1.1 Safety Tests",
        ),
        ExtractedTestCase(
            test_case_id="TC-002",
            test_case_text="Verify that the system verifies calculation results.",
            target_document_uuid="doc-tgt-001",
            target_section="2.1 Functional Tests",
        ),
        ExtractedTestCase(
            test_case_id="TC-003",
            test_case_text="Checks display format of the welcome screen.",
            target_document_uuid="doc-tgt-002",
            target_section="3.1 UI Tests",
        ),
    ]


@pytest.fixture
def links_covering_req001_and_tc001():
    """Links that cover REQ-001 and TC-001 (confidence >= 0.5)."""
    return [
        CandidateLink(
            requirement_id="REQ-001",
            requirement_text="The system shall ensure safety.",
            source_document_uuid="doc-src-001",
            source_section="1.1",
            test_case_id="TC-001",
            test_case_text="Verify alarm verification.",
            target_document_uuid="doc-tgt-001",
            target_section="1.1",
            link_confidence=0.85,
            link_method="semantic_match",
        ),
    ]


@pytest.fixture
def links_with_near_miss():
    """Links including a near-miss (confidence 0.3-0.49) for TC-002."""
    return [
        CandidateLink(
            requirement_id="REQ-001",
            requirement_text="Safety requirement.",
            source_document_uuid="doc-src-001",
            source_section="1.1",
            test_case_id="TC-001",
            test_case_text="Safety test.",
            target_document_uuid="doc-tgt-001",
            target_section="1.1",
            link_confidence=0.85,
            link_method="semantic_match",
        ),
        CandidateLink(
            requirement_id="REQ-002",
            requirement_text="Data validation.",
            source_document_uuid="doc-src-001",
            source_section="2.1",
            test_case_id="TC-002",
            test_case_text="Verifies calculation.",
            target_document_uuid="doc-tgt-001",
            target_section="2.1",
            link_confidence=0.4,
            link_method="semantic_match",
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Orphan Requirement Identification (Requirements 1.12, 2.1)
# ─────────────────────────────────────────────────────────────────────────────


class TestIdentifyOrphanRequirements:
    """Tests for identify_orphan_requirements."""

    @pytest.mark.asyncio
    async def test_requirement_with_no_links_is_orphan(
        self, service_no_inference, sample_requirements
    ):
        """A requirement with zero links is classified as orphan."""
        orphans = await service_no_inference.identify_orphan_requirements(
            sample_requirements, links=[]
        )
        assert len(orphans) == 3
        orphan_ids = {o.requirement_id for o in orphans}
        assert orphan_ids == {"REQ-001", "REQ-002", "REQ-003"}

    @pytest.mark.asyncio
    async def test_requirement_with_link_below_threshold_is_orphan(
        self, service_no_inference, sample_requirements
    ):
        """A requirement with links below 0.5 confidence is still orphan."""
        low_confidence_links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Safety.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.49,
                link_method="semantic_match",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            sample_requirements, links=low_confidence_links
        )
        # REQ-001 still orphan because 0.49 < 0.5
        orphan_ids = {o.requirement_id for o in orphans}
        assert "REQ-001" in orphan_ids

    @pytest.mark.asyncio
    async def test_requirement_with_link_at_threshold_is_covered(
        self, service_no_inference, sample_requirements
    ):
        """A requirement with link at exactly 0.5 confidence is covered."""
        threshold_links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Safety.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.5,
                link_method="semantic_match",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            sample_requirements, links=threshold_links
        )
        orphan_ids = {o.requirement_id for o in orphans}
        assert "REQ-001" not in orphan_ids
        assert len(orphans) == 2

    @pytest.mark.asyncio
    async def test_empty_requirements_returns_empty(self, service_no_inference):
        """Empty requirements list returns no orphans."""
        orphans = await service_no_inference.identify_orphan_requirements(
            requirements=[], links=[]
        )
        assert orphans == []

    @pytest.mark.asyncio
    async def test_all_covered_returns_empty(
        self, service_no_inference, sample_requirements
    ):
        """When all requirements are covered, no orphans are returned."""
        full_coverage_links = [
            CandidateLink(
                requirement_id=req.requirement_id,
                requirement_text=req.requirement_text,
                source_document_uuid=req.source_document_uuid,
                source_section=req.source_section,
                test_case_id=f"TC-{i:03d}",
                test_case_text="Test.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.8,
                link_method="exact_id_match",
            )
            for i, req in enumerate(sample_requirements, start=1)
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            sample_requirements, links=full_coverage_links
        )
        assert orphans == []

    @pytest.mark.asyncio
    async def test_orphan_contains_correct_metadata(
        self, service_no_inference
    ):
        """Orphan requirements contain correct source document metadata."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-100",
                requirement_text="The system shall comply with FDA regulations.",
                source_document_uuid="doc-uuid-abc",
                source_section="Section 4.2 Regulatory",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        assert len(orphans) == 1
        orphan = orphans[0]
        assert orphan.requirement_id == "REQ-100"
        assert orphan.source_document_uuid == "doc-uuid-abc"
        assert orphan.source_section == "Section 4.2 Regulatory"
        assert orphan.requirement_text == "The system shall comply with FDA regulations."


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Orphan Test Case Identification (Requirements 3.1, 3.2)
# ─────────────────────────────────────────────────────────────────────────────


class TestIdentifyOrphanTestCases:
    """Tests for identify_orphan_test_cases."""

    @pytest.mark.asyncio
    async def test_test_case_with_no_links_is_orphan(
        self, service_no_inference, sample_test_cases
    ):
        """A test case with zero links is classified as orphan."""
        orphans = await service_no_inference.identify_orphan_test_cases(
            sample_test_cases, links=[]
        )
        assert len(orphans) == 3
        orphan_ids = {o.test_case_id for o in orphans}
        assert orphan_ids == {"TC-001", "TC-002", "TC-003"}

    @pytest.mark.asyncio
    async def test_test_case_with_link_below_threshold_is_orphan(
        self, service_no_inference, sample_test_cases
    ):
        """A test case with links below 0.5 confidence is still orphan."""
        low_links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.49,
                link_method="semantic_match",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            sample_test_cases, links=low_links
        )
        orphan_ids = {o.test_case_id for o in orphans}
        assert "TC-001" in orphan_ids

    @pytest.mark.asyncio
    async def test_test_case_with_link_at_threshold_is_covered(
        self, service_no_inference, sample_test_cases
    ):
        """A test case with link at exactly 0.5 confidence is covered."""
        threshold_links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.5,
                link_method="semantic_match",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            sample_test_cases, links=threshold_links
        )
        orphan_ids = {o.test_case_id for o in orphans}
        assert "TC-001" not in orphan_ids
        assert len(orphans) == 2

    @pytest.mark.asyncio
    async def test_empty_test_cases_returns_empty(self, service_no_inference):
        """Empty test cases list returns no orphans."""
        orphans = await service_no_inference.identify_orphan_test_cases(
            test_cases=[], links=[]
        )
        assert orphans == []

    @pytest.mark.asyncio
    async def test_all_covered_returns_empty(
        self, service_no_inference, sample_test_cases
    ):
        """When all test cases are covered, no orphans are returned."""
        full_links = [
            CandidateLink(
                requirement_id=f"REQ-{i:03d}",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id=tc.test_case_id,
                test_case_text=tc.test_case_text,
                target_document_uuid=tc.target_document_uuid,
                target_section=tc.target_section,
                link_confidence=0.9,
                link_method="exact_id_match",
            )
            for i, tc in enumerate(sample_test_cases, start=1)
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            sample_test_cases, links=full_links
        )
        assert orphans == []

    @pytest.mark.asyncio
    async def test_near_miss_determines_suggested_action(
        self, service_no_inference, sample_test_cases, links_with_near_miss
    ):
        """Near-miss links (0.3-0.49) result in 'link_to_requirement' action."""
        orphans = await service_no_inference.identify_orphan_test_cases(
            sample_test_cases, links=links_with_near_miss
        )
        # TC-002 has a near-miss link at 0.4
        tc002 = next(o for o in orphans if o.test_case_id == "TC-002")
        assert tc002.suggested_action == "link_to_requirement"

        # TC-003 has no links at all → create_requirement
        tc003 = next(o for o in orphans if o.test_case_id == "TC-003")
        assert tc003.suggested_action == "create_requirement"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Severity Classification (Requirement 2.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestSeverityClassification:
    """Tests for severity classification by keyword analysis."""

    @pytest.mark.asyncio
    async def test_critical_safety_keywords(self, service_no_inference):
        """Requirements with safety-critical keywords get 'critical' severity."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="The system shall ensure hazard mitigation.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
            ExtractedRequirement(
                requirement_id="REQ-002",
                requirement_text="Sterility must be maintained at all times.",
                source_document_uuid="doc-001",
                source_section="1.2",
            ),
            ExtractedRequirement(
                requirement_id="REQ-003",
                requirement_text="The alarm system shall activate on breach.",
                source_document_uuid="doc-001",
                source_section="1.3",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        for orphan in orphans:
            assert orphan.severity == "critical"

    @pytest.mark.asyncio
    async def test_critical_regulatory_keywords(self, service_no_inference):
        """Requirements with regulatory keywords get 'critical' severity."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-010",
                requirement_text="The system shall comply with FDA 21 CFR Part 11.",
                source_document_uuid="doc-001",
                source_section="2.1",
            ),
            ExtractedRequirement(
                requirement_id="REQ-011",
                requirement_text="Must meet ISO 13485 requirements.",
                source_document_uuid="doc-001",
                source_section="2.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        for orphan in orphans:
            assert orphan.severity == "critical"

    @pytest.mark.asyncio
    async def test_major_functional_keywords(self, service_no_inference):
        """Requirements with functional keywords get 'major' severity."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-020",
                requirement_text="The system shall perform batch calculations.",
                source_document_uuid="doc-001",
                source_section="3.1",
            ),
            ExtractedRequirement(
                requirement_id="REQ-021",
                requirement_text="The system shall display user dashboard.",
                source_document_uuid="doc-001",
                source_section="3.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        for orphan in orphans:
            assert orphan.severity == "major"

    @pytest.mark.asyncio
    async def test_minor_informational_keywords(self, service_no_inference):
        """Requirements with only informational keywords get 'minor' severity."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-030",
                requirement_text="The system should provide tooltips.",
                source_document_uuid="doc-001",
                source_section="4.1",
            ),
            ExtractedRequirement(
                requirement_id="REQ-031",
                requirement_text="This feature is optional for users.",
                source_document_uuid="doc-001",
                source_section="4.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        for orphan in orphans:
            assert orphan.severity == "minor"

    @pytest.mark.asyncio
    async def test_precedence_critical_over_major(self, service_no_inference):
        """Critical keywords take precedence over major keywords."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-040",
                requirement_text="The system shall perform safety interlock checks.",
                source_document_uuid="doc-001",
                source_section="5.1",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        # Contains both "shall perform" (major) and "safety" (critical)
        assert orphans[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_precedence_major_over_minor(self, service_no_inference):
        """Major keywords take precedence over minor keywords."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-041",
                requirement_text="The system shall display optional settings.",
                source_document_uuid="doc-001",
                source_section="5.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        # Contains both "shall display" (major) and "optional" (minor)
        assert orphans[0].severity == "major"

    @pytest.mark.asyncio
    async def test_no_keywords_defaults_to_major(self, service_no_inference):
        """Requirements with no matching keywords default to 'major'."""
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-050",
                requirement_text="The system processes data in batches.",
                source_document_uuid="doc-001",
                source_section="6.1",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_requirements(
            reqs, links=[]
        )
        assert orphans[0].severity == _DEFAULT_SEVERITY


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Risk Level Classification (Requirement 3.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestRiskLevelClassification:
    """Tests for risk_level classification by keyword analysis."""

    @pytest.mark.asyncio
    async def test_high_risk_safety_keywords(self, service_no_inference):
        """Test cases with safety-critical indicators get 'high' risk_level."""
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-100",
                test_case_text="Validates safety function of the interlock.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
            ExtractedTestCase(
                test_case_id="TC-101",
                test_case_text="Alarm verification for critical systems.",
                target_document_uuid="doc-tgt-001",
                target_section="1.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            tcs, links=[]
        )
        for orphan in orphans:
            assert orphan.risk_level == "high"

    @pytest.mark.asyncio
    async def test_medium_risk_functional_keywords(self, service_no_inference):
        """Test cases with functional indicators get 'medium' risk_level."""
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-110",
                test_case_text="Verifies calculation of batch totals.",
                target_document_uuid="doc-tgt-001",
                target_section="2.1",
            ),
            ExtractedTestCase(
                test_case_id="TC-111",
                test_case_text="Confirms workflow transitions correctly.",
                target_document_uuid="doc-tgt-001",
                target_section="2.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            tcs, links=[]
        )
        for orphan in orphans:
            assert orphan.risk_level == "medium"

    @pytest.mark.asyncio
    async def test_low_risk_informational_keywords(self, service_no_inference):
        """Test cases with informational indicators get 'low' risk_level."""
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-120",
                test_case_text="Checks display format of the report header.",
                target_document_uuid="doc-tgt-001",
                target_section="3.1",
            ),
            ExtractedTestCase(
                test_case_id="TC-121",
                test_case_text="Verifies label text on the form.",
                target_document_uuid="doc-tgt-001",
                target_section="3.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            tcs, links=[]
        )
        for orphan in orphans:
            assert orphan.risk_level == "low"

    @pytest.mark.asyncio
    async def test_precedence_high_over_medium(self, service_no_inference):
        """High risk keywords take precedence over medium."""
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-130",
                test_case_text="Validates safety function and verifies calculation.",
                target_document_uuid="doc-tgt-001",
                target_section="4.1",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            tcs, links=[]
        )
        assert orphans[0].risk_level == "high"

    @pytest.mark.asyncio
    async def test_precedence_medium_over_low(self, service_no_inference):
        """Medium risk keywords take precedence over low."""
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-131",
                test_case_text="Verifies calculation and checks display format.",
                target_document_uuid="doc-tgt-001",
                target_section="4.2",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            tcs, links=[]
        )
        assert orphans[0].risk_level == "medium"

    @pytest.mark.asyncio
    async def test_no_keywords_defaults_to_medium(self, service_no_inference):
        """Test cases with no matching keywords default to 'medium'."""
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-140",
                test_case_text="Run the standard test procedure.",
                target_document_uuid="doc-tgt-001",
                target_section="5.1",
            ),
        ]
        orphans = await service_no_inference.identify_orphan_test_cases(
            tcs, links=[]
        )
        assert orphans[0].risk_level == _DEFAULT_RISK_LEVEL


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Default Assignment on Agent Timeout (Requirements 2.5, 3.5)
# ─────────────────────────────────────────────────────────────────────────────


class TestAgentTimeoutDefaults:
    """Tests for default assignment when agent classification times out."""

    @pytest.mark.asyncio
    async def test_severity_defaults_to_major_on_timeout(
        self, mock_inference_client, mock_agent_registry
    ):
        """On agent timeout, orphan requirements get default severity 'major'."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-060",
                requirement_text="Generic requirement with no keywords.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_requirements(reqs, links=[])
        # Falls back to local keyword classification (no keywords → major)
        assert orphans[0].severity == "major"

    @pytest.mark.asyncio
    async def test_risk_level_defaults_to_medium_on_timeout(
        self, mock_inference_client, mock_agent_registry
    ):
        """On agent timeout, orphan test cases get default risk_level 'medium'."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-060",
                test_case_text="Generic test with no keywords.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_test_cases(tcs, links=[])
        assert orphans[0].risk_level == "medium"
        assert orphans[0].suggested_action == "create_requirement"

    @pytest.mark.asyncio
    async def test_suggested_action_defaults_on_timeout_with_near_miss(
        self, mock_inference_client, mock_agent_registry
    ):
        """On timeout with near-miss, suggested_action is 'link_to_requirement'."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-070",
                test_case_text="Some test case.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        near_miss_links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-070",
                test_case_text="Some test case.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.35,
                link_method="semantic_match",
            ),
        ]
        orphans = await service.identify_orphan_test_cases(
            tcs, links=near_miss_links
        )
        assert orphans[0].suggested_action == "link_to_requirement"

    @pytest.mark.asyncio
    async def test_severity_falls_back_on_generic_exception(
        self, mock_inference_client, mock_agent_registry
    ):
        """On generic exception from agent, falls back to local classification."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=ConnectionError("Service unavailable")
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-070",
                requirement_text="The system shall ensure safety.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_requirements(reqs, links=[])
        # "safety" keyword → critical via local fallback
        assert orphans[0].severity == "critical"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: AI-Based Classification with Mocked InferenceClient
# ─────────────────────────────────────────────────────────────────────────────


class TestAIBasedClassification:
    """Tests for AI-based classification via mocked InferenceClient."""

    @pytest.mark.asyncio
    async def test_successful_severity_classification(
        self, mock_inference_client, mock_agent_registry
    ):
        """Successful AI response is used for severity classification."""
        ai_response = json.dumps({
            "classifications": [
                {
                    "requirement_id": "REQ-080",
                    "severity": "critical",
                    "suggested_action": "create_test_case",
                },
            ]
        })
        mock_inference_client.chat_completion = AsyncMock(
            return_value=ai_response
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-080",
                requirement_text="Some requirement.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_requirements(reqs, links=[])
        assert orphans[0].severity == "critical"
        assert orphans[0].suggested_action == "create_test_case"

    @pytest.mark.asyncio
    async def test_successful_risk_level_classification(
        self, mock_inference_client, mock_agent_registry
    ):
        """Successful AI response is used for risk_level classification."""
        ai_response = json.dumps({
            "classifications": [
                {
                    "test_case_id": "TC-080",
                    "risk_level": "high",
                    "suggested_action": "link_to_requirement",
                },
            ]
        })
        mock_inference_client.chat_completion = AsyncMock(
            return_value=ai_response
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-080",
                test_case_text="Some test case.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_test_cases(tcs, links=[])
        assert orphans[0].risk_level == "high"
        assert orphans[0].suggested_action == "link_to_requirement"

    @pytest.mark.asyncio
    async def test_invalid_json_response_falls_back(
        self, mock_inference_client, mock_agent_registry
    ):
        """Invalid JSON from AI falls back to local keyword classification."""
        mock_inference_client.chat_completion = AsyncMock(
            return_value="not valid json at all"
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-090",
                requirement_text="The system shall ensure sterility.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_requirements(reqs, links=[])
        # Falls back to local: "sterility" → critical
        assert orphans[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_ai_response_with_invalid_severity_uses_local(
        self, mock_inference_client, mock_agent_registry
    ):
        """AI response with invalid severity value falls back to local."""
        ai_response = json.dumps({
            "classifications": [
                {
                    "requirement_id": "REQ-091",
                    "severity": "unknown_level",
                    "suggested_action": "create_test_case",
                },
            ]
        })
        mock_inference_client.chat_completion = AsyncMock(
            return_value=ai_response
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-091",
                requirement_text="The system shall perform data export.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_requirements(reqs, links=[])
        # Invalid severity from AI → local fallback: "shall perform" → major
        assert orphans[0].severity == "major"

    @pytest.mark.asyncio
    async def test_ai_response_with_invalid_suggested_action_defaults(
        self, mock_inference_client, mock_agent_registry
    ):
        """AI response with invalid suggested_action gets default action."""
        ai_response = json.dumps({
            "classifications": [
                {
                    "test_case_id": "TC-091",
                    "risk_level": "low",
                    "suggested_action": "invalid_action",
                },
            ]
        })
        mock_inference_client.chat_completion = AsyncMock(
            return_value=ai_response
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-091",
                test_case_text="Some test.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_test_cases(tcs, links=[])
        assert orphans[0].risk_level == "low"
        # Invalid action → falls back to _determine_suggested_action
        # No near-miss → "create_requirement"
        assert orphans[0].suggested_action == "create_requirement"

    @pytest.mark.asyncio
    async def test_ai_response_wrapped_in_markdown_code_block(
        self, mock_inference_client, mock_agent_registry
    ):
        """AI response wrapped in ```json code block is parsed correctly."""
        ai_response = '```json\n{"classifications": [{"requirement_id": "REQ-092", "severity": "minor", "suggested_action": "review_requirement"}]}\n```'
        mock_inference_client.chat_completion = AsyncMock(
            return_value=ai_response
        )
        service = OrphanDetectionService(
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-092",
                requirement_text="Nice-to-have feature.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        orphans = await service.identify_orphan_requirements(reqs, links=[])
        assert orphans[0].severity == "minor"
        assert orphans[0].suggested_action == "review_requirement"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Suggested Action Determination (Requirement 3.2)
# ─────────────────────────────────────────────────────────────────────────────


class TestSuggestedActionDetermination:
    """Tests for suggested_action logic based on near-miss confidence."""

    def test_near_miss_at_lower_bound(self):
        """Link at exactly 0.3 confidence counts as near-miss."""
        service = OrphanDetectionService()
        near_miss_ids = {"TC-001"}
        action = service._determine_suggested_action("TC-001", near_miss_ids)
        assert action == "link_to_requirement"

    def test_no_near_miss_creates_requirement(self):
        """Test case with no near-miss gets 'create_requirement'."""
        service = OrphanDetectionService()
        action = service._determine_suggested_action("TC-002", set())
        assert action == "create_requirement"

    def test_near_miss_detection_boundary_below(self):
        """Link at 0.29 confidence does NOT count as near-miss."""
        service = OrphanDetectionService()
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-200",
                test_case_text="Test.",
                target_document_uuid="doc-001",
                target_section="1.1",
            ),
        ]
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-200",
                test_case_text="Test.",
                target_document_uuid="doc-001",
                target_section="1.1",
                link_confidence=0.29,
                link_method="semantic_match",
            ),
        ]
        near_miss_ids = service._find_near_miss_test_cases(tcs, links)
        assert "TC-200" not in near_miss_ids

    def test_near_miss_detection_boundary_at_max(self):
        """Link at exactly 0.49 confidence counts as near-miss."""
        service = OrphanDetectionService()
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-201",
                test_case_text="Test.",
                target_document_uuid="doc-001",
                target_section="1.1",
            ),
        ]
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-201",
                test_case_text="Test.",
                target_document_uuid="doc-001",
                target_section="1.1",
                link_confidence=0.49,
                link_method="semantic_match",
            ),
        ]
        near_miss_ids = service._find_near_miss_test_cases(tcs, links)
        assert "TC-201" in near_miss_ids

    def test_near_miss_detection_at_threshold_excluded(self):
        """Link at exactly 0.5 confidence does NOT count as near-miss."""
        service = OrphanDetectionService()
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-202",
                test_case_text="Test.",
                target_document_uuid="doc-001",
                target_section="1.1",
            ),
        ]
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-202",
                test_case_text="Test.",
                target_document_uuid="doc-001",
                target_section="1.1",
                link_confidence=0.5,
                link_method="semantic_match",
            ),
        ]
        near_miss_ids = service._find_near_miss_test_cases(tcs, links)
        # 0.5 is at the coverage threshold, not in near-miss range
        assert "TC-202" not in near_miss_ids


# ─────────────────────────────────────────────────────────────────────────────
# Tests: classify_orphan_severity public method (Requirement 2.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyOrphanSeverityPublic:
    """Tests for the public classify_orphan_severity method."""

    @pytest.mark.asyncio
    async def test_classifies_with_local_keywords_when_no_client(self):
        """Uses local keyword classification when no InferenceClient."""
        service = OrphanDetectionService()
        reqs = [
            ExtractedRequirement(
                requirement_id="REQ-200",
                requirement_text="The system shall comply with EMA guidelines.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        orphans = await service.classify_orphan_severity(reqs, company_id=1)
        assert orphans[0].severity == "critical"
        assert orphans[0].requirement_id == "REQ-200"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: classify_orphan_risk_level public method (Requirement 3.4)
# ─────────────────────────────────────────────────────────────────────────────


class TestClassifyOrphanRiskLevelPublic:
    """Tests for the public classify_orphan_risk_level method."""

    @pytest.mark.asyncio
    async def test_classifies_with_local_keywords_when_no_client(self):
        """Uses local keyword classification when no InferenceClient."""
        service = OrphanDetectionService()
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-200",
                test_case_text="Interlock test for safety system.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        orphans = await service.classify_orphan_risk_level(
            tcs, company_id=1, links=[]
        )
        assert orphans[0].risk_level == "high"
        assert orphans[0].test_case_id == "TC-200"

    @pytest.mark.asyncio
    async def test_near_miss_links_affect_suggested_action(self):
        """Near-miss links passed to classify_orphan_risk_level affect action."""
        service = OrphanDetectionService()
        tcs = [
            ExtractedTestCase(
                test_case_id="TC-210",
                test_case_text="Standard test procedure.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        near_miss_links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-210",
                test_case_text="Standard test.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.45,
                link_method="semantic_match",
            ),
        ]
        orphans = await service.classify_orphan_risk_level(
            tcs, company_id=1, links=near_miss_links
        )
        assert orphans[0].suggested_action == "link_to_requirement"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Agent Configuration Loading
# ─────────────────────────────────────────────────────────────────────────────


class TestAgentConfiguration:
    """Tests for agent configuration loading."""

    def test_uses_registry_config_when_available(self, mock_agent_registry):
        """Uses agent registry config when Traceability Analyst is found."""
        service = OrphanDetectionService(
            inference_client=AsyncMock(),
            agent_registry=mock_agent_registry,
        )
        prompt, temp, tokens = service._get_agent_config()
        assert prompt == "You are a Traceability Analyst."
        assert temp == 0.15
        assert tokens == 4096

    def test_uses_defaults_when_no_registry(self):
        """Uses default config when no agent registry is provided."""
        service = OrphanDetectionService()
        prompt, temp, tokens = service._get_agent_config()
        assert "Traceability Analyst" in prompt
        assert temp == 0.15
        assert tokens == 4096

    def test_uses_defaults_when_archetype_not_found(self):
        """Uses default config when Traceability Analyst not in registry."""
        registry = MagicMock()
        registry.list_archetypes.return_value = [
            {"archetype": "Change Impact Analyst"}
        ]
        service = OrphanDetectionService(
            inference_client=AsyncMock(),
            agent_registry=registry,
        )
        prompt, temp, tokens = service._get_agent_config()
        assert "Traceability Analyst" in prompt
        assert temp == 0.15
        assert tokens == 4096

    def test_uses_defaults_when_registry_raises(self):
        """Uses default config when registry raises an exception."""
        registry = MagicMock()
        registry.list_archetypes.side_effect = RuntimeError("Registry error")
        service = OrphanDetectionService(
            inference_client=AsyncMock(),
            agent_registry=registry,
        )
        prompt, temp, tokens = service._get_agent_config()
        assert "Traceability Analyst" in prompt
