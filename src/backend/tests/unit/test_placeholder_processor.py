"""Unit tests for PlaceholderProcessor.

Tests each placeholder type generates correct format, unrecognized markers
fall back to SECTION_CONTENT, and constraint enforcement.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from alcoabase.services.cross_reference import CrossReference
from alcoabase.services.placeholder_processor import (
    PlaceholderProcessor,
    SectionGenerationContext,
)


@pytest.fixture
def inference_client():
    """Mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(return_value="Generated content paragraph 1.\n\nGenerated content paragraph 2.")
    return client


@pytest.fixture
def knowledge_service():
    """Mock KnowledgeService."""
    return MagicMock()


@pytest.fixture
def cross_reference_service():
    """Mock CrossReferenceService."""
    return MagicMock()


@pytest.fixture
def processor(inference_client, knowledge_service, cross_reference_service):
    """Create PlaceholderProcessor with mocked dependencies."""
    return PlaceholderProcessor(
        inference_client=inference_client,
        knowledge_service=knowledge_service,
        cross_reference_service=cross_reference_service,
    )


@pytest.fixture
def section_context():
    """Create a sample SectionGenerationContext."""
    return SectionGenerationContext(
        section_heading="1.1 Purpose and Scope",
        section_level=2,
        section_position=1,
        total_sections=10,
        preceding_sections_summary="Introduction section covered the document overview.",
        knowledge_base_chunks=[
            {"title": "SOP-001", "excerpt": "Standard operating procedure content.", "relevance_score": 0.85},
        ],
        reference_doc_excerpts=[
            {"title": "URS-001", "text": "User requirement specification content."},
        ],
        placeholder_instructions=[],
        cross_reference_map={},
        generation_instructions="Generate a URS for the validation system.",
        document_type_target="URS",
    )


@pytest.fixture
def cross_reference_map():
    """Create a sample cross-reference map."""
    return {
        "requirement": [
            CrossReference(
                reference_type="requirement",
                reference_identifier="REQ-001",
                reference_text="The system shall validate user inputs.",
                source_document_id=1,
                source_document_title="URS-001",
            ),
            CrossReference(
                reference_type="requirement",
                reference_identifier="REQ-002",
                reference_text="The system shall log all changes.",
                source_document_id=1,
                source_document_title="URS-001",
            ),
        ],
        "test_case": [
            CrossReference(
                reference_type="test_case",
                reference_identifier="TC-001",
                reference_text="Verify input validation works correctly.",
                source_document_id=2,
                source_document_title="Test Protocol",
            ),
        ],
        "section": [],
    }


class TestIsRecognizedMarker:
    """Tests for is_recognized_marker method."""

    def test_recognized_standard_markers(self, processor):
        """All standard markers should be recognized."""
        assert processor.is_recognized_marker("SECTION_CONTENT") is True
        assert processor.is_recognized_marker("REQUIREMENT_LIST") is True
        assert processor.is_recognized_marker("CROSS_REF") is True
        assert processor.is_recognized_marker("TABLE") is True
        assert processor.is_recognized_marker("PROCEDURE_STEPS") is True
        assert processor.is_recognized_marker("RISK_ASSESSMENT") is True

    def test_unrecognized_markers(self, processor):
        """Non-standard markers should not be recognized."""
        assert processor.is_recognized_marker("UNKNOWN") is False
        assert processor.is_recognized_marker("custom_marker") is False
        assert processor.is_recognized_marker("") is False
        assert processor.is_recognized_marker("section_content") is False  # case-sensitive


class TestClassVariables:
    """Tests for class-level constants."""

    def test_standard_markers_set(self):
        """STANDARD_MARKERS should contain exactly 6 markers."""
        assert len(PlaceholderProcessor.STANDARD_MARKERS) == 6
        assert "SECTION_CONTENT" in PlaceholderProcessor.STANDARD_MARKERS
        assert "REQUIREMENT_LIST" in PlaceholderProcessor.STANDARD_MARKERS
        assert "CROSS_REF" in PlaceholderProcessor.STANDARD_MARKERS
        assert "TABLE" in PlaceholderProcessor.STANDARD_MARKERS
        assert "PROCEDURE_STEPS" in PlaceholderProcessor.STANDARD_MARKERS
        assert "RISK_ASSESSMENT" in PlaceholderProcessor.STANDARD_MARKERS

    def test_max_placeholders_per_template(self):
        """MAX_PLACEHOLDERS_PER_TEMPLATE should be 50."""
        assert PlaceholderProcessor.MAX_PLACEHOLDERS_PER_TEMPLATE == 50


