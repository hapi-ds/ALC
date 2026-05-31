"""Unit tests for URSGeneratorService.

Tests cover:
- Task 6.1: Prerequisites validation (all present, no company, no doc-admin,
  no workflow), content generation (header, modules, minimum 40 REQ-IDs),
  content validation (empty, no REQ-IDs, valid), URS_CONTENT constant validity.
- Task 6.2: Document operations (detect, create, version), tagging,
  workflow application, and report structure.

References:
    - Requirements: 1.1, 1.2, 1.6, 2.5, 3.1, 3.2, 3.4, 4.1, 4.2, 7.1, 7.4, 7.5, 8.1, 8.2, 8.3, 8.5
    - Design: .kiro/specs/Step_8-3_urs-alc-corporate/design.md
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.services.urs_content import (
    URS_CONTENT,
    URS_DOCUMENT_TITLE,
    URS_DOCUMENT_TYPE,
    URS_TAGS,
)
from alcoabase.services.urs_generator_service import URSGeneratorService


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


def _make_company(id_: int = 1) -> Company:
    """Create a Company instance matching ALC corporate."""
    company = MagicMock(spec=Company)
    company.id = id_
    company.slug = "alc-corporate"
    return company


def _make_doc_admin(id_: int = 10) -> User:
    """Create a User instance for the doc-admin."""
    user = MagicMock(spec=User)
    user.id = id_
    user.username = "alc-doc-admin"
    return user


def _make_user(id_: int = 10, username: str = "alc-doc-admin") -> User:
    """Create a User instance with configurable attributes."""
    user = MagicMock(spec=User)
    user.id = id_
    user.username = username
    return user


def _make_workflow(id_: int = 5, company_id: int = 1) -> WorkflowDefinition:
    """Create a WorkflowDefinition instance for the governance workflow."""
    workflow = MagicMock(spec=WorkflowDefinition)
    workflow.id = id_
    workflow.name = "ALC Governance Document Lifecycle"
    workflow.document_tag = "ALC-GOV"
    workflow.company_id = company_id
    return workflow


def _make_document(id_: int = 100, company_id: int = 1) -> Document:
    """Create a Document instance for testing."""
    doc = MagicMock(spec=Document)
    doc.id = id_
    doc.document_uuid = "2025-00042"
    doc.title = URS_DOCUMENT_TITLE
    doc.company_id = company_id
    doc.current_status = "Draft"
    return doc


# ---------------------------------------------------------------------------
# Task 6.1: Prerequisites Validation Tests
# ---------------------------------------------------------------------------


class TestValidatePrerequisitesAllPresent:
    """Test: validate_prerequisites returns company, user, workflow when all exist.

    Validates: Requirements 8.1, 8.2, 8.3
    """

    @pytest.mark.asyncio
    async def test_returns_tuple_when_all_present(self, async_session: AsyncMock):
        """Returns (company, doc_admin, workflow) when all prerequisites exist."""
        company = _make_company()
        doc_admin = _make_doc_admin()
        workflow = _make_workflow()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),
                _mock_scalar_one_or_none(doc_admin),
                _mock_scalar_one_or_none(workflow),
            ]
        )

        service = URSGeneratorService(async_session)
        result = await service._validate_prerequisites()

        assert result == (company, doc_admin, workflow)
        assert result[0].slug == "alc-corporate"
        assert result[1].username == "alc-doc-admin"
        assert result[2].document_tag == "ALC-GOV"


class TestValidatePrerequisitesNoCompany:
    """Test: validate_prerequisites raises RuntimeError when company missing.

    Validates: Requirements 8.1
    """

    @pytest.mark.asyncio
    async def test_raises_when_no_company(self, async_session: AsyncMock):
        """Raises RuntimeError with expected message when ALC company not found."""
        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        service = URSGeneratorService(async_session)

        with pytest.raises(
            RuntimeError,
            match="ALC corporate environment not provisioned. Run Phase 8.2 seed first.",
        ):
            await service._validate_prerequisites()


class TestValidatePrerequisitesNoDocAdmin:
    """Test: validate_prerequisites raises RuntimeError when doc-admin missing.

    Validates: Requirements 8.2
    """

    @pytest.mark.asyncio
    async def test_raises_when_no_doc_admin(self, async_session: AsyncMock):
        """Raises RuntimeError with expected message when doc-admin not found."""
        company = _make_company()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),
                _mock_scalar_one_or_none(None),  # doc-admin not found
            ]
        )

        service = URSGeneratorService(async_session)

        with pytest.raises(
            RuntimeError,
            match="ALC Document Administrator user not found. Run Phase 8.2 seed first.",
        ):
            await service._validate_prerequisites()


class TestValidatePrerequisitesNoWorkflow:
    """Test: validate_prerequisites raises RuntimeError when workflow missing.

    Validates: Requirements 8.3
    """

    @pytest.mark.asyncio
    async def test_raises_when_no_workflow(self, async_session: AsyncMock):
        """Raises RuntimeError with expected message when governance workflow not found."""
        company = _make_company()
        doc_admin = _make_doc_admin()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),
                _mock_scalar_one_or_none(doc_admin),
                _mock_scalar_one_or_none(None),  # workflow not found
            ]
        )

        service = URSGeneratorService(async_session)

        with pytest.raises(
            RuntimeError,
            match="ALC Governance workflow not found. Run Phase 8.2 seed first.",
        ):
            await service._validate_prerequisites()


# ---------------------------------------------------------------------------
# Task 6.1: Content Generation Tests
# ---------------------------------------------------------------------------


class TestGenerateContentHeader:
    """Test: generate_content includes header with title, version, and timestamp.

    Validates: Requirements 1.1
    """

    @pytest.mark.asyncio
    async def test_header_includes_title(self, async_session: AsyncMock):
        """Generated content includes the document title in the header."""
        service = URSGeneratorService(async_session)
        content = await service._generate_content(1)

        assert URS_DOCUMENT_TITLE in content

    @pytest.mark.asyncio
    async def test_header_includes_version(self, async_session: AsyncMock):
        """Generated content replaces {{VERSION}} placeholder with version number."""
        service = URSGeneratorService(async_session)
        content = await service._generate_content(3)

        assert "{{VERSION}}" not in content
        assert "| **Version** | 3 |" in content

    @pytest.mark.asyncio
    async def test_header_includes_timestamp(self, async_session: AsyncMock):
        """Generated content replaces {{TIMESTAMP}} placeholder with ISO timestamp."""
        service = URSGeneratorService(async_session)
        content = await service._generate_content(1)

        assert "{{TIMESTAMP}}" not in content
        # Verify ISO format timestamp is present (YYYY-MM-DDTHH:MM:SS pattern)
        iso_pattern = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        assert iso_pattern.search(content) is not None


class TestGenerateContentModules:
    """Test: generate_content includes all expected module sections.

    Validates: Requirements 1.1, 1.2
    """

    @pytest.mark.asyncio
    async def test_includes_all_module_sections(self, async_session: AsyncMock):
        """Generated content contains all 19 requirement module sections."""
        service = URSGeneratorService(async_session)
        content = await service._generate_content(1)

        expected_modules = [
            "Document Management (REQ-DM)",
            "Deterministic PDF Protocol (REQ-PDF)",
            "Workflows and Electronic Signatures (REQ-WF, REQ-SIG)",
            "Training Execution Gate (REQ-TRN)",
            "ALCOA+ Audit Trail (REQ-AUD)",
            "Computer System Validation (REQ-CSV)",
            "Hybrid Search and Knowledge Base (REQ-SRCH)",
            "RAG Document Q&A (REQ-RAG)",
            "AI Model Integration (REQ-AI)",
            "Agent Registry and Personality Framework (REQ-AGT)",
            "Multi-Agent Auditing (REQ-MAA)",
            "AI Training Ecosystem (REQ-ATE)",
            "AI Document Generator (REQ-GEN)",
            "Change Impact Analysis (REQ-CIA)",
            "Traceability and Gap Discovery (REQ-TRC)",
            "User Management and RBAC (REQ-USR)",
            "System Configuration (REQ-SYS)",
            "AI Risk and Compliance Framework (REQ-RISK)",
            "ALC Corporate Environment (REQ-GOV)",
        ]

        for module in expected_modules:
            assert module in content, f"Module '{module}' not found in generated content"


class TestGenerateContentMinimumRequirements:
    """Test: generate_content produces minimum 40 distinct REQ-IDs.

    Validates: Requirements 2.5
    """

    @pytest.mark.asyncio
    async def test_minimum_40_distinct_req_ids(self, async_session: AsyncMock):
        """Generated content contains at least 40 distinct Requirement_IDs."""
        service = URSGeneratorService(async_session)
        content = await service._generate_content(1)

        req_id_pattern = re.compile(r"REQ-[A-Z]+-\d{2,}")
        matches = req_id_pattern.findall(content)
        distinct_ids = set(matches)

        assert len(distinct_ids) >= 40, (
            f"Expected at least 40 distinct REQ-IDs, found {len(distinct_ids)}"
        )


# ---------------------------------------------------------------------------
# Task 6.1: Content Validation Tests
# ---------------------------------------------------------------------------


class TestContentValidationRejectsEmpty:
    """Test: content validation rejects empty content.

    Validates: Requirements 8.5
    """

    def test_raises_on_empty_string(self, async_session: AsyncMock):
        """Raises RuntimeError for empty string content."""
        service = URSGeneratorService(async_session)

        with pytest.raises(
            RuntimeError, match="URS content generation produced empty output"
        ):
            service._validate_content("")

    def test_raises_on_whitespace_only(self, async_session: AsyncMock):
        """Raises RuntimeError for whitespace-only content."""
        service = URSGeneratorService(async_session)

        with pytest.raises(
            RuntimeError, match="URS content generation produced empty output"
        ):
            service._validate_content("   \n\t  ")


class TestContentValidationRejectsNoReqIds:
    """Test: content validation rejects content without REQ-IDs.

    Validates: Requirements 8.5
    """

    def test_raises_on_content_without_req_ids(self, async_session: AsyncMock):
        """Raises RuntimeError for content that has no valid Requirement_IDs."""
        service = URSGeneratorService(async_session)

        with pytest.raises(
            RuntimeError,
            match="no valid Requirement_IDs found",
        ):
            service._validate_content("This is some content without any requirement IDs.")


class TestContentValidationAcceptsValid:
    """Test: content validation accepts valid content with REQ-IDs.

    Validates: Requirements 8.5
    """

    def test_accepts_content_with_req_ids(self, async_session: AsyncMock):
        """No error raised for content containing valid Requirement_IDs."""
        service = URSGeneratorService(async_session)

        # Should not raise
        service._validate_content("REQ-DM-01 is a valid requirement identifier.")

    def test_accepts_content_with_multiple_req_ids(self, async_session: AsyncMock):
        """No error raised for content with multiple REQ-IDs."""
        service = URSGeneratorService(async_session)

        content = (
            "## Module 1\n"
            "REQ-DM-01: Document upload\n"
            "REQ-DM-02: Document versioning\n"
            "REQ-AI-01: AI integration\n"
        )
        # Should not raise
        service._validate_content(content)


# ---------------------------------------------------------------------------
# Task 6.1: URS_CONTENT Constant Tests
# ---------------------------------------------------------------------------


class TestURSContentConstant:
    """Test: URS_CONTENT constant is non-empty and well-formed.

    Validates: Requirements 1.1, 1.2
    """

    def test_urs_content_is_non_empty(self):
        """URS_CONTENT constant is a non-empty string."""
        assert isinstance(URS_CONTENT, str)
        assert len(URS_CONTENT.strip()) > 0

    def test_urs_content_contains_req_ids(self):
        """URS_CONTENT contains valid Requirement_IDs."""
        req_id_pattern = re.compile(r"REQ-[A-Z]+-\d{2,}")
        matches = req_id_pattern.findall(URS_CONTENT)
        assert len(matches) > 0, "URS_CONTENT contains no Requirement_IDs"

    def test_urs_content_has_minimum_40_req_ids(self):
        """URS_CONTENT has at least 40 distinct Requirement_IDs."""
        req_id_pattern = re.compile(r"REQ-[A-Z]+-\d{2,}")
        matches = req_id_pattern.findall(URS_CONTENT)
        distinct_ids = set(matches)
        assert len(distinct_ids) >= 40, (
            f"Expected at least 40 distinct REQ-IDs, found {len(distinct_ids)}"
        )

    def test_urs_content_has_version_placeholder(self):
        """URS_CONTENT contains {{VERSION}} placeholder for injection."""
        assert "{{VERSION}}" in URS_CONTENT

    def test_urs_content_has_timestamp_placeholder(self):
        """URS_CONTENT contains {{TIMESTAMP}} placeholder for injection."""
        assert "{{TIMESTAMP}}" in URS_CONTENT

    def test_urs_content_has_document_title(self):
        """URS_CONTENT contains the expected document title."""
        assert URS_DOCUMENT_TITLE in URS_CONTENT

    def test_urs_content_has_numbered_sections(self):
        """URS_CONTENT has numbered module sections (## N. ...)."""
        module_pattern = re.compile(r"^## \d+\.\s+", re.MULTILINE)
        matches = module_pattern.findall(URS_CONTENT)
        assert len(matches) >= 14, (
            f"Expected at least 14 numbered sections, found {len(matches)}"
        )

    def test_urs_document_title_constant(self):
        """URS_DOCUMENT_TITLE is the expected value."""
        assert URS_DOCUMENT_TITLE == "AlcoaBase — Enhanced User Requirement Specifications"

    def test_urs_document_type_constant(self):
        """URS_DOCUMENT_TYPE is the expected value."""
        assert URS_DOCUMENT_TYPE == "User Requirement Specifications"

    def test_urs_tags_constant(self):
        """URS_TAGS contains the expected governance tags."""
        assert URS_TAGS == ["URS", "ALC-GOV"]

# ---------------------------------------------------------------------------
# Task 6.2: Document Operations Tests
# ---------------------------------------------------------------------------


class TestDetectExistingDocumentFound:
    """Test: detect_existing_document returns Document when tags match.

    Validates: Requirements 1.6, 7.1
    """

    @pytest.mark.asyncio
    async def test_detect_existing_document_found(self, async_session: AsyncMock):
        """Returns existing Document when both URS and ALC-GOV tags present."""
        company = _make_company()
        existing_doc = _make_document(id_=100, company_id=company.id)

        # Mock: query returns the existing document
        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(existing_doc)
        )

        service = URSGeneratorService(async_session)
        result = await service._detect_existing_document(company)

        assert result is existing_doc
        assert result.id == 100


