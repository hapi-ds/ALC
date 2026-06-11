"""Unit tests for ContradictionDetectionService.

Tests contradiction analysis, novelty flag creation, escalation logic,
partial failure handling, and JSON response parsing.

References:
    - Requirements: 5.1, 5.2, 5.6, 6.2, 6.3
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridSearchResponse,
    HybridSearchResult,
)
from alcoabase.literature.review.services.contradiction_detection_service import (
    ContradictionAnalysisResult,
    ContradictionDetectionService,
    classify_priority,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession with standard methods."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock):
    """Create a session factory returning mock session as async context manager."""

    @asynccontextmanager
    async def _factory():
        yield mock_session

    return _factory


@pytest.fixture
def mock_hybrid_query_engine() -> AsyncMock:
    """Mock HybridQueryEngine with search method."""
    engine = AsyncMock()
    engine.search = AsyncMock(
        return_value=HybridSearchResponse(
            results=[], total_count=0, page=1, page_size=10
        )
    )
    return engine


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Mock InferenceClient with chat_completion method."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(return_value="")
    return client


@pytest.fixture
def mock_impact_analysis_service() -> AsyncMock:
    """Mock ImpactAnalysisService with compute_change_delta method."""
    service = AsyncMock()
    service.compute_change_delta = AsyncMock()
    return service


@pytest.fixture
def mock_ingestion_record() -> MagicMock:
    """Create a mock IngestionRecord ORM object."""
    record = MagicMock()
    record.id = 1
    record.company_id = 42
    record.title = "Novel CRISPR Gene Editing Technique"
    record.abstract = "We present a new approach to gene editing with improved efficiency."
    return record


@pytest.fixture
def service(
    mock_session_factory,
    mock_hybrid_query_engine: AsyncMock,
    mock_inference_client: AsyncMock,
    mock_impact_analysis_service: AsyncMock,
) -> ContradictionDetectionService:
    """Create a ContradictionDetectionService with mocked dependencies."""
    return ContradictionDetectionService(
        session_factory=mock_session_factory,
        hybrid_query_engine=mock_hybrid_query_engine,
        inference_client=mock_inference_client,
        impact_analysis_service=mock_impact_analysis_service,
        model_name="test-model",
        similarity_threshold=0.6,
        confidence_threshold=0.7,
        max_candidates=10,
    )


@pytest.fixture
def valid_contradiction_json() -> str:
    """Valid JSON response indicating a contradiction was found."""
    return json.dumps({
        "contradiction_found": True,
        "contradiction_description": "The paper recommends 25°C storage, but SOP-001 mandates 2-8°C.",
        "severity": "critical",
        "affected_internal_sections": ["Section 4.2", "Section 4.3"],
        "evidence_from_literature": "Study data shows stability at 25°C for 24 months.",
        "recommended_action": "Review SOP-001 storage conditions against new stability data.",
        "confidence": 0.92,
    })


@pytest.fixture
def no_contradiction_json() -> str:
    """Valid JSON response indicating no contradiction."""
    return json.dumps({
        "contradiction_found": False,
        "contradiction_description": "",
        "severity": "minor",
        "affected_internal_sections": [],
        "evidence_from_literature": "",
        "recommended_action": "",
        "confidence": 0.85,
    })


def _make_search_result(
    relevance_score: float = 0.8,
    title: str = "Internal SOP-001",
    chunk_text: str = "Store product at 2-8°C per validated conditions.",
    ingestion_record_id: int = 100,
) -> HybridSearchResult:
    """Helper to build a HybridSearchResult."""
    return HybridSearchResult(
        chunk_text=chunk_text,
        title=title,
        authors=["Author A"],
        doi=None,
        publication_date=None,
        source_id=None,
        relevance_score=relevance_score,
        partition_tag="private_knowledge",
        section_heading="Storage Conditions",
        ingestion_record_id=ingestion_record_id,
    )


# ---------------------------------------------------------------------------
# Tests: analyze_record — no internal docs found (creates NoveltyFlag)
# ---------------------------------------------------------------------------


class TestAnalyzeRecordNoveltyFlag:
    """Tests for analyze_record when no internal docs found."""

    @pytest.mark.asyncio
    async def test_creates_novelty_flag_when_no_internal_docs(
        self,
        service: ContradictionDetectionService,
        mock_session: AsyncMock,
        mock_hybrid_query_engine: AsyncMock,
        mock_inference_client: AsyncMock,
        mock_ingestion_record: MagicMock,
    ):
        """Creates NoveltyFlag when HybridQueryEngine returns no results.

        Validates: Requirements 5.1, 5.2
        """
        # Mock: record is found in DB
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ingestion_record
        mock_session.execute.return_value = mock_result

        # Mock: no internal docs found
        mock_hybrid_query_engine.search.return_value = HybridSearchResponse(
            results=[], total_count=0, page=1, page_size=10
        )

        # Mock: novelty LLM response
        mock_inference_client.chat_completion.return_value = json.dumps({
            "novelty_description": "Novel gene editing approach not in internal docs.",
            "relevance_score": 0.75,
            "suggested_document_types": ["SOP", "Risk Assessment"],
        })

        result = await service.analyze_record(record_id=1, company_id=42)

        assert result["novelty_flagged"] is True
        assert result["contradiction_count"] == 0
        assert result["alerts_created"] == 0
        # NoveltyFlag was added to session
        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.__class__.__name__ == "NoveltyFlag"
        assert added_obj.ingestion_record_id == 1
        assert added_obj.company_id == 42
        mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: analyze_record — contradiction detected (creates Alert)
# ---------------------------------------------------------------------------


class TestAnalyzeRecordContradictionDetected:
    """Tests for analyze_record when contradictions are found."""

    @pytest.mark.asyncio
    async def test_creates_alert_when_contradiction_above_threshold(
        self,
        service: ContradictionDetectionService,
        mock_session: AsyncMock,
        mock_hybrid_query_engine: AsyncMock,
        mock_inference_client: AsyncMock,
        mock_ingestion_record: MagicMock,
        valid_contradiction_json: str,
    ):
        """Creates ContradictionAlert when contradiction found with confidence >= threshold.

        Validates: Requirements 5.2, 5.6
        """
        # Mock: record is found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ingestion_record
        mock_session.execute.return_value = mock_result

        # Mock: internal docs found above similarity threshold
        search_result = _make_search_result(relevance_score=0.8)
        mock_hybrid_query_engine.search.return_value = HybridSearchResponse(
            results=[search_result], total_count=1, page=1, page_size=10
        )

        # Mock: LLM returns contradiction
        mock_inference_client.chat_completion.return_value = valid_contradiction_json

        result = await service.analyze_record(record_id=1, company_id=42)

        assert result["contradiction_count"] == 1
        assert result["alerts_created"] == 1
        assert result["novelty_flagged"] is False

        # Alert was added to session
        added_calls = mock_session.add.call_args_list
        alert_obj = added_calls[0][0][0]
        assert alert_obj.__class__.__name__ == "ContradictionAlert"
        assert alert_obj.severity == "critical"
        assert alert_obj.confidence == 0.92
        assert alert_obj.ingestion_record_id == 1
        assert alert_obj.company_id == 42
        assert alert_obj.status == "new"


# ---------------------------------------------------------------------------
# Tests: analyze_record — contradiction below confidence threshold
# ---------------------------------------------------------------------------


class TestAnalyzeRecordBelowThreshold:
    """Tests for analyze_record when contradiction below confidence threshold."""

    @pytest.mark.asyncio
    async def test_no_alert_when_confidence_below_threshold(
        self,
        service: ContradictionDetectionService,
        mock_session: AsyncMock,
        mock_hybrid_query_engine: AsyncMock,
        mock_inference_client: AsyncMock,
        mock_ingestion_record: MagicMock,
    ):
        """No alert created when contradiction confidence is below threshold (0.7).

        Validates: Requirements 5.6, 6.2
        """
        # Mock: record is found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ingestion_record
        mock_session.execute.return_value = mock_result

        # Mock: internal docs found
        search_result = _make_search_result(relevance_score=0.75)
        mock_hybrid_query_engine.search.return_value = HybridSearchResponse(
            results=[search_result], total_count=1, page=1, page_size=10
        )

        # Mock: LLM returns contradiction with low confidence (0.5 < 0.7 threshold)
        low_confidence_response = json.dumps({
            "contradiction_found": True,
            "contradiction_description": "Minor discrepancy in temperature range.",
            "severity": "minor",
            "affected_internal_sections": ["Section 2.1"],
            "evidence_from_literature": "Paper mentions 20-25°C.",
            "recommended_action": "Consider reviewing.",
            "confidence": 0.5,
        })
        mock_inference_client.chat_completion.return_value = low_confidence_response

        result = await service.analyze_record(record_id=1, company_id=42)

        # Contradiction is counted but no alert is created
        assert result["contradiction_count"] == 1
        assert result["alerts_created"] == 0
        assert result["novelty_flagged"] is False
        # No objects should be added (no alert)
        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _escalate_critical calls ImpactAnalysisService
# ---------------------------------------------------------------------------


class TestEscalateCritical:
    """Tests for _escalate_critical method."""

    @pytest.mark.asyncio
    async def test_invokes_impact_analysis_for_critical(
        self,
        service: ContradictionDetectionService,
        mock_session: AsyncMock,
        mock_impact_analysis_service: AsyncMock,
    ):
        """Escalate triggers ImpactAnalysisService.compute_change_delta for critical.

        Validates: Requirements 6.2, 6.3
        """
        await service._escalate_critical(
            session=mock_session,
            alert_id=99,
            internal_document_id="doc-uuid-123",
            company_id=42,
        )

        mock_impact_analysis_service.compute_change_delta.assert_awaited_once_with(
            document_uuid="doc-uuid-123",
            new_version_id=0,
            previous_version_id=None,
            company_id=42,
        )

    @pytest.mark.asyncio
    async def test_escalation_does_not_raise_on_impact_failure(
        self,
        service: ContradictionDetectionService,
        mock_session: AsyncMock,
        mock_impact_analysis_service: AsyncMock,
    ):
        """Escalation logs error but does not propagate exceptions.

        Validates: Requirements 6.3
        """
        mock_impact_analysis_service.compute_change_delta.side_effect = RuntimeError(
            "Impact service unavailable"
        )

        # Should not raise
        await service._escalate_critical(
            session=mock_session,
            alert_id=99,
            internal_document_id="doc-uuid-456",
            company_id=42,
        )


# ---------------------------------------------------------------------------
# Tests: _parse_contradiction_response — valid JSON
# ---------------------------------------------------------------------------


class TestParseContradictionResponseValid:
    """Tests for _parse_contradiction_response with valid input."""

    def test_valid_json_returns_result(
        self,
        service: ContradictionDetectionService,
        valid_contradiction_json: str,
    ):
        """Valid JSON produces a ContradictionAnalysisResult.

        Validates: Requirements 5.2
        """
        result = service._parse_contradiction_response(valid_contradiction_json)

        assert result is not None
        assert isinstance(result, ContradictionAnalysisResult)
        assert result.contradiction_found is True
        assert result.severity == "critical"
        assert result.confidence == 0.92
        assert "25°C storage" in result.contradiction_description
        assert "Section 4.2" in result.affected_internal_sections
        assert result.evidence_from_literature != ""
        assert result.recommended_action != ""

    def test_valid_json_no_contradiction(
        self,
        service: ContradictionDetectionService,
        no_contradiction_json: str,
    ):
        """Valid JSON with contradiction_found=False is correctly parsed."""
        result = service._parse_contradiction_response(no_contradiction_json)

        assert result is not None
        assert result.contradiction_found is False
        assert result.severity == "minor"
        assert result.confidence == 0.85

    def test_json_wrapped_in_code_fence(
        self,
        service: ContradictionDetectionService,
    ):
        """JSON wrapped in markdown code fences is correctly parsed."""
        data = {
            "contradiction_found": False,
            "contradiction_description": "",
            "severity": "minor",
            "affected_internal_sections": [],
            "evidence_from_literature": "",
            "recommended_action": "",
            "confidence": 0.6,
        }
        fenced = f"```json\n{json.dumps(data)}\n```"

        result = service._parse_contradiction_response(fenced)

        assert result is not None
        assert result.contradiction_found is False
        assert result.confidence == 0.6


# ---------------------------------------------------------------------------
# Tests: _parse_contradiction_response — malformed JSON
# ---------------------------------------------------------------------------


class TestParseContradictionResponseMalformed:
    """Tests for _parse_contradiction_response with invalid input."""

    def test_malformed_json_returns_none(
        self,
        service: ContradictionDetectionService,
    ):
        """Completely malformed JSON string returns None.

        Validates: Requirements 5.6
        """
        result = service._parse_contradiction_response("not json {{{")

        assert result is None

    def test_missing_contradiction_found_returns_none(
        self,
        service: ContradictionDetectionService,
    ):
        """Missing contradiction_found field returns None."""
        data = json.dumps({
            "contradiction_description": "Some desc",
            "severity": "major",
            "affected_internal_sections": [],
            "evidence_from_literature": "",
            "recommended_action": "",
            "confidence": 0.8,
        })

        result = service._parse_contradiction_response(data)

        assert result is None

    def test_invalid_severity_returns_none(
        self,
        service: ContradictionDetectionService,
    ):
        """Invalid severity value returns None."""
        data = json.dumps({
            "contradiction_found": True,
            "contradiction_description": "Desc",
            "severity": "extreme",
            "affected_internal_sections": [],
            "evidence_from_literature": "",
            "recommended_action": "",
            "confidence": 0.9,
        })

        result = service._parse_contradiction_response(data)

        assert result is None

    def test_confidence_out_of_range_returns_none(
        self,
        service: ContradictionDetectionService,
    ):
        """Confidence > 1.0 returns None."""
        data = json.dumps({
            "contradiction_found": True,
            "contradiction_description": "Desc",
            "severity": "major",
            "affected_internal_sections": [],
            "evidence_from_literature": "",
            "recommended_action": "",
            "confidence": 1.5,
        })

        result = service._parse_contradiction_response(data)

        assert result is None

    def test_empty_string_returns_none(
        self,
        service: ContradictionDetectionService,
    ):
        """Empty string returns None."""
        result = service._parse_contradiction_response("")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: Partial failure handling (some pairs succeed, some fail, retries)
# ---------------------------------------------------------------------------


class TestPartialFailureHandling:
    """Tests for partial failure and retry behavior in analyze_record."""

    @pytest.mark.asyncio
    async def test_successful_pairs_persisted_despite_failures(
        self,
        service: ContradictionDetectionService,
        mock_session: AsyncMock,
        mock_hybrid_query_engine: AsyncMock,
        mock_inference_client: AsyncMock,
        mock_ingestion_record: MagicMock,
        valid_contradiction_json: str,
    ):
        """Successful pair analyses are persisted even when other pairs fail.

        Validates: Requirements 5.6, 6.2
        """
        # Mock: record found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ingestion_record
        mock_session.execute.return_value = mock_result

        # Mock: 2 internal docs found
        result1 = _make_search_result(relevance_score=0.85, title="SOP-001")
        result2 = _make_search_result(
            relevance_score=0.75, title="URS-002", ingestion_record_id=200
        )
        mock_hybrid_query_engine.search.return_value = HybridSearchResponse(
            results=[result1, result2], total_count=2, page=1, page_size=10
        )

        # First pair succeeds, second pair fails all attempts (initial + 2 retries)
        mock_inference_client.chat_completion.side_effect = [
            valid_contradiction_json,  # pair 1: success
            RuntimeError("LLM timeout"),  # pair 2: initial fail
            RuntimeError("LLM timeout"),  # pair 2: retry 1
            RuntimeError("LLM timeout"),  # pair 2: retry 2
        ]

        result = await service.analyze_record(record_id=1, company_id=42)

        # First pair's contradiction should still be persisted
        assert result["contradiction_count"] == 1
        assert result["alerts_created"] == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(
        self,
        service: ContradictionDetectionService,
        mock_session: AsyncMock,
        mock_hybrid_query_engine: AsyncMock,
        mock_inference_client: AsyncMock,
        mock_ingestion_record: MagicMock,
        valid_contradiction_json: str,
    ):
        """Failed pairs that succeed on retry are included in results.

        Validates: Requirements 5.6
        """
        # Mock: record found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ingestion_record
        mock_session.execute.return_value = mock_result

        # Mock: 1 internal doc found
        result1 = _make_search_result(relevance_score=0.9, title="SOP-003")
        mock_hybrid_query_engine.search.return_value = HybridSearchResponse(
            results=[result1], total_count=1, page=1, page_size=10
        )

        # Initial attempt fails, first retry succeeds
        mock_inference_client.chat_completion.side_effect = [
            RuntimeError("LLM overloaded"),  # initial fail
            valid_contradiction_json,  # retry 1: success
        ]

        result = await service.analyze_record(record_id=1, company_id=42)

        assert result["contradiction_count"] == 1
        assert result["alerts_created"] == 1


# ---------------------------------------------------------------------------
# Tests: classify_priority helper
# ---------------------------------------------------------------------------


class TestClassifyPriority:
    """Tests for the classify_priority pure function."""

    def test_score_at_threshold_is_high_priority(self):
        """Relevance score exactly 0.8 is high priority."""
        assert classify_priority(0.8) is True

    def test_score_above_threshold_is_high_priority(self):
        """Relevance score above 0.8 is high priority."""
        assert classify_priority(0.95) is True

    def test_score_below_threshold_is_not_high_priority(self):
        """Relevance score below 0.8 is not high priority."""
        assert classify_priority(0.79) is False

    def test_zero_score_is_not_high_priority(self):
        """Zero relevance score is not high priority."""
        assert classify_priority(0.0) is False