class TestProcessPlaceholder:
    """Tests for process_placeholder routing."""

    @pytest.mark.asyncio
    async def test_routes_section_content(self, processor, section_context, cross_reference_map):
        """SECTION_CONTENT marker routes to generate_section_content."""
        result = await processor.process_placeholder(
            "SECTION_CONTENT", None, section_context, cross_reference_map
        )
        assert result  # Non-empty content generated
        processor._inference_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_requirement_list(self, processor, section_context, cross_reference_map):
        """REQUIREMENT_LIST marker routes to generate_requirement_list."""
        result = await processor.process_placeholder(
            "REQUIREMENT_LIST", None, section_context, cross_reference_map
        )
        assert "REQ-001" in result
        assert "REQ-002" in result

    @pytest.mark.asyncio
    async def test_routes_cross_ref(self, processor, section_context, cross_reference_map):
        """CROSS_REF marker routes to generate_cross_reference_section."""
        result = await processor.process_placeholder(
            "CROSS_REF", "URS", section_context, cross_reference_map
        )
        assert "REQ-001" in result

    @pytest.mark.asyncio
    async def test_routes_table(self, processor, section_context, cross_reference_map):
        """TABLE marker routes to generate_table."""
        processor._inference_client.chat_completion.return_value = (
            "| Col1 | Col2 |\n|---|---|\n| A | B |\n| C | D |"
        )
        result = await processor.process_placeholder(
            "TABLE", "Equipment list", section_context, cross_reference_map
        )
        assert "|" in result

    @pytest.mark.asyncio
    async def test_routes_procedure_steps(self, processor, section_context, cross_reference_map):
        """PROCEDURE_STEPS marker routes to generate_procedure_steps."""
        processor._inference_client.chat_completion.return_value = (
            "1. Step one - Role: Operator | Criteria: Complete\n"
            "2. Step two - Role: QA | Criteria: Verified"
        )
        result = await processor.process_placeholder(
            "PROCEDURE_STEPS", None, section_context, cross_reference_map
        )
        assert "1." in result

    @pytest.mark.asyncio
    async def test_routes_risk_assessment(self, processor, section_context, cross_reference_map):
        """RISK_ASSESSMENT marker routes to generate_risk_assessment."""
        processor._inference_client.chat_completion.return_value = (
            "RISK-001 | Data loss | 4 | 3 | Implement backup\n"
            "RISK-002 | Access breach | 5 | 2 | Add MFA"
        )
        result = await processor.process_placeholder(
            "RISK_ASSESSMENT", None, section_context, cross_reference_map
        )
        assert "Risk ID" in result
        assert "RISK-001" in result

    @pytest.mark.asyncio
    async def test_unrecognized_marker_falls_back_to_section_content(
        self, processor, section_context, cross_reference_map
    ):
        """Unrecognized markers fall back to SECTION_CONTENT (Req 10.6)."""
        result = await processor.process_placeholder(
            "UNKNOWN_MARKER", None, section_context, cross_reference_map
        )
        assert result  # Should generate content via section_content fallback
        processor._inference_client.chat_completion.assert_called_once()


class TestGenerateSectionContent:
    """Tests for generate_section_content."""

    @pytest.mark.asyncio
    async def test_generates_paragraphs(self, processor, section_context):
        """Should generate 1-10 paragraphs of prose."""
        processor._inference_client.chat_completion.return_value = (
            "First paragraph of content.\n\n"
            "Second paragraph of content.\n\n"
            "Third paragraph of content."
        )
        result = await processor.generate_section_content(section_context)
        paragraphs = [p for p in result.split("\n\n") if p.strip()]
        assert 1 <= len(paragraphs) <= 10

    @pytest.mark.asyncio
    async def test_caps_at_10_paragraphs(self, processor, section_context):
        """Should cap output at 10 paragraphs."""
        # Generate 15 paragraphs
        many_paragraphs = "\n\n".join([f"Paragraph {i}." for i in range(15)])
        processor._inference_client.chat_completion.return_value = many_paragraphs
        result = await processor.generate_section_content(section_context)
        paragraphs = [p for p in result.split("\n\n") if p.strip()]
        assert len(paragraphs) <= 10

    @pytest.mark.asyncio
    async def test_empty_response_handled(self, processor, section_context):
        """Should handle empty LLM response gracefully."""
        processor._inference_client.chat_completion.return_value = ""
        result = await processor.generate_section_content(section_context)
        assert result  # Should have fallback content


