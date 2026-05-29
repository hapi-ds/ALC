"""Orphan Detection Service for AI-Powered Traceability & Gap Discovery.

Identifies orphan requirements (requirements without test cases) and orphan
test cases (tests without justifying requirements). Classifies severity and
risk levels using the Traceability Analyst agent via keyword-based analysis.

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: 1.12, 2.1, 2.2, 2.4, 2.5, 3.1, 3.2, 3.4, 3.5
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from alcoabase.services.agent_registry import AgentRegistryService
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.traceability_matrix import (
        CandidateLink,
        ExtractedRequirement,
        ExtractedTestCase,
    )

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Agent classification timeout (seconds) — Requirements 2.5, 3.5
_CLASSIFICATION_TIMEOUT = 30.0

# Minimum link confidence threshold for considering a requirement/test covered
_LINK_CONFIDENCE_THRESHOLD = 0.5

# Near-miss confidence range for suggested_action determination
_NEAR_MISS_CONFIDENCE_MIN = 0.3
_NEAR_MISS_CONFIDENCE_MAX = 0.49

# Keyword categories for severity classification (Requirement 2.4)
_SEVERITY_KEYWORDS: dict[str, list[str]] = {
    "critical": [
        # Safety-critical keywords
        "hazard",
        "safety",
        "sterility",
        "biocompatibility",
        "alarm",
        "interlock",
        # Regulatory-mandatory keywords
        "shall comply",
        "regulatory requirement",
        "fda",
        "ema",
        "iso",
    ],
    "major": [
        # Functional keywords
        "shall perform",
        "shall calculate",
        "shall display",
    ],
    "minor": [
        # Informational keywords
        "should",
        "may",
        "nice-to-have",
        "optional",
    ],
}

# Keyword categories for risk_level classification (Requirement 3.4)
_RISK_LEVEL_KEYWORDS: dict[str, list[str]] = {
    "high": [
        # Safety-critical indicators
        "validates safety function",
        "alarm verification",
        "interlock test",
    ],
    "medium": [
        # Functional indicators
        "verifies calculation",
        "confirms workflow",
        "validates data entry",
    ],
    "low": [
        # Informational indicators
        "checks display format",
        "verifies label text",
        "cosmetic verification",
    ],
}

# Default severity when agent classification fails (Requirement 2.5)
_DEFAULT_SEVERITY = "major"

# Default risk_level when agent classification fails (Requirement 3.5)
_DEFAULT_RISK_LEVEL = "medium"

# Default suggested_action when agent classification fails (Requirement 3.5)
_DEFAULT_SUGGESTED_ACTION = "link_to_requirement"


# Prompt for severity classification
_SEVERITY_CLASSIFICATION_PROMPT = """Classify the severity of the following orphan requirements.

For each requirement, determine the severity based on keyword analysis:
- "critical": Contains safety-critical keywords (hazard, safety, sterility, biocompatibility, alarm, interlock) OR regulatory-mandatory keywords (shall comply, regulatory requirement, FDA, EMA, ISO)
- "major": Contains functional keywords (shall perform, shall calculate, shall display)
- "minor": Contains only informational keywords (should, may, nice-to-have, optional)

If a requirement matches multiple categories, assign the highest-precedence severity (critical > major > minor).

Return a JSON object:
{
  "classifications": [
    {"requirement_id": "<ID>", "severity": "<critical|major|minor>", "suggested_action": "<create_test_case|review_requirement|link_existing_test>"}
  ]
}

Requirements to classify:
"""

# Prompt for risk_level classification
_RISK_LEVEL_CLASSIFICATION_PROMPT = """Classify the risk level of the following orphan test cases.

For each test case, determine the risk_level based on content analysis:
- "high": Validates safety function, alarm verification, interlock test
- "medium": Verifies calculation, confirms workflow, validates data entry
- "low": Checks display format, verifies label text, cosmetic verification

Also determine the suggested_action:
- "link_to_requirement": When a plausible requirement match exists (near-miss)
- "create_requirement": When no plausible match exists and the test validates observable system behavior
- "remove_test_case": When the test is redundant or duplicates another linked test case

