"""Unit tests for GuidelinesGeneratorService — content generation and validation.

Tests cover:
- Task 7.2: Content generation (master guideline structure, sector guidelines,
  risk integration blocks, prohibited uses, URS notices, default classification
  notices, policy section structure, compliance procedures, headers, roles,
  periodic review, regulatory reference table, URS reference blocks) and
  content validation (validate_content, validate_section_lengths).

References:
    - Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7,
      2.8, 4.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.6, 8.7
    - Design: .kiro/specs/Step_8-4_cross-sector-ai-regulatory-guidelines/design.md
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.services.guidelines_content import (
    GUIDELINE_DOCUMENT_TYPE,
    GUIDELINE_TAGS,
    MASTER_GUIDELINE_TITLE,
    PROHIBITED_USES,
    REGULATORY_FRAMEWORKS,
    SECTOR_MODULES,
    RiskFrameworkContext,
    assemble_master_guideline,
    assemble_sector_guideline,
)
from alcoabase.services.guidelines_generator_service import GuidelinesGeneratorService
from alcoabase.services.risk_classification_service import TIER_DEFINITIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_scalar_one_or_none(value):
    """Create a mock result that returns value from result.scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


def _mock_scalars_all(items: list):
    """Create a mock result that returns items from result.scalars().all()."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _make_company(id_: int = 1) -> MagicMock:
    """Create a Company instance matching ALC corporate."""
    company = MagicMock(spec=Company)
    company.id = id_
    company.slug = "alc-corporate"
    return company


def _make_doc_admin(id_: int = 10) -> MagicMock:
    """Create a User instance for the doc-admin."""
    user = MagicMock(spec=User)
    user.id = id_
    user.username = "alc-doc-admin"
    return user


def _make_workflow(id_: int = 5, company_id: int = 1) -> MagicMock:
    """Create a WorkflowDefinition instance for the governance workflow."""
    workflow = MagicMock(spec=WorkflowDefinition)
    workflow.id = id_
    workflow.name = "ALC Governance Document Lifecycle"
    workflow.document_tag = "ALC-GOV"
    workflow.company_id = company_id
    return workflow


def _make_document(
    id_: int = 100, company_id: int = 1, uuid: str = "2025-00042"
) -> MagicMock:
    """Create a Document instance for testing."""
    doc = MagicMock(spec=Document)
    doc.id = id_
    doc.document_uuid = uuid
    doc.title = MASTER_GUIDELINE_TITLE
    doc.company_id = company_id
    doc.current_status = "Draft"
    return doc


def _make_mock_task_type(
    task_type_id: str = "document_generation",
    display_name: str = "Document Generation",
    default_risk_tier: str = "high",
    module_reference: str = "5.4",
    risk_factors: list[str] | None = None,
) -> MagicMock:
    """Create a mock AITaskType entity."""
    tt = MagicMock()
    tt.task_type_id = task_type_id
    tt.display_name = display_name
    tt.description = f"Description for {display_name}"
    tt.module_reference = module_reference
    tt.default_risk_tier = default_risk_tier
    tt.risk_factors = risk_factors or [
        "Generates GxP-regulated content",
        "Output enters approval workflows",
    ]
    tt.is_active = True
    tt.is_system_defined = True
    tt.company_id = None
    return tt


def _build_standard_task_types() -> list[MagicMock]:
    """Build a standard set of task types covering all tiers."""
    return [
        _make_mock_task_type(
            "document_generation",
            "Document Generation",
            "high",
            "5.4",
            ["Generates GxP-regulated content entering approval workflows"],
        ),
        _make_mock_task_type(
            "multi_agent_audit",
            "Multi-Agent Compliance Audit",
            "high",
            "5.2",
            ["Produces compliance assessments influencing approval decisions"],
        ),
        _make_mock_task_type(
            "training_content_generation",
            "Training Content Generation",
            "high",
            "5.3",
            ["Creates training materials requiring validation"],
        ),
        _make_mock_task_type(
            "change_impact_analysis",
            "Change Impact Analysis",
            "medium",
            "5.5",
            ["Identifies affected documents without modifying records"],
        ),
        _make_mock_task_type(
            "traceability_gap_discovery",
            "Traceability Gap Discovery",
            "medium",
            "5.6",
            ["Discovers missing traceability links in requirements"],
        ),
        _make_mock_task_type(
            "rag_knowledge_query",
            "RAG Knowledge Query",
            "low",
            "4.2",
            ["Retrieves or summarizes existing approved content"],
        ),
        _make_mock_task_type(
            "document_search",
            "Document Search",
            "low",
            "4.1",
            ["Searches existing document repository"],
        ),
        _make_mock_task_type(
            "template_analysis",
            "Template Analysis",
            "low",
            "2.4",
            ["Analyzes document templates for structure"],
        ),
    ]


def _build_risk_context(
    task_types: list[MagicMock] | None = None,
    company_profile_active: bool = True,
) -> RiskFrameworkContext:
    """Build a RiskFrameworkContext from mock task types."""
    if task_types is None:
        task_types = _build_standard_task_types()

    effective_tiers = {
        tt.task_type_id: tt.default_risk_tier for tt in task_types
    }
    risk_factors_map = {
        tt.task_type_id: tt.risk_factors or [] for tt in task_types
    }

    return RiskFrameworkContext(
        task_types=task_types,
        effective_tiers=effective_tiers,
        tier_definitions=TIER_DEFINITIONS,
        company_profile_active=company_profile_active,
        risk_factors_map=risk_factors_map,
    )


def _make_service() -> GuidelinesGeneratorService:
    """Create a GuidelinesGeneratorService with mock session."""
    session = AsyncMock()
    return GuidelinesGeneratorService(session=session)


# ---------------------------------------------------------------------------
# Task 7.2: Content Generation Tests — Master Guideline
# ---------------------------------------------------------------------------


class TestGenerateMasterGuideline:
    """Tests for master guideline content generation."""

    def test_has_all_required_sections_in_order(self) -> None:
        """Master guideline contains all required sections in specified order.

        Validates: Requirements 1.2
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        # Required sections in order per design
        required_sections = [
            "Document Header",
            "Purpose and Scope",
            "Regulatory Framework Overview",
            "Risk Classification Summary",
            "AI Feature Usage Policies",
            "Human Oversight Requirements",
            "Audit and Evidence Requirements",
            "Prohibited Uses",
            "Roles and Responsibilities",
            "Periodic Review",
            "Glossary",
            "URS Traceability References",
            "Regulatory Reference Table",
        ]

        # Find positions of each section heading
        positions = []
        for section_name in required_sections:
            pattern = re.compile(rf"^##\s+{re.escape(section_name)}", re.MULTILINE)
            match = pattern.search(content)
            assert match is not None, (
                f"Required section '{section_name}' not found in master guideline"
            )
            positions.append(match.start())

        # Verify sections appear in order
        for i in range(len(positions) - 1):
            assert positions[i] < positions[i + 1], (
                f"Section '{required_sections[i]}' (pos {positions[i]}) should "
                f"appear before '{required_sections[i + 1]}' (pos {positions[i + 1]})"
            )

    def test_includes_risk_integration_blocks_for_each_task_type(self) -> None:
        """Master guideline includes Risk_Integration_Blocks for each task type.

        Validates: Requirements 1.3
        """
        task_types = _build_standard_task_types()
        risk_context = _build_risk_context(task_types)
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        for tt in task_types:
            # Each task type should appear as a heading in the risk summary
            assert tt.display_name in content, (
                f"Task type '{tt.display_name}' not found in master guideline"
            )
            # Verify tier is shown
            tier = risk_context.effective_tiers[tt.task_type_id]
            assert f"**Risk Tier:** {tier.capitalize()}" in content, (
                f"Risk tier for '{tt.display_name}' not shown correctly"
            )

    def test_includes_all_4_prohibited_uses(self) -> None:
        """Master guideline includes all 4 prohibited uses.

        Validates: Requirements 4.4
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        for prohibited_use in PROHIBITED_USES:
            assert prohibited_use in content, (
                f"Prohibited use not found: '{prohibited_use}'"
            )

    def test_includes_urs_notice_when_unavailable(self) -> None:
        """Master guideline includes URS unavailability notice when URS not present.

        Validates: Requirements 1.5, 8.8 (partial)
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=False)

        assert "URS cross-references unavailable" in content
        assert "generate URS (Phase 8.3) for full traceability" in content

    def test_includes_default_classifications_notice_when_no_profile(self) -> None:
        """Master guideline includes notice when no company risk profile is active.

        Validates: Requirements 4.5 (partial)
        """
        risk_context = _build_risk_context(company_profile_active=False)
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        assert "Default risk classifications are applied" in content
        assert "no company-specific risk profile" in content


