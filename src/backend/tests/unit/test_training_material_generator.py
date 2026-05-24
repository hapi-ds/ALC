"""Unit tests for TrainingMaterialGeneratorService.

Tests the core logic of the training material generator including:
- Document chunking for large content
- Material content parsing from LLM responses
- Approve/reject status transitions
- Generation prompt construction
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.training_material_generator import (
    DEFAULT_CHUNK_SIZE,
    TrainingMaterialGeneratorService,
)


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory."""
    session = AsyncMock()
    factory = AsyncMock(return_value=session)
    factory.__aenter__ = AsyncMock(return_value=session)
    factory.__aexit__ = AsyncMock(return_value=None)

    # Make the factory callable and return an async context manager
    mock_factory = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_cm
    mock_factory._session = session
    return mock_factory


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(return_value='{"content": {"summary": "Test"}, "learning_objectives": ["LO1"], "estimated_duration_minutes": 10}')
    return client


@pytest.fixture
def mock_agent_registry():
    """Create a mock AgentRegistryService."""
    registry = MagicMock()
    registry._load_archetype_raw = MagicMock(return_value={
        "archetype": "Educational Specialist",
        "system_prompt": "You are an Educational Specialist.",
        "contextual_tuning": {
            "temperature": 0.6,
            "max_tokens": 8192,
        },
    })
    return registry


@pytest.fixture
def mock_storage_service():
    """Create a mock StorageService."""
    return AsyncMock()


@pytest.fixture
def service(mock_session_factory, mock_inference_client, mock_agent_registry, mock_storage_service):
    """Create a TrainingMaterialGeneratorService with mocked dependencies."""
    return TrainingMaterialGeneratorService(
        session_factory=mock_session_factory,
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
        storage_service=mock_storage_service,
    )


class TestParseGenerationResponse:
    """Tests for _parse_generation_response method."""

    def test_parses_valid_json(self, service):
        """Valid JSON response is parsed correctly."""
        response = json.dumps({
            "content": {"summary": "Test summary"},
            "learning_objectives": ["Identify key steps"],
            "estimated_duration_minutes": 15,
        })
        result = service._parse_generation_response(response, "executive_summary")

        assert result["content"] == {"summary": "Test summary"}
        assert result["learning_objectives"] == ["Identify key steps"]
        assert result["estimated_duration_minutes"] == 15

    def test_parses_json_in_code_block(self, service):
        """JSON wrapped in markdown code blocks is parsed correctly."""
        response = '```json\n{"content": {"summary": "Test"}, "learning_objectives": [], "estimated_duration_minutes": 5}\n```'
        result = service._parse_generation_response(response, "executive_summary")

        assert result["content"] == {"summary": "Test"}

    def test_fallback_on_invalid_json(self, service):
        """Invalid JSON falls back to wrapped raw content."""
        response = "This is not JSON, just plain text."
        result = service._parse_generation_response(response, "executive_summary")

        assert result["content"] == {"summary": response}
        assert result["learning_objectives"] == []
        assert result["estimated_duration_minutes"] == 10

    def test_includes_changes_summary_when_present(self, service):
        """Changes summary is included when present in response."""
        response = json.dumps({
            "content": {"summary": "Updated"},
            "learning_objectives": [],
            "estimated_duration_minutes": 5,
            "changes_summary": "Section 3 was updated.",
        })
        result = service._parse_generation_response(response, "executive_summary")

        assert result["changes_summary"] == "Section 3 was updated."

    def test_defaults_when_fields_missing(self, service):
        """Missing fields get sensible defaults."""
        response = json.dumps({"content": {"steps": []}})
        result = service._parse_generation_response(response, "detailed_walkthrough")

        assert result["learning_objectives"] == []
        assert result["estimated_duration_minutes"] == 10


class TestSplitIntoChunks:
    """Tests for _split_into_chunks method."""

    def test_small_content_single_chunk(self, service):
        """Content smaller than chunk size stays as one chunk."""
        content = "Short document content."
        chunks = service._split_into_chunks(content)

        assert len(chunks) == 1
        assert chunks[0] == content

    def test_large_content_splits_at_paragraphs(self, service):
        """Large content is split at paragraph boundaries."""
        # Create content that exceeds chunk size
        paragraph = "A" * 10000
        content = f"{paragraph}\n\n{paragraph}\n\n{paragraph}"
        chunks = service._split_into_chunks(content)

        assert len(chunks) > 1
        # Each chunk should be within size limit
        for chunk in chunks:
            assert len(chunk) <= DEFAULT_CHUNK_SIZE

    def test_single_huge_paragraph_force_split(self, service):
        """A single paragraph larger than chunk size is force-split."""
        content = "B" * (DEFAULT_CHUNK_SIZE * 2 + 100)
        chunks = service._split_into_chunks(content)

        assert len(chunks) >= 2

    def test_empty_content_returns_single_chunk(self, service):
        """Empty content returns a single chunk."""
        chunks = service._split_into_chunks("")

        assert len(chunks) == 1


