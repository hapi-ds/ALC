"""Traceability Matrix Service for AI-Powered Traceability & Gap Discovery.

Orchestrates traceability matrix generation: requirement extraction from
source documents, test case extraction from target documents, three-pass
matching (exact ID, cross-reference, semantic), deduplication, and persistence.

Uses the Traceability Analyst agent archetype for AI-powered extraction
via InferenceClient, with fallback to Change Impact Analyst if unavailable.

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11,
                    4.1, 4.3, 4.4, 4.5, 4.6, 6.4, 6.5, 6.7
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import cast, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from alcoabase.services.agent_registry import AgentRegistryService
    from alcoabase.services.cross_reference import CrossReferenceService
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.job_tracker import JobTracker
    from alcoabase.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Connection timeout for InferenceClient calls (seconds)
_INFERENCE_CONNECTION_TIMEOUT = 30.0

# Per-document extraction timeout (seconds) — Requirement 6.7
_EXTRACTION_TIMEOUT = 120.0

# Maximum retries for retryable errors (503, 429)
_MAX_RETRIES = 3

# Exponential backoff delays (seconds)
_BACKOFF_DELAYS = [1.0, 2.0, 4.0]

# Maximum generation timeout (seconds) — Requirement 1.6
_GENERATION_TIMEOUT = 600.0

# Maximum source documents per request — Requirement 1.5
_MAX_SOURCE_DOCUMENTS = 10

# Maximum target documents per request — Requirement 1.5
_MAX_TARGET_DOCUMENTS = 20

# Maximum retries for database persistence — Requirement 4.6
_DB_PERSIST_MAX_RETRIES = 3

# Exponential backoff delays for DB persistence (seconds)
_DB_PERSIST_BACKOFF_DELAYS = [1.0, 2.0, 4.0]

# Operation name for job tracking
_JOB_OPERATION = "traceability_matrix_generation"

# Requirement ID patterns for extraction
_REQUIREMENT_ID_PATTERNS = [
    r"REQ-\d{3,}",
    r"URS-\d{3,}",
    r"R\.\d+\.\d+",
    r"FR-\d{3,}",
]

# Test case ID patterns for extraction
_TEST_CASE_ID_PATTERNS = [
    r"TC-\d{3,}",
    r"IQ-\d{3,}",
    r"OQ-\d{3,}",
    r"PQ-\d{3,}",
    r"MVP-\d{3,}",
]


# Prompt for requirement extraction
_REQUIREMENT_EXTRACTION_PROMPT = """Extract all identifiable requirements from the following document text.

For each requirement, identify:
1. requirement_id: The formal identifier (patterns: REQ-NNN, URS-NNN, R.N.N, FR-NNN)
2. requirement_text: The full requirement statement (first 500 characters)
3. section_heading: The section heading where this requirement appears
4. acceptance_criteria: Any measurable acceptance criteria associated with this requirement

Return a JSON object with the following structure:
{
  "requirements": [
    {
      "requirement_id": "<ID>",
      "requirement_text": "<text, max 500 chars>",
      "section_heading": "<heading>",
      "acceptance_criteria": "<criteria or null>"
    }
  ]
}

Rules:
- Extract ALL identifiable requirements — do not skip items.
- If no formal ID is found but a clear requirement statement exists, use the section heading as a pseudo-ID.
- Truncate requirement_text to 500 characters maximum.
- Include section references for all extracted items.

Document text:
"""

# Prompt for test case extraction
_TEST_CASE_EXTRACTION_PROMPT = """Extract all identifiable test cases from the following document text.

For each test case, identify:
1. test_case_id: The formal identifier (patterns: TC-NNN, IQ-NNN, OQ-NNN, PQ-NNN, MVP-NNN)
2. test_description: What is being verified (first 500 characters)
3. expected_result: The pass/fail criteria or expected outcome
4. section_heading: The section heading where this test case appears

Return a JSON object with the following structure:
{
  "test_cases": [
    {
      "test_case_id": "<ID>",
      "test_description": "<description, max 500 chars>",
      "expected_result": "<expected result or null>",
      "section_heading": "<heading>"
    }
  ]
}

Rules:
- Extract ALL identifiable test cases — do not skip items.
- If no formal ID is found but a clear test case exists, use the section heading as a pseudo-ID.
- Truncate test_description to 500 characters maximum.
- Include section references for all extracted items.

