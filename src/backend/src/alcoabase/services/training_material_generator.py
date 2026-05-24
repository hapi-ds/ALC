"""Training Material Generator service for AI-enhanced training ecosystem.

Produces structured educational content (summaries, walkthroughs, presentations,
safety highlights) from source documents using the Educational Specialist agent
archetype via the InferenceClient.

All generated materials start with status "pending_review" and require
coordinator approval before presentation to trainees.

References:
    - Design doc Section 2: Training Material Generator Service
    - Requirements 3.1–3.12: AI Training Material Generator
    - Educational Specialist archetype (5.1) provides system prompts
    - InferenceClient (4.3) handles all LLM inference calls
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.training_ecosystem import (
    ContentStatus,
    MaterialType,
    TrainingMaterial,
)
from alcoabase.services.agent_registry import AgentRegistryService
from alcoabase.services.inference_client import InferenceClient
from alcoabase.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# Maximum characters per chunk for document content that exceeds context window.
# Approximate token-to-char ratio is ~4 chars per token; with 8192 max_tokens
# for generation and ~6000 tokens for input context, we use ~24000 chars.
DEFAULT_CHUNK_SIZE = 24000


class TrainingMaterialGeneratorService:
    """AI-powered training material generation from documents.

    Generates structured educational content using the Educational Specialist
    agent archetype. Supports five material types: executive_summary,
    detailed_walkthrough, key_takeaways, presentation_outline, and
    safety_highlights.

    All generated materials are persisted with status "pending_review" and
    require coordinator approval before being served to trainees.

    Attributes:
        _session_factory: Async session factory for database access.
        _inference_client: Client for LLM inference via vLLM.
        _agent_registry: Service for loading archetype configurations.
        _storage_service: Service for retrieving document content from MinIO.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        inference_client: InferenceClient,
        agent_registry: AgentRegistryService,
        storage_service: StorageService,
    ) -> None:
        """Initialize the TrainingMaterialGeneratorService.

        Args:
            session_factory: Async session factory for database operations.
            inference_client: InferenceClient for LLM calls.
            agent_registry: AgentRegistryService for archetype config.
            storage_service: StorageService for MinIO document retrieval.
        """
        self._session_factory = session_factory
        self._inference_client = inference_client
        self._agent_registry = agent_registry
        self._storage_service = storage_service

    async def request_generation(
        self,
        document_id: int,
        document_version_id: int,
        company_id: int,
        material_types: list[str] | None = None,
    ) -> str:
        """Validate document and dispatch async material generation task.

        Verifies the document exists and belongs to the specified company,
        then dispatches a Celery task for background generation.

        Args:
            document_id: Source document ID.
            document_version_id: Specific version to generate materials from.
            company_id: Company scope for tenant isolation.
            material_types: Optional list of material types to generate.
                Defaults to all 5 types if not specified.

        Returns:
            Job ID string for tracking the async generation task.

        Raises:
            ValueError: If the document or version does not exist or does
                not belong to the specified company.
        """
        # Validate document exists and belongs to company
        async with self._session_factory() as session:
            doc_result = await session.execute(
                select(Document.id).where(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            if doc_result.scalar_one_or_none() is None:
                raise ValueError(
                    f"Document {document_id} not found for company {company_id}"
                )

            # Validate document version exists
            version_result = await session.execute(
                select(DocumentVersion.id).where(
                    DocumentVersion.id == document_version_id,
                    DocumentVersion.document_id == document_id,
                )
            )
            if version_result.scalar_one_or_none() is None:
                raise ValueError(
                    f"Document version {document_version_id} not found "
                    f"for document {document_id}"
                )

        # Default to all material types if not specified
        if material_types is None:
            material_types = [mt.value for mt in MaterialType]

        # Generate job_id and dispatch Celery task
        job_id = uuid.uuid4().hex

        from alcoabase.tasks.training_tasks import generate_training_materials

        generate_training_materials.delay(
            document_id=document_id,
            document_version_id=document_version_id,
            company_id=company_id,
            material_types=material_types,
            job_id=job_id,
        )

        logger.info(
            "Dispatched material generation job %s for document %d version %d",
            job_id,
            document_id,
            document_version_id,
        )

        return job_id

    async def get_materials(
        self,
        document_id: int,
        company_id: int,
        material_type: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[TrainingMaterial], int]:
        """Retrieve generated materials with filtering and pagination.

        Args:
            document_id: Source document ID to filter by.
            company_id: Company scope for tenant isolation.
            material_type: Optional filter by material type.
            status: Optional filter by content status.
            limit: Maximum number of results (default 20).
            offset: Number of results to skip (default 0).

        Returns:
            Tuple of (list of TrainingMaterial records, total count).
        """
        async with self._session_factory() as session:
            # Build base query
            base_filter = [
                TrainingMaterial.document_id == document_id,
                TrainingMaterial.company_id == company_id,
            ]

            if material_type is not None:
                base_filter.append(
                    TrainingMaterial.material_type == material_type
                )

            if status is not None:
                base_filter.append(TrainingMaterial.status == status)

            # Get total count
            count_query = select(func.count(TrainingMaterial.id)).where(
                *base_filter
            )
            total_result = await session.execute(count_query)
            total = total_result.scalar_one()

            # Get paginated results
            query = (
                select(TrainingMaterial)
                .where(*base_filter)
                .order_by(TrainingMaterial.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(query)
            materials = list(result.scalars().all())

            return materials, total

    async def approve_material(
        self,
        material_id: int,
        reviewer_id: int,
        company_id: int,
    ) -> TrainingMaterial:
        """Approve a training material after coordinator review.

        Material must be in pending_review status to be approved.

        Args:
            material_id: ID of the material to approve.
            reviewer_id: ID of the reviewing coordinator.
            company_id: Company scope for tenant isolation.

        Returns:
            Updated TrainingMaterial with approved status.

        Raises:
            ValueError: If material is not found, does not belong to the
                company, or is not in pending_review status.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TrainingMaterial).where(
                    TrainingMaterial.id == material_id,
                    TrainingMaterial.company_id == company_id,
                )
            )
            material = result.scalar_one_or_none()

            if material is None:
                raise ValueError(
                    f"Training material {material_id} not found "
                    f"for company {company_id}"
                )

            if material.status != ContentStatus.PENDING_REVIEW.value:
                raise ValueError(
                    f"Training material {material_id} is not pending review "
                    f"(current status: {material.status})"
                )

            material.status = ContentStatus.APPROVED.value
            material.reviewed_by = reviewer_id
            material.reviewed_at = datetime.now(UTC)

            await session.commit()
            await session.refresh(material)

            logger.info(
                "Training material %d approved by user %d",
                material_id,
                reviewer_id,
            )

            return material

    async def reject_material(
        self,
        material_id: int,
        reviewer_id: int,
        company_id: int,
    ) -> TrainingMaterial:
        """Reject a training material after coordinator review.

        Material must be in pending_review status to be rejected.

        Args:
            material_id: ID of the material to reject.
            reviewer_id: ID of the reviewing coordinator.
            company_id: Company scope for tenant isolation.

        Returns:
            Updated TrainingMaterial with rejected status.

        Raises:
            ValueError: If material is not found, does not belong to the
                company, or is not in pending_review status.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TrainingMaterial).where(
                    TrainingMaterial.id == material_id,
                    TrainingMaterial.company_id == company_id,
                )
            )
            material = result.scalar_one_or_none()

            if material is None:
                raise ValueError(
                    f"Training material {material_id} not found "
                    f"for company {company_id}"
                )

            if material.status != ContentStatus.PENDING_REVIEW.value:
                raise ValueError(
                    f"Training material {material_id} is not pending review "
                    f"(current status: {material.status})"
                )

            material.status = ContentStatus.REJECTED.value
            material.reviewed_by = reviewer_id
            material.reviewed_at = datetime.now(UTC)

            await session.commit()
            await session.refresh(material)

            logger.info(
                "Training material %d rejected by user %d",
                material_id,
                reviewer_id,
            )

            return material

    async def generate_material_content(
        self,
        document_content: str,
        material_type: str,
        previous_content: str | None = None,
    ) -> dict[str, Any]:
        """Core LLM generation logic for a single material type.

        Uses the Educational Specialist archetype to generate structured
        training material content. Handles document chunking when content
        exceeds the context window.

        Args:
            document_content: Full text content of the source document.
            material_type: Type of material to generate (e.g., "executive_summary").
            previous_content: Optional previous version content for change comparison.

        Returns:
            Dict containing structured material content with keys:
                - content: The generated material content (structure varies by type).
                - learning_objectives: List of measurable learning objectives.
                - estimated_duration_minutes: Estimated consumption time.
                - changes_summary: Changes from previous version (if applicable).
        """
        # Load Educational Specialist archetype configuration
        archetype_config = self._agent_registry._load_archetype_raw(
            "Educational Specialist"
        )

        system_prompt = self._build_system_prompt(archetype_config)
        temperature = 0.6
        max_tokens = 8192

        if archetype_config and "contextual_tuning" in archetype_config:
            temperature = archetype_config["contextual_tuning"].get(
                "temperature", 0.6
            )
            max_tokens = archetype_config["contextual_tuning"].get(
                "max_tokens", 8192
            )

        # Handle chunking for large documents
        if len(document_content) > DEFAULT_CHUNK_SIZE:
            return await self._generate_chunked(
                document_content=document_content,
                material_type=material_type,
                previous_content=previous_content,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Build the generation prompt
        user_prompt = self._build_generation_prompt(
            document_content=document_content,
            material_type=material_type,
            previous_content=previous_content,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        from alcoabase.config import get_settings

        settings = get_settings()

        response_text = await self._inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120.0,
        )

        return self._parse_generation_response(response_text, material_type)

    async def _generate_chunked(
        self,
        document_content: str,
        material_type: str,
        previous_content: str | None,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Generate material content by chunking large documents.

        Splits the document into manageable chunks, generates partial
        content for each chunk, then merges results into a unified structure.

        Args:
            document_content: Full document text exceeding context window.
            material_type: Type of material to generate.
            previous_content: Optional previous version content.
            system_prompt: System prompt from archetype.
            temperature: LLM temperature setting.
            max_tokens: Maximum tokens for generation.

        Returns:
            Merged material content dict.
        """
        chunks = self._split_into_chunks(document_content)
        partial_results: list[dict[str, Any]] = []

        from alcoabase.config import get_settings

        settings = get_settings()

        for i, chunk in enumerate(chunks):
            context_note = (
                f"This is section {i + 1} of {len(chunks)} from the document. "
                "Generate content for this section that can be merged with "
                "other sections into a complete material."
            )

            user_prompt = self._build_generation_prompt(
                document_content=chunk,
                material_type=material_type,
                previous_content=previous_content if i == 0 else None,
                context_note=context_note,
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response_text = await self._inference_client.chat_completion(
                model=settings.model_chat_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120.0,
            )

            partial = self._parse_generation_response(response_text, material_type)
            partial_results.append(partial)

        return self._merge_chunked_results(partial_results, material_type)

    def _split_into_chunks(self, content: str) -> list[str]:
        """Split document content into chunks respecting paragraph boundaries.

        Attempts to split at paragraph boundaries (double newlines) to
        maintain coherent sections. Falls back to character-based splitting
        if paragraphs are too large.

        Args:
            content: Full document text to split.

        Returns:
            List of content chunks, each within DEFAULT_CHUNK_SIZE.
        """
        paragraphs = content.split("\n\n")
        chunks: list[str] = []
        current_chunk = ""

        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) + 2 > DEFAULT_CHUNK_SIZE:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # Handle single paragraphs larger than chunk size
                if len(paragraph) > DEFAULT_CHUNK_SIZE:
                    # Force-split at chunk size boundaries
                    for start in range(0, len(paragraph), DEFAULT_CHUNK_SIZE):
                        chunks.append(
                            paragraph[start : start + DEFAULT_CHUNK_SIZE]
                        )
                    current_chunk = ""
                else:
                    current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [content]

    def _merge_chunked_results(
        self,
        partial_results: list[dict[str, Any]],
        material_type: str,
    ) -> dict[str, Any]:
        """Merge partial generation results from chunked processing.

        Combines content from multiple chunks into a unified material
        structure, deduplicating learning objectives and summing durations.

        Args:
            partial_results: List of partial content dicts from each chunk.
            material_type: Type of material being generated.

        Returns:
            Merged material content dict.
        """
        if not partial_results:
            return {
                "content": {},
                "learning_objectives": [],
                "estimated_duration_minutes": 5,
            }

        if len(partial_results) == 1:
            return partial_results[0]

        # Merge learning objectives (deduplicate)
        all_objectives: list[str] = []
        seen_objectives: set[str] = set()
        for result in partial_results:
            for obj in result.get("learning_objectives", []):
                normalized = obj.strip().lower()
                if normalized not in seen_objectives:
                    seen_objectives.add(normalized)
                    all_objectives.append(obj)

        # Sum estimated durations
        total_duration = sum(
            result.get("estimated_duration_minutes", 5)
            for result in partial_results
        )

        # Merge content based on material type
        merged_content = self._merge_content_by_type(
            partial_results, material_type
        )

        result: dict[str, Any] = {
            "content": merged_content,
            "learning_objectives": all_objectives,
            "estimated_duration_minutes": total_duration,
        }

        # Merge changes_summary if present
        changes = [
            r["changes_summary"]
            for r in partial_results
            if r.get("changes_summary")
        ]
        if changes:
            result["changes_summary"] = " ".join(changes)

        return result

    def _merge_content_by_type(
        self,
        partial_results: list[dict[str, Any]],
        material_type: str,
    ) -> dict[str, Any]:
        """Merge content sections based on material type structure.

        Args:
            partial_results: List of partial content dicts.
            material_type: Type of material determining merge strategy.

        Returns:
            Merged content dict.
        """
        if material_type == MaterialType.EXECUTIVE_SUMMARY.value:
            # Concatenate summary sections
            sections = []
            for result in partial_results:
                content = result.get("content", {})
                if isinstance(content, dict):
                    sections.append(content.get("summary", ""))
                elif isinstance(content, str):
                    sections.append(content)
            return {"summary": "\n\n".join(s for s in sections if s)}

        elif material_type == MaterialType.DETAILED_WALKTHROUGH.value:
            # Concatenate steps
            all_steps: list[dict[str, Any]] = []
            for result in partial_results:
                content = result.get("content", {})
                if isinstance(content, dict):
                    all_steps.extend(content.get("steps", []))
            return {"steps": all_steps}

        elif material_type == MaterialType.KEY_TAKEAWAYS.value:
            # Concatenate takeaway lists
            all_takeaways: list[str] = []
            for result in partial_results:
                content = result.get("content", {})
                if isinstance(content, dict):
                    all_takeaways.extend(content.get("takeaways", []))
            return {"takeaways": all_takeaways}

        elif material_type == MaterialType.PRESENTATION_OUTLINE.value:
            # Concatenate slides
            all_slides: list[dict[str, Any]] = []
            for result in partial_results:
                content = result.get("content", {})
                if isinstance(content, dict):
                    all_slides.extend(content.get("slides", []))
            return {"slides": all_slides}

        elif material_type == MaterialType.SAFETY_HIGHLIGHTS.value:
            # Concatenate safety items
            all_highlights: list[dict[str, Any]] = []
            for result in partial_results:
                content = result.get("content", {})
                if isinstance(content, dict):
                    all_highlights.extend(content.get("highlights", []))
            return {"highlights": all_highlights}

        # Fallback: merge as generic sections
        merged: dict[str, Any] = {}
        for result in partial_results:
            content = result.get("content", {})
            if isinstance(content, dict):
                for key, value in content.items():
                    if key in merged and isinstance(merged[key], list):
                        merged[key].extend(value if isinstance(value, list) else [value])
                    else:
                        merged[key] = value
        return merged

    def _build_system_prompt(
        self, archetype_config: dict[str, Any] | None
    ) -> str:
        """Build the system prompt from archetype configuration.

        Args:
            archetype_config: Raw archetype YAML data, or None.

        Returns:
            System prompt string for the LLM.
        """
        if archetype_config and archetype_config.get("system_prompt"):
            return archetype_config["system_prompt"]

        # Fallback system prompt if archetype not found
        return (
            "You are an Educational Specialist with expertise in instructional "
            "design for regulated industries. Your role is to create training "
            "materials from source documents.\n\n"
            "When creating educational content:\n"
            "1. Define clear, measurable learning objectives using Bloom's taxonomy\n"
            "2. Structure content with progressive complexity\n"
            "3. Include practical examples and real-world scenarios\n"
            "4. Ensure training materials meet GxP requirements\n\n"
            "Always respond with valid JSON."
        )

    def _build_generation_prompt(
        self,
        document_content: str,
        material_type: str,
        previous_content: str | None = None,
        context_note: str | None = None,
    ) -> str:
        """Build the user prompt for material generation.

        Args:
            document_content: Source document text.
            material_type: Type of material to generate.
            previous_content: Optional previous version for change comparison.
            context_note: Optional note about chunking context.

        Returns:
            Formatted user prompt string.
        """
        type_instructions = self._get_type_instructions(material_type)

        prompt_parts = []

        if context_note:
            prompt_parts.append(context_note)

        prompt_parts.append(
            f"Generate a {material_type.replace('_', ' ')} training material "
            f"from the following document content."
        )

        prompt_parts.append(f"\n\n## Instructions\n{type_instructions}")

        if previous_content:
            prompt_parts.append(
                "\n\n## Previous Version Content (for change comparison)\n"
                f"{previous_content[:5000]}"
            )

        prompt_parts.append(
            f"\n\n## Source Document Content\n{document_content}"
        )

        prompt_parts.append(
            "\n\n## Required Output Format\n"
            "Respond with a valid JSON object containing:\n"
            '- "content": The structured material content (format depends on type)\n'
            '- "learning_objectives": Array of measurable learning objectives '
            "(using Bloom's taxonomy verbs)\n"
            '- "estimated_duration_minutes": Integer estimate of consumption time\n'
        )

        if previous_content:
            prompt_parts.append(
                '- "changes_summary": Brief description of what changed '
                "from the previous version\n"
            )

        return "\n".join(prompt_parts)

    def _get_type_instructions(self, material_type: str) -> str:
        """Get type-specific generation instructions.

        Args:
            material_type: The material type to get instructions for.

        Returns:
            Instruction string for the specific material type.
        """
        instructions = {
            MaterialType.EXECUTIVE_SUMMARY.value: (
                "Create a concise executive summary for quick reference. "
                "Include: overview of the document purpose, key points, "
                "critical requirements, and regulatory implications. "
                'Structure the content as {"summary": "..."} with clear paragraphs.'
            ),
            MaterialType.DETAILED_WALKTHROUGH.value: (
                "Create a step-by-step procedural guide with explanations. "
                "Include: numbered steps, rationale for each step, common "
                "pitfalls to avoid, and tips for compliance. "
                'Structure as {"steps": [{"step_number": N, "title": "...", '
                '"description": "...", "rationale": "...", "tips": [...]}]}.'
            ),
            MaterialType.KEY_TAKEAWAYS.value: (
                "Extract the most critical information as a bullet-point list. "
                "Focus on: must-know facts, compliance requirements, safety "
                "critical items, and common assessment topics. "
                'Structure as {"takeaways": ["...", "..."]}.'
            ),
            MaterialType.PRESENTATION_OUTLINE.value: (
                "Create a structured slide-by-slide outline with speaker notes. "
                "Include: title slide, learning objectives, content slides "
                "(one concept per slide), summary slide, and Q&A slide. "
                'Structure as {"slides": [{"slide_number": N, "title": "...", '
                '"bullet_points": [...], "speaker_notes": "..."}]}.'
            ),
            MaterialType.SAFETY_HIGHLIGHTS.value: (
                "Extract all safety-critical information with emphasis markers. "
                "Include: hazards, required PPE, emergency procedures, "
                "critical limits, and regulatory warnings. "
                'Structure as {"highlights": [{"category": "...", '
                '"description": "...", "severity": "...", "action_required": "..."}]}.'
            ),
        }
        return instructions.get(
            material_type,
            "Generate structured training content from the document.",
        )

    def _parse_generation_response(
        self, response_text: str, material_type: str
    ) -> dict[str, Any]:
        """Parse the LLM response into structured material content.

        Attempts to parse as JSON. Falls back to wrapping raw text in
        a structured format if JSON parsing fails.

        Args:
            response_text: Raw LLM response text.
            material_type: Type of material for fallback structuring.

        Returns:
            Parsed material content dict.
        """
        # Try to extract JSON from the response
        try:
            # Handle responses wrapped in markdown code blocks
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            parsed = json.loads(cleaned)

            # Ensure required fields exist
            result: dict[str, Any] = {
                "content": parsed.get("content", parsed),
                "learning_objectives": parsed.get("learning_objectives", []),
                "estimated_duration_minutes": parsed.get(
                    "estimated_duration_minutes", 10
                ),
            }

            if "changes_summary" in parsed:
                result["changes_summary"] = parsed["changes_summary"]

            return result

        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Failed to parse LLM response as JSON for material type %s, "
                "wrapping as raw content",
                material_type,
            )
            # Fallback: wrap raw text in appropriate structure
            return {
                "content": self._wrap_raw_content(response_text, material_type),
                "learning_objectives": [],
                "estimated_duration_minutes": 10,
            }

    def _wrap_raw_content(
        self, raw_text: str, material_type: str
    ) -> dict[str, Any]:
        """Wrap raw text in a type-appropriate structure.

        Args:
            raw_text: Unparsed LLM response text.
            material_type: Material type for structure selection.

        Returns:
            Structured content dict.
        """
        if material_type == MaterialType.EXECUTIVE_SUMMARY.value:
            return {"summary": raw_text}
        elif material_type == MaterialType.DETAILED_WALKTHROUGH.value:
            return {"steps": [{"step_number": 1, "title": "Content", "description": raw_text}]}
        elif material_type == MaterialType.KEY_TAKEAWAYS.value:
            return {"takeaways": [raw_text]}
        elif material_type == MaterialType.PRESENTATION_OUTLINE.value:
            return {"slides": [{"slide_number": 1, "title": "Content", "bullet_points": [raw_text]}]}
        elif material_type == MaterialType.SAFETY_HIGHLIGHTS.value:
            return {"highlights": [{"category": "General", "description": raw_text, "severity": "medium", "action_required": "Review"}]}
        return {"text": raw_text}
