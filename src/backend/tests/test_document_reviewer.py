"""Tests for the Document Reviewer service.

Covers:
- Task 21.11: Property-based tests for structure check (chapter detection)
- Task 21.12: Property-based tests for review agent tag matching
- Task 21.13: Property-based tests for review agent YAML round-trip
- Task 21.14: Unit tests for review report structure and finding severity
"""

import uuid
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from alcoabase.services.agent_registry import AgentDefinition, AgentRegistry
from alcoabase.services.document_reviewer import (
    ChapterResult,
    ContentReviewModule,
    DocumentReviewer,
    FindingSeverity,
    ReviewFinding,
    ReviewReport,
    ReviewReportStore,
    ReviewStatus,
    StructureCheckModule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_review_agent(
    target_tag: str = "SOP",
    required_chapters: list[dict] | None = None,
    compliance_checklist: list[str] | None = None,
    severity_rules: dict[str, str] | None = None,
) -> AgentDefinition:
    """Create a review agent definition for testing."""
    if required_chapters is None:
        required_chapters = [
            {"name": "Purpose", "required": True},
            {"name": "Scope", "required": True},
            {"name": "Procedure", "required": True},
        ]
    if compliance_checklist is None:
        compliance_checklist = ["Document has a unique number"]
    if severity_rules is None:
        severity_rules = {
            "critical": "Missing required chapter",
            "major": "Incomplete section",
            "minor": "Formatting issues",
            "informational": "Style suggestions",
        }

    return AgentDefinition(
        id=str(uuid.uuid4()),
        schema_version="1.0",
        agent_type="review",
        name=f"Test Review Agent ({target_tag})",
        description=f"Review agent for {target_tag} documents",
        system_prompt="You are a reviewer.",
        dspy_modules=[{"name": "structure_check", "type": "ChainOfThought"}],
        knowledge_scopes={"tags": [target_tag]},
        target_document_tag=target_tag,
        required_chapters=required_chapters,
        compliance_checklist=compliance_checklist,
        severity_rules=severity_rules,
    )


# ---------------------------------------------------------------------------
# Task 21.14: Unit tests for review report structure
# ---------------------------------------------------------------------------


class TestReviewReportStructure:
    """Unit tests for ReviewReport and ReviewFinding models."""

    def test_review_report_creation(self):
        """ReviewReport can be created with all required fields."""
        report = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
        )
        assert report.document_uuid == "2024-00001"
        assert report.overall_status == ReviewStatus.PASS
        assert report.chapter_results == []
        assert report.findings == []

    def test_review_finding_creation(self):
        """ReviewFinding can be created with severity classification."""
        finding = ReviewFinding(
            severity=FindingSeverity.CRITICAL,
            chapter="Purpose",
            page_or_section="Section 1",
            description="Required chapter is missing",
            recommendation="Add a Purpose section",
        )
        assert finding.severity == FindingSeverity.CRITICAL
        assert finding.chapter == "Purpose"
        assert finding.id  # Auto-generated

    def test_chapter_result_passed_required_present(self):
        """Required chapter passes when present and complete."""
        result = ChapterResult(
            chapter_name="Purpose",
            required=True,
            present=True,
            complete=True,
        )
        assert result.passed is True

    def test_chapter_result_failed_required_missing(self):
        """Required chapter fails when not present."""
        result = ChapterResult(
            chapter_name="Purpose",
            required=True,
            present=False,
            complete=False,
        )
        assert result.passed is False

    def test_chapter_result_optional_always_passes(self):
        """Optional chapter always passes regardless of presence."""
        result = ChapterResult(
            chapter_name="Definitions",
            required=False,
            present=False,
            complete=False,
        )
        assert result.passed is True

    def test_compute_overall_status_pass(self):
        """Overall status is Pass when no findings and all chapters pass."""
        report = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
            chapter_results=[
                ChapterResult(chapter_name="Purpose", required=True, present=True, complete=True),
            ],
            findings=[],
        )
        report.compute_overall_status()
        assert report.overall_status == ReviewStatus.PASS

    def test_compute_overall_status_pass_with_findings(self):
        """Overall status is Pass with Findings when non-critical findings exist."""
        report = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
            chapter_results=[
                ChapterResult(chapter_name="Purpose", required=True, present=True, complete=True),
            ],
            findings=[
                ReviewFinding(
                    severity=FindingSeverity.MINOR,
                    chapter="Purpose",
                    description="Formatting issue",
                ),
            ],
        )
        report.compute_overall_status()
        assert report.overall_status == ReviewStatus.PASS_WITH_FINDINGS

    def test_compute_overall_status_fail_critical(self):
        """Overall status is Fail when critical findings exist."""
        report = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
            chapter_results=[],
            findings=[
                ReviewFinding(
                    severity=FindingSeverity.CRITICAL,
                    chapter="Purpose",
                    description="Missing required chapter",
                ),
            ],
        )
        report.compute_overall_status()
        assert report.overall_status == ReviewStatus.FAIL

    def test_compute_overall_status_fail_missing_required(self):
        """Overall status is Fail when required chapter is missing."""
        report = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
            chapter_results=[
                ChapterResult(chapter_name="Purpose", required=True, present=False, complete=False),
            ],
            findings=[],
        )
        report.compute_overall_status()
        assert report.overall_status == ReviewStatus.FAIL

    def test_review_report_store_save_and_get(self):
        """ReviewReportStore can save and retrieve reports."""
        store = ReviewReportStore()
        report = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
        )
        store.save(report)
        retrieved = store.get(report.id)
        assert retrieved is not None
        assert retrieved.document_uuid == "2024-00001"

    def test_review_report_store_get_by_document(self):
        """ReviewReportStore can retrieve all reports for a document."""
        store = ReviewReportStore()
        report1 = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
        )
        report2 = ReviewReport(
            document_uuid="2024-00001",
            document_version="2.0",
            review_agent_id="agent-123",
            reviewer_user_id=1,
        )
        store.save(report1)
        store.save(report2)
        reports = store.get_by_document("2024-00001")
        assert len(reports) == 2

    def test_finding_severity_classification(self):
        """All severity levels are valid FindingSeverity values."""
        for severity in FindingSeverity:
            finding = ReviewFinding(
                severity=severity,
                chapter="Test",
                description="Test finding",
            )
            assert finding.severity == severity

    def test_audit_trail_fields_present(self):
        """ReviewReport contains all audit trail fields."""
        report = ReviewReport(
            document_uuid="2024-00001",
            document_version="1.0",
            review_agent_id="agent-123",
            review_agent_name="Test Agent",
            reviewer_user_id=42,
        )
        assert report.reviewer_user_id == 42
        assert report.review_agent_id == "agent-123"
        assert report.timestamp is not None
        assert report.id is not None


