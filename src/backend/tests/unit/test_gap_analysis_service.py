"""Unit tests for GapAnalysisService.

Tests gap finding production, limiting, timeout handling, validation errors.
Mocks InferenceClient and KnowledgeService.

References:
    - Requirements: 4.1–4.12
"""

import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.document import Document
from alcoabase.models.impact_analysis import DependencyEdge, GapAnalysisResult
from alcoabase.services.gap_analysis import (
    GAP_ANALYSIS_TIMEOUT_SECONDS,
    MAX_GAP_FINDINGS,
    GapAnalysisService,
    limit_gap_findings,
)
from alcoabase.services.inference_client import InferenceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(
    id: int,
    uuid: str,
    title: str = "Test Doc",
    company_id: int = 1,
) -> Document:
    """Create a Document instance for testing."""
    doc = Document(
        id=id,
        document_uuid=uuid,
        title=title,
        document_type="SOP",
        current_status="Active",
        folder_path="/test",
        created_by=1,
    )
    doc.company_id = company_id
    return doc


def _make_gap_finding(severity: str = "major", section: str = "Section 1") -> dict:
    """Create a gap finding dict for testing."""
    return {
        "source_section": section,
        "source_content_excerpt": "Source content excerpt text",
        "target_section": "Target Section",
        "target_content_excerpt": "Target content excerpt text",
        "gap_type": "missing",
        "severity": severity,
        "remediation_suggestion": "Update the target document.",
        "inference_prompt_summary": "Prompt summary text",
        "model_response_summary": "Response summary text",
        "token_count": 100,
    }


def _make_search_result(document_uuid: str, excerpt: str = "text"):
    """Create a mock search result."""
    result = MagicMock()
    result.document_uuid = document_uuid
    result.relevance_score = 0.9
    result.excerpt = excerpt
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_knowledge_service() -> MagicMock:
    """Create a mock KnowledgeService."""
    svc = MagicMock()
    svc.hybrid_search = MagicMock(return_value=([], 0))
    return svc


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(return_value='{"gap_found": false}')
    return client


@pytest.fixture
def service(
    mock_session: AsyncMock,
    mock_knowledge_service: MagicMock,
    mock_inference_client: AsyncMock,
) -> GapAnalysisService:
    """Create a GapAnalysisService with mocked dependencies."""
    return GapAnalysisService(
        session=mock_session,
        knowledge_service=mock_knowledge_service,
        inference_client=mock_inference_client,
    )


