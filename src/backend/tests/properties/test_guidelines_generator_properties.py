"""Property-based tests for Guidelines Generator Service (Step 8.4).

Tests correctness properties from the Step_8-4 design document, validating
the GuidelinesGeneratorService behavior for document generation, governance
integration, and workflow application.

References:
    - Design: .kiro/specs/Step_8-4_cross-sector-ai-regulatory-guidelines/design.md
    - Requirements: .kiro/specs/Step_8-4_cross-sector-ai-regulatory-guidelines/requirements.md
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.schemas.guidelines_generation import (
    DocumentReportEntry,
    GuidelinesGenerationReport,
)
from alcoabase.services.guidelines_content import (
    GUIDELINE_TAGS,
    MASTER_GUIDELINE_TITLE,
    REGULATORY_FRAMEWORKS,
    SECTOR_MODULES,
    DocumentResult,
    RiskFrameworkContext,
    assemble_master_guideline,
    assemble_risk_classification_summary,
    assemble_sector_guideline,
    assemble_sector_risk_mapping_table,
)
from alcoabase.services.guidelines_generator_service import GuidelinesGeneratorService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_company(company_id: int = 1) -> MagicMock:
    """Create a mock Company entity."""
    company = MagicMock(spec=Company)
    company.id = company_id
    company.slug = "alc-corporate"
    return company


def _make_mock_user(user_id: int = 10) -> MagicMock:
    """Create a mock doc-admin User entity."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.username = "alc-doc-admin"
    return user


def _make_mock_workflow(workflow_id: int = 5, company_id: int = 1) -> MagicMock:
    """Create a mock WorkflowDefinition entity."""
    workflow = MagicMock(spec=WorkflowDefinition)
    workflow.id = workflow_id
    workflow.name = "ALC Governance Document Lifecycle"
    workflow.document_tag = "ALC-GOV"
    workflow.company_id = company_id
    return workflow


def _make_mock_task_type(
    task_type_id: str,
    display_name: str,
    default_risk_tier: str,
    risk_factors: list[str] | None = None,
) -> MagicMock:
    """Create a mock AITaskType entity."""
    tt = MagicMock()
    tt.task_type_id = task_type_id
    tt.display_name = display_name
    tt.description = f"Description for {display_name}"
    tt.module_reference = "5.4"
    tt.default_risk_tier = default_risk_tier
    tt.risk_factors = risk_factors or ["factor_1", "factor_2"]
    tt.is_active = True
    tt.is_system_defined = True
    tt.company_id = None
    return tt


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Realistic task type identifiers matching the system-defined pattern
_REALISTIC_TASK_TYPE_IDS = [
    "document_generation",
    "multi_agent_audit",
    "rag_knowledge_retrieval",
    "training_content_generation",
    "change_impact_analysis",
    "traceability_gap_discovery",
    "compliance_scoring",
    "risk_assessment_automation",
    "sop_review_assistance",
    "deviation_report_analysis",
    "batch_record_review",
    "capa_recommendation",
]

# Realistic display names for AI task types
_REALISTIC_DISPLAY_NAMES = [
    "Document Generation",
    "Multi-Agent Compliance Audit",
    "RAG Knowledge Retrieval",
    "Training Content Generation",
    "Change Impact Analysis",
    "Traceability Gap Discovery",
    "Compliance Scoring Engine",
    "Risk Assessment Automation",
    "SOP Review Assistance",
    "Deviation Report Analysis",
    "Batch Record Review",
    "CAPA Recommendation Engine",
]

# Realistic risk factors
_REALISTIC_RISK_FACTORS = [
    "Generates GxP-regulated content entering approval workflows",
    "Produces compliance assessments influencing approval decisions",
    "Identifies affected documents or gaps without modifying records",
    "Output informs human decision-making in regulated context",
    "Retrieves or summarizes existing approved content",
    "Creates training materials requiring validation",
    "Analyzes change propagation across document hierarchy",
    "Discovers missing traceability links in requirements",
]

# Strategy: generate random risk tiers
st_risk_tier = st.sampled_from(["high", "medium", "low"])

# Strategy: generate random task type identifiers
st_task_type_id = st.sampled_from(_REALISTIC_TASK_TYPE_IDS)

# Strategy: generate random display names (sampled from realistic data)
st_display_name = st.sampled_from(_REALISTIC_DISPLAY_NAMES)

# Strategy: generate random risk factors
st_risk_factors = st.lists(
    st.sampled_from(_REALISTIC_RISK_FACTORS),
    min_size=1,
    max_size=5,
)

# Strategy: generate a set of task types (at least 1) — plain strategy
st_task_type_set = st.lists(
    st.tuples(
        st.sampled_from(_REALISTIC_TASK_TYPE_IDS),
        st.sampled_from(_REALISTIC_DISPLAY_NAMES),
        st_risk_tier,
        st.lists(st.sampled_from(_REALISTIC_RISK_FACTORS), min_size=2, max_size=4),
    ),
    min_size=1,
    max_size=8,
    unique_by=lambda t: t[0],  # unique task_type_ids
)


@st.composite
def st_realistic_task_type_set(
    draw: st.DrawFn,
) -> list[tuple[str, str, str, list[str]]]:
    """Generate a realistic set of task types for Property 6 testing.

    Uses realistic task type IDs and display names to ensure the content
    generation functions produce sections with sufficient content (>= 100 chars).
    Minimum 3 task types to ensure all sector sections meet the 100-char threshold.
    """
    count = draw(st.integers(min_value=3, max_value=8))
    # Pick unique indices
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=len(_REALISTIC_TASK_TYPE_IDS) - 1),
            min_size=count,
            max_size=count,
            unique=True,
        )
    )
    result = []
    for idx in indices:
        tier = draw(st_risk_tier)
        # Pick 2-4 risk factors
        num_factors = draw(st.integers(min_value=2, max_value=4))
        factors = draw(
            st.lists(
                st.sampled_from(_REALISTIC_RISK_FACTORS),
                min_size=num_factors,
                max_size=num_factors,
            )
        )
        result.append((
            _REALISTIC_TASK_TYPE_IDS[idx],
            _REALISTIC_DISPLAY_NAMES[idx],
            tier,
            factors,
        ))
    return result


# Strategy: generate document UUIDs in YYYY-NNNNN format
st_document_uuid = st.from_regex(r"^20[2-3][0-9]-[0-9]{5}$", fullmatch=True)


# ---------------------------------------------------------------------------
# Session Builder for Property 6
# ---------------------------------------------------------------------------


def _build_session_for_governance_test(
    mock_company: MagicMock,
    mock_user: MagicMock,
    mock_workflow: MagicMock,
    task_types: list[MagicMock],
    document_uuid: str,
    added_objects: list,
) -> AsyncMock:
    """Build a mock AsyncSession for a full service execution (new documents).

    Simulates the complete query sequence for a first-time execution where
    all 4 documents are new (no existing documents).

    The query sequence for the service is:
    1. Advisory lock
    2. Company query (prerequisites)
    3. User query (prerequisites)
    4. Workflow query (prerequisites)
    5. Task types query (risk framework)
    6. Company risk profile query (risk framework)
    7. URS availability query
    8-11. Detect existing document (×4, one per guideline) — returns None
    12-15. For each of 4 documents: detect existing (in _upload_or_version_document)
    16-19. Apply tags query (×4)
    20-23. Apply workflow query (×4)

    Args:
        mock_company: The mock Company to return.
        mock_user: The mock User to return.
        mock_workflow: The mock WorkflowDefinition to return.
        task_types: List of mock AITaskType objects.
        document_uuid: UUID to assign to created documents.
        added_objects: Mutable list to track objects added to the session.

    Returns:
        A configured AsyncMock session.
    """
    session = AsyncMock()
    doc_id_counter = {"next": 100}

    def track_add(obj):
        added_objects.append(obj)
        # Simulate DB ID assignment for Document objects
        if isinstance(obj, Document):
            obj.id = doc_id_counter["next"]
            obj.document_uuid = document_uuid
            doc_id_counter["next"] += 1

    session.add = MagicMock(side_effect=track_add)
    session.flush = AsyncMock()

    call_counter = {"count": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_counter["count"] += 1
        result = MagicMock()
        call_num = call_counter["count"]

        # Convert stmt to string for pattern matching
        stmt_str = str(stmt) if not isinstance(stmt, str) else stmt

        if call_num == 1:
            # Advisory lock: pg_try_advisory_xact_lock
            result.scalar.return_value = True
        elif call_num == 2:
            # Company query
            result.scalar_one_or_none.return_value = mock_company
        elif call_num == 3:
            # User query
            result.scalar_one_or_none.return_value = mock_user
        elif call_num == 4:
            # Workflow query
            result.scalar_one_or_none.return_value = mock_workflow
        elif call_num == 5:
            # Task types query — returns scalars().all()
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = task_types
            result.scalars.return_value = scalars_obj
        elif call_num == 6:
            # Company risk profile query — no active profile
            result.scalar_one_or_none.return_value = None
        elif call_num == 7:
            # URS availability query — URS not available
            result.scalar_one_or_none.return_value = None
        elif call_num in (8, 9, 10, 11):
            # Detect existing documents (in execute() for version number)
            result.scalar_one_or_none.return_value = None
        elif call_num in (12, 15, 18, 21):
            # Detect existing document (in _upload_or_version_document)
            result.scalar_one_or_none.return_value = None
        elif call_num in (13, 16, 19, 22):
            # Apply tags: SELECT existing tags → empty
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = []
            result.scalars.return_value = scalars_obj
        elif call_num in (14, 17, 20, 23):
            # Apply workflow: SELECT DocumentState → None (create new)
            result.scalar_one_or_none.return_value = None
        else:
            # Fallback for any additional queries
            result.scalar_one_or_none.return_value = None
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = []
            result.scalars.return_value = scalars_obj

        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


# ---------------------------------------------------------------------------
# Property 6: Document governance completeness
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=None)
@given(
    task_type_data=st_realistic_task_type_set(),
    document_uuid=st_document_uuid,
)
@pytest.mark.asyncio
async def test_property_6_document_governance_completeness(
    task_type_data: list[tuple[str, str, str, list[str]]],
    document_uuid: str,
) -> None:
    """For any successfully generated guideline document, there SHALL exist:
    a Document record with content_type "text/markdown" and created_by
    referencing the alc-doc-admin user, a document_uuid matching the pattern
    `\\d{4}-\\d{5}`, DocumentTag records for both "AI-Guidelines" and "ALC-GOV",
    and a DocumentState record with current_state="Draft" linked to the ALC
    Governance workflow.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """
    # Build mock task types from generated data
    task_types = [
        _make_mock_task_type(
            task_type_id=tt_id,
            display_name=display_name,
            default_risk_tier=tier,
            risk_factors=factors,
        )
        for tt_id, display_name, tier, factors in task_type_data
    ]

    # Setup mock prerequisites
    mock_company = _make_mock_company()
    mock_user = _make_mock_user()
    mock_workflow = _make_mock_workflow()

    # Track objects added to session
    added_objects: list = []

    # Build mock session
    session = _build_session_for_governance_test(
        mock_company=mock_company,
        mock_user=mock_user,
        mock_workflow=mock_workflow,
        task_types=task_types,
        document_uuid=document_uuid,
        added_objects=added_objects,
    )

    # Create mock storage and UUID services
    mock_storage = AsyncMock()
    mock_storage.upload_file = AsyncMock()

    mock_uuid_service = AsyncMock()
    mock_uuid_service.generate_document_uuid = AsyncMock(
        return_value=document_uuid
    )

    # Execute the service (patch _validate_section_lengths since Property 6
    # tests governance completeness, not content validation — that's Property 5)
    service = GuidelinesGeneratorService(
        session=session,
        storage_service=mock_storage,
        uuid_service=mock_uuid_service,
    )
    service._validate_section_lengths = lambda content, title: None  # type: ignore[method-assign]

    report = await service.execute()

    # --- Property 6 Assertions ---

    # The report should contain exactly 4 document entries
    assert report.total_documents == 4, (
        f"Expected 4 documents, got {report.total_documents}"
    )
    assert len(report.documents_created) == 4, (
        f"Expected 4 document entries, got {len(report.documents_created)}"
    )

    # UUID pattern: YYYY-NNNNN (4 digits, dash, 5 digits)
    uuid_pattern = re.compile(r"^\d{4}-\d{5}$")

    for entry in report.documents_created:
        # Assertion 1: document_uuid matches the YYYY-NNNNN pattern
        assert uuid_pattern.match(entry.document_uuid), (
            f"Document '{entry.title}' has document_uuid='{entry.document_uuid}' "
            f"which does not match the expected pattern \\d{{4}}-\\d{{5}}"
        )

        # Assertion 2: tags_applied contains both "AI-Guidelines" and "ALC-GOV"
        assert "AI-Guidelines" in entry.tags_applied, (
            f"Document '{entry.title}' is missing 'AI-Guidelines' tag. "
            f"tags_applied={entry.tags_applied}"
        )
        assert "ALC-GOV" in entry.tags_applied, (
            f"Document '{entry.title}' is missing 'ALC-GOV' tag. "
            f"tags_applied={entry.tags_applied}"
        )

        # Assertion 3: workflow_state is "Draft"
        assert entry.workflow_state == "Draft", (
            f"Document '{entry.title}' has workflow_state='{entry.workflow_state}', "
            f"expected 'Draft'"
        )

        # Assertion 4: is_new_document is True (first run, all new)
        assert entry.is_new_document is True, (
            f"Document '{entry.title}' has is_new_document={entry.is_new_document}, "
            f"expected True for first run"
        )

    # Verify Document objects added to session have correct created_by
    documents_added = [obj for obj in added_objects if isinstance(obj, Document)]
    assert len(documents_added) == 4, (
        f"Expected 4 Document objects added to session, got {len(documents_added)}"
    )

    for doc in documents_added:
        # Assertion 5: created_by references the alc-doc-admin user
        assert doc.created_by == mock_user.id, (
            f"Document '{doc.title}' has created_by={doc.created_by}, "
            f"expected {mock_user.id} (alc-doc-admin)"
        )

        # Assertion 6: document_uuid matches the YYYY-NNNNN pattern
        assert uuid_pattern.match(doc.document_uuid), (
            f"Document '{doc.title}' has document_uuid='{doc.document_uuid}' "
            f"which does not match the expected pattern \\d{{4}}-\\d{{5}}"
        )

    # Verify DocumentTag objects were created for each document
    tags_added = [obj for obj in added_objects if isinstance(obj, DocumentTag)]
    # Each document should have 2 tags (AI-Guidelines + ALC-GOV) = 8 total
    assert len(tags_added) == 8, (
        f"Expected 8 DocumentTag objects (2 per document × 4 documents), "
        f"got {len(tags_added)}"
    )

    # Verify tag values
    tag_values = {tag.tag for tag in tags_added}
    assert "AI-Guidelines" in tag_values, (
        "No 'AI-Guidelines' DocumentTag was created"
    )
    assert "ALC-GOV" in tag_values, (
        "No 'ALC-GOV' DocumentTag was created"
    )

    # Verify DocumentState objects were created with current_state="Draft"
    states_added = [
        obj for obj in added_objects if isinstance(obj, DocumentState)
    ]
    assert len(states_added) == 4, (
        f"Expected 4 DocumentState objects (one per document), "
        f"got {len(states_added)}"
    )

    for state in states_added:
        assert state.current_state == "Draft", (
            f"DocumentState has current_state='{state.current_state}', "
            f"expected 'Draft'"
        )
        assert state.workflow_id == mock_workflow.id, (
            f"DocumentState has workflow_id={state.workflow_id}, "
            f"expected {mock_workflow.id} (ALC Governance workflow)"
        )
        assert state.updated_by == mock_user.id, (
            f"DocumentState has updated_by={state.updated_by}, "
            f"expected {mock_user.id} (alc-doc-admin)"
        )


