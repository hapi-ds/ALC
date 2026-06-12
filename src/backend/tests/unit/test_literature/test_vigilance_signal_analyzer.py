"""Unit tests for the VigilanceSignalAnalyzer.

Tests cover:
- _construct_prompt contains product name, device_class, intended_purpose, MDR criteria, JSON schema
- _parse_response with valid JSON (correct SignalAnalysisResult)
- _parse_response with malformed JSON (returns None)
- _parse_response with missing fields, wrong severity enum, confidence out of range
- analyze_record with successful response above threshold (creates signal)
- analyze_record with response below threshold (no signal)
- analyze_record fallback to uncertain on parse failure
- analyze_batch continues on per-record failure
- _get_agent_config loads archetype, falls back on not found

References:
    - Requirements: 1.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
    - Task: 14.4
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.vigilance.exceptions import InferenceConnectionError
from alcoabase.literature.vigilance.services.vigilance_signal_analyzer import (
    SignalAnalysisResult,
    VigilanceSignalAnalyzer,
)
from alcoabase.services.inference_client import (
    InferenceConnectionError as ClientConnectionError,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory.

    The service uses `async with self._session_factory() as session:`,
    so the factory must be a callable returning an async context manager.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    # Create an async context manager mock
    ctx_mgr = AsyncMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=session)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)

    # Factory is a regular callable that returns the async context manager
    factory = MagicMock(return_value=ctx_mgr)
    return factory, session


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_agent_registry():
    """Create a mock AgentRegistryService."""
    registry = MagicMock()
    registry._load_archetype_raw = MagicMock(return_value=None)
    return registry


@pytest.fixture
def analyzer(mock_session_factory, mock_inference_client, mock_agent_registry):
    """Create a VigilanceSignalAnalyzer with mocked dependencies."""
    factory, _ = mock_session_factory
    return VigilanceSignalAnalyzer(
        session_factory=factory,
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
        model_name="test-model",
        confidence_threshold=0.7,
        batch_size=10,
    )


def _make_record_mock(record_id=1, title="Test Paper", abstract="Test abstract"):
    """Create a mock IngestionRecord."""
    record = MagicMock()
    record.id = record_id
    record.title = title
    record.abstract = abstract
    return record


def _make_product_mock(
    product_id=1,
    name="CardioMonitor X200",
    device_class="IIb",
    intended_purpose="Continuous cardiac monitoring",
    predicate_devices=None,
):
    """Create a mock MedicalProduct."""
    product = MagicMock()
    product.id = product_id
    product.name = name
    product.device_class = device_class
    product.intended_purpose = intended_purpose
    product.predicate_devices = predicate_devices
    return product


def _valid_llm_response(
    signal_detected=True,
    severity="major",
    confidence=0.85,
    evidence_summary="Adverse event identified in cardiac monitoring context.",
):
    """Generate a valid JSON response string from LLM."""
    return json.dumps({
        "signal_detected": signal_detected,
        "severity": severity,
        "evidence_summary": evidence_summary,
        "affected_product_aspects": ["cardiac sensor", "alarm system"],
        "regulatory_references": ["MDR Article 87(1)(a)"],
        "recommended_actions": ["Review device logs", "Notify competent authority"],
        "confidence": confidence,
    })


# ---------------------------------------------------------------------------
# Tests for _construct_prompt
# ---------------------------------------------------------------------------


class TestConstructPrompt:
    """Tests for VigilanceSignalAnalyzer._construct_prompt."""

    def test_prompt_contains_product_name(self, analyzer):
        """Prompt includes the product name."""
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract="Abstract",
            body_text=None,
            product_name="CardioMonitor X200",
            device_class="IIb",
            intended_purpose="Cardiac monitoring",
            predicate_devices=None,
        )
        assert "CardioMonitor X200" in prompt

    def test_prompt_contains_device_class(self, analyzer):
        """Prompt includes the device class."""
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract="Abstract",
            body_text=None,
            product_name="Device",
            device_class="III",
            intended_purpose="Implant",
            predicate_devices=None,
        )
        assert "III" in prompt

    def test_prompt_contains_intended_purpose(self, analyzer):
        """Prompt includes the intended purpose."""
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract="Abstract",
            body_text=None,
            product_name="Device",
            device_class="IIa",
            intended_purpose="Diagnostic imaging for soft tissue",
            predicate_devices=None,
        )
        assert "Diagnostic imaging for soft tissue" in prompt

    def test_prompt_contains_mdr_severity_criteria(self, analyzer):
        """Prompt includes MDR severity classification criteria."""
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract="Abstract",
            body_text=None,
            product_name="Device",
            device_class="IIb",
            intended_purpose="Monitoring",
            predicate_devices=None,
        )
        assert "CRITICAL" in prompt
        assert "MAJOR" in prompt
        assert "MINOR" in prompt
        assert "MDR Article 87" in prompt

    def test_prompt_contains_json_schema(self, analyzer):
        """Prompt includes the expected JSON output schema."""
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract="Abstract",
            body_text=None,
            product_name="Device",
            device_class="IIb",
            intended_purpose="Monitoring",
            predicate_devices=None,
        )
        assert "signal_detected" in prompt
        assert "severity" in prompt
        assert "evidence_summary" in prompt
        assert "confidence" in prompt

    def test_prompt_includes_predicate_devices(self, analyzer):
        """Prompt includes predicate devices when provided."""
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract="Abstract",
            body_text=None,
            product_name="Device",
            device_class="IIb",
            intended_purpose="Monitoring",
            predicate_devices=["PredicateA", "PredicateB"],
        )
        assert "PredicateA" in prompt
        assert "PredicateB" in prompt

    def test_prompt_includes_title_and_abstract(self, analyzer):
        """Prompt includes the paper title and abstract."""
        prompt = analyzer._construct_prompt(
            title="Novel Adverse Events in Cardiac Devices",
            abstract="We report a case series of device malfunctions...",
            body_text=None,
            product_name="Device",
            device_class="IIa",
            intended_purpose="Monitoring",
            predicate_devices=None,
        )
        assert "Novel Adverse Events in Cardiac Devices" in prompt
        assert "We report a case series of device malfunctions..." in prompt

    def test_prompt_truncates_long_abstract(self, analyzer):
        """Prompt truncates abstract exceeding 4000 chars."""
        long_abstract = "A" * 5000
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract=long_abstract,
            body_text=None,
            product_name="Device",
            device_class="IIa",
            intended_purpose="Monitoring",
            predicate_devices=None,
        )
        assert "... [truncated]" in prompt
        # Should not contain the full 5000 chars
        assert "A" * 5000 not in prompt

    def test_prompt_includes_body_when_provided(self, analyzer):
        """Prompt includes body text when provided."""
        prompt = analyzer._construct_prompt(
            title="Test",
            abstract="Abstract",
            body_text="The study enrolled 200 patients over 12 months.",
            product_name="Device",
            device_class="IIa",
            intended_purpose="Monitoring",
            predicate_devices=None,
        )
        assert "The study enrolled 200 patients over 12 months." in prompt


# ---------------------------------------------------------------------------
# Tests for _parse_response
# ---------------------------------------------------------------------------


class TestParseResponse:
    """Tests for VigilanceSignalAnalyzer._parse_response."""

    def test_valid_response_returns_result(self, analyzer):
        """Valid JSON produces a SignalAnalysisResult."""
        response = _valid_llm_response()
        result = analyzer._parse_response(response)
        assert result is not None
        assert isinstance(result, SignalAnalysisResult)
        assert result.signal_detected is True
        assert result.severity == "major"
        assert result.confidence == 0.85

    def test_valid_no_signal_response(self, analyzer):
        """Valid response with signal_detected=False returns valid result."""
        response = _valid_llm_response(signal_detected=False, severity=None, confidence=0.3)
        result = analyzer._parse_response(response)
        assert result is not None
        assert result.signal_detected is False
        assert result.severity is None

    def test_malformed_json_returns_none(self, analyzer):
        """Non-JSON string returns None."""
        result = analyzer._parse_response("This is not JSON at all")
        assert result is None

    def test_empty_string_returns_none(self, analyzer):
        """Empty string returns None."""
        result = analyzer._parse_response("")
        assert result is None

    def test_missing_signal_detected_returns_none(self, analyzer):
        """Missing signal_detected field returns None."""
        data = {
            "severity": "major",
            "evidence_summary": "Some evidence",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 0.8,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_wrong_severity_enum_returns_none(self, analyzer):
        """Invalid severity value returns None."""
        data = {
            "signal_detected": True,
            "severity": "catastrophic",  # invalid
            "evidence_summary": "Evidence",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 0.9,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_confidence_above_one_returns_none(self, analyzer):
        """Confidence > 1.0 returns None."""
        data = {
            "signal_detected": True,
            "severity": "major",
            "evidence_summary": "Evidence",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 1.5,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_confidence_below_zero_returns_none(self, analyzer):
        """Confidence < 0.0 returns None."""
        data = {
            "signal_detected": True,
            "severity": "minor",
            "evidence_summary": "Evidence",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": -0.1,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_missing_evidence_summary_returns_none(self, analyzer):
        """Missing evidence_summary returns None."""
        data = {
            "signal_detected": True,
            "severity": "major",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 0.8,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_empty_evidence_summary_returns_none(self, analyzer):
        """Empty evidence_summary returns None."""
        data = {
            "signal_detected": True,
            "severity": "major",
            "evidence_summary": "   ",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 0.8,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_non_bool_signal_detected_returns_none(self, analyzer):
        """Non-boolean signal_detected returns None."""
        data = {
            "signal_detected": "yes",
            "severity": "major",
            "evidence_summary": "Evidence",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 0.8,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_non_list_affected_aspects_returns_none(self, analyzer):
        """Non-list affected_product_aspects returns None."""
        data = {
            "signal_detected": True,
            "severity": "major",
            "evidence_summary": "Evidence",
            "affected_product_aspects": "cardiac sensor",
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 0.8,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is None

    def test_recommended_actions_truncated_to_five(self, analyzer):
        """Recommended actions are truncated to max 5."""
        data = {
            "signal_detected": True,
            "severity": "minor",
            "evidence_summary": "Evidence found",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"],
            "confidence": 0.75,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is not None
        assert len(result.recommended_actions) == 5

    def test_markdown_code_fence_stripped(self, analyzer):
        """JSON wrapped in markdown code fences is parsed correctly."""
        inner_json = json.dumps({
            "signal_detected": True,
            "severity": "critical",
            "evidence_summary": "Death reported",
            "affected_product_aspects": ["battery"],
            "regulatory_references": ["MDR Art 87"],
            "recommended_actions": ["Recall"],
            "confidence": 0.95,
        })
        response = f"```json\n{inner_json}\n```"
        result = analyzer._parse_response(response)
        assert result is not None
        assert result.severity == "critical"

    def test_null_severity_accepted(self, analyzer):
        """Null severity with signal_detected=False is valid."""
        data = {
            "signal_detected": False,
            "severity": None,
            "evidence_summary": "No signal found in this literature.",
            "affected_product_aspects": [],
            "regulatory_references": [],
            "recommended_actions": [],
            "confidence": 0.2,
        }
        result = analyzer._parse_response(json.dumps(data))
        assert result is not None
        assert result.severity is None

    def test_random_bytes_returns_none(self, analyzer):
        """Random bytes return None."""
        result = analyzer._parse_response(b"\x00\x01\x02\xff".decode("latin-1"))
        assert result is None


# ---------------------------------------------------------------------------
# Tests for _get_agent_config
# ---------------------------------------------------------------------------


class TestGetAgentConfig:
    """Tests for VigilanceSignalAnalyzer._get_agent_config."""

    def test_fallback_when_archetype_not_found(self, analyzer, mock_agent_registry):
        """Returns fallback defaults when archetype is not found."""
        mock_agent_registry._load_archetype_raw.return_value = None

        system_prompt, temperature, max_tokens, top_p = analyzer._get_agent_config()

        assert system_prompt == VigilanceSignalAnalyzer.FALLBACK_SYSTEM_PROMPT
        assert temperature == 0.05
        assert max_tokens == 6144
        assert top_p == 0.90

    def test_loads_archetype_config(self, analyzer, mock_agent_registry):
        """Loads config from archetype when found."""
        mock_agent_registry._load_archetype_raw.return_value = {
            "archetype": "Vigilance Analyst",
            "system_prompt": "Custom prompt for analysis",
            "contextual_tuning": {
                "temperature": 0.1,
                "max_tokens": 4096,
                "top_p": 0.85,
            },
        }

        system_prompt, temperature, max_tokens, top_p = analyzer._get_agent_config()

        assert system_prompt == "Custom prompt for analysis"
        assert temperature == 0.1
        assert max_tokens == 4096
        assert top_p == 0.85

    def test_partial_archetype_uses_defaults(self, analyzer, mock_agent_registry):
        """Missing contextual_tuning fields fall back to defaults."""
        mock_agent_registry._load_archetype_raw.return_value = {
            "archetype": "Vigilance Analyst",
            "system_prompt": "Partial prompt",
            "contextual_tuning": {},
        }

        system_prompt, temperature, max_tokens, top_p = analyzer._get_agent_config()

        assert system_prompt == "Partial prompt"
        assert temperature == 0.05
        assert max_tokens == 6144
        assert top_p == 0.90


# ---------------------------------------------------------------------------
# Tests for analyze_record
# ---------------------------------------------------------------------------


class TestAnalyzeRecord:
    """Tests for VigilanceSignalAnalyzer.analyze_record."""

    async def test_creates_signal_above_threshold(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Creates VigilanceSignal when confidence >= threshold and signal_detected."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        product = _make_product_mock()

        session.get = AsyncMock(side_effect=[record, product])
        mock_inference_client.chat_completion = AsyncMock(
            return_value=_valid_llm_response(confidence=0.85)
        )

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
            confidence_threshold=0.7,
        )

        result = await analyzer.analyze_record(
            record_id=1, product_id=1, profile_id=1, company_id=10
        )

        assert result.signal_detected is True
        assert result.confidence == 0.85
        # Verify session.add was called (signal created)
        session.add.assert_called_once()
        session.commit.assert_called_once()

    async def test_no_signal_below_threshold(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Does not create signal when confidence < threshold."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        product = _make_product_mock()

        session.get = AsyncMock(side_effect=[record, product])
        mock_inference_client.chat_completion = AsyncMock(
            return_value=_valid_llm_response(confidence=0.5)
        )

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
            confidence_threshold=0.7,
        )

        result = await analyzer.analyze_record(
            record_id=1, product_id=1, profile_id=1, company_id=10
        )

        assert result.signal_detected is True
        assert result.confidence == 0.5
        # No signal should be created
        session.add.assert_not_called()
        session.commit.assert_not_called()

    async def test_no_signal_when_not_detected(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Does not create signal when signal_detected=False."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        product = _make_product_mock()

        session.get = AsyncMock(side_effect=[record, product])
        mock_inference_client.chat_completion = AsyncMock(
            return_value=_valid_llm_response(
                signal_detected=False, severity=None, confidence=0.9
            )
        )

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
            confidence_threshold=0.7,
        )

        result = await analyzer.analyze_record(
            record_id=1, product_id=1, profile_id=1, company_id=10
        )

        assert result.signal_detected is False
        session.add.assert_not_called()

    async def test_uncertain_on_malformed_response(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Returns uncertain result on malformed LLM response."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        product = _make_product_mock()

        session.get = AsyncMock(side_effect=[record, product])
        mock_inference_client.chat_completion = AsyncMock(
            return_value="This is not valid JSON at all"
        )

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
            confidence_threshold=0.7,
        )

        result = await analyzer.analyze_record(
            record_id=1, product_id=1, profile_id=1, company_id=10
        )

        assert result.signal_detected is False
        assert result.confidence == 0.0
        assert "malformed" in result.evidence_summary.lower() or "manual review" in result.evidence_summary.lower()
        session.add.assert_not_called()

    async def test_record_not_found(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Returns no-signal result when record not found."""
        factory, session = mock_session_factory
        session.get = AsyncMock(return_value=None)

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
        )

        result = await analyzer.analyze_record(
            record_id=999, product_id=1, profile_id=1, company_id=10
        )

        assert result.signal_detected is False
        assert "not found" in result.evidence_summary.lower()

    async def test_product_not_found(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Returns no-signal result when product not found."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        session.get = AsyncMock(side_effect=[record, None])

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
        )

        result = await analyzer.analyze_record(
            record_id=1, product_id=999, profile_id=1, company_id=10
        )

        assert result.signal_detected is False
        assert "not found" in result.evidence_summary.lower()

    async def test_inference_connection_error_propagates(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """InferenceConnectionError is raised when vLLM is unreachable."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        product = _make_product_mock()

        session.get = AsyncMock(side_effect=[record, product])
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=ClientConnectionError("Connection refused")
        )

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
        )

        with pytest.raises(InferenceConnectionError):
            await analyzer.analyze_record(
                record_id=1, product_id=1, profile_id=1, company_id=10
            )


# ---------------------------------------------------------------------------
# Tests for analyze_batch
# ---------------------------------------------------------------------------


class TestAnalyzeBatch:
    """Tests for VigilanceSignalAnalyzer.analyze_batch."""

    async def test_batch_processes_all_records(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Batch processes all record IDs and returns results."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        product = _make_product_mock()

        session.get = AsyncMock(side_effect=[record, product, record, product])
        mock_inference_client.chat_completion = AsyncMock(
            return_value=_valid_llm_response(signal_detected=False, severity=None, confidence=0.3)
        )

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
            confidence_threshold=0.7,
        )

        results = await analyzer.analyze_batch(
            record_ids=[1, 2], product_id=1, profile_id=1, company_id=10
        )

        assert len(results) == 2
        assert all(isinstance(r[1], SignalAnalysisResult) for r in results)

    async def test_batch_continues_on_per_record_failure(
        self, mock_session_factory, mock_inference_client, mock_agent_registry
    ):
        """Batch continues processing after a single record fails."""
        factory, session = mock_session_factory
        record = _make_record_mock()
        product = _make_product_mock()

        # First call raises, second succeeds
        call_count = [0]
        original_record = record
        original_product = product

        async def side_effect_get(model_class, id_val):
            call_count[0] += 1
            if call_count[0] <= 2:
                # First record access
                if call_count[0] == 1:
                    return original_record
                else:
                    return original_product
            else:
                # Second record access
                if call_count[0] == 3:
                    return original_record
                else:
                    return original_product

        session.get = AsyncMock(side_effect=side_effect_get)

        # First call raises exception, second returns valid
        responses = [
            ClientConnectionError("timeout"),
            _valid_llm_response(signal_detected=False, severity=None, confidence=0.2),
        ]
        mock_inference_client.chat_completion = AsyncMock(side_effect=responses)

        analyzer = VigilanceSignalAnalyzer(
            session_factory=factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            model_name="test-model",
            confidence_threshold=0.7,
        )

        results = await analyzer.analyze_batch(
            record_ids=[1, 2], product_id=1, profile_id=1, company_id=10
        )

        # Both records should have results (first is uncertain/failed, second is analyzed)
        assert len(results) == 2
        # First record should be marked as failed/uncertain
        assert results[0][1].confidence == 0.0
        assert "failed" in results[0][1].evidence_summary.lower()
        # Second record should be analyzed normally
        assert results[1][1].signal_detected is False
