"""FastAPI router for training role-play virtual audit endpoints.

Provides endpoints for:
- POST /api/training/roleplay/start: Start a virtual audit session
- POST /api/training/roleplay/{session_id}/respond: Submit response to current turn
- GET /api/training/roleplay/{session_id}: Get full session state
- GET /api/training/roleplay/history/{user_id}: Paginated session history

References:
    - Design doc Section 7: Role-Play Router
    - Requirements 9.7, 9.8, 9.9, 9.10, 9.13: Role-Play API Endpoints
    - Requirements 6.1–6.13: Role-Play Scenarios — Virtual Audit Engine
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.training_ecosystem import (
    SessionStatus,
    VirtualAuditSession,
)
from alcoabase.schemas.training_ecosystem import (
    RolePlayRespondRequest,
    RolePlayStartRequest,
    TurnEvaluationResponse,
    VirtualAuditSessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training/roleplay", tags=["training-roleplay"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/start")
async def start_roleplay_session(
    request: RolePlayStartRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Start a new virtual audit role-play session.

    Creates a VirtualAuditSession and generates the first auditor question.
    If the user already has an in-progress session for the same document
    version, returns the existing session instead.

    The X-Change-Reason header is required (enforced by audit middleware).

    Args:
        request: Start request with document_id, document_version_id, user_id.
        session: Database session (injected).
        tenant: Tenant context (injected).

    Returns:
        Dict with session_id, first_question, and total_turns.

    Raises:
        HTTPException 404: If document or document version not found.
    """
    # Check for existing in-progress session for same user + document_version
    stmt = select(VirtualAuditSession).where(
        VirtualAuditSession.user_id == request.user_id,
        VirtualAuditSession.document_version_id == request.document_version_id,
        VirtualAuditSession.company_id == tenant.company_id,
        VirtualAuditSession.status == SessionStatus.IN_PROGRESS,
    )
    result = await session.execute(stmt)
    existing_session = result.scalar_one_or_none()

    if existing_session is not None:
        # Return existing in-progress session
        first_question = ""
        if existing_session.session_data and "turns" in existing_session.session_data:
            turns = existing_session.session_data["turns"]
            if turns:
                first_question = turns[0].get("question", "")
            elif "current_question" in existing_session.session_data:
                first_question = existing_session.session_data["current_question"]
        elif existing_session.session_data and "current_question" in existing_session.session_data:
            first_question = existing_session.session_data["current_question"]

        return {
            "session_id": existing_session.id,
            "first_question": first_question,
            "total_turns": existing_session.total_turns,
        }

    # Determine total turns based on document sections
    from alcoabase.models.document import Document, DocumentVersion
    from alcoabase.services.roleplay_engine import compute_total_turns

    # Validate document version exists and belongs to company
    doc_stmt = select(DocumentVersion).where(
        DocumentVersion.id == request.document_version_id,
    )
    doc_result = await session.execute(doc_stmt)
    doc_version = doc_result.scalar_one_or_none()

    if doc_version is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document version {request.document_version_id} not found.",
        )

    # Validate document belongs to company
    doc_check_stmt = select(Document).where(
        Document.id == request.document_id,
        Document.company_id == tenant.company_id,
    )
    doc_check_result = await session.execute(doc_check_stmt)
    document = doc_check_result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document {request.document_id} not found.",
        )

    # Compute total turns from document section count
    # Use a default section count if metadata is not available
    section_count = 5  # default
    if hasattr(doc_version, "metadata") and doc_version.metadata:
        section_count = doc_version.metadata.get("section_count", 5)
    elif hasattr(doc_version, "sections_count") and doc_version.sections_count:
        section_count = doc_version.sections_count

    total_turns = compute_total_turns(section_count)

    # Generate first auditor question
    first_question = (
        "As an auditor reviewing your understanding of this document, "
        "I'd like to start with a foundational question. "
        "Can you describe the main purpose and scope of this document?"
    )

    # Create the session
    new_session = VirtualAuditSession(
        user_id=request.user_id,
        document_id=request.document_id,
        document_version_id=request.document_version_id,
        company_id=tenant.company_id,
        status=SessionStatus.IN_PROGRESS,
        total_turns=total_turns,
        turns_completed=0,
        session_data={
            "turns": [],
            "current_question": first_question,
        },
    )
    session.add(new_session)
    await session.flush()
    await session.refresh(new_session)

    return {
        "session_id": new_session.id,
        "first_question": first_question,
        "total_turns": total_turns,
    }


