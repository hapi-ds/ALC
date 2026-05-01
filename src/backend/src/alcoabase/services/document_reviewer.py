"""Document Reviewer service for AI-powered document review.

This module provides:
- Review agent resolution by document tag or manual override
- Structure check DSPy module (placeholder)
- Content review DSPy module (placeholder)
- ReviewReport and ReviewFinding Pydantic models
- Review report persistence and audit trail recording

References:
    - Task 21: Document Reviewer (AI-Powered Review)
    - Design doc Section 10a: Document Reviewer
"""

import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReviewStatus(str, Enum):
    """Overall review status."""

    PASS = "Pass"
    PASS_WITH_FINDINGS = "Pass with Findings"
    FAIL = "Fail"


class FindingSeverity(str, Enum):
    """Severity levels for review findings."""

    CRITICAL = "Critical"
    MAJOR = "Major"
    MINOR = "Minor"
    INFORMATIONAL = "Informational"


# ---------------------------------------------------------------------------
# Pydantic Models (Task 21.4)
# ---------------------------------------------------------------------------


class ChapterResult(BaseModel):
    """Result of a single chapter/section check.

    Attributes:
        chapter_name: Name of the chapter being checked.
        required: Whether this chapter is required.
        present: Whether the chapter was found in the document.
        complete: Whether the chapter content is complete.
        order_correct: Whether the chapter appears in the expected order.
        notes: Additional notes about the chapter.
    """

    chapter_name: str
    required: bool = True
    present: bool = False
    complete: bool = False
    order_correct: bool = True
    notes: str = ""

    @property
    def passed(self) -> bool:
        """Chapter passes if present and complete (or not required)."""
        if not self.required:
            return True
        return self.present and self.complete


class ReviewFinding(BaseModel):
    """A single finding from the document review.

    Attributes:
        id: Unique finding identifier.
        severity: Severity classification.
        chapter: Which chapter/section the finding relates to.
        page_or_section: Page number or section reference.
        description: Description of the finding.
        recommendation: Recommended action to address the finding.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    severity: FindingSeverity
    chapter: str
    page_or_section: str = ""
    description: str
    recommendation: str = ""


class ReviewReport(BaseModel):
    """Structured review report for a document.

    Attributes:
        id: Unique report identifier.
        document_uuid: UUID of the reviewed document.
        document_version: Version of the reviewed document.
        review_agent_id: ID of the review agent used.
        review_agent_name: Name of the review agent used.
        reviewer_user_id: ID of the user who triggered the review.
        timestamp: When the review was performed.
        overall_status: Overall review status (Pass, Pass with Findings, Fail).
        chapter_results: Per-chapter pass/fail results.
        findings: List of findings with severity and recommendations.
        summary: Overall review summary text.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_uuid: str
    document_version: str
    review_agent_id: str
    review_agent_name: str = ""
    reviewer_user_id: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overall_status: ReviewStatus = ReviewStatus.PASS
    chapter_results: list[ChapterResult] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = ""

    def compute_overall_status(self) -> "ReviewReport":
        """Compute overall status based on chapter results and findings.

        Returns:
            Self with updated overall_status.
        """
        has_critical = any(
            f.severity == FindingSeverity.CRITICAL for f in self.findings
        )
        has_required_missing = any(
            r.required and not r.passed for r in self.chapter_results
        )

        if has_critical or has_required_missing:
            self.overall_status = ReviewStatus.FAIL
        elif len(self.findings) > 0:
            self.overall_status = ReviewStatus.PASS_WITH_FINDINGS
        else:
            self.overall_status = ReviewStatus.PASS

        return self


# ---------------------------------------------------------------------------
# Structure Check DSPy Module (Task 21.2 - Placeholder)
# ---------------------------------------------------------------------------


class StructureCheckModule:
    """DSPy module for checking document structure against required chapters.

    Parses document headings/sections and compares against the
    required_chapters list from the Review_Agent_Definition.

    This is a placeholder implementation that performs basic heading matching.
    In production, this would use DSPy ChainOfThought with a local LLM.
    """

    def __init__(self, required_chapters: list[dict[str, Any]]) -> None:
        """Initialize with required chapters configuration.

        Args:
            required_chapters: List of chapter definitions with name, required flag.
        """
        self.required_chapters = required_chapters

    def check(self, document_text: str) -> list[ChapterResult]:
        """Check document structure against required chapters.

        Args:
            document_text: Full text content of the document.

        Returns:
            List of ChapterResult for each required chapter.
        """
        results: list[ChapterResult] = []
        text_lower = document_text.lower()

        for chapter_def in self.required_chapters:
            name = chapter_def["name"]
            required = chapter_def.get("required", True)

            # Basic heading detection (placeholder for LLM-based analysis)
            present = name.lower() in text_lower
            complete = present  # Placeholder: assume complete if present

            results.append(
                ChapterResult(
                    chapter_name=name,
                    required=required,
                    present=present,
                    complete=complete,
                    order_correct=True,
                    notes="" if present else f"Section '{name}' not found in document",
                )
            )

        return results