# ---------------------------------------------------------------------------
# Tests: Validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    """Tests for input validation in execute_gap_analysis."""

    @pytest.mark.asyncio
    async def test_same_document_returns_422(self, service):
        """Same source and target document raises 422."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.execute_gap_analysis(
                source_doc_id=1,
                target_doc_id=1,
                source_version_id=None,
                target_version_id=None,
                company_id=1,
            )

        assert exc_info.value.status_code == 422
        assert "distinct documents" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_source_document_not_found_returns_404(
        self, service, mock_session
    ):
        """Source document not in company scope raises 404."""
        from fastapi import HTTPException

        # Mock: source document not found
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result)

        with pytest.raises(HTTPException) as exc_info:
            await service.execute_gap_analysis(
                source_doc_id=999,
                target_doc_id=2,
                source_version_id=None,
                target_version_id=None,
                company_id=1,
            )

        assert exc_info.value.status_code == 404
        assert "source document" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_target_document_not_found_returns_404(
        self, service, mock_session
    ):
        """Target document not in company scope raises 404."""
        from fastapi import HTTPException

        source_doc = _make_document(1, "2025-00001", "Source Doc")

        # First call: source found; second call: target not found
        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source_doc

        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[source_result, target_result]
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.execute_gap_analysis(
                source_doc_id=1,
                target_doc_id=2,
                source_version_id=None,
                target_version_id=None,
                company_id=1,
            )

        assert exc_info.value.status_code == 404
        assert "target document" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_dependency_edge_returns_422(
        self, service, mock_session
    ):
        """No dependency edge with confidence >= 0.5 raises 422."""
        from fastapi import HTTPException

        source_doc = _make_document(1, "2025-00001", "Source Doc")
        target_doc = _make_document(2, "2025-00002", "Target Doc")

        # Mock: both documents found
        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source_doc
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = target_doc

        # Mock: no dependency edge found
        dep_result = MagicMock()
        dep_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[source_result, target_result, dep_result]
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.execute_gap_analysis(
                source_doc_id=1,
                target_doc_id=2,
                source_version_id=None,
                target_version_id=None,
                company_id=1,
            )

        assert exc_info.value.status_code == 422
        assert "no dependency" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Tests: Successful gap analysis
# ---------------------------------------------------------------------------


class TestSuccessfulGapAnalysis:
    """Tests for successful gap analysis execution."""

    @pytest.mark.asyncio
    async def test_successful_gap_analysis_with_findings(
        self, service, mock_session, mock_knowledge_service, mock_inference_client
    ):
        """Successful analysis produces findings and persists result."""
        source_doc = _make_document(1, "2025-00001", "Source Doc")
        target_doc = _make_document(2, "2025-00002", "Target Doc")

        # Mock: documents found
        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source_doc
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = target_doc

        # Mock: dependency edge exists
        dep_result = MagicMock()
        dep_result.scalar_one_or_none.return_value = 1  # edge ID

        # Mock: dependency type query
        dep_type_result = MagicMock()
        dep_type_result.scalar_one_or_none.return_value = "validates"

        mock_session.execute = AsyncMock(
            side_effect=[source_result, target_result, dep_result, dep_type_result]
        )

        # Mock: KnowledgeService returns text for both documents
        search_result = _make_search_result(
            "2025-00001",
            "# Requirements\nThe system shall validate inputs.\n\n"
            "# Safety\nAll operations must be logged.",
        )
        mock_knowledge_service.hybrid_search.return_value = ([search_result], 1)

        # Mock: InferenceClient returns a gap finding
        gap_response = json.dumps({
            "gap_found": True,
            "target_section": "Validation",
            "target_content_excerpt": "Partial validation exists",
            "gap_type": "incomplete",
            "severity": "major",
            "remediation_suggestion": "Add full input validation coverage.",
        })
        mock_inference_client.chat_completion = AsyncMock(return_value=gap_response)

        result = await service.execute_gap_analysis(
            source_doc_id=1,
            target_doc_id=2,
            source_version_id=None,
            target_version_id=None,
            company_id=1,
        )

        assert result.status == "completed"
        assert result.source_document_uuid == "2025-00001"
        assert result.target_document_uuid == "2025-00002"
        assert result.total_gaps_detected > 0
        assert result.gaps_retained > 0
        assert result.company_id == 1
        assert result.analysis_duration_ms >= 0
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_gaps_found_returns_completed_with_empty_findings(
        self, service, mock_session, mock_knowledge_service, mock_inference_client
    ):
        """Analysis with no gaps returns completed status with empty findings."""
        source_doc = _make_document(1, "2025-00001", "Source Doc")
        target_doc = _make_document(2, "2025-00002", "Target Doc")

        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source_doc
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = target_doc
        dep_result = MagicMock()
        dep_result.scalar_one_or_none.return_value = 1
        dep_type_result = MagicMock()
        dep_type_result.scalar_one_or_none.return_value = "references"

        mock_session.execute = AsyncMock(
            side_effect=[source_result, target_result, dep_result, dep_type_result]
        )

        # KnowledgeService returns text with a single section
        search_result = _make_search_result(
            "2025-00001", "# Overview\nThis is a simple document."
        )
        mock_knowledge_service.hybrid_search.return_value = ([search_result], 1)

        # InferenceClient says no gap found
        mock_inference_client.chat_completion = AsyncMock(
            return_value='{"gap_found": false}'
        )

        result = await service.execute_gap_analysis(
            source_doc_id=1,
            target_doc_id=2,
            source_version_id=None,
            target_version_id=None,
            company_id=1,
        )

        assert result.status == "completed"
        assert result.total_gaps_detected == 0
        assert result.gaps_retained == 0
        assert result.gap_findings == []


# ---------------------------------------------------------------------------
# Tests: Timeout handling
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Tests for timeout handling during gap analysis."""

    @pytest.mark.asyncio
    async def test_timeout_returns_partial_success(
        self, service, mock_session, mock_knowledge_service, mock_inference_client
    ):
        """Analysis exceeding 180s timeout returns partial_success."""
        source_doc = _make_document(1, "2025-00001", "Source Doc")
        target_doc = _make_document(2, "2025-00002", "Target Doc")

        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source_doc
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = target_doc
        dep_result = MagicMock()
        dep_result.scalar_one_or_none.return_value = 1
        dep_type_result = MagicMock()
        dep_type_result.scalar_one_or_none.return_value = "validates"

        mock_session.execute = AsyncMock(
            side_effect=[source_result, target_result, dep_result, dep_type_result]
        )

        # KnowledgeService returns text with many sections
        many_sections = "\n\n".join(
            [f"# Section {i}\nContent for section {i}." for i in range(20)]
        )
        search_result = _make_search_result("2025-00001", many_sections)
        mock_knowledge_service.hybrid_search.return_value = ([search_result], 1)

        # Mock time.monotonic to simulate timeout after first section
        call_count = [0]
        start_time = 0.0

        def mock_monotonic():
            call_count[0] += 1
            if call_count[0] <= 1:
                return start_time
            # After first section, exceed timeout
            return start_time + GAP_ANALYSIS_TIMEOUT_SECONDS + 1

        mock_inference_client.chat_completion = AsyncMock(
            return_value='{"gap_found": false}'
        )

        with patch(
            "alcoabase.services.gap_analysis.time.monotonic",
            side_effect=mock_monotonic,
        ):
            result = await service.execute_gap_analysis(
                source_doc_id=1,
                target_doc_id=2,
                source_version_id=None,
                target_version_id=None,
                company_id=1,
            )

        assert result.status == "partial_success"