class TestMergeChunkedResults:
    """Tests for _merge_chunked_results method."""

    def test_single_result_returned_as_is(self, service):
        """Single partial result is returned unchanged."""
        partial = {
            "content": {"summary": "Test"},
            "learning_objectives": ["LO1"],
            "estimated_duration_minutes": 10,
        }
        result = service._merge_chunked_results([partial], "executive_summary")

        assert result == partial

    def test_empty_results_returns_defaults(self, service):
        """Empty partial results returns default structure."""
        result = service._merge_chunked_results([], "executive_summary")

        assert result["content"] == {}
        assert result["learning_objectives"] == []
        assert result["estimated_duration_minutes"] == 5

    def test_merges_learning_objectives_deduplicates(self, service):
        """Learning objectives are merged and deduplicated."""
        partials = [
            {"content": {"summary": "A"}, "learning_objectives": ["LO1", "LO2"], "estimated_duration_minutes": 5},
            {"content": {"summary": "B"}, "learning_objectives": ["LO2", "LO3"], "estimated_duration_minutes": 5},
        ]
        result = service._merge_chunked_results(partials, "executive_summary")

        assert len(result["learning_objectives"]) == 3
        assert "LO1" in result["learning_objectives"]
        assert "LO3" in result["learning_objectives"]

    def test_sums_estimated_durations(self, service):
        """Estimated durations are summed across chunks."""
        partials = [
            {"content": {"summary": "A"}, "learning_objectives": [], "estimated_duration_minutes": 10},
            {"content": {"summary": "B"}, "learning_objectives": [], "estimated_duration_minutes": 15},
        ]
        result = service._merge_chunked_results(partials, "executive_summary")

        assert result["estimated_duration_minutes"] == 25

    def test_merges_executive_summary_content(self, service):
        """Executive summary content sections are concatenated."""
        partials = [
            {"content": {"summary": "Part 1"}, "learning_objectives": [], "estimated_duration_minutes": 5},
            {"content": {"summary": "Part 2"}, "learning_objectives": [], "estimated_duration_minutes": 5},
        ]
        result = service._merge_chunked_results(partials, "executive_summary")

        assert "Part 1" in result["content"]["summary"]
        assert "Part 2" in result["content"]["summary"]

    def test_merges_safety_highlights_content(self, service):
        """Safety highlights are concatenated."""
        partials = [
            {"content": {"highlights": [{"category": "PPE"}]}, "learning_objectives": [], "estimated_duration_minutes": 5},
            {"content": {"highlights": [{"category": "Chemical"}]}, "learning_objectives": [], "estimated_duration_minutes": 5},
        ]
        result = service._merge_chunked_results(partials, "safety_highlights")

        assert len(result["content"]["highlights"]) == 2


class TestBuildGenerationPrompt:
    """Tests for _build_generation_prompt method."""

    def test_includes_material_type(self, service):
        """Prompt includes the material type."""
        prompt = service._build_generation_prompt(
            document_content="Test content",
            material_type="executive_summary",
        )
        assert "executive summary" in prompt

    def test_includes_document_content(self, service):
        """Prompt includes the source document content."""
        prompt = service._build_generation_prompt(
            document_content="Important SOP content here",
            material_type="key_takeaways",
        )
        assert "Important SOP content here" in prompt

    def test_includes_previous_content_when_provided(self, service):
        """Prompt includes previous version content for comparison."""
        prompt = service._build_generation_prompt(
            document_content="New content",
            material_type="executive_summary",
            previous_content="Old content",
        )
        assert "Old content" in prompt
        assert "changes_summary" in prompt

    def test_includes_context_note_when_chunking(self, service):
        """Prompt includes context note for chunked processing."""
        prompt = service._build_generation_prompt(
            document_content="Chunk content",
            material_type="executive_summary",
            context_note="This is section 1 of 3",
        )
        assert "section 1 of 3" in prompt


class TestBuildSystemPrompt:
    """Tests for _build_system_prompt method."""

    def test_uses_archetype_prompt(self, service):
        """Uses system prompt from archetype config."""
        config = {"system_prompt": "Custom archetype prompt"}
        result = service._build_system_prompt(config)

        assert result == "Custom archetype prompt"

    def test_fallback_when_no_config(self, service):
        """Falls back to default prompt when config is None."""
        result = service._build_system_prompt(None)

        assert "Educational Specialist" in result
        assert "JSON" in result

    def test_fallback_when_empty_prompt(self, service):
        """Falls back to default prompt when system_prompt is empty."""
        result = service._build_system_prompt({"system_prompt": ""})

        assert "Educational Specialist" in result


