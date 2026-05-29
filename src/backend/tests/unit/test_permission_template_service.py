"""Unit tests for PermissionTemplateService.

Tests cover:
- Template CRUD operations (create, update, delete, list, get detail)
- Name uniqueness validation within a company
- Deletion guard (active documents prevent deletion)
- Default template seeding ("Internal SOP", "External Supplier File")
- active_document_count computation

References:
    - Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.schemas.admin_permission_templates import (
    PermissionTemplateCreateRequest,
    PermissionTemplateUpdateRequest,
    RoleActionMapping,
)
from alcoabase.services.permission_template import PermissionTemplateService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> PermissionTemplateService:
    """Create a PermissionTemplateService instance."""
    return PermissionTemplateService()


@pytest.fixture
def create_payload() -> PermissionTemplateCreateRequest:
    """Create a valid template creation payload."""
    return PermissionTemplateCreateRequest(
        name="Test Template",
        description="A test permission template",
        document_type="SOP",
        role_permissions=[
            RoleActionMapping(role="system_admin", actions=["read", "write", "approve"]),
            RoleActionMapping(role="doc_admin", actions=["read", "write", "approve"]),
            RoleActionMapping(role="member", actions=["read"]),
            RoleActionMapping(role="viewer", actions=["read"]),
        ],
    )


@pytest.fixture
def update_payload() -> PermissionTemplateUpdateRequest:
    """Create a valid template update payload."""
    return PermissionTemplateUpdateRequest(
        name="Updated Template",
        description="Updated description",
        role_permissions=[
            RoleActionMapping(role="system_admin", actions=["read", "write", "approve"]),
            RoleActionMapping(role="member", actions=["read", "write"]),
        ],
    )


def _make_template(
    template_id: int = 1,
    name: str = "Test Template",
    document_type: str = "SOP",
    company_id: int = 1,
    is_default: bool = False,
) -> PermissionTemplate:
    """Helper to create a PermissionTemplate instance."""
    return PermissionTemplate(
        id=template_id,
        name=name,
        description="Test description",
        document_type=document_type,
        role_permissions={
            "system_admin": ["read", "write", "approve"],
            "doc_admin": ["read", "write"],
            "member": ["read"],
        },
        company_id=company_id,
        is_default=is_default,
        created_by=1,
        created_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
    )


def _mock_session_no_existing(template: PermissionTemplate | None = None) -> AsyncMock:
    """Create a mock session where name uniqueness check passes (no existing template)."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()

    # First execute: uniqueness check returns None (no conflict)
    uniqueness_result = MagicMock()
    uniqueness_result.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(return_value=uniqueness_result)
    session.refresh = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Test: Template creation (Requirement 4.1)
# ---------------------------------------------------------------------------


