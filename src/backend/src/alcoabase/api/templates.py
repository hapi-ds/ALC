"""FastAPI router for template management endpoints.

Provides endpoints for template creation, retrieval, listing, and
PDF generation (download offline template).

References:
    - Design doc Section 4: Template Service
    - Requirements 3: Template CRUD and immutability
    - Requirements 4: Offline PDF Generation from Templates
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.template import (
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
    TemplateVersionResponse,
    VersionCreate,
)
from alcoabase.services.pdf_generator import PDFGenerator
from alcoabase.services.storage_service import StorageService
from alcoabase.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["Templates"])

# Module-level service instances
_template_service = TemplateService()
_pdf_generator = PDFGenerator()
_storage_service = StorageService()


def get_template_service() -> TemplateService:
    """Provide the TemplateService instance as a dependency.

    Returns:
        The module-level TemplateService instance.
    """
    return _template_service


def get_pdf_generator() -> PDFGenerator:
    """Provide the PDFGenerator instance as a dependency.

    Returns:
        The module-level PDFGenerator instance.
    """
    return _pdf_generator


def get_storage_service() -> StorageService:
    """Provide the StorageService instance as a dependency.

    Returns:
        The module-level StorageService instance.
    """
    return _storage_service


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    payload: TemplateCreate,
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TemplateResponse:
    """Create a new template with auto-generated UUIDs.

    Generates a Document-UUID for the template and assigns Field-UUIDs
    to all fields. The template is immediately set to ReadOnly status.

    Args:
        payload: Template creation request with name and JSON schema.
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        The created template with metadata and field UUIDs.

    Raises:
        HTTPException: 400 for invalid schema, 500 for internal errors.
    """
    try:
        template = await service.create_template(
            session=session,
            name=payload.name,
            json_schema=payload.json_schema.model_dump(),
            user_id=payload.user_id,
            company_id=tenant.company_id,
        )
        return TemplateResponse.model_validate(template)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{document_uuid}", response_model=TemplateResponse)
async def update_template(
    document_uuid: str,
    payload: TemplateUpdate,
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TemplateResponse:
    """Update a template (rejected if ReadOnly).

    Args:
        document_uuid: The Document-UUID of the template to update.
        payload: Update request with optional name and schema changes.
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        The updated template.

    Raises:
        HTTPException: 400 if template is ReadOnly, 404 if not found.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    template = await service.update_template(
        session=session,
        document_uuid=document_uuid,
        name=payload.name,
        json_schema=payload.json_schema.model_dump() if payload.json_schema else None,
    )
    return TemplateResponse.model_validate(template)


