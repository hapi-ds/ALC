"""Unit tests for ImpactAnalysisService.assess_affected_items.

Tests candidate prioritization, severity assignment, per-item error handling,
and training task identification logic.

References:
    - Requirements 3.1: Query dependency graph for downstream edges
    - Requirements 3.2: Use Change_Impact_Analyst to assess each candidate
    - Requirements 3.3: Severity assignment (critical/major/minor)
    - Requirements 3.4: Training task identification
    - Requirements 3.5: Produce AffectedItemSchema list
    - Requirements 3.6: Candidate prioritization (top 50)
    - Requirements 3.7: Company scoping
    - Requirements 3.8: InferenceClient failure handling
    - Requirements 3.9: KnowledgeService failure handling
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.impact_analysis import DependencyEdge
from alcoabase.schemas.impact_analysis import AffectedItemSchema, ChangeDeltaSchema
from alcoabase.services.impact_analysis import ImpactAnalysisService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_edge(
    source_uuid: str = "SRC-00001",
    target_uuid: str = "TGT-00001",
    dependency_type: str = "references",
    confidence_score: float = 0.8,
    company_id: int = 1,
) -> DependencyEdge:
    """Create a mock DependencyEdge for testing."""
    edge = MagicMock(spec=DependencyEdge)
    edge.source_document_uuid = source_uuid
    edge.target_document_uuid = target_uuid
    edge.dependency_type = dependency_type
    edge.confidence_score = confidence_score
    edge.company_id = company_id
    return edge


def _make_change_delta(
    sections_added: list[dict] | None = None,
    sections_modified: list[dict] | None = None,
    sections_deleted: list[dict] | None = None,
    significance_levels: dict | None = None,
) -> ChangeDeltaSchema:
    """Create a ChangeDeltaSchema for testing."""
    return ChangeDeltaSchema(
        sections_added=sections_added or [],
        sections_modified=sections_modified or [
            {"title": "Safety Procedures", "content": "Updated PPE requirements"}
        ],
        sections_deleted=sections_deleted or [],
        significance_levels=significance_levels or {"high": 1, "medium": 0, "low": 0},
    )


@pytest.fixture
def mock_knowledge_service() -> MagicMock:
    """Create a mock KnowledgeService that returns document content."""
    ks = MagicMock()
    mock_result = MagicMock()
    mock_result.excerpt = "# Section 1\nThis is the dependent document content."
    ks.hybrid_search = MagicMock(return_value=([mock_result], 1))
    return ks


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient that returns a valid assessment."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(
        return_value=json.dumps({
            "is_impacted": True,
            "impact_severity": "major",
            "affected_sections": ["Section 1"],
            "change_summary": "The dependent document is missing updated PPE requirements",
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
# Candidate Prioritization Tests
# ---------------------------------------------------------------------------


class TestCandidatePrioritization:
    """Tests for _prioritize_candidates method (Req 3.6)."""

    def test_sorts_by_confidence_score_descending(
        self, service: ImpactAnalysisService
    ) -> None:
        """Candidates are sorted by confidence_score descending."""
        edges = [
            _make_edge(target_uuid="LOW-00001", confidence_score=0.5),
            _make_edge(target_uuid="HIGH-0001", confidence_score=0.9),
            _make_edge(target_uuid="MED-00001", confidence_score=0.7),
        ]
        result = service._prioritize_candidates(edges)
        scores = [e.confidence_score for e in result]
        assert scores == [0.9, 0.7, 0.5]

    def test_sorts_by_dependency_type_priority_on_tie(
        self, service: ImpactAnalysisService
    ) -> None:
        """On equal confidence, sorts by dependency_type priority."""
        edges = [
            _make_edge(dependency_type="derived_from", confidence_score=0.8),
            _make_edge(dependency_type="validates", confidence_score=0.8),
            _make_edge(dependency_type="references", confidence_score=0.8),
            _make_edge(dependency_type="implements", confidence_score=0.8),
            _make_edge(dependency_type="trains_on", confidence_score=0.8),
        ]
        result = service._prioritize_candidates(edges)
        types = [e.dependency_type for e in result]
        assert types == [
            "validates", "implements", "references", "trains_on", "derived_from"
        ]

    def test_limits_to_50_candidates(
        self, service: ImpactAnalysisService
    ) -> None:
        """Only top 50 candidates are returned."""
        edges = [
            _make_edge(target_uuid=f"DOC-{i:05d}", confidence_score=i / 100.0)
            for i in range(80)
        ]
        result = service._prioritize_candidates(edges)
        assert len(result) == 50

    def test_empty_edges_returns_empty(
        self, service: ImpactAnalysisService
    ) -> None:
        """Empty input returns empty list."""
        result = service._prioritize_candidates([])
        assert result == []

    def test_fewer_than_50_returns_all(
        self, service: ImpactAnalysisService
    ) -> None:
        """Fewer than 50 candidates returns all of them."""
        edges = [_make_edge(target_uuid=f"DOC-{i:05d}") for i in range(10)]
        result = service._prioritize_candidates(edges)
        assert len(result) == 10


# ---------------------------------------------------------------------------
# Affected Item Assessment Tests
# ---------------------------------------------------------------------------


class TestAssessAffectedItems:
    """Tests for assess_affected_items method."""

    @pytest.mark.asyncio
    async def test_returns_affected_items_on_impact(
        self, service: ImpactAnalysisService
    ) -> None:
        """Returns AffectedItemSchema when agent confirms impact."""
        edges = [_make_edge()]
        delta = _make_change_delta()

        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert len(result) == 1
        item = result[0]
        assert isinstance(item, AffectedItemSchema)
        assert item.affected_document_uuid == "TGT-00001"
        assert item.impact_severity == "major"
        assert item.recommended_action == "update_required"
        assert item.dependency_type == "references"

    @pytest.mark.asyncio
    async def test_excludes_non_impacted_items(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Items determined as not impacted are excluded."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "is_impacted": False,
            "impact_severity": "minor",
            "affected_sections": [],
            "change_summary": "No impact",
            "recommended_action": "review_recommended",
        })

        edges = [_make_edge()]
        delta = _make_change_delta()

        result = await service.assess_affected_items(delta, edges, company_id=1)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_empty_edges_returns_empty(
        self, service: ImpactAnalysisService
    ) -> None:
        """Empty downstream edges returns empty list."""
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, [], company_id=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_edges_assessed(
        self, service: ImpactAnalysisService
    ) -> None:
        """Multiple edges are each assessed independently."""
        edges = [
            _make_edge(target_uuid="DOC-00001"),
            _make_edge(target_uuid="DOC-00002"),
            _make_edge(target_uuid="DOC-00003"),
        ]
        delta = _make_change_delta()

        result = await service.assess_affected_items(delta, edges, company_id=1)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Severity Assignment Tests
# ---------------------------------------------------------------------------


class TestSeverityAssignment:
    """Tests for severity assignment (Req 3.3)."""

    @pytest.mark.asyncio
    async def test_critical_severity_on_contradiction(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Critical severity when dependent contradicts source."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "is_impacted": True,
            "impact_severity": "critical",
            "affected_sections": ["Safety"],
            "change_summary": "Document contradicts updated safety requirements",
            "recommended_action": "update_required",
        })

        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert result[0].impact_severity == "critical"

    @pytest.mark.asyncio
    async def test_major_severity_on_missing(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Major severity when dependent is missing required content."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "is_impacted": True,
            "impact_severity": "major",
            "affected_sections": ["Requirements"],
            "change_summary": "Missing updated requirements",
            "recommended_action": "update_required",
        })

        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert result[0].impact_severity == "major"

    @pytest.mark.asyncio
    async def test_minor_severity_on_outdated(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Minor severity when dependent uses outdated terminology."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "is_impacted": True,
            "impact_severity": "minor",
            "affected_sections": ["References"],
            "change_summary": "Uses outdated version reference",
            "recommended_action": "review_recommended",
        })

        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert result[0].impact_severity == "minor"


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestPerItemErrorHandling:
    """Tests for per-item error handling (Req 3.8, 3.9)."""

    @pytest.mark.asyncio
    async def test_inference_failure_marks_unknown(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """InferenceClient failure marks item as unknown/manual_review_required."""
        mock_inference_client.chat_completion.side_effect = Exception(
            "Connection timeout"
        )

        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert len(result) == 1
        assert result[0].impact_severity == "unknown"
        assert result[0].recommended_action == "manual_review_required"
        assert "Inference" in result[0].model_response_summary

    @pytest.mark.asyncio
    async def test_knowledge_service_failure_marks_unknown(
        self,
        mock_inference_client: AsyncMock,
        mock_agent_registry: MagicMock,
    ) -> None:
        """KnowledgeService failure marks item as unknown/manual_review_required."""
        ks = MagicMock()
        ks.hybrid_search = MagicMock(side_effect=Exception("Storage unavailable"))

        svc = ImpactAnalysisService(
            knowledge_service=ks,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await svc.assess_affected_items(delta, edges, company_id=1)

        assert len(result) == 1
        assert result[0].impact_severity == "unknown"
        assert result[0].recommended_action == "manual_review_required"
        assert "KnowledgeService" in result[0].model_response_summary

    @pytest.mark.asyncio
    async def test_knowledge_service_returns_none(
        self,
        mock_inference_client: AsyncMock,
        mock_agent_registry: MagicMock,
    ) -> None:
        """When KnowledgeService returns no content, marks as unknown."""
        ks = MagicMock()
        ks.hybrid_search = MagicMock(return_value=([], 0))

        svc = ImpactAnalysisService(
            knowledge_service=ks,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await svc.assess_affected_items(delta, edges, company_id=1)

        assert len(result) == 1
        assert result[0].impact_severity == "unknown"
        assert result[0].recommended_action == "manual_review_required"

    @pytest.mark.asyncio
    async def test_inference_client_none_marks_unknown(
        self,
        mock_knowledge_service: MagicMock,
        mock_agent_registry: MagicMock,
    ) -> None:
        """When InferenceClient is None, marks item as unknown."""
        svc = ImpactAnalysisService(
            knowledge_service=mock_knowledge_service,
            inference_client=None,
            agent_registry=mock_agent_registry,
        )

        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await svc.assess_affected_items(delta, edges, company_id=1)

        assert len(result) == 1
        assert result[0].impact_severity == "unknown"
        assert result[0].recommended_action == "manual_review_required"

    @pytest.mark.asyncio
    async def test_partial_failures_continue_processing(
        self,
        service: ImpactAnalysisService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Failure on one item doesn't stop processing of others."""
        # First call fails, second succeeds
        mock_inference_client.chat_completion.side_effect = [
            Exception("Timeout"),
            json.dumps({
                "is_impacted": True,
                "impact_severity": "minor",
                "affected_sections": [],
                "change_summary": "Outdated reference",
                "recommended_action": "review_recommended",
            }),
        ]

        edges = [
            _make_edge(target_uuid="FAIL-0001"),
            _make_edge(target_uuid="PASS-0001"),
        ]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert len(result) == 2
        # First item failed
        assert result[0].impact_severity == "unknown"
        assert result[0].affected_document_uuid == "FAIL-0001"
        # Second item succeeded
        assert result[1].impact_severity == "minor"
        assert result[1].affected_document_uuid == "PASS-0001"