# ---------------------------------------------------------------------------
# Task 21.11: Property-based tests for structure check
# ---------------------------------------------------------------------------


# Strategy for generating chapter names
chapter_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=3,
    max_size=30,
).filter(lambda s: s.strip() != "")

# Strategy for generating required chapter lists
required_chapters_st = st.lists(
    st.fixed_dictionaries({
        "name": chapter_name_st,
        "required": st.booleans(),
    }),
    min_size=1,
    max_size=10,
    unique_by=lambda c: c["name"].lower(),
)


class TestStructureCheckProperty:
    """Property-based tests for structure check chapter detection.

    **Validates: Requirements 24.2, 24.3**
    """

    @given(
        required_chapters=required_chapters_st,
        chapters_to_include=st.data(),
    )
    @settings(max_examples=50)
    def test_missing_chapters_detected(
        self, required_chapters: list[dict], chapters_to_include: st.DataObject
    ):
        """For documents with random subsets of required chapters removed,
        all omissions are detected by the structure check.

        **Validates: Requirements 24.2**
        """
        # Decide which chapters to include in the document
        include_flags = chapters_to_include.draw(
            st.lists(
                st.booleans(),
                min_size=len(required_chapters),
                max_size=len(required_chapters),
            )
        )

        # Build document text with only included chapters
        doc_parts = []
        for chapter, include in zip(required_chapters, include_flags):
            if include:
                doc_parts.append(f"# {chapter['name']}\nContent for {chapter['name']}.")

        document_text = "\n\n".join(doc_parts)

        # Run structure check
        module = StructureCheckModule(required_chapters=required_chapters)
        results = module.check(document_text)

        # Verify: every chapter has a result
        assert len(results) == len(required_chapters)

        # Verify: chapters not included are detected as missing
        for chapter, include, result in zip(required_chapters, include_flags, results):
            if not include:
                assert result.present is False, (
                    f"Chapter '{chapter['name']}' was not in document but marked as present"
                )


# ---------------------------------------------------------------------------
# Task 21.12: Property-based tests for review agent tag matching
# ---------------------------------------------------------------------------


