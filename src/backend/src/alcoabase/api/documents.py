"""FastAPI router for document management endpoints.

Provides endpoints for document creation, versioning, retrieval,
search operations, and AI-powered document generation.

References:
    - Design doc Section 3: Document Service API
    - Design doc Section 10: Document Generator
    - Requirements 1, 2: Document CRUD and versioning
    - Task 14.6: POST /api/documents/generate endpoint
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.document import (
    DocumentResponse,
    DocumentSearchResponse,
    DocumentVersionCreate,
    DocumentVersionResponse,
)
from alcoabase.services.document_generator import DocumentGenerator
from alcoabase.services.document_reviewer import (
    DocumentReviewer,
    ReviewReport as ReviewReportModel,
)
from alcoabase.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])

# Module-level service instance
_document_service = DocumentService()


def get_document_service() -> DocumentService:
    """Provide the DocumentService instance as a dependency.

    Returns:
        The module-level DocumentService instance.
    """
    return _document_service


@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    folder_path: str = Form(...),
    document_type: str = Form(...),
    tags: str = Form(default=""),
    user_id: int = Form(default=1),
    session: AsyncSession = Depends(get_db_session),
    service: DocumentService = Depends(get_document_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentResponse:
    """Create a new document with file upload.

    Generates a Document-UUID, stores the file in MinIO, and persists
    metadata in PostgreSQL.

    Args:
        file: The uploaded file.
        title: Document title.
        folder_path: Logical folder path.
        document_type: Classification type.
        tags: Comma-separated list of tags.
        user_id: ID of the creating user.
        session: Database session dependency.
        service: DocumentService dependency.

    Returns:
        The created document with metadata.

    Raises:
        HTTPException: 500 if storage or database operation fails.
    """
    file_data = await file.read()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    content_type = file.content_type or "application/octet-stream"

    try:
        document = await service.create_document(
            session=session,
            file_data=file_data,
            title=title,
            folder_path=folder_path,
            document_type=document_type,
            tags=tag_list,
            user_id=user_id,
            content_type=content_type,
            company_id=tenant.company_id,
        )
        # Re-fetch with eager loading for serialization
        document = await service.get_document(session, document.document_uuid)
        return DocumentResponse.model_validate(document)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{document_uuid}/versions",
    response_model=DocumentVersionResponse,
    status_code=201,
)
async def create_version(
    document_uuid: str,
    file: UploadFile = File(...),
    version_type: str = Form(...),
    change_reason: str = Form(...),
    user_id: int = Form(default=1),
    session: AsyncSession = Depends(get_db_session),
    service: DocumentService = Depends(get_document_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentVersionResponse:
    """Create a new version of an existing document.

    Args:
        document_uuid: The Document-UUID of the target document.
        file: The new file upload.
        version_type: Either "major" or "minor".
        change_reason: Reason for the version change.
        user_id: ID of the uploading user.
        session: Database session dependency.
        service: DocumentService dependency.

    Returns:
        The created document version.

    Raises:
        HTTPException: 404 if document not found, 400 for invalid input.
    """
    file_data = await file.read()
    content_type = file.content_type or "application/octet-stream"

    try:
        # TODO: Pass tenant.company_id to service layer for filtering
        version = await service.create_version(
            session=session,
            document_uuid=document_uuid,
            file_data=file_data,
            version_type=version_type,
            change_reason=change_reason,
            user_id=user_id,
            content_type=content_type,
        )
        return DocumentVersionResponse.model_validate(version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_uuid}", response_model=DocumentResponse)
async def get_document(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    service: DocumentService = Depends(get_document_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentResponse:
    """Retrieve a document by its Document-UUID.

    Args:
        document_uuid: The Document-UUID to look up.
        session: Database session dependency.
        service: DocumentService dependency.

    Returns:
        The document with metadata, tags, and versions.

    Raises:
        HTTPException: 404 if document not found.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    document = await service.get_document(session, document_uuid)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_uuid}")
    return DocumentResponse.model_validate(document)