# ---------------------------------------------------------------------------
# Training Task Identification Tests
# ---------------------------------------------------------------------------


class TestTrainingTaskIdentification:
    """Tests for training task identification (Req 3.4)."""

    @pytest.mark.asyncio
    async def test_incomplete_tasks_flagged_for_review(
        self,
        service: ImpactAnalysisService,
    ) -> None:
        """Incomplete training tasks are flagged with major severity."""
        # Create mock session and training task
        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.task_title = "Read SOP v2.0"
        mock_task.is_completed = False

        incomplete_result = MagicMock()
        incomplete_result.scalars.return_value.all.return_value = [mock_task]

        # No completed tasks
        completed_result = MagicMock()
        completed_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[incomplete_result, completed_result]
        )

        edges = [_make_edge(source_uuid="SOP-00001")]
        delta = _make_change_delta()

        result = await service.assess_affected_items(
            delta, edges, company_id=1, session=mock_session
        )

        # Find the training task item (exclude the document assessment item)
        training_items = [i for i in result if i.training_task_id is not None]
        assert len(training_items) == 1
        assert training_items[0].training_task_id == 42
        assert training_items[0].impact_severity == "major"
        assert training_items[0].recommended_action == "review_recommended"
        assert training_items[0].dependency_type == "trains_on"

    @pytest.mark.asyncio
    async def test_completed_tasks_flagged_on_safety_changes(
        self,
        service: ImpactAnalysisService,
    ) -> None:
        """Completed tasks flagged for retraining on procedural/safety changes."""
        # Create mock session
        incomplete_task = MagicMock()
        incomplete_task.id = 10
        incomplete_task.task_title = "Read SOP v2.0 (incomplete)"
        incomplete_task.is_completed = False

        completed_task = MagicMock()
        completed_task.id = 20
        completed_task.task_title = "Read SOP v1.0 (completed)"
        completed_task.is_completed = True

        incomplete_result = MagicMock()
        incomplete_result.scalars.return_value.all.return_value = [incomplete_task]

        completed_result = MagicMock()
        completed_result.scalars.return_value.all.return_value = [completed_task]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=[incomplete_result, completed_result]
        )

        edges = [_make_edge(source_uuid="SOP-00001")]
        # Delta with high significance (safety changes)
        delta = _make_change_delta(
            sections_modified=[
                {"title": "Safety Procedures", "content": "New PPE requirements"}
            ],
            significance_levels={"high": 1, "medium": 0, "low": 0},
        )

        result = await service.assess_affected_items(
            delta, edges, company_id=1, session=mock_session
        )

        training_items = [i for i in result if i.training_task_id is not None]
        # Should have both incomplete and completed task items
        assert len(training_items) == 2

        completed_items = [
            i for i in training_items if i.recommended_action == "retraining_required"
        ]
        assert len(completed_items) == 1
        assert completed_items[0].impact_severity == "critical"
        assert completed_items[0].training_task_id == 20

    @pytest.mark.asyncio
    async def test_completed_tasks_not_flagged_without_safety_changes(
        self,
        service: ImpactAnalysisService,
    ) -> None:
        """Completed tasks NOT flagged when no procedural/safety changes."""
        incomplete_result = MagicMock()
        incomplete_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=incomplete_result)

        edges = [_make_edge(source_uuid="SOP-00001")]
        # Delta with only low significance (no safety changes)
        delta = _make_change_delta(
            sections_modified=[
                {"title": "Formatting", "content": "Fixed typo in header"}
            ],
            significance_levels={"high": 0, "medium": 0, "low": 1},
        )

        result = await service.assess_affected_items(
            delta, edges, company_id=1, session=mock_session
        )

        training_items = [i for i in result if i.training_task_id is not None]
        # No training tasks should be flagged for retraining
        retraining_items = [
            i for i in training_items if i.recommended_action == "retraining_required"
        ]
        assert len(retraining_items) == 0

    @pytest.mark.asyncio
    async def test_training_task_query_failure_marks_unknown(
        self,
        service: ImpactAnalysisService,
    ) -> None:
        """DB query failure for training tasks marks as unknown."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=Exception("Database connection lost")
        )

        edges = [_make_edge(source_uuid="SOP-00001")]
        delta = _make_change_delta()

        result = await service.assess_affected_items(
            delta, edges, company_id=1, session=mock_session
        )

        training_items = [
            i for i in result
            if i.impact_severity == "unknown" and i.dependency_type == "trains_on"
        ]
        assert len(training_items) == 1
        assert training_items[0].recommended_action == "manual_review_required"


# ---------------------------------------------------------------------------
# Procedural/Safety Change Detection Tests
# ---------------------------------------------------------------------------


class TestHasProceduralSafetyChanges:
    """Tests for _has_procedural_safety_changes method."""

    def test_detects_safety_keywords(
        self, service: ImpactAnalysisService
    ) -> None:
        """Detects safety-related keywords in changes."""
        delta = _make_change_delta(
            sections_modified=[
                {"title": "PPE Requirements", "content": "Wear gloves and goggles"}
            ],
            significance_levels={"high": 0, "medium": 1, "low": 0},
        )
        assert service._has_procedural_safety_changes(delta) is True

    def test_detects_high_significance(
        self, service: ImpactAnalysisService
    ) -> None:
        """High significance level implies safety changes."""
        delta = _make_change_delta(
            sections_modified=[
                {"title": "General", "content": "Some content"}
            ],
            significance_levels={"high": 1, "medium": 0, "low": 0},
        )
        assert service._has_procedural_safety_changes(delta) is True

    def test_no_safety_changes_detected(
        self, service: ImpactAnalysisService
    ) -> None:
        """Returns False when no safety-related content found."""
        delta = _make_change_delta(
            sections_modified=[
                {"title": "Background", "content": "General information about the project"}
            ],
            significance_levels={"high": 0, "medium": 1, "low": 0},
        )
        assert service._has_procedural_safety_changes(delta) is False


# ---------------------------------------------------------------------------
# AffectedItemSchema Output Tests
# ---------------------------------------------------------------------------


class TestAffectedItemSchemaOutput:
    """Tests for correct AffectedItemSchema field population (Req 3.5)."""

    @pytest.mark.asyncio
    async def test_inference_prompt_summary_populated(
        self, service: ImpactAnalysisService
    ) -> None:
        """inference_prompt_summary is populated (max 500 chars)."""
        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert result[0].inference_prompt_summary != ""
        assert len(result[0].inference_prompt_summary) <= 500

    @pytest.mark.asyncio
    async def test_model_response_summary_populated(
        self, service: ImpactAnalysisService
    ) -> None:
        """model_response_summary is populated (max 500 chars)."""
        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert result[0].model_response_summary != ""
        assert len(result[0].model_response_summary) <= 500

    @pytest.mark.asyncio
    async def test_token_count_populated(
        self, service: ImpactAnalysisService
    ) -> None:
        """token_count is populated with a positive value."""
        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert result[0].token_count > 0

    @pytest.mark.asyncio
    async def test_affected_sections_from_agent(
        self, service: ImpactAnalysisService
    ) -> None:
        """affected_sections comes from the agent response."""
        edges = [_make_edge()]
        delta = _make_change_delta()
        result = await service.assess_affected_items(delta, edges, company_id=1)

        assert result[0].affected_sections == ["Section 1"]
