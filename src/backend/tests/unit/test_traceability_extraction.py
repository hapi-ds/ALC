"""Unit tests for TraceabilityMatrixService extraction methods.

Tests requirement extraction and test case extraction including:
- Successful extraction with AI response parsing
- InferenceClient unavailability handling (retries, backoff)
- Per-document extraction timeout (120s)
- Empty document handling
- JSON response parsing edge cases

Requirements: 1.2, 1.10, 6.4, 6.7
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.services.traceability_matrix import (
    TraceabilityMatrixService,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_knowledge_service():
    """Mock KnowledgeService that returns document text."""
    ks = MagicMock()
    # Return search results with excerpts
    from alcoabase.services.knowledge_service import SearchResult

    ks.hybrid_search.return_value = (
        [
            SearchResult(
                document_uuid="doc-001",
                title="Test Doc",
                version="1.0",
                excerpt="## 1.1 Input Validation\nREQ-001: The system shall validate user input.\n",
                relevance_score=0.9,
            ),
            SearchResult(
                document_uuid="doc-001",
                title="Test Doc",
                version="1.0",
                excerpt="## 2.1 Audit\nREQ-002: The system shall log all access.\n",
                relevance_score=0.8,
            ),
        ],
        2,
    )
    return ks


@pytest.fixture
def mock_inference_client():
    """Mock InferenceClient that returns valid JSON responses."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_agent_registry():
    """Mock AgentRegistryService with Traceability Analyst archetype."""
    registry = MagicMock()
    registry.list_archetypes.return_value = [
        {
            "archetype": "Traceability Analyst",
            "name": "Traceability Analyst",
            "system_prompt": "You are a Traceability Analyst.",
            "contextual_tuning": {
                "temperature": 0.15,
                "max_tokens": 4096,
            },
        }
    ]
    return registry


@pytest.fixture
def source_documents():
    """Sample source documents for extraction."""
    return [
        {"document_uuid": "doc-src-001", "document_id": 1},
        {"document_uuid": "doc-src-002", "document_id": 2},
    ]


@pytest.fixture
def target_documents():
    """Sample target documents for extraction."""
    return [
        {"document_uuid": "doc-tgt-001", "document_id": 3},
        {"document_uuid": "doc-tgt-002", "document_id": 4},
    ]


def _make_requirements_response(reqs: list[dict]) -> str:
    """Helper to create a valid AI response for requirements."""
    return json.dumps({"requirements": reqs})


def _make_test_cases_response(tcs: list[dict]) -> str:
    """Helper to create a valid AI response for test cases."""
    return json.dumps({"test_cases": tcs})