# ---------------------------------------------------------------------------
# Content Review DSPy Module (Task 21.3 - Placeholder)
# ---------------------------------------------------------------------------


class ContentReviewModule:
    """DSPy module for reviewing document content against compliance checklist.

    Evaluates each section against compliance_checklist items and classifies
    findings by severity_rules.

    This is a placeholder implementation. In production, this would use
    DSPy ChainOfThought with a local LLM and Knowledge_Service retrieval.
    """

    def __init__(
        self,
        compliance_checklist: list[str],
        severity_rules: dict[str, str],
    ) -> None:
        """Initialize with compliance checklist and severity rules.

        Args:
            compliance_checklist: List of compliance items to check.
            severity_rules: Mapping of severity level to description.
        """
        self.compliance_checklist = compliance_checklist
        self.severity_rules = severity_rules

    def review(
        self, document_text: str, chapter_results: list[ChapterResult]
    ) -> list[ReviewFinding]:
        """Review document content for compliance.

        Args:
            document_text: Full text content of the document.
            chapter_results: Results from structure check.

        Returns:
            List of ReviewFinding for any compliance issues found.
        """
        findings: list[ReviewFinding] = []

        # Generate findings for missing required chapters
        for result in chapter_results:
            if result.required and not result.present:
                findings.append(
                    ReviewFinding(
                        severity=FindingSeverity.CRITICAL,
                        chapter=result.chapter_name,
                        page_or_section="N/A",
                        description=f"Required chapter '{result.chapter_name}' is missing from the document",
                        recommendation=f"Add a '{result.chapter_name}' section to the document",
                    )
                )

        # Placeholder: In production, LLM would evaluate each checklist item
        # against the document content and generate findings

        return findings


# ---------------------------------------------------------------------------
# Review Report Storage (Task 21.5)
# ---------------------------------------------------------------------------


class ReviewReportStore:
    """In-memory store for review reports.

    In production, this would persist to PostgreSQL.
    """

    def __init__(self) -> None:
        """Initialize empty report store."""
        self._reports: dict[str, ReviewReport] = {}

    def save(self, report: ReviewReport) -> ReviewReport:
        """Save a review report.

        Args:
            report: The review report to persist.

        Returns:
            The saved report.
        """
        self._reports[report.id] = report
        logger.info(
            "Saved review report %s for document %s (status: %s)",
            report.id,
            report.document_uuid,
            report.overall_status.value,
        )
        return report

    def get(self, report_id: str) -> ReviewReport | None:
        """Get a review report by ID.

        Args:
            report_id: The report identifier.

        Returns:
            The ReviewReport, or None if not found.
        """
        return self._reports.get(report_id)

    def get_by_document(self, document_uuid: str) -> list[ReviewReport]:
        """Get all review reports for a document.

        Args:
            document_uuid: The document UUID.

        Returns:
            List of review reports for the document.
        """
        return [
            r for r in self._reports.values()
            if r.document_uuid == document_uuid
        ]


# ---------------------------------------------------------------------------
# Document Reviewer Service (Task 21.1)
# ---------------------------------------------------------------------------


