"""Property-based tests for tenant context resolution and membership.

Tests Properties 4, 5, 6, 14, and 15 from the multi-tenancy design document,
validating membership creation, multi-membership support, membership revocation,
tenant context resolution for multi-company users, unauthorized access rejection,
and company deactivation/reactivation behavior.

**Validates: Requirements 2.1, 2.2, 2.3, 2.5, 9.2, 9.3, 9.4, 9.5, 13.1, 13.2, 13.4**

References:
    - Design: .kiro/specs/multi-tenancy/design.md (Correctness Properties 4, 5, 6, 14, 15)
    - Requirements: .kiro/specs/multi-tenancy/requirements.md (Requirements 2, 9, 13)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import hypothesis.strategies as st
import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from sqlalchemy import create_engine, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from alcoabase.database import Base
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.user import User


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_company_slug(draw: st.DrawFn) -> str:
    """Generate a valid company slug matching ^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$.

    Returns:
        A URL-safe slug string between 3 and 100 characters.
    """
    start = draw(st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789")))
    end = draw(st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789")))
    middle_len = draw(st.integers(min_value=1, max_value=20))
    middle = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=middle_len,
            max_size=middle_len,
        )
    )
    return start + middle + end


def st_membership_role() -> st.SearchStrategy[str]:
    """Generate a valid membership role.

    Returns:
        Strategy producing one of the allowed role strings.
    """
    return st.sampled_from(["admin", "member", "viewer"])


def st_num_companies() -> st.SearchStrategy[int]:
    """Generate a number of companies for multi-membership tests.

    Returns:
        Strategy producing integers between 2 and 5.
    """
    return st.integers(min_value=2, max_value=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_session() -> tuple[Session, "Engine"]:
    """Create a fresh SQLite in-memory database session with all tables.

    Returns:
        Tuple of (session, engine) for cleanup.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


def _create_user(session: Session, user_id: int) -> User:
    """Create and persist a test user.

    Args:
        session: Active database session.
        user_id: The user ID to assign.

    Returns:
        The persisted User instance.
    """
    user = User(
        id=user_id,
        username=f"user_{user_id}",
        email=f"user_{user_id}@test.local",
        hashed_password="hashed",
        full_name=f"Test User {user_id}",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_company(session: Session, company_id: int, slug: str, is_active: bool = True) -> Company:
    """Create and persist a test company.

    Args:
        session: Active database session.
        company_id: The company ID to assign.
        slug: Unique slug for the company.
        is_active: Whether the company is active.

    Returns:
        The persisted Company instance.
    """
    company = Company(
        id=company_id,
        slug=slug,
        display_name=f"Company {slug}",
        regulatory_framework="ISO_13485",
        is_active=is_active,
    )
    session.add(company)
    session.flush()
    return company


def _create_membership(
    session: Session, user_id: int, company_id: int, role: str
) -> CompanyMembership:
    """Create and persist a company membership.

    Args:
        session: Active database session.
        user_id: The user to assign.
        company_id: The company to assign to.
        role: The membership role.

    Returns:
        The persisted CompanyMembership instance.
    """
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=role,
    )
    session.add(membership)
    session.flush()
    return membership


def _make_mock_request(user_id: int | None = None, company_id: int | None = None) -> MagicMock:
    """Create a mock FastAPI Request with specified headers.

    Args:
        user_id: Value for X-User-Id header (None to omit).
        company_id: Value for X-Company-Id header (None to omit).

    Returns:
        Mock Request object with headers.
    """
    request = MagicMock()
    headers: dict[str, str] = {}
    if user_id is not None:
        headers["X-User-Id"] = str(user_id)
    if company_id is not None:
        headers["X-Company-Id"] = str(company_id)
    mock_headers = MagicMock()
    mock_headers.get = lambda key, default=None: headers.get(key, default)
    request.headers = mock_headers
    return request


async def _make_async_session(engine) -> AsyncSession:
    """Create an async session from an async engine.

    Args:
        engine: The async SQLAlchemy engine.

    Returns:
        An active AsyncSession.
    """
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return factory()