class TestGetTypeInstructions:
    """Tests for _get_type_instructions method."""

    def test_executive_summary_instructions(self, service):
        """Executive summary has appropriate instructions."""
        instructions = service._get_type_instructions("executive_summary")
        assert "concise" in instructions.lower()
        assert "summary" in instructions.lower()

    def test_detailed_walkthrough_instructions(self, service):
        """Detailed walkthrough has step-by-step instructions."""
        instructions = service._get_type_instructions("detailed_walkthrough")
        assert "step" in instructions.lower()

    def test_safety_highlights_instructions(self, service):
        """Safety highlights has safety-focused instructions."""
        instructions = service._get_type_instructions("safety_highlights")
        assert "safety" in instructions.lower()

    def test_unknown_type_returns_generic(self, service):
        """Unknown material type returns generic instructions."""
        instructions = service._get_type_instructions("unknown_type")
        assert "training content" in instructions.lower()


class TestWrapRawContent:
    """Tests for _wrap_raw_content method."""

    def test_wraps_executive_summary(self, service):
        """Executive summary wraps as summary dict."""
        result = service._wrap_raw_content("Raw text", "executive_summary")
        assert result == {"summary": "Raw text"}

    def test_wraps_detailed_walkthrough(self, service):
        """Detailed walkthrough wraps as steps list."""
        result = service._wrap_raw_content("Raw text", "detailed_walkthrough")
        assert "steps" in result
        assert len(result["steps"]) == 1

    def test_wraps_key_takeaways(self, service):
        """Key takeaways wraps as takeaways list."""
        result = service._wrap_raw_content("Raw text", "key_takeaways")
        assert result == {"takeaways": ["Raw text"]}

    def test_wraps_presentation_outline(self, service):
        """Presentation outline wraps as slides list."""
        result = service._wrap_raw_content("Raw text", "presentation_outline")
        assert "slides" in result

    def test_wraps_safety_highlights(self, service):
        """Safety highlights wraps as highlights list."""
        result = service._wrap_raw_content("Raw text", "safety_highlights")
        assert "highlights" in result

    def test_wraps_unknown_type(self, service):
        """Unknown type wraps as text dict."""
        result = service._wrap_raw_content("Raw text", "unknown")
        assert result == {"text": "Raw text"}


@pytest.mark.asyncio
class TestGenerateMaterialContent:
    """Tests for generate_material_content method."""

    async def test_generates_content_for_small_document(self, service, mock_inference_client):
        """Small documents are processed in a single LLM call."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "content": {"summary": "Generated summary"},
            "learning_objectives": ["Understand the process"],
            "estimated_duration_minutes": 12,
        })

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(model_chat_name="test-model")
            result = await service.generate_material_content(
                document_content="Short document content.",
                material_type="executive_summary",
            )

        assert result["content"] == {"summary": "Generated summary"}
        assert result["learning_objectives"] == ["Understand the process"]
        assert result["estimated_duration_minutes"] == 12
        mock_inference_client.chat_completion.assert_called_once()

    async def test_chunks_large_documents(self, service, mock_inference_client):
        """Large documents are chunked and processed in multiple calls."""
        # Create content larger than DEFAULT_CHUNK_SIZE
        large_content = ("A" * 10000 + "\n\n") * 5

        mock_inference_client.chat_completion.return_value = json.dumps({
            "content": {"summary": "Chunk result"},
            "learning_objectives": ["LO"],
            "estimated_duration_minutes": 5,
        })

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(model_chat_name="test-model")
            result = await service.generate_material_content(
                document_content=large_content,
                material_type="executive_summary",
            )

        # Should have made multiple calls
        assert mock_inference_client.chat_completion.call_count > 1
        assert "content" in result

    async def test_includes_previous_content_for_changes(self, service, mock_inference_client):
        """Previous content is included in prompt for change comparison."""
        mock_inference_client.chat_completion.return_value = json.dumps({
            "content": {"summary": "Updated"},
            "learning_objectives": [],
            "estimated_duration_minutes": 5,
            "changes_summary": "Section 2 updated",
        })

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(model_chat_name="test-model")
            result = await service.generate_material_content(
                document_content="New content",
                material_type="executive_summary",
                previous_content="Old content",
            )

        assert result.get("changes_summary") == "Section 2 updated"
        # Verify previous content was in the prompt
        call_args = mock_inference_client.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_message = messages[1]["content"]
        assert "Old content" in user_message