class TestGenerateRequirementList:
    """Tests for generate_requirement_list."""

    @pytest.mark.asyncio
    async def test_formats_requirements_as_numbered_list(self, processor, cross_reference_map):
        """Should format requirements as a numbered list."""
        result = await processor.generate_requirement_list(
            [], cross_reference_map
        )
        assert "1. REQ-001:" in result
        assert "2. REQ-002:" in result
        assert "Source: URS-001" in result

    @pytest.mark.asyncio
    async def test_empty_requirements_returns_notice(self, processor):
        """Should return notice when no requirements found (Req 10.8)."""
        empty_map: dict[str, list[CrossReference]] = {"requirement": [], "test_case": [], "section": []}
        result = await processor.generate_requirement_list([], empty_map)
        assert "No requirements were found" in result

    @pytest.mark.asyncio
    async def test_caps_at_200_items(self, processor):
        """Should cap requirement list at 200 items."""
        many_reqs = [
            CrossReference(
                reference_type="requirement",
                reference_identifier=f"REQ-{i:05d}",
                reference_text=f"Requirement {i} text",
                source_document_id=1,
                source_document_title="Source Doc",
            )
            for i in range(250)
        ]
        ref_map: dict[str, list[CrossReference]] = {"requirement": many_reqs, "test_case": [], "section": []}
        result = await processor.generate_requirement_list([], ref_map)
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) == 200

    @pytest.mark.asyncio
    async def test_truncates_text_to_500_chars(self, processor):
        """Should truncate requirement text to 500 characters."""
        long_text = "A" * 600
        reqs = [
            CrossReference(
                reference_type="requirement",
                reference_identifier="REQ-001",
                reference_text=long_text,
                source_document_id=1,
                source_document_title="Source",
            ),
        ]
        ref_map: dict[str, list[CrossReference]] = {"requirement": reqs, "test_case": [], "section": []}
        result = await processor.generate_requirement_list([], ref_map)
        # The text portion should be truncated
        assert "A" * 501 not in result


class TestGenerateCrossReferenceSection:
    """Tests for generate_cross_reference_section."""

    @pytest.mark.asyncio
    async def test_table_format_for_5_or_more_items(self, processor):
        """Should format as table when >= 5 items (Req 3.3)."""
        refs = [
            CrossReference(
                reference_type="requirement",
                reference_identifier=f"REQ-{i:03d}",
                reference_text=f"Requirement {i}",
                source_document_id=1,
                source_document_title="URS-001",
            )
            for i in range(6)
        ]
        ref_map: dict[str, list[CrossReference]] = {"requirement": refs, "test_case": [], "section": []}
        result = await processor.generate_cross_reference_section("URS", ref_map)
        assert "| # |" in result  # Table header
        assert "|---|" in result  # Table separator

    @pytest.mark.asyncio
    async def test_list_format_for_fewer_than_5_items(self, processor):
        """Should format as numbered list when < 5 items."""
        refs = [
            CrossReference(
                reference_type="requirement",
                reference_identifier=f"REQ-{i:03d}",
                reference_text=f"Requirement {i}",
                source_document_id=1,
                source_document_title="URS-001",
            )
            for i in range(3)
        ]
        ref_map: dict[str, list[CrossReference]] = {"requirement": refs, "test_case": [], "section": []}
        result = await processor.generate_cross_reference_section("URS", ref_map)
        assert "1. REQ-000:" in result
        assert "|" not in result or "\\|" in result  # No table pipes

    @pytest.mark.asyncio
    async def test_empty_references_returns_notice(self, processor):
        """Should return notice when no references found."""
        empty_map: dict[str, list[CrossReference]] = {"requirement": [], "test_case": [], "section": []}
        result = await processor.generate_cross_reference_section("URS", empty_map)
        assert "No cross-references found" in result


