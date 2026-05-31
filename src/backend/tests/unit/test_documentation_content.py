"""Unit tests for documentation content generation and validation.

Tests cover Task 7.2: Content generation (user guide structure, admin guide
structure, section content, procedure blocks, screenshot placeholders, headers,
ToC, cross-references, glossary) and content validation (_validate_content,
_validate_section_lengths, _count_sections, _count_procedures,
_count_screenshot_placeholders).

References:
    - Requirements: 1.2-1.10, 2.2-2.10, 6.1-6.8, 7.1-7.7, 8.5, 8.6
    - Design: .kiro/specs/Step_8-5_documentation-suite-user-admin-guides/design.md
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.services.documentation_content import (
    ADMIN_GUIDE_SECTIONS,
    USER_GUIDE_SECTIONS,
    CrossReferenceContext,
    assemble_admin_guide,
    assemble_document_header,
    assemble_user_guide,
)
from alcoabase.services.documentation_generator_service import (
    DocumentationGeneratorService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cross_refs_all_available() -> CrossReferenceContext:
    """CrossReferenceContext with URS and AI Guidelines available."""
    return CrossReferenceContext(
        urs_available=True,
        urs_document_uuid="2024-00001",
        urs_document_title="Enhanced User Requirement Specifications",
        ai_guidelines_available=True,
        ai_guidelines_documents=[
            {
                "title": "AI Usage Guidelines — Master",
                "uuid": "2024-00010",
                "state": "Draft",
            },
        ],
        governance_documents=[
            {
                "title": "Enhanced User Requirement Specifications",
                "uuid": "2024-00001",
                "state": "Draft",
            },
            {
                "title": "AI Usage Guidelines — Master",
                "uuid": "2024-00010",
                "state": "Draft",
            },
            {
                "title": "AlcoaBase — Comprehensive User Guide",
                "uuid": "2024-00020",
                "state": "Draft",
            },
        ],
    )


@pytest.fixture
def cross_refs_none_available() -> CrossReferenceContext:
    """CrossReferenceContext with URS and AI Guidelines unavailable."""
    return CrossReferenceContext(
        urs_available=False,
        ai_guidelines_available=False,
        governance_documents=[],
    )


@pytest.fixture
def user_guide_content(cross_refs_all_available: CrossReferenceContext) -> str:
    """Generated User Guide content with all cross-references available."""
    return assemble_user_guide(cross_refs=cross_refs_all_available, version_number=1)


@pytest.fixture
def admin_guide_content(cross_refs_all_available: CrossReferenceContext) -> str:
    """Generated Admin Guide content with all cross-references available."""
    return assemble_admin_guide(cross_refs=cross_refs_all_available, version_number=1)


@pytest.fixture
def user_guide_no_refs(cross_refs_none_available: CrossReferenceContext) -> str:
    """Generated User Guide content without cross-references."""
    return assemble_user_guide(cross_refs=cross_refs_none_available, version_number=1)


@pytest.fixture
def admin_guide_no_refs(cross_refs_none_available: CrossReferenceContext) -> str:
    """Generated Admin Guide content without cross-references."""
    return assemble_admin_guide(cross_refs=cross_refs_none_available, version_number=1)


@pytest.fixture
def service() -> DocumentationGeneratorService:
    """DocumentationGeneratorService with a mock session."""
    mock_session = AsyncMock()
    return DocumentationGeneratorService(session=mock_session)


# ---------------------------------------------------------------------------
# User Guide Structure Tests
# ---------------------------------------------------------------------------


class TestUserGuideStructure:
    """Tests for User Guide section structure and ordering."""

    EXPECTED_SECTIONS = [
        "Getting Started",
        "Document Management",
        "Template Builder",
        "Report Data Entry and PDF Extraction",
        "Workflows",
        "Training Management",
        "Electronic Signatures",
        "Search and Knowledge Base",
        "AI Agent Interaction",
        "AI Document Generator",
        "Related Governance Documents",
        "Appendices",
    ]

    def test_user_guide_has_all_12_sections_in_order(
        self, user_guide_content: str
    ) -> None:
        """User Guide contains all 12 required sections in specified order."""
        # Extract level-2 headings (## N. Title)
        headings = re.findall(r"^## \d+\.\s+(.+)$", user_guide_content, re.MULTILINE)
        assert len(headings) >= 12
        # Check order of the 12 content sections (skip Document Header and ToC)
        for expected_title in self.EXPECTED_SECTIONS:
            assert expected_title in headings, (
                f"Missing section: {expected_title}"
            )
        # Verify ordering
        indices = [headings.index(t) for t in self.EXPECTED_SECTIONS]
        assert indices == sorted(indices), "Sections are not in the expected order"

    def test_getting_started_has_prerequisites_login_navigation_quickstart(
        self, user_guide_content: str
    ) -> None:
        """Getting Started section covers prerequisites, login, navigation, quick-start."""
        # Find the Getting Started section content
        match = re.search(
            r"## \d+\.\s+Getting Started\n(.*?)(?=\n---\n|\n## \d+\.)",
            user_guide_content,
            re.DOTALL,
        )
        assert match is not None, "Getting Started section not found"
        section = match.group(1)
        assert "prerequisites" in section.lower() or "system access" in section.lower()
        assert "Logging In" in section or "login" in section.lower()
        assert "Navigating" in section or "navigation" in section.lower()
        assert "Quick-Start" in section or "quick-start" in section.lower()

    def test_document_management_covers_upload_bulk_folders_versioning_metadata(
        self, user_guide_content: str
    ) -> None:
        """Document Management covers upload, bulk, folders, versioning, metadata."""
        match = re.search(
            r"## \d+\.\s+Document Management\n(.*?)(?=\n---\n|\n## \d+\.)",
            user_guide_content,
            re.DOTALL,
        )
        assert match is not None, "Document Management section not found"
        section = match.group(1)
        assert "upload" in section.lower()
        assert "bulk" in section.lower()
        assert "folder" in section.lower()
        assert "version" in section.lower()
        assert "metadata" in section.lower()

    def test_search_section_covers_hybrid_search_rag_ai_answers(
        self, user_guide_content: str
    ) -> None:
        """Search section covers hybrid search, RAG, AI answers."""
        match = re.search(
            r"## \d+\.\s+Search and Knowledge Base\n(.*?)(?=\n---\n|\n## \d+\.)",
            user_guide_content,
            re.DOTALL,
        )
        assert match is not None, "Search and Knowledge Base section not found"
        section = match.group(1)
        assert "hybrid" in section.lower() or "lexical" in section.lower()
        assert "rag" in section.lower() or "retrieval" in section.lower()
        assert "ai" in section.lower() or "answer" in section.lower()

    def test_ai_agent_section_covers_reports_scorecards_severity_master_auditor_training(
        self, user_guide_content: str
    ) -> None:
        """AI Agent section covers reports, scorecards, severity, master auditor, training ecosystem."""
        match = re.search(
            r"## \d+\.\s+AI Agent Interaction\n(.*?)(?=\n---\n|\n## \d+\.)",
            user_guide_content,
            re.DOTALL,
        )
        assert match is not None, "AI Agent Interaction section not found"
        section = match.group(1)
        assert "report" in section.lower()
        assert "scorecard" in section.lower()
        assert "severity" in section.lower()
        assert "master auditor" in section.lower()
        assert "training" in section.lower()

    def test_user_guide_minimum_counts(self, user_guide_content: str, service: DocumentationGeneratorService) -> None:
        """User Guide has ≥10 sections and ≥25 procedures."""
        section_count = service._count_sections(user_guide_content)
        procedure_count = service._count_procedures(user_guide_content)
        assert section_count >= 10, f"Expected ≥10 sections, got {section_count}"
        assert procedure_count >= 25, f"Expected ≥25 procedures, got {procedure_count}"


# ---------------------------------------------------------------------------
# Admin Guide Structure Tests
# ---------------------------------------------------------------------------


class TestAdminGuideStructure:
    """Tests for Admin Guide section structure and ordering."""

    EXPECTED_SECTIONS = [
        "Administration Overview",
        "User Management",
        "Role-Based Access Control",
        "System Configuration",
        "AI Model Layer Management",
        "Storage and Backup",
        "Audit Trail Administration",
        "Compliance Monitoring",
        "Agent Registry Management",
        "Workflow Administration",
        "Related Governance Documents",
        "Appendices",
    ]

    def test_admin_guide_has_all_12_sections_in_order(
        self, admin_guide_content: str
    ) -> None:
        """Admin Guide contains all 12 required sections in specified order."""
        headings = re.findall(r"^## \d+\.\s+(.+)$", admin_guide_content, re.MULTILINE)
        assert len(headings) >= 12
        for expected_title in self.EXPECTED_SECTIONS:
            assert expected_title in headings, (
                f"Missing section: {expected_title}"
            )
        indices = [headings.index(t) for t in self.EXPECTED_SECTIONS]
        assert indices == sorted(indices), "Sections are not in the expected order"

    def test_user_management_covers_crud_roles_activation_password_permissions(
        self, admin_guide_content: str
    ) -> None:
        """User Management covers CRUD, roles, activation, password, permissions."""
        match = re.search(
            r"## \d+\.\s+User Management\n(.*?)(?=\n---\n|\n## \d+\.)",
            admin_guide_content,
            re.DOTALL,
        )
        assert match is not None, "User Management section not found"
        section = match.group(1)
        assert "creat" in section.lower()  # create/creating
        assert "role" in section.lower()
        assert "activat" in section.lower()  # activate/activation
        assert "password" in section.lower()
        assert "permission" in section.lower()

    def test_system_configuration_covers_ai_hardware_quotas_backup_health_services(
        self, admin_guide_content: str
    ) -> None:
        """System Configuration covers AI hardware, quotas, backup, health, services."""
        match = re.search(
            r"## \d+\.\s+System Configuration\n(.*?)(?=\n---\n|\n## \d+\.)",
            admin_guide_content,
            re.DOTALL,
        )
        assert match is not None, "System Configuration section not found"
        section = match.group(1)
        assert "hardware" in section.lower() or "gpu" in section.lower()
        assert "quota" in section.lower() or "storage" in section.lower()
        assert "backup" in section.lower()
        assert "health" in section.lower()
        assert "service" in section.lower()

    def test_ai_model_layer_covers_vllm_weights_gpu_cpu_mock_embedding_ocr_timeouts(
        self, admin_guide_content: str
    ) -> None:
        """AI Model Layer covers vLLM, weights, GPU/CPU/mock, embedding, OCR, timeouts."""
        match = re.search(
            r"## \d+\.\s+AI Model Layer Management\n(.*?)(?=\n---\n|\n## \d+\.)",
            admin_guide_content,
            re.DOTALL,
        )
        assert match is not None, "AI Model Layer Management section not found"
        section = match.group(1)
        assert "vllm" in section.lower()
        assert "weight" in section.lower()
        assert "gpu" in section.lower()
        assert "cpu" in section.lower() or "mock" in section.lower()
        assert "embedding" in section.lower()
        assert "ocr" in section.lower()
        assert "timeout" in section.lower()

    def test_agent_registry_covers_yaml_add_modify_hot_reload_audit_profiles(
        self, admin_guide_content: str
    ) -> None:
        """Agent Registry covers YAML structure, add/modify, hot-reload, audit profiles."""
        match = re.search(
            r"## \d+\.\s+Agent Registry Management\n(.*?)(?=\n---\n|\n## \d+\.)",
            admin_guide_content,
            re.DOTALL,
        )
        assert match is not None, "Agent Registry Management section not found"
        section = match.group(1)
        assert "yaml" in section.lower()
        assert "add" in section.lower() or "modify" in section.lower()
        assert "hot-reload" in section.lower() or "hot reload" in section.lower()
        assert "audit profile" in section.lower() or "audit profiles" in section.lower()

    def test_compliance_monitoring_covers_scorecards_thresholds_findings_risk_tiers(
        self, admin_guide_content: str
    ) -> None:
        """Compliance Monitoring covers scorecards, thresholds, findings, risk workflow, tiers."""
        match = re.search(
            r"## \d+\.\s+Compliance Monitoring\n(.*?)(?=\n---\n|\n## \d+\.)",
            admin_guide_content,
            re.DOTALL,
        )
        assert match is not None, "Compliance Monitoring section not found"
        section = match.group(1)
        assert "scorecard" in section.lower()
        assert "threshold" in section.lower()
        assert "finding" in section.lower()
        assert "risk" in section.lower()
        assert "tier" in section.lower()

    def test_cli_reference_lists_all_5_commands_with_syntax_and_examples(
        self, admin_guide_content: str
    ) -> None:
        """CLI Reference lists all 5 required commands with syntax and examples."""
        # Find the CLI Reference section in appendices
        match = re.search(
            r"### CLI Reference\n(.*?)(?=\n### |\Z)",
            admin_guide_content,
            re.DOTALL,
        )
        assert match is not None, "CLI Reference section not found"
        cli_section = match.group(1)
        # Check for 5 required commands
        assert "generate_urs_alc" in cli_section
        assert "generate_ai_guidelines" in cli_section
        assert "generate_documentation" in cli_section
        assert "bulk_upload" in cli_section
        assert "ensure_tables" in cli_section
        # Each should have syntax (backtick code) and example
        assert cli_section.count("`uv run python") >= 5

    def test_environment_variables_has_required_columns(
        self, admin_guide_content: str
    ) -> None:
        """Environment Variables has name, description, default, component columns."""
        match = re.search(
            r"### Environment Variables\n(.*?)(?=\n### |\Z)",
            admin_guide_content,
            re.DOTALL,
        )
        assert match is not None, "Environment Variables section not found"
        env_section = match.group(1)
        # Check table header columns
        assert "Variable" in env_section or "variable" in env_section.lower()
        assert "Description" in env_section
        assert "Default" in env_section
        assert "Component" in env_section

    def test_admin_guide_minimum_counts(self, admin_guide_content: str, service: DocumentationGeneratorService) -> None:
        """Admin Guide has ≥10 sections and ≥20 procedures."""
        section_count = service._count_sections(admin_guide_content)
        procedure_count = service._count_procedures(admin_guide_content)
        assert section_count >= 10, f"Expected ≥10 sections, got {section_count}"
        assert procedure_count >= 20, f"Expected ≥20 procedures, got {procedure_count}"


# ---------------------------------------------------------------------------
# Content Validation Tests
# ---------------------------------------------------------------------------


class TestContentValidation:
    """Tests for _validate_content and _validate_section_lengths."""

    def test_validate_content_passes_for_valid_content(
        self, service: DocumentationGeneratorService
    ) -> None:
        """validate_content passes for valid content with headings."""
        valid_content = "# Title\n\n## Section 1\n\nSome content here.\n"
        # Should not raise
        service._validate_content(valid_content, "Test Document")

    def test_validate_content_raises_for_empty_content(
        self, service: DocumentationGeneratorService
    ) -> None:
        """validate_content raises RuntimeError for empty content."""
        with pytest.raises(RuntimeError, match="empty"):
            service._validate_content("", "Test Document")

    def test_validate_content_raises_for_whitespace_only(
        self, service: DocumentationGeneratorService
    ) -> None:
        """validate_content raises RuntimeError for whitespace-only content."""
        with pytest.raises(RuntimeError, match="empty"):
            service._validate_content("   \n\n  ", "Test Document")

    def test_validate_content_raises_for_no_headings(
        self, service: DocumentationGeneratorService
    ) -> None:
        """validate_content raises RuntimeError for content without headings."""
        with pytest.raises(RuntimeError, match="no Markdown headings"):
            service._validate_content(
                "This is plain text without any headings.", "Test Document"
            )

    def test_validate_section_lengths_passes_when_all_sections_sufficient(
        self, service: DocumentationGeneratorService
    ) -> None:
        """validate_section_lengths passes when all sections ≥ 200 chars."""
        content = "# Title\n\n"
        content += "## Section One\n\n" + ("A" * 250) + "\n\n"
        content += "## Section Two\n\n" + ("B" * 300) + "\n\n"
        # Should not raise
        service._validate_section_lengths(content, "Test Document")

    def test_validate_section_lengths_raises_identifying_short_section(
        self, service: DocumentationGeneratorService
    ) -> None:
        """validate_section_lengths raises RuntimeError identifying short section and guide."""
        content = "# Title\n\n"
        content += "## Good Section\n\n" + ("A" * 250) + "\n\n"
        content += "## Short Section\n\n" + ("B" * 50) + "\n\n"
        with pytest.raises(RuntimeError, match="Short Section") as exc_info:
            service._validate_section_lengths(content, "My Guide")
        assert "My Guide" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Procedure Block Tests
# ---------------------------------------------------------------------------


class TestProcedureBlocks:
    """Tests for procedure block structure and formatting."""

    def test_procedure_blocks_have_3_to_15_steps(
        self, user_guide_content: str, admin_guide_content: str
    ) -> None:
        """Procedure blocks have 3–15 numbered steps each."""
        for content in [user_guide_content, admin_guide_content]:
            # Find each procedure block and count its steps
            procedures = re.split(r"### \d+\.\d+ Procedure:", content)
            for proc in procedures[1:]:  # Skip content before first procedure
                # Count numbered steps (lines starting with digit + period)
                steps = re.findall(r"^\d+\.\s+\*\*", proc, re.MULTILINE)
                assert 3 <= len(steps) <= 15, (
                    f"Procedure has {len(steps)} steps (expected 3-15)"
                )

    def test_procedure_steps_start_with_bold_action_verb(
        self, user_guide_content: str, admin_guide_content: str
    ) -> None:
        """Procedure block steps start with bold action verb."""
        for content in [user_guide_content, admin_guide_content]:
            # Find all numbered steps
            steps = re.findall(r"^\d+\.\s+(.+)$", content, re.MULTILINE)
            for step in steps:
                assert step.startswith("**"), (
                    f"Step does not start with bold action verb: {step[:60]}"
                )

    def test_procedure_steps_include_italic_expected_outcome(
        self, user_guide_content: str, admin_guide_content: str
    ) -> None:
        """Procedure block steps include italic expected outcome."""
        for content in [user_guide_content, admin_guide_content]:
            steps = re.findall(r"^\d+\.\s+(.+)$", content, re.MULTILINE)
            for step in steps:
                # Each step should contain italic text (expected outcome)
                assert re.search(r"\*[^*]+\*", step), (
                    f"Step missing italic expected outcome: {step[:60]}"
                )


# ---------------------------------------------------------------------------
# Screenshot Placeholder Tests
# ---------------------------------------------------------------------------


class TestScreenshotPlaceholders:
    """Tests for screenshot placeholder format."""

    def test_screenshot_placeholders_match_required_format(
        self, user_guide_content: str, admin_guide_content: str
    ) -> None:
        """Screenshot placeholders match required format with kebab-case slugs."""
        kebab_pattern = r"[a-z0-9]+(-[a-z0-9]+)*"
        placeholder_pattern = re.compile(
            rf"!\[.+?\]\(screenshots/({kebab_pattern})/({kebab_pattern})\.png\)"
        )
        for content in [user_guide_content, admin_guide_content]:
            placeholders = re.findall(
                r"!\[.*?\]\(screenshots/.*?\)", content
            )
            assert len(placeholders) > 0, "No screenshot placeholders found"
            for placeholder in placeholders:
                assert placeholder_pattern.match(placeholder), (
                    f"Placeholder does not match required format: {placeholder}"
                )


# ---------------------------------------------------------------------------
# Header Tests
# ---------------------------------------------------------------------------


class TestDocumentHeader:
    """Tests for document header content."""

    def test_header_contains_version_number_and_iso_timestamp(
        self, user_guide_content: str
    ) -> None:
        """Header contains version number and ISO 8601 timestamp."""
        # Check version number
        assert re.search(r"\|\s*\*\*Version\*\*\s*\|\s*1\s*\|", user_guide_content)
        # Check ISO 8601 timestamp (YYYY-MM-DDTHH:MM:SS+00:00)
        assert re.search(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", user_guide_content
        )

    def test_header_contains_target_audience_end_users(
        self, user_guide_content: str
    ) -> None:
        """User Guide header contains target audience 'End-Users'."""
        assert "End-Users" in user_guide_content

    def test_header_contains_target_audience_administrators(
        self, admin_guide_content: str
    ) -> None:
        """Admin Guide header contains target audience 'Administrators'."""
        assert "Administrators" in admin_guide_content


# ---------------------------------------------------------------------------
# Table of Contents Tests
# ---------------------------------------------------------------------------


class TestTableOfContents:
    """Tests for Table of Contents consistency."""

    def test_toc_entries_correspond_to_actual_headings(
        self, user_guide_content: str
    ) -> None:
        """ToC entries correspond to actual document headings."""
        # Extract ToC section
        toc_match = re.search(
            r"## Table of Contents\n(.*?)(?=\n---\n|\n## \d+\.)",
            user_guide_content,
            re.DOTALL,
        )
        assert toc_match is not None, "Table of Contents not found"
        toc = toc_match.group(1)

        # Extract ToC entries (bold section titles)
        toc_titles = re.findall(r"\*\*\d+\.\s+(.+?)\*\*", toc)
        assert len(toc_titles) >= 12

        # Extract actual level-2 headings from the document body
        actual_headings = re.findall(
            r"^## \d+\.\s+(.+)$", user_guide_content, re.MULTILINE
        )

        # Every ToC entry should have a corresponding heading
        for toc_title in toc_titles:
            assert toc_title in actual_headings, (
                f"ToC entry '{toc_title}' has no corresponding heading"
            )


# ---------------------------------------------------------------------------
# Cross-Reference Tests
# ---------------------------------------------------------------------------


class TestCrossReferences:
    """Tests for URS and AI Guidelines cross-references."""

    def test_urs_cross_references_when_available(
        self, user_guide_content: str
    ) -> None:
        """URS cross-references included when urs_available=True."""
        # Pattern: "Implements: REQ-{MODULE}-{NN}"
        assert re.search(r"Implements:\s*REQ-\w+-\d+", user_guide_content)

    def test_urs_notice_when_unavailable(self, user_guide_no_refs: str) -> None:
        """URS notice included when urs_available=False."""
        assert "URS cross-references unavailable" in user_guide_no_refs

    def test_ai_guidelines_cross_references_when_available(
        self, user_guide_content: str
    ) -> None:
        """AI Guidelines cross-references in AI sections when ai_guidelines_available=True."""
        # AI sections should reference AI Usage Guidelines
        assert "AI Usage Guidelines" in user_guide_content

    def test_ai_guidelines_notice_when_unavailable(
        self, user_guide_no_refs: str
    ) -> None:
        """AI Guidelines notice in AI sections when ai_guidelines_available=False."""
        assert "AI Usage Guidelines cross-references unavailable" in user_guide_no_refs

    def test_user_guide_references_admin_guide(
        self, user_guide_content: str
    ) -> None:
        """User Guide references Admin Guide sections (inter-guide cross-refs)."""
        assert re.search(
            r"[Aa]dmin [Gg]uide [Ss]ection", user_guide_content
        )

    def test_admin_guide_references_user_guide(
        self, admin_guide_content: str
    ) -> None:
        """Admin Guide references User Guide sections (inter-guide cross-refs)."""
        assert re.search(
            r"[Uu]ser [Gg]uide [Ss]ection", admin_guide_content
        )


# ---------------------------------------------------------------------------
# Related Governance Documents Tests
# ---------------------------------------------------------------------------


class TestRelatedGovernanceDocuments:
    """Tests for Related Governance Documents section."""

    def test_related_governance_documents_lists_all_docs(
        self, user_guide_content: str
    ) -> None:
        """Related Governance Documents section lists all ALC-GOV documents with title, UUID, state."""
        # Check the governance documents table is present
        assert "Related Governance Documents" in user_guide_content
        # Check that our test documents appear
        assert "2024-00001" in user_guide_content
        assert "2024-00010" in user_guide_content
        assert "Enhanced User Requirement Specifications" in user_guide_content


# ---------------------------------------------------------------------------
# Glossary Tests
# ---------------------------------------------------------------------------


class TestGlossary:
    """Tests for glossary appendix presence."""

    def test_glossary_present_in_user_guide(self, user_guide_content: str) -> None:
        """Glossary appendix present in User Guide."""
        assert "### Glossary" in user_guide_content

    def test_glossary_present_in_admin_guide(self, admin_guide_content: str) -> None:
        """Glossary appendix present in Admin Guide."""
        assert "### Glossary" in admin_guide_content


# ---------------------------------------------------------------------------
# Counting Method Tests
# ---------------------------------------------------------------------------


class TestCountingMethods:
    """Tests for _count_sections, _count_procedures, _count_screenshot_placeholders."""

    def test_count_sections_returns_correct_level2_heading_count(
        self, service: DocumentationGeneratorService
    ) -> None:
        """_count_sections returns correct level-2 heading count."""
        content = "# Title\n\n## Section 1\n\nText\n\n## Section 2\n\nText\n\n## Section 3\n\nText\n"
        assert service._count_sections(content) == 3

    def test_count_procedures_returns_correct_procedure_block_count(
        self, service: DocumentationGeneratorService
    ) -> None:
        """_count_procedures returns correct Procedure_Block count."""
        content = (
            "## Section\n\n"
            "### 1.1 Procedure: First Task\n\n1. Step one\n\n"
            "### 1.2 Procedure: Second Task\n\n1. Step one\n\n"
            "### Not a Procedure\n\nSome text\n\n"
            "### 2.1 Procedure: Third Task\n\n1. Step one\n"
        )
        assert service._count_procedures(content) == 3

    def test_count_screenshot_placeholders_returns_correct_count(
        self, service: DocumentationGeneratorService
    ) -> None:
        """_count_screenshot_placeholders returns correct count."""
        content = (
            "Some text\n\n"
            "![Alt text](screenshots/section-one/action-one.png)\n\n"
            "More text\n\n"
            "![Another](screenshots/section-two/action-two.png)\n\n"
            "![Third](screenshots/section-three/action-three.png)\n"
        )
        assert service._count_screenshot_placeholders(content) == 3