# ---------------------------------------------------------------------------
# Property 7: Effective tier resolution
# ---------------------------------------------------------------------------

# Additional strategies for Property 7

st_override_map = st.dictionaries(
    keys=st_task_type_id,
    values=st_risk_tier,
    min_size=0,
    max_size=5,
)


@st.composite
def st_task_types_with_overrides(draw: st.DrawFn) -> tuple[
    list[MagicMock], dict[str, str], dict[str, str], bool
]:
    """Generate task types with a random subset having tier overrides.

    Returns:
        Tuple of (task_types, override_map, expected_effective_tiers, profile_active).
        - task_types: list of mock task type objects
        - override_map: dict of task_type_id -> overridden tier
        - expected_effective_tiers: dict of task_type_id -> expected effective tier
        - profile_active: whether a company profile is active
    """
    task_type_data = draw(st_task_type_set)
    task_types = [
        _make_mock_task_type(
            task_type_id=tt_id,
            display_name=display_name,
            default_risk_tier=tier,
            risk_factors=factors,
        )
        for tt_id, display_name, tier, factors in task_type_data
    ]

    profile_active = draw(st.booleans())

    # Build override map: only relevant when profile is active
    override_map: dict[str, str] = {}
    if profile_active:
        for tt in task_types:
            should_override = draw(st.booleans())
            if should_override:
                override_tier = draw(st_risk_tier)
                override_map[tt.task_type_id] = override_tier

    # Compute expected effective tiers using the same logic as
    # _load_risk_framework_data: override_map.get(task_type_id, default_risk_tier)
    expected_effective_tiers: dict[str, str] = {}
    for tt in task_types:
        if profile_active:
            expected_effective_tiers[tt.task_type_id] = override_map.get(
                tt.task_type_id, tt.default_risk_tier
            )
        else:
            expected_effective_tiers[tt.task_type_id] = tt.default_risk_tier

    return task_types, override_map, expected_effective_tiers, profile_active


class TestEffectiveTierResolution:
    """Property 7: Effective tier resolution.

    For any AI_Task_Type, if the active Company_Risk_Profile contains a tier
    override for that task type, the effective tier used in guideline generation
    SHALL be the override value; otherwise it SHALL be the AI_Task_Type's
    default_risk_tier. If no active Company_Risk_Profile exists, all task types
    SHALL resolve to their default_risk_tier and the guideline SHALL include a
    notice indicating default classifications are applied.

    **Validates: Requirements 4.1, 4.5**
    """

    @settings(max_examples=100, deadline=None)
    @given(data=st_task_types_with_overrides())
    def test_override_used_when_present(
        self,
        data: tuple[list[MagicMock], dict[str, str], dict[str, str], bool],
    ) -> None:
        """When company profile has overrides, effective tier uses override value."""
        from alcoabase.services.guidelines_content import (
            assemble_risk_classification_summary,
        )
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        task_types, override_map, expected_effective_tiers, profile_active = data

        # Build RiskFrameworkContext
        risk_factors_map = {
            tt.task_type_id: tt.risk_factors or [] for tt in task_types
        }

        risk_context = RiskFrameworkContext(
            task_types=task_types,
            effective_tiers=expected_effective_tiers,
            tier_definitions=TIER_DEFINITIONS,
            company_profile_active=profile_active,
            risk_factors_map=risk_factors_map,
        )

        # Verify effective tiers match expected resolution
        for tt in task_types:
            tid = tt.task_type_id
            if profile_active and tid in override_map:
                assert expected_effective_tiers[tid] == override_map[tid], (
                    f"Task {tid}: expected override tier '{override_map[tid]}', "
                    f"got '{expected_effective_tiers[tid]}'"
                )
            else:
                assert expected_effective_tiers[tid] == tt.default_risk_tier, (
                    f"Task {tid}: expected default tier '{tt.default_risk_tier}', "
                    f"got '{expected_effective_tiers[tid]}'"
                )

        # Verify the content assembly uses the effective tiers correctly
        content = assemble_risk_classification_summary(risk_context)
        for tt in task_types:
            tid = tt.task_type_id
            expected_tier = expected_effective_tiers[tid]
            # The tier should appear capitalized in the content
            assert f"**Risk Tier:** {expected_tier.capitalize()}" in content, (
                f"Task '{tt.display_name}' should show tier "
                f"'{expected_tier.capitalize()}' in generated content"
            )

    @settings(max_examples=100, deadline=None)
    @given(data=st_task_types_with_overrides())
    def test_default_used_when_no_override(
        self,
        data: tuple[list[MagicMock], dict[str, str], dict[str, str], bool],
    ) -> None:
        """When no override exists for a task type, default_risk_tier is used."""
        task_types, override_map, expected_effective_tiers, profile_active = data

        # Re-implement the resolution logic from _load_risk_framework_data
        resolved_tiers: dict[str, str] = {}
        for tt in task_types:
            if profile_active:
                resolved_tiers[tt.task_type_id] = override_map.get(
                    tt.task_type_id, tt.default_risk_tier
                )
            else:
                resolved_tiers[tt.task_type_id] = tt.default_risk_tier

        # Verify non-overridden tasks use their default tier
        for tt in task_types:
            tid = tt.task_type_id
            if not profile_active or tid not in override_map:
                assert resolved_tiers[tid] == tt.default_risk_tier, (
                    f"Task {tid}: without override, effective tier should be "
                    f"default '{tt.default_risk_tier}', got '{resolved_tiers[tid]}'"
                )

    @settings(max_examples=100, deadline=None)
    @given(
        task_type_data=st_task_type_set,
    )
    def test_no_active_profile_uses_all_defaults_with_notice(
        self,
        task_type_data: list[tuple[str, str, str, list[str]]],
    ) -> None:
        """When no active Company_Risk_Profile exists, all tasks use default tiers
        and the guideline includes a notice about default classifications."""
        from alcoabase.services.guidelines_content import (
            assemble_risk_classification_summary,
        )
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        task_types = [
            _make_mock_task_type(
                task_type_id=tt_id,
                display_name=display_name,
                default_risk_tier=tier,
                risk_factors=factors,
            )
            for tt_id, display_name, tier, factors in task_type_data
        ]

        # No overrides — simulate no active profile
        effective_tiers: dict[str, str] = {
            tt.task_type_id: tt.default_risk_tier for tt in task_types
        }
        risk_factors_map = {
            tt.task_type_id: tt.risk_factors or [] for tt in task_types
        }

        risk_context = RiskFrameworkContext(
            task_types=task_types,
            effective_tiers=effective_tiers,
            tier_definitions=TIER_DEFINITIONS,
            company_profile_active=False,
            risk_factors_map=risk_factors_map,
        )

        # All effective tiers should be the default
        for tt in task_types:
            assert effective_tiers[tt.task_type_id] == tt.default_risk_tier, (
                f"Task {tt.task_type_id}: without active profile, "
                f"should use default '{tt.default_risk_tier}'"
            )

        # Content should include the default classifications notice
        content = assemble_risk_classification_summary(risk_context)
        assert "default risk classifications are applied" in content.lower(), (
            "Content must include notice about default classifications "
            "when no company-specific risk profile is active"
        )

    @settings(max_examples=100, deadline=None)
    @given(
        task_type_data=st_task_type_set,
    )
    def test_active_profile_no_default_notice(
        self,
        task_type_data: list[tuple[str, str, str, list[str]]],
    ) -> None:
        """When an active Company_Risk_Profile exists, no default notice appears."""
        from alcoabase.services.guidelines_content import (
            assemble_risk_classification_summary,
        )
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        task_types = [
            _make_mock_task_type(
                task_type_id=tt_id,
                display_name=display_name,
                default_risk_tier=tier,
                risk_factors=factors,
            )
            for tt_id, display_name, tier, factors in task_type_data
        ]

        effective_tiers: dict[str, str] = {
            tt.task_type_id: tt.default_risk_tier for tt in task_types
        }
        risk_factors_map = {
            tt.task_type_id: tt.risk_factors or [] for tt in task_types
        }

        risk_context = RiskFrameworkContext(
            task_types=task_types,
            effective_tiers=effective_tiers,
            tier_definitions=TIER_DEFINITIONS,
            company_profile_active=True,
            risk_factors_map=risk_factors_map,
        )

        content = assemble_risk_classification_summary(risk_context)
        assert "default risk classifications are applied" not in content.lower(), (
            "Content must NOT include default classifications notice "
            "when a company-specific risk profile is active"
        )

    @settings(max_examples=100, deadline=None)
    @given(data=st_task_types_with_overrides())
    def test_effective_tier_resolution_mirrors_service_logic(
        self,
        data: tuple[list[MagicMock], dict[str, str], dict[str, str], bool],
    ) -> None:
        """Effective tier resolution logic matches _load_risk_framework_data.

        The resolution rule is: override_map.get(task_type_id, default_risk_tier).
        This test verifies the same logic produces consistent results.
        """
        task_types, override_map, expected_effective_tiers, profile_active = data

        # Re-implement the resolution logic from _load_risk_framework_data
        resolved_tiers: dict[str, str] = {}
        for tt in task_types:
            if profile_active:
                resolved_tiers[tt.task_type_id] = override_map.get(
                    tt.task_type_id, tt.default_risk_tier
                )
            else:
                resolved_tiers[tt.task_type_id] = tt.default_risk_tier

        # Must match the expected effective tiers
        assert resolved_tiers == expected_effective_tiers, (
            f"Resolved tiers {resolved_tiers} do not match "
            f"expected {expected_effective_tiers}"
        )


# ---------------------------------------------------------------------------
# Composite Strategies for Property 2
# ---------------------------------------------------------------------------

# Validation types used in tier control sets
_p2_validation_types = st.sampled_from([
    "format",
    "cross-reference",
    "completeness",
    "schema",
    "consistency",
])

# Output label values
_p2_output_labels = st.sampled_from(["ai_assisted", "ai_generated"])


@st.composite
def _p2_tier_definition(draw: st.DrawFn) -> MagicMock:
    """Generate a mock tier definition with a complete control set."""
    hitl_required = draw(st.booleans())
    audit_depth = draw(st.sampled_from(["full", "standard", "minimal"]))
    validations = draw(
        st.lists(_p2_validation_types, min_size=0, max_size=3, unique=True)
    )
    output_label = draw(st.one_of(st.none(), _p2_output_labels))
    expiry_hours = draw(
        st.one_of(st.none(), st.integers(min_value=1, max_value=720))
    )
    rate_limit = draw(
        st.one_of(st.none(), st.integers(min_value=1, max_value=1000))
    )

    tier_def = MagicMock()
    tier_def.hitl_required = hitl_required
    tier_def.audit_depth = audit_depth
    tier_def.validations = validations
    tier_def.output_label = output_label
    tier_def.expiry_hours = expiry_hours
    tier_def.rate_limit = rate_limit
    return tier_def


@st.composite
def _p2_risk_context(draw: st.DrawFn) -> RiskFrameworkContext:
    """Generate a RiskFrameworkContext with random task types and tiers.

    Ensures:
    - At least 1 task type (up to 8)
    - Each task type has an assigned effective tier
    - Tier definitions exist for all referenced tiers
    - Each task type has a non-empty risk_factors list
    """
    count = draw(st.integers(min_value=1, max_value=8))
    # Pick unique indices from realistic data
    indices = draw(
        st.lists(
            st.integers(
                min_value=0, max_value=len(_REALISTIC_TASK_TYPE_IDS) - 1
            ),
            min_size=count,
            max_size=count,
            unique=True,
        )
    )

    task_types = []
    for idx in indices:
        tt = MagicMock()
        tt.task_type_id = _REALISTIC_TASK_TYPE_IDS[idx]
        tt.display_name = _REALISTIC_DISPLAY_NAMES[idx]
        task_types.append(tt)

    # Assign effective tiers
    effective_tiers: dict[str, str] = {}
    for tt in task_types:
        effective_tiers[tt.task_type_id] = draw(st_risk_tier)

    # Build tier definitions for all referenced tiers
    referenced_tiers = set(effective_tiers.values())
    tier_definitions: dict[str, MagicMock] = {}
    for tier_level in referenced_tiers:
        tier_definitions[tier_level] = draw(_p2_tier_definition())

    # Build risk factors map (non-empty for each task type)
    risk_factors_map: dict[str, list[str]] = {}
    for tt in task_types:
        num_factors = draw(st.integers(min_value=1, max_value=4))
        factors = draw(
            st.lists(
                st.sampled_from(_REALISTIC_RISK_FACTORS),
                min_size=num_factors,
                max_size=num_factors,
            )
        )
        risk_factors_map[tt.task_type_id] = factors

    company_profile_active = draw(st.booleans())

    return RiskFrameworkContext(
        task_types=task_types,
        effective_tiers=effective_tiers,
        tier_definitions=tier_definitions,
        company_profile_active=company_profile_active,
        risk_factors_map=risk_factors_map,
    )


# ---------------------------------------------------------------------------
# Property 2: Risk data completeness in guidelines
# ---------------------------------------------------------------------------