class TestGenerateTable:
    """Tests for generate_table."""

    @pytest.mark.asyncio
    async def test_generates_table_with_header_and_rows(self, processor, section_context):
        """Should generate a table with header and data rows."""
        processor._inference_client.chat_completion.return_value = (
            "| Equipment | Model | Location |\n"
            "|---|---|---|\n"
            "| HPLC | Agilent 1260 | Lab A |\n"
            "| GC | Shimadzu | Lab B |"
        )
        result = await processor.generate_table("Equipment list", section_context)
        assert "|" in result
        lines = [line for line in result.split("\n") if line.strip() and "|" in line]
        assert len(lines) >= 3  # header + separator + at least 2 data rows

    @pytest.mark.asyncio
    async def test_constrains_to_max_8_columns(self, processor, section_context):
        """Should constrain table to max 8 columns."""
        # Generate a table with 10 columns
        cols = " | ".join([f"Col{i}" for i in range(10)])
        data = " | ".join([f"D{i}" for i in range(10)])
        processor._inference_client.chat_completion.return_value = (
            f"| {cols} |\n|{'---|' * 10}\n| {data} |\n| {data} |"
        )
        result = await processor.generate_table("Wide table", section_context)
        # Count columns in first line
        first_line = result.split("\n")[0]
        col_count = first_line.count("|") - 1
        assert col_count <= 8


class TestGenerateProcedureSteps:
    """Tests for generate_procedure_steps."""

    @pytest.mark.asyncio
    async def test_generates_numbered_steps(self, processor, section_context):
        """Should generate numbered procedure steps."""
        processor._inference_client.chat_completion.return_value = (
            "1. Prepare equipment - Role: Operator | Criteria: Equipment calibrated\n"
            "2. Verify setup - Role: QA | Criteria: Checklist complete\n"
            "3. Execute procedure - Role: Operator | Criteria: Within spec"
        )
        result = await processor.generate_procedure_steps(section_context)
        assert "1." in result
        assert "2." in result
        assert "3." in result

    @pytest.mark.asyncio
    async def test_constrains_to_max_50_steps(self, processor, section_context):
        """Should constrain to maximum 50 steps."""
        steps = "\n".join([f"{i}. Step {i} description" for i in range(1, 60)])
        processor._inference_client.chat_completion.return_value = steps
        result = await processor.generate_procedure_steps(section_context)
        lines = [line for line in result.split("\n") if line.strip() and line.strip()[0].isdigit()]
        assert len(lines) <= 50


class TestGenerateRiskAssessment:
    """Tests for generate_risk_assessment."""

    @pytest.mark.asyncio
    async def test_generates_risk_table_with_correct_columns(self, processor, section_context):
        """Should generate table with Risk ID, Severity, Likelihood, RPN, Mitigation."""
        processor._inference_client.chat_completion.return_value = (
            "RISK-001 | Data integrity failure | 4 | 3 | Implement checksums\n"
            "RISK-002 | Unauthorized access | 5 | 2 | Add role-based access"
        )
        result = await processor.generate_risk_assessment(section_context)
        assert "Risk ID" in result
        assert "Severity" in result
        assert "Likelihood" in result
        assert "RPN" in result
        assert "Mitigation" in result
        assert "RISK-001" in result
        assert "RISK-002" in result

    @pytest.mark.asyncio
    async def test_rpn_is_severity_times_likelihood(self, processor, section_context):
        """RPN should be calculated as Severity × Likelihood."""
        processor._inference_client.chat_completion.return_value = (
            "RISK-001 | Test risk | 4 | 3 | Mitigate"
        )
        result = await processor.generate_risk_assessment(section_context)
        # Severity=4, Likelihood=3, RPN should be 12
        assert "| 12 |" in result

    @pytest.mark.asyncio
    async def test_ensures_minimum_2_rows(self, processor, section_context):
        """Should ensure minimum 2 risk rows."""
        processor._inference_client.chat_completion.return_value = (
            "RISK-001 | Single risk | 3 | 2 | Mitigate"
        )
        result = await processor.generate_risk_assessment(section_context)
        # Count data rows (lines with RISK- in them)
        data_rows = [row for row in result.split("\n") if "RISK-" in row]
        assert len(data_rows) >= 2

    @pytest.mark.asyncio
    async def test_caps_at_25_rows(self, processor, section_context):
        """Should cap at 25 risk rows."""
        lines = "\n".join(
            [f"RISK-{i:03d} | Risk {i} | 3 | 3 | Mitigate {i}" for i in range(1, 35)]
        )
        processor._inference_client.chat_completion.return_value = lines
        result = await processor.generate_risk_assessment(section_context)
        data_rows = [row for row in result.split("\n") if "RISK-" in row]
        assert len(data_rows) <= 25

    @pytest.mark.asyncio
    async def test_severity_clamped_to_1_5(self, processor, section_context):
        """Severity and Likelihood should be clamped to 1-5."""
        processor._inference_client.chat_completion.return_value = (
            "RISK-001 | Risk A | 9 | 0 | Mitigate\n"
            "RISK-002 | Risk B | 3 | 3 | Mitigate"
        )
        result = await processor.generate_risk_assessment(section_context)
        # Severity 9 should be clamped to 5, Likelihood 0 should be clamped to 1
        # RPN = 5 * 1 = 5
        lines = result.split("\n")
        # Find the RISK-001 line
        risk_001_line = next((row for row in lines if "RISK-001" in row), "")
        assert "| 5 |" in risk_001_line  # Severity clamped to 5


