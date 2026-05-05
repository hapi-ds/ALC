"""FastAPI router for electronic signature operations.

Provides endpoints for:
- Signing documents with re-authentication
- Retrieving signature records for a document

References:
    - Design doc Section 6: Signature Service (PAdES)
    - CFR 21 Part 11: Electronic records and signatures
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.signature import (
    SignatureRecordResponse,
    SignRequest,
    SignResponse,
    SignatureStampResponse,
)
from alcoabase.services.signature_service import SignatureService
from alcoabase.services.storage_service import StorageService

router = APIRouter(prefix="/signatures", tags=["Signatures"])


def _get_signature_service() -> SignatureService:
    """Dependency provider for SignatureService."""
    return SignatureService()


def _get_storage_service() -> StorageService:
    """Dependency provider for StorageService."""
    return StorageService()


@router.post("/sign", response_model=SignResponse)
async def sign_document(
    request: SignRequest,
    session: AsyncSession = Depends(get_db_session),
    signature_service: SignatureService = Depends(_get_signature_service),
    storage_service: StorageService = Depends(_get_storage_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> SignResponse:
    """Sign a document with re-authentication enforcement.

    Performs the full signing flow:
    1. Verify user credentials (re-authentication)
    2. Download the PDF from storage
    3. Apply PAdES-style signature with visual stamp
    4. Upload signed PDF back to storage
    5. Record signature event in audit trail

    Args:
        request: Sign request with document_uuid, transition, reason, password.
        session: Database session (injected).
        signature_service: Signature service (injected).
        storage_service: Storage service (injected).

    Returns:
        SignResponse with signature hash and stamp data.

    Raises:
        HTTPException: 401 if re-authentication fails.
        HTTPException: 400 if document not found or empty.
    """
    from sqlalchemy import select

    from alcoabase.models.document import Document, DocumentVersion

    # Resolve document and version
    doc_result = await session.execute(
        select(Document).where(Document.document_uuid == request.document_uuid)
    )
    document = doc_result.scalar_one_or_none()
    if document is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"Document not found: {request.document_uuid}",
        )

    version_result = await session.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == request.document_version_id
        )
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"Document version not found: {request.document_version_id}",
        )

    # Download PDF from storage
    pdf_bytes = await storage_service.download_file(version.storage_key)

    # Sign the document (includes re-authentication)
    # Note: user_id would come from JWT token in production;
    # for now we extract from the session context
    # Using a placeholder user_id=1 for the API; in production this comes from auth
    user_id = 1  # TODO: Extract from JWT auth context
    # TODO: Pass tenant.company_id to service layer for filtering

    result = await signature_service.sign_document(
        session=session,
        pdf_bytes=pdf_bytes,
        user_id=user_id,
        password=request.password,
        document_uuid=request.document_uuid,
        document_version_id=request.document_version_id,
        transition=request.transition,
        reason=request.reason,
    )

    # Upload signed PDF back to storage
    signed_key = f"{version.storage_key}.signed"
    await storage_service.upload_file(
        key=signed_key,
        data=result.signed_pdf,
        content_type="application/pdf",
    )

    return SignResponse(
        success=result.success,
        signature_hash=result.signature_hash,
        signature_record_id=result.signature_record_id,
        stamp=SignatureStampResponse(
            signer_name=result.stamp.signer_name,
            signed_at=result.stamp.signed_at,
            reason=result.stamp.reason,
            transition=result.stamp.transition,
        ),
    )


@router.get(
    "/records/{document_uuid}",
    response_model=list[SignatureRecordResponse],
)
async def get_signature_records(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    signature_service: SignatureService = Depends(_get_signature_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[SignatureRecordResponse]:
    """Get all signature records for a document.

    Args:
        document_uuid: The document's unique identifier.
        session: Database session (injected).
        signature_service: Signature service (injected).

    Returns:
        List of signature records ordered by signing time.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    records = await signature_service.get_signature_records(session, document_uuid)
    return [
        SignatureRecordResponse.model_validate(record) for record in records
    ]
