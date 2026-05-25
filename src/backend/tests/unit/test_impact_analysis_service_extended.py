"""Extended unit tests for ImpactAnalysisService.

Covers additional gaps in requirements 2.6, 2.8, 3.1-3.9, 5.1-5.8:
- _build_change_summary method
- _parse_impact_assessment method (JSON parsing, code blocks, fallback)
- Company scoping in _retrieve_document_content (Req 3.7)
- Invalid severity/action mapping fallback
- Report generation with combined affected_items and gap_findings (Req 5.1, 5.3)

References:
    - Requirements 2.6: Change delta computation
    - Requirements 3.2: Use Change_Impact_Analyst to assess each candidate
    - Requirements 3.3: Severity assignment (critical/major/minor)
    - Requirements 3.7: Company scoping
    - Requirements 5.1: Report creation for all terminal states
    - Requirements 5.3: Report fields
    - Requirements 5.5: Per-item AI reasoning
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.schemas.impact_analysis import (
    AffectedItemSchema,
    ChangeDeltaSchema,
    GapFindingSchema,
)
from alcoabase.services.impact_analysis import ImpactAnalysisService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_knowledge_service() -> MagicMock:
    """Create a mock KnowledgeService."""
    ks = MagicMock()
    mock_result = MagicMock()
    mock_result.excerpt = "# Section 1\nDependent document content."
    ks.hybrid_search = MagicMock(return_value=([mock_result], 1))
    return ks


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(
        return_value=json.dumps({
            "is_impacted": True,
            "impact_severity": "major",
            "affected_sections": ["Section 1"],
            "change_summary": "Missing updated requirements",
            "recommended_action": "update_required",
        })
    )
    return client


@pytest.fixture
def mock_agent_registry() -> MagicMock:
    """Create a mock AgentRegistryService."""
    registry = MagicMock()
    registry.list_archetypes = MagicMock(
        return_value=[
            {
                "archetype": "Change Impact Analyst",
                "system_prompt": "You are a Change Impact Analyst.",
                "contextual_tuning": {"temperature": 0.2, "max_tokens": 4096},
            }
        ]
    )
    return registry


@pytest.fixture
def service(
    mock_knowledge_service: MagicMock,
    mock_inference_client: AsyncMock,
    mock_agent_registry: MagicMock,
) -> ImpactAnalysisService:
    """Create an ImpactAnalysisService with mocked dependencies."""
    return ImpactAnalysisService(
        knowledge_service=mock_knowledge_service,
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
    )


# ---------------------------------------------------------------------------
# _build_change_summary Tests
# ---------------------------------------------------------------------------


class TestBuildChangeSummary:
    """Tests for _build_change_summary method."""

    def test_includes_added_sections(self, service: ImpactAnalysisService) -> None:
        """Summary includes added section titles."""
        delta = ChangeDeltaSchema(
            sections_added=[
                {"title": "New Safety", "content": "PPE required"},
                {"title": "New Scope", "content": "Extended scope"},
            ],
            sections_modified=[],
            sections_deleted=[],
            significance_levels={"high": 1, "medium": 1, "low": 0},
        )
        result = service._build_change_summary(delta)
        assert "Sections added: New Safety, New Scope" in result

    def test_includes_modified_sections(self, service: ImpactAnalysisService) -> None:
        """Summary includes modified section titles."""
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[
                {"title": "Procedures", "content": "Updated steps"},
            ],
            sections_deleted=[],
            significance_levels={"high": 1, "medium": 0, "low": 0},
        )
        result = service._build_change_summary(delta)
        assert "Sections modified: Procedures" in result

    def test_includes_deleted_sections(self, service: ImpactAnalysisService) -> None:
        """Summary includes deleted section titles."""
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[],
            sections_deleted=[
                {"title": "Obsolete Section", "content": "Old content"},
            ],
            significance_levels={"high": 0, "medium": 0, "low": 1},
        )
        result = service._build_change_summary(delta)
        assert "Sections deleted: Obsolete Section" in result

    def test_includes_significance_levels(self, service: ImpactAnalysisService) -> None:
        """Summary includes significance level counts."""
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[
                {"title": "Safety", "content": "Updated"},
            ],
            sections_deleted=[],
            significance_levels={"high": 2, "medium": 1, "low": 3},
        )
        result = service._build_change_summary(delta)
        assert "2 high" in result
        assert "1 medium" in result
        assert "3 low" in result

    def test_empty_delta_only_has_significance(
        self, service: ImpactAnalysisService
    ) -> None:
        """Empty delta only includes significance line."""
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[],
            sections_deleted=[],
            significance_levels={"high": 0, "medium": 0, "low": 0},
        )
        result = service._build_change_summary(delta)
        assert "Significance:" in result
        assert "Sections added" not in result
        assert "Sections modified" not in result
        assert "Sections deleted" not in result


# ---------------------------------------------------------------------------
# _parse_impact_assessment Tests
# ---------------------------------------------------------------------------


class TestParseImpactAssessment:
    """Tests for _parse_impact_assessment method."""

    def test_valid_json_response(self, service: ImpactAnalysisService) -> None:
        """Valid JSON response is correctly parsed."""
        response = json.dumps({
            "is_impacted": True,
            "impact_severity": "critical",
            "affected_sections": ["Section 1", "Section 2"],
            "change_summary": "Document contradicts updated requirements",
            "recommended_action": "update_required",
        })
        result = service._parse_impact_assessment(response)
        assert result["is_impacted"] is True
        assert result["impact_severity"] == "critical"
        assert result["affected_sections"] == ["Section 1", "Section 2"]
        assert result["recommended_action"] == "update_required"

    def test_json_in_code_block(self, service: ImpactAnalysisService) -> None:
        """JSON wrapped in ```json code block is correctly parsed."""
        response = '```json\n{"is_impacted": true, "impact_severity": "major", "affected_sections": [], "change_summary": "Missing content", "recommended_action": "update_required"}\n```'
        result = service._parse_impact_assessment(response)
        assert result["is_impacted"] is True
        assert result["impact_severity"] == "major"

    def test_json_in_generic_code_block(self, service: ImpactAnalysisService) -> None:
        """JSON wrapped in generic ``` code block is correctly parsed."""
        response = '```\n{"is_impacted": false, "impact_severity": "minor", "affected_sections": [], "change_summary": "No impact", "recommended_action": "review_recommended"}\n```'
        result = service._parse_impact_assessment(response)
        assert result["is_impacted"] is False

    def test_invalid_json_returns_fallback(
        self, service: ImpactAnalysisService
    ) -> None:
        """Invalid JSON falls back to impacted with minor severity."""
        response = "This is not valid JSON at all."
        result = service._parse_impact_assessment(response)
        assert result["is_impacted"] is True
        assert result["impact_severity"] == "minor"
        assert result["recommended_action"] == "review_recommended"

    def test_empty_response_returns_fallback(
        self, service: ImpactAnalysisService
    ) -> None:
        """Empty response falls back to impacted with minor severity."""
        result = service._parse_impact_assessment("")
        assert result["is_impacted"] is True
        assert result["impact_severity"] == "minor"


# ---------------------------------------------------------------------------
# Company Scoping Tests (Req 3.7)
# ---------------------------------------------------------------------------


class TestCompanyScoping:
    """Tests for company scoping in document retrieval."""

    @pytest.mark.asyncio
    async def test_retrieve_document_content_passes_company_filter(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock
    ) -> None:
        """_retrieve_document_content passes document_uuid filter to KnowledgeService."""
        await service._retrieve_document_content("DOC-12345", company_id=7)

        mock_knowledge_service.hybrid_search.assert_called_once()
        call_kwargs = mock_knowledge_service.hybrid_search.call_args
        # Verify the filters include document_uuid
        assert call_kwargs[1]["filters"]["document_uuid"] == ["DOC-12345"]

    @pytest.mark.asyncio
    async def test_assess_affected_items_passes_company_id(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock
    ) -> None:
        """assess_affected_items uses company_id for document retrieval."""
        from alcoabase.models.impact_analysis import DependencyEdge

        edge = MagicMock(spec=DependencyEdge)
        edge.source_document_uuid = "SRC-00001"
        edge.target_document_uuid = "TGT-00001"
        edge.dependency_type = "references"
        edge.confidence_score = 0.8
        edge.company_id = 5

        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[{"title": "Test", "content": "Changed"}],
            sections_deleted=[],
            significance_levels={"high": 1, "medium": 0, "low": 0},
        )

        await service.assess_affected_items(delta, [edge], company_id=5)

        # Verify KnowledgeService was called (for document retrieval)
        assert mock_knowledge_service.hybrid_search.called


# ---------------------------------------------------------------------------
# Invalid Severity/Action Mapping Tests
# ---------------------------------------------------------------------------


class TestInvalidSeverityActionMapping:
    """Tests for handling invalid severity/action values from AI response."""

    @pytest.mark.asyncio
    async def test_invalid_severity_defaults_to_minor(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Invalid severity value from AI defaults to 'minor'."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "is_impacted": True,
            "impact_severity": "extreme",  # Invalid value
            "affected_sections": ["Section 1"],
            "change_summary": "Some impact detected",
            "recommended_action": "update_required",
        })

        from alcoabase.models.impact_analysis import DependencyEdge

        edge = MagicMock(spec=DependencyEdge)
        edge.source_document_uuid = "SRC-00001"
        edge.target_document_uuid = "TGT-00001"
        edge.dependency_type = "references"
        edge.confidence_score = 0.8
        edge.company_id = 1

        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[{"title": "Test", "content": "Changed"}],
            sections_deleted=[],
            significance_levels={"high": 1, "medium": 0, "low": 0},
        )

        result = await service.assess_affected_items(delta, [edge], company_id=1)
        assert len(result) == 1
        assert result[0].impact_severity == "minor"

    @pytest.mark.asyncio
    async def test_invalid_action_defaults_to_review_recommended(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Invalid recommended_action from AI defaults to 'review_recommended'."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "is_impacted": True,
            "impact_severity": "major",
            "affected_sections": ["Section 1"],
            "change_summary": "Missing content",
            "recommended_action": "do_something_else",  # Invalid value
        })

        from alcoabase.models.impact_analysis import DependencyEdge

        edge = MagicMock(spec=DependencyEdge)
        edge.source_document_uuid = "SRC-00001"
        edge.target_document_uuid = "TGT-00001"
        edge.dependency_type = "references"
        edge.confidence_score = 0.8
        edge.company_id = 1

        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[{"title": "Test", "content": "Changed"}],
            sections_deleted=[],
            significance_levels={"high": 1, "medium": 0, "low": 0},
        )

        result = await service.assess_affected_items(delta, [edge], company_id=1)
        assert len(result) == 1
        assert result[0].recommended_action == "review_recommended"


# ---------------------------------------------------------------------------
# Report Generation with Combined Data (Req 5.1, 5.3, 5.5)
# ---------------------------------------------------------------------------


class TestReportGenerationCombined:
    """Tests for report generation with both affected_items and gap_findings."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create a mock async database session."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def report_service(self) -> ImpactAnalysisService:
        """Create service for report generation tests."""
        return ImpactAnalysisService(
            knowledge_service=None,
            inference_client=None,
            agent_registry=None,
            session_factory=None,
            job_tracker=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_report_with_both_items_and_findings(
        self, report_service: ImpactAnalysisService, mock_session: AsyncMock
    ) -> None:
        """Report correctly stores both affected_items and gap_findings."""
        affected_items = [
            AffectedItemSchema(
                affected_document_uuid="DOC-00001",
                affected_document_title="SOP-001",
                dependency_type="validates",
                impact_severity="critical",
                affected_sections=["Section 3.1"],
                change_summary="Contradicts updated safety requirements",
                recommended_action="update_required",
                inference_prompt_summary="Assess impact of changes to safety...",
                model_response_summary="The document contradicts...",
                token_count=512,
            ),
            AffectedItemSchema(
                affected_document_uuid="DOC-00002",
                affected_document_title="MVP-001",
                dependency_type="implements",
                impact_severity="major",
                affected_sections=["Section 2.1", "Section 2.2"],
                change_summary="Missing updated test requirements",
                recommended_action="update_required",
                inference_prompt_summary="Assess impact on test protocol...",
                model_response_summary="The protocol is missing...",
                token_count=480,
            ),
        ]

        gap_findings = [
            GapFindingSchema(
                source_section="1.1 Purpose",
                source_content_excerpt="The purpose of this document...",
                target_section="1.1 Purpose",
                target_content_excerpt="This document describes...",
                gap_type="outdated",
                severity="minor",
                remediation_suggestion="Update target section.",
                inference_prompt_summary="Compare source and target...",
                model_response_summary="The target uses outdated...",
                token_count=256,
            ),
        ]

        delta = ChangeDeltaSchema(
            sections_added=[{"title": "New Req", "content": "New requirement"}],
            sections_modified=[{"title": "Safety", "content": "Updated PPE"}],
            sections_deleted=[],
            significance_levels={"high": 2, "medium": 0, "low": 0},
        )

        report_id = await report_service.create_impact_report(
            session=mock_session,
            job_id="job-combined",
            triggering_document_uuid="2024-00001",
            triggering_version_id=3,
            change_delta_summary=delta,
            affected_items=affected_items,
            gap_findings=gap_findings,
            status="completed",
            analysis_timestamp=datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc),
            analysis_duration_ms=12000,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=1248,
            company_id=1,
            requesting_user_id=10,
        )

        assert report_id is not None
        report = mock_session.add.call_args[0][0]

        # Verify affected_items serialization
        assert len(report.affected_items) == 2
        assert report.affected_items[0]["impact_severity"] == "critical"
        assert report.affected_items[0]["inference_prompt_summary"] != ""
        assert report.affected_items[1]["impact_severity"] == "major"
        assert report.affected_items[1]["token_count"] == 480

        # Verify gap_findings serialization
        assert len(report.gap_findings) == 1
        assert report.gap_findings[0]["gap_type"] == "outdated"
        assert report.gap_findings[0]["inference_prompt_summary"] != ""

        # Verify total_token_count
        assert report.total_token_count == 1248

    @pytest.mark.asyncio
    async def test_partial_success_report_preserves_partial_data(
        self, report_service: ImpactAnalysisService, mock_session: AsyncMock
    ) -> None:
        """Partial success report preserves items assessed before timeout."""
        affected_items = [
            AffectedItemSchema(
                affected_document_uuid="DOC-00001",
                affected_document_title="SOP-001",
                dependency_type="references",
                impact_severity="minor",
                affected_sections=["Section 1"],
                change_summary="Outdated reference",
                recommended_action="review_recommended",
                inference_prompt_summary="Assess...",
                model_response_summary="Outdated...",
                token_count=200,
            ),
        ]

        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[{"title": "Refs", "content": "Updated ref"}],
            sections_deleted=[],
            significance_levels={"high": 0, "medium": 1, "low": 0},
            metadata={"unassessed_items": ["DOC-00002", "DOC-00003"]},
        )

        await report_service.create_impact_report(
            session=mock_session,
            job_id="job-partial",
            triggering_document_uuid="2024-00001",
            triggering_version_id=2,
            change_delta_summary=delta,
            affected_items=affected_items,
            gap_findings=[],
            status="partial_success",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=600000,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=200,
            company_id=1,
        )

        report = mock_session.add.call_args[0][0]
        assert report.status == "partial_success"
        assert len(report.affected_items) == 1
        assert report.change_delta_summary["metadata"]["unassessed_items"] == [
            "DOC-00002", "DOC-00003"
        ]