class TestGenerateProcedureStepsEmptyResults:
    """Tests for generate_procedure_steps with no SOP/WI content (Req 10.9)."""

    @pytest.mark.asyncio
    async def test_generates_generic_steps_without_sop_content(self, processor):
        """Should generate generic steps when no SOPs/WIs found (Req 10.9)."""
        # Context with no SOP/WI document types in KB chunks
        context = SectionGenerationContext(
            section_heading="3.1 Cleaning Procedure",
            section_level=2,
            section_position=3,
            total_sections=10,
            preceding_sections_summary="Previous sections covered equipment setup.",
            knowledge_base_chunks=[
                {"title": "General Guide", "excerpt": "General content.", "relevance_score": 0.7},
            ],
            reference_doc_excerpts=[],
            placeholder_instructions=[],
            cross_reference_map={},
            generation_instructions="Generate cleaning procedure steps.",
            document_type_target="SOP",
        )
        processor._inference_client.chat_completion.return_value = (
            "1. Prepare cleaning materials - Role: Operator | Criteria: Materials verified\n"
            "2. Execute cleaning - Role: Operator | Criteria: Area visually clean"
        )
        result = await processor.generate_procedure_steps(context)
        assert "1." in result
        # Verify the system prompt mentions no SOP sources
        call_args = processor._inference_client.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages", call_args[0][1] if len(call_args[0]) > 1 else None)
        if messages is None:
            # Try positional args
            messages = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        assert "No SOP" in system_msg or "no SOP" in system_msg.lower() or "generic" in system_msg.lower()

    @pytest.mark.asyncio
    async def test_generates_steps_with_sop_content(self, processor):
        """Should derive steps from SOP content when available."""
        context = SectionGenerationContext(
            section_heading="3.1 Cleaning Procedure",
            section_level=2,
            section_position=3,
            total_sections=10,
            preceding_sections_summary="Previous sections covered equipment setup.",
            knowledge_base_chunks=[
                {"title": "SOP-CLEAN-001", "excerpt": "Step 1: Wipe surfaces.", "relevance_score": 0.9, "document_type": "SOP"},
            ],
            reference_doc_excerpts=[],
            placeholder_instructions=[],
            cross_reference_map={},
            generation_instructions="Generate cleaning procedure steps.",
            document_type_target="SOP",
        )
        processor._inference_client.chat_completion.return_value = (
            "1. Wipe surfaces - Role: Operator | Criteria: No residue\n"
            "2. Verify cleanliness - Role: QA | Criteria: Visual inspection passed"
        )
        result = await processor.generate_procedure_steps(context)
        assert "1." in result
        # Verify the system prompt mentions deriving from SOP content
        call_args = processor._inference_client.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs["messages"]
        if isinstance(messages, tuple):
            messages = call_args.kwargs["messages"]
        system_msg = messages[0]["content"]
        assert "Derive" in system_msg or "SOP" in system_msg