# ---------------------------------------------------------------------------
# Property 5: Tenant context requires explicit selection for multi-company users
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 5: Tenant context requires explicit selection for multi-company users
@settings(max_examples=20)
@given(
    num_companies=st_num_companies(),
    roles=st.lists(st_membership_role(), min_size=5, max_size=5),
    slugs=st.lists(st_company_slug(), min_size=5, max_size=5, unique=True),
    selected_index=st.integers(min_value=0, max_value=4),
)
@pytest.mark.asyncio
async def test_multi_company_user_requires_explicit_selection(
    num_companies: int,
    roles: list[str],
    slugs: list[str],
    selected_index: int,
) -> None:
    """For any user with N > 1 active company memberships, a request without
    an explicit company identifier SHALL be rejected with HTTP 400, and a
    request with a valid company identifier for one of their memberships
    SHALL succeed.

    **Validates: Requirements 2.3, 9.2, 9.3, 9.4**
    """
    # Limit to actual num_companies
    actual_slugs = slugs[:num_companies]
    actual_roles = roles[:num_companies]
    target_index = selected_index % num_companies

    # Set up sync database state
    session, engine = _make_sync_session()
    try:
        user = _create_user(session, user_id=1)

        companies = []
        for i, (slug, role) in enumerate(zip(actual_slugs, actual_roles)):
            company = _create_company(session, company_id=i + 1, slug=slug)
            _create_membership(session, user_id=1, company_id=company.id, role=role)
            companies.append(company)

        session.commit()

        # Now test with async engine pointing to same in-memory DB isn't possible
        # with SQLite, so we use a file-based approach or test the logic directly.
        # Instead, create a fresh async engine and replicate the state.
        async_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session_factory = async_sessionmaker(
            bind=async_engine, class_=AsyncSession, expire_on_commit=False
        )

        # Populate async database
        async with async_session_factory() as async_session:
            async_user = User(
                id=1,
                username="user_1",
                email="user_1@test.local",
                hashed_password="hashed",
                full_name="Test User 1",
                is_active=True,
            )
            async_session.add(async_user)

            async_companies = []
            for i, (slug, role) in enumerate(zip(actual_slugs, actual_roles)):
                c = Company(
                    id=i + 1,
                    slug=slug,
                    display_name=f"Company {slug}",
                    regulatory_framework="ISO_13485",
                    is_active=True,
                )
                async_session.add(c)
                async_companies.append(c)

            await async_session.flush()

            for i, (slug, role) in enumerate(zip(actual_slugs, actual_roles)):
                m = CompanyMembership(
                    user_id=1,
                    company_id=i + 1,
                    role=role,
                )
                async_session.add(m)

            await async_session.commit()

        # Test 1: Request WITHOUT X-Company-Id should fail with 400
        async with async_session_factory() as async_session:
            request_no_company = _make_mock_request(user_id=1, company_id=None)
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant_context(request=request_no_company, session=async_session)
            assert exc_info.value.status_code == 400

        # Test 2: Request WITH valid X-Company-Id should succeed
        target_company = async_companies[target_index]
        async with async_session_factory() as async_session:
            request_with_company = _make_mock_request(
                user_id=1, company_id=target_company.id
            )
            result = await get_tenant_context(
                request=request_with_company, session=async_session
            )
            assert isinstance(result, TenantContext)
            assert result.company_id == target_company.id
            assert result.company_slug == target_company.slug
            assert result.user_id == 1
            assert result.membership_role == actual_roles[target_index]

        await async_engine.dispose()
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 14: Unauthorized company access returns forbidden
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 14: Unauthorized company access returns forbidden
@settings(max_examples=20)
@given(
    user_slug=st_company_slug(),
    other_slug=st_company_slug(),
    role=st_membership_role(),
)
@pytest.mark.asyncio
async def test_unauthorized_company_access_returns_forbidden(
    user_slug: str,
    other_slug: str,
    role: str,
) -> None:
    """For any authenticated user and any company where the user has no active
    membership, specifying that company in the X-Company-Id header SHALL result
    in HTTP 403.

    **Validates: Requirements 9.5**
    """
    # Ensure slugs are different
    if user_slug == other_slug:
        other_slug = other_slug + "x"

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Populate: user has membership in company 1, but NOT in company 2
    async with async_session_factory() as async_session:
        user = User(
            id=1,
            username="user_1",
            email="user_1@test.local",
            hashed_password="hashed",
            full_name="Test User 1",
            is_active=True,
        )
        async_session.add(user)

        company_member = Company(
            id=1,
            slug=user_slug,
            display_name=f"Company {user_slug}",
            regulatory_framework="ISO_13485",
            is_active=True,
        )
        async_session.add(company_member)

        company_other = Company(
            id=2,
            slug=other_slug,
            display_name=f"Company {other_slug}",
            regulatory_framework="GMP",
            is_active=True,
        )
        async_session.add(company_other)

        await async_session.flush()

        membership = CompanyMembership(
            user_id=1,
            company_id=1,
            role=role,
        )
        async_session.add(membership)
        await async_session.commit()

    # Request specifying company_id=2 (user has no membership there)
    async with async_session_factory() as async_session:
        request = _make_mock_request(user_id=1, company_id=2)
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_context(request=request, session=async_session)
        assert exc_info.value.status_code == 403

    await async_engine.dispose()