class TestDetectExistingDocumentNotFound:
    """Test: detect_existing_document returns None when no matching document.

    Validates: Requirements 1.6, 7.1
    """

    @pytest.mark.asyncio
    async def test_detect_existing_document_not_found(self, async_session: AsyncMock):
        """Returns None when no document with both URS and ALC-GOV tags exists."""
        company = _make_company()

        # Mock: query returns None (no matching document)
        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        service = URSGeneratorService(async_session)
        result = await service._detect_existing_document(company)

        assert result is None


# ---------------------------------------------------------------------------
# Task 6.2: Create New Document Tests
# ---------------------------------------------------------------------------


class TestCreateNewDocumentAttributes:
    """Test: create_new_document has correct title, type, company_id, created_by.

    Validates: Requirements 3.1, 3.4
    """

    @pytest.mark.asyncio
    async def test_create_new_document_attributes(self, async_session: AsyncMock):
        """New document has correct title, type, company_id, and created_by."""
        company = _make_company(id_=1)
        doc_admin = _make_user(id_=10)
        content = "# URS\n\nREQ-DM-01: Test requirement"

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(return_value="documents/2025-00001/1.0/document.md")

        mock_uuid = AsyncMock()
        mock_uuid.generate_document_uuid = AsyncMock(return_value="2025-00001")

        # Track added objects
        added_objects = []

        def track_add(obj):
            added_objects.append(obj)
            if isinstance(obj, Document):
                obj.id = 100

        async_session.add = MagicMock(side_effect=track_add)

        service = URSGeneratorService(
            async_session,
            storage_service=mock_storage,
            uuid_service=mock_uuid,
        )
        document, version = await service._create_new_document(content, company, doc_admin)

        # Verify Document attributes
        assert isinstance(document, Document)
        assert document.title == URS_DOCUMENT_TITLE
        assert document.document_type == URS_DOCUMENT_TYPE
        assert document.company_id == company.id
        assert document.created_by == doc_admin.id
        assert document.document_uuid == "2025-00001"
        assert document.folder_path == "/governance/urs"
        assert document.current_status == "Draft"


