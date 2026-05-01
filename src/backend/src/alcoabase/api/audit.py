"""Audit trail API endpoints.

This module provides:
- GET /api/audit/{record_type}/{record_id}: Retrieve version history
- DELETE blocking: All DELETE attempts on audit endpoints return HTTP 403

The audit endpoints enforce immutability by explicitly blocking any
DELETE requests, ensuring the audit trail cannot be tampered with.

References:
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
    - CFR 21 Part 11: electronic records and electronic signatures
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.services.audit_service import AuditService, RECORD_TYPE_MODEL_MAP

router = APIRouter(prefix="/audit", tags=["Audit"])

# Singleton service instance
_audit_service = AuditService()


# ---------------------------------------------------------------------------
# DELETE blocking — all DELETE attempts on audit endpoints return HTTP 403
# ---------------------------------------------------------------------------


@router.api_route(
    "/{path:path}",
    methods=["DELETE"],
    include_in_schema=False,
)
async def block_audit_delete(path: str) -> Response:
    """Block all DELETE requests on audit endpoints.

    Any attempt to delete audit trail entries is rejected with HTTP 403
    to enforce immutability of the audit trail.

    Args:
        path: The requested path (captured but unused).

    Raises:
        HTTPException: Always raises HTTP 403 Forbidden.
    """
    raise HTTPException(
        status_code=403,
        detail="Deletion of audit trail entries is forbidden. "
        "Audit records are immutable per ALCOA+ and CFR 21 Part 11.",
    )


# ---------------------------------------------------------------------------
# GET /api/audit/{record_type}/{record_id} — version history retrieval
# ---------------------------------------------------------------------------


@router.get(
    "/{record_type}/{record_id}",
    response_model=list[dict[str, Any]],
    summary="Get audit version history",
    description=(
        "Retrieve the complete version history for a specific record "
        "in chronological order. Returns all version entries with "
        "monotonically increasing transaction IDs."
    ),
)
async def get_audit_history(
    record_type: str,
    record_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    """Retrieve version history for a specific record.

    Returns all version entries in chronological order (ascending
    transaction_id) for the specified record type and ID.

    Supported record types:
        - documents
        - templates
        - reports
        - workflows
        - signatures
        - training_tasks
        - training_records

    Args:
        record_type: The type of record to query.
        record_id: The primary key ID of the record.
        request: The incoming HTTP request.
        session: Database session (injected).

    Returns:
        List of version entry dictionaries in chronological order.

    Raises:
        HTTPException: 400 if record_type is not supported.
        HTTPException: 404 if the record does not exist.
    """
    # Validate record type
    if record_type not in RECORD_TYPE_MODEL_MAP:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported record type: '{record_type}'. "
                f"Supported types: {list(RECORD_TYPE_MODEL_MAP.keys())}"
            ),
        )

    # Check record exists
    exists = await _audit_service.get_record_exists(
        session, record_type, record_id
    )
    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Record not found: {record_type}/{record_id}",
        )

    # Retrieve version history
    try:
        versions = await _audit_service.get_version_history(
            session, record_type, record_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return versions