@router.get("/{document_uuid}", response_model=TemplateResponse)
async def get_template(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TemplateResponse:
    """Retrieve a template by its Document-UUID.

    Args:
        document_uuid: The Document-UUID to look up.
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        The template with metadata and fields.

    Raises:
        HTTPException: 404 if template not found.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    template = await service.get_template(session, document_uuid)
    if template is None:
        raise HTTPException(
            status_code=404, detail=f"Template not found: {document_uuid}"
        )
    return TemplateResponse.model_validate(template)


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[TemplateResponse]:
    """List all templates.

    Args:
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        List of all templates with metadata and fields.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    templates = await service.list_templates(session)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.post("/{document_uuid}/download-pdf")
async def download_pdf(
    document_uuid: str,
    version: int | None = Query(
        default=None,
        description="Specific version number to download. "
        "If omitted, downloads the active version.",
    ),
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    pdf_gen: PDFGenerator = Depends(get_pdf_generator),
    storage: StorageService = Depends(get_storage_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> Response:
    """Generate and download a fillable AcroForm PDF from a template.

    Version-aware: uses the active version when available. If a specific
    version number is provided via query parameter, downloads that version
    with a watermark annotation if it is not the active version.

    The filename includes the version number: {name}_{uuid}_v{version}.pdf

    Args:
        document_uuid: The Document-UUID of the template.
        version: Optional specific version number to download.
        session: Database session dependency.
        service: TemplateService dependency.
        pdf_gen: PDFGenerator dependency.
        storage: StorageService dependency.

    Returns:
        PDF file as a downloadable response.

    Raises:
        HTTPException: 404 if template not found or version not found,
            400 if not ReadOnly.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    template = await service.get_template(session, document_uuid)
    if template is None:
        raise HTTPException(
            status_code=404, detail=f"Template not found: {document_uuid}"
        )

    if template.status != "ReadOnly":
        raise HTTPException(
            status_code=400,
            detail="PDF generation requires a ReadOnly template. "
            "Only approved templates can be downloaded as PDF.",
        )

    # Determine which version to use for PDF generation
    is_historical = False
    version_number: int | None = None

    if version is not None:
        # Specific version requested (Requirement 13.5)
        template_version = await service.get_version(
            session, document_uuid, version
        )
        if template_version is None:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for template: {document_uuid}",
            )
        version_number = template_version.version_number
        is_historical = not template_version.is_active
    else:
        # Use active version when available (Requirements 13.1, 13.2)
        template_version = await service.get_active_version(
            session, document_uuid
        )
        if template_version is not None:
            version_number = template_version.version_number
            is_historical = False

    # Generate the PDF — pass version info for version-aware rendering
    pdf_bytes = pdf_gen.generate_offline_pdf(
        template,
        version_number=version_number,
        is_historical=is_historical,
    )

    # Build version-aware filename (Requirement 12.3)
    sanitized_name = template.name.replace(" ", "_")
    if version_number is not None:
        filename = f"{sanitized_name}_{document_uuid}_v{version_number}.pdf"
        storage_key = (
            f"templates/{document_uuid}/offline-template-v{version_number}.pdf"
        )
    else:
        filename = f"{sanitized_name}_{document_uuid}.pdf"
        storage_key = f"templates/{document_uuid}/offline-template.pdf"

    # Store in MinIO for audit trail
    await storage.upload_file(
        key=storage_key,
        data=pdf_bytes,
        content_type="application/pdf",
    )

    # Return as file download
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.post(
    "/{document_uuid}/versions",
    response_model=TemplateVersionResponse,
    status_code=201,
)
async def create_version(
    document_uuid: str,
    payload: VersionCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TemplateVersionResponse:
    """Create a new version for an existing template.

    Requires X-Change-Reason header for ALCOA+ audit compliance.
    Uses SELECT FOR UPDATE to prevent race conditions on concurrent
    version creation attempts (returns 409 on conflict).

    Args:
        document_uuid: The Document-UUID of the parent template.
        payload: Version creation request with schema and user_id.
        request: The incoming HTTP request (for header extraction).
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        The created template version with metadata and fields.

    Raises:
        HTTPException: 404 if template not found, 400 if template is not
            ReadOnly or schema is invalid, 409 if concurrent version
            creation is detected.
    """
    change_reason = request.headers.get("X-Change-Reason", "")

    version = await service.create_version(
        session=session,
        document_uuid=document_uuid,
        json_schema=payload.json_schema.model_dump(),
        user_id=payload.user_id,
        change_reason=change_reason,
    )
    return TemplateVersionResponse.model_validate(version)


@router.get(
    "/{document_uuid}/versions",
    response_model=list[TemplateVersionResponse],
)
async def list_versions(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[TemplateVersionResponse]:
    """List all versions for a template in descending order (newest first).

    Provides the complete version history for audit trail purposes.

    Args:
        document_uuid: The Document-UUID of the parent template.
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        List of all template versions with metadata and fields.

    Raises:
        HTTPException: 404 if template not found.
    """
    versions = await service.get_version_history(session, document_uuid)
    return [TemplateVersionResponse.model_validate(v) for v in versions]


@router.get(
    "/{document_uuid}/versions/{version_number}",
    response_model=TemplateVersionResponse,
)
async def get_version(
    document_uuid: str,
    version_number: int,
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TemplateVersionResponse:
    """Get a specific version by template UUID and version number.

    Args:
        document_uuid: The Document-UUID of the parent template.
        version_number: The version number to retrieve.
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        The template version with metadata and fields.

    Raises:
        HTTPException: 404 if template or version not found.
    """
    version = await service.get_version(session, document_uuid, version_number)
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version_number} not found for template: {document_uuid}",
        )
    return TemplateVersionResponse.model_validate(version)