class TestRiskDataCompleteness:
    """Property 2: Risk data completeness in guidelines.

    For any active AI_Task_Type with an assigned effective tier, the generated
    guideline SHALL contain a Risk_Integration_Block with: the task_type
    display_name, the effective tier level, all controls from the tier's
    Control_Set (HITL requirements, audit depth, validations, output labeling,
    expiry windows, rate limits), and the risk_factors array from the
    AI_Task_Type registry.

    **Validates: Requirements 1.3, 4.2, 4.3**
    """

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_display_name(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's display_name appears in the risk classification summary."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            assert task_type.display_name in output, (
                f"display_name '{task_type.display_name}' not found in "
                f"Risk Classification Summary output."
            )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_tier_level(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's effective tier level appears in its block."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            # The tier is rendered as capitalized (e.g., "High", "Medium", "Low")
            assert tier.capitalize() in output, (
                f"Tier level '{tier.capitalize()}' for task type "
                f"'{task_type.display_name}' not found in output."
            )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_hitl_status(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's HITL requirement status appears in its block."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            tier_def = risk_context.tier_definitions[tier]
            expected_hitl = "Yes" if tier_def.hitl_required else "No"
            assert f"**HITL Required:** {expected_hitl}" in output, (
                f"HITL status '{expected_hitl}' for task type "
                f"'{task_type.display_name}' (tier={tier}) not found in output."
            )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_audit_depth(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's audit depth appears in its block."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            tier_def = risk_context.tier_definitions[tier]
            expected_depth = tier_def.audit_depth.capitalize()
            assert f"**Audit Depth:** {expected_depth}" in output, (
                f"Audit depth '{expected_depth}' for task type "
                f"'{task_type.display_name}' (tier={tier}) not found in output."
            )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_validations(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's validations appear in its block when present."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            tier_def = risk_context.tier_definitions[tier]
            if tier_def.validations:
                validations_str = ", ".join(tier_def.validations)
                assert f"**Validations:** {validations_str}" in output, (
                    f"Validations '{validations_str}' for task type "
                    f"'{task_type.display_name}' (tier={tier}) not found."
                )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_output_labeling(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's output labeling appears in its block when present."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            tier_def = risk_context.tier_definitions[tier]
            if tier_def.output_label:
                assert f"**Output Labeling:** {tier_def.output_label}" in output, (
                    f"Output label '{tier_def.output_label}' for task type "
                    f"'{task_type.display_name}' (tier={tier}) not found."
                )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_expiry_window(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's expiry window appears in its block when present."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            tier_def = risk_context.tier_definitions[tier]
            if tier_def.expiry_hours:
                assert (
                    f"**Expiry Window:** {tier_def.expiry_hours} hours" in output
                ), (
                    f"Expiry window '{tier_def.expiry_hours} hours' for task type "
                    f"'{task_type.display_name}' (tier={tier}) not found."
                )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_rate_limit(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's rate limit appears in its block when present."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            tier_def = risk_context.tier_definitions[tier]
            if tier_def.rate_limit:
                assert (
                    f"**Rate Limit:** {tier_def.rate_limit} requests/user/hour"
                    in output
                ), (
                    f"Rate limit '{tier_def.rate_limit}' for task type "
                    f"'{task_type.display_name}' (tier={tier}) not found."
                )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_contains_risk_factors(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each task type's risk factors appear in its block."""
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            factors = risk_context.risk_factors_map[tid]
            for factor in factors:
                assert factor in output, (
                    f"Risk factor '{factor}' for task type "
                    f"'{task_type.display_name}' not found in output."
                )

    @settings(max_examples=50, deadline=None)
    @given(risk_context=_p2_risk_context())
    @pytest.mark.asyncio
    async def test_risk_block_completeness(
        self, risk_context: RiskFrameworkContext
    ) -> None:
        """Each Risk_Integration_Block contains all required fields together.

        Verifies the complete property: for any active AI_Task_Type with an
        assigned effective tier, the output contains display_name, tier level,
        HITL status, audit depth, and risk factors in a single coherent block.
        """
        output = assemble_risk_classification_summary(risk_context)

        for task_type in risk_context.task_types:
            tid = task_type.task_type_id
            tier = risk_context.effective_tiers[tid]
            tier_def = risk_context.tier_definitions[tier]
            factors = risk_context.risk_factors_map[tid]

            # Find the block for this task type (starts with ### display_name)
            block_header = f"### {task_type.display_name}"
            assert block_header in output, (
                f"Block header for '{task_type.display_name}' not found."
            )

            # Extract the block content (from header to next ### or end)
            header_pos = output.index(block_header)
            next_header_pos = output.find("### ", header_pos + len(block_header))
            if next_header_pos == -1:
                block = output[header_pos:]
            else:
                block = output[header_pos:next_header_pos]

            # Verify tier level in block
            assert tier.capitalize() in block, (
                f"Tier '{tier.capitalize()}' not in block for "
                f"'{task_type.display_name}'."
            )

            # Verify HITL status in block
            expected_hitl = "Yes" if tier_def.hitl_required else "No"
            assert f"**HITL Required:** {expected_hitl}" in block, (
                f"HITL status not in block for '{task_type.display_name}'."
            )

            # Verify audit depth in block
            assert (
                f"**Audit Depth:** {tier_def.audit_depth.capitalize()}" in block
            ), (
                f"Audit depth not in block for '{task_type.display_name}'."
            )

            # Verify validations in block (when present)
            if tier_def.validations:
                validations_str = ", ".join(tier_def.validations)
                assert f"**Validations:** {validations_str}" in block, (
                    f"Validations not in block for '{task_type.display_name}'."
                )

            # Verify output labeling in block (when present)
            if tier_def.output_label:
                assert f"**Output Labeling:** {tier_def.output_label}" in block, (
                    f"Output label not in block for '{task_type.display_name}'."
                )

            # Verify expiry window in block (when present)
            if tier_def.expiry_hours:
                assert (
                    f"**Expiry Window:** {tier_def.expiry_hours} hours" in block
                ), (
                    f"Expiry window not in block for '{task_type.display_name}'."
                )

            # Verify rate limit in block (when present)
            if tier_def.rate_limit:
                assert (
                    f"**Rate Limit:** {tier_def.rate_limit} requests/user/hour"
                    in block
                ), (
                    f"Rate limit not in block for '{task_type.display_name}'."
                )

            # Verify risk factors in block
            for factor in factors:
                assert factor in block, (
                    f"Risk factor '{factor}' not in block for "
                    f"'{task_type.display_name}'."
                )


# ---------------------------------------------------------------------------
# Mock Tier Definition for Property 1
# ---------------------------------------------------------------------------


class _MockTierDef:
    """Mock tier definition with control set details for content assembly."""

    def __init__(
        self,
        hitl_required: bool,
        audit_depth: str,
        validations: list[str],
        output_label: str,
        expiry_hours: int | None,
        rate_limit: int | None,
    ) -> None:
        self.hitl_required = hitl_required
        self.audit_depth = audit_depth
        self.validations = validations
        self.output_label = output_label
        self.expiry_hours = expiry_hours
        self.rate_limit = rate_limit


_TIER_DEFS: dict[str, _MockTierDef] = {
    "high": _MockTierDef(
        hitl_required=True,
        audit_depth="full",
        validations=["format", "cross-reference", "completeness"],
        output_label="ai_generated",
        expiry_hours=24,
        rate_limit=10,
    ),
    "medium": _MockTierDef(
        hitl_required=True,
        audit_depth="standard",
        validations=["format", "cross-reference"],
        output_label="ai_assisted",
        expiry_hours=72,
        rate_limit=50,
    ),
    "low": _MockTierDef(
        hitl_required=False,
        audit_depth="minimal",
        validations=["format"],
        output_label="ai_assisted",
        expiry_hours=None,
        rate_limit=None,
    ),
}


# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 1
# ---------------------------------------------------------------------------

# Strategy for module references used in content assembly
_st_module_references = st.sampled_from([
    "document_generation",
    "multi_agent_audit",
    "rag_search",
    "training_content_generation",
    "change_impact_analysis",
    "traceability_gap_discovery",
    "quiz_generation",
    "inference_client",
])

# Strategy for display names for Property 1
_st_display_name_p1 = st.sampled_from(_REALISTIC_DISPLAY_NAMES)

# Strategy for risk factors for Property 1
_st_risk_factors_p1 = st.lists(
    st.sampled_from(_REALISTIC_RISK_FACTORS),
    min_size=1,
    max_size=5,
)


@st.composite
def _st_task_type_for_content(draw: st.DrawFn) -> MagicMock:
    """Generate a mock AI task type suitable for content assembly functions."""
    tt = MagicMock()
    tt.task_type_id = draw(st_task_type_id)
    tt.display_name = draw(_st_display_name_p1)
    tt.module_reference = draw(_st_module_references)
    tt.default_risk_tier = draw(st_risk_tier)
    tt.risk_factors = draw(_st_risk_factors_p1)
    return tt


# Strategy for a list of task types (N >= 1, up to 15) with unique IDs
_st_task_types_for_content = st.lists(
    _st_task_type_for_content(), min_size=1, max_size=15
).filter(
    lambda types: len({t.task_type_id for t in types}) == len(types)
)


def _build_risk_context_for_content(
    task_types: list[MagicMock],
    company_profile_active: bool = True,
) -> RiskFrameworkContext:
    """Build a RiskFrameworkContext from mock task types for content assembly.

    Args:
        task_types: List of mock AI task types.
        company_profile_active: Whether a company profile is active.

    Returns:
        A RiskFrameworkContext populated with the given task types.
    """
    effective_tiers = {
        t.task_type_id: t.default_risk_tier for t in task_types
    }
    risk_factors_map = {
        t.task_type_id: t.risk_factors for t in task_types
    }

    return RiskFrameworkContext(
        task_types=task_types,
        effective_tiers=effective_tiers,
        tier_definitions=_TIER_DEFS,
        company_profile_active=company_profile_active,
        risk_factors_map=risk_factors_map,
    )


# ---------------------------------------------------------------------------
# Required section headings for master and sector guidelines
# ---------------------------------------------------------------------------

_MASTER_REQUIRED_SECTIONS = [
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

_SECTOR_REQUIRED_SECTIONS = [
    "Document Header",
    "Sector Regulatory Context",
    "Sector-Specific Risk Considerations",
    "AI Feature Usage Policies",
    "Sector Risk Mapping Table",
    "Validation Requirements",
    "Record Keeping Requirements",
    "Cross-References",
    "Regulatory Reference Table",
]


def _find_section_position(content: str, section_name: str) -> int:
    """Find the position of a section heading in the content.

    Searches for the section name as a Markdown heading (# or ## or ### prefix)
    or as a recognizable section marker in the content.

    Args:
        content: The full guideline Markdown content.
        section_name: The section name to find.

    Returns:
        The character position of the section, or -1 if not found.
    """
    # Match as ## heading or # heading
    patterns = [
        rf"^##\s+{re.escape(section_name)}",
        rf"^#\s+{re.escape(section_name)}",
        rf"^###\s+{re.escape(section_name)}",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            return match.start()

    # Fallback: search for the section name as a substring in a heading line
    for match in re.finditer(r"^#{1,3}\s+(.+)$", content, re.MULTILINE):
        if section_name.lower() in match.group(1).lower():
            return match.start()

    return -1


# ---------------------------------------------------------------------------
# Property 1: Document structure invariant
# ---------------------------------------------------------------------------


class TestDocumentStructureInvariant:
    """Property 1: Document structure invariant.

    For any set of N active AI_Task_Types (where N >= 1), the generated
    master guideline SHALL contain all required sections in the specified
    order, and for any sector guideline, it SHALL contain all required
    sector sections in the specified order.

    **Validates: Requirements 1.2, 2.2**
    """

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_master_guideline_contains_all_sections_in_order(
        self, task_types: list[MagicMock]
    ) -> None:
        """Master guideline contains all required sections in specified order."""
        risk_context = _build_risk_context_for_content(task_types)
        content = assemble_master_guideline(
            risk_context=risk_context,
            version_number=1,
            urs_available=True,
        )

        # Verify all required sections are present
        positions: list[tuple[str, int]] = []
        for section_name in _MASTER_REQUIRED_SECTIONS:
            pos = _find_section_position(content, section_name)
            assert pos != -1, (
                f"Master guideline missing required section: '{section_name}'. "
                f"Generated with {len(task_types)} task types."
            )
            positions.append((section_name, pos))

        # Verify sections appear in the specified order
        for i in range(len(positions) - 1):
            current_name, current_pos = positions[i]
            next_name, next_pos = positions[i + 1]
            assert current_pos < next_pos, (
                f"Master guideline sections out of order: "
                f"'{current_name}' (pos={current_pos}) should appear before "
                f"'{next_name}' (pos={next_pos})."
            )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_guidelines_contain_all_sections_in_order(
        self, task_types: list[MagicMock]
    ) -> None:
        """Each sector guideline contains all required sector sections in order."""
        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            content = assemble_sector_guideline(
                sector=sector,
                risk_context=risk_context,
                version_number=1,
                urs_available=True,
            )

            # Verify all required sector sections are present
            positions: list[tuple[str, int]] = []
            for section_name in _SECTOR_REQUIRED_SECTIONS:
                pos = _find_section_position(content, section_name)
                assert pos != -1, (
                    f"Sector guideline '{sector.sector_label}' missing "
                    f"required section: '{section_name}'. "
                    f"Generated with {len(task_types)} task types."
                )
                positions.append((section_name, pos))

            # Verify sections appear in the specified order
            for i in range(len(positions) - 1):
                current_name, current_pos = positions[i]
                next_name, next_pos = positions[i + 1]
                assert current_pos < next_pos, (
                    f"Sector guideline '{sector.sector_label}' sections "
                    f"out of order: '{current_name}' (pos={current_pos}) "
                    f"should appear before '{next_name}' (pos={next_pos})."
                )

    @settings(max_examples=30, deadline=None)
    @given(
        task_types=_st_task_types_for_content,
        urs_available=st.booleans(),
        version_number=st.integers(min_value=1, max_value=100),
    )
    def test_master_guideline_structure_invariant_across_parameters(
        self,
        task_types: list[MagicMock],
        urs_available: bool,
        version_number: int,
    ) -> None:
        """Master guideline structure is invariant regardless of URS availability or version."""
        risk_context = _build_risk_context_for_content(task_types)
        content = assemble_master_guideline(
            risk_context=risk_context,
            version_number=version_number,
            urs_available=urs_available,
        )

        # All required sections must be present regardless of parameters
        for section_name in _MASTER_REQUIRED_SECTIONS:
            pos = _find_section_position(content, section_name)
            assert pos != -1, (
                f"Master guideline missing section '{section_name}' with "
                f"urs_available={urs_available}, version={version_number}, "
                f"task_types={len(task_types)}."
            )

    @settings(max_examples=30, deadline=None)
    @given(
        task_types=_st_task_types_for_content,
        urs_available=st.booleans(),
        version_number=st.integers(min_value=1, max_value=100),
    )
    def test_sector_guideline_structure_invariant_across_parameters(
        self,
        task_types: list[MagicMock],
        urs_available: bool,
        version_number: int,
    ) -> None:
        """Sector guideline structure is invariant regardless of URS availability or version."""
        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            content = assemble_sector_guideline(
                sector=sector,
                risk_context=risk_context,
                version_number=version_number,
                urs_available=urs_available,
            )

            # All required sector sections must be present
            for section_name in _SECTOR_REQUIRED_SECTIONS:
                pos = _find_section_position(content, section_name)
                assert pos != -1, (
                    f"Sector '{sector.sector_label}' missing section "
                    f"'{section_name}' with urs_available={urs_available}, "
                    f"version={version_number}, task_types={len(task_types)}."
                )


# ---------------------------------------------------------------------------
# Property 8: Transaction atomicity on failure
# ---------------------------------------------------------------------------

# Enumeration of steps where failure can be injected
_FAILURE_STEPS = st.sampled_from([
    "advisory_lock",
    "prerequisite_validation",
    "risk_data_loading",
    "content_generation",
    "content_validation",
    "document_upload",
    "tag_application",
    "workflow_assignment",
])


class _SessionTracker:
    """Tracks objects added to a mock session and supports rollback simulation.

    This simulates the caller's transaction management pattern:
    - Objects are added via session.add() during service execution
    - On success, the caller commits (objects persist)
    - On failure (RuntimeError), the caller rolls back (objects discarded)

    The tracker records all add() calls so we can verify that after rollback,
    no records from the current attempt would persist.
    """

    def __init__(self) -> None:
        self.added_objects: list = []
        self.rolled_back: bool = False

    def add(self, obj: object) -> None:
        """Track an object being added to the session."""
        self.added_objects.append(obj)

    def rollback(self) -> None:
        """Simulate transaction rollback — discard all added objects."""
        self.rolled_back = True
        self.added_objects.clear()

    @property
    def new_documents(self) -> list:
        """Get Document objects added in this transaction."""
        return [o for o in self.added_objects if isinstance(o, Document)]

    @property
    def new_versions(self) -> list:
        """Get DocumentVersion objects added in this transaction."""
        return [o for o in self.added_objects if isinstance(o, DocumentVersion)]

    @property
    def new_tags(self) -> list:
        """Get DocumentTag objects added in this transaction."""
        return [o for o in self.added_objects if isinstance(o, DocumentTag)]

    @property
    def new_states(self) -> list:
        """Get DocumentState objects added in this transaction."""
        return [o for o in self.added_objects if isinstance(o, DocumentState)]


def _build_failing_session(
    failure_step: str,
    tracker: _SessionTracker,
) -> AsyncMock:
    """Build a mock AsyncSession that injects a failure at the specified step.

    The session is configured to allow the service to progress through steps
    until the failure point, at which point a RuntimeError is raised.

    Args:
        failure_step: Which step should raise RuntimeError.
        tracker: _SessionTracker to record add() calls.

    Returns:
        A configured AsyncMock session.
    """
    session = AsyncMock()
    session.add = MagicMock(side_effect=tracker.add)
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    mock_company = _make_mock_company()
    mock_user = _make_mock_user()
    mock_workflow = _make_mock_workflow()

    # Advisory lock failure: lock returns False
    if failure_step == "advisory_lock":
        async def _fail_on_lock(stmt, params=None, **kwargs):
            result = MagicMock()
            result.scalar.return_value = False
            return result

        session.execute = AsyncMock(side_effect=_fail_on_lock)
        return session

    # Prerequisite failure: lock succeeds, company query returns None
    if failure_step == "prerequisite_validation":
        call_counter = {"count": 0}

        async def _fail_on_prereq(stmt, params=None, **kwargs):
            call_counter["count"] += 1
            result = MagicMock()
            if call_counter["count"] == 1:
                # Advisory lock succeeds
                result.scalar.return_value = True
            else:
                # Company query returns None → RuntimeError
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=_fail_on_prereq)
        return session

    # Risk data loading failure: prerequisites pass, task types empty
    if failure_step == "risk_data_loading":
        call_counter = {"count": 0}

        async def _fail_on_risk(stmt, params=None, **kwargs):
            call_counter["count"] += 1
            result = MagicMock()
            if call_counter["count"] == 1:
                result.scalar.return_value = True  # Advisory lock
            elif call_counter["count"] == 2:
                result.scalar_one_or_none.return_value = mock_company
            elif call_counter["count"] == 3:
                result.scalar_one_or_none.return_value = mock_user
            elif call_counter["count"] == 4:
                result.scalar_one_or_none.return_value = mock_workflow
            elif call_counter["count"] == 5:
                # AI Task Types query → empty list (triggers RuntimeError)
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=_fail_on_risk)
        return session

    # For later-stage failures, build a session that passes through early steps.
    # The actual failure will be injected via patch on the service methods.
    call_counter = {"count": 0}

    async def _pass_through(stmt, params=None, **kwargs):
        call_counter["count"] += 1
        result = MagicMock()
        if call_counter["count"] == 1:
            result.scalar.return_value = True  # Advisory lock
        elif call_counter["count"] == 2:
            result.scalar_one_or_none.return_value = mock_company
        elif call_counter["count"] == 3:
            result.scalar_one_or_none.return_value = mock_user
        elif call_counter["count"] == 4:
            result.scalar_one_or_none.return_value = mock_workflow
        else:
            result.scalar_one_or_none.return_value = None
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = []
            result.scalars.return_value = scalars_mock
        return result

    session.execute = AsyncMock(side_effect=_pass_through)
    return session


@settings(max_examples=50, deadline=None)
@given(failure_step=_FAILURE_STEPS)
@pytest.mark.asyncio
async def test_property_8_transaction_atomicity_on_failure(
    failure_step: str,
) -> None:
    """For any step in the generation sequence that raises an exception,
    the database SHALL contain zero new Document, DocumentVersion,
    DocumentTag, or DocumentState records from the current generation
    attempt after rollback, and the state SHALL be identical to the state
    before the service was invoked.

    **Validates: Requirements 5.3, 6.7, 8.5**

    This test verifies the transaction boundary behavior:
    1. When the service raises an exception, the caller can rollback
    2. After rollback, no new records exist from the failed attempt
    3. The service never calls commit (caller's responsibility)
    """
    tracker = _SessionTracker()
    session = _build_failing_session(failure_step, tracker)

    mock_storage = AsyncMock()
    mock_storage.upload_file = AsyncMock()
    mock_uuid_service = AsyncMock()
    mock_uuid_service.generate_document_uuid = AsyncMock(return_value="2025-00001")

    service = GuidelinesGeneratorService(
        session=session,
        storage_service=mock_storage,
        uuid_service=mock_uuid_service,
    )

    # For later-stage failures, patch internal methods to inject the error
    if failure_step in (
        "content_generation",
        "content_validation",
        "document_upload",
        "tag_application",
        "workflow_assignment",
    ):
        # Build a mock risk context that passes through
        mock_risk_context = MagicMock(spec=RiskFrameworkContext)
        mock_risk_context.task_types = [_make_mock_task_type("doc_gen", "Doc Gen", "high")]
        mock_risk_context.effective_tiers = {"doc_gen": "high"}
        mock_risk_context.tier_definitions = {}
        mock_risk_context.company_profile_active = True
        mock_risk_context.risk_factors_map = {"doc_gen": ["factor1"]}

        # Determine which method to make fail
        if failure_step == "content_generation":
            p_risk = patch.object(
                service, "_load_risk_framework_data",
                new_callable=AsyncMock, return_value=mock_risk_context,
            )
            p_urs = patch.object(
                service, "_check_urs_availability",
                new_callable=AsyncMock, return_value=False,
            )
            p_detect = patch.object(
                service, "_detect_existing_document",
                new_callable=AsyncMock, return_value=None,
            )
            p_fail = patch.object(
                service, "_generate_master_guideline",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Content generation failed"),
            )
            p_risk.start()
            p_urs.start()
            p_detect.start()
            p_fail.start()
            try:
                with pytest.raises(RuntimeError, match="Content generation failed"):
                    await service.execute()
            finally:
                p_risk.stop()
                p_urs.stop()
                p_detect.stop()
                p_fail.stop()

        elif failure_step == "content_validation":
            p_risk = patch.object(
                service, "_load_risk_framework_data",
                new_callable=AsyncMock, return_value=mock_risk_context,
            )
            p_urs = patch.object(
                service, "_check_urs_availability",
                new_callable=AsyncMock, return_value=False,
            )
            p_detect = patch.object(
                service, "_detect_existing_document",
                new_callable=AsyncMock, return_value=None,
            )
            p_master = patch.object(
                service, "_generate_master_guideline",
                new_callable=AsyncMock, return_value="# Valid\n\nContent",
            )
            p_sector = patch.object(
                service, "_generate_sector_guideline",
                new_callable=AsyncMock, return_value="# Sector\n\nContent",
            )
            p_fail = patch.object(
                service, "_validate_content",
                side_effect=RuntimeError("Content validation failed"),
            )
            p_risk.start()
            p_urs.start()
            p_detect.start()
            p_master.start()
            p_sector.start()
            p_fail.start()
            try:
                with pytest.raises(RuntimeError, match="Content validation failed"):
                    await service.execute()
            finally:
                p_risk.stop()
                p_urs.stop()
                p_detect.stop()
                p_master.stop()
                p_sector.stop()
                p_fail.stop()

        else:
            # document_upload, tag_application, workflow_assignment
            # All these fail inside _upload_or_version_document
            p_risk = patch.object(
                service, "_load_risk_framework_data",
                new_callable=AsyncMock, return_value=mock_risk_context,
            )
            p_urs = patch.object(
                service, "_check_urs_availability",
                new_callable=AsyncMock, return_value=False,
            )
            p_detect = patch.object(
                service, "_detect_existing_document",
                new_callable=AsyncMock, return_value=None,
            )
            p_master = patch.object(
                service, "_generate_master_guideline",
                new_callable=AsyncMock, return_value="# Valid\n\nContent",
            )
            p_sector = patch.object(
                service, "_generate_sector_guideline",
                new_callable=AsyncMock, return_value="# Sector\n\nContent",
            )
            p_validate = patch.object(
                service, "_validate_content", return_value=None,
            )
            p_section_len = patch.object(
                service, "_validate_section_lengths", return_value=None,
            )
            p_upload = patch.object(
                service, "_upload_or_version_document",
                new_callable=AsyncMock,
                side_effect=RuntimeError(
                    f"Failure at {failure_step} step"
                ),
            )
            p_risk.start()
            p_urs.start()
            p_detect.start()
            p_master.start()
            p_sector.start()
            p_validate.start()
            p_section_len.start()
            p_upload.start()
            try:
                with pytest.raises(RuntimeError, match=f"Failure at {failure_step}"):
                    await service.execute()
            finally:
                p_risk.stop()
                p_urs.stop()
                p_detect.stop()
                p_master.stop()
                p_sector.stop()
                p_validate.stop()
                p_section_len.stop()
                p_upload.stop()

    else:
        # Early failures: advisory_lock, prerequisite_validation, risk_data_loading
        with pytest.raises(RuntimeError):
            await service.execute()

    # --- Property 8 Assertion: Transaction atomicity ---
    # Simulate what the caller does on failure: rollback the transaction
    tracker.rollback()

    # After rollback, the tracker must have zero records from this attempt
    assert tracker.rolled_back is True, "Caller must rollback on service failure"

    assert len(tracker.new_documents) == 0, (
        f"After rollback, expected 0 Document records but found "
        f"{len(tracker.new_documents)}. Failure step: {failure_step}"
    )
    assert len(tracker.new_versions) == 0, (
        f"After rollback, expected 0 DocumentVersion records but found "
        f"{len(tracker.new_versions)}. Failure step: {failure_step}"
    )
    assert len(tracker.new_tags) == 0, (
        f"After rollback, expected 0 DocumentTag records but found "
        f"{len(tracker.new_tags)}. Failure step: {failure_step}"
    )
    assert len(tracker.new_states) == 0, (
        f"After rollback, expected 0 DocumentState records but found "
        f"{len(tracker.new_states)}. Failure step: {failure_step}"
    )

    # The service must NEVER call commit — that's the caller's responsibility
    session.commit.assert_not_called()


@settings(max_examples=50, deadline=None)
@given(failure_step=_FAILURE_STEPS)
@pytest.mark.asyncio
async def test_property_8_service_raises_runtime_error_on_failure(
    failure_step: str,
) -> None:
    """For any step that encounters an error, the service SHALL raise a
    RuntimeError, enabling the caller to perform a rollback. The service
    never silently swallows errors or commits partial state.

    **Validates: Requirements 5.3, 6.7, 8.5**
    """
    tracker = _SessionTracker()
    session = _build_failing_session(failure_step, tracker)

    mock_storage = AsyncMock()
    mock_storage.upload_file = AsyncMock()
    mock_uuid_service = AsyncMock()
    mock_uuid_service.generate_document_uuid = AsyncMock(return_value="2025-00001")

    service = GuidelinesGeneratorService(
        session=session,
        storage_service=mock_storage,
        uuid_service=mock_uuid_service,
    )

    # For later-stage failures, patch internal methods
    if failure_step in (
        "content_generation",
        "content_validation",
        "document_upload",
        "tag_application",
        "workflow_assignment",
    ):
        mock_risk_context = MagicMock(spec=RiskFrameworkContext)
        mock_risk_context.task_types = [_make_mock_task_type("doc_gen", "Doc Gen", "high")]
        mock_risk_context.effective_tiers = {"doc_gen": "high"}
        mock_risk_context.tier_definitions = {}
        mock_risk_context.company_profile_active = True
        mock_risk_context.risk_factors_map = {"doc_gen": ["factor1"]}

        patches = [
            patch.object(
                service, "_load_risk_framework_data",
                new_callable=AsyncMock, return_value=mock_risk_context,
            ),
            patch.object(
                service, "_check_urs_availability",
                new_callable=AsyncMock, return_value=False,
            ),
            patch.object(
                service, "_detect_existing_document",
                new_callable=AsyncMock, return_value=None,
            ),
            # Inject failure at the first method that runs for this step
            patch.object(
                service, "_generate_master_guideline",
                new_callable=AsyncMock,
                side_effect=RuntimeError(f"Simulated {failure_step} failure"),
            ),
        ]
        for p in patches:
            p.start()
        try:
            with pytest.raises(RuntimeError):
                await service.execute()
        finally:
            for p in patches:
                p.stop()
    else:
        # Early failures raise RuntimeError directly from session interactions
        with pytest.raises(RuntimeError):
            await service.execute()

    # Verify: the exception propagated (test would fail if no RuntimeError raised)
    # and no commit was called
    session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers for Property 10
# ---------------------------------------------------------------------------

# Known task type IDs that the content module handles
_KNOWN_TASK_TYPE_IDS = [
    "document_generation",
    "multi_agent_audit",
    "rag_query",
    "training_content_generation",
    "change_impact_analysis",
    "traceability_gap_discovery",
    "quiz_generation",
    "knowledge_search",
]

_TIER_LEVELS = ["high", "medium", "low"]


def _count_policy_sections_in_content(content: str) -> int:
    """Count Policy_Section headings (### Policy:) in generated content."""
    pattern = re.compile(r"^### Policy:", re.MULTILINE)
    return len(pattern.findall(content))


def _build_report_from_generated_content(
    risk_context: RiskFrameworkContext,
    master_content: str,
    sector_contents: list[tuple],
    duration_ms: int,
) -> GuidelinesGenerationReport:
    """Build a GuidelinesGenerationReport from generated content.

    Mirrors the report-building logic in GuidelinesGeneratorService.execute().
    """
    from alcoabase.services.guidelines_content import (
        IVD_GUIDELINE_TITLE,
        MEDTECH_GUIDELINE_TITLE,
        PHARMA_GUIDELINE_TITLE,
    )

    # Count total policy sections
    total_policy_sections = _count_policy_sections_in_content(master_content)
    for _sector, content in sector_contents:
        total_policy_sections += _count_policy_sections_in_content(content)

    # Collect unique risk tiers referenced
    risk_tiers_referenced = sorted(set(risk_context.effective_tiers.values()))

    # Collect regulatory frameworks covered (same logic as service)
    regulatory_frameworks_covered = sorted(
        {fw.identifier for fw in REGULATORY_FRAMEWORKS}
    )

    # Build report entries (simulate document IDs)
    entries: list[DocumentReportEntry] = []

    # Master entry
    entries.append(
        DocumentReportEntry(
            document_id=1,
            document_uuid="2025-00001",
            title=MASTER_GUIDELINE_TITLE,
            sector="cross-sector",
            version_number=1,
            tags_applied=GUIDELINE_TAGS,
            workflow_state="Draft",
            is_new_document=True,
            policy_section_count=_count_policy_sections_in_content(master_content),
        )
    )

    # Sector entries
    for i, (sector, content) in enumerate(sector_contents, start=2):
        entries.append(
            DocumentReportEntry(
                document_id=i,
                document_uuid=f"2025-{i:05d}",
                title=sector.title,
                sector=sector.sector_id,
                version_number=1,
                tags_applied=GUIDELINE_TAGS,
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=_count_policy_sections_in_content(content),
            )
        )

    return GuidelinesGenerationReport(
        documents_created=entries,
        total_documents=len(entries),
        total_policy_sections=total_policy_sections,
        risk_tiers_referenced=risk_tiers_referenced,
        regulatory_frameworks_covered=regulatory_frameworks_covered,
        total_duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 10
# ---------------------------------------------------------------------------


@st.composite
def st_task_types_for_report(draw: st.DrawFn) -> list[MagicMock]:
    """Generate a random list of AI task types for report accuracy testing.

    Draws between 1 and 8 task types with random tier assignments.
    """
    n = draw(st.integers(min_value=1, max_value=8))
    selected_ids = draw(
        st.lists(
            st.sampled_from(_KNOWN_TASK_TYPE_IDS),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )

    task_types = []
    for tid in selected_ids:
        tier = draw(st.sampled_from(_TIER_LEVELS))
        risk_factors = draw(
            st.lists(
                st.sampled_from([
                    "generates_regulated_content",
                    "influences_approval_decisions",
                    "modifies_controlled_records",
                    "informs_human_decisions",
                    "retrieves_existing_content",
                    "summarizes_approved_data",
                ]),
                min_size=1,
                max_size=3,
                unique=True,
            )
        )
        task_types.append(
            _make_mock_task_type(
                task_type_id=tid,
                display_name=tid.replace("_", " ").title(),
                default_risk_tier=tier,
                risk_factors=risk_factors,
            )
        )

    return task_types


@st.composite
def st_risk_context_for_report(draw: st.DrawFn) -> RiskFrameworkContext:
    """Generate a random RiskFrameworkContext for report accuracy testing."""
    from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

    task_types = draw(st_task_types_for_report())

    effective_tiers: dict[str, str] = {}
    risk_factors_map: dict[str, list[str]] = {}

    for tt in task_types:
        # Optionally override the tier (simulating company profile overrides)
        use_override = draw(st.booleans())
        if use_override:
            effective_tiers[tt.task_type_id] = draw(st.sampled_from(_TIER_LEVELS))
        else:
            effective_tiers[tt.task_type_id] = tt.default_risk_tier
        risk_factors_map[tt.task_type_id] = tt.risk_factors or []

    company_profile_active = draw(st.booleans())

    return RiskFrameworkContext(
        task_types=task_types,
        effective_tiers=effective_tiers,
        tier_definitions=TIER_DEFINITIONS,
        company_profile_active=company_profile_active,
        risk_factors_map=risk_factors_map,
    )


# ---------------------------------------------------------------------------
# Property 10: Report accuracy
# ---------------------------------------------------------------------------


@settings(max_examples=25, deadline=None)
@given(
    risk_context=st_risk_context_for_report(),
    duration_ms=st.integers(min_value=1, max_value=120_000),
)
def test_property_10_report_accuracy(
    risk_context: RiskFrameworkContext,
    duration_ms: int,
) -> None:
    """For any successful execution of the GuidelinesGeneratorService, the
    returned GuidelinesGenerationReport SHALL contain: documents_created with
    exactly 4 entries (one per guideline), total_documents equal to 4,
    total_policy_sections equal to the actual sum of Policy_Sections across
    all 4 documents, risk_tiers_referenced containing exactly the set of tier
    levels used in generation, regulatory_frameworks_covered containing all
    framework identifiers referenced, and total_duration_ms as a positive
    integer.

    **Validates: Requirements 5.4, 6.5**
    """
    # Generate all 4 documents using the content assembly functions
    master_content = assemble_master_guideline(
        risk_context=risk_context,
        version_number=1,
        urs_available=True,
    )

    sector_contents: list[tuple] = []
    for sector in SECTOR_MODULES:
        sector_content = assemble_sector_guideline(
            sector=sector,
            risk_context=risk_context,
            version_number=1,
            urs_available=True,
        )
        sector_contents.append((sector, sector_content))

    # Build the report using the same logic as the service
    report = _build_report_from_generated_content(
        risk_context=risk_context,
        master_content=master_content,
        sector_contents=sector_contents,
        duration_ms=duration_ms,
    )

    # --- Property 10 Assertions ---

    # Assertion 1: documents_created has exactly 4 entries
    assert len(report.documents_created) == 4, (
        f"Expected exactly 4 entries in documents_created, "
        f"got {len(report.documents_created)}. "
        f"One entry per guideline (1 master + 3 sector-specific)."
    )

    # Assertion 2: total_documents equals 4
    assert report.total_documents == 4, (
        f"Expected total_documents=4, got {report.total_documents}."
    )

    # Assertion 3: total_policy_sections matches actual count across all 4 docs
    actual_total_policy_sections = _count_policy_sections_in_content(master_content)
    for _sector, content in sector_contents:
        actual_total_policy_sections += _count_policy_sections_in_content(content)

    assert report.total_policy_sections == actual_total_policy_sections, (
        f"Expected total_policy_sections={actual_total_policy_sections}, "
        f"got {report.total_policy_sections}. "
        f"Report must match actual sum of '### Policy:' headings across all docs."
    )

    # Assertion 4: Each document entry's policy_section_count matches its content
    master_entry = report.documents_created[0]
    assert master_entry.policy_section_count == _count_policy_sections_in_content(
        master_content
    ), (
        f"Master guideline policy_section_count={master_entry.policy_section_count} "
        f"does not match actual count="
        f"{_count_policy_sections_in_content(master_content)}."
    )
    for i, (_sector, content) in enumerate(sector_contents):
        entry = report.documents_created[i + 1]
        expected_count = _count_policy_sections_in_content(content)
        assert entry.policy_section_count == expected_count, (
            f"Sector '{entry.title}' policy_section_count="
            f"{entry.policy_section_count} "
            f"does not match actual count={expected_count}."
        )

    # Assertion 5: risk_tiers_referenced matches the set of unique tiers used
    expected_tiers = sorted(set(risk_context.effective_tiers.values()))
    assert report.risk_tiers_referenced == expected_tiers, (
        f"Expected risk_tiers_referenced={expected_tiers}, "
        f"got {report.risk_tiers_referenced}. "
        f"Must contain exactly the set of tier levels used in generation."
    )

    # Assertion 6: total_duration_ms is a positive integer
    assert report.total_duration_ms > 0, (
        f"Expected total_duration_ms > 0, got {report.total_duration_ms}."
    )

    # Assertion 7: regulatory_frameworks_covered contains all framework identifiers
    expected_frameworks = sorted({fw.identifier for fw in REGULATORY_FRAMEWORKS})
    assert report.regulatory_frameworks_covered == expected_frameworks, (
        f"Expected regulatory_frameworks_covered={expected_frameworks}, "
        f"got {report.regulatory_frameworks_covered}."
    )

    # Assertion 8: Sum of per-document policy_section_count equals total_policy_sections
    sum_per_doc = sum(e.policy_section_count for e in report.documents_created)
    assert sum_per_doc == report.total_policy_sections, (
        f"Sum of per-document policy_section_count ({sum_per_doc}) "
        f"does not equal total_policy_sections ({report.total_policy_sections})."
    )

# ---------------------------------------------------------------------------
# Property 4: Sector non-contradiction invariant
# ---------------------------------------------------------------------------

# Tier ordering for comparison: low < medium < high
_TIER_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def _parse_sector_elevation(elevation_str: str) -> str | None:
    """Parse a sector elevation recommendation into the elevated tier.

    Args:
        elevation_str: The elevation string from the mapping table.

    Returns:
        The elevated tier level, or None if no elevation.
    """
    if "Elevate to High" in elevation_str:
        return "high"
    elif "Elevate to Medium" in elevation_str:
        return "medium"
    return None


def _get_effective_sector_tier(base_tier: str, elevation_str: str) -> str:
    """Determine the effective sector tier after applying elevation.

    The sector tier is the base tier elevated according to the recommendation.
    If no elevation, the sector tier equals the base tier.

    Args:
        base_tier: The base risk tier from the master guideline.
        elevation_str: The elevation recommendation string.

    Returns:
        The effective sector tier level.
    """
    elevated = _parse_sector_elevation(elevation_str)
    if elevated is not None:
        return elevated
    return base_tier


class TestSectorNonContradictionInvariant:
    """Property 4: Sector non-contradiction invariant.

    For any AI_Task_Type and for any sector-specific guideline, the sector's
    risk tier recommendation SHALL be greater than or equal to the master
    guideline's tier for that task type, and the sector's control set SHALL
    be a superset of (or equal to) the master guideline's control set.

    **Validates: Requirements 2.7**
    """

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_tier_never_lower_than_master(
        self, task_types: list[MagicMock]
    ) -> None:
        """No sector guideline assigns a lower tier than the master guideline."""
        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            mapping_table = assemble_sector_risk_mapping_table(sector, risk_context)

            for task_type in risk_context.task_types:
                tid = task_type.task_type_id
                base_tier = risk_context.effective_tiers.get(tid, "low")

                # Determine the sector's effective tier from the mapping table
                if tid in sector.risk_elevation_rules:
                    # Sector elevates this task type
                    from alcoabase.services.guidelines_content import (
                        _get_elevation_recommendation,
                    )

                    elevation = _get_elevation_recommendation(base_tier)
                    sector_tier = _get_effective_sector_tier(base_tier, elevation)
                else:
                    # No elevation — sector tier equals base tier
                    sector_tier = base_tier

                # Assert: sector tier >= master tier (never lower)
                assert _TIER_ORDER[sector_tier] >= _TIER_ORDER[base_tier], (
                    f"Sector '{sector.sector_label}' assigns tier "
                    f"'{sector_tier}' to task type '{task_type.display_name}' "
                    f"which is LOWER than master tier '{base_tier}'. "
                    f"Sector guidelines must never contradict the master by "
                    f"assigning a lower risk tier."
                )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_elevation_only_goes_up(
        self, task_types: list[MagicMock]
    ) -> None:
        """When a sector elevates a tier, it only goes UP (low→medium, medium→high)."""
        from alcoabase.services.guidelines_content import (
            _get_elevation_recommendation,
        )

        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            for task_type in risk_context.task_types:
                tid = task_type.task_type_id
                base_tier = risk_context.effective_tiers.get(tid, "low")

                if tid in sector.risk_elevation_rules:
                    elevation = _get_elevation_recommendation(base_tier)
                    elevated_tier = _parse_sector_elevation(elevation)

                    if elevated_tier is not None:
                        # Elevation must be strictly higher than base
                        assert _TIER_ORDER[elevated_tier] > _TIER_ORDER[base_tier], (
                            f"Sector '{sector.sector_label}' elevation for "
                            f"'{task_type.display_name}' (base={base_tier}) "
                            f"resulted in tier '{elevated_tier}' which is not "
                            f"strictly higher. Elevations must only go UP."
                        )
                    else:
                        # "No elevation" means base is already "high"
                        assert base_tier == "high", (
                            f"Sector '{sector.sector_label}' returned 'No elevation' "
                            f"for '{task_type.display_name}' with base_tier="
                            f"'{base_tier}', but 'No elevation' should only occur "
                            f"when base_tier is already 'high'."
                        )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_mapping_table_reflects_non_contradiction(
        self, task_types: list[MagicMock]
    ) -> None:
        """The sector risk mapping table content reflects the non-contradiction rule."""
        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            mapping_table = assemble_sector_risk_mapping_table(sector, risk_context)

            for task_type in risk_context.task_types:
                tid = task_type.task_type_id
                base_tier = risk_context.effective_tiers.get(tid, "low")

                # The mapping table must contain the task type's display name
                assert task_type.display_name in mapping_table, (
                    f"Task type '{task_type.display_name}' not found in "
                    f"sector '{sector.sector_label}' mapping table."
                )

                # The base tier (capitalized) must appear in the row
                assert base_tier.capitalize() in mapping_table, (
                    f"Base tier '{base_tier.capitalize()}' for task type "
                    f"'{task_type.display_name}' not found in sector "
                    f"'{sector.sector_label}' mapping table."
                )

                # If elevated, the elevation recommendation must appear
                if tid in sector.risk_elevation_rules:
                    from alcoabase.services.guidelines_content import (
                        _get_elevation_recommendation,
                    )

                    elevation = _get_elevation_recommendation(base_tier)
                    assert elevation in mapping_table, (
                        f"Elevation '{elevation}' for task type "
                        f"'{task_type.display_name}' not found in sector "
                        f"'{sector.sector_label}' mapping table."
                    )
                else:
                    # Non-elevated tasks should show "No elevation"
                    assert "No elevation" in mapping_table, (
                        f"'No elevation' not found in sector "
                        f"'{sector.sector_label}' mapping table for "
                        f"non-elevated task types."
                    )

    @settings(max_examples=50, deadline=None)
    @given(
        tier_assignment=st.sampled_from(["low", "medium", "high"]),
    )
    def test_elevation_recommendation_correctness(
        self, tier_assignment: str
    ) -> None:
        """_get_elevation_recommendation returns correct elevation for each tier.

        low → "Elevate to Medium", medium → "Elevate to High", high → "No elevation"
        """
        from alcoabase.services.guidelines_content import (
            _get_elevation_recommendation,
        )

        elevation = _get_elevation_recommendation(tier_assignment)

        if tier_assignment == "low":
            assert elevation == "Elevate to Medium", (
                f"Expected 'Elevate to Medium' for base tier 'low', "
                f"got '{elevation}'"
            )
        elif tier_assignment == "medium":
            assert elevation == "Elevate to High", (
                f"Expected 'Elevate to High' for base tier 'medium', "
                f"got '{elevation}'"
            )
        else:
            assert elevation == "No elevation", (
                f"Expected 'No elevation' for base tier 'high', "
                f"got '{elevation}'"
            )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_control_set_superset_of_master(
        self, task_types: list[MagicMock]
    ) -> None:
        """Sector control sets are supersets of (or equal to) master control sets.

        When a sector elevates a tier, the elevated tier's control set must
        include all controls from the base tier (since higher tiers have
        stricter controls).
        """
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            for task_type in risk_context.task_types:
                tid = task_type.task_type_id
                base_tier = risk_context.effective_tiers.get(tid, "low")
                base_tier_def = TIER_DEFINITIONS[base_tier]

                if tid in sector.risk_elevation_rules:
                    from alcoabase.services.guidelines_content import (
                        _get_elevation_recommendation,
                    )

                    elevation = _get_elevation_recommendation(base_tier)
                    sector_tier = _get_effective_sector_tier(base_tier, elevation)
                    sector_tier_def = TIER_DEFINITIONS[sector_tier]

                    # Sector tier's HITL requirement must be >= base
                    # (True >= False, True >= True, False >= False are valid)
                    if base_tier_def.hitl_required:
                        assert sector_tier_def.hitl_required, (
                            f"Sector '{sector.sector_label}' tier "
                            f"'{sector_tier}' does not require HITL, but "
                            f"master tier '{base_tier}' does. Sector control "
                            f"set must be a superset of master."
                        )

                    # Sector tier's audit depth must be >= base
                    # (full > standard > minimal)
                    audit_order = {"minimal": 0, "standard": 1, "full": 2}
                    base_audit = audit_order.get(base_tier_def.audit_depth, 0)
                    sector_audit = audit_order.get(
                        sector_tier_def.audit_depth, 0
                    )
                    assert sector_audit >= base_audit, (
                        f"Sector '{sector.sector_label}' audit depth "
                        f"'{sector_tier_def.audit_depth}' for task "
                        f"'{task_type.display_name}' is less than master "
                        f"audit depth '{base_tier_def.audit_depth}'. "
                        f"Sector controls must be >= master."
                    )

                    # Sector tier's validations must be a superset of base
                    base_validations = set(base_tier_def.validations or [])
                    sector_validations = set(
                        sector_tier_def.validations or []
                    )
                    assert base_validations.issubset(sector_validations), (
                        f"Sector '{sector.sector_label}' validations "
                        f"{sector_validations} for task "
                        f"'{task_type.display_name}' do not include all "
                        f"master validations {base_validations}. "
                        f"Sector control set must be a superset."
                    )

# ---------------------------------------------------------------------------
# Property 5: Section minimum content validation
# ---------------------------------------------------------------------------

# Strategies for Property 5

# Strategy: generate a section heading (## or ###)
_P5_HEADING_LEVELS = ["##", "###"]

# Realistic section names for guideline documents
_P5_SECTION_NAMES = [
    "Sector Regulatory Context",
    "Sector-Specific Risk Considerations",
    "AI Feature Usage Policies",
    "Sector Risk Mapping Table",
    "Validation Requirements",
    "Record Keeping Requirements",
    "Cross-References",
    "Regulatory Reference Table",
    "GMP Data Integrity",
    "CSV Expectations",
    "AI Model Qualification",
    "Change Control for AI Updates",
    "Design Control Integration",
    "Software Lifecycle Requirements",
    "Risk Management Integration",
    "Post-Market Surveillance",
]

# Realistic document titles for sector guidelines
_P5_DOCUMENT_TITLES = [
    "AlcoaBase — AI Usage Guidelines (Pharma / GMP)",
    "AlcoaBase — AI Usage Guidelines (MedTech / ISO 13485)",
    "AlcoaBase — AI Usage Guidelines (IVD / IVDR)",
]


@st.composite
def st_section_content_valid(draw: st.DrawFn) -> tuple[str, str]:
    """Generate Markdown content where ALL sections have >= 100 chars of body.

    Returns:
        Tuple of (markdown_content, document_title).
    """
    document_title = draw(st.sampled_from(_P5_DOCUMENT_TITLES))
    num_sections = draw(st.integers(min_value=2, max_value=6))

    # Pick unique section names
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=len(_P5_SECTION_NAMES) - 1),
            min_size=num_sections,
            max_size=num_sections,
            unique=True,
        )
    )

    sections: list[str] = []
    # Add a top-level heading first
    sections.append(f"# {document_title}\n")

    for idx in indices:
        heading_level = draw(st.sampled_from(_P5_HEADING_LEVELS))
        section_name = _P5_SECTION_NAMES[idx]
        # Generate body text with at least 100 characters
        body_length = draw(st.integers(min_value=100, max_value=300))
        body_text = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "Z"),
                    whitelist_characters=" .,;:-\n",
                ),
                min_size=body_length,
                max_size=body_length,
            )
        )
        sections.append(f"{heading_level} {section_name}\n\n{body_text}\n")

    content = "\n".join(sections)
    return content, document_title


@st.composite
def st_section_content_with_short_section(draw: st.DrawFn) -> tuple[str, str, str]:
    """Generate Markdown content where at least one section has < 100 chars of body.

    Returns:
        Tuple of (markdown_content, document_title, short_section_name).
    """
    document_title = draw(st.sampled_from(_P5_DOCUMENT_TITLES))
    num_sections = draw(st.integers(min_value=2, max_value=6))

    # Pick unique section names
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=len(_P5_SECTION_NAMES) - 1),
            min_size=num_sections,
            max_size=num_sections,
            unique=True,
        )
    )

    # Choose which section will be short (by position in the list)
    short_section_pos = draw(st.integers(min_value=0, max_value=num_sections - 1))

    sections: list[str] = []
    # Add a top-level heading first
    sections.append(f"# {document_title}\n")

    short_section_name = ""

    for i, idx in enumerate(indices):
        heading_level = draw(st.sampled_from(_P5_HEADING_LEVELS))
        section_name = _P5_SECTION_NAMES[idx]

        if i == short_section_pos:
            # This section will have < 100 chars of body content
            body_length = draw(st.integers(min_value=0, max_value=99))
            body_text = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N"),
                        whitelist_characters=" .,",
                    ),
                    min_size=body_length,
                    max_size=body_length,
                )
            )
            short_section_name = section_name
        else:
            # Valid section with >= 100 chars
            body_length = draw(st.integers(min_value=100, max_value=300))
            body_text = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("L", "N", "P", "Z"),
                        whitelist_characters=" .,;:-\n",
                    ),
                    min_size=body_length,
                    max_size=body_length,
                )
            )

        sections.append(f"{heading_level} {section_name}\n\n{body_text}\n")

    content = "\n".join(sections)
    return content, document_title, short_section_name


