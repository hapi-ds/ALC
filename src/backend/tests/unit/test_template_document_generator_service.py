"""Unit tests for TemplateDocumentGeneratorService.

Tests section generation retry logic, 50 MB output limit with section-boundary
truncation, concurrent generation prevention, knowledge base empty results
failure, and reference document prioritization in context.

Requirements: 2.5, 2.6, 2.9, 2.11, 7.6
"""

import io
import zipfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from alcoabase.services.placeholder_processor import SectionGenerationContext
from alcoabase.services.template_document_generator import (
    MAX_OUTPUT_SIZE_BYTES,
    SECTION_FAILURE_PLACEHOLDER,
    SectionResult,
    TemplateDocumentGeneratorService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def inference_client():
    """Mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(
        return_value="Generated section content for testing purposes."
    )
    return client


@pytest.fixture
def knowledge_service():
    """Mock KnowledgeService."""
    svc = MagicMock()
    svc.hybrid_search = MagicMock(return_value=([], 0))
    svc.extract_text = MagicMock(return_value="Extracted text content.")
    return svc


@pytest.fixture
def storage_service():
    """Mock StorageService."""
    svc = AsyncMock()
    svc.upload_file = AsyncMock(return_value="output/doc.docx")
    svc.download_file = AsyncMock(return_value=b"mock docx bytes")
    return svc


@pytest.fixture
def job_tracker():
    """Mock JobTracker."""
    tracker = AsyncMock()
    tracker.create_job = AsyncMock()
    tracker.complete_job = AsyncMock()
    return tracker


@pytest.fixture
def template_analysis_service():
    """Mock TemplateAnalysisService."""
    return MagicMock()


@pytest.fixture
def agent_registry():
    """Mock AgentRegistryService."""
    return MagicMock()


@pytest.fixture
def session_factory(async_session):
    """Create a mock async session factory (async context manager).

    The service uses `async with self._session_factory() as session:`,
    so the factory call must return an async context manager.
    """
    factory = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=async_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = ctx
    return factory


@pytest.fixture
def service(
    session_factory,
    inference_client,
    knowledge_service,
    agent_registry,
    storage_service,
    job_tracker,
    template_analysis_service,
):
    """Create TemplateDocumentGeneratorService with mocked dependencies."""
    return TemplateDocumentGeneratorService(
        session_factory=session_factory,
        inference_client=inference_client,
        knowledge_service=knowledge_service,
        agent_registry=agent_registry,
        storage_service=storage_service,
        job_tracker=job_tracker,
        template_analysis_service=template_analysis_service,
    )


@pytest.fixture
def section_context():
    """Create a sample SectionGenerationContext."""
    return SectionGenerationContext(
        section_heading="1.1 Purpose",
        section_level=2,
        section_position=0,
        total_sections=5,
        preceding_sections_summary="",
        knowledge_base_chunks=[
            {
                "chunk_document_uuid": "doc-uuid-1",
                "title": "Source Doc",
                "excerpt": "Relevant content.",
                "text": "Relevant content.",
                "relevance_score": 0.85,
            }
        ],
        reference_doc_excerpts=[
            {"title": "Ref Doc", "text": "Reference content."}
        ],
        placeholder_instructions=[],
        cross_reference_map={},
        generation_instructions="Generate a URS document.",
        document_type_target="URS",
    )


# ---------------------------------------------------------------------------
# Test: Section Generation Retry Logic (Requirement 2.9)
# ---------------------------------------------------------------------------


class TestSectionGenerationRetry:
    """Tests for generate_section retry logic.

    Requirement 2.9: Retry once on failure, insert placeholder on second failure.
    """

    @pytest.mark.asyncio
    async def test_successful_generation_returns_content(
        self, service, section_context
    ):
        """First attempt succeeds — returns generated content."""
        service._inference_client.chat_completion.return_value = (
            "This is the generated section content."
        )

        result = await service.generate_section(section_context)

        assert result.heading == "1.1 Purpose"
        assert result.content == "This is the generated section content."
        assert result.generation_failed is False
        assert result.failure_reason is None
        service._inference_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_first_failure_succeeds(
        self, service, section_context
    ):
        """First attempt fails, retry succeeds — returns content from retry."""
        service._inference_client.chat_completion.side_effect = [
            RuntimeError("Connection timeout"),
            "Content from retry attempt.",
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.generate_section(section_context)

        assert result.content == "Content from retry attempt."
        assert result.generation_failed is False
        assert result.failure_reason is None
        assert service._inference_client.chat_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_placeholder_on_second_failure(
        self, service, section_context
    ):
        """Both attempts fail — inserts SECTION_FAILURE_PLACEHOLDER."""
        service._inference_client.chat_completion.side_effect = [
            RuntimeError("First failure"),
            RuntimeError("Second failure"),
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.generate_section(section_context)

        assert result.content == SECTION_FAILURE_PLACEHOLDER
        assert result.generation_failed is True
        assert "Second failure" in result.failure_reason
        assert service._inference_client.chat_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_placeholder_text_matches_constant(
        self, service, section_context
    ):
        """Placeholder text is exactly the defined constant."""
        service._inference_client.chat_completion.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.generate_section(section_context)

        assert result.content == "[GENERATION FAILED: Section requires manual completion]"

    @pytest.mark.asyncio
    async def test_token_count_zero_on_failure(
        self, service, section_context
    ):
        """Token count should be 0 when generation fails."""
        service._inference_client.chat_completion.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.generate_section(section_context)

        assert result.token_count == 0


# ---------------------------------------------------------------------------
# Test: 50 MB Output Limit with Section-Boundary Truncation (Requirement 2.6)
# ---------------------------------------------------------------------------


class TestOutputSizeLimit:
    """Tests for 50 MB output limit with section-boundary truncation.

    Requirement 2.6: Output capped at 50 MB, truncated at last complete section.
    """

    def test_max_output_size_constant(self):
        """MAX_OUTPUT_SIZE_BYTES should be 50 MB."""
        assert MAX_OUTPUT_SIZE_BYTES == 50 * 1024 * 1024

    def test_validate_output_docx_valid_zip(self, service):
        """Valid .docx (ZIP with [Content_Types].xml) passes validation."""
        # Create a minimal valid .docx-like ZIP
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
            zf.writestr("word/document.xml", "<document></document>")
        valid_bytes = buffer.getvalue()

        assert service.validate_output_docx(valid_bytes) is True

    def test_validate_output_docx_invalid_zip(self, service):
        """Invalid ZIP data fails validation."""
        assert service.validate_output_docx(b"not a zip file") is False

    def test_validate_output_docx_missing_content_types(self, service):
        """ZIP without [Content_Types].xml fails validation."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("word/document.xml", "<document></document>")
        invalid_bytes = buffer.getvalue()

        assert service.validate_output_docx(invalid_bytes) is False

    @pytest.mark.asyncio
    async def test_truncate_at_section_boundary_reduces_sections(self, service):
        """_truncate_at_section_boundary removes sections until under limit."""
        sections = [
            SectionResult(
                heading=f"Section {i}",
                content=f"Content for section {i}",
                token_count=100,
                inference_duration_ms=500,
            )
            for i in range(5)
        ]

        # Mock assemble_docx to return decreasing sizes
        call_count = [0]

        async def mock_assemble(*args, **kwargs):
            call_count[0] += 1
            # First call (4 sections) still too big, second call (3 sections) fits
            if call_count[0] == 1:
                return b"x" * (MAX_OUTPUT_SIZE_BYTES + 1)
            else:
                # Create a valid small docx
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    zf.writestr("[Content_Types].xml", "<Types></Types>")
                return buf.getvalue()

        service.assemble_docx = AsyncMock(side_effect=mock_assemble)

        from alcoabase.services.template_analysis import TemplateAnalysis

        result = await service._truncate_at_section_boundary(
            template_bytes=b"template",
            sections=sections,
            template_analysis=MagicMock(spec=TemplateAnalysis),
            title="Test Doc",
            company_name="Test Co",
            requesting_user_name="Test User",
        )

        # Should have called assemble_docx multiple times
        assert service.assemble_docx.call_count >= 2
        # Result should be the smaller output
        assert len(result) <= MAX_OUTPUT_SIZE_BYTES


# ---------------------------------------------------------------------------
# Test: Concurrent Generation Prevention (Requirement 7.6)
# ---------------------------------------------------------------------------


class TestConcurrentGenerationPrevention:
    """Tests for concurrent generation prevention.

    Requirement 7.6: Prevent concurrent jobs for same template_id + title.
    """

    @pytest.mark.asyncio
    async def test_concurrent_job_raises_runtime_error(
        self, service, session_factory
    ):
        """Should raise RuntimeError when concurrent job exists."""
        mock_session = AsyncMock()

        # First execute: template exists
        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.company_id = 1
        mock_template.template_analysis = {"total_sections": 3}
        mock_template.document_id = 10

        # Fourth execute: concurrent job exists
        mock_concurrent_job = MagicMock()
        mock_concurrent_job.job_id = "existing-job-123"

        # Build mock results
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = mock_template

        concurrent_result = MagicMock()
        concurrent_result.scalar_one_or_none.return_value = mock_concurrent_job

        # The session execute calls in order:
        # 1. template lookup
        # 2. concurrent job check
        mock_session.execute = AsyncMock(
            side_effect=[template_result, concurrent_result]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Make session factory return our mock session via async context manager
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx

        with pytest.raises(RuntimeError, match="Concurrent generation job already exists"):
            await service.request_generation(
                template_id=1,
                title="Test Document",
                generation_instructions="Generate a URS",
                output_folder_path="/output/",
                requesting_user_id=1,
                company_id=1,
                reference_document_ids=None,
            )

    @pytest.mark.asyncio
    async def test_no_concurrent_job_proceeds(self, service, session_factory):
        """Should proceed when no concurrent job exists."""
        mock_session = AsyncMock()

        mock_template = MagicMock()
        mock_template.id = 1
        mock_template.company_id = 1
        mock_template.template_analysis = {"total_sections": 3}
        mock_template.document_id = 10

        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = mock_template

        # No concurrent job
        no_concurrent_result = MagicMock()
        no_concurrent_result.scalar_one_or_none.return_value = None

        # document_uuid query
        doc_uuid_result = MagicMock()
        doc_uuid_result.scalar_one_or_none.return_value = "2025-00001"

        mock_session.execute = AsyncMock(
            side_effect=[template_result, no_concurrent_result, doc_uuid_result]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        # Make session factory return our mock session
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session_factory.return_value = ctx

        # Mock the Celery task dispatch (imported inside the function)
        with patch(
            "alcoabase.tasks.document_generation_tasks.generate_document_task"
        ) as mock_task:
            mock_task.delay = MagicMock()

            job_id = await service.request_generation(
                template_id=1,
                title="Test Document",
                generation_instructions="Generate a URS",
                output_folder_path="/output/",
                requesting_user_id=1,
                company_id=1,
                reference_document_ids=None,
            )

        assert job_id  # Should return a valid job_id string
        assert len(job_id) == 36  # UUID format


# ---------------------------------------------------------------------------
# Test: Knowledge Base Empty Results Fails Job (Requirement 2.11)
# ---------------------------------------------------------------------------


class TestKnowledgeBaseEmptyResults:
    """Tests for knowledge base empty results failure.

    Requirement 2.11: If KB returns no relevant content, job fails.
    """

    @pytest.mark.asyncio
    async def test_empty_kb_and_no_references_raises_value_error(self, service):
        """Should raise ValueError when KB returns no results and no references."""
        # Mock hybrid_search to return empty results
        service._knowledge_service.hybrid_search = MagicMock(
            return_value=([], 0)
        )

        result = await service.retrieve_knowledge_context(
            generation_instructions="Generate a URS",
            document_type_target="URS",
            reference_document_ids=None,
            company_id=1,
        )

        kb_chunks, reference_excerpts = result
        # Both should be empty
        assert kb_chunks == []
        assert reference_excerpts == []

    @pytest.mark.asyncio
    async def test_kb_results_below_relevance_threshold_treated_as_empty(
        self, service
    ):
        """KB results with relevance < 0.3 should be filtered out."""
        # Mock search results with low relevance
        low_relevance_result = MagicMock()
        low_relevance_result.relevance_score = 0.2
        low_relevance_result.document_uuid = "doc-1"
        low_relevance_result.title = "Low Relevance Doc"
        low_relevance_result.excerpt = "Some content"
        low_relevance_result.document_type = "SOP"

        service._knowledge_service.hybrid_search = MagicMock(
            return_value=([low_relevance_result], 1)
        )

        kb_chunks, reference_excerpts = await service.retrieve_knowledge_context(
            generation_instructions="Generate a URS",
            document_type_target="URS",
            reference_document_ids=None,
            company_id=1,
        )

        # Low relevance results should be filtered out
        assert kb_chunks == []

    @pytest.mark.asyncio
    async def test_kb_results_above_threshold_included(self, service):
        """KB results with relevance >= 0.3 should be included."""
        high_relevance_result = MagicMock()
        high_relevance_result.relevance_score = 0.85
        high_relevance_result.document_uuid = "doc-1"
        high_relevance_result.title = "Relevant Doc"
        high_relevance_result.excerpt = "Highly relevant content."
        high_relevance_result.document_type = "URS"

        service._knowledge_service.hybrid_search = MagicMock(
            return_value=([high_relevance_result], 1)
        )

        kb_chunks, _ = await service.retrieve_knowledge_context(
            generation_instructions="Generate a URS",
            document_type_target="URS",
            reference_document_ids=None,
            company_id=1,
        )

        assert len(kb_chunks) == 1
        assert kb_chunks[0]["title"] == "Relevant Doc"
        assert kb_chunks[0]["relevance_score"] == 0.85


# ---------------------------------------------------------------------------
# Test: Reference Document Prioritization in Context (Requirement 2.5)
# ---------------------------------------------------------------------------


class TestReferenceDocumentPrioritization:
    """Tests for reference document prioritization in context.

    Requirement 2.5: Reference documents prioritized over general KB results.
    """

    def test_build_section_prompt_places_references_before_kb(self, service):
        """Reference doc excerpts should appear before KB chunks in prompt."""
        context = SectionGenerationContext(
            section_heading="1.1 Purpose",
            section_level=2,
            section_position=0,
            total_sections=5,
            preceding_sections_summary="",
            knowledge_base_chunks=[
                {
                    "title": "KB Doc",
                    "excerpt": "KB content here.",
                    "relevance_score": 0.8,
                }
            ],
            reference_doc_excerpts=[
                {"title": "Primary Reference", "text": "Reference content here."}
            ],
            placeholder_instructions=[],
            cross_reference_map={},
            generation_instructions="Generate a URS.",
            document_type_target="URS",
        )

        messages = service.build_section_prompt(context)

        # Find the user message content
        user_msg = next(m for m in messages if m["role"] == "user")
        content = user_msg["content"]

        # Reference documents should appear before KB in the source material
        ref_pos = content.find("Primary Reference")
        kb_pos = content.find("KB Doc")

        assert ref_pos != -1, "Reference doc should be in prompt"
        assert kb_pos != -1, "KB doc should be in prompt"
        assert ref_pos < kb_pos, (
            "Reference documents should appear before KB chunks in prompt"
        )

    def test_build_section_prompt_labels_references_as_primary(self, service):
        """Reference docs should be labeled as 'Primary Sources' in prompt."""
        context = SectionGenerationContext(
            section_heading="2.1 Scope",
            section_level=2,
            section_position=1,
            total_sections=5,
            preceding_sections_summary="",
            knowledge_base_chunks=[],
            reference_doc_excerpts=[
                {"title": "URS-001", "text": "User requirements."}
            ],
            placeholder_instructions=[],
            cross_reference_map={},
            generation_instructions="Generate scope section.",
            document_type_target="URS",
        )

        messages = service.build_section_prompt(context)
        user_msg = next(m for m in messages if m["role"] == "user")

        assert "Primary Sources" in user_msg["content"] or "Reference Documents" in user_msg["content"]

    def test_manage_context_window_preserves_reference_ordering(self, service):
        """manage_context_window should preserve KB chunk relevance ordering."""
        preceding = [
            SectionResult(
                heading="Intro",
                content="Short intro.",
                token_count=10,
                inference_duration_ms=100,
            )
        ]
        kb_chunks = [
            {"title": "Doc A", "excerpt": "A content", "relevance_score": 0.9},
            {"title": "Doc B", "excerpt": "B content", "relevance_score": 0.7},
            {"title": "Doc C", "excerpt": "C content", "relevance_score": 0.5},
        ]

        _, trimmed = service.manage_context_window(preceding, kb_chunks)

        # Chunks should maintain their order (already sorted by relevance desc)
        assert trimmed[0]["title"] == "Doc A"
        assert trimmed[1]["title"] == "Doc B"
        assert trimmed[2]["title"] == "Doc C"


# ---------------------------------------------------------------------------
# Test: Context Window Management
# ---------------------------------------------------------------------------


class TestContextWindowManagement:
    """Tests for manage_context_window method."""

    def test_within_limit_returns_unchanged(self, service):
        """When within token limit, returns data unchanged."""
        preceding = [
            SectionResult(
                heading="Intro",
                content="Short.",
                token_count=5,
                inference_duration_ms=50,
            )
        ]
        kb_chunks = [
            {"title": "Doc", "excerpt": "Short text.", "relevance_score": 0.9}
        ]

        summary, chunks = service.manage_context_window(preceding, kb_chunks)

        assert "Intro" in summary
        assert len(chunks) == 1

    def test_exceeds_limit_truncates_preceding_and_chunks(self, service):
        """When exceeding limit, truncates preceding and keeps top 5 chunks."""
        # Create large preceding sections (each summary entry ~220 chars)
        preceding = [
            SectionResult(
                heading=f"Section {i}",
                content="x" * 5000,  # Large content
                token_count=1250,
                inference_duration_ms=500,
            )
            for i in range(20)
        ]
        # Create many KB chunks with large excerpts to exceed 6000 tokens total
        kb_chunks = [
            {
                "title": f"Doc {i}",
                "excerpt": "y" * 5000,
                "relevance_score": 0.9 - i * 0.05,
            }
            for i in range(10)
        ]

        summary, trimmed = service.manage_context_window(preceding, kb_chunks)

        # Should truncate preceding summary
        assert len(summary) <= 4000 + 3  # MAX_PRECEDING_SUMMARY_TOKENS * CHARS_PER_TOKEN + "..."
        # Should keep only top 5 chunks
        assert len(trimmed) == 5
        # Top chunks should be the most relevant
        assert trimmed[0]["title"] == "Doc 0"
        assert trimmed[4]["title"] == "Doc 4"

    def test_empty_preceding_sections(self, service):
        """Should handle empty preceding sections gracefully."""
        summary, chunks = service.manage_context_window([], [])

        assert summary == ""
        assert chunks == []


# ---------------------------------------------------------------------------
# Test: validate_output_docx edge cases
# ---------------------------------------------------------------------------


class TestValidateOutputDocx:
    """Additional edge case tests for validate_output_docx."""

    def test_empty_bytes_fails(self, service):
        """Empty bytes should fail validation."""
        assert service.validate_output_docx(b"") is False

    def test_corrupted_zip_fails(self, service):
        """Corrupted ZIP data should fail validation."""
        # Start with valid ZIP header but corrupt the rest
        assert service.validate_output_docx(b"PK\x03\x04corrupted") is False

    def test_valid_docx_structure_passes(self, service):
        """A properly structured .docx-like ZIP passes."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
            zf.writestr("word/document.xml", "<w:document></w:document>")
            zf.writestr("_rels/.rels", "<Relationships></Relationships>")
        valid_bytes = buffer.getvalue()

        assert service.validate_output_docx(valid_bytes) is True
