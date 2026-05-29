"""Unit tests for DocumentService RBAC integration.

Tests cover:
- check_document_access delegates to RBACService
- search_documents excludes documents by permission template
- "Most restrictive wins" policy enforcement
- Backward compatibility when no RBACService is configured

References:
    - Requirements 13.1, 13.2, 13.3
    - Task 10.2: Integrate RBAC with Document Access
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.document import Document
from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.models.user import Role
from alcoabase.services.document_service import DocumentService
from alcoabase.services.rbac import AccessDenied, AccessGranted, RBACService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage_service() -> AsyncMock:
    """Create a mock StorageService."""
    storage = AsyncMock()
    storage.upload_file = AsyncMock()
    storage.download_file = AsyncMock(return_value=b"file content")
    storage.delete_file = AsyncMock()
    return storage


@pytest.fixture
def mock_uuid_service() -> AsyncMock:
    """Create a mock UUIDService."""
    uuid_svc = AsyncMock()
    uuid_svc.generate_document_uuid = AsyncMock(return_value="2025-00001")
    return uuid_svc


@pytest.fixture
def mock_rbac_service() -> AsyncMock:
    """Create a mock RBACService."""
    rbac = AsyncMock(spec=RBACService)
    return rbac


@pytest.fixture
def document_service_with_rbac(
    mock_storage_service: AsyncMock,
    mock_uuid_service: AsyncMock,
    mock_rbac_service: AsyncMock,
) -> DocumentService:
    """Create a DocumentService with mocked RBAC service."""
    return DocumentService(
        storage_service=mock_storage_service,
        uuid_service=mock_uuid_service,
        rbac_service=mock_rbac_service,
    )


@pytest.fixture
def document_service_no_rbac(
    mock_storage_service: AsyncMock,
    mock_uuid_service: AsyncMock,
) -> DocumentService:
    """Create a DocumentService without RBAC service (backward compatible)."""
    return DocumentService(
        storage_service=mock_storage_service,
        uuid_service=mock_uuid_service,
    )


@pytest.fixture
def sample_document() -> Document:
    """Create a sample document for testing."""
    return Document(
        id=1,
        document_uuid="2025-00001",
        title="Test SOP",
        folder_path="/sops",
        document_type="SOP",
        current_status="Draft",
        created_by=1,
        company_id=1,
    )


# ---------------------------------------------------------------------------
# Test: check_document_access
# ---------------------------------------------------------------------------


class TestCheckDocumentAccess:
    """Tests for DocumentService.check_document_access()."""

    @pytest.mark.asyncio
    async def test_delegates_to_rbac_service(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
        sample_document: Document,
    ) -> None:
        """check_document_access delegates to RBACService.check_document_access."""
        mock_rbac_service.check_document_access.return_value = AccessGranted(
            user_id=1, resource="documents", action="read"
        )
        session = AsyncMock()

        result = await document_service_with_rbac.check_document_access(
            session=session,
            document=sample_document,
            user_id=1,
            company_id=1,
            action="read",
        )

        assert result is True
        mock_rbac_service.check_document_access.assert_awaited_once_with(
            user_id=1,
            company_id=1,
            document=sample_document,
            action="read",
            session=session,
        )

    @pytest.mark.asyncio
    async def test_returns_false_when_denied(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
        sample_document: Document,
    ) -> None:
        """check_document_access returns False when RBAC denies access."""
        mock_rbac_service.check_document_access.return_value = AccessDenied(
            user_id=1,
            resource="documents",
            action="approve",
            reason="Template denies approve for member.",
        )
        session = AsyncMock()

        result = await document_service_with_rbac.check_document_access(
            session=session,
            document=sample_document,
            user_id=1,
            company_id=1,
            action="approve",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_no_rbac_service_allows_access(
        self,
        document_service_no_rbac: DocumentService,
        sample_document: Document,
    ) -> None:
        """Without RBACService configured, access is always granted (backward compat)."""
        session = AsyncMock()

        result = await document_service_no_rbac.check_document_access(
            session=session,
            document=sample_document,
            user_id=1,
            company_id=1,
            action="read",
        )

        assert result is True


# ---------------------------------------------------------------------------
# Test: search_documents with RBAC filtering
# ---------------------------------------------------------------------------


class TestSearchDocumentsRBACFiltering:
    """Tests for RBAC-aware document search filtering."""

    @pytest.mark.asyncio
    async def test_excludes_restricted_document_types(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
    ) -> None:
        """Documents with restricted types are excluded from search results."""
        # Setup: user has "member" role, template restricts SOP type
        member_role = Role(
            id=1,
            name="member",
            permissions={"documents": ["create", "read", "update"]},
            company_id=1,
            is_system=True,
        )
        mock_rbac_service.get_role_for_user.return_value = member_role

        # Template that doesn't grant "read" to "member"
        template = PermissionTemplate(
            id=1,
            name="Restricted SOP",
            document_type="SOP",
            role_permissions={
                "system_admin": ["read", "write", "approve"],
                "doc_admin": ["read", "write"],
                # "member" not listed → excluded
            },
            company_id=1,
            created_by=1,
        )

        session = AsyncMock()

        # Mock the template query
        templates_result = MagicMock()
        templates_scalars = MagicMock()
        templates_scalars.all.return_value = [template]
        templates_result.scalars.return_value = templates_scalars

        # Mock the count query (returns 0 after filtering)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        # Mock the items query
        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(
            side_effect=[templates_result, count_result, items_result]
        )

        result = await document_service_with_rbac.search_documents(
            session=session,
            user_id=1,
            company_id=1,
        )

        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_no_exclusion_when_template_grants_read(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
    ) -> None:
        """Documents are not excluded when template grants read to user's role."""
        member_role = Role(
            id=1,
            name="member",
            permissions={"documents": ["create", "read", "update"]},
            company_id=1,
            is_system=True,
        )
        mock_rbac_service.get_role_for_user.return_value = member_role

        # Template that grants "read" to "member"
        template = PermissionTemplate(
            id=1,
            name="Open SOP",
            document_type="SOP",
            role_permissions={
                "system_admin": ["read", "write", "approve"],
                "member": ["read"],
            },
            company_id=1,
            created_by=1,
        )

        session = AsyncMock()

        # Template query returns template with read access for member
        templates_result = MagicMock()
        templates_scalars = MagicMock()
        templates_scalars.all.return_value = [template]
        templates_result.scalars.return_value = templates_scalars

        # Count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 5

        # Items query
        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(
            side_effect=[templates_result, count_result, items_result]
        )

        result = await document_service_with_rbac.search_documents(
            session=session,
            user_id=1,
            company_id=1,
        )

        # No exclusion, so total reflects all documents
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_no_filtering_without_user_id(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
    ) -> None:
        """Without user_id, no RBAC filtering is applied."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 10

        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await document_service_with_rbac.search_documents(
            session=session,
            user_id=None,
            company_id=None,
        )

        assert result["total"] == 10
        # get_role_for_user should not be called
        mock_rbac_service.get_role_for_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_filtering_without_rbac_service(
        self,
        document_service_no_rbac: DocumentService,
    ) -> None:
        """Without RBACService, no filtering is applied even with user_id."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 10

        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await document_service_no_rbac.search_documents(
            session=session,
            user_id=1,
            company_id=1,
        )

        assert result["total"] == 10

    @pytest.mark.asyncio
    async def test_no_role_excludes_all_template_types(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
    ) -> None:
        """When user has no role, all template-governed types are excluded."""
        mock_rbac_service.get_role_for_user.return_value = None

        session = AsyncMock()

        # Query for all template document types
        doc_types_result = MagicMock()
        doc_types_scalars = MagicMock()
        doc_types_scalars.all.return_value = ["SOP", "Report"]
        doc_types_result.scalars.return_value = doc_types_scalars

        # Count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        # Items query
        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(
            side_effect=[doc_types_result, count_result, items_result]
        )

        result = await document_service_with_rbac.search_documents(
            session=session,
            user_id=1,
            company_id=1,
        )

        assert result["total"] == 0