class TestCreateNewDocumentVersion:
    """Test: initial version is major=1, minor=0.

    Validates: Requirements 3.1
    """

    @pytest.mark.asyncio
    async def test_create_new_document_initial_version(self, async_session: AsyncMock):
        """Initial DocumentVersion has major_version=1, minor_version=0."""
        company = _make_company(id_=1)
        doc_admin = _make_user(id_=10)
        content = "# URS\n\nREQ-DM-01: Test requirement"

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(return_value="documents/2025-00001/1.0/document.md")

        mock_uuid = AsyncMock()
        mock_uuid.generate_document_uuid = AsyncMock(return_value="2025-00001")

        added_objects = []

        def track_add(obj):
            added_objects.append(obj)
            if isinstance(obj, Document):
                obj.id = 100

        async_session.add = MagicMock(side_effect=track_add)

        service = URSGeneratorService(
            async_session,
            storage_service=mock_storage,
            uuid_service=mock_uuid,
        )
        document, version = await service._create_new_document(content, company, doc_admin)

        # Verify DocumentVersion attributes
        assert isinstance(version, DocumentVersion)
        assert version.major_version == 1
        assert version.minor_version == 0
        assert version.document_id == 100
        assert version.uploaded_by == doc_admin.id
        assert "SHA-512" not in version.file_hash or len(version.file_hash) == 128