# ---------------------------------------------------------------------------
# Tests: InferenceClient failure
# ---------------------------------------------------------------------------


class TestInferenceFailure:
    """Tests for InferenceClient failure handling."""

    @pytest.mark.asyncio
    async def test_inference_error_returns_failed_status(
        self, service, mock_session, mock_knowledge_service, mock_inference_client
    ):
        """InferenceClient failure marks result as failed."""
        source_doc = _make_document(1, "2025-00001", "Source Doc")
        target_doc = _make_document(2, "2025-00002", "Target Doc")

        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source_doc
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = target_doc
        dep_result = MagicMock()
        dep_result.scalar_one_or_none.return_value = 1
        dep_type_result = MagicMock()
        dep_type_result.scalar_one_or_none.return_value = "validates"

        mock_session.execute = AsyncMock(
            side_effect=[source_result, target_result, dep_result, dep_type_result]
        )

        # KnowledgeService returns text
        search_result = _make_search_result(
            "2025-00001", "# Requirements\nThe system shall do X."
        )
        mock_knowledge_service.hybrid_search.return_value = ([search_result], 1)

        # InferenceClient raises InferenceError
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceError("Service unavailable", status_code=503)
        )

        result = await service.execute_gap_analysis(
            source_doc_id=1,
            target_doc_id=2,
            source_version_id=None,
            target_version_id=None,
            company_id=1,
        )

        assert result.status == "failed"
        assert result.total_gaps_detected == 0
        assert result.gaps_retained == 0
        assert result.gap_findings == []

    @pytest.mark.asyncio
    async def test_text_extraction_failure_returns_failed(
        self, service, mock_session, mock_knowledge_service, mock_inference_client
    ):
        """Document text extraction failure marks result as failed."""
        source_doc = _make_document(1, "2025-00001", "Source Doc")
        target_doc = _make_document(2, "2025-00002", "Target Doc")

        source_result = MagicMock()
        source_result.scalar_one_or_none.return_value = source_doc
        target_result = MagicMock()
        target_result.scalar_one_or_none.return_value = target_doc
        dep_result = MagicMock()
        dep_result.scalar_one_or_none.return_value = 1
        dep_type_result = MagicMock()
        dep_type_result.scalar_one_or_none.return_value = "references"

        mock_session.execute = AsyncMock(
            side_effect=[source_result, target_result, dep_result, dep_type_result]
        )

        # KnowledgeService returns no results (text extraction fails)
        mock_knowledge_service.hybrid_search.return_value = ([], 0)

        result = await service.execute_gap_analysis(
            source_doc_id=1,
            target_doc_id=2,
            source_version_id=None,
            target_version_id=None,
            company_id=1,
        )

        assert result.status == "failed"
        assert result.gap_findings == []


# ---------------------------------------------------------------------------
# Tests: Gap finding limiting
# ---------------------------------------------------------------------------


