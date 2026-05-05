"""FastAPI router for company management endpoints.

Provides CRUD operations for company entities including creation,
listing, retrieval, update, deactivation, and reactivation.

Endpoints:
    POST /api/companies - Create a new company
    GET /api/companies - List all companies
    GET /api/companies/{slug} - Get company details
    PATCH /api/companies/{slug} - Update company config
    POST /api/companies/{slug}/deactivate - Deactivate company
    POST /api/companies/{slug}/reactivate - Reactivate company

References:
    - Design doc: .kiro/specs/multi-tenancy/design.md
    - Requirements: 1.1, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 13.1, 13.4
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.models.company import Company
from alcoabase.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["Companies"])


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    payload: CompanyCreate,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Create a new company.

    Creates a new tenant entity with the provided configuration.
    The slug must be unique across all companies.

    Args:
        payload: Company creation request body.
        session: Database session.

    Returns:
        The created company record.

    Raises:
        HTTPException: 409 if a company with the same slug already exists.
    """
    # TODO: Add auth guard — System Admin only
    company = Company(
        slug=payload.slug,
        display_name=payload.display_name,
        regulatory_framework=payload.regulatory_framework,
        audit_config=payload.audit_config,
    )
    session.add(company)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Company with slug '{payload.slug}' already exists.",
        )

    return CompanyResponse.model_validate(company)


@router.get("", response_model=list[CompanyResponse])
async def list_companies(
    session: AsyncSession = Depends(get_db_session),
) -> list[CompanyResponse]:
    """List all companies.

    Returns all company records regardless of active status.

    Args:
        session: Database session.

    Returns:
        List of all companies.
    """
    # TODO: Add auth guard — System Admin only
    result = await session.execute(select(Company))
    companies = result.scalars().all()
    return [CompanyResponse.model_validate(c) for c in companies]


@router.get("/{slug}", response_model=CompanyResponse)
async def get_company(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Get company details by slug.

    Args:
        slug: The unique URL-safe identifier of the company.
        session: Database session.

    Returns:
        The company record.

    Raises:
        HTTPException: 404 if company not found.
    """
    # TODO: Add auth guard — System Admin or Company Member
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    return CompanyResponse.model_validate(company)


@router.patch("/{slug}", response_model=CompanyResponse)
async def update_company(
    slug: str,
    payload: CompanyUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Update company configuration.

    Allows partial updates to display_name, regulatory_framework,
    and audit_config.

    Args:
        slug: The unique URL-safe identifier of the company.
        payload: Company update request body (partial).
        session: Database session.

    Returns:
        The updated company record.

    Raises:
        HTTPException: 404 if company not found.
    """
    # TODO: Add auth guard — System Admin or Company Admin
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return CompanyResponse.model_validate(company)

    for field, value in update_data.items():
        setattr(company, field, value)

    await session.flush()
    return CompanyResponse.model_validate(company)


@router.post("/{slug}/deactivate", response_model=CompanyResponse)
async def deactivate_company(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Deactivate a company.

    Sets is_active to False. Deactivated companies block all member
    access via the tenant context dependency.

    Args:
        slug: The unique URL-safe identifier of the company.
        session: Database session.

    Returns:
        The updated company record.

    Raises:
        HTTPException: 404 if company not found.
        HTTPException: 409 if company is already inactive.
    """
    # TODO: Add auth guard — System Admin only
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    if not company.is_active:
        raise HTTPException(
            status_code=409, detail="Company is already inactive."
        )

    company.is_active = False
    await session.flush()
    return CompanyResponse.model_validate(company)


@router.post("/{slug}/reactivate", response_model=CompanyResponse)
async def reactivate_company(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Reactivate a company.

    Sets is_active to True. Reactivated companies restore member
    access without requiring re-assignment of memberships.

    Args:
        slug: The unique URL-safe identifier of the company.
        session: Database session.

    Returns:
        The updated company record.

    Raises:
        HTTPException: 404 if company not found.
        HTTPException: 409 if company is already active.
    """
    # TODO: Add auth guard — System Admin only
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    if company.is_active:
        raise HTTPException(
            status_code=409, detail="Company is already active."
        )

    company.is_active = True
    await session.flush()
    return CompanyResponse.model_validate(company)
