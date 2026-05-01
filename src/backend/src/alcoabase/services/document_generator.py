"""AI-Powered Document Generator service.

This module provides:
- Source document retrieval via KnowledgeService
- DSPy pipeline execution (placeholder)
- Style matching from source documents
- Chat history incorporation
- Draft creation with provenance tracking
- Generation audit trail recording

References:
    - Task 14: Document Generator (AI-Powered)
    - Design doc Section 10: Document Generator
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from alcoabase.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class GenerationProvenance:
    """Provenance record for a generated document.

    Attributes:
        generation_id: Unique ID for this generation event.
        source_document_uuids: Document-UUIDs used as source material.
        agent_id: ID of the agent definition used.
        user_id: ID of the user who triggered generation.
        timestamp: When the generation occurred.
        instructions: User-provided generation instructions.
        chat_history_used: Whether chat history was incorporated.
    """

    generation_id: str
    source_document_uuids: list[str]
    agent_id: str
    user_id: int
    timestamp: datetime
    instructions: str
    chat_history_used: bool


@dataclass
class DocumentStyle:
    """Analyzed style of a source document.

    Attributes:
        has_headers: Whether the document uses headers.
        header_levels: Number of header levels detected.
        has_numbered_sections: Whether sections are numbered.
        has_bullet_points: Whether bullet points are used.
        average_paragraph_length: Average paragraph length in words.
        tone: Detected tone (formal, technical, etc.).
    """

    has_headers: bool = True
    header_levels: int = 3
    has_numbered_sections: bool = True
    has_bullet_points: bool = True
    average_paragraph_length: int = 50
    tone: str = "formal_technical"


@dataclass
class GeneratedDocument:
    """Result of a document generation.

    Attributes:
        content: The generated document content.
        title: Generated or provided title.
        document_type: Type of document generated.
        style: Style applied to the document.
        provenance: Provenance record for audit trail.
        draft_uuid: Document-UUID of the created draft (if stored).
    """

    content: str
    title: str
    document_type: str
    style: DocumentStyle
    provenance: GenerationProvenance
    draft_uuid: str | None = None


# ---------------------------------------------------------------------------
# Document Generator
# ---------------------------------------------------------------------------


class DocumentGenerator:
    """AI-powered document generator using DSPy pipeline (placeholder).

    Retrieves relevant source documents via KnowledgeService, analyzes
    their structure and style, and generates new documents matching the
    source format. Generated documents are stored as Drafts.

    Attributes:
        _knowledge_service: Service for source document retrieval.
        _provenance_log: In-memory provenance audit trail.
    """

    def __init__(
        self,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        """Initialize the DocumentGenerator.

        Args:
            knowledge_service: KnowledgeService instance for retrieval.
                Creates a new instance if not provided.
        """
        self._knowledge_service = knowledge_service or KnowledgeService()
        self._provenance_log: list[GenerationProvenance] = []

    # -----------------------------------------------------------------------
    # Source Document Retrieval (Task 14.1)
    # -----------------------------------------------------------------------

    def retrieve_source_documents(
        self,
        query: str,
        user_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant source documents for generation context.

        Uses KnowledgeService hybrid search to find documents matching
        the generation query, filtered by user permissions (ABAC).

        Args:
            query: Search query describing desired content.
            user_id: ID of the user (for ABAC filtering).
            limit: Maximum number of source documents to retrieve.

        Returns:
            List of source document metadata and excerpts.
        """
        results = self._knowledge_service.hybrid_search(
            query=query,
            user_id=user_id,
            limit=limit,
        )

        sources: list[dict[str, Any]] = []
        for result in results:
            sources.append({
                "document_uuid": result.document_uuid,
                "title": result.title,
                "version": result.version,
                "excerpt": result.excerpt,
                "relevance_score": result.relevance_score,
            })

        return sources

    # -----------------------------------------------------------------------
    # Style Matching (Task 14.2)
    # -----------------------------------------------------------------------

    def analyze_style(self, source_text: str) -> DocumentStyle:
        """Analyze the structure and style of a source document.

        Examines headers, sections, formatting patterns, and tone
        to create a style profile for the generated document.

        Args:
            source_text: Text content of the source document.

        Returns:
            DocumentStyle describing the source document's structure.
        """
        lines = source_text.split("\n") if source_text else []

        # Detect headers (lines starting with # or all-caps short lines)
        header_lines = [
            line for line in lines
            if line.strip().startswith("#")
            or (line.strip().isupper() and 0 < len(line.strip()) < 80)
        ]
        has_headers = len(header_lines) > 0

        # Detect header levels
        header_levels = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                level = len(stripped) - len(stripped.lstrip("#"))
                header_levels = max(header_levels, level)

        # Detect numbered sections
        has_numbered = any(
            line.strip()[:3].replace(".", "").replace(" ", "").isdigit()
            for line in lines
            if line.strip()
        )

        # Detect bullet points
        has_bullets = any(
            line.strip().startswith(("-", "*", "•"))
            for line in lines
        )

        # Average paragraph length
        paragraphs = [p for p in source_text.split("\n\n") if p.strip()]
        avg_length = (
            sum(len(p.split()) for p in paragraphs) // max(len(paragraphs), 1)
        )

        return DocumentStyle(
            has_headers=has_headers,
            header_levels=max(header_levels, 1),
            has_numbered_sections=has_numbered,
            has_bullet_points=has_bullets,
            average_paragraph_length=avg_length,
            tone="formal_technical",
        )

    # -----------------------------------------------------------------------
    # Chat History Incorporation (Task 14.3)
    # -----------------------------------------------------------------------

    def extract_content_from_history(
        self, chat_history: list[dict[str, str]]
    ) -> str:
        """Extract user-directed content from conversation history.

        Parses chat history to identify content instructions, preferences,
        and specific text the user wants included in the generated document.

        Args:
            chat_history: List of message dicts with "role" and "content" keys.

        Returns:
            Extracted content instructions as a single string.
        """
        if not chat_history:
            return ""

        user_messages = [
            msg["content"]
            for msg in chat_history
            if msg.get("role") == "user"
        ]

        return "\n".join(user_messages)

    # -----------------------------------------------------------------------
    # Document Generation (Task 14.1 + 14.4)
    # -----------------------------------------------------------------------

    async def generate(
        self,
        instructions: str,
        user_id: int,
        agent_id: str,
        document_type: str = "SOP",
        title: str | None = None,
        chat_history: list[dict[str, str]] | None = None,
    ) -> GeneratedDocument:
        """Generate a new document using the DSPy pipeline (placeholder).

        1. Retrieve relevant source documents via KnowledgeService
        2. Analyze source document style
        3. Incorporate chat history if provided
        4. Generate document content via DSPy (placeholder)
        5. Record provenance in audit trail

        Args:
            instructions: User-provided generation instructions.
            user_id: ID of the user triggering generation.
            agent_id: ID of the Agent_Definition to use.
            document_type: Type of document to generate (default "SOP").
            title: Optional title for the generated document.
            chat_history: Optional conversation history for context.

        Returns:
            GeneratedDocument with content, style, and provenance.
        """
        # Step 1: Retrieve source documents
        sources = self.retrieve_source_documents(
            query=instructions,
            user_id=user_id,
            limit=10,
        )
        source_uuids = [s["document_uuid"] for s in sources]

        # Step 2: Analyze style from source documents
        source_text = "\n\n".join(s.get("excerpt", "") for s in sources)
        style = self.analyze_style(source_text)

        # Step 3: Incorporate chat history
        chat_content = ""
        if chat_history:
            chat_content = self.extract_content_from_history(chat_history)

        # Step 4: Generate content (placeholder - DSPy pipeline)
        generated_title = title or f"Generated {document_type} - {datetime.now(UTC).strftime('%Y-%m-%d')}"
        content = self._placeholder_generate(
            instructions=instructions,
            style=style,
            source_text=source_text,
            chat_content=chat_content,
            document_type=document_type,
        )

        # Step 5: Record provenance (Task 14.5)
        provenance = GenerationProvenance(
            generation_id=str(uuid.uuid4()),
            source_document_uuids=source_uuids,
            agent_id=agent_id,
            user_id=user_id,
            timestamp=datetime.now(UTC),
            instructions=instructions,
            chat_history_used=bool(chat_history),
        )
        self._provenance_log.append(provenance)

        logger.info(
            "Generated document '%s' using agent %s with %d sources",
            generated_title,
            agent_id,
            len(source_uuids),
        )

        return GeneratedDocument(
            content=content,
            title=generated_title,
            document_type=document_type,
            style=style,
            provenance=provenance,
        )

    # -----------------------------------------------------------------------
    # Provenance Audit Trail (Task 14.5)
    # -----------------------------------------------------------------------

    def get_provenance_log(self) -> list[GenerationProvenance]:
        """Get the full provenance audit trail.

        Returns:
            List of all generation provenance records.
        """
        return list(self._provenance_log)

    def get_provenance_by_id(
        self, generation_id: str
    ) -> GenerationProvenance | None:
        """Get a specific provenance record by generation ID.

        Args:
            generation_id: The unique generation event ID.

        Returns:
            The provenance record, or None if not found.
        """
        for record in self._provenance_log:
            if record.generation_id == generation_id:
                return record
        return None

    # -----------------------------------------------------------------------
    # Placeholder Generation
    # -----------------------------------------------------------------------

    def _placeholder_generate(
        self,
        instructions: str,
        style: DocumentStyle,
        source_text: str,
        chat_content: str,
        document_type: str,
    ) -> str:
        """Placeholder document generation (DSPy pipeline stub).

        Will be replaced with real DSPy pipeline execution when
        Model_Manager (Task 18) provides LLM inference.

        Args:
            instructions: User generation instructions.
            style: Target document style.
            source_text: Source document excerpts.
            chat_content: Extracted chat history content.
            document_type: Type of document to generate.

        Returns:
            Placeholder generated document content.
        """
        sections = []

        if style.has_headers:
            sections.append(f"# {document_type}: [Generated Document]")
            sections.append("")

        sections.append("## 1. Purpose")
        sections.append(
            f"This {document_type} was generated based on the following "
            f"instructions: {instructions[:200]}"
        )
        sections.append("")

        sections.append("## 2. Scope")
        sections.append(
            "[Placeholder - Real content will be generated by DSPy pipeline "
            "via Model_Manager (Task 18)]"
        )
        sections.append("")

        sections.append("## 3. Procedure")
        sections.append(
            "[Placeholder - Procedural steps will be generated based on "
            "source document analysis]"
        )
        sections.append("")

        if chat_content:
            sections.append("## 4. Additional Context (from chat)")
            sections.append(
                f"User-provided context incorporated: {chat_content[:200]}"
            )
            sections.append("")

        sections.append("---")
        sections.append(
            f"Generated from {len(source_text.split())} words of source material."
        )

        return "\n".join(sections)