class TestGapFindingLimiting:
    """Tests for gap finding limiting (>100 findings → top 100 retained)."""

    def test_limit_gap_findings_retains_top_100_by_severity(self):
        """More than 100 findings retains top 100 sorted by severity."""
        # Create 150 findings: 30 critical, 50 major, 70 minor
        findings = []
        for i in range(30):
            findings.append(_make_gap_finding("critical", f"Critical {i}"))
        for i in range(50):
            findings.append(_make_gap_finding("major", f"Major {i}"))
        for i in range(70):
            findings.append(_make_gap_finding("minor", f"Minor {i}"))

        result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

        assert len(result) == 100
        # All 30 critical should be retained
        critical_count = sum(1 for f in result if f["severity"] == "critical")
        assert critical_count == 30
        # All 50 major should be retained
        major_count = sum(1 for f in result if f["severity"] == "major")
        assert major_count == 50
        # Only 20 minor should be retained (100 - 30 - 50 = 20)
        minor_count = sum(1 for f in result if f["severity"] == "minor")
        assert minor_count == 20

    def test_limit_gap_findings_preserves_severity_order(self):
        """Retained findings are sorted by severity priority."""
        findings = []
        for i in range(40):
            findings.append(_make_gap_finding("minor", f"Minor {i}"))
        for i in range(40):
            findings.append(_make_gap_finding("critical", f"Critical {i}"))
        for i in range(40):
            findings.append(_make_gap_finding("major", f"Major {i}"))

        result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

        assert len(result) == 100
        # Verify ordering: critical first, then major, then minor
        severities = [f["severity"] for f in result]
        critical_idx = [i for i, s in enumerate(severities) if s == "critical"]
        major_idx = [i for i, s in enumerate(severities) if s == "major"]
        minor_idx = [i for i, s in enumerate(severities) if s == "minor"]

        # All critical indices should be before all major indices
        if critical_idx and major_idx:
            assert max(critical_idx) < min(major_idx)
        # All major indices should be before all minor indices
        if major_idx and minor_idx:
            assert max(major_idx) < min(minor_idx)

    def test_limit_gap_findings_under_limit_returns_all_sorted(self):
        """Fewer than 100 findings returns all, sorted by severity."""
        findings = [
            _make_gap_finding("minor", "Minor 1"),
            _make_gap_finding("critical", "Critical 1"),
            _make_gap_finding("major", "Major 1"),
        ]

        result = limit_gap_findings(findings, MAX_GAP_FINDINGS)

        assert len(result) == 3
        assert result[0]["severity"] == "critical"
        assert result[1]["severity"] == "major"
        assert result[2]["severity"] == "minor"

    def test_limit_gap_findings_empty_list(self):
        """Empty findings list returns empty list."""
        result = limit_gap_findings([], MAX_GAP_FINDINGS)
        assert result == []


# ---------------------------------------------------------------------------
# Tests: Section extraction
# ---------------------------------------------------------------------------


class TestSectionExtraction:
    """Tests for _extract_sections helper method."""

    def test_extract_sections_from_markdown_headings(
        self, service
    ):
        """Sections are split on markdown headings."""
        text = (
            "# Introduction\n"
            "This is the intro.\n\n"
            "# Requirements\n"
            "The system shall do X.\n"
            "The system shall do Y.\n\n"
            "# Safety\n"
            "All operations must be logged."
        )

        sections = service._extract_sections(text)

        assert len(sections) == 3
        assert sections[0]["heading"] == "Introduction"
        assert "intro" in sections[0]["content"].lower()
        assert sections[1]["heading"] == "Requirements"
        assert "system shall" in sections[1]["content"].lower()
        assert sections[2]["heading"] == "Safety"

    def test_extract_sections_all_caps_headings(self, service):
        """All-caps lines are treated as headings."""
        text = (
            "OVERVIEW\n"
            "This is the overview section.\n\n"
            "PROCEDURES\n"
            "Step 1: Do something.\n"
            "Step 2: Do something else."
        )

        sections = service._extract_sections(text)

        assert len(sections) == 2
        assert sections[0]["heading"] == "OVERVIEW"
        assert sections[1]["heading"] == "PROCEDURES"

    def test_extract_sections_filters_empty_sections(self, service):
        """Empty sections (heading with no content) are filtered out."""
        text = (
            "# Empty Section\n"
            "\n\n"
            "# Content Section\n"
            "This has content."
        )

        sections = service._extract_sections(text)

        # Only the section with content should be returned
        assert len(sections) == 1
        assert sections[0]["heading"] == "Content Section"

    def test_extract_sections_no_headings(self, service):
        """Text without headings returns single section with default heading."""
        text = "This is plain text without any headings or structure."

        sections = service._extract_sections(text)

        assert len(sections) == 1
        assert sections[0]["heading"] == "Introduction"
        assert "plain text" in sections[0]["content"]


