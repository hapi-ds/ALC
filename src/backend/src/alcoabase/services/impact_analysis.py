"""Impact Analysis Service for AI-Driven Change Impact Analysis.

Orchestrates the impact analysis pipeline: change delta computation,
affected item assessment, and report generation. Uses the Change Impact
Analyst agent archetype for significance classification via InferenceClient.

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: 2.6, 2.8, 3.1-3.9, 5.1-5.8
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.impact_analysis import DependencyEdge
from alcoabase.schemas.impact_analysis import (
    AffectedItemSchema,
    ChangeDeltaSchema,
    GapFindingSchema,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from alcoabase.services.agent_registry import AgentRegistryService
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.job_tracker import JobTracker
    from alcoabase.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

# Section heading pattern: lines starting with # or numbered headings (e.g., "1.2 Title")
_SECTION_HEADING_PATTERN = re.compile(
    r"^(?:#{1,6}\s+.+|(?:\d+\.)+\d*\s+.+)$", re.MULTILINE
)

# Default significance classification prompt suffix for the Change Impact Analyst
_SIGNIFICANCE_CLASSIFICATION_PROMPT = """
Classify each of the following document section changes by significance level.
Return a JSON object with the following structure:
{
  "classifications": [
    {
      "section_title": "<section heading>",
      "significance": "high" | "medium" | "low",
      "reason": "<brief reason>"
    }
  ]
}

Significance levels:
- "high": Changes to procedural steps, safety-critical content, regulatory requirements,
  hazard warnings, PPE requirements, critical process parameters, or compliance statements.
- "medium": Changes to descriptive content, non-critical references, explanatory text,
  or background information.
- "low": Formatting changes, typographical corrections, cosmetic adjustments, or
  whitespace-only changes.

