"""Unit tests for LiteratureScreenerAgentRunner.

Tests prompt construction, JSON response parsing and validation,
screen_record end-to-end flow, and screen_batch error handling.

References:
    - Requirements: 1.3, 1.5, 3.1, 3.2, 3.6
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.review.services.screener_agent_runner import (
    LiteratureScreenerAgentRunner,
    ScreeningResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Mock InferenceClient with chat_completion method."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(return_value="")
    return client


@pytest.fixture
def mock_agent_registry() -> MagicMock:
    """Mock AgentRegistryService with _load_archetype_raw method."""
    registry = MagicMock()
    registry._load_archetype_raw = MagicMock(return_value=None)
    return registry


@pytest.fixture
def runner(
    mock_inference_client: AsyncMock,
    mock_agent_registry: MagicMock,
) -> LiteratureScreenerAgentRunner:
    """Create a LiteratureScreenerAgentRunner instance with mocked dependencies."""
    return LiteratureScreenerAgentRunner(
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
        model_name="test-model",
    )


@pytest.fixture
def sample_protocol_criteria() -> dict:
    """Sample protocol criteria for testing prompt construction."""
    return {
        "pico_criteria": {
            "population": "Adults with type 2 diabetes",
            "intervention": "GLP-1 receptor agonists",
            "comparison": "Placebo",
            "outcome": "HbA1c reduction",
        },
        "inclusion_criteria": [
            "randomized controlled trial",
            "published after 2015",
        ],
        "exclusion_criteria": [
            "animal studies",
            "case reports only",
        ],
    }


@pytest.fixture
def valid_llm_response() -> str:
    """Valid JSON response from the LLM."""
    return json.dumps({
        "verdict": "include",
        "confidence": 0.92,
        "rationale": "The study is a randomized controlled trial evaluating GLP-1 agonists.",
        "matched_inclusion_criteria": [0, 1],
        "matched_exclusion_criteria": [],
    })


# ---------------------------------------------------------------------------
# Tests: _construct_prompt
# ---------------------------------------------------------------------------


class TestConstructPrompt:
    """Tests for LiteratureScreenerAgentRunner._construct_prompt."""

    def test_contains_title(self, runner: LiteratureScreenerAgentRunner):
        """Prompt includes the paper title."""
        prompt = runner._construct_prompt(
            title="Effect of Metformin on Blood Glucose",
            abstract="A short abstract.",
            body_sections=None,
            protocol_criteria={"pico_criteria": {}},
        )

        assert "Effect of Metformin on Blood Glucose" in prompt

    def test_contains_abstract(self, runner: LiteratureScreenerAgentRunner):
        """Prompt includes the abstract text."""
        prompt = runner._construct_prompt(
            title="Test",
            abstract="This is a detailed abstract about diabetes treatment outcomes.",
            body_sections=None,
            protocol_criteria={"pico_criteria": {}},
        )

        assert "This is a detailed abstract about diabetes treatment outcomes." in prompt

    def test_contains_pico_criteria(
        self,
        runner: LiteratureScreenerAgentRunner,
        sample_protocol_criteria: dict,
    ):
        """Prompt includes PICO criteria fields."""
        prompt = runner._construct_prompt(
            title="Test Paper",
            abstract="Abstract text",
            body_sections=None,
            protocol_criteria=sample_protocol_criteria,
        )

        assert "Adults with type 2 diabetes" in prompt
        assert "GLP-1 receptor agonists" in prompt
        assert "Placebo" in prompt
        assert "HbA1c reduction" in prompt

    def test_contains_inclusion_exclusion_patterns(
        self,
        runner: LiteratureScreenerAgentRunner,
        sample_protocol_criteria: dict,
    ):
        """Prompt includes inclusion and exclusion criteria patterns."""
        prompt = runner._construct_prompt(
            title="Test Paper",
            abstract="Abstract text",
            body_sections=None,
            protocol_criteria=sample_protocol_criteria,
        )

        assert "randomized controlled trial" in prompt
        assert "published after 2015" in prompt
        assert "animal studies" in prompt
        assert "case reports only" in prompt

    def test_contains_body_sections_when_provided(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Prompt includes body section content when provided."""
        body_sections = [
            {"heading": "Methods", "text": "We conducted a double-blind RCT."},
            {"heading": "Results", "text": "HbA1c decreased by 1.2%."},
        ]
        prompt = runner._construct_prompt(
            title="Test Paper",
            abstract="Abstract",
            body_sections=body_sections,
            protocol_criteria={"pico_criteria": {}},
        )

        assert "Methods" in prompt
        assert "We conducted a double-blind RCT." in prompt
        assert "Results" in prompt
        assert "HbA1c decreased by 1.2%." in prompt