Document text:
"""


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ExtractedRequirement:
    """A requirement extracted from a source document.

    Attributes:
        requirement_id: Formal identifier (e.g., REQ-001, URS-001, R.1.1).
        requirement_text: Full requirement statement (max 500 chars).
        source_document_uuid: UUID of the source document.
        source_section: Section heading where the requirement appears.
        acceptance_criteria: Measurable acceptance criteria, if any.
    """

    requirement_id: str
    requirement_text: str
    source_document_uuid: str
    source_section: str
    acceptance_criteria: str | None = None


@dataclass
class ExtractedTestCase:
    """A test case extracted from a target document.

    Attributes:
        test_case_id: Formal identifier (e.g., TC-001, IQ-001, OQ-001).
        test_case_text: What is being verified (max 500 chars).
        target_document_uuid: UUID of the target document.
        target_section: Section heading where the test case appears.
        expected_result: Pass/fail criteria or expected outcome.
    """

    test_case_id: str
    test_case_text: str
    target_document_uuid: str
    target_section: str
    expected_result: str | None = None


@dataclass
class CandidateLink:
    """A candidate traceability link between a requirement and a test case.

    Attributes:
        requirement_id: Formal requirement identifier.
        requirement_text: Requirement statement text.
        source_document_uuid: UUID of the source document.
        source_section: Section in the source document.
        test_case_id: Formal test case identifier.
        test_case_text: Test case description text.
        target_document_uuid: UUID of the target document.
        target_section: Section in the target document.
        link_confidence: Confidence score (0.0 to 1.0).
        link_method: Method used to establish the link.
    """

    requirement_id: str
    requirement_text: str
    source_document_uuid: str
    source_section: str
    test_case_id: str
    test_case_text: str
    target_document_uuid: str
    target_section: str
    link_confidence: float
    link_method: str


@dataclass
class ExtractionMetadata:
    """Metadata about the extraction process for a single document.

    Attributes:
        document_uuid: UUID of the document processed.
        success: Whether extraction succeeded.
        error: Error message if extraction failed.
        timeout: Whether extraction timed out.
        items_extracted: Number of items extracted.
    """

    document_uuid: str
    success: bool = True
    error: str | None = None
    timeout: bool = False
    items_extracted: int = 0


@dataclass
class ExtractionResult:
    """Result of a batch extraction operation.

    Attributes:
        requirements: List of extracted requirements (for requirement extraction).
        test_cases: List of extracted test cases (for test case extraction).
        metadata: Per-document extraction metadata.
        failed: Whether the entire extraction failed (all retries exhausted).
        failure_phase: Phase at which failure occurred.
        failure_message: Error message for the failure.
    """

    requirements: list[ExtractedRequirement] = field(default_factory=list)
    test_cases: list[ExtractedTestCase] = field(default_factory=list)
    metadata: list[ExtractionMetadata] = field(default_factory=list)
    failed: bool = False
    failure_phase: str | None = None
    failure_message: str | None = None


@dataclass
class MatchingResult:
    """Result of the three-pass matching strategy.

    Attributes:
        links: Deduplicated list of candidate links.
        status: "completed" or "partial_success" if a pass was skipped.
        metadata: Additional metadata about the matching process.
    """

    links: list[CandidateLink] = field(default_factory=list)
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class TraceabilityMatrixService:
    """Service for orchestrating traceability matrix generation.

    Provides requirement extraction from source documents, test case
    extraction from target documents, three-pass matching, deduplication,
    and matrix persistence. Uses the Traceability Analyst agent archetype
    for AI-powered extraction via InferenceClient.

    Args:
        knowledge_service: Service for text extraction and semantic search.
        inference_client: Async HTTP client for vLLM inference.
        agent_registry: Service for loading agent archetypes.
        cross_reference_service: Service for document cross-reference detection.
        session_factory: SQLAlchemy async session factory for DB operations.
        job_tracker: JobTracker for async job state management.
    """

    def __init__(
        self,
        knowledge_service: KnowledgeService | None = None,
        inference_client: InferenceClient | None = None,
        agent_registry: AgentRegistryService | None = None,
        cross_reference_service: CrossReferenceService | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        job_tracker: JobTracker | None = None,
    ) -> None:
        """Initialize TraceabilityMatrixService.

        Args:
            knowledge_service: KnowledgeService for text extraction.
            inference_client: InferenceClient for AI inference.
            agent_registry: AgentRegistryService for loading agent archetypes.
            cross_reference_service: CrossReferenceService for cross-ref matching.
            session_factory: Async session factory for database operations.
            job_tracker: JobTracker for managing job states.
        """
        self._knowledge_service = knowledge_service
        self._inference_client = inference_client
        self._agent_registry = agent_registry
        self._cross_reference_service = cross_reference_service
        self._session_factory = session_factory
        self._job_tracker = job_tracker

    # ───────────────────────────────────────────────────────────────────────
    # Requirement Extraction (Requirement 1.2, 6.4, 6.7)
    # ───────────────────────────────────────────────────────────────────────

    async def extract_requirements(
        self,
        source_documents: list[dict[str, Any]],
        company_id: int,
    ) -> ExtractionResult:
        """Extract requirements from source documents using AI.

        For each source document, extracts text via KnowledgeService, then
        uses the Traceability Analyst agent via InferenceClient to identify
        requirement IDs, requirement text, section headings, and acceptance
        criteria.

        Handles InferenceClient unavailability with 3 retries and exponential
        backoff for HTTP 503/429. Marks job as "failed" on exhaustion.
        Handles per-document extraction timeout of 120s.

        Args:
            source_documents: List of dicts with at minimum
                {"document_uuid": str, "document_id": int}.
            company_id: Company ID for tenant scoping.

        Returns:
            ExtractionResult with extracted requirements and metadata.
        """
        result = ExtractionResult()

        if not source_documents:
            return result

        # Load agent configuration
        system_prompt, temperature, max_tokens, fallback_used = (
            self._get_agent_config()
        )

        for doc in source_documents:
            doc_uuid = doc["document_uuid"]
            doc_metadata = ExtractionMetadata(document_uuid=doc_uuid)

            try:
                # Extract text from document via KnowledgeService
                doc_text = await self._extract_document_text(
                    doc_uuid, company_id
                )

                if not doc_text:
                    doc_metadata.success = False
                    doc_metadata.error = "No text content extracted"
                    result.metadata.append(doc_metadata)
                    continue

                # Use AI to extract requirements with timeout
                requirements = await self._extract_requirements_with_ai(
                    doc_text=doc_text,
                    doc_uuid=doc_uuid,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                result.requirements.extend(requirements)
                doc_metadata.items_extracted = len(requirements)
                result.metadata.append(doc_metadata)

            except _ExtractionTimeoutError:
                doc_metadata.success = False
                doc_metadata.timeout = True
                doc_metadata.error = (
                    f"Extraction timed out after {_EXTRACTION_TIMEOUT}s"
                )
                result.metadata.append(doc_metadata)
                logger.warning(
                    "Requirement extraction timed out for document %s",
                    doc_uuid,
                )

            except _InferenceUnavailableError as e:
                # InferenceClient exhausted all retries — mark as failed
                result.failed = True
                result.failure_phase = "extracting_requirements"
                result.failure_message = str(e)
                doc_metadata.success = False
                doc_metadata.error = str(e)
                result.metadata.append(doc_metadata)
                logger.error(
                    "Inference service unavailable during requirement "
                    "extraction for document %s: %s",
                    doc_uuid,
                    str(e),
                )
                return result

        return result

    # ───────────────────────────────────────────────────────────────────────
    # Test Case Extraction (Requirement 1.2, 6.4, 6.7)
    # ───────────────────────────────────────────────────────────────────────

    async def extract_test_cases(
        self,
        target_documents: list[dict[str, Any]],
        company_id: int,
    ) -> ExtractionResult:
        """Extract test cases from target documents using AI.

        For each target document, extracts text via KnowledgeService, then
        uses the Traceability Analyst agent via InferenceClient to identify
        test case IDs, test descriptions, expected results, and section
        headings.

        Handles InferenceClient unavailability with 3 retries and exponential
        backoff for HTTP 503/429. Marks job as "failed" on exhaustion.
        Handles per-document extraction timeout of 120s.

        Args:
            target_documents: List of dicts with at minimum
                {"document_uuid": str, "document_id": int}.
            company_id: Company ID for tenant scoping.

        Returns:
            ExtractionResult with extracted test cases and metadata.
        """
        result = ExtractionResult()

        if not target_documents:
            return result

        # Load agent configuration
        system_prompt, temperature, max_tokens, fallback_used = (
            self._get_agent_config()
        )

        for doc in target_documents:
            doc_uuid = doc["document_uuid"]
            doc_metadata = ExtractionMetadata(document_uuid=doc_uuid)

            try:
                # Extract text from document via KnowledgeService
                doc_text = await self._extract_document_text(
                    doc_uuid, company_id
                )

                if not doc_text:
                    doc_metadata.success = False
                    doc_metadata.error = "No text content extracted"
                    result.metadata.append(doc_metadata)
                    continue

                # Use AI to extract test cases with timeout
                test_cases = await self._extract_test_cases_with_ai(
                    doc_text=doc_text,
                    doc_uuid=doc_uuid,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                result.test_cases.extend(test_cases)
                doc_metadata.items_extracted = len(test_cases)
                result.metadata.append(doc_metadata)

            except _ExtractionTimeoutError:
                doc_metadata.success = False
                doc_metadata.timeout = True
                doc_metadata.error = (
                    f"Extraction timed out after {_EXTRACTION_TIMEOUT}s"
                )
                result.metadata.append(doc_metadata)
                logger.warning(
                    "Test case extraction timed out for document %s",
                    doc_uuid,
                )

            except _InferenceUnavailableError as e:
                # InferenceClient exhausted all retries — mark as failed
                result.failed = True
                result.failure_phase = "extracting_test_cases"
                result.failure_message = str(e)
                doc_metadata.success = False
                doc_metadata.error = str(e)
                result.metadata.append(doc_metadata)
                logger.error(
                    "Inference service unavailable during test case "
                    "extraction for document %s: %s",
                    doc_uuid,
                    str(e),
                )
                return result

        return result

    # ───────────────────────────────────────────────────────────────────────
    # Internal: Text Extraction
    # ───────────────────────────────────────────────────────────────────────

    async def _extract_document_text(
        self,
        document_uuid: str,
        company_id: int,
    ) -> str | None:
        """Extract text content from a document via KnowledgeService.

        Uses hybrid_search to retrieve indexed text chunks for the document
        and concatenates them to reconstruct the full text.

        Args:
            document_uuid: UUID of the document to extract text from.
            company_id: Company ID for tenant scoping.

        Returns:
            Extracted text content, or None if extraction fails.
        """
        if self._knowledge_service is None:
            logger.warning(
                "KnowledgeService not available, cannot extract text for "
                "document %s",
                document_uuid,
            )
            return None

        try:
            results, _ = self._knowledge_service.hybrid_search(
                query=document_uuid,
                user_id=0,  # System-level access
                limit=100,
                filters={"document_uuid": [document_uuid]},
            )

            if results:
                return "\n".join(r.excerpt for r in results)

            return None
        except Exception as e:
            logger.warning(
                "Failed to extract text for document %s: %s",
                document_uuid,
                str(e),
            )
            return None

    # ───────────────────────────────────────────────────────────────────────
    # Internal: AI-Powered Extraction with Retry and Timeout
    # ───────────────────────────────────────────────────────────────────────

    async def _extract_requirements_with_ai(
        self,
        doc_text: str,
        doc_uuid: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> list[ExtractedRequirement]:
        """Extract requirements from document text using AI with timeout.

        Sends the document text to the Traceability Analyst agent for
        requirement extraction. Enforces a 120s per-document timeout.

        Args:
            doc_text: Full text content of the document.
            doc_uuid: UUID of the source document.
            system_prompt: Agent system prompt.
            temperature: LLM temperature parameter.
            max_tokens: Maximum tokens for the response.

        Returns:
            List of ExtractedRequirement objects.

        Raises:
            _ExtractionTimeoutError: If extraction exceeds 120s.
            _InferenceUnavailableError: If inference service is unavailable
                after all retries.
        """
        user_prompt = _REQUIREMENT_EXTRACTION_PROMPT + doc_text[:8000]

        response_text = await self._call_inference_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=_EXTRACTION_TIMEOUT,
            phase="requirement_extraction",
        )

        return self._parse_requirements_response(response_text, doc_uuid)

    async def _extract_test_cases_with_ai(
        self,
        doc_text: str,
        doc_uuid: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> list[ExtractedTestCase]:
        """Extract test cases from document text using AI with timeout.

        Sends the document text to the Traceability Analyst agent for
        test case extraction. Enforces a 120s per-document timeout.

        Args:
            doc_text: Full text content of the document.
            doc_uuid: UUID of the target document.
            system_prompt: Agent system prompt.
            temperature: LLM temperature parameter.
            max_tokens: Maximum tokens for the response.

        Returns:
            List of ExtractedTestCase objects.

        Raises:
            _ExtractionTimeoutError: If extraction exceeds 120s.
            _InferenceUnavailableError: If inference service is unavailable
                after all retries.
        """
        user_prompt = _TEST_CASE_EXTRACTION_PROMPT + doc_text[:8000]

        response_text = await self._call_inference_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=_EXTRACTION_TIMEOUT,
            phase="test_case_extraction",
        )

        return self._parse_test_cases_response(response_text, doc_uuid)

    async def _call_inference_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        timeout: float,
        phase: str,
    ) -> str:
        """Call InferenceClient with retry logic and timeout.

        Implements 3 retries with exponential backoff for HTTP 503/429
        and connection errors. Enforces per-document timeout of 120s.
        Raises _InferenceUnavailableError on exhaustion.

        Args:
            system_prompt: System prompt for the agent.
            user_prompt: User prompt with document content.
            temperature: LLM temperature parameter.
            max_tokens: Maximum tokens for the response.
            timeout: Per-request timeout in seconds.
            phase: Current phase name for error reporting.

        Returns:
            Response text from the inference service.

        Raises:
            _ExtractionTimeoutError: If the request exceeds timeout.
            _InferenceUnavailableError: If all retries are exhausted.
        """
        from alcoabase.services.inference_client import (
            InferenceConnectionError,
            InferenceError,
            InferenceTimeoutError,
        )

        if self._inference_client is None:
            raise _InferenceUnavailableError(
                "InferenceClient not configured",
                phase=phase,
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        model_name = self._get_model_name()
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response_text = await asyncio.wait_for(
                    self._inference_client.chat_completion(
                        model=model_name,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                    ),
                    timeout=timeout,
                )
                return response_text

            except asyncio.TimeoutError:
                raise _ExtractionTimeoutError(
                    f"Extraction timed out after {timeout}s during {phase}"
                )

            except InferenceTimeoutError:
                raise _ExtractionTimeoutError(
                    f"Extraction timed out after {timeout}s during {phase}"
                )

            except InferenceConnectionError as e:
                last_error = e
                if attempt < _MAX_RETRIES - 1:
                    delay = _BACKOFF_DELAYS[attempt]
                    logger.warning(
                        "Inference connection failed during %s, "
                        "retrying in %.1fs (attempt %d/%d): %s",
                        phase,
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                        str(e),
                    )
                    await asyncio.sleep(delay)
                    continue

            except InferenceError as e:
                last_error = e
                # Retry on 503 and 429
                if e.status_code in (503, 429):
                    if attempt < _MAX_RETRIES - 1:
                        delay = _BACKOFF_DELAYS[attempt]
                        logger.warning(
                            "Inference returned %d during %s, "
                            "retrying in %.1fs (attempt %d/%d)",
                            e.status_code,
                            phase,
                            delay,
                            attempt + 1,
                            _MAX_RETRIES,
                        )
                        await asyncio.sleep(delay)
                        continue

                # Non-retryable error
                raise _InferenceUnavailableError(
                    f"Inference service error during {phase}: {e}",
                    phase=phase,
                    status_code=e.status_code,
                )

        # All retries exhausted
        raise _InferenceUnavailableError(
            f"Inference service unavailable after {_MAX_RETRIES} retries "
            f"during {phase}: {last_error}",
            phase=phase,
        )

    # ───────────────────────────────────────────────────────────────────────
    # Internal: Response Parsing
    # ───────────────────────────────────────────────────────────────────────

    def _parse_requirements_response(
        self,
        response_text: str,
        doc_uuid: str,
    ) -> list[ExtractedRequirement]:
        """Parse AI response into ExtractedRequirement objects.

        Extracts JSON from the response (handling markdown code blocks),
        validates the structure, and creates ExtractedRequirement instances.

        Args:
            response_text: Raw text response from the AI agent.
            doc_uuid: UUID of the source document.

        Returns:
            List of ExtractedRequirement objects.
        """
        try:
            data = self._extract_json(response_text)
            requirements_data = data.get("requirements", [])

            requirements: list[ExtractedRequirement] = []
            for item in requirements_data:
                req_id = item.get("requirement_id", "").strip()
                req_text = item.get("requirement_text", "").strip()

                if not req_id and not req_text:
                    continue

                # Truncate requirement_text to 500 chars
                req_text = req_text[:500]

                requirements.append(
                    ExtractedRequirement(
                        requirement_id=req_id,
                        requirement_text=req_text,
                        source_document_uuid=doc_uuid,
                        source_section=item.get("section_heading", ""),
                        acceptance_criteria=item.get("acceptance_criteria"),
                    )
                )

            return requirements

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(
                "Failed to parse requirement extraction response for "
                "document %s: %s",
                doc_uuid,
                str(e),
            )
            return []

    def _parse_test_cases_response(
        self,
        response_text: str,
        doc_uuid: str,
    ) -> list[ExtractedTestCase]:
        """Parse AI response into ExtractedTestCase objects.

        Extracts JSON from the response (handling markdown code blocks),
        validates the structure, and creates ExtractedTestCase instances.

        Args:
            response_text: Raw text response from the AI agent.
            doc_uuid: UUID of the target document.

        Returns:
            List of ExtractedTestCase objects.
        """
        try:
            data = self._extract_json(response_text)
            test_cases_data = data.get("test_cases", [])

            test_cases: list[ExtractedTestCase] = []
            for item in test_cases_data:
                tc_id = item.get("test_case_id", "").strip()
                tc_text = item.get("test_description", "").strip()

                if not tc_id and not tc_text:
                    continue

                # Truncate test_case_text to 500 chars
                tc_text = tc_text[:500]

                test_cases.append(
                    ExtractedTestCase(
                        test_case_id=tc_id,
                        test_case_text=tc_text,
                        target_document_uuid=doc_uuid,
                        target_section=item.get("section_heading", ""),
                        expected_result=item.get("expected_result"),
                    )
                )

            return test_cases

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(
                "Failed to parse test case extraction response for "
                "document %s: %s",
                doc_uuid,
                str(e),
            )
            return []

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """Extract JSON from AI response text.

        Handles responses wrapped in markdown code blocks (```json ... ```)
        or plain JSON.

        Args:
            response_text: Raw response text from the AI.

        Returns:
            Parsed JSON as a dictionary.

        Raises:
            json.JSONDecodeError: If JSON parsing fails.
        """
        json_text = response_text.strip()

        # Handle markdown code blocks
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0]
        elif "```" in json_text:
            parts = json_text.split("```")
            if len(parts) >= 3:
                json_text = parts[1]

        json_text = json_text.strip()

        # Try to find JSON object boundaries if parsing fails
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            # Try to find the first { and last }
            start = json_text.find("{")
            end = json_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(json_text[start : end + 1])
            raise

    # ───────────────────────────────────────────────────────────────────────
    # Three-Pass Matching Strategy (Requirements 1.2, 1.3, 1.7, 1.11)
    # ───────────────────────────────────────────────────────────────────────

    # Minimum semantic similarity threshold for link creation (Requirement 1.3)
    _SEMANTIC_MATCH_THRESHOLD = 0.5

    # Regex patterns for requirement ID matching in test case text
    _MATCH_REQUIREMENT_ID_PATTERNS = [
        re.compile(r"\b(REQ-\d{1,5})\b"),
        re.compile(r"\b(URS-\d{1,3}\.\d{1,3})\b"),
        re.compile(r"\b(R\.\d{1,3}\.\d{1,3})\b"),
    ]

    def pass_1_exact_id_match(
        self,
        requirements: list[ExtractedRequirement],
        test_cases: list[ExtractedTestCase],
    ) -> list[CandidateLink]:
        """Pass 1: Scan test case text for explicit requirement ID citations.

        For each test case, scans its text for requirement ID patterns
        (REQ-NNN, URS-N.N, R.N.N). When a match is found against a known
        requirement, creates a link with confidence 1.0.

        Args:
            requirements: List of extracted requirements from source documents.
            test_cases: List of extracted test cases from target documents.

        Returns:
            List of CandidateLink objects with link_confidence = 1.0 and
            link_method = "exact_id_match".
        """
        candidate_links: list[CandidateLink] = []

        # Build a lookup map from requirement_id to requirement
        req_map: dict[str, ExtractedRequirement] = {
            req.requirement_id: req for req in requirements
        }

        for test_case in test_cases:
            # Scan test case text for requirement ID patterns
            found_ids: set[str] = set()
            for pattern in self._MATCH_REQUIREMENT_ID_PATTERNS:
                for match in pattern.finditer(test_case.test_case_text):
                    found_ids.add(match.group(1))

            # Create links for IDs that match known requirements
            for req_id in found_ids:
                if req_id in req_map:
                    req = req_map[req_id]
                    candidate_links.append(
                        CandidateLink(
                            requirement_id=req.requirement_id,
                            requirement_text=req.requirement_text,
                            source_document_uuid=req.source_document_uuid,
                            source_section=req.source_section,
                            test_case_id=test_case.test_case_id,
                            test_case_text=test_case.test_case_text,
                            target_document_uuid=test_case.target_document_uuid,
                            target_section=test_case.target_section,
                            link_confidence=1.0,
                            link_method="exact_id_match",
                        )
                    )

        return candidate_links

    async def pass_2_cross_reference_match(
        self,
        requirements: list[ExtractedRequirement],
        test_cases: list[ExtractedTestCase],
        company_id: int,
    ) -> list[CandidateLink]:
        """Pass 2: Query CrossReferenceService for structural links.

        Queries the CrossReferenceService to find structural cross-references
        between source and target document pairs. When a cross-reference links
        a requirement ID to a test case document (or vice versa), creates a
        link with confidence 0.9.

        Handles CrossReferenceService unavailability gracefully by raising
        an exception (caller should mark job as "partial_success").

        Args:
            requirements: List of extracted requirements from source documents.
            test_cases: List of extracted test cases from target documents.
            company_id: Company ID for tenant scoping.

        Returns:
            List of CandidateLink objects with link_confidence = 0.9 and
            link_method = "cross_reference".

        Raises:
            Exception: When the CrossReferenceService is unreachable.
        """
        candidate_links: list[CandidateLink] = []

        if self._cross_reference_service is None:
            logger.warning(
                "CrossReferenceService not available, skipping pass 2"
            )
            return candidate_links

        # Build lookup maps
        req_map: dict[str, ExtractedRequirement] = {
            req.requirement_id: req for req in requirements
        }
        tc_map: dict[str, ExtractedTestCase] = {
            tc.test_case_id: tc for tc in test_cases
        }

        # Collect unique target document IDs for cross-reference extraction
        target_doc_uuids = list({tc.target_document_uuid for tc in test_cases})

        # Query cross-references from target documents to find requirement citations
        # The CrossReferenceService extracts references from documents
        cross_ref_map = (
            await self._cross_reference_service.build_cross_reference_map(
                reference_document_ids=[],  # Resolved by UUID below
                company_id=company_id,
            )
        )

        # Match requirement references found in target documents
        requirement_refs = cross_ref_map.get("requirement", [])
        for ref in requirement_refs:
            req_id = ref.reference_identifier
            if req_id in req_map:
                req = req_map[req_id]
                # Link to all test cases in the same document as the reference
                for tc in test_cases:
                    if tc.target_document_uuid == str(
                        ref.source_document_id
                    ) or ref.source_document_id in [
                        int(uuid) for uuid in target_doc_uuids
                        if uuid.isdigit()
                    ]:
                        candidate_links.append(
                            CandidateLink(
                                requirement_id=req.requirement_id,
                                requirement_text=req.requirement_text,
                                source_document_uuid=req.source_document_uuid,
                                source_section=req.source_section,
                                test_case_id=tc.test_case_id,
                                test_case_text=tc.test_case_text,
                                target_document_uuid=tc.target_document_uuid,
                                target_section=tc.target_section,
                                link_confidence=0.9,
                                link_method="cross_reference",
                            )
                        )

        # Match test case references found in source documents
        test_case_refs = cross_ref_map.get("test_case", [])
        for ref in test_case_refs:
            tc_id = ref.reference_identifier
            if tc_id in tc_map:
                tc = tc_map[tc_id]
                # Link to all requirements in the same source document
                for req in requirements:
                    candidate_links.append(
                        CandidateLink(
                            requirement_id=req.requirement_id,
                            requirement_text=req.requirement_text,
                            source_document_uuid=req.source_document_uuid,
                            source_section=req.source_section,
                            test_case_id=tc.test_case_id,
                            test_case_text=tc.test_case_text,
                            target_document_uuid=tc.target_document_uuid,
                            target_section=tc.target_section,
                            link_confidence=0.9,
                            link_method="cross_reference",
                        )
                    )

        return candidate_links

    async def pass_3_semantic_match(
        self,
        requirements: list[ExtractedRequirement],
        test_cases: list[ExtractedTestCase],
        company_id: int,
    ) -> list[CandidateLink]:
        """Pass 3: Compute embedding similarity via KnowledgeService.

        Generates embeddings for all requirement texts and test case texts,
        then computes cosine similarity between each pair. Creates links
        where similarity >= 0.5 threshold, with link_confidence equal to
        the similarity score.

        Handles KnowledgeService unavailability gracefully by raising an
        exception (caller should mark job as "partial_success").

        Args:
            requirements: List of extracted requirements from source documents.
            test_cases: List of extracted test cases from target documents.
            company_id: Company ID for tenant scoping.

        Returns:
            List of CandidateLink objects with link_confidence = similarity
            score and link_method = "semantic_match". Only includes matches
            where similarity >= 0.5.

        Raises:
            Exception: When the KnowledgeService is unreachable.
        """
        candidate_links: list[CandidateLink] = []

        if self._knowledge_service is None:
            logger.warning(
                "KnowledgeService not available, skipping pass 3"
            )
            return candidate_links

        if not requirements or not test_cases:
            return candidate_links

        # Generate embeddings for requirement texts and test case texts
        req_texts = [req.requirement_text for req in requirements]
        tc_texts = [tc.test_case_text for tc in test_cases]

        req_embeddings = await self._knowledge_service.generate_embeddings(
            req_texts
        )
        tc_embeddings = await self._knowledge_service.generate_embeddings(
            tc_texts
        )

        # Compute cosine similarity between each requirement and test case
        for i, req in enumerate(requirements):
            for j, tc in enumerate(test_cases):
                similarity = self._cosine_similarity(
                    req_embeddings[i], tc_embeddings[j]
                )

                # Only create links above the threshold (Requirement 1.3)
                if similarity >= self._SEMANTIC_MATCH_THRESHOLD:
                    candidate_links.append(
                        CandidateLink(
                            requirement_id=req.requirement_id,
                            requirement_text=req.requirement_text,
                            source_document_uuid=req.source_document_uuid,
                            source_section=req.source_section,
                            test_case_id=tc.test_case_id,
                            test_case_text=tc.test_case_text,
                            target_document_uuid=tc.target_document_uuid,
                            target_section=tc.target_section,
                            link_confidence=similarity,
                            link_method="semantic_match",
                        )
                    )

        return candidate_links

    def deduplicate_links(
        self,
        candidate_links: list[CandidateLink],
    ) -> list[CandidateLink]:
        """Deduplicate candidate links by (requirement_id, test_case_id) pair.

        For duplicate pairs detected via multiple methods, retains the link
        with the highest confidence score and merges all detection methods
        into the link_methods metadata.

        Args:
            candidate_links: List of all candidate links from all three passes.

        Returns:
            Deduplicated list where each (requirement_id, test_case_id) pair
            appears exactly once with the highest confidence score.
        """
        # Group links by (requirement_id, test_case_id)
        link_groups: dict[tuple[str, str], list[CandidateLink]] = {}
        for link in candidate_links:
            key = (link.requirement_id, link.test_case_id)
            if key not in link_groups:
                link_groups[key] = []
            link_groups[key].append(link)

        # For each group, keep the link with highest confidence
        deduplicated: list[CandidateLink] = []
        self._dedup_methods: dict[tuple[str, str], list[str]] = {}

        for key, group in link_groups.items():
            # Sort by confidence descending, take the best
            group.sort(key=lambda lnk: lnk.link_confidence, reverse=True)
            best_link = group[0]
            deduplicated.append(best_link)

            # Collect all unique methods for this pair (ordered by confidence)
            methods = list(dict.fromkeys(lnk.link_method for lnk in group))
            self._dedup_methods[key] = methods

        return deduplicated

    def get_link_methods(
        self, requirement_id: str, test_case_id: str
    ) -> list[str]:
        """Get all detection methods for a deduplicated link pair.

        Must be called after deduplicate_links() to retrieve the merged
        methods list for a specific (requirement_id, test_case_id) pair.

        Args:
            requirement_id: The requirement identifier.
            test_case_id: The test case identifier.

        Returns:
            List of all detection methods that found this link pair.
        """
        return self._dedup_methods.get(
            (requirement_id, test_case_id), []
        )

    async def run_three_pass_matching(
        self,
        requirements: list[ExtractedRequirement],
        test_cases: list[ExtractedTestCase],
        company_id: int,
    ) -> "MatchingResult":
        """Execute the full three-pass matching strategy.

        Runs all three passes sequentially, handles service unavailability
        gracefully, deduplicates results, and returns the final link set
        with status metadata.

        Args:
            requirements: List of extracted requirements from source documents.
            test_cases: List of extracted test cases from target documents.
            company_id: Company ID for tenant scoping.

        Returns:
            MatchingResult with deduplicated links, status, and metadata.
        """
        all_candidates: list[CandidateLink] = []
        result = MatchingResult()
        skipped_passes: list[str] = []

        # Pass 1: Exact ID matching (always runs, no external dependencies)
        pass_1_links = self.pass_1_exact_id_match(requirements, test_cases)
        all_candidates.extend(pass_1_links)
        result.metadata["pass_1_count"] = len(pass_1_links)

        # Pass 2: Cross-reference matching
        try:
            pass_2_links = await self.pass_2_cross_reference_match(
                requirements, test_cases, company_id
            )
            all_candidates.extend(pass_2_links)
            result.metadata["pass_2_count"] = len(pass_2_links)
        except Exception as e:
            logger.warning(
                "Pass 2 (cross-reference) skipped due to service "
                "unavailability: %s",
                str(e),
            )
            skipped_passes.append("cross_reference")
            result.metadata["pass_2_count"] = 0
            result.metadata["pass_2_skipped"] = True
            result.metadata["pass_2_error"] = str(e)

        # Pass 3: Semantic matching
        try:
            pass_3_links = await self.pass_3_semantic_match(
                requirements, test_cases, company_id
            )
            all_candidates.extend(pass_3_links)
            result.metadata["pass_3_count"] = len(pass_3_links)
        except Exception as e:
            logger.warning(
                "Pass 3 (semantic) skipped due to service "
                "unavailability: %s",
                str(e),
            )
            skipped_passes.append("semantic_match")
            result.metadata["pass_3_count"] = 0
            result.metadata["pass_3_skipped"] = True
            result.metadata["pass_3_error"] = str(e)

        # Deduplicate all candidate links (Requirement 1.7)
        deduplicated = self.deduplicate_links(all_candidates)
        result.links = deduplicated
        result.metadata["total_candidates_before_dedup"] = len(all_candidates)
        result.metadata["total_links_after_dedup"] = len(deduplicated)

        # Determine status based on skipped passes (Requirement 1.11)
        if skipped_passes:
            result.status = "partial_success"
            result.metadata["skipped_passes"] = skipped_passes
        else:
            result.status = "completed"

        return result

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec_a: First embedding vector.
            vec_b: Second embedding vector.

        Returns:
            Cosine similarity score clamped to [0.0, 1.0]. Returns 0.0 if
            either vector has zero magnitude or vectors have different lengths.
        """
        if len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = sum(a * a for a in vec_a) ** 0.5
        magnitude_b = sum(b * b for b in vec_b) ** 0.5

        if magnitude_a == 0.0 or magnitude_b == 0.0:
            return 0.0

        similarity = dot_product / (magnitude_a * magnitude_b)
        # Clamp to valid range to handle floating point errors
        return max(0.0, min(1.0, similarity))

    # ───────────────────────────────────────────────────────────────────────
    # Internal: Agent Configuration
    # ───────────────────────────────────────────────────────────────────────

    def _get_agent_config(self) -> tuple[str, float, int, bool]:
        """Get the Traceability Analyst agent configuration.

        Loads the agent archetype from the registry. Falls back to the
        Change Impact Analyst if not found, appending a system prompt
        suffix for traceability focus. Records the fallback event.

        Validates the archetype YAML against agent-definition-v2.json schema.
        If validation fails, rejects the file, logs the validation error
        identifying the failing field, and retains the default configuration.
        (Requirement 6.6)

        Returns:
            Tuple of (system_prompt, temperature, max_tokens, fallback_used).
            fallback_used is True when the primary archetype was not found
            and the Change Impact Analyst was used instead.
        """
        default_system_prompt = (
            "You are a Traceability Analyst specializing in requirement-to-test "
            "mapping for regulated document management systems (GxP, FDA, EMA "
            "compliance). Extract requirements and test cases from documents, "
            "identifying IDs, text, section headings, and acceptance criteria. "
            "Output structured JSON matching the expected schema exactly."
        )
        default_temperature = 0.15
        default_max_tokens = 4096

        if self._agent_registry is None:
            return (
                default_system_prompt,
                default_temperature,
                default_max_tokens,
                False,
            )

        try:
            archetypes = self._agent_registry.list_archetypes()

            # Try to load the Traceability Analyst archetype
            for archetype in archetypes:
                if archetype.get("archetype") == "Traceability Analyst":
                    # Validate against agent-definition-v2.json schema (Req 6.6)
                    validation_errors = self._validate_archetype_schema(
                        archetype
                    )
                    if validation_errors:
                        logger.error(
                            "Traceability Analyst archetype failed schema "
                            "validation against agent-definition-v2.json. "
                            "Rejecting file and retaining default "
                            "configuration. Failing fields: %s",
                            "; ".join(validation_errors),
                        )
                        # Reject the file, retain default config
                        return (
                            default_system_prompt,
                            default_temperature,
                            default_max_tokens,
                            False,
                        )

                    system_prompt = archetype.get(
                        "system_prompt", default_system_prompt
                    )
                    tuning = archetype.get("contextual_tuning", {})
                    temperature = tuning.get(
                        "temperature", default_temperature
                    )
                    max_tokens = tuning.get("max_tokens", default_max_tokens)
                    return system_prompt, temperature, max_tokens, False

            # Fallback: try Change Impact Analyst (Requirement 6.5)
            for archetype in archetypes:
                if archetype.get("archetype") == "Change Impact Analyst":
                    system_prompt = archetype.get("system_prompt", "")
                    system_prompt += (
                        "\n\nAdditional context: You are acting as a "
                        "Traceability Analyst. Focus on requirement-to-test "
                        "traceability mapping rather than change impact "
                        "assessment. Extract requirements and test cases "
                        "from documents, identifying IDs, text, section "
                        "headings, and acceptance criteria. Output structured "
                        "JSON matching the expected schema exactly."
                    )
                    tuning = archetype.get("contextual_tuning", {})
                    temperature = tuning.get(
                        "temperature", default_temperature
                    )
                    max_tokens = tuning.get("max_tokens", default_max_tokens)
                    logger.info(
                        "Traceability Analyst archetype not found, "
                        "using Change Impact Analyst as fallback"
                    )
                    return system_prompt, temperature, max_tokens, True

        except Exception as e:
            logger.error(
                "Failed to load agent archetype: %s. "
                "Retaining default configuration.",
                str(e),
            )

        return default_system_prompt, default_temperature, default_max_tokens, False

    def _validate_archetype_schema(
        self, archetype_data: dict[str, Any]
    ) -> list[str]:
        """Validate archetype data against agent-definition-v2.json schema.

        Uses jsonschema to validate the archetype definition. Returns a list
        of validation error messages identifying failing fields.

        Args:
            archetype_data: The archetype definition dict to validate.

        Returns:
            List of validation error strings. Empty if valid.
        """
        try:
            import jsonschema
            from pathlib import Path

            schema_path = (
                Path(__file__).resolve().parents[5]
                / "agents"
                / "schema"
                / "agent-definition-v2.json"
            )

            if not schema_path.exists():
                logger.debug(
                    "Schema file not found at %s, skipping validation",
                    schema_path,
                )
                return []

            with open(schema_path) as f:
                schema = json.load(f)

            validator = jsonschema.Draft7Validator(schema)
            errors: list[str] = []
            for error in validator.iter_errors(archetype_data):
                path = (
                    " -> ".join(str(p) for p in error.absolute_path)
                    if error.absolute_path
                    else "root"
                )
                errors.append(f"{path}: {error.message}")

            return errors

        except ImportError:
            logger.debug(
                "jsonschema not available, skipping archetype validation"
            )
            return []
        except Exception as e:
            logger.warning(
                "Failed to validate archetype schema: %s", str(e)
            )
            return []

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

    # ───────────────────────────────────────────────────────────────────────
    # Orchestration: validate_and_enqueue (Requirement 1.1, 1.4, 1.5, 1.9)
    # ───────────────────────────────────────────────────────────────────────

    async def validate_and_enqueue(
        self,
        request: Any,
        company_id: int,
        user_id: int,
    ) -> dict[str, str]:
        """Validate a matrix generation request and enqueue the job.

        Validates document IDs exist in company scope, checks for overlapping
        source/target, checks document count limits, and checks for existing
        processing jobs (same docs → 409).

        Args:
            request: GenerateMatrixRequest with source/target doc IDs and metadata.
            company_id: Company ID for tenant scoping.
            user_id: ID of the requesting user.

        Returns:
            Dict with 'job_id' key containing the created job UUID.

        Raises:
            DocumentNotFoundError: When document IDs don't exist in company scope.
            ValidationError: When source/target overlap or limits exceeded.
            JobConflictError: When a processing job already exists for same docs.
        """
        from alcoabase.services.job_tracker import JobConflictError

        # Check for overlapping source and target document IDs
        source_set = set(request.source_document_ids)
        target_set = set(request.target_document_ids)
        overlap = source_set & target_set
        if overlap:
            raise _ValidationError(
                f"Documents cannot be both source and target: {sorted(overlap)}"
            )

        if self._session_factory is None:
            raise _ValidationError("Database session factory not configured")

        async with self._session_factory() as session:
            # Validate all document IDs exist in company scope
            from alcoabase.models.document import Document

            all_doc_ids = list(source_set | target_set)
            result = await session.execute(
                select(Document.id).where(
                    Document.id.in_(all_doc_ids),
                    Document.company_id == company_id,
                )
            )
            existing_ids = set(result.scalars().all())
            missing_ids = set(all_doc_ids) - existing_ids
            if missing_ids:
                raise _DocumentNotFoundError(
                    f"Documents not found in company scope: {sorted(missing_ids)}"
                )

            # Create a canonical key for duplicate job detection
            sorted_source = sorted(request.source_document_ids)
            sorted_target = sorted(request.target_document_ids)
            doc_key = f"trace:{sorted_source}:{sorted_target}"

            # Create job via JobTracker (raises JobConflictError if duplicate)
            if self._job_tracker is None:
                raise _ValidationError("JobTracker not configured")

            job = await self._job_tracker.create_job(
                session,
                document_uuid=doc_key,
                operation="traceability_matrix_generation",
                estimated_duration_seconds=max(
                    60,
                    30 * (len(request.source_document_ids) + len(request.target_document_ids)),
                ),
                company_id=company_id,
            )

            await session.commit()

        return {"job_id": job.job_id}

    # ───────────────────────────────────────────────────────────────────────
    # Orchestration: generate_matrix (Requirement 1.1, 1.6, 4.1, 4.4)
    # ───────────────────────────────────────────────────────────────────────

    async def generate_matrix(
        self,
        job_id: str,
        request: Any,
        company_id: int,
        user_id: int,
    ) -> Any:
        """Orchestrate the full matrix generation pipeline.

        Executes: extract requirements → extract test cases → three-pass
        matching → orphan detection → compute metrics → persist matrix.

        Implements 600s timeout with partial_success persistence and
        3 retries with exponential backoff on database write failure.

        Args:
            job_id: UUID of the job to track progress.
            request: GenerateMatrixRequest with source/target doc IDs.
            company_id: Company ID for tenant scoping.
            user_id: ID of the requesting user.

        Returns:
            The persisted TraceabilityMatrix record or a result dict.

        Raises:
            Exception: On unrecoverable errors after retries exhausted.
        """
        start_time = time.monotonic()

        # Capture document versions at generation time
        source_document_versions: list[dict[str, Any]] = []
        target_document_versions: list[dict[str, Any]] = []

        if self._session_factory is not None:
            async with self._session_factory() as session:
                from alcoabase.models.document import Document, DocumentVersion

                # Capture source document versions
                for doc_id in request.source_document_ids:
                    result = await session.execute(
                        select(Document.document_uuid, DocumentVersion.id).join(
                            DocumentVersion,
                            DocumentVersion.document_id == Document.id,
                        ).where(
                            Document.id == doc_id,
                            Document.company_id == company_id,
                        ).order_by(DocumentVersion.id.desc()).limit(1)
                    )
                    row = result.first()
                    if row:
                        source_document_versions.append(
                            {"document_uuid": row[0], "version_id": row[1]}
                        )

                # Capture target document versions
                for doc_id in request.target_document_ids:
                    result = await session.execute(
                        select(Document.document_uuid, DocumentVersion.id).join(
                            DocumentVersion,
                            DocumentVersion.document_id == Document.id,
                        ).where(
                            Document.id == doc_id,
                            Document.company_id == company_id,
                        ).order_by(DocumentVersion.id.desc()).limit(1)
                    )
                    row = result.first()
                    if row:
                        target_document_versions.append(
                            {"document_uuid": row[0], "version_id": row[1]}
                        )

        # Build source/target document dicts for extraction using real UUIDs
        source_docs: list[dict[str, Any]] = []
        target_docs: list[dict[str, Any]] = []

        if self._session_factory is not None:
            async with self._session_factory() as session:
                from alcoabase.models.document import Document

                for doc_id in request.source_document_ids:
                    result = await session.execute(
                        select(Document.document_uuid).where(
                            Document.id == doc_id,
                            Document.company_id == company_id,
                        )
                    )
                    doc_uuid = result.scalar_one_or_none()
                    source_docs.append({
                        "document_uuid": doc_uuid or f"doc-{doc_id}",
                        "document_id": doc_id,
                    })

                for doc_id in request.target_document_ids:
                    result = await session.execute(
                        select(Document.document_uuid).where(
                            Document.id == doc_id,
                            Document.company_id == company_id,
                        )
                    )
                    doc_uuid = result.scalar_one_or_none()
                    target_docs.append({
                        "document_uuid": doc_uuid or f"doc-{doc_id}",
                        "document_id": doc_id,
                    })
        else:
            source_docs = [
                {"document_uuid": f"doc-{doc_id}", "document_id": doc_id}
                for doc_id in request.source_document_ids
            ]
            target_docs = [
                {"document_uuid": f"doc-{doc_id}", "document_id": doc_id}
                for doc_id in request.target_document_ids
            ]

        # Extract requirements (with timeout check)
        elapsed = time.monotonic() - start_time
        if elapsed >= _GENERATION_TIMEOUT:
            return await self._persist_partial_success(
                job_id=job_id,
                request=request,
                source_docs=source_docs,
                target_docs=target_docs,
                source_document_versions=source_document_versions,
                target_document_versions=target_document_versions,
                links=[],
                requirements=[],
                test_cases=[],
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                unprocessed_reason="Timeout before requirement extraction",
            )

        req_result = await self.extract_requirements(source_docs, company_id)
        if req_result.failed:
            if self._job_tracker and self._session_factory:
                async with self._session_factory() as session:
                    await self._job_tracker.fail_job(
                        session, job_id,
                        req_result.failure_message or "Extraction failed",
                    )
                    await session.commit()
            raise _InferenceUnavailableError(
                req_result.failure_message or "Requirement extraction failed",
                phase="extracting_requirements",
            )

        # Extract test cases (with timeout check)
        elapsed = time.monotonic() - start_time
        if elapsed >= _GENERATION_TIMEOUT:
            return await self._persist_partial_success(
                job_id=job_id,
                request=request,
                source_docs=source_docs,
                target_docs=target_docs,
                source_document_versions=source_document_versions,
                target_document_versions=target_document_versions,
                links=[],
                requirements=req_result.requirements,
                test_cases=[],
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                unprocessed_reason="Timeout before test case extraction",
            )

        tc_result = await self.extract_test_cases(target_docs, company_id)
        if tc_result.failed:
            if self._job_tracker and self._session_factory:
                async with self._session_factory() as session:
                    await self._job_tracker.fail_job(
                        session, job_id,
                        tc_result.failure_message or "Extraction failed",
                    )
                    await session.commit()
            raise _InferenceUnavailableError(
                tc_result.failure_message or "Test case extraction failed",
                phase="extracting_test_cases",
            )

        # Three-pass matching (with timeout check)
        elapsed = time.monotonic() - start_time
        if elapsed >= _GENERATION_TIMEOUT:
            return await self._persist_partial_success(
                job_id=job_id,
                request=request,
                source_docs=source_docs,
                target_docs=target_docs,
                source_document_versions=source_document_versions,
                target_document_versions=target_document_versions,
                links=[],
                requirements=req_result.requirements,
                test_cases=tc_result.test_cases,
                company_id=company_id,
                user_id=user_id,
                start_time=start_time,
                unprocessed_reason="Timeout before link matching",
            )

        matching_result = await self.run_three_pass_matching(
            req_result.requirements, tc_result.test_cases, company_id
        )

        # Compute generation duration
        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Orphan detection — call if available, skip gracefully if not
        orphan_requirements: list[dict[str, Any]] = []
        orphan_test_cases: list[dict[str, Any]] = []
        try:
            from alcoabase.services.orphan_detection import (
                OrphanDetectionService,
            )
            orphan_service = OrphanDetectionService(
                inference_client=self._inference_client,
                agent_registry=self._agent_registry,
            )
            orphan_reqs = await orphan_service.identify_orphan_requirements(
                req_result.requirements, matching_result.links
            )
            orphan_tcs = await orphan_service.identify_orphan_test_cases(
                tc_result.test_cases, matching_result.links
            )
            orphan_requirements = [
                {
                    "requirement_id": o.requirement_id,
                    "requirement_text": o.requirement_text,
                    "source_document_uuid": o.source_document_uuid,
                    "source_section": o.source_section,
                    "severity": o.severity,
                    "suggested_action": o.suggested_action,
                }
                for o in orphan_reqs
            ]
            orphan_test_cases = [
                {
                    "test_case_id": o.test_case_id,
                    "test_case_text": o.test_case_text,
                    "target_document_uuid": o.target_document_uuid,
                    "target_section": o.target_section,
                    "risk_level": o.risk_level,
                    "suggested_action": o.suggested_action,
                }
                for o in orphan_tcs
            ]
        except (ImportError, AttributeError, Exception) as e:
            logger.info(
                "Orphan detection skipped (service not available): %s",
                str(e),
            )

        # Coverage metrics — call if available, skip gracefully if not
        coverage_metrics: dict[str, Any] = {}
        try:
            from alcoabase.services.coverage_metrics import (
                CoverageMetricsService,
            )
            coverage_service = CoverageMetricsService()
            coverage_metrics = coverage_service.compute_coverage_metrics(
                requirements=req_result.requirements,
                test_cases=tc_result.test_cases,
                links=matching_result.links,
                source_docs=source_docs,
                target_docs=target_docs,
            )
        except (ImportError, AttributeError, Exception) as e:
            logger.info(
                "Coverage metrics computation skipped (service not available): %s",
                str(e),
            )

        # Resolve parent matrix ID
        source_uuids = [v["document_uuid"] for v in source_document_versions] or [
            d["document_uuid"] for d in source_docs
        ]
        target_uuids = [v["document_uuid"] for v in target_document_versions] or [
            d["document_uuid"] for d in target_docs
        ]

        parent_matrix_id = None
        if self._session_factory:
            async with self._session_factory() as session:
                parent_matrix_id = await self._resolve_parent_matrix_id(
                    source_document_uuids=source_uuids,
                    target_document_uuids=target_uuids,
                    company_id=company_id,
                    session=session,
                )

        # Get agent config info
        _, _, _, fallback_used = self._get_agent_config()

        # Build matrix metadata — include matching metadata and fallback info
        matrix_metadata: dict[str, Any] = dict(matching_result.metadata)
        if fallback_used:
            matrix_metadata["fallback_used"] = {
                "missing_archetype": "Traceability Analyst",
                "used_archetype": "Change Impact Analyst",
            }

        # Record any per-document timeout events in metadata (Req 6.7)
        timeout_events: list[dict[str, str]] = []
        for meta in getattr(req_result, "metadata", []):
            if meta.timeout:
                timeout_events.append({
                    "document_uuid": meta.document_uuid,
                    "phase": "requirement_extraction",
                    "error": meta.error or "Extraction timed out",
                })
        for meta in getattr(tc_result, "metadata", []):
            if meta.timeout:
                timeout_events.append({
                    "document_uuid": meta.document_uuid,
                    "phase": "test_case_extraction",
                    "error": meta.error or "Extraction timed out",
                })
        if timeout_events:
            matrix_metadata["timeout_events"] = timeout_events

        # Build matrix record
        matrix_data = _MatrixResult(
            matrix_id=str(uuid.uuid4()),
            matrix_name=request.matrix_name,
            description=getattr(request, "description", None),
            source_document_uuids=source_uuids,
            target_document_uuids=target_uuids,
            source_document_versions=source_document_versions,
            target_document_versions=target_document_versions,
            traceability_links=[
                {
                    "requirement_id": link.requirement_id,
                    "requirement_text": link.requirement_text,
                    "source_document_uuid": link.source_document_uuid,
                    "source_section": link.source_section,
                    "test_case_id": link.test_case_id,
                    "test_case_text": link.test_case_text,
                    "target_document_uuid": link.target_document_uuid,
                    "target_section": link.target_section,
                    "link_confidence": link.link_confidence,
                    "link_method": link.link_method,
                    "link_methods": self.get_link_methods(
                        link.requirement_id, link.test_case_id
                    ),
                    "verification_status": "unverified",
                }
                for link in matching_result.links
            ],
            orphan_requirements=orphan_requirements,
            orphan_test_cases=orphan_test_cases,
            coverage_metrics=coverage_metrics,
            status=matching_result.status,
            parent_matrix_id=parent_matrix_id,
            generation_duration_ms=duration_ms,
            agent_archetype_used="Traceability Analyst" if not fallback_used else "Change Impact Analyst (fallback)",
            model_used=self._get_model_name(),
            total_token_count=0,
            requesting_user_id=user_id,
            company_id=company_id,
            metadata=matrix_metadata,
        )

        # Persist with retries (Requirement 4.6)
        max_retries = 3
        backoff_delays = [1.0, 2.0, 4.0]

        for attempt in range(max_retries):
            try:
                if self._session_factory:
                    async with self._session_factory() as session:
                        from alcoabase.models.traceability import TraceabilityMatrix

                        matrix_record = TraceabilityMatrix(
                            matrix_id=matrix_data.matrix_id,
                            matrix_name=matrix_data.matrix_name,
                            description=matrix_data.description,
                            source_document_uuids=matrix_data.source_document_uuids,
                            target_document_uuids=matrix_data.target_document_uuids,
                            source_document_versions=matrix_data.source_document_versions,
                            target_document_versions=matrix_data.target_document_versions,
                            traceability_links=matrix_data.traceability_links,
                            orphan_requirements=matrix_data.orphan_requirements,
                            orphan_test_cases=matrix_data.orphan_test_cases,
                            coverage_metrics=matrix_data.coverage_metrics,
                            status=matrix_data.status,
                            parent_matrix_id=matrix_data.parent_matrix_id,
                            generation_timestamp=datetime.now(tz=timezone.utc),
                            generation_duration_ms=matrix_data.generation_duration_ms,
                            agent_archetype_used=matrix_data.agent_archetype_used,
                            model_used=matrix_data.model_used,
                            total_token_count=matrix_data.total_token_count,
                            requesting_user_id=matrix_data.requesting_user_id,
                            company_id=matrix_data.company_id,
                        )
                        session.add(matrix_record)
                        await session.flush()
                        await session.commit()

                        # Complete the job
                        if self._job_tracker:
                            async with self._session_factory() as job_session:
                                await self._job_tracker.complete_job(
                                    job_session, job_id, matrix_data.matrix_id
                                )
                                await job_session.commit()

                break  # Success
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff_delays[attempt])
                else:
                    # All retries exhausted — mark job as failed
                    if self._job_tracker and self._session_factory:
                        try:
                            async with self._session_factory() as fail_session:
                                await self._job_tracker.fail_job(
                                    fail_session,
                                    job_id,
                                    f"Database write failure after {max_retries} retries: {str(e)[:200]}",
                                )
                                await fail_session.commit()
                        except Exception:
                            pass
                    raise

        return matrix_data

    # ───────────────────────────────────────────────────────────────────────
    # Orchestration: _resolve_parent_matrix_id (Requirement 4.3)
    # ───────────────────────────────────────────────────────────────────────

    async def _resolve_parent_matrix_id(
        self,
        source_document_uuids: list[str],
        target_document_uuids: list[str],
        company_id: int,
        session: Any | None = None,
    ) -> str | None:
        """Find the most recent matrix with matching sorted source/target doc UUIDs.

        Uses sorted document UUID arrays for consistent matching regardless
        of input order.

        Args:
            source_document_uuids: Source document UUIDs for the new matrix.
            target_document_uuids: Target document UUIDs for the new matrix.
            company_id: Company ID for tenant scoping.
            session: Optional async session. If None, creates one from factory.

        Returns:
            The matrix_id of the most recent matching matrix, or None if
            this is the first matrix for this document set.
        """
        from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

        from alcoabase.models.traceability import TraceabilityMatrix

        sorted_source = sorted(source_document_uuids)
        sorted_target = sorted(target_document_uuids)

        async def _query(sess: Any) -> str | None:
            # Query for the most recent non-deleted matrix with matching doc sets
            result = await sess.execute(
                select(TraceabilityMatrix.matrix_id)
                .where(
                    TraceabilityMatrix.company_id == company_id,
                    TraceabilityMatrix.deleted_at.is_(None),
                    TraceabilityMatrix.source_document_uuids == cast(
                        sorted_source, PG_JSONB
                    ),
                    TraceabilityMatrix.target_document_uuids == cast(
                        sorted_target, PG_JSONB
                    ),
                )
                .order_by(TraceabilityMatrix.generation_timestamp.desc())
                .limit(1)
            )
            return result.scalars().first()

        if session is not None:
            return await _query(session)

        if self._session_factory is None:
            return None

        async with self._session_factory() as new_session:
            return await _query(new_session)

    # ───────────────────────────────────────────────────────────────────────
    # Orchestration: _persist_partial_success (Requirement 1.6)
    # ───────────────────────────────────────────────────────────────────────

    async def _persist_partial_success(
        self,
        job_id: str,
        request: Any,
        source_docs: list[dict[str, Any]],
        target_docs: list[dict[str, Any]],
        source_document_versions: list[dict[str, Any]],
        target_document_versions: list[dict[str, Any]],
        links: list[CandidateLink],
        requirements: list[ExtractedRequirement],
        test_cases: list[ExtractedTestCase],
        company_id: int,
        user_id: int,
        start_time: float,
        unprocessed_reason: str,
    ) -> _MatrixResult:
        """Persist a partial_success matrix when the 600s timeout is hit.

        Persists all links discovered so far and records unprocessed
        requirements in the matrix metadata.

        Args:
            job_id: UUID of the job.
            request: Original generation request.
            source_docs: Source document dicts.
            target_docs: Target document dicts.
            source_document_versions: Captured source doc versions.
            target_document_versions: Captured target doc versions.
            links: Links discovered so far.
            requirements: Requirements extracted so far.
            test_cases: Test cases extracted so far.
            company_id: Company ID for tenant scoping.
            user_id: Requesting user ID.
            start_time: Monotonic start time for duration calculation.
            unprocessed_reason: Reason for partial completion.

        Returns:
            The persisted _MatrixResult with status "partial_success".
        """
        duration_ms = int((time.monotonic() - start_time) * 1000)

        source_uuids = [
            v["document_uuid"] for v in source_document_versions
        ] or [d["document_uuid"] for d in source_docs]
        target_uuids = [
            v["document_uuid"] for v in target_document_versions
        ] or [d["document_uuid"] for d in target_docs]

        _, _, _, fallback_used = self._get_agent_config()

        # Build link dicts from whatever we have
        link_dicts = [
            {
                "requirement_id": link.requirement_id,
                "requirement_text": link.requirement_text,
                "source_document_uuid": link.source_document_uuid,
                "source_section": link.source_section,
                "test_case_id": link.test_case_id,
                "test_case_text": link.test_case_text,
                "target_document_uuid": link.target_document_uuid,
                "target_section": link.target_section,
                "link_confidence": link.link_confidence,
                "link_method": link.link_method,
                "link_methods": [link.link_method],
                "verification_status": "unverified",
            }
            for link in links
        ]

        # Build metadata with timeout info and fallback status (Req 6.5, 6.7)
        partial_metadata: dict[str, Any] = {
            "timeout": True,
            "timeout_seconds": _GENERATION_TIMEOUT,
            "unprocessed_reason": unprocessed_reason,
            "requirements_extracted": len(requirements),
            "test_cases_extracted": len(test_cases),
            "links_discovered": len(links),
        }
        if fallback_used:
            partial_metadata["fallback_used"] = {
                "missing_archetype": "Traceability Analyst",
                "used_archetype": "Change Impact Analyst",
            }

        matrix_data = _MatrixResult(
            matrix_id=str(uuid.uuid4()),
            matrix_name=request.matrix_name,
            description=getattr(request, "description", None),
            source_document_uuids=source_uuids,
            target_document_uuids=target_uuids,
            source_document_versions=source_document_versions,
            target_document_versions=target_document_versions,
            traceability_links=link_dicts,
            orphan_requirements=[],
            orphan_test_cases=[],
            coverage_metrics={},
            status="partial_success",
            parent_matrix_id=None,
            generation_duration_ms=duration_ms,
            agent_archetype_used=(
                "Traceability Analyst"
                if not fallback_used
                else "Change Impact Analyst (fallback)"
            ),
            model_used=self._get_model_name(),
            total_token_count=0,
            requesting_user_id=user_id,
            company_id=company_id,
            metadata=partial_metadata,
        )

        # Persist with retries
        for attempt in range(_DB_PERSIST_MAX_RETRIES):
            try:
                if self._session_factory:
                    async with self._session_factory() as session:
                        from alcoabase.models.traceability import (
                            TraceabilityMatrix,
                        )

                        matrix_record = TraceabilityMatrix(
                            matrix_id=matrix_data.matrix_id,
                            matrix_name=matrix_data.matrix_name,
                            description=matrix_data.description,
                            source_document_uuids=matrix_data.source_document_uuids,
                            target_document_uuids=matrix_data.target_document_uuids,
                            source_document_versions=matrix_data.source_document_versions,
                            target_document_versions=matrix_data.target_document_versions,
                            traceability_links=matrix_data.traceability_links,
                            orphan_requirements=matrix_data.orphan_requirements,
                            orphan_test_cases=matrix_data.orphan_test_cases,
                            coverage_metrics=matrix_data.coverage_metrics,
                            status="partial_success",
                            parent_matrix_id=None,
                            generation_timestamp=datetime.now(tz=timezone.utc),
                            generation_duration_ms=matrix_data.generation_duration_ms,
                            agent_archetype_used=matrix_data.agent_archetype_used,
                            model_used=matrix_data.model_used,
                            total_token_count=0,
                            requesting_user_id=user_id,
                            company_id=company_id,
                        )
                        session.add(matrix_record)
                        await session.commit()

                    # Complete job with partial_success
                    if self._job_tracker:
                        async with self._session_factory() as job_session:
                            await self._job_tracker.complete_job(
                                job_session,
                                job_id,
                                matrix_data.matrix_id,
                            )
                            await job_session.commit()
                break
            except Exception as e:
                if attempt < _DB_PERSIST_MAX_RETRIES - 1:
                    await asyncio.sleep(
                        _DB_PERSIST_BACKOFF_DELAYS[attempt]
                    )
                else:
                    logger.error(
                        "Failed to persist partial_success matrix "
                        "after %d retries: %s",
                        _DB_PERSIST_MAX_RETRIES,
                        str(e),
                    )
                    if self._job_tracker and self._session_factory:
                        try:
                            async with self._session_factory() as fs:
                                await self._job_tracker.fail_job(
                                    fs,
                                    job_id,
                                    f"Persistence failure: {str(e)[:200]}",
                                )
                                await fs.commit()
                        except Exception:
                            pass

        return matrix_data