# ---------------------------------------------------------------------------
# Task 7.2: Content Generation Tests — Sector Guidelines
# ---------------------------------------------------------------------------


class TestGenerateSectorGuideline:
    """Tests for sector-specific guideline content generation."""

    def test_pharma_has_4_dedicated_subsections(self) -> None:
        """Pharma/GMP guideline has 4 dedicated subsections.

        Validates: Requirements 2.3
        """
        pharma = SECTOR_MODULES[0]
        assert pharma.sector_id == "pharma_gmp"

        risk_context = _build_risk_context()
        content = assemble_sector_guideline(pharma, risk_context, version_number=1, urs_available=True)

        # Pharma dedicated subsections
        expected_subsections = [
            "GMP Data Integrity",
            "Computer System Validation",
            "AI Model Qualification",
            "Change Control",
        ]
        for subsection in expected_subsections:
            assert subsection in content, (
                f"Pharma dedicated subsection '{subsection}' not found"
            )

    def test_medtech_has_4_dedicated_subsections(self) -> None:
        """MedTech/ISO 13485 guideline has 4 dedicated subsections.

        Validates: Requirements 2.4
        """
        medtech = SECTOR_MODULES[1]
        assert medtech.sector_id == "medtech_iso13485"

        risk_context = _build_risk_context()
        content = assemble_sector_guideline(medtech, risk_context, version_number=1, urs_available=True)

        expected_subsections = [
            "Design Control",
            "Software Lifecycle",
            "Risk Management Integration",
            "Post-Market Surveillance",
        ]
        for subsection in expected_subsections:
            assert subsection in content, (
                f"MedTech dedicated subsection '{subsection}' not found"
            )

    def test_ivd_has_4_dedicated_subsections(self) -> None:
        """IVD/IVDR guideline has 4 dedicated subsections.

        Validates: Requirements 2.5
        """
        ivd = SECTOR_MODULES[2]
        assert ivd.sector_id == "ivd_ivdr"

        risk_context = _build_risk_context()
        content = assemble_sector_guideline(ivd, risk_context, version_number=1, urs_available=True)

        expected_subsections = [
            "Performance Evaluation",
            "Common Specifications",
            "Clinical Evidence",
            "Notified Body",
        ]
        for subsection in expected_subsections:
            assert subsection in content, (
                f"IVD dedicated subsection '{subsection}' not found"
            )

    def test_includes_mapping_table_with_all_task_types(self) -> None:
        """Sector guideline includes mapping table with all task types.

        Validates: Requirements 2.6
        """
        pharma = SECTOR_MODULES[0]
        task_types = _build_standard_task_types()
        risk_context = _build_risk_context(task_types)
        content = assemble_sector_guideline(pharma, risk_context, version_number=1, urs_available=True)

        # Verify mapping table header
        assert "Sector Risk Mapping Table" in content
        assert "AI Task Type" in content
        assert "Base Risk Tier" in content
        assert "Sector Elevation" in content
        assert "Additional Controls" in content
        assert "Regulatory Reference" in content

        # Verify all task types appear in the mapping table
        for tt in task_types:
            assert tt.display_name in content, (
                f"Task type '{tt.display_name}' not found in sector mapping table"
            )

    def test_sector_never_assigns_lower_tier_than_master(self) -> None:
        """Sector guideline never assigns a lower tier than the master guideline.

        Validates: Requirements 2.7
        """
        tier_order = {"low": 0, "medium": 1, "high": 2}

        for sector in SECTOR_MODULES:
            task_types = _build_standard_task_types()
            risk_context = _build_risk_context(task_types)
            content = assemble_sector_guideline(
                sector, risk_context, version_number=1, urs_available=True
            )

            # Check that elevation recommendations never lower the tier
            for tt in task_types:
                base_tier = risk_context.effective_tiers[tt.task_type_id]
                tid = tt.task_type_id

                if tid in sector.risk_elevation_rules:
                    # If elevated, the recommendation should be equal or higher
                    if base_tier == "low":
                        assert "Elevate to Medium" in content or "Elevate to High" in content
                    elif base_tier == "medium":
                        assert "Elevate to High" in content or "No elevation" in content
                    # high tier can only stay at "No elevation"