Return a JSON object:
{
  "classifications": [
    {"test_case_id": "<ID>", "risk_level": "<high|medium|low>", "suggested_action": "<link_to_requirement|create_requirement|remove_test_case>"}
  ]
}

Test cases to classify:
"""


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class OrphanRequirement:
    """An orphan requirement with no corresponding test case.

    Attributes:
        requirement_id: Formal requirement identifier.
        requirement_text: Requirement statement text (max 500 chars).
        source_document_uuid: UUID of the source document.
        source_section: Section heading where the requirement appears.
        severity: Classified severity (critical, major, minor).
        suggested_action: Recommended remediation action.
    """

    requirement_id: str
    requirement_text: str
    source_document_uuid: str
    source_section: str
    severity: str
    suggested_action: str


@dataclass
class OrphanTestCase:
    """An orphan test case with no justifying requirement.

    Attributes:
        test_case_id: Formal test case identifier.
        test_case_text: Test case description text (max 500 chars).
        target_document_uuid: UUID of the target document.
        target_section: Section heading where the test case appears.
        risk_level: Classified risk level (high, medium, low).
        suggested_action: Recommended remediation action.
    """

    test_case_id: str
    test_case_text: str
    target_document_uuid: str
    target_section: str
    risk_level: str
    suggested_action: str


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class OrphanDetectionService:
    """Service for identifying and classifying orphan requirements and test cases.

    Detects requirements without test coverage and test cases without
    justifying requirements. Uses the Traceability Analyst agent for
    keyword-based severity and risk classification via InferenceClient.

    Args:
        inference_client: Async HTTP client for vLLM inference.
        agent_registry: Service for loading agent archetypes.
    """

    def __init__(
        self,
        inference_client: InferenceClient | None = None,
        agent_registry: AgentRegistryService | None = None,
    ) -> None:
        """Initialize OrphanDetectionService.

        Args:
            inference_client: InferenceClient for AI-powered classification.
            agent_registry: AgentRegistryService for loading agent config.
        """
        self._inference_client = inference_client
        self._agent_registry = agent_registry

    # ───────────────────────────────────────────────────────────────────────
    # Public: Orphan Requirement Identification (Requirements 1.12, 2.1, 2.2)
    # ───────────────────────────────────────────────────────────────────────

    async def identify_orphan_requirements(
        self,
        requirements: list[ExtractedRequirement],
        links: list[CandidateLink],
    ) -> list[OrphanRequirement]:
        """Identify requirements with no test coverage.

        A requirement is classified as orphan if it has zero links with
        link_confidence >= 0.5. Produces a structured OrphanRequirement
        list with severity and suggested_action classifications.

        Args:
            requirements: All extracted requirements from source documents.
            links: All established traceability links.

        Returns:
            List of OrphanRequirement objects for requirements without
            adequate test coverage.
        """
        if not requirements:
            return []

        # Build set of covered requirement IDs (links with confidence >= 0.5)
        covered_requirement_ids: set[str] = set()
        for link in links:
            if link.link_confidence >= _LINK_CONFIDENCE_THRESHOLD:
                covered_requirement_ids.add(link.requirement_id)

        # Identify orphan requirements
        orphan_reqs: list[ExtractedRequirement] = [
            req
            for req in requirements
            if req.requirement_id not in covered_requirement_ids
        ]

        if not orphan_reqs:
            return []

        # Classify severity using keyword analysis
        classified = await self._classify_severity_with_keywords(orphan_reqs)

        return classified

    # ───────────────────────────────────────────────────────────────────────
    # Public: Orphan Test Case Identification (Requirements 3.1, 3.2)
    # ───────────────────────────────────────────────────────────────────────

    async def identify_orphan_test_cases(
        self,
        test_cases: list[ExtractedTestCase],
        links: list[CandidateLink],
    ) -> list[OrphanTestCase]:
        """Identify test cases with no justifying requirement.

        A test case is classified as orphan if it has zero links with
        link_confidence >= 0.5. Produces a structured OrphanTestCase
        list with risk_level and suggested_action classifications.

        Args:
            test_cases: All extracted test cases from target documents.
            links: All established traceability links.

        Returns:
            List of OrphanTestCase objects for test cases without
            justifying requirements.
        """
        if not test_cases:
            return []

        # Build set of covered test case IDs (links with confidence >= 0.5)
        covered_test_case_ids: set[str] = set()
        for link in links:
            if link.link_confidence >= _LINK_CONFIDENCE_THRESHOLD:
                covered_test_case_ids.add(link.test_case_id)

        # Identify orphan test cases
        orphan_tcs: list[ExtractedTestCase] = [
            tc
            for tc in test_cases
            if tc.test_case_id not in covered_test_case_ids
        ]

        if not orphan_tcs:
            return []

        # Determine near-miss information for suggested_action
        near_miss_ids = self._find_near_miss_test_cases(orphan_tcs, links)

        # Classify risk_level using keyword analysis
        classified = await self._classify_risk_level_with_keywords(
            orphan_tcs, near_miss_ids
        )

        return classified

    # ───────────────────────────────────────────────────────────────────────
    # Public: Severity Classification (Requirement 2.4)
    # ───────────────────────────────────────────────────────────────────────

    async def classify_orphan_severity(
        self,
        orphan_requirements: list[ExtractedRequirement],
        company_id: int,
    ) -> list[OrphanRequirement]:
        """Classify orphan requirement severity using the Traceability Analyst.

        Uses keyword-based severity classification with precedence:
        critical > major > minor. Falls back to default severity "major"
        on agent timeout (30s).

        Args:
            orphan_requirements: List of orphan requirements to classify.
            company_id: Company ID for tenant scoping.

        Returns:
            List of OrphanRequirement objects with severity classifications.
        """
        return await self._classify_severity_with_keywords(
            orphan_requirements
        )

    # ───────────────────────────────────────────────────────────────────────
    # Public: Risk Level Classification (Requirement 3.4)
    # ───────────────────────────────────────────────────────────────────────

    async def classify_orphan_risk_level(
        self,
        orphan_test_cases: list[ExtractedTestCase],
        company_id: int,
        links: list[CandidateLink] | None = None,
    ) -> list[OrphanTestCase]:
        """Classify orphan test case risk level using the Traceability Analyst.

        Uses keyword-based risk classification with precedence:
        high > medium > low. Determines suggested_action based on
        near-miss confidence (0.3-0.49). Falls back to default risk_level
        "medium" and suggested_action "link_to_requirement" on agent
        timeout (30s).

        Args:
            orphan_test_cases: List of orphan test cases to classify.
            company_id: Company ID for tenant scoping.
            links: Optional list of all links for near-miss detection.

        Returns:
            List of OrphanTestCase objects with risk_level classifications.
        """
        near_miss_ids: set[str] = set()
        if links:
            near_miss_ids = self._find_near_miss_test_cases(
                orphan_test_cases, links
            )

        return await self._classify_risk_level_with_keywords(
            orphan_test_cases, near_miss_ids
        )

    # ───────────────────────────────────────────────────────────────────────
    # Internal: Severity Classification with Keywords
    # ───────────────────────────────────────────────────────────────────────

    async def _classify_severity_with_keywords(
        self,
        orphan_requirements: list[ExtractedRequirement],
    ) -> list[OrphanRequirement]:
        """Classify orphan requirement severity using keyword analysis.

        Attempts AI-based classification first via the Traceability Analyst
        agent. Falls back to local keyword matching if the agent is
        unavailable or times out (30s). On timeout, assigns default
        severity "major" per Requirement 2.5.

        Args:
            orphan_requirements: Requirements to classify.

        Returns:
            List of OrphanRequirement with severity and suggested_action.
        """
        # Try AI-based classification first
        ai_classifications = await self._try_ai_severity_classification(
            orphan_requirements
        )

        if ai_classifications is not None:
            return ai_classifications

        # Fallback: local keyword-based classification
        return self._local_severity_classification(orphan_requirements)

    async def _try_ai_severity_classification(
        self,
        orphan_requirements: list[ExtractedRequirement],
    ) -> list[OrphanRequirement] | None:
        """Attempt AI-based severity classification via the agent.

        Sends orphan requirements to the Traceability Analyst agent for
        classification. Returns None if the agent is unavailable or
        times out, triggering fallback to local classification.

        Args:
            orphan_requirements: Requirements to classify.

        Returns:
            List of OrphanRequirement if successful, None on failure.
        """
        if self._inference_client is None:
            return None

        system_prompt, temperature, max_tokens = self._get_agent_config()

        # Build the classification request
        req_data = [
            {
                "requirement_id": req.requirement_id,
                "requirement_text": req.requirement_text,
            }
            for req in orphan_requirements
        ]
        user_prompt = (
            _SEVERITY_CLASSIFICATION_PROMPT + json.dumps(req_data, indent=2)
        )

        try:
            response_text = await asyncio.wait_for(
                self._inference_client.chat_completion(
                    model=self._get_model_name(),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=_CLASSIFICATION_TIMEOUT,
                ),
                timeout=_CLASSIFICATION_TIMEOUT,
            )
            return self._parse_severity_response(
                response_text, orphan_requirements
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(
                "AI severity classification failed (timeout or error), "
                "falling back to local keyword classification: %s",
                str(e),
            )
            return None

    def _parse_severity_response(
        self,
        response_text: str,
        orphan_requirements: list[ExtractedRequirement],
    ) -> list[OrphanRequirement] | None:
        """Parse AI severity classification response.

        Args:
            response_text: Raw response from the AI agent.
            orphan_requirements: Original requirements for fallback data.

        Returns:
            List of OrphanRequirement if parsing succeeds, None otherwise.
        """
        try:
            data = self._extract_json(response_text)
            classifications = data.get("classifications", [])

            # Build lookup from AI response
            ai_map: dict[str, dict[str, str]] = {}
            for item in classifications:
                req_id = item.get("requirement_id", "")
                severity = item.get("severity", "")
                action = item.get("suggested_action", "")
                if req_id and severity in ("critical", "major", "minor"):
                    ai_map[req_id] = {
                        "severity": severity,
                        "suggested_action": action,
                    }

            # Map back to OrphanRequirement objects
            results: list[OrphanRequirement] = []
            for req in orphan_requirements:
                if req.requirement_id in ai_map:
                    ai_result = ai_map[req.requirement_id]
                    severity = ai_result["severity"]
                    suggested_action = ai_result.get(
                        "suggested_action", "create_test_case"
                    )
                    # Validate suggested_action
                    if suggested_action not in (
                        "create_test_case",
                        "review_requirement",
                        "link_existing_test",
                    ):
                        suggested_action = "create_test_case"
                else:
                    # AI didn't classify this one — use local fallback
                    severity = self._classify_severity_by_keywords(
                        req.requirement_text
                    )
                    suggested_action = "create_test_case"

                results.append(
                    OrphanRequirement(
                        requirement_id=req.requirement_id,
                        requirement_text=req.requirement_text,
                        source_document_uuid=req.source_document_uuid,
                        source_section=req.source_section,
                        severity=severity,
                        suggested_action=suggested_action,
                    )
                )

            return results

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(
                "Failed to parse AI severity classification response: %s",
                str(e),
            )
            return None

    def _local_severity_classification(
        self,
        orphan_requirements: list[ExtractedRequirement],
    ) -> list[OrphanRequirement]:
        """Classify severity using local keyword matching.

        Uses keyword precedence: critical > major > minor.
        Assigns default severity "major" if no keywords match
        (per Requirement 2.5 timeout fallback behavior).

        Args:
            orphan_requirements: Requirements to classify.

        Returns:
            List of OrphanRequirement with severity classifications.
        """
        results: list[OrphanRequirement] = []
        for req in orphan_requirements:
            severity = self._classify_severity_by_keywords(
                req.requirement_text
            )
            suggested_action = "create_test_case"

            results.append(
                OrphanRequirement(
                    requirement_id=req.requirement_id,
                    requirement_text=req.requirement_text,
                    source_document_uuid=req.source_document_uuid,
                    source_section=req.source_section,
                    severity=severity,
                    suggested_action=suggested_action,
                )
            )

        return results

    @staticmethod
    def _classify_severity_by_keywords(text: str) -> str:
        """Classify severity of a single requirement by keyword matching.

        Applies precedence: critical > major > minor. If no keywords
        match, defaults to "major" (Requirement 2.5 fallback).

        Args:
            text: Requirement text to analyze.

        Returns:
            Severity string: "critical", "major", or "minor".
        """
        text_lower = text.lower()

        # Check critical keywords first (highest precedence)
        for keyword in _SEVERITY_KEYWORDS["critical"]:
            if keyword in text_lower:
                return "critical"

        # Check major keywords
        for keyword in _SEVERITY_KEYWORDS["major"]:
            if keyword in text_lower:
                return "major"

        # Check minor keywords
        for keyword in _SEVERITY_KEYWORDS["minor"]:
            if keyword in text_lower:
                return "minor"

        # Default to "major" when no keywords match (Requirement 2.5)
        return _DEFAULT_SEVERITY

    # ───────────────────────────────────────────────────────────────────────
    # Internal: Risk Level Classification with Keywords
    # ───────────────────────────────────────────────────────────────────────

    async def _classify_risk_level_with_keywords(
        self,
        orphan_test_cases: list[ExtractedTestCase],
        near_miss_ids: set[str],
    ) -> list[OrphanTestCase]:
        """Classify orphan test case risk level using keyword analysis.

        Attempts AI-based classification first via the Traceability Analyst
        agent. Falls back to local keyword matching if the agent is
        unavailable or times out (30s). On timeout, assigns default
        risk_level "medium" and suggested_action "link_to_requirement"
        per Requirement 3.5.

        Args:
            orphan_test_cases: Test cases to classify.
            near_miss_ids: Set of test case IDs with near-miss links
                (confidence 0.3-0.49).

        Returns:
            List of OrphanTestCase with risk_level and suggested_action.
        """
        # Try AI-based classification first
        ai_classifications = await self._try_ai_risk_classification(
            orphan_test_cases, near_miss_ids
        )

        if ai_classifications is not None:
            return ai_classifications

        # Fallback: local keyword-based classification
        return self._local_risk_level_classification(
            orphan_test_cases, near_miss_ids
        )

    async def _try_ai_risk_classification(
        self,
        orphan_test_cases: list[ExtractedTestCase],
        near_miss_ids: set[str],
    ) -> list[OrphanTestCase] | None:
        """Attempt AI-based risk level classification via the agent.

        Sends orphan test cases to the Traceability Analyst agent for
        classification. Returns None if the agent is unavailable or
        times out, triggering fallback to local classification.

        Args:
            orphan_test_cases: Test cases to classify.
            near_miss_ids: Set of test case IDs with near-miss links.

        Returns:
            List of OrphanTestCase if successful, None on failure.
        """
        if self._inference_client is None:
            return None

        system_prompt, temperature, max_tokens = self._get_agent_config()

        # Build the classification request
        tc_data = [
            {
                "test_case_id": tc.test_case_id,
                "test_case_text": tc.test_case_text,
                "has_near_miss": tc.test_case_id in near_miss_ids,
            }
            for tc in orphan_test_cases
        ]
        user_prompt = (
            _RISK_LEVEL_CLASSIFICATION_PROMPT + json.dumps(tc_data, indent=2)
        )

        try:
            response_text = await asyncio.wait_for(
                self._inference_client.chat_completion(
                    model=self._get_model_name(),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=_CLASSIFICATION_TIMEOUT,
                ),
                timeout=_CLASSIFICATION_TIMEOUT,
            )
            return self._parse_risk_level_response(
                response_text, orphan_test_cases, near_miss_ids
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(
                "AI risk level classification failed (timeout or error), "
                "falling back to local keyword classification: %s",
                str(e),
            )
            return None

    def _parse_risk_level_response(
        self,
        response_text: str,
        orphan_test_cases: list[ExtractedTestCase],
        near_miss_ids: set[str],
    ) -> list[OrphanTestCase] | None:
        """Parse AI risk level classification response.

        Args:
            response_text: Raw response from the AI agent.
            orphan_test_cases: Original test cases for fallback data.
            near_miss_ids: Set of test case IDs with near-miss links.

        Returns:
            List of OrphanTestCase if parsing succeeds, None otherwise.
        """
        try:
            data = self._extract_json(response_text)
            classifications = data.get("classifications", [])

            # Build lookup from AI response
            ai_map: dict[str, dict[str, str]] = {}
            for item in classifications:
                tc_id = item.get("test_case_id", "")
                risk_level = item.get("risk_level", "")
                action = item.get("suggested_action", "")
                if tc_id and risk_level in ("high", "medium", "low"):
                    ai_map[tc_id] = {
                        "risk_level": risk_level,
                        "suggested_action": action,
                    }

            # Map back to OrphanTestCase objects
            results: list[OrphanTestCase] = []
            for tc in orphan_test_cases:
                if tc.test_case_id in ai_map:
                    ai_result = ai_map[tc.test_case_id]
                    risk_level = ai_result["risk_level"]
                    suggested_action = ai_result.get(
                        "suggested_action", ""
                    )
                    # Validate suggested_action
                    if suggested_action not in (
                        "link_to_requirement",
                        "create_requirement",
                        "remove_test_case",
                    ):
                        suggested_action = self._determine_suggested_action(
                            tc.test_case_id, near_miss_ids
                        )
                else:
                    # AI didn't classify this one — use local fallback
                    risk_level = self._classify_risk_level_by_keywords(
                        tc.test_case_text
                    )
                    suggested_action = self._determine_suggested_action(
                        tc.test_case_id, near_miss_ids
                    )

                results.append(
                    OrphanTestCase(
                        test_case_id=tc.test_case_id,
                        test_case_text=tc.test_case_text,
                        target_document_uuid=tc.target_document_uuid,
                        target_section=tc.target_section,
                        risk_level=risk_level,
                        suggested_action=suggested_action,
                    )
                )

            return results

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(
                "Failed to parse AI risk level classification response: %s",
                str(e),
            )
            return None

    def _local_risk_level_classification(
        self,
        orphan_test_cases: list[ExtractedTestCase],
        near_miss_ids: set[str],
    ) -> list[OrphanTestCase]:
        """Classify risk level using local keyword matching.

        Uses keyword precedence: high > medium > low.
        Assigns default risk_level "medium" and suggested_action
        "link_to_requirement" if no keywords match (per Requirement 3.5
        timeout fallback behavior).

        Args:
            orphan_test_cases: Test cases to classify.
            near_miss_ids: Set of test case IDs with near-miss links.

        Returns:
            List of OrphanTestCase with risk_level classifications.
        """
        results: list[OrphanTestCase] = []
        for tc in orphan_test_cases:
            risk_level = self._classify_risk_level_by_keywords(
                tc.test_case_text
            )
            suggested_action = self._determine_suggested_action(
                tc.test_case_id, near_miss_ids
            )

            results.append(
                OrphanTestCase(
                    test_case_id=tc.test_case_id,
                    test_case_text=tc.test_case_text,
                    target_document_uuid=tc.target_document_uuid,
                    target_section=tc.target_section,
                    risk_level=risk_level,
                    suggested_action=suggested_action,
                )
            )

        return results

    @staticmethod
    def _classify_risk_level_by_keywords(text: str) -> str:
        """Classify risk level of a single test case by keyword matching.

        Applies precedence: high > medium > low. If no keywords match,
        defaults to "medium" (Requirement 3.5 fallback).

        Args:
            text: Test case text to analyze.

        Returns:
            Risk level string: "high", "medium", or "low".
        """
        text_lower = text.lower()

        # Check high keywords first (highest precedence)
        for keyword in _RISK_LEVEL_KEYWORDS["high"]:
            if keyword in text_lower:
                return "high"

        # Check medium keywords
        for keyword in _RISK_LEVEL_KEYWORDS["medium"]:
            if keyword in text_lower:
                return "medium"

        # Check low keywords
        for keyword in _RISK_LEVEL_KEYWORDS["low"]:
            if keyword in text_lower:
                return "low"

        # Default to "medium" when no keywords match (Requirement 3.5)
        return _DEFAULT_RISK_LEVEL

    # ───────────────────────────────────────────────────────────────────────
    # Internal: Near-Miss Detection and Suggested Action
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def _find_near_miss_test_cases(
        orphan_test_cases: list[ExtractedTestCase],
        links: list[CandidateLink],
    ) -> set[str]:
        """Find test cases with near-miss links (confidence 0.3-0.49).

        A near-miss is a link that exists but with confidence below the
        threshold (0.5), specifically in the range 0.3-0.49. These test
        cases likely have a plausible requirement match.

        Args:
            orphan_test_cases: Orphan test cases to check.
            links: All established traceability links.

        Returns:
            Set of test case IDs that have near-miss links.
        """
        orphan_tc_ids = {tc.test_case_id for tc in orphan_test_cases}
        near_miss_ids: set[str] = set()

        for link in links:
            if (
                link.test_case_id in orphan_tc_ids
                and _NEAR_MISS_CONFIDENCE_MIN
                <= link.link_confidence
                <= _NEAR_MISS_CONFIDENCE_MAX
            ):
                near_miss_ids.add(link.test_case_id)

        return near_miss_ids

    @staticmethod
    def _determine_suggested_action(
        test_case_id: str,
        near_miss_ids: set[str],
    ) -> str:
        """Determine suggested action for an orphan test case.

        Logic per Requirement 3.2:
        - Near-miss confidence (0.3-0.49) → "link_to_requirement"
        - No match → "create_requirement"
        - Redundant → "remove_test_case" (determined by AI only)

        Since redundancy detection requires AI analysis, the local
        fallback only distinguishes between near-miss and no-match.

        Args:
            test_case_id: The test case identifier.
            near_miss_ids: Set of test case IDs with near-miss links.

        Returns:
            Suggested action string.
        """
        if test_case_id in near_miss_ids:
            return "link_to_requirement"
        return "create_requirement"

    # ───────────────────────────────────────────────────────────────────────
    # Internal: Agent Configuration
    # ───────────────────────────────────────────────────────────────────────

    def _get_agent_config(self) -> tuple[str, float, int]:
        """Get the Traceability Analyst agent configuration for classification.

        Loads the agent archetype from the registry. Falls back to a
        default system prompt if the registry is unavailable.

        Returns:
            Tuple of (system_prompt, temperature, max_tokens).
        """
        default_system_prompt = (
            "You are a Traceability Analyst specializing in requirement-to-test "
            "mapping for regulated document management systems (GxP, FDA, EMA "
            "compliance). Classify orphan items by analyzing their text content "
            "against keyword categories. Output structured JSON matching the "
            "expected schema exactly."
        )
        default_temperature = 0.15
        default_max_tokens = 4096

        if self._agent_registry is None:
            return default_system_prompt, default_temperature, default_max_tokens

        try:
            archetypes = self._agent_registry.list_archetypes()

            # Try to load the Traceability Analyst archetype
            for archetype in archetypes:
                if archetype.get("archetype") == "Traceability Analyst":
                    system_prompt = archetype.get(
                        "system_prompt", default_system_prompt
                    )
                    tuning = archetype.get("contextual_tuning", {})
                    temperature = tuning.get(
                        "temperature", default_temperature
                    )
                    max_tokens = tuning.get("max_tokens", default_max_tokens)
                    return system_prompt, temperature, max_tokens

        except Exception as e:
            logger.warning(
                "Failed to load agent archetype for classification: %s",
                str(e),
            )

        return default_system_prompt, default_temperature, default_max_tokens

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
    # Internal: JSON Extraction
    # ───────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_json(response_text: str) -> dict[str, Any]:
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