class TestReviewAgentTagMatching:
    """Property-based tests for review agent tag resolution.

    **Validates: Requirements 25.5**
    """

    @given(
        tags=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L",)),
                min_size=3,
                max_size=15,
            ),
            min_size=2,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_correct_agent_resolved_for_matching_tag(self, tags: list[str]):
        """Review agent tag matching resolves correct agent for matching tags.

        **Validates: Requirements 25.5**
        """
        registry = AgentRegistry()

        # Register a review agent for each tag
        agents = {}
        for tag in tags:
            agent = make_review_agent(target_tag=tag)
            registry.register_agent(agent)
            agents[tag] = agent

        reviewer = DocumentReviewer(agent_registry=registry)

        # Each tag should resolve to its corresponding agent
        for tag in tags:
            resolved = reviewer.resolve_review_agent(document_tag=tag)
            assert resolved.target_document_tag == tag
            assert resolved.id == agents[tag].id

    @given(
        registered_tag=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=3,
            max_size=15,
        ),
        query_tag=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=3,
            max_size=15,
        ),
    )
    @settings(max_examples=30)
    def test_unmatched_tag_returns_error(self, registered_tag: str, query_tag: str):
        """For documents with no matching review agent, the system returns an error.

        **Validates: Requirements 25.5**
        """
        assume(registered_tag.lower() != query_tag.lower())

        registry = AgentRegistry()
        agent = make_review_agent(target_tag=registered_tag)
        registry.register_agent(agent)

        reviewer = DocumentReviewer(agent_registry=registry)

        with pytest.raises(ValueError, match="No review agent found"):
            reviewer.resolve_review_agent(document_tag=query_tag)


# ---------------------------------------------------------------------------
# Task 21.13: Property-based tests for review agent YAML round-trip
# ---------------------------------------------------------------------------


class TestReviewAgentRoundTrip:
    """Property-based tests for review agent YAML portability round-trip.

    **Validates: Requirements 25.6**
    """

    @given(
        target_tag=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=3,
            max_size=15,
        ),
        num_chapters=st.integers(min_value=1, max_value=8),
        num_checklist_items=st.integers(min_value=1, max_value=6),
    )
    @settings(max_examples=30)
    def test_export_import_preserves_review_fields(
        self, target_tag: str, num_chapters: int, num_checklist_items: int
    ):
        """Export then import produces equivalent review agent definition
        including required_chapters, compliance_checklist, and severity_rules.

        **Validates: Requirements 25.6**
        """
        # Build a review agent with generated fields
        chapters = [
            {"name": f"Chapter{i}", "required": i % 2 == 0}
            for i in range(num_chapters)
        ]
        checklist = [f"Check item {i}" for i in range(num_checklist_items)]
        severity_rules = {
            "critical": "Critical issue",
            "major": "Major issue",
            "minor": "Minor issue",
            "informational": "Info",
        }

        agent = make_review_agent(
            target_tag=target_tag,
            required_chapters=chapters,
            compliance_checklist=checklist,
            severity_rules=severity_rules,
        )

        registry = AgentRegistry()
        registry.register_agent(agent)

        # Export
        yaml_bytes = registry.export_agent(agent.id)
        assert yaml_bytes is not None

        # Import into fresh registry
        registry2 = AgentRegistry()
        imported = registry2.import_agent(yaml_bytes)

        # Verify equivalence
        assert imported.agent_type == "review"
        assert imported.target_document_tag == target_tag
        assert imported.required_chapters == chapters
        assert imported.compliance_checklist == checklist
        assert imported.severity_rules == severity_rules
        assert imported.name == agent.name
        assert imported.description == agent.description
        assert imported.system_prompt == agent.system_prompt


# ---------------------------------------------------------------------------
# Task 21.10: Review agent import/export unit tests
# ---------------------------------------------------------------------------