class TestCreateTemplate:
    """Test template creation with name uniqueness validation."""

    @pytest.mark.asyncio
    async def test_create_template_success(
        self,
        service: PermissionTemplateService,
        create_payload: PermissionTemplateCreateRequest,
    ) -> None:
        """Creating a template with a unique name should succeed."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        # Uniqueness check returns None (no conflict)
        uniqueness_result = MagicMock()
        uniqueness_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=uniqueness_result)

        result = await service.create_template(
            payload=create_payload,
            company_id=1,
            user_id=5,
            session=session,
        )

        assert result.name == "Test Template"
        assert result.description == "A test permission template"
        assert result.document_type == "SOP"
        assert result.company_id == 1
        assert result.created_by == 5
        assert result.is_default is False
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_template_stores_role_permissions_as_dict(
        self,
        service: PermissionTemplateService,
        create_payload: PermissionTemplateCreateRequest,
    ) -> None:
        """role_permissions should be stored as a dict mapping role -> actions."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        uniqueness_result = MagicMock()
        uniqueness_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=uniqueness_result)

        result = await service.create_template(
            payload=create_payload,
            company_id=1,
            user_id=5,
            session=session,
        )

        expected_perms = {
            "system_admin": ["read", "write", "approve"],
            "doc_admin": ["read", "write", "approve"],
            "member": ["read"],
            "viewer": ["read"],
        }
        assert result.role_permissions == expected_perms

    @pytest.mark.asyncio
    async def test_create_template_duplicate_name_raises_409(
        self,
        service: PermissionTemplateService,
        create_payload: PermissionTemplateCreateRequest,
    ) -> None:
        """Creating a template with a duplicate name in the same company raises 409."""
        session = AsyncMock()

        # Uniqueness check returns an existing template (conflict)
        existing_template = _make_template()
        uniqueness_result = MagicMock()
        uniqueness_result.scalar_one_or_none.return_value = existing_template
        session.execute = AsyncMock(return_value=uniqueness_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_template(
                payload=create_payload,
                company_id=1,
                user_id=5,
                session=session,
            )

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_template_same_name_different_company_succeeds(
        self,
        service: PermissionTemplateService,
        create_payload: PermissionTemplateCreateRequest,
    ) -> None:
        """Same template name in a different company should succeed."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        # Uniqueness check scoped to company_id=2 returns None
        uniqueness_result = MagicMock()
        uniqueness_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=uniqueness_result)

        result = await service.create_template(
            payload=create_payload,
            company_id=2,
            user_id=5,
            session=session,
        )

        assert result.company_id == 2
        assert result.name == "Test Template"


# ---------------------------------------------------------------------------
# Test: Template update (Requirement 4.2, 4.3)
# ---------------------------------------------------------------------------


class TestUpdateTemplate:
    """Test template update with name uniqueness on rename."""

    @pytest.mark.asyncio
    async def test_update_template_success(
        self,
        service: PermissionTemplateService,
        update_payload: PermissionTemplateUpdateRequest,
    ) -> None:
        """Updating a template with valid data should succeed."""
        template = _make_template()

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        # First execute: template lookup (get_template_or_404)
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template

        # Second execute: name uniqueness check
        uniqueness_result = MagicMock()
        uniqueness_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(side_effect=[template_result, uniqueness_result])

        result = await service.update_template(
            template_id=1,
            payload=update_payload,
            company_id=1,
            session=session,
        )

        assert result.name == "Updated Template"
        assert result.description == "Updated description"
        assert result.role_permissions == {
            "system_admin": ["read", "write", "approve"],
            "member": ["read", "write"],
        }

    @pytest.mark.asyncio
    async def test_update_template_name_conflict_raises_409(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Renaming to an existing name in the same company raises 409."""
        template = _make_template(name="Original Name")
        payload = PermissionTemplateUpdateRequest(name="Conflicting Name")

        session = AsyncMock()

        # First execute: template lookup
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template

        # Second execute: name uniqueness check finds conflict
        conflict_template = _make_template(template_id=2, name="Conflicting Name")
        uniqueness_result = MagicMock()
        uniqueness_result.scalar_one_or_none.return_value = conflict_template

        session.execute = AsyncMock(side_effect=[template_result, uniqueness_result])

        with pytest.raises(HTTPException) as exc_info:
            await service.update_template(
                template_id=1,
                payload=payload,
                company_id=1,
                session=session,
            )

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_template_same_name_no_conflict(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Updating without changing the name should not trigger uniqueness check."""
        template = _make_template(name="Same Name")
        payload = PermissionTemplateUpdateRequest(
            name="Same Name",
            description="New description",
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        # Only one execute: template lookup (no uniqueness check needed)
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template
        session.execute = AsyncMock(return_value=template_result)

        result = await service.update_template(
            template_id=1,
            payload=payload,
            company_id=1,
            session=session,
        )

        assert result.description == "New description"

    @pytest.mark.asyncio
    async def test_update_template_not_found_raises_404(
        self,
        service: PermissionTemplateService,
        update_payload: PermissionTemplateUpdateRequest,
    ) -> None:
        """Updating a non-existent template raises 404."""
        session = AsyncMock()

        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=template_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.update_template(
                template_id=999,
                payload=update_payload,
                company_id=1,
                session=session,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_partial_fields(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Updating only description should leave other fields unchanged."""
        template = _make_template(name="Original")
        original_perms = template.role_permissions.copy()
        payload = PermissionTemplateUpdateRequest(description="Only description changed")

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template
        session.execute = AsyncMock(return_value=template_result)

        result = await service.update_template(
            template_id=1,
            payload=payload,
            company_id=1,
            session=session,
        )

        assert result.name == "Original"
        assert result.description == "Only description changed"
        assert result.role_permissions == original_perms


# ---------------------------------------------------------------------------
# Test: Template deletion guard (Requirement 4.4)
# ---------------------------------------------------------------------------


class TestDeleteTemplate:
    """Test deletion guard: active documents prevent deletion."""

    @pytest.mark.asyncio
    async def test_delete_template_no_active_documents(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Deleting a template with no active documents should succeed."""
        template = _make_template()

        session = AsyncMock()
        session.delete = AsyncMock()
        session.flush = AsyncMock()

        # First execute: template lookup
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template

        # Second execute: active document count = 0
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        session.execute = AsyncMock(side_effect=[template_result, count_result])

        # Should not raise
        await service.delete_template(
            template_id=1,
            company_id=1,
            session=session,
        )

        session.delete.assert_awaited_once_with(template)
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_template_with_active_documents_raises_409(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Deleting a template with active documents raises 409."""
        template = _make_template()

        session = AsyncMock()

        # First execute: template lookup
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template

        # Second execute: active document count = 3
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3

        session.execute = AsyncMock(side_effect=[template_result, count_result])

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_template(
                template_id=1,
                company_id=1,
                session=session,
            )

        assert exc_info.value.status_code == 409
        assert "Cannot delete" in exc_info.value.detail
        assert "3 active document(s)" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_template_not_found_raises_404(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Deleting a non-existent template raises 404."""
        session = AsyncMock()

        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=template_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_template(
                template_id=999,
                company_id=1,
                session=session,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_template_wrong_company_raises_404(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Deleting a template from a different company raises 404."""
        session = AsyncMock()

        # Template lookup returns None because company_id doesn't match
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=template_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_template(
                template_id=1,
                company_id=99,
                session=session,
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Test: Default template seeding (Requirement 4.6)
# ---------------------------------------------------------------------------


class TestSeedDefaultTemplates:
    """Test seeding of default permission templates."""

    @pytest.mark.asyncio
    async def test_seeds_two_default_templates(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """seed_default_templates should create exactly two templates."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.seed_default_templates(
            company_id=1,
            user_id=1,
            session=session,
        )

        assert len(result) == 2
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_seeds_internal_sop_template(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Should create an 'Internal SOP' template with correct permissions."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.seed_default_templates(
            company_id=1,
            user_id=1,
            session=session,
        )

        sop_template = next(t for t in result if t.name == "Internal SOP")
        assert sop_template.document_type == "SOP"
        assert sop_template.is_default is True
        assert sop_template.company_id == 1
        assert sop_template.created_by == 1
        # Members can read and write
        assert "read" in sop_template.role_permissions["member"]
        assert "write" in sop_template.role_permissions["member"]
        # Doc admins can approve
        assert "approve" in sop_template.role_permissions["doc_admin"]

    @pytest.mark.asyncio
    async def test_seeds_external_supplier_file_template(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Should create an 'External Supplier File' template with correct permissions."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.seed_default_templates(
            company_id=1,
            user_id=1,
            session=session,
        )

        supplier_template = next(t for t in result if t.name == "External Supplier File")
        assert supplier_template.document_type == "Supplier"
        assert supplier_template.is_default is True
        assert supplier_template.company_id == 1
        # Members have restricted access (read only)
        assert supplier_template.role_permissions["member"] == ["read"]
        # Doc admins and system_admins can approve
        assert "approve" in supplier_template.role_permissions["doc_admin"]
        assert "approve" in supplier_template.role_permissions["system_admin"]

    @pytest.mark.asyncio
    async def test_seeded_templates_marked_as_default(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """All seeded templates should have is_default=True."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.seed_default_templates(
            company_id=1,
            user_id=1,
            session=session,
        )

        for template in result:
            assert template.is_default is True

    @pytest.mark.asyncio
    async def test_seeded_templates_scoped_to_company(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Seeded templates should be scoped to the given company."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.seed_default_templates(
            company_id=42,
            user_id=5,
            session=session,
        )

        for template in result:
            assert template.company_id == 42
            assert template.created_by == 5


# ---------------------------------------------------------------------------
# Test: List templates with active_document_count (Requirement 4.1)
# ---------------------------------------------------------------------------


class TestListTemplates:
    """Test listing templates with active document count computation."""

    @pytest.mark.asyncio
    async def test_list_templates_returns_all_for_company(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """list_templates should return all templates for the company."""
        template1 = _make_template(template_id=1, name="Template A")
        template2 = _make_template(template_id=2, name="Template B")

        session = AsyncMock()

        # First execute: list query
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [template1, template2]

        # Subsequent executes: active document count for each template
        count_result_0 = MagicMock()
        count_result_0.scalar_one.return_value = 0

        count_result_5 = MagicMock()
        count_result_5.scalar_one.return_value = 5

        session.execute = AsyncMock(
            side_effect=[list_result, count_result_0, count_result_5]
        )

        result = await service.list_templates(company_id=1, session=session)

        assert len(result) == 2
        assert result[0]["name"] == "Template A"
        assert result[0]["active_document_count"] == 0
        assert result[1]["name"] == "Template B"
        assert result[1]["active_document_count"] == 5

    @pytest.mark.asyncio
    async def test_list_templates_empty_company(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """list_templates should return empty list for company with no templates."""
        session = AsyncMock()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=list_result)

        result = await service.list_templates(company_id=1, session=session)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_templates_includes_all_fields(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Each template dict should include all expected fields."""
        template = _make_template()

        session = AsyncMock()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [template]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        session.execute = AsyncMock(side_effect=[list_result, count_result])

        result = await service.list_templates(company_id=1, session=session)

        assert len(result) == 1
        item = result[0]
        assert "id" in item
        assert "name" in item
        assert "description" in item
        assert "document_type" in item
        assert "role_permissions" in item
        assert "is_default" in item
        assert "created_by" in item
        assert "created_at" in item
        assert "active_document_count" in item
        assert item["active_document_count"] == 2


# ---------------------------------------------------------------------------
# Test: Get template detail (Requirement 4.1)
# ---------------------------------------------------------------------------


class TestGetTemplateDetail:
    """Test getting a single template with active document count."""

    @pytest.mark.asyncio
    async def test_get_template_detail_success(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """get_template_detail should return template data with active count."""
        template = _make_template()

        session = AsyncMock()

        # First execute: template lookup
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template

        # Second execute: active document count
        count_result = MagicMock()
        count_result.scalar_one.return_value = 7

        session.execute = AsyncMock(side_effect=[template_result, count_result])

        result = await service.get_template_detail(
            template_id=1,
            company_id=1,
            session=session,
        )

        assert result["id"] == 1
        assert result["name"] == "Test Template"
        assert result["active_document_count"] == 7

    @pytest.mark.asyncio
    async def test_get_template_detail_not_found_raises_404(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """get_template_detail for non-existent template raises 404."""
        session = AsyncMock()

        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=template_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_template_detail(
                template_id=999,
                company_id=1,
                session=session,
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Test: active_document_count computation
# ---------------------------------------------------------------------------


class TestActiveDocumentCount:
    """Test that active_document_count correctly excludes Archived/Obsolete."""

    @pytest.mark.asyncio
    async def test_active_count_excludes_archived_and_obsolete(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """_get_active_document_count should count only non-terminal documents."""
        session = AsyncMock()

        # The count query returns 4 (meaning 4 active documents)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 4
        session.execute = AsyncMock(return_value=count_result)

        result = await service._get_active_document_count(
            document_type="SOP",
            company_id=1,
            session=session,
        )

        assert result == 4
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_active_count_zero_when_no_documents(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """_get_active_document_count should return 0 when no matching documents."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=count_result)

        result = await service._get_active_document_count(
            document_type="Report",
            company_id=1,
            session=session,
        )

        assert result == 0

    @pytest.mark.asyncio
    async def test_active_count_used_in_deletion_guard(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """Deletion guard uses active_document_count to decide whether to allow deletion."""
        template = _make_template(document_type="SOP")

        session = AsyncMock()
        session.delete = AsyncMock()
        session.flush = AsyncMock()

        # Template lookup
        template_result = MagicMock()
        template_result.scalar_one_or_none.return_value = template

        # Active count = 1 (should block deletion)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        session.execute = AsyncMock(side_effect=[template_result, count_result])

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_template(
                template_id=1,
                company_id=1,
                session=session,
            )

        assert exc_info.value.status_code == 409
        # Ensure delete was NOT called
        session.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_count_in_list_response(
        self,
        service: PermissionTemplateService,
    ) -> None:
        """list_templates should include computed active_document_count per template."""
        template = _make_template(document_type="SOP")

        session = AsyncMock()

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [template]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 10

        session.execute = AsyncMock(side_effect=[list_result, count_result])

        result = await service.list_templates(company_id=1, session=session)

        assert result[0]["active_document_count"] == 10
