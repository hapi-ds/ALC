"""Property-based tests for URS Generator Service (Step 8.3).

Tests correctness properties from the Step_8-3 design document, validating
the URSGeneratorService behavior for document generation, versioning,
and governance workflow application.

References:
    - Design: .kiro/specs/Step_8-3_urs-alc-corporate/design.md
    - Requirements: .kiro/specs/Step_8-3_urs-alc-corporate/requirements.md
"""

import re
from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.schemas.urs_generation import URSGenerationReport
from alcoabase.services.urs_content import (
    URS_CONTENT,
    URS_DOCUMENT_TITLE,
    URS_TAGS,
)
from alcoabase.services.urs_generator_service import URSGeneratorService


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


def _build_session_for_invocation(
    mock_company: MagicMock,
    mock_user: MagicMock,
    mock_workflow: MagicMock,
    existing_document: MagicMock | None,
    current_max_version: int | None,
    added_objects: list,
) -> AsyncMock:
    """Build a mock AsyncSession configured for a single service invocation.

    Args:
        mock_company: The mock Company to return from prerequisite queries.
        mock_user: The mock User to return from prerequisite queries.
        mock_workflow: The mock WorkflowDefinition to return.
        existing_document: The existing Document if this is a subsequent
            invocation, or None for the first invocation.
        current_max_version: The current max major_version if document exists.
        added_objects: Mutable list to track objects added to the session.

    Returns:
        A configured AsyncMock session.
    """
    session = AsyncMock()

    def track_add(obj):
        added_objects.append(obj)
        # Simulate DB ID assignment for Document objects
        if isinstance(obj, Document):
            obj.id = 100
            obj.document_uuid = "2025-00001"

    session.add = MagicMock(side_effect=track_add)
    session.flush = AsyncMock()

    # Track query sequence
    call_counter = {"count": 0}
    is_new = existing_document is None

    async def mock_execute(stmt):
        call_counter["count"] += 1
        result = MagicMock()
        call_num = call_counter["count"]

        if is_new:
            # New document path queries:
            # 1. Company, 2. User, 3. Workflow, 4. Detect existing (None)
            # 5. Apply tags (empty), 6. Apply workflow (None)
            if call_num == 1:
                result.scalar_one_or_none.return_value = mock_company
            elif call_num == 2:
                result.scalar_one_or_none.return_value = mock_user
            elif call_num == 3:
                result.scalar_one_or_none.return_value = mock_workflow
            elif call_num == 4:
                result.scalar_one_or_none.return_value = None
            elif call_num == 5:
                # apply_tags: SELECT existing tags → empty
                scalars_obj = MagicMock()
                scalars_obj.all.return_value = []
                result.scalars.return_value = scalars_obj
            elif call_num == 6:
                # apply_workflow: SELECT DocumentState → None
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
        else:
            # Existing document path queries:
            # 1. Company, 2. User, 3. Workflow, 4. Detect existing (doc)
            # 5. MAX(major_version), 6. Apply tags (existing), 7. Apply workflow (existing state)
            if call_num == 1:
                result.scalar_one_or_none.return_value = mock_company
            elif call_num == 2:
                result.scalar_one_or_none.return_value = mock_user
            elif call_num == 3:
                result.scalar_one_or_none.return_value = mock_workflow
            elif call_num == 4:
                result.scalar_one_or_none.return_value = existing_document
            elif call_num == 5:
                # _get_next_version_number: MAX(major_version)
                result.scalar_one_or_none.return_value = current_max_version
            elif call_num == 6:
                # apply_tags: tags already present
                mock_tag_urs = MagicMock(spec=DocumentTag)
                mock_tag_urs.tag = "URS"
                mock_tag_gov = MagicMock(spec=DocumentTag)
                mock_tag_gov.tag = "ALC-GOV"
                scalars_obj = MagicMock()
                scalars_obj.all.return_value = [mock_tag_urs, mock_tag_gov]
                result.scalars.return_value = scalars_obj
            elif call_num == 7:
                # apply_workflow: existing DocumentState
                existing_state = MagicMock(spec=DocumentState)
                existing_state.current_state = "Approved"
                existing_state.workflow_id = mock_workflow.id
                existing_state.updated_by = mock_user.id
                result.scalar_one_or_none.return_value = existing_state
            else:
                result.scalar_one_or_none.return_value = None

        return result

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