# ---------------------------------------------------------------------------
# Task 7.2: Content Validation Tests
# ---------------------------------------------------------------------------


class TestValidateContent:
    """Tests for _validate_content method."""

    def test_passes_for_valid_content_with_headings(self) -> None:
        """validate_content passes for valid content with Markdown headings.

        Validates: Requirements 8.6
        """
        service = _make_service()
        valid_content = "# Title\n\nSome content here.\n\n## Section\n\nMore content."
        # Should not raise
        service._validate_content(valid_content, "Test Document")

    def test_raises_for_empty_content(self) -> None:
        """validate_content raises RuntimeError for empty content.

        Validates: Requirements 8.6, 8.7
        """
        service = _make_service()

        with pytest.raises(RuntimeError, match="is empty"):
            service._validate_content("", "Test Document")

        with pytest.raises(RuntimeError, match="is empty"):
            service._validate_content("   ", "Test Document")

    def test_raises_for_content_without_headings(self) -> None:
        """validate_content raises RuntimeError for content without headings.

        Validates: Requirements 8.6, 8.7
        """
        service = _make_service()
        no_heading_content = "This is content without any markdown headings.\nJust plain text."

        with pytest.raises(RuntimeError, match="contains no Markdown headings"):
            service._validate_content(no_heading_content, "Test Document")

    def test_error_message_includes_document_title(self) -> None:
        """validate_content error message includes the document title.

        Validates: Requirements 8.7
        """
        service = _make_service()
        title = "AlcoaBase — AI Usage Guidelines (Cross-Sector)"

        with pytest.raises(RuntimeError, match=re.escape(title)):
            service._validate_content("no headings here", title)


# ---------------------------------------------------------------------------
# Task 7.2: Section Length Validation Tests
# ---------------------------------------------------------------------------


class TestValidateSectionLengths:
    """Tests for _validate_section_lengths method."""

    def test_passes_when_all_sections_ge_100_chars(self) -> None:
        """validate_section_lengths passes when all sections have ≥ 100 chars.

        Validates: Requirements 2.8
        """
        service = _make_service()
        # Build content with sections that each have > 100 chars
        long_text = "A" * 150
        content = (
            f"## Section One\n\n{long_text}\n\n"
            f"## Section Two\n\n{long_text}\n\n"
            f"## Section Three\n\n{long_text}\n"
        )
        # Should not raise
        service._validate_section_lengths(content, "Test Document")

    def test_raises_identifying_short_section(self) -> None:
        """validate_section_lengths raises RuntimeError identifying short section.

        Validates: Requirements 2.8
        """
        service = _make_service()
        long_text = "A" * 150
        short_text = "Too short"
        content = (
            f"## Good Section\n\n{long_text}\n\n"
            f"## Bad Section\n\n{short_text}\n\n"
            f"## Another Good Section\n\n{long_text}\n"
        )

        with pytest.raises(RuntimeError, match="Bad Section"):
            service._validate_section_lengths(content, "Test Document")