# ---------------------------------------------------------------------------
# Property 15: Company deactivation blocks access
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 15: Company deactivation blocks access
@settings(max_examples=20)
@given(
    slug=st_company_slug(),
    num_members=st.integers(min_value=1, max_value=5),
    roles=st.lists(st_membership_role(), min_size=5, max_size=5),
)
@pytest.mark.asyncio
async def test_company_deactivation_blocks_access_and_reactivation_restores(
    slug: str,
    num_members: int,
    roles: list[str],
) -> None:
    """For any active company with N members, after deactivation, all requests
    specifying that company's tenant context SHALL return HTTP 403, and after
    reactivation, all N members SHALL regain access without re-assignment.

    **Validates: Requirements 13.1, 13.2, 13.4**
    """
    actual_roles = roles[:num_members]

    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Populate: company with N members
    async with async_session_factory() as async_session:
        company = Company(
            id=1,
            slug=slug,
            display_name=f"Company {slug}",
            regulatory_framework="ISO_13485",
            is_active=True,
        )
        async_session.add(company)

        for i in range(num_members):
            user = User(
                id=i + 1,
                username=f"user_{i + 1}",
                email=f"user_{i + 1}@test.local",
                hashed_password="hashed",
                full_name=f"Test User {i + 1}",
                is_active=True,
            )
            async_session.add(user)

        await async_session.flush()

        for i in range(num_members):
            membership = CompanyMembership(
                user_id=i + 1,
                company_id=1,
                role=actual_roles[i],
            )
            async_session.add(membership)

        await async_session.commit()

    # Phase 1: Verify all members CAN access while company is active
    for i in range(num_members):
        async with async_session_factory() as async_session:
            request = _make_mock_request(user_id=i + 1, company_id=1)
            result = await get_tenant_context(request=request, session=async_session)
            assert isinstance(result, TenantContext)
            assert result.company_id == 1

    # Phase 2: Deactivate the company
    async with async_session_factory() as async_session:
        company_result = await async_session.execute(
            select(Company).where(Company.id == 1)
        )
        company = company_result.scalar_one()
        company.is_active = False
        await async_session.commit()

    # Phase 3: Verify all members are BLOCKED after deactivation
    for i in range(num_members):
        async with async_session_factory() as async_session:
            request = _make_mock_request(user_id=i + 1, company_id=1)
            with pytest.raises(HTTPException) as exc_info:
                await get_tenant_context(request=request, session=async_session)
            assert exc_info.value.status_code == 403

    # Phase 4: Reactivate the company
    async with async_session_factory() as async_session:
        company_result = await async_session.execute(
            select(Company).where(Company.id == 1)
        )
        company = company_result.scalar_one()
        company.is_active = True
        await async_session.commit()

    # Phase 5: Verify all members regain access without re-assignment
    for i in range(num_members):
        async with async_session_factory() as async_session:
            request = _make_mock_request(user_id=i + 1, company_id=1)
            result = await get_tenant_context(request=request, session=async_session)
            assert isinstance(result, TenantContext)
            assert result.company_id == 1
            assert result.user_id == i + 1
            assert result.membership_role == actual_roles[i]

    await async_engine.dispose()


