"""Pydantic request/response schemas for document endpoints.

Provides validated schemas for document creation, versioning,
retrieval, and search operations.

References:
    - Design doc Section 3: Document Service API
    - Requirements 1, 2: Document CRUD and versioning
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from alcoabase.schemas.uuid import DocumentUUID


class DocumentCreate(BaseModel):
    """Request schema for creating a new document.

    Attributes:
        title: Document title (1-500 chars).
        folder_path: Logical folder path for organization.
        document_type: Classification type (SOP, Report, Template, etc.).
        tags: List of classification tags.
    """

    title: str = Field(..., min_length=1, max_length=500)
    folder_path: str = Field(..., min_length=1, max_length=1000)
    document_type: str = Field(..., min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list)


class DocumentVersionCreate(BaseModel):
    """Request schema for creating a new document version.

    Attributes:
        version_type: Either "major" or "minor".
        change_reason: User-provided reason for the version change.
    """

    version_type: Literal["major", "minor"] = Field(
        ..., description="Version increment type: 'major' or 'minor'."
    )
    change_reason: str = Field(
        ..., min_length=1, max_length=2000, description="Reason for the version change."
    )


class DocumentTagResponse(BaseModel):
    """Response schema for a document tag.

    Attributes:
        id: Tag primary key.
        tag: Tag string value.
    """

    id: int
    tag: str

    model_config = {"from_attributes": True}


class DocumentVersionResponse(BaseModel):
    """Response schema for a document version.

    Attributes:
        id: Version primary key.
        major_version: Major version number.
        minor_version: Minor version number.
        storage_key: MinIO object key.
        file_hash: SHA-512 hash of the file.
        uploaded_by: ID of the uploading user.
        uploaded_at: Upload timestamp.
        change_reason: Reason for the version change.
    """

    id: int
    major_version: int
    minor_version: int
    storage_key: str
    file_hash: str
    uploaded_by: int
    uploaded_at: datetime | None = None
    change_reason: str | None = None

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    """Response schema for a document with metadata.

    Attributes:
        id: Document primary key.
        document_uuid: Unique identifier in YYYY-NNNNN format.
        title: Document title.
        folder_path: Logical folder path.
        document_type: Classification type.
        current_status: Current workflow state.
        created_by: ID of the creating user.
        created_at: Creation timestamp.
        tags: List of associated tags.
        versions: List of document versions.
    """

    id: int
    document_uuid: str
    title: str
    folder_path: str
    document_type: str
    current_status: str
    created_by: int
    created_at: datetime | None = None
    tags: list[DocumentTagResponse] = Field(default_factory=list)
    versions: list[DocumentVersionResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class DocumentSearchParams(BaseModel):
    """Query parameters for document search.

    Attributes:
        tag: Optional tag to filter by.
        folder_path: Optional folder path to filter by.
        document_uuid: Optional Document-UUID to filter by.
        offset: Number of results to skip.
        limit: Maximum number of results to return.
    """

    tag: str | None = None
    folder_path: str | None = None
    document_uuid: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class DocumentSearchResponse(BaseModel):
    """Response schema for document search results.

    Attributes:
        items: List of matching documents.
        total: Total number of matching documents.
    """

    items: list[DocumentResponse]
    total: int


class VirtualFolderCreate(BaseModel):
    """Request schema for creating a virtual folder.

    Attributes:
        name: Unique folder name.
        tag_filter: JSON filter expression.
        sort_order: Default sort order.
    """

    name: str = Field(..., min_length=1, max_length=200)
    tag_filter: dict = Field(..., description="Filter criteria (e.g., {'tags': ['SOP']})")
    sort_order: str = Field(default="created_at_desc", max_length=50)


class VirtualFolderUpdate(BaseModel):
    """Request schema for updating a virtual folder.

    Attributes:
        name: Updated folder name.
        tag_filter: Updated filter expression.
        sort_order: Updated sort order.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    tag_filter: dict | None = None
    sort_order: str | None = Field(default=None, max_length=50)


class VirtualFolderResponse(BaseModel):
    """Response schema for a virtual folder.

    Attributes:
        id: Folder primary key.
        name: Folder name.
        tag_filter: Filter criteria.
        sort_order: Default sort order.
        is_system_default: Whether this is a built-in folder.
        created_by: ID of the creating user.
        created_at: Creation timestamp.
    """

    id: int
    name: str
    tag_filter: dict
    sort_order: str
    is_system_default: bool
    created_by: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
