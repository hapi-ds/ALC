"""Orchestrates LLM-based literature screening against protocols.

Loads the Literature Screener archetype, constructs screening prompts,
dispatches to vLLM via InferenceClient, parses structured JSON responses,
and returns ScreeningResult dataclass instances.

References:
    - Requirements 1.1, 1.3, 1.5, 3.1, 3.2, 3.6
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from alcoabase.services.agent_registry import AgentRegistryService
from alcoabase.services.inference_client import InferenceClient

logger = logging.getLogger(__name__)

# Valid verdict values for response validation
_VALID_VERDICTS = frozenset({"include", "exclude", "uncertain"})

# Truncation limits for prompt construction
_ABSTRACT_MAX_CHARS = 4000
_BODY_MAX_CHARS = 8000


@dataclass(frozen=True)
class ScreeningResult:
    """Structured result from a single screening evaluation.

    Attributes:
        verdict: "include", "exclude", or "uncertain".
        confidence: Float 0.0–1.0.
        rationale: Explanation text (max 2000 chars).
        matched_inclusion_criteria: Indices of matched inclusion criteria.
        matched_exclusion_criteria: Indices of matched exclusion criteria.
        screening_duration_ms: Time to produce this decision.
    """

    verdict: str
    confidence: float
    rationale: str
    matched_inclusion_criteria: list[int]
    matched_exclusion_criteria: list[int]
    screening_duration_ms: int


class LiteratureScreenerAgentRunner:
    """Runs the Literature Screener Agent against individual papers.

    Responsibilities:
        - Load the Literature Screener archetype from AgentRegistryService
        - Construct structured prompts with paper metadata + protocol criteria
        - Dispatch to vLLM and parse JSON response
        - Validate response schema (verdict enum, confidence range, rationale presence)
        - Handle malformed responses gracefully (fallback to uncertain/0.0)
    """

    ARCHETYPE_NAME = "Literature Screener"
    FALLBACK_TEMPERATURE = 0.1
    FALLBACK_MAX_TOKENS = 4096
    FALLBACK_SYSTEM_PROMPT = (
        "You are a Literature Screening Agent. Evaluate the provided paper "
        "against the given screening criteria and produce a JSON response with: "
        "verdict (include/exclude/uncertain), confidence (0.0-1.0), rationale, "
        "matched_inclusion_criteria (list of indices), and "
        "matched_exclusion_criteria (list of indices)."
    )

    def __init__(
        self,
        inference_client: InferenceClient,
        agent_registry: AgentRegistryService,
        model_name: str,
    ) -> None:
        """Initialize with LLM client and agent registry.

        Args:
            inference_client: Client for vLLM chat completion.
            agent_registry: Service for loading agent archetypes.
            model_name: Chat model identifier for inference.
        """
        self._inference_client = inference_client
        self._agent_registry = agent_registry
        self._model_name = model_name

    async def screen_record(
        self,
        title: str,
        abstract: str,
        body_sections: list[dict[str, str]] | None,
        protocol_criteria: dict[str, Any],
    ) -> ScreeningResult:
        """Screen a single paper against protocol criteria.

        Steps:
            1. Load archetype system prompt and tuning params
            2. Construct user prompt with paper content + criteria
            3. Dispatch to InferenceClient.chat_completion
            4. Parse and validate JSON response
            5. Return ScreeningResult or fallback on parse failure

        Args:
            title: Paper title.
            abstract: Paper abstract text.
            body_sections: Optional list of {heading, text} body sections.
            protocol_criteria: Dict with pico, inclusion, exclusion, etc.

        Returns:
            ScreeningResult with verdict, confidence, rationale.

        Raises:
            InferenceConnectionError: If vLLM unreachable (caller handles retry).
        """
        start_ns = time.perf_counter_ns()

        system_prompt, temperature, max_tokens = self._get_agent_config()
        user_prompt = self._construct_prompt(
            title, abstract, body_sections, protocol_criteria
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response_text = await self._inference_client.chat_completion(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

        result = self._parse_response(response_text)

        if result is None:
            logger.warning(
                "Malformed LLM response for title='%s', returning uncertain fallback",
                title[:80],
            )
            return ScreeningResult(
                verdict="uncertain",
                confidence=0.0,
                rationale="Agent response parsing failed: malformed or invalid JSON response",
                matched_inclusion_criteria=[],
                matched_exclusion_criteria=[],
                screening_duration_ms=duration_ms,
            )

        # Return result with actual duration
        return ScreeningResult(
            verdict=result.verdict,
            confidence=result.confidence,
            rationale=result.rationale,
            matched_inclusion_criteria=result.matched_inclusion_criteria,
            matched_exclusion_criteria=result.matched_exclusion_criteria,
            screening_duration_ms=duration_ms,
        )

    async def screen_batch(
        self,
        records: list[dict[str, Any]],
        protocol_criteria: dict[str, Any],
    ) -> list[tuple[int, ScreeningResult]]:
        """Screen a batch of records sequentially.

        Processes each record, collecting results. On per-record failure,
        returns uncertain/0.0 fallback for that record and continues.

        Args:
            records: List of dicts with record_id, title, abstract, body_sections.
            protocol_criteria: Protocol criteria for this screening run.

        Returns:
            List of (record_id, ScreeningResult) tuples.
        """
        results: list[tuple[int, ScreeningResult]] = []

        for record in records:
            record_id: int = record["record_id"]
            title: str = record.get("title", "")
            abstract: str = record.get("abstract", "")
            body_sections: list[dict[str, str]] | None = record.get("body_sections")

            try:
                result = await self.screen_record(
                    title=title,
                    abstract=abstract,
                    body_sections=body_sections,
                    protocol_criteria=protocol_criteria,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Screening failed for record_id=%d: %s",
                    record_id,
                    str(exc),
                )
                result = ScreeningResult(
                    verdict="uncertain",
                    confidence=0.0,
                    rationale=f"Agent response parsing failed: {type(exc).__name__}: {exc}",
                    matched_inclusion_criteria=[],
                    matched_exclusion_criteria=[],
                    screening_duration_ms=0,
                )

            results.append((record_id, result))

        return results

    def _construct_prompt(
        self,
        title: str,
        abstract: str,
        body_sections: list[dict[str, str]] | None,
        protocol_criteria: dict[str, Any],
    ) -> str:
        """Build the user prompt for screening evaluation.

        Includes: paper title, abstract (truncated to 4000 chars),
        body sections (truncated to 8000 chars total), PICO criteria,
        inclusion/exclusion patterns, date range, publication types.

        Args:
            title: Paper title.
            abstract: Paper abstract.
            body_sections: Optional body sections.
            protocol_criteria: Full protocol criteria dict.

        Returns:
            Formatted prompt string.
        """
        parts: list[str] = []

        # Paper content
        parts.append("=== PAPER TO SCREEN ===")
        parts.append(f"\n## Title\n{title}")

        # Abstract (truncated)
        truncated_abstract = abstract[:_ABSTRACT_MAX_CHARS]
        if len(abstract) > _ABSTRACT_MAX_CHARS:
            truncated_abstract += "... [truncated]"
        parts.append(f"\n## Abstract\n{truncated_abstract}")

        # Body sections (truncated to 8000 chars total)
        if body_sections:
            body_text_parts: list[str] = []
            total_chars = 0
            for section in body_sections:
                heading = section.get("heading", "Untitled Section")
                text = section.get("text", "")
                section_str = f"### {heading}\n{text}"
                if total_chars + len(section_str) > _BODY_MAX_CHARS:
                    # Truncate and break
                    remaining = _BODY_MAX_CHARS - total_chars
                    if remaining > 0:
                        body_text_parts.append(section_str[:remaining] + "... [truncated]")
                    break
                body_text_parts.append(section_str)
                total_chars += len(section_str)

            if body_text_parts:
                parts.append("\n## Body Sections\n" + "\n\n".join(body_text_parts))

        # Screening criteria
        parts.append("\n=== SCREENING CRITERIA ===")

        # PICO criteria
        pico = protocol_criteria.get("pico_criteria") or protocol_criteria.get("pico") or {}
        if any(v for v in pico.values() if v):
            parts.append("\n## PICO Criteria")
            if pico.get("population"):
                parts.append(f"- Population: {pico['population']}")
            if pico.get("intervention"):
                parts.append(f"- Intervention: {pico['intervention']}")
            if pico.get("comparison"):
                parts.append(f"- Comparison: {pico['comparison']}")
            if pico.get("outcome"):
                parts.append(f"- Outcome: {pico['outcome']}")

        # Inclusion criteria
        inclusion = protocol_criteria.get("inclusion_criteria") or []
        if inclusion:
            parts.append("\n## Inclusion Criteria")
            for i, criterion in enumerate(inclusion):
                parts.append(f"  [{i}] {criterion}")

        # Exclusion criteria
        exclusion = protocol_criteria.get("exclusion_criteria") or []
        if exclusion:
            parts.append("\n## Exclusion Criteria")
            for i, criterion in enumerate(exclusion):
                parts.append(f"  [{i}] {criterion}")

        # Date range
        date_from = protocol_criteria.get("publication_date_from")
        date_to = protocol_criteria.get("publication_date_to")
        if date_from or date_to:
            parts.append("\n## Date Range")
            if date_from:
                parts.append(f"- From: {date_from}")
            if date_to:
                parts.append(f"- To: {date_to}")

        # Publication types
        pub_types = protocol_criteria.get("allowed_publication_types")
        if pub_types:
            parts.append(f"\n## Allowed Publication Types\n{', '.join(pub_types)}")

        # Response instruction
        parts.append(
            "\n=== INSTRUCTIONS ===\n"
            "Evaluate the paper against the criteria above. Respond with ONLY "
            "a JSON object containing:\n"
            '{\n'
            '  "verdict": "include" | "exclude" | "uncertain",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "rationale": "explanation (max 2000 chars)",\n'
            '  "matched_inclusion_criteria": [indices],\n'
            '  "matched_exclusion_criteria": [indices]\n'
            '}'
        )

        return "\n".join(parts)

    def _parse_response(self, response_text: str) -> ScreeningResult | None:
        """Parse and validate the LLM JSON response.

        Expected schema:
            {
                "verdict": "include" | "exclude" | "uncertain",
                "confidence": 0.0–1.0,
                "rationale": "...",
                "matched_inclusion_criteria": [0, 2, 5],
                "matched_exclusion_criteria": [1]
            }

        Returns None if parsing fails or required fields are missing/invalid.

        Args:
            response_text: Raw LLM response text.

        Returns:
            ScreeningResult or None on validation failure.
        """
        try:
            # Try to extract JSON from the response (LLMs sometimes wrap in markdown)
            text = response_text.strip()
            if text.startswith("```"):
                # Strip markdown code fence
                lines = text.split("\n")
                # Remove first and last lines if they are fences
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

        # Validate verdict
        verdict = data.get("verdict")
        if verdict not in _VALID_VERDICTS:
            return None

        # Validate confidence
        confidence = data.get("confidence")
        if not isinstance(confidence, (int, float)):
            return None
        confidence = float(confidence)
        if confidence < 0.0 or confidence > 1.0:
            return None

        # Validate rationale
        rationale = data.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            return None

        # Validate matched criteria (optional arrays of ints)
        matched_inclusion = data.get("matched_inclusion_criteria", [])
        if not isinstance(matched_inclusion, list):
            return None
        if not all(isinstance(i, int) for i in matched_inclusion):
            return None

        matched_exclusion = data.get("matched_exclusion_criteria", [])
        if not isinstance(matched_exclusion, list):
            return None
        if not all(isinstance(i, int) for i in matched_exclusion):
            return None

        # Truncate rationale to 2000 chars as per spec
        rationale = rationale[:2000]

        return ScreeningResult(
            verdict=verdict,
            confidence=confidence,
            rationale=rationale,
            matched_inclusion_criteria=matched_inclusion,
            matched_exclusion_criteria=matched_exclusion,
            screening_duration_ms=0,  # Will be overridden by caller
        )

    def _get_agent_config(self) -> tuple[str, float, int]:
        """Load Literature Screener archetype configuration.

        Falls back to built-in defaults if archetype not found.

        Returns:
            Tuple of (system_prompt, temperature, max_tokens).
        """
        archetype_data = self._agent_registry._load_archetype_raw(self.ARCHETYPE_NAME)

        if archetype_data is None:
            logger.warning(
                "Literature Screener archetype not found in registry, "
                "using fallback defaults"
            )
            return (
                self.FALLBACK_SYSTEM_PROMPT,
                self.FALLBACK_TEMPERATURE,
                self.FALLBACK_MAX_TOKENS,
            )

        # Extract system prompt
        system_prompt = archetype_data.get("system_prompt", self.FALLBACK_SYSTEM_PROMPT)

        # Extract contextual tuning
        tuning = archetype_data.get("contextual_tuning", {})
        temperature = tuning.get("temperature", self.FALLBACK_TEMPERATURE)
        max_tokens = tuning.get("max_tokens", self.FALLBACK_MAX_TOKENS)

        return system_prompt, float(temperature), int(max_tokens)
