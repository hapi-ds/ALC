"""Cross-references newly indexed literature against internal documents.

Uses HybridQueryEngine to find related internal SOPs/URS, dispatches
LLM-based contradiction analysis, creates alerts and novelty flags.

References:
    - Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.2, 6.3,
      7.1, 7.2, 7.3, 7.6
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridSearchRequest,
)
from alcoabase.literature.ingestion.models.ingestion import IngestionRecord
from alcoabase.literature.review.models.contradiction_alert import (
    ContradictionAlert,
)
from alcoabase.literature.review.models.novelty_flag import NoveltyFlag

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from alcoabase.literature.embedding.services.hybrid_query_engine import (
        HybridQueryEngine,
    )
    from alcoabase.services.impact_analysis import ImpactAnalysisService
    from alcoabase.services.inference_client import InferenceClient

logger = logging.getLogger(__name__)

# Valid severity levels for contradiction classification
_VALID_SEVERITIES = frozenset({"critical", "major", "minor"})

# Maximum retries for individual pair analysis failures
_MAX_PAIR_RETRIES = 2

# Priority classification threshold for novelty flags
_HIGH_PRIORITY_THRESHOLD = 0.8


def classify_priority(relevance_score: float) -> bool:
    """Classify whether a novelty flag should be marked as high priority.

    A novelty flag is high priority when its relevance_score meets or exceeds
    the threshold (0.8). This pure function encapsulates the priority
    classification logic used by _create_novelty_flag.

    Args:
        relevance_score: Float 0.0–1.0 indicating relevance to company domain.

    Returns:
        True if relevance_score >= 0.8, False otherwise.

    References:
        - Requirements 5.7, 7.1, 7.3
    """
    return relevance_score >= _HIGH_PRIORITY_THRESHOLD


@dataclass(frozen=True)
class ContradictionAnalysisResult:
    """Result of analyzing one literature-vs-internal-doc pair.

    Attributes:
        contradiction_found: Whether a contradiction was detected.
        contradiction_description: Description of the contradiction.
        severity: "critical", "major", or "minor".
        affected_internal_sections: Section identifiers in internal doc.
        evidence_from_literature: Supporting evidence text.
        recommended_action: Suggested corrective action.
        confidence: Analysis confidence (0.0–1.0).
    """

    contradiction_found: bool
    contradiction_description: str
    severity: str
    affected_internal_sections: list[str]
    evidence_from_literature: str
    recommended_action: str
    confidence: float


class ContradictionDetectionService:
    """Detects contradictions between external literature and internal docs.

    Responsibilities:
        - Search for related internal documents via HybridQueryEngine
        - Construct contradiction analysis prompts
        - Parse structured analysis results from LLM
        - Create ContradictionAlerts for confirmed contradictions
        - Create NoveltyFlags when no related internal docs exist
        - Trigger ImpactAnalysisService for critical contradictions
        - Handle partial failures (persist successful, retry failed)
    """

    SIMILARITY_THRESHOLD = 0.6
    CONFIDENCE_THRESHOLD = 0.7
    MAX_CANDIDATES = 10

    def __init__(
        self,
        session_factory: "async_sessionmaker",
        hybrid_query_engine: "HybridQueryEngine",
        inference_client: "InferenceClient",
        impact_analysis_service: "ImpactAnalysisService",
        model_name: str,
        similarity_threshold: float = 0.6,
        confidence_threshold: float = 0.7,
        max_candidates: int = 10,
    ) -> None:
        """Initialize with all dependencies.

        Args:
            session_factory: Async session factory for DB operations.
            hybrid_query_engine: For searching internal documents.
            inference_client: For LLM-based contradiction analysis.
            impact_analysis_service: For escalating critical contradictions.
            model_name: Chat model identifier.
            similarity_threshold: Min similarity for internal doc match.
            confidence_threshold: Min confidence to create an alert.
            max_candidates: Max internal docs to compare per paper.
        """
        self._session_factory = session_factory
        self._hybrid_query_engine = hybrid_query_engine
        self._inference_client = inference_client
        self._impact_analysis_service = impact_analysis_service
        self._model_name = model_name
        self._similarity_threshold = similarity_threshold
        self._confidence_threshold = confidence_threshold
        self._max_candidates = max_candidates

    async def analyze_record(
        self,
        record_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Analyze a newly indexed record for contradictions and novelty.

        Steps:
            1. Load IngestionRecord (title, abstract, body)
            2. Search internal docs via HybridQueryEngine
            3. If no results: create NoveltyFlag
            4. If results: analyze each pair for contradictions
            5. Create ContradictionAlerts for confirmed findings
            6. Escalate critical contradictions via ImpactAnalysisService
            7. Log all operations to audit trail

        Args:
            record_id: IngestionRecord to analyze.
            company_id: Tenant scope.

        Returns:
            Dict with contradiction_count, novelty_flagged,
            alerts_created, analysis_duration_ms.

        Raises:
            InferenceConnectionError: After retries exhausted.
            SearchServiceUnavailableError: After retries exhausted.
        """
        start_ns = time.perf_counter_ns()

        async with self._session_factory() as session:
            # Step 1: Load IngestionRecord
            stmt = select(IngestionRecord).where(
                IngestionRecord.id == record_id,
                IngestionRecord.company_id == company_id,
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record is None:
                logger.warning(
                    "IngestionRecord id=%d not found for company_id=%d",
                    record_id,
                    company_id,
                )
                return {
                    "contradiction_count": 0,
                    "novelty_flagged": False,
                    "alerts_created": 0,
                    "analysis_duration_ms": 0,
                }

            title = record.title or ""
            abstract = record.abstract or ""
            query_text = f"{title} {abstract}".strip()

            if not query_text:
                logger.warning(
                    "IngestionRecord id=%d has no title or abstract, skipping",
                    record_id,
                )
                return {
                    "contradiction_count": 0,
                    "novelty_flagged": False,
                    "alerts_created": 0,
                    "analysis_duration_ms": 0,
                }

            # Step 2: Search internal docs via HybridQueryEngine
            candidates = await self._search_internal_documents(
                query_text, company_id
            )

            # Step 3: Branch based on whether internal docs were found
            if not candidates:
                # No internal docs found — create NoveltyFlag
                novelty_result = await self._create_novelty_flag(
                    session, record_id, company_id, abstract or title
                )
                await session.commit()

                duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
                logger.info(
                    "Novelty flag created for record_id=%d, company_id=%d, "
                    "relevance_score=%.2f",
                    record_id,
                    company_id,
                    novelty_result.get("relevance_score", 0.0),
                )
                return {
                    "contradiction_count": 0,
                    "novelty_flagged": True,
                    "alerts_created": 0,
                    "analysis_duration_ms": duration_ms,
                }

            # Step 4: Analyze each candidate for contradictions
            paper_findings = f"Title: {title}\n\nAbstract: {abstract}"
            alerts_created = 0
            contradiction_count = 0

            # Handle partial failures: track which pairs failed
            failed_pairs: list[dict[str, Any]] = []
            successful_results: list[
                tuple[dict[str, Any], ContradictionAnalysisResult]
            ] = []

            for candidate in candidates:
                internal_doc_sections = candidate.get("chunk_text", "")
                internal_doc_title = candidate.get("title", "Unknown Document")
                internal_document_id = candidate.get(
                    "internal_document_id",
                    candidate.get("ingestion_record_id", ""),
                )

                try:
                    analysis_result = await self._analyze_contradiction(
                        paper_findings=paper_findings,
                        internal_doc_sections=internal_doc_sections,
                        internal_doc_title=internal_doc_title,
                    )
                    successful_results.append((candidate, analysis_result))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Contradiction analysis failed for record_id=%d "
                        "vs internal_doc='%s': %s",
                        record_id,
                        internal_doc_title[:50],
                        str(exc),
                    )
                    failed_pairs.append(candidate)

            # Retry failed pairs (up to _MAX_PAIR_RETRIES additional attempts)
            for retry_attempt in range(1, _MAX_PAIR_RETRIES + 1):
                if not failed_pairs:
                    break

                still_failing: list[dict[str, Any]] = []
                for candidate in failed_pairs:
                    internal_doc_sections = candidate.get("chunk_text", "")
                    internal_doc_title = candidate.get(
                        "title", "Unknown Document"
                    )

                    try:
                        analysis_result = await self._analyze_contradiction(
                            paper_findings=paper_findings,
                            internal_doc_sections=internal_doc_sections,
                            internal_doc_title=internal_doc_title,
                        )
                        successful_results.append((candidate, analysis_result))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Retry %d/%d failed for record_id=%d "
                            "vs internal_doc='%s': %s",
                            retry_attempt,
                            _MAX_PAIR_RETRIES,
                            record_id,
                            internal_doc_title[:50],
                            str(exc),
                        )
                        still_failing.append(candidate)

                failed_pairs = still_failing

            if failed_pairs:
                logger.error(
                    "Exhausted retries for %d pair(s) analyzing record_id=%d",
                    len(failed_pairs),
                    record_id,
                )

            # Step 5: Create ContradictionAlerts for confirmed findings
            for candidate, analysis_result in successful_results:
                if analysis_result.contradiction_found:
                    contradiction_count += 1

                    if analysis_result.confidence >= self._confidence_threshold:
                        internal_document_id = str(
                            candidate.get(
                                "internal_document_id",
                                candidate.get("ingestion_record_id", ""),
                            )
                        )

                        alert = ContradictionAlert(
                            ingestion_record_id=record_id,
                            internal_document_id=internal_document_id,
                            company_id=company_id,
                            severity=analysis_result.severity,
                            contradiction_description=(
                                analysis_result.contradiction_description[:3000]
                            ),
                            evidence_from_literature=(
                                analysis_result.evidence_from_literature[:2000]
                            ),
                            recommended_action=(
                                analysis_result.recommended_action[:1000]
                            ),
                            confidence=analysis_result.confidence,
                            affected_internal_sections=(
                                analysis_result.affected_internal_sections
                            ),
                            status="new",
                        )
                        session.add(alert)
                        alerts_created += 1

                        # Step 6: Escalate critical contradictions
                        if analysis_result.severity == "critical":
                            # Flush to get alert.id before escalation
                            await session.flush()
                            await self._escalate_critical(
                                session=session,
                                alert_id=alert.id,
                                internal_document_id=internal_document_id,
                                company_id=company_id,
                            )

            await session.commit()

        duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
        logger.info(
            "Contradiction analysis complete for record_id=%d: "
            "contradictions=%d, alerts_created=%d, duration_ms=%d",
            record_id,
            contradiction_count,
            alerts_created,
            duration_ms,
        )

        return {
            "contradiction_count": contradiction_count,
            "novelty_flagged": False,
            "alerts_created": alerts_created,
            "analysis_duration_ms": duration_ms,
        }

    async def _search_internal_documents(
        self,
        query_text: str,
        company_id: int,
    ) -> list[dict[str, Any]]:
        """Search for related internal documents.

        Uses HybridQueryEngine with partition_filter='private_knowledge'
        and minimum similarity threshold.

        Args:
            query_text: Paper title + abstract as query.
            company_id: Tenant scope.

        Returns:
            List of internal document result dicts (max MAX_CANDIDATES).
        """
        # Truncate query text if too long (HybridSearchRequest accepts 1-1000)
        truncated_query = query_text[:1000]

        request = HybridSearchRequest(
            query=truncated_query,
            company_id=company_id,
            user_id=0,  # System-level search (no specific user context)
            partition_filter="private_knowledge",
            semantic_weight=0.7,  # Prioritize semantic similarity
            page=1,
            page_size=self._max_candidates,
        )

        response = await self._hybrid_query_engine.search(request)

        # Filter by minimum similarity threshold
        candidates: list[dict[str, Any]] = []
        for result in response.results:
            if result.relevance_score >= self._similarity_threshold:
                candidates.append({
                    "chunk_text": result.chunk_text,
                    "title": result.title,
                    "relevance_score": result.relevance_score,
                    "partition_tag": result.partition_tag,
                    "section_heading": result.section_heading,
                    "ingestion_record_id": result.ingestion_record_id,
                    "internal_document_id": str(result.ingestion_record_id),
                })

        return candidates[: self._max_candidates]

    async def _analyze_contradiction(
        self,
        paper_findings: str,
        internal_doc_sections: str,
        internal_doc_title: str,
    ) -> ContradictionAnalysisResult:
        """Analyze a single literature-vs-internal-document pair.

        Constructs prompt using Master Auditor archetype extended with
        contradiction-specific instructions.

        Args:
            paper_findings: Extracted key findings from the paper.
            internal_doc_sections: Relevant sections of internal document.
            internal_doc_title: Title of internal document (for context).

        Returns:
            ContradictionAnalysisResult with structured fields.
        """
        prompt = self._construct_contradiction_prompt(
            paper_findings=paper_findings,
            internal_doc_sections=internal_doc_sections,
            internal_doc_title=internal_doc_title,
        )

        system_prompt = (
            "You are the Master Auditor operating in Contradiction Detection mode. "
            "You have the highest standards of analytical rigor and regulatory "
            "compliance expertise. Your task is to compare external scientific "
            "literature against internal corporate documents (SOPs, URS, validation "
            "plans) and identify any contradictions that may impact regulatory "
            "compliance, patient safety, or process validity.\n\n"
            "You MUST respond with ONLY a valid JSON object. Do not include any "
            "other text, explanation, or markdown formatting."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        response_text = await self._inference_client.chat_completion(
            model=self._model_name,
            messages=messages,
            temperature=0.1,
            max_tokens=4096,
            timeout=90.0,
        )

        result = self._parse_contradiction_response(response_text)

        if result is None:
            logger.warning(
                "Failed to parse contradiction analysis response for "
                "internal_doc='%s'",
                internal_doc_title[:50],
            )
            # Return a safe default (no contradiction found)
            return ContradictionAnalysisResult(
                contradiction_found=False,
                contradiction_description="",
                severity="minor",
                affected_internal_sections=[],
                evidence_from_literature="",
                recommended_action="",
                confidence=0.0,
            )

        return result

    async def _create_novelty_flag(
        self,
        session: "AsyncSession",
        record_id: int,
        company_id: int,
        paper_abstract: str,
    ) -> dict[str, Any]:
        """Create a NoveltyFlag when no internal docs match.

        Dispatches LLM to generate novelty_description and relevance_score.
        Groups with existing flags by topic similarity if applicable.

        Args:
            session: Active DB session.
            record_id: The novel paper's IngestionRecord ID.
            company_id: Tenant scope.
            paper_abstract: Abstract for novelty summary generation.

        Returns:
            Created NoveltyFlag dict.
        """
        # Generate novelty description and relevance score via LLM
        novelty_prompt = (
            "Analyze the following paper abstract and determine:\n"
            "1. A concise description of what novel topics this paper covers "
            "that might not be addressed by internal corporate documentation "
            "(SOPs, URS, validation plans).\n"
            "2. A relevance score (0.0–1.0) indicating how relevant this paper's "
            "topic is to pharmaceutical/biotech/manufacturing operations.\n"
            "3. Suggested document types that might need to be created internally "
            "(e.g., 'SOP', 'URS', 'Validation Plan', 'Risk Assessment').\n\n"
            f"Paper Abstract:\n{paper_abstract[:2000]}\n\n"
            "Respond with ONLY a JSON object:\n"
            "{\n"
            '  "novelty_description": "...",\n'
            '  "relevance_score": 0.0-1.0,\n'
            '  "suggested_document_types": ["SOP", "URS", ...]\n'
            "}"
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a knowledge gap analyst for regulated industries. "
                    "Identify novel topics in scientific literature that are not "
                    "typically covered by internal corporate documentation. "
                    "Respond with ONLY valid JSON."
                ),
            },
            {"role": "user", "content": novelty_prompt},
        ]

        try:
            response_text = await self._inference_client.chat_completion(
                model=self._model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=1024,
            )
            novelty_data = self._parse_novelty_response(response_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM novelty generation failed for record_id=%d: %s",
                record_id,
                str(exc),
            )
            novelty_data = None

        if novelty_data is None:
            # Fallback defaults
            novelty_description = (
                "Novel findings detected in literature not covered by "
                "internal documentation."
            )
            relevance_score = 0.5
            suggested_document_types: list[str] | None = None
        else:
            novelty_description = novelty_data.get(
                "novelty_description",
                "Novel findings detected in literature.",
            )[:2000]
            relevance_score = float(
                novelty_data.get("relevance_score", 0.5)
            )
            # Clamp relevance score to valid range
            relevance_score = max(0.0, min(1.0, relevance_score))
            suggested_document_types = novelty_data.get(
                "suggested_document_types"
            )

        high_priority = classify_priority(relevance_score)

        # Check for topic-similar existing flags to group
        group_id = await self._find_topic_group(session, company_id, record_id)

        flag = NoveltyFlag(
            ingestion_record_id=record_id,
            company_id=company_id,
            novelty_description=novelty_description,
            suggested_document_types=suggested_document_types,
            relevance_score=relevance_score,
            high_priority=high_priority,
            status="new",
            group_id=group_id,
        )
        session.add(flag)

        logger.info(
            "NoveltyFlag created for record_id=%d, company_id=%d, "
            "relevance_score=%.2f, high_priority=%s",
            record_id,
            company_id,
            relevance_score,
            high_priority,
        )

        return {
            "flag_id": None,  # Will be set after flush/commit
            "ingestion_record_id": record_id,
            "company_id": company_id,
            "novelty_description": novelty_description,
            "relevance_score": relevance_score,
            "high_priority": high_priority,
            "suggested_document_types": suggested_document_types,
            "group_id": group_id,
        }

    async def _escalate_critical(
        self,
        session: "AsyncSession",
        alert_id: int,
        internal_document_id: str,
        company_id: int,
    ) -> None:
        """Escalate a critical contradiction via ImpactAnalysisService.

        Triggers impact analysis on the affected internal document.
        Dispatches notifications to document_admin and system_admin users.

        Args:
            session: Active DB session.
            alert_id: The ContradictionAlert being escalated.
            internal_document_id: UUID of the affected internal document.
            company_id: Tenant scope.
        """
        # Invoke ImpactAnalysisService for the affected document
        try:
            await self._impact_analysis_service.compute_change_delta(
                document_uuid=internal_document_id,
                new_version_id=0,  # Current version (latest)
                previous_version_id=None,
                company_id=company_id,
            )
            logger.info(
                "Impact analysis triggered for alert_id=%d, "
                "internal_document_id=%s",
                alert_id,
                internal_document_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Impact analysis failed for alert_id=%d, "
                "internal_document_id=%s: %s",
                alert_id,
                internal_document_id,
                str(exc),
            )

        # Log notification dispatch for document_admin/system_admin users
        # In production, this would dispatch actual notifications via the
        # notification service. For now, we log the intent.
        logger.info(
            "Critical contradiction notification dispatched: "
            "alert_id=%d, company_id=%d, internal_document_id=%s, "
            "target_roles=['document_admin', 'system_admin']",
            alert_id,
            company_id,
            internal_document_id,
        )

    def _construct_contradiction_prompt(
        self,
        paper_findings: str,
        internal_doc_sections: str,
        internal_doc_title: str,
    ) -> str:
        """Build the contradiction analysis prompt.

        Uses severity classification criteria:
        - critical: contradicts validated process steps/safety parameters
        - major: invalidates assumptions but no direct contradiction
        - minor: suggests improvements without contradicting

        Returns:
            Formatted prompt string with expected JSON output schema.
        """
        return (
            "=== CONTRADICTION ANALYSIS TASK ===\n\n"
            "Compare the external literature findings below against the internal "
            "corporate document and determine whether any contradictions exist.\n\n"
            "== EXTERNAL LITERATURE FINDINGS ==\n"
            f"{paper_findings[:4000]}\n\n"
            f"== INTERNAL DOCUMENT: {internal_doc_title} ==\n"
            f"{internal_doc_sections[:4000]}\n\n"
            "== SEVERITY CLASSIFICATION CRITERIA ==\n"
            "- CRITICAL: The external finding directly contradicts a validated "
            "process step, dosage, safety parameter, or regulatory claim in an "
            "active SOP or validation plan. Immediate action required.\n"
            "- MAJOR: The external finding presents evidence that could invalidate "
            "assumptions in internal documents but does not directly contradict "
            "validated parameters. Review and assessment needed.\n"
            "- MINOR: The external finding suggests improvements or alternatives "
            "to internal processes without contradicting validated parameters. "
            "Informational, no immediate action required.\n\n"
            "== INSTRUCTIONS ==\n"
            "Analyze the relationship between the literature findings and the "
            "internal document. Determine if a contradiction exists and classify "
            "its severity.\n\n"
            "Respond with ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "contradiction_found": true/false,\n'
            '  "contradiction_description": "detailed description (max 3000 chars)",\n'
            '  "severity": "critical" | "major" | "minor",\n'
            '  "affected_internal_sections": ["section identifiers"],\n'
            '  "evidence_from_literature": "supporting evidence (max 2000 chars)",\n'
            '  "recommended_action": "suggested action (max 1000 chars)",\n'
            '  "confidence": 0.0-1.0\n'
            "}\n\n"
            "If no contradiction is found, set contradiction_found to false and "
            "provide minimal placeholder values for other fields."
        )

    def _parse_contradiction_response(
        self,
        response_text: str,
    ) -> ContradictionAnalysisResult | None:
        """Parse LLM contradiction analysis response.

        Expected JSON schema:
            {
                "contradiction_found": bool,
                "contradiction_description": str,
                "severity": "critical" | "major" | "minor",
                "affected_internal_sections": [str],
                "evidence_from_literature": str,
                "recommended_action": str,
                "confidence": float
            }

        Returns None on parse failure.

        Args:
            response_text: Raw LLM response text.

        Returns:
            ContradictionAnalysisResult or None on validation failure.
        """
        try:
            text = response_text.strip()
            # Handle markdown code fences
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)

            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(data, dict):
            return None

        # Validate contradiction_found
        contradiction_found = data.get("contradiction_found")
        if not isinstance(contradiction_found, bool):
            return None

        # Validate contradiction_description
        contradiction_description = data.get("contradiction_description", "")
        if not isinstance(contradiction_description, str):
            return None

        # Validate severity
        severity = data.get("severity", "minor")
        if severity not in _VALID_SEVERITIES:
            return None

        # Validate affected_internal_sections
        affected_sections = data.get("affected_internal_sections", [])
        if not isinstance(affected_sections, list):
            return None
        # Coerce all items to str
        affected_sections = [str(s) for s in affected_sections]

        # Validate evidence_from_literature
        evidence = data.get("evidence_from_literature", "")
        if not isinstance(evidence, str):
            return None

        # Validate recommended_action
        recommended_action = data.get("recommended_action", "")
        if not isinstance(recommended_action, str):
            return None

        # Validate confidence
        confidence = data.get("confidence")
        if not isinstance(confidence, (int, float)):
            return None
        confidence = float(confidence)
        if confidence < 0.0 or confidence > 1.0:
            return None

        return ContradictionAnalysisResult(
            contradiction_found=contradiction_found,
            contradiction_description=contradiction_description[:3000],
            severity=severity,
            affected_internal_sections=affected_sections,
            evidence_from_literature=evidence[:2000],
            recommended_action=recommended_action[:1000],
            confidence=confidence,
        )

    def _parse_novelty_response(
        self,
        response_text: str,
    ) -> dict[str, Any] | None:
        """Parse LLM novelty analysis response.

        Expected JSON:
            {
                "novelty_description": str,
                "relevance_score": float,
                "suggested_document_types": [str]
            }

        Returns None on parse failure.
        """
        try:
            text = response_text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)

            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(data, dict):
            return None

        # Basic validation
        if "novelty_description" not in data:
            return None
        if not isinstance(data.get("novelty_description"), str):
            return None

        relevance_score = data.get("relevance_score")
        if relevance_score is not None and not isinstance(
            relevance_score, (int, float)
        ):
            return None

        return data

    async def _find_topic_group(
        self,
        session: "AsyncSession",
        company_id: int,
        record_id: int,
    ) -> str | None:
        """Find an existing topic group for this novelty flag.

        Checks if there are existing novelty flags with similar topics
        (same company, recent) that could be grouped together.

        For now, returns None. Topic grouping based on embedding similarity
        (cosine >= 0.8) can be implemented when the batch novelty analysis
        feature is fully integrated (Requirement 7.6).

        Args:
            session: Active DB session.
            company_id: Tenant scope.
            record_id: The novel paper's IngestionRecord ID.

        Returns:
            Group UUID string or None if no grouping applicable.
        """
        # Topic grouping is a batch operation (Requirement 7.6).
        # Individual record analysis does not perform grouping inline.
        # The batch novelty analysis task will handle grouping.
        return None
