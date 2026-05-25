"""Unit tests for ImpactAnalysisService change delta computation.

Tests the compute_change_delta function including section parsing,
section-level diff, significance classification, and first-version handling.

References:
    - Requirements 2.6: Change delta computation
    - Requirements 2.8: First-version handling
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.schemas.impact_analysis import ChangeDeltaSchema
from alcoabase.services.impact_analysis import ImpactAnalysisService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_knowledge_service() -> MagicMock:
    """Create a mock KnowledgeService."""
    ks = MagicMock()
    ks.hybrid_search = MagicMock(return_value=([], 0))
    return ks


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(
        return_value=json.dumps(
            {
                "classifications": [
                    {"section_title": "Test", "significance": "high", "reason": "safety"}
                ]
            }
        )
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
                "name": "Change Impact Analyst",
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
# Section Parsing Tests
# ---------------------------------------------------------------------------


class TestParseSections:
    """Tests for _parse_sections method."""

    def test_empty_text(self, service: ImpactAnalysisService) -> None:
        """Empty text returns empty sections dict."""
        result = service._parse_sections("")
        assert result == {}

    def test_whitespace_only(self, service: ImpactAnalysisService) -> None:
        """Whitespace-only text returns empty sections dict."""
        result = service._parse_sections("   \n  \n  ")
        assert result == {}

    def test_no_headings(self, service: ImpactAnalysisService) -> None:
        """Text without headings is treated as a single [Document Body] section."""
        text = "This is some plain text without any headings."
        result = service._parse_sections(text)
        assert "[Document Body]" in result
        assert result["[Document Body]"] == text.strip()

    def test_markdown_headings(self, service: ImpactAnalysisService) -> None:
        """Markdown headings are correctly parsed."""
        text = "# Introduction\nThis is the intro.\n\n# Methods\nThis is methods."
        result = service._parse_sections(text)
        assert "Introduction" in result
        assert "Methods" in result
        assert "intro" in result["Introduction"]
        assert "methods" in result["Methods"]

    def test_numbered_headings(self, service: ImpactAnalysisService) -> None:
        """Numbered headings (e.g., '1.2 Title') are correctly parsed."""
        text = "1.1 Purpose\nThe purpose is...\n\n1.2 Scope\nThe scope is..."
        result = service._parse_sections(text)
        assert "1.1 Purpose" in result
        assert "1.2 Scope" in result

    def test_preamble_before_first_heading(self, service: ImpactAnalysisService) -> None:
        """Content before the first heading is captured as [Preamble]."""
        text = "Some preamble text.\n\n# First Section\nSection content."
        result = service._parse_sections(text)
        assert "[Preamble]" in result
        assert "preamble" in result["[Preamble]"]
        assert "First Section" in result


# ---------------------------------------------------------------------------
# Section Diff Tests
# ---------------------------------------------------------------------------


class TestComputeSectionDiff:
    """Tests for _compute_section_diff method."""

    def test_identical_sections(self, service: ImpactAnalysisService) -> None:
        """Identical sections produce no changes."""
        old = {"Section A": "content a", "Section B": "content b"}
        new = {"Section A": "content a", "Section B": "content b"}
        added, modified, deleted = service._compute_section_diff(old, new)
        assert added == []
        assert modified == []
        assert deleted == []

    def test_added_sections(self, service: ImpactAnalysisService) -> None:
        """New sections are correctly identified as added."""
        old = {"Section A": "content a"}
        new = {"Section A": "content a", "Section B": "content b"}
        added, modified, deleted = service._compute_section_diff(old, new)
        assert len(added) == 1
        assert added[0]["title"] == "Section B"
        assert added[0]["content"] == "content b"
        assert modified == []
        assert deleted == []

    def test_deleted_sections(self, service: ImpactAnalysisService) -> None:
        """Removed sections are correctly identified as deleted."""
        old = {"Section A": "content a", "Section B": "content b"}
        new = {"Section A": "content a"}
        added, modified, deleted = service._compute_section_diff(old, new)
        assert added == []
        assert modified == []
        assert len(deleted) == 1
        assert deleted[0]["title"] == "Section B"

    def test_modified_sections(self, service: ImpactAnalysisService) -> None:
        """Sections with changed content are correctly identified as modified."""
        old = {"Section A": "old content"}
        new = {"Section A": "new content"}
        added, modified, deleted = service._compute_section_diff(old, new)
        assert added == []
        assert len(modified) == 1
        assert modified[0]["title"] == "Section A"
        assert modified[0]["content"] == "new content"
        assert modified[0]["previous_content"] == "old content"
        assert deleted == []

    def test_mixed_changes(self, service: ImpactAnalysisService) -> None:
        """Combination of added, modified, and deleted sections."""
        old = {"Keep": "same", "Modify": "old", "Delete": "gone"}
        new = {"Keep": "same", "Modify": "new", "Add": "fresh"}
        added, modified, deleted = service._compute_section_diff(old, new)
        assert len(added) == 1
        assert added[0]["title"] == "Add"
        assert len(modified) == 1
        assert modified[0]["title"] == "Modify"
        assert len(deleted) == 1
        assert deleted[0]["title"] == "Delete"


# ---------------------------------------------------------------------------
# First Version Handling Tests
# ---------------------------------------------------------------------------


class TestFirstVersionHandling:
    """Tests for first-version case (Requirement 2.8)."""

    @pytest.mark.asyncio
    async def test_first_version_no_previous_id(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock
    ) -> None:
        """When previous_version_id is None, all content is treated as new."""
        # Mock knowledge service to return document text
        mock_result = MagicMock()
        mock_result.excerpt = "# Safety\nWear PPE at all times."
        mock_knowledge_service.hybrid_search.return_value = ([mock_result], 1)

        result = await service.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=1,
            previous_version_id=None,
            company_id=1,
        )

        assert isinstance(result, ChangeDeltaSchema)
        assert len(result.sections_added) > 0
        assert result.sections_modified == []
        assert result.sections_deleted == []
        assert result.metadata.get("first_version") is True

    @pytest.mark.asyncio
    async def test_first_version_empty_content(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock
    ) -> None:
        """When first version has no content, returns empty delta."""
        mock_knowledge_service.hybrid_search.return_value = ([], 0)

        result = await service.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=1,
            previous_version_id=None,
            company_id=1,
        )

        assert isinstance(result, ChangeDeltaSchema)
        assert result.sections_added == []
        assert result.sections_modified == []
        assert result.sections_deleted == []
        assert result.metadata.get("first_version") is True
        assert result.metadata.get("empty_content") is True

    @pytest.mark.asyncio
    async def test_previous_version_not_found(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock
    ) -> None:
        """When previous version text cannot be retrieved, treat as first version."""
        # First call returns new version text, second returns nothing
        mock_result = MagicMock()
        mock_result.excerpt = "# Overview\nNew content here."
        mock_knowledge_service.hybrid_search.side_effect = [
            ([mock_result], 1),  # new version
            ([], 0),  # previous version not found
        ]

        result = await service.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=2,
            previous_version_id=1,
            company_id=1,
        )

        assert isinstance(result, ChangeDeltaSchema)
        assert result.metadata.get("first_version") is True


# ---------------------------------------------------------------------------
# Change Delta Computation Tests
# ---------------------------------------------------------------------------


class TestComputeChangeDelta:
    """Tests for the full compute_change_delta pipeline."""

    @pytest.mark.asyncio
    async def test_normal_delta_computation(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock
    ) -> None:
        """Normal case: computes diff between two versions."""
        old_result = MagicMock()
        old_result.excerpt = "# Introduction\nOld intro.\n\n# Methods\nOld methods."
        new_result = MagicMock()
        new_result.excerpt = "# Introduction\nNew intro.\n\n# Results\nNew results."

        mock_knowledge_service.hybrid_search.side_effect = [
            ([new_result], 1),  # new version
            ([old_result], 1),  # previous version
        ]

        result = await service.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=2,
            previous_version_id=1,
            company_id=1,
        )

        assert isinstance(result, ChangeDeltaSchema)
        # "Results" is added, "Introduction" is modified, "Methods" is deleted
        added_titles = [s["title"] for s in result.sections_added]
        modified_titles = [s["title"] for s in result.sections_modified]
        deleted_titles = [s["title"] for s in result.sections_deleted]

        assert "Results" in added_titles
        assert "Introduction" in modified_titles
        assert "Methods" in deleted_titles

    @pytest.mark.asyncio
    async def test_significance_levels_populated(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock
    ) -> None:
        """Significance levels are populated in the result."""
        old_result = MagicMock()
        old_result.excerpt = "# Safety\nOld safety content."
        new_result = MagicMock()
        new_result.excerpt = "# Safety\nNew safety content with PPE requirements."

        mock_knowledge_service.hybrid_search.side_effect = [
            ([new_result], 1),
            ([old_result], 1),
        ]

        result = await service.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=2,
            previous_version_id=1,
            company_id=1,
        )

        assert "high" in result.significance_levels
        assert "medium" in result.significance_levels
        assert "low" in result.significance_levels
        total = sum(result.significance_levels.values())
        assert total > 0  # At least one change classified


# ---------------------------------------------------------------------------
# Significance Classification Tests
# ---------------------------------------------------------------------------


class TestSignificanceClassification:
    """Tests for significance classification logic."""

    def test_heuristic_high_keywords(self, service: ImpactAnalysisService) -> None:
        """Heuristic classifies safety-related changes as high."""
        changes = [
            {"title": "Safety Procedures", "content": "Wear PPE at all times."},
            {"title": "Regulatory Requirements", "content": "Must comply with FDA."},
        ]
        result = service._classify_heuristic(changes)
        assert result["high"] == 2

    def test_heuristic_low_keywords(self, service: ImpactAnalysisService) -> None:
        """Heuristic classifies formatting changes as low."""
        changes = [
            {"title": "Formatting", "content": "Fixed typo in header."},
            {"title": "Style Guide", "content": "Updated font size."},
        ]
        result = service._classify_heuristic(changes)
        assert result["low"] == 2

    def test_heuristic_medium_default(self, service: ImpactAnalysisService) -> None:
        """Heuristic classifies unmatched changes as medium."""
        changes = [
            {"title": "Background", "content": "General information about the project."},
        ]
        result = service._classify_heuristic(changes)
        assert result["medium"] == 1

    def test_parse_significance_response_valid_json(
        self, service: ImpactAnalysisService
    ) -> None:
        """Valid JSON response is correctly parsed."""
        response = json.dumps(
            {
                "classifications": [
                    {"section_title": "A", "significance": "high", "reason": "safety"},
                    {"section_title": "B", "significance": "low", "reason": "typo"},
                    {"section_title": "C", "significance": "medium", "reason": "desc"},
                ]
            }
        )
        result = service._parse_significance_response(response, 3)
        assert result == {"high": 1, "medium": 1, "low": 1}

    def test_parse_significance_response_with_code_block(
        self, service: ImpactAnalysisService
    ) -> None:
        """JSON wrapped in markdown code block is correctly parsed."""
        response = '```json\n{"classifications": [{"section_title": "A", "significance": "high", "reason": "x"}]}\n```'
        result = service._parse_significance_response(response, 1)
        assert result == {"high": 1, "medium": 0, "low": 0}

    def test_parse_significance_response_invalid_json(
        self, service: ImpactAnalysisService
    ) -> None:
        """Invalid JSON falls back to medium classification."""
        response = "This is not valid JSON at all."
        result = service._parse_significance_response(response, 3)
        assert result == {"high": 0, "medium": 3, "low": 0}

    def test_parse_significance_response_partial(
        self, service: ImpactAnalysisService
    ) -> None:
        """Partial classifications assign remainder as medium."""
        response = json.dumps(
            {
                "classifications": [
                    {"section_title": "A", "significance": "high", "reason": "x"},
                ]
            }
        )
        result = service._parse_significance_response(response, 3)
        assert result == {"high": 1, "medium": 2, "low": 0}


# ---------------------------------------------------------------------------
# Agent Config Tests
# ---------------------------------------------------------------------------


class TestAgentConfig:
    """Tests for agent configuration loading."""

    def test_loads_change_impact_analyst(
        self, service: ImpactAnalysisService
    ) -> None:
        """Successfully loads Change Impact Analyst archetype config."""
        system_prompt, temperature, max_tokens, fallback_used = service._get_agent_config()
        assert "Change Impact Analyst" in system_prompt
        assert temperature == 0.2
        assert max_tokens == 4096
        assert fallback_used is False

    def test_fallback_to_regulatory_auditor(
        self, mock_knowledge_service: MagicMock, mock_inference_client: AsyncMock
    ) -> None:
        """Falls back to Regulatory Compliance Auditor when CIA not found."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Regulatory Compliance Auditor",
                    "name": "Regulatory Compliance Auditor",
                    "system_prompt": "You are a regulatory auditor.",
                    "contextual_tuning": {"temperature": 0.3, "max_tokens": 2048},
                }
            ]
        )
        svc = ImpactAnalysisService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        system_prompt, temperature, max_tokens, fallback_used = svc._get_agent_config()
        assert "regulatory auditor" in system_prompt.lower()
        assert "Change Impact Analyst" in system_prompt
        assert temperature == 0.3
        assert fallback_used is True

    def test_no_registry_uses_defaults(
        self, mock_knowledge_service: MagicMock, mock_inference_client: AsyncMock
    ) -> None:
        """Without agent registry, uses default config."""
        svc = ImpactAnalysisService(
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
        self, mock_knowledge_service: MagicMock, mock_inference_client: AsyncMock
    ) -> None:
        """YAML schema validation failure retains default config (Req 7.6)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            side_effect=Exception("YAML schema validation failed: missing field 'system_prompt'")
        )
        svc = ImpactAnalysisService(
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

    def test_fallback_records_metadata_in_change_delta(
        self, mock_knowledge_service: MagicMock, mock_inference_client: AsyncMock
    ) -> None:
        """Fallback usage is recorded in ChangeDeltaSchema metadata (Req 7.5)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Regulatory Compliance Auditor",
                    "name": "Regulatory Compliance Auditor",
                    "system_prompt": "You are a regulatory auditor.",
                    "contextual_tuning": {"temperature": 0.3, "max_tokens": 2048},
                }
            ]
        )
        svc = ImpactAnalysisService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        _prompt, _temp, _max_tok, fallback_used = svc._get_agent_config()
        assert fallback_used is True

    def test_fallback_prompt_suffix_appended(
        self, mock_knowledge_service: MagicMock, mock_inference_client: AsyncMock
    ) -> None:
        """Fallback appends system prompt suffix for change impact focus (Req 7.5)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Regulatory Compliance Auditor",
                    "name": "Regulatory Compliance Auditor",
                    "system_prompt": "You are a regulatory auditor.",
                    "contextual_tuning": {"temperature": 0.3, "max_tokens": 2048},
                }
            ]
        )
        svc = ImpactAnalysisService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )
        system_prompt, _temp, _max_tok, _fallback = svc._get_agent_config()
        # Should contain the original prompt plus the appended suffix
        assert "regulatory auditor" in system_prompt.lower()
        assert "Change Impact Analyst" in system_prompt
        assert "significance level" in system_prompt.lower()


# ---------------------------------------------------------------------------
# Agent Config: InferenceClient Parameter Passing (Req 7.4)
# ---------------------------------------------------------------------------


class TestAgentConfigInferencePassing:
    """Tests that agent config parameters are passed to InferenceClient calls.

    Validates Requirements 7.4: temperature 0.2 and max_tokens 4096 passed
    to InferenceClient during actual inference calls.
    """

    @pytest.mark.asyncio
    async def test_temperature_and_max_tokens_passed_to_inference(
        self,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
        mock_agent_registry: MagicMock,
    ) -> None:
        """Temperature 0.2 and max_tokens 4096 are passed to InferenceClient (Req 7.4)."""
        svc = ImpactAnalysisService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        old_result = MagicMock()
        old_result.excerpt = "# Safety\nOld safety content."
        new_result = MagicMock()
        new_result.excerpt = "# Safety\nNew safety content with PPE."

        mock_knowledge_service.hybrid_search.side_effect = [
            ([new_result], 1),
            ([old_result], 1),
        ]

        await svc.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=2,
            previous_version_id=1,
            company_id=1,
        )

        # Verify InferenceClient was called with correct temperature and max_tokens
        mock_inference_client.chat_completion.assert_called_once()
        call_kwargs = mock_inference_client.chat_completion.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.2 or call_kwargs[1].get("temperature") == 0.2
        assert call_kwargs.kwargs.get("max_tokens") == 4096 or call_kwargs[1].get("max_tokens") == 4096

    @pytest.mark.asyncio
    async def test_fallback_metadata_recorded_in_change_delta_output(
        self,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Fallback_used is recorded in ChangeDeltaSchema metadata (Req 7.5)."""
        registry = MagicMock()
        registry.list_archetypes = MagicMock(
            return_value=[
                {
                    "archetype": "Regulatory Compliance Auditor",
                    "name": "Regulatory Compliance Auditor",
                    "system_prompt": "You are a regulatory auditor.",
                    "contextual_tuning": {"temperature": 0.3, "max_tokens": 2048},
                }
            ]
        )
        svc = ImpactAnalysisService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=registry,
        )

        old_result = MagicMock()
        old_result.excerpt = "# Procedures\nOld procedure steps."
        new_result = MagicMock()
        new_result.excerpt = "# Procedures\nNew procedure steps with updates."

        mock_knowledge_service.hybrid_search.side_effect = [
            ([new_result], 1),
            ([old_result], 1),
        ]

        result = await svc.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=2,
            previous_version_id=1,
            company_id=1,
        )

        assert isinstance(result, ChangeDeltaSchema)
        assert "fallback_used" in result.metadata
        assert result.metadata["fallback_used"]["missing_archetype"] == "Change Impact Analyst"
        assert result.metadata["fallback_used"]["used_archetype"] == "Regulatory Compliance Auditor"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_knowledge_service_unavailable(
        self, mock_inference_client: AsyncMock, mock_agent_registry: MagicMock
    ) -> None:
        """When KnowledgeService is None, returns empty delta for first version."""
        svc = ImpactAnalysisService(
            knowledge_service=None,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )
        result = await svc.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=1,
            previous_version_id=None,
            company_id=1,
        )
        assert isinstance(result, ChangeDeltaSchema)
        assert result.metadata.get("first_version") is True

    @pytest.mark.asyncio
    async def test_inference_failure_falls_back_to_heuristic(
        self, service: ImpactAnalysisService, mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock
    ) -> None:
        """When inference fails, falls back to heuristic classification."""
        mock_inference_client.chat_completion.side_effect = Exception("Connection refused")

        old_result = MagicMock()
        old_result.excerpt = "# Safety\nOld safety."
        new_result = MagicMock()
        new_result.excerpt = "# Safety\nNew safety with hazard warnings."

        mock_knowledge_service.hybrid_search.side_effect = [
            ([new_result], 1),
            ([old_result], 1),
        ]

        result = await service.compute_change_delta(
            document_uuid="DOC-001",
            new_version_id=2,
            previous_version_id=1,
            company_id=1,
        )

        assert isinstance(result, ChangeDeltaSchema)
        # Should still have significance levels from heuristic
        total = sum(result.significance_levels.values())
        assert total > 0