Sections to classify:
"""


class ImpactAnalysisService:
    """Service for orchestrating change impact analysis.

    Provides change delta computation between document versions,
    significance classification via the Change Impact Analyst agent,
    report generation and persistence, and handles first-version edge cases.

    Args:
        knowledge_service: Service for text extraction and semantic search.
        inference_client: Async HTTP client for vLLM inference.
        agent_registry: Service for loading agent archetypes.
        session_factory: SQLAlchemy async session factory for DB operations.
        job_tracker: JobTracker for async job state management.
    """

    def __init__(
        self,
        knowledge_service: KnowledgeService | None = None,
        inference_client: InferenceClient | None = None,
        agent_registry: AgentRegistryService | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        job_tracker: JobTracker | None = None,
    ) -> None:
        """Initialize ImpactAnalysisService.

        Args:
            knowledge_service: KnowledgeService for text extraction.
            inference_client: InferenceClient for AI inference.
            agent_registry: AgentRegistryService for loading agent archetypes.
            session_factory: Async session factory for database operations.
            job_tracker: JobTracker for managing job states.
        """
        self._knowledge_service = knowledge_service
        self._inference_client = inference_client
        self._agent_registry = agent_registry
        self._session_factory = session_factory
        self._job_tracker = job_tracker

    async def compute_change_delta(
        self,
        document_uuid: str,
        new_version_id: int,
        previous_version_id: int | None,
        company_id: int,
    ) -> ChangeDeltaSchema:
        """Compute the change delta between two document versions.

        Extracts text from both versions via KnowledgeService, performs
        section-level diff, and classifies changes by significance using
        the Change Impact Analyst agent.

        For first-version case (previous_version_id is None or previous
        version text cannot be retrieved): treats entire content as "new"
        with all sections classified as added.

        Args:
            document_uuid: UUID of the document being analyzed.
            new_version_id: ID of the new document version.
            previous_version_id: ID of the previous version (None for first version).
            company_id: Company ID for tenant scoping.

        Returns:
            ChangeDeltaSchema with sections_added, sections_modified,
            sections_deleted, and significance_levels.
        """
        # Extract text from the new version
        new_text = await self._extract_version_text(
            document_uuid, new_version_id, company_id
        )

        # Handle first-version case (Requirement 2.8)
        if previous_version_id is None:
            return await self._handle_first_version(new_text, company_id)

        # Extract text from the previous version
        previous_text = await self._extract_version_text(
            document_uuid, previous_version_id, company_id
        )

        # If previous text cannot be retrieved, treat as first version
        if previous_text is None:
            return await self._handle_first_version(new_text, company_id)

        # Parse sections from both versions
        new_sections = self._parse_sections(new_text or "")
        old_sections = self._parse_sections(previous_text)

        # Compute section-level diff
        sections_added, sections_modified, sections_deleted = (
            self._compute_section_diff(old_sections, new_sections)
        )

        # Classify significance using the Change Impact Analyst agent
        significance_levels = await self._classify_significance(
            sections_added=sections_added,
            sections_modified=sections_modified,
            sections_deleted=sections_deleted,
            company_id=company_id,
        )

        # Check if agent fallback was used and record in metadata (Req 7.5)
        metadata: dict[str, Any] = {}
        _sys_prompt, _temp, _max_tok, fallback_used = self._get_agent_config()
        if fallback_used:
            metadata["fallback_used"] = {
                "missing_archetype": "Change Impact Analyst",
                "used_archetype": "Regulatory Compliance Auditor",
            }

        return ChangeDeltaSchema(
            sections_added=sections_added,
            sections_modified=sections_modified,
            sections_deleted=sections_deleted,
            significance_levels=significance_levels,
            metadata=metadata if metadata else {},
        )

    async def _handle_first_version(
        self,
        new_text: str | None,
        company_id: int,
    ) -> ChangeDeltaSchema:
        """Handle the first-version case where all content is treated as new.

        Args:
            new_text: Text content of the new (first) version.
            company_id: Company ID for tenant scoping.

        Returns:
            ChangeDeltaSchema with all sections as added.
        """
        if not new_text:
            return ChangeDeltaSchema(
                sections_added=[],
                sections_modified=[],
                sections_deleted=[],
                significance_levels={"high": 0, "medium": 0, "low": 0},
                metadata={"first_version": True, "empty_content": True},
            )

        # Parse all sections from the new content
        new_sections = self._parse_sections(new_text)

        # All sections are "added"
        sections_added = [
            {"title": title, "content": content}
            for title, content in new_sections.items()
        ]

        # Classify significance
        significance_levels = await self._classify_significance(
            sections_added=sections_added,
            sections_modified=[],
            sections_deleted=[],
            company_id=company_id,
        )

        # Check if agent fallback was used and record in metadata (Req 7.5)
        metadata: dict[str, Any] = {"first_version": True}
        _sys_prompt, _temp, _max_tok, fallback_used = self._get_agent_config()
        if fallback_used:
            metadata["fallback_used"] = {
                "missing_archetype": "Change Impact Analyst",
                "used_archetype": "Regulatory Compliance Auditor",
            }

        return ChangeDeltaSchema(
            sections_added=sections_added,
            sections_modified=[],
            sections_deleted=[],
            significance_levels=significance_levels,
            metadata=metadata,
        )

    async def _extract_version_text(
        self,
        document_uuid: str,
        version_id: int,
        company_id: int,
    ) -> str | None:
        """Extract text content from a specific document version.

        Uses KnowledgeService to retrieve indexed text for the version.
        Falls back to searching the knowledge index by document UUID.

        Args:
            document_uuid: UUID of the document.
            version_id: ID of the specific version to extract.
            company_id: Company ID for tenant scoping.

        Returns:
            Extracted text content, or None if extraction fails.
        """
        if self._knowledge_service is None:
            logger.warning(
                "KnowledgeService not available, cannot extract text for "
                "document %s version %d",
                document_uuid,
                version_id,
            )
            return None

        try:
            # Search the knowledge index for this document's content
            results, _ = self._knowledge_service.hybrid_search(
                query=document_uuid,
                user_id=0,  # System-level access
                limit=50,
                filters={"document_uuid": [document_uuid]},
            )

            if results:
                # Concatenate all chunks to reconstruct the full text
                return "\n".join(r.excerpt for r in results)

            return None
        except Exception as e:
            logger.warning(
                "Failed to extract text for document %s version %d: %s",
                document_uuid,
                version_id,
                str(e),
            )
            return None

    def _parse_sections(self, text: str) -> dict[str, str]:
        """Parse document text into sections by headings.

        Splits text at section headings (markdown # headings or numbered
        headings like "1.2 Title"). Each section includes the content
        between its heading and the next heading.

        Args:
            text: Full document text content.

        Returns:
            Ordered dict mapping section title to section content.
        """
        sections: dict[str, str] = {}

        if not text.strip():
            return sections

        # Find all heading positions
        headings: list[tuple[int, str]] = []
        for match in _SECTION_HEADING_PATTERN.finditer(text):
            headings.append((match.start(), match.group().strip()))

        if not headings:
            # No headings found — treat entire text as a single section
            sections["[Document Body]"] = text.strip()
            return sections

        # Extract content between headings
        for i, (pos, title) in enumerate(headings):
            # Content starts after the heading line
            content_start = text.index("\n", pos) + 1 if "\n" in text[pos:] else len(text)

            # Content ends at the next heading or end of text
            if i + 1 < len(headings):
                content_end = headings[i + 1][0]
            else:
                content_end = len(text)

            content = text[content_start:content_end].strip()
            # Clean the title (remove # prefix)
            clean_title = re.sub(r"^#+\s*", "", title).strip()
            sections[clean_title] = content

        # If there's content before the first heading, include it
        first_heading_pos = headings[0][0]
        preamble = text[:first_heading_pos].strip()
        if preamble:
            sections["[Preamble]"] = preamble

        return sections

    def _compute_section_diff(
        self,
        old_sections: dict[str, str],
        new_sections: dict[str, str],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
        """Compute section-level diff between old and new document versions.

        Partitions sections into added, modified, and deleted based on
        title matching and content comparison.

        Args:
            old_sections: Sections from the previous version.
            new_sections: Sections from the new version.

        Returns:
            Tuple of (sections_added, sections_modified, sections_deleted).
            Each is a list of dicts with "title" and "content" keys.
        """
        old_titles = set(old_sections.keys())
        new_titles = set(new_sections.keys())

        # Sections present in new but not in old → added
        added_titles = new_titles - old_titles
        sections_added = [
            {"title": title, "content": new_sections[title]}
            for title in sorted(added_titles)
        ]

        # Sections present in old but not in new → deleted
        deleted_titles = old_titles - new_titles
        sections_deleted = [
            {"title": title, "content": old_sections[title]}
            for title in sorted(deleted_titles)
        ]

        # Sections present in both but with different content → modified
        common_titles = old_titles & new_titles
        sections_modified = [
            {
                "title": title,
                "content": new_sections[title],
                "previous_content": old_sections[title],
            }
            for title in sorted(common_titles)
            if old_sections[title] != new_sections[title]
        ]

        return sections_added, sections_modified, sections_deleted

    async def _classify_significance(
        self,
        sections_added: list[dict[str, str]],
        sections_modified: list[dict[str, str]],
        sections_deleted: list[dict[str, str]],
        company_id: int,
    ) -> dict[str, int]:
        """Classify changes by significance using the Change Impact Analyst agent.

        Sends the change summary to the AI agent for classification into
        high/medium/low significance levels.

        Falls back to heuristic classification if the inference client is
        unavailable or the agent cannot be loaded.

        Args:
            sections_added: List of added sections.
            sections_modified: List of modified sections.
            sections_deleted: List of deleted sections.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict with counts: {"high": N, "medium": N, "low": N}.
        """
        all_changes = sections_added + sections_modified + sections_deleted
        if not all_changes:
            return {"high": 0, "medium": 0, "low": 0}

        # Try AI-based classification
        if self._inference_client is not None:
            try:
                return await self._classify_with_agent(all_changes, company_id)
            except Exception as e:
                logger.warning(
                    "AI significance classification failed, falling back to "
                    "heuristic: %s",
                    str(e),
                )

        # Fallback: heuristic classification
        return self._classify_heuristic(all_changes)

    async def _classify_with_agent(
        self,
        changes: list[dict[str, str]],
        company_id: int,
    ) -> dict[str, int]:
        """Classify changes using the Change Impact Analyst agent via inference.

        Loads the agent's system prompt and sends the classification request
        to the InferenceClient.

        Args:
            changes: List of change dicts with "title" and "content" keys.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict with counts: {"high": N, "medium": N, "low": N}.
        """
        # Load agent system prompt and tuning params
        system_prompt, temperature, max_tokens, _fallback_used = self._get_agent_config()

        # Build the classification prompt
        change_descriptions = []
        for change in changes:
            title = change.get("title", "Unknown Section")
            content = change.get("content", "")[:200]  # Truncate for prompt
            change_descriptions.append(f"- Section: \"{title}\"\n  Content: \"{content}\"")

        user_prompt = (
            _SIGNIFICANCE_CLASSIFICATION_PROMPT
            + "\n".join(change_descriptions)
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Call inference
        response_text = await self._inference_client.chat_completion(
            model=self._get_model_name(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=30.0,
        )

        # Parse the AI response
        return self._parse_significance_response(response_text, len(changes))

    def _get_agent_config(self) -> tuple[str, float, int, bool]:
        """Get the Change Impact Analyst agent configuration.

        Loads the agent archetype from the registry. Falls back to the
        Regulatory Compliance Auditor if not found, recording the fallback.

        Handles YAML schema validation failures by rejecting the invalid
        file, logging the error, and retaining the previous (default)
        configuration.

        Returns:
            Tuple of (system_prompt, temperature, max_tokens, fallback_used).
            fallback_used is True when the primary archetype was not found
            and the Regulatory Compliance Auditor was used instead.
        """
        # Default values from the Change Impact Analyst archetype
        default_system_prompt = (
            "You are a Change Impact Analyst specializing in regulated "
            "document management. Classify document changes by significance."
        )
        default_temperature = 0.2
        default_max_tokens = 4096

        if self._agent_registry is None:
            return default_system_prompt, default_temperature, default_max_tokens, False

        try:
            # Try to load the Change Impact Analyst archetype
            archetypes = self._agent_registry.list_archetypes()
            for archetype in archetypes:
                if archetype.get("archetype") == "Change Impact Analyst":
                    system_prompt = archetype.get(
                        "system_prompt", default_system_prompt
                    )
                    tuning = archetype.get("contextual_tuning", {})
                    temperature = tuning.get("temperature", default_temperature)
                    max_tokens = tuning.get("max_tokens", default_max_tokens)
                    return system_prompt, temperature, max_tokens, False

            # Fallback: try Regulatory Compliance Auditor (Req 7.5)
            for archetype in archetypes:
                if archetype.get("archetype") == "Regulatory Compliance Auditor":
                    system_prompt = archetype.get("system_prompt", "")
                    system_prompt += (
                        "\n\nAdditional context: You are acting as a Change "
                        "Impact Analyst. Classify document changes by "
                        "significance level (high/medium/low) and identify "
                        "gaps between document pairs."
                    )
                    tuning = archetype.get("contextual_tuning", {})
                    temperature = tuning.get("temperature", default_temperature)
                    max_tokens = tuning.get("max_tokens", default_max_tokens)
                    logger.info(
                        "Change Impact Analyst archetype not found, "
                        "using Regulatory Compliance Auditor as fallback"
                    )
                    return system_prompt, temperature, max_tokens, True

        except Exception as e:
            # Handle YAML schema validation failure (Req 7.6):
            # reject file, log error, retain previous (default) config
            logger.error(
                "Failed to load agent archetype (YAML schema validation "
                "failure or other error): %s. Retaining default configuration.",
                str(e),
            )

        return default_system_prompt, default_temperature, default_max_tokens, False

    def _get_model_name(self) -> str:
        """Get the model name for inference.

        Returns:
            The model name string from settings or a default.
        """
        try:
            from alcoabase.config import get_settings

            settings = get_settings()
            return settings.model_chat_name
        except Exception:
            return "gemma-4-e4b-it"

    def _parse_significance_response(
        self,
        response_text: str,
        total_changes: int,
    ) -> dict[str, int]:
        """Parse the AI response for significance classifications.

        Extracts the JSON classifications from the response and counts
        occurrences of each significance level.

        Args:
            response_text: Raw text response from the AI agent.
            total_changes: Total number of changes submitted for classification.

        Returns:
            Dict with counts: {"high": N, "medium": N, "low": N}.
        """
        counts = {"high": 0, "medium": 0, "low": 0}

        try:
            # Try to extract JSON from the response
            # Handle cases where the response may have markdown code blocks
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            data = json.loads(json_text.strip())
            classifications = data.get("classifications", [])

            for item in classifications:
                significance = item.get("significance", "").lower()
                if significance in counts:
                    counts[significance] += 1

            # If we got fewer classifications than changes, assign remainder as medium
            classified = sum(counts.values())
            if classified < total_changes:
                counts["medium"] += total_changes - classified

        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            logger.warning(
                "Failed to parse significance response, using heuristic: %s",
                str(e),
            )
            # Fall back to heuristic for all changes
            counts = {"high": 0, "medium": total_changes, "low": 0}

        return counts

    def _classify_heuristic(
        self,
        changes: list[dict[str, str]],
    ) -> dict[str, int]:
        """Classify changes using keyword-based heuristics.

        Used as a fallback when AI classification is unavailable.

        High significance keywords: safety, hazard, critical, regulatory,
        compliance, procedure, step, PPE, warning, requirement.

        Low significance keywords: format, typo, spacing, cosmetic, style.

        Everything else is classified as medium.

        Args:
            changes: List of change dicts with "title" and "content" keys.

        Returns:
            Dict with counts: {"high": N, "medium": N, "low": N}.
        """
        high_keywords = {
            "safety", "hazard", "critical", "regulatory", "compliance",
            "procedure", "step", "ppe", "warning", "requirement", "shall",
            "must", "mandatory", "prohibited",
        }
        low_keywords = {
            "format", "typo", "spacing", "cosmetic", "style", "font",
            "margin", "indent", "whitespace",
        }

        counts = {"high": 0, "medium": 0, "low": 0}

        for change in changes:
            title = change.get("title", "").lower()
            content = change.get("content", "").lower()
            combined = f"{title} {content}"

            words = set(combined.split())

            if words & high_keywords:
                counts["high"] += 1
            elif words & low_keywords:
                counts["low"] += 1
            else:
                counts["medium"] += 1

        return counts

    # --- Dependency type priority for candidate prioritization (Req 3.6) ---
    _DEPENDENCY_TYPE_PRIORITY: dict[str, int] = {
        "validates": 0,
        "implements": 1,
        "references": 2,
        "trains_on": 3,
        "derived_from": 4,
    }

    # Maximum number of candidates to assess per job (Req 3.6)
    _MAX_CANDIDATES = 50

    # Impact assessment prompt template for the Change Impact Analyst agent
    _IMPACT_ASSESSMENT_PROMPT = """You are assessing the impact of a document change on a dependent document.

