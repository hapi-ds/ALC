"""FastAPI router for virtual folder management endpoints.

Provides CRUD operations for virtual folders and dynamic document
filtering based on tag_filter expressions.

References:
    - Design doc Section 3: Virtual Folder Design
    - Requirements 2.5-2.8: Virtual folder operations
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.document import Document, DocumentTag
from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.schemas.document import (
    DocumentResponse,
    VirtualFolderCreate,
    VirtualFolderResponse,
    VirtualFolderUpdate,
)

router = APIRouter(prefix="/virtual-folders", tags=["Virtual Folders"])


@router.post("", response_model=VirtualFolderResponse, status_code=201)
async def create_virtual_folder(
    data: VirtualFolderCreate,
    user_id: int = Query(default=1),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> VirtualFolderResponse:
    """Create a new virtual folder.

    Args:
        data: Virtual folder creation data.
        user_id: ID of the creating user.
        session: Database session dependency.

    Returns:
        The created virtual folder.

    Raises:
        HTTPException: 400 if name already exists.
    """
    # Check for duplicate name
    existing = await session.execute(
        select(VirtualFolder).where(VirtualFolder.name == data.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=f"Virtual folder '{data.name}' already exists.")

    folder = VirtualFolder(
        name=data.name,
        tag_filter=data.tag_filter,
        sort_order=data.sort_order,
        is_system_default=False,
        created_by=user_id,
    )
    # TODO: Set company_id=tenant.company_id on created resource
    session.add(folder)
    await session.flush()

    return VirtualFolderResponse.model_validate(folder)


@router.get("", response_model=list[VirtualFolderResponse])
async def list_virtual_folders(
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[VirtualFolderResponse]:
    """List all virtual folders (system defaults + user-created).

    Args:
        session: Database session dependency.

    Returns:
        List of all virtual folders.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    result = await session.execute(
        select(VirtualFolder).order_by(VirtualFolder.is_system_default.desc(), VirtualFolder.name)
    )
    folders = result.scalars().all()
    return [VirtualFolderResponse.model_validate(f) for f in folders]


@router.get("/{folder_id}", response_model=VirtualFolderResponse)
async def get_virtual_folder(
    folder_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> VirtualFolderResponse:
    """Get a virtual folder by ID.

    Args:
        folder_id: The virtual folder primary key.
        session: Database session dependency.

    Returns:
        The virtual folder.

    Raises:
        HTTPException: 404 if not found.
    """
    result = await session.execute(
        select(VirtualFolder).where(VirtualFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Virtual folder not found.")
    return VirtualFolderResponse.model_validate(folder)


@router.get("/{folder_id}/documents", response_model=list[DocumentResponse])
async def get_virtual_folder_documents(
    folder_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[DocumentResponse]:
    """Get documents matching a virtual folder's tag_filter.

    Executes a dynamic query against the document table filtered by
    the virtual folder's tag_filter expression.

    Args:
        folder_id: The virtual folder primary key.
        offset: Number of results to skip.
        limit: Maximum number of results to return.
        session: Database session dependency.

    Returns:
        List of documents matching the filter.

    Raises:
        HTTPException: 404 if folder not found.
    """
    # Get the virtual folder
    result = await session.execute(
        select(VirtualFolder).where(VirtualFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Virtual folder not found.")

    # Build dynamic query from tag_filter
    # TODO: Pass tenant.company_id to service layer for filtering
    # Ensure tag filter matches only documents within the same company
    query = select(Document).options(
        selectinload(Document.tags),
        selectinload(Document.versions),
    )

    tag_filter = folder.tag_filter or {}

    # Filter by tags
    if "tags" in tag_filter and tag_filter["tags"]:
        tags_list = tag_filter["tags"]
        query = query.join(DocumentTag).where(DocumentTag.tag.in_(tags_list))

    # Filter by status
    if "status" in tag_filter and tag_filter["status"]:
        query = query.where(Document.current_status == tag_filter["status"])

    query = query.offset(offset).limit(limit).order_by(Document.created_at.desc())

    doc_result = await session.execute(query)
    documents = list(doc_result.scalars().unique().all())

    return [DocumentResponse.model_validate(doc) for doc in documents]


@router.put("/{folder_id}", response_model=VirtualFolderResponse)
async def update_virtual_folder(
    folder_id: int,
    data: VirtualFolderUpdate,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> VirtualFolderResponse:
    """Update a virtual folder.

    Args:
        folder_id: The virtual folder primary key.
        data: Fields to update.
        session: Database session dependency.

    Returns:
        The updated virtual folder.

    Raises:
        HTTPException: 404 if not found, 400 if name conflict.
    """
    result = await session.execute(
        select(VirtualFolder).where(VirtualFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Virtual folder not found.")

    # Check name uniqueness if updating name
    if data.name is not None and data.name != folder.name:
        existing = await session.execute(
            select(VirtualFolder).where(VirtualFolder.name == data.name)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=400, detail=f"Virtual folder '{data.name}' already exists.")
        folder.name = data.name

    if data.tag_filter is not None:
        folder.tag_filter = data.tag_filter

    if data.sort_order is not None:
        folder.sort_order = data.sort_order

    await session.flush()
    return VirtualFolderResponse.model_validate(folder)


@router.delete("/{folder_id}", status_code=204)
async def delete_virtual_folder(
    folder_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> None:
    """Delete a virtual folder.

    System default folders cannot be deleted (returns HTTP 400).

    Args:
        folder_id: The virtual folder primary key.
        session: Database session dependency.

    Raises:
        HTTPException: 404 if not found, 400 if system default.
    """
    result = await session.execute(
        select(VirtualFolder).where(VirtualFolder.id == folder_id)
    )
    folder = result.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Virtual folder not found.")

    if folder.is_system_default:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete system default virtual folders.",
        )

    await session.delete(folder)
    await session.flush()
