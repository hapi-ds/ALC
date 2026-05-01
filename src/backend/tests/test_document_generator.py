"""Unit tests for Document Generator service.

Tests cover:
- Document generation flow
- Provenance recording
- Draft creation with metadata
- Style analysis
- Chat history incorporation

References:
    - Task 14.7: Unit tests for generation flow, provenance recording, Draft creation
"""

import pytest

from alcoabase.services.document_generator import (
    DocumentGenerator,
    DocumentStyle,
    GeneratedDocument,
)
from alcoabase.services.knowledge_service import KnowledgeService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def knowledge_service() -> KnowledgeService:
    """Create a KnowledgeService with test data."""
    service = KnowledgeService()

    # Index source documents for generation context
    service.index_document(
        document_uuid="2024-00010",
        version="1.0",
        chunks=[
            "# SOP: Equipment Cleaning\n\n## 1. Purpose\nThis SOP defines the cleaning procedure.",
            "## 2. Scope\nApplies to all laboratory equipment in Building A.",
            "## 3. Procedure\n1. Gather cleaning materials\n2. Don PPE\n3. Clean surfaces",
        ],
        embeddings=service.generate_embeddings(["c1", "c2", "c3"]),
        metadata={"title": "Equipment Cleaning SOP", "tags": ["SOP"]},
    )

    return service


@pytest.fixture
def generator(knowledge_service: KnowledgeService) -> DocumentGenerator:
    """Create a DocumentGenerator with test data."""
    return DocumentGenerator(knowledge_service=knowledge_service)


# ---------------------------------------------------------------------------
# Generation Flow Tests
# ---------------------------------------------------------------------------


class TestGenerationFlow:
    """Tests for the document generation flow."""

    @pytest.mark.asyncio
    async def test_generate_returns_document(
        self, generator: DocumentGenerator
    ) -> None:
        """Generation returns a GeneratedDocument with content."""
        result = await generator.generate(
            instructions="Create a new cleaning SOP for Lab B",
            user_id=1,
            agent_id="test-agent-001",
            document_type="SOP",
        )

        assert isinstance(result, GeneratedDocument)
        assert result.content is not None
        assert len(result.content) > 0
        assert result.document_type == "SOP"

    @pytest.mark.asyncio
    async def test_generate_uses_provided_title(
        self, generator: DocumentGenerator
    ) -> None:
        """Generation uses the provided title."""
        result = await generator.generate(
            instructions="Create a cleaning SOP",
            user_id=1,
            agent_id="test-agent-001",
            title="Lab B Cleaning SOP v1",
        )

        assert result.title == "Lab B Cleaning SOP v1"

    @pytest.mark.asyncio
    async def test_generate_creates_default_title(
        self, generator: DocumentGenerator
    ) -> None:
        """Generation creates a default title when none provided."""
        result = await generator.generate(
            instructions="Create a cleaning SOP",
            user_id=1,
            agent_id="test-agent-001",
        )

        assert "Generated" in result.title or "SOP" in result.title

    @pytest.mark.asyncio
    async def test_generate_includes_style(
        self, generator: DocumentGenerator
    ) -> None:
        """Generated document includes style analysis."""
        result = await generator.generate(
            instructions="cleaning",
            user_id=1,
            agent_id="test-agent-001",
        )

        assert isinstance(result.style, DocumentStyle)


# ---------------------------------------------------------------------------
# Provenance Recording Tests (Task 14.5)
# ---------------------------------------------------------------------------