# ---------------------------------------------------------------------------
# Task 6.2: Create New Version Tests
# ---------------------------------------------------------------------------


class TestCreateNewVersionIncrementsMajor:
    """Test: create_new_version increments major_version correctly.

    Validates: Requirements 7.1
    """

    @pytest.mark.asyncio
    async def test_create_new_version_increments_major(self, async_session: AsyncMock):
        """New version has major_version = version_number passed in."""
        document = _make_document(id_=100)
        doc_admin = _make_user(id_=10)
        content = "# URS v3\n\nREQ-DM-01: Test requirement"
        version_number = 3  # Simulating third version

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(
            return_value=f"documents/{document.document_uuid}/{version_number}.0/document.md"
        )

        added_objects = []

        def track_add(obj):
            added_objects.append(obj)

        async_session.add = MagicMock(side_effect=track_add)

        service = URSGeneratorService(
            async_session,
            storage_service=mock_storage,
        )
        version = await service._create_new_version(
            document, content, doc_admin, version_number
        )

        # Verify version attributes
        assert isinstance(version, DocumentVersion)
        assert version.major_version == 3
        assert version.minor_version == 0
        assert version.document_id == document.id
        assert version.uploaded_by == doc_admin.id

        # Verify document status reset to Draft
        assert document.current_status == "Draft"

        # Verify storage key includes version number
        mock_storage.upload_file.assert_awaited_once()
        call_args = mock_storage.upload_file.call_args
        assert f"/{version_number}.0/" in call_args[0][0]


