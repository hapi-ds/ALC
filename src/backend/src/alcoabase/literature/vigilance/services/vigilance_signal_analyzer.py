"""LLM-based signal detection and severity classification.

Loads the Vigilance Analyst archetype, constructs signal detection prompts,
dispatches to vLLM via InferenceClient, parses structured JSON responses,
and creates VigilanceSignal records when thresholds are met.

References:
    - Requirements 1.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from alcoabase.literature.ingestion.models.ingestion import IngestionRecord
from alcoabase.literature.vigilance.audit import log_signal_created
from alcoabase.literature.vigilance.exceptions import InferenceConnectionError
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_signal import VigilanceSignal
from alcoabase.services.inference_client import (
    InferenceConnectionError as ClientConnectionError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from alcoabase.services.agent_registry import AgentRegistryService
    from alcoabase.services.inference_client import InferenceClient

logger = logging.getLogger(__name__)

# Valid severity values for response validation
_VALID_SEVERITIES = frozenset({"critical", "major", "minor"})

# Truncation limits for prompt construction
_ABSTRACT_MAX_CHARS = 4000
_BODY_MAX_CHARS = 8000


@dataclass(frozen=True)
class SignalAnalysisResult:
    """Structured result from vigilance signal analysis.

    Attributes:
        signal_detected: Whether a safety signal was identified.
        severity: "critical", "major", "minor", or None.
        evidence_summary: Explanation of findings (max 3000 chars).
        affected_product_aspects: Device functions/components implicated.
        regulatory_references: Applicable regulation articles.
        recommended_actions: Suggested next steps (max 5).
        confidence: Analysis confidence (0.0-1.0).
        analysis_duration_ms: Time to produce this analysis.
    """

    signal_detected: bool
    severity: str | None
    evidence_summary: str
    affected_product_aspects: list[str]
    regulatory_references: list[str]
    recommended_actions: list[str]
    confidence: float
    analysis_duration_ms: int


class VigilanceSignalAnalyzer:
    """Runs the Vigilance Analyst Agent for signal detection.

    Responsibilities:
        - Load the Vigilance Analyst archetype from AgentRegistryService
        - Construct prompts with paper content + product safety profile
        - Dispatch to vLLM and parse JSON response
        - Validate response schema (severity enum, confidence range, required fields)
        - Handle malformed responses (fallback to uncertain/manual review)
        - Create VigilanceSignal records when threshold met
        - Support batch processing of multiple records
    """

    ARCHETYPE_NAME = "Vigilance Analyst"
    FALLBACK_TEMPERATURE = 0.05
    FALLBACK_MAX_TOKENS = 6144
    FALLBACK_TOP_P = 0.90
    FALLBACK_SYSTEM_PROMPT = (
        "You are a Vigilance Analyst agent. Evaluate the provided literature "
        "finding against the medical device product profile and determine whether "
        "it represents a genuine safety signal. Classify severity using MDR "
        "Article 87 serious incident criteria. Respond with ONLY a JSON object "
        "containing: signal_detected (bool), severity (critical/major/minor/null), "
        "evidence_summary (string), affected_product_aspects (array), "
        "regulatory_references (array), recommended_actions (array, max 5), "
        "confidence (0.0-1.0)."
    )

    def __init__(
        self,
        session_factory: "async_sessionmaker",
        inference_client: "InferenceClient",
        agent_registry: "AgentRegistryService",
        model_name: str,
        confidence_threshold: float = 0.7,
        batch_size: int = 10,
    ) -> None:
        """Initialize with LLM client and agent registry.

        Args:
            session_factory: Async session factory for DB operations.
            inference_client: Client for vLLM chat completion.
            agent_registry: Service for loading agent archetypes.
            model_name: Chat model identifier for inference.
            confidence_threshold: Min confidence to create signal (0.1-1.0).
            batch_size: Records per batch (1-50).
        """
        self._session_factory = session_factory
        self._inference_client = inference_client
        self._agent_registry = agent_registry
        self._model_name = model_name
        self._confidence_threshold = confidence_threshold
        self._batch_size = batch_size

    async def analyze_record(
        self,
        record_id: int,
        product_id: int,
        profile_id: int,
        company_id: int,
    ) -> SignalAnalysisResult:
        """Analyze a single ingestion record for safety signals.

        Steps:
            1. Load IngestionRecord content (title, abstract, body)
            2. Load MedicalProduct metadata (class, intended purpose, risks)
            3. Load archetype system prompt and tuning params
            4. Construct user prompt with paper content + product profile
            5. Dispatch to InferenceClient.chat_completion
            6. Parse and validate JSON response
            7. If signal detected and confidence >= threshold: create VigilanceSignal
            8. Return analysis result

        Args:
            record_id: IngestionRecord to analyze.
            product_id: Associated MedicalProduct.
            profile_id: Originating VigilanceSearchProfile.
            company_id: Tenant scope.

        Returns:
            SignalAnalysisResult with detection outcome.

        Raises:
            InferenceConnectionError: If vLLM unreachable (caller handles retry).
        """
        start_ns = time.perf_counter_ns()

        async with self._session_factory() as session:
            # 1. Load IngestionRecord
            record = await session.get(IngestionRecord, record_id)
            if record is None:
                logger.error("IngestionRecord %d not found", record_id)
                duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
                return SignalAnalysisResult(
                    signal_detected=False,
                    severity=None,
                    evidence_summary="Record not found for analysis",
                    affected_product_aspects=[],
                    regulatory_references=[],
                    recommended_actions=[],
                    confidence=0.0,
                    analysis_duration_ms=duration_ms,
                )

            # 2. Load MedicalProduct
            product = await session.get(MedicalProduct, product_id)
            if product is None:
                logger.error("MedicalProduct %d not found", product_id)
                duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
                return SignalAnalysisResult(
                    signal_detected=False,
                    severity=None,
                    evidence_summary="Product not found for analysis",
                    affected_product_aspects=[],
                    regulatory_references=[],
                    recommended_actions=[],
                    confidence=0.0,
                    analysis_duration_ms=duration_ms,
                )

            # 3. Load archetype config
            system_prompt, temperature, max_tokens, top_p = self._get_agent_config()

            # 4. Construct prompt
            user_prompt = self._construct_prompt(
                title=record.title,
                abstract=record.abstract or "",
                body_text=None,  # Body comes from sanitized content if available
                product_name=product.name,
                device_class=product.device_class,
                intended_purpose=product.intended_purpose,
                predicate_devices=product.predicate_devices,
            )

            # 5. Dispatch to InferenceClient
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            try:
                response_text = await self._inference_client.chat_completion(
                    model=self._model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=120.0,
                )
            except ClientConnectionError as exc:
                raise InferenceConnectionError(
                    f"vLLM unreachable during signal detection for record {record_id}: {exc}",
                    record_id=record_id,
                    retry_attempts=0,
                ) from exc

            duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

            # 6. Parse and validate response
            result = self._parse_response(response_text)

            if result is None:
                # Malformed response — mark as uncertain for manual review
                logger.warning(
                    "Malformed LLM response for record_id=%d, flagging for manual review",
                    record_id,
                )
                return SignalAnalysisResult(
                    signal_detected=False,
                    severity=None,
                    evidence_summary=(
                        "Agent response parsing failed: malformed or invalid JSON response. "
                        "Record flagged for manual review."
                    ),
                    affected_product_aspects=[],
                    regulatory_references=[],
                    recommended_actions=[],
                    confidence=0.0,
                    analysis_duration_ms=duration_ms,
                )

            # Build final result with actual duration
            analysis_result = SignalAnalysisResult(
                signal_detected=result.signal_detected,
                severity=result.severity,
                evidence_summary=result.evidence_summary,
                affected_product_aspects=result.affected_product_aspects,
                regulatory_references=result.regulatory_references,
                recommended_actions=result.recommended_actions,
                confidence=result.confidence,
                analysis_duration_ms=duration_ms,
            )

            # 7. Create VigilanceSignal if threshold met
            if result.signal_detected and result.confidence >= self._confidence_threshold:
                signal = VigilanceSignal(
                    ingestion_record_id=record_id,
                    product_id=product_id,
                    profile_id=profile_id,
                    company_id=company_id,
                    severity=result.severity or "minor",
                    evidence_summary=result.evidence_summary,
                    affected_product_aspects=result.affected_product_aspects,
                    regulatory_references=result.regulatory_references,
                    recommended_actions=result.recommended_actions,
                    confidence=result.confidence,
                    disposition="under_review",
                    created_by=1,  # System user for automated detection
                )
                session.add(signal)
                await session.commit()
                await session.refresh(signal)

                # Structured audit log for signal creation (Requirement 12.2)
                log_signal_created(
                    signal_id=signal.id,
                    ingestion_record_id=record_id,
                    product_id=product_id,
                    profile_id=profile_id,
                    company_id=company_id,
                    severity=result.severity or "minor",
                    confidence=result.confidence,
                    detection_duration_ms=duration_ms,
                )
            else:
                logger.debug(
                    "No signal created for record_id=%d (detected=%s, confidence=%.3f, threshold=%.3f)",
                    record_id,
                    result.signal_detected,
                    result.confidence,
                    self._confidence_threshold,
                )

            return analysis_result

    async def analyze_batch(
        self,
        record_ids: list[int],
        product_id: int,
        profile_id: int,
        company_id: int,
    ) -> list[tuple[int, SignalAnalysisResult]]:
        """Analyze a batch of records sequentially.

        Processes each record; on per-record failure, marks as uncertain
        and continues with remaining records.

        Args:
            record_ids: IngestionRecord IDs to analyze.
            product_id: Associated MedicalProduct.
            profile_id: Originating VigilanceSearchProfile.
            company_id: Tenant scope.

        Returns:
            List of (record_id, SignalAnalysisResult) tuples.
        """
        results: list[tuple[int, SignalAnalysisResult]] = []

        for record_id in record_ids:
            try:
                result = await self.analyze_record(
                    record_id=record_id,
                    product_id=product_id,
                    profile_id=profile_id,
                    company_id=company_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Signal analysis failed for record_id=%d: %s",
                    record_id,
                    str(exc),
                )
                result = SignalAnalysisResult(
                    signal_detected=False,
                    severity=None,
                    evidence_summary=(
                        f"Analysis failed: {type(exc).__name__}: {exc}. "
                        "Record marked as uncertain and flagged for manual review."
                    ),
                    affected_product_aspects=[],
                    regulatory_references=[],
                    recommended_actions=[],
                    confidence=0.0,
                    analysis_duration_ms=0,
                )

            results.append((record_id, result))

        return results

    def _construct_prompt(
        self,
        title: str,
        abstract: str,
        body_text: str | None,
        product_name: str,
        device_class: str,
        intended_purpose: str,
        predicate_devices: list[str] | None,
    ) -> str:
        """Build the signal detection prompt.

        Includes: paper content (title, abstract, body truncated),
        product metadata (name, device_class, intended_purpose, predicate_devices),
        MDR severity criteria reference, and expected JSON output schema.

        Args:
            title: Paper title.
            abstract: Paper abstract.
            body_text: Optional body text (truncated).
            product_name: Medical device name.
            device_class: Regulatory device class.
            intended_purpose: Device intended use description.
            predicate_devices: Optional list of predicate device names.

        Returns:
            Formatted prompt string.
        """
        parts: list[str] = []

        # Paper content section
        parts.append("=== LITERATURE FINDING ===")
        parts.append(f"\n## Title\n{title}")

        # Abstract (truncated)
        truncated_abstract = abstract[:_ABSTRACT_MAX_CHARS]
        if len(abstract) > _ABSTRACT_MAX_CHARS:
            truncated_abstract += "... [truncated]"
        parts.append(f"\n## Abstract\n{truncated_abstract}")

        # Body text (truncated)
        if body_text:
            truncated_body = body_text[:_BODY_MAX_CHARS]
            if len(body_text) > _BODY_MAX_CHARS:
                truncated_body += "... [truncated]"
            parts.append(f"\n## Body\n{truncated_body}")

        # Product profile section
        parts.append("\n=== MEDICAL DEVICE PRODUCT PROFILE ===")
        parts.append(f"\n## Product Name\n{product_name}")
        parts.append(f"\n## Device Class\n{device_class}")
        parts.append(f"\n## Intended Purpose\n{intended_purpose}")

        if predicate_devices:
            predicates_str = ", ".join(predicate_devices)
            parts.append(f"\n## Predicate Devices\n{predicates_str}")

        # MDR severity criteria reference
        parts.append(
            "\n=== MDR SEVERITY CLASSIFICATION CRITERIA ===\n"
            "\n**CRITICAL** — Death, serious injury, or serious public health threat "
            "directly attributable to the device, or systematic failure requiring "
            "immediate FSCA (MDR Article 87(1)).\n"
            "\n**MAJOR** — Non-serious adverse event, near-miss, or emerging trend "
            "that could escalate to a serious incident if unaddressed "
            "(MEDDEV 2.12/1 trend reporting).\n"
            "\n**MINOR** — Isolated complaint or performance issue with low "
            "likelihood of patient harm. Warrants monitoring but not immediate action."
        )

        # Expected JSON output schema
        parts.append(
            "\n=== REQUIRED JSON OUTPUT SCHEMA ===\n"
            "Respond with ONLY a valid JSON object:\n"
            "{\n"
            '  "signal_detected": true | false,\n'
            '  "severity": "critical" | "major" | "minor" | null,\n'
            '  "evidence_summary": "concise summary of adverse event evidence '
            'and causal relationship (max 3000 characters)",\n'
            '  "affected_product_aspects": ["device functions/components implicated"],\n'
            '  "regulatory_references": ["applicable regulation articles, '
            "e.g., 'MDR Article 87(1)(a)'\"],\n"
            '  "recommended_actions": ["specific next steps, max 5 actions"],\n'
            '  "confidence": 0.0-1.0\n'
            "}"
        )

        return "\n".join(parts)

    def _parse_response(self, response_text: str) -> SignalAnalysisResult | None:
        """Parse and validate the LLM JSON response.

        Expected schema:
            {
                "signal_detected": bool,
                "severity": "critical" | "major" | "minor" | null,
                "evidence_summary": str (max 3000),
                "affected_product_aspects": [str],
                "regulatory_references": [str],
                "recommended_actions": [str] (max 5),
                "confidence": float (0.0-1.0)
            }

        Returns None if parsing fails or required fields are missing/invalid.

        Args:
            response_text: Raw LLM response text.

        Returns:
            SignalAnalysisResult or None on validation failure.
        """
        try:
            # Try to extract JSON from the response (LLMs sometimes wrap in markdown)
            text = response_text.strip()
            if text.startswith("```"):
                # Strip markdown code fence
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

        # Validate signal_detected (required, must be bool)
        signal_detected = data.get("signal_detected")
        if not isinstance(signal_detected, bool):
            return None

        # Validate severity (must be valid enum or null/None)
        severity = data.get("severity")
        if severity is not None and severity not in _VALID_SEVERITIES:
            return None

        # Validate confidence (required, must be 0.0-1.0)
        confidence = data.get("confidence")
        if not isinstance(confidence, (int, float)):
            return None
        confidence = float(confidence)
        if confidence < 0.0 or confidence > 1.0:
            return None

        # Validate evidence_summary (required, must be non-empty string)
        evidence_summary = data.get("evidence_summary")
        if not isinstance(evidence_summary, str) or not evidence_summary.strip():
            return None
        # Truncate to 3000 chars as per spec
        evidence_summary = evidence_summary[:3000]

        # Validate affected_product_aspects (array of strings, optional)
        affected_product_aspects = data.get("affected_product_aspects", [])
        if not isinstance(affected_product_aspects, list):
            return None
        if not all(isinstance(item, str) for item in affected_product_aspects):
            return None

        # Validate regulatory_references (array of strings, optional)
        regulatory_references = data.get("regulatory_references", [])
        if not isinstance(regulatory_references, list):
            return None
        if not all(isinstance(item, str) for item in regulatory_references):
            return None

        # Validate recommended_actions (array of strings, max 5)
        recommended_actions = data.get("recommended_actions", [])
        if not isinstance(recommended_actions, list):
            return None
        if not all(isinstance(item, str) for item in recommended_actions):
            return None
        # Enforce max 5 actions
        recommended_actions = recommended_actions[:5]

        return SignalAnalysisResult(
            signal_detected=signal_detected,
            severity=severity,
            evidence_summary=evidence_summary,
            affected_product_aspects=affected_product_aspects,
            regulatory_references=regulatory_references,
            recommended_actions=recommended_actions,
            confidence=confidence,
            analysis_duration_ms=0,  # Will be overridden by caller
        )

    def _get_agent_config(self) -> tuple[str, float, int, float]:
        """Load Vigilance Analyst archetype configuration.

        Falls back to built-in defaults if archetype not found.

        Returns:
            Tuple of (system_prompt, temperature, max_tokens, top_p).
        """
        archetype_data = self._agent_registry._load_archetype_raw(self.ARCHETYPE_NAME)

        if archetype_data is None:
            logger.warning(
                "Vigilance Analyst archetype not found in registry, "
                "using fallback defaults"
            )
            return (
                self.FALLBACK_SYSTEM_PROMPT,
                self.FALLBACK_TEMPERATURE,
                self.FALLBACK_MAX_TOKENS,
                self.FALLBACK_TOP_P,
            )

        # Extract system prompt
        system_prompt = archetype_data.get("system_prompt", self.FALLBACK_SYSTEM_PROMPT)

        # Extract contextual tuning
        tuning = archetype_data.get("contextual_tuning", {})
        temperature = tuning.get("temperature", self.FALLBACK_TEMPERATURE)
        max_tokens = tuning.get("max_tokens", self.FALLBACK_MAX_TOKENS)
        top_p = tuning.get("top_p", self.FALLBACK_TOP_P)

        return system_prompt, float(temperature), int(max_tokens), float(top_p)