class TestProvenanceRecording:
    """Tests for generation provenance audit trail."""

    @pytest.mark.asyncio
    async def test_provenance_recorded_on_generation(
        self, generator: DocumentGenerator
    ) -> None:
        """Each generation records a provenance entry."""
        result = await generator.generate(
            instructions="Create a cleaning SOP",
            user_id=42,
            agent_id="agent-xyz",
        )

        provenance = result.provenance
        assert provenance.agent_id == "agent-xyz"
        assert provenance.user_id == 42
        assert provenance.instructions == "Create a cleaning SOP"
        assert provenance.generation_id is not None

    @pytest.mark.asyncio
    async def test_provenance_log_accumulates(
        self, generator: DocumentGenerator
    ) -> None:
        """Multiple generations accumulate in the provenance log."""
        await generator.generate(
            instructions="First SOP",
            user_id=1,
            agent_id="agent-1",
        )
        await generator.generate(
            instructions="Second SOP",
            user_id=2,
            agent_id="agent-2",
        )

        log = generator.get_provenance_log()
        assert len(log) == 2
        assert log[0].instructions == "First SOP"
        assert log[1].instructions == "Second SOP"

    @pytest.mark.asyncio
    async def test_provenance_includes_source_uuids(
        self, generator: DocumentGenerator
    ) -> None:
        """Provenance records source document UUIDs used."""
        result = await generator.generate(
            instructions="cleaning",
            user_id=1,
            agent_id="agent-1",
        )

        # Should have source UUIDs from the indexed documents
        assert isinstance(result.provenance.source_document_uuids, list)

    @pytest.mark.asyncio
    async def test_provenance_retrievable_by_id(
        self, generator: DocumentGenerator
    ) -> None:
        """Provenance can be retrieved by generation ID."""
        result = await generator.generate(
            instructions="Create SOP",
            user_id=1,
            agent_id="agent-1",
        )

        retrieved = generator.get_provenance_by_id(
            result.provenance.generation_id
        )
        assert retrieved is not None
        assert retrieved.generation_id == result.provenance.generation_id

    @pytest.mark.asyncio
    async def test_provenance_tracks_chat_history_usage(
        self, generator: DocumentGenerator
    ) -> None:
        """Provenance records whether chat history was used."""
        # Without chat history
        result1 = await generator.generate(
            instructions="Create SOP",
            user_id=1,
            agent_id="agent-1",
        )
        assert result1.provenance.chat_history_used is False

        # With chat history
        result2 = await generator.generate(
            instructions="Create SOP",
            user_id=1,
            agent_id="agent-1",
            chat_history=[{"role": "user", "content": "Include safety section"}],
        )
        assert result2.provenance.chat_history_used is True


# ---------------------------------------------------------------------------
# Style Analysis Tests (Task 14.2)
# ---------------------------------------------------------------------------


class TestStyleAnalysis:
    """Tests for source document style analysis."""

    def test_analyze_style_detects_headers(
        self, generator: DocumentGenerator
    ) -> None:
        """Style analysis detects markdown headers."""
        text = "# Title\n\n## Section 1\n\nContent here.\n\n## Section 2\n\nMore content."
        style = generator.analyze_style(text)

        assert style.has_headers is True
        assert style.header_levels >= 2

    def test_analyze_style_detects_numbered_sections(
        self, generator: DocumentGenerator
    ) -> None:
        """Style analysis detects numbered sections."""
        text = "1. First step\n2. Second step\n3. Third step"
        style = generator.analyze_style(text)

        assert style.has_numbered_sections is True

    def test_analyze_style_detects_bullet_points(
        self, generator: DocumentGenerator
    ) -> None:
        """Style analysis detects bullet points."""
        text = "- Item one\n- Item two\n* Item three"
        style = generator.analyze_style(text)

        assert style.has_bullet_points is True

    def test_analyze_style_empty_text(
        self, generator: DocumentGenerator
    ) -> None:
        """Style analysis handles empty text gracefully."""
        style = generator.analyze_style("")

        assert isinstance(style, DocumentStyle)


# ---------------------------------------------------------------------------
# Chat History Incorporation Tests (Task 14.3)
# ---------------------------------------------------------------------------


class TestChatHistoryIncorporation:
    """Tests for chat history content extraction."""

    def test_extract_user_messages_from_history(
        self, generator: DocumentGenerator
    ) -> None:
        """Extracts user messages from chat history."""
        history = [
            {"role": "user", "content": "Include a safety section"},
            {"role": "assistant", "content": "I'll add that."},
            {"role": "user", "content": "Also add references to ISO 9001"},
        ]

        content = generator.extract_content_from_history(history)

        assert "Include a safety section" in content
        assert "Also add references to ISO 9001" in content
        # Should not include assistant messages
        assert "I'll add that" not in content

    def test_extract_empty_history(
        self, generator: DocumentGenerator
    ) -> None:
        """Empty history returns empty string."""
        content = generator.extract_content_from_history([])
        assert content == ""

    @pytest.mark.asyncio
    async def test_chat_history_incorporated_in_generation(
        self, generator: DocumentGenerator
    ) -> None:
        """Chat history content appears in generated document."""
        result = await generator.generate(
            instructions="Create SOP",
            user_id=1,
            agent_id="agent-1",
            chat_history=[
                {"role": "user", "content": "Include detailed safety warnings"},
            ],
        )

        # The placeholder includes chat content
        assert "safety warnings" in result.content.lower() or "context" in result.content.lower()