# ---------------------------------------------------------------------------
# Property 4: Versioning idempotency
# ---------------------------------------------------------------------------


# Feature: Step_8-3_urs-alc-corporate, Property 4: Versioning idempotency
@settings(max_examples=20, deadline=None)
@given(n=st.integers(min_value=1, max_value=5))
@pytest.mark.asyncio
async def test_property_4_versioning_idempotency(n: int) -> None:
    """For any number of successive invocations N (where N >= 1) of the
    URSGeneratorService against the same ALC company, there SHALL exist
    exactly one Document record with tags ["URS", "ALC-GOV"], exactly N
    DocumentVersion records with strictly increasing major_version numbers,
    and the DocumentState SHALL have current_state="Draft" after each
    invocation. The URSGenerationReport SHALL report is_new_document=True
    for the first invocation and is_new_document=False for all subsequent.

    **Validates: Requirements 1.6, 7.1, 7.4, 7.5**
    """
    # Setup shared mock prerequisites
    mock_company = _make_mock_company()
    mock_user = _make_mock_user()
    mock_workflow = _make_mock_workflow()
    mock_storage = AsyncMock()
    mock_storage.upload_file = AsyncMock()
    mock_uuid_service = AsyncMock()
    mock_uuid_service.generate_document_uuid = AsyncMock(return_value="2025-00001")

    # Accumulate state across invocations
    documents_created: list[Document] = []
    versions_created: list[DocumentVersion] = []
    reports = []
    the_document: MagicMock | None = None

    for invocation in range(n):
        added_objects: list = []

        # Build session configured for this invocation's state
        session = _build_session_for_invocation(
            mock_company=mock_company,
            mock_user=mock_user,
            mock_workflow=mock_workflow,
            existing_document=the_document,
            current_max_version=invocation if invocation > 0 else None,
            added_objects=added_objects,
        )

        # Create and run the service
        service = URSGeneratorService(
            session=session,
            storage_service=mock_storage,
            uuid_service=mock_uuid_service,
        )

        report = await service.execute()
        reports.append(report)

        # Capture created objects
        for obj in added_objects:
            if isinstance(obj, Document):
                documents_created.append(obj)
                the_document = obj
            elif isinstance(obj, DocumentVersion):
                versions_created.append(obj)

    # --- Property 4 Assertions ---

    # Assertion 1: Exactly one Document record created (first invocation only)
    assert len(documents_created) == 1, (
        f"Expected exactly 1 Document created across {n} invocations, "
        f"got {len(documents_created)}. Versioning should reuse the existing document."
    )

    # Assertion 2: Exactly N DocumentVersion records created
    assert len(versions_created) == n, (
        f"Expected exactly {n} DocumentVersion records for {n} invocations, "
        f"got {len(versions_created)}. Each invocation should create one version."
    )

    # Assertion 3: Versions have strictly increasing major_version numbers (1, 2, ..., N)
    version_numbers = [v.major_version for v in versions_created]
    expected_versions = list(range(1, n + 1))
    assert version_numbers == expected_versions, (
        f"Expected strictly increasing versions {expected_versions}, "
        f"got {version_numbers}."
    )

    # Assertion 4: DocumentState current_state is "Draft" after each invocation
    for i, report in enumerate(reports):
        assert report.workflow_state == "Draft", (
            f"Invocation {i + 1}: expected workflow_state='Draft', "
            f"got '{report.workflow_state}'."
        )

    # Assertion 5: is_new_document=True for first, False for subsequent
    assert reports[0].is_new_document is True, (
        "First invocation should report is_new_document=True."
    )
    for i in range(1, n):
        assert reports[i].is_new_document is False, (
            f"Invocation {i + 1} should report is_new_document=False, "
            f"got {reports[i].is_new_document}."
        )

    # Assertion 6: Tags are always ["URS", "ALC-GOV"] in the report
    for i, report in enumerate(reports):
        assert set(report.tags_applied) == {"URS", "ALC-GOV"}, (
            f"Invocation {i + 1}: expected tags ['URS', 'ALC-GOV'], "
            f"got {report.tags_applied}."
        )