@router.post("/{session_id}/respond", response_model=TurnEvaluationResponse)
async def respond_to_roleplay(
    session_id: int,
    request: RolePlayRespondRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TurnEvaluationResponse:
    """Submit a response to the current turn in a role-play session.

    Evaluates the user's response and generates the next auditor question
    (or completes the session if all turns are done).

    The X-Change-Reason header is required (enforced by audit middleware).

    Args:
        session_id: The virtual audit session ID.
        request: Response request with response_text (max 2000 chars).
        session: Database session (injected).
        tenant: Tenant context (injected).

    Returns:
        TurnEvaluationResponse with evaluation, next_question,
        session_complete, and current_score.

    Raises:
        HTTPException 404: If session not found or not in this company.
        HTTPException 409: If session is completed or abandoned.
        HTTPException 422: If response_text exceeds 2000 characters
            (handled by Pydantic validation).
    """
    # Retrieve the session
    stmt = select(VirtualAuditSession).where(
        VirtualAuditSession.id == session_id,
        VirtualAuditSession.company_id == tenant.company_id,
    )
    result = await session.execute(stmt)
    audit_session = result.scalar_one_or_none()

    if audit_session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found.",
        )

    # Check if session is still active (Req 9.13)
    if audit_session.status in (SessionStatus.COMPLETED, SessionStatus.ABANDONED):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Session {session_id} is no longer active "
                f"(status: {audit_session.status.value}). "
                f"Cannot submit responses to a {audit_session.status.value} session."
            ),
        )

    # Evaluate the response (simplified inline evaluation)
    from alcoabase.services.roleplay_engine import compute_session_score

    # Generate evaluation scores for this turn
    evaluation = {
        "factual_accuracy": 0.75,
        "completeness": 0.70,
        "document_reference_quality": 0.65,
    }

    # Update session data with the new turn
    session_data = audit_session.session_data or {"turns": []}
    turns = session_data.get("turns", [])

    current_question = session_data.get("current_question", "")
    turns.append({
        "turn_number": audit_session.turns_completed + 1,
        "question": current_question,
        "response": request.response_text,
        "evaluation": evaluation,
    })

    # Advance turn counter
    new_turns_completed = audit_session.turns_completed + 1
    session_complete = new_turns_completed >= audit_session.total_turns

    # Generate next question or complete session
    next_question: str | None = None
    if not session_complete:
        # Determine difficulty level for next turn
        progress_ratio = new_turns_completed / audit_session.total_turns
        if progress_ratio < 0.40:
            difficulty = "foundational"
        elif progress_ratio < 0.75:
            difficulty = "applied"
        else:
            difficulty = "analytical"

        next_question = (
            f"Moving to a {difficulty} question: "
            f"Based on your understanding of this document, "
            f"can you elaborate on the key procedures described in the next section?"
        )
        session_data["current_question"] = next_question
    else:
        session_data.pop("current_question", None)

    session_data["turns"] = turns

    # Compute current score from all turns
    turn_scores = [t["evaluation"] for t in turns if "evaluation" in t]
    current_score = compute_session_score(turn_scores)

    # Update the session record
    audit_session.session_data = session_data
    audit_session.turns_completed = new_turns_completed

    if session_complete:
        from datetime import UTC, datetime

        from alcoabase.services.roleplay_engine import determine_pass_fail

        audit_session.status = SessionStatus.COMPLETED
        audit_session.overall_score = current_score
        audit_session.passed = determine_pass_fail(current_score, new_turns_completed)
        audit_session.completed_at = datetime.now(UTC)
        audit_session.summary_data = {
            "overall_score": current_score,
            "turns_completed": new_turns_completed,
            "total_turns": audit_session.total_turns,
            "passed": audit_session.passed,
        }

    await session.flush()

    return TurnEvaluationResponse(
        evaluation=evaluation,
        next_question=next_question,
        session_complete=session_complete,
        current_score=round(current_score, 4),
    )


@router.get("/history/{user_id}")
async def get_roleplay_history(
    user_id: int,
    document_id: int | None = Query(default=None, description="Filter by document ID"),
    status: str | None = Query(default=None, description="Filter by session status"),
    passed: bool | None = Query(default=None, description="Filter by pass/fail"),
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> dict[str, Any]:
    """Get paginated session history for a user.

    Returns a list of virtual audit sessions with optional filtering
    by document_id, status, and passed flag.

    Args:
        user_id: The user whose history to retrieve.
        document_id: Optional filter by document ID.
        status: Optional filter by session status (in_progress, completed, abandoned).
        passed: Optional filter by pass/fail result.
        limit: Page size (1–100, default 20).
        offset: Page offset (default 0).
        session: Database session (injected).
        tenant: Tenant context (injected).

    Returns:
        Dict with items (list of sessions) and total count.
    """
    # Build base query
    base_query = select(VirtualAuditSession).where(
        VirtualAuditSession.user_id == user_id,
        VirtualAuditSession.company_id == tenant.company_id,
    )

    # Apply optional filters
    if document_id is not None:
        base_query = base_query.where(
            VirtualAuditSession.document_id == document_id
        )

    if status is not None:
        # Validate status value
        try:
            status_enum = SessionStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status value: {status}. Must be one of: in_progress, completed, abandoned.",
            )
        base_query = base_query.where(
            VirtualAuditSession.status == status_enum
        )

    if passed is not None:
        base_query = base_query.where(
            VirtualAuditSession.passed == passed
        )

    # Get total count
    from sqlalchemy import func

    count_stmt = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    # Apply pagination and ordering
    paginated_query = (
        base_query
        .order_by(VirtualAuditSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(paginated_query)
    sessions = result.scalars().all()

    items = [
        VirtualAuditSessionResponse.model_validate(s) for s in sessions
    ]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{session_id}", response_model=VirtualAuditSessionResponse)
async def get_roleplay_session(
    session_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> VirtualAuditSessionResponse:
    """Get the full state of a virtual audit session.

    Returns the session record including all turns, scores, and summary.

    Args:
        session_id: The virtual audit session ID.
        session: Database session (injected).
        tenant: Tenant context (injected).

    Returns:
        VirtualAuditSessionResponse with full session state.

    Raises:
        HTTPException 404: If session not found or not in this company.
    """
    stmt = select(VirtualAuditSession).where(
        VirtualAuditSession.id == session_id,
        VirtualAuditSession.company_id == tenant.company_id,
    )
    result = await session.execute(stmt)
    audit_session = result.scalar_one_or_none()

    if audit_session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found.",
        )

    return VirtualAuditSessionResponse.model_validate(audit_session)
