"""Unit tests for DocumentationGeneratorService — document operations and report building.

Tests cover Task 7.3:
- detect_existing_document (found / not found)
- upload_or_version (new document / existing document versioning)
- apply_tags (creates both tags / no duplicates on re-run)
- apply_workflow (creates Draft state / resets to Draft on new version)
- Report building (2 entries, is_new_document flags, section/procedure/screenshot counts,
  cross_references_included flags, total_duration_ms)

References:
    - Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
    - Design: .kiro/specs/Step_8-5_documentation-suite-user-admin-guides/design.md
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.schemas.documentation_generation import (
    CrossReferenceSummary,
    DocumentationGenerationReport,
    DocumentReportEntry,
)
from alcoabase.services.documentation_content import (
    ADMIN_GUIDE_TITLE,
    DOCUMENTATION_DOCUMENT_TYPE,
    DOCUMENTATION_TAGS,
    USER_GUIDE_TITLE,
)
from alcoabase.services.documentation_generator_service import (
    DocumentationGeneratorService,
)


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
    id_: int = 100,
    company_id: int = 1,
    uuid: str = "2025-00042",
    title: str = USER_GUIDE_TITLE,
) -> MagicMock:
    """Create a Document instance for testing."""
    doc = MagicMock(spec=Document)
    doc.id = id_
    doc.document_uuid = uuid
    doc.title = title
    doc.company_id = company_id
    doc.current_status = "Draft"
    return doc


# ---------------------------------------------------------------------------
# Task 7.3: detect_existing_document Tests
# ---------------------------------------------------------------------------


class TestDetectExistingDocumentFound:
    """Test: detect_existing_document returns Document when found.

    Validates: Requirements 3.1, 5.1
    """

    @pytest.mark.asyncio
    async def test_returns_document_when_found(self, async_session: AsyncMock):
        """Returns existing Document when title + tags + company_id match."""
        company = _make_company()
        existing_doc = _make_document(id_=100, company_id=company.id)

        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(existing_doc)
        )

        service = DocumentationGeneratorService(async_session)
        result = await service._detect_existing_document(
            USER_GUIDE_TITLE, company
        )

        assert result is existing_doc
        assert result.id == 100
        assert result.title == USER_GUIDE_TITLE


class TestDetectExistingDocumentNotFound:
    """Test: detect_existing_document returns None when not found.

    Validates: Requirements 3.1, 5.1
    """

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, async_session: AsyncMock):
        """Returns None when no document with matching title + tags exists."""
        company = _make_company()

        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        service = DocumentationGeneratorService(async_session)
        result = await service._detect_existing_document(
            USER_GUIDE_TITLE, company
        )

        assert result is None


# ---------------------------------------------------------------------------
# Task 7.3: upload_or_version — New Document Tests
# ---------------------------------------------------------------------------


class TestUploadOrVersionNewDocument:
    """Test: upload_or_version new document has correct attributes.

    Validates: Requirements 3.1, 3.4, 3.5, 5.2, 5.3
    """

    @pytest.mark.asyncio
    async def test_new_document_attributes(self, async_session: AsyncMock):
        """New document has correct title, type, company_id, created_by, UUID."""
        company = _make_company(id_=1)
        doc_admin = _make_doc_admin(id_=10)
        workflow = _make_workflow(id_=5)
        content = "# User Guide\n\n## Getting Started\n\nTest content."

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

        # Mock execute calls in order:
        # 1. _detect_existing_document → None (new document)
        # 2. _apply_tags query → no existing tags
        # 3. _apply_workflow query → no existing state
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_scalar_one_or_none(None)
            if call_count == 2:
                return _mock_scalars_all([])
            if call_count == 3:
                return _mock_scalar_one_or_none(None)
            return _mock_scalar_one_or_none(None)

        async_session.execute = AsyncMock(side_effect=mock_execute)

        service = DocumentationGeneratorService(
            async_session,
            storage_service=mock_storage,
            uuid_service=mock_uuid,
        )
        result = await service._upload_or_version_document(
            USER_GUIDE_TITLE, content, "user_guide", company, doc_admin, workflow
        )

        # Verify result attributes
        assert result.title == USER_GUIDE_TITLE
        assert result.is_new_document is True
        assert result.version_number == 1
        assert result.workflow_state == "Draft"
        assert result.tags_applied == DOCUMENTATION_TAGS

        # Verify UUID format (YYYY-NNNNN)
        assert re.match(r"\d{4}-\d{5}", result.document_uuid)

        # Verify Document was created with correct attributes
        doc_objects = [o for o in added_objects if isinstance(o, Document)]
        assert len(doc_objects) == 1
        doc = doc_objects[0]
        assert doc.title == USER_GUIDE_TITLE
        assert doc.document_type == DOCUMENTATION_DOCUMENT_TYPE
        assert doc.company_id == company.id
        assert doc.created_by == doc_admin.id
        assert doc.document_uuid == "2025-00099"


# ---------------------------------------------------------------------------
# Task 7.3: upload_or_version — Existing Document Version Tests
# ---------------------------------------------------------------------------


class TestUploadOrVersionExistingDocument:
    """Test: upload_or_version existing document increments major_version.

    Validates: Requirements 5.1, 5.4, 5.5, 5.6
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
        content = "# User Guide v2\n\n## Getting Started\n\nUpdated content."

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
                existing_tag1.tag = "DOC-GUIDE"
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

        service = DocumentationGeneratorService(
            async_session,
            storage_service=mock_storage,
        )
        result = await service._upload_or_version_document(
            USER_GUIDE_TITLE, content, "user_guide", company, doc_admin, workflow
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
    """Test: apply_tags creates both "DOC-GUIDE" and "ALC-GOV" tags on new document.

    Validates: Requirements 3.2
    """

    @pytest.mark.asyncio
    async def test_creates_both_tags_on_new_document(
        self, async_session: AsyncMock
    ):
        """Both DOC-GUIDE and ALC-GOV tags created for a new document."""
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

        service = DocumentationGeneratorService(async_session)
        tags_applied = await service._apply_tags(document, is_new=True)

        # Verify both tags were applied
        assert tags_applied == ["DOC-GUIDE", "ALC-GOV"]

        # Verify DocumentTag objects were created
        tag_objects = [o for o in added_objects if isinstance(o, DocumentTag)]
        assert len(tag_objects) == 2

        tag_values = {t.tag for t in tag_objects}
        assert tag_values == {"DOC-GUIDE", "ALC-GOV"}

        for tag_obj in tag_objects:
            assert tag_obj.document_id == document.id


class TestApplyTagsNoDuplicates:
    """Test: apply_tags does not duplicate on re-run.

    Validates: Requirements 3.2, 5.1
    """

    @pytest.mark.asyncio
    async def test_no_duplicate_tags_on_rerun(self, async_session: AsyncMock):
        """Tags not duplicated when already present on existing document."""
        document = _make_document(id_=100)

        # Mock: both tags already exist
        existing_tag1 = MagicMock(spec=DocumentTag)
        existing_tag1.tag = "DOC-GUIDE"
        existing_tag1.document_id = document.id

        existing_tag2 = MagicMock(spec=DocumentTag)
        existing_tag2.tag = "ALC-GOV"
        existing_tag2.document_id = document.id

        async_session.execute = AsyncMock(
            return_value=_mock_scalars_all([existing_tag1, existing_tag2])
        )
        async_session.flush = AsyncMock()

        service = DocumentationGeneratorService(async_session)
        tags_applied = await service._apply_tags(document, is_new=False)

        # Tags should still be reported as applied
        assert tags_applied == ["DOC-GUIDE", "ALC-GOV"]

        # But no new tags should have been added to the session
        async_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Task 7.3: apply_workflow Tests
# ---------------------------------------------------------------------------


class TestApplyWorkflowNewDocument:
    """Test: apply_workflow creates DocumentState with state="Draft" on new document.

    Validates: Requirements 3.3
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

        service = DocumentationGeneratorService(async_session)
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

    Validates: Requirements 3.3, 5.4
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

        service = DocumentationGeneratorService(async_session)
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
    """Test: report has 2 entries, all is_new_document=True on first run.

    Validates: Requirements 4.4, 5.5
    """

    @pytest.mark.asyncio
    async def test_report_two_entries_all_new(self, async_session: AsyncMock):
        """Report contains 2 entries with is_new_document=True on first run."""
        # Simulate a report from first run (all new documents)
        entries = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title=USER_GUIDE_TITLE,
                guide_type="user_guide",
                version_number=1,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                section_count=12,
                procedure_count=30,
                screenshot_placeholder_count=30,
            ),
            DocumentReportEntry(
                document_id=2,
                document_uuid="2025-00002",
                title=ADMIN_GUIDE_TITLE,
                guide_type="admin_guide",
                version_number=1,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                section_count=12,
                procedure_count=25,
                screenshot_placeholder_count=25,
            ),
        ]

        report = DocumentationGenerationReport(
            documents_created=entries,
            total_documents=2,
            total_sections=24,
            total_procedures=55,
            cross_references_included=CrossReferenceSummary(
                urs_references=True, ai_guidelines_references=True
            ),
            total_duration_ms=500,
        )

        assert report.total_documents == 2
        assert len(report.documents_created) == 2
        assert all(e.is_new_document is True for e in report.documents_created)
        assert all(e.version_number == 1 for e in report.documents_created)
        assert all(
            e.workflow_state == "Draft" for e in report.documents_created
        )


class TestReportSubsequentRun:
    """Test: report correctly identifies new vs versioned on subsequent runs.

    Validates: Requirements 5.4, 5.5, 5.6
    """

    @pytest.mark.asyncio
    async def test_report_identifies_versioned_documents(
        self, async_session: AsyncMock
    ):
        """Report shows is_new_document=False for versioned documents."""
        entries = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title=USER_GUIDE_TITLE,
                guide_type="user_guide",
                version_number=2,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=False,
                section_count=12,
                procedure_count=30,
                screenshot_placeholder_count=30,
            ),
            DocumentReportEntry(
                document_id=2,
                document_uuid="2025-00002",
                title=ADMIN_GUIDE_TITLE,
                guide_type="admin_guide",
                version_number=2,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=False,
                section_count=12,
                procedure_count=25,
                screenshot_placeholder_count=25,
            ),
        ]

        report = DocumentationGenerationReport(
            documents_created=entries,
            total_documents=2,
            total_sections=24,
            total_procedures=55,
            cross_references_included=CrossReferenceSummary(
                urs_references=True, ai_guidelines_references=False
            ),
            total_duration_ms=450,
        )

        assert report.total_documents == 2
        assert all(
            e.is_new_document is False for e in report.documents_created
        )
        assert all(e.version_number == 2 for e in report.documents_created)


class TestReportSectionCount:
    """Test: report section_count matches actual level-2 headings per guide.

    Validates: Requirements 4.4
    """

    def test_count_sections_returns_correct_count(
        self, async_session: AsyncMock
    ):
        """_count_sections returns correct level-2 heading count."""
        service = DocumentationGeneratorService(async_session)

        content = (
            "# Document Title\n\n"
            "## Section One\n\nContent.\n\n"
            "## Section Two\n\nContent.\n\n"
            "### Subsection\n\nNested content.\n\n"
            "## Section Three\n\nContent.\n"
        )
        count = service._count_sections(content)
        assert count == 3

    def test_count_sections_empty_content(self, async_session: AsyncMock):
        """Returns 0 for content with no level-2 headings."""
        service = DocumentationGeneratorService(async_session)

        content = "# Title\n\n### Only level-3\n\nContent."
        count = service._count_sections(content)
        assert count == 0

    def test_report_section_count_matches_sum(self, async_session: AsyncMock):
        """Report total_sections matches sum of individual section_counts."""
        entries = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title=USER_GUIDE_TITLE,
                guide_type="user_guide",
                version_number=1,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                section_count=12,
                procedure_count=30,
                screenshot_placeholder_count=30,
            ),
            DocumentReportEntry(
                document_id=2,
                document_uuid="2025-00002",
                title=ADMIN_GUIDE_TITLE,
                guide_type="admin_guide",
                version_number=1,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                section_count=12,
                procedure_count=25,
                screenshot_placeholder_count=25,
            ),
        ]

        report = DocumentationGenerationReport(
            documents_created=entries,
            total_documents=2,
            total_sections=24,
            total_procedures=55,
            cross_references_included=CrossReferenceSummary(
                urs_references=True, ai_guidelines_references=True
            ),
            total_duration_ms=300,
        )

        individual_sum = sum(
            e.section_count for e in report.documents_created
        )
        assert report.total_sections == individual_sum


class TestReportProcedureCount:
    """Test: report procedure_count matches actual Procedure_Blocks per guide.

    Validates: Requirements 4.4
    """

    def test_count_procedures_returns_correct_count(
        self, async_session: AsyncMock
    ):
        """_count_procedures returns correct Procedure_Block count."""
        service = DocumentationGeneratorService(async_session)

        content = (
            "# Document\n\n"
            "## Section One\n\n"
            "### Procedure: Upload Document\n\n"
            "1. **Click** the upload button — *file dialog opens*\n\n"
            "### Procedure: Download Document\n\n"
            "1. **Click** the download icon — *file downloads*\n\n"
            "## Section Two\n\n"
            "### Procedure: Create User\n\n"
            "1. **Navigate** to user management — *page loads*\n"
        )
        count = service._count_procedures(content)
        assert count == 3

    def test_count_procedures_empty(self, async_session: AsyncMock):
        """Returns 0 for content with no Procedure_Blocks."""
        service = DocumentationGeneratorService(async_session)

        content = "# Document\n\n## Overview\n\nNo procedures here."
        count = service._count_procedures(content)
        assert count == 0

    def test_report_procedure_count_matches_sum(
        self, async_session: AsyncMock
    ):
        """Report total_procedures matches sum of individual procedure_counts."""
        entries = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title=USER_GUIDE_TITLE,
                guide_type="user_guide",
                version_number=1,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                section_count=12,
                procedure_count=28,
                screenshot_placeholder_count=28,
            ),
            DocumentReportEntry(
                document_id=2,
                document_uuid="2025-00002",
                title=ADMIN_GUIDE_TITLE,
                guide_type="admin_guide",
                version_number=1,
                tags_applied=list(DOCUMENTATION_TAGS),
                workflow_state="Draft",
                is_new_document=True,
                section_count=12,
                procedure_count=22,
                screenshot_placeholder_count=22,
            ),
        ]

        report = DocumentationGenerationReport(
            documents_created=entries,
            total_documents=2,
            total_sections=24,
            total_procedures=50,
            cross_references_included=CrossReferenceSummary(
                urs_references=True, ai_guidelines_references=True
            ),
            total_duration_ms=400,
        )

        individual_sum = sum(
            e.procedure_count for e in report.documents_created
        )
        assert report.total_procedures == individual_sum


class TestReportScreenshotPlaceholderCount:
    """Test: report screenshot_placeholder_count matches actual placeholders per guide.

    Validates: Requirements 4.4
    """

    def test_count_screenshot_placeholders_returns_correct_count(
        self, async_session: AsyncMock
    ):
        """_count_screenshot_placeholders returns correct count."""
        service = DocumentationGeneratorService(async_session)

        content = (
            "# Document\n\n"
            "## Section One\n\n"
            "![Upload dialog](screenshots/document-management/upload-dialog.png)\n\n"
            "Some text.\n\n"
            "![Version history](screenshots/document-management/version-history.png)\n\n"
            "## Section Two\n\n"
            "![User list](screenshots/user-management/user-list.png)\n"
        )
        count = service._count_screenshot_placeholders(content)
        assert count == 3

    def test_count_screenshot_placeholders_empty(
        self, async_session: AsyncMock
    ):
        """Returns 0 for content with no screenshot placeholders."""
        service = DocumentationGeneratorService(async_session)

        content = "# Document\n\n## Overview\n\nNo screenshots here."
        count = service._count_screenshot_placeholders(content)
        assert count == 0

    def test_does_not_count_non_screenshot_images(
        self, async_session: AsyncMock
    ):
        """Does not count images that don't match screenshots/ path."""
        service = DocumentationGeneratorService(async_session)

        content = (
            "![Logo](images/logo.png)\n\n"
            "![Diagram](diagrams/flow.png)\n\n"
            "![Screenshot](screenshots/section/action.png)\n"
        )
        count = service._count_screenshot_placeholders(content)
        assert count == 1


class TestReportCrossReferencesIncluded:
    """Test: report cross_references_included flags match actual availability.

    Validates: Requirements 4.4
    """

    def test_both_available(self, async_session: AsyncMock):
        """cross_references_included reflects both URS and AI Guidelines available."""
        report = DocumentationGenerationReport(
            documents_created=[],
            total_documents=0,
            total_sections=0,
            total_procedures=0,
            cross_references_included=CrossReferenceSummary(
                urs_references=True, ai_guidelines_references=True
            ),
            total_duration_ms=100,
        )

        assert report.cross_references_included.urs_references is True
        assert report.cross_references_included.ai_guidelines_references is True

    def test_urs_only(self, async_session: AsyncMock):
        """cross_references_included reflects only URS available."""
        report = DocumentationGenerationReport(
            documents_created=[],
            total_documents=0,
            total_sections=0,
            total_procedures=0,
            cross_references_included=CrossReferenceSummary(
                urs_references=True, ai_guidelines_references=False
            ),
            total_duration_ms=100,
        )

        assert report.cross_references_included.urs_references is True
        assert report.cross_references_included.ai_guidelines_references is False

    def test_neither_available(self, async_session: AsyncMock):
        """cross_references_included reflects neither available."""
        report = DocumentationGenerationReport(
            documents_created=[],
            total_documents=0,
            total_sections=0,
            total_procedures=0,
            cross_references_included=CrossReferenceSummary(
                urs_references=False, ai_guidelines_references=False
            ),
            total_duration_ms=100,
        )

        assert report.cross_references_included.urs_references is False
        assert report.cross_references_included.ai_guidelines_references is False


class TestReportTotalDurationMs:
    """Test: report total_duration_ms > 0.

    Validates: Requirements 4.4
    """

    def test_total_duration_ms_positive(self, async_session: AsyncMock):
        """total_duration_ms is greater than 0."""
        report = DocumentationGenerationReport(
            documents_created=[],
            total_documents=0,
            total_sections=0,
            total_procedures=0,
            cross_references_included=CrossReferenceSummary(
                urs_references=True, ai_guidelines_references=True
            ),
            total_duration_ms=523,
        )

        assert report.total_duration_ms > 0

    def test_total_duration_ms_is_integer(self, async_session: AsyncMock):
        """total_duration_ms is an integer value."""
        report = DocumentationGenerationReport(
            documents_created=[],
            total_documents=0,
            total_sections=0,
            total_procedures=0,
            cross_references_included=CrossReferenceSummary(
                urs_references=False, ai_guidelines_references=False
            ),
            total_duration_ms=1042,
        )

        assert isinstance(report.total_duration_ms, int)
        assert report.total_duration_ms == 1042