# ─────────────────────────────────────────────────────────────────────────────
# Internal Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class _ExtractionTimeoutError(Exception):
    """Raised when a per-document extraction exceeds the 120s timeout."""

    pass


class _InferenceUnavailableError(Exception):
    """Raised when InferenceClient is unavailable after all retries.

    Attributes:
        phase: The extraction phase where failure occurred.
        status_code: HTTP status code if applicable.
    """

    def __init__(
        self,
        message: str,
        phase: str = "",
        status_code: int | None = None,
    ) -> None:
        self.phase = phase
        self.status_code = status_code
        super().__init__(message)


class _ValidationError(Exception):
    """Raised when request validation fails (422 semantics)."""

    pass


class _DocumentNotFoundError(Exception):
    """Raised when document IDs are not found in company scope (404 semantics)."""

    pass


@dataclass
class _MatrixResult:
    """Internal result object for a generated traceability matrix.

    Holds all data needed to persist the matrix record.
    """

    matrix_id: str
    matrix_name: str
    description: str | None
    source_document_uuids: list[str]
    target_document_uuids: list[str]
    source_document_versions: list[dict[str, Any]]
    target_document_versions: list[dict[str, Any]]
    traceability_links: list[dict[str, Any]]
    orphan_requirements: list[dict[str, Any]]
    orphan_test_cases: list[dict[str, Any]]
    coverage_metrics: dict[str, Any]
    status: str
    parent_matrix_id: str | None
    generation_duration_ms: int
    agent_archetype_used: str
    model_used: str
    total_token_count: int
    requesting_user_id: int
    company_id: int
    metadata: dict[str, Any] = field(default_factory=dict)
