"""Gap Analysis Service for AI-Driven Change Impact Analysis.

Performs section-level gap analysis between document pairs, identifying
misalignments where a target document no longer meets the requirements
of an updated source document.

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.document import Document
from alcoabase.models.impact_analysis import DependencyEdge, GapAnalysisResult
from alcoabase.schemas.impact_analysis import GapFindingSchema
from alcoabase.services.inference_client import (
    InferenceClient,
    InferenceError,
)
from alcoabase.services.knowledge_service import KnowledgeService
from alcoabase.services.risk_controlled import risk_controlled

if TYPE_CHECKING:
    from alcoabase.services.agent_registry import AgentRegistryService

logger = logging.getLogger(__name__)

# Timeout for gap analysis execution (seconds)
GAP_ANALYSIS_TIMEOUT_SECONDS = 180

# Maximum number of gap findings to retain
MAX_GAP_FINDINGS = 100

# Severity priority for sorting (lower index = higher priority)
SEVERITY_PRIORITY = {"critical": 0, "major": 1, "minor": 2}

# Minimum confidence score for dependency validation
MIN_DEPENDENCY_CONFIDENCE = 0.5


# Agent archetype names
CHANGE_IMPACT_ANALYST = "Change Impact Analyst"
FALLBACK_AGENT = "Regulatory Compliance Auditor"

# Fallback system prompt suffix appended when using Regulatory Compliance Auditor
_FALLBACK_PROMPT_SUFFIX = (
    "\n\nAdditional context: You are acting as a Change Impact Analyst. "
    "Focus on change impact assessment and gap identification between "
    "document pairs rather than general compliance auditing. Identify "
    "misalignments, classify gaps by severity (critical, major, minor), "
    "and provide specific section references for all findings."
)


class GapAnalysisService:
    """Service for performing gap analysis between document pairs.

    Extracts text from source and target documents, identifies requirements
    and assertions in the source, and uses the Change_Impact_Analyst agent
    to find misalignments in the target document.

    Loads the Change Impact Analyst agent from the Agent Registry for
    system prompt and tuning parameters. Falls back to the Regulatory
    Compliance Auditor if the primary archetype is not found (Req 7.5).

    Args:
        session: Async database session for queries and persistence.
        knowledge_service: Service for text extraction and search.
        inference_client: Client for AI inference via vLLM.
        model_name: Name of the AI model to use for inference.
        agent_registry: Optional AgentRegistryService for loading archetypes.
    """

    def __init__(
        self,
        session: AsyncSession,
        knowledge_service: KnowledgeService,
        inference_client: InferenceClient,
        model_name: str = "Qwen/Qwen3.6-35B-A3B",
        agent_registry: AgentRegistryService | None = None,
    ) -> None:
        """Initialize GapAnalysisService.

        Args:
            session: Async database session.
            knowledge_service: Service for text extraction and search.
            inference_client: Client for AI inference via vLLM.
            model_name: Name of the AI model to use.
            agent_registry: Optional AgentRegistryService for loading archetypes.
        """
        self._session = session
        self._knowledge_service = knowledge_service
        self._inference_client = inference_client
        self._model_name = model_name
        self._agent_registry = agent_registry

    @risk_controlled(task_type_id="traceability_gap_discovery")
    async def execute_gap_analysis(
        self,
        source_doc_id: int,
        target_doc_id: int,
        source_version_id: int | None,
        target_version_id: int | None,
        company_id: int,
        user_id: int | None = None,
    ) -> GapAnalysisResult:
        """Execute gap analysis between two documents.

        Validates inputs, extracts text from both documents, identifies
        requirements/steps/assertions in the source, searches the target
        for coverage, and produces GapFindings.

        Args:
            source_doc_id: ID of the source (updated) document.
            target_doc_id: ID of the target (dependent) document.
            source_version_id: Specific source version (None = latest).
            target_version_id: Specific target version (None = latest).
            company_id: Company ID for tenant scoping.

        Returns:
            Persisted GapAnalysisResult record.

        Raises:
            HTTPException: 404 if document not found, 422 if validation fails.
        """
        start_time = time.monotonic()
        job_id = str(uuid.uuid4())

        # Validation: same-document check
        if source_doc_id == target_doc_id:
            raise HTTPException(
                status_code=422,
                detail="Gap analysis requires two distinct documents. "
                "source_document_id and target_document_id must differ.",
            )

        # Validate document existence in company scope
        source_doc = await self._get_document(source_doc_id, company_id)
        if source_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Source document with id {source_doc_id} "
                f"not found in company scope.",
            )

        target_doc = await self._get_document(target_doc_id, company_id)
        if target_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Target document with id {target_doc_id} "
                f"not found in company scope.",
            )

        # Validate dependency exists with confidence >= 0.5
        has_dependency = await self._check_dependency_exists(
            source_doc.document_uuid,
            target_doc.document_uuid,
            company_id,
        )
        if not has_dependency:
            raise HTTPException(
                status_code=422,
                detail="No dependency relationship with confidence_score >= 0.5 "
                "exists between the specified documents. Build the dependency "
                "graph first using POST /api/impact-analysis/dependency-graph/build.",
            )

        # Get dependency type for context-aware analysis
        dependency_type = await self._get_dependency_type(
            source_doc.document_uuid,
            target_doc.document_uuid,
            company_id,
        )

        # Extract text from source and target documents
        source_text = await self._extract_document_text(
            source_doc, source_version_id
        )
        target_text = await self._extract_document_text(
            target_doc, target_version_id
        )

        if source_text is None or target_text is None:
            # Document text extraction failed
            duration_ms = int((time.monotonic() - start_time) * 1000)
            result = GapAnalysisResult(
                job_id=job_id,
                source_document_uuid=source_doc.document_uuid,
                target_document_uuid=target_doc.document_uuid,
                gap_findings=[],
                total_gaps_detected=0,
                gaps_retained=0,
                status="failed",
                analysis_duration_ms=duration_ms,
                company_id=company_id,
            )
            self._session.add(result)
            await self._session.flush()
            return result

        # Extract sections from source document
        source_sections = self._extract_sections(source_text)

        # Perform gap analysis with timeout handling
        all_findings: list[dict] = []
        total_token_count = 0
        status = "completed"

        try:
            for section in source_sections:
                # Check timeout
                elapsed = time.monotonic() - start_time
                if elapsed >= GAP_ANALYSIS_TIMEOUT_SECONDS:
                    status = "partial_success"
                    break

                # Use AI to compare source section against target
                finding = await self._analyze_section_gap(
                    source_section=section,
                    target_text=target_text,
                    dependency_type=dependency_type,
                    source_title=source_doc.title,
                    target_title=target_doc.title,
                )

                if finding is not None:
                    all_findings.append(finding)
                    total_token_count += finding.get("token_count", 0)

        except InferenceError:
            # AI service unavailable — mark as failed
            duration_ms = int((time.monotonic() - start_time) * 1000)
            result = GapAnalysisResult(
                job_id=job_id,
                source_document_uuid=source_doc.document_uuid,
                target_document_uuid=target_doc.document_uuid,
                gap_findings=[],
                total_gaps_detected=0,
                gaps_retained=0,
                status="failed",
                analysis_duration_ms=duration_ms,
                company_id=company_id,
            )
            self._session.add(result)
            await self._session.flush()
            return result

        # Apply gap finding limiting: retain top 100 by severity
        total_gaps_detected = len(all_findings)
        retained_findings = limit_gap_findings(all_findings, MAX_GAP_FINDINGS)
        gaps_retained = len(retained_findings)

        # Serialize findings for JSONB storage
        serialized_findings = [
            GapFindingSchema(**f).model_dump() for f in retained_findings
        ]

        # Persist result
        duration_ms = int((time.monotonic() - start_time) * 1000)
        result = GapAnalysisResult(
            job_id=job_id,
            source_document_uuid=source_doc.document_uuid,
            target_document_uuid=target_doc.document_uuid,
            gap_findings=serialized_findings,
            total_gaps_detected=total_gaps_detected,
            gaps_retained=gaps_retained,
            status=status,
            analysis_duration_ms=duration_ms,
            company_id=company_id,
        )
        self._session.add(result)
        await self._session.flush()

        return result

    # -------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------

    async def _get_document(
        self, document_id: int, company_id: int
    ) -> Document | None:
        """Get a document by ID within company scope.

        Args:
            document_id: The document's primary key.
            company_id: Company ID for tenant scoping.

        Returns:
            The Document if found, None otherwise.
        """
        result = await self._session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def _check_dependency_exists(
        self,
        source_uuid: str,
        target_uuid: str,
        company_id: int,
    ) -> bool:
        """Check if a dependency edge exists with confidence >= 0.5.

        Checks both directions (source→target and target→source) since
        the dependency could be in either direction.

        Args:
            source_uuid: UUID of the source document.
            target_uuid: UUID of the target document.
            company_id: Company ID for tenant scoping.

        Returns:
            True if a qualifying edge exists, False otherwise.
        """
        from sqlalchemy import or_

        result = await self._session.execute(
            select(DependencyEdge.id).where(
                DependencyEdge.company_id == company_id,
                DependencyEdge.confidence_score >= MIN_DEPENDENCY_CONFIDENCE,
                or_(
                    (
                        (DependencyEdge.source_document_uuid == source_uuid)
                        & (DependencyEdge.target_document_uuid == target_uuid)
                    ),
                    (
                        (DependencyEdge.source_document_uuid == target_uuid)
                        & (DependencyEdge.target_document_uuid == source_uuid)
                    ),
                ),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_dependency_type(
        self,
        source_uuid: str,
        target_uuid: str,
        company_id: int,
    ) -> str:
        """Get the dependency type between two documents.

        Returns the dependency_type of the highest-confidence edge
        between the documents.

        Args:
            source_uuid: UUID of the source document.
            target_uuid: UUID of the target document.
            company_id: Company ID for tenant scoping.

        Returns:
            The dependency type string, or "references" as default.
        """
        from sqlalchemy import or_

        result = await self._session.execute(
            select(DependencyEdge.dependency_type).where(
                DependencyEdge.company_id == company_id,
                DependencyEdge.confidence_score >= MIN_DEPENDENCY_CONFIDENCE,
                or_(
                    (
                        (DependencyEdge.source_document_uuid == source_uuid)
                        & (DependencyEdge.target_document_uuid == target_uuid)
                    ),
                    (
                        (DependencyEdge.source_document_uuid == target_uuid)
                        & (DependencyEdge.target_document_uuid == source_uuid)
                    ),
                ),
            ).order_by(DependencyEdge.confidence_score.desc()).limit(1)
        )
        dep_type = result.scalar_one_or_none()
        return dep_type if dep_type else "references"

    async def _extract_document_text(
        self,
        doc: Document,
        version_id: int | None,
    ) -> str | None:
        """Extract text content from a document version.

        Uses KnowledgeService hybrid_search to retrieve indexed text.
        If version_id is specified, attempts to get that specific version.

        Args:
            doc: The document to extract text from.
            version_id: Specific version ID (None = latest).

        Returns:
            Extracted text content, or None if extraction fails.
        """
        try:
            # Use KnowledgeService to get indexed text
            filters: dict[str, list[str]] = {
                "document_uuid": [doc.document_uuid]
            }
            results, total = self._knowledge_service.hybrid_search(
                query=doc.title,
                user_id=0,  # System-level access
                limit=50,
                filters=filters,
            )
            if results:
                # Concatenate all chunks to get full document text
                return "\n\n".join(r.excerpt for r in results)
            return None
        except Exception:
            logger.warning(
                "Failed to extract text for document %s",
                doc.document_uuid,
            )
            return None

    def _extract_sections(self, text: str) -> list[dict[str, str]]:
        """Extract sections from document text.

        Splits text into logical sections based on headings or paragraph
        breaks. Each section contains a heading and content.

        Args:
            text: Full document text.

        Returns:
            List of dicts with "heading" and "content" keys.
        """
        sections: list[dict[str, str]] = []
        lines = text.split("\n")
        current_heading = "Introduction"
        current_content: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Detect headings (markdown-style or all-caps lines)
            if (
                stripped.startswith("#")
                or (stripped.isupper() and len(stripped) > 3 and len(stripped) < 100)
            ):
                # Save previous section if it has content
                if current_content:
                    sections.append({
                        "heading": current_heading,
                        "content": "\n".join(current_content).strip(),
                    })
                current_heading = stripped.lstrip("#").strip()
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections.append({
                "heading": current_heading,
                "content": "\n".join(current_content).strip(),
            })

        # Filter out empty sections
        return [s for s in sections if s["content"].strip()]

    async def _analyze_section_gap(
        self,
        source_section: dict[str, str],
        target_text: str,
        dependency_type: str,
        source_title: str,
        target_title: str,
    ) -> dict | None:
        """Analyze a single source section for gaps in the target document.

        Uses the Change_Impact_Analyst agent to perform semantic comparison
        with dependency_type-aware instructions. Loads agent configuration
        from the Agent Registry (Req 7.4).

        Args:
            source_section: Dict with "heading" and "content" keys.
            target_text: Full text of the target document.
            dependency_type: Type of dependency between documents.
            source_title: Title of the source document.
            target_title: Title of the target document.

        Returns:
            A gap finding dict if a gap is detected, None otherwise.

        Raises:
            InferenceError: If the AI service is unavailable.
        """
        prompt = self._build_gap_analysis_prompt(
            source_section=source_section,
            target_text=target_text,
            dependency_type=dependency_type,
            source_title=source_title,
            target_title=target_title,
        )

        # Load agent config from registry (Req 7.4)
        system_prompt, temperature, max_tokens, _fallback_used = (
            self._get_agent_config(dependency_type)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        # Call inference with agent parameters (Req 7.4)
        response = await self._inference_client.chat_completion(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=60.0,
        )

        # Parse the AI response
        finding = self._parse_gap_response(
            response=response,
            source_section=source_section,
            prompt_summary=prompt[:500],
        )

        return finding

    def _get_agent_config(
        self, dependency_type: str = "references"
    ) -> tuple[str, float, int, bool]:
        """Get the Change Impact Analyst agent configuration for gap analysis.

        Loads the agent archetype from the registry. Falls back to the
        Regulatory Compliance Auditor if not found, recording the fallback.

        Handles YAML schema validation failures by rejecting the invalid
        file, logging the error, and retaining the default configuration
        (Req 7.6).

        Args:
            dependency_type: The dependency type for context-aware instructions.

        Returns:
            Tuple of (system_prompt, temperature, max_tokens, fallback_used).
            fallback_used is True when the primary archetype was not found
            and the Regulatory Compliance Auditor was used instead.
        """
        # Default values matching the Change Impact Analyst archetype
        default_temperature = 0.2
        default_max_tokens = 4096

        if self._agent_registry is None:
            # No registry available — use built-in system prompt
            return (
                self._get_system_prompt(dependency_type),
                default_temperature,
                default_max_tokens,
                False,
            )

        try:
            # Try to load the Change Impact Analyst archetype (Req 7.4)
            archetypes = self._agent_registry.list_archetypes()
            for archetype in archetypes:
                if archetype.get("archetype") == CHANGE_IMPACT_ANALYST:
                    system_prompt = archetype.get("system_prompt", "")
                    if not system_prompt:
                        system_prompt = self._get_system_prompt(dependency_type)
                    tuning = archetype.get("contextual_tuning", {})
                    temperature = tuning.get("temperature", default_temperature)
                    max_tokens = tuning.get("max_tokens", default_max_tokens)
                    return system_prompt, temperature, max_tokens, False

            # Fallback: try Regulatory Compliance Auditor (Req 7.5)
            for archetype in archetypes:
                if archetype.get("archetype") == FALLBACK_AGENT:
                    system_prompt = archetype.get("system_prompt", "")
                    system_prompt += _FALLBACK_PROMPT_SUFFIX
                    tuning = archetype.get("contextual_tuning", {})
                    temperature = tuning.get("temperature", default_temperature)
                    max_tokens = tuning.get("max_tokens", default_max_tokens)
                    logger.info(
                        "Change Impact Analyst archetype not found, "
                        "using Regulatory Compliance Auditor as fallback "
                        "for gap analysis"
                    )
                    return system_prompt, temperature, max_tokens, True

        except Exception as e:
            # Handle YAML schema validation failure (Req 7.6):
            # reject file, log error, retain previous (default) config
            logger.error(
                "Failed to load agent archetype for gap analysis (YAML schema "
                "validation failure or other error): %s. Retaining default "
                "configuration.",
                str(e),
            )

        # Default fallback — use built-in system prompt
        return (
            self._get_system_prompt(dependency_type),
            default_temperature,
            default_max_tokens,
            False,
        )

    def get_fallback_metadata(self) -> dict[str, Any] | None:
        """Check if agent fallback is being used and return metadata.

        Returns metadata dict for recording in job metadata when fallback
        is active, or None if the primary agent is available.

        Returns:
            Dict with fallback details if fallback is used, None otherwise.
        """
        _sys_prompt, _temp, _max_tok, fallback_used = self._get_agent_config()
        if fallback_used:
            return {
                "fallback_used": {
                    "missing_archetype": CHANGE_IMPACT_ANALYST,
                    "used_archetype": FALLBACK_AGENT,
                }
            }
        return None

    def _build_gap_analysis_prompt(
        self,
        source_section: dict[str, str],
        target_text: str,
        dependency_type: str,
        source_title: str,
        target_title: str,
    ) -> str:
        """Build the prompt for gap analysis of a single section.

        Args:
            source_section: Dict with "heading" and "content" keys.
            target_text: Full text of the target document.
            dependency_type: Type of dependency between documents.
            source_title: Title of the source document.
            target_title: Title of the target document.

        Returns:
            Formatted prompt string.
        """
        # Truncate target text to avoid exceeding context window
        target_excerpt = target_text[:8000]

        return (
            f"Analyze the following source section from '{source_title}' "
            f"against the target document '{target_title}'.\n\n"
            f"Dependency type: {dependency_type}\n\n"
            f"SOURCE SECTION: {source_section['heading']}\n"
            f"---\n{source_section['content'][:2000]}\n---\n\n"
            f"TARGET DOCUMENT CONTENT:\n"
            f"---\n{target_excerpt}\n---\n\n"
            f"Determine if the target document adequately covers the "
            f"requirements/content in this source section.\n\n"
            f"If a gap exists, respond with a JSON object:\n"
            f'{{"gap_found": true, "target_section": "<section heading or '
            f'not_found>", "target_content_excerpt": "<first 300 chars of '
            f'relevant target text>", "gap_type": "<missing|contradicts|'
            f'incomplete|outdated>", "severity": "<critical|major|minor>", '
            f'"remediation_suggestion": "<one sentence recommendation>"}}\n\n'
            f"If no gap exists, respond with:\n"
            f'{{"gap_found": false}}'
        )

    def _get_system_prompt(self, dependency_type: str) -> str:
        """Get the system prompt with dependency-type-aware instructions.

        Args:
            dependency_type: Type of dependency between documents.

        Returns:
            System prompt string for the Change_Impact_Analyst.
        """
        base_prompt = (
            "You are a Change Impact Analyst specializing in regulated "
            "document management. Your role is to identify misalignments "
            "between document pairs.\n\n"
            "Classification rules:\n"
            "- CRITICAL: The target document contains statements that "
            "directly contradict the source content.\n"
            "- MAJOR: The target document is missing content that the "
            "source now requires or mandates.\n"
            "- MINOR: The target document uses outdated terminology or "
            "references but remains functionally correct.\n\n"
        )

        type_instructions = {
            "validates": (
                "Dependency type 'validates': Every requirement in the "
                "source MUST have corresponding coverage in the target. "
                "Missing coverage is MAJOR."
            ),
            "implements": (
                "Dependency type 'implements': Test cases must cover all "
                "updated requirements. Missing tests are MAJOR."
            ),
            "references": (
                "Dependency type 'references': Only direct contradictions "
                "are flagged. Missing references are MINOR unless they "
                "create ambiguity."
            ),
            "trains_on": (
                "Dependency type 'trains_on': Procedural changes in the "
                "source require training content updates. Safety-critical "
                "changes are CRITICAL."
            ),
            "derived_from": (
                "Dependency type 'derived_from': Template changes require "
                "regeneration review. Structural changes are MAJOR."
            ),
        }

        type_instruction = type_instructions.get(dependency_type, "")
        return base_prompt + type_instruction + (
            "\n\nRules:\n"
            "1. Provide specific section references for ALL findings.\n"
            "2. Require clear evidence before reporting a gap.\n"
            "3. Consider the regulatory context (GxP, ALCOA+).\n"
            "4. Output structured JSON as specified in the user prompt."
        )

    def _parse_gap_response(
        self,
        response: str,
        source_section: dict[str, str],
        prompt_summary: str,
    ) -> dict | None:
        """Parse the AI response into a gap finding dict.

        Args:
            response: Raw AI response text.
            source_section: The source section that was analyzed.
            prompt_summary: First 500 chars of the prompt for audit trail.

        Returns:
            A gap finding dict conforming to GapFindingSchema, or None
            if no gap was detected.
        """
        try:
            # Try to extract JSON from the response
            # Handle cases where response has markdown code blocks
            cleaned = response.strip()
            if cleaned.startswith("```"):
                # Remove markdown code block markers
                lines = cleaned.split("\n")
                json_lines = [
                    line for line in lines
                    if not line.strip().startswith("```")
                ]
                cleaned = "\n".join(json_lines)

            parsed = json.loads(cleaned)

            if not parsed.get("gap_found", False):
                return None

            # Calculate token count estimate (chars / 4 as rough estimate)
            token_count = (len(prompt_summary) + len(response)) // 4

            return {
                "source_section": source_section["heading"],
                "source_content_excerpt": source_section["content"][:300],
                "target_section": parsed.get("target_section", "not_found"),
                "target_content_excerpt": parsed.get(
                    "target_content_excerpt", ""
                )[:300],
                "gap_type": parsed.get("gap_type", "missing"),
                "severity": parsed.get("severity", "minor"),
                "remediation_suggestion": parsed.get(
                    "remediation_suggestion", "Review and update required."
                ),
                "inference_prompt_summary": prompt_summary[:500],
                "model_response_summary": response[:500],
                "token_count": token_count,
            }
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning(
                "Failed to parse gap analysis response for section: %s",
                source_section["heading"],
            )
            return None


# ---------------------------------------------------------------------------
# Module-level utility functions
# ---------------------------------------------------------------------------


def limit_gap_findings(
    findings: list[dict], max_count: int = MAX_GAP_FINDINGS
) -> list[dict]:
    """Retain top findings by severity priority.

    Sorts findings by severity (critical > major > minor) and retains
    at most max_count findings.

    Args:
        findings: List of gap finding dicts with "severity" key.
        max_count: Maximum number of findings to retain.

    Returns:
        List of retained findings, sorted by severity priority.
    """
    if len(findings) <= max_count:
        return sorted(
            findings,
            key=lambda f: SEVERITY_PRIORITY.get(f.get("severity", "minor"), 2),
        )

    # Sort by severity priority (critical first, then major, then minor)
    sorted_findings = sorted(
        findings,
        key=lambda f: SEVERITY_PRIORITY.get(f.get("severity", "minor"), 2),
    )

    return sorted_findings[:max_count]