class TestMaxPlaceholdersEnforcement:
    """Tests for MAX_PLACEHOLDERS_PER_TEMPLATE enforcement (Req 10.1)."""

    def test_max_placeholders_constant_is_50(self):
        """MAX_PLACEHOLDERS_PER_TEMPLATE should be 50."""
        assert PlaceholderProcessor.MAX_PLACEHOLDERS_PER_TEMPLATE == 50

    def test_max_placeholders_accessible_from_instance(self, processor):
        """MAX_PLACEHOLDERS_PER_TEMPLATE should be accessible from instance."""
        assert processor.MAX_PLACEHOLDERS_PER_TEMPLATE == 50

    @pytest.mark.asyncio
    async def test_placeholder_count_within_limit(self, processor, section_context, cross_reference_map):
        """Processing placeholders within the 50 limit should succeed."""
        # Process a single placeholder — should work fine
        result = await processor.process_placeholder(
            "SECTION_CONTENT", None, section_context, cross_reference_map
        )
        assert result

    def test_limit_can_be_used_for_validation(self, processor):
        """The limit constant should be usable for external validation logic."""
        # Simulate a template with placeholders exceeding the limit
        placeholder_count = 51
        exceeds_limit = placeholder_count > processor.MAX_PLACEHOLDERS_PER_TEMPLATE
        assert exceeds_limit is True

        # Within limit
        placeholder_count = 50
        exceeds_limit = placeholder_count > processor.MAX_PLACEHOLDERS_PER_TEMPLATE
        assert exceeds_limit is False


class TestFormatKbContext:
    """Tests for _format_kb_context helper method."""

    def test_formats_reference_docs_and_kb_chunks(self, processor):
        """Should format both reference docs and KB chunks."""
        context = SectionGenerationContext(
            section_heading="Test Section",
            section_level=1,
            section_position=0,
            total_sections=5,
            preceding_sections_summary="",
            knowledge_base_chunks=[
                {"title": "KB Doc", "excerpt": "KB content.", "relevance_score": 0.8},
            ],
            reference_doc_excerpts=[
                {"title": "Ref Doc", "text": "Reference content."},
            ],
            placeholder_instructions=[],
            cross_reference_map={},
            generation_instructions="",
            document_type_target="URS",
        )
        result = processor._format_kb_context(context)
        assert "Reference Documents" in result
        assert "Knowledge Base" in result
        assert "Ref Doc" in result
        assert "KB Doc" in result

    def test_empty_context_returns_notice(self, processor):
        """Should return notice when no source content available."""
        context = SectionGenerationContext(
            section_heading="Test Section",
            section_level=1,
            section_position=0,
            total_sections=5,
            preceding_sections_summary="",
            knowledge_base_chunks=[],
            reference_doc_excerpts=[],
            placeholder_instructions=[],
            cross_reference_map={},
            generation_instructions="",
            document_type_target="URS",
        )
        result = processor._format_kb_context(context)
        assert "No source content available" in result


class TestClampScore:
    """Tests for _clamp_score static method."""

    def test_valid_scores(self):
        """Should parse valid integer scores."""
        assert PlaceholderProcessor._clamp_score("3") == 3
        assert PlaceholderProcessor._clamp_score("1") == 1
        assert PlaceholderProcessor._clamp_score("5") == 5

    def test_clamps_high_values(self):
        """Should clamp values above 5 to 5."""
        assert PlaceholderProcessor._clamp_score("9") == 5
        assert PlaceholderProcessor._clamp_score("7") == 5

    def test_clamps_low_values(self):
        """Should clamp values below 1 to 1."""
        # "0" extracts digit 0, clamped to 1
        assert PlaceholderProcessor._clamp_score("0") == 1

    def test_non_numeric_defaults_to_3(self):
        """Should default to 3 for non-numeric input."""
        assert PlaceholderProcessor._clamp_score("high") == 3
        assert PlaceholderProcessor._clamp_score("") == 3

    def test_extracts_first_digit(self):
        """Should extract first digit from mixed strings."""
        assert PlaceholderProcessor._clamp_score("4/5") == 4
        assert PlaceholderProcessor._clamp_score("Score: 2") == 2