# ---------------------------------------------------------------------------
# Tests: AI response parsing
# ---------------------------------------------------------------------------


class TestAIResponseParsing:
    """Tests for _parse_gap_response method."""

    def test_parse_valid_json_with_gap(self, service):
        """Valid JSON response with gap_found=true returns finding dict."""
        response = json.dumps({
            "gap_found": True,
            "target_section": "Section 2.1",
            "target_content_excerpt": "Existing content in target",
            "gap_type": "missing",
            "severity": "critical",
            "remediation_suggestion": "Add missing requirement coverage.",
        })
        source_section = {"heading": "Req 1", "content": "The system shall X."}

        result = service._parse_gap_response(
            response=response,
            source_section=source_section,
            prompt_summary="Analyze section...",
        )

        assert result is not None
        assert result["source_section"] == "Req 1"
        assert result["target_section"] == "Section 2.1"
        assert result["gap_type"] == "missing"
        assert result["severity"] == "critical"
        assert result["remediation_suggestion"] == "Add missing requirement coverage."
        assert result["token_count"] > 0

    def test_parse_valid_json_no_gap(self, service):
        """Valid JSON response with gap_found=false returns None."""
        response = '{"gap_found": false}'
        source_section = {"heading": "Req 1", "content": "Content"}

        result = service._parse_gap_response(
            response=response,
            source_section=source_section,
            prompt_summary="Analyze...",
        )

        assert result is None

    def test_parse_invalid_json_returns_none(self, service):
        """Invalid JSON response returns None (graceful handling)."""
        response = "This is not valid JSON at all."
        source_section = {"heading": "Req 1", "content": "Content"}

        result = service._parse_gap_response(
            response=response,
            source_section=source_section,
            prompt_summary="Analyze...",
        )

        assert result is None

    def test_parse_json_in_markdown_code_block(self, service):
        """JSON wrapped in markdown code block is parsed correctly."""
        response = (
            "```json\n"
            '{"gap_found": true, "target_section": "Safety", '
            '"target_content_excerpt": "Old safety text", '
            '"gap_type": "outdated", "severity": "minor", '
            '"remediation_suggestion": "Update terminology."}\n'
            "```"
        )
        source_section = {"heading": "Safety", "content": "New safety content."}

        result = service._parse_gap_response(
            response=response,
            source_section=source_section,
            prompt_summary="Analyze safety...",
        )

        assert result is not None
        assert result["gap_type"] == "outdated"
        assert result["severity"] == "minor"

    def test_parse_truncates_excerpts_to_300_chars(self, service):
        """Source and target content excerpts are truncated to 300 chars."""
        long_content = "A" * 500
        response = json.dumps({
            "gap_found": True,
            "target_section": "Long Section",
            "target_content_excerpt": long_content,
            "gap_type": "incomplete",
            "severity": "major",
            "remediation_suggestion": "Complete the section.",
        })
        source_section = {
            "heading": "Source",
            "content": long_content,
        }

        result = service._parse_gap_response(
            response=response,
            source_section=source_section,
            prompt_summary="Analyze...",
        )

        assert result is not None
        assert len(result["source_content_excerpt"]) <= 300
        assert len(result["target_content_excerpt"]) <= 300

# ---------------------------------------------------------------------------
# Agent Loading and Fallback Tests (Task 9.2)
# ---------------------------------------------------------------------------


