"""FastAPI router for admin permission template management endpoints.

Provides CRUD endpoints for permission templates that define role-action
mappings for document types. All endpoints require appropriate RBAC
permissions and operate within the tenant's company scope.

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md §3
    - Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.schemas.admin_permission_templates import (
    PermissionTemplateCreateRequest,
    PermissionTemplateListResponse,
    PermissionTemplateResponse,
    PermissionTemplateUpdateRequest,
)
from alcoabase.services.permission_template import PermissionTemplateService

router = APIRouter(prefix="/admin/permission-templates", tags=["Admin Permission Templates"])

_permission_template_service = PermissionTemplateService()


def get_permission_template_service() -> PermissionTemplateService:
    """Provide the PermissionTemplateService instance as a dependency.

    Returns:
        The module-level PermissionTemplateService instance.
    """
    return _permission_template_service


@router.get("", response_model=PermissionTemplateListResponse)
async def list_permission_templates(
    ctx: TenantContext = Depends(require_permission("templates", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: PermissionTemplateService = Depends(get_permission_template_service),
) -> PermissionTemplateListResponse:
    """List all permission templates for the current company.

    Requires ``templates:read`` permission.

    Args:
        ctx: Resolved tenant context with company_id and user_id.
        session: Active async database session.
        service: PermissionTemplateService dependency.

    Returns:
        List of permission templates with active document counts.
    """
    templates = await service.list_templates(
        company_id=ctx.company_id,
        session=session,
    )
    return PermissionTemplateListResponse(
        templates=[PermissionTemplateResponse(**t) for t in templates]
    )


@router.post("", response_model=PermissionTemplateResponse, status_code=201)
async def create_permission_template(
    payload: PermissionTemplateCreateRequest,
    ctx: TenantContext = Depends(require_permission("templates", "create")),
    session: AsyncSession = Depends(get_db_session),
    service: PermissionTemplateService = Depends(get_permission_template_service),
) -> PermissionTemplateResponse:
    """Create a new permission template for the current company.

    Requires ``templates:create`` permission and ``X-Change-Reason`` header.

    Args:
        payload: Validated creation request with name, description,
            document_type, and role_permissions.
        ctx: Resolved tenant context with company_id and user_id.
        session: Active async database session.
        service: PermissionTemplateService dependency.

    Returns:
        The newly created permission template.

    Raises:
        HTTPException: 409 if a template with the same name already exists.
    """
    template = await service.create_template(
        payload=payload,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        session=session,
    )
    return PermissionTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        document_type=template.document_type,
        role_permissions=template.role_permissions,
        is_default=template.is_default,
        created_by=template.created_by,
        created_at=template.created_at,
        active_document_count=0,
    )


@router.get("/{template_id}", response_model=PermissionTemplateResponse)
async def get_permission_template(
    template_id: int,
    ctx: TenantContext = Depends(require_permission("templates", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: PermissionTemplateService = Depends(get_permission_template_service),
) -> PermissionTemplateResponse:
    """Get a single permission template by ID.

    Requires ``templates:read`` permission.

    Args:
        template_id: The database ID of the template to retrieve.
        ctx: Resolved tenant context with company_id and user_id.
        session: Active async database session.
        service: PermissionTemplateService dependency.

    Returns:
        The permission template with active document count.

    Raises:
        HTTPException: 404 if the template is not found or does not
            belong to the current company.
    """
    template_data = await service.get_template_detail(
        template_id=template_id,
        company_id=ctx.company_id,
        session=session,
    )
    return PermissionTemplateResponse(**template_data)


@router.patch("/{template_id}", response_model=PermissionTemplateResponse)
async def update_permission_template(
    template_id: int,
    payload: PermissionTemplateUpdateRequest,
    ctx: TenantContext = Depends(require_permission("templates", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: PermissionTemplateService = Depends(get_permission_template_service),
) -> PermissionTemplateResponse:
    """Update an existing permission template.

    Requires ``templates:update`` permission and ``X-Change-Reason`` header.
    Only provided fields are updated.

    Args:
        template_id: The database ID of the template to update.
        payload: Validated update request with optional fields.
        ctx: Resolved tenant context with company_id and user_id.
        session: Active async database session.
        service: PermissionTemplateService dependency.

    Returns:
        The updated permission template.

    Raises:
        HTTPException: 404 if the template is not found.
        HTTPException: 409 if the new name conflicts with an existing template.
    """
    template = await service.update_template(
        template_id=template_id,
        payload=payload,
        company_id=ctx.company_id,
        session=session,
    )
    # Fetch active document count for the response
    active_count = await service._get_active_document_count(
        document_type=template.document_type,
        company_id=ctx.company_id,
        session=session,
    )
    return PermissionTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        document_type=template.document_type,
        role_permissions=template.role_permissions,
        is_default=template.is_default,
        created_by=template.created_by,
        created_at=template.created_at,
        active_document_count=active_count,
    )


@router.delete("/{template_id}", status_code=204)
async def delete_permission_template(
    template_id: int,
    ctx: TenantContext = Depends(require_permission("templates", "delete")),
    session: AsyncSession = Depends(get_db_session),
    service: PermissionTemplateService = Depends(get_permission_template_service),
) -> None:
    """Delete a permission template if no active documents use it.

    Requires ``templates:delete`` permission and ``X-Change-Reason`` header.
    Deletion is rejected with 409 if active documents are associated with
    the template's document type.

    Args:
        template_id: The database ID of the template to delete.
        ctx: Resolved tenant context with company_id and user_id.
        session: Active async database session.
        service: PermissionTemplateService dependency.

    Raises:
        HTTPException: 404 if the template is not found.
        HTTPException: 409 if active documents are using this template.
    """
    await service.delete_template(
        template_id=template_id,
        company_id=ctx.company_id,
        session=session,
    )