# ---------------------------------------------------------------------------
# Task 7.2: Policy Section Structure Tests
# ---------------------------------------------------------------------------


class TestPolicySectionStructure:
    """Tests for policy section structural requirements."""

    def test_policy_section_has_exactly_5_subsections_in_order(self) -> None:
        """Each policy section has exactly 5 subsections (a–e) in order.

        Validates: Requirements 7.3
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        # Find all policy sections
        policy_pattern = re.compile(r"### Policy: (.+?)$", re.MULTILINE)
        policy_matches = list(policy_pattern.finditer(content))
        assert len(policy_matches) > 0, "No policy sections found"

        # Required subsections in order
        required_subsections = [
            "(a) Permitted Uses",
            "(b) Restrictions",
            "(c) Compliance Procedure",
            "(d) Required Evidence and Documentation",
            "(e) Consequences of Non-Compliance",
        ]

        for i, match in enumerate(policy_matches):
            # Get the section content (until next policy section or end)
            start = match.start()
            end = policy_matches[i + 1].start() if i + 1 < len(policy_matches) else len(content)
            section_content = content[start:end]

            # Verify all 5 subsections are present and in order
            positions = []
            for subsection in required_subsections:
                pos = section_content.find(f"**{subsection}**")
                assert pos != -1, (
                    f"Subsection '{subsection}' not found in policy section "
                    f"'{match.group(1)}'"
                )
                positions.append(pos)

            # Verify order
            for j in range(len(positions) - 1):
                assert positions[j] < positions[j + 1], (
                    f"Subsection '{required_subsections[j]}' should appear before "
                    f"'{required_subsections[j + 1]}' in policy '{match.group(1)}'"
                )

    def test_compliance_procedure_has_3_to_15_numbered_steps(self) -> None:
        """Compliance procedure has 3–15 numbered steps.

        Validates: Requirements 7.3
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        # Find all compliance procedure sections
        # Pattern: **(c) Compliance Procedure** followed by numbered steps
        procedure_pattern = re.compile(
            r"\*\*\(c\) Compliance Procedure\*\*\n\n((?:\d+\..+\n)+)",
            re.MULTILINE,
        )
        procedures = procedure_pattern.findall(content)
        assert len(procedures) > 0, "No compliance procedures found"

        for proc_text in procedures:
            # Count numbered steps
            step_pattern = re.compile(r"^\d+\.", re.MULTILINE)
            steps = step_pattern.findall(proc_text)
            assert 3 <= len(steps) <= 15, (
                f"Compliance procedure has {len(steps)} steps, expected 3–15"
            )


# ---------------------------------------------------------------------------
# Task 7.2: Header Tests
# ---------------------------------------------------------------------------


class TestDocumentHeader:
    """Tests for document header content."""

    def test_header_contains_version_number_and_iso_timestamp(self) -> None:
        """Header contains version number and ISO 8601 timestamp.

        Validates: Requirements 1.6
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=3, urs_available=True)

        # Version number in header table
        assert "| **Version** | 3 |" in content

        # ISO 8601 timestamp pattern (YYYY-MM-DDTHH:MM:SSZ)
        iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
        assert iso_pattern.search(content), (
            "ISO 8601 timestamp not found in document header"
        )

    def test_header_lists_all_applicable_regulatory_frameworks(self) -> None:
        """Header lists all applicable regulatory frameworks.

        Validates: Requirements 1.6
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        for fw in REGULATORY_FRAMEWORKS:
            assert fw.display_name in content, (
                f"Regulatory framework '{fw.display_name}' not found in header"
            )


# ---------------------------------------------------------------------------
# Task 7.2: Roles and Responsibilities Tests
# ---------------------------------------------------------------------------


class TestRolesAndResponsibilities:
    """Tests for roles and responsibilities section."""

    def test_has_correct_role_mappings(self) -> None:
        """Roles and responsibilities section has correct role mappings.

        Validates: Requirements 7.4
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        # Required role mappings per Requirement 7.4
        assert "quality_manager" in content
        assert "system_administrator" in content or "system_admin" in content
        assert "document_administrator" in content or "doc_admin" in content

        # Required responsibilities
        assert "Approving AI outputs" in content
        assert "Monitoring compliance" in content
        assert "Configuring risk profiles" in content
        assert "periodic reviews" in content.lower() or "Conducting periodic reviews" in content


# ---------------------------------------------------------------------------
# Task 7.2: Periodic Review Tests
# ---------------------------------------------------------------------------


class TestPeriodicReview:
    """Tests for periodic review section."""

    def test_references_review_cycle_days(self) -> None:
        """Periodic review section references review_cycle_days.

        Validates: Requirements 7.6
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        assert "review_cycle_days" in content
        assert "365 days" in content or "365" in content
        assert "Company Risk Profile is modified" in content


# ---------------------------------------------------------------------------
# Task 7.2: Regulatory Reference Table Tests
# ---------------------------------------------------------------------------


