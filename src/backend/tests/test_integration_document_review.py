"""Integration tests for AI document review.

Tests: submit document → receive structured review report with chapter results and findings.

References:
    - Task 22.8: Integration tests for AI document review
"""

import uuid

import pytest

from alcoabase.services.agent_registry import AgentDefinition, AgentRegistry
from alcoabase.services.document_reviewer import (
    DocumentReviewer,
    FindingSeverity,
    ReviewStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def review_registry() -> AgentRegistry:
    """Create an AgentRegistry with a review agent registered."""
    registry = AgentRegistry()

    agent = AgentDefinition(
        id=str(uuid.uuid4()),
        schema_version="1.0",
        agent_type="review",
        name="SOP Review Agent",
        description="Reviews SOPs for completeness",
        system_prompt="You are a reviewer.",
        dspy_modules=[{"name": "structure_check", "type": "ChainOfThought"}],
        knowledge_scopes={"tags": ["SOP"]},
        target_document_tag="SOP",
        required_chapters=[
            {"name": "Purpose", "required": True},
            {"name": "Scope", "required": True},
            {"name": "Responsibilities", "required": True},
            {"name": "Procedure", "required": True},
            {"name": "Safety Precautions", "required": True},
            {"name": "References", "required": True},
            {"name": "Revision History", "required": True},
            {"name": "Definitions", "required": False},
        ],
        compliance_checklist=[
            "Document has a unique document number",
            "All procedural steps are numbered sequentially",
            "Safety warnings appear before the steps they relate to",
        ],
        severity_rules={
            "critical": "Missing required chapter",
            "major": "Incomplete section",
            "minor": "Formatting issues",
            "informational": "Style suggestions",
        },
    )
    registry.register_agent(agent)
    return registry


@pytest.fixture
def reviewer(review_registry) -> DocumentReviewer:
    """Create a DocumentReviewer with the test registry."""
    return DocumentReviewer(agent_registry=review_registry)


# ---------------------------------------------------------------------------
# Integration Tests: Document Review
# ---------------------------------------------------------------------------


class TestDocumentReviewIntegration:
    """Integration tests for the full document review flow."""

    def test_complete_document_passes_review(self, reviewer):
        """Document with all required chapters passes review."""
        document_text = """
# Purpose
This SOP defines the procedure for sample analysis.

# Scope
Applies to all laboratory personnel in Lab-A.

# Responsibilities
Lab Manager: Oversees procedure execution.
Analyst: Performs the analysis.

# Procedure
1. Prepare samples
2. Run analysis
3. Record results

# Safety Precautions
Wear PPE at all times. Handle chemicals in fume hood.

# References
ISO 17025, Internal SOP-001

# Revision History
v1.0 - 2025-01-15 - Initial release
"""
        report = reviewer.review_document(
            document_uuid="2025-00001",
            document_version="1.0",
            document_text=document_text,
            document_tag="SOP",
            user_id=1,
        )

        assert report.overall_status == ReviewStatus.PASS
        assert report.document_uuid == "2025-00001"
        assert report.reviewer_user_id == 1
        assert report.summary != ""

    def test_incomplete_document_fails_review(self, reviewer):
        """Document missing required chapters fails review."""
        document_text = """
# Purpose
This SOP defines the procedure for sample analysis.

# Scope
Applies to all laboratory personnel.
"""
        report = reviewer.review_document(
            document_uuid="2025-00002",
            document_version="1.0",
            document_text=document_text,
            document_tag="SOP",
            user_id=1,
        )

        assert report.overall_status == ReviewStatus.FAIL
        assert len(report.findings) > 0

        # Should have critical findings for missing required chapters
        critical_findings = [
            f for f in report.findings if f.severity == FindingSeverity.CRITICAL
        ]
        assert len(critical_findings) >= 1

    def test_review_report_has_chapter_results(self, reviewer):
        """Review report includes per-chapter pass/fail results."""
        document_text = "# Purpose\nTest purpose.\n\n# Scope\nTest scope."

        report = reviewer.review_document(
            document_uuid="2025-00003",
            document_version="1.0",
            document_text=document_text,
            document_tag="SOP",
            user_id=1,
        )

        assert len(report.chapter_results) > 0

        # Check that chapter results have expected structure
        for result in report.chapter_results:
            assert result.chapter_name != ""
            assert isinstance(result.required, bool)
            assert isinstance(result.present, bool)

    def test_review_report_findings_have_recommendations(self, reviewer):
        """Review findings include actionable recommendations."""
        document_text = "# Purpose\nBrief purpose."

        report = reviewer.review_document(
            document_uuid="2025-00004",
            document_version="1.0",
            document_text=document_text,
            document_tag="SOP",
            user_id=1,
        )

        for finding in report.findings:
            assert finding.description != ""
            assert finding.recommendation != ""
            assert finding.severity in FindingSeverity

    def test_review_report_persisted(self, reviewer):
        """Review report is persisted and retrievable."""
        document_text = "# Purpose\nTest."

        report = reviewer.review_document(
            document_uuid="2025-00005",
            document_version="1.0",
            document_text=document_text,
            document_tag="SOP",
            user_id=1,
        )

        # Retrieve by ID
        retrieved = reviewer.get_report(report.id)
        assert retrieved is not None
        assert retrieved.id == report.id

        # Retrieve by document UUID
        doc_reports = reviewer.get_reports_for_document("2025-00005")
        assert len(doc_reports) == 1

    def test_no_matching_agent_returns_error(self, reviewer):
        """Review for unregistered document tag raises ValueError."""
        with pytest.raises(ValueError, match="No review agent found"):
            reviewer.review_document(
                document_uuid="2025-00006",
                document_version="1.0",
                document_text="Content",
                document_tag="UnknownType",
                user_id=1,
            )

    def test_optional_chapters_dont_cause_failure(self, reviewer):
        """Missing optional chapters don't cause review failure."""
        # Include all required chapters but skip optional "Definitions"
        document_text = """
# Purpose
Test purpose.

# Scope
Test scope.

# Responsibilities
Test responsibilities.

# Procedure
1. Step one.

# Safety Precautions
Wear PPE.

# References
ISO 17025.

# Revision History
v1.0 - Initial.
"""
        report = reviewer.review_document(
            document_uuid="2025-00007",
            document_version="1.0",
            document_text=document_text,
            document_tag="SOP",
            user_id=1,
        )

        # Should pass even without optional "Definitions" chapter
        assert report.overall_status in (ReviewStatus.PASS, ReviewStatus.PASS_WITH_FINDINGS)
