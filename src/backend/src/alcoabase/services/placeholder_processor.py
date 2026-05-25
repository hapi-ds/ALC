"""Placeholder Processor for AI Document Generator.

Processes template placeholder markers ({{IDENTIFIER}} and {{IDENTIFIER:parameter}})
and generates appropriate content for each marker type using the InferenceClient
and knowledge base services.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10
"""

import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

from alcoabase.config import get_settings
from alcoabase.services.cross_reference import CrossReference, CrossReferenceService
from alcoabase.services.inference_client import InferenceClient
from alcoabase.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


@dataclass
class SectionGenerationContext:
    """Context provided to the LLM for generating a single section.

    Attributes:
        section_heading: The heading text of the section being generated.
        section_level: Heading level (1-4).
        section_position: 0-indexed position in the document.
        total_sections: Total number of sections in the template.
        preceding_sections_summary: Condensed summary of preceding sections (max 1000 tokens).
        knowledge_base_chunks: KB chunks ordered by relevance descending.
        reference_doc_excerpts: Excerpts from reference documents (prioritized before KB).
        placeholder_instructions: List of placeholder instructions for this section.
        cross_reference_map: Cross-reference map keyed by reference_type.
        generation_instructions: User-provided generation instructions.
        document_type_target: Target document type (e.g., "URS", "SOP").
    """

    section_heading: str
    section_level: int
    section_position: int
    total_sections: int
    preceding_sections_summary: str
    knowledge_base_chunks: list[dict[str, Any]] = field(default_factory=list)
    reference_doc_excerpts: list[dict[str, str]] = field(default_factory=list)
    placeholder_instructions: list[str] = field(default_factory=list)
    cross_reference_map: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    generation_instructions: str = ""
    document_type_target: str = ""


