"""FastAPI router for template management endpoints.

Provides endpoints for template creation, retrieval, listing, and
PDF generation (download offline template).

References:
    - Design doc Section 4: Template Service
    - Requirements 3: Template CRUD and immutability
    - Requirements 4: Offline PDF Generation from Templates
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.schemas.template import (
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
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
) -> list[TemplateResponse]:
    """List all templates.

    Args:
        session: Database session dependency.
        service: TemplateService dependency.

    Returns:
        List of all templates with metadata and fields.
    """
    templates = await service.list_templates(session)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.post("/{document_uuid}/download-pdf")
async def download_pdf(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    service: TemplateService = Depends(get_template_service),
    pdf_gen: PDFGenerator = Depends(get_pdf_generator),
    storage: StorageService = Depends(get_storage_service),
) -> Response:
    """Generate and download a fillable AcroForm PDF from a template.

    Validates that the template has ReadOnly status before generating.
    Stores the generated PDF in MinIO and returns it as a file download.

    Args:
        document_uuid: The Document-UUID of the template.
        session: Database session dependency.
        service: TemplateService dependency.
        pdf_gen: PDFGenerator dependency.
        storage: StorageService dependency.

    Returns:
        PDF file as a downloadable response.

    Raises:
        HTTPException: 404 if template not found, 400 if not ReadOnly.
    """
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

    # Generate the PDF
    pdf_bytes = pdf_gen.generate_offline_pdf(template)

    # Store in MinIO for audit trail
    storage_key = f"templates/{document_uuid}/offline-template.pdf"
    await storage.upload_file(
        key=storage_key,
        data=pdf_bytes,
        content_type="application/pdf",
    )

    # Return as file download
    filename = f"{template.name.replace(' ', '_')}_{document_uuid}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )
