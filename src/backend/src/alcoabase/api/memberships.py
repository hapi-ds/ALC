"""FastAPI router for company membership management endpoints.

Provides CRUD operations for user-company memberships including
adding members, listing members, updating roles, and revoking access.

Endpoints:
    POST /api/companies/{slug}/members - Add user to company
    GET /api/companies/{slug}/members - List company members
    PATCH /api/companies/{slug}/members/{user_id} - Update member role
    DELETE /api/companies/{slug}/members/{user_id} - Revoke membership

References:
    - Design doc: .kiro/specs/multi-tenancy/design.md
    - Requirements: 2.1, 2.2, 2.4, 2.5
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.user import User
from alcoabase.schemas.company import (
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
)

router = APIRouter(prefix="/companies/{slug}/members", tags=["Memberships"])


@router.post("", response_model=MembershipResponse, status_code=201)
async def add_member(
    slug: str,
    payload: MembershipCreate,
    session: AsyncSession = Depends(get_db_session),
) -> MembershipResponse:
    """Add a user to a company.

    Creates a new membership associating the specified user with the
    company identified by slug.

    Args:
        slug: The unique URL-safe identifier of the company.
        payload: Membership creation request body (user_id, role).
        session: Database session.

    Returns:
        The created membership record.

    Raises:
        HTTPException: 404 if company not found.
        HTTPException: 404 if user not found.
        HTTPException: 409 if user is already a member of this company.
    """
    # TODO: Add auth guard — System Admin only
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    # Verify user exists
    user_result = await session.execute(
        select(User).where(User.id == payload.user_id)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    membership = CompanyMembership(
        user_id=payload.user_id,
        company_id=company.id,
        role=payload.role,
    )
    session.add(membership)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="User is already a member of this company.",
        )

    return MembershipResponse.model_validate(membership)


@router.get("", response_model=list[MembershipResponse])
async def list_members(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[MembershipResponse]:
    """List all members of a company.

    Returns all membership records for the specified company,
    including revoked memberships.

    Args:
        slug: The unique URL-safe identifier of the company.
        session: Database session.

    Returns:
        List of membership records for the company.

    Raises:
        HTTPException: 404 if company not found.
    """
    # TODO: Add auth guard — Company Admin only
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    memberships_result = await session.execute(
        select(CompanyMembership).where(
            CompanyMembership.company_id == company.id
        )
    )
    memberships = memberships_result.scalars().all()
    return [MembershipResponse.model_validate(m) for m in memberships]


@router.patch("/{user_id}", response_model=MembershipResponse)
async def update_member_role(
    slug: str,
    user_id: int,
    payload: MembershipUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> MembershipResponse:
    """Update a member's role within a company.

    Args:
        slug: The unique URL-safe identifier of the company.
        user_id: The ID of the user whose role is being updated.
        payload: Membership update request body (role).
        session: Database session.

    Returns:
        The updated membership record.

    Raises:
        HTTPException: 404 if company not found.
        HTTPException: 404 if membership not found.
    """
    # TODO: Add auth guard — System Admin or Company Admin
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    membership_result = await session.execute(
        select(CompanyMembership).where(
            CompanyMembership.company_id == company.id,
            CompanyMembership.user_id == user_id,
        )
    )
    membership = membership_result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found.")

    membership.role = payload.role
    await session.flush()
    return MembershipResponse.model_validate(membership)


@router.delete("/{user_id}", response_model=MembershipResponse)
async def revoke_membership(
    slug: str,
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> MembershipResponse:
    """Revoke a user's membership in a company.

    Sets revoked_at to the current UTC time rather than deleting
    the record, preserving audit history.

    Args:
        slug: The unique URL-safe identifier of the company.
        user_id: The ID of the user whose membership is being revoked.
        session: Database session.

    Returns:
        The updated membership record with revoked_at set.

    Raises:
        HTTPException: 404 if company not found.
        HTTPException: 404 if membership not found.
        HTTPException: 409 if membership is already revoked.
    """
    # TODO: Add auth guard — System Admin or Company Admin
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    membership_result = await session.execute(
        select(CompanyMembership).where(
            CompanyMembership.company_id == company.id,
            CompanyMembership.user_id == user_id,
        )
    )
    membership = membership_result.scalar_one_or_none()

    if membership is None:
        raise HTTPException(status_code=404, detail="Membership not found.")

    if membership.revoked_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Membership is already revoked.",
        )

    membership.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    return MembershipResponse.model_validate(membership)