class DocumentReviewer:
    """AI-powered document review service.

    Resolves review agents by document tag, runs structure and content
    checks, and produces structured ReviewReports.

    Attributes:
        _agent_registry: Reference to the AgentRegistry for agent resolution.
        _report_store: Storage for review reports.
    """

    def __init__(
        self,
        agent_registry: Any = None,
        report_store: ReviewReportStore | None = None,
    ) -> None:
        """Initialize the DocumentReviewer.

        Args:
            agent_registry: AgentRegistry instance for resolving review agents.
            report_store: Optional ReviewReportStore (creates default if None).
        """
        self._agent_registry = agent_registry
        self._report_store = report_store or ReviewReportStore()

    def resolve_review_agent(
        self, document_tag: str, review_agent_id: str | None = None
    ) -> Any:
        """Resolve the review agent for a document.

        Args:
            document_tag: The document's primary tag (e.g., "SOP").
            review_agent_id: Optional explicit agent ID override.

        Returns:
            The resolved AgentDefinition.

        Raises:
            ValueError: If no matching review agent is found.
        """
        if self._agent_registry is None:
            raise ValueError("Agent registry not configured")

        # If explicit agent ID provided, use it
        if review_agent_id:
            agent = self._agent_registry.get_agent(review_agent_id)
            if agent is None:
                raise ValueError(f"Review agent not found: {review_agent_id}")
            if agent.agent_type != "review":
                raise ValueError(
                    f"Agent '{agent.name}' is not a review agent (type: {agent.agent_type})"
                )
            return agent

        # Auto-resolve by document tag
        review_agents = self._agent_registry.list_agents(agent_type="review")
        for agent in review_agents:
            if agent.target_document_tag == document_tag:
                return agent

        raise ValueError(
            f"No review agent found for document tag '{document_tag}'. "
            f"Register a review agent with target_document_tag='{document_tag}' "
            f"or specify a review_agent_id explicitly."
        )

    def review_document(
        self,
        document_uuid: str,
        document_version: str,
        document_text: str,
        document_tag: str,
        user_id: int,
        review_agent_id: str | None = None,
    ) -> ReviewReport:
        """Perform AI-driven document review.

        Args:
            document_uuid: UUID of the document to review.
            document_version: Version string of the document.
            document_text: Full text content of the document.
            document_tag: Primary tag of the document (for agent resolution).
            user_id: ID of the user triggering the review.
            review_agent_id: Optional explicit review agent ID.

        Returns:
            Structured ReviewReport with chapter results and findings.

        Raises:
            ValueError: If no matching review agent is found.
        """
        # 1. Resolve review agent
        agent = self.resolve_review_agent(document_tag, review_agent_id)

        # 2. Run structure check
        structure_module = StructureCheckModule(
            required_chapters=agent.required_chapters or []
        )
        chapter_results = structure_module.check(document_text)

        # 3. Run content review
        content_module = ContentReviewModule(
            compliance_checklist=agent.compliance_checklist or [],
            severity_rules=agent.severity_rules or {},
        )
        findings = content_module.review(document_text, chapter_results)

        # 4. Build report
        report = ReviewReport(
            document_uuid=document_uuid,
            document_version=document_version,
            review_agent_id=agent.id,
            review_agent_name=agent.name,
            reviewer_user_id=user_id,
            chapter_results=chapter_results,
            findings=findings,
        )

        # 5. Compute overall status
        report.compute_overall_status()

        # 6. Generate summary
        report.summary = self._generate_summary(report)

        # 7. Persist report
        self._report_store.save(report)

        logger.info(
            "Document review completed: doc=%s, agent=%s, status=%s, findings=%d",
            document_uuid,
            agent.name,
            report.overall_status.value,
            len(findings),
        )

        return report

    def _generate_summary(self, report: ReviewReport) -> str:
        """Generate a human-readable summary of the review.

        Args:
            report: The completed review report.

        Returns:
            Summary text.
        """
        total_chapters = len(report.chapter_results)
        passed_chapters = sum(1 for r in report.chapter_results if r.passed)
        critical_count = sum(
            1 for f in report.findings if f.severity == FindingSeverity.CRITICAL
        )
        major_count = sum(
            1 for f in report.findings if f.severity == FindingSeverity.MAJOR
        )

        parts = [
            f"Review completed with status: {report.overall_status.value}.",
            f"Chapters: {passed_chapters}/{total_chapters} passed.",
        ]

        if report.findings:
            parts.append(
                f"Findings: {len(report.findings)} total "
                f"({critical_count} critical, {major_count} major)."
            )

        return " ".join(parts)

    def get_report(self, report_id: str) -> ReviewReport | None:
        """Get a review report by ID.

        Args:
            report_id: The report identifier.

        Returns:
            The ReviewReport, or None if not found.
        """
        return self._report_store.get(report_id)

    def get_reports_for_document(self, document_uuid: str) -> list[ReviewReport]:
        """Get all review reports for a document.

        Args:
            document_uuid: The document UUID.

        Returns:
            List of review reports.
        """
        return self._report_store.get_by_document(document_uuid)