# ---------------------------------------------------------------------------
# Helpers for Property 5
# ---------------------------------------------------------------------------


def _count_requirements_from_content(content: str) -> int:
    """Independently count distinct REQ-IDs in URS_CONTENT."""
    return len(set(re.findall(r"REQ-[A-Z]+-\d{2,}", content)))


def _count_modules_from_content(content: str) -> int:
    """Independently count module headings (## N. ...) in URS_CONTENT."""
    return len(re.findall(r"^## \d+\.\s+", content, re.MULTILINE))


def _make_mock_session_for_report(document_id: int, document_uuid: str) -> AsyncMock:
    """Create a mock AsyncSession that simulates a successful first execution.

    The mock session handles:
    - Prerequisites queries (company, user, workflow)
    - Existing document detection (returns None = new document)
    - Document creation with flush assigning IDs
    - Tag application (no existing tags)
    - Workflow application (no existing state)

    Args:
        document_id: The ID to assign to the created document.
        document_uuid: The UUID to assign to the created document.

    Returns:
        A configured mock AsyncSession.
    """
    session = AsyncMock()
    added_entities: list = []

    def _track_add(entity):
        added_entities.append(entity)
        # Simulate flush assigning IDs to Document objects
        if hasattr(entity, "document_uuid") and hasattr(entity, "title") and hasattr(entity, "folder_path"):
            entity.id = document_id
            entity.document_uuid = document_uuid

    session.add = MagicMock(side_effect=_track_add)
    session._added_entities = added_entities
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # Build mock entities for prerequisites
    mock_company = MagicMock()
    mock_company.id = 1
    mock_company.slug = "alc-corporate"

    mock_user = MagicMock()
    mock_user.id = 10
    mock_user.username = "alc-doc-admin"

    mock_workflow = MagicMock()
    mock_workflow.id = 5
    mock_workflow.name = "ALC Governance Document Lifecycle"
    mock_workflow.document_tag = "ALC-GOV"
    mock_workflow.company_id = 1

    call_count = {"n": 0}

    async def mock_execute(stmt):
        call_count["n"] += 1
        n = call_count["n"]

        mock_result = MagicMock()

        if n == 1:
            # Company query
            mock_result.scalar_one_or_none.return_value = mock_company
        elif n == 2:
            # User query
            mock_result.scalar_one_or_none.return_value = mock_user
        elif n == 3:
            # Workflow query
            mock_result.scalar_one_or_none.return_value = mock_workflow
        elif n == 4:
            # Detect existing document — None means new document
            mock_result.scalar_one_or_none.return_value = None
        elif n == 5:
            # Apply tags — existing tags query (empty = no existing tags)
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = []
            mock_result.scalars.return_value = mock_scalars
        elif n == 6:
            # Apply workflow — existing state query (None = create new)
            mock_result.scalar_one_or_none.return_value = None
        else:
            mock_result.scalar_one_or_none.return_value = None

        return mock_result

    session.execute = AsyncMock(side_effect=mock_execute)

    return session


# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 5
# ---------------------------------------------------------------------------

# Strategy: generate plausible document IDs (positive integers)
st_document_ids = st.integers(min_value=1, max_value=100_000)