# ---------------------------------------------------------------------------
# Property 4: Membership creation and multi-membership support
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 4: Membership creation and multi-membership support
@settings(max_examples=20)
@given(
    num_companies=st.integers(min_value=1, max_value=5),
    slugs=st.lists(st_company_slug(), min_size=5, max_size=5, unique=True),
    roles=st.lists(st_membership_role(), min_size=5, max_size=5),
)
def test_membership_creation_and_multi_membership_support(
    num_companies: int,
    slugs: list[str],
    roles: list[str],
) -> None:
    """For any valid user and any set of N distinct active companies, assigning
    the user to all N companies SHALL result in exactly N active membership
    records, each queryable independently.

    **Validates: Requirements 2.1, 2.2**
    """
    actual_slugs = slugs[:num_companies]
    actual_roles = roles[:num_companies]

    session, engine = _make_sync_session()
    try:
        # Create a user
        user = _create_user(session, user_id=1)

        # Create N distinct companies and assign the user to each
        companies = []
        for i, (slug, role) in enumerate(zip(actual_slugs, actual_roles)):
            company = _create_company(session, company_id=i + 1, slug=slug)
            _create_membership(session, user_id=1, company_id=company.id, role=role)
            companies.append(company)

        session.commit()

        # Verify exactly N active membership records exist for this user
        all_memberships = session.execute(
            select(CompanyMembership).where(
                CompanyMembership.user_id == 1,
                CompanyMembership.revoked_at.is_(None),
            )
        ).scalars().all()

        assert len(all_memberships) == num_companies

        # Verify each membership is queryable independently
        for i, company in enumerate(companies):
            membership = session.execute(
                select(CompanyMembership).where(
                    CompanyMembership.user_id == 1,
                    CompanyMembership.company_id == company.id,
                    CompanyMembership.revoked_at.is_(None),
                )
            ).scalar_one_or_none()

            assert membership is not None
            assert membership.user_id == 1
            assert membership.company_id == company.id
            assert membership.role == actual_roles[i]
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 6: Membership revocation prevents access
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 6: Membership revocation prevents access
@settings(max_examples=20)
@given(
    slug=st_company_slug(),
    role=st_membership_role(),
)
@pytest.mark.asyncio
async def test_membership_revocation_prevents_access(
    slug: str,
    role: str,
) -> None:
    """For any user with an active membership in a company, after that
    membership is revoked (revoked_at set), subsequent tenant context
    resolution specifying that company SHALL be rejected with HTTP 403.

    **Validates: Requirements 2.5**
    """
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Populate: user with active membership in a company
    async with async_session_factory() as async_session:
        user = User(
            id=1,
            username="user_1",
            email="user_1@test.local",
            hashed_password="hashed",
            full_name="Test User 1",
            is_active=True,
        )
        async_session.add(user)

        company = Company(
            id=1,
            slug=slug,
            display_name=f"Company {slug}",
            regulatory_framework="ISO_13485",
            is_active=True,
        )
        async_session.add(company)

        await async_session.flush()

        membership = CompanyMembership(
            user_id=1,
            company_id=1,
            role=role,
        )
        async_session.add(membership)
        await async_session.commit()

    # Phase 1: Verify access works BEFORE revocation
    async with async_session_factory() as async_session:
        request = _make_mock_request(user_id=1, company_id=1)
        result = await get_tenant_context(request=request, session=async_session)
        assert isinstance(result, TenantContext)
        assert result.company_id == 1
        assert result.user_id == 1

    # Phase 2: Revoke the membership (set revoked_at)
    async with async_session_factory() as async_session:
        membership_result = await async_session.execute(
            select(CompanyMembership).where(
                CompanyMembership.user_id == 1,
                CompanyMembership.company_id == 1,
            )
        )
        membership = membership_result.scalar_one()
        membership.revoked_at = datetime.now(timezone.utc)
        await async_session.commit()

    # Phase 3: Verify access is BLOCKED after revocation (HTTP 403)
    async with async_session_factory() as async_session:
        request = _make_mock_request(user_id=1, company_id=1)
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_context(request=request, session=async_session)
        assert exc_info.value.status_code == 403

    await async_engine.dispose()