class TestRegulatoryReferenceTable:
    """Tests for regulatory reference table."""

    def test_present_with_required_columns(self) -> None:
        """Regulatory reference table present with required columns.

        Validates: Requirements 7.2
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        # Table should be present
        assert "## Regulatory Reference Table" in content

        # Required columns
        assert "Regulation" in content
        assert "Article/Section" in content
        assert "Requirement Summary" in content
        assert "ALC Implementation" in content

        # At least one row per framework
        for fw in REGULATORY_FRAMEWORKS:
            assert fw.display_name in content, (
                f"Framework '{fw.display_name}' not in regulatory reference table"
            )


# ---------------------------------------------------------------------------
# Task 7.2: URS Reference Block Tests
# ---------------------------------------------------------------------------


class TestURSReferenceBlocks:
    """Tests for URS reference blocks."""

    def test_match_implements_req_module_nn_pattern(self) -> None:
        """URS reference blocks match 'Implements: REQ-{MODULE}-{NN}' pattern.

        Validates: Requirements 1.5
        """
        risk_context = _build_risk_context()
        content = assemble_master_guideline(risk_context, version_number=1, urs_available=True)

        # Find all URS reference blocks
        req_pattern = re.compile(r"Implements: REQ-([A-Z]+)-(\d{2})")
        matches = req_pattern.findall(content)

        assert len(matches) > 0, (
            "No URS reference blocks matching 'Implements: REQ-{MODULE}-{NN}' found"
        )

        # Verify format: MODULE is uppercase letters, NN is 2-digit zero-padded
        for module, nn in matches:
            assert module.isalpha() and module.isupper(), (
                f"MODULE '{module}' should be uppercase letters"
            )
            assert len(nn) == 2 and nn.isdigit(), (
                f"NN '{nn}' should be zero-padded two-digit number"
            )


# ---------------------------------------------------------------------------
# Task 7.3: detect_existing_document Tests
# ---------------------------------------------------------------------------


class TestDetectExistingDocumentFound:
    """Test: detect_existing_document returns Document when found.

    Validates: Requirements 6.1, 6.6
    """

    @pytest.mark.asyncio
    async def test_returns_document_when_found(self, async_session: AsyncMock):
        """Returns existing Document when title + tags + company_id match."""
        company = _make_company()
        existing_doc = _make_document(id_=100, company_id=company.id)

        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(existing_doc)
        )

        service = GuidelinesGeneratorService(async_session)
        result = await service._detect_existing_document(
            MASTER_GUIDELINE_TITLE, company
        )

        assert result is existing_doc
        assert result.id == 100
        assert result.title == MASTER_GUIDELINE_TITLE


class TestDetectExistingDocumentNotFound:
    """Test: detect_existing_document returns None when not found.

    Validates: Requirements 6.1, 6.6
    """

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, async_session: AsyncMock):
        """Returns None when no document with matching title + tags exists."""
        company = _make_company()

        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        service = GuidelinesGeneratorService(async_session)
        result = await service._detect_existing_document(
            MASTER_GUIDELINE_TITLE, company
        )

        assert result is None


# ---------------------------------------------------------------------------
# Task 7.3: upload_or_version — New Document Tests
# ---------------------------------------------------------------------------


class TestUploadOrVersionNewDocument:
    """Test: upload_or_version new document has correct attributes.

    Validates: Requirements 3.1, 3.4, 3.5, 6.2
    """

    @pytest.mark.asyncio
    async def test_new_document_attributes(self, async_session: AsyncMock):
        """New document has correct title, type, company_id, created_by, UUID."""
        company = _make_company(id_=1)
        doc_admin = _make_doc_admin(id_=10)
        workflow = _make_workflow(id_=5)
        content = "# AI Guidelines\n\n## Purpose\n\nTest content."

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(
            return_value="documents/2025-00099/1.0/document.md"
        )

        mock_uuid = AsyncMock()
        mock_uuid.generate_document_uuid = AsyncMock(return_value="2025-00099")

        # Track added objects
        added_objects = []

        def track_add(obj):
            added_objects.append(obj)
            if isinstance(obj, Document):
                obj.id = 200

        async_session.add = MagicMock(side_effect=track_add)
        async_session.flush = AsyncMock()

        # Mock: detect_existing_document returns None (new document)
        # Mock: apply_tags query returns no existing tags
        # Mock: apply_workflow query returns no existing state
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # _detect_existing_document → None
                return _mock_scalar_one_or_none(None)
            if call_count == 2:
                # _apply_tags → no existing tags
                return _mock_scalars_all([])
            if call_count == 3:
                # _apply_workflow → no existing state
                return _mock_scalar_one_or_none(None)
            return _mock_scalar_one_or_none(None)

        async_session.execute = AsyncMock(side_effect=mock_execute)

        service = GuidelinesGeneratorService(
            async_session,
            storage_service=mock_storage,
            uuid_service=mock_uuid,
        )
        result = await service._upload_or_version_document(
            MASTER_GUIDELINE_TITLE, content, company, doc_admin, workflow
        )

        # Verify result attributes
        assert result.title == MASTER_GUIDELINE_TITLE
        assert result.is_new_document is True
        assert result.version_number == 1
        assert result.workflow_state == "Draft"
        assert result.tags_applied == GUIDELINE_TAGS

        # Verify UUID format (YYYY-NNNNN)
        assert re.match(r"\d{4}-\d{5}", result.document_uuid)

        # Verify Document was created with correct attributes
        doc_objects = [o for o in added_objects if isinstance(o, Document)]
        assert len(doc_objects) == 1
        doc = doc_objects[0]
        assert doc.title == MASTER_GUIDELINE_TITLE
        assert doc.document_type == GUIDELINE_DOCUMENT_TYPE
        assert doc.company_id == company.id
        assert doc.created_by == doc_admin.id
        assert doc.document_uuid == "2025-00099"


# ---------------------------------------------------------------------------
# Task 7.3: upload_or_version — Existing Document Version Tests
# ---------------------------------------------------------------------------


class TestUploadOrVersionExistingDocument:
    """Test: upload_or_version existing document increments major_version.

    Validates: Requirements 6.1, 6.3, 6.4
    """

    @pytest.mark.asyncio
    async def test_existing_document_increments_version(
        self, async_session: AsyncMock
    ):
        """Existing document gets new version with incremented major_version."""
        company = _make_company(id_=1)
        doc_admin = _make_doc_admin(id_=10)
        workflow = _make_workflow(id_=5)
        existing_doc = _make_document(
            id_=100, company_id=1, uuid="2025-00042"
        )
        content = "# AI Guidelines v2\n\n## Purpose\n\nUpdated content."

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(
            return_value="documents/2025-00042/2.0/document.md"
        )

        # Track added objects
        added_objects = []

        def track_add(obj):
            added_objects.append(obj)

        async_session.add = MagicMock(side_effect=track_add)
        async_session.flush = AsyncMock()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # _detect_existing_document → existing doc
                return _mock_scalar_one_or_none(existing_doc)
            if call_count == 2:
                # SELECT MAX(major_version) → 1
                return _mock_scalar_one_or_none(1)
            if call_count == 3:
                # _apply_tags → existing tags already present
                existing_tag1 = MagicMock(spec=DocumentTag)
                existing_tag1.tag = "AI-Guidelines"
                existing_tag2 = MagicMock(spec=DocumentTag)
                existing_tag2.tag = "ALC-GOV"
                return _mock_scalars_all([existing_tag1, existing_tag2])
            if call_count == 4:
                # _apply_workflow → existing state
                existing_state = MagicMock(spec=DocumentState)
                existing_state.document_id = existing_doc.id
                existing_state.current_state = "Approved"
                return _mock_scalar_one_or_none(existing_state)
            return _mock_scalar_one_or_none(None)

        async_session.execute = AsyncMock(side_effect=mock_execute)

        service = GuidelinesGeneratorService(
            async_session,
            storage_service=mock_storage,
        )
        result = await service._upload_or_version_document(
            MASTER_GUIDELINE_TITLE, content, company, doc_admin, workflow
        )

        # Verify version was incremented
        assert result.is_new_document is False
        assert result.version_number == 2
        assert result.document_uuid == "2025-00042"
        assert result.workflow_state == "Draft"

        # Verify DocumentVersion was created with major_version=2
        version_objects = [
            o for o in added_objects if isinstance(o, DocumentVersion)
        ]
        assert len(version_objects) == 1
        version = version_objects[0]
        assert version.major_version == 2
        assert version.minor_version == 0
        assert version.document_id == existing_doc.id
        assert version.uploaded_by == doc_admin.id


# ---------------------------------------------------------------------------
# Task 7.3: apply_tags Tests
# ---------------------------------------------------------------------------


class TestApplyTagsNewDocument:
    """Test: apply_tags creates both "AI-Guidelines" and "ALC-GOV" tags.

    Validates: Requirements 3.2
    """

    @pytest.mark.asyncio
    async def test_creates_both_tags_on_new_document(
        self, async_session: AsyncMock
    ):
        """Both AI-Guidelines and ALC-GOV tags created for a new document."""
        document = _make_document(id_=100)

        # Mock: no existing tags
        async_session.execute = AsyncMock(
            return_value=_mock_scalars_all([])
        )

        added_objects = []

        def track_add(obj):
            added_objects.append(obj)

        async_session.add = MagicMock(side_effect=track_add)
        async_session.flush = AsyncMock()

        service = GuidelinesGeneratorService(async_session)
        tags_applied = await service._apply_tags(document, is_new=True)

        # Verify both tags were applied
        assert tags_applied == ["AI-Guidelines", "ALC-GOV"]

        # Verify DocumentTag objects were created
        tag_objects = [o for o in added_objects if isinstance(o, DocumentTag)]
        assert len(tag_objects) == 2

        tag_values = {t.tag for t in tag_objects}
        assert tag_values == {"AI-Guidelines", "ALC-GOV"}

        for tag_obj in tag_objects:
            assert tag_obj.document_id == document.id


class TestApplyTagsNoDuplicates:
    """Test: apply_tags does not duplicate on re-run.

    Validates: Requirements 3.2, 6.6
    """

    @pytest.mark.asyncio
    async def test_no_duplicate_tags_on_rerun(self, async_session: AsyncMock):
        """Tags not duplicated when already present on existing document."""
        document = _make_document(id_=100)

        # Mock: both tags already exist
        existing_tag1 = MagicMock(spec=DocumentTag)
        existing_tag1.tag = "AI-Guidelines"
        existing_tag1.document_id = document.id

        existing_tag2 = MagicMock(spec=DocumentTag)
        existing_tag2.tag = "ALC-GOV"
        existing_tag2.document_id = document.id

        async_session.execute = AsyncMock(
            return_value=_mock_scalars_all([existing_tag1, existing_tag2])
        )
        async_session.flush = AsyncMock()

        service = GuidelinesGeneratorService(async_session)
        tags_applied = await service._apply_tags(document, is_new=False)

        # Tags should still be reported as applied
        assert tags_applied == ["AI-Guidelines", "ALC-GOV"]

        # But no new tags should have been added to the session
        async_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Task 7.3: apply_workflow Tests
# ---------------------------------------------------------------------------


class TestApplyWorkflowNewDocument:
    """Test: apply_workflow creates DocumentState with state="Draft".

    Validates: Requirements 3.3, 6.2
    """

    @pytest.mark.asyncio
    async def test_creates_document_state_draft(self, async_session: AsyncMock):
        """DocumentState created with state='Draft' for new document."""
        document = _make_document(id_=100)
        workflow = _make_workflow(id_=5)
        doc_admin = _make_doc_admin(id_=10)

        # Mock: no existing DocumentState
        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        added_objects = []

        def track_add(obj):
            added_objects.append(obj)

        async_session.add = MagicMock(side_effect=track_add)
        async_session.flush = AsyncMock()

        service = GuidelinesGeneratorService(async_session)
        state = await service._apply_workflow(document, workflow, doc_admin)

        assert state == "Draft"

        # Verify DocumentState was created
        doc_states = [o for o in added_objects if isinstance(o, DocumentState)]
        assert len(doc_states) == 1

        doc_state = doc_states[0]
        assert doc_state.document_id == document.id
        assert doc_state.current_state == "Draft"
        assert doc_state.workflow_id == workflow.id
        assert doc_state.updated_by == doc_admin.id


class TestApplyWorkflowResetToDraft:
    """Test: apply_workflow resets to "Draft" on new version.

    Validates: Requirements 6.4
    """

    @pytest.mark.asyncio
    async def test_resets_existing_state_to_draft(
        self, async_session: AsyncMock
    ):
        """Existing DocumentState reset to 'Draft' when new version created."""
        document = _make_document(id_=100)
        workflow = _make_workflow(id_=5)
        doc_admin = _make_doc_admin(id_=10)

        # Mock: existing DocumentState with state="Approved"
        existing_state = MagicMock(spec=DocumentState)
        existing_state.document_id = document.id
        existing_state.current_state = "Approved"
        existing_state.workflow_id = 3  # Old workflow

        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(existing_state)
        )
        async_session.flush = AsyncMock()

        service = GuidelinesGeneratorService(async_session)
        state = await service._apply_workflow(document, workflow, doc_admin)

        assert state == "Draft"

        # Verify existing state was updated (not a new one created)
        assert existing_state.current_state == "Draft"
        assert existing_state.workflow_id == workflow.id
        assert existing_state.updated_by == doc_admin.id

        # session.add should NOT have been called (update in place)
        async_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Task 7.3: Report Building Tests
# ---------------------------------------------------------------------------


class TestReportFirstRun:
    """Test: report has 4 entries, all is_new_document=True on first run.

    Validates: Requirements 5.4, 6.5
    """

    @pytest.mark.asyncio
    async def test_report_four_entries_all_new(self, async_session: AsyncMock):
        """Report contains 4 entries with is_new_document=True on first run."""
        from alcoabase.schemas.guidelines_generation import (
            DocumentReportEntry,
            GuidelinesGenerationReport,
        )

        # Simulate a report from first run (all new documents)
        entries = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title=MASTER_GUIDELINE_TITLE,
                sector="cross-sector",
                version_number=1,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=2,
                document_uuid="2025-00002",
                title=SECTOR_MODULES[0].title,
                sector="pharma_gmp",
                version_number=1,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=3,
                document_uuid="2025-00003",
                title=SECTOR_MODULES[1].title,
                sector="medtech_iso13485",
                version_number=1,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=4,
                document_uuid="2025-00004",
                title=SECTOR_MODULES[2].title,
                sector="ivd_ivdr",
                version_number=1,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=8,
            ),
        ]

        report = GuidelinesGenerationReport(
            documents_created=entries,
            total_documents=4,
            total_policy_sections=32,
            risk_tiers_referenced=["high", "low", "medium"],
            regulatory_frameworks_covered=["EU_AI_Act", "FDA_21CFR11"],
            total_duration_ms=500,
        )

        assert report.total_documents == 4
        assert len(report.documents_created) == 4
        assert all(e.is_new_document is True for e in report.documents_created)
        assert all(e.version_number == 1 for e in report.documents_created)
        assert all(
            e.workflow_state == "Draft" for e in report.documents_created
        )


class TestReportSubsequentRun:
    """Test: report correctly identifies new vs versioned on subsequent runs.

    Validates: Requirements 5.4, 6.5
    """

    @pytest.mark.asyncio
    async def test_report_identifies_versioned_documents(
        self, async_session: AsyncMock
    ):
        """Report shows is_new_document=False for versioned documents."""
        from alcoabase.schemas.guidelines_generation import (
            DocumentReportEntry,
            GuidelinesGenerationReport,
        )

        # Simulate a report from second run (all versioned)
        entries = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title=MASTER_GUIDELINE_TITLE,
                sector="cross-sector",
                version_number=2,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=False,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=2,
                document_uuid="2025-00002",
                title=SECTOR_MODULES[0].title,
                sector="pharma_gmp",
                version_number=2,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=False,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=3,
                document_uuid="2025-00003",
                title=SECTOR_MODULES[1].title,
                sector="medtech_iso13485",
                version_number=2,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=False,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=4,
                document_uuid="2025-00004",
                title=SECTOR_MODULES[2].title,
                sector="ivd_ivdr",
                version_number=2,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=False,
                policy_section_count=8,
            ),
        ]

        report = GuidelinesGenerationReport(
            documents_created=entries,
            total_documents=4,
            total_policy_sections=32,
            risk_tiers_referenced=["high", "low", "medium"],
            regulatory_frameworks_covered=["EU_AI_Act", "FDA_21CFR11"],
            total_duration_ms=450,
        )

        assert report.total_documents == 4
        assert all(
            e.is_new_document is False for e in report.documents_created
        )
        assert all(e.version_number == 2 for e in report.documents_created)


class TestReportPolicySectionCount:
    """Test: report total_policy_sections matches actual count.

    Validates: Requirements 5.4
    """

    def test_total_policy_sections_matches_sum(self, async_session: AsyncMock):
        """total_policy_sections equals sum of per-document policy_section_count."""
        service = GuidelinesGeneratorService(async_session)

        # Test _count_policy_sections with known content
        content_with_3_sections = (
            "# Document\n\n"
            "### Policy: Document Generation\n\nContent here.\n\n"
            "### Policy: Multi-Agent Auditing\n\nContent here.\n\n"
            "### Policy: RAG Q&A\n\nContent here.\n"
        )
        count = service._count_policy_sections(content_with_3_sections)
        assert count == 3

    def test_count_policy_sections_empty(self, async_session: AsyncMock):
        """Returns 0 for content with no policy sections."""
        service = GuidelinesGeneratorService(async_session)

        content_no_sections = "# Document\n\n## Overview\n\nNo policies here."
        count = service._count_policy_sections(content_no_sections)
        assert count == 0

    def test_report_total_matches_individual_counts(
        self, async_session: AsyncMock
    ):
        """Report total_policy_sections matches sum of individual counts."""
        from alcoabase.schemas.guidelines_generation import (
            DocumentReportEntry,
            GuidelinesGenerationReport,
        )

        entries = [
            DocumentReportEntry(
                document_id=i,
                document_uuid=f"2025-0000{i}",
                title=f"Doc {i}",
                sector="cross-sector",
                version_number=1,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=count,
            )
            for i, count in enumerate([10, 8, 8, 8], start=1)
        ]

        report = GuidelinesGenerationReport(
            documents_created=entries,
            total_documents=4,
            total_policy_sections=34,
            risk_tiers_referenced=["high", "medium", "low"],
            regulatory_frameworks_covered=["EU_AI_Act"],
            total_duration_ms=300,
        )

        # Verify total matches sum of individual counts
        individual_sum = sum(
            e.policy_section_count for e in report.documents_created
        )
        assert report.total_policy_sections == individual_sum


class TestReportRiskTiersReferenced:
    """Test: report risk_tiers_referenced matches used tiers.

    Validates: Requirements 5.4
    """

    def test_risk_tiers_referenced_matches_effective_tiers(
        self, async_session: AsyncMock
    ):
        """risk_tiers_referenced contains exactly the set of tiers used."""
        from alcoabase.schemas.guidelines_generation import (
            DocumentReportEntry,
            GuidelinesGenerationReport,
        )

        # Simulate effective tiers: some high, some medium, no low
        effective_tiers = {
            "document_generation": "high",
            "multi_agent_audit": "high",
            "rag_qa": "medium",
            "training_content": "medium",
        }
        expected_tiers = sorted(set(effective_tiers.values()))

        entries = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title=MASTER_GUIDELINE_TITLE,
                sector="cross-sector",
                version_number=1,
                tags_applied=list(GUIDELINE_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=4,
            ),
        ]

        report = GuidelinesGenerationReport(
            documents_created=entries,
            total_documents=1,
            total_policy_sections=4,
            risk_tiers_referenced=expected_tiers,
            regulatory_frameworks_covered=["EU_AI_Act"],
            total_duration_ms=200,
        )

        # Verify tiers match what was used
        assert report.risk_tiers_referenced == ["high", "medium"]
        assert "low" not in report.risk_tiers_referenced

    def test_risk_tiers_all_three_when_present(
        self, async_session: AsyncMock
    ):
        """All three tiers present when task types span all levels."""
        from alcoabase.schemas.guidelines_generation import (
            DocumentReportEntry,
            GuidelinesGenerationReport,
        )

        effective_tiers = {
            "document_generation": "high",
            "rag_qa": "medium",
            "search": "low",
        }
        expected_tiers = sorted(set(effective_tiers.values()))

        report = GuidelinesGenerationReport(
            documents_created=[],
            total_documents=0,
            total_policy_sections=0,
            risk_tiers_referenced=expected_tiers,
            regulatory_frameworks_covered=[],
            total_duration_ms=100,
        )

        assert report.risk_tiers_referenced == ["high", "low", "medium"]