# ---------------------------------------------------------------------------
# Task 6.2: Apply Tags Tests
# ---------------------------------------------------------------------------


class TestApplyTagsNewDocument:
    """Test: apply_tags creates both "URS" and "ALC-GOV" tags on new document.

    Validates: Requirements 3.2
    """

    @pytest.mark.asyncio
    async def test_apply_tags_new_document(self, async_session: AsyncMock):
        """Both URS and ALC-GOV tags created for a new document."""
        document = _make_document(id_=100)

        # Mock: no existing tags
        async_session.execute = AsyncMock(
            return_value=_mock_scalars_all([])
        )

        added_objects = []

        def track_add(obj):
            added_objects.append(obj)

        async_session.add = MagicMock(side_effect=track_add)

        service = URSGeneratorService(async_session)
        tags_applied = await service._apply_tags(document, is_new=True)

        # Verify both tags were added
        assert tags_applied == ["URS", "ALC-GOV"]

        tag_objects = [o for o in added_objects if isinstance(o, DocumentTag)]
        assert len(tag_objects) == 2

        tag_values = {t.tag for t in tag_objects}
        assert tag_values == {"URS", "ALC-GOV"}

        for tag_obj in tag_objects:
            assert tag_obj.document_id == document.id


class TestApplyTagsExistingDocument:
    """Test: apply_tags does not duplicate tags on re-run.

    Validates: Requirements 3.2
    """

    @pytest.mark.asyncio
    async def test_apply_tags_no_duplicates(self, async_session: AsyncMock):
        """Tags not duplicated when already present on existing document."""
        document = _make_document(id_=100)

        # Mock: both tags already exist
        existing_tag_urs = MagicMock(spec=DocumentTag)
        existing_tag_urs.tag = "URS"
        existing_tag_urs.document_id = document.id

        existing_tag_gov = MagicMock(spec=DocumentTag)
        existing_tag_gov.tag = "ALC-GOV"
        existing_tag_gov.document_id = document.id

        async_session.execute = AsyncMock(
            return_value=_mock_scalars_all([existing_tag_urs, existing_tag_gov])
        )

        service = URSGeneratorService(async_session)
        tags_applied = await service._apply_tags(document, is_new=False)

        # Tags should still be reported as applied
        assert tags_applied == ["URS", "ALC-GOV"]

        # But no new tags should have been added to the session
        async_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Task 6.2: Apply Workflow Tests