# ---------------------------------------------------------------------------
# Tests: _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    """Tests for LiteratureScreenerAgentRunner._parse_response."""

    def test_valid_json_returns_screening_result(
        self, runner: LiteratureScreenerAgentRunner, valid_llm_response: str
    ):
        """Valid JSON response is parsed into a ScreeningResult."""
        result = runner._parse_response(valid_llm_response)

        assert result is not None
        assert isinstance(result, ScreeningResult)
        assert result.verdict == "include"
        assert result.confidence == 0.92
        assert "randomized controlled trial" in result.rationale
        assert result.matched_inclusion_criteria == [0, 1]
        assert result.matched_exclusion_criteria == []

    def test_malformed_json_returns_none(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Malformed JSON (not valid JSON) returns None."""
        result = runner._parse_response("this is not json at all {{{")

        assert result is None

    def test_missing_verdict_field_returns_none(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Missing required 'verdict' field returns None."""
        response = json.dumps({
            "confidence": 0.9,
            "rationale": "Some rationale",
            "matched_inclusion_criteria": [],
            "matched_exclusion_criteria": [],
        })

        result = runner._parse_response(response)

        assert result is None

    def test_missing_confidence_field_returns_none(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Missing required 'confidence' field returns None."""
        response = json.dumps({
            "verdict": "include",
            "rationale": "Some rationale",
            "matched_inclusion_criteria": [],
            "matched_exclusion_criteria": [],
        })

        result = runner._parse_response(response)

        assert result is None

    def test_missing_rationale_field_returns_none(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Missing required 'rationale' field returns None."""
        response = json.dumps({
            "verdict": "include",
            "confidence": 0.85,
            "matched_inclusion_criteria": [],
            "matched_exclusion_criteria": [],
        })

        result = runner._parse_response(response)

        assert result is None

    def test_confidence_above_1_returns_none(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Confidence > 1.0 returns None."""
        response = json.dumps({
            "verdict": "include",
            "confidence": 1.5,
            "rationale": "Some rationale",
            "matched_inclusion_criteria": [],
            "matched_exclusion_criteria": [],
        })

        result = runner._parse_response(response)

        assert result is None

    def test_confidence_below_0_returns_none(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Confidence < 0.0 returns None."""
        response = json.dumps({
            "verdict": "exclude",
            "confidence": -0.1,
            "rationale": "Some rationale",
            "matched_inclusion_criteria": [],
            "matched_exclusion_criteria": [],
        })

        result = runner._parse_response(response)

        assert result is None

    def test_invalid_verdict_value_returns_none(
        self, runner: LiteratureScreenerAgentRunner
    ):
        """Invalid verdict value (not include/exclude/uncertain) returns None."""
        response = json.dumps({
            "verdict": "maybe",
            "confidence": 0.5,
            "rationale": "Some rationale",
            "matched_inclusion_criteria": [],
            "matched_exclusion_criteria": [],
        })

        result = runner._parse_response(response)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: screen_record
# ---------------------------------------------------------------------------


class TestScreenRecord:
    """Tests for LiteratureScreenerAgentRunner.screen_record."""

    @pytest.mark.asyncio
    async def test_successful_screening(
        self,
        runner: LiteratureScreenerAgentRunner,
        mock_inference_client: AsyncMock,
        valid_llm_response: str,
        sample_protocol_criteria: dict,
    ):
        """Successful screen_record returns parsed ScreeningResult."""
        mock_inference_client.chat_completion.return_value = valid_llm_response

        result = await runner.screen_record(
            title="GLP-1 Agonist RCT",
            abstract="A randomized trial of GLP-1 agonists.",
            body_sections=None,
            protocol_criteria=sample_protocol_criteria,
        )

        assert isinstance(result, ScreeningResult)
        assert result.verdict == "include"
        assert result.confidence == 0.92
        assert result.screening_duration_ms >= 0
        mock_inference_client.chat_completion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_to_uncertain_on_parse_failure(
        self,
        runner: LiteratureScreenerAgentRunner,
        mock_inference_client: AsyncMock,
        sample_protocol_criteria: dict,
    ):
        """Returns uncertain/0.0 fallback when LLM response is unparseable."""
        mock_inference_client.chat_completion.return_value = "not valid json"

        result = await runner.screen_record(
            title="Some Paper",
            abstract="Abstract text",
            body_sections=None,
            protocol_criteria=sample_protocol_criteria,
        )

        assert result.verdict == "uncertain"
        assert result.confidence == 0.0
        assert "parsing failed" in result.rationale.lower()
        assert result.matched_inclusion_criteria == []
        assert result.matched_exclusion_criteria == []


# ---------------------------------------------------------------------------
# Tests: screen_batch
# ---------------------------------------------------------------------------


class TestScreenBatch:
    """Tests for LiteratureScreenerAgentRunner.screen_batch."""

    @pytest.mark.asyncio
    async def test_continues_on_per_record_failure(
        self,
        runner: LiteratureScreenerAgentRunner,
        mock_inference_client: AsyncMock,
        valid_llm_response: str,
        sample_protocol_criteria: dict,
    ):
        """Batch processing continues when an individual record raises an exception."""
        # First record succeeds, second raises, third succeeds
        mock_inference_client.chat_completion.side_effect = [
            valid_llm_response,
            RuntimeError("LLM connection lost"),
            valid_llm_response,
        ]

        records = [
            {"record_id": 1, "title": "Paper A", "abstract": "Abstract A"},
            {"record_id": 2, "title": "Paper B", "abstract": "Abstract B"},
            {"record_id": 3, "title": "Paper C", "abstract": "Abstract C"},
        ]

        results = await runner.screen_batch(records, sample_protocol_criteria)

        assert len(results) == 3

        # First record: success
        assert results[0][0] == 1
        assert results[0][1].verdict == "include"

        # Second record: failure => uncertain fallback
        assert results[1][0] == 2
        assert results[1][1].verdict == "uncertain"
        assert results[1][1].confidence == 0.0

        # Third record: success
        assert results[2][0] == 3
        assert results[2][1].verdict == "include"


# ---------------------------------------------------------------------------
# Tests: _get_agent_config
# ---------------------------------------------------------------------------


class TestGetAgentConfig:
    """Tests for LiteratureScreenerAgentRunner._get_agent_config."""

    def test_loads_archetype_from_registry(
        self,
        runner: LiteratureScreenerAgentRunner,
        mock_agent_registry: MagicMock,
    ):
        """Loads system prompt and tuning from the archetype when found."""
        mock_agent_registry._load_archetype_raw.return_value = {
            "system_prompt": "You are a literature screening specialist.",
            "contextual_tuning": {
                "temperature": 0.05,
                "max_tokens": 2048,
            },
        }

        system_prompt, temperature, max_tokens = runner._get_agent_config()

        assert system_prompt == "You are a literature screening specialist."
        assert temperature == 0.05
        assert max_tokens == 2048
        mock_agent_registry._load_archetype_raw.assert_called_once_with(
            "Literature Screener"
        )

    def test_falls_back_on_archetype_not_found(
        self,
        runner: LiteratureScreenerAgentRunner,
        mock_agent_registry: MagicMock,
    ):
        """Falls back to default config when archetype is not found."""
        mock_agent_registry._load_archetype_raw.return_value = None

        system_prompt, temperature, max_tokens = runner._get_agent_config()

        assert system_prompt == LiteratureScreenerAgentRunner.FALLBACK_SYSTEM_PROMPT
        assert temperature == LiteratureScreenerAgentRunner.FALLBACK_TEMPERATURE
        assert max_tokens == LiteratureScreenerAgentRunner.FALLBACK_MAX_TOKENS