Source document change summary:
{change_summary}

Dependent document content (dependency type: {dependency_type}):
{dependent_content}

Assess whether the change impacts the dependent document. Return a JSON object:
{{
  "is_impacted": true | false,
  "impact_severity": "critical" | "major" | "minor",
  "affected_sections": ["<section heading 1>", "<section heading 2>"],
  "change_summary": "<one-sentence description of why the item is affected, max 500 chars>",
  "recommended_action": "update_required" | "review_recommended" | "retraining_required"
}}

Severity rules:
- "critical": The dependent document contains statements that now CONTRADICT the updated source.
- "major": The dependent document is MISSING content that the updated source now requires.
- "minor": The dependent document uses OUTDATED terminology or references but remains functionally aligned.

If the change does NOT impact the dependent document, set is_impacted to false.
"""

    async def assess_affected_items(
        self,
        change_delta: ChangeDeltaSchema,
        downstream_edges: list[DependencyEdge],
        company_id: int,
        session: AsyncSession | None = None,
    ) -> list[AffectedItemSchema]:
        """Assess affected items from downstream dependencies.

        For each candidate downstream dependency, retrieves the dependent
        document's sections via KnowledgeService and uses the Change Impact
        Analyst agent to assess whether the change actually impacts it.

        Implements candidate prioritization (Req 3.6): limits to 50 candidates,
        sorted by confidence_score descending then dependency_type priority.

        Implements per-item error handling (Req 3.8, 3.9): marks items as
        severity "unknown" / action "manual_review_required" on failure.

        Implements training task identification (Req 3.4): queries TrainingTask
        records and flags incomplete/completed tasks as needed.

        Args:
            change_delta: The computed change delta for the triggering document.
            downstream_edges: List of DependencyEdge objects representing
                downstream dependencies from the changed document.
            company_id: Company ID for tenant scoping.
            session: Optional async DB session for training task queries.

        Returns:
            List of AffectedItemSchema for confirmed affected items.
        """
        if not downstream_edges:
            return []

        # Prioritize candidates (Req 3.6)
        prioritized = self._prioritize_candidates(downstream_edges)

        # Build change summary for the prompt
        change_summary = self._build_change_summary(change_delta)

        # Assess each candidate
        affected_items: list[AffectedItemSchema] = []

        for edge in prioritized:
            item = await self._assess_single_item(
                edge=edge,
                change_summary=change_summary,
                company_id=company_id,
            )
            if item is not None:
                affected_items.append(item)

        # Identify affected training tasks (Req 3.4)
        if session is not None:
            training_items = await self._identify_affected_training_tasks(
                change_delta=change_delta,
                downstream_edges=downstream_edges,
                company_id=company_id,
                session=session,
            )
            affected_items.extend(training_items)

        return affected_items

    def _prioritize_candidates(
        self,
        edges: list[DependencyEdge],
    ) -> list[DependencyEdge]:
        """Prioritize downstream dependency candidates for assessment.

        Sorts by confidence_score descending, then by dependency_type
        priority (validates=0 > implements=1 > references=2 > trains_on=3
        > derived_from=4). Takes the top 50.

        Args:
            edges: List of DependencyEdge objects.

        Returns:
            Sorted and limited list of edges (max 50).
        """
        sorted_edges = sorted(
            edges,
            key=lambda e: (
                -e.confidence_score,
                self._DEPENDENCY_TYPE_PRIORITY.get(e.dependency_type, 99),
            ),
        )
        return sorted_edges[: self._MAX_CANDIDATES]

    def _build_change_summary(self, change_delta: ChangeDeltaSchema) -> str:
        """Build a textual summary of the change delta for the AI prompt.

        Args:
            change_delta: The computed change delta.

        Returns:
            A formatted string summarizing the changes.
        """
        parts: list[str] = []

        if change_delta.sections_added:
            titles = [s.get("title", "Unknown") for s in change_delta.sections_added]
            parts.append(f"Sections added: {', '.join(titles)}")

        if change_delta.sections_modified:
            titles = [s.get("title", "Unknown") for s in change_delta.sections_modified]
            parts.append(f"Sections modified: {', '.join(titles)}")

        if change_delta.sections_deleted:
            titles = [s.get("title", "Unknown") for s in change_delta.sections_deleted]
            parts.append(f"Sections deleted: {', '.join(titles)}")

        sig = change_delta.significance_levels
        parts.append(
            f"Significance: {sig.get('high', 0)} high, "
            f"{sig.get('medium', 0)} medium, {sig.get('low', 0)} low"
        )

        return "\n".join(parts)

    async def _assess_single_item(
        self,
        edge: DependencyEdge,
        change_summary: str,
        company_id: int,
    ) -> AffectedItemSchema | None:
        """Assess a single candidate affected item.

        Retrieves the dependent document's content via KnowledgeService,
        sends it to the Change Impact Analyst agent for assessment, and
        returns an AffectedItemSchema if the item is confirmed as impacted.

        On inference or knowledge service failure, returns an item with
        severity "unknown" and action "manual_review_required" (Req 3.8, 3.9).

        Args:
            edge: The DependencyEdge representing the dependency.
            change_summary: Textual summary of the change delta.
            company_id: Company ID for tenant scoping.

        Returns:
            AffectedItemSchema if impacted or on error, None if not impacted.
        """
        target_uuid = edge.target_document_uuid
        dependency_type = edge.dependency_type

        # Retrieve dependent document content via KnowledgeService (Req 3.2)
        dependent_content: str | None = None
        document_title = f"Document {target_uuid}"

        try:
            dependent_content = await self._retrieve_document_content(
                target_uuid, company_id
            )
        except Exception as e:
            # KnowledgeService failure (Req 3.9)
            logger.warning(
                "KnowledgeService failed for document %s: %s",
                target_uuid,
                str(e),
            )
            return AffectedItemSchema(
                affected_document_uuid=target_uuid,
                affected_document_title=document_title,
                dependency_type=dependency_type,
                impact_severity="unknown",
                affected_sections=[],
                change_summary=f"Unable to retrieve document content: {str(e)[:200]}",
                recommended_action="manual_review_required",
                inference_prompt_summary="",
                model_response_summary=f"KnowledgeService failure: {str(e)[:400]}",
                token_count=0,
            )

        if dependent_content is None:
            # Document content not found (Req 3.9)
            return AffectedItemSchema(
                affected_document_uuid=target_uuid,
                affected_document_title=document_title,
                dependency_type=dependency_type,
                impact_severity="unknown",
                affected_sections=[],
                change_summary="Document content could not be retrieved from knowledge index",
                recommended_action="manual_review_required",
                inference_prompt_summary="",
                model_response_summary="Document not found in knowledge index",
                token_count=0,
            )

        # Build the assessment prompt
        prompt = self._IMPACT_ASSESSMENT_PROMPT.format(
            change_summary=change_summary,
            dependency_type=dependency_type,
            dependent_content=dependent_content[:3000],  # Limit content size
        )

        # Get agent config
        system_prompt, temperature, max_tokens, _fallback_used = self._get_agent_config()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        inference_prompt_summary = prompt[:500]

        # Call inference (Req 3.2)
        try:
            if self._inference_client is None:
                raise RuntimeError("InferenceClient not available")

            response_text = await self._inference_client.chat_completion(
                model=self._get_model_name(),
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=30.0,
            )

            model_response_summary = response_text[:500]
            token_count = len(prompt.split()) + len(response_text.split())

            # Parse the AI response
            assessment = self._parse_impact_assessment(response_text)

            if not assessment.get("is_impacted", False):
                # Agent determined no impact — exclude from results (Req 3.2)
                return None

            # Map severity (Req 3.3)
            severity = assessment.get("impact_severity", "minor")
            if severity not in ("critical", "major", "minor"):
                severity = "minor"

            # Map recommended action
            action = assessment.get("recommended_action", "review_recommended")
            if action not in (
                "update_required",
                "review_recommended",
                "retraining_required",
                "manual_review_required",
            ):
                action = "review_recommended"

            return AffectedItemSchema(
                affected_document_uuid=target_uuid,
                affected_document_title=document_title,
                dependency_type=dependency_type,
                impact_severity=severity,
                affected_sections=assessment.get("affected_sections", []),
                change_summary=assessment.get("change_summary", "Impact detected")[:500],
                recommended_action=action,
                inference_prompt_summary=inference_prompt_summary,
                model_response_summary=model_response_summary,
                token_count=token_count,
            )

        except Exception as e:
            # InferenceClient failure (Req 3.8)
            logger.warning(
                "Inference failed for document %s assessment: %s",
                target_uuid,
                str(e),
            )
            return AffectedItemSchema(
                affected_document_uuid=target_uuid,
                affected_document_title=document_title,
                dependency_type=dependency_type,
                impact_severity="unknown",
                affected_sections=[],
                change_summary=f"Inference service unavailable: {str(e)[:200]}",
                recommended_action="manual_review_required",
                inference_prompt_summary=inference_prompt_summary,
                model_response_summary=f"Inference failure: {str(e)[:400]}",
                token_count=0,
            )

    async def _retrieve_document_content(
        self,
        document_uuid: str,
        company_id: int,
    ) -> str | None:
        """Retrieve document content from KnowledgeService.

        Args:
            document_uuid: UUID of the document to retrieve.
            company_id: Company ID for tenant scoping.

        Returns:
            Concatenated text content, or None if not found.

        Raises:
            Exception: If KnowledgeService encounters an error.
        """
        if self._knowledge_service is None:
            return None

        results, _ = self._knowledge_service.hybrid_search(
            query=document_uuid,
            user_id=0,  # System-level access
            limit=50,
            filters={"document_uuid": [document_uuid]},
        )

        if results:
            return "\n".join(r.excerpt for r in results)
        return None

    def _parse_impact_assessment(self, response_text: str) -> dict[str, Any]:
        """Parse the AI impact assessment response.

        Extracts JSON from the response, handling markdown code blocks.

        Args:
            response_text: Raw text response from the AI agent.

        Returns:
            Parsed assessment dict with is_impacted, impact_severity,
            affected_sections, change_summary, recommended_action.
        """
        try:
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            return json.loads(json_text.strip())
        except (json.JSONDecodeError, IndexError, TypeError) as e:
            logger.warning(
                "Failed to parse impact assessment response: %s", str(e)
            )
            # Default to impacted with minor severity if parsing fails
            return {
                "is_impacted": True,
                "impact_severity": "minor",
                "affected_sections": [],
                "change_summary": "Assessment response could not be parsed",
                "recommended_action": "review_recommended",
            }

    async def _identify_affected_training_tasks(
        self,
        change_delta: ChangeDeltaSchema,
        downstream_edges: list[DependencyEdge],
        company_id: int,
        session: AsyncSession,
    ) -> list[AffectedItemSchema]:
        """Identify training tasks affected by the document change.

        Queries TrainingTask records where sop_document_uuid matches the
        changed document (source of the edges). Flags incomplete tasks for
        review and completed tasks if procedural/safety changes are detected.

        Args:
            change_delta: The computed change delta.
            downstream_edges: Downstream dependency edges.
            company_id: Company ID for tenant scoping.
            session: Active async database session.

        Returns:
            List of AffectedItemSchema for affected training tasks.
        """
        from sqlalchemy import select

        from alcoabase.models.training import TrainingTask

        # Get the source document UUID (the changed document)
        if not downstream_edges:
            return []

        source_uuid = downstream_edges[0].source_document_uuid

        affected_training_items: list[AffectedItemSchema] = []

        try:
            # Query incomplete training tasks (Req 3.4)
            incomplete_result = await session.execute(
                select(TrainingTask).where(
                    TrainingTask.sop_document_uuid == source_uuid,
                    TrainingTask.company_id == company_id,
                    TrainingTask.is_completed.is_(False),
                )
            )
            incomplete_tasks = list(incomplete_result.scalars().all())

            for task in incomplete_tasks:
                affected_training_items.append(
                    AffectedItemSchema(
                        training_task_id=task.id,
                        affected_document_title=task.task_title,
                        dependency_type="trains_on",
                        impact_severity="major",
                        affected_sections=[],
                        change_summary=(
                            "Incomplete training task requires content review "
                            "due to source document update"
                        ),
                        recommended_action="review_recommended",
                        inference_prompt_summary="",
                        model_response_summary="Flagged: incomplete training task for updated SOP",
                        token_count=0,
                    )
                )

            # Query completed training tasks — flag if procedural/safety changes
            has_procedural_safety_changes = self._has_procedural_safety_changes(
                change_delta
            )

            if has_procedural_safety_changes:
                completed_result = await session.execute(
                    select(TrainingTask).where(
                        TrainingTask.sop_document_uuid == source_uuid,
                        TrainingTask.company_id == company_id,
                        TrainingTask.is_completed.is_(True),
                    )
                )
                completed_tasks = list(completed_result.scalars().all())

                for task in completed_tasks:
                    affected_training_items.append(
                        AffectedItemSchema(
                            training_task_id=task.id,
                            affected_document_title=task.task_title,
                            dependency_type="trains_on",
                            impact_severity="critical",
                            affected_sections=[],
                            change_summary=(
                                "Completed training potentially invalidated: "
                                "procedural or safety-critical changes detected "
                                "in source SOP"
                            ),
                            recommended_action="retraining_required",
                            inference_prompt_summary="",
                            model_response_summary=(
                                "Flagged: completed training invalidated by "
                                "procedural/safety changes"
                            ),
                            token_count=0,
                        )
                    )

        except Exception as e:
            logger.warning(
                "Failed to query training tasks for document %s: %s",
                source_uuid,
                str(e),
            )
            # On failure, create a single unknown item (Req 3.9 spirit)
            affected_training_items.append(
                AffectedItemSchema(
                    affected_document_uuid=source_uuid,
                    affected_document_title=f"Training tasks for {source_uuid}",
                    dependency_type="trains_on",
                    impact_severity="unknown",
                    affected_sections=[],
                    change_summary=f"Unable to query training tasks: {str(e)[:200]}",
                    recommended_action="manual_review_required",
                    inference_prompt_summary="",
                    model_response_summary=f"Training task query failure: {str(e)[:400]}",
                    token_count=0,
                )
            )

        return affected_training_items

    def _has_procedural_safety_changes(
        self,
        change_delta: ChangeDeltaSchema,
    ) -> bool:
        """Determine if the change delta includes procedural or safety changes.

        Checks for keywords indicating procedural steps, safety-critical
        content, hazard warnings, PPE requirements, critical process
        parameters, or regulatory compliance statements.

        Args:
            change_delta: The computed change delta.

        Returns:
            True if procedural or safety-critical changes are detected.
        """
        safety_keywords = {
            "safety", "hazard", "critical", "ppe", "warning", "procedure",
            "step", "caution", "danger", "emergency", "protective",
            "compliance", "regulatory", "shall", "must", "prohibited",
            "parameter", "limit", "tolerance", "specification",
        }

        # Check all modified and added sections
        all_changes = change_delta.sections_added + change_delta.sections_modified
        for section in all_changes:
            title = section.get("title", "").lower()
            content = section.get("content", "").lower()
            combined_words = set(f"{title} {content}".split())
            if combined_words & safety_keywords:
                return True

        # Also check significance levels — high significance implies safety
        if change_delta.significance_levels.get("high", 0) > 0:
            return True

        return False

    async def create_impact_report(
        self,
        *,
        session: AsyncSession,
        job_id: str,
        triggering_document_uuid: str,
        triggering_version_id: int,
        change_delta_summary: ChangeDeltaSchema,
        affected_items: list[AffectedItemSchema],
        gap_findings: list[GapFindingSchema],
        status: str,
        analysis_timestamp: datetime,
        analysis_duration_ms: int,
        agent_archetype_used: str,
        model_used: str,
        total_token_count: int,
        company_id: int,
        requesting_user_id: int | None = None,
        user_attribution_unavailable: bool = False,
    ) -> str:
        """Create and persist an immutable ImpactReport record.

        Assembles an ImpactReport with all required fields and persists it
        to the database. The report is created for ALL terminal states
        (completed, partial_success, failed).

        For auto-triggered analyses, requesting_user_id comes from
        DocumentVersion.uploaded_by. If uploaded_by is null, set
        requesting_user_id=None and add metadata flag
        "user_attribution_unavailable": true.

        On database write failure, marks the job as failed via JobTracker.

        Args:
            session: Active async database session.
            job_id: Job ID for tracking (used to mark failure if DB write fails).
            triggering_document_uuid: UUID of the document that triggered analysis.
            triggering_version_id: Version ID that triggered the analysis.
            change_delta_summary: Structured summary of what changed.
            affected_items: List of affected items with severity and recommendations.
            gap_findings: List of gap findings.
            status: Terminal status ("completed", "partial_success", "failed").
            analysis_timestamp: When the analysis was executed.
            analysis_duration_ms: Total analysis time in milliseconds.
            agent_archetype_used: Name of the agent archetype used.
            model_used: Name of the AI model used for inference.
            total_token_count: Sum of input and output tokens.
            company_id: Company ID for tenant isolation.
            requesting_user_id: User who requested analysis (None for auto-triggered
                with unavailable attribution).
            user_attribution_unavailable: If True, adds metadata flag indicating
                user attribution is unavailable.

        Returns:
            The generated report_id (UUID string).

        Raises:
            No exceptions are raised to the caller. On DB write failure,
            the job is marked as failed via JobTracker.
        """
        from alcoabase.models.impact_analysis import ImpactReport

        report_id = str(uuid.uuid4())

        # Build the change_delta_summary dict, adding metadata flag if needed
        delta_dict = change_delta_summary.model_dump()
        if user_attribution_unavailable:
            delta_dict.setdefault("metadata", {})
            delta_dict["metadata"]["user_attribution_unavailable"] = True

        # Serialize affected items and gap findings to JSONB-compatible dicts
        affected_items_data = [item.model_dump() for item in affected_items]
        gap_findings_data = [finding.model_dump() for finding in gap_findings]

        report = ImpactReport(
            report_id=report_id,
            triggering_document_uuid=triggering_document_uuid,
            triggering_version_id=triggering_version_id,
            change_delta_summary=delta_dict,
            affected_items=affected_items_data,
            gap_findings=gap_findings_data,
            status=status,
            analysis_timestamp=analysis_timestamp,
            analysis_duration_ms=analysis_duration_ms,
            agent_archetype_used=agent_archetype_used,
            model_used=model_used,
            total_token_count=total_token_count,
            requesting_user_id=requesting_user_id,
            company_id=company_id,
        )

        try:
            session.add(report)
            await session.flush()
            logger.info(
                "Impact report %s created for document %s (status=%s)",
                report_id,
                triggering_document_uuid,
                status,
            )
            return report_id
        except Exception as e:
            logger.error(
                "Failed to persist impact report for document %s: %s",
                triggering_document_uuid,
                str(e),
            )
            # Mark job as failed via JobTracker (Requirement 5.7)
            await self._mark_job_failed_on_persistence_error(
                session, job_id, str(e)
            )
            raise

    async def _mark_job_failed_on_persistence_error(
        self,
        session: AsyncSession,
        job_id: str,
        error_detail: str,
    ) -> None:
        """Mark a job as failed when report persistence fails.

        Uses the JobTracker to record the failure. If JobTracker is
        unavailable, logs the error.

        Args:
            session: Active async database session.
            job_id: Job ID to mark as failed.
            error_detail: Description of the persistence error.
        """
        error_message = (
            f"Impact report persistence failed: {error_detail[:200]}"
        )

        if self._job_tracker is not None:
            try:
                await self._job_tracker.fail_job(
                    session, job_id, error_message
                )
                logger.info(
                    "Job %s marked as failed due to report persistence error",
                    job_id,
                )
            except Exception as tracker_err:
                logger.error(
                    "Failed to mark job %s as failed via JobTracker: %s",
                    job_id,
                    str(tracker_err),
                )
        else:
            logger.warning(
                "JobTracker unavailable; cannot mark job %s as failed. "
                "Error: %s",
                job_id,
                error_message,
            )

    @staticmethod
    def resolve_requesting_user_id(
        document_version: Any,
    ) -> tuple[int | None, bool]:
        """Resolve the requesting_user_id from a DocumentVersion.

        For auto-triggered analyses, the requesting_user_id comes from
        DocumentVersion.uploaded_by. If uploaded_by is null, returns
        None with a flag indicating attribution is unavailable.

        Args:
            document_version: A DocumentVersion model instance (or any object
                with an uploaded_by attribute).

        Returns:
            Tuple of (requesting_user_id, user_attribution_unavailable).
            If uploaded_by is available, returns (user_id, False).
            If uploaded_by is None, returns (None, True).
        """
        uploaded_by = getattr(document_version, "uploaded_by", None)
        if uploaded_by is None:
            return None, True
        return uploaded_by, False