# Strategy: generate plausible document UUIDs in YYYY-NNNNN format
st_document_uuids = st.from_regex(r"^20[2-3][0-9]-[0-9]{5}$", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 5: Report accuracy
# ---------------------------------------------------------------------------


# Feature: Step_8-3_urs-alc-corporate, Property 5: Report accuracy
@settings(max_examples=100, deadline=None)
@given(
    document_id=st_document_ids,
    document_uuid=st_document_uuids,
)
@pytest.mark.asyncio
async def test_property_5_report_accuracy(
    document_id: int,
    document_uuid: str,
) -> None:
    """For any successful execution of the URSGeneratorService, the returned
    URSGenerationReport SHALL contain: a document_id matching the persisted
    Document's ID, a document_uuid matching the Document's UUID,
    tags_applied equal to ["URS", "ALC-GOV"], workflow_state equal to "Draft",
    requirement_count equal to the actual number of distinct Requirement_IDs
    in the generated content, and module_count equal to the actual number of
    requirement modules.

    **Validates: Requirements 6.4**
    """
    # Create mock session simulating successful first execution
    session = _make_mock_session_for_report(document_id, document_uuid)

    # Create mock storage and UUID services
    mock_storage = AsyncMock()
    mock_storage.upload_file = AsyncMock()

    mock_uuid_service = AsyncMock()
    mock_uuid_service.generate_document_uuid = AsyncMock(return_value=document_uuid)

    # Create the service and execute
    service = URSGeneratorService(
        session=session,
        storage_service=mock_storage,
        uuid_service=mock_uuid_service,
    )

    report = await service.execute()

    # --- Verify Property 5: Report accuracy ---

    # Assertion 1: document_id matches the persisted Document's ID
    assert report.document_id == document_id, (
        f"report.document_id={report.document_id} does not match "
        f"expected document_id={document_id}"
    )

    # Assertion 2: document_uuid matches the Document's UUID
    assert report.document_uuid == document_uuid, (
        f"report.document_uuid={report.document_uuid} does not match "
        f"expected document_uuid={document_uuid}"
    )

    # Assertion 3: document_title matches expected title
    assert report.document_title == URS_DOCUMENT_TITLE, (
        f"report.document_title={report.document_title!r} does not match "
        f"expected title={URS_DOCUMENT_TITLE!r}"
    )

    # Assertion 4: tags_applied equals ["URS", "ALC-GOV"]
    assert report.tags_applied == ["URS", "ALC-GOV"], (
        f"report.tags_applied={report.tags_applied} does not match "
        f"expected ['URS', 'ALC-GOV']"
    )

    # Assertion 5: workflow_state equals "Draft"
    assert report.workflow_state == "Draft", (
        f"report.workflow_state={report.workflow_state!r} does not match "
        f"expected 'Draft'"
    )

    # Assertion 6: requirement_count matches actual distinct REQ-IDs in content
    expected_req_count = _count_requirements_from_content(URS_CONTENT)
    assert report.requirement_count == expected_req_count, (
        f"report.requirement_count={report.requirement_count} does not match "
        f"actual distinct REQ-IDs in URS_CONTENT={expected_req_count}"
    )

    # Assertion 7: module_count matches actual module count from URS_CONTENT
    expected_module_count = _count_modules_from_content(URS_CONTENT)
    assert report.module_count == expected_module_count, (
        f"report.module_count={report.module_count} does not match "
        f"actual module headings in URS_CONTENT={expected_module_count}"
    )

    # Assertion 8: is_new_document is True for first run (no existing document)
    assert report.is_new_document is True, (
        f"report.is_new_document={report.is_new_document} should be True "
        f"for first run (new document creation)"
    )

    # Assertion 9: total_duration_ms is non-negative
    assert report.total_duration_ms >= 0, (
        f"report.total_duration_ms={report.total_duration_ms} should be >= 0"
    )
