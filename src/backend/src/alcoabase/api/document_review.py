"""FastAPI router for AI-generated document review endpoints.

Provides endpoints for approving/rejecting AI-generated documents and
listing generated documents with filtering and pagination.

Endpoints:
    - POST /api/documents/{document_id}/review: Approve or reject a generated document
    - GET /api/documents/generated: List AI-generated documents (filterable, paginated)

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 6.2, 6.3, 6.4, 6.5, 6.7, 6.8, 6.9, 6.10
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.document_generation import (
    DocumentReviewRequest,
    DocumentReviewResponse,
    GeneratedDocumentListResponse,
    GeneratedDocumentResponse,
)
from alcoabase.services.generated_doc_review import GeneratedDocReviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Document Review"])


# ---------------------------------------------------------------------------
# Dependency: GeneratedDocReviewService
# ---------------------------------------------------------------------------

_generated_doc_review_service: GeneratedDocReviewService | None = None


def set_generated_doc_review_service(service: GeneratedDocReviewService) -> None:
    """Set the module-level GeneratedDocReviewService instance.

    Called during application startup to wire the service into the router.

    Args:
        service: The initialized GeneratedDocReviewService instance.
    """
    global _generated_doc_review_service
    _generated_doc_review_service = service


def get_generated_doc_review_service() -> GeneratedDocReviewService:
    """Provide the GeneratedDocReviewService as a FastAPI dependency.

    Returns:
        The module-level GeneratedDocReviewService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _generated_doc_review_service is None:
        raise HTTPException(
            status_code=503,
            detail="Generated document review service is not available.",
        )
    return _generated_doc_review_service


# ---------------------------------------------------------------------------
# Document Review Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{document_id}/review",
    response_model=DocumentReviewResponse,
    status_code=200,
)
async def review_document(
    document_id: int,
    request: DocumentReviewRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: GeneratedDocReviewService = Depends(get_generated_doc_review_service),
) -> DocumentReviewResponse:
    """Approve or reject an AI-generated document.

    Transitions the document's ContentStatus based on the review action:
    - approve: Draft → Review (enters standard BPMN workflow)
    - reject: ContentStatus → rejected, document remains in Draft

    Requires X-Company-Id and X-Change-Reason headers.

    Args:
        document_id: ID of the document to review.
        request: Review action and optional comments.
        tenant: Resolved tenant context (company_id, user_id).
        service: GeneratedDocReviewService dependency.

    Returns:
        DocumentReviewResponse with updated document_id, current_status,
        and content_status.

    Raises:
        HTTPException 404: If document not found in the company scope.
        HTTPException 409: If document has already been reviewed.
        HTTPException 422: If document is not AI-generated or comment too long.
    """
    try:
        result = await service.review_document(
            document_id=document_id,
            action=request.action,
            reviewer_id=tenant.user_id,
            company_id=tenant.company_id,
            reviewer_comments=request.reviewer_comments,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found.",
        )
    except ValueError as e:
        error_msg = str(e)
        if "already been reviewed" in error_msg:
            raise HTTPException(
                status_code=409,
                detail=error_msg,
            )
        # Non-AI-generated document or other validation error → 422
        raise HTTPException(
            status_code=422,
            detail=error_msg,
        )

    return DocumentReviewResponse(
        document_id=result["document_id"],
        current_status=result["current_status"],
        content_status=result["content_status"],
    )


@router.get(
    "/generated",
    response_model=GeneratedDocumentListResponse,
    status_code=200,
)
async def list_generated_documents(
    content_status: str | None = Query(
        default=None,
        description="Filter by content review status (pending_review, approved, rejected)",
    ),
    document_type: str | None = Query(
        default=None,
        description="Filter by document classification type",
    ),
    start_date: str | None = Query(
        default=None,
        description="Filter from date (ISO 8601 format)",
    ),
    end_date: str | None = Query(
        default=None,
        description="Filter to date (ISO 8601 format)",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: GeneratedDocReviewService = Depends(get_generated_doc_review_service),
) -> GeneratedDocumentListResponse:
    """List AI-generated documents for the current company.

    Returns documents that have an associated GenerationProvenance record,
    with optional filtering by content_status, document_type, and date range.
    Results are paginated.

    Requires X-Company-Id header.

    Args:
        content_status: Optional filter by content review status.
        document_type: Optional filter by document type.
        start_date: Optional ISO 8601 date string for range start.
        end_date: Optional ISO 8601 date string for range end.
        limit: Maximum number of results (default 20, max 100).
        offset: Number of results to skip (default 0).
        tenant: Resolved tenant context (company_id).
        service: GeneratedDocReviewService dependency.

    Returns:
        GeneratedDocumentListResponse with items and total count.
    """
    documents, total = await service.list_generated_documents(
        company_id=tenant.company_id,
        content_status=content_status,
        document_type=document_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    items = [
        GeneratedDocumentResponse(
            id=doc["id"],
            document_uuid=doc["document_uuid"],
            title=doc["title"],
            document_type=doc["document_type"],
            current_status=doc["current_status"],
            content_status=doc["content_status"],
            template_name=doc["template_name"],
            generated_at=doc["generated_at"],
            generation_duration_ms=doc["generation_duration_ms"],
        )
        for doc in documents
    ]

    return GeneratedDocumentListResponse(items=items, total=total)