# ─────────────────────────────────────────────────────────────────────────────
# Tests: extract_requirements
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractRequirements:
    """Tests for extract_requirements method."""

    @pytest.mark.asyncio
    async def test_successful_extraction(
        self, mock_knowledge_service, mock_inference_client, mock_agent_registry
    ):
        """Successfully extracts requirements from source documents."""
        mock_inference_client.chat_completion.return_value = (
            _make_requirements_response([
                {
                    "requirement_id": "REQ-001",
                    "requirement_text": "The system shall validate user input.",
                    "section_heading": "1.1 Input Validation",
                    "acceptance_criteria": "All inputs validated",
                },
                {
                    "requirement_id": "REQ-002",
                    "requirement_text": "The system shall log all access.",
                    "section_heading": "2.1 Audit",
                    "acceptance_criteria": None,
                },
            ])
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        assert not result.failed
        assert len(result.requirements) == 2
        assert result.requirements[0].requirement_id == "REQ-001"
        assert result.requirements[0].source_document_uuid == "doc-001"
        assert result.requirements[1].requirement_id == "REQ-002"

    @pytest.mark.asyncio
    async def test_empty_source_documents(self, mock_agent_registry):
        """Returns empty result for empty source documents list."""
        service = TraceabilityMatrixService(agent_registry=mock_agent_registry)

        result = await service.extract_requirements([], company_id=1)

        assert not result.failed
        assert result.requirements == []
        assert result.metadata == []

    @pytest.mark.asyncio
    async def test_no_text_extracted(
        self, mock_inference_client, mock_agent_registry
    ):
        """Records failure when no text can be extracted from document."""
        mock_ks = MagicMock()
        mock_ks.hybrid_search.return_value = ([], 0)

        service = TraceabilityMatrixService(
            knowledge_service=mock_ks,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-empty", "document_id": 1}],
            company_id=1,
        )

        assert not result.failed
        assert result.requirements == []
        assert len(result.metadata) == 1
        assert not result.metadata[0].success
        assert result.metadata[0].error == "No text content extracted"

    @pytest.mark.asyncio
    async def test_inference_unavailable_marks_failed(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Marks result as failed when inference is unavailable after retries."""
        from alcoabase.services.inference_client import InferenceConnectionError

        mock_client = AsyncMock()
        mock_client.chat_completion.side_effect = InferenceConnectionError(
            "Cannot connect to vLLM", endpoint="/v1/chat/completions"
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        assert result.failed
        assert result.failure_phase == "extracting_requirements"
        assert "unavailable" in result.failure_message.lower() or "connect" in result.failure_message.lower()

    @pytest.mark.asyncio
    async def test_inference_503_retries_then_fails(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Retries on HTTP 503 with exponential backoff, then marks failed."""
        from alcoabase.services.inference_client import InferenceError

        mock_client = AsyncMock()
        mock_client.chat_completion.side_effect = InferenceError(
            "Service unavailable",
            status_code=503,
            endpoint="/v1/chat/completions",
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        assert result.failed
        assert result.failure_phase == "extracting_requirements"
        # Should have retried 3 times
        assert mock_client.chat_completion.call_count == 3

    @pytest.mark.asyncio
    async def test_inference_429_retries_then_fails(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Retries on HTTP 429 with exponential backoff, then marks failed."""
        from alcoabase.services.inference_client import InferenceError

        mock_client = AsyncMock()
        mock_client.chat_completion.side_effect = InferenceError(
            "Too many requests",
            status_code=429,
            endpoint="/v1/chat/completions",
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        assert result.failed
        assert mock_client.chat_completion.call_count == 3

    @pytest.mark.asyncio
    async def test_inference_timeout_records_timeout_event(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Records timeout event when extraction exceeds 120s."""
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_client = AsyncMock()
        mock_client.chat_completion.side_effect = InferenceTimeoutError(
            "Request timed out after 120s",
            endpoint="/v1/chat/completions",
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        # Timeout is per-document, not a total failure
        assert not result.failed
        assert len(result.metadata) == 1
        assert result.metadata[0].timeout
        assert "timed out" in result.metadata[0].error.lower()

    @pytest.mark.asyncio
    async def test_truncates_requirement_text_to_500_chars(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Truncates requirement_text to 500 characters."""
        long_text = "A" * 600
        mock_client = AsyncMock()
        mock_client.chat_completion.return_value = _make_requirements_response([
            {
                "requirement_id": "REQ-001",
                "requirement_text": long_text,
                "section_heading": "1.1",
                "acceptance_criteria": None,
            }
        ])

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        assert len(result.requirements) == 1
        assert len(result.requirements[0].requirement_text) == 500

    @pytest.mark.asyncio
    async def test_handles_markdown_wrapped_json(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Parses JSON wrapped in markdown code blocks."""
        response = '```json\n{"requirements": [{"requirement_id": "REQ-001", "requirement_text": "Test.", "section_heading": "1.1", "acceptance_criteria": null}]}\n```'
        mock_client = AsyncMock()
        mock_client.chat_completion.return_value = response

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        assert len(result.requirements) == 1
        assert result.requirements[0].requirement_id == "REQ-001"

    @pytest.mark.asyncio
    async def test_handles_invalid_json_gracefully(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Returns empty list when AI returns invalid JSON."""
        mock_client = AsyncMock()
        mock_client.chat_completion.return_value = "This is not valid JSON at all"

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        # Should not fail, just return empty requirements for that doc
        assert not result.failed
        assert result.requirements == []

    @pytest.mark.asyncio
    async def test_multiple_documents_extraction(
        self, mock_knowledge_service, mock_inference_client, mock_agent_registry
    ):
        """Extracts requirements from multiple source documents."""
        mock_inference_client.chat_completion.side_effect = [
            _make_requirements_response([
                {"requirement_id": "REQ-001", "requirement_text": "Req 1.", "section_heading": "1.1", "acceptance_criteria": None},
            ]),
            _make_requirements_response([
                {"requirement_id": "REQ-002", "requirement_text": "Req 2.", "section_heading": "2.1", "acceptance_criteria": None},
            ]),
        ]

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [
                {"document_uuid": "doc-001", "document_id": 1},
                {"document_uuid": "doc-002", "document_id": 2},
            ],
            company_id=1,
        )

        assert not result.failed
        assert len(result.requirements) == 2
        assert result.requirements[0].source_document_uuid == "doc-001"
        assert result.requirements[1].source_document_uuid == "doc-002"
        assert len(result.metadata) == 2

    @pytest.mark.asyncio
    async def test_no_inference_client_marks_failed(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Marks result as failed when InferenceClient is None."""
        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=None,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_requirements(
            [{"document_uuid": "doc-001", "document_id": 1}],
            company_id=1,
        )

        assert result.failed
        assert "not configured" in result.failure_message.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: extract_test_cases
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractTestCases:
    """Tests for extract_test_cases method."""

    @pytest.mark.asyncio
    async def test_successful_extraction(
        self, mock_knowledge_service, mock_inference_client, mock_agent_registry
    ):
        """Successfully extracts test cases from target documents."""
        mock_inference_client.chat_completion.return_value = (
            _make_test_cases_response([
                {
                    "test_case_id": "TC-001",
                    "test_description": "Verify user input validation.",
                    "expected_result": "Invalid input rejected",
                    "section_heading": "1.1 Input Tests",
                },
                {
                    "test_case_id": "IQ-002",
                    "test_description": "Verify audit logging.",
                    "expected_result": "Logs captured",
                    "section_heading": "2.1 Audit Tests",
                },
            ])
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_test_cases(
            [{"document_uuid": "doc-tgt-001", "document_id": 3}],
            company_id=1,
        )

        assert not result.failed
        assert len(result.test_cases) == 2
        assert result.test_cases[0].test_case_id == "TC-001"
        assert result.test_cases[0].target_document_uuid == "doc-tgt-001"
        assert result.test_cases[1].test_case_id == "IQ-002"

    @pytest.mark.asyncio
    async def test_empty_target_documents(self, mock_agent_registry):
        """Returns empty result for empty target documents list."""
        service = TraceabilityMatrixService(agent_registry=mock_agent_registry)

        result = await service.extract_test_cases([], company_id=1)

        assert not result.failed
        assert result.test_cases == []
        assert result.metadata == []

    @pytest.mark.asyncio
    async def test_inference_unavailable_marks_failed(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Marks result as failed when inference is unavailable."""
        from alcoabase.services.inference_client import InferenceConnectionError

        mock_client = AsyncMock()
        mock_client.chat_completion.side_effect = InferenceConnectionError(
            "Cannot connect", endpoint="/v1/chat/completions"
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_test_cases(
            [{"document_uuid": "doc-tgt-001", "document_id": 3}],
            company_id=1,
        )

        assert result.failed
        assert result.failure_phase == "extracting_test_cases"

    @pytest.mark.asyncio
    async def test_timeout_records_event(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Records timeout event when test case extraction exceeds 120s."""
        from alcoabase.services.inference_client import InferenceTimeoutError

        mock_client = AsyncMock()
        mock_client.chat_completion.side_effect = InferenceTimeoutError(
            "Timed out", endpoint="/v1/chat/completions"
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_test_cases(
            [{"document_uuid": "doc-tgt-001", "document_id": 3}],
            company_id=1,
        )

        assert not result.failed
        assert len(result.metadata) == 1
        assert result.metadata[0].timeout

    @pytest.mark.asyncio
    async def test_truncates_test_case_text_to_500_chars(
        self, mock_knowledge_service, mock_agent_registry
    ):
        """Truncates test_case_text to 500 characters."""
        long_text = "B" * 600
        mock_client = AsyncMock()
        mock_client.chat_completion.return_value = _make_test_cases_response([
            {
                "test_case_id": "TC-001",
                "test_description": long_text,
                "expected_result": None,
                "section_heading": "1.1",
            }
        ])

        service = TraceabilityMatrixService(
            knowledge_service=mock_knowledge_service,
            inference_client=mock_client,
            agent_registry=mock_agent_registry,
        )

        result = await service.extract_test_cases(
            [{"document_uuid": "doc-tgt-001", "document_id": 3}],
            company_id=1,
        )

        assert len(result.test_cases) == 1
        assert len(result.test_cases[0].test_case_text) == 500


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Agent Configuration
# ─────────────────────────────────────────────────────────────────────────────


class TestAgentConfig:
    """Tests for _get_agent_config method."""

    def test_loads_traceability_analyst(self, mock_agent_registry):
        """Loads Traceability Analyst archetype when available."""
        service = TraceabilityMatrixService(
            agent_registry=mock_agent_registry
        )

        prompt, temp, max_tok, fallback = service._get_agent_config()

        assert "Traceability Analyst" in prompt
        assert temp == 0.15
        assert max_tok == 4096
        assert not fallback

    def test_falls_back_to_change_impact_analyst(self):
        """Falls back to Change Impact Analyst when Traceability Analyst missing."""
        registry = MagicMock()
        registry.list_archetypes.return_value = [
            {
                "archetype": "Change Impact Analyst",
                "name": "Change Impact Analyst",
                "system_prompt": "You are a Change Impact Analyst.",
                "contextual_tuning": {
                    "temperature": 0.2,
                    "max_tokens": 4096,
                },
            }
        ]

        service = TraceabilityMatrixService(agent_registry=registry)

        prompt, temp, max_tok, fallback = service._get_agent_config()

        assert "Traceability Analyst" in prompt  # suffix appended
        assert fallback

    def test_uses_defaults_when_no_registry(self):
        """Uses default config when agent registry is None."""
        service = TraceabilityMatrixService(agent_registry=None)

        prompt, temp, max_tok, fallback = service._get_agent_config()

        assert "Traceability Analyst" in prompt
        assert temp == 0.15
        assert max_tok == 4096
        assert not fallback

    def test_uses_defaults_on_registry_error(self):
        """Uses default config when registry raises an exception."""
        registry = MagicMock()
        registry.list_archetypes.side_effect = RuntimeError("Registry broken")

        service = TraceabilityMatrixService(agent_registry=registry)

        prompt, temp, max_tok, fallback = service._get_agent_config()

        assert temp == 0.15
        assert max_tok == 4096
        assert not fallback

    def test_schema_validation_failure_retains_defaults(self):
        """Rejects archetype and retains defaults when schema validation fails.

        Requirement 6.6: If YAML fails schema validation against
        agent-definition-v2.json, reject file, log validation error
        identifying failing field, retain previous valid configuration.
        """
        registry = MagicMock()
        # Return an archetype with invalid data (missing required fields)
        registry.list_archetypes.return_value = [
            {
                "archetype": "Traceability Analyst",
                "name": "Traceability Analyst",
                # Missing required fields: description, system_prompt,
                # dspy_modules, knowledge_scopes — will fail schema validation
                "contextual_tuning": {
                    "temperature": 0.15,
                    "max_tokens": 4096,
                },
            }
        ]

        service = TraceabilityMatrixService(agent_registry=registry)

        prompt, temp, max_tok, fallback = service._get_agent_config()

        # Should retain defaults since schema validation failed
        assert "Traceability Analyst" in prompt
        assert temp == 0.15
        assert max_tok == 4096
        assert not fallback  # Not a fallback, just default retention

    def test_schema_validation_passes_for_valid_archetype(self):
        """Loads archetype successfully when schema validation passes.

        Requirement 6.6: Valid archetypes should be loaded normally.
        """
        registry = MagicMock()
        registry.list_archetypes.return_value = [
            {
                "schema_version": "2.0",
                "archetype": "Traceability Analyst",
                "name": "Traceability Analyst",
                "description": "Specialized agent for traceability.",
                "agent_type": "review",
                "system_prompt": "You are a Traceability Analyst for GxP.",
                "dspy_modules": [
                    {"name": "requirement_extraction", "type": "ChainOfThought"}
                ],
                "knowledge_scopes": {"tags": ["Traceability"]},
                "target_document_tag": "All",
                "required_chapters": [
                    {"name": "Requirements", "required": True}
                ],
                "compliance_checklist": ["All requirements extracted"],
                "severity_rules": {
                    "critical": "Safety-critical",
                    "major": "Functional",
                    "minor": "Informational",
                    "informational": "Optional",
                },
                "contextual_tuning": {
                    "temperature": 0.15,
                    "max_tokens": 4096,
                },
            }
        ]

        service = TraceabilityMatrixService(agent_registry=registry)

        prompt, temp, max_tok, fallback = service._get_agent_config()

        assert prompt == "You are a Traceability Analyst for GxP."
        assert temp == 0.15
        assert max_tok == 4096
        assert not fallback

    def test_fallback_used_recorded_in_metadata(self):
        """Verifies fallback_used is available for metadata recording.

        Requirement 6.5: Record fallback event in job metadata under
        "fallback_used" field.
        """
        registry = MagicMock()
        registry.list_archetypes.return_value = [
            {
                "archetype": "Change Impact Analyst",
                "name": "Change Impact Analyst",
                "system_prompt": "You are a Change Impact Analyst.",
                "contextual_tuning": {
                    "temperature": 0.2,
                    "max_tokens": 4096,
                },
            }
        ]

        service = TraceabilityMatrixService(agent_registry=registry)

        _, _, _, fallback_used = service._get_agent_config()

        assert fallback_used is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Schema Validation
# ─────────────────────────────────────────────────────────────────────────────


class TestArchetypeSchemaValidation:
    """Tests for _validate_archetype_schema method."""

    def test_valid_archetype_returns_no_errors(self):
        """Valid archetype data passes schema validation."""
        service = TraceabilityMatrixService()

        valid_data = {
            "schema_version": "2.0",
            "archetype": "Traceability Analyst",
            "name": "Traceability Analyst",
            "description": "Specialized agent for traceability.",
            "agent_type": "review",
            "system_prompt": "You are a Traceability Analyst.",
            "dspy_modules": [
                {"name": "requirement_extraction", "type": "ChainOfThought"}
            ],
            "knowledge_scopes": {"tags": ["Traceability"]},
            "target_document_tag": "All",
            "required_chapters": [
                {"name": "Requirements", "required": True}
            ],
            "compliance_checklist": ["All requirements extracted"],
            "severity_rules": {
                "critical": "Safety-critical",
                "major": "Functional",
                "minor": "Informational",
                "informational": "Optional",
            },
        }

        errors = service._validate_archetype_schema(valid_data)
        assert errors == []

    def test_missing_required_field_returns_error(self):
        """Missing required field produces validation error identifying field."""
        service = TraceabilityMatrixService()

        # Missing 'name' which is required
        invalid_data = {
            "schema_version": "2.0",
            "archetype": "Traceability Analyst",
            "description": "Test.",
            "system_prompt": "Test prompt.",
            "dspy_modules": [{"name": "test", "type": "ChainOfThought"}],
            "knowledge_scopes": {"tags": ["Test"]},
        }

        errors = service._validate_archetype_schema(invalid_data)
        assert len(errors) > 0
        # Should identify the failing field
        assert any("name" in e.lower() for e in errors)

    def test_invalid_schema_version_returns_error(self):
        """Invalid schema_version produces validation error."""
        service = TraceabilityMatrixService()

        invalid_data = {
            "schema_version": "3.0",  # Invalid — only "2.0" allowed
            "archetype": "Traceability Analyst",
            "name": "Traceability Analyst",
            "description": "Test.",
            "system_prompt": "Test prompt.",
            "dspy_modules": [{"name": "test", "type": "ChainOfThought"}],
            "knowledge_scopes": {"tags": ["Test"]},
        }

        errors = service._validate_archetype_schema(invalid_data)
        assert len(errors) > 0
        assert any("schema_version" in e for e in errors)

    def test_invalid_temperature_returns_error(self):
        """Temperature outside valid range produces validation error."""
        service = TraceabilityMatrixService()

        invalid_data = {
            "schema_version": "2.0",
            "archetype": "Traceability Analyst",
            "name": "Traceability Analyst",
            "description": "Test.",
            "agent_type": "review",
            "system_prompt": "Test prompt.",
            "dspy_modules": [{"name": "test", "type": "ChainOfThought"}],
            "knowledge_scopes": {"tags": ["Test"]},
            "target_document_tag": "All",
            "required_chapters": [{"name": "R", "required": True}],
            "compliance_checklist": ["Check"],
            "severity_rules": {
                "critical": "C",
                "major": "M",
                "minor": "m",
                "informational": "i",
            },
            "contextual_tuning": {
                "temperature": 5.0,  # Invalid — max is 2.0
            },
        }

        errors = service._validate_archetype_schema(invalid_data)
        assert len(errors) > 0
        assert any("temperature" in e for e in errors)

    def test_review_agent_missing_required_chapters_returns_error(self):
        """Review agent without required_chapters produces validation error."""
        service = TraceabilityMatrixService()

        invalid_data = {
            "schema_version": "2.0",
            "archetype": "Traceability Analyst",
            "name": "Traceability Analyst",
            "description": "Test.",
            "agent_type": "review",
            "system_prompt": "Test prompt.",
            "dspy_modules": [{"name": "test", "type": "ChainOfThought"}],
            "knowledge_scopes": {"tags": ["Test"]},
            # Missing target_document_tag, required_chapters,
            # compliance_checklist, severity_rules — required for review agents
        }

        errors = service._validate_archetype_schema(invalid_data)
        assert len(errors) > 0