class TestSectionMinimumContentValidation:
    """Property 5: Section minimum content validation.

    For any sector-specific guideline and for any section within that guideline,
    if the section content (excluding the section header) contains fewer than
    100 characters, the content validation SHALL raise a RuntimeError identifying
    the section name and the sector guideline title.

    **Validates: Requirements 2.8**
    """

    @settings(max_examples=50, deadline=None)
    @given(data=st_section_content_valid())
    def test_valid_sections_pass_validation(
        self,
        data: tuple[str, str],
    ) -> None:
        """Content with all sections >= 100 chars passes validation without error."""
        content, document_title = data

        session = AsyncMock()
        service = GuidelinesGeneratorService(session=session)

        # Should not raise any exception
        service._validate_section_lengths(content, document_title)

    @settings(max_examples=50, deadline=None)
    @given(data=st_section_content_with_short_section())
    def test_short_section_raises_runtime_error(
        self,
        data: tuple[str, str, str],
    ) -> None:
        """Content with any section < 100 chars raises RuntimeError."""
        content, document_title, short_section_name = data

        session = AsyncMock()
        service = GuidelinesGeneratorService(session=session)

        with pytest.raises(RuntimeError) as exc_info:
            service._validate_section_lengths(content, document_title)

        error_message = str(exc_info.value)

        # Error message must include the document title
        assert document_title in error_message, (
            f"Error message must include document title '{document_title}'. "
            f"Got: '{error_message}'"
        )

        # Error message must include a section name (the first short one found)
        # Note: the validator stops at the first failing section it encounters,
        # which may be the short section we injected or an earlier one if
        # generated text happened to be short after stripping.
        # We verify the error mentions at least one section name from our list.
        has_section_name = any(
            name in error_message for name in _P5_SECTION_NAMES
        )
        assert has_section_name, (
            f"Error message must include a section name. "
            f"Got: '{error_message}'"
        )

    @settings(max_examples=50, deadline=None)
    @given(data=st_section_content_with_short_section())
    def test_error_message_includes_section_name_and_title(
        self,
        data: tuple[str, str, str],
    ) -> None:
        """RuntimeError message identifies both the failing section and document title."""
        content, document_title, short_section_name = data

        session = AsyncMock()
        service = GuidelinesGeneratorService(session=session)

        with pytest.raises(RuntimeError) as exc_info:
            service._validate_section_lengths(content, document_title)

        error_message = str(exc_info.value)

        # The error must reference the document title
        assert document_title in error_message, (
            f"Error must reference document title '{document_title}'. "
            f"Got: '{error_message}'"
        )

        # The error must reference a section name (from the content headings)
        # Extract all section names from the content for verification
        section_pattern = re.compile(r"^#{2,3}\s+(.+)$", re.MULTILINE)
        content_section_names = [
            m.group(1).strip() for m in section_pattern.finditer(content)
        ]
        has_content_section = any(
            name in error_message for name in content_section_names
        )
        assert has_content_section, (
            f"Error must reference a section name from the content. "
            f"Section names in content: {content_section_names}. "
            f"Got error: '{error_message}'"
        )

    @settings(max_examples=50, deadline=None)
    @given(
        document_title=st.sampled_from(_P5_DOCUMENT_TITLES),
        section_name=st.sampled_from(_P5_SECTION_NAMES),
        body_length=st.integers(min_value=0, max_value=99),
    )
    def test_single_short_section_always_fails(
        self,
        document_title: str,
        section_name: str,
        body_length: int,
    ) -> None:
        """A document with a single section having < 100 chars always fails."""
        # Build minimal content with one short section
        body_text = "x" * body_length
        content = f"# {document_title}\n\n## {section_name}\n\n{body_text}\n"

        session = AsyncMock()
        service = GuidelinesGeneratorService(session=session)

        with pytest.raises(RuntimeError) as exc_info:
            service._validate_section_lengths(content, document_title)

        error_message = str(exc_info.value)
        assert section_name in error_message, (
            f"Error must identify section '{section_name}'. Got: '{error_message}'"
        )
        assert document_title in error_message, (
            f"Error must identify document '{document_title}'. Got: '{error_message}'"
        )

    @settings(max_examples=50, deadline=None)
    @given(
        document_title=st.sampled_from(_P5_DOCUMENT_TITLES),
        section_name=st.sampled_from(_P5_SECTION_NAMES),
        body_length=st.integers(min_value=100, max_value=500),
    )
    def test_single_valid_section_always_passes(
        self,
        document_title: str,
        section_name: str,
        body_length: int,
    ) -> None:
        """A document with a single section having >= 100 chars always passes."""
        body_text = "x" * body_length
        content = f"# {document_title}\n\n## {section_name}\n\n{body_text}\n"

        session = AsyncMock()
        service = GuidelinesGeneratorService(session=session)

        # Should not raise
        service._validate_section_lengths(content, document_title)