# ---------------------------------------------------------------------------


class TestApplyWorkflowNewDocument:
    """Test: apply_workflow creates DocumentState with state="Draft" on new document.

    Validates: Requirements 4.1, 4.2
    """

    @pytest.mark.asyncio
    async def test_apply_workflow_new_document(self, async_session: AsyncMock):
        """DocumentState created with state='Draft' for new document."""
        document = _make_document(id_=100)
        workflow = _make_workflow(id_=5)
        doc_admin = _make_user(id_=10)

        # Mock: no existing DocumentState
        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        added_objects = []

        def track_add(obj):
            added_objects.append(obj)

        async_session.add = MagicMock(side_effect=track_add)

        service = URSGeneratorService(async_session)
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


class TestApplyWorkflowVersionReset:
    """Test: apply_workflow resets DocumentState to "Draft" on new version.

    Validates: Requirements 7.4
    """

    @pytest.mark.asyncio
    async def test_apply_workflow_resets_to_draft(self, async_session: AsyncMock):
        """Existing DocumentState reset to 'Draft' when new version created."""
        document = _make_document(id_=100)
        workflow = _make_workflow(id_=5)
        doc_admin = _make_user(id_=10)

        # Mock: existing DocumentState with state="Approved"
        existing_state = MagicMock(spec=DocumentState)
        existing_state.document_id = document.id
        existing_state.current_state = "Approved"
        existing_state.workflow_id = 3  # Old workflow

        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(existing_state)
        )

        service = URSGeneratorService(async_session)
        state = await service._apply_workflow(document, workflow, doc_admin)

        assert state == "Draft"

        # Verify existing state was updated (not a new one created)
        assert existing_state.current_state == "Draft"
        assert existing_state.workflow_id == workflow.id
        assert existing_state.updated_by == doc_admin.id

        # session.add should NOT have been called (update in place)
        async_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Task 6.2: Report Structure Tests
# ---------------------------------------------------------------------------