# ---------------------------------------------------------------------------
# Test: Most restrictive wins policy
# ---------------------------------------------------------------------------


class TestMostRestrictiveWinsPolicy:
    """Tests verifying the 'most restrictive wins' policy."""

    @pytest.mark.asyncio
    async def test_base_role_denies_template_irrelevant(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
        sample_document: Document,
    ) -> None:
        """If base role denies, template check is not needed — access denied."""
        mock_rbac_service.check_document_access.return_value = AccessDenied(
            user_id=1,
            resource="documents",
            action="delete",
            reason="Missing permission: delete on documents",
        )
        session = AsyncMock()

        result = await document_service_with_rbac.check_document_access(
            session=session,
            document=sample_document,
            user_id=1,
            company_id=1,
            action="delete",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_both_grant_access_allowed(
        self,
        document_service_with_rbac: DocumentService,
        mock_rbac_service: AsyncMock,
        sample_document: Document,
    ) -> None:
        """Access granted only when BOTH base role AND template allow."""
        mock_rbac_service.check_document_access.return_value = AccessGranted(
            user_id=1, resource="documents", action="read"
        )
        session = AsyncMock()

        result = await document_service_with_rbac.check_document_access(
            session=session,
            document=sample_document,
            user_id=1,
            company_id=1,
            action="read",
        )

        assert result is True