class TestReviewAgentImportExport:
    """Unit tests for review agent import/export via AgentRegistry."""

    def test_import_valid_review_agent_yaml(self):
        """Valid review agent YAML can be imported."""
        yaml_content = b"""
schema_version: "1.0"
agent_type: "review"
name: "Test Review Agent"
description: "A test review agent"
target_document_tag: "SOP"
system_prompt: "You are a reviewer."
required_chapters:
  - name: "Purpose"
    required: true
  - name: "Scope"
    required: true
compliance_checklist:
  - "Has document number"
severity_rules:
  critical: "Missing chapter"
  major: "Incomplete"
  minor: "Formatting"
  informational: "Style"
dspy_modules:
  - name: "structure_check"
    type: "ChainOfThought"
knowledge_scopes:
  tags: ["SOP"]
"""
        registry = AgentRegistry()
        agent = registry.import_agent(yaml_content)

        assert agent.agent_type == "review"
        assert agent.target_document_tag == "SOP"
        assert len(agent.required_chapters) == 2
        assert agent.compliance_checklist == ["Has document number"]

    def test_export_review_agent_includes_review_fields(self):
        """Exported review agent YAML includes all review-specific fields."""
        agent = make_review_agent(target_tag="Report")
        registry = AgentRegistry()
        registry.register_agent(agent)

        yaml_bytes = registry.export_agent(agent.id)
        yaml_str = yaml_bytes.decode("utf-8")

        assert "target_document_tag" in yaml_str
        assert "required_chapters" in yaml_str
        assert "compliance_checklist" in yaml_str
        assert "severity_rules" in yaml_str
        assert "Report" in yaml_str

    def test_load_review_agents_from_directory(self):
        """Review agent YAML files can be loaded from the examples directory."""
        examples_dir = Path(__file__).parent.parent.parent.parent / "agents" / "examples"
        if not examples_dir.exists():
            pytest.skip("agents/examples directory not found")

        registry = AgentRegistry()
        agents = registry.load_agents(examples_dir)

        review_agents = [a for a in agents if a.agent_type == "review"]
        assert len(review_agents) >= 1, "Expected at least one review agent in examples"

        for agent in review_agents:
            assert agent.target_document_tag is not None
            assert agent.required_chapters is not None
            assert len(agent.required_chapters) > 0


# ---------------------------------------------------------------------------
# Document Reviewer integration tests
# ---------------------------------------------------------------------------


class TestDocumentReviewerIntegration:
    """Integration tests for the full document review flow."""

    def test_review_document_with_all_chapters_present(self):
        """Document with all required chapters gets Pass status."""
        registry = AgentRegistry()
        agent = make_review_agent(
            target_tag="SOP",
            required_chapters=[
                {"name": "Purpose", "required": True},
                {"name": "Scope", "required": True},
            ],
        )
        registry.register_agent(agent)

        reviewer = DocumentReviewer(agent_registry=registry)
        report = reviewer.review_document(
            document_uuid="2024-00001",
            document_version="1.0",
            document_text="# Purpose\nThis SOP covers...\n\n# Scope\nApplies to...",
            document_tag="SOP",
            user_id=1,
        )

        assert report.overall_status == ReviewStatus.PASS
        assert all(r.present for r in report.chapter_results)

    def test_review_document_with_missing_chapters(self):
        """Document with missing required chapters gets Fail status."""
        registry = AgentRegistry()
        agent = make_review_agent(
            target_tag="SOP",
            required_chapters=[
                {"name": "Purpose", "required": True},
                {"name": "Scope", "required": True},
                {"name": "Procedure", "required": True},
            ],
        )
        registry.register_agent(agent)

        reviewer = DocumentReviewer(agent_registry=registry)
        report = reviewer.review_document(
            document_uuid="2024-00001",
            document_version="1.0",
            document_text="# Purpose\nThis SOP covers testing.",
            document_tag="SOP",
            user_id=1,
        )

        assert report.overall_status == ReviewStatus.FAIL
        assert len(report.findings) >= 2  # Scope and Procedure missing

    def test_review_with_explicit_agent_id(self):
        """Review can be triggered with explicit agent ID override."""
        registry = AgentRegistry()
        agent = make_review_agent(target_tag="Report")
        registry.register_agent(agent)

        reviewer = DocumentReviewer(agent_registry=registry)
        report = reviewer.review_document(
            document_uuid="2024-00002",
            document_version="1.0",
            document_text="Some content",
            document_tag="SOP",  # Different tag, but explicit agent ID
            user_id=1,
            review_agent_id=agent.id,
        )

        assert report.review_agent_id == agent.id

    def test_review_no_matching_agent_raises_error(self):
        """Review raises ValueError when no matching agent found."""
        registry = AgentRegistry()
        reviewer = DocumentReviewer(agent_registry=registry)

        with pytest.raises(ValueError, match="No review agent found"):
            reviewer.review_document(
                document_uuid="2024-00001",
                document_version="1.0",
                document_text="Content",
                document_tag="UnknownType",
                user_id=1,
            )