class TestReportStructureNewDocument:
    """Test: report structure for new document (is_new_document=True).

    Validates: Requirements 7.5
    """

    @pytest.mark.asyncio
    async def test_report_new_document(self, async_session: AsyncMock):
        """Report has is_new_document=True and correct fields for new document."""
        company = _make_company(id_=1)
        doc_admin = _make_user(id_=10)
        workflow = _make_workflow(id_=5)

        # Mock prerequisites
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1

            # Step 1: validate_prerequisites - company
            if call_count == 1:
                return _mock_scalar_one_or_none(company)
            # Step 1: validate_prerequisites - doc_admin
            if call_count == 2:
                return _mock_scalar_one_or_none(doc_admin)
            # Step 1: validate_prerequisites - workflow
            if call_count == 3:
                return _mock_scalar_one_or_none(workflow)
            # Step 3: detect_existing_document
            if call_count == 4:
                return _mock_scalar_one_or_none(None)
            # Step 6: apply_tags - existing tags query
            if call_count == 5:
                return _mock_scalars_all([])
            # Step 7: apply_workflow - existing state query
            if call_count == 6:
                return _mock_scalar_one_or_none(None)
            return _mock_scalar_one_or_none(None)

        async_session.execute = AsyncMock(side_effect=mock_execute)

        # Track added objects and assign IDs
        added_objects = []

        def track_add(obj):
            added_objects.append(obj)
            if isinstance(obj, Document):
                obj.id = 100
                obj.document_uuid = "2025-00001"

        async_session.add = MagicMock(side_effect=track_add)

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(return_value="documents/2025-00001/1.0/document.md")

        mock_uuid = AsyncMock()
        mock_uuid.generate_document_uuid = AsyncMock(return_value="2025-00001")

        service = URSGeneratorService(
            async_session,
            storage_service=mock_storage,
            uuid_service=mock_uuid,
        )
        report = await service.execute()

        # Verify report structure
        assert report.is_new_document is True
        assert report.version_number == 1
        assert report.document_id == 100
        assert report.document_uuid == "2025-00001"
        assert report.document_title == URS_DOCUMENT_TITLE
        assert report.tags_applied == ["URS", "ALC-GOV"]
        assert report.workflow_state == "Draft"
        assert report.requirement_count >= 40
        assert report.module_count >= 1
        assert report.total_duration_ms >= 0


class TestReportStructureExistingDocument:
    """Test: report structure for existing document (is_new_document=False, incremented version).

    Validates: Requirements 7.5
    """

    @pytest.mark.asyncio
    async def test_report_existing_document(self, async_session: AsyncMock):
        """Report has is_new_document=False and incremented version for existing doc."""
        company = _make_company(id_=1)
        doc_admin = _make_user(id_=10)
        workflow = _make_workflow(id_=5)
        existing_doc = _make_document(id_=100, company_id=1)

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1

            # Step 1: validate_prerequisites - company
            if call_count == 1:
                return _mock_scalar_one_or_none(company)
            # Step 1: validate_prerequisites - doc_admin
            if call_count == 2:
                return _mock_scalar_one_or_none(doc_admin)
            # Step 1: validate_prerequisites - workflow
            if call_count == 3:
                return _mock_scalar_one_or_none(workflow)
            # Step 2: detect_existing_document
            if call_count == 4:
                return _mock_scalar_one_or_none(existing_doc)
            # Step 2: _get_next_version_number (MAX major_version = 2)
            if call_count == 5:
                return _mock_scalar_one_or_none(2)
            # Step 6: apply_tags - existing tags query
            if call_count == 6:
                existing_tag_urs = MagicMock(spec=DocumentTag)
                existing_tag_urs.tag = "URS"
                existing_tag_gov = MagicMock(spec=DocumentTag)
                existing_tag_gov.tag = "ALC-GOV"
                return _mock_scalars_all([existing_tag_urs, existing_tag_gov])
            # Step 7: apply_workflow - existing state
            if call_count == 7:
                existing_state = MagicMock(spec=DocumentState)
                existing_state.current_state = "Approved"
                return _mock_scalar_one_or_none(existing_state)
            return _mock_scalar_one_or_none(None)

        async_session.execute = AsyncMock(side_effect=mock_execute)

        added_objects = []

        def track_add(obj):
            added_objects.append(obj)

        async_session.add = MagicMock(side_effect=track_add)

        mock_storage = AsyncMock()
        mock_storage.upload_file = AsyncMock(
            return_value="documents/2025-00042/3.0/document.md"
        )

        service = URSGeneratorService(
            async_session,
            storage_service=mock_storage,
        )
        report = await service.execute()

        # Verify report structure for existing document
        assert report.is_new_document is False
        assert report.version_number == 3  # Previous max was 2, so next is 3
        assert report.document_id == 100
        assert report.document_uuid == "2025-00042"
        assert report.document_title == URS_DOCUMENT_TITLE
        assert report.tags_applied == ["URS", "ALC-GOV"]
        assert report.workflow_state == "Draft"
        assert report.requirement_count >= 40
        assert report.module_count >= 1
        assert report.total_duration_ms >= 0