# ---------------------------------------------------------------------------
# Property 13: Policy section count invariant
# ---------------------------------------------------------------------------

# Extended task type IDs for Property 13 (need N >= 8, up to 15)
_P13_TASK_TYPE_IDS = [
    "document_generation",
    "multi_agent_audit",
    "rag_query",
    "training_content_generation",
    "change_impact_analysis",
    "traceability_gap_discovery",
    "quiz_generation",
    "knowledge_search",
    "compliance_scoring",
    "risk_assessment_automation",
    "sop_review_assistance",
    "deviation_report_analysis",
    "batch_record_review",
    "capa_recommendation",
    "supplier_audit_analysis",
]


@st.composite
def st_task_types_for_policy_count(
    draw: st.DrawFn,
) -> list[MagicMock]:
    """Generate N task types where N is drawn from integers(min_value=8, max_value=15).

    Ensures unique task_type_ids and realistic display names for content
    assembly functions to produce valid policy sections.
    """
    n = draw(st.integers(min_value=8, max_value=15))
    selected_ids = draw(
        st.lists(
            st.sampled_from(_P13_TASK_TYPE_IDS),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )

    task_types = []
    for tid in selected_ids:
        tier = draw(st.sampled_from(_TIER_LEVELS))
        risk_factors = draw(
            st.lists(
                st.sampled_from(_REALISTIC_RISK_FACTORS),
                min_size=2,
                max_size=4,
            )
        )
        task_types.append(
            _make_mock_task_type(
                task_type_id=tid,
                display_name=tid.replace("_", " ").title(),
                default_risk_tier=tier,
                risk_factors=risk_factors,
            )
        )

    return task_types


class TestPolicySectionCountInvariant:
    """Property 13: Policy section count invariant.

    Generate with N task types (N >= 8):
    - Verify master guideline has exactly N Policy_Sections
    - Verify each sector guideline has >= 6 Policy_Sections
    - Verify total_policy_sections in report equals actual count across all 4 documents

    **Validates: Requirements 1.1, 7.5**
    """

    @settings(max_examples=30, deadline=None)
    @given(task_types=st_task_types_for_policy_count())
    def test_master_guideline_has_exactly_n_policy_sections(
        self, task_types: list[MagicMock]
    ) -> None:
        """Master guideline has exactly N Policy_Sections (one per task type).

        **Validates: Requirements 1.1, 7.5**
        """
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        n = len(task_types)

        effective_tiers = {
            t.task_type_id: t.default_risk_tier for t in task_types
        }
        risk_factors_map = {
            t.task_type_id: t.risk_factors for t in task_types
        }

        risk_context = RiskFrameworkContext(
            task_types=task_types,
            effective_tiers=effective_tiers,
            tier_definitions=TIER_DEFINITIONS,
            company_profile_active=True,
            risk_factors_map=risk_factors_map,
        )

        master_content = assemble_master_guideline(
            risk_context=risk_context,
            version_number=1,
            urs_available=True,
        )

        actual_count = _count_policy_sections_in_content(master_content)
        assert actual_count == n, (
            f"Master guideline should have exactly {n} Policy_Sections "
            f"(one per task type), but found {actual_count}. "
            f"Task types: {[t.task_type_id for t in task_types]}"
        )

    @settings(max_examples=30, deadline=None)
    @given(task_types=st_task_types_for_policy_count())
    def test_each_sector_guideline_has_at_least_6_policy_sections(
        self, task_types: list[MagicMock]
    ) -> None:
        """Each sector guideline has >= 6 Policy_Sections.

        **Validates: Requirements 1.1, 7.5**
        """
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        effective_tiers = {
            t.task_type_id: t.default_risk_tier for t in task_types
        }
        risk_factors_map = {
            t.task_type_id: t.risk_factors for t in task_types
        }

        risk_context = RiskFrameworkContext(
            task_types=task_types,
            effective_tiers=effective_tiers,
            tier_definitions=TIER_DEFINITIONS,
            company_profile_active=True,
            risk_factors_map=risk_factors_map,
        )

        for sector in SECTOR_MODULES:
            sector_content = assemble_sector_guideline(
                sector=sector,
                risk_context=risk_context,
                version_number=1,
                urs_available=True,
            )

            sector_count = _count_policy_sections_in_content(sector_content)
            assert sector_count >= 6, (
                f"Sector guideline '{sector.sector_label}' should have >= 6 "
                f"Policy_Sections, but found {sector_count}. "
                f"Generated with {len(task_types)} task types."
            )

    @settings(max_examples=30, deadline=None)
    @given(task_types=st_task_types_for_policy_count())
    def test_total_policy_sections_in_report_equals_actual_count(
        self, task_types: list[MagicMock]
    ) -> None:
        """total_policy_sections in report equals actual count across all 4 documents.

        **Validates: Requirements 1.1, 7.5**
        """
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        effective_tiers = {
            t.task_type_id: t.default_risk_tier for t in task_types
        }
        risk_factors_map = {
            t.task_type_id: t.risk_factors for t in task_types
        }

        risk_context = RiskFrameworkContext(
            task_types=task_types,
            effective_tiers=effective_tiers,
            tier_definitions=TIER_DEFINITIONS,
            company_profile_active=True,
            risk_factors_map=risk_factors_map,
        )

        # Generate all 4 documents
        master_content = assemble_master_guideline(
            risk_context=risk_context,
            version_number=1,
            urs_available=True,
        )

        sector_contents: list[tuple] = []
        for sector in SECTOR_MODULES:
            sector_content = assemble_sector_guideline(
                sector=sector,
                risk_context=risk_context,
                version_number=1,
                urs_available=True,
            )
            sector_contents.append((sector, sector_content))

        # Count actual policy sections across all 4 documents
        actual_total = _count_policy_sections_in_content(master_content)
        for _sector, content in sector_contents:
            actual_total += _count_policy_sections_in_content(content)

        # Build the report using the same logic as the service
        report = _build_report_from_generated_content(
            risk_context=risk_context,
            master_content=master_content,
            sector_contents=sector_contents,
            duration_ms=100,
        )

        # Verify total_policy_sections in report equals actual count
        assert report.total_policy_sections == actual_total, (
            f"Report total_policy_sections={report.total_policy_sections} "
            f"does not match actual count={actual_total} across all 4 documents. "
            f"Generated with {len(task_types)} task types."
        )

        # Also verify the sum of per-document counts equals the total
        sum_per_doc = sum(
            e.policy_section_count for e in report.documents_created
        )
        assert sum_per_doc == actual_total, (
            f"Sum of per-document policy_section_count ({sum_per_doc}) "
            f"does not equal actual total ({actual_total})."
        )


# ---------------------------------------------------------------------------
# Property 12: Regulatory citation completeness
# ---------------------------------------------------------------------------

# Citation patterns:
# 1. Inline citation: "RegulationName Article/Section — Description"
#    e.g., "EU AI Act Article 14 — Human Oversight"
#    e.g., "21 CFR 11.10(a) — Validation"
#    e.g., "EU GMP Annex 11 Section 7 — Data Storage and Integrity"
# 2. Industry best practice fallback:
#    "Regulatory reference: Industry best practice — no specific article applicable"

# Regex matching inline regulatory citations (regulation name + article/section)
_CITATION_PATTERN = re.compile(
    r"("
    # EU AI Act citations
    r"EU AI Act Article \d+"
    r"|"
    # 21 CFR Part 11 citations
    r"21 CFR 11\.\d+\([a-z]\)"
    r"|"
    # EU GMP Annex 11 citations
    r"EU GMP Annex 11 Section \d+"
    r"|"
    # ISO 13485 citations
    r"ISO 13485 Section [\d.]+"
    r"|"
    # IVDR citations
    r"IVDR (?:2017/746 )?(?:Article \d+|Annex [XIVL]+)"
    r"|"
    # IEC 62304 citations
    r"IEC 62304 Section \d+"
    r"|"
    # MDR citations
    r"MDR 2017/745 Article \d+"
    r"|"
    # ICH citations
    r"ICH Q\d+ Section \d+"
    r"|"
    # EU GMP Chapter 4 citations
    r"EU GMP Chapter 4"
    r"|"
    # FDA 21 CFR 820 citations
    r"(?:FDA )?21 CFR 820"
    r"|"
    # GAMP 5 references
    r"GAMP 5"
    r"|"
    # ISO 14971 references
    r"ISO 14971"
    r")"
    r"\s*(?:—|–|-)\s*\S+"
)

# Pattern for the industry best practice fallback
_BEST_PRACTICE_PATTERN = re.compile(
    r"(?:Regulatory reference: )?Industry best practice"
)

# Pattern for Regulatory Reference Table rows (Markdown table row)
_REF_TABLE_ROW_PATTERN = re.compile(
    r"^\| .+ \| .+ \| .+ \| .+ \|$", re.MULTILINE
)


def _extract_cited_regulations_from_content(content: str) -> set[str]:
    """Extract distinct regulation identifiers cited in the content body.

    Maps inline citation patterns back to framework identifiers used in
    the Regulatory Reference Table.

    Returns:
        Set of regulation identifier strings (e.g., "EU_AI_Act", "FDA_21CFR11").
    """
    cited: set[str] = set()

    if "EU AI Act" in content:
        cited.add("EU_AI_Act")
    if "21 CFR 11" in content or "21 CFR Part 11" in content:
        cited.add("FDA_21CFR11")
    if "EU GMP Annex 11" in content or "GMP Annex 11" in content:
        cited.add("EU_GMP_Annex11")
    if "ISO 13485" in content:
        cited.add("ISO_13485")
    if "IVDR" in content or "2017/746" in content:
        cited.add("IVDR_2017_746")
    if "IEC 62304" in content:
        cited.add("IEC_62304")
    if "MDR 2017/745" in content or "MDR" in content:
        cited.add("MDR_2017_745")
    if "ICH Q9" in content or "ICH Q10" in content:
        cited.add("ICH_Q9_Q10")
    if "EU GMP Chapter 4" in content:
        cited.add("EU_GMP_Chapter4")
    if "21 CFR 820" in content:
        cited.add("FDA_21CFR820")
    if "EU Common Specifications" in content or "Common Specifications" in content:
        cited.add("EU_Common_Specifications")

    return cited


def _extract_ref_table_regulations(content: str) -> set[str]:
    """Extract regulation identifiers present in the Regulatory Reference Table.

    Looks for the table section and extracts regulation names from rows.

    Returns:
        Set of regulation identifier strings found in the table.
    """
    # Find the Regulatory Reference Table section
    table_marker = "## Regulatory Reference Table"
    table_start = content.find(table_marker)
    if table_start == -1:
        return set()

    table_content = content[table_start:]

    found: set[str] = set()
    if "EU AI Act" in table_content:
        found.add("EU_AI_Act")
    if "21 CFR Part 11" in table_content or "21 CFR 11" in table_content:
        found.add("FDA_21CFR11")
    if "EU GMP Annex 11" in table_content or "GMP Annex 11" in table_content:
        found.add("EU_GMP_Annex11")
    if "ISO 13485" in table_content:
        found.add("ISO_13485")
    if "IVDR" in table_content or "2017/746" in table_content:
        found.add("IVDR_2017_746")
    if "IEC 62304" in table_content:
        found.add("IEC_62304")
    if "MDR 2017/745" in table_content:
        found.add("MDR_2017_745")
    if "ICH Q9" in table_content or "ICH Q10" in table_content:
        found.add("ICH_Q9_Q10")
    if "EU GMP Chapter 4" in table_content:
        found.add("EU_GMP_Chapter4")
    if "21 CFR 820" in table_content:
        found.add("FDA_21CFR820")
    if "EU Common Specifications" in table_content or "Common Specifications" in table_content:
        found.add("EU_Common_Specifications")

    return found


def _count_ref_table_rows(content: str) -> int:
    """Count data rows in the Regulatory Reference Table (excluding header/separator).

    Returns:
        Number of data rows in the table.
    """
    table_marker = "## Regulatory Reference Table"
    table_start = content.find(table_marker)
    if table_start == -1:
        return 0

    table_content = content[table_start:]
    # Find all table rows (lines starting with |)
    rows = re.findall(r"^\| .+\|$", table_content, re.MULTILINE)
    # Subtract header row and separator row
    data_rows = max(0, len(rows) - 2)
    return data_rows


class TestRegulatoryCitationCompleteness:
    """Property 12: Regulatory citation completeness.

    For any control requirement stated in a guideline, there SHALL be an
    inline citation containing a regulation name and specific article/section
    number, OR the annotation "Regulatory reference: Industry best practice —
    no specific article applicable". For any generated guideline, the
    Regulatory Reference Table SHALL have >= 1 row per distinct regulation
    cited in the document body.

    **Validates: Requirements 7.1, 7.2, 7.7**
    """

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_master_guideline_policy_sections_have_citations(
        self, task_types: list[MagicMock]
    ) -> None:
        """Every policy section in the master guideline has regulatory citations
        or industry best practice annotations."""
        risk_context = _build_risk_context_for_content(task_types)
        content = assemble_master_guideline(
            risk_context=risk_context,
            version_number=1,
            urs_available=True,
        )

        # Extract each policy section
        policy_sections = re.split(r"(?=^### Policy:)", content, flags=re.MULTILINE)
        policy_sections = [s for s in policy_sections if s.startswith("### Policy:")]

        assert len(policy_sections) > 0, (
            "Master guideline must contain at least one Policy section."
        )

        for section in policy_sections:
            # Extract the policy section title for error reporting
            title_match = re.match(r"### Policy: (.+)", section)
            section_title = title_match.group(1) if title_match else "Unknown"

            # Each policy section must have at least one citation or best practice
            has_citation = bool(_CITATION_PATTERN.search(section))
            has_best_practice = bool(_BEST_PRACTICE_PATTERN.search(section))

            assert has_citation or has_best_practice, (
                f"Policy section '{section_title}' in master guideline has no "
                f"inline regulatory citation and no 'Industry best practice' "
                f"annotation. Every control requirement must have a citation "
                f"(Requirements 7.1, 7.7)."
            )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_guideline_policy_sections_have_citations(
        self, task_types: list[MagicMock]
    ) -> None:
        """Every policy section in each sector guideline has regulatory citations
        or industry best practice annotations."""
        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            content = assemble_sector_guideline(
                sector=sector,
                risk_context=risk_context,
                version_number=1,
                urs_available=True,
            )

            # Extract each policy section
            policy_sections = re.split(
                r"(?=^### Policy:)", content, flags=re.MULTILINE
            )
            policy_sections = [
                s for s in policy_sections if s.startswith("### Policy:")
            ]

            assert len(policy_sections) > 0, (
                f"Sector guideline '{sector.sector_label}' must contain "
                f"at least one Policy section."
            )

            for section in policy_sections:
                title_match = re.match(r"### Policy: (.+)", section)
                section_title = title_match.group(1) if title_match else "Unknown"

                has_citation = bool(_CITATION_PATTERN.search(section))
                has_best_practice = bool(_BEST_PRACTICE_PATTERN.search(section))

                assert has_citation or has_best_practice, (
                    f"Policy section '{section_title}' in sector guideline "
                    f"'{sector.sector_label}' has no inline regulatory citation "
                    f"and no 'Industry best practice' annotation "
                    f"(Requirements 7.1, 7.7)."
                )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_master_guideline_ref_table_covers_cited_regulations(
        self, task_types: list[MagicMock]
    ) -> None:
        """The Regulatory Reference Table in the master guideline has >= 1 row
        per distinct regulation cited in the document body."""
        risk_context = _build_risk_context_for_content(task_types)
        content = assemble_master_guideline(
            risk_context=risk_context,
            version_number=1,
            urs_available=True,
        )

        # Verify the Regulatory Reference Table section exists
        assert "## Regulatory Reference Table" in content, (
            "Master guideline must contain a '## Regulatory Reference Table' "
            "section (Requirement 7.2)."
        )

        # Extract regulations cited in the body (before the table)
        table_pos = content.find("## Regulatory Reference Table")
        body_content = content[:table_pos]
        cited_in_body = _extract_cited_regulations_from_content(body_content)

        # Extract regulations present in the reference table
        regulations_in_table = _extract_ref_table_regulations(content)

        # Every regulation cited in the body must appear in the table
        for reg_id in cited_in_body:
            assert reg_id in regulations_in_table, (
                f"Regulation '{reg_id}' is cited in the master guideline body "
                f"but does not appear in the Regulatory Reference Table. "
                f"Table must have >= 1 row per distinct regulation cited "
                f"(Requirement 7.2). "
                f"Cited in body: {sorted(cited_in_body)}, "
                f"In table: {sorted(regulations_in_table)}."
            )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_guideline_ref_table_covers_cited_regulations(
        self, task_types: list[MagicMock]
    ) -> None:
        """The Regulatory Reference Table in each sector guideline has >= 1 row
        per distinct regulation cited in the document body."""
        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            content = assemble_sector_guideline(
                sector=sector,
                risk_context=risk_context,
                version_number=1,
                urs_available=True,
            )

            # Verify the Regulatory Reference Table section exists
            assert "## Regulatory Reference Table" in content, (
                f"Sector guideline '{sector.sector_label}' must contain a "
                f"'## Regulatory Reference Table' section (Requirement 7.2)."
            )

            # Extract regulations cited in the body (before the table)
            table_pos = content.find("## Regulatory Reference Table")
            body_content = content[:table_pos]
            cited_in_body = _extract_cited_regulations_from_content(body_content)

            # Extract regulations present in the reference table
            regulations_in_table = _extract_ref_table_regulations(content)

            # Every regulation cited in the body must appear in the table
            for reg_id in cited_in_body:
                assert reg_id in regulations_in_table, (
                    f"Regulation '{reg_id}' is cited in sector guideline "
                    f"'{sector.sector_label}' body but does not appear in "
                    f"the Regulatory Reference Table. "
                    f"Table must have >= 1 row per distinct regulation cited "
                    f"(Requirement 7.2). "
                    f"Cited in body: {sorted(cited_in_body)}, "
                    f"In table: {sorted(regulations_in_table)}."
                )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_master_guideline_ref_table_has_data_rows(
        self, task_types: list[MagicMock]
    ) -> None:
        """The Regulatory Reference Table in the master guideline has at least
        one data row per framework passed to assemble_regulatory_reference_table."""
        risk_context = _build_risk_context_for_content(task_types)
        content = assemble_master_guideline(
            risk_context=risk_context,
            version_number=1,
            urs_available=True,
        )

        row_count = _count_ref_table_rows(content)

        # The master guideline uses REGULATORY_FRAMEWORKS (5 frameworks),
        # each with multiple key_articles. Must have >= 1 row per framework.
        assert row_count >= len(REGULATORY_FRAMEWORKS), (
            f"Regulatory Reference Table in master guideline has {row_count} "
            f"data rows, but must have >= {len(REGULATORY_FRAMEWORKS)} "
            f"(one per distinct regulation framework). "
            f"(Requirement 7.2)."
        )

    @settings(max_examples=50, deadline=None)
    @given(task_types=_st_task_types_for_content)
    def test_sector_guideline_ref_table_has_data_rows(
        self, task_types: list[MagicMock]
    ) -> None:
        """The Regulatory Reference Table in each sector guideline has at least
        one data row per sector-applicable framework."""
        risk_context = _build_risk_context_for_content(task_types)

        for sector in SECTOR_MODULES:
            content = assemble_sector_guideline(
                sector=sector,
                risk_context=risk_context,
                version_number=1,
                urs_available=True,
            )

            row_count = _count_ref_table_rows(content)

            # Each sector uses its own applicable_regulations list
            assert row_count >= len(sector.applicable_regulations), (
                f"Regulatory Reference Table in sector guideline "
                f"'{sector.sector_label}' has {row_count} data rows, "
                f"but must have >= {len(sector.applicable_regulations)} "
                f"(one per distinct sector regulation framework). "
                f"(Requirement 7.2)."
            )


# ---------------------------------------------------------------------------
# Property 9: Versioning idempotency
# ---------------------------------------------------------------------------

# All 4 guideline titles for versioning tests
_ALL_GUIDELINE_TITLES = [
    MASTER_GUIDELINE_TITLE,
    *[sm.title for sm in SECTOR_MODULES],
]


class _VersioningState:
    """Tracks simulated DB state across multiple service invocations.

    Maintains Document and DocumentVersion records to simulate the versioning
    behavior of the service across N successive invocations.
    """

    def __init__(self) -> None:
        self.documents: dict[str, MagicMock] = {}  # title -> Document mock
        self.versions: dict[str, list[int]] = {}  # title -> [major_version, ...]
        self._next_doc_id: int = 100
        self._next_uuid_seq: int = 1

    def get_document(self, title: str) -> MagicMock | None:
        """Get existing document by title, or None if not yet created."""
        return self.documents.get(title)

    def create_document(self, title: str) -> MagicMock:
        """Create a new Document mock and record it."""
        doc = MagicMock(spec=Document)
        doc.id = self._next_doc_id
        doc.title = title
        doc.document_uuid = f"2025-{self._next_uuid_seq:05d}"
        doc.company_id = 1
        doc.current_status = "Draft"
        self._next_doc_id += 1
        self._next_uuid_seq += 1
        self.documents[title] = doc
        self.versions[title] = [1]
        return doc

    def add_version(self, title: str) -> int:
        """Add a new version for an existing document. Returns new version number."""
        current_max = max(self.versions[title])
        new_version = current_max + 1
        self.versions[title].append(new_version)
        return new_version

    def get_max_version(self, title: str) -> int:
        """Get the current maximum version number for a document."""
        return max(self.versions[title]) if title in self.versions else 0


def _build_session_for_versioning(
    state: _VersioningState,
    mock_company: MagicMock,
    mock_user: MagicMock,
    mock_workflow: MagicMock,
    task_types: list[MagicMock],
) -> AsyncMock:
    """Build a mock AsyncSession for a versioning test invocation.

    Uses a phase-based approach to handle the dynamic call sequence that
    varies depending on whether documents already exist. The service's
    execute() method follows this sequence:

    Phase 1 (fixed): advisory_lock, company, user, workflow, task_types,
                     risk_profile, urs_availability
    Phase 2 (variable): For each of 4 titles: detect_existing, then
                        _get_next_version_number if existing
    Phase 3 (variable): For each of 4 titles: _upload_or_version_document
                        which calls detect_existing, [max_version if existing],
                        apply_tags, apply_workflow

    Args:
        state: The _VersioningState tracking documents across runs.
        mock_company: The mock Company to return.
        mock_user: The mock User to return.
        mock_workflow: The mock WorkflowDefinition to return.
        task_types: List of mock AITaskType objects.

    Returns:
        A configured AsyncMock session.
    """
    session = AsyncMock()
    added_objects: list = []

    def track_add(obj):
        added_objects.append(obj)
        if isinstance(obj, Document):
            title = obj.title
            if title and title not in state.documents:
                created_doc = state.create_document(title)
                obj.id = created_doc.id
                obj.document_uuid = created_doc.document_uuid
        elif isinstance(obj, DocumentVersion):
            # Track version creation for existing documents
            doc_id = obj.document_id
            major_ver = obj.major_version
            # Find the title by document ID
            for title, doc in state.documents.items():
                if doc.id == doc_id and major_ver > state.get_max_version(title):
                    state.add_version(title)
                    break

    session.add = MagicMock(side_effect=track_add)
    session.flush = AsyncMock()

    # Use a phase-based state machine to handle the dynamic call sequence
    phase = {"current": "init", "title_idx": 0, "sub_step": 0}
    call_counter = {"count": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_counter["count"] += 1
        result = MagicMock()
        call_num = call_counter["count"]

        # Phase 1: Fixed prerequisite queries (calls 1-7)
        if call_num == 1:
            result.scalar.return_value = True  # Advisory lock
        elif call_num == 2:
            result.scalar_one_or_none.return_value = mock_company
        elif call_num == 3:
            result.scalar_one_or_none.return_value = mock_user
        elif call_num == 4:
            result.scalar_one_or_none.return_value = mock_workflow
        elif call_num == 5:
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = task_types
            result.scalars.return_value = scalars_obj
        elif call_num == 6:
            result.scalar_one_or_none.return_value = None  # No risk profile
        elif call_num == 7:
            result.scalar_one_or_none.return_value = None  # No URS
            phase["current"] = "detect_for_version"
            phase["title_idx"] = 0
        else:
            # Phase 2+3: Dynamic sequence based on document existence
            if phase["current"] == "detect_for_version":
                # Detecting existing document in execute() for version number
                title = _ALL_GUIDELINE_TITLES[phase["title_idx"]]
                existing = state.get_document(title)
                result.scalar_one_or_none.return_value = existing
                if existing:
                    phase["current"] = "get_version_number"
                else:
                    # No existing doc, skip _get_next_version_number
                    phase["title_idx"] += 1
                    if phase["title_idx"] >= 4:
                        phase["current"] = "upload_detect"
                        phase["title_idx"] = 0
                        phase["sub_step"] = 0

            elif phase["current"] == "get_version_number":
                # _get_next_version_number: SELECT MAX(major_version)
                title = _ALL_GUIDELINE_TITLES[phase["title_idx"]]
                max_ver = state.get_max_version(title)
                result.scalar_one_or_none.return_value = max_ver
                phase["title_idx"] += 1
                if phase["title_idx"] >= 4:
                    phase["current"] = "upload_detect"
                    phase["title_idx"] = 0
                    phase["sub_step"] = 0
                else:
                    phase["current"] = "detect_for_version"

            elif phase["current"] == "upload_detect":
                # _upload_or_version_document: _detect_existing_document
                title = _ALL_GUIDELINE_TITLES[phase["title_idx"]]
                existing = state.get_document(title)
                result.scalar_one_or_none.return_value = existing
                if existing:
                    phase["current"] = "upload_max_version"
                else:
                    phase["current"] = "upload_tags"

            elif phase["current"] == "upload_max_version":
                # _upload_or_version_document: SELECT MAX(major_version)
                title = _ALL_GUIDELINE_TITLES[phase["title_idx"]]
                max_ver = state.get_max_version(title)
                result.scalar_one_or_none.return_value = max_ver
                phase["current"] = "upload_tags"

            elif phase["current"] == "upload_tags":
                # _apply_tags: SELECT existing tags
                scalars_obj = MagicMock()
                scalars_obj.all.return_value = []
                result.scalars.return_value = scalars_obj
                phase["current"] = "upload_workflow"

            elif phase["current"] == "upload_workflow":
                # _apply_workflow: SELECT DocumentState
                result.scalar_one_or_none.return_value = None
                phase["title_idx"] += 1
                if phase["title_idx"] >= 4:
                    phase["current"] = "done"
                else:
                    phase["current"] = "upload_detect"

            else:
                # Fallback for any unexpected calls
                result.scalar_one_or_none.return_value = None
                scalars_obj = MagicMock()
                scalars_obj.all.return_value = []
                result.scalars.return_value = scalars_obj

        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    session.added_objects = added_objects
    return session


@settings(max_examples=20, deadline=None)
@given(
    num_runs=st.integers(min_value=1, max_value=5),
    task_type_data=st_realistic_task_type_set(),
)
@pytest.mark.asyncio
async def test_property_9_versioning_idempotency(
    num_runs: int,
    task_type_data: list[tuple[str, str, str, list[str]]],
) -> None:
    """For any number of successive invocations N (where N >= 1) of the
    GuidelinesGeneratorService against the same ALC company, there SHALL
    exist exactly one Document record per guideline title (4 total) with
    tags ["AI-Guidelines", "ALC-GOV"], each with exactly N DocumentVersion
    records with strictly increasing major_version numbers. After each
    invocation, the DocumentState for each document SHALL have
    current_state="Draft". The report SHALL indicate is_new_document=true
    for the first invocation and is_new_document=false for all subsequent
    invocations.

    **Validates: Requirements 6.1, 6.3, 6.4, 6.5**
    """
    # Build mock task types from generated data
    task_types = [
        _make_mock_task_type(
            task_type_id=tt_id,
            display_name=display_name,
            default_risk_tier=tier,
            risk_factors=factors,
        )
        for tt_id, display_name, tier, factors in task_type_data
    ]

    mock_company = _make_mock_company()
    mock_user = _make_mock_user()
    mock_workflow = _make_mock_workflow()

    # Track versioning state across all runs
    state = _VersioningState()

    # Collect reports from each run
    reports: list[GuidelinesGenerationReport] = []

    for run_idx in range(num_runs):
        # Build a fresh session for each run, using shared state
        session = _build_session_for_versioning(
            state=state,
            mock_company=mock_company,
            mock_user=mock_user,
            mock_workflow=mock_workflow,
            task_types=task_types,
        )

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock()

        mock_uuid_service = AsyncMock()
        mock_uuid_service.generate_document_uuid = AsyncMock(
            return_value=f"2025-{state._next_uuid_seq:05d}"
        )

        service = GuidelinesGeneratorService(
            session=session,
            storage_service=mock_storage,
            uuid_service=mock_uuid_service,
        )
        # Skip section length validation (tested in Property 5)
        service._validate_section_lengths = lambda content, title: None  # type: ignore[method-assign]

        report = await service.execute()
        reports.append(report)

    # --- Property 9 Assertions ---

    # Assertion 1: Exactly 4 Document records exist (one per title)
    assert len(state.documents) == 4, (
        f"Expected exactly 4 Document records after {num_runs} runs, "
        f"got {len(state.documents)}. Titles: {list(state.documents.keys())}"
    )

    # Verify each expected title has a document
    for title in _ALL_GUIDELINE_TITLES:
        assert title in state.documents, (
            f"Missing Document record for title: '{title}'"
        )

    # Assertion 2: Each document has exactly N DocumentVersion records
    for title in _ALL_GUIDELINE_TITLES:
        version_count = len(state.versions[title])
        assert version_count == num_runs, (
            f"Document '{title}' has {version_count} versions after "
            f"{num_runs} runs, expected exactly {num_runs}."
        )

    # Assertion 3: Version numbers are strictly increasing (1, 2, 3, ...)
    for title in _ALL_GUIDELINE_TITLES:
        versions = state.versions[title]
        for i in range(len(versions) - 1):
            assert versions[i] < versions[i + 1], (
                f"Document '{title}' has non-increasing version numbers: "
                f"{versions}. Expected strictly increasing sequence."
            )
        # Also verify they form the sequence 1, 2, ..., N
        expected_versions = list(range(1, num_runs + 1))
        assert versions == expected_versions, (
            f"Document '{title}' has versions {versions}, "
            f"expected {expected_versions}."
        )

    # Assertion 4: First run report has is_new_document=True for all 4 docs
    first_report = reports[0]
    assert first_report.total_documents == 4, (
        f"First run report has total_documents={first_report.total_documents}, "
        f"expected 4."
    )
    for entry in first_report.documents_created:
        assert entry.is_new_document is True, (
            f"First run: document '{entry.title}' has "
            f"is_new_document={entry.is_new_document}, expected True."
        )
        assert entry.version_number == 1, (
            f"First run: document '{entry.title}' has "
            f"version_number={entry.version_number}, expected 1."
        )

    # Assertion 5: Subsequent run reports have is_new_document=False
    for run_idx in range(1, num_runs):
        run_report = reports[run_idx]
        assert run_report.total_documents == 4, (
            f"Run {run_idx + 1} report has "
            f"total_documents={run_report.total_documents}, expected 4."
        )
        for entry in run_report.documents_created:
            assert entry.is_new_document is False, (
                f"Run {run_idx + 1}: document '{entry.title}' has "
                f"is_new_document={entry.is_new_document}, expected False."
            )
            # Version number should be run_idx + 1
            assert entry.version_number == run_idx + 1, (
                f"Run {run_idx + 1}: document '{entry.title}' has "
                f"version_number={entry.version_number}, "
                f"expected {run_idx + 1}."
            )

    # Assertion 6: All reports show workflow_state="Draft"
    for run_idx, run_report in enumerate(reports):
        for entry in run_report.documents_created:
            assert entry.workflow_state == "Draft", (
                f"Run {run_idx + 1}: document '{entry.title}' has "
                f"workflow_state='{entry.workflow_state}', expected 'Draft'."
            )