class PlaceholderProcessor:
    """Processes {{IDENTIFIER}} and {{IDENTIFIER:parameter}} markers in templates.

    Routes each placeholder marker to the appropriate content generation handler
    based on the marker type. Supports standard markers for section content,
    requirement lists, cross-references, tables, procedure steps, and risk
    assessments.

    Args:
        inference_client: Async HTTP client for vLLM inference.
        knowledge_service: KnowledgeService for document retrieval and search.
        cross_reference_service: CrossReferenceService for reference extraction.
    """

    STANDARD_MARKERS: ClassVar[set[str]] = {
        "SECTION_CONTENT",
        "REQUIREMENT_LIST",
        "CROSS_REF",
        "TABLE",
        "PROCEDURE_STEPS",
        "RISK_ASSESSMENT",
    }
    MAX_PLACEHOLDERS_PER_TEMPLATE: ClassVar[int] = 50

    def __init__(
        self,
        inference_client: InferenceClient,
        knowledge_service: KnowledgeService,
        cross_reference_service: CrossReferenceService,
    ) -> None:
        """Initialize PlaceholderProcessor.

        Args:
            inference_client: Async HTTP client for vLLM inference.
            knowledge_service: KnowledgeService for document retrieval and search.
            cross_reference_service: CrossReferenceService for reference extraction.
        """
        self._inference_client = inference_client
        self._knowledge_service = knowledge_service
        self._cross_reference_service = cross_reference_service

    async def process_placeholder(
        self,
        marker: str,
        parameter: str | None,
        section_context: SectionGenerationContext,
        cross_reference_map: dict[str, list[CrossReference]],
    ) -> str:
        """Route placeholder to appropriate handler based on marker type.

        If the marker is not recognized, falls back to SECTION_CONTENT behavior
        per Requirement 10.6.

        Args:
            marker: The placeholder identifier (e.g., "SECTION_CONTENT", "TABLE").
            parameter: Optional parameter string (e.g., description for TABLE).
            section_context: Context for the current section being generated.
            cross_reference_map: Cross-reference map from reference documents.

        Returns:
            Generated content string to replace the placeholder.
        """
        if marker == "SECTION_CONTENT":
            return await self.generate_section_content(section_context)

        elif marker == "REQUIREMENT_LIST":
            return await self.generate_requirement_list(
                section_context.reference_doc_excerpts,
                cross_reference_map,
            )

        elif marker == "CROSS_REF":
            document_type = parameter or section_context.document_type_target
            return await self.generate_cross_reference_section(
                document_type, cross_reference_map
            )

        elif marker == "TABLE":
            description = parameter or section_context.section_heading
            return await self.generate_table(description, section_context)

        elif marker == "PROCEDURE_STEPS":
            return await self.generate_procedure_steps(section_context)

        elif marker == "RISK_ASSESSMENT":
            return await self.generate_risk_assessment(section_context)

        else:
            # Requirement 10.6: Unrecognized markers fall back to SECTION_CONTENT
            logger.warning(
                "Unrecognized placeholder marker '%s', falling back to SECTION_CONTENT",
                marker,
            )
            return await self.generate_section_content(section_context)

    async def generate_section_content(
        self,
        context: SectionGenerationContext,
    ) -> str:
        """Generate 1-10 paragraphs of prose for a section.

        Uses the InferenceClient to generate body text based on the section
        heading, generation instructions, and knowledge base content.

        Requirement 10.10: Produces between 1 and 10 paragraphs of content
        appropriate to the section topic.

        Args:
            context: Section generation context with heading, KB chunks, etc.

        Returns:
            Generated prose content (1-10 paragraphs).
        """
        settings = get_settings()

        # Build context from KB chunks and reference excerpts
        kb_context = self._format_kb_context(context)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Technical Writer specializing in regulatory documentation. "
                    "Generate professional prose content for the specified section of a "
                    f"{context.document_type_target} document. "
                    "Write between 1 and 10 paragraphs that are clear, precise, and "
                    "appropriate for GxP-regulated environments. "
                    "Use the provided knowledge base content as source material. "
                    "Do not fabricate references or identifiers."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Section: {context.section_heading}\n"
                    f"Document Type: {context.document_type_target}\n"
                    f"Instructions: {context.generation_instructions}\n\n"
                    f"Preceding Context:\n{context.preceding_sections_summary}\n\n"
                    f"Knowledge Base Content:\n{kb_context}\n\n"
                    "Generate the section body text (1-10 paragraphs):"
                ),
            },
        ]

        response = await self._inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=messages,
            temperature=0.4,
            max_tokens=4096,
        )

        # Ensure output is between 1 and 10 paragraphs
        paragraphs = [p.strip() for p in response.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [response.strip()] if response.strip() else ["[Content pending]"]
        paragraphs = paragraphs[:10]

        return "\n\n".join(paragraphs)

    async def generate_requirement_list(
        self,
        reference_docs: list[dict[str, str]],
        cross_reference_map: dict[str, list[CrossReference]],
    ) -> str:
        """Generate a numbered list of requirements from reference documents.

        Requirement 10.2: Numbered list with requirement ID, text (max 500 chars),
        and source document reference. Maximum 200 items.

        Requirement 10.8: If no requirements found, inserts a notice.

        Args:
            reference_docs: List of reference document excerpts.
            cross_reference_map: Cross-reference map with extracted requirements.

        Returns:
            Formatted numbered requirement list or notice if none found.
        """
        requirements = cross_reference_map.get("requirement", [])

        if not requirements:
            return (
                "[No requirements were found in the specified reference documents "
                "or knowledge base for this context.]"
            )

        # Cap at 200 items per Requirement 10.2
        requirements = requirements[:200]

        lines: list[str] = []
        for idx, req in enumerate(requirements, start=1):
            # Truncate reference_text to 500 characters
            text = req.reference_text[:500] if req.reference_text else ""
            source = req.source_document_title or "Unknown Source"
            identifier = req.reference_identifier

            lines.append(
                f"{idx}. {identifier}: {text} (Source: {source})"
            )

        return "\n".join(lines)

    async def generate_cross_reference_section(
        self,
        document_type: str,
        cross_reference_map: dict[str, list[CrossReference]],
    ) -> str:
        """Generate a cross-reference section for the specified document type.

        Requirement 10.3 (via Requirement 3.3): Table if >= 5 items, list if < 5.
        Each entry includes reference_identifier, reference_text (first 150 chars),
        and source_document_title.

        Args:
            document_type: The document type to filter references for.
            cross_reference_map: Cross-reference map from reference documents.

        Returns:
            Formatted cross-reference section (table or list).
        """
        # Collect all references across all types
        all_refs: list[CrossReference] = []
        for ref_list in cross_reference_map.values():
            all_refs.extend(ref_list)

        # Filter by document type if it maps to a reference_type
        type_mapping = {
            "URS": "requirement",
            "SOP": "section",
            "WI": "section",
            "TC": "test_case",
            "TEST": "test_case",
        }

        target_type = type_mapping.get(document_type.upper())
        if target_type:
            filtered_refs = [r for r in all_refs if r.reference_type == target_type]
        else:
            # If no specific mapping, include all references
            filtered_refs = all_refs

        if not filtered_refs:
            return (
                f"[No cross-references found for document type '{document_type}'.]"
            )

        if len(filtered_refs) >= 5:
            # Format as table
            return self._format_cross_ref_table(filtered_refs)
        else:
            # Format as numbered list
            return self._format_cross_ref_list(filtered_refs)

    def _format_cross_ref_table(self, refs: list[CrossReference]) -> str:
        """Format cross-references as a markdown-style table.

        Args:
            refs: List of CrossReference objects to format.

        Returns:
            Table-formatted string with header and data rows.
        """
        lines: list[str] = [
            "| # | Reference ID | Description | Source Document |",
            "|---|---|---|---|",
        ]
        for idx, ref in enumerate(refs, start=1):
            text = ref.reference_text[:150] if ref.reference_text else ""
            # Escape pipe characters in text
            text = text.replace("|", "\\|")
            source = (ref.source_document_title or "Unknown").replace("|", "\\|")
            identifier = ref.reference_identifier.replace("|", "\\|")
            lines.append(f"| {idx} | {identifier} | {text} | {source} |")

        return "\n".join(lines)

    def _format_cross_ref_list(self, refs: list[CrossReference]) -> str:
        """Format cross-references as a numbered list.

        Args:
            refs: List of CrossReference objects to format.

        Returns:
            Numbered list string.
        """
        lines: list[str] = []
        for idx, ref in enumerate(refs, start=1):
            text = ref.reference_text[:150] if ref.reference_text else ""
            source = ref.source_document_title or "Unknown"
            lines.append(
                f"{idx}. {ref.reference_identifier}: {text} (Source: {source})"
            )
        return "\n".join(lines)

    async def generate_table(
        self,
        description: str,
        context: SectionGenerationContext,
    ) -> str:
        """Generate a table with header row and 2-50 data rows.

        Requirement 10.3: Description parameter (max 200 chars) guides column
        structure. Header row + 2-50 data rows, max 8 columns.

        Args:
            description: Description guiding the table content (max 200 chars).
            context: Section generation context for KB and instructions.

        Returns:
            Markdown-formatted table string.
        """
        settings = get_settings()

        # Truncate description to 200 characters
        description = description[:200]

        kb_context = self._format_kb_context(context)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Technical Writer generating tables for regulatory documents. "
                    "Generate a markdown table with a header row and between 2 and 50 data rows. "
                    "Use a maximum of 8 columns. The table should be relevant to the section "
                    "context and document type. Output ONLY the markdown table, no other text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Table Description: {description}\n"
                    f"Section: {context.section_heading}\n"
                    f"Document Type: {context.document_type_target}\n"
                    f"Instructions: {context.generation_instructions}\n\n"
                    f"Knowledge Base Content:\n{kb_context}\n\n"
                    "Generate the markdown table:"
                ),
            },
        ]

        response = await self._inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=messages,
            temperature=0.4,
            max_tokens=4096,
        )

        # Validate and constrain the table output
        return self._constrain_table(response)

    def _constrain_table(self, table_text: str) -> str:
        """Constrain table to max 8 columns and 2-50 data rows.

        Args:
            table_text: Raw table text from LLM.

        Returns:
            Constrained table text.
        """
        lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]

        if not lines:
            return "| Column 1 | Column 2 |\n|---|---|\n| Data | Data |"

        # Filter to only table lines (containing pipes)
        table_lines = [line for line in lines if "|" in line]
        if not table_lines:
            return "| Column 1 | Column 2 |\n|---|---|\n| Data | Data |"

        # Separate header, separator, and data rows
        result_lines: list[str] = []
        data_row_count = 0

        for i, line in enumerate(table_lines):
            # Check if it's a separator line (contains only |, -, :, spaces)
            stripped = line.replace("|", "").replace("-", "").replace(":", "").strip()
            if not stripped:
                # Separator line
                result_lines.append(line)
                continue

            if i == 0:
                # Header row - constrain to 8 columns
                cells = [c.strip() for c in line.split("|")]
                # Remove empty strings from split
                cells = [c for c in cells if c or cells.index(c) not in (0, len(cells) - 1)]
                cells = cells[:8]
                result_lines.append("| " + " | ".join(cells) + " |")
            else:
                # Data row
                if data_row_count >= 50:
                    break
                cells = [c.strip() for c in line.split("|")]
                cells = [c for c in cells if c or cells.index(c) not in (0, len(cells) - 1)]
                cells = cells[:8]
                result_lines.append("| " + " | ".join(cells) + " |")
                data_row_count += 1

        # Ensure at least 2 data rows
        if data_row_count < 2:
            # Add placeholder rows
            header_cells = result_lines[0].count("|") - 1 if result_lines else 2
            for _ in range(2 - data_row_count):
                placeholder_row = "| " + " | ".join(["—"] * max(header_cells, 2)) + " |"
                result_lines.append(placeholder_row)

        return "\n".join(result_lines)

    async def generate_procedure_steps(
        self,
        context: SectionGenerationContext,
    ) -> str:
        """Generate numbered procedural steps from SOPs and Work Instructions.

        Requirement 10.4: Numbered steps with action description, responsible
        role, and acceptance criteria. Maximum 50 steps.

        Requirement 10.9: If no SOPs/WIs found, generates generic steps from
        section heading and generation instructions.

        Args:
            context: Section generation context with KB chunks and instructions.

        Returns:
            Formatted numbered procedure steps.
        """
        settings = get_settings()

        kb_context = self._format_kb_context(context)

        # Check if we have SOP/WI content in KB chunks
        has_sop_content = any(
            chunk.get("document_type", "").upper() in ("SOP", "WI", "WORK INSTRUCTION")
            for chunk in context.knowledge_base_chunks
        )

        if has_sop_content:
            source_note = "Derive steps from the SOP/Work Instruction content provided."
        else:
            source_note = (
                "No SOP or Work Instruction sources are available. "
                "Generate generic procedural steps based on the section heading "
                "and generation instructions."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Technical Writer generating procedural steps for "
                    "regulatory documents. Generate numbered steps (maximum 50) with:\n"
                    "- Step number\n"
                    "- Action description\n"
                    "- Responsible role (if determinable)\n"
                    "- Acceptance criteria (if applicable)\n\n"
                    "Format each step as:\n"
                    "N. [Action] - Role: [role] | Criteria: [criteria]\n\n"
                    f"{source_note}\n"
                    "Output ONLY the numbered steps, no other text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Section: {context.section_heading}\n"
                    f"Document Type: {context.document_type_target}\n"
                    f"Instructions: {context.generation_instructions}\n\n"
                    f"Source Content:\n{kb_context}\n\n"
                    "Generate the procedure steps:"
                ),
            },
        ]

        response = await self._inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=messages,
            temperature=0.4,
            max_tokens=4096,
        )

        # Constrain to max 50 steps
        return self._constrain_steps(response)

    def _constrain_steps(self, steps_text: str) -> str:
        """Constrain procedure steps to maximum 50.

        Args:
            steps_text: Raw steps text from LLM.

        Returns:
            Constrained steps text (max 50 steps).
        """
        lines = steps_text.strip().split("\n")
        result_lines: list[str] = []
        step_count = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                # Preserve blank lines between steps
                if result_lines:
                    result_lines.append("")
                continue

            # Check if line starts with a number (step line)
            if stripped and stripped[0].isdigit():
                step_count += 1
                if step_count > 50:
                    break
            result_lines.append(stripped)

        return "\n".join(result_lines)

    async def generate_risk_assessment(
        self,
        context: SectionGenerationContext,
    ) -> str:
        """Generate a risk assessment table.

        Requirement 10.5: Table with columns Risk ID, Risk Description,
        Severity (1-5), Likelihood (1-5), RPN (Severity × Likelihood),
        and Mitigation Strategy. Between 2 and 25 risk rows.

        Args:
            context: Section generation context with KB chunks and instructions.

        Returns:
            Formatted risk assessment table.
        """
        settings = get_settings()

        kb_context = self._format_kb_context(context)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Technical Writer generating risk assessments for "
                    "regulatory documents. Generate a risk assessment as a structured "
                    "list of risks. For each risk provide:\n"
                    "- Risk ID (e.g., RISK-001)\n"
                    "- Risk Description\n"
                    "- Severity (integer 1-5, where 5 is most severe)\n"
                    "- Likelihood (integer 1-5, where 5 is most likely)\n"
                    "- Mitigation Strategy\n\n"
                    "Generate between 2 and 25 risks relevant to the context.\n"
                    "Output each risk on a single line in this exact format:\n"
                    "RISK-NNN | Description | Severity | Likelihood | Mitigation\n\n"
                    "Output ONLY the risk lines, no headers or other text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Section: {context.section_heading}\n"
                    f"Document Type: {context.document_type_target}\n"
                    f"Instructions: {context.generation_instructions}\n\n"
                    f"Source Content:\n{kb_context}\n\n"
                    "Generate the risk assessment:"
                ),
            },
        ]

        response = await self._inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=messages,
            temperature=0.4,
            max_tokens=4096,
        )

        # Parse and format as a proper risk assessment table
        return self._format_risk_assessment_table(response)

    def _format_risk_assessment_table(self, raw_response: str) -> str:
        """Parse LLM response and format as a risk assessment table.

        Ensures Severity and Likelihood are 1-5, calculates RPN as S×L,
        and constrains to 2-25 rows.

        Args:
            raw_response: Raw text from LLM with risk data.

        Returns:
            Formatted markdown table with proper RPN calculation.
        """
        header = (
            "| Risk ID | Risk Description | Severity (1-5) | "
            "Likelihood (1-5) | RPN (S×L) | Mitigation Strategy |"
        )
        separator = "|---|---|---|---|---|---|"

        rows: list[str] = []
        lines = raw_response.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to parse pipe-delimited format
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 5:
                risk_id = parts[0]
                description = parts[1]
                severity = self._clamp_score(parts[2])
                likelihood = self._clamp_score(parts[3])
                rpn = severity * likelihood
                mitigation = parts[4] if len(parts) > 4 else "To be determined"

                rows.append(
                    f"| {risk_id} | {description} | {severity} | "
                    f"{likelihood} | {rpn} | {mitigation} |"
                )
            elif len(parts) >= 3:
                # Partial parse - try to extract what we can
                risk_id = parts[0] if parts else f"RISK-{len(rows) + 1:03d}"
                description = parts[1] if len(parts) > 1 else "Risk identified"
                severity = self._clamp_score(parts[2]) if len(parts) > 2 else 3
                likelihood = self._clamp_score(parts[3]) if len(parts) > 3 else 3
                rpn = severity * likelihood
                mitigation = parts[4] if len(parts) > 4 else "To be determined"

                rows.append(
                    f"| {risk_id} | {description} | {severity} | "
                    f"{likelihood} | {rpn} | {mitigation} |"
                )

            # Stop at 25 rows
            if len(rows) >= 25:
                break

        # Ensure minimum 2 rows
        if len(rows) < 2:
            while len(rows) < 2:
                idx = len(rows) + 1
                rows.append(
                    f"| RISK-{idx:03d} | Risk to be assessed | 3 | 3 | 9 | "
                    f"Mitigation to be determined |"
                )

        return "\n".join([header, separator] + rows)

    @staticmethod
    def _clamp_score(value: str) -> int:
        """Parse and clamp a severity/likelihood score to 1-5.

        Args:
            value: String representation of the score.

        Returns:
            Integer score clamped between 1 and 5.
        """
        try:
            # Extract first number from the string
            digits = "".join(c for c in value if c.isdigit())
            if digits:
                score = int(digits[:1])
                return max(1, min(5, score))
        except (ValueError, IndexError):
            pass
        return 3  # Default to medium if unparseable

    def is_recognized_marker(self, identifier: str) -> bool:
        """Check if identifier is a standard placeholder marker.

        Args:
            identifier: The marker identifier to check (e.g., "SECTION_CONTENT").

        Returns:
            True if the identifier is in STANDARD_MARKERS, False otherwise.
        """
        return identifier in self.STANDARD_MARKERS

    def _format_kb_context(self, context: SectionGenerationContext) -> str:
        """Format knowledge base chunks and reference excerpts into context string.

        Combines reference document excerpts (prioritized) and KB chunks
        into a single context string for the LLM prompt.

        Args:
            context: Section generation context containing KB and reference data.

        Returns:
            Formatted context string.
        """
        parts: list[str] = []

        # Reference doc excerpts are prioritized (Requirement 9.3)
        if context.reference_doc_excerpts:
            parts.append("--- Reference Documents ---")
            for excerpt in context.reference_doc_excerpts:
                title = excerpt.get("title", "Reference Document")
                text = excerpt.get("text", "")
                parts.append(f"[{title}]: {text}")

        # Knowledge base chunks ordered by relevance
        if context.knowledge_base_chunks:
            parts.append("--- Knowledge Base ---")
            for chunk in context.knowledge_base_chunks:
                title = chunk.get("title", "")
                text = chunk.get("excerpt", chunk.get("text", ""))
                score = chunk.get("relevance_score", 0)
                parts.append(f"[{title} (relevance: {score:.2f})]: {text}")

        if not parts:
            return "[No source content available]"

        return "\n".join(parts)
