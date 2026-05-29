"""Permission template service for document-type-specific RBAC management.

Provides CRUD operations for permission templates, including name
uniqueness validation, deletion guards (active documents check), and
default template seeding for new companies.

References:
    - Phase 6.1 design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.document import Document
from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.schemas.admin_permission_templates import (
    PermissionTemplateCreateRequest,
    PermissionTemplateUpdateRequest,
    RoleActionMapping,
)

logger = logging.getLogger(__name__)


def _role_permissions_to_dict(
    role_permissions: list[RoleActionMapping],
) -> dict[str, list[str]]:
    """Convert a list of RoleActionMapping to a dict for JSON storage.

    Args:
        role_permissions: List of role-to-action mappings from the request payload.

    Returns:
        Dictionary mapping role names to their permitted action lists.
    """
    return {mapping.role: mapping.actions for mapping in role_permissions}


class PermissionTemplateService:
    """Service for permission template CRUD and lifecycle management.

    Handles creation, update, deletion (with active document guard),
    listing, detail retrieval, and default template seeding.
    """

    async def create_template(
        self,
        payload: PermissionTemplateCreateRequest,
        company_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> PermissionTemplate:
        """Create a new permission template for a company.

        Validates that the template name is unique within the company,
        then persists the template with the role_permissions stored as
        a JSON dict.

        Args:
            payload: Validated creation request with name, description,
                document_type, and role_permissions.
            company_id: The company this template belongs to.
            user_id: The user creating the template.
            session: Active async database session.

        Returns:
            The newly created PermissionTemplate instance.

        Raises:
            HTTPException: 409 if a template with the same name already
                exists in the company.
        """
        # Validate name uniqueness within company
        existing_stmt = select(PermissionTemplate).where(
            PermissionTemplate.company_id == company_id,
            PermissionTemplate.name == payload.name,
        )
        existing_result = await session.execute(existing_stmt)
        if existing_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"A permission template named '{payload.name}' already exists in this company.",
            )

        template = PermissionTemplate(
            name=payload.name,
            description=payload.description,
            document_type=payload.document_type,
            role_permissions=_role_permissions_to_dict(payload.role_permissions),
            company_id=company_id,
            is_default=False,
            created_by=user_id,
        )
        session.add(template)
        await session.flush()
        await session.refresh(template)
        return template

    async def update_template(
        self,
        template_id: int,
        payload: PermissionTemplateUpdateRequest,
        company_id: int,
        session: AsyncSession,
    ) -> PermissionTemplate:
        """Update an existing permission template.

        Validates that the template belongs to the specified company
        (ownership check). Only provided fields are updated.

        Args:
            template_id: The ID of the template to update.
            payload: Validated update request with optional fields.
            company_id: The company context for ownership validation.
            session: Active async database session.

        Returns:
            The updated PermissionTemplate instance.

        Raises:
            HTTPException: 404 if the template is not found or does not
                belong to the company.
            HTTPException: 409 if the new name conflicts with an existing
                template in the company.
        """
        template = await self._get_template_or_404(template_id, company_id, session)

        # Validate name uniqueness if name is being changed
        if payload.name is not None and payload.name != template.name:
            existing_stmt = select(PermissionTemplate).where(
                PermissionTemplate.company_id == company_id,
                PermissionTemplate.name == payload.name,
                PermissionTemplate.id != template_id,
            )
            existing_result = await session.execute(existing_stmt)
            if existing_result.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"A permission template named '{payload.name}' already exists in this company.",
                )
            template.name = payload.name

        if payload.description is not None:
            template.description = payload.description

        if payload.role_permissions is not None:
            template.role_permissions = _role_permissions_to_dict(
                payload.role_permissions
            )

        await session.flush()
        await session.refresh(template)
        return template

    async def delete_template(
        self,
        template_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> None:
        """Delete a permission template if no active documents use it.

        Performs a pre-deletion check counting active documents whose
        document_type matches the template's document_type within the
        same company. Rejects deletion with 409 if any active documents
        are found.

        Args:
            template_id: The ID of the template to delete.
            company_id: The company context for ownership validation.
            session: Active async database session.

        Raises:
            HTTPException: 404 if the template is not found or does not
                belong to the company.
            HTTPException: 409 if active documents are using this template.
        """
        template = await self._get_template_or_404(template_id, company_id, session)

        # Check for active documents using this template's document_type
        active_count = await self._get_active_document_count(
            template.document_type, company_id, session
        )
        if active_count > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot delete template '{template.name}': "
                    f"{active_count} active document(s) are using this template."
                ),
            )

        await session.delete(template)
        await session.flush()

    async def list_templates(
        self,
        company_id: int,
        session: AsyncSession,
    ) -> list[dict]:
        """Return all permission templates for a company with active document counts.

        Args:
            company_id: The company to list templates for.
            session: Active async database session.

        Returns:
            List of template data dicts including active_document_count.
        """
        stmt = select(PermissionTemplate).where(
            PermissionTemplate.company_id == company_id
        )
        result = await session.execute(stmt)
        templates = result.scalars().all()

        template_list = []
        for template in templates:
            active_count = await self._get_active_document_count(
                template.document_type, company_id, session
            )
            template_list.append(
                {
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                    "document_type": template.document_type,
                    "role_permissions": template.role_permissions,
                    "is_default": template.is_default,
                    "created_by": template.created_by,
                    "created_at": template.created_at,
                    "active_document_count": active_count,
                }
            )

        return template_list

    async def get_template_detail(
        self,
        template_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> dict:
        """Return a single template with its active document count.

        Args:
            template_id: The ID of the template to retrieve.
            company_id: The company context for ownership validation.
            session: Active async database session.

        Returns:
            Template data dict including active_document_count.

        Raises:
            HTTPException: 404 if the template is not found or does not
                belong to the company.
        """
        template = await self._get_template_or_404(template_id, company_id, session)

        active_count = await self._get_active_document_count(
            template.document_type, company_id, session
        )

        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "document_type": template.document_type,
            "role_permissions": template.role_permissions,
            "is_default": template.is_default,
            "created_by": template.created_by,
            "created_at": template.created_at,
            "active_document_count": active_count,
        }

    async def seed_default_templates(
        self,
        company_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> list[PermissionTemplate]:
        """Create the two default permission templates for a company.

        Seeds "Internal SOP" and "External Supplier File" templates with
        predefined role-action mappings as specified in Requirement 4.6.

        - Internal SOP: department members can read, doc_admins can approve.
        - External Supplier File: restricted read, doc_admins and system_admins
          can approve.

        Args:
            company_id: The company to seed templates for.
            user_id: The user performing the seeding (typically system_admin).
            session: Active async database session.

        Returns:
            List of the two created PermissionTemplate instances.
        """
        default_templates = [
            {
                "name": "Internal SOP",
                "description": "Standard Operating Procedure for internal use. "
                "Department members can read, doc_admins can approve.",
                "document_type": "SOP",
                "role_permissions": {
                    "system_admin": ["read", "write", "approve"],
                    "doc_admin": ["read", "write", "approve"],
                    "member": ["read", "write"],
                    "viewer": ["read"],
                },
            },
            {
                "name": "External Supplier File",
                "description": "Restricted access for external supplier documents. "
                "Only doc_admins and system_admins can approve.",
                "document_type": "Supplier",
                "role_permissions": {
                    "system_admin": ["read", "write", "approve"],
                    "doc_admin": ["read", "write", "approve"],
                    "member": ["read"],
                    "viewer": ["read"],
                },
            },
        ]

        created_templates: list[PermissionTemplate] = []

        for tmpl_data in default_templates:
            template = PermissionTemplate(
                name=tmpl_data["name"],
                description=tmpl_data["description"],
                document_type=tmpl_data["document_type"],
                role_permissions=tmpl_data["role_permissions"],
                company_id=company_id,
                is_default=True,
                created_by=user_id,
            )
            session.add(template)
            created_templates.append(template)

        await session.flush()
        return created_templates

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    async def _get_template_or_404(
        self,
        template_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> PermissionTemplate:
        """Load a template by ID and company, raising 404 if not found.

        Args:
            template_id: The template's database ID.
            company_id: The company context for ownership validation.
            session: Active async database session.

        Returns:
            The PermissionTemplate instance.

        Raises:
            HTTPException: 404 if the template does not exist or does not
                belong to the specified company.
        """
        stmt = select(PermissionTemplate).where(
            PermissionTemplate.id == template_id,
            PermissionTemplate.company_id == company_id,
        )
        result = await session.execute(stmt)
        template = result.scalar_one_or_none()

        if template is None:
            raise HTTPException(
                status_code=404,
                detail=f"Permission template with id {template_id} not found.",
            )

        return template

    async def _get_active_document_count(
        self,
        document_type: str,
        company_id: int,
        session: AsyncSession,
    ) -> int:
        """Count active documents matching a document type within a company.

        Active documents are those whose current_status is not in a
        terminal/archived state (i.e., not 'Archived' or 'Obsolete').

        Args:
            document_type: The document type to count.
            company_id: The company to scope the count to.
            session: Active async database session.

        Returns:
            The count of active documents.
        """
        count_stmt = select(func.count(Document.id)).where(
            Document.company_id == company_id,
            Document.document_type == document_type,
            Document.current_status.notin_(["Archived", "Obsolete"]),
        )
        count_result = await session.execute(count_stmt)
        return count_result.scalar_one()