@router.get("/{document_uuid}/versions/{major_version}/{minor_version}", response_model=DocumentVersionResponse)
async def get_version(
    document_uuid: str,
    major_version: int,
    minor_version: int,
    session: AsyncSession = Depends(get_db_session),
    service: DocumentService = Depends(get_document_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentVersionResponse:
    """Retrieve a specific version of a document.

    Args:
        document_uuid: The Document-UUID of the document.
        major_version: Major version number.
        minor_version: Minor version number.
        session: Database session dependency.
        service: DocumentService dependency.

    Returns:
        The document version.

    Raises:
        HTTPException: 404 if version not found.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    version = await service.get_version(session, document_uuid, major_version, minor_version)
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {major_version}.{minor_version} not found for document {document_uuid}",
        )
    return DocumentVersionResponse.model_validate(version)


@router.get("", response_model=DocumentSearchResponse)
async def search_documents(
    tag: str | None = Query(default=None),
    folder_path: str | None = Query(default=None),
    document_uuid: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    service: DocumentService = Depends(get_document_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentSearchResponse:
    """Search documents with filtering and pagination.

    Args:
        tag: Optional tag to filter by.
        folder_path: Optional folder path to filter by.
        document_uuid: Optional Document-UUID to filter by.
        offset: Number of results to skip.
        limit: Maximum number of results to return.
        session: Database session dependency.
        service: DocumentService dependency.

    Returns:
        Search results with items and total count.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    result = await service.search_documents(
        session=session,
        tag=tag,
        folder_path=folder_path,
        document_uuid=document_uuid,
        offset=offset,
        limit=limit,
    )
    items = [DocumentResponse.model_validate(doc) for doc in result["items"]]
    return DocumentSearchResponse(items=items, total=result["total"])


# ---------------------------------------------------------------------------
# Document Generation (Task 14.6)
# ---------------------------------------------------------------------------


class DocumentGenerateRequest(BaseModel):
    """Request schema for AI document generation."""

    instructions: str = Field(..., min_length=1, description="Generation instructions")
    user_id: int = Field(..., description="ID of the requesting user")
    agent_id: str = Field(..., description="Agent definition ID to use")
    document_type: str = Field(default="SOP", description="Type of document to generate")
    title: str | None = Field(default=None, description="Optional title for the document")
    chat_history: list[dict[str, str]] | None = Field(
        default=None, description="Optional chat history for context"
    )


class GenerationProvenanceResponse(BaseModel):
    """Response schema for generation provenance."""

    generation_id: str
    source_document_uuids: list[str]
    agent_id: str
    user_id: int
    timestamp: str
    instructions: str
    chat_history_used: bool


class DocumentGenerateResponse(BaseModel):
    """Response schema for document generation."""

    content: str
    title: str
    document_type: str
    provenance: GenerationProvenanceResponse
    draft_uuid: str | None = None


_document_generator: DocumentGenerator | None = None


def get_document_generator() -> DocumentGenerator:
    """Provide the DocumentGenerator instance as a dependency."""
    global _document_generator
    if _document_generator is None:
        _document_generator = DocumentGenerator()
    return _document_generator


@router.post("/generate", response_model=DocumentGenerateResponse, status_code=201)
async def generate_document(
    request: DocumentGenerateRequest,
    generator: DocumentGenerator = Depends(get_document_generator),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentGenerateResponse:
    """Generate a new document using AI (DSPy pipeline placeholder).

    Retrieves relevant source documents, analyzes their style, and
    generates a new document matching the source format. The generated
    document is stored as a Draft with full provenance tracking.

    Args:
        request: Generation parameters including instructions and agent ID.
        generator: DocumentGenerator dependency.

    Returns:
        Generated document content with provenance metadata.

    Raises:
        HTTPException: 500 if generation fails.
    """
    try:
        # TODO: Pass tenant.company_id to service layer for filtering
        result = await generator.generate(
            instructions=request.instructions,
            user_id=request.user_id,
            agent_id=request.agent_id,
            document_type=request.document_type,
            title=request.title,
            chat_history=request.chat_history,
        )

        return DocumentGenerateResponse(
            content=result.content,
            title=result.title,
            document_type=result.document_type,
            provenance=GenerationProvenanceResponse(
                generation_id=result.provenance.generation_id,
                source_document_uuids=result.provenance.source_document_uuids,
                agent_id=result.provenance.agent_id,
                user_id=result.provenance.user_id,
                timestamp=result.provenance.timestamp.isoformat(),
                instructions=result.provenance.instructions,
                chat_history_used=result.provenance.chat_history_used,
            ),
            draft_uuid=result.draft_uuid,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document generation failed: {e}")


# ---------------------------------------------------------------------------
# Document Review (Task 21.6)
# ---------------------------------------------------------------------------


class DocumentReviewRequest(BaseModel):
    """Request schema for AI document review."""

    review_agent_id: str | None = Field(
        default=None, description="Optional explicit review agent ID"
    )
    user_id: int = Field(default=1, description="ID of the requesting user")


class ReviewFindingResponse(BaseModel):
    """Response schema for a single review finding."""

    id: str
    severity: str
    chapter: str
    page_or_section: str
    description: str
    recommendation: str


class ChapterResultResponse(BaseModel):
    """Response schema for a chapter result."""

    chapter_name: str
    required: bool
    present: bool
    complete: bool
    order_correct: bool
    notes: str


class DocumentReviewResponse(BaseModel):
    """Response schema for document review."""

    id: str
    document_uuid: str
    document_version: str
    review_agent_id: str
    review_agent_name: str
    reviewer_user_id: int
    timestamp: str
    overall_status: str
    chapter_results: list[ChapterResultResponse]
    findings: list[ReviewFindingResponse]
    summary: str


_document_reviewer: DocumentReviewer | None = None


def get_document_reviewer() -> DocumentReviewer:
    """Provide the DocumentReviewer instance as a dependency."""
    global _document_reviewer
    if _document_reviewer is None:
        _document_reviewer = DocumentReviewer()
    return _document_reviewer


@router.post(
    "/{document_uuid}/review",
    response_model=DocumentReviewResponse,
    status_code=200,
)
async def review_document(
    document_uuid: str,
    request: DocumentReviewRequest = DocumentReviewRequest(),
    reviewer: DocumentReviewer = Depends(get_document_reviewer),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentReviewResponse:
    """Trigger AI-powered document review.

    Resolves the appropriate review agent (by document tag or explicit ID),
    runs structure and content checks, and returns a structured ReviewReport.

    Args:
        document_uuid: The Document-UUID of the document to review.
        request: Review parameters including optional agent ID.
        reviewer: DocumentReviewer dependency.

    Returns:
        Structured review report with chapter results and findings.

    Raises:
        HTTPException: 400 if no matching review agent found.
        HTTPException: 404 if document not found.
    """
    try:
        # TODO: Pass tenant.company_id to service layer for filtering
        # Placeholder: In production, would load document text from storage
        # For now, use empty text to demonstrate the flow
        report = reviewer.review_document(
            document_uuid=document_uuid,
            document_version="1.0",
            document_text="",
            document_tag="SOP",
            user_id=request.user_id,
            review_agent_id=request.review_agent_id,
        )

        return DocumentReviewResponse(
            id=report.id,
            document_uuid=report.document_uuid,
            document_version=report.document_version,
            review_agent_id=report.review_agent_id,
            review_agent_name=report.review_agent_name,
            reviewer_user_id=report.reviewer_user_id,
            timestamp=report.timestamp.isoformat(),
            overall_status=report.overall_status.value,
            chapter_results=[
                ChapterResultResponse(
                    chapter_name=r.chapter_name,
                    required=r.required,
                    present=r.present,
                    complete=r.complete,
                    order_correct=r.order_correct,
                    notes=r.notes,
                )
                for r in report.chapter_results
            ],
            findings=[
                ReviewFindingResponse(
                    id=f.id,
                    severity=f.severity.value,
                    chapter=f.chapter,
                    page_or_section=f.page_or_section,
                    description=f.description,
                    recommendation=f.recommendation,
                )
                for f in report.findings
            ],
            summary=report.summary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document review failed: {e}")