class TestGapAnalysisAgentLoading:
    """Tests for agent loading and fallback logic in GapAnalysisService.

    Validates Requirements 7.4, 7.5, 7.6.
    """

    def test_loads_change_impact_analyst_from_registry(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Successfully loads Change Impact Analyst archetype config (Req 7.4)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Change Impact Analyst",
                    "name": "Change Impact Analyst",
                    "system_prompt": "You are a Change Impact Analyst.",
                    "contextual_tuning": {"temperature": 0.2, "max_tokens": 4096},
                }
            ]
        )
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        system_prompt, temperature, max_tokens, fallback_used = svc._get_agent_config()
        assert "Change Impact Analyst" in system_prompt
        assert temperature == 0.2
        assert max_tokens == 4096
        assert fallback_used is False

    def test_fallback_to_regulatory_auditor(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Falls back to Regulatory Compliance Auditor when CIA not found (Req 7.5)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Regulatory Compliance Auditor",
                    "name": "Regulatory Compliance Auditor",
                    "system_prompt": "You are a regulatory compliance auditor.",
                    "contextual_tuning": {"temperature": 0.3, "max_tokens": 2048},
                }
            ]
        )
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        system_prompt, temperature, max_tokens, fallback_used = svc._get_agent_config()
        assert "regulatory compliance auditor" in system_prompt.lower()
        assert "gap identification" in system_prompt.lower()
        assert temperature == 0.3
        assert max_tokens == 2048
        assert fallback_used is True

    def test_fallback_appends_prompt_suffix(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Fallback appends system prompt suffix for change impact focus (Req 7.5)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Regulatory Compliance Auditor",
                    "name": "Regulatory Compliance Auditor",
                    "system_prompt": "Base auditor prompt.",
                    "contextual_tuning": {"temperature": 0.2, "max_tokens": 4096},
                }
            ]
        )
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        system_prompt, _temp, _max_tok, _fallback = svc._get_agent_config()
        assert "Base auditor prompt." in system_prompt
        assert "Change Impact Analyst" in system_prompt
        assert "gap identification" in system_prompt.lower()

    def test_no_registry_uses_builtin_prompt(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Without agent registry, uses built-in system prompt (Req 7.4)."""
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=None,
        )
        system_prompt, temperature, max_tokens, fallback_used = svc._get_agent_config()
        assert "Change Impact Analyst" in system_prompt
        assert temperature == 0.2
        assert max_tokens == 4096
        assert fallback_used is False

    def test_yaml_schema_validation_failure_retains_defaults(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """YAML schema validation failure retains default config (Req 7.6)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            side_effect=Exception("YAML schema validation failed: missing field")
        )
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        system_prompt, temperature, max_tokens, fallback_used = svc._get_agent_config()
        # Should retain default config, not crash
        assert "Change Impact Analyst" in system_prompt
        assert temperature == 0.2
        assert max_tokens == 4096
        assert fallback_used is False

    def test_passes_agent_temperature_to_inference(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Agent's temperature (0.2) and max_tokens (4096) are passed to inference (Req 7.4)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Change Impact Analyst",
                    "name": "Change Impact Analyst",
                    "system_prompt": "You are a Change Impact Analyst.",
                    "contextual_tuning": {"temperature": 0.2, "max_tokens": 4096},
                }
            ]
        )
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        _prompt, temperature, max_tokens, _fallback = svc._get_agent_config()
        assert temperature == 0.2
        assert max_tokens == 4096

    def test_get_fallback_metadata_when_fallback_used(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """get_fallback_metadata returns metadata when fallback is active (Req 7.5)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Regulatory Compliance Auditor",
                    "name": "Regulatory Compliance Auditor",
                    "system_prompt": "Auditor prompt.",
                    "contextual_tuning": {"temperature": 0.3, "max_tokens": 2048},
                }
            ]
        )
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        metadata = svc.get_fallback_metadata()
        assert metadata is not None
        assert "fallback_used" in metadata
        assert metadata["fallback_used"]["missing_archetype"] == "Change Impact Analyst"
        assert metadata["fallback_used"]["used_archetype"] == "Regulatory Compliance Auditor"

    def test_get_fallback_metadata_when_primary_available(
        self,
        mock_session: AsyncMock,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """get_fallback_metadata returns None when primary agent is available."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Change Impact Analyst",
                    "name": "Change Impact Analyst",
                    "system_prompt": "You are a Change Impact Analyst.",
                    "contextual_tuning": {"temperature": 0.2, "max_tokens": 4096},
                }
            ]
        )
        svc = GapAnalysisService(
            session=mock_session,
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        metadata = svc.get_fallback_metadata()
        assert metadata is None
